# app_data/search_templates.py
"""
检索入口模板表。
"""
from urllib.parse import quote
from app_data import ALL_SUB_PLATFORMS

# =========================================================
# ★ 自定义搜索引擎下拉框的展示顺序 (按此列表的先后顺序)
# =========================================================
SEARCH_PLATFORM_PRIORITY = [
    "百度搜索",
    # "uc搜索",
    "夸克搜索",
    "百度知道",
    "百度贴吧",
]

SEARCH_TEMPLATES = {
    "百度搜索": {
        "template": "https://www.baidu.com/s?wd={kw}",
        "mode": "direct",
        "exact_support": "quote",
        "note": "",
    },
    "百度知道": {
        "template": "https://zhidao.baidu.com/search?word={kw}",
        "mode": "direct",
        "exact_support": "none",
        "note": "百度知道站内搜索",
    },
    "百度贴吧": {
        "template": "https://tieba.baidu.com/f/search/res?ie=utf-8&tab=thread&qw={kw}", # ★ 加上了 tab=thread
        "mode": "direct",
        "exact_support": "none",
        "note": "贴吧全站搜索(仅贴子)",
    },
    "夸克搜索": {
        "template": "https://www.quark.cn/s/?q={kw}",
        "mode": "direct",
        "exact_support": "none",
        "note": "",
    },
    # "uc搜索": {
        # "template": "https://so.m.sm.cn/s?q={kw}",
        # "mode": "direct",
        # "exact_support": "none",
        # "note": "神马搜索",
    # },
}


def get_search_url(platform, keyword, exact=False):
    """
    根据平台、关键词拼出搜索 URL。
    只要平台支持双引号，就强制加上，以达到尽量准确的目的。
    """
    if platform not in SEARCH_TEMPLATES:
        raise ValueError(f"平台「{platform}」没有配置搜索模板")

    cfg = SEARCH_TEMPLATES[platform]
    kw = keyword.strip()

    # 核心逻辑：支持就加双引号
    if cfg["exact_support"] == "quote":
        kw = f'"{kw}"'

    return cfg["template"].format(kw=quote(kw))


def get_available_platforms():
    """检索控制台可选的平台列表，按自定义优先级排序。"""
    # 1. 先过滤出所有有搜索模板的平台
    available = [p for p in ALL_SUB_PLATFORMS if p in SEARCH_TEMPLATES]

    # 2. 按照自定义优先级排序
    def sort_key(platform):
        if platform in SEARCH_PLATFORM_PRIORITY:
            return SEARCH_PLATFORM_PRIORITY.index(platform)
        return 999

        # 3. 返回排序后的结果

    return sorted(available, key=sort_key)


# 启动时校验：模板键必须都是合法平台名
_invalid = set(SEARCH_TEMPLATES) - set(ALL_SUB_PLATFORMS)
if _invalid:
    raise RuntimeError(
        f"search_templates.py 中存在未在 PLATFORM_CONFIG 注册的平台名：{_invalid}"
    )