# app_data/features.py
FEATURE_PATTERNS = [
    r'(?:pan\.baidu\.com/s/|surl=)([a-zA-Z0-9_-]+)',  # 百度网盘
    r'pan\.quark\.cn/s/([a-zA-Z0-9]+)',               # 夸克网盘
    r'drive\.uc\.cn/s/([a-zA-Z0-9]+)',                # UC网盘
    r'pan\.xunlei\.com/s/([a-zA-Z0-9_-]+)',           # 迅雷网盘
    r'zhidao\.baidu\.com/question/(\d+)',             # 百度知道
    r'tieba\.baidu\.com/p/(\d+)',                     # 百度贴吧
]