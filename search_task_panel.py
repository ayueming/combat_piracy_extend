# search_task_panel.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QFrame, QMessageBox)
from PySide6.QtCore import Qt
from search_task_queue import task_queue, queue_signals


class TaskRow(QFrame):
    def __init__(self, data, index):
        super().__init__()
        self.data = data
        self.setObjectName("TaskRow")

        border_color = "#E5E7EB"
        if data["status"] == "running":
            border_color = "#10B981"
        elif data["status"] == "failed":
            border_color = "#EF4444"

        self.setStyleSheet(
            f"#TaskRow {{ background: #FFF; border: 1px solid #E5E7EB; border-left: 3px solid {border_color}; border-radius: 4px; }}")
        self.setFixedHeight(65)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(4)

        lbl_index = QLabel(f"{index}.")
        lbl_index.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: bold; border: none;")
        top.addWidget(lbl_index)

        lbl_title = QLabel(f"《{data['book_name']}》 {data['platform']} {data['max_pages']}页")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #374151; border: none;")
        top.addWidget(lbl_title)
        top.addStretch()

        btn_run = QPushButton("▶")
        btn_run.setFixedSize(24, 24)
        btn_run.setStyleSheet(
            "QPushButton { background: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; border-radius: 4px; font-weight: bold; } QPushButton:hover { background: #D1FAE5; }")
        btn_run.setCursor(Qt.PointingHandCursor)
        btn_run.clicked.connect(self._on_run)

        btn_del = QPushButton("×")
        btn_del.setFixedSize(28, 28)
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; color: #9CA3AF; border: none; font-size: 18px; font-weight: bold; } QPushButton:hover { color: #EF4444; }")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(self._on_del)

        top.addWidget(btn_run)
        top.addWidget(btn_del)
        lay.addLayout(top)

        # ★ 第二行：主词 + 副词
        sub_text = " ".join(data["sub_keywords"]) if data["sub_keywords"] else "无副关键词"
        lbl_sub = QLabel(f" {data['main_keyword']}  |  {sub_text}")
        lbl_sub.setStyleSheet("color: #6B7280; font-size: 11px; border: none; margin-left: 16px;")
        lbl_sub.setToolTip(lbl_sub.text())
        lay.addWidget(lbl_sub)

    def _on_run(self):
        if self.data["status"] == "running":
            QMessageBox.information(self, "提示",
                                    "该任务当前正在执行中，请勿重复点击。\n如果已卡死，请点击上方的「停止」按钮。")
            return
        if task_queue.is_running:
            QMessageBox.warning(self, "提示", "队列中已有其他任务正在执行，请先等待或点击「停止」。")
            return
        from link_ingest_service import check_drafts_exist
        if check_drafts_exist() > 0:
            QMessageBox.warning(
                self, "提示",
                "发现还有草稿尚未处理完毕。\n\n"
                "请先将右侧数据（入库/永删/忽略）处理完，\n"
                "或点击右下角【清空当前分类】清理后，再进行搜索。"
            )
            return
        task_queue.start_one(self.data["id"])

    def _on_del(self):
        if self.data["status"] == "running":
            QMessageBox.warning(self, "提示", "该任务正在执行中，无法删除。请先点击「停止」。")
            return
        success = task_queue.remove_task(self.data["id"])
        if not success:
            QMessageBox.warning(self, "提示", "队列正被锁定使用中，无法删除该任务。")


