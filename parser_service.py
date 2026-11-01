# parser_service.py
import threading
from PySide6.QtCore import QObject, Signal
from link_ingest_service import organize_pending_links


class ParserSignals(QObject):
    parse_finished = Signal(bool)


parser_signals = ParserSignals()

_parse_lock = threading.Lock()
_parsing_batches = set()


def trigger_parse(batch_id, is_exact=False, only_manual=False):
    with _parse_lock:
        if batch_id in _parsing_batches:
            print(f"⏭️ batch={batch_id} 正在解析中，跳过")
            return
        _parsing_batches.add(batch_id)

    print(f"🛠️ 触发后台智能解析，批次: {batch_id}")

    def run():
        try:
            organize_pending_links(
                is_exact_match=is_exact,
                batch_id=batch_id,
                process_events_func=None,
                only_manual=only_manual,  # ★ 透传
            )
            print("✅ 解析完成！")
            parser_signals.parse_finished.emit(True)
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            parser_signals.parse_finished.emit(False)
        finally:
            with _parse_lock:
                _parsing_batches.discard(batch_id)

    t = threading.Thread(target=run, daemon=True)
    t.start()