"""
晚风后端回归测试

覆盖 2026-10 巡检发现的全部 P0：
- 空库能建表（images / apikey 两列历史缺失）
- 老库能迁移（v3 的 apikey 明文列、缺 images/user_id）
- 笔记按用户隔离
- 恶意 id / images 被拒
- 置顶上限对 sync 同样生效
- 404 不再被吞成 500
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))


@pytest.fixture(scope="session")
def wf(tmp_path_factory):
    """用临时目录导入 app（导入即建库，正好验证 P0）。"""
    root = tmp_path_factory.mktemp("wanfeng")
    os.environ["WANFENG_DATA_DIR"] = str(root / "data")
    os.environ["WANFENG_LOG_DIR"] = str(root / "log")
    os.environ["WANFENG_UPLOAD_DIR"] = str(root / "uploads")
    os.environ.pop("WANFENG_RESET_KEY", None)
    import app as module

    module._client = module.app.test_client()
    return module


@pytest.fixture(scope="session")
def admin(wf):
    return {"Authorization": "Bearer " + wf.API_KEY}


@pytest.fixture(scope="session")
def user2(wf, admin):
    res = wf._client.post("/api/admin/keys", json={"label": "小明"}, headers=admin)
    assert res.status_code == 201, res.get_data(as_text=True)
    return {"Authorization": "Bearer " + res.get_json()["apikey"]}


def test_fresh_install_builds_schema(wf, admin):
    """P0：空库必须能建表，且笔记接口可用。"""
    assert wf._client.get("/api/health").status_code == 200
    res = wf._client.get("/api/notes", headers=admin)
    assert res.status_code == 200
    assert res.get_json() == {"notes": []}

    db = sqlite3.connect(str(wf.DB_PATH))
    notes_cols = {r[1] for r in db.execute("PRAGMA table_info(notes)")}
    users_cols = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    db.close()
    assert {"images", "user_id", "pinned", "pinned_at", "shared"} <= notes_cols
    assert "apikey" not in users_cols  # 新库只存哈希


def test_legacy_schema_migrates(wf):
    """老库：缺 images/user_id，users 还带 v3 的 apikey 明文列。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT NOT NULL, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, apikey TEXT NOT NULL UNIQUE, "
        "apikey_hash TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', "
        "is_admin INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, "
        "revoked INTEGER NOT NULL DEFAULT 0)"
    )
    wf.add_missing_columns(conn, "notes", wf.NOTE_MIGRATIONS)
    wf.add_missing_columns(conn, "users", wf.USER_MIGRATIONS)
    cols = wf.table_columns(conn, "notes")
    assert {"images", "user_id", "shared", "pinned", "group"} <= cols
    # v3 的 apikey 是 NOT NULL UNIQUE，写用户时必须一起填上
    uid = wf.insert_user(conn, "LEGACYKEY", "老用户", False)
    row = conn.execute("SELECT apikey, label FROM users WHERE id = ?", (uid,)).fetchone()
    assert row["apikey"] == "LEGACYKEY"
    conn.close()


def test_auth_required_and_verify(wf, admin):
    assert wf._client.get("/api/notes").status_code == 401
    assert wf._client.get("/api/notes", headers={"Authorization": "Bearer nope"}).status_code == 401
    res = wf._client.post("/api/auth/verify", json={"key": wf.API_KEY})
    assert res.status_code == 200
    assert res.get_json()["is_admin"] is True


def test_note_crud(wf, admin):
    res = wf._client.post("/api/notes", json={
        "id": "crud1", "body": "第一条", "title": "标题",
        "group": "生活", "tags": ["a", "b"], "images": [],
    }, headers=admin)
    assert res.status_code == 201
    assert res.get_json()["id"] == "crud1"

    res = wf._client.put("/api/notes/crud1", json={
        "body": "改过", "title": "标题2", "group": "生活", "tags": ["a"], "images": [],
    }, headers=admin)
    assert res.status_code == 200
    assert res.get_json()["body"] == "改过"

    assert wf._client.delete("/api/notes/crud1", headers=admin).status_code == 200
    assert wf._client.delete("/api/notes/crud1", headers=admin).status_code == 404


