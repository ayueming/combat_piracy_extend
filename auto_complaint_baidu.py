# auto_complaint_baidu.py
import time
import os
from complaint_base import BaseComplaintRunner, AutoComplaintSignals
from complaint_common import DESC_TEMPLATE
from app_data import MODULE_NETDISK, MODULE_OTHER, PLATFORM_BAIDU


class BaiduComplaintRunner(BaseComplaintRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.platform_code = PLATFORM_BAIDU
        self.platform_logo = "百度"

    def check_platform_login(self) -> bool:
        """
        百度专属登录检测：通过 URL 变化判断
        """
        try:
            # 1. 如果 URL 包含了 subject，说明进入了主体信息页，绝对登录成功
            if "subject" in self.page.url:
                return True

            # 2. 如果页面出现了登录框，说明没登录
            if self.page.locator("input[placeholder='手机号/用户名/邮箱']").count() > 0:
                if self.page.locator("input[placeholder='手机号/用户名/邮箱']").first.is_visible():
                    return False

            # 3. 没登录框，但也没有跳转，可能还在首页或者其他页，返回 False
            return False
        except Exception:
            return False

    def _wait_for_user_handle(self, error_msg=""):
        """
        百度专属：人工接管挂起逻辑
        将原脚本中的闭包改为了类方法，方便访问 self.page 和 self.log
        """
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
        """百度核心业务逻辑"""
        first_item = self.complaints_data[0]
        book_name = first_item.get("book", "未知作品")
        baidu_id = first_item.get("baidu_id", "")
        clean_book_name = book_name.strip("《》")

        self.log("正在打开百度版权投诉页...")
        self.page.goto("https://newcopyright.baidu.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        self.page.wait_for_timeout(3000)

        self.log("正在点击“发起投诉”...")
        try:
            start_btn = self.page.locator("button:has-text('发起投诉'):visible").first
            start_btn.wait_for(state="visible", timeout=10000)
            start_btn.click()
        except Exception as e:
            return self._wait_for_user_handle(f"找不到【发起投诉】按钮，页面可能未加载完成: {e}")

        time.sleep(3)

        # 1. 调用基类的等待登录（会自动调用 check_platform_login）
        if "subject" not in self.page.url:
            # 判断一下有没有登录框，如果没有，说明大概率是网络慢没跳过去，而不是没登录
            has_login_box = self.page.locator("input[placeholder='手机号/用户名/邮箱']").count() > 0

            if not has_login_box:
                self.log("检测到未进入主体页，但未见登录框，正在尝试重新点击“发起投诉”...")
                try:
                    new_start_btn = self.page.locator("button:has-text('发起投诉'):visible").first
                    if new_start_btn.count() > 0:
                        new_start_btn.click()
                        time.sleep(3)  # 再等它 3 秒
                except Exception as e:
                    self.log(f"重试点击失败: {e}")

            # 2. 此时再调用基类的等待登录，如果还没进去，才真的走挂起弹窗
        if not self.wait_for_login(timeout_sec=300):
            return self._wait_for_user_handle("等待登录超时（5分钟）或页面发生异常")

        self.log("正在确认账号主体信息，点击“下一步”...")
        try:
            next_btn = self.page.locator("button.el-button--primary:has-text('下一步'):visible").first
            next_btn.wait_for(state="visible", timeout=10000)
            next_btn.click()
            self.log("正在等待跳转到【权属登记】...")
            self.page.wait_for_url("**/hasownership**", timeout=15000)
            time.sleep(2)
        except Exception as e:
            return self._wait_for_user_handle(f"进入权属登记页(/hasownership)失败: {e}")

        # 2. 搜索作品
        try:
            if baidu_id:
                self.log(f"✅ 检测到百度CP号，正在通过 百度CP号 搜索: {baidu_id}")
                id_input = self.page.locator("input[placeholder*='ID'], input[placeholder*='id']").first
                if id_input.count() > 0:
                    id_input.fill(baidu_id)
                else:
                    self.page.locator("input").nth(1).fill(baidu_id)
            else:
                self.log(f"⚠️ 未检测到百度CP号，正在通过 作品名 搜索: {clean_book_name}")
                name_input = self.page.locator("input[placeholder='请输入作品名称']").first
                name_input.wait_for(state="visible", timeout=10000)
                name_input.fill(clean_book_name[:4])

            self.page.locator("button:has-text('搜索')").first.click()
            time.sleep(3)
            target_text = baidu_id if baidu_id else clean_book_name[:4]
            row = self.page.locator("div.el-table__row, tr").filter(has_text=target_text).first
            select_btn = row.locator("p.selectpop:has-text('选择')").first
            select_btn.click()
            self.log("正在等待跳转到【填写投诉链接】...")
            self.page.wait_for_url("**/complaint**", timeout=15000)
            time.sleep(2)
        except Exception as e:
            return self._wait_for_user_handle(f"选择作品失败（可能未登记或网络慢）: {e}")

        # 3. 填写表单
        self.log("正在填写投诉表单...")
        self.log("正在选择投诉产品...")
        try:
            select_input = self.page.locator(".el-select input[placeholder='请选择']").first
            select_input.click(force=True)
            time.sleep(1)

            module_code = first_item.get("module_code", MODULE_OTHER)
            web_text = first_item.get("web_text", "")

            try:
                option = self.page.locator("li:visible").filter(has_text=web_text).first
                option.click(timeout=3000)
                self.log(f"-> 已选择: {web_text}")
            except Exception:
                self.log(f"⚠️ 点击选项失败，降级使用键盘盲按: {web_text}")
                if module_code == MODULE_NETDISK:
                    self.page.keyboard.press("ArrowDown")
                else:
                    self.page.keyboard.press("ArrowDown")
                    self.page.keyboard.press("ArrowDown")
                time.sleep(0.5)
                self.page.keyboard.press("Enter")

            time.sleep(1)
            self.log("✅ 产品选择完成")
        except Exception as e:
            return self._wait_for_user_handle(f"选择投诉产品失败: {e}")

        self.log("正在填写投诉描述...")
        try:
            desc_text = DESC_TEMPLATE.format(name_str=first_item["name_str"], url_str=first_item["url_str"])
            desc_box = self.page.locator("textarea[placeholder*='请详细描述您遇到的问题']").first
            desc_box.click(force=True)
            desc_box.fill(desc_text[:200])
            self.log("✅ 描述填写完成")
        except Exception as e:
            return self._wait_for_user_handle(f"填写描述失败: {e}")

        self.log("正在填写原版链接...")
        try:
            self.page.locator("input[placeholder='请输入链接标题']").first.click(force=True)
            self.page.locator("input[placeholder='请输入链接标题']").first.fill("原版主页链接，点击目录则是正文内容")
            time.sleep(0.5)
            self.page.locator("input[placeholder='请输入链接地址']").first.click(force=True)
            self.page.locator("input[placeholder='请输入链接地址']").first.fill(first_item["url_str"])
            self.log("✅ 原版链接填写完成")
        except Exception as e:
            return self._wait_for_user_handle(f"填写原版链接失败: {e}")

        self.log("正在自动上传批量链接 Excel...")
        try:
            with self.page.expect_file_chooser() as fc_info:
                self.page.locator("span:has-text('选择文件')").first.click(force=True)
            file_chooser = fc_info.value
            file_chooser.set_files(os.path.abspath(self.temp_excel_path))
            self.log("✅ 文件已上传，等待百度解析...")
            time.sleep(5)
        except Exception as e:
            return self._wait_for_user_handle(f"自动上传文件失败: {e}")

        if self.page.locator("text=该链接已投诉").count() > 0:
            self.log("❌ 检测到本批次有链接【已被投诉】（存在历史记录）。")
            return self._wait_for_user_handle("存在已投诉记录")
        else:
            self.log("✅ 链接检查通过，未发现已投诉记录。")

        # 4. 扫码验证
        self.log("正在进入下一步（身份真实性验证）...")
        try:
            next_btn_2 = self.page.locator("button.el-button--primary:has-text('下一步'):visible").last
            next_btn_2.wait_for(state="visible", timeout=10000)
            next_btn_2.click(force=True)
            self.log("正在等待跳转到【扫码验证页】...")
            self.page.wait_for_url("**/verification**", timeout=15000)
            time.sleep(2)
        except Exception as e:
            return self._wait_for_user_handle(f"进入扫码页(/verification)失败: {e}")

        self.log("👉 【需要人工干预】请在弹出的页面中扫码进行身份验证！")
        self.log("扫码成功后，脚本将自动继续并提交...")

        max_wait = 600
        waited = 0
        scan_success = False
        while waited < max_wait:
            if self.stop_event and self.stop_event.is_set():
                return
            try:
                for p_tab in self.page.context.pages:
                    if p_tab.is_closed():
                        continue
                    if "confirm" in p_tab.url or p_tab.locator("button:has-text('提交投诉'):visible").count() > 0:
                        self.page = p_tab  # ★ 核心：切换页面
                        scan_success = True
                        break
                if scan_success:
                    break
            except Exception:
                pass
            if waited > 0 and waited % 5 == 0:
                self.log(f"⏳ 正在等待扫码验证...（已等待 {waited} 秒）")
            time.sleep(1)
            waited += 1

        if not scan_success:
            return self._wait_for_user_handle("等待扫码超时（10分钟）或发生页面异常")

        self.log("✅ 扫码成功，已进入确认页面。")
        time.sleep(3)

        # 5. 最终提交
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            try:
                checkbox = self.page.locator("span.el-checkbox__inner:visible").first
                if checkbox.count() > 0 and checkbox.is_visible():
                    checkbox.click(force=True)
                    time.sleep(0.5)
            except:
                pass

            submit_btn = self.page.locator("button:has-text('提交投诉'):visible").first
            submit_btn.wait_for(state="visible", timeout=10000)
            submit_btn.click(force=True)
            self.log("🎉 已点击提交！正在等待百度响应...")

            success_found = False
            for _ in range(15):
                if "complete" in self.page.url or self.page.locator("text=反馈完成").count() > 0 or self.page.locator(
                        "text=提交成功").count() > 0:
                    success_found = True
                    break
                time.sleep(1)

            if success_found:
                self.log("✅ 页面提示提交成功！本批次完成。")
            else:
                self.log("⚠️ 未能明确检测到成功提示，但已点击提交。")
        except Exception as e:
            return self._wait_for_user_handle(f"提交或验证成功提示失败: {e}")


# ★ 保持调度器调用的接口不变
def run_auto_complaint_baidu(complaints_data, signals=None, is_all=False, stop_event=None, login_event=None,
                             dialog_signal=None):
    runner = BaiduComplaintRunner(complaints_data, signals, is_all, stop_event, login_event, dialog_signal)
    return runner.run()