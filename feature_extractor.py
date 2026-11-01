# feature_extractor.py
import re
from app_data import DOMAIN_RULES, FEATURE_PATTERNS, ALL_SUB_PLATFORMS

def get_platform_category(url):
    """
    根据链接自动识别平台分类。
    返回匹配到的标准显示名（必须存在于 ALL_SUB_PLATFORMS 中），识别不到返回空字符串。
    """
    if not url:
        return ""

    url_lower = url.lower()

    # 1. 优先匹配具体域名（如网盘直链）
    for domain, cat_name in DOMAIN_RULES:
        if domain in url_lower:
            # ★ 核心防御：只有当该分类存在于当前系统配置中时才返回
            if cat_name in ALL_SUB_PLATFORMS:
                return cat_name
            return ""

    # 2. 兜底：如果是普通的 baidu.com 链接，识别为百度搜索
    if "baidu.com" in url_lower and "百度搜索" in ALL_SUB_PLATFORMS:
        return "百度搜索"

    # 3. 兜底：如果是普通的 quark.cn 链接，识别为夸克搜索
    if "quark.cn" in url_lower and "夸克搜索" in ALL_SUB_PLATFORMS:
        return "夸克搜索"

    return ""


def extract_pure_feature(url):
    """
    智能提取纯净的特征码。
    """
    url = url.strip()

    if url.startswith("1http"):
        url = url[1:]
    elif url.startswith("1") and len(url) > 20 and not url.startswith("http"):
        url = url[1:]

    code = ""

    # ★ 循环遍历正则列表进行匹配
    for pattern in FEATURE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            code = match.group(1)
            break

    # 如果没匹配到具体的规则，就把整个 url 作为特征码
    if not code:
        code = url

    # 去除开头可能误带的 '1'
    if code.startswith('1') and len(code) >= 20:
        code = code[1:]

    return code