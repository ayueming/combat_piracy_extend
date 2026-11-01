# page_complaints.py
import os
import threading
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QTableWidget, QTableWidgetItem, QHeaderView,
                               QFileDialog, QMessageBox, QSplitter, QAbstractItemView,
                               QProgressBar, QTabWidget, QDialog, QFrame)
from PySide6.QtCore import Qt, Signal
from datetime import datetime
from db_config import get_conn

# === ★ 统一调度器 ===
from complaint_dispatcher import ComplaintDispatcher, PLATFORM_ROUTER

from license_manager import license_mgr

# ★ 引入独立的历史记录组件
from complaint_history import ComplaintHistoryWidget

# ★ 引入 Excel 生成工具
from complaint_excel_utils import generate_platform_excel

# ★ 引入投诉业务常量
from app_data import COMPLAINT_BATCH_SIZE

# ★ 按钮/表格样式统一从 ui_styles 引入
from ui_styles import (
    BTN_SECONDARY,
    BTN_SECONDARY_DARK,
    BTN_PRIMARY,
    BTN_DARK,
    BTN_DANGER,
    TABLE_READONLY,
    TABLE_READONLY_ALT,
    HEADER_BASE,
    LIST_BASE,
    TAB_WIDGET,
)


# ============================================================
# 安全小窗：独立运行 + 关闭即中断信号 + 挂起唤醒
# ============================================================
class ProcessDialog(QDialog):
    closed_by_user = Signal()
    login_confirmed = Signal()

    def __init__(self, parent=None):
        super().__init__(None)
        self.setFixedSize(520, 260)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; border: 1px solid #D0D0D0; border-radius: 8px; }
        """)
        self._drag_offset = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- 标题栏 ---
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet("""
            QWidget { background-color: #F5F5F5; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QLabel { background: transparent; border: none; color: #333; font-weight: bold; font-size: 13px; }
            QPushButton { border: none; background: transparent; color: #999; font-size: 15px; }
            QPushButton:hover { color: #E74C3C; }
        """)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 6, 0)
        title_lbl = QLabel("自动投诉运行状态")
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        tb_layout.addWidget(close_btn)

        title_bar.mousePressEvent = self._tb_press
        title_bar.mouseMoveEvent = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release
        layout.addWidget(title_bar)

        # --- 内容区 ---
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(15, 10, 15, 15)
        c_layout.setSpacing(10)

        self.label = QLabel("初始化中...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            "color: #333; font-weight: bold; font-size: 13px; border: none; background: transparent;")
        c_layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #E0E0E0; border-radius: 4px; background: #FFF; }
            QProgressBar::chunk { background-color: #10B981; border-radius: 3px; }
        """)
        c_layout.addWidget(self.progress_bar)

        # ★ 挂起时的已登录按钮
        self.login_btn = QPushButton("我已登录，继续运行")
        self.login_btn.setStyleSheet("""
            QPushButton { background-color: #3B82F6; color: white; padding: 8px; font-weight: bold; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #2563EB; }
        """)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setVisible(False)
        self.login_btn.clicked.connect(self._on_login_clicked)
        c_layout.addWidget(self.login_btn)

        self.tip = QLabel("关闭本窗口或浏览器，将强行终止本脚本。\n（仅关闭小窗不会关闭浏览器）")
        self.tip.setAlignment(Qt.AlignCenter)
        self.tip.setWordWrap(True)
        self.tip.setStyleSheet("color: #999; font-size: 11px; border: none; background: transparent;")
        c_layout.addWidget(self.tip)
        layout.addWidget(content)

    def _tb_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _tb_move(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def _tb_release(self, event):
        self._drag_offset = None
        event.accept()

    def update_text(self, text):
        self.label.setText(text)
        self.label.setToolTip(text)

    def show_login_required(self):
        self.update_text("⚠️ 检测到未登录/掉线！\n请在浏览器扫码登录后，点击下方按钮。")
        self.login_btn.setVisible(True)
        self.progress_bar.setRange(0, 0)

    def reset_progress(self):
        self.progress_bar.setRange(0, 0)
        self.update_text("正在验证登录并继续执行...")
        self.login_btn.setVisible(False)

    def _on_login_clicked(self):
        self.login_btn.setVisible(False)
        self.update_text("正在检查登录状态...")
        self.login_confirmed.emit()

    def closeEvent(self, event):
        self.closed_by_user.emit()
        event.accept()


# ============================================================
# 投诉页主类
# ============================================================
class ComplaintsPage(QWidget):
    refresh_links_signal = Signal()
    task_finished = Signal()
    batch_done = Signal(object)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.batches = []
        self.auto_running = False
        self.dispatcher = None
        self.progress_dialog = None

        # ★ 线程间通信的事件控制
        self.stop_event = threading.Event()
        self.login_event = threading.Event()

        self.refresh_links_signal.connect(self.do_refresh_links)
        self.task_finished.connect(self._on_task_finished)
        self.batch_done.connect(self._on_batch_done)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # ★ 使用 TAB_WIDGET
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET)
        layout.addWidget(self.tabs)

        # ================= Tab 1: 投诉队列 =================
        self.queue_tab = QWidget()
        queue_layout = QVBoxLayout(self.queue_tab)

        top_layout = QHBoxLayout()
        lbl_center = QLabel(f"【投诉批次中心】 系统已智能拆分（单批上限{COMPLAINT_BATCH_SIZE}条）。")
        top_layout.addWidget(lbl_center)
        top_layout.addStretch()

        self.clear_btn = QPushButton("清空当前批次")
        self.clear_btn.setStyleSheet(BTN_SECONDARY)
        self.clear_btn.clicked.connect(self.clear_batches)
        top_layout.addWidget(self.clear_btn)
        queue_layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_title = QLabel("批次列表:")
        left_title.setStyleSheet("font-weight: bold; color: #1F1F1F; margin-bottom: 4px;")
        left_layout.addWidget(left_title)

        self.batch_list = QListWidget()
        self.batch_list.setStyleSheet(LIST_BASE)
        self.batch_list.currentRowChanged.connect(self.on_batch_selected)
        left_layout.addWidget(self.batch_list)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_spacer = QLabel("投诉明细:")
        right_spacer.setStyleSheet("font-weight: bold; color: #1F1F1F; margin-bottom: 4px;")
        right_layout.addWidget(right_spacer)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["关联作品", "分类", "侵权链接"])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_table.setStyleSheet(TABLE_READONLY + HEADER_BASE)
        right_layout.addWidget(self.queue_table)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # 1. 黑底全批投诉
        self.auto_all_btn = QPushButton("全批自动投诉 (循环提交)")
        self.auto_all_btn.setStyleSheet(BTN_DARK + "QPushButton { padding: 8px 16px; }")
        self.auto_all_btn.clicked.connect(lambda: self.trigger_auto_fill(is_all=True))
        btn_layout.addWidget(self.auto_all_btn)

        # 2. 红底单批投诉
        self.auto_btn = QPushButton("单批自动填表")
        self.auto_btn.setStyleSheet(BTN_DANGER + "QPushButton { padding: 8px 16px; }")
        self.auto_btn.clicked.connect(lambda: self.trigger_auto_fill(is_all=False))
        btn_layout.addWidget(self.auto_btn)

        # 3. 绿底手动标记
        self.mark_done_btn = QPushButton("手动标记本批已投诉")
        self.mark_done_btn.setStyleSheet(BTN_PRIMARY + "QPushButton { padding: 8px 16px; }")
        self.mark_done_btn.clicked.connect(self.mark_batch_done)
        btn_layout.addWidget(self.mark_done_btn)

        # 4. 白底导出Excel
        self.export_btn = QPushButton("导出为Excel")
        self.export_btn.setStyleSheet(BTN_SECONDARY + "QPushButton { padding: 8px 16px; }")
        self.export_btn.clicked.connect(self.export_current_batch)
        btn_layout.addWidget(self.export_btn)

        right_layout.addLayout(btn_layout)
        splitter.addWidget(right_widget)

        splitter.setSizes([280, 720])
        queue_layout.addWidget(splitter)

        self.tabs.addTab(self.queue_tab, "投诉队列")

        # ================= Tab 2: 历史记录 =================
        self.history_tab = QWidget()
        history_layout = QVBoxLayout(self.history_tab)
        history_layout.setContentsMargins(0, 0, 0, 0)

        self.history_widget = ComplaintHistoryWidget(self)
        history_layout.addWidget(self.history_widget)

        self.tabs.addTab(self.history_tab, "历史记录")

        self._set_running_ui(False)

    # ==================== 状态控制与权限拦截 ====================
    def _set_running_ui(self, running):
        is_exp = license_mgr.is_expired

        self.clear_btn.setEnabled(not running)

        self.auto_all_btn.setEnabled(not running and not is_exp)
        self.auto_btn.setEnabled(not running and not is_exp)
        self.export_btn.setEnabled(not running and not is_exp)
        self.mark_done_btn.setEnabled(not running and not is_exp)

        self.batch_list.setEnabled(not running)

        if is_exp:
            tip = "您的会员已过期，无法使用投诉相关功能。请联系管理员续费。"
            self.auto_all_btn.setToolTip(tip)
            self.auto_btn.setToolTip(tip)
            self.export_btn.setToolTip(tip)
            self.mark_done_btn.setToolTip(tip)
        else:
            self.auto_all_btn.setToolTip("")
            self.auto_btn.setToolTip("")
            self.export_btn.setToolTip("")
            self.mark_done_btn.setToolTip("")

        if not running:
            self.on_batch_selected(self.batch_list.currentRow())

    def _on_task_finished(self):
        self.auto_running = False
        self.dispatcher = None

        if getattr(self, "progress_dialog", None):
            try:
                self.progress_dialog.closed_by_user.disconnect()
            except Exception:
                pass
            try:
                self.progress_dialog.login_confirmed.disconnect()
            except Exception:
                pass
            try:
                self.progress_dialog.close()
            except Exception:
                pass
            self.progress_dialog = None

        self._set_running_ui(False)

    def _on_dialog_closed(self):
        """用户点击了 ✕ 按钮：发送停止信号，并启动倒计时强行解锁"""
        if not self.auto_running:
            return

        self.stop_event.set()
        self.login_event.set()
        print("用户强行关闭了小窗，已发送停止信号（浏览器将保留）。")

        # ★ 新增：给 UI 留个后门，如果 2 秒后后台还没发出 task_finished，就直接强制解锁
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._force_unlock_ui)

    def _force_unlock_ui(self):
        """强行解锁 UI（防止后台线程因死锁无法发出 task_finished）"""
        if self.auto_running:
            print("⚠️ 检测到后台线程可能已死锁，强行解锁界面按钮。")
            self._on_task_finished()

    def _on_login_confirmed(self):
        """用户点击了 已登录继续 按钮"""
        self.login_event.set()

    def _on_batch_done(self, batch):
        if batch in self.batches:
            self.batches.remove(batch)
        self._rebuild_batch_list()
        self.refresh_links_signal.emit()

    def _rebuild_batch_list(self):
        self.batch_list.blockSignals(True)
        self.batch_list.clear()
        for i, b in enumerate(self.batches):
            if b:
                cat = b[0].get("cat", "未知分类")
                book = b[0].get("book", "未知作品")
                self.batch_list.addItem(f"[{cat}] {book} ({len(b)} 条)")
            else:
                self.batch_list.addItem(f"第 {i + 1} 批 (0 条)")
        self.batch_list.blockSignals(False)

        if self.batches:
            self.batch_list.setCurrentRow(0)
        else:
            self.queue_table.setRowCount(0)

    # ==================== 刷新 ====================
    def do_refresh_links(self):
        if hasattr(self.main_window, 'links_page'):
            self.main_window.links_page.refresh_table()
        self.history_widget.load_history()

    # ==================== 批次管理 ====================
    def load_batches(self, batches):
        self.batches = batches
        self.batch_list.clear()
        for i, batch in enumerate(self.batches):
            if batch:
                cat = batch[0].get("cat", "未知分类")
                book = batch[0].get("book", "未知作品")
                self.batch_list.addItem(f"[{cat}] {book} ({len(batch)} 条)")
            else:
                self.batch_list.addItem(f"第 {i + 1} 批 (0 条)")

        if self.batches:
            self.batch_list.setCurrentRow(0)
            self.tabs.setCurrentIndex(0)

    def clear_batches(self):
        if self.auto_running:
            return
        self.batches = []
        self.batch_list.clear()
        self.queue_table.setRowCount(0)

    def on_batch_selected(self, index):
        if index < 0 or index >= len(self.batches):
            return
        current_batch = self.batches[index]
        self.queue_table.setRowCount(0)
        for row_data in current_batch:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            self.queue_table.setItem(row, 0, QTableWidgetItem(row_data["book"]))
            self.queue_table.setItem(row, 1, QTableWidgetItem(row_data["cat"]))
            self.queue_table.setItem(row, 2, QTableWidgetItem(row_data["url"]))

        if self.auto_running:
            return

        if current_batch:
            platform_code = current_batch[0].get("platform_code")
            if not platform_code:
                # 数据缺平台代号：不猜、不兜底，直接禁用全批按钮
                self.auto_all_btn.setEnabled(False)
                self.auto_all_btn.setText("平台代号缺失，无法全批")
            else:
                self.auto_all_btn.setEnabled(not license_mgr.is_expired)
                self.auto_all_btn.setText("全批自动投诉 (循环提交)")

    # ==================== 自动投诉入口 ====================
    def trigger_auto_fill(self, is_all=False):
        if license_mgr.is_expired:
            QMessageBox.warning(self, "授权已过期",
                                "您的会员已过期，无法发起自动投诉。\n请前往【个人中心】查看详情或联系管理员续费。")
            return

        if self.auto_running:
            QMessageBox.warning(self, "提示", "自动任务正在运行中，请勿重复点击！")
            return

        if not self.batches:
            QMessageBox.warning(self, "提示", "当前没有可处理的批次数据！")
            return

        if is_all:
            if not self.batches[0]:
                QMessageBox.warning(self, "提示", "首批数据为空，无法开始！")
                return
            target_cat = self.batches[0][0].get("cat", "")
            target_platform_code = self.batches[0][0].get("platform_code")
            initial_batch = None
        else:
            index = self.batch_list.currentRow()
            if index < 0 or index >= len(self.batches):
                QMessageBox.warning(self, "提示", "请先选择一个批次！")
                return
            initial_batch = self.batches[index]
            if not initial_batch:
                QMessageBox.warning(self, "提示", "当前批次为空！")
                return
            target_cat = initial_batch[0].get("cat", "")
            target_platform_code = initial_batch[0].get("platform_code")

        # ★ 平台代号缺失：不猜、不兜底，直接拦下
        if not target_platform_code:
            QMessageBox.critical(
                self, "⛔ 数据异常",
                f"当前批次【{target_cat}】缺少平台代号（platform_code）。\n\n"
                f"这通常意味着该分类不在系统平台配置中，或批次数据不是由【盗文链接】页正常生成的。\n"
                f"请检查分类是否正确，或重新从【盗文链接】页发起投诉。"
            )
            return

        # if is_all and target_platform_code == PLATFORM_BAIDU:
        #     QMessageBox.warning(self, "提示", "百度投诉需要频繁登录，无法无人值守全批运行，请使用单批填表！")
        #     return

        # === ★ 拦截暂未开通的投诉方式 ===
        #   直接复用调度器的路由表判断，不在这里再维护一份平台列表
        if not is_all:
            if target_platform_code not in PLATFORM_ROUTER:
                QMessageBox.warning(self, "暂未开通",
                                    f"当前选择的是【{target_cat}】分类，\n系统暂未开通该平台的自动投诉方式！")
                return

        self.stop_event.clear()
        self.login_event.clear()

        self.progress_dialog = ProcessDialog()
        self.progress_dialog.closed_by_user.connect(self._on_dialog_closed)
        self.progress_dialog.login_confirmed.connect(self._on_login_confirmed)

        # ★ 统一调度器：内部自己创建 AutoComplaintSignals，并通过 progress_msg 转发
        self.dispatcher = ComplaintDispatcher(
            batches=self.batches,
            is_all=is_all,
            target_cat=target_cat,
            initial_batch=initial_batch,
            stop_event=self.stop_event,
            login_event=self.login_event,
            dialog_signal=self.progress_dialog,
        )
        self.dispatcher.progress_msg.connect(self.progress_dialog.update_text)
        self.dispatcher.batch_success.connect(self.mark_specific_batch_done)
        self.dispatcher.task_finished.connect(self._on_task_finished)

        self.auto_running = True
        self._set_running_ui(True)

        # ★ 核心修复：先把弹窗 show 出来，防止后台线程秒结束导致弹窗瞬间被销毁
        self.progress_dialog.show()

        # 强制刷新一下 UI，确保弹窗完全渲染出来
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        t = threading.Thread(target=self.dispatcher.run, daemon=True)
        t.start()

    def mark_specific_batch_done(self, batch):
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        try:
            for item in batch:
                conn.execute("UPDATE sites SET complaint_time=? WHERE id=?", (today, item["id"]))
            conn.commit()
        finally:
            conn.close()

        self.batch_done.emit(batch)

    # ==================== 导出 / 手动标记 ====================
    def export_current_batch(self):
        if license_mgr.is_expired:
            QMessageBox.warning(self, "功能受限", "您的授权已过期，无法导出 Excel。")
            return

        index = self.batch_list.currentRow()
        if index < 0:
            return
        current_batch = self.batches[index]
        if not current_batch:
            return

        category_name = current_batch[0].get("cat", "未知分类")
        platform_code = current_batch[0].get("platform_code")
        if not platform_code:
            QMessageBox.critical(
                self, "⛔ 数据异常",
                f"当前批次【{category_name}】缺少平台代号（platform_code），无法生成对应模板的 Excel。"
            )
            return

        book_name = current_batch[0].get("book", "未知作品")
        time_str = datetime.now().strftime("%Y%m%d%H%M")
        default_name = f"{book_name}_{category_name}投诉_{time_str}.xlsx"

        path, _ = QFileDialog.getSaveFileName(self, "保存文件", default_name, "Excel 文件 (*.xlsx)")
        if not path:
            return

        # ★ 改为传 platform_code，与四个自动脚本保持一致
        success = generate_platform_excel(current_batch, platform_code, path)

        if success:
            QMessageBox.information(self, "导出成功", f"已生成适用于【{category_name}】的 Excel 模板！")
        else:
            QMessageBox.critical(self, "导出失败", "生成 Excel 时发生错误，请检查文件是否被占用。")

    def mark_batch_done(self):
        if license_mgr.is_expired:
            QMessageBox.warning(self, "功能受限", "您的授权已过期，无法进行标记。")
            return

        if self.auto_running:
            return
        index = self.batch_list.currentRow()
        if index < 0:
            return
        current_batch = self.batches[index]
        reply = QMessageBox.question(self, "确认", f"确定将这批 ({len(current_batch)}条) 标记为已投诉吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.mark_specific_batch_done(current_batch)