# login_device_id.py
import hashlib
import subprocess
import uuid


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5
        ).decode(errors="ignore").strip()
    except Exception:
        return ""


def get_machine_id() -> str:
    """
    生成稳定的设备指纹（Windows）：
    - 主板序列号
    - 硬盘序列号
    - MAC 地址
    组合后取 SHA-256 前 32 位。
    """
    parts = [
        _run('wmic baseboard get serialnumber'),
        _run('wmic diskdrive get serialnumber'),
        str(uuid.getnode()),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]