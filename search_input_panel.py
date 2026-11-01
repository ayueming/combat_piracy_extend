# search_input_panel.py
import re
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
                               QLineEdit, QPushButton, QMessageBox, QLayout, QSizePolicy)
from PySide6.QtCore import Qt, QRect, QSize, QPoint

from db_config import get_conn
from app_data.search_templates import get_available_platforms
from ws_server import current_context, dispatch_search_task, dispatch_stale_urls_resolve, get_app_mode
from link_ingest_service import check_drafts_exist
from parser_service import trigger_parse
from ui_styles import BTN_PRIMARY
from search_result_panel import ToastLabel


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=5):
        super().__init__(parent)
        self._item_list = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        return self._item_list[index] if 0 <= index < len(self._item_list) else None

    def takeAt(self, index):
        return self._item_list.pop(index) if 0 <= index < len(self._item_list) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _do_layout(self, rect, test_only):
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._item_list:
            space_x, space_y = self._h_spacing, self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()


class SearchInputPanel(QWidget):
    def __init__(self, main_page):
        super().__init__()
        self.main_page = main_page
        self.books_data = {}
        self.base_sub_kws = []
        self.dynamic_sub_kws = []
        self.temp_sub_kws = []
        self.selected_sub_kws = set()

        self.load_user_signals()
        self.setup_ui()
        self.load_books()

        from ws_server import ws_signals
        ws_signals.search_finished.connect(self._on_search_end)
        ws_signals.scan_state_changed.connect(self._on_scan_state_changed)

    def _on_search_end(self, batch_id):
        """搜索结束，恢复按钮"""
        self._reset_search_btn()

    def _on_scan_state_changed(self, state):
        """状态变更为 idle 时（涵盖超时、断连），恢复按钮"""
        if state == "idle":
            self._reset_search_btn()

    def _reset_search_btn(self):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("🔍 搜索")

    def load_user_signals(self):
        self.base_sub_kws = ["资源", "txt", "下载", "免费阅读", "提取码", "全文阅读"]
        conn = get_conn()
        try:
            rows = conn.execute("SELECT word FROM user_signals").fetchall()
            for r in rows:
                if r[0] not in self.base_sub_kws:
                    self.base_sub_kws.append(r[0])
        finally:
            conn.close()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(5, 0, 0, 0)
        lbl_auto_search = QLabel("自动搜索")
        lbl_auto_search.setStyleSheet("font-size: 16px; font-weight: bold; color: #111827;")
        title_layout.addWidget(lbl_auto_search)
        title_layout.addStretch()

        self.parse_btn = QPushButton("🔄 发现异常数据，点击重试")
        self.parse_btn.setStyleSheet(
            "QPushButton { color: #D97706; font-weight: bold; background: transparent; border: none; font-size: 12px; padding: 0; } "
            "QPushButton:hover { color: #B45309; text-decoration: underline; }"
        )
        self.parse_btn.setCursor(Qt.PointingHandCursor)
        self.parse_btn.clicked.connect(self.trigger_manual_parse)
        self.parse_btn.hide()
        title_layout.addWidget(self.parse_btn)

        self.parsing_label = QLabel("⏳ 正在请求解析...")
        self.parsing_label.setStyleSheet("color: #DC2626; font-weight: bold; font-size: 12px; background: transparent;")
        self.parsing_label.hide()
        title_layout.addWidget(self.parsing_label)

        layout.addLayout(title_layout)

        input_style = "QComboBox, QLineEdit { border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px 12px; background: #FFFFFF; font-size: 13px; color: #374151; } QComboBox:hover, QLineEdit:hover { border: 1px solid #D1D5DB; } QComboBox:focus, QLineEdit:focus { border: 1px solid #059669; background: #F8FAFC; } QComboBox::drop-down { border: none; width: 24px; } QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #6B7280; width: 0; height: 0; margin-right: 8px; } QComboBox::down-arrow:hover { border-top: 5px solid #059669; }"

        form_widget = QWidget()
        grid_layout = QGridLayout(form_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(12)

        lbl_book = QLabel("关联作品:")
        lbl_book.setStyleSheet("color:#4B5563; font-size: 13px;")
        lbl_book.setFixedWidth(65)
        lbl_book.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.book_combo = QComboBox()
        self.book_combo.setStyleSheet(input_style)
        self.book_combo.activated.connect(self.on_book_changed)
        grid_layout.addWidget(lbl_book, 0, 0)
        grid_layout.addWidget(self.book_combo, 0, 1)

        lbl_plat = QLabel("搜索引擎:")
        lbl_plat.setStyleSheet("color:#4B5563; font-size: 13px;")
        lbl_plat.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(get_available_platforms())
        self.platform_combo.setStyleSheet(input_style)
        grid_layout.addWidget(lbl_plat, 1, 0)
        grid_layout.addWidget(self.platform_combo, 1, 1)

        lbl_main = QLabel("主关键词:")
        lbl_main.setStyleSheet("color:#4B5563; font-size: 13px;")
        lbl_main.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.main_kw_input = QLineEdit()
        self.main_kw_input.setReadOnly(True)
        self.main_kw_input.setStyleSheet(
            "QLineEdit { border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px 12px; background: #F3F4F6; font-weight: bold; color: #059669; font-size: 13px; }")
        grid_layout.addWidget(lbl_main, 2, 0)
        grid_layout.addWidget(self.main_kw_input, 2, 1)

        self.main_kw_layout = FlowLayout(h_spacing=6, v_spacing=6)
        main_kw_container = QWidget()
        main_kw_container.setLayout(self.main_kw_layout)
        grid_layout.addWidget(main_kw_container, 3, 1)

        lbl_sub = QLabel("副关键词:")
        lbl_sub.setStyleSheet("color:#4B5563; font-size: 13px;")
        lbl_sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.sub_kw_input = QLineEdit()
        self.sub_kw_input.setPlaceholderText("输入并回车添加")
        self.sub_kw_input.setStyleSheet(input_style)
        self.sub_kw_input.returnPressed.connect(self.on_add_sub_kw_from_input)
        grid_layout.addWidget(lbl_sub, 4, 0)
        grid_layout.addWidget(self.sub_kw_input, 4, 1)

        self.sub_kw_layout = FlowLayout(h_spacing=6, v_spacing=6)
        sub_kw_container = QWidget()
        sub_kw_container.setLayout(self.sub_kw_layout)
        grid_layout.addWidget(sub_kw_container, 5, 1)

        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)
        layout.addWidget(form_widget)

        page_layout = QHBoxLayout()
        page_layout.setContentsMargins(0, 5, 0, 5)
        lbl_page = QLabel("自动翻页数:")
        lbl_page.setStyleSheet("color:#4B5563; font-size: 13px;")
        lbl_page.setFixedWidth(65)
        lbl_page.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.page_limit_combo = QComboBox()
        self.page_limit_combo.addItems(["1页", "2页", "3页", "4页", "5页"])
        self.page_limit_combo.setCurrentIndex(2)
        self.page_limit_combo.setStyleSheet(input_style)

        page_layout.addWidget(lbl_page)
        page_layout.addWidget(self.page_limit_combo)
        page_layout.addStretch()
        layout.addLayout(page_layout)

        self.btn_search = QPushButton("🔍 搜索")
        self.btn_search.setStyleSheet(
            BTN_PRIMARY + "QPushButton { padding: 12px 0; font-size: 15px; border-radius: 8px; font-weight: bold; }")
        self.btn_search.clicked.connect(self.start_search)
        layout.addWidget(self.btn_search)

    def load_books(self):
        conn = get_conn()
        try:
            books = conn.execute("SELECT id, name, pen_name, aliases FROM books ORDER BY name").fetchall()
            self.books_data.clear()
            self.book_combo.clear()
            for b in books:
                b_id, b_name, b_pen, b_aliases = b
                self.books_data[b_id] = {"name": b_name, "pen_name": b_pen, "aliases": b_aliases}
                self.book_combo.addItem(b_name, b_id)
        finally:
            conn.close()
        if self.book_combo.count() > 0:
            self.on_book_changed(0)

    def on_book_changed(self, index=None):
        book_id = self.book_combo.currentData()
        if not book_id or book_id not in self.books_data:
            return
        book = self.books_data[book_id]

        while self.main_kw_layout.count():
            item = self.main_kw_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        main_kws = [book["name"]]
        if book.get("aliases"):
            for a in re.split(r'[,，/\\|、\s]+', book["aliases"]):
                a = a.strip()
                if a and a not in main_kws:
                    main_kws.append(a)
        self.main_kw_input.setText(book["name"])

        for kw in main_kws:
            btn = QPushButton(kw)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background-color: #F0F4F8; border: 1px solid #D0D7E5; border-radius: 10px; padding: 3px 10px; color: #333; font-size: 11px; } QPushButton:hover { background-color: #E2E8F0; border-color: #059669; color: #059669; }")
            btn.clicked.connect(lambda checked, t=kw: self.main_kw_input.setText(t))
            self.main_kw_layout.addWidget(btn)

        self.dynamic_sub_kws = [book["pen_name"]] if book.get("pen_name") else []
        self.selected_sub_kws.clear()
        self.temp_sub_kws.clear()
        self.refresh_sub_kws()

        current_context["book_name"] = self.book_combo.currentText()
        current_context["keyword"] = self.main_kw_input.text()

    def refresh_sub_kws(self):
        while self.sub_kw_layout.count():
            item = self.sub_kw_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        all_kws = self.dynamic_sub_kws + [kw for kw in self.base_sub_kws if
                                          kw not in self.dynamic_sub_kws] + self.temp_sub_kws
        for kw in all_kws:
            btn = QPushButton(kw)
            btn.setCursor(Qt.PointingHandCursor)
            if kw in self.dynamic_sub_kws:
                btn.setStyleSheet(
                    "QPushButton { border: 1px solid #D97706; border-radius: 10px; padding: 3px 10px; background: #D97706; color: white; font-weight: bold; font-size: 11px; }"
                    if kw in self.selected_sub_kws else
                    "QPushButton { border: 1px dashed #D97706; border-radius: 10px; padding: 3px 10px; background: #FEF3C7; color: #D97706; font-size: 11px; }")
            else:
                btn.setStyleSheet(
                    "QPushButton { border: 1px solid #059669; border-radius: 10px; padding: 3px 10px; background: #059669; color: white; font-size: 11px; }"
                    if kw in self.selected_sub_kws else
                    "QPushButton { border: 1px solid #DCDCDC; border-radius: 10px; padding: 3px 10px; background: #FFF; color: #666; font-size: 11px; }")
            btn.clicked.connect(lambda checked, t=kw: self.toggle_sub_kw(t))
            self.sub_kw_layout.addWidget(btn)

    def toggle_sub_kw(self, kw):
        if kw in self.selected_sub_kws:
            self.selected_sub_kws.remove(kw)
        else:
            self.selected_sub_kws.add(kw)
        self.refresh_sub_kws()

    def on_add_sub_kw_from_input(self):
        text = self.sub_kw_input.text().strip()
        if not text:
            return
        if text not in self.base_sub_kws and text not in self.dynamic_sub_kws and text not in self.temp_sub_kws:
            self.temp_sub_kws.append(text)
        self.selected_sub_kws.add(text)
        self.sub_kw_input.clear()
        self.refresh_sub_kws()

    def start_search(self):
        if get_app_mode() == "previewing":
            QMessageBox.warning(self, "提示", "请先按 Esc 退出专注预览模式，再进行自动搜索。")
            return

        draft_count = check_drafts_exist()
        if draft_count > 0:
            # 引导用户使用右下角的按钮去清理中间态的垃圾数据
            QMessageBox.warning(
                self, "提示",
                f"发现还有 {draft_count} 条草稿尚未处理完毕。\n\n"
                f"请先将右侧的数据处理完（入库 / 永删 / 忽略），\n"
                f"或者直接点击右下角的【清空当前分类】清理掉它们，\n"
                f"然后再进行下一次搜索。"
            )
            return

        main_kw = self.main_kw_input.text().strip()
        if not main_kw:
            QMessageBox.warning(self, "提示", "主关键词不能为空")
            return

        platform = self.platform_combo.currentText()
        self.main_page.current_batch_id = f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.main_page.result_panel.current_batch_id = self.main_page.current_batch_id

        current_context["book_name"] = self.book_combo.currentText()
        current_context["keyword"] = self.main_kw_input.text()
        current_context["batch_id"] = self.main_page.current_batch_id

        page_limit_text = self.page_limit_combo.currentText()
        max_pages = int(page_limit_text.replace("页", ""))

        sub_kws = list(self.selected_sub_kws)
        result = dispatch_search_task(platform, main_kw, max_pages, sub_kws)

        if result == "success":
            ToastLabel(self.main_page, "🚀 已下发搜索任务...", "#3B82F6")
            self.btn_search.setEnabled(False)
            self.btn_search.setText("🔄 搜索中...")
        elif result == "opening":
            ToastLabel(self.main_page, "🌐 正在启动浏览器，请稍候...", "#F59E0B")
            self.btn_search.setEnabled(False)
            self.btn_search.setText("🔄 搜索中...")
        elif result == "busy":
            ToastLabel(self.main_page, "⏳ 已有搜索任务进行中，请等待完成", "#F59E0B")
        elif result == "no_browser":
            QMessageBox.warning(self, "缺少浏览器", "未检测到 Chrome 或 Edge 浏览器！\n请先安装后再试。")
        else:
            QMessageBox.warning(self, "提示", "任务派发失败，请稍后重试。")

    def trigger_manual_parse(self):
        if getattr(self.main_page, "_is_background_parsing", False):
            return

        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT site_url FROM draft_links WHERE batch_id = ? AND crawl_status IN ('pending', 'parse_failed') AND site_url LIKE '%baidu.com/link%'",
                (self.main_page.current_batch_id,)
            ).fetchall()
        finally:
            conn.close()

        if rows:
            stale_links = [{"url": r[0], "original_url": r[0]} for r in rows]
            self.parsing_label.setText(f"🔄 正在解析 {len(stale_links)} 条历史短链...")
            self.parsing_label.show()
            self.parse_btn.hide()

            if dispatch_stale_urls_resolve(stale_links):
                return

        self.parse_btn.hide()
        self.parsing_label.show()
        self.main_page._is_background_parsing = True
        trigger_parse(self.main_page.current_batch_id, is_exact=False)

    def update_parse_state(self, stats):
        # ★ 核心逻辑：只要右侧发来了数据刷新，说明插件解析一定有结果了，红字无条件隐藏！
        self.parsing_label.hide()

        # 顺便把遗留的历史锁砸碎，防止干扰后续操作
        self.main_page._is_background_parsing = False

        # 检查是否还有没解析完的数据
        pending_count = stats.get("待解析", 0) + stats.get("解析失败", 0)

        if pending_count > 0:
            # 如果还有没解析的，显示黄色文字重试按钮
            self.parse_btn.setText(f"⚠️ {pending_count} 条未解析，点击重试")
            self.parse_btn.show()
        else:
            # 如果全部解析完了，干干净净，全都隐藏
            self.parse_btn.hide()