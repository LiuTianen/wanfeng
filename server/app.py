"""
晚风 · 笔记后端
Flask + SQLite，极简 API
"""
import os
import uuid
import sqlite3
import secrets
import hashlib
import json
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, g

app = Flask(__name__)

# ── 强制 API 响应不可缓存 ──
@app.after_request
def no_cache_api(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ── 日志 ──
LOG_DIR = Path(os.environ.get("WANFENG_LOG_DIR", "/var/log/wanfeng"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler(),  # stderr → journalctl
    ]
)
log = logging.getLogger(__name__)
log.info("晚风服务启动")

# ── 访问日志：记录真实 IP + 方法 + 路径 + 状态码 + 耗时 ──
@app.before_request
def _start_timer():
    g._start_time = time.time()


@app.after_request
def _log_access(response):
    if request.path.startswith('/api/'):
        ip = (request.headers.get('X-Real-IP')
              or (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
              or request.remote_addr)
        cost_ms = (time.time() - getattr(g, '_start_time', time.time())) * 1000
        log.info("访问 %s %s %s → %s (%.0fms)", ip, request.method, request.path, response.status_code, cost_ms)
    return response

DB_DIR = Path(os.environ.get("WANFENG_DATA_DIR", "/var/lib/wanfeng"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "notes.db"

# ── 上传目录 ──
UPLOAD_DIR = Path(os.environ.get("WANFENG_UPLOAD_DIR", "/var/www/wanfeng/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── API Key 管理 ──
KEY_FILE = DB_DIR / ".apikey"

def get_or_create_apikey():
    # 重新部署时生成全新 Key
    if os.environ.get("WANFENG_RESET_KEY") == "1":
        KEY_FILE.unlink(missing_ok=True)
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
            "group" TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            shared INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC)")
    db.execute('CREATE INDEX IF NOT EXISTS idx_notes_group ON notes("group")')
    # 迁移
    for col, default in [("title", "''"), ("group", "''"), ("tags", "'[]'"), ("shared", "0")]:
        try:
            db.execute(f"ALTER TABLE notes ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
        except:
            pass
    # 置顶迁移
    try:
        db.execute("ALTER TABLE notes ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    except:
        pass
    try:
        db.execute("ALTER TABLE notes ADD COLUMN pinned_at TEXT")
    except:
        pass
    # users 表 + 管理员种子
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            apikey_hash TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
    """)
    if os.environ.get("WANFENG_RESET_KEY") == "1":
        db.execute("DELETE FROM users WHERE is_admin = 1")
    # 没有管理员则创建
    admin_exists = db.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    if not admin_exists:
        db.execute(
            "INSERT INTO users (id, apikey, apikey_hash, label, is_admin, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (str(uuid.uuid4()), API_KEY, API_KEY_HASH, "管理员", datetime.now(timezone.utc).isoformat()),
        )
    db.commit()
    db.close()

# ── Auth ──
def check_auth():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if token_hash == API_KEY_HASH:
            return True
        # 检查用户表
        try:
            db = get_db()
            row = db.execute(
                "SELECT 1 FROM users WHERE apikey_hash = ? AND revoked = 0",
                (token_hash,)
            ).fetchone()
            if row:
                return True
        except Exception:
            pass
    return False


def require_auth():
    if not check_auth():
        return jsonify({"error": "unauthorized"}), 401
    return None


def is_admin():
    """当前请求是否为管理员"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if token_hash == API_KEY_HASH:
        return True
    try:
        db = get_db()
        row = db.execute(
            "SELECT is_admin FROM users WHERE apikey_hash = ? AND revoked = 0",
            (token_hash,)
        ).fetchone()
        return bool(row and row["is_admin"])
    except Exception:
        return False


def require_admin():
    if not check_auth():
        return jsonify({"error": "unauthorized"}), 401
    if not is_admin():
        return jsonify({"error": "admin required"}), 403
    return None


# ── API ──
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/auth/verify", methods=["POST"])
def verify_auth():
    """验证 API key"""
    data = request.get_json(silent=True) or {}
    token = data.get("key", "")
    if not token:
        return jsonify({"valid": False}), 401
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    # 检查主 Key
    if token_hash == API_KEY_HASH:
        return jsonify({"valid": True, "is_admin": True})
    # 检查用户表
    db = get_db()
    row = db.execute(
        "SELECT is_admin FROM users WHERE apikey_hash = ? AND revoked = 0",
        (token_hash,)
    ).fetchone()
    if row:
        return jsonify({"valid": True, "is_admin": bool(row["is_admin"])})
    return jsonify({"valid": False}), 401


@app.route("/api/notes", methods=["GET"])
def list_notes():
    auth_err = require_auth()
    if auth_err:
        return auth_err

    db = get_db()
    group = request.args.get("group", "")
    tag = request.args.get("tag", "")
    select = 'SELECT id, body, title, "group", tags, images, shared, pinned, pinned_at, created_at, updated_at FROM notes'
    order = " ORDER BY pinned DESC, pinned_at DESC, created_at DESC"
    if group:
        rows = db.execute(
            select + ' WHERE "group" = ?' + order,
            (group,)
        ).fetchall()
    elif tag:
        rows = db.execute(
            select + " WHERE tags LIKE ?" + order,
            (f'%"{tag}"%',)
        ).fetchall()
    else:
        rows = db.execute(
            select + order
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
    images = data.get("images", [])
    if not isinstance(images, list): images = []
    images_json = json.dumps(images)
    note_id = data.get("id") or gen_id()
    now = utcnow()

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO notes (id, body, title, \"group\", tags, images, shared, pinned, pinned_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)",
        (note_id, body, title, group, tags_json, images_json, 1 if data.get("shared") else 0, now, now),
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
    images = data.get("images", [])
    if not isinstance(images, list): images = []
    images_json = json.dumps(images)
    now = utcnow()
    db = get_db()

    row = db.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row:
        db.execute(
            "UPDATE notes SET body = ?, title = ?, \"group\" = ?, tags = ?, images = ?, shared = ?, updated_at = ? WHERE id = ?",
            (body, title, group, tags_json, images_json, 1 if data.get("shared") else 0, now, note_id),
        )
    else:
        db.execute(
            "INSERT INTO notes (id, body, title, \"group\", tags, images, shared, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (note_id, body, title, group, tags_json, images_json, 1 if data.get("shared") else 0, now, now),
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


@app.route("/api/notes/<note_id>/pin", methods=["POST"])
def pin_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    db = get_db()
    row = db.execute("SELECT id, pinned FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["pinned"]:
        return jsonify({"pinned": True, "pinned_at": None, "message": "already pinned"})
    pinned_count = db.execute("SELECT COUNT(*) FROM notes WHERE pinned = 1").fetchone()[0]
    if pinned_count >= 3:
        return jsonify({"error": "最多置顶 3 条笔记"}), 400
    now = utcnow()
    db.execute("UPDATE notes SET pinned = 1, pinned_at = ? WHERE id = ?", (now, note_id))
    db.commit()
    return jsonify({"pinned": True, "pinned_at": now})


@app.route("/api/notes/<note_id>/unpin", methods=["POST"])
def unpin_note(note_id):
    auth_err = require_auth()
    if auth_err:
        return auth_err
    db = get_db()
    row = db.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    db.execute("UPDATE notes SET pinned = 0, pinned_at = NULL WHERE id = ?", (note_id,))
    db.commit()
    return jsonify({"pinned": False})


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
        images = note.get("images", [])
        if not isinstance(images, list): images = []
        images_json = json.dumps(images)
        created = note.get("created_at", now)
        title = (note.get("title", "") or "").strip()
        db.execute(
            "INSERT OR REPLACE INTO notes (id, body, title, \"group\", tags, images, shared, pinned, pinned_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (note_id, body, title, group, tags_json, images_json, 1 if note.get("shared") else 0, 1 if note.get("pinned") else 0, note.get("pinned_at"), created, now),
        )
        upserted += 1

    db.commit()

    # 返回合并后的全部笔记
    rows = db.execute(
        "SELECT id, body, title, \"group\", tags, images, shared, pinned, pinned_at, created_at, updated_at FROM notes ORDER BY pinned DESC, pinned_at DESC, created_at DESC"
    ).fetchall()
    all_notes = [note_row(r) for r in rows]

    return jsonify({"upserted": upserted, "total": len(all_notes), "notes": all_notes})



# ── 发现页（公开）──
@app.route("/api/discover", methods=["GET"])
def discover():
    """公开接口：浏览被分享的笔记。无认证最多 10 条，有认证无限制"""
    db = get_db()
    limit = 10
    if check_auth():
        limit = -1  # SQLite: -1 = no limit
    rows = db.execute(
        "SELECT id, body, title, \"group\", tags, images, shared, pinned, pinned_at, created_at, updated_at FROM notes WHERE shared = 1 ORDER BY pinned DESC, pinned_at DESC, created_at DESC" +
        (" LIMIT ?" if limit > 0 else ""),
        (limit,) if limit > 0 else ()
    ).fetchall()
    notes = [note_row(r) for r in rows]
    has_more = len(notes) >= limit if limit > 0 else False
    return jsonify({"notes": notes, "has_more": has_more, "authenticated": check_auth()})

# ── 图片上传 ──
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'dng', 'heic', 'heif', 'tiff', 'tif'}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
# 需要转换的原始格式（浏览器无法直接显示）
RAW_EXTENSIONS = {'dng', 'heic', 'heif', 'tiff', 'tif'}
# 原始文件存档目录
ORIGINAL_DIR = UPLOAD_DIR / "originals"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/upload", methods=["POST"])
def upload_file():
    auth_err = require_auth()
    if auth_err:
        log.warning("上传失败：未认证")
        return auth_err
    if 'file' not in request.files:
        log.warning("上传失败：请求中无 file 字段")
        return jsonify({"error": "no file"}), 400
    file = request.files['file']
    if file.filename == '':
        log.warning("上传失败：空文件名")
        return jsonify({"error": "empty filename"}), 400
    if not allowed_file(file.filename):
        log.warning("上传失败：不支持的文件类型 %s", file.filename)
        return jsonify({"error": "unsupported file type"}), 400

    # 检查文件大小
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_SIZE:
        log.warning("上传失败：文件过大 %d bytes (上限 %d)", size, MAX_UPLOAD_SIZE)
        return jsonify({"error": f"file too large ({size} bytes, max {MAX_UPLOAD_SIZE})"}), 413

    ext = file.filename.rsplit('.', 1)[1].lower()
    uid = uuid.uuid4().hex
    raw_filename = f"{uid}.{ext}"

    # 保存原始文件
    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    raw_dest = str(ORIGINAL_DIR / raw_filename)
    try:
        file.save(raw_dest)
    except Exception as e:
        log.error("上传失败：保存文件出错 %s", e)
        return jsonify({"error": "save failed"}), 500

    # 如果是 RAW 格式，转换为 JPEG
    if ext in RAW_EXTENSIONS:
        display_filename = f"{uid}.jpg"
        display_dest = str(UPLOAD_DIR / display_filename)
        try:
            result = subprocess.run(
                ['convert', raw_dest, '-auto-orient', '-resize', '1920x1920>',
                 '-quality', '92', display_dest],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                log.error("格式转换失败 %s: %s", raw_filename, result.stderr.strip())
                return jsonify({"error": "conversion failed"}), 500
            log.info("上传成功 %s (%d bytes) → %s (转JPEG)", file.filename, size, display_filename)
        except subprocess.TimeoutExpired:
            log.error("格式转换超时 %s", raw_filename)
            return jsonify({"error": "conversion timeout"}), 500
        except Exception as e:
            log.error("格式转换异常 %s: %s", raw_filename, e)
            return jsonify({"error": "conversion error"}), 500
    else:
        # Web 格式直接可用
        display_filename = raw_filename
        display_dest = str(UPLOAD_DIR / display_filename)
        try:
            os.rename(raw_dest, display_dest)
        except OSError:
            import shutil
            shutil.copy2(raw_dest, display_dest)
        log.info("上传成功 %s (%d bytes) → %s", file.filename, size, display_filename)

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
        "SELECT id, apikey_hash, label, is_admin, created_at, revoked FROM users ORDER BY created_at DESC"
    ).fetchall()
    keys = []
    for r in rows:
        keys.append({
            "id": r["id"],
            "key_preview": r["apikey_hash"][:8] + "…",
            "label": r["label"],
            "is_admin": bool(r["is_admin"]),
            "created_at": r["created_at"],
            "revoked": bool(r["revoked"]),
        })
    return jsonify({"keys": keys})

@app.route("/api/admin/keys", methods=["POST"])
def create_key():
    admin_err = require_admin()
    if admin_err:
        return admin_err
    data = request.get_json(silent=True) or {}
    label = (data.get("label", "") or "").strip() or "用户"
    new_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(new_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO users (id, apikey, apikey_hash, label, is_admin, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (key_id, new_key, key_hash, label, now),
    )
    db.commit()
    return jsonify({
        "id": key_id,
        "apikey": new_key,
        "label": label,
        "key_preview": key_hash[:8] + "…",
    }), 201

@app.route("/api/admin/keys/<key_id>", methods=["DELETE"])
def revoke_key(key_id):
    admin_err = require_admin()
    if admin_err:
        return admin_err
    db = get_db()
    db.execute("UPDATE users SET revoked = 1 WHERE id = ? AND is_admin = 0", (key_id,))
    db.commit()
    return jsonify({"revoked": key_id})

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


# ── 全局错误处理 ──
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
        "tags": json.loads(r["tags"] or "[]"),
        "images": json.loads(r["images"] or "[]"),
        "ts": iso_to_ts(r["updated_at"]),
        "created_ts": iso_to_ts(r["created_at"]),
        "created_at": r["created_at"],
        "shared": bool(r["shared"]),
        "updated_at": r["updated_at"],
        "pinned": bool(r["pinned"]),
        "pinned_at": r["pinned_at"] or None,
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
