# link_ingest_service.py
import sqlite3
import time
import random
import json
import re
import threading
from datetime import datetime

from db_config import get_conn
from feature_extractor import extract_pure_feature
from app_data.crawl_status_consts import (
    CRAWL_STATUS_PENDING, CRAWL_STATUS_ORGANIZED, CRAWL_STATUS_DONE,
    CRAWL_STATUS_PARSE_FAILED, CRAWL_STATUS_UNMATCHED,
    CRAWL_STATUS_WHITELIST, CRAWL_STATUS_IGNORED, CRAWL_STATUS_DUPLICATE
)
from app_data.copyright_whitelist_consts import (
    COPYRIGHT_WHITELIST_DOMAINS,
    COPYRIGHT_WHITELIST_KEYWORDS,
    COPYRIGHT_WHITELIST_SOURCE_ALIASES,
)
from app_data.crawl_consts import CRAWL_REDIRECT_TIMEOUT_MS
from app_data.complaint_platform_consts import PLATFORM_DOMAINS

from search_relevance_scorer import score as score_relevance
from app_data.relevance_signal_consts import RELEVANCE_SIGNALS

from app_data.complaint_platform_consts import PLATFORM_DOMAINS, ACTIVE_NETDISK_DOMAINS

_db_checked = False
_db_lock = threading.Lock()  # ★ 新增：数据库初始化锁，防止多线程并发建表报错


def _log_short_resolve(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "short_resolve.log"), "a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        pass


def _hit_whitelist(title, source_site, url=""):
    s = source_site or ""
    u = (url or "").lower()

    for kw in COPYRIGHT_WHITELIST_KEYWORDS:
        if kw in s:
            return True
    for d in COPYRIGHT_WHITELIST_DOMAINS:
        if d in u:
            return True
    for alias in COPYRIGHT_WHITELIST_SOURCE_ALIASES:
        if s.strip() == alias:
            return True

    return False


