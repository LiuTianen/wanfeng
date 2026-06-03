"""
晚风 · 笔记后端
Flask + SQLite，极简 API
"""
import os
import sqlite3
import secrets
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, g

app = Flask(__name__)

DB_DIR = Path(os.environ.get("WANFENG_DATA_DIR", "/var/lib/wanfeng"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "notes.db"

# ── API Key 管理 ──
KEY_FILE = DB_DIR / ".apikey"

def get_or_create_apikey():
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(32)
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)
    return key

API_KEY = get_or_create_apikey()
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()


# ── 数据库 ──
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            \"group\" TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_group ON notes(\"group\")")
    # 迁移
    for col, default in [("title", "''"), ("group", "''"), ("tags", "'[]'")]:
        try:
            db.execute(f"ALTER TABLE notes ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
        except:
            pass
    db.commit()
    db.close()


# ── Auth ──
def check_auth():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if hashlib.sha256(token.encode()).hexdigest() == API_KEY_HASH:
            return True
    return False


def require_auth():
    if not check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return None


# ── API ──
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/auth/verify", methods=["POST"])
def verify_auth():
    """验证 API key，返回是否有效"""
    data = request.get_json(silent=True) or {}
    token = data.get("key", "")
    if token == API_KEY:
        return jsonify({"valid": True, "token": API_KEY_HASH})
    return jsonify({"valid": False}), 401


@app.route("/api/notes", methods=["GET"])
def list_notes():
    auth_err = require_auth()
    if auth_err:
        return auth_err

    db = get_db()
    group = request.args.get("group", "")
    tag = request.args.get("tag", "")
    if group:
        rows = db.execute(
            "SELECT id, body, \"group\", tags, created_at, updated_at FROM notes WHERE \"group\" = ? ORDER BY updated_at DESC",
            (group,)
        ).fetchall()
    elif tag:
        # 标签筛选用 LIKE 匹配 JSON 数组中的标签名
        rows = db.execute(
            "SELECT id, body, \"group\", tags, created_at, updated_at FROM notes WHERE tags LIKE ? ORDER BY updated_at DESC",
            (f'%"{tag}"%',)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, body, \"group\", tags, created_at, updated_at FROM notes ORDER BY updated_at DESC"
        ).fetchall()

    notes = []
    for r in rows:
        notes.append(note_row(r))
    return jsonify({"notes": notes})


@app.route("/api/notes", methods=["POST"])
def create_note():
    auth_err = require_auth()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid json"}), 400

    body = (data.get("body", "") or "").strip()
    if not body:
        return jsonify({"error": "body is required"}), 400

    title = (data.get("title", "") or "").strip()
    group = (data.get("group", "") or "").strip()
    tags = data.get("tags", [])
    if not isinstance(tags, list): tags = []
    tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
    note_id = data.get("id") or gen_id()
    now = utcnow()

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO notes (id, body, title, \"group\", tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (note_id, body, title, group, tags_json, now, now),
    )
    db.commit()

    return jsonify({
        "id": note_id, "body": body, "title": title, "group": group, "tags": json.loads(tags_json),
        "ts": iso_to_ts(now), "created_at": now, "updated_at": now,
    }), 201


@app.route("/api/notes/<note_id>", methods=["PUT"])
def update_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid json"}), 400

    body = (data.get("body", "") or "").strip()
    if not body:
        return jsonify({"error": "body is required"}), 400

    title = (data.get("title", "") or "").strip()
    group = (data.get("group", "") or "").strip()
    tags = data.get("tags", [])
    if not isinstance(tags, list): tags = []
    tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
    now = utcnow()
    db = get_db()

    row = db.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row:
        db.execute(
            "UPDATE notes SET body = ?, title = ?, \"group\" = ?, tags = ?, updated_at = ? WHERE id = ?",
            (body, title, group, tags_json, now, note_id),
        )
    else:
        db.execute(
            "INSERT INTO notes (id, body, title, \"group\", tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (note_id, body, title, group, tags_json, now, now),
        )
    db.commit()

    return jsonify({
        "id": note_id, "body": body, "title": title, "group": group, "tags": json.loads(tags_json),
        "ts": iso_to_ts(now), "updated_at": now,
    })


@app.route("/api/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err

    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    return jsonify({"deleted": note_id})


@app.route("/api/notes/sync", methods=["POST"])
def sync_notes():
    """批量同步：接收客户端全部笔记，合并到服务端"""
    auth_err = require_auth()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("notes"), list):
        return jsonify({"error": "notes array required"}), 400

    now = utcnow()
    db = get_db()

    upserted = 0
    for note in data["notes"]:
        body = (note.get("body", "") or "").strip()
        if not body:
            continue
        note_id = note.get("id") or gen_id()
        group = (note.get("group", "") or "").strip()
        tags = note.get("tags", [])
        if not isinstance(tags, list): tags = []
        tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
        created = note.get("created_at", now)
        db.execute(
            "INSERT OR REPLACE INTO notes (id, body, \"group\", tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, body, group, tags_json, created, now),
        )
        upserted += 1

    db.commit()

    # 返回合并后的全部笔记
    rows = db.execute(
        "SELECT id, body, \"group\", tags, created_at, updated_at FROM notes ORDER BY updated_at DESC"
    ).fetchall()
    all_notes = [note_row(r) for r in rows]

    return jsonify({"upserted": upserted, "total": len(all_notes), "notes": all_notes})


# ── 分组 ──
@app.route("/api/groups", methods=["GET"])
def list_groups():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT \"group\", COUNT(*) as count FROM notes WHERE \"group\" != '' GROUP BY \"group\" ORDER BY \"group\""
    ).fetchall()
    return jsonify({
        "groups": [{"name": r["group"], "count": r["count"]} for r in rows]
    })


# ── 标签 ──
@app.route("/api/tags", methods=["GET"])
def list_tags():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    db = get_db()
    rows = db.execute("SELECT tags FROM notes WHERE tags != '[]'").fetchall()
    tag_counts = {}
    for r in rows:
        try:
            for t in json.loads(r["tags"]):
                if t:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        except: pass
    result = sorted([{"name": k, "count": v} for k, v in tag_counts.items()], key=lambda x: -x["count"])
    return jsonify({"tags": result})


# ── 工具 ──
def note_row(r):
    return {
        "id": r["id"],
        "body": r["body"],
        "title": r["title"] or "",
        "group": r["group"] or "",
        "tags": json.loads(r["tags"] or "[]"),
        "ts": iso_to_ts(r["updated_at"]),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
def gen_id():
    import time, random, string
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return base36(ts) + rand

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

def iso_to_ts(s):
    """ISO string → JS timestamp (ms)"""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0

# ── 启动 ──
if __name__ == "__main__":
    init_db()
    print(f"🔑 API Key (save this!): {API_KEY}")
    print(f"📂 Database: {DB_PATH}")
    app.run(host="127.0.0.1", port=5000, debug=False)
