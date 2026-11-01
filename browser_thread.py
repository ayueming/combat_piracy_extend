# browser_thread.py
"""
常驻浏览器线程：所有 Playwright 同步对象都锁定在这个线程里。

外部只能通过 submit(fn, *args, **kwargs) 投递任务，
任务内部对 bm.new_page / bm.push_context 等的调用会因重入判断直接执行，
不会造成跨线程死锁，也不会触发 "Sync API is not thread-safe"。
"""
import queue
import threading
import traceback


class BrowserThread:
    def __init__(self):
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="BrowserThread", daemon=True)
        self._tid = None
        self._started = False
        self._stopped = False

    def start(self):
        if self._started:
            return
        self._thread.start()
        self._started = True

    def is_alive(self):
        return self._thread.is_alive() and not self._stopped

    def _loop(self):
        self._tid = threading.get_ident()
        while True:
            item = self._q.get()
            if item is None:  # 哨兵
                break
            fn, args, kwargs, box = item
            try:
                box["result"] = fn(*args, **kwargs)
                box["ok"] = True
            except BaseException as e:
                box["error"] = e
                box["traceback"] = traceback.format_exc()
                box["ok"] = False
            finally:
                box["event"].set()
        self._stopped = True

    def submit(self, fn, *args, block=True, timeout=None, **kwargs):
        if not self._started:
            raise RuntimeError("BrowserThread 尚未启动")
        # 重入：就在浏览器线程里，直接执行
        if threading.get_ident() == self._tid:
            return fn(*args, **kwargs)
        if self._stopped:
            raise RuntimeError("BrowserThread 已退出")

        box = {"event": threading.Event()}
        self._q.put((fn, args, kwargs, box))
        if not block:
            return None
        if not box["event"].wait(timeout):
            raise TimeoutError("BrowserThread 任务超时")
        if not box["ok"]:
            raise box["error"]
        return box["result"]

    def stop(self):
        if not self._started or self._stopped:
            return
        try:
            self._q.put(None)
        except Exception:
            pass
        self._thread.join(timeout=5)