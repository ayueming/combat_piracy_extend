# config.py —— 配置加载器（开源版本，不含真实密钥）
import sys

# ===== 默认值：任何情况下都必须存在 =====
SUPABASE_URL = ""
SUPABASE_ANON_KEY = ""
DEV_MODE = False


# ===== 1. 本地开发配置：优先加载 config_local.py =====
try:
    from config_local import SUPABASE_URL, SUPABASE_ANON_KEY, DEV_MODE
except ImportError:
    pass  # 没有本地配置，使用默认值


# ===== 2. 打包时注入的 _secrets.py（覆盖上面的 URL/key）=====
#   注意：_secrets.py 只包含 URL 和 anon key，不含 DEV_MODE
try:
    from _secrets import SUPABASE_URL, SUPABASE_ANON_KEY
except ImportError:
    pass


def is_dev_mode() -> bool:
    """
    是否处于开发模式（可跳过登录）。
    - 打包成 exe 后：永远返回 False（即使 DEV_MODE=True 也不行）
    - 源码运行且 DEV_MODE=True：返回 True
    """
    if getattr(sys, 'frozen', False):
        return False
    return bool(DEV_MODE)


def has_supabase_config() -> bool:
    """是否有可用的 Supabase 配置（URL 和 key 都非空）"""
    return bool(SUPABASE_URL) and bool(SUPABASE_ANON_KEY)