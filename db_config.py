# db_config.py
import sqlite3
import os
import time
import re
from contextlib import contextmanager
from app_paths import get_user_dir, FILE_DB

# 晋江书号 / 百度ID 的合法字符检查
_ALNUM_CHECK_SQL = "NOT GLOB '*[^A-Za-z0-9]*'"

# books 表字段定义（init_db 建表 & 迁移重建共用，改一处生效两处）
BOOKS_COLUMNS_SQL = f"""(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id   TEXT CHECK (platform_id IS NULL OR platform_id {_ALNUM_CHECK_SQL}),
    name          TEXT UNIQUE NOT NULL,
    pen_name      TEXT,
    aliases       TEXT,
    evidence_path TEXT,
    rights_holder TEXT,
    baidu_id      TEXT CHECK (baidu_id IS NULL OR baidu_id {_ALNUM_CHECK_SQL})
)"""

# evidences 表字段定义（新结构建表 & 旧结构迁移共用）
EVIDENCES_COLUMNS_SQL = """(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,
    owner_key  TEXT NOT NULL,
    ev_type    TEXT,
    file_path  TEXT,
    UNIQUE (owner_type, owner_key, ev_type)
)"""

# ★ 新增：draft_links 表结构（搜索草稿，独立于 sites；归档时才搬进 sites）
#   故意不加 UNIQUE 约束：重复检测改由显式查询完成，命中后标 CRAWL_STATUS_DUPLICATE，
#   让用户能在搜索页"已在库"tab 看到"这次抓到多少条是已经存过的"。
#   字段与 sites 对齐，归档时字段对字段搬过去，无需映射。
DRAFT_LINKS_COLUMNS_SQL = """(
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            TEXT,
    category            TEXT,
    site_url            TEXT,
    name                TEXT,
    body_text           TEXT,
    source_site         TEXT,
    attr                TEXT,
    feature_code        TEXT,
    complaint_time      TEXT,
    resource_status     TEXT,
    book_id             INTEGER,
    book_name           TEXT,
    crawl_status        TEXT,
    source_platform     TEXT DEFAULT '',
    source_keyword      TEXT DEFAULT '',
    source_url          TEXT DEFAULT '',
    fetch_time          TEXT DEFAULT '',
    target_platform     TEXT DEFAULT '',
    match_status        TEXT DEFAULT '',
    domain_matched      INTEGER DEFAULT 0,
    relevance           REAL DEFAULT 0,
    relevance_hits      TEXT,
    duplicate_of_id     INTEGER,
    duplicate_of_table  TEXT,
    has_pan             INTEGER DEFAULT 0
)"""

# ★ 全局变量，记住当前是谁在登录
_current_user_id = None


def set_current_user(user_id):
    """登录成功后，必须调用此函数，告诉数据库现在是谁在使用"""
    global _current_user_id
    _current_user_id = str(user_id)
    # 确保该用户的文件夹存在
    get_user_dir(_current_user_id)


def get_current_user():
    return _current_user_id


def get_db_path():
    """动态获取当前用户的数据库完整路径"""
    if not _current_user_id:
        raise Exception("系统异常：未设置当前登录用户，无法连接数据库。")
    return os.path.join(get_user_dir(_current_user_id), FILE_DB)


def get_conn():
    """获取当前用户的数据库连接。

    - foreign_keys=ON：PRAGMA foreign_keys 是"每连接生效"的，之前只在 init_db
      设过一次，导致后续所有连接的外键实际都是关闭的（book_keywords 的
      ON DELETE CASCADE 从未生效）。
    - timeout=5.0（等价 busy_timeout=5000ms）：给后台线程和 UI 线程争锁时
      留出等待窗口，避免 database is locked。
    """
    conn = sqlite3.connect(get_db_path(), timeout=5.0)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """统一的连接获取方式：自动 close，异常时 rollback。

    用法：
        with db() as conn:
            conn.execute(...)
            conn.commit()
    """
    conn = get_conn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _add_column_if_missing(cursor, table, col_name, col_type):
    """安全地新增列：只吞"列已存在"，其余 OperationalError 重新抛出。

    ★ A1 修复：原代码 `except sqlite3.OperationalError: pass` 会静默吞掉
      "database is locked"、"disk I/O error" 等真实故障，导致列没加上却继续
      跑，直到某处 SELECT 才报错，且离根因很远。
    """
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise


