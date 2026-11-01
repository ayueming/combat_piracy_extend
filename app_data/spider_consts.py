# app_data/spider_consts.py
"""
待抓取页面（SpiderPage）相关的业务常量。

================================================================
★ 维护手册（基于 module 判断）
================================================================

本文件通过读取 PLATFORM_CONFIG 里的 module 字段，自动推导
"哪些分类不需要抓章节"。

【规则】
  1. 只有明确属于以下 module 的分类，才不会进入待抓取页面：
     - MODULE_NETDISK (网盘)
     - MODULE_ZHIDAO (百度知道)
     - MODULE_TIEBA (百度贴吧)
  2. 其余 module（包括 MODULE_SEARCH 搜索、MODULE_OTHER 其他、暂未开通等）
     全部视为需要抓取，【会】出现在待抓取页面。

【为什么这么设计？】
  - 搜索页（search）虽然本身不抓章节，但用户可能将普通小说站误分类为“夸克搜索”。
    为了让这类错分数据也能被 Spider 捞出来抓章节，我们不排除 search。
  - 暂未开通 (other) 和 其他 (other) 也视为普通站点，进入 Spider。

【新增平台时怎么做】
  · 如果新增的是网盘 / 知道 / 贴吧：
      → 在 PLATFORM_CONFIG 中将其 module 设为对应的值
      → 本文件【无需改动】，自动排除
  · 如果新增的是其他类型（包括搜索、小说站等）：
      → 本文件【无需改动】，自动进入待抓取页
================================================================
"""
from app_data.complaint_platform_consts import (
    PLATFORM_CONFIG,
    MODULE_NETDISK,
    MODULE_ZHIDAO,
    MODULE_TIEBA,
)

# 不需要抓章节的 module 集合（属于这些模块的不进 Spider）
_MODULES_TO_EXCLUDE = {
    MODULE_NETDISK,
    MODULE_ZHIDAO,
    MODULE_TIEBA,
}

def _build_no_crawl_categories():
    """从 PLATFORM_CONFIG 推导出所有不需要抓章节的分类名。"""
    cats = set()
    for sub_list in PLATFORM_CONFIG.values():
        for display_name, _p_code, m_code, _web_text, _aliases in sub_list:
            if m_code in _MODULES_TO_EXCLUDE:
                cats.add(display_name)
    return cats

# 待抓取页面应从 sites 表中排除的分类
NO_CHAPTER_CRAWL_CATEGORIES = _build_no_crawl_categories()