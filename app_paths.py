# app_paths.py
import os
import sys

# ================= 目录 / 文件名常量 =================
DATA_ROOT_NAME = "CombatPiracy"

DIR_USERS = "users"
DIR_EVIDENCES = "evidences"
DIR_LOGS = "logs"
DIR_TEMP = "temp"
DIR_BROWSER_PROFILE = "browser_profile"
DIR_ERROR_SHOTS = "error_screenshots"
DIR_TEMPLATES = "templates"

FILE_SESSION = "session.json"
FILE_AUTH = "auth.json"
FILE_DB = "piracy_records.db"
FILE_AUTHORIZATION_PDF = "authorization.pdf"
FILE_DEVTOOLS_ACTIVE_PORT = "DevToolsActivePort"

# 浏览器残留锁文件（启动前需清理）
BROWSER_LOCK_FILES = (
    "DevToolsActivePort",
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
)

# 临时 Excel 文件名模板，按平台代号格式化
TEMP_EXCEL_TPL = "temp_{platform}_import.xlsx"


def get_app_dir():
    """程序安装目录（打包后=exe所在目录；开发时=源码目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_data_root():
    r"""
    获取数据根目录。
    1. 开发环境（PyCharm运行）：项目目录下的 data 文件夹。
    2. 打包后的生产环境：C:\Users\用户名\AppData\Local\CombatPiracy，避免 Program Files 无写入权限的问题。
    """
    if getattr(sys, 'frozen', False):
        base_dir = os.getenv('LOCALAPPDATA') or os.path.expanduser('~')
        d = os.path.join(base_dir, DATA_ROOT_NAME)
    else:
        d = os.path.join(get_app_dir(), "data")

    os.makedirs(d, exist_ok=True)
    return d


def get_user_dir(user_id):
    """
    获取指定用户的专属数据目录。
    会自动创建该用户的所有子文件夹（evidences, logs, temp, templates）。
    """
    if not user_id:
        raise ValueError("user_id 不能为空")

    user_dir = os.path.join(get_data_root(), DIR_USERS, str(user_id))

    for sub in (DIR_EVIDENCES, DIR_LOGS, DIR_TEMP, DIR_TEMPLATES):
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

    return user_dir


def get_user_subdir(user_id, subdir_name, create=True):
    """获取用户目录下的子目录，默认自动创建。"""
    d = os.path.join(get_user_dir(user_id), subdir_name)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def get_session_path():
    """获取当前登录会话（指针）的文件路径"""
    return os.path.join(get_data_root(), FILE_SESSION)


# ================= 兼容旧代码的变量和函数 =================
# 提示：这些是过渡期的兼容代码，后续我们会把调用它们的地方改掉。

def get_temp_dir():
    """【兼容旧代码】获取全局临时目录（后续需改为按用户隔离）"""
    d = os.path.join(get_data_root(), DIR_TEMP)
    os.makedirs(d, exist_ok=True)
    return d


APP_DIR = get_app_dir()
DATA_DIR = get_data_root()