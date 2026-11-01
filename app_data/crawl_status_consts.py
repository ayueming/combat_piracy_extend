# app_data/crawl_status_consts.py

# 基础状态
CRAWL_STATUS_PENDING      = "pending"        # 刚爬下、待解析
CRAWL_STATUS_ORGANIZED    = "organized"      # 已解析、等用户分流
CRAWL_STATUS_DONE         = "done"           # 已归档入库
CRAWL_STATUS_UNMATCHED    = "unmatched"      # 关键词未命中
CRAWL_STATUS_PARSE_FAILED = "parse_failed"   # 解析失败
CRAWL_STATUS_WHITELIST    = "whitelist"      # 命中版权白名单
CRAWL_STATUS_IGNORED      = "ignored"        # 命中黑名单 / 已拉黑

# ★ 新增：已在 sites 或同批草稿中存在
CRAWL_STATUS_DUPLICATE    = "duplicate"

# 集合（导出所有状态供外部遍历使用）
ALL_CRAWL_STATUS = (
    CRAWL_STATUS_PENDING,
    CRAWL_STATUS_ORGANIZED,
    CRAWL_STATUS_DONE,
    CRAWL_STATUS_UNMATCHED,
    CRAWL_STATUS_PARSE_FAILED,
    CRAWL_STATUS_WHITELIST,
    CRAWL_STATUS_IGNORED,
    CRAWL_STATUS_DUPLICATE,
)