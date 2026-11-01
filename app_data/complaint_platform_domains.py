# app_data/complaint_platform_domains.py
# 数据已迁移至complaint_platform_consts
# 为了向下兼容，保留本文件

from app_data.complaint_platform_consts import PLATFORM_DOMAINS

# 为了向下兼容旧的 import (如 feature_extractor.py)，保持原有的列表格式：
# [("pan.baidu.com", "百度网盘"), ...]

DOMAIN_RULES = []
for platform_name, domains in PLATFORM_DOMAINS.items():
    for domain in domains:
        DOMAIN_RULES.append((domain, platform_name))

# 兼容旧的注释域名 (目前不参与匹配，仅作记录)
# "aliyundrive.com" : 阿里网盘 (后续业务增加再启用)