# 晚风 · 图文日记

> 晚风吹人醒，万事藏于心

一个极简的个人日记 PWA，支持文字+图片记录、分组标签、日历翻阅、服务端同步。

## 功能

- 📝 文字日记 —— 暗色卡片流，支持分组 & 标签
- 📸 图片附件 —— 上传即显，灯箱预览
- 📅 日历视图 —— 按月翻阅，有日记的日子标点
- 🔄 服务端同步 —— Flask + SQLite，离线本地兜底
- 📱 PWA —— 可安装到桌面，iOS/Android 独立运行
- 🔑 API Key 认证 —— 单用户安全访问

## 项目结构

```
wanfeng/
├── index.html          # 前端 PWA（单文件）
├── manifest.json       # PWA 配置
├── sw.js               # Service Worker
├── server/
│   └── app.py          # Flask 后端 API
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
sudo cp index.html manifest.json sw.js /var/www/wanfeng/

# 配置 Nginx（含 SSL + API 反向代理 + 图片上传）
sudo cp deploy/nginx/wanfeng.conf /etc/nginx/sites-available/wanfeng
sudo ln -s /etc/nginx/sites-available/wanfeng /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 创建上传目录
sudo mkdir -p /var/www/wanfeng/uploads
sudo chown www-data:www-data /var/www/wanfeng/uploads
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/notes` | 列表 |
| POST | `/api/notes` | 创建 |
| PUT | `/api/notes/:id` | 更新 |
| DELETE | `/api/notes/:id` | 删除 |
| POST | `/api/notes/sync` | 批量同步 |
| GET | `/api/groups` | 分组列表 |
| GET | `/api/tags` | 标签列表 |
| POST | `/api/upload` | 图片上传（multipart） |
| POST | `/api/auth/verify` | 验证 API Key |

所有接口需 `Authorization: Bearer <key>` 头。

## 技术栈

- **前端**: Vanilla HTML/CSS/JS，PWA（manifest + Service Worker）
- **后端**: Python Flask + SQLite + Gunicorn
- **部署**: Nginx 反向代理 + Let's Encrypt SSL
- **图片**: 服务端本地存储，Nginx alias 直接服务

## License

MIT
