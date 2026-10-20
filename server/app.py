"""
晚风 · 笔记后端
Flask + SQLite，极简 API

设计要点（2026-10 巡检修复）：
- 建表与迁移都以 PRAGMA table_info 为准，不再用裸 except 吞错误
- notes 表带 user_id，笔记按用户隔离；历史无归属笔记（user_id=''）仍对所有人可见
- 所有写接口校验 id / images 文件名 / 长度，杜绝把 HTML 注入前端
- init_db() 在模块导入时执行，gunicorn 直接启动也能建表
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# ── 上传/请求大小限制 ──
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB，与 nginx client_max_body_size 保持一致
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE + 1024 * 1024

# ── 业务上限 ──
MAX_BODY_CHARS = 100_000
MAX_TITLE_CHARS = 200
MAX_GROUP_CHARS = 64
MAX_TAGS = 20
MAX_TAG_CHARS = 32
MAX_IMAGES = 30
MAX_PINS = 3

# 笔记 id 只允许 url-safe 字符：既防注入，也保证前端拿去拼 data-id 是安全的
NOTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# 图片文件名：uuid.扩展名（历史数据也可能是时间戳命名，一律按扩展名白名单兜底）
IMAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}\.(png|jpe?g|gif|webp|bmp|svg)$", re.I)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "dng", "heic", "heif", "tiff", "tif"}
# 注意：svg 已从上传白名单移除 —— 同源直出 SVG 等于给攻击者一个存储型 XSS 落点
RAW_EXTENSIONS = {"dng", "heic", "heif", "tiff", "tif"}
WEB_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
    b"II*\x00": "tiff",
    b"MM\x00*": "tiff",
}


# ── 强制 API 响应不可缓存 ──
@app.after_request
def no_cache_api(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ── 日志 ──
LOG_DIR = Path(os.environ.get("WANFENG_LOG_DIR", "/var/log/wanfeng"))
_handlers = [logging.StreamHandler()]  # stderr → journalctl
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _handlers.insert(0, logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"))
except OSError:
    # 目录不可写（例如 /var/log 需要 root）时退化为只写 stderr，不让服务起不来
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
log = logging.getLogger(__name__)


# ── 访问日志：记录真实 IP + 方法 + 路径 + 状态码 + 耗时 ──
@app.before_request
def _start_timer():
    g._start_time = time.time()


@app.after_request
def _log_access(response):
    if request.path.startswith("/api/"):
        cost_ms = (time.time() - getattr(g, "_start_time", time.time())) * 1000
        log.info("访问 %s %s %s → %s (%.0fms)", client_ip(), request.method, request.path,
                 response.status_code, cost_ms)
    return response


def client_ip():
    """nginx 反代下 remote_addr 永远是 127.0.0.1，真实 IP 在 X-Real-IP 里。"""
    return (request.headers.get("X-Real-IP")
            or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            or request.remote_addr
            or "-")


# ── 目录 ──
DB_DIR = Path(os.environ.get("WANFENG_DATA_DIR", "/var/lib/wanfeng"))
try:
    DB_DIR.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    raise RuntimeError(
        f"无法创建数据目录 {DB_DIR}: {exc}；请先 mkdir -p 并 chown 给服务用户，"
        "或用 WANFENG_DATA_DIR 指定可写目录"
    ) from exc
DB_PATH = DB_DIR / "notes.db"

UPLOAD_DIR = Path(os.environ.get("WANFENG_UPLOAD_DIR", "/var/www/wanfeng/uploads"))
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    raise RuntimeError(f"无法创建上传目录 {UPLOAD_DIR}: {exc}") from exc

ORIGINAL_DIR = UPLOAD_DIR / "originals"

# ── API Key ──
KEY_FILE = DB_DIR / ".apikey"
RESET_MASTER_KEY = os.environ.get("WANFENG_RESET_KEY") == "1"


def get_or_create_apikey():
    """读取或生成主 Key。只有显式 WANFENG_RESET_KEY=1 才轮换。"""
    if RESET_MASTER_KEY:
        KEY_FILE.unlink(missing_ok=True)
    if KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(32)
    KEY_FILE.write_text(key, encoding="utf-8")
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return key


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


API_KEY = get_or_create_apikey()
API_KEY_HASH = sha256(API_KEY)


# ── 数据库 ──
def connect():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


SCHEMA_NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    "group" TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    images TEXT NOT NULL DEFAULT '[]',
    shared INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    pinned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    apikey_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
)
"""

