# plugin_bridge.py
import asyncio
import json
import threading
import subprocess
import os
import shutil
import psutil
import socket

try:
    import winreg
    import win32gui
    import win32process
    import win32con
except ImportError:
    winreg = None

from PySide6.QtCore import QObject, Signal


class PluginBridgeSignals(QObject):
    plugin_timeout = Signal(str)
    plugin_connected = Signal()
    plugin_disconnected = Signal()


bridge_signals = PluginBridgeSignals()


class PluginBridge:
    def __init__(self):
        self._ws = None
        self._loop = None
        self._connected_event = threading.Event()
        self._lock = threading.Lock()

    def set_websocket(self, ws):
        with self._lock:
            self._ws = ws
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            self._connected_event.set()
        print("🔌 插件连接已建立")
        bridge_signals.plugin_connected.emit()

    def clear_websocket(self):
        with self._lock:
            self._ws = None
            self._loop = None
            self._connected_event.clear()
        print("🔌 插件连接已断开")
        bridge_signals.plugin_disconnected.emit()

    def is_connected(self):
        with self._lock:
            return self._ws is not None

    def wait_connected(self, timeout=8.0):
        return self._connected_event.wait(timeout)

    def send_sync(self, payload):
        with self._lock:
            ws = self._ws
            loop = self._loop
        if not ws or not loop:
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send(json.dumps(payload)), loop
            )
            return True
        except Exception as e:
            print(f"[Bridge] 发送失败: {e}")
            return False


bridge = PluginBridge()

# ===================== 专用浏览器管理 =====================
EXTENSION_DEV_MODE = True

# 记录当前进程使用的 user_id，供比对兜底
_browser_proc = None
_browser_proc_user_id = None
_browser_lock = threading.Lock()
_ready_lock = threading.Lock()  # 防并发死锁


# 从 exe 路径推导浏览器身份标识，用于按品牌隔离 profile
def _browser_identity(exe_path):
    low = exe_path.lower()
    name = os.path.basename(low)
    if "playwright" in low:
        return "chromium"
    if "msedge" in name:
        return "edge"
    if "chromium" in name:
        return "chromium"
    if "chrome" in name:
        return "chrome"
    import hashlib
    return "custom_" + hashlib.md5(low.encode()).hexdigest()[:8]


# 按 user_id + 浏览器品牌隔离的 profile 目录
def _get_extension_profile_dir(user_id, exe_path):
    from app_paths import get_user_dir
    if not user_id:
        raise RuntimeError("未登录，拒绝启动专用浏览器")
    ident = _browser_identity(exe_path)
    d = os.path.join(get_user_dir(user_id), f"extension_profile_{ident}")
    os.makedirs(d, exist_ok=True)
    return d


# ★ 核心新增：暴力强杀所有使用该 profile 目录的浏览器进程
def _force_kill_browser_by_profile(profile_dir):
    """无视 _browser_proc 变量，直接物理超度所有残留的旧浏览器进程"""
    if not profile_dir or not os.path.exists(profile_dir):
        return
    target_profile = profile_dir.lower()
    killed = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = proc.info.get('name', '').lower()
            if 'msedge' in name or 'chrome' in name:
                cmdline = proc.info.get('cmdline')
                if cmdline and target_profile in " ".join(cmdline).lower():
                    proc.kill()
                    killed = True
        except Exception:
            pass
    if killed:
        print("[Bridge] 发现残留的旧浏览器进程，已强制物理超度！")
        import time
        time.sleep(0.5)  # 等待系统释放文件和锁


# 清理 Chrome/Edge 异常退出后残留的锁文件
def _cleanup_lock_files(profile_dir):
    from app_paths import BROWSER_LOCK_FILES
    for fname in BROWSER_LOCK_FILES:
        p = os.path.join(profile_dir, fname)
        try:
            if os.path.islink(p) or os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _get_wakeup_url():
    plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_extension")
    wakeup_file = os.path.join(plugin_dir, "wakeup.html")
    return f"file:///{wakeup_file.replace(os.sep, '/')}"


