# ui_styles.py
"""全软件统一的 QSS 样式常量。

============================================================
★ 按钮样式速查目录（按视觉语义分类）
============================================================
【标准按钮】 (默认 padding: 6px 12px，字体 13px)
- BTN_SECONDARY        白底灰边，普通次级操作（取消、导入、导出）
- BTN_PRIMARY          绿底白字，主操作（制作维权书、上传、确认）
- BTN_PRIMARY_OUTLINE  白底绿边，强调性次级操作（新增空白行）
- BTN_BLUE             蓝底白字，次级操作（查看、导出 Word）
- BTN_ORANGE           橙底白字，下载类操作
- BTN_DARK             黑底白字，强强调操作（全批自动投诉）
- BTN_DANGER           红底白字，破坏性操作（标记已投诉、清空数据）
- BTN_DANGER_OUTLINE   白底红字灰边，弱破坏性操作（删除选中）
- BTN_SECONDARY_DARK   白底灰边，hover变黑（清空、刷新等小工具按钮。padding稍小: 4px 12px，字体 12px）

【状态/切换按钮】 (默认 padding: 6px 12px)
- BTN_TOGGLE           分类筛选，未选中白底，选中绿底
- BTN_TOGGLE_MAIN      快捷分组，未选中灰底，选中绿底，更粗

【小尺寸对话框按钮】
- BTN_DIALOG_CANCEL    白底灰边（取消）
- BTN_DIALOG_OK        绿底白字（确定）

【纯文本按钮 / 文字链】
- btn_link_style(color, hover_color) 无边框透明底，hover 下划线（预览、重传、删除）

============================================================
★ 替换原则：
  - 颜色、边框、圆角、padding、状态色 → 用这里的常量
  - 尺寸（setFixedSize）、文字、图标、位置、行为 → 不在本文件，各页自己管
  - 单次使用的特例（如 ProcessDialog 的 ✕ 按钮）→ 留内联，不进本文件
  - 所有按钮不写 :pressed，按下沿用 hover 态（保持全项目一致）
============================================================
"""

# ================= 颜色常量（改色只需改这里） =================
PRIMARY_GREEN = "#00B87C"
PRIMARY_GREEN_HOVER = "#00996A"
PRIMARY_GREEN_BG_HOVER = "#F0FFF8"  # 绿边按钮 hover 时的浅绿底

# ★ 合并：将 TOGGLE 绿统一指向 PRIMARY 绿，全局只剩一种主绿
TOGGLE_GREEN = PRIMARY_GREEN
TOGGLE_GREEN_HOVER = PRIMARY_GREEN_HOVER

# 交互蓝（按钮底、文字链共用同一组色值）
INFO_BLUE = "#3B82F6"
INFO_BLUE_HOVER = "#2563EB"

# 橙色（下载/警告类操作）
ORANGE = "#F59E0B"
ORANGE_HOVER = "#EA580C"

# 文字链 / 标签辅助色（兼容旧命名，值指向交互蓝）
TEXT_BLUE = INFO_BLUE
TEXT_BLUE_HOVER = INFO_BLUE_HOVER
TEXT_ORANGE = "#E67E22"
TEXT_ORANGE_HOVER = "#C96A12"
TEXT_NAVY = "#2C3E50"        # 深蓝灰（文件名等）

# 危险操作红
DANGER_RED = "#E74C3C"
DANGER_RED_HOVER = "#C0392B"
DANGER_BG_HOVER = "#FFF0F0"  # 危险按钮 hover 浅红

# 报错提示红（单元格格式错误专用）
ERROR_BG = "#FADBD8"
ERROR_BG_SELECTED = "#F4C2C2"

DARK_BG = "#1F1F1F"
DARK_BG_HOVER = "#333333"

BG_WHITE = "#FFFFFF"
BG_HOVER = "#F5F5F5"
BG_SOFT = "#F8F9FA"
BG_DISABLED = "#9CA3AF"

BORDER_GRAY = "#CCCCCC"
BORDER_LIGHT = "#DCDFE6"
BORDER_SOFT = "#E9ECEF"

