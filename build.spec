# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    collect_all,
)

# ===== Supabase 生态包（包含底层网络请求依赖，一个都不能少） =====
SUPABASE_PKGS = [
    'supabase',
    'postgrest',
    'gotrue',
    'realtime',
    'storage3',
    'supabase_functions',
    'httpx',
    'httpcore',
    'anyio',
    'sniffio',
    'h11',
    'h2',
    'certifi',
    'idna',
    'pydantic',
    'pydantic_core',
]

sb_datas, sb_binaries, sb_hidden = [], [], []
for pkg in SUPABASE_PKGS:
    d, b, h = collect_all(pkg)
    sb_datas += d
    sb_binaries += b
    sb_hidden += h


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=sb_binaries,
    datas=[
        # ★ 核心资源文件
        ('*.md', '.'),                           # 所有md文档

        # ★ 库自带的静态资源
        *collect_data_files('playwright'),
        *sb_datas,
    ],
    hiddenimports=[
        # ★ 核心模块
        'sqlite3',
        'openpyxl',
        'docx',
        'PIL',
        'fpdf',
        'bs4',
        'playwright',

        # ★ 你的配置模块（必须包含，否则打包后连不上数据库）
        'config',
        'config_local',

        # ★ 你的业务逻辑模块（防漏掉动态引入）
        'login_window',
        'login_device_id',
        'license_manager',
        'page_profile',

        # ★ 第三方库依赖
        *collect_submodules('PySide6'),
        *sb_hidden,
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # ★ 明确排除不需要的测试代码，减小体积
        'supabase.tests',
        'test_spiser',       # 排除你自己写的测试脚本
        'config_local.py.example',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='打盗维权系统_试用版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # 千万不要开 UPX，会导致 Playwright 崩溃
    console=False,           # 想看报错时临时改 True
    disable_windowed_traceback=False,
    icon=None,               # 以后有图标了，在这里加上 icon='app.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='打盗维权系统',
)