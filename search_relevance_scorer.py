# relevance_scorer.py
"""
资源相关度计算（纯函数，无数据库、无 UI 依赖）。

接口：
    score(title, body, source_site, signals) -> (float, list[str])
        signals: [{"word": str, "weight": float}, ...]
        返回：加权分数 + 命中的词列表

设计约定：
  - 按"不同词"去重，同一个词出现多次只算一次
  - 标题 / 正文 / 来源网站 任一命中即算
  - 权重从 signals 里读，函数内不硬编码任何权重
  - 未来加位置权重时，加 position_weights 参数，默认 None 行为不变
"""


def score(title, body, source_site, signals, position_weights=None):
    """
    返回 (total_score: float, hit_words: list[str])。
    hit_words 按 signals 列表顺序返回，便于 tooltip 展示。
    """
    title = title or ""
    body = body or ""
    source_site = source_site or ""

    total = 0.0
    hit_words = []

    for sig in signals:
        word = sig.get("word") or ""
        if not word:
            continue

        weight = sig.get("weight", 1.0)

        # 位置权重：第一版不传 position_weights，全部按 1.0 处理
        if position_weights:
            hit_weight = 0.0
            if word in title:
                hit_weight = max(hit_weight, weight * position_weights.get("title", 1.0))
            if word in body:
                hit_weight = max(hit_weight, weight * position_weights.get("body", 1.0))
            if word in source_site:
                hit_weight = max(hit_weight, weight * position_weights.get("source_site", 1.0))
            if hit_weight > 0:
                total += hit_weight
                hit_words.append(word)
        else:
            # 第一版：任意位置命中即加一次权重（去重）
            if word in title or word in body or word in source_site:
                total += weight
                hit_words.append(word)

    return total, hit_words