TEXT_DARK = "#333333"
TEXT_GRAY = "#606266"
TEXT_MUTED = "#999999"
TEXT_DISABLED = "#9CA3AF"

# 表格选中行底纹
ROW_SELECTED_BG = BG_HOVER


# ================= 按钮公共片段 =================
_BTN_COMMON = "border-radius: 4px; padding: 6px 12px; font-size: 13px;"
_BTN_COMMON_SMALL = "border-radius: 4px; padding: 4px 12px; font-size: 12px;"


# ================= 按钮变体 =================

# 白底灰边（普通次级）
BTN_SECONDARY = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {BG_WHITE};
        color: {TEXT_DARK};
        border: 1px solid {BORDER_GRAY};
    }}
    QPushButton:hover {{ background-color: {BG_HOVER}; }}
    QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER_LIGHT}; }}
"""

# 白底灰边，hover 变黑边（清空/刷新/导出）
BTN_SECONDARY_DARK = f"""
    QPushButton {{
        {_BTN_COMMON_SMALL}
        background-color: {BG_WHITE};
        color: {TEXT_GRAY};
        border: 1px solid {BORDER_LIGHT};
    }}
    QPushButton:hover {{ border-color: {DARK_BG}; color: {DARK_BG}; }}
    QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER_SOFT}; }}
"""

# 绿底白字（主操作）
BTN_PRIMARY = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {PRIMARY_GREEN};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {PRIMARY_GREEN_HOVER}; }}
    QPushButton:disabled {{ background-color: {BG_DISABLED}; color: #E5E7EB; }}
"""

# 白底绿字绿边（强调性的次级操作，如“新增空白行”）
BTN_PRIMARY_OUTLINE = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {BG_WHITE};
        color: {PRIMARY_GREEN};
        border: 1px solid {PRIMARY_GREEN};
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {PRIMARY_GREEN_BG_HOVER}; }}
    QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER_LIGHT}; }}
"""

# 蓝底白字（次级操作：查看、导出 Word）
BTN_BLUE = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {INFO_BLUE};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {INFO_BLUE_HOVER}; }}
    QPushButton:disabled {{ background-color: {BG_DISABLED}; color: #E5E7EB; }}
"""

# 橙底白字（下载类操作）
BTN_ORANGE = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {ORANGE};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {ORANGE_HOVER}; }}
    QPushButton:disabled {{ background-color: {BG_DISABLED}; color: #E5E7EB; }}
"""

# 黑底白字（强调操作）
BTN_DARK = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {DARK_BG};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {DARK_BG_HOVER}; }}
    QPushButton:disabled {{ background-color: {BG_DISABLED}; color: #E5E7EB; }}
"""

# 红底白字（标记/清空）
BTN_DANGER = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {DANGER_RED};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {DANGER_RED_HOVER}; }}
    QPushButton:disabled {{ background-color: {BG_DISABLED}; color: #E5E7EB; }}
"""

# 白底红字灰边（删除选中）
BTN_DANGER_OUTLINE = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {BG_WHITE};
        color: {DANGER_RED};
        border: 1px solid {BORDER_GRAY};
    }}
    QPushButton:hover {{ border-color: {DANGER_RED}; background-color: {DANGER_BG_HOVER}; }}
    QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER_LIGHT}; }}
"""

# 可勾选按钮（分类筛选，未选中白底，选中绿底）
BTN_TOGGLE = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: {BG_WHITE};
        color: {TEXT_DARK};
        border: 1px solid {BORDER_GRAY};
    }}
    QPushButton:hover {{ background-color: {BG_HOVER}; }}
    QPushButton:checked {{
        background-color: {TOGGLE_GREEN};
        color: white;
        border: 1px solid {TOGGLE_GREEN};
        font-weight: bold;
    }}
