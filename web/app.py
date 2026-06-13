"""
web/app.py
----------
FastAPI 主应用入口 / FastAPI main application entry point

功能 / Features:
  - 挂载所有 API 路由 / Mount all API routers
  - 托管前端静态文件（Vue 构建产物）/ Serve frontend static files (Vue build output)
  - CORS 配置（开发时允许本地前端访问）/ CORS config for local dev frontend
  - 根路由重定向到前端 index.html / Root redirects to frontend index.html

启动方式 / How to run:
  cd /home/ubuntu/alpha
  uvicorn web.app:app --host 0.0.0.0 --port 8000

访问地址 / Access URL:
  http://<服务器IP>:8000
"""

import sys
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 将项目根目录加入 Python 路径，使 machine_lib 可被子模块导入
# Add project root to Python path so machine_lib is importable from sub-modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.routers import status, alphas, platform, agent, control, experiments, config_router

app = FastAPI(
    title="Alpha Mining Dashboard",
    description="WorldQuant Brain 因子挖掘监控仪表盘 + AI Agent 框架",
    version="1.0.0",
)

# ── CORS 配置 ──────────────────────────────────────────────────────────────────
# 开发阶段允许所有来源（生产部署时可按需限制）
# Allow all origins during development (restrict in production if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册 API 路由 ───────────────────────────────────────────────────────────────
# /api/status /api/stats /api/simulations /api/logs /api/logs/stream
app.include_router(status.router, prefix="/api", tags=["监控/Monitoring"])

# /api/alphas
app.include_router(alphas.router, prefix="/api", tags=["本地因子/Local Alphas"])

# /api/platform/overview /api/platform/alphas /api/platform/alphas/{id}/pnl
app.include_router(platform.router, prefix="/api/platform", tags=["平台数据/Platform"])

# /api/agent/analyze /api/agent/result/{id}
app.include_router(agent.router, prefix="/api/agent", tags=["AI Agent"])

# /api/control/start/{name} /api/control/stop/{name} /api/control/status
app.include_router(control.router, prefix="/api/control", tags=["脚本控制/Script Control"])

# /api/experiments /api/experiments/switch
app.include_router(experiments.router, prefix="/api/experiments", tags=["实验配置/Experiments"])

# /api/config /api/config/credentials /api/config/test-login
app.include_router(config_router.router, prefix="/api/config", tags=["系统配置/Config"])

# ── 静态文件（前端构建产物）────────────────────────────────────────────────────
# Vue build output is placed in web/static/ after `npm run build && scp dist/*`
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    # 挂载 assets/ 等静态资源目录 / Mount static assets directory
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
        """
        将所有非 /api 路由都返回 index.html，交给 Vue Router 处理
        Return index.html for all non-API routes; Vue Router handles client-side routing
        """
        # API 路由不在这里处理，由上面的 router 负责
        # API routes are handled by routers above; this only catches frontend routes
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "Frontend not deployed yet. Run npm build and upload dist/"}
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        """前端尚未部署时的提示 / Shown when frontend is not yet deployed"""
        return {
            "message": "Frontend not deployed. Build Vue project locally and upload dist/ to web/static/",
            "api_docs": "/docs",
        }