class SearchTaskPanel(QWidget):
    def __init__(self, main_page):
        super().__init__()
        self.main_page = main_page
        self.setup_ui()

        queue_signals.queue_updated.connect(self.refresh_list)
        queue_signals.batch_switched.connect(self._on_batch_switched)
        self.refresh_list()

    def setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.lbl_queue_title = QLabel("📋 搜索队列 (0)")
        self.lbl_queue_title.setStyleSheet("font-weight: bold; color: #374151; font-size: 13px;")
        header.addWidget(self.lbl_queue_title)
        header.addStretch()

        self.btn_add = QPushButton("＋ 添加")
        self.btn_add.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #3B82F6; font-size: 12px; font-weight: bold; padding: 0; } QPushButton:hover { color: #2563EB; }")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_current)

        self.lbl_div = QLabel("|")
        self.lbl_div.setStyleSheet("color: #D1D5DB; font-size: 12px;")

        self.btn_run_all = QPushButton("▶ 执行全部")
        self.btn_run_all.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #10B981; font-size: 12px; font-weight: bold; padding: 0; } QPushButton:hover { color: #059669; }")
        self.btn_run_all.setCursor(Qt.PointingHandCursor)
        self.btn_run_all.clicked.connect(self._run_all)

        self.btn_stop = QPushButton("⏸ 强制停止")
        self.btn_stop.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #EF4444; font-size: 12px; font-weight: bold; padding: 0; } QPushButton:hover { color: #DC2626; }")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(task_queue.stop)
        self.btn_stop.hide()

        header.addWidget(self.btn_add)
        header.addWidget(self.lbl_div)
        header.addWidget(self.btn_run_all)
        header.addWidget(self.btn_stop)

        lay.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { border: none; background: transparent; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #D1D5DB; min-height: 20px; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #9CA3AF; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.list_container)
        lay.addWidget(self.scroll, 1)

    def refresh_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tasks = task_queue.get_tasks()
        self.lbl_queue_title.setText(f"📋 搜索队列 ({len(tasks)})")

        if not tasks:
            lbl = QLabel("队列为空，请配置搜索项后点击「添加」")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #9CA3AF; font-size: 12px; margin-top: 20px;")
            self.list_layout.addWidget(lbl)
        else:
            for i, t in enumerate(tasks):
                self.list_layout.addWidget(TaskRow(t, i + 1))

        if task_queue.is_running:
            self.btn_run_all.hide()
            self.btn_add.hide()
            self.lbl_div.hide()
            self.btn_stop.show()
        else:
            self.btn_run_all.show()
            self.btn_stop.hide()
            self.btn_add.show()
            self.lbl_div.show()

    def _add_current(self):
        if not self.main_page: return
        book_id = self.main_page.input_panel.book_combo.currentData()
        book_name = self.main_page.input_panel.book_combo.currentText()
        platform = self.main_page.input_panel.platform_combo.currentText()
        main_kw = self.main_page.input_panel.main_kw_input.text().strip()

        if not book_name or not main_kw:
            QMessageBox.warning(self, "提示", "请先在主界面选择作品和主关键词。")
            return

        sub_kws = list(self.main_page.input_panel.selected_sub_kws)
        max_pages = int(self.main_page.input_panel.page_limit_combo.currentText().replace("页", ""))

        success = task_queue.add_task(book_id, book_name, platform, main_kw, sub_kws, max_pages)
        if not success:
            QMessageBox.warning(
                self, "无法添加",
                "队列中已存在完全相同的检索任务（同书籍、同平台、同关键词）。\n\n"
                "为防止频繁请求触发搜索引擎风控，请勿重复添加。\n"
                "如需更改页数，请点击该任务右侧的删除键（×），重新添加即可。"
            )

    def _run_all(self):
        if task_queue.is_running: return
        tasks = task_queue.get_tasks()
        if not tasks: return

        from link_ingest_service import check_drafts_exist
        if check_drafts_exist() > 0:
            QMessageBox.warning(
                self, "提示",
                "发现还有草稿尚未处理完毕。\n\n"
                "请先将右侧数据（入库/永删/忽略）处理完，\n"
                "或点击右下角【清空当前分类】清理后，再进行批量搜索。"
            )
            return

        task_queue.start_all()

    def _on_batch_switched(self, batch_id, book_name):
        if not self.main_page: return
        idx = self.main_page.input_panel.book_combo.findText(book_name)
        if idx >= 0:
            self.main_page.input_panel.book_combo.setCurrentIndex(idx)
        if hasattr(self.main_page, "result_panel"):
            self.main_page.result_panel.current_batch_id = batch_id
            self.main_page.result_panel.refresh_tables()