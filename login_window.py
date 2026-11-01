# login_window.py
import os
import re
import json
import time
import httpx
import threading  # ★ 新增：用于后台异步预热

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QApplication, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QCursor, QAction, QPixmap, QPainter, QPen, QIcon, QColor

from login_device_id import get_machine_id
from config import SUPABASE_URL, SUPABASE_ANON_KEY, has_supabase_config
from ui_components import draw_checkbox, CHECK_BOX_SIZE
from app_paths import get_user_dir, get_session_path, FILE_AUTH

EMAIL_PATTERN = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

# ★ 全局复用同一个 HTTP 连接池，大幅减少 TLS 握手时间
_http_client = httpx.Client(timeout=15.0)


def create_eye_icon(is_open=True):
    """纯代码绘制“眼睛”图标"""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(Qt.GlobalColor.darkGray, 1.5)
    painter.setPen(pen)

    if is_open:
        painter.drawEllipse(4, 7, 16, 10)
        painter.setBrush(Qt.GlobalColor.darkGray)
        painter.drawEllipse(9, 9, 6, 6)
    else:
        painter.drawLine(4, 12, 20, 12)
        painter.drawLine(4, 12, 2, 10)
        painter.drawLine(12, 12, 12, 9)
        painter.drawLine(20, 12, 22, 10)

    painter.end()
    return QIcon(pixmap)


