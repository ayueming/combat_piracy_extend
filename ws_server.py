# ws_server.py
import asyncio
import websockets
import json
import threading
import datetime
import logging
import random
import time

from PySide6.QtCore import QObject, Signal
from db_config import get_conn
from link_ingest_service import save_picked_link
from parser_service import trigger_parse
from app_data.search_templates import get_search_url
from app_data.ext_search_strategies import get_ext_strategy
from plugin_bridge import bridge, ensure_ready, bridge_signals  # 加上 bridge_signals

# 全局互斥锁
_app_state_lock = threading.Lock()
_app_mode = "idle"  # 可以是 "idle", "searching", "previewing"

def get_app_mode():
    with _app_state_lock:
        return _app_mode

def set_app_mode(mode):
    global _app_mode
    with _app_state_lock:
        _app_mode = mode
    print(f"[状态锁] 当前模式切换为: {mode}")

def _on_plugin_disconnected_ws():
    print("🔌 [WS] 插件已断开，强制清除搜索锁和状态")
    _clear_busy("plugin_disconnected")
    set_app_mode("idle")

bridge_signals.plugin_disconnected.connect(_on_plugin_disconnected_ws)

def check_and_lock(mode_name):
    """尝试锁定状态，如果当前是 idle 则锁定成功，否则失败"""
    with _app_state_lock:
        global _app_mode
        if _app_mode == "idle":
            _app_mode = mode_name
            return True
        return False


class WsSignals(QObject):
    new_data_inserted = Signal(int)
    scan_state_changed = Signal(str)
    search_finished = Signal(str)  # ★ 新增：通知队列搜索已完成 (batch_id)


ws_signals = WsSignals()

current_context = {
    "book_name": "未选择作品",
    "keyword": "未选择关键词",
    "batch_id": f"plugin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
    "source_platform": ""  # ★ 新增
}

_search_busy = False
_busy_timer = None
_active_tasks = {}
_debounce_timers = {}


def _make_task_id(platform):
    return f"{platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"


def _clear_busy(reason=""):
    global _search_busy, _busy_timer
    if _busy_timer:
        try:
            _busy_timer.cancel()
        except:
            pass
        _busy_timer = None
    if _search_busy:
        _search_busy = False
        print(f"[任务] 已清除 busy 状态 ({reason})")
        ws_signals.scan_state_changed.emit("idle")


def _start_busy_timeout(task_id, seconds=300):
    global _busy_timer

    def _timeout():
        print(f"[任务] 超时未收到 scan_finished，task_id={task_id}")
        _active_tasks.pop(task_id, None)
        _clear_busy("timeout")

    t = threading.Timer(seconds, _timeout)
    t.daemon = True
    t.start()
    _busy_timer = t


# ==================== WebSocket 消息处理 ====================