def test_repost_keeps_created_at_and_pin(wf, admin):
    """P1：同 id 重新 POST 不允许重置创建时间 / 置顶 / 归属。"""
    res = wf._client.post("/api/notes", json={"id": "keepme", "body": "v1"}, headers=admin)
    created = res.get_json()["created_at"]
    assert wf._client.post("/api/notes/keepme/pin", headers=admin).status_code == 200

    res = wf._client.post("/api/notes", json={"id": "keepme", "body": "v2"}, headers=admin)
    note = res.get_json()
    assert note["created_at"] == created
    assert note["pinned"] is True
    assert note["body"] == "v2"


def test_sync_does_not_clear_pin(wf, admin):
    """普通保存/同步不应该顺手把置顶清掉（前端 sync 不再带 pinned 字段）。"""
    for note in wf._client.get("/api/notes", headers=admin).get_json()["notes"]:
        if note["pinned"]:
            wf._client.post(f"/api/notes/{note['id']}/unpin", headers=admin)
    wf._client.post("/api/notes", json={"id": "pinkeep", "body": "x"}, headers=admin)
    assert wf._client.post("/api/notes/pinkeep/pin", headers=admin).status_code == 200

    wf._client.post("/api/notes/sync", json={"notes": [{"id": "pinkeep", "body": "updated"}]},
                    headers=admin)
    note = [n for n in wf._client.get("/api/notes", headers=admin).get_json()["notes"]
            if n["id"] == "pinkeep"][0]
    assert note["pinned"] is True
    assert note["body"] == "updated"


def test_tenant_isolation(wf, admin, user2):
    """P0：子用户读/改/删不到别人的笔记。"""
    wf._client.post("/api/notes", json={"id": "admin-secret", "body": "管理员的秘密"}, headers=admin)

    listed = wf._client.get("/api/notes", headers=user2).get_json()["notes"]
    assert all(n["id"] != "admin-secret" for n in listed)

    assert wf._client.delete("/api/notes/admin-secret", headers=user2).status_code == 403
    assert wf._client.put("/api/notes/admin-secret", json={"body": "改"}, headers=user2).status_code == 403
    assert wf._client.post("/api/notes", json={"id": "admin-secret", "body": "抢占"}, headers=user2).status_code == 403

    still = [n for n in wf._client.get("/api/notes", headers=admin).get_json()["notes"]
             if n["id"] == "admin-secret"]
    assert still and still[0]["body"] == "管理员的秘密"


def test_tampered_id_and_images_rejected(wf, admin):
    """P0：id / images 是前端拼 HTML 的原料，必须服务端校验。"""
    bad_id = 'x" onmouseover="alert(1)'
    assert wf._client.post("/api/notes", json={"id": bad_id, "body": "b"},
                           headers=admin).status_code == 400
    bad_img = ["x');alert(document.domain);//"]
    assert wf._client.post("/api/notes", json={"id": "img1", "body": "b", "images": bad_img},
                           headers=admin).status_code == 400
    assert wf._client.get("/api/notes/../etc/passwd", headers=admin).status_code in (400, 404)


def test_limits(wf, admin):
    res = wf._client.post("/api/notes", json={"id": "big1", "body": "A" * 200_000}, headers=admin)
    assert res.status_code == 413
    res = wf._client.post("/api/notes", json={"id": "many", "body": "b",
                                              "images": [f"{i:032x}.png" for i in range(40)]},
                          headers=admin)
    assert res.status_code == 400


