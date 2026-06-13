"""
brain_client.py
---------------
WorldQuant Brain API 统一 session 管理器 / Unified session manager for WorldQuant Brain API

设计目的 / Design rationale:
  - 后端统一维护一个长期存活的认证 session，避免前端直接接触账号密码
  - 每 3 小时自动刷新 session（平台 token 有效期约 4 小时）
  - 线程安全：使用 threading.Lock 保证并发请求时不会重复登录
  - 提供 .get() / .post() 快捷方法，自动拼接 base URL

Unified authenticated session maintained by the backend.
Frontend never sees credentials; all Brain API calls go through this module.
Auto-refreshes every 3 hours; thread-safe via Lock.
"""

import requests
import time
import threading
import sys
import os

# 将项目根目录加入路径，以便导入 machine_lib
# Add project root to path so machine_lib can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from machine_lib import login

# Session 有效期（秒）/ Session validity period in seconds
SESSION_EXPIRY = 3 * 60 * 60  # 3 hours


class BrainClient:
    """
    WorldQuant Brain API 客户端单例
    Singleton client for WorldQuant Brain API

    用法 / Usage:
        from brain_client import brain
        resp = brain.get("/users/self")
    """

    def __init__(self):
        # 当前认证 session / Current authenticated session
        self._session: requests.Session | None = None
        # Session 创建时间戳 / Timestamp when session was created
        self._start_time: float = 0
        # 线程锁，防止并发时重复登录 / Lock to prevent concurrent re-logins
        self._lock = threading.Lock()

    def _refresh(self):
        """
        重新登录并刷新 session
        Re-authenticate and refresh the session
        """
        self._session = login()
        self._start_time = time.time()

    def get_session(self) -> requests.Session:
        """
        获取有效的认证 session（自动检查过期）
        Return a valid session, refreshing if expired
        """
        with self._lock:
            if self._session is None or time.time() - self._start_time > SESSION_EXPIRY:
                self._refresh()
            return self._session

    def get(self, path: str, **kwargs) -> requests.Response:
        """
        发送 GET 请求到 Brain API
        Send a GET request to the Brain API

        Args:
            path: API 路径，如 "/users/self" / API path e.g. "/users/self"
        """
        s = self.get_session()
        return s.get(f"https://api.worldquantbrain.com{path}", **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        """
        发送 POST 请求到 Brain API
        Send a POST request to the Brain API
        """
        s = self.get_session()
        return s.post(f"https://api.worldquantbrain.com{path}", **kwargs)


# 全局单例，所有 router 共享同一个认证 session
# Global singleton — all routers share one authenticated session
brain = BrainClient()