# 列名 → 声明；迁移按 PRAGMA 结果判断，不再靠 try/except 猜
NOTE_MIGRATIONS = [
    ("title", "TEXT NOT NULL DEFAULT ''"),
    ('"group"', "TEXT NOT NULL DEFAULT ''"),
    ("tags", "TEXT NOT NULL DEFAULT '[]'"),
    ("images", "TEXT NOT NULL DEFAULT '[]'"),
    ("shared", "INTEGER NOT NULL DEFAULT 0"),
    ("pinned", "INTEGER NOT NULL DEFAULT 0"),
    ("pinned_at", "TEXT"),
    ("user_id", "TEXT NOT NULL DEFAULT ''"),
]

USER_MIGRATIONS = [
    ("apikey_hash", "TEXT"),
    ("label", "TEXT NOT NULL DEFAULT ''"),
    ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
    ("created_at", "TEXT"),
    ("revoked", "INTEGER NOT NULL DEFAULT 0"),
]


def table_columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def add_missing_columns(db, table, migrations):
    cols = table_columns(db, table)
    for name, decl in migrations:
        if name.strip('"') not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            log.info("迁移：%s 增加列 %s", table, name.strip('"'))


def insert_user(db, plaintext, label, is_admin):
    """兼容两种历史库：v3 的 users 有 apikey 明文列，现在的库只有哈希。"""
    uid = str(uuid.uuid4())
    cols = table_columns(db, "users")
    if "apikey" in cols:
        db.execute(
            "INSERT INTO users (id, apikey, apikey_hash, label, is_admin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, plaintext, sha256(plaintext), label, 1 if is_admin else 0, utcnow()),
        )
    else:
        db.execute(
            "INSERT INTO users (id, apikey_hash, label, is_admin, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, sha256(plaintext), label, 1 if is_admin else 0, utcnow()),
        )
    return uid


def init_db():
    """建表 + 迁移 + 主 Key 落库。导入时调用，gunicorn 启动也会执行。"""
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(SCHEMA_NOTES)
        db.execute(SCHEMA_USERS)
        add_missing_columns(db, "notes", NOTE_MIGRATIONS)
        add_missing_columns(db, "users", USER_MIGRATIONS)
        db.execute('CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_notes_group ON notes("group")')
        db.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_users_hash ON users(apikey_hash)")

        admin = db.execute(
            "SELECT id FROM users WHERE apikey_hash = ? LIMIT 1", (API_KEY_HASH,)
        ).fetchone()
        if admin:
            db.execute("UPDATE users SET is_admin = 1, revoked = 0 WHERE id = ?", (admin["id"],))
        elif RESET_MASTER_KEY:
            # 轮换主 Key：更新既有管理员行而不是删掉重建，避免笔记失去归属
            oldest = db.execute(
                "SELECT id FROM users WHERE is_admin = 1 ORDER BY created_at LIMIT 1"
            ).fetchone()
            if oldest:
                db.execute(
                    "UPDATE users SET apikey_hash = ?, revoked = 0 WHERE id = ?",
                    (API_KEY_HASH, oldest["id"]),
                )
            else:
                insert_user(db, API_KEY, "管理员", True)
        else:
            insert_user(db, API_KEY, "管理员", True)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Auth ──
def _lookup_user(token_hash):
    row = get_db().execute(
        "SELECT id, label, is_admin, revoked FROM users WHERE apikey_hash = ?",
        (token_hash,),
    ).fetchone()
    if not row or row["revoked"]:
        return None
    return {"id": row["id"], "label": row["label"], "is_admin": bool(row["is_admin"])}


