# focus_preview_window.py
import win32gui
import win32con
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer

from plugin_bridge import get_browser_hwnd
from ws_server import dispatch_open_preview, set_app_mode, check_and_lock


class BaseFocusWindow(QWidget):
    def __init__(self, main_page, workbench_widget, preview_url="", title="专注预览 (按 Esc 退出)"):
        super().__init__()
        self.main_page = main_page
        self.workbench_widget = workbench_widget
        self.preview_url = preview_url
        self.browser_hwnd = None
        self._closed_handled = False

        self.setWindowTitle(title)
        self.setStyleSheet("QWidget { background-color: #F8FAFC; }")
        self.setFocusPolicy(Qt.StrongFocus)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------- 左侧浏览器容器 ----------
        self.browser_container = QWidget()
        self.browser_container.setStyleSheet("background: #000;")
        self.browser_container.setAttribute(Qt.WA_NativeWindow)
        main_layout.addWidget(self.browser_container, 65)

        # ---------- 右侧：外部传入的工作台 ----------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        btn_close = QPushButton("🛑 退出分屏 (Esc)")
        btn_close.setStyleSheet(
            "QPushButton { border: 1px solid #FECACA; border-radius: 4px; background: #FEF2F2; color: #DC2626; font-size: 12px; font-weight: bold; padding: 6px; } "
            "QPushButton:hover { background: #FEE2E2; }")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        right_layout.addWidget(btn_close)

        # ★ 核心：把外部传进来的真实面板插进去，而不是自己造
        if self.workbench_widget is not None:
            right_layout.addWidget(self.workbench_widget, 1)

        main_layout.addWidget(right_panel, 35)

    @classmethod
    def launch(cls, main_page, workbench_widget, preview_url, title="专注预览"):
        if not preview_url:
            return None

        if not check_and_lock("previewing"):
            QMessageBox.warning(main_page, "提示", "后台正在执行自动任务，请等待完成后再预览。")
            return None

        # 已有预览窗先关掉（会触发 closeEvent 把 workbench 收回，然后再被拔出来）
        if getattr(main_page, 'focus_window', None):
            main_page.focus_window.close()

        win = cls(main_page, workbench_widget, preview_url, title)
        main_page.focus_window = win

        screen_rect = QApplication.primaryScreen().availableGeometry()
        win.setGeometry(screen_rect)
        win.show()
        win.setFocus()

        dispatch_open_preview(preview_url)
        QTimer.singleShot(1000, win.embed_browser)
        return win

    # ---------- Win32 嵌入 ----------
    def embed_browser(self):
        hwnd = get_browser_hwnd()
        if not hwnd:
            print("[FocusWindow] 未能获取到浏览器句柄，500ms后重试...")
            QTimer.singleShot(500, self.embed_browser)
            return

        self.browser_hwnd = hwnd
        container_hwnd = int(self.browser_container.winId())

        try:
            win32gui.ShowWindow(self.browser_hwnd, win32con.SW_RESTORE)

            style = win32gui.GetWindowLong(self.browser_hwnd, win32con.GWL_STYLE)
            style = style & ~win32con.WS_CAPTION
            style = style & ~win32con.WS_THICKFRAME
            style = style & ~win32con.WS_MINIMIZEBOX
            style = style & ~win32con.WS_MAXIMIZEBOX
            style = style & ~win32con.WS_SYSMENU
            style = style | win32con.WS_CHILD
            win32gui.SetWindowLong(self.browser_hwnd, win32con.GWL_STYLE, style)

            win32gui.SetParent(self.browser_hwnd, container_hwnd)

            self.resize_browser()
            win32gui.SetFocus(self.browser_hwnd)
            print("[FocusWindow] 嵌入成功！")
        except Exception as e:
            print(f"[FocusWindow] 嵌入出错: {e}")

    def resize_browser(self):
        if not self.browser_hwnd:
            return
        rect = self.browser_container.rect()
        dpr = self.browser_container.devicePixelRatioF()
        win32gui.MoveWindow(
            self.browser_hwnd, 0, 0,
            int(rect.width() * dpr),
            int(rect.height() * dpr),
            True
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_browser()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # ---------- 关闭：先解绑 workbench，再通知主界面收回 ----------
    def closeEvent(self, event):
        if self._closed_handled:
            event.accept()
            return
        self._closed_handled = True

        # 1. 解除 win32 嵌入，浏览器送回桌面并最小化
        if self.browser_hwnd:
            try:
                win32gui.SetParent(self.browser_hwnd, 0)

                style = win32gui.GetWindowLong(self.browser_hwnd, win32con.GWL_STYLE)
                style = style | win32con.WS_CAPTION
                style = style | win32con.WS_THICKFRAME
                style = style | win32con.WS_MINIMIZEBOX
                style = style | win32con.WS_MAXIMIZEBOX
                style = style | win32con.WS_SYSMENU
                style = style & ~win32con.WS_CHILD
                win32gui.SetWindowLong(self.browser_hwnd, win32con.GWL_STYLE, style)

                win32gui.ShowWindow(self.browser_hwnd, win32con.SW_MINIMIZE)
            except Exception as e:
                print(f"清理浏览器窗口失败: {e}")

        # 2. ★ 关键：先把 workbench 从窗口里摘出来，避免随窗口销毁
        if self.workbench_widget is not None:
            self.workbench_widget.setParent(None)

        # 3. 主窗口恢复显示
        try:
            self.main_page.window().show()
        except Exception:
            pass

        # 4. 通知主页面把 workbench 插回去
        if hasattr(self.main_page, 'on_focus_window_closed'):
            try:
                self.main_page.on_focus_window_closed()
            except Exception as e:
                print(f"[FocusWindow] on_focus_window_closed 出错: {e}")

        # 5. 释放状态锁
        set_app_mode("idle")
        event.accept()