def test_pin_limit_including_sync(wf, admin):
    # 先清空已有置顶，保证用例不依赖执行顺序
    for note in wf._client.get("/api/notes", headers=admin).get_json()["notes"]:
        if note["pinned"]:
            wf._client.post(f"/api/notes/{note['id']}/unpin", headers=admin)

    for i in range(4):
        wf._client.post("/api/notes", json={"id": f"pin{i}", "body": "x"}, headers=admin)
    assert wf._client.post("/api/notes/pin0/pin", headers=admin).status_code == 200
    assert wf._client.post("/api/notes/pin1/pin", headers=admin).status_code == 200
    assert wf._client.post("/api/notes/pin2/pin", headers=admin).status_code == 200
    assert wf._client.post("/api/notes/pin3/pin", headers=admin).status_code == 400

    # sync 不能成为绕过置顶上限的后门
    payload = {"notes": [{"id": f"sp{i}", "body": "synced", "pinned": True} for i in range(9)]}
    res = wf._client.post("/api/notes/sync", json=payload, headers=admin)
    assert res.status_code == 200
    pinned = [n for n in res.get_json()["notes"] if n["pinned"]]
    assert len(pinned) <= wf.MAX_PINS


def test_sync_deletes_and_validates_created_at(wf, admin):
    wf._client.post("/api/notes", json={"id": "synctarget", "body": "x"}, headers=admin)
    res = wf._client.post("/api/notes/sync", json={
        "notes": [{"id": "syncnew", "body": "新", "created_at": "not-a-date"}],
        "deleted": ["synctarget"],
    }, headers=admin)
    assert res.status_code == 200
    ids = {n["id"] for n in res.get_json()["notes"]}
    assert "synctarget" not in ids
    assert "syncnew" in ids
    fresh = [n for n in res.get_json()["notes"] if n["id"] == "syncnew"][0]
    assert fresh["created_at"]  # 非法时间被替换成服务端时间


def test_http_errors_are_json(wf):
    res = wf._client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"
    assert wf._client.delete("/api/health").status_code == 405


def test_upload_guard(wf, admin):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    res = wf._client.post("/api/upload", data={"file": (io_bytes(svg), "evil.svg")},
                          headers=admin, content_type="multipart/form-data")
    assert res.status_code == 400

    res = wf._client.post("/api/upload", data={"file": (io_bytes(b"<script>alert(1)</script>"), "evil.png")},
                          headers=admin, content_type="multipart/form-data")
    assert res.status_code == 400

    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    res = wf._client.post("/api/upload", data={"file": (io_bytes(png), "ok.png")},
                          headers=admin, content_type="multipart/form-data")
    assert res.status_code == 201
    assert res.get_json()["filename"].endswith(".png")


def io_bytes(data):
    from io import BytesIO
    return BytesIO(data)


def test_discover_is_public_but_only_shared(wf, admin):
    wf._client.post("/api/notes", json={"id": "pub1", "body": "公开的", "shared": True}, headers=admin)
    wf._client.post("/api/notes", json={"id": "priv1", "body": "私密的", "shared": False}, headers=admin)
    res = wf._client.get("/api/discover")
    assert res.status_code == 200
    ids = {n["id"] for n in res.get_json()["notes"]}
    assert "pub1" in ids
    assert "priv1" not in ids


def test_admin_key_management(wf, admin, user2):
    keys = wf._client.get("/api/admin/keys", headers=admin).get_json()["keys"]
    assert len(keys) >= 2

    victim = [k for k in keys if not k["is_admin"] and not k["revoked"]][0]
    assert wf._client.delete(f"/api/admin/keys/{victim['id']}", headers=admin).status_code == 200
    assert wf._client.delete(f"/api/admin/keys/{victim['id']}", headers=admin).status_code == 404

    # 撤销后该 Key 立即失效
    assert wf._client.get("/api/notes", headers=user2).status_code == 401


def test_non_admin_cannot_manage_keys(wf, admin):
    # 单独建一个未被撤销的子用户，避免依赖上个用例的副作用
    res = wf._client.post("/api/admin/keys", json={"label": "普通用户"}, headers=admin)
    normal = {"Authorization": "Bearer " + res.get_json()["apikey"]}
    assert wf._client.get("/api/admin/keys", headers=normal).status_code == 403
    assert wf._client.post("/api/admin/claim-notes", headers=normal).status_code == 403
