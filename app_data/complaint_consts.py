# app_data/complaint_consts.py

"""
投诉业务常量。
"""

# 批次大小：按 (分类, 书籍) 分组后，每组每 N 条切一批
COMPLAINT_BATCH_SIZE = 200

# 暂未在 PLATFORM_CONFIG 注册，但需要识别为网盘的域名
# ★ 已迁移至 PLATFORM_DOMAINS["暂未开通"]，本列表保留为空以兼容旧 import。
#   新代码请直接使用 PLATFORM_DOMAINS，不要再往这里加域名。
MISC_NETDISK_DOMAINS = []