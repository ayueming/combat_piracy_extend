# data_importer.py
import csv
import os
import sqlite3
from db_config import get_conn
from feature_extractor import extract_pure_feature

# ★ 统一从 app_data 推导，不再手工维护白名单。
#   PLATFORM_CONFIG 新增/删除平台时，导入校验会自动同步。
from app_data import ALL_SUB_PLATFORMS

VALID_CATEGORIES = set(ALL_SUB_PLATFORMS)


def import_sites_from_file(file_path):
    """
    核心导入逻辑，极度严格校验模式。
    返回 (成功数量, 重复数量, 错误明细列表)
    """
    ext = os.path.splitext(file_path)[1].lower()
    rows = []

    # 1. 读取文件
    if ext == '.csv':
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            rows = list(csv.reader(f))
    elif ext == '.xlsx':
        try:
            import openpyxl
        except ImportError:
            raise ImportError("读取 Excel 需要 openpyxl 模块。\n请在终端运行：pip install openpyxl")

        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if any(row):
                rows.append([str(cell) if cell is not None else "" for cell in row])
    else:
        raise ValueError("不支持的文件格式，仅支持 .csv 或 .xlsx")

    if not rows or len(rows) <= 1:
        raise ValueError("文件里没有有效数据（必须包含表头且至少有一行数据）！")

    # 2. 智能识别表头
    header = rows[0]
    col_idx = {"pid": 0, "book": 1, "cat": 2, "url": 3, "name": 4, "attr": 5, "time": 6, "status": 7}

    for i, h in enumerate(header):
        h_str = str(h).strip().lower()
        if "书号" in h_str or "晋江id" in h_str or "作品id" in h_str:
            col_idx["pid"] = i
        elif "作品" in h_str or "中文" in h_str or "书名" in h_str:
            col_idx["book"] = i
        elif "分类" in h_str or "平台" in h_str:
            col_idx["cat"] = i
        elif "链接" in h_str or "网址" in h_str or "url" in h_str:
            col_idx["url"] = i
        elif "名称" in h_str or "描述" in h_str:
            col_idx["name"] = i
        elif "属性" in h_str:
            col_idx["attr"] = i
        elif "投诉" in h_str or "日期" in h_str or "时间" in h_str:
            col_idx["time"] = i
        elif "状态" in h_str:
            col_idx["status"] = i

    # 3. 准备数据库数据
    conn = get_conn()
    cursor = conn.cursor()

    # 提取系统内的书籍字典用于严格比对
    books_dict = {name: b_id for b_id, name in conn.execute("SELECT id, name FROM books").fetchall()}
    platform_dict = {
        str(pid): (b_id, name)
        for b_id, pid, name in conn.execute(
            "SELECT id, platform_id, name FROM books WHERE platform_id IS NOT NULL AND platform_id != ''").fetchall()
    }

    success_count = 0
    duplicate_count = 0
    error_details = []  # 记录所有解析失败的行

    # 4. 遍历数据行进行“极度严格”校验
    for row_idx, row in enumerate(rows[1:], start=2):
        if len(row) <= col_idx["url"]:
            error_details.append(f"第 {row_idx} 行：字段太少，缺少链接列。")
            continue

        # 提取所有字段并去除首尾空格
        url = str(row[col_idx["url"]]).strip()
        cat = str(row[col_idx["cat"]]).strip() if len(row) > col_idx["cat"] else ""
        name = str(row[col_idx["name"]]).strip() if len(row) > col_idx["name"] else ""
        attr = str(row[col_idx["attr"]]).strip() if len(row) > col_idx["attr"] else ""
        comp_time = str(row[col_idx["time"]]).strip() if len(row) > col_idx["time"] else ""
        status = str(row[col_idx["status"]]).strip() if len(row) > col_idx["status"] else ""

        excel_pid = str(row[col_idx["pid"]]).strip() if len(row) > col_idx["pid"] else ""
        excel_book = str(row[col_idx["book"]]).strip() if len(row) > col_idx["book"] else ""

        # 清洗可能带有的书名号（用于匹配）
        clean_excel_book = excel_book.strip("《》 ")

        # --- 开始闸机校验 ---
        row_errors = []

        # 校验1：必填项缺失
        if not url:
            row_errors.append("缺失【资源链接】")

        if not cat:
            row_errors.append("缺失【资源分类】")
        elif cat not in VALID_CATEGORIES:
            row_errors.append(f"【资源分类】'{cat}'不属于系统预设分类")

        if not excel_pid:
            row_errors.append("缺失【晋江书号】")

        if not clean_excel_book:
            row_errors.append("缺失【关联作品】(书名)")

        # 如果任何必填项缺失或格式错误，直接记录错误并跳过本行
        if row_errors:
            error_details.append(f"第 {row_idx} 行：{'；'.join(row_errors)}")
            continue

        # --- 校验2：书号与书名的匹配校验 ---
        if excel_pid not in platform_dict:
            error_details.append(f"第 {row_idx} 行：书号【{excel_pid}】在系统中不存在，请先前往【作品管理】添加。")
            continue

        sys_id, sys_name = platform_dict[excel_pid]

        # 核对系统里的书名和表格里的书名是否一致（兼容带不带书名号）
        clean_sys_name = sys_name.strip("《》 ")
        if clean_excel_book != clean_sys_name:
            error_details.append(
                f"第 {row_idx} 行：书号【{excel_pid}】在系统中的对应书名是《{sys_name}》，与您填写的《{clean_excel_book}》不匹配，请核对！"
            )
            continue

        # --- 校验3：查重 ---
        pure_code = extract_pure_feature(url)
        cursor.execute("SELECT id FROM sites WHERE feature_code = ?", (pure_code,))
        if cursor.fetchone():
            duplicate_count += 1
            continue

        # --- 校验全数通过，入库 ---
        try:
            # 强制使用系统里的标准名字入库，防止用户多敲空格
            final_book_name = sys_name

            # ★ 关键修复：同步写入 target_platform，与页面 save_row_to_db 保持一致。
            #   page_links.refresh_table() 的"资源分类"列读的就是 target_platform。
            cursor.execute('''INSERT INTO sites
                              (category, target_platform, site_url, name, attr, feature_code, complaint_time,
                               resource_status, book_id, book_name)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (cat, cat, url, name, attr, pure_code, comp_time, status, sys_id, final_book_name))
            success_count += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

    return success_count, duplicate_count, error_details