async def echo(websocket):
    bridge.set_websocket(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action")

                if action == "request_context":
                    print(f"🔗 插件请求当前上下文，已发送：{current_context['book_name']}")
                    await websocket.send(json.dumps({
                        "action": "set_context",
                        "book_name": current_context["book_name"],
                        "keyword": current_context["keyword"]
                    }))

                elif action == "scan_result":
                    await _handle_scan_result(websocket, data)

                elif action == "scan_finished":
                    _handle_scan_finished(data)

                elif action == "scan_heartbeat":
                    batch_id = data.get("batch_id", "")
                    if batch_id:
                        _schedule_debounce_parse(batch_id)

                elif action == "stale_urls_resolved":
                    links = data.get("links", [])
                    _update_stale_urls(links)

                # ★ 接收手动拾取
                elif action == "manual_pick":
                    await _handle_manual_pick(websocket, data)

                # ★ 接收保存本批
                elif action == "save_manual_batch":
                    batch_id = data.get("batch_id") or current_context.get("batch_id", "")
                    if batch_id:
                        print(f"💾 用户点击保存本批: {batch_id}")
                        trigger_parse(batch_id, only_manual=True)

            except Exception as e:
                print(f"处理数据出错: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        bridge.clear_websocket()


async def _handle_manual_pick(websocket, data):
    """
    处理插件端通过 Alt/拾取模式发来的单条链接
    """
    from link_ingest_service import save_picked_link

    book_name = data.get("book_name") or current_context.get("book_name", "")
    category = data.get("category") or ""

    ctx = {
        "book_name": book_name,
        "keyword": current_context.get("keyword", ""),
        "batch_id": data.get("batch_id") or current_context.get("batch_id", ""),
        "pick_origin": "手动获取",
        "source_platform": category,
    }

    try:
        record, is_dup, is_new = save_picked_link(
            url=data["url"],
            title=data.get("title", ""),
            ctx=ctx,
            body=data.get("body", ""),
            source_site=data.get("source_site", ""),
            parent_url=data.get("parent_url", ""),
            parent_title=data.get("parent_title", ""),
            is_manual=True,
            category=category or None,
        )

        if is_new:
            print(f"📥 手动拾取入库: {data['url'][:60]}...")
            ws_signals.new_data_inserted.emit(1)
        else:
            print(f"♻️ 手动拾取记录重复，忽略: {data['url'][:60]}...")

    except Exception as e:
        print(f"❌ [手动拾取] 入库失败: {e}")


async def _handle_scan_result(websocket, data):
    task_id = data.get("task_id", "")
    links = data.get("links", [])
    if not links: return

    task = _active_tasks.get(task_id)
    if not task:
        # ★ 降级兜底：绝不瞎编“手动粘贴”，从 context 拿真实平台
        ctx_platform = current_context.get("source_platform") or "未知平台"
        ctx_keyword = current_context.get("keyword", "")
        ctx_book = current_context.get("book_name", "")
        ctx_batch = current_context.get("batch_id", "")
        print(f"⚠️ 找不到 task_id={task_id} 的上下文，使用 current_context 兜底，来源平台: {ctx_platform}")
    else:
        ctx_platform = task["platform"]
        ctx_keyword = task["keyword"]
        ctx_book = task["book_name"]
        ctx_batch = task["batch_id"]

    is_manual = bool(data.get("is_manual", False))
    pick_origin = "手动获取" if is_manual else "机器人获取"

    ctx = {
        "source_platform": ctx_platform,
        "keyword": ctx_keyword,
        "book_name": ctx_book,
        "batch_id": ctx_batch,
        "pick_origin": pick_origin,
    }

    new_count = 0
    for link in links:
        try:
            record, is_dup, is_new = save_picked_link(
                url=link["url"], title=link.get("title", ""), ctx=ctx,
                body=link.get("body", ""), source_site=link.get("source_site", ""),
                parent_url="", parent_title="", is_manual=is_manual,
            )
            if is_new: new_count += 1
        except Exception as e:
            print(f"单条清洗失败: {e}")

    if new_count > 0:
        print(f"✅ task_id={task_id} 新增草稿 {new_count} 条")
        ws_signals.new_data_inserted.emit(new_count)

    if is_manual and ctx_batch:
        trigger_parse(ctx_batch)
    else:
        # _schedule_debounce_parse(ctx_batch)
        # 既然前端有 scan_finished 兜底了，这里就不必盲目等 5 秒了
        # 如果要防万一，可以把 5 秒改短，比如 1 秒
        pass


def _handle_scan_finished(data):
    task_id = data.get("task_id", "")
    batch_id = data.get("batch_id", "")
    _active_tasks.pop(task_id, None)
    _cancel_debounce(batch_id)
    _clear_busy("scan_finished")
    if batch_id:
        ws_signals.search_finished.emit(batch_id)

    set_app_mode("idle")

    if batch_id:
        print(f"✅ 扫描完成 task_id={task_id}，立即触发解析 batch={batch_id}")
        trigger_parse(batch_id)

    _clear_busy("scan_finished")


def _schedule_debounce_parse(batch_id, delay=5.0):
    if not batch_id: return
    _cancel_debounce(batch_id)

    def _do():
        _debounce_timers.pop(batch_id, None)
        print(f"⏱ 5 秒未收到新数据，debounce 兜底解析 batch={batch_id}")
        try:
            trigger_parse(batch_id)
        except Exception as e:
            print(f"debounce 解析失败: {e}")

    t = threading.Timer(delay, _do)
    t.daemon = True
    t.start()
    _debounce_timers[batch_id] = t


def _cancel_debounce(batch_id):
    if not batch_id: return
    t = _debounce_timers.pop(batch_id, None)
    if t:
        try:
            t.cancel()
        except:
            pass


# ==================== 对外派发接口 ====================

def dispatch_search_task(platform, keyword, max_pages, sub_kws=None):
    global _search_busy

    if not check_and_lock("searching"):
        return "busy"

    if _search_busy:
        return "busy"

    # ★ 核心修改：拼接副关键词到搜索 query
    query_for_url = keyword
    if sub_kws:
        query_for_url = f"{keyword} {' '.join(sub_kws)}"
    url = get_search_url(platform, query_for_url)
    strategy = get_ext_strategy(platform)

    # 先构造 task 对象
    task = {
        "action": "do_search",
        "task_id": _make_task_id(platform),
        "batch_id": current_context.get(
            "batch_id") or f"{platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "platform": platform,
        "keyword": keyword,  # ★ 传给插件的依旧是主词，保证命中判断不受影响
        "book_name": current_context.get("book_name", ""),
        "max_pages": max_pages, "url": url, "strategy": strategy,
    }

    # ★ 关键：拿到 task 以后，再更新上下文
    current_context.update({
        "book_name": task["book_name"],
        "keyword": task["keyword"],
        "batch_id": task["batch_id"],
        "source_platform": platform  # ★ 新增
    })

    _search_busy = True
    ws_signals.scan_state_changed.emit("scanning")
    _start_busy_timeout(task["task_id"], seconds=300)

    if bridge.is_connected():
        _active_tasks[task["task_id"]] = task
        bridge.send_sync(task)
        print(f"🚀 已下发搜索任务 task_id={task['task_id']}")
        return "success"

    def _wait_and_dispatch():
        if ensure_ready(business_name="搜索", timeout=8.0):
            _active_tasks[task["task_id"]] = task
            bridge.send_sync(task)
            print(f"🚀 插件已连接，补发搜索任务 task_id={task['task_id']}")
        else:
            print(f"❌ 插件连接超时，搜索任务放弃 task_id={task['task_id']}")
            _clear_busy("plugin_timeout")

    threading.Thread(target=_wait_and_dispatch, daemon=True).start()
    return "opening"


def dispatch_stale_urls_resolve(links):
    if not bridge.is_connected():
        return False
    task = {
        "action": "resolve_stale_urls",
        "task_id": f"stale_{datetime.datetime.now().strftime('%H%M%S')}_{random.randint(100, 999)}",
        "links": links
    }
    bridge.send_sync(task)
    return True


def _update_stale_urls(links):
    from app_data.crawl_status_consts import CRAWL_STATUS_PARSE_FAILED
    conn = get_conn()
    updated_count = 0
    try:
        cursor = conn.cursor()
        for link in links:
            new_url = link.get("url")
            old_url = link.get("original_url")
            if new_url and old_url and "baidu.com/link" not in new_url:
                cursor.execute(
                    "UPDATE draft_links SET site_url = ?, crawl_status = 'pending', match_status = '' WHERE site_url = ?",
                    (new_url, old_url)
                )
                updated_count += cursor.rowcount
        conn.commit()
        print(f"✅ 存量短链解析完毕，成功更新 {updated_count} 条数据库记录")
    except Exception as e:
        print(f"更新存量短链失败: {e}")
        conn.rollback()
    finally:
        conn.close()

    if updated_count > 0:
        ws_signals.new_data_inserted.emit(updated_count)
    else:
        ws_signals.new_data_inserted.emit(0)


def dispatch_close_preview():
    if bridge.is_connected():
        bridge.send_sync({"action": "close_preview"})


def dispatch_open_preview(url, book_name="", keyword="", batch_id="",
                           source_db_id=None, category="",
                           available_books=None, available_categories=None):
    """通知插件浏览器打开指定的预览链接（异步，防卡顿）"""
    def _run():
        if not bridge.is_connected():
            ensure_ready(business_name="预览", timeout=8.0)
        bridge.send_sync({
            "action": "open_preview",
            "url": url,
            "book_name": book_name,
            "keyword": keyword,
            "batch_id": batch_id,
            "source_db_id": source_db_id,
            "category": category,
            "available_books": available_books or [],
            "available_categories": available_categories or [],
        })
    threading.Thread(target=_run, daemon=True).start()


async def main():
    print("🚀 WebSocket 后台控制台已启动，监听 8080 端口...")
    logging.getLogger('websockets').setLevel(logging.CRITICAL)
    async with websockets.serve(echo, "127.0.0.1", 8080):
        await asyncio.Future()


def run_loop():
    asyncio.run(main())


def start_ws_server():
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()