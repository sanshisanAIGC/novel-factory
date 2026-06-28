"""
飞书 API 认证模块
获取和维护 tenant_access_token
"""
import time
import httpx


class FeishuAuth:
    """飞书 API 认证客户端，带 token 缓存"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=15.0)

    def get_token(self) -> str:
        """获取有效的 tenant_access_token（带缓存和过期检查）"""
        # 提前 5 分钟刷新，避免边界情况
        if self._token and time.time() < self._token_expires_at - 300:
            return self._token

        resp = self._http.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
        )
        data = resp.json()
        code = data.get("code", -1)

        if code != 0:
            raise RuntimeError(
                f"获取飞书 Token 失败: code={code}, msg={data.get('msg')}"
            )

        self._token = data["tenant_access_token"]
        # token 有效期 2 小时，提前 5 分钟刷新
        expires_in = data.get("expire", 7200)
        self._token_expires_at = time.time() + expires_in
        return self._token

    def request(self, method: str, path: str, **kwargs) -> dict:
        """通用 API 请求，自动带上 Authorization header"""
        token = self.get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")

        resp = self._http.request(
            method,
            f"https://open.feishu.cn{path}",
            headers=headers,
            **kwargs,
        )
        return resp.json()

    def get(self, path: str, params: dict = None) -> dict:
        """GET 请求"""
        return self.request("GET", path, params=params)

    def post(self, path: str, data: dict = None) -> dict:
        """POST 请求"""
        return self.request("POST", path, json=data)

    def patch(self, path: str, data: dict = None) -> dict:
        """PATCH 请求"""
        return self.request("PATCH", path, json=data)

    def close(self):
        """关闭 HTTP 客户端"""
        self._http.close()