# ================= 1. DB 层格式约束：检测 / 清洗 / 迁移 =================
def _books_has_alnum_check(cursor):
    row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='books'"
    ).fetchone()
    if not row or not row[0]:
        return False
    return "[^A-Za-z0-9]" in row[0]


def _clean_invalid_book_ids(cursor):
    bad = []
    for col in ("platform_id", "baidu_id"):
        rows = cursor.execute(
            f"SELECT id, name, {col} FROM books "
            f"WHERE {col} IS NOT NULL AND {col} != '' "
            f"AND {col} GLOB '*[^A-Za-z0-9]*'"
        ).fetchall()
        for r in rows:
            bad.append({"id": r[0], "name": r[1], "field": col, "value": r[2]})
        if rows:
            cursor.execute(
                f"UPDATE books SET {col}=NULL "
                f"WHERE {col} IS NOT NULL AND {col} != '' "
                f"AND {col} GLOB '*[^A-Za-z0-9]*'"
            )
    return bad


def _log_migration(records):
    if not records:
        return
    log_dir = os.path.join(get_user_dir(_current_user_id), "logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"db_migrate_{ts}.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("以下记录因【晋江书号 / 百度ID】包含非字母数字字符，已被置为 NULL：\n")
            f.write("如需保留，请手工修正后重新填写。\n\n")
            for r in records:
                f.write(f"  id={r['id']}  作品={r['name']}  字段={r['field']}  原值={r['value']!r}\n")
        print(f"[DB迁移] 已清洗 {len(records)} 条非法ID记录，日志：{log_path}")
    except Exception as e:
        print(f"[DB迁移] 写日志失败: {e}")


def _migrate_books_add_check(conn, cursor):
    """重建 books 表以加 CHECK 约束。

    ★ A2 修复：原实现四步 DDL（CREATE / INSERT / DROP / RENAME）不在事务里，
      中途失败会留下"books 已被 DROP、books_new 存在"的半迁移状态，下次启动
      `CREATE TABLE IF NOT EXISTS books` 会建空表，用户数据"看似丢失"。

      这里临时切到 isolation_level=None（autocommit），用显式 BEGIN/COMMIT
      把四步包成一个原子操作。SQLite 的 DDL 在默认 isolation_level 下会
      隐式提交，只有 autocommit + BEGIN 才能真正事务化。
    """
    bad_records = _clean_invalid_book_ids(cursor)
    conn.commit()

    old_isolation = conn.isolation_level
    conn.isolation_level = None  # 切到 autocommit，手动控制事务
    try:
        # PRAGMA foreign_keys 必须在事务外设置
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(f"CREATE TABLE books_new {BOOKS_COLUMNS_SQL}")
                cursor.execute('''
                               INSERT INTO books_new
                               (id, platform_id, name, pen_name, aliases, evidence_path, rights_holder, baidu_id)
                               SELECT id,
                                      platform_id,
                                      name,
                                      pen_name,
                                      aliases,
                                      evidence_path,
                                      rights_holder,
                                      baidu_id
                               FROM books
                               ''')
                cursor.execute("DROP TABLE books")
                cursor.execute("ALTER TABLE books_new RENAME TO books")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        print("[DB迁移] books 表已重建，platform_id / baidu_id 已加 CHECK 约束")
    finally:
        conn.isolation_level = old_isolation

    _log_migration(bad_records)


# ================= 2. 关键词字典自动生成 [spider - 暂停] =================
def _sync_book_keywords(conn, cursor):
    """扫描 books 表，自动拆分曾用名，将词条同步到 book_keywords 字典表"""
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS book_keywords
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       book_id
                       INTEGER
                       NOT
                       NULL,
                       keyword
                       TEXT
                       NOT
                       NULL,
                       keyword_type
                       TEXT
                       NOT
                       NULL, -- 'name', 'pen_name', 'alias'
                       UNIQUE
                   (
                       book_id,
                       keyword,
                       keyword_type
                   ),
                       FOREIGN KEY
                   (
                       book_id
                   ) REFERENCES books
                   (
                       id
                   ) ON DELETE CASCADE
                       )
                   ''')

    books = cursor.execute("SELECT id, name, pen_name, aliases FROM books").fetchall()
    for b_id, name, pen_name, aliases in books:
        if name:
            cursor.execute("INSERT OR IGNORE INTO book_keywords (book_id, keyword, keyword_type) VALUES (?, ?, 'name')",
                           (b_id, name.strip()))

        if pen_name:
            cursor.execute(
                "INSERT OR IGNORE INTO book_keywords (book_id, keyword, keyword_type) VALUES (?, ?, 'pen_name')",
                (b_id, pen_name.strip()))

        if aliases:
            # 正则拆分中英文逗号、斜杠、反斜杠、竖线、顿号、空格
            split_aliases = re.split(r'[,，/\\|、\s]+', aliases)
            for a in split_aliases:
                a = a.strip()
                if a:
                    cursor.execute(
                        "INSERT OR IGNORE INTO book_keywords (book_id, keyword, keyword_type) VALUES (?, ?, 'alias')",
                        (b_id, a))
    conn.commit()


# ================= 3. 网站处理规则初始化 [spider - 暂停] =================
def _init_site_rules(conn, cursor):
    """初始化网站规则表，并写入默认白名单"""
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS site_rules
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       domain
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       category
                       TEXT,
                       strategy
                       TEXT,
                       description
                       TEXT
                   )
                   ''')

    # 检查是否为空，如果为空，写入出厂默认规则
    count = cursor.execute("SELECT COUNT(*) FROM site_rules").fetchone()[0]
    if count == 0:
        default_rules = [
            # 策略代码: ignore(跳过), netdisk(提取网盘), deep_crawl(深挖)
            ("jjwxc", "白名单", "ignore", "晋江正版，直接跳过"),
            ("qidian.com", "白名单", "ignore", "起点正版，直接跳过"),
            ("zongheng.com", "白名单", "ignore", "纵横正版，直接跳过"),
            ("pan.baidu.com", "网盘", "netdisk", "百度网盘直链"),
            ("pan.quark.cn", "网盘", "netdisk", "夸克网盘直链"),
            ("aliyundrive.com", "网盘", "netdisk", "阿里云盘直链"),
            ("alipan.com", "网盘", "netdisk", "阿里云盘直链")
        ]
        cursor.executemany(
            "INSERT INTO site_rules (domain, category, strategy, description) VALUES (?, ?, ?, ?)",
            default_rules
        )
        print("[DB初始化] 已写入默认网站规则。")
    conn.commit()