def ensure_db_columns():
    global _db_checked
    if _db_checked:
        return

    with _db_lock:
        if _db_checked:
            return

        conn = get_conn()
        cursor = conn.cursor()

        # ★ 核心改进：先确保所有基础表都存在，防止查表或改表时报 "no such table"
        try:
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS ignored_links
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               site_url
                               TEXT
                               UNIQUE,
                               add_time
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS draft_links
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               site_url
                               TEXT,
                               name
                               TEXT,
                               body_text
                               TEXT,
                               source_site
                               TEXT,
                               feature_code
                               TEXT,
                               source_platform
                               TEXT,
                               source_keyword
                               TEXT,
                               source_url
                               TEXT,
                               attr
                               TEXT,
                               book_id
                               INTEGER,
                               book_name
                               TEXT,
                               category
                               TEXT,
                               crawl_status
                               TEXT,
                               fetch_time
                               TEXT,
                               batch_id
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS sites
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               site_url
                               TEXT,
                               name
                               TEXT,
                               body_text
                               TEXT,
                               source_site
                               TEXT,
                               feature_code
                               TEXT,
                               book_id
                               INTEGER,
                               book_name
                               TEXT,
                               category
                               TEXT,
                               target_platform
                               TEXT,
                               source_platform
                               TEXT,
                               source_keyword
                               TEXT,
                               source_url
                               TEXT,
                               attr
                               TEXT,
                               fetch_time
                               TEXT,
                               batch_id
                               TEXT,
                               domain_matched
                               INTEGER,
                               relevance
                               REAL,
                               relevance_hits
                               TEXT,
                               crawl_status
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS user_signals
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               word
                               TEXT
                               UNIQUE
                               NOT
                               NULL,
                               weight
                               REAL
                               DEFAULT
                               1.0,
                               add_time
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS search_tasks
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               book_id
                               INTEGER,
                               book_name
                               TEXT
                               NOT
                               NULL,
                               platform
                               TEXT
                               NOT
                               NULL,
                               main_keyword
                               TEXT
                               NOT
                               NULL,
                               sub_keywords
                               TEXT,
                               max_pages
                               INTEGER
                               DEFAULT
                               3,
                               status
                               TEXT
                               DEFAULT
                               'ready',
                               last_batch_id
                               TEXT,
                               created_at
                               TEXT,
                               last_run_at
                               TEXT
                           )
                           """)
            conn.commit()
        except Exception as e:
            print(f"[DB] 基础表初始化检查完毕 (可能有已存在的): {e}")

        # ★ 第二步：逐个检查并添加缺失的字段（加了独立的异常捕获，避免一处报错导致全盘中断）
        try:
            cursor.execute("PRAGMA table_info(ignored_links)")
            ignored_columns = [row[1] for row in cursor.fetchall()]
            if ignored_columns and "title" not in ignored_columns:
                try:
                    cursor.execute("ALTER TABLE ignored_links ADD COLUMN title TEXT")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e): print(e)
        except Exception as e:
            print(f"[DB] ignored_links 字段检查跳过: {e}")

        try:
            cursor.execute("PRAGMA table_info(draft_links)")
            draft_cols = [row[1] for row in cursor.fetchall()]
            if draft_cols:
                for col, col_type in [("parent_url", "TEXT"), ("parent_title", "TEXT"),
                                      ("has_pan", "INTEGER DEFAULT 0")]:
                    if col not in draft_cols:
                        try:
                            cursor.execute(f"ALTER TABLE draft_links ADD COLUMN {col} {col_type}")
                        except sqlite3.OperationalError as e:
                            if "duplicate column name" not in str(e): print(e)
        except Exception as e:
            print(f"[DB] draft_links 字段检查跳过: {e}")

        try:
            cursor.execute("PRAGMA table_info(sites)")
            sites_cols = [row[1] for row in cursor.fetchall()]
            if sites_cols:
                for col in ["parent_url", "parent_title", "original_title"]:
                    if col not in sites_cols:
                        try:
                            cursor.execute(f"ALTER TABLE sites ADD COLUMN {col} TEXT")
                        except sqlite3.OperationalError as e:
                            if "duplicate column name" not in str(e): print(e)
        except Exception as e:
            print(f"[DB] sites 字段检查跳过: {e}")

        conn.commit()
        conn.close()
        _db_checked = True
        print("[DB] 数据库结构自动检查完成。")


def save_picked_link(url, title, ctx, body="", source_site="", parent_url="", parent_title="", is_manual=False,
                     category=None):
    ensure_db_columns()

    raw_url = (url or "").replace(" ", "").replace("\n", "").replace("\r", "")

    url_match = re.search(r'https?://[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=%]+', raw_url)
    if url_match:
        url = url_match.group(0)
    else:
        return None, False, False

    if "pan.baidu.com/share/init?surl=" in url:
        url = url.replace("/share/init?surl=", "/s/1")
        url = url.replace("&pwd=", "?pwd=")

    if not url.lower().startswith(("http://", "https://")):
        return None, False, False

    ctx = ctx or {}
    source_platform = (ctx.get("source_platform") or "").strip()
    source_keyword = (ctx.get("keyword") or "").strip()
    source_url = (ctx.get("source_url") or "").strip()
    book_name = (ctx.get("book_name") or "").strip()
    book_id = ctx.get("book_id")
    batch_id = (ctx.get("batch_id") or "").strip()
    pick_origin = (ctx.get("pick_origin") or "").strip()

    if not source_url and parent_url:
        source_url = parent_url

    if book_id in (None, "", 0):
        book_id = None
    elif isinstance(book_id, str) and book_id.isdigit():
        book_id = int(book_id)

    # ★ 优先使用传入的 category（浮窗手动选择）
    if not category:
        category = source_platform or "其他"

    feature_code = extract_pure_feature(url)
    page_title = (title or "").strip()[:200]
    source_site_text = (source_site or "").strip()
    fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    bg_text = ""
    if parent_title:
        bg_text += f"[来源页面: {parent_title}] "
    if body:
        bg_text += body
    body_text = bg_text.strip()

    conn = get_conn()
    cursor = conn.cursor()
    try:
        final_status = CRAWL_STATUS_PENDING

        if cursor.execute("SELECT id FROM draft_links WHERE site_url = ? LIMIT 1", (url,)).fetchone():
            print(f"♻️ 链接已在待处理草稿中，跳过: {url}")
            # 直接返回一个伪记录，告诉外部不用刷新
            return {
                "db_id": None, "book_name": book_name, "category": category, "site_url": url,
                "name": page_title, "body_text": body_text, "source_site": source_site_text,
                "attr": pick_origin, "feature_code": feature_code, "crawl_status": "duplicate",
                "complaint_time": "", "resource_status": "", "source_platform": source_platform,
                "source_keyword": source_keyword, "source_url": source_url, "fetch_time": fetch_time,
                "batch_id": batch_id, "domain_matched": 0
            }, True, False

        if _hit_whitelist(page_title, source_site_text, url):
            final_status = CRAWL_STATUS_WHITELIST

        if final_status == CRAWL_STATUS_PENDING and not is_manual:
            clean_kw = source_keyword.split()[0] if source_keyword else ""
            if clean_kw:
                def clean_text(t):
                    return re.sub(r'[\s\W]+', '', t or "")

                t_clean = clean_text(page_title)
                b_clean = clean_text(body_text)
                kw_clean = clean_text(clean_kw)

                if not ((kw_clean in t_clean) or (kw_clean in b_clean)):
                    final_status = CRAWL_STATUS_UNMATCHED

        if final_status == CRAWL_STATUS_PENDING:
            if page_title and cursor.execute(
                    "SELECT id FROM ignored_links WHERE title = ? AND title != '' LIMIT 1", (page_title,)
            ).fetchone():
                final_status = CRAWL_STATUS_IGNORED

        # ★ 把 parent_url 和 parent_title 写入数据库
        cursor.execute(
            "INSERT INTO draft_links (site_url, name, body_text, source_site, feature_code, "
            "source_platform, source_keyword, source_url, attr, book_id, book_name, category, "
            "crawl_status, fetch_time, batch_id, parent_url, parent_title) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (url, page_title, body_text, source_site_text, feature_code,
             source_platform, source_keyword, source_url, pick_origin,
             book_id, book_name or None, category, final_status, fetch_time,
             batch_id, parent_url or None, parent_title or None)
        )
        conn.commit()
        db_id = str(cursor.lastrowid)
    finally:
        conn.close()

    record = {
        "db_id": db_id, "book_name": book_name, "category": category, "site_url": url,
        "name": page_title, "body_text": body_text, "source_site": source_site_text,
        "attr": pick_origin, "feature_code": feature_code, "crawl_status": final_status,
        "complaint_time": "", "resource_status": "", "source_platform": source_platform,
        "source_keyword": source_keyword, "source_url": source_url, "fetch_time": fetch_time,
        "batch_id": batch_id, "domain_matched": 0
    }

    is_new = (final_status == CRAWL_STATUS_PENDING)
    return record, (not is_new), is_new


def organize_pending_links(is_exact_match=False, work_page=None, batch_id=None, process_events_func=None,
                           only_manual=False):
    ensure_db_columns()

    conn = get_conn()
    cursor = conn.cursor()

    _sel = ("SELECT id, site_url, source_platform, name, source_keyword, body_text, source_site "
            "FROM draft_links WHERE crawl_status = ?")

    if batch_id == "LEGACY_BATCH":
        if only_manual:
            records = cursor.execute(
                _sel + " AND (batch_id IS NULL OR batch_id = '') AND attr = '手动获取'",
                (CRAWL_STATUS_PENDING,)
            ).fetchall()
        else:
            records = cursor.execute(
                _sel + " AND (batch_id IS NULL OR batch_id = '')",
                (CRAWL_STATUS_PENDING,)
            ).fetchall()
    elif batch_id:
        if only_manual:
            records = cursor.execute(
                _sel + " AND batch_id = ? AND attr = '手动获取'",
                (CRAWL_STATUS_PENDING, batch_id)
            ).fetchall()
        else:
            records = cursor.execute(
                _sel + " AND batch_id = ?",
                (CRAWL_STATUS_PENDING, batch_id)
            ).fetchall()
    else:
        if only_manual:
            records = cursor.execute(
                _sel + " AND attr = '手动获取'",
                (CRAWL_STATUS_PENDING,)
            ).fetchall()
        else:
            records = cursor.execute(_sel, (CRAWL_STATUS_PENDING,)).fetchall()

    total = len(records)
    if total == 0:
        conn.close()
        return 0, 0, 0, 0, 0, 0, 0, 0, 0

    success_count, failed_count, unmatched_count = 0, 0, 0
    whitelist_skipped, blacklist_skipped = 0, 0
    matched_count, unknown_count, duplicate_count = 0, 0, 0
    consecutive_fail = 0

    user_sigs_rows = cursor.execute("SELECT word, weight FROM user_signals").fetchall()
    user_signals = [{"word": r[0], "weight": r[1]} for r in user_sigs_rows]
    all_signals = RELEVANCE_SIGNALS + user_signals

    try:
        for index, (db_id, raw_url, source_platform, page_title,
                    source_keyword, body_text, source_site_text) in enumerate(records):

            real_url = raw_url
            target_status = CRAWL_STATUS_ORGANIZED
            match_status = "matched"

            try:
                # ★ 彻底放弃后端的网络请求和 Playwright 短链解析
                if "baidu.com/link?url=" in real_url:
                    target_status = CRAWL_STATUS_PARSE_FAILED
                    failed_count += 1
                    cursor.execute(
                        "UPDATE draft_links SET crawl_status = ?, match_status = ? WHERE id = ?",
                        (target_status, "parse_failed", db_id)
                    )
                    conn.commit()
                    continue

                consecutive_fail = 0
            except Exception as e:
                target_status = CRAWL_STATUS_PARSE_FAILED
                failed_count += 1
                consecutive_fail += 1
                cursor.execute(
                    "UPDATE draft_links SET crawl_status = ?, match_status = ? WHERE id = ?",
                    (target_status, "parse_failed", db_id)
                )
                conn.commit()
                if consecutive_fail >= 5:
                    break
                continue

            new_feature = extract_pure_feature(real_url)
            dup_draft = cursor.execute(
                "SELECT id FROM draft_links WHERE batch_id = ? AND id != ? "
                "AND (site_url = ? OR (feature_code IS NOT NULL AND feature_code != '' AND feature_code = ?)) LIMIT 1",
                (batch_id, db_id, real_url, new_feature or "")
            ).fetchone()
            if dup_draft:
                cursor.execute("DELETE FROM draft_links WHERE id = ?", (db_id,))
                conn.commit()
                continue

            if any(domain in real_url for domain in COPYRIGHT_WHITELIST_DOMAINS):
                target_status = CRAWL_STATUS_WHITELIST
                whitelist_skipped += 1
                cursor.execute(
                    "UPDATE draft_links SET site_url = ?, crawl_status = ?, domain_matched = 0 WHERE id = ?",
                    (real_url, target_status, db_id)
                )
                conn.commit()
                continue

            if cursor.execute("SELECT id FROM ignored_links WHERE site_url = ?", (real_url,)).fetchone():
                target_status = CRAWL_STATUS_IGNORED
                blacklist_skipped += 1
                cursor.execute(
                    "UPDATE draft_links SET site_url = ?, crawl_status = ?, domain_matched = 0 WHERE id = ?",
                    (real_url, target_status, db_id)
                )
                conn.commit()
                continue

            dup_site = cursor.execute(
                "SELECT id FROM sites WHERE site_url = ? OR "
                "(feature_code IS NOT NULL AND feature_code != '' AND feature_code = ?) LIMIT 1",
                (real_url, new_feature or "")
            ).fetchone()
            if dup_site:
                cursor.execute(
                    "UPDATE draft_links SET site_url = ?, feature_code = ?, crawl_status = ?, "
                    "duplicate_of_id = ?, duplicate_of_table = 'sites' WHERE id = ?",
                    (real_url, new_feature, CRAWL_STATUS_DUPLICATE, dup_site[0], db_id)
                )
                conn.commit()
                duplicate_count += 1
                continue

            target_platform = "其他"
            domain_matched = 0
            for plat_name, domains in PLATFORM_DOMAINS.items():
                if any(d in real_url for d in domains):
                    target_platform = plat_name
                    domain_matched = 1
                    break

            if domain_matched == 0:
                target_platform = source_platform or "其他"
                relevance_val, relevance_hits_list = score_relevance(
                    page_title, body_text, source_site_text, all_signals
                )
                relevance_hits_json = (
                    json.dumps(relevance_hits_list, ensure_ascii=False)
                    if relevance_hits_list else None
                )
            else:
                relevance_val = 0.0
                relevance_hits_json = None

            check_text = (page_title + " " + body_text).lower()
            has_pan = 0
            for pan_domain in ACTIVE_NETDISK_DOMAINS:
                if pan_domain in check_text:
                    has_pan = 1
                    break  # 只要命中一个网盘域名就足够了

            # 修改原有的 UPDATE 语句
            cursor.execute(
                "UPDATE draft_links SET site_url = ?, category = ?, target_platform = ?, match_status = ?, "
                "feature_code = ?, crawl_status = ?, domain_matched = ?, relevance = ?, relevance_hits = ?, "
                "has_pan = ? "  # ★ 新增
                "WHERE id = ?",
                (real_url, target_platform, target_platform, match_status,
                 new_feature, target_status, domain_matched, relevance_val, relevance_hits_json,
                 has_pan,  # ★ 新增传入参数
                 db_id)
            )

            cursor.execute(
                "UPDATE draft_links SET site_url = ?, category = ?, target_platform = ?, match_status = ?, "
                "feature_code = ?, crawl_status = ?, domain_matched = ?, relevance = ?, relevance_hits = ? "
                "WHERE id = ?",
                (real_url, target_platform, target_platform, match_status,
                 new_feature, target_status, domain_matched, relevance_val, relevance_hits_json, db_id)
            )
            conn.commit()
            success_count += 1
            if domain_matched == 1:
                matched_count += 1
            else:
                unknown_count += 1

    finally:
        conn.close()

    return total, success_count, failed_count, unmatched_count, whitelist_skipped, \
        blacklist_skipped, matched_count, unknown_count, duplicate_count


def write_organized_links():
    return 0


def archive_batch_by_ids(keep_items, drop_ids, blacklist_ids):
    if not keep_items and not drop_ids and not blacklist_ids:
        return 0, 0, 0

    conn = get_conn()
    try:
        cursor = conn.cursor()
        inserted_count, dropped_count, black_count = 0, 0, 0

        if keep_items:
            for db_id, category in keep_items:
                # ★ 把 parent_url / parent_title 查出来
                row = cursor.execute(
                    "SELECT site_url, name, body_text, source_site, feature_code, "
                    "  source_platform, source_keyword, source_url, attr, "
                    "  book_id, book_name, target_platform, fetch_time, batch_id, "
                    "  parent_url, parent_title "
                    "FROM draft_links WHERE id = ?", (db_id,)
                ).fetchone()

                if not row:
                    continue

                (url, name, body, source_site, code,
                 plat, kw, src_url, attr,
                 book_id, book_name, target_platform, fetch_time, batch_id,
                 parent_url, parent_title) = row

                try:
                    # ★ 修改：把 source_site 写进 name，把原来的 name 写进 original_title
                    cursor.execute(
                        "INSERT INTO sites (category, target_platform, site_url, name, original_title, body_text, "
                        "  source_site, attr, feature_code, book_id, book_name, "
                        "  source_platform, source_keyword, source_url, fetch_time, "
                        "  batch_id, domain_matched, parent_url, parent_title) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (category, target_platform or category, url,
                         source_site or "未知来源",  # ★ 1. name 字段接收 source_site
                         name,  # ★ 2. original_title 接收 name
                         body,
                         source_site, attr, code, book_id, book_name,
                         plat, kw, src_url, fetch_time,
                         batch_id, 1 if target_platform else 0, parent_url, parent_title)
                    )
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    pass
                cursor.execute("DELETE FROM draft_links WHERE id = ?", (db_id,))

        if blacklist_ids:
            placeholders = ','.join('?' * len(blacklist_ids))
            rows = cursor.execute(
                f"SELECT id, site_url, name FROM draft_links WHERE id IN ({placeholders})",
                blacklist_ids
            ).fetchall()

            for r in rows:
                cursor.execute(
                    "INSERT OR IGNORE INTO ignored_links (site_url, title, add_time) VALUES (?, ?, ?)",
                    (r[1], r[2], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                cursor.execute("DELETE FROM draft_links WHERE id = ?", (r[0],))
                black_count += 1

        if drop_ids:
            placeholders = ','.join('?' * len(drop_ids))
            cursor.execute(f"DELETE FROM draft_links WHERE id IN ({placeholders})", drop_ids)
            dropped_count = cursor.rowcount

        conn.commit()
        print(f"[批次] 归档完成：入库 {inserted_count} 条，拉黑 {black_count} 条，丢弃 {dropped_count} 条。")
        return inserted_count, dropped_count, black_count
    finally:
        conn.close()


def check_drafts_exist():
    conn = get_conn()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM draft_links WHERE crawl_status IN (?, ?, ?, ?)",
            (CRAWL_STATUS_PENDING, CRAWL_STATUS_UNMATCHED,
             CRAWL_STATUS_PARSE_FAILED, CRAWL_STATUS_ORGANIZED)
        ).fetchone()[0]
        return count
    finally:
        conn.close()


def clear_all_drafts():
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM draft_links WHERE crawl_status IN (?, ?, ?, ?)",
            (CRAWL_STATUS_PENDING, CRAWL_STATUS_UNMATCHED,
             CRAWL_STATUS_PARSE_FAILED, CRAWL_STATUS_ORGANIZED)
        )
        conn.commit()
        print("[批次] 已彻底清空全库历史草稿（draft_links）。")
    finally:
        conn.close()