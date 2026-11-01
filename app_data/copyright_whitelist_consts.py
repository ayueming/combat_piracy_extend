# app_data/copyright_whitelist_consts.py
"""
版权方/正版网站白名单。
抓取到的链接如果命中这些域名，直接丢弃（不进入待审核库）。
"""

COPYRIGHT_WHITELIST_DOMAINS = [
    "jjwxc.net",       # 晋江文学城
    "jjwxc.com",       # 晋江文学城
    "qidian.com",      # 起点中文网
    "zongheng.com",    # 纵横中文网
    "ciweimao.com",    # 刺猬猫
    "faloo.com",       # 飞卢小说网
    "hongxiu.com",     # 红袖添香
]

# 标题 / 发布者 双文本匹配用的全名关键词（避免简称误伤标题）
COPYRIGHT_WHITELIST_KEYWORDS = [
    "晋江文学城",
    "起点中文网",
    "纵横中文网",
    "刺猬猫",
    "飞卢小说网",
    "红袖添香",
]

# 仅用于「发布者」字段的简称（发布者通常就是站名简称，标题里不用，防误伤）
COPYRIGHT_WHITELIST_SOURCE_ALIASES = [
    "晋江",
    "起点",
    "纵横",
    "飞卢",
    "红袖",
    "jjwxc", "qidian", "zongheng", "faloo", "hongxiu"
]