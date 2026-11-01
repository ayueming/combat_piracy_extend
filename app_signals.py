# app_signals.py
from PySide6.QtCore import QObject, Signal

class AppSignals(QObject):
    # 原有信号
    link_saved = Signal(object, bool)
    # 手动拾取完成信号（用于触发统一分析和关闭浏览器）
    manual_pick_finished = Signal()
    # ★ 新增：用户强关浏览器且存在暂存拾取，交给 UI 线程弹窗决策
    pending_picks_on_close = Signal()
    # ★ 新增：暂存区变化，UI 侧可监听（用于状态栏显示 N 条待保存）
    pending_count_changed = Signal(int)

    # ★ 新增：预览浮窗点击「保存本批」——只落库解析，不关闭浏览器/分屏
    save_batch_requested = Signal()

signals = AppSignals()