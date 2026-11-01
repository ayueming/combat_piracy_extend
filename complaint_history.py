# complaint_history.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from db_config import get_conn

# ★ 样式全部从 ui_styles 引入
from ui_styles import (
    PRIMARY_GREEN,
    BTN_SECONDARY,
    TABLE_READONLY_ALT,
    HEADER_BASE,
)


class ComplaintHistoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_history()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        h_top_layout = QHBoxLayout()
        h_top_layout.addWidget(QLabel("【历史投诉记录】 以下是您所有的投诉批次汇总。"))
        h_top_layout.addStretch()

        refresh_btn = QPushButton("刷新记录")
        # ★ 使用统一的小尺寸白底黑边按钮
        refresh_btn.setStyleSheet(BTN_SECONDARY)
        refresh_btn.clicked.connect(self.load_history)
        h_top_layout.addWidget(refresh_btn)
        layout.addLayout(h_top_layout)

        self.history_table = QTableWidget()
        # 5 列：投诉时间、投诉作品、分类、投诉链接数量、关联作品
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["投诉时间", "投诉作品", "分类", "投诉链接数量", "关联作品"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)

        # ★ 使用统一的只读表格样式 + 表头样式
        self.history_table.setStyleSheet(TABLE_READONLY_ALT + HEADER_BASE)
        layout.addWidget(self.history_table)

    def load_history(self):
        """读取数据并刷新表格"""
        self.history_table.setRowCount(0)
        conn = get_conn()

        query = """
                SELECT s.book_id, \
                       s.complaint_time, \
                       COALESCE(b.name, s.book_name, '未关联') as display_book, \
                       s.category, \
                       b.platform_id, \
                       COUNT(*) as count
                FROM sites s
                    LEFT JOIN books b \
                ON s.book_id = b.id
                WHERE s.complaint_time IS NOT NULL AND s.complaint_time != ''
                GROUP BY
                    s.book_id,
                    s.complaint_time,
                    COALESCE (b.name, s.book_name, '未关联'),
                    s.category,
                    b.platform_id
                ORDER BY s.complaint_time DESC
                """
        records = conn.execute(query).fetchall()
        conn.close()

        for db_id, comp_time, book_name, cat, platform_id, count in records:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            self.history_table.setItem(row, 0, QTableWidgetItem(comp_time))

            # 投诉作品列（正常显示书名）
            self.history_table.setItem(row, 1, QTableWidgetItem(book_name))
            self.history_table.setItem(row, 2, QTableWidgetItem(cat or "未分类"))

            # 数量列
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            font = count_item.font()
            font.setBold(True)
            count_item.setFont(font)
            # ★ 使用从 ui_styles 引入的统一主绿色
            count_item.setForeground(QColor(PRIMARY_GREEN))
            self.history_table.setItem(row, 3, count_item)

            # 作品晋江书号 列（★ 已去除所有自定义颜色，统一为默认黑色）
            if db_id:
                if platform_id:
                    # 拼装成 “最新书名 (晋江书号)” 的形式
                    id_text = f"{book_name} ({platform_id})"
                    id_item = QTableWidgetItem(id_text)
                else:
                    # 有内部ID，但没填晋江书号的情况
                    id_item = QTableWidgetItem(f"{book_name} (无晋江书号)")
            else:
                # 纯文本未关联
                id_item = QTableWidgetItem("纯文本 (未关联)")

            id_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(row, 4, id_item)