# app_data/crawl_consts.py
"""
抓取和解析相关参数配置
"""

# 最大抓取页数
CRAWL_MAX_PAGES = 3

# 页面首屏等待时间（毫秒），应对动态渲染
CRAWL_FIRST_WAIT_MS = 3000

# 翻页后的等待时间区间（毫秒），随机取值以反爬
CRAWL_PAGING_WAIT_MS_RANGE = (3500, 6000)

# 页面加载超时时间（毫秒）
CRAWL_PAGE_TIMEOUT_MS = 15000

# 百度跳转链接解析超时时间（毫秒）
CRAWL_REDIRECT_TIMEOUT_MS = 8000