# auto_complaint_xunlei.py
import time
import os
import datetime
import calendar
from complaint_base import BaseComplaintRunner, AutoComplaintSignals
from complaint_common import DESC_TEMPLATE
from app_paths import DIR_TEMPLATES, FILE_AUTHORIZATION_PDF

# ★ 平台代号常量
from app_data import PLATFORM_XUNLEI


class XunleiComplaintRunner(BaseComplaintRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.platform_code = PLATFORM_XUNLEI
        self.platform_logo = "迅雷"

    def check_platform_login(self) -> bool:
        """迅雷专属登录检测：通过 URL 判断"""
        try:
            return "login" not in self.page.url
        except Exception:
            return False

    def _wait_for_user_handle(self, error_msg=""):
        """迅雷专属：人工接管挂起逻辑"""
        self.log(f"❌ 运行中断: {error_msg}")
        self.log("🛑 脚本已暂停，未关闭浏览器。请在弹出的窗口中查看当前状态。")
        self.log("👉 您可以手动接管完成后续操作，或者直接点击小窗右上角的 X，程序会自动结束。")

        self.take_screenshot()

        while True:
            if self.stop_event and self.stop_event.is_set():
                self.log("✅ 检测到用户主动停止信号，任务结束。")
                return
            try:
                if self.page.is_closed():
                    self.log("✅ 检测到当前标签页已关闭，任务结束。")
                    return
            except:
                return
            time.sleep(2)

    def execute_flow(self):
        """迅雷核心业务逻辑"""
        first_item = self.complaints_data[0]
        book_name = first_item.get("book", "未知作品").strip("《》")
        proof_file_path = os.path.join(self.user_dir, DIR_TEMPLATES, FILE_AUTHORIZATION_PDF)

        self.log("正在打开迅雷版权投诉页...")
        self.page.goto("https://copyright.xunlei.com/legal/#/", wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(3000)

        # 1. 登录检测
        if not self.wait_for_login(timeout_sec=300):
            return self._wait_for_user_handle("等待登录超时（5分钟）")

        # 2. 进入表单
        self.log("正在点击【同意并发起投诉】...")
        try:
            start_btn = self.page.locator("button:has-text('同意并发起投诉'):visible").first
            start_btn.wait_for(state="visible", timeout=10000)
            start_btn.click()
            self.page.wait_for_url("**/appeal**", timeout=15000)
            self.page.wait_for_timeout(2000)
        except Exception as e:
            return self._wait_for_user_handle(f"无法进入投诉填表页: {e}")

        self.log("正在填写投诉表单...")
        self.page.locator("input[placeholder*='作品名称']").fill(book_name)
        self.page.wait_for_timeout(500)

        self.log("-> 选择单选框...")
        self.page.locator("label:has-text('视听作品')").click()
        self.page.locator("label:has-text('信息网络传播权')").click()
        self.page.locator("label:has-text('原始取得')").click()

        # 3. 选择服务类型
        web_text = first_item.get("web_text", "")
        if not web_text:
            return self._wait_for_user_handle("web_text 为空，无法确定服务类型")
        try:
            self.page.locator(f"label:has-text('{web_text}')").click(timeout=5000)
            self.log(f"✅ 已选择服务类型: {web_text}")
        except Exception as e:
            return self._wait_for_user_handle(f"选择服务类型失败: {e}")

        self.page.wait_for_timeout(500)

        # 4. 上传证明文件
        if proof_file_path and os.path.exists(proof_file_path):
            self.log("正在上传权利证明文件...")
            try:
                file_input = self.page.locator(".ant-upload input[type='file']")
                file_input.set_input_files(proof_file_path)
                self.page.wait_for_timeout(3000)
                self.log("✅ 证明文件上传成功！")
            except Exception as e:
                self.log(f"⚠️ 文件上传失败: {e}")
        else:
            self.log("⚠️ 未检测到本地证明文件，跳过自动上传。请确保网页已保留历史文件。")

        # 5. 选择权利保护期
        self.log("正在选择权利保护期...")
        try:
            today = datetime.date.today()
            next_month = today.month % 12 + 1
            next_year = today.year if today.month < 12 else today.year + 1
            last_day = calendar.monthrange(next_year, next_month)[1]
            end_date_str = f"{next_year}年{next_month}月{last_day}日"

            self.page.locator("span.ant-calendar-picker-input").click()
            self.page.wait_for_selector(".ant-calendar-range", state="visible")
            self.page.locator(".ant-calendar-range-left .ant-calendar-today").click()
            self.page.wait_for_timeout(500)
            self.page.locator(f".ant-calendar-range-right td[title='{end_date_str}']").click()
            self.page.wait_for_timeout(500)
            self.log("✅ 日期选择完成！")
        except Exception as e:
            return self._wait_for_user_handle(f"日期选择失败: {e}")

        # 6. 上传批量链接 Excel
        self.log("正在自动上传批量链接 Excel...")
        try:
            with self.page.expect_file_chooser() as fc_info:
                self.page.locator("button:has-text('从Excel导入')").click()
            file_chooser = fc_info.value
            file_chooser.set_files(os.path.abspath(self.temp_excel_path))
            self.log("✅ 文件已上传，等待迅雷解析...")
            self.page.wait_for_timeout(4000)
        except Exception as e:
            return self._wait_for_user_handle(f"自动上传Excel失败: {e}")

        # 7. 填写描述并提交
        self.log("正在填写侵权理由...")
        desc_text = DESC_TEMPLATE.format(name_str=first_item["name_str"], url_str=first_item["url_str"])
        self.page.locator("textarea[placeholder='最多800字']").fill(desc_text[:800])

        self.log("点击下一步，进入预览页...")
        self.page.locator("button:has-text('下一步')").click()
        self.page.wait_for_timeout(3000)

        self.log("点击确认提交...")
        try:
            submit_btn = self.page.locator("button:has-text('确认提交'):visible").first
            submit_btn.wait_for(state="visible", timeout=10000)
            submit_btn.click()
        except Exception as e:
            return self._wait_for_user_handle(f"找不到确认提交按钮: {e}")

        self.log("等待提交结果...")
        try:
            self.page.wait_for_selector("text='提交成功'", timeout=15000)
            self.log("🎉 迅雷投诉提交成功！本批次完成。")
        except:
            self.log("⚠️ 未能明确检测到成功提示，但已点击提交，请人工确认。")


# ★ 保持调度器调用的接口不变
def run_auto_complaint_xunlei(complaints_data, signals=None, is_all=False, stop_event=None, login_event=None,
                              dialog_signal=None):
    runner = XunleiComplaintRunner(complaints_data, signals, is_all, stop_event, login_event, dialog_signal)
    return runner.run()