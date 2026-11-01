# complaint_dispatcher.py
import time
from PySide6.QtCore import QObject, Signal

# ★ 引入各平台脚本
from auto_complaint_quark import run_auto_complaint_quark, AutoComplaintSignals
from auto_complaint_uc import run_auto_complaint_uc
from auto_complaint_baidu import run_auto_complaint_baidu
from auto_complaint_xunlei import run_auto_complaint_xunlei

from browser_manager import BrowserManager

# ★ 平台代号常量
from app_data import (
    PLATFORM_BAIDU, PLATFORM_QUARK, PLATFORM_UC, PLATFORM_XUNLEI, PLATFORM_OTHER,
    PLATFORM_EXECUTION_ORDER,
)

PLATFORM_ORDER = {code: idx for idx, code in enumerate(PLATFORM_EXECUTION_ORDER)}

# =========================================================
# ★ 插件路由字典：以后加新平台，只需在这里加一行映射
# =========================================================
PLATFORM_ROUTER = {
    PLATFORM_QUARK: run_auto_complaint_quark,
    PLATFORM_UC: run_auto_complaint_uc,
    PLATFORM_BAIDU: run_auto_complaint_baidu,
    PLATFORM_XUNLEI: run_auto_complaint_xunlei,
}


class ComplaintDispatcher(QObject):
    progress_msg = Signal(str)
    batch_success = Signal(object)
    task_finished = Signal()

    def __init__(self, batches, is_all, target_cat, initial_batch, stop_event, login_event, dialog_signal):
        super().__init__()
        self.batches = batches
        self.is_all = is_all
        self.target_cat = target_cat
        self.initial_batch = initial_batch
        self.stop_event = stop_event
        self.login_event = login_event
        self.dialog_signal = dialog_signal

        self.complaint_signals = AutoComplaintSignals()
        self.complaint_signals.progress.connect(self.progress_msg.emit)

    def _execute_platform(self, batch, is_all_run=False):
        """
        统一执行入口，根据批次中的 platform_code 动态分发到对应的脚本。

        ★ 关键：整段投递到 BrowserThread 执行。
          因为改造后所有 page 都归属 BrowserThread，
          在 dispatcher 线程直接调 run_func 会跨线程操作 Playwright 对象而崩溃。
        """
        if not batch:
            return False

        platform_code = batch[0].get("platform_code", PLATFORM_OTHER)
        run_func = PLATFORM_ROUTER.get(platform_code)

        if not run_func:
            self.progress_msg.emit(f"⚠️ 暂未开通【{self.target_cat}】的自动投诉方式")
            return False

        bm = BrowserManager.instance()
        # 整段投递：run_func 内部所有 page 操作都在 BrowserThread 里执行
        # 内部 bm.new_page() 等调用会因 submit 的重入判断直接原地执行，不会死锁
        return bm.run_in_browser_thread(
            run_func,
            batch,
            signals=self.complaint_signals,
            is_all=is_all_run,
            stop_event=self.stop_event,
            login_event=self.login_event,
            dialog_signal=self.dialog_signal,
            block=True,
            timeout=None,   # 投诉流程可能几十分钟（等扫码），不设超时
        )

    def run(self):
        finished_ok = False
        try:
            if not self.is_all:
                finished_ok = self._run_single()
            else:
                finished_ok = self._run_all()
        except Exception as e:
            # ★ 加上 print，这样报错就能在控制台看到了
            print(f"❌ 自动投诉线程异常: {e}")
            self.progress_msg.emit(f"❌ 自动投诉线程异常: {e}")
            finished_ok = False
        finally:
            # 只有在全部成功且没有被用户强行中断的情况下，才关闭浏览器
            if finished_ok and not self.stop_event.is_set():
                try:
                    BrowserManager.instance().shutdown()
                    print("【调度器】任务全部成功完成，已关闭浏览器进程。")
                except Exception as e:
                    print(f"关闭浏览器失败: {e}")
            else:
                print("【调度器】任务未成功完成或用户中断，浏览器已保留。")
            self.task_finished.emit()

    def _run_single(self):
        """单批处理模式"""
        if self.initial_batch is None:
            return False

        success = self._execute_platform(self.initial_batch, is_all_run=False)

        # ★ 新增拦截：如果执行成功，但其实是用户中途强行点了X，则拒绝标记！
        if success and self.stop_event.is_set():
            print("⚠️ 检测到执行成功信号，但用户已强制中断，取消标记。")
            return False

        if success:
            self.batch_success.emit(self.initial_batch)
        return success

    def _run_all(self):
        """全批循环处理模式"""
        queue_snapshot = list(self.batches)

        # ★ 按 PLATFORM_EXECUTION_ORDER 重排：夸克 → UC → 迅雷 → 百度 → 其他
        queue_snapshot.sort(key=lambda batch: PLATFORM_ORDER.get(
            batch[0].get("platform_code", PLATFORM_OTHER),
            len(PLATFORM_ORDER)
        ))

        total = len(queue_snapshot)
        has_failure = False
        stopped = False
        aborted = False

        for idx, batch in enumerate(queue_snapshot):
            if not batch:
                continue

            if self.stop_event.is_set():
                print("⚠️ 检测到停止信号（stop_event），任务中断。")
                stopped = True
                self.progress_msg.emit("检测到停止信号，中断全批任务。")
                break

            print(f"👉 准备执行批次: {batch[0].get('cat')}")

            cat = batch[0].get("cat", "")
            book = batch[0].get("book", "未知作品")
            platform_code = batch[0].get("platform_code", PLATFORM_OTHER)


            # ★ 路由拦截：如果是系统未支持的平台，直接跳过
            if platform_code not in PLATFORM_ROUTER:
                self.progress_msg.emit(f"⚠️ 暂未开通【{cat}】的投诉方式，已跳过。")
                continue

            remaining = total - idx
            self.progress_msg.emit(f"正在处理: [{cat}] {book} (剩余 {remaining} 批)...")

            # 执行当前批次
            success = self._execute_platform(batch, is_all_run=True)

            if success and self.stop_event.is_set():
                self.progress_msg.emit("⚠️ 用户已强制中断，取消本批标记并停止循环。")
                has_failure = True
                break

            if success:
                self.progress_msg.emit("本批提交成功！正在标记并进入下一批...")
                self.batch_success.emit(batch)
                time.sleep(3)  # 缓冲时间，防止操作过快
            else:
                has_failure = True
                self.progress_msg.emit("本批提交失败或用户中断，全批任务暂停！")
                break

        return (not has_failure) and (not stopped)