# ★ 构建启动命令（包含 9222 端口和跨域允许）
def _build_browser_cmd(exe, wakeup_url, profile_dir):
    cmd = [
        exe,
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",  # 允许 Playwright 接管
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if EXTENSION_DEV_MODE:
        plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_extension")
        cmd.append(f"--load-extension={plugin_dir}")
        cmd.append(f"--disable-extensions-except={plugin_dir}")

    cmd.append(wakeup_url)
    return cmd


def get_browser_path():
    edge_in_path = shutil.which("msedge.exe")
    if edge_in_path: return edge_in_path
    chrome_in_path = shutil.which("chrome.exe")
    if chrome_in_path: return chrome_in_path
    paths = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for p in paths:
        if p and os.path.exists(p): return p
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        path, _ = winreg.QueryValueEx(key, "")
        if os.path.exists(path): return path
    except Exception:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
        path, _ = winreg.QueryValueEx(key, "")
        if os.path.exists(path): return path
    except Exception:
        pass
    return None


def ensure_ready(business_name="业务", timeout=8.0):
    if bridge.is_connected():
        return True

    if not _ready_lock.acquire(blocking=False):
        print(f"[Bridge] 已有线程在等待连接，跳过本次 {business_name} 的等待")
        return bridge.is_connected()

    try:
        from db_config import get_current_user
        user_id = get_current_user()
        if not user_id:
            print(f"❌ [Bridge] 未登录，拒绝为 {business_name} 启动浏览器")
            bridge_signals.plugin_timeout.emit(business_name)
            return False

        exe = get_browser_path()
        if not exe:
            print("❌ 未找到 Edge 或 Chrome，无法启动浏览器")
            bridge_signals.plugin_timeout.emit(business_name)
            return False

        wakeup_url = _get_wakeup_url()
        profile_dir = _get_extension_profile_dir(user_id, exe)

        global _browser_proc, _browser_proc_user_id
        with _browser_lock:
            need_launch = _browser_proc is None or _browser_proc.poll() is not None

            # 1. 检测用户是否切换
            if not need_launch and _browser_proc_user_id != user_id:
                print(f"[Bridge] 检测到用户切换 ({_browser_proc_user_id} -> {user_id})，正在重启浏览器...")
                try:
                    _browser_proc.kill()
                    _browser_proc.wait(timeout=3)
                except Exception:
                    pass
                _browser_proc = None
                _browser_proc_user_id = None
                bridge.clear_websocket()
                need_launch = True

            # 2. 检测当前进程是否开启了 9222 端口
            if not need_launch:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.1)
                if s.connect_ex(("127.0.0.1", 9222)) != 0:
                    print("[Bridge] 检测到现存浏览器未开启调试端口，准备重启以支持 CDP...")
                    _browser_proc = None
                    _browser_proc_user_id = None
                    bridge.clear_websocket()
                    need_launch = True
                s.close()

            if need_launch:
                # ★ 关键核心：强制物理超度所有残留的旧浏览器，确保 9222 参数生效
                _force_kill_browser_by_profile(profile_dir)
                _cleanup_lock_files(profile_dir)

                cmd = _build_browser_cmd(exe, wakeup_url, profile_dir)
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                try:
                    _browser_proc = subprocess.Popen(cmd, creationflags=creationflags)
                    _browser_proc_user_id = user_id
                    print(f"[Bridge] 启动专用浏览器 PID={_browser_proc.pid} profile={profile_dir}")
                except Exception as e:
                    print(f"[Bridge] 启动浏览器失败: {e}")
                    bridge_signals.plugin_timeout.emit(business_name)
                    return False
            else:
                print(f"[Bridge] 专用浏览器已在运行 PID={_browser_proc.pid}，等待扩展连接...")

        print(f"⏳ 等待插件连接（最长 {timeout} 秒）...")
        if bridge.wait_connected(timeout):
            print("✅ 插件已连接")
            return True

        print(f"⚠️ {business_name}：插件 {timeout} 秒内未连接")
        bridge_signals.plugin_timeout.emit(business_name)
        return False
    finally:
        _ready_lock.release()


def restart_extension_browser(business_name="调试重启", timeout=8.0):
    global _browser_proc, _browser_proc_user_id
    with _browser_lock:
        if _browser_proc and _browser_proc.poll() is None:
            try:
                _browser_proc.kill()
                _browser_proc.wait(timeout=5)
            except Exception:
                pass
        _browser_proc = None
        _browser_proc_user_id = None
    bridge.clear_websocket()
    return ensure_ready(business_name=business_name, timeout=timeout)


def shutdown_extension_browser():
    """登出时调用：杀掉专用浏览器并断开 WS，避免串用户"""
    global _browser_proc, _browser_proc_user_id
    with _browser_lock:
        if _browser_proc and _browser_proc.poll() is None:
            try:
                _browser_proc.kill()
                _browser_proc.wait(timeout=3)
            except Exception:
                pass
        _browser_proc = None
        _browser_proc_user_id = None
    bridge.clear_websocket()
    print("🔌 [Bridge] 专用浏览器已强制关闭")


def get_browser_hwnd():
    global _browser_proc
    target_pids = set()
    if _browser_proc and _browser_proc.poll() is None:
        try:
            parent = psutil.Process(_browser_proc.pid)
            target_pids.add(parent.pid)
            for child in parent.children(recursive=True):
                target_pids.add(child.pid)
        except Exception:
            pass

    target_profile = ""
    try:
        if _browser_proc and _browser_proc.args:
            for a in _browser_proc.args:
                if isinstance(a, str) and a.startswith("--user-data-dir="):
                    target_profile = a[len("--user-data-dir="):].lower()
                    break
    except Exception:
        pass

    if target_profile:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = proc.info.get('name', '').lower()
                    if 'msedge' in name or 'chrome' in name:
                        cmdline = proc.info.get('cmdline')
                        if cmdline and target_profile in " ".join(cmdline).lower():
                            target_pids.add(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

    if not target_pids: return None

    found_hwnds = []

    def enum_windows_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            class_name = win32gui.GetClassName(hwnd)
            if "Chrome_WidgetWin" in class_name:
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id in target_pids:
                    rect = win32gui.GetWindowRect(hwnd)
                    if rect[2] - rect[0] > 100 and rect[3] - rect[1] > 100:
                        found_hwnds.append((hwnd, rect))
        return True

    win32gui.EnumWindows(enum_windows_callback, None)
    if found_hwnds:
        found_hwnds.sort(key=lambda x: (x[1][2] - x[1][0]) * (x[1][3] - x[1][1]), reverse=True)
        return found_hwnds[0][0]
    return None