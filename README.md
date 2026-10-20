# 晚风 · 图文日记

> 晚风吹人醒，万事藏于心

一个极简的个人图文日记 PWA：暗色卡片流、分组与标签、日历翻阅、公开分享页，Flask + SQLite 后端，离线可用、多设备同步。

---

## 功能

- 📝 **图文日记** —— 标题、分组、标签，图片上传即显，灯箱预览
- 📸 **原图支持** —— HEIC / DNG / TIFF 自动转 JPEG，原图单独归档
- 📅 **日历视图** —— 按月翻阅，有笔记的日子打点，按本地时区归日
- 🕯️ **拾光页** —— 浏览大家公开分享的笔记，无需登录即可看
- 🔑 **多用户** —— 管理员发放 / 撤销子 Key，**笔记按用户隔离**
- 🔄 **离线优先** —— 本地先写、断网可用；恢复网络后自动补传，删除也不会被别的设备「复活」
- 📱 **PWA** —— 可安装到桌面，图标齐全，离线打开
- 🎨 **可换背景** —— 预设渐变 + 自定义图片

## 目录结构

```
wanfeng/
├── index.html                 # PWA 入口
├── manifest.json              # PWA 配置
├── sw.js                      # Service Worker（API 不拦截 / 静态缓存优先）
├── icons/                     # 192 / 512 / maskable / apple-touch 图标
├── css/
│   └── style.css
├── js/                        # 前端逻辑（无构建，按顺序加载）
│   ├── utils.js               #   转义、标签、灯箱、toast
│   ├── api.js                 #   fetch 封装（统一错误）
│   ├── state.js               #   全局状态
│   ├── sync.js                #   离线队列 / 删除墓碑 / 合并策略
│   ├── notes.js               #   数据加载 + 卡片渲染
│   ├── calendar.js            #   日历视图
│   ├── discover.js            #   拾光页
│   ├── editor.js              #   编辑器 + 删除
│   ├── settings.js            #   设置 + Admin Key 管理
│   └── app.js                 #   入口 + 事件绑定
├── server/
│   └── app.py                 # Flask 后端（建表、鉴权、隔离、上传）
├── tests/
│   └── test_app.py            # 后端回归测试（pytest）
├── deploy/
│   ├── nginx/wanfeng.conf     # 站点配置（含安全头 / 限流 / 上传目录）
│   ├── systemd/wanfeng-api.service
│   └── security_report.py     # 可选的扫描器黑名单巡检脚本
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## 本地开发

```bash
# 后端
cd server
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
export WANFENG_DATA_DIR=$PWD/../data
export WANFENG_LOG_DIR=$PWD/../logs
export WANFENG_UPLOAD_DIR=$PWD/../uploads
python app.py
# 🔑 API Key (save this!): xxxxx

# 前端：任意静态服务器指向仓库根目录即可，API 通过 /api 反代
python3 -m http.server 8080
```

> 前端默认把请求打到同源的 `/api`，所以本地调试要么用反向代理，要么直接改 `js/utils.js` 里的 `API_BASE`。

首次启动会在 `WANFENG_DATA_DIR` 下生成 SQLite 库和 `.apikey` 主密钥文件，并自动把主 Key 登记为管理员。

## 部署

### 1. 后端

```bash
sudo mkdir -p /var/www/wanfeng
sudo cp -r index.html manifest.json sw.js css js icons /var/www/wanfeng/

cd /var/www/wanfeng/server
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r ../requirements.txt

# 需要转换 HEIC/DNG/TIFF 时安装 ImageMagick（可选，但用到就必须装）
sudo apt install -y imagemagick

# 用 systemd 的 StateDirectory / LogsDirectory 自动建目录并授权
sudo cp ../deploy/systemd/wanfeng-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wanfeng-api

# 日志轮转（应用长期持有句柄，用 copytruncate）
sudo cp ../deploy/logrotate/wanfeng /etc/logrotate.d/wanfeng

# 取主 Key（首次启动后生成）
sudo cat /var/lib/wanfeng/.apikey
```

`systemd` 单元已包含 `NoNewPrivileges`、`ProtectSystem=strict`、`PrivateTmp` 等加固项；`/var/lib/wanfeng`、`/var/log/wanfeng`、`/var/www/wanfeng/uploads` 是唯一可写路径。gunicorn 26 的控制套接字默认写在 `$HOME`，在只读根文件系统下会报错，所以单元里显式加了 `--no-control-socket`。

### 2. 前端 + Nginx

```bash
sudo mkdir -p /var/www/wanfeng/uploads
sudo chown www-data:www-data /var/www/wanfeng/uploads