"""

# 可勾选按钮-快捷分组（更粗，灰底）
BTN_TOGGLE_MAIN = f"""
    QPushButton {{
        {_BTN_COMMON}
        background-color: #F0F0F0;
        color: {DARK_BG};
        border: 1px solid #D0D0D0;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: #E5E5E5; }}
    QPushButton:checked {{
        background-color: {TOGGLE_GREEN};
        color: white;
        border: 1px solid {TOGGLE_GREEN};
    }}
"""

# 对话框内取消（小尺寸，白底灰边）
BTN_DIALOG_CANCEL = f"""
    QPushButton {{
        padding: 5px 15px;
        border: 1px solid {BORDER_GRAY};
        border-radius: 4px;
        background-color: {BG_WHITE};
        color: {TEXT_DARK};
    }}
    QPushButton:hover {{ background-color: {BG_HOVER}; }}
"""

# 对话框内确认（小尺寸，绿底）
BTN_DIALOG_OK = f"""
    QPushButton {{
        background-color: {TOGGLE_GREEN};
        color: white;
        border-radius: 4px;
        padding: 5px 20px;
        font-weight: bold;
        border: none;
    }}
    QPushButton:hover {{ background-color: {TOGGLE_GREEN_HOVER}; }}
"""


def btn_link_style(color, hover_color):
    """文字链按钮：无边框、透明底、hover 下划线。

    用法：
        btn.setStyleSheet(btn_link_style(TEXT_BLUE, TEXT_BLUE_HOVER))
        btn.setFlat(True)  # 记得同时设 flat
        btn.setFocusPolicy(Qt.NoFocus)
    """
    return f"""
        QPushButton {{
            color: {color};
            background: transparent;
            border: none;
            padding: 2px 2px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            color: {hover_color};
            text-decoration: underline;
        }}
    """


# ================= 表格 =================

# 可编辑主表格（带交替行）
TABLE_BASE = f"""
    QTableWidget {{
        background-color: {BG_WHITE};
        alternate-background-color: {BG_SOFT};
        color: {TEXT_DARK};
        gridline-color: {BORDER_SOFT};
        outline: none;
    }}
    QTableWidget::item {{
        margin: 0px; padding: 0px; border-bottom: 1px solid {BORDER_SOFT};
    }}
    QTableWidget::item:selected {{
        background-color: {ROW_SELECTED_BG}; color: {TEXT_DARK};
    }}
"""

# 只读表格（排队列表、历史记录、批次明细）
TABLE_READONLY = f"""
    QTableWidget {{
        border: 1px solid {BORDER_SOFT}; border-radius: 4px; background-color: {BG_WHITE};
    }}
    QTableWidget::item:selected {{
        background-color: {ROW_SELECTED_BG}; color: {TEXT_DARK};
    }}
"""

# 带交替行的只读表格（历史记录）
TABLE_READONLY_ALT = f"""
    QTableWidget {{
        border: 1px solid {BORDER_SOFT}; border-radius: 4px; alternate-background-color: #FAFAFA;
    }}
    QTableWidget::item:selected {{
        background-color: {ROW_SELECTED_BG}; color: {TEXT_DARK};
    }}
"""


# ================= 表头 =================

HEADER_BASE = f"""
    QHeaderView::section {{
        background-color: {BG_SOFT}; font-weight: bold; padding: 6px;
        border: none; border-bottom: 1px solid {BORDER_SOFT}; color: {TEXT_DARK};
    }}
"""


# ================= TabWidget =================

TAB_WIDGET = f"""
    QTabWidget::pane {{ border: 1px solid #DCDCDC; background: {BG_WHITE}; top: -1px; }}
    QTabBar::tab {{
        background: {BG_HOVER}; color: #666666; padding: 8px 24px;
        border: 1px solid #DCDCDC; border-bottom: none;
        border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px;
    }}
    QTabBar::tab:hover {{ background: #EBEBEB; }}
    QTabBar::tab:selected {{
        background: {BG_WHITE}; color: {DARK_BG}; font-weight: bold;
        border-bottom: 1px solid {BG_WHITE};
    }}
"""


# ================= 列表（批次列表） =================

LIST_BASE = f"""
    QListWidget {{ border: 1px solid {BORDER_SOFT}; border-radius: 4px; outline: none; }}
    QListWidget::item {{ padding: 8px; border-bottom: 1px solid #F2F2F2; }}
    QListWidget::item:selected {{
        background-color: {BG_HOVER}; color: {DARK_BG}; font-weight: bold; border-left: 3px solid {DARK_BG};
    }}
"""