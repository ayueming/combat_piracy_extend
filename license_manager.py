# license_manager.py
import os
import json
from datetime import datetime, timezone, timedelta
from app_paths import get_user_dir, FILE_AUTH
from db_config import get_current_user


class LicenseManager:
    _instance = None
    _is_expired = False
    _days_left = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.refresh_status()
        return cls._instance

    def refresh_status(self):
        """重新读取本地文件，更新过期状态"""
        user_id = get_current_user()

        # 开发模式或未登录时跳过
        try:
            from config import is_dev_mode
            if is_dev_mode():
                self._is_expired = False
                self._days_left = 999
                return
        except:
            pass

        if not user_id:
            self._is_expired = True
            self._days_left = 0
            return

        auth_file = os.path.join(get_user_dir(user_id), FILE_AUTH)

        if not os.path.exists(auth_file):
            self._is_expired = True
            self._days_left = 0
            return

        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                info = json.load(f)
            expires_at_str = info.get("expires_at")

            if not expires_at_str:
                self._is_expired = False  # 永久有效
                self._days_left = 999
                return

            utc_time = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            beijing_tz = timezone(timedelta(hours=8))
            beijing_time = utc_time.astimezone(beijing_tz)
            now = datetime.now(beijing_tz)

            self._days_left = (beijing_time - now).days
            self._is_expired = self._days_left < 0

        except Exception:
            self._is_expired = True

    @property
    def is_expired(self) -> bool:
        return self._is_expired

    @property
    def days_left(self) -> int:
        return self._days_left


# 全局实例
license_mgr = LicenseManager()