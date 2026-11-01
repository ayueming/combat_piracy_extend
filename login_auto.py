# login_auto.py
import os
import json
import httpx

from app_paths import get_session_path, get_user_dir, FILE_AUTH
from login_device_id import get_machine_id
from config import SUPABASE_URL, SUPABASE_ANON_KEY


def try_auto_login() -> str | None:
    """
    尝试用本地 session + refresh_token 自动登录。
    成功返回 user_id；失败返回 None（调用方回退到登录窗口）。
    """
    session_path = get_session_path()
    if not os.path.exists(session_path):
        return None

    try:
        with open(session_path, "r", encoding="utf-8") as f:
            session = json.load(f)
    except Exception:
        _safe_remove(session_path)
        return None

    user_id = session.get("user_id")
    if not user_id:
        _safe_remove(session_path)
        return None

    try:
        auth_file = os.path.join(get_user_dir(user_id), FILE_AUTH)
    except Exception:
        _safe_remove(session_path)
        return None

    if not os.path.exists(auth_file):
        _safe_remove(session_path)
        return None

    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            auth = json.load(f)
    except Exception:
        return None

    refresh_token = auth.get("refresh_token")
    if not refresh_token:
        return None

    base = SUPABASE_URL.rstrip("/")
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}

    # 1) refresh_token 换 access_token
    try:
        resp = httpx.post(
            f"{base}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
            headers=headers,
            timeout=15.0,
        )
    except Exception as e:
        print(f"[auto_login] 刷新 token 网络异常: {e}")
        return None  # 网络问题：保留 session，下次再试

    if resp.status_code != 200:
        print(f"[auto_login] 刷新 token 失败: {resp.status_code} {resp.text[:200]}")
        _safe_remove(session_path)  # refresh_token 失效，清指针
        return None

    try:
        token_data = resp.json()
    except Exception:
        return None

    access_token = token_data.get("access_token")
    new_refresh = token_data.get("refresh_token") or refresh_token
    if not access_token:
        return None

    # 2) 授权校验（设备指纹 + 授权状态）
    func_headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    try:
        rf = httpx.post(
            f"{base}/functions/v1/verify-license",
            json={"device_id": get_machine_id()},
            headers=func_headers,
            timeout=30.0,
        )
    except Exception as e:
        print(f"[auto_login] 授权校验网络异常: {e}")
        return None  # 网络问题：保留 session

    if rf.status_code != 200:
        print(f"[auto_login] 授权校验失败: {rf.status_code}")
        return None

    try:
        result = rf.json()
    except Exception:
        return None

    if not result.get("ok"):
        reason = result.get("reason", "")
        print(f"[auto_login] 授权未通过: {reason}")
        # 无授权/停用/设备超限：不自动清 session，交给用户手动处理
        return None

    # 3) 回写 refresh_token（Supabase 会轮换，不回写第二次就失败）
    try:
        auth["refresh_token"] = new_refresh
        auth["expires_at"] = result.get("expires_at", auth.get("expires_at"))
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump(auth, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[auto_login] 回写 auth.json 失败: {e}")

    # 4) 设置当前用户 + 初始化数据库 + 刷新授权状态
    from db_config import set_current_user, init_db
    set_current_user(user_id)
    init_db()

    from license_manager import license_mgr
    license_mgr.refresh_status()

    return user_id


def clear_session():
    """退出登录时调用，清除自动登录指针"""
    _safe_remove(get_session_path())


def _safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass