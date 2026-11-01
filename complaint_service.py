# complaint_service.py
from collections import defaultdict
from PySide6.QtCore import Qt
from db_config import get_conn

# ★ 引入最新的常量配置
from app_data import (
    CAT_TO_CODE_MAP, CAT_TO_STANDARD_NAME, COMPLAINT_BATCH_SIZE,
    PLATFORM_OTHER, MODULE_OTHER,
)


def prepare_complaints_data(model, book_list):
    """
    从模型中提取勾选的数据，按【分类+书籍】分组，并分别按 COMPLAINT_BATCH_SIZE 切片。
    """
    checked_data = []
    missing_books = set()

    conn = get_conn()
    book_details = {
        row[1]: {
            "aliases": row[2],
            "platform_id": row[3],
            "evidence_path": row[4],
            "rights_holder": row[5],
            "baidu_id": row[6]
        }
        for row in
        conn.execute(
            "SELECT id, name, aliases, platform_id, evidence_path, rights_holder, baidu_id FROM books").fetchall()
    }
    conn.close()

    for row in range(model.rowCount()):
        chk_item = model.item(row, 0)
        if chk_item and chk_item.checkState() == Qt.Checked:
            db_id = chk_item.data(Qt.UserRole)
            if not db_id: continue

            book_name = model.item(row, 1).text()

            aliases = ""
            p_id = ""
            evidence_path = ""
            rights_holder = ""
            baidu_id = ""

            if book_name in book_details:
                aliases = book_details[book_name].get("aliases", "")
                p_id = book_details[book_name].get("platform_id", "")
                evidence_path = book_details[book_name].get("evidence_path", "")
                rights_holder = book_details[book_name].get("rights_holder", "")
                baidu_id = book_details[book_name].get("baidu_id", "")

            # ==========================================
            # 1. 数据归一化（先判断是否 other，提前 continue）
            # ==========================================
            raw_cat = model.item(row, 2).text().strip()

            # 查字典获取代号 (如果没查到，默认 other)
            code_info = CAT_TO_CODE_MAP.get(
                raw_cat, {"platform": PLATFORM_OTHER, "module": MODULE_OTHER}
            )

            # ★ 兜底过滤：不支持自动投诉的平台直接跳过，不参与 missing 校验、不进入批次
            if code_info.get("platform") == PLATFORM_OTHER:
                continue

            # ==========================================
            # 2. 校验：晋江书号、维权书、权利人缺一不可
            #    （只对"要真跑"的行校验，other 行已经在上一步 continue 掉了）
            # ==========================================
            if not p_id or not evidence_path or not rights_holder:
                missing_books.add(book_name)

            # ==========================================
            # 3. 源头统一拼装长文本需要的字符串
            # ==========================================
            url_str = f"https://www.jjwxc.net/onebook.php?novelid={p_id}" if p_id else ""

            clean_book = book_name.strip("《》").strip()
            clean_aliases = aliases.strip("《》").strip()

            if clean_aliases:
                name_str = f"《{clean_book}（原名：{clean_aliases}）》"
            else:
                name_str = f"《{clean_book}》"

            # 查字典获取标准显示名
            standard_cat = CAT_TO_STANDARD_NAME.get(raw_cat, raw_cat)

            checked_data.append({
                "id": db_id,
                "book": book_name,
                "aliases": aliases,
                "platform_id": p_id or "",
                "evidence_path": evidence_path or "",
                "rights_holder": rights_holder or "",
                "baidu_id": baidu_id or "",
                "cat": standard_cat,
                "url": model.item(row, 3).text().replace(" (重复资源链接)", "").strip(),
                "name": model.item(row, 4).text(),
                "url_str": url_str,
                "name_str": name_str,
                "platform_code": code_info["platform"],
                "module_code": code_info["module"],
                "web_text": code_info.get("web_text", ""),
            })

    if not checked_data:
        return [], missing_books

    # 【核心逻辑】严格按照 (分类, 书名) 进行双重分组
    grouped_data = defaultdict(list)
    for item in checked_data:
        cat = item["cat"] or "未分类"
        book = item["book"] or "未关联"
        grouped_data[(cat, book)].append(item)

    batches = []

    # 遍历每个“分类+书名”组合，对每个组合再按 COMPLAINT_BATCH_SIZE 切分
    for (cat, book), items in grouped_data.items():
        for i in range(0, len(items), COMPLAINT_BATCH_SIZE):
            batches.append(items[i:i + COMPLAINT_BATCH_SIZE])

    return batches, missing_books