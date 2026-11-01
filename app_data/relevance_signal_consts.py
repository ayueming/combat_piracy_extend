# app_data/relevance_signal_consts.py
"""
资源相关度信号词库（系统自带，纯数据，不含任何逻辑）。

用途：判断一条链接与"盗版资源"的相关程度，结果写入 sites.relevance。
     只影响"未知网站"这一档的排序，不参与分档。

规则：
  - 命中的不同信号加权求和（按不同信号去重，不按出现次数）
  - 匹配范围：标题 / 正文 / 网站域名（source_site）
  - 第一版权重全 1.0，后续按实际数据调整

⚠️ 本文件是纯数据配置，不要写任何逻辑。
   计算逻辑见 relevance_scorer.py。
   用户自定义词库走数据库 user_signals 表（后续实现），不写本文件。
"""

# 格式：[{"word": str, "weight": float}, ...]
# 分组注释只是给人看的，计算时拍平成一个列表遍历
RELEVANCE_SIGNALS = [
    # ---- 强信号：提取码 / 网盘域名 ----
    {"word": "提取码", "weight": 1.0},
    {"word": "pan.baidu.com", "weight": 1.0},
    {"word": "lanzou", "weight": 1.0},
    {"word": "aliyundrive", "weight": 1.0},
    {"word": "123pan", "weight": 1.0},
    {"word": "回复可见", "weight": 1.0},

    # ---- 阅读站信号 ----
    {"word": "免费阅读", "weight": 1.0},
    {"word": "全文阅读", "weight": 1.0},
    {"word": "在线阅读", "weight": 1.0},
    {"word": "无弹窗", "weight": 1.0},
    {"word": "最新章节", "weight": 1.0},
    {"word": "全文免费", "weight": 1.0},

    # ---- 下载站信号 ----
    {"word": "txt下载", "weight": 1.0},
    {"word": "全集下载", "weight": 1.0},
    {"word": "电子书下载", "weight": 1.0},
    {"word": "打包下载", "weight": 1.0},
    {"word": "全本", "weight": 1.0},
    {"word": "精校版", "weight": 1.0},

    # ---- 弱信号（宽词，先放着看数据） ----
    {"word": "资源", "weight": 1.0},
    {"word": "免费", "weight": 1.0},
    {"word": "分享", "weight": 1.0},
]