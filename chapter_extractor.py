import re

# 预设的规则字典，以后想加什么“第X回”、“第X卷”，直接在这里加即可
CHAPTER_PATTERNS = {
    "第X章": r"第\s*[\d一二三四五六七八九十百千万]+\s*章",
    "第X节": r"第\s*[\d一二三四五六七八九十百千万]+\s*节",
    "分节阅读X": r"分节阅读\s*\d+",
    "纯数字": r"^\d+$"
}


def is_target_chapter(title, rule_name, custom_keyword=""):
    """
    判断一个标题是否符合提取规则。
    """
    # 如果是自定义关键字，直接判断标题是否包含这个词
    if rule_name == "自定义关键字":
        if not custom_keyword:
            return False
        return custom_keyword in title

    # 否则使用正则匹配
    pattern = CHAPTER_PATTERNS.get(rule_name)
    if pattern:
        return bool(re.search(pattern, title))

    return False