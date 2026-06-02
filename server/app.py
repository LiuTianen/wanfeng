"""
晚风 · 笔记后端 v3
Flask + SQLite — 多用户隔离 + API Key 管理
"""
import os
import sqlite3
import secrets
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

DB_DIR = Path(os.environ.get("WANFENG_DATA_DIR", "/var/lib/wanfeng"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "notes.db"

UPLOAD_DIR = Path(os.environ.get("WANFENG_UPLOAD_DIR", "/var/www/wanfeng/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Master Key ──
MASTER_KEY_FILE = DB_DIR / ".masterkey"

def get_or_create_master_key():
    if MASTER_KEY_FILE.exists():
        return MASTER_KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(32)
    MASTER_KEY_FILE.write_text(key)
    MASTER_KEY_FILE.chmod(0o600)
    return key

MASTER_KEY = get_or_create_master_key()

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
    if db: db.close()

def init_db():
    db = sqlite3.connect(str(DB_PATH))

    # 用户表
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            apikey TEXT NOT NULL UNIQUE,
            apikey_hash TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 笔记表
    db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            "group" TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            images TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_group ON notes(\"group\")")

    # 迁移旧表
    for col, default in [("group", "''"), ("tags", "'[]'"), ("images", "'[]'"), ("user_id", "''")]:
        try:
            db.execute(f'ALTER TABLE notes ADD COLUMN "{col}" TEXT NOT NULL DEFAULT {default}')
        except: pass

    # 确保 master 用户存在
    master_hash = hashlib.sha256(MASTER_KEY.encode()).hexdigest()
    existing = db.execute("SELECT id FROM users WHERE apikey_hash = ?", (master_hash,)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (id, apikey, apikey_hash, label, is_admin, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (str(uuid.uuid4()), MASTER_KEY, master_hash, "管理员", utcnow())
        )
    else:
        # 确保 master 始终是 admin
        db.execute("UPDATE users SET is_admin = 1, revoked = 0 WHERE apikey_hash = ?", (master_hash,))

    db.commit()
    db.close()

# ── Auth ──
def resolve_user(token: str):
    """根据 token 查找用户，返回 (user_id, is_admin) 或 None"""
    db = get_db()
    h = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute(
        "SELECT id, is_admin, revoked FROM users WHERE apikey_hash = ?", (h,)
    ).fetchone()
    if row and not row["revoked"]:
        return row["id"], bool(row["is_admin"])
    return None

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401
        token = auth[7:]
        user = resolve_user(token)
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        g.user_id, g.is_admin = user
        return f(*args, **kwargs)
    return wrapper

def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401
        token = auth[7:]
        user = resolve_user(token)
        if not user or not user[1]:
            return jsonify({"error": "admin required"}), 403
        g.user_id, g.is_admin = user
        return f(*args, **kwargs)
    return wrapper

# ── 图片上传 ──
@app.route("/api/upload", methods=["POST"])
@require_auth
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "no file field"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"unsupported file type. allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_SIZE:
        return jsonify({"error": "file too large (max 10MB)"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}_{secrets.token_hex(4)}.{ext}"
    filepath = UPLOAD_DIR / filename
    file.save(str(filepath))

    return jsonify({"filename": filename, "url": f"/uploads/{filename}", "size": size}), 201

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

# ── 基础 API ──
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "3.0.0", "multi_tenant": True})

@app.route("/api/auth/verify", methods=["POST"])
def verify_auth():
    data = request.get_json(silent=True) or {}
    token = data.get("key", "")
    user = resolve_user(token)
    if user:
        return jsonify({"valid": True, "is_admin": user[1], "user_id": user[0]})
    return jsonify({"valid": False}), 401

# ── 笔记 CRUD（用户隔离）──
@app.route("/api/notes", methods=["GET"])
@require_auth
def list_notes():
    db = get_db()
    group = request.args.get("group", "")
    tag = request.args.get("tag", "")
    uid = g.user_id

    if group:
        rows = db.execute(
            'SELECT * FROM notes WHERE user_id = ? AND "group" = ? ORDER BY updated_at DESC',
            (uid, group)
        ).fetchall()
    elif tag:
        rows = db.execute(
            'SELECT * FROM notes WHERE user_id = ? AND tags LIKE ? ORDER BY updated_at DESC',
            (uid, f'%"{tag}"%')
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT * FROM notes WHERE user_id = ? ORDER BY updated_at DESC',
            (uid,)
        ).fetchall()

    return jsonify({"notes": [note_row(r) for r in rows]})

@app.route("/api/notes", methods=["POST"])
@require_auth
def create_note():
    data = request.get_json(silent=True)
    if not data: return jsonify({"error": "invalid json"}), 400
    body = (data.get("body", "") or "").strip()
    if not body: return jsonify({"error": "body is required"}), 400

    group = (data.get("group", "") or "").strip()
    tags = data.get("tags", [])
    if not isinstance(tags, list): tags = []
    tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
    images = data.get("images", [])
    if not isinstance(images, list): images = []
    images_json = json.dumps([i for i in images if isinstance(i, str)])
    note_id = data.get("id") or gen_id()
    now = utcnow()

    db = get_db()
    db.execute(
        'INSERT OR REPLACE INTO notes (id, user_id, body, "group", tags, images, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (note_id, g.user_id, body, group, tags_json, images_json, now, now)
    )
    db.commit()
    return jsonify({
        "id": note_id, "body": body, "group": group,
        "tags": json.loads(tags_json), "images": json.loads(images_json),
        "ts": iso_to_ts(now), "created_at": now, "updated_at": now
    }), 201

@app.route("/api/notes/<note_id>", methods=["PUT"])
@require_auth
def update_note(note_id):
    data = request.get_json(silent=True)
    if not data: return jsonify({"error": "invalid json"}), 400
    body = (data.get("body", "") or "").strip()
    if not body: return jsonify({"error": "body is required"}), 400

    group = (data.get("group", "") or "").strip()
    tags = data.get("tags", [])
    if not isinstance(tags, list): tags = []
    tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
    images = data.get("images", [])
    if not isinstance(images, list): images = []
    images_json = json.dumps([i for i in images if isinstance(i, str)])
    now = utcnow()
    db = get_db()

    # 只能更新自己的笔记（或管理员可更新任意）
    row = db.execute("SELECT id FROM notes WHERE id = ? AND user_id = ?", (note_id, g.user_id)).fetchone()
    if row:
        db.execute(
            'UPDATE notes SET body = ?, "group" = ?, tags = ?, images = ?, updated_at = ? WHERE id = ?',
            (body, group, tags_json, images_json, now, note_id)
        )
    else:
        db.execute(
            'INSERT INTO notes (id, user_id, body, "group", tags, images, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (note_id, g.user_id, body, group, tags_json, images_json, now, now)
        )
    db.commit()
    return jsonify({
        "id": note_id, "body": body, "group": group,
        "tags": json.loads(tags_json), "images": json.loads(images_json),
        "ts": iso_to_ts(now), "updated_at": now
    })

@app.route("/api/notes/<note_id>", methods=["DELETE"])
@require_auth
def delete_note(note_id):
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, g.user_id))
    db.commit()
    return jsonify({"deleted": note_id})

@app.route("/api/notes/sync", methods=["POST"])
@require_auth
def sync_notes():
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("notes"), list):
        return jsonify({"error": "notes array required"}), 400
    now = utcnow()
    db = get_db()
    upserted = 0
    for note in data["notes"]:
        body = (note.get("body", "") or "").strip()
        if not body: continue
        note_id = note.get("id") or gen_id()
        group = (note.get("group", "") or "").strip()
        tags = note.get("tags", [])
        if not isinstance(tags, list): tags = []
        tags_json = json.dumps([t.strip() for t in tags if isinstance(t, str) and t.strip()])
        images = note.get("images", [])
        if not isinstance(images, list): images = []
        images_json = json.dumps([i for i in images if isinstance(i, str)])
        created = note.get("created_at", now)
        db.execute(
            'INSERT OR REPLACE INTO notes (id, user_id, body, "group", tags, images, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (note_id, g.user_id, body, group, tags_json, images_json, created, now)
        )
        upserted += 1
    db.commit()
    rows = db.execute(
        "SELECT * FROM notes WHERE user_id = ? ORDER BY updated_at DESC", (g.user_id,)
    ).fetchall()
    return jsonify({"upserted": upserted, "total": len(rows), "notes": [note_row(r) for r in rows]})

# ── 分组 & 标签（用户隔离）──
@app.route("/api/groups", methods=["GET"])
@require_auth
def list_groups():
    db = get_db()
    rows = db.execute(
        'SELECT DISTINCT "group", COUNT(*) as count FROM notes WHERE user_id = ? AND "group" != \'\' GROUP BY "group" ORDER BY "group"',
        (g.user_id,)
    ).fetchall()
    return jsonify({"groups": [{"name": r["group"], "count": r["count"]} for r in rows]})

@app.route("/api/tags", methods=["GET"])
@require_auth
def list_tags():
    db = get_db()
    rows = db.execute("SELECT tags FROM notes WHERE user_id = ? AND tags != '[]'", (g.user_id,)).fetchall()
    tag_counts = {}
    for r in rows:
        try:
            for t in json.loads(r["tags"]):
                if t: tag_counts[t] = tag_counts.get(t, 0) + 1
        except: pass
    result = sorted([{"name": k, "count": v} for k, v in tag_counts.items()], key=lambda x: -x["count"])
    return jsonify({"tags": result})

# ── 管理员 API ──
@app.route("/api/admin/keys", methods=["GET"])
@require_admin
def admin_list_keys():
    db = get_db()
    rows = db.execute(
        "SELECT id, apikey_hash, label, is_admin, created_at, revoked FROM users ORDER BY created_at"
    ).fetchall()
    keys = []
    for r in rows:
        keys.append({
            "id": r["id"],
            "label": r["label"],
            "is_admin": bool(r["is_admin"]),
            "created_at": r["created_at"],
            "revoked": bool(r["revoked"]),
            # 返回密钥前缀（安全起见不返回完整 key，除非创建时）
            "key_preview": "wf_" + r["apikey_hash"][:8] + "..."
        })
    return jsonify({"keys": keys})

@app.route("/api/admin/keys", methods=["POST"])
@require_admin
def admin_create_key():
    data = request.get_json(silent=True) or {}
    label = (data.get("label", "") or "").strip() or "用户"
    apikey = "wf_" + secrets.token_urlsafe(24)
    apikey_hash = hashlib.sha256(apikey.encode()).hexdigest()
    uid = str(uuid.uuid4())
    now = utcnow()
    db = get_db()
    db.execute(
        "INSERT INTO users (id, apikey, apikey_hash, label, is_admin, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (uid, apikey, apikey_hash, label, now)
    )
    db.commit()
    return jsonify({
        "id": uid,
        "apikey": apikey,  # 仅创建时返回完整 key
        "label": label,
        "created_at": now
    }), 201

@app.route("/api/admin/keys/<key_id>", methods=["DELETE"])
@require_admin
def admin_revoke_key(key_id):
    db = get_db()
    row = db.execute("SELECT is_admin FROM users WHERE id = ?", (key_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["is_admin"]:
        return jsonify({"error": "cannot revoke admin key"}), 403
    db.execute("UPDATE users SET revoked = 1 WHERE id = ?", (key_id,))
    db.commit()
    return jsonify({"revoked": key_id})

@app.route("/api/admin/stats", methods=["GET"])
@require_admin
def admin_stats():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as c FROM users WHERE revoked = 0").fetchone()["c"]
    total_notes = db.execute("SELECT COUNT(*) as c FROM notes").fetchone()["c"]
    return jsonify({"total_users": total_users, "total_notes": total_notes})

# ── 工具 ──
def note_row(r):
    return {
        "id": r["id"],
        "body": r["body"],
        "group": r["group"] or "",
        "tags": json.loads(r["tags"] or "[]"),
        "images": json.loads(r["images"] or "[]"),
        "ts": iso_to_ts(r["updated_at"]),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }

def gen_id():
    import time, random, string as s
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(s.ascii_lowercase + s.digits, k=8))
    return base36(ts) + rand

def base36(n):
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0: return "0"
    result = ""
    while n: result = chars[n % 36] + result; n //= 36
    return result

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def iso_to_ts(s):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except: return 0

# ── 初始化 ──
init_db()

if __name__ == "__main__":
    print(f"👑 Master Key: {MASTER_KEY}")
    print(f"📂 Database: {DB_PATH}")
    print(f"🖼️  Uploads: {UPLOAD_DIR}")
    app.run(host="127.0.0.1", port=5000, debug=False)
