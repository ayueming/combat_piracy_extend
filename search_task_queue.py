# search_task_queue.py
import json
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QMessageBox
from db_config import get_conn
from ws_server import current_context, dispatch_search_task, ws_signals
from plugin_bridge import bridge_signals


class QueueSignals(QObject):
    queue_updated = Signal()
    task_state_changed = Signal(int, str)
    batch_switched = Signal(str, str)


queue_signals = QueueSignals()


class SearchTaskQueue(QObject):
    def __init__(self):
        super().__init__()
        self.is_running = False
        self._current_task_id = None
        self._running_tasks = []

        self._session_batch_id = None
        self._ui_notified_batch = None

        # 兜底任务超时定时器（5分钟）
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_task_timeout)

        # ★ 断联保护定时器（5秒重连宽限）
        self.disconnect_timer = QTimer(self)
        self.disconnect_timer.setSingleShot(True)
        self.disconnect_timer.timeout.connect(self._force_abort_on_disconnect)

        ws_signals.search_finished.connect(self._on_search_finished)

        # 监听插件连接状态
        bridge_signals.plugin_disconnected.connect(self._on_plugin_disconnected)
        bridge_signals.plugin_connected.connect(self._on_plugin_connected)

    def _cleanup_orphans(self):
        """清理因为软件异常关闭而卡在 running 状态的任务"""
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM search_tasks WHERE status = 'running'")
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"[Queue] 发现 {count} 个上次残留的 running 任务，正在重置为 failed")
                conn.execute("UPDATE search_tasks SET status = 'failed' WHERE status = 'running'")
                conn.commit()
        finally:
            conn.close()

    def _on_plugin_disconnected(self):
        """当浏览器被关闭或插件断开时触发"""
        if self.is_running:
            print("[Queue] ⚠️ 检测到插件连接断开！等待 5 秒重连宽限期...")
            self.disconnect_timer.start(5000)  # 给 5 秒容错

    def _on_plugin_connected(self):
        """插件重连成功"""
        if self.disconnect_timer.isActive():
            print("[Queue] ✅ 插件已重新连接，取消强制中断")
            self.disconnect_timer.stop()

    def _force_abort_on_disconnect(self):
        """断联超时，强制终止队列"""
        if not self.is_running:
            return
        print("[Queue] ❌ 插件断联超时，强制清空当前队列！")

        self.is_running = False
        self._running_tasks.clear()

        if self.timeout_timer.isActive():
            self.timeout_timer.stop()

        if self._current_task_id:
            self._set_status(self._current_task_id, 'failed')
            self._current_task_id = None

        # 清空当前上下文中的批次，防止后续脏数据关联
        current_context["batch_id"] = ""

        self._session_batch_id = None
        self._ui_notified_batch = None

        queue_signals.queue_updated.emit()

        QMessageBox.warning(None, "任务中断",
                            "浏览器或插件连接已断开超过 5 秒，当前搜索队列已被强制清空。\n\n请确保插件已连接，重新点击执行即可。")

    def get_tasks(self):
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT id, book_id, book_name, platform, main_keyword, sub_keywords, max_pages, status, last_batch_id FROM search_tasks ORDER BY id ASC").fetchall()
            return [{
                "id": r[0], "book_id": r[1], "book_name": r[2], "platform": r[3],
                "main_keyword": r[4], "sub_keywords": json.loads(r[5]) if r[5] else [],
                "max_pages": r[6], "status": r[7], "last_batch_id": r[8]
            } for r in rows]
        finally:
            conn.close()

    def add_task(self, book_id, book_name, platform, main_keyword, sub_keywords, max_pages):
        existing_tasks = self.get_tasks()
        for t in existing_tasks:
            if (t["book_id"] == book_id and
                    t["platform"] == platform and
                    t["main_keyword"] == main_keyword and
                    sorted(t["sub_keywords"]) == sorted(sub_keywords)):
                return False

        conn = get_conn()
        try:
            sub_kws_json = json.dumps(sorted(sub_keywords), ensure_ascii=False)
            conn.execute(
                "INSERT INTO search_tasks (book_id, book_name, platform, main_keyword, sub_keywords, max_pages, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (book_id, book_name, platform, main_keyword, sub_kws_json, max_pages, 'ready',
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            queue_signals.queue_updated.emit()
            return True
        finally:
            conn.close()

    def remove_task(self, task_id):
        if self.is_running and self._current_task_id == task_id:
            return False

        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM search_tasks WHERE id = ?", (task_id,))
            conn.commit()
            queue_signals.queue_updated.emit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def start_all(self):
        if self.is_running: return
        tasks = self.get_tasks()
        if not tasks: return

        conn = get_conn()
        try:
            conn.execute("UPDATE search_tasks SET status = 'ready' WHERE status = 'failed'")
            conn.commit()
        finally:
            conn.close()

        self._session_batch_id = f"QUEUE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._ui_notified_batch = None  # 重置通知状态

        self._running_tasks = [t["id"] for t in tasks]
        self.is_running = True
        self._execute_next()

    def start_one(self, task_id):
        if self.is_running: return

        self._session_batch_id = f"SINGLE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._ui_notified_batch = None  # 重置通知状态

        self._running_tasks = [task_id]
        self.is_running = True
        self._execute_next()

    def stop(self):
        self.is_running = False
        self._running_tasks.clear()
        if self.timeout_timer.isActive():
            self.timeout_timer.stop()
        if self._current_task_id:
            self._set_status(self._current_task_id, 'ready')
            self._current_task_id = None

        self._session_batch_id = None
        self._ui_notified_batch = None

        queue_signals.queue_updated.emit()

    def _execute_next(self):
        if not self.is_running or not self._running_tasks:
            self.is_running = False
            queue_signals.queue_updated.emit()
            return

        self._current_task_id = self._running_tasks.pop(0)
        task = self._get_task_data(self._current_task_id)
        if not task:
            self._execute_next()
            return

        self._set_status(task["id"], 'running')
        queue_signals.queue_updated.emit()

        # ★ 使用外部的会话大 Batch
        batch_id = self._session_batch_id

        current_context.update({
            "book_name": task["book_name"],
            "keyword": task["main_keyword"],
            "batch_id": batch_id
        })

        # ★ 核心：只有当当前的会话 batch 和已经通知过 UI 的不一样时，才切换 UI
        if self._ui_notified_batch != batch_id:
            queue_signals.batch_switched.emit(batch_id, task["book_name"])
            self._ui_notified_batch = batch_id

        res = dispatch_search_task(task["platform"], task["main_keyword"], task["max_pages"], task["sub_keywords"])

        if res in ("success", "opening"):
            self.timeout_timer.start(300000)
        else:
            print(f"[Queue] 任务派发失败，返回状态: {res}")
            self._set_status(task["id"], 'failed')
            self.stop()
            if res == "busy":
                QMessageBox.warning(None, "任务受阻",
                                    "检测到有其他搜索/预览正在运行，队列已暂停。请处理完后重新点击执行。")
            else:
                QMessageBox.warning(None, "任务异常", f"任务派发失败，状态返回: {res}")

    def _on_search_finished(self, batch_id):
        if not self.is_running or not self._current_task_id:
            return

        self.timeout_timer.stop()
        self._update_batch_id(self._current_task_id, batch_id)
        self._set_status(self._current_task_id, 'ready')
        self._current_task_id = None

        QTimer.singleShot(1000, self._execute_next)

    def _on_task_timeout(self):
        if self._current_task_id:
            print(f"⚠️ 队列任务 {self._current_task_id} 超时未完成，跳过。")
            self._set_status(self._current_task_id, 'failed')
            self._current_task_id = None
            self._execute_next()

    def _get_task_data(self, task_id):
        conn = get_conn()
        try:
            r = conn.execute(
                "SELECT id, book_id, book_name, platform, main_keyword, sub_keywords, max_pages FROM search_tasks WHERE id = ?",
                (task_id,)).fetchone()
            if r:
                return {"id": r[0], "book_id": r[1], "book_name": r[2], "platform": r[3], "main_keyword": r[4],
                        "sub_keywords": json.loads(r[5]) if r[5] else [], "max_pages": r[6]}
            return None
        finally:
            conn.close()

    def _set_status(self, task_id, status):
        conn = get_conn()
        try:
            conn.execute("UPDATE search_tasks SET status = ?, last_run_at = ? WHERE id = ?",
                         (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id))
            conn.commit()
            queue_signals.task_state_changed.emit(task_id, status)
        finally:
            conn.close()

    def _update_batch_id(self, task_id, batch_id):
        conn = get_conn()
        try:
            conn.execute("UPDATE search_tasks SET last_batch_id = ? WHERE id = ?", (batch_id, task_id))
            conn.commit()
        finally:
            conn.close()

    def init_cleanup(self):
        """供外部在数据库初始化完成后调用，清理残留任务"""
        self._cleanup_orphans()


task_queue = SearchTaskQueue()