class UnifiedCheckBox(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(24)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box_rect = QRect(0, (self.height() - CHECK_BOX_SIZE) // 2, CHECK_BOX_SIZE, CHECK_BOX_SIZE)
        draw_checkbox(p, box_rect, self.isChecked())
        text_rect = QRect(box_rect.right() + 8, 0, self.width() - box_rect.width() - 8, self.height())
        p.setPen(QColor("#666666"))
        font = p.font()
        font.setPixelSize(13)
        p.setFont(font)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())


class LoginWindow(QDialog):
    # ★ 类级别变量，防止多实例绕过探测限频
    _probe_window_start = 0.0
    _probe_count = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打盗维权系统 - 登录")
        self.setFixedSize(420, 500)
        self.is_register_mode = False

        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #333; }
            QLineEdit {
                border: 1px solid #DCDCDC; border-radius: 4px;
                padding: 8px 10px; font-size: 13px; background: #FAFAFA;
            }
            QLineEdit:focus { border: 1px solid #10B981; background: #FFFFFF; }
            QLineEdit[error="true"] { 
                background-color: #FEF2F2; 
                border: 1px solid #EF4444; 
            }
            QPushButton#mainBtn {
                background: #10B981; color: white; font-weight: bold;
                padding: 10px; border: none; border-radius: 4px; font-size: 14px;
            }
            QPushButton#mainBtn:hover { background: #059669; }
            QPushButton#mainBtn:disabled { background: #9CA3AF; }
            QLabel#linkLbl { color: #10B981; font-size: 12px; }
            QLabel#linkLbl:hover { text-decoration: underline; }
        """)
        self._setup_ui()

        # ★ 窗口初始化完成后，开启后台预热
        self._prewarm_edge_function()

    def _prewarm_edge_function(self):
        """后台静默请求一次，唤醒 Supabase 边缘函数"""

        def _ping():
            if not has_supabase_config():
                return
            try:
                base_url = SUPABASE_URL.rstrip("/")
                # 发一个空请求，必然被拦截，但足以让云端建立连接并唤醒函数
                _http_client.post(
                    f"{base_url}/functions/v1/verify-license",
                    headers={"apikey": SUPABASE_ANON_KEY},
                    json={},
                    timeout=10.0
                )
            except Exception:
                pass  # 预热失败静默处理，不影响主流程

        threading.Thread(target=_ping, daemon=True).start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(14)

        self.title_lbl = QLabel("打盗维权系统")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_lbl.setFont(title_font)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_lbl)

        self.subtitle = QLabel("请登录后使用")
        self.subtitle.setStyleSheet("color: #888; font-size: 12px;")
        self.subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle)
        layout.addSpacing(10)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("邮箱")
        self.email_input.textChanged.connect(lambda: self._clear_error(self.email_input))
        self.email_input.editingFinished.connect(self._check_email_on_focus_out)
        layout.addWidget(self.email_input)

        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("密码（至少6位）")
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.returnPressed.connect(self.on_main_action)
        self.pwd_input.textChanged.connect(lambda: self._clear_error(self.pwd_input))
        self.pwd_input.editingFinished.connect(self._check_pwd_on_focus_out)

        self.toggle_pwd_action = QAction(create_eye_icon(is_open=True), "", self)
        self.toggle_pwd_action.triggered.connect(self._toggle_pwd_visibility)
        self.pwd_input.addAction(self.toggle_pwd_action, QLineEdit.TrailingPosition)
        layout.addWidget(self.pwd_input)

        self.reg_tip_label = QLabel("提示：密码请不要和自己的重要密码相关联，666666也可以。")
        self.reg_tip_label.setStyleSheet("color: #F59E0B; font-size: 12px;")
        self.reg_tip_label.setWordWrap(True)
        self.reg_tip_label.hide()
        layout.addWidget(self.reg_tip_label)

        self.remember_cb = UnifiedCheckBox("记住登录状态")
        self.remember_cb.setChecked(True)
        layout.addWidget(self.remember_cb)

        self.tip_label = QLabel("")
        self.tip_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self.tip_label.setWordWrap(True)
        self.tip_label.setMinimumHeight(32)
        self.tip_label.setTextFormat(Qt.RichText)
        self.tip_label.setOpenExternalLinks(False)
        self.tip_label.linkActivated.connect(self._on_tip_link)
        layout.addWidget(self.tip_label)

        self.main_btn = QPushButton("登 录")
        self.main_btn.setObjectName("mainBtn")
        self.main_btn.setCursor(Qt.PointingHandCursor)
        self.main_btn.clicked.connect(self.on_main_action)
        layout.addWidget(self.main_btn)

        self.switch_lbl = QLabel("还没有账号？点击免费注册")
        self.switch_lbl.setObjectName("linkLbl")
        self.switch_lbl.setAlignment(Qt.AlignCenter)
        self.switch_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        self.switch_lbl.mousePressEvent = self.toggle_mode
        layout.addWidget(self.switch_lbl)
        layout.addStretch()

    def _set_input_error(self, widget, is_error):
        widget.setProperty("error", "true" if is_error else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _clear_error(self, widget):
        self._set_input_error(widget, False)
        self.tip_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self.tip_label.setText("")
        self.tip_label.setMinimumHeight(32)

    def _check_email_on_focus_out(self):
        email = self.email_input.text().strip()
        if not email:
            return
        if not re.match(EMAIL_PATTERN, email):
            self._set_input_error(self.email_input, True)
            self._show_error("邮箱格式不正确，请检查。")
        else:
            self._set_input_error(self.email_input, False)

    def _check_pwd_on_focus_out(self):
        pwd = self.pwd_input.text()
        if not pwd:
            return

        has_error = False
        error_msg = ""
        if len(pwd) < 6:
            has_error = True
            error_msg = "密码长度至少为 6 位"
        elif re.search(r'[\u4e00-\u9fa5]', pwd):
            has_error = True
            error_msg = "密码不能包含中文字符"

        if has_error:
            self._set_input_error(self.pwd_input, True)
            self._show_error(error_msg)
        else:
            self._set_input_error(self.pwd_input, False)

    def _on_tip_link(self, href: str):
        if href == "register":
            if not self.is_register_mode:
                self.toggle_mode(None)
            self.tip_label.setMinimumHeight(32)
        elif href == "reset":
            QMessageBox.information(self, "重置密码",
                                    "请联系管理员重置密码。\n\n管理员可在后台为您设置新密码。")
        elif href == "resend_verify":
            QMessageBox.information(self, "邮箱验证",
                                    "请联系管理员重新发送验证邮件，或检查垃圾邮件箱。")

    def _toggle_pwd_visibility(self):
        if self.pwd_input.echoMode() == QLineEdit.Password:
            self.pwd_input.setEchoMode(QLineEdit.Normal)
            self.toggle_pwd_action.setIcon(create_eye_icon(is_open=False))
        else:
            self.pwd_input.setEchoMode(QLineEdit.Password)
            self.toggle_pwd_action.setIcon(create_eye_icon(is_open=True))

    def toggle_mode(self, event):
        self.is_register_mode = not self.is_register_mode

        self.tip_label.setText("")
        self.tip_label.setMinimumHeight(32)
        self._set_input_error(self.email_input, False)
        self._set_input_error(self.pwd_input, False)

        self.pwd_input.clear()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.toggle_pwd_action.setIcon(create_eye_icon(is_open=True))

        if self.is_register_mode:
            self.title_lbl.setText("注册新账号")
            self.subtitle.setText("请填写邮箱和密码进行注册")
            self.main_btn.setText("注 册")
            self.remember_cb.hide()
            self.reg_tip_label.show()
            self.switch_lbl.setText("已有账号？返回登录")
        else:
            self.title_lbl.setText("打盗维权系统")
            self.subtitle.setText("请登录后使用")
            self.main_btn.setText("登 录")
            self.remember_cb.show()
            self.reg_tip_label.hide()
            self.switch_lbl.setText("还没有账号？点击免费注册试用")

    def on_main_action(self):
        email = self.email_input.text().strip()
        pwd = self.pwd_input.text()

        self._set_input_error(self.email_input, False)
        self._set_input_error(self.pwd_input, False)
        self.tip_label.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self.tip_label.setText("")
        self.tip_label.setMinimumHeight(32)

        if not email:
            self._set_input_error(self.email_input, True)
            self._show_error("请输入邮箱")
            return
        if not pwd:
            self._set_input_error(self.pwd_input, True)
            self._show_error("请输入密码")
            return

        if self.is_register_mode:
            if not re.match(EMAIL_PATTERN, email):
                self._set_input_error(self.email_input, True)
                self._show_error("请输入正确的邮箱格式（如：name@example.com）")
                return
            if len(pwd) < 6:
                self._set_input_error(self.pwd_input, True)
                self._show_error("密码长度至少为 6 位")
                return
            if re.search(r'[\u4e00-\u9fa5]', pwd):
                self._set_input_error(self.pwd_input, True)
                self._show_error("密码不能包含中文字符")
                return

        self._set_loading(True)
        try:
            if not has_supabase_config():
                self._show_error("未配置 Supabase 服务，请联系开发者。")
                return

            base_url = SUPABASE_URL.rstrip("/")

            if self.is_register_mode:
                self._do_register(base_url, email, pwd)
            else:
                self._do_login(base_url, email, pwd)
        finally:
            self._set_loading(False)

    def _do_register(self, base_url, email, pwd):
        url = f"{base_url}/auth/v1/signup"
        headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
        payload = {"email": email, "password": pwd}

        try:
            # ★ 使用全局 client 发起请求
            resp = _http_client.post(url, json=payload, headers=headers)
        except Exception as e:
            self._show_error(f"网络连接失败：{e}")
            return

        if resp.status_code != 200:
            try:
                err_data = resp.json()
            except Exception:
                err_data = {}
            err_msg = (err_data.get("msg")
                       or err_data.get("error_description")
                       or err_data.get("message")
                       or f"HTTP {resp.status_code}")

            # ★ 优化：专门拦截“已注册”的情况
            if "already registered" in err_msg.lower():
                QMessageBox.warning(self, "该邮箱已注册", "这个邮箱已经注册过啦，请直接登录。")
                self.toggle_mode(None)  # 切回登录模式
                self.email_input.setText(email)  # 自动回填邮箱
                return

            self._show_error(f"注册失败：{err_msg}")
            return

        QMessageBox.information(self, "注册成功", "账号注册成功，请直接登录。")
        self.toggle_mode(None)
        self.email_input.setText(email)

    def _do_login(self, base_url, email, pwd):
        auth_url = f"{base_url}/auth/v1/token?grant_type=password"
        headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
        payload = {"email": email, "password": pwd}

        try:
            # ★ 使用全局 client 发起请求
            resp = _http_client.post(auth_url, json=payload, headers=headers)
        except Exception as e:
            self._show_error(f"网络连接失败：{e}")
            return

        if resp.status_code != 200:
            try:
                err_data = resp.json()
            except Exception:
                err_data = {}

            code = (err_data.get("error_code") or "").lower()
            msg = (err_data.get("error_description")
                   or err_data.get("msg")
                   or err_data.get("message")
                   or f"HTTP {resp.status_code}")

            if code == "invalid_credentials" or "Invalid login credentials" in msg:
                exists = self._probe_email_exists(base_url, email)

                if exists is True:
                    self._set_input_error(self.pwd_input, True)
                    self.tip_label.setMinimumHeight(64)
                    self.tip_label.setText(
                        '该邮箱已注册，但<b>密码不正确</b>。<br>'
                        '· <a href="reset" style="color:#10B981;">重置密码</a><br>'
                        '· 或检查大小写、输入法空格后重试'
                    )
                elif exists is False:
                    self._set_input_error(self.email_input, True)
                    self.tip_label.setMinimumHeight(48)
                    self.tip_label.setText(
                        '该邮箱<b>尚未注册</b>。<br>'
                        '<a href="register" style="color:#10B981;">→ 立即注册</a>'
                    )
                else:
                    self._set_input_error(self.email_input, True)
                    self._set_input_error(self.pwd_input, True)
                    self.tip_label.setMinimumHeight(64)
                    self.tip_label.setText(
                        '邮箱或密码错误。<br>'
                        '· 还没注册？<a href="register" style="color:#10B981;">立即注册</a><br>'
                        '· 忘记密码？<a href="reset" style="color:#10B981;">重置密码</a>'
                    )
                return

            if code == "email_not_confirmed" or "Email not confirmed" in msg:
                self._set_input_error(self.email_input, True)
                self.tip_label.setMinimumHeight(48)
                self.tip_label.setText(
                    '账号存在，但邮箱还没验证。<br>'
                    '请查收验证邮件；没收到？'
                    '<a href="resend_verify" style="color:#10B981;">重新发送</a>'
                )
                return

            if code == "user_banned" or "banned" in msg.lower():
                self._show_error("账号已被停用，请联系管理员")
                return
            if resp.status_code == 429 or "rate" in code:
                self._show_error("操作过于频繁，请稍后再试")
                return
            if resp.status_code >= 500:
                self._show_error(f"服务端异常 (HTTP {resp.status_code})，请稍后重试")
                return

            self._show_error(f"登录失败：{msg}")
            return

        try:
            auth_data = resp.json()
        except Exception:
            self._show_error("登录失败：响应解析异常")
            return

        access_token = auth_data.get("access_token")
        refresh_token = auth_data.get("refresh_token")
        if not access_token:
            self._show_error("登录失败：未获取到凭证")
            return

        device_id = get_machine_id()
        func_url = f"{base_url}/functions/v1/verify-license"
        func_headers = {
            "Authorization": f"Bearer {access_token}",
            "apikey": SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
        }

        # ★ 分阶段更新 UI 提示，缓解用户等待焦虑
        self._set_loading(True, step_text="校验设备授权...")

        try:
            # ★ 使用全局 client 发起请求，注意这里配置了更长的 timeout
            resp_func = _http_client.post(func_url, json={"device_id": device_id},
                                          headers=func_headers, timeout=30.0)
        except Exception as e:
            self._show_error(f"授权校验网络异常：{e}")
            return

        if resp_func.status_code != 200:
            self._show_error(f"授权校验请求失败 (HTTP {resp_func.status_code})")
            return

        try:
            result = resp_func.json()
        except Exception:
            self._show_error("授权校验响应解析异常")
            return

        if not result.get("ok"):
            reason = result.get("reason", "")
            if reason == "device_limit_reached":
                max_dev = result.get("max", 1)
                reply = QMessageBox.question(
                    self, "设备达到上限",
                    f"当前账号最多绑 {max_dev} 台设备。\n"
                    f"是否解绑【最早登录的旧设备】以继续？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._do_reset_device(base_url, func_headers)
                return

            msg_map = {
                "unauthorized": "登录态无效",
                "no_license": "尚未授权，请联系管理员",
                "inactive": "账号已被停用，请联系管理员",
            }
            self._show_error(msg_map.get(reason, f"校验未通过（{reason}）"))
            return

        expires_at = result.get("expires_at")
        user_data = auth_data.get("user", {}) or {}
        user_id = user_data.get("id", "")

        metadata = user_data.get("user_metadata", {}) or {}
        default_nickname = f"用户_{user_id[:8]}" if user_id else "未知用户"
        nickname = metadata.get("nickname") or default_nickname

        # 1. 保存身份信息并生成路径 (带错误提示)
        if not self._save_auth_info(email, nickname, user_id, refresh_token, expires_at):
            self._show_error("登录成功，但本地凭证保存失败！请检查磁盘权限。")
            return

        # 2. 设置当前用户，并初始化该用户的数据库（建表）
        try:
            from db_config import set_current_user, init_db
            set_current_user(user_id)
            init_db()

            from license_manager import license_mgr
            license_mgr.refresh_status()
        except Exception as e:
            self._show_error(f"登录成功，但本地初始化异常：{e}")
            return

        if license_mgr.is_expired:
            QMessageBox.warning(
                self, "授权已过期",
                "登录成功，但您的授权已过期。\n\n"
                "您可以进入软件查看历史数据，但无法使用自动投诉、导出维权书等高级功能。\n"
                "如需继续使用，请联系管理员续费。"
            )

        self.accept()

    def _probe_email_exists(self, base_url, email):
        now = time.time()
        # ★ 改用了类级别的 _probe_window_start 和 _probe_count
        if now - self._probe_window_start > 60:
            self.__class__._probe_window_start = now
            self.__class__._probe_count = 0
        self.__class__._probe_count += 1

        if self.__class__._probe_count > 5:
            return None

        try:
            # ★ 使用全局 client
            r = _http_client.post(
                f"{base_url}/rest/v1/rpc/email_exists",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                    "Content-Type": "application/json",
                },
                json={"p_email": email},
                timeout=8.0,
            )
            if r.status_code == 200:
                return bool(r.json())
            print(f"[probe] email_exists 返回 {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"[probe] email_exists 异常: {e}")
            return None

    def _do_reset_device(self, base_url, func_headers):
        reset_url = f"{base_url}/functions/v1/reset-devices"
        try:
            reset_resp = _http_client.post(reset_url, headers=func_headers, timeout=30.0)
        except Exception as e:
            self._show_error(f"解绑网络异常：{e}")
            return

        try:
            r_json = reset_resp.json()
        except Exception:
            r_json = {}

        if reset_resp.status_code == 200 and r_json.get("ok"):
            self._show_error("已解绑最早设备！请再次点击“登录”。")
        elif r_json.get("reason") == "cooldown":
            self._show_error(f"解绑失败：冷却中，还需等待 {r_json.get('days_left')} 天。")
        else:
            self._show_error(f"解绑失败：{r_json}")

    def _save_auth_info(self, email, nickname, user_id, refresh_token, expires_at) -> bool:
        """把凭证保存在该用户自己的目录下，并根据勾选决定是否记录自动登录 Session。返回是否成功"""
        try:
            user_dir = get_user_dir(user_id)
            auth_file = os.path.join(user_dir, FILE_AUTH)

            data = {
                "email": email,
                "nickname": nickname,
                "user_id": user_id,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
            }
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if self.remember_cb.isChecked():
                session_data = {
                    "user_id": user_id,
                    "email": email
                }
                with open(get_session_path(), "w", encoding="utf-8") as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)
            else:
                if os.path.exists(get_session_path()):
                    os.remove(get_session_path())
            return True

        except Exception as e:
            print(f"[Login] 保存凭证失败: {e}")
            return False

    def _set_loading(self, loading: bool, step_text: str = None):
        """★ 支持多阶段状态文字"""
        self.main_btn.setEnabled(not loading)
        if loading:
            self.main_btn.setText(step_text or "处理中...")
        else:
            self.main_btn.setText("注 册" if self.is_register_mode else "登 录")

        self.email_input.setEnabled(not loading)
        self.pwd_input.setEnabled(not loading)
        QApplication.processEvents()

    def _show_error(self, msg: str):
        self.tip_label.setMinimumHeight(32)
        self.tip_label.setText(msg)