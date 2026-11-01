# page_search.py
import os
from plugin_bridge import bridge_signals
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QApplication)
from PySide6.QtCore import Qt

from link_ingest_service import ensure_db_columns
from ws_server import set_app_mode, current_context
from search_result_panel import SearchResultPanel, ToastLabel

# ★ 拆分出的两个子面板
from search_input_panel import SearchInputPanel
from search_task_panel import SearchTaskPanel


class SearchConsolePage(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.current_batch_id = ""
        self.focus_window = None
        self.active_preview_db_id = None
        self._is_background_parsing = False

        ensure_db_columns()

        # ★ 新增：在这里调用队列的清理方法
        from search_task_queue import task_queue
        task_queue.init_cleanup()

        self.setup_ui()

        if self.result_panel.current_batch_id:
            self.current_batch_id = self.result_panel.current_batch_id
            current_context["batch_id"] = self.current_batch_id

        bridge_signals.plugin_timeout.connect(self._on_plugin_timeout)

    def _on_plugin_timeout(self, business_name):
        ToastLabel(self, f"⚠️ {business_name}插件未连接，请检查浏览器是否打开", "#EF4444")

    def setup_ui(self):
        # ★ 修改点：不要直接覆盖，改用追加。并强制指定 QMessageBox 的白底黑字
        app = QApplication.instance()
        app.setStyleSheet(app.styleSheet() + """
            QToolTip {
                background-color: #FFFFFF;
                color: #374151;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QMessageBox {
                background-color: #FFFFFF;
            }
            QMessageBox QLabel {
                color: #374151;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 5px 15px;
                color: #374151;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ---- 左侧滚动区 ----
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.left_scroll.setMinimumWidth(360)
        self.left_scroll.setMaximumWidth(420)

        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 9, 5, 0)
        left_layout.setSpacing(15)

        # 1. 自动搜索面板（输入区）
        self.input_panel = SearchInputPanel(self)
        left_layout.addWidget(self.input_panel)

        # 2. 搜索队列面板
        self.task_panel = SearchTaskPanel(self)
        left_layout.addWidget(self.task_panel, 1) # 占满剩余高度

        self.left_scroll.setWidget(left_panel)
        main_layout.addWidget(self.left_scroll, alignment=Qt.AlignLeft)

        # ---- 右侧分拣区 ----
        self.result_panel = SearchResultPanel(self)
        self.result_panel.request_preview.connect(self._on_request_preview)
        self.result_panel.stats_updated.connect(self._on_stats_updated)
        main_layout.addWidget(self.result_panel, 1)

    def _on_stats_updated(self, stats):
        # 转发给输入面板更新重试按钮
        self.input_panel.update_parse_state(stats)

    def _on_request_preview(self, db_id, raw_url, category, book_name):
        if not raw_url:
            return
        self.active_preview_db_id = db_id

        from ws_server import dispatch_open_preview
        from app_data import ALL_SUB_PLATFORMS

        available_books = [b["name"] for b in self.input_panel.books_data.values()]
        available_categories = list(ALL_SUB_PLATFORMS)

        if getattr(self, 'focus_window', None) and self.focus_window.isVisible():
            dispatch_open_preview(
                url=raw_url,
                book_name=book_name or "",
                keyword=current_context.get("keyword", ""),
                batch_id=self.current_batch_id,
                source_db_id=db_id,
                category=category or "",
                available_books=available_books,
                available_categories=available_categories,
            )
            self.result_panel.refresh_tables()
            return

        main_layout = self.layout()
        main_layout.removeWidget(self.result_panel)
        self.result_panel.setParent(None)

        from focus_preview_window import BaseFocusWindow
        BaseFocusWindow.launch(
            main_page=self,
            workbench_widget=self.result_panel,
            preview_url=raw_url,
            title=f"专注预览: {book_name or '未知作品'}"
        )

        dispatch_open_preview(
            url=raw_url,
            book_name=book_name or "",
            keyword=current_context.get("keyword", ""),
            batch_id=self.current_batch_id,
            source_db_id=db_id,
            category=category or "",
            available_books=available_books,
            available_categories=available_categories,
        )

    def on_focus_window_closed(self):
        self.focus_window = None
        self.active_preview_db_id = None
        set_app_mode("idle")
        main_layout = self.layout()
        if main_layout.indexOf(self.result_panel) == -1:
            main_layout.addWidget(self.result_panel, 1)
        self.result_panel.refresh_tables()

    def refresh_tables(self):
        if hasattr(self, 'result_panel') and self.result_panel:
            self.result_panel.refresh_tables()

    def load_books(self):
        """向后兼容：将刷新书籍请求代理给输入面板"""
        if hasattr(self, 'input_panel') and self.input_panel:
            self.input_panel.load_books()

    def on_book_changed(self, index=None):
        """向后兼容：将切换作品请求代理给输入面板"""
        if hasattr(self, 'input_panel') and self.input_panel:
            self.input_panel.on_book_changed(index)