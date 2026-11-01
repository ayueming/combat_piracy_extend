import os
import sys
import asyncio

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QStackedWidget, QDialog, QLabel,
)
from PySide6.QtCore import Qt

# 导入后台通信服务
from ws_server import start_ws_server, ws_signals

# 导入你的页面模块
from page_books import BooksPage
from page_links import LinksPage
from page_search import SearchConsolePage
from page_spider import SpiderPage
from page_complaints import ComplaintsPage
from page_evidence import EvidencePage
from page_platforms import PlatformsPage
from page_profile import ProfilePage

# 导入登录模块
from login_window import LoginWindow
from login_auto import try_auto_login, clear_session

VERSION = "2.2.1"

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"打盗维权系统_试用版_v{VERSION}")
        self.setStyleSheet("QMainWindow { background-color: #F0F4F1; }")

        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            target_w = min(1200, available.width() - 100)
            target_h = min(800, available.height() - 100)
            self.resize(target_w, target_h)
            frame = self.frameGeometry()
            frame.moveCenter(available.center())
            self.move(frame.topLeft())
        else:
            self.resize(1200, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ================= 左侧菜单栏 =================
        self.left_container = QWidget()
        self.left_container.setFixedWidth(160)
        self.left_container.setStyleSheet("background-color: #F0F4F1;")
        left_layout = QVBoxLayout(self.left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setStyleSheet("""
            QListWidget { background-color: #F0F4F1; color: #4B5563; font-size: 15px; border: none; outline: none; padding-top: 15px; } 
            QListWidget::viewport { background-color: transparent; }
            QListWidget::item { height: 50px; margin: 0; padding-left: 20px; border: none; } 
            QListWidget::item:hover { background-color: #E1E9E3; color: #1F1F1F; }
            QListWidget::item:selected { background-color: #FFFFFF; color: #059669; font-weight: bold; border-left: 4px solid #059669; border-top-right-radius: 0px; border-bottom-right-radius: 0px; }
        """)
        self.sidebar.addItems([
            "📚 作品管理", "🔗 盗文链接", "🌐️ 检索管理", "🕷️ 抓取管理",
            "⚖️ 投诉管理", "🏛️ 投诉平台", "📂 维权资料",
            "👤 个人与帮助",
        ])
        left_layout.addWidget(self.sidebar)

        version_container = QWidget()
        version_layout = QVBoxLayout(version_container)
        version_layout.setContentsMargins(20, 10, 15, 20)
        version_layout.setSpacing(0)

        version_text = f"""
        <div style='line-height: 1.6; color: #9CA3AF; font-size: 11px;'>
            <p style='margin: 0; color: #A1A1AA;'>本软件仅供维权辅助使用，请严格遵守相关平台法规。</p>
            <p style='margin: 0; margin-bottom: 8px;'>v.{VERSION} ©HowLittle</p>
        </div>
        """
        lbl_version = QLabel(version_text)
        lbl_version.setTextFormat(Qt.RichText)
        lbl_version.setWordWrap(True)
        lbl_version.setStyleSheet("color: #9CA3AF;")
        version_layout.addWidget(lbl_version)
        left_layout.addWidget(version_container)

        layout.addWidget(self.left_container)

        # ================= 右侧页面区 =================
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background-color: #FFFFFF; }")
        layout.addWidget(self.stack)

        self.books_page = BooksPage(self)
        self.links_page = LinksPage(self)
        self.search_page = SearchConsolePage(self)
        self.spider_page = SpiderPage(self)
        self.complaint_page = ComplaintsPage(self)
        self.platforms_page = PlatformsPage()
        self.evidence_page = EvidencePage()
        self.profile_page = ProfilePage(self)

        self.stack.addWidget(self.books_page)
        self.stack.addWidget(self.links_page)
        self.stack.addWidget(self.search_page)
        self.stack.addWidget(self.spider_page)
        self.stack.addWidget(self.complaint_page)
        self.stack.addWidget(self.platforms_page)
        self.stack.addWidget(self.evidence_page)
        self.stack.addWidget(self.profile_page)

        self.sidebar.currentRowChanged.connect(self.change_page)
        self.sidebar.setCurrentRow(0)

        # ★ 核心：监听后台发来的信号，让 UI 自动刷新（必须在类内部）
        ws_signals.new_data_inserted.connect(self.on_new_data)

    # ★ 这个回调函数也必须放在类里面
    def on_new_data(self, count):
        """后台洗完数据后，自动刷新你的检索页"""
        print(f"UI收到通知：后台新增 {count} 条数据，正在刷新界面...")
        if hasattr(self, 'search_page'):
            self.search_page.refresh_tables()

    def change_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.links_page.refresh_table()
        elif index == 2:
            self.search_page.load_books()
            self.search_page.refresh_tables()
        elif index == 3:
            self.spider_page.refresh_data()
        elif index == 6:
            self.evidence_page.refresh_books()
            self.evidence_page.load_evidences()
        elif index == 7:
            self.profile_page.refresh_profile()

    def on_new_data(self, count):
        """后台洗完数据后，自动刷新你的检索页"""
        print(f"UI收到通知：后台新增 {count} 条数据，正在刷新界面...")
        # ★ 关键修改：右侧面板 SearchResultPanel 已经自己监听并刷新了，
        # 这里不要再调用 self.search_page.refresh_tables()，否则会双重刷新。
        # 如果你有左侧的状态需要同步，可以在这里做，目前不需要。

    def change_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.links_page.refresh_table()
        elif index == 2:
            self.search_page.load_books()
            # ★ 关键修改：不再调用 self.search_page.refresh_tables()
            # 右侧面板每次被切回来时，是否需要强制刷新一次最新数据？
            # 如果想确保切回来看到最新，调用右侧面板的方法：
            if hasattr(self.search_page, 'result_panel'):
                self.search_page.result_panel.refresh_tables()
        elif index == 3:
            self.spider_page.refresh_data()
        elif index == 6:
            self.evidence_page.refresh_books()
            self.evidence_page.load_evidences()
        elif index == 7:
            self.profile_page.refresh_profile()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 启动后台通信线程
    start_ws_server()

    auto_ok = try_auto_login()

    while True:
        if not auto_ok:
            login = LoginWindow()
            if login.exec() != QDialog.Accepted:
                sys.exit(0)

        auto_ok = False

        window = MainApp()
        window.show()

        exit_code = app.exec()

        if getattr(window, "_logout_requested", False):
            clear_session()
            continue

        sys.exit(exit_code)