# app_data/ext_search_strategies.py
"""
插件模式（browser extension）专用搜索抓取策略。

★ strategy 结构：
  - mode: "click" | "scroll"
      click  -> 找到 nextBtnSelector 并点击
      scroll -> 向下滚动触发瀑布流加载
  - scanner: "generic" | "tieba"
      generic -> 按 selector 提取（resultSelector -> titleSelector/bodySelector/sourceSelector）
      tieba   -> 走贴吧专用扫描（卡片结构特殊，selector 不通用）
  - resultSelector  结果容器（每条结果的外层包裹）
  - titleSelector   标题元素（a 标签，从此读 href 和 innerText）
  - bodySelector    正文摘要（可选）
  - sourceSelector  来源网站（可选）
  - nextBtnSelector 翻页按钮（仅 click 模式）
"""

DEFAULT_EXT_STRATEGY = {
    "mode": "click",
    "scanner": "generic",
    "resultSelector": "",
    "titleSelector": "",
    "bodySelector": "",
    "sourceSelector": "",
    "nextBtnSelector": "",
}

EXT_SEARCH_STRATEGIES = {
    "百度搜索": {
        "mode": "click",
        "scanner": "generic",
        "resultSelector": "#content_left .result, #content_left .c-container",
        "titleSelector": "h3 a",
        "bodySelector": ".c-abstract, [data-module='abstract']",
        "sourceSelector": ".c-showurl, .siteLink_9TPP3, .g",
        # ★ 改成下面这样：把所有可能是分页的 a 标签都抓过来
        "nextBtnSelector": "a.n, .page-box a, a[href*='pn=']",
    },
    "百度知道": {
        "mode": "click",
        "scanner": "generic",
        "resultSelector": "dl.dl",
        "titleSelector": "dt.dt a.ti",
        "bodySelector": "dd.answer",
        "sourceSelector": "dd.explain a.f-lighter",
        "nextBtnSelector": "a.pager-next",
    },
    "百度贴吧": {
        "mode": "scroll",
        "scanner": "tieba",
        # 贴吧卡片结构特殊，selector 在 content.js 的 scanTieba() 内部处理
    },
    "夸克搜索": {
        "mode": "scroll",
        "scanner": "generic",
        # ★ 核心修改：加上 .pc-s-grid-content-left 限制，只抓左侧真实结果
        "resultSelector": ".pc-s-grid-content-left .qk-card",
        "titleSelector": ".qk-title-content a",
        "bodySelector": ".qk-paragraph-text",
        "sourceSelector": ".qk-source-item",
        "nextBtnSelector": None,
    },
}


def get_ext_strategy(platform):
    """获取插件抓取策略，找不到则回退到默认策略。"""
    return EXT_SEARCH_STRATEGIES.get(platform, DEFAULT_EXT_STRATEGY)