# ================= 4. 初始化主入口 =================
def init_db():
    """初始化当前用户的数据库"""
    if not _current_user_id:
        raise Exception("系统异常：未设置当前用户，无法初始化数据库。")

    with db() as conn:
        # WAL 模式：持久化设置，读写可以并发，避免后台线程与 UI 撞锁。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        cursor = conn.cursor()

        # 1. 初始化 books 表
        cursor.execute(f"CREATE TABLE IF NOT EXISTS books {BOOKS_COLUMNS_SQL}")

        book_columns_to_add = [("evidence_path", "TEXT"), ("rights_holder", "TEXT"), ("baidu_id", "TEXT")]
        for col_name, col_type in book_columns_to_add:
            _add_column_if_missing(cursor, "books", col_name, col_type)
        conn.commit()

        if not _books_has_alnum_check(cursor):
            _migrate_books_add_check(conn, cursor)

        # 2. 初始化 sites 表
        cursor.execute('''CREATE TABLE IF NOT EXISTS sites
                          (
                              id
                              INTEGER
                              PRIMARY
                              KEY
                              AUTOINCREMENT,
                              category
                              TEXT,
                              site_url
                              TEXT
                              UNIQUE,
                              name
                              TEXT,
                              attr
                              TEXT,
                              feature_code
                              TEXT,
                              complaint_time
                              TEXT,
                              resource_status
                              TEXT,
                              book_id
                              INTEGER,
                              book_name
                              TEXT,
                              crawl_status
                              TEXT
                          )''')

        site_columns_to_add = [
            ("name", "TEXT"), ("attr", "TEXT"), ("feature_code", "TEXT"),
            ("complaint_time", "TEXT"), ("resource_status", "TEXT"),
            ("book_id", "INTEGER"), ("book_name", "TEXT"), ("crawl_status", "TEXT"),
            # ★ 抓取溯源三列（拾取入库时写入）
            ("source_platform", "TEXT DEFAULT ''"),
            ("source_keyword", "TEXT DEFAULT ''"),
            ("source_url", "TEXT DEFAULT ''"),
            # ★ 新增：抓取时间、目标平台、匹配状态
            ("fetch_time", "TEXT DEFAULT ''"),
            ("target_platform", "TEXT DEFAULT ''"),
            ("match_status", "TEXT DEFAULT ''")
        ]
        for col_name, col_type in site_columns_to_add:
            _add_column_if_missing(cursor, "sites", col_name, col_type)

        # ★ 新增：2.5 初始化 draft_links 表（搜索草稿，独立于 sites）
        cursor.execute(f"CREATE TABLE IF NOT EXISTS draft_links {DRAFT_LINKS_COLUMNS_SQL}")

        # ★ 升级旧库：补全 has_pan 字段
        _add_column_if_missing(cursor, "draft_links", "has_pan", "INTEGER DEFAULT 0")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_draft_links_batch   ON draft_links(batch_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_draft_links_status  ON draft_links(crawl_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_draft_links_feature ON draft_links(feature_code)")
        conn.commit()

        # 3. 初始化 records 表
        cursor.execute(
            '''CREATE TABLE IF NOT EXISTS records
               (
                   id
                   INTEGER
                   PRIMARY
                   KEY
                   AUTOINCREMENT,
                   date
                   TEXT,
                   attr
                   TEXT,
                   platform_id
                   TEXT,
                   book_name
                   TEXT,
                   url
                   TEXT
                   UNIQUE
               )''')

        # 4. 初始化 evidences 表（旧结构迁移 + 新结构建表，合并为一段逻辑）
        ev_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidences'"
        ).fetchone()

        need_migration = False
        if ev_exists:
            cols = [r[1] for r in cursor.execute("PRAGMA table_info(evidences)").fetchall()]
            if "book_id" in cols and "owner_type" not in cols:
                cursor.execute("ALTER TABLE evidences RENAME TO evidences_old")
                need_migration = True

        # 建新结构（幂等，只有一处 CREATE）
        cursor.execute(f"CREATE TABLE IF NOT EXISTS evidences {EVIDENCES_COLUMNS_SQL}")

        # 迁移旧数据
        if need_migration:
            for b_id, ev_type, f_path in cursor.execute(
                    "SELECT book_id, ev_type, file_path FROM evidences_old"
            ).fetchall():
                if b_id == 0:
                    cursor.execute(
                        "INSERT OR IGNORE INTO evidences (owner_type, owner_key, ev_type, file_path) "
                        "VALUES ('holder', '__default__', ?, ?)", (ev_type, f_path))
                else:
                    cursor.execute(
                        "INSERT OR IGNORE INTO evidences (owner_type, owner_key, ev_type, file_path) "
                        "VALUES ('book', ?, ?, ?)", (str(b_id), ev_type, f_path))
            cursor.execute("DROP TABLE evidences_old")

        # ========================================================
        # ★ 新增：初始化 user_signals 表（修复 no such table 报错）
        # ========================================================
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_signals
                          (
                              id
                              INTEGER
                              PRIMARY
                              KEY
                              AUTOINCREMENT,
                              word
                              TEXT
                              UNIQUE,
                              add_time
                              TEXT
                          )''')
        conn.commit()
        # ========================================================

        # 5. 初始化 search_logs 表 [spider - 暂停]
        cursor.execute('''CREATE TABLE IF NOT EXISTS search_logs
                          (
                              id
                              INTEGER
                              PRIMARY
                              KEY
                              AUTOINCREMENT,
                              book_id
                              INTEGER,
                              search_keyword
                              TEXT,
                              keyword_type
                              TEXT,
                              search_time
                              TIMESTAMP
                              DEFAULT
                              CURRENT_TIMESTAMP
                          )''')

        # 6. 自动构建专属关键词字典表 [spider - 暂停]
        _sync_book_keywords(conn, cursor)

        # 7. 初始化网站处理规则表 [spider - 暂停]
        _init_site_rules(conn, cursor)

        conn.commit()