sudo cp deploy/nginx/wanfeng.conf /etc/nginx/sites-available/wanfeng
sudo ln -s /etc/nginx/sites-available/wanfeng /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 证书
sudo certbot --nginx -d your.domain
```

配置里已经包含：HSTS、CSP、`X-Content-Type-Options`、`Referrer-Policy`、验 Key 接口限流、`/uploads/originals/` 禁止公网访问、SVG 强制下载。

> 修改 `js/` 或 `css/` 后记得同步更新三处版本号：`index.html` 的 `?v=`、`sw.js` 里的 `CACHE_NAME` 与 `PRECACHE`、`js/utils.js` 的 `APP_VERSION`。否则 Service Worker 会继续用旧缓存。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WANFENG_DATA_DIR` | `/var/lib/wanfeng` | SQLite 与 `.apikey` 所在目录 |
| `WANFENG_LOG_DIR` | `/var/log/wanfeng` | 应用日志目录（不可写时只输出到 stderr） |
| `WANFENG_UPLOAD_DIR` | `/var/www/wanfeng/uploads` | 图片目录，需与 nginx `alias` 一致 |
| `WANFENG_RESET_KEY` | 未设置 | 设为 `1` 时**轮换主 Key**，用完请立刻移除 |

## API

认证方式：`Authorization: Bearer <api key>`。

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| GET | `/api/health` | — | 健康检查 |
| POST | `/api/auth/verify` | — | 校验 Key，返回 `valid` / `is_admin`（限流） |
| GET | `/api/notes` | Bearer | 笔记列表，支持 `?group=` / `?tag=` |
| POST | `/api/notes` | Bearer | 新建笔记（同 id 为幂等更新，保留创建时间与置顶） |
| PUT | `/api/notes/:id` | Bearer | 更新笔记（不存在返回 404） |
| DELETE | `/api/notes/:id` | Bearer | 删除笔记 |
| POST | `/api/notes/:id/pin` | Bearer | 置顶（每人最多 3 条） |
| POST | `/api/notes/:id/unpin` | Bearer | 取消置顶 |
| POST | `/api/notes/sync` | Bearer | 离线队列：上送 `notes` + `deleted`，返回合并后全量 |
| GET | `/api/groups` | Bearer | 分组及计数 |
| GET | `/api/tags` | Bearer | 标签及计数 |
| POST | `/api/upload` | Bearer | 图片上传（multipart，≤50MB） |
| GET | `/api/discover` | 可选 | 公开笔记（无需登录） |
| GET | `/api/admin/keys` | Admin | Key 列表 |
| POST | `/api/admin/keys` | Admin | 生成子 Key（明文仅返回一次） |
| DELETE | `/api/admin/keys/:id` | Admin | 撤销子 Key |
| POST | `/api/admin/claim-notes` | Admin | 把升级前的无归属笔记划归自己 |

### 笔记字段

```json
{
  "id": "mabc123xyz",
  "body": "正文",
  "title": "标题",
  "group": "分组",
  "tags": ["标签"],
  "images": ["<uuid>.jpg"],
  "shared": false,
  "pinned": false,
  "pinned_at": null,
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-02T00:00:00+00:00",
  "ts": 1767225600000,
  "created_ts": 1767225600000
}
```

`id` 只允许 `[A-Za-z0-9_-]{1,64}`；`images` 只接受服务端生成的文件名。两者都会做服务端校验，因为前端会把它们拼进 HTML。

## 数据升级（从旧版本）

旧库启动时会自动补齐 `images`、`user_id`、`pinned` 等列，**不会删数据**。升级前的笔记没有归属（`user_id=''`），默认对**所有已登录用户可见可改**，避免升级后数据「消失」。

确认无误后，建议由管理员执行一次认领，把它们收归自己：

```bash
curl -X POST -H "Authorization: Bearer <主 Key>" https://your.domain/api/admin/claim-notes
```

## 安全设计

- **租户隔离**：`notes.user_id` 由服务端从 token 解析，所有读/写/删都带归属条件
- **输出转义**：前端 `esc()` 覆盖 `& < > " '`，不再用 `innerHTML` 拼内联事件
- **上传白名单**：不接受 SVG；扩展名之外还校验文件头魔数
- **大小与长度限制**：请求体 51MB 上限、正文 10 万字符、标签 20 个、图片 30 张
- **错误语义**：4xx/5xx 统一 JSON，404 不再被吞成 500
- **Key 只存哈希**：`users.apikey_hash` 为 SHA-256，明文仅在生成时返回一次

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q      # 后端：建表、迁移、隔离、校验、限流上限
npm ci && npm run lint         # 前端静态检查
```

CI 在 `.github/workflows/ci.yml`，push 与 PR 都会跑。

## License

MIT
