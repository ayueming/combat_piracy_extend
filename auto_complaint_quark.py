# auto_complaint_quark.py
import time
import re
import os
from complaint_base import BaseComplaintRunner, AutoComplaintSignals
from complaint_common import DESC_TEMPLATE
from app_data import MODULE_SEARCH, MODULE_NETDISK, MODULE_OTHER, PLATFORM_QUARK


class QuarkComplaintRunner(BaseComplaintRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.platform_code = PLATFORM_QUARK
        self.platform_logo = "夸克"

    def check_platform_login(self) -> bool:
        """夸克专属登录检测：通过 DOM 元素判断"""
        try:
            # 如果有未登录的iframe，说明掉线
            if self.page.locator("div.box-quark, iframe#quarkIframe").count() > 0:
                return False

            # 尝试找用户头像或标识
            user_span = self.page.locator("span.user.ant-dropdown-trigger").first
            if user_span.count() > 0 and "夸克用户" in user_span.inner_text():
                return True
        except Exception:
            pass
        return False

    def execute_flow(self):
        """夸克核心业务逻辑"""
        self.log("正在打开夸克投诉主页...")
        self.page.goto("https://ipp.quark.cn/#/home", wait_until="domcontentloaded", timeout=30000)

        # 1. 等待登录（调用基类骨架）
        if not self.wait_for_login(timeout_sec=300):
            raise RuntimeError("用户中断了脚本或登录超时")

        if self.stop_event.is_set():
            return

        # 2. 进入投诉表单
        self.log("正在进入投诉表单...")
        try:
            btn_start = self.page.locator("button.ant-btn-primary:has-text('发起侵权投诉')").first
            btn_start.wait_for(state="visible", timeout=10000)
            btn_start.click()
            self.page.wait_for_timeout(2000)
        except Exception as e:
            raise RuntimeError(f"找不到【发起侵权投诉】按钮: {e}")

        # 3. 自动勾选固定选项
        self.log("正在自动勾选固定选项...")
        try:
            self.page.locator("label:has-text('权利人')").click(timeout=3000)
        except:
            pass

        first_holder = self.complaints_data[0].get("rights_holder", "")
        if first_holder:
            self.log(f"正在自动选择具体权利人: {first_holder}")
            try:
                dropdown = self.page.locator("#obligee_id")
                if dropdown.count() > 0:
                    dropdown.scroll_into_view_if_needed()
                    self.page.wait_for_timeout(500)
                    dropdown.click(force=True)
                    self.page.wait_for_timeout(1500)
                    option = self.page.locator(".ant-select-dropdown-menu-item").filter(has_text=first_holder).first
                    if option.count() > 0 and option.is_visible():
                        option.click(force=True)
                    else:
                        self.page.keyboard.press("ArrowDown")
                        self.page.wait_for_timeout(500)
                        self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(1000)
            except Exception as e:
                self.log(f"⚠️ 自动选择权利人失败: {e}")

        try:
            self.page.get_by_text("知识产权").click(timeout=3000)
            self.page.get_by_text("著作权(含视频、图文、图集等)").click(timeout=3000)
        except:
            pass

        # 4. 核心修复：基于 module_code 严格选择
        module_code = self.complaints_data[0].get("module_code", MODULE_OTHER)
        self.log(f"正在选择功能模块，当前识别模块代号: {module_code}")

        try:
            if module_code == MODULE_SEARCH:
                self.page.get_by_text("夸克搜索", exact=True).click(timeout=5000)
                self.log("✅ 已选择：夸克搜索")
            elif module_code == MODULE_NETDISK:
                self.page.get_by_text("夸克网盘", exact=True).click(timeout=5000)
                self.log("✅ 已选择：夸克网盘")
            else:
                raise RuntimeError(f"未知的模块代号: {module_code}，为防止投错，脚本已停止。")
        except Exception as e:
            raise RuntimeError(f"选择功能模块失败，找不到对应选项: {e}")

        try:
            self.page.get_by_text("小说", exact=True).click(timeout=3000)
            self.log("✅ 已选择：小说")
        except Exception as e:
            self.log(f"⚠️ 选择“小说”失败，继续执行... ({e})")

        if self.stop_event.is_set():
            return

        # 5. 批量导入
        self.log("正在执行【批量导入】...")
        try:
            self.page.locator("a.multi-add").first.click()
            self.page.wait_for_timeout(2000)
            with self.page.expect_file_chooser() as fc_info:
                btn_upload = self.page.locator(
                    "button.ant-btn-sm:has-text('上传文件'), button:has-text('上传文件')").first
                btn_upload.click()
            file_chooser = fc_info.value
            file_chooser.set_files(os.path.abspath(self.temp_excel_path))
            self.page.wait_for_timeout(4000)

            self.log("正在点击【解析数据】...")
            parse_btn = self.page.locator("button.ant-btn-primary:has-text('解析数据')").first
            parse_btn.wait_for(state="visible", timeout=5000)
            parse_btn.click(force=True)
            self.log("✅ 解析数据点击成功！正在等待填充...")
            self.page.wait_for_timeout(5000)
        except Exception as e:
            raise RuntimeError(f"解析过程出错: {e}")

        if self.stop_event.is_set():
            return

        # 6. 填写描述与上传证明
        self.log("正在填写投诉描述...")
        try:
            first_item = self.complaints_data[0]
            desc_text = DESC_TEMPLATE.format(name_str=first_item["name_str"], url_str=first_item["url_str"])
            desc_textarea = self.page.locator("textarea[placeholder*='请客观公正描述']")
            if desc_textarea.count() > 0:
                desc_textarea.fill(desc_text)
                self.page.wait_for_timeout(500)
        except Exception as e:
            self.log(f"填写描述失败: {e}")

        pdf_path = self.complaints_data[0].get("evidence_path", "")
        self.log(f"正在准备上传证明材料，路径: {pdf_path}")
        if pdf_path and os.path.exists(pdf_path):
            try:
                upload_btn = self.page.locator("p", has_text="点击上传").first
                if upload_btn.count() > 0:
                    self.log("找到【证明文件】上传框，正在模拟点击并注入文件...")
                    with self.page.expect_file_chooser(timeout=5000) as fc_info:
                        upload_btn.click(force=True)
                    file_chooser = fc_info.value
                    file_chooser.set_files(os.path.abspath(pdf_path))
                    try:
                        self.page.wait_for_selector("div.ant-message:has-text('上传成功')", timeout=10000)
                        self.log("🎉 检测到“上传成功” Toast 提示，文件已挂载！")
                        self.page.wait_for_selector("div.ant-message:has-text('上传成功')", state="hidden",
                                                    timeout=5000)
                    except Exception:
                        self.log("⚠️ 未检测到“上传成功”提示，但文件可能已塞入，继续尝试提交...")
                else:
                    self.log("⚠️ 未找到“点击上传”按钮！")
            except Exception as e:
                self.log(f"❌ PDF上传过程发生异常: {e}")
        else:
            self.log(f"⚠️ 本地证明材料文件不存在或为空，跳过上传。")

        if self.stop_event.is_set():
            return

        # 7. 滚动并提交
        self.log("正在滚动到底部准备提交...")
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        self.page.wait_for_timeout(2000)

        self.log("准备点击【提交】...")
        try:
            btn_submit = self.page.locator("button.ant-btn-primary").filter(has_text=re.compile(r"提\s*交")).last
            btn_submit.scroll_into_view_if_needed()
            self.page.wait_for_timeout(1000)
            self.log("正在执行真实鼠标点击...")
            btn_submit.click(force=True)
            self.log("✅ 已触发提交，等待响应...")
            self.page.wait_for_timeout(2000)
            try:
                confirm_btn = self.page.locator("button.ant-btn-primary:visible").filter(
                    has_text=re.compile("确定|确认")).first
                if confirm_btn.count() > 0 and confirm_btn.is_visible():
                    confirm_btn.click(force=True)
                    self.log("✅ 已点击二次确认弹窗！")
                    self.page.wait_for_timeout(2000)
            except:
                pass

            self.log("正在等待提交成功的弹窗响应...")
            self.page.wait_for_selector("text=提交成功", timeout=15000)
            self.log("🎉 检测到「提交成功」弹窗，本批次投诉确认成功！")

            # 无需在这里写 is_all 的 goto 了，基类会自动处理 about:blank 复用
        except Exception as e:
            raise RuntimeError(f"提交失败或未检测到成功提示: {e}")


# ★ 保持调度器调用的接口不变
def run_auto_complaint_quark(complaints_data, signals=None, is_all=False, stop_event=None, login_event=None,
                             dialog_signal=None):
    runner = QuarkComplaintRunner(complaints_data, signals, is_all, stop_event, login_event, dialog_signal)
    return runner.run()