# complaint_base.py
import os
import time
import traceback
from PySide6.QtCore import QObject, Signal

from app_paths import get_user_dir, DIR_TEMP, TEMP_EXCEL_TPL
from db_config import get_current_user
from browser_manager import BrowserManager
from complaint_excel_utils import generate_platform_excel
from complaint_common import take_error_screenshot


class AutoComplaintSignals(QObject):
    progress = Signal(str)


class BaseComplaintRunner:
    def __init__(self, complaints_data, signals=None, is_all=False, stop_event=None, login_event=None,
                 dialog_signal=None):
        self.complaints_data = complaints_data
        self.signals = signals or AutoComplaintSignals()
        self.is_all = is_all
        self.stop_event = stop_event
        self.login_event = login_event
        self.dialog_signal = dialog_signal

        # 1. 系统级校验
        self.user_id = get_current_user()
        if not self.user_id:
            raise ValueError("❌ 错误：未获取到当前登录用户")
        self.user_dir = get_user_dir(self.user_id)

        # 2. 运行状态初始化
        self.page = None
        self.temp_excel_path = ""
        self.task_success = False

        # 3. 子类必须覆盖的标识
        self.platform_code = ""
        self.platform_logo = ""

    def log(self, msg):
        """统一日志输出，自动带上平台前缀"""
        full_msg = f"[{self.platform_logo}] {msg}"
        print(full_msg)
        if self.signals:
            self.signals.progress.emit(full_msg)

    def generate_excel(self):
        """生成临时 Excel，统一存放在 DIR_TEMP"""
        self.temp_excel_path = os.path.join(self.user_dir, DIR_TEMP, TEMP_EXCEL_TPL.format(platform=self.platform_code))
        if os.path.exists(self.temp_excel_path):
            try:
                os.remove(self.temp_excel_path)
            except:
                pass

        self.log("正在生成临时 Excel...")
        if not generate_platform_excel(self.complaints_data, self.platform_code, self.temp_excel_path):
            raise RuntimeError("生成临时 Excel 失败")

    def init_browser(self):
        """唤醒浏览器并获取工作页面"""
        self.log("正在唤醒统一浏览器...")
        try:
            bm = BrowserManager.instance()
            self.page = bm.new_page()
        except Exception as e:
            raise RuntimeError(f"浏览器启动失败: {e}")

    def take_screenshot(self):
        """保存报错截图"""
        if self.page and not self.page.is_closed():
            shot_path = take_error_screenshot(self.page, self.user_dir, self.platform_code)
            if shot_path:
                self.log(f"📸 已保存失败现场截图: {shot_path}")

    # ==================== 登录等待骨架 ====================
    def check_platform_login(self) -> bool:
        """
        ★ 抽象方法：子类必须实现，返回 True 表示已登录，False 表示未登录/掉线
        """
        raise NotImplementedError("子类必须实现 check_platform_login")

    def wait_for_login(self, timeout_sec=300, reload_on_event=True):
        """
        通用的登录等待骨架：循环调用子类的 check_platform_login
        """
        self.log("⏳ 正在检查账号登录状态...")
        waited = 0
        while True:
            if self.stop_event and self.stop_event.is_set():
                return False

            # 调用子类判断
            if self.check_platform_login():
                self.log("✅ 账号已登录！脚本自动接管。")
                if self.dialog_signal:
                    self.dialog_signal.reset_progress()
                return True

            # 首次提示
            if waited == 0:
                self.log("⚠️ 检测到未登录/掉线，脚本已挂起...")
                if self.dialog_signal:
                    self.dialog_signal.show_login_required()

            # 等待事件或超时
            if self.login_event:
                self.login_event.wait(timeout=5)
                self.login_event.clear()
            else:
                time.sleep(5)

            waited += 5
            if waited % 10 == 0:
                self.log(f"⏳ 等待登录中...（已等待 {waited} 秒）")

            if waited >= timeout_sec:
                self.log(f"❌ 等待登录超时（{timeout_sec}秒）")
                return False

            # 如果用户点击了“我已登录”按钮，可能需要刷新页面
            if reload_on_event and self.page and not self.page.is_closed():
                try:
                    self.page.wait_for_load_state("networkidle", timeout=3000)
                except:
                    pass

    # ==================== 生命周期统一入口 ====================
    def run(self):
        """统一执行入口，负责资源回收和现场保护"""
        try:
            self.generate_excel()
            self.init_browser()

            # 调用子类的业务实现
            self.execute_flow()

            # 如果没抛异常，且没返回 False，则视为成功
            self.task_success = True
            self.log("✅ 任务执行成功！")
            return True

        except Exception as e:
            self.log(f"❌ 运行遇到严重错误：{e}")
            self.log(traceback.format_exc())
            self.take_screenshot()
            return False

        finally:
            # 1. 清理临时文件
            if self.temp_excel_path and os.path.exists(self.temp_excel_path):
                try:
                    os.remove(self.temp_excel_path)
                except:
                    pass

            # 2. 成功复用Tab，失败保留现场
            if self.task_success:
                try:
                    if self.page and not self.page.is_closed():
                        self.page.goto("about:blank", timeout=5000)
                        print(f"[{self.platform_logo}] （任务成功，页面已重置为空白页，供下一批复用）")
                except Exception:
                    pass
            else:
                print(f"[{self.platform_logo}] （任务失败/挂起，保留当前现场页面，供用户查看）")

    def execute_flow(self):
        """★ 抽象方法：子类必须实现具体的业务逻辑"""
        raise NotImplementedError("子类必须实现 execute_flow 方法")