def current_user():
    """解析 Bearer token → 用户；主 Key 作为兜底映射到管理员。"""
    if "user" in g:
        return g.user
    g.user = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            token_hash = sha256(token)
            user = _lookup_user(token_hash)
            if user is None and hmac.compare_digest(token_hash, API_KEY_HASH):
                row = get_db().execute(
                    "SELECT id, label FROM users WHERE is_admin = 1 ORDER BY created_at LIMIT 1"
                ).fetchone()
                user = {
                    "id": row["id"] if row else "master",
                    "label": row["label"] if row else "管理员",
                    "is_admin": True,
                }
            g.user = user
    return g.user


def require_auth():
    if not current_user():
        return jsonify({"error": "unauthorized"}), 401
    return None


def require_admin():
    user = current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    if not user["is_admin"]:
        return jsonify({"error": "admin required"}), 403
    return None


def visible_clause(user):
    """自己的笔记 + 历史无归属笔记（升级前的数据不会凭空消失）。"""
    return "(user_id = ? OR user_id = '')", (user["id"],)


def can_write(user, owner_id):
    return owner_id in ("", user["id"])


# ── 请求校验 ──
def _text(value, limit):
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def parse_note_payload(data, *, note_id=None):
    """把请求体规整成安全的结构；返回 (payload, error_response)。"""
    if not isinstance(data, dict):
        return None, (jsonify({"error": "invalid json"}), 400)

    body = (data.get("body") or "").strip() if isinstance(data.get("body"), str) else ""
    if not body:
        return None, (jsonify({"error": "body is required"}), 400)
    if len(body) > MAX_BODY_CHARS:
        return None, (jsonify({"error": f"body too long (max {MAX_BODY_CHARS})"}), 413)

    title = _text(data.get("title"), MAX_TITLE_CHARS)
    group = _text(data.get("group"), MAX_GROUP_CHARS)

    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = []
    for t in raw_tags:
        if isinstance(t, str):
            t = t.strip()[:MAX_TAG_CHARS]
            if t and t not in tags:
                tags.append(t)
        if len(tags) >= MAX_TAGS:
            break

    raw_images = data.get("images", [])
    if not isinstance(raw_images, list):
        raw_images = []
    images = []
    for f in raw_images:
        if not isinstance(f, str) or not IMAGE_NAME_RE.match(f):
            return None, (jsonify({"error": "invalid image reference"}), 400)
        if f not in images:
            images.append(f)
    if len(images) > MAX_IMAGES:
        return None, (jsonify({"error": f"too many images (max {MAX_IMAGES})"}), 400)

    if note_id is not None:
        if not isinstance(note_id, str) or not NOTE_ID_RE.match(note_id):
            return None, (jsonify({"error": "invalid note id"}), 400)

    return {
        "id": note_id,
        "body": body,
        "title": title,
        "group": group,
        "tags": tags,
        "images": images,
        "shared": bool(data.get("shared")),
        "pinned": bool(data.get("pinned")),
        # 只有显式带了 pinned 字段才改置顶状态，避免普通保存把置顶清掉
        "pinned_provided": "pinned" in data,
        "created_at": data.get("created_at"),
    }, None


# ── API ──
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.1.0"})


_VERIFY_HITS = {}


def _verify_rate_limited(ip):
    now = time.time()
    hits = [t for t in _VERIFY_HITS.get(ip, []) if now - t < 60]
    if len(hits) >= 20:
        _VERIFY_HITS[ip] = hits
        return True
    hits.append(now)
    if len(_VERIFY_HITS) > 5000:
        _VERIFY_HITS.clear()
    _VERIFY_HITS[ip] = hits
    return False


@app.route("/api/auth/verify", methods=["POST"])
def verify_auth():
    """验证 API key"""
    if _verify_rate_limited(client_ip()):
        return jsonify({"error": "too many attempts"}), 429

    data = request.get_json(silent=True) or {}
    token = data.get("key", "")
    if not isinstance(token, str) or not token:
        return jsonify({"valid": False}), 401

    user = _lookup_user(sha256(token))
    if user:
        return jsonify({"valid": True, "is_admin": user["is_admin"], "label": user["label"]})
    if hmac.compare_digest(sha256(token), API_KEY_HASH):
        return jsonify({"valid": True, "is_admin": True, "label": "管理员"})
    return jsonify({"valid": False}), 401


