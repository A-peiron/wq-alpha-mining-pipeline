# 云端部署指南

本文档说明如何将本项目部署到云服务器（以 Ubuntu 为例）。

> ⚠️ 凭证安全：`credentials.json` 含 BRAIN 账号密码，**不要**写进镜像、仓库或公开文档。部署时单独上传到服务器，并确保权限受限。

## 一、服务器准备

```bash
# Python 3.10+
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
# Node.js（用于构建前端，可在本地构建后只传产物）
sudo apt install -y nodejs npm
```

## 二、拉取代码

```bash
cd /home/ubuntu
git clone https://github.com/A-peiron/wq-alpha-mining-pipeline.git alpha
cd alpha
```

## 三、配置凭证（手动，不入库）

```bash
cp credentials.json.template credentials.json
nano credentials.json          # 填入 email / password
chmod 600 credentials.json     # 限制读取权限
```

## 四、安装后端依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 五、前端构建

**方式 A：服务器上构建**

```bash
cd frontend
npm install
npm run build          # 产物输出到 src/alpha/web/static
cd ..
```

**方式 B：本地构建后只传产物**（服务器无需 Node）

```bash
# 本地执行
cd frontend && npm run build && cd ..
scp -r src/alpha/web/static/* <user>@<server>:/home/ubuntu/alpha/src/alpha/web/static/
```

> 前端构建产物的目标路径始终是 `src/alpha/web/static/`。

## 六、用 supervisor 守护 Web 服务

`/etc/supervisor/conf.d/alpha-web.conf`：

```ini
[program:alpha-web]
command=/home/ubuntu/alpha/.venv/bin/uvicorn alpha.web.app:app --host 0.0.0.0 --port 8000
directory=/home/ubuntu/alpha
user=ubuntu
autostart=true
autorestart=true
stdout_logfile=/home/ubuntu/alpha/logs/web.log
stderr_logfile=/home/ubuntu/alpha/logs/web.log
environment=PYTHONIOENCODING="utf-8",PYTHONUTF8="1"
```

启用：

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start alpha-web
```

挖掘 / check 脚本由 Web 控制台「脚本控制」页启停，无需单独守护。

## 七、更新部署流程

```bash
# 服务器上
cd /home/ubuntu/alpha
git pull
source .venv/bin/activate
pip install -e .        # 依赖有变动时
# 前端有改动则重新 build 或重传 src/alpha/web/static
sudo supervisorctl restart alpha-web   # 改了后端/路由后重启
```

## 八、反向代理（可选，推荐）

用 Nginx 在前面挡一层，统一 80/443，并加 HTTPS：

```nginx
server {
    listen 80;
    server_name your.domain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE 日志流需要关闭缓冲
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

## 九、安全检查清单

- [ ] `credentials.json` 权限 600，且不在 git 跟踪中（`git status` 确认）
- [ ] `user_info.txt` 不上传（已 gitignore）
- [ ] Web 服务若暴露公网，建议加反向代理 + 基础认证 / 防火墙白名单
- [ ] `records/`、`logs/` 不入库，由运行时生成

## 十、编码注意（Windows 本地 → Linux 部署）

- supervisor 配置已设 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`，避免中文日志乱码
- 日志文件统一 UTF-8 读写，前端 SSE 已带 `charset=utf-8`
