# app_data/__init__.py

# 1. 从当前文件夹下的数据文件引入真实常量（注意前面的点 .）
from .complaint_platform_consts import (
    PLATFORM_CONFIG, ALL_SUB_PLATFORMS, CAT_TO_CODE_MAP, CAT_TO_STANDARD_NAME,
    PLATFORM_BAIDU, PLATFORM_QUARK, PLATFORM_UC, PLATFORM_XUNLEI, PLATFORM_OTHER,
    MODULE_SEARCH, MODULE_NETDISK, MODULE_FORUM, MODULE_OTHER,MODULE_TOUTIAO,
    PLATFORM_EXECUTION_ORDER,
)
from .complaint_platform_domains import DOMAIN_RULES
from .complaint_link_features import FEATURE_PATTERNS
from .complaint_consts import COMPLAINT_BATCH_SIZE

# 2. 从当前文件夹下的其他模块引入
from .search_templates import SEARCH_TEMPLATES, get_search_url, get_available_platforms
from .crawl_status_consts import (
    CRAWL_STATUS_PENDING,
    CRAWL_STATUS_ORGANIZED,
    CRAWL_STATUS_DONE,
    CRAWL_STATUS_PARSE_FAILED,
    ALL_CRAWL_STATUS
)

# =========================================================
# ★ 启动时断言校验：防止不同文件之间的名字没对齐
# =========================================================

# 1. 域名规则里的平台名，必须在平台配置中存在
_invalid_domains = set([cat for _, cat in DOMAIN_RULES]) - set(ALL_SUB_PLATFORMS)
if _invalid_domains:
    raise RuntimeError(
        f"【配置致命错误】complaint_platform_domains.py 中存在未在 complaint_platform_consts.py 注册的平台名：{_invalid_domains}"
    )

# 2. 搜索模板里的平台名，必须在平台配置中存在
_invalid_templates = set(SEARCH_TEMPLATES.keys()) - set(ALL_SUB_PLATFORMS)
if _invalid_templates:
    raise RuntimeError(
        f"【配置致命错误】search_templates.py 中存在未在 complaint_platform_consts.py 注册的平台名：{_invalid_templates}"
    )

# 3. 对外暴露的 __all__（方便其他文件使用 from app_data import *）
__all__ = [
    "PLATFORM_CONFIG", "ALL_SUB_PLATFORMS", "CAT_TO_CODE_MAP", "CAT_TO_STANDARD_NAME",
    "PLATFORM_BAIDU", "PLATFORM_QUARK", "PLATFORM_UC", "PLATFORM_XUNLEI", "PLATFORM_OTHER",
    "MODULE_SEARCH", "MODULE_NETDISK", "MODULE_ZHIDAO", "MODULE_TIEBA", "MODULE_TOUTIAO", "MODULE_OTHER",
    "DOMAIN_RULES", "FEATURE_PATTERNS",
    "SEARCH_TEMPLATES", "get_search_url", "get_available_platforms",
    "CRAWL_STATUS_PENDING", "CRAWL_STATUS_ORGANIZED", "CRAWL_STATUS_DONE",
    "CRAWL_STATUS_PARSE_FAILED", "ALL_CRAWL_STATUS",
    "COMPLAINT_BATCH_SIZE"
]