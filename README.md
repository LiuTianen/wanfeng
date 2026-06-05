# 晚风 · 图文日记

> 晚风吹人醒，万事藏于心

一个极简的个人日记 PWA，支持图文记录、分组标签、日历翻阅、多用户共享、服务端同步。

## 功能

- 📝 文字日记 —— 暗色卡片流，支持标题、分组 & 标签
- 📸 图片上传 —— 上传即显，灯箱预览
- 📅 日历视图 —— 按月翻阅，有日记的日子标点
- 🕯️ 拾光页 —— 浏览大家公开分享的笔记（公开/私有切换）
- 🔑 多用户 —— API Key 管理，管理员可创建/撤销子 Key
- 🔄 服务端同步 —— Flask + SQLite，离线本地兜底
- 📱 PWA —— 可安装到桌面，iOS/Android 独立运行
- 🎨 可换背景 —— 预设渐变 + 自定义图片

## 项目结构

```
wanfeng/
├── index.html              # PWA 入口（65 行骨架）
├── manifest.json           # PWA 配置
├── sw.js                   # Service Worker
├── css/
│   └── style.css           # 全部样式（300 行）
├── js/                     # 前端逻辑（9 个模块）
│   ├── utils.js            #   工具函数
│   ├── api.js              #   API 通信层
│   ├── state.js            #   全局状态
│   ├── notes.js            #   笔记 CRUD + 列表渲染
│   ├── calendar.js         #   日历视图
│   ├── discover.js         #   拾光页
│   ├── editor.js           #   编辑器弹窗
│   ├── settings.js         #   设置 + Admin 面板
│   └── app.js              #   入口 + 事件绑定
├── server/
│   └── app.py              # Flask 后端（529 行）
└── deploy/
    ├── nginx/
    │   └── wanfeng.conf    # Nginx 站点配置
    └── systemd/
        └── wanfeng-api.service  # Gunicorn 服务
```

## 部署

### 后端

```bash
# 1. 安装依赖
cd server
python3 -m venv venv
source venv/bin/activate
pip install flask gunicorn

# 2. 初始化（会自动生成 API Key）
python app.py
# 🔑 API Key (save this!): xxxxx

# 3. 部署 systemd 服务
sudo cp deploy/systemd/wanfeng-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wanfeng-api
```

### 前端 + Nginx

```bash
# 复制前端文件
sudo cp -r index.html manifest.json sw.js css/ js/ /var/www/wanfeng/

# 配置 Nginx（含 SSL + API 反向代理 + 图片上传）
sudo cp deploy/nginx/wanfeng.conf /etc/nginx/sites-available/wanfeng
sudo ln -s /etc/nginx/sites-available/wanfeng /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 创建上传目录
sudo mkdir -p /var/www/wanfeng/uploads
sudo chown www-data:www-data /var/www/wanfeng/uploads
```

### API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/notes` | Bearer | 笔记列表 |
| POST | `/api/notes` | Bearer | 创建笔记 |
| PUT | `/api/notes/:id` | Bearer | 更新笔记 |
| DELETE | `/api/notes/:id` | Bearer | 删除笔记 |
| POST | `/api/notes/sync` | Bearer | 批量同步 |
| GET | `/api/groups` | Bearer | 分组列表 |
| GET | `/api/tags` | Bearer | 标签列表 |
| POST | `/api/upload` | Bearer | 图片上传（multipart） |
| GET | `/api/discover` | 可选 | 公开笔记发现页 |
| POST | `/api/auth/verify` | — | 验证 API Key |
| GET | `/api/admin/keys` | Admin | Key 列表 |
| POST | `/api/admin/keys` | Admin | 创建 Key |
| DELETE | `/api/admin/keys/:id` | Admin | 撤销 Key |

## 技术栈

- **前端**: Vanilla HTML/CSS/JS，模块化拆分，PWA（manifest + Service Worker）
- **后端**: Python Flask + SQLite + Gunicorn
- **部署**: Nginx 反向代理 + Let's Encrypt SSL
- **图片**: 服务端本地存储，Nginx alias 直接服务

## License

MIT
