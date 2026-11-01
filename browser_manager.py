# browser_manager.py
import os
import time
import threading
import atexit
import random
from playwright.sync_api import sync_playwright

from app_paths import get_user_dir, DIR_BROWSER_PROFILE
from db_config import get_current_user

from app_signals import signals
from browser_thread import BrowserThread


# ★ 导入 plugin_bridge 提供的启动器（注意避免循环依赖，尽量在函数内 import 也可以）
# from plugin_bridge import ensure_ready

class BrowserManager:
    _instance = None
    _init_lock = threading.Lock()

    @classmethod
    def instance(cls):
        # 如果实例不存在，或者 BrowserThread 已死（被 shutdown 过），则重建
        if cls._instance is None or not cls._instance._bt.is_alive():
            with cls._init_lock:
                if cls._instance is None or not cls._instance._bt.is_alive():
                    user_id = get_current_user()
                    if not user_id:
                        raise Exception("未登录")
                    # 这里的路径仅作记录，实际启动由 plugin_bridge 负责，但保持路径一致性
                    profile_dir = os.path.join(get_user_dir(user_id), DIR_BROWSER_PROFILE)
                    cls._instance = cls(profile_dir)
                    atexit.register(cls._instance.shutdown)
        return cls._instance

    def __init__(self, profile_dir):
        self.profile_dir = profile_dir

        self._bt = BrowserThread()
        self._bt.start()

        self._pw = None
        self._browser = None
        self._context = None

        self._shutdown_lock = threading.Lock()

        self.preview_page = None
        self.is_shutting_down = False
        self._picker_injected = False

        self.batch_urls = []
        self.batch_index = 0
        self.batch_ctx = {}
        self._batch_ctx_list = []
        self.window_bounds = None

        self._pull_pending = False
        self._pull_lock = threading.Lock()

        # 暂存区（暂存拾取结果，不直接落库）
        self._pending_picks = []
        self._pending_lock = threading.Lock()

        self._current_ctx = None

    def run_in_browser_thread(self, fn, *args, block=True, timeout=None, **kwargs):
        return self._bt.submit(fn, *args, block=block, timeout=timeout, **kwargs)

    def ensure_started(self, minimized=False):
        try:
            self._bt.submit(self._ensure_started_impl, minimized)
        except Exception as e:
            print(f"[BrowserManager] ensure_started 失败: {e}")

    def new_page(self, url=None, force_new=False):
        return self._bt.submit(self._new_page_impl, url, force_new)

    def get_work_page(self, force_new=False, prefer_about_blank=True):
        return self._bt.submit(self._get_work_page_impl, force_new, prefer_about_blank)

    def push_context(self, page, ctx):
        try:
            self._bt.submit(self._push_context_impl, page, ctx)
        except Exception as e:
            print(f"[BrowserManager] push_context 失败: {e}")

    def ensure_injected(self, page):
        try:
            self._bt.submit(self._ensure_injected_impl, page)
        except Exception:
            pass

    def pull_all_queues(self):
        with self._pull_lock:
            if self._pull_pending:
                return
            self._pull_pending = True

        def _job():
            try:
                self._pull_all_queues_impl()
            finally:
                with self._pull_lock:
                    self._pull_pending = False

        try:
            self._bt.submit(_job, block=False)
        except Exception as e:
            with self._pull_lock:
                self._pull_pending = False
            print(f"[BrowserManager] pull_all_queues 失败: {e}")

    def start_batch_preview(self, urls, ctx=None, ctx_list=None, window_bounds=None):
        try:
            self._bt.submit(
                self._start_batch_preview_impl,
                urls, ctx, ctx_list, window_bounds,
                block=False,
            )
        except Exception as e:
            print(f"[BrowserManager] start_batch_preview 失败: {e}")

    def navigate_preview(self, direction):
        try:
            self._bt.submit(self._navigate_preview_impl, direction, block=False)
        except Exception as e:
            print(f"[BrowserManager] navigate_preview 失败: {e}")

    def resolve_short_url(self, url):
        return self._bt.submit(self._resolve_short_url_impl, url)

    # ===== 暂存区管理 API =====
    def get_pending_count(self):
        with self._pending_lock:
            return len(self._pending_picks)

    def take_pending_picks(self):
        with self._pending_lock:
            picks = list(self._pending_picks)
            self._pending_picks.clear()
        return picks

    def clear_pending_picks(self):
        with self._pending_lock:
            self._pending_picks.clear()
        signals.pending_count_changed.emit(0)

    def shutdown(self, force=False):
        with self._shutdown_lock:
            if self.is_shutting_down:
                return
            self.is_shutting_down = True

        try:
            if self._bt.is_alive():
                # ★ 只断开 Playwright 的连接，不杀浏览器进程（留给 plugin_bridge 管）
                self._bt.submit(self._shutdown_impl, block=True, timeout=20)
        except Exception as e:
            print(f"[BrowserManager] shutdown 投递失败: {e}")
        finally:
            try:
                self._bt.stop()
            except Exception:
                pass
            self.is_shutting_down = False

    # ================= 核心接管逻辑 =================

    def _ensure_started_impl(self, minimized=False):
        if self._browser and self._browser.is_connected():
            return

        try:
            from plugin_bridge import ensure_ready, restart_extension_browser
            if not ensure_ready(business_name="投诉接管", timeout=8.0):
                raise RuntimeError("无法通过 plugin_bridge 启动专用浏览器")
        except ImportError:
            raise RuntimeError("未找到 plugin_bridge 模块")

        print("🔗 [BrowserManager] 正在通过 CDP 接管浏览器...")
        if not self._pw:
            self._pw = sync_playwright().start()

        try:
            self._browser = self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            self._context = self._browser.contexts[0]

            if not self._picker_injected:
                self._context.add_init_script(self._get_stealth_js())
                # self._context.add_init_script(get_picker_script())
                self._picker_injected = True

            self._context.on("page", self._on_new_page)
            print("✅ [BrowserManager] 成功接管插件浏览器！")
        except Exception as e:
            print(f"❌ [BrowserManager] CDP 接管失败，尝试强制重启浏览器... ({e})")
            # 说明连不上 9222，可能是一个没开端口的旧进程霸占了。呼叫 plugin_bridge 重启！
            from plugin_bridge import restart_extension_browser
            restart_extension_browser(business_name="投诉接管重试")

            try:
                self._browser = self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
                self._context = self._browser.contexts[0]
                if not self._picker_injected:
                    self._context.add_init_script(self._get_stealth_js())
                    self._context.add_init_script(get_picker_script())
                    self._picker_injected = True
                self._context.on("page", self._on_new_page)
                print("✅ [BrowserManager] 重启后成功接管浏览器！")
            except Exception as retry_e:
                print(f"❌ [BrowserManager] 重启后仍然接管失败: {retry_e}")
                self._pw.stop()
                self._pw = None
                raise

    def _on_new_page(self, new_page):
        try:
            def _on_load():
                self._ensure_injected_impl(new_page)
                opener_info = {}
                try:
                    opener_page = new_page.opener()
                    if opener_page:
                        opener_info = {"url": opener_page.url, "title": opener_page.title()}
                except Exception:
                    pass

                if self._current_ctx:
                    ctx = dict(self._current_ctx)
                    if opener_info:
                        ctx["_opener_url"] = opener_info["url"]
                        ctx["_opener_title"] = opener_info["title"]
                    self._push_context_impl(new_page, ctx)

            new_page.on("load", _on_load)
        except Exception:
            pass

    def _ensure_injected_impl(self, page):
        try:
            if page.is_closed() or not page.url.startswith("http"):
                return
            # exists = page.evaluate("() => !!document.getElementById('__apt_picker_host__')")
            # if not exists:
                # page.evaluate(get_picker_script())
        except Exception:
            pass

    def _safe_new_page(self):
        try:
            return self._context.new_page()
        except Exception as e:
            err_msg = str(e)
            if ("Target.createTarget" in err_msg
                    or "Target closed" in err_msg
                    or "Connection closed" in err_msg):
                print(f"[BrowserManager] 浏览器连接已断开，正在尝试重连... ({err_msg})")
                try:
                    if self._pw:
                        self._pw.stop()
                except Exception:
                    pass
                self._browser = None
                self._context = None
                self._pw = None
                self._picker_injected = False
                # 重新接管
                self._ensure_started_impl(minimized=False)
                return self._context.new_page()
            raise

    def _new_page_impl(self, url=None, force_new=False):
        self._ensure_started_impl(minimized=False)
        page = None

        if not force_new:
            for p in self._context.pages:
                try:
                    if p.url == "about:blank":
                        page = p
                        break
                except Exception:
                    pass

        if page is None:
            page = self._safe_new_page()

        self._force_activate(page)
        if url:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                print(f"页面加载超时: {e}")
        self._ensure_injected_impl(page)
        return page

    def _get_work_page_impl(self, force_new=False, prefer_about_blank=True):
        self._ensure_started_impl(minimized=False)

        if force_new:
            return self._safe_new_page()

        try:
            pages = [p for p in self._context.pages if not p.is_closed()]
        except Exception:
            pages = []

        if prefer_about_blank:
            for p in pages:
                try:
                    if p.url == "about:blank":
                        return p
                except Exception:
                    pass

        for p in pages:
            try:
                if p.url not in ("", "about:blank"):
                    return p
            except Exception:
                pass

        return self._safe_new_page()

    def _force_activate(self, page):
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            cdp = self._context.new_cdp_session(page)
            try:
                cdp.send("Page.bringToFront")
            finally:
                cdp.detach()
        except Exception:
            pass
        try:
            page.evaluate("window.focus()")
        except Exception:
            pass

    def _get_stealth_js(self):
        return """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin' },
                    { name: 'Chrome PDF Viewer' },
                    { name: 'Native Client' }
                ]
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) UHD Graphics 620';
                return getParameter.apply(this, arguments);
            };
        """

    def _pull_all_queues_impl(self):
        if not self._context:
            return

        finish_requested = False
        save_batch_requested = False
        appended = 0

        for page in list(self._context.pages):
            try:
                if page.is_closed():
                    continue
                items = page.evaluate("""() => {
                    if (!window.__aptSaveQueue || window.__aptSaveQueue.length === 0) return [];
                    const q = window.__aptSaveQueue; window.__aptSaveQueue = []; return q;
                }""")
                if not items:
                    continue

                for payload in items:
                    action = payload.get("action", "")

                    if action in ("finish_analyze", "close_browser"):
                        finish_requested = True
                        continue
                    elif action == "save_batch":
                        save_batch_requested = True
                        continue
                    elif action == "preview_nav":
                        self._navigate_preview_impl(payload.get("url", ""))
                        continue

                    ctx = payload.get("ctx", {}) or {}
                    is_manual = (ctx.get("pick_origin") == "手动获取")

                    with self._pending_lock:
                        self._pending_picks.append({
                            "url": payload.get("url", ""),
                            "title": payload.get("title", ""),
                            "body": payload.get("body", ""),
                            "source_site": payload.get("source_site", ""),
                            "ctx": ctx,
                            "parent_url": payload.get("parent_url", ""),
                            "parent_title": payload.get("parent_title", ""),
                            "is_manual": is_manual,
                        })
                    appended += 1
            except Exception:
                pass

        if appended > 0:
            total = self.get_pending_count()
            signals.pending_count_changed.emit(total)
            for page in list(self._context.pages):
                try:
                    if not page.is_closed():
                        page.evaluate("(n) => { if (window.__aptUpdateSavedCount) window.__aptUpdateSavedCount(n); }",
                                      total)
                except Exception:
                    pass

        if save_batch_requested:
            signals.save_batch_requested.emit()

        if finish_requested:
            signals.manual_pick_finished.emit()

    def _push_context_impl(self, page, ctx):
        try:
            # exists = page.evaluate("() => !!document.getElementById('__apt_picker_host__')")
            # if not exists:
                # page.evaluate(get_picker_script())
            page.evaluate("(c) => { if (window.__aptUpdateCtx) window.__aptUpdateCtx(c); }", ctx)
            page.evaluate("(n) => { if (window.__aptUpdateSavedCount) window.__aptUpdateSavedCount(n); }",
                          self.get_pending_count())
        except Exception:
            pass

    def _start_batch_preview_impl(self, urls, ctx=None, ctx_list=None, window_bounds=None):
        if not urls:
            return
        self.batch_urls = urls
        self.batch_index = 0
        self.batch_ctx = ctx or {}
        self._batch_ctx_list = ctx_list or []
        self.window_bounds = window_bounds
        self._load_preview_url_impl()

    def _load_preview_url_impl(self):
        if not self.batch_urls or self.batch_index < 0 or self.batch_index >= len(self.batch_urls):
            return

        self._ensure_started_impl(minimized=False)

        if self.preview_page is None or self.preview_page.is_closed():
            page = None
            for p in self._context.pages:
                try:
                    if p.url == "about:blank":
                        page = p
                        break
                except Exception:
                    pass
            if page is None:
                page = self._safe_new_page()
            self.preview_page = page
            self.preview_page.on("load", lambda: self._ensure_injected_impl(self.preview_page))

        self._force_activate(self.preview_page)

        if getattr(self, "window_bounds", None):
            try:
                cdp = self._context.new_cdp_session(self.preview_page)
                window_info = cdp.send("Browser.getWindowForTarget")
                window_id = window_info["windowId"]

                cdp.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {"windowState": "normal"},
                })

                cdp.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {
                        "left": self.window_bounds["left"],
                        "top": self.window_bounds["top"],
                        "width": self.window_bounds["width"],
                        "height": self.window_bounds["height"],
                    },
                })
                cdp.detach()
            except Exception as e:
                print(f"调整浏览器窗口失败: {e}")
            finally:
                self.window_bounds = None

        url = self.batch_urls[self.batch_index]

        base_ctx = dict(self.batch_ctx)
        if self._batch_ctx_list and self.batch_index < len(self._batch_ctx_list):
            per = self._batch_ctx_list[self.batch_index] or {}
            base_ctx.update(per)

        ctx_with_nav = dict(base_ctx)
        ctx_with_nav.update({
            "batch_total": len(self.batch_urls),
            "batch_index": self.batch_index + 1,
        })

        self._current_ctx = dict(ctx_with_nav)

        try:
            try:
                self.preview_page.evaluate(
                    "sessionStorage.removeItem('__aptCtx'); sessionStorage.removeItem('__aptPickingMode');")
            except Exception:
                pass

            self.preview_page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._ensure_injected_impl(self.preview_page)
            self._push_context_impl(self.preview_page, ctx_with_nav)
        except Exception as e:
            print(f"预览加载失败: {e}")

    def _navigate_preview_impl(self, direction):
        if not self.batch_urls:
            return
        if direction == "next" and self.batch_index < len(self.batch_urls) - 1:
            self.batch_index += 1
            self._load_preview_url_impl()
        elif direction == "prev" and self.batch_index > 0:
            self.batch_index -= 1
            self._load_preview_url_impl()

    def _resolve_short_url_impl(self, url):
        self._ensure_started_impl(minimized=False)
        page = self._safe_new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=8000)
            except Exception as nav_err:
                if ("interrupted by another navigation" not in str(nav_err)
                        and "ERR_ABORTED" not in str(nav_err)):
                    raise
            try:
                page.mouse.wheel(0, random.randint(200, 500))
                page.wait_for_timeout(700)
            except Exception:
                pass
            return page.url
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _shutdown_impl(self):
        """★ 核心改造：只断开 Playwright 的 CDP 连接，绝对不杀浏览器"""
        try:
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
        finally:
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass

            self._browser = None
            self._context = None
            self._pw = None
            self.preview_page = None
            self.batch_urls = []
            self._batch_ctx_list = []
            self._picker_injected = False
            self._current_ctx = None
            print("🔌 [BrowserManager] 已断开 CDP 连接，浏览器进程予以保留。")