@app.route("/api/notes", methods=["GET"])
def list_notes():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    where, params = visible_clause(user)
    group = request.args.get("group", "")
    tag = request.args.get("tag", "")
    if group:
        where += ' AND "group" = ?'
        params += (group,)
    elif tag:
        escaped = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where += " AND tags LIKE ? ESCAPE '\\'"
        params += (f'%"{escaped}"%',)

    db = get_db()
    rows = db.execute(
        "SELECT * FROM notes WHERE " + where +
        " ORDER BY pinned DESC, pinned_at DESC, created_at DESC",
        params,
    ).fetchall()
    return jsonify({"notes": [note_row(r) for r in rows]})


def _upsert(db, user, payload, note_id, *, allow_pin, created_at=None):
    """写入单条笔记；返回 'ok' / 'forbidden'。"""
    existing = db.execute(
        "SELECT user_id, pinned, pinned_at, created_at FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if existing and not can_write(user, existing["user_id"]):
        return "forbidden"

    pinned = bool(existing["pinned"]) if existing else False
    pinned_at = existing["pinned_at"] if existing else None
    if allow_pin and payload.get("pinned_provided"):
        if payload.get("pinned"):
            if not pinned:
                where, params = visible_clause(user)
                count = db.execute(
                    f"SELECT COUNT(*) FROM notes WHERE {where} AND pinned = 1", params
                ).fetchone()[0]
                if count < MAX_PINS:
                    pinned = True
                    pinned_at = utcnow()
        else:
            pinned = False
            pinned_at = None

    owner = existing["user_id"] if existing else user["id"]
    created = existing["created_at"] if existing else parse_iso(created_at) or utcnow()
    now = utcnow()

    db.execute(
        """
        INSERT INTO notes (id, user_id, body, title, "group", tags, images,
                           shared, pinned, pinned_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            body = excluded.body,
            title = excluded.title,
            "group" = excluded."group",
            tags = excluded.tags,
            images = excluded.images,
            shared = excluded.shared,
            pinned = excluded.pinned,
            pinned_at = excluded.pinned_at,
            updated_at = excluded.updated_at
        """,
        (note_id, owner, payload["body"], payload["title"], payload["group"],
         json.dumps(payload["tags"]), json.dumps(payload["images"]),
         1 if payload["shared"] else 0, 1 if pinned else 0, pinned_at,
         created, now),
    )
    return "ok"


@app.route("/api/notes", methods=["POST"])
def create_note():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    data = request.get_json(silent=True)
    note_id = (data or {}).get("id") if isinstance(data, dict) else None
    if note_id is None:
        note_id = gen_id()
    payload, err = parse_note_payload(data, note_id=note_id)
    if err:
        return err

    db = get_db()
    if _upsert(db, user, payload, note_id, allow_pin=False) == "forbidden":
        return jsonify({"error": "forbidden"}), 403
    db.commit()

    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return jsonify(note_row(row)), 201


@app.route("/api/notes/<note_id>", methods=["PUT"])
def update_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    if not NOTE_ID_RE.match(note_id):
        return jsonify({"error": "invalid note id"}), 400
    data = request.get_json(silent=True)
    payload, err = parse_note_payload(data, note_id=note_id)
    if err:
        return err

    db = get_db()
    existing = db.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    if _upsert(db, user, payload, note_id, allow_pin=False) == "forbidden":
        return jsonify({"error": "forbidden"}), 403
    db.commit()

    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return jsonify(note_row(row))


@app.route("/api/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    if not NOTE_ID_RE.match(note_id):
        return jsonify({"error": "invalid note id"}), 400
    db = get_db()
    row = db.execute("SELECT user_id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not can_write(user, row["user_id"]):
        return jsonify({"error": "forbidden"}), 403
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    return jsonify({"deleted": note_id})


@app.route("/api/notes/<note_id>/pin", methods=["POST"])
def pin_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    if not NOTE_ID_RE.match(note_id):
        return jsonify({"error": "invalid note id"}), 400
    db = get_db()
    row = db.execute("SELECT user_id, pinned FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not can_write(user, row["user_id"]):
        return jsonify({"error": "forbidden"}), 403
    if row["pinned"]:
        return jsonify({"pinned": True, "pinned_at": None, "message": "already pinned"})

    where, params = visible_clause(user)
    pinned_count = db.execute(
        f"SELECT COUNT(*) FROM notes WHERE {where} AND pinned = 1", params
    ).fetchone()[0]
    if pinned_count >= MAX_PINS:
        return jsonify({"error": f"最多置顶 {MAX_PINS} 条笔记"}), 400
    now = utcnow()
    db.execute("UPDATE notes SET pinned = 1, pinned_at = ? WHERE id = ?", (now, note_id))
    db.commit()
    return jsonify({"pinned": True, "pinned_at": now})


@app.route("/api/notes/<note_id>/unpin", methods=["POST"])
def unpin_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    if not NOTE_ID_RE.match(note_id):
        return jsonify({"error": "invalid note id"}), 400
    db = get_db()
    row = db.execute("SELECT user_id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not can_write(user, row["user_id"]):
        return jsonify({"error": "forbidden"}), 403
    db.execute("UPDATE notes SET pinned = 0, pinned_at = NULL WHERE id = ?", (note_id,))
    db.commit()
    return jsonify({"pinned": False})


@app.route("/api/notes/sync", methods=["POST"])
def sync_notes():
    """离线队列同步：上送未落库的变更 + 已删除的 id，返回合并后的全量列表。"""
    auth_err = require_auth()
    if auth_err:
        return auth_err
    user = current_user()

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
        return jsonify({"error": "notes array required"}), 400
    if len(data["notes"]) > 500:
        return jsonify({"error": "too many notes in one sync (max 500)"}), 413

    db = get_db()
    upserted = 0
    skipped = 0
    for item in data["notes"]:
        if not isinstance(item, dict):
            skipped += 1
            continue
        note_id = item.get("id")
        payload, err = parse_note_payload(item, note_id=note_id)
        if err or not note_id:
            skipped += 1
            continue
        if _upsert(db, user, payload, note_id, allow_pin=True,
                   created_at=item.get("created_at")) != "ok":
            skipped += 1
            continue
        upserted += 1

    deleted = data.get("deleted") or []
    if isinstance(deleted, list):
        for note_id in deleted:
            if not isinstance(note_id, str) or not NOTE_ID_RE.match(note_id):
                continue
            row = db.execute("SELECT user_id FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row and can_write(user, row["user_id"]):
                db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()

    where, params = visible_clause(user)
    rows = db.execute(
        "SELECT * FROM notes WHERE " + where +
        " ORDER BY pinned DESC, pinned_at DESC, created_at DESC",
        params,
    ).fetchall()
    all_notes = [note_row(r) for r in rows]
    return jsonify({"upserted": upserted, "skipped": skipped,
                    "total": len(all_notes), "notes": all_notes})


# ── 发现页（公开）──
@app.route("/api/discover", methods=["GET"])
def discover():
    """公开接口：浏览被分享的笔记。无需认证即可查看全部公开内容"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM notes WHERE shared = 1 "
        "ORDER BY pinned DESC, pinned_at DESC, created_at DESC LIMIT 200"
    ).fetchall()
    return jsonify({
        "notes": [note_row(r) for r in rows],
        "has_more": False,
        "authenticated": bool(current_user()),
    })


# ── 图片上传 ──
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def sniff_ok(head, ext):
    """对浏览器可直接显示的格式做一次魔数校验，挡住改扩展名的垃圾文件。"""
    if ext not in WEB_EXTENSIONS:
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return ext == "webp"
    for magic, kind in MAGIC_BYTES.items():
        if head.startswith(magic):
            if kind == "tiff":
                return ext in ("tiff", "tif")
            if kind == "jpg":
                return ext in ("jpg", "jpeg")
            return kind == ext
    return False


@app.route("/api/upload", methods=["POST"])
def upload_file():
    auth_err = require_auth()
    if auth_err:
        log.warning("上传失败：未认证")
        return auth_err
    if "file" not in request.files:
        log.warning("上传失败：请求中无 file 字段")
        return jsonify({"error": "no file"}), 400
    file = request.files["file"]
    if not file.filename:
        log.warning("上传失败：空文件名")
        return jsonify({"error": "empty filename"}), 400
    if not allowed_file(file.filename):
        log.warning("上传失败：不支持的文件类型 %s", file.filename)
        return jsonify({"error": "unsupported file type"}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_SIZE:
        log.warning("上传失败：文件过大 %d bytes (上限 %d)", size, MAX_UPLOAD_SIZE)
        return jsonify({"error": f"file too large ({size} bytes, max {MAX_UPLOAD_SIZE})"}), 413
    if size == 0:
        return jsonify({"error": "empty file"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    head = file.read(16)
    file.seek(0)
    if not sniff_ok(head, ext):
        log.warning("上传失败：文件头与扩展名不符 %s", file.filename)
        return jsonify({"error": "file content does not match its extension"}), 400

    uid = uuid.uuid4().hex
    raw_filename = f"{uid}.{ext}"

    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    raw_dest = str(ORIGINAL_DIR / raw_filename)
    try:
        file.save(raw_dest)
    except Exception as e:
        log.error("上传失败：保存文件出错 %s", e)
        return jsonify({"error": "save failed"}), 500

    if ext in RAW_EXTENSIONS:
        display_filename = f"{uid}.jpg"
        display_dest = str(UPLOAD_DIR / display_filename)
        try:
            result = subprocess.run(
                ["convert", raw_dest, "-auto-orient", "-resize", "1920x1920>",
                 "-quality", "92", "-limit", "memory", "256MiB",
                 "-limit", "map", "512MiB", display_dest],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                log.error("格式转换失败 %s: %s", raw_filename, result.stderr.strip())
                return jsonify({"error": "conversion failed"}), 500
            log.info("上传成功 %s (%d bytes) → %s (转JPEG)", file.filename, size, display_filename)
        except FileNotFoundError:
            log.error("格式转换失败：系统未安装 ImageMagick (convert)")
            return jsonify({"error": "server missing ImageMagick"}), 503
        except subprocess.TimeoutExpired:
            log.error("格式转换超时 %s", raw_filename)
            return jsonify({"error": "conversion timeout"}), 500
        except Exception as e:
            log.error("格式转换异常 %s: %s", raw_filename, e)
            return jsonify({"error": "conversion error"}), 500
    else:
        display_filename = raw_filename
        display_dest = str(UPLOAD_DIR / display_filename)
        try:
            os.replace(raw_dest, display_dest)
        except OSError:
            shutil.copy2(raw_dest, display_dest)

    return jsonify({
        "filename": display_filename,
        "url": f"/uploads/{display_filename}",
        "size": size,
        "converted": ext in RAW_EXTENSIONS,
        "original_ext": ext if ext in RAW_EXTENSIONS else None,
    }), 201


# ── Admin: Key 管理 ──
@app.route("/api/admin/keys", methods=["GET"])
def list_keys():
    admin_err = require_admin()
    if admin_err:
        return admin_err
    db = get_db()
    rows = db.execute(
        "SELECT id, apikey_hash, label, is_admin, created_at, revoked "
        "FROM users ORDER BY created_at DESC"
    ).fetchall()
    keys = [{
        "id": r["id"],
        "key_preview": (r["apikey_hash"] or "")[:8] + "…",
        "label": r["label"],
        "is_admin": bool(r["is_admin"]),
        "created_at": r["created_at"],
        "revoked": bool(r["revoked"]),
    } for r in rows]
    return jsonify({"keys": keys})


@app.route("/api/admin/keys", methods=["POST"])
def create_key():
    admin_err = require_admin()
    if admin_err:
        return admin_err
    data = request.get_json(silent=True) or {}
    label = _text(data.get("label"), 40) or "用户"
    new_key = secrets.token_urlsafe(32)
    db = get_db()
    key_id = insert_user(db, new_key, label, False)
    db.commit()
    return jsonify({
        "id": key_id,
        "apikey": new_key,          # 仅此一次返回明文
        "label": label,
        "key_preview": sha256(new_key)[:8] + "…",
    }), 201


@app.route("/api/admin/keys/<key_id>", methods=["DELETE"])
def revoke_key(key_id):
    admin_err = require_admin()
    if admin_err:
        return admin_err
    db = get_db()
    cur = db.execute(
        "UPDATE users SET revoked = 1 WHERE id = ? AND is_admin = 0 AND revoked = 0",
        (key_id,),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"revoked": key_id})


@app.route("/api/admin/claim-notes", methods=["POST"])
def claim_legacy_notes():
    """把升级前无归属的笔记划归当前管理员，消除"所有人可改"的历史数据。"""
    admin_err = require_admin()
    if admin_err:
        return admin_err
    user = current_user()
    db = get_db()
    cur = db.execute("UPDATE notes SET user_id = ? WHERE user_id = ''", (user["id"],))
    db.commit()
    return jsonify({"claimed": cur.rowcount, "owner": user["id"]})


# ── 分组 ──
@app.route("/api/groups", methods=["GET"])
def list_groups():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    where, params = visible_clause(current_user())
    rows = get_db().execute(
        'SELECT DISTINCT "group", COUNT(*) AS count FROM notes '
        f'WHERE {where} AND "group" != \'\' GROUP BY "group" ORDER BY "group"',
        params,
    ).fetchall()
    return jsonify({"groups": [{"name": r["group"], "count": r["count"]} for r in rows]})


# ── 标签 ──
@app.route("/api/tags", methods=["GET"])
def list_tags():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    where, params = visible_clause(current_user())
    rows = get_db().execute(
        f"SELECT tags FROM notes WHERE {where} AND tags != '[]'", params
    ).fetchall()
    tag_counts = {}
    for r in rows:
        try:
            for t in json.loads(r["tags"] or "[]"):
                if isinstance(t, str) and t:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        except (ValueError, TypeError):
            continue
    result = sorted(({"name": k, "count": v} for k, v in tag_counts.items()),
                    key=lambda x: -x["count"])
    return jsonify({"tags": result})


# ── 错误处理 ──
@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return jsonify({"error": (e.name or "error").lower().replace(" ", "_")}), e.code


@app.errorhandler(Exception)
def handle_exception(e):
    log.error("未捕获异常: %s", e, exc_info=True)
    return jsonify({"error": "internal server error"}), 500


# ── 工具 ──
def note_row(r):
    return {
        "id": r["id"],
        "body": r["body"],
        "title": r["title"] or "",
        "group": r["group"] or "",
        "tags": _json_list(r["tags"]),
        "images": _json_list(r["images"]),
        "ts": iso_to_ts(r["updated_at"]),
        "created_ts": iso_to_ts(r["created_at"]),
        "created_at": r["created_at"],
        "shared": bool(r["shared"]),
        "updated_at": r["updated_at"],
        "pinned": bool(r["pinned"]),
        "pinned_at": r["pinned_at"] or None,
    }


def _json_list(raw):
    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def gen_id():
    return base36(int(time.time() * 1000)) + secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:8].lower()


def base36(n):
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    s = ""
    while n:
        s = chars[n % 36] + s
        n //= 36
    return s


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value):
    """宽松解析客户端时间戳；失败返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def iso_to_ts(s):
    """ISO string → JS timestamp (ms)"""
    try:
        dt = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


# ── 启动 ──
init_db()
log.info("晚风服务启动")

if __name__ == "__main__":
    print(f"🔑 API Key (save this!): {API_KEY}")
    print(f"📂 Database: {DB_PATH}")
    app.run(host="127.0.0.1", port=5000, debug=False)
