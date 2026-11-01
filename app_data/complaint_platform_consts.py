# app_data/complaint_platform_consts.py

# =========================================================
# 平台代号 / 模块代号常量
# 供 PLATFORM_CONFIG、调度器、自动脚本、默认值统一引用
#
# ★ module 仅作 5 元组占位，调用用途不大，新代码尽量不要读取它。
#   当前只有夸克/UC 脚本用 module 做功能模块分支，后续应逐步改为 web_text。
#   新增“暂未开通”类子分类时，module 统一填 MODULE_OTHER，不要新增 module 常量。
# =========================================================
PLATFORM_BAIDU = "baidu"
PLATFORM_QUARK = "quark"
PLATFORM_UC = "uc"
PLATFORM_XUNLEI = "xunlei"
PLATFORM_OTHER = "other"


MODULE_SEARCH = "search"
MODULE_NETDISK = "netdisk"
MODULE_FORUM = "forum"
MODULE_OTHER = "other"
# 以下都属于论坛，已合并到FLATFORM_FORUM，保留暂不报错
MODULE_ZHIDAO = "zhidao"
MODULE_TIEBA = "tieba"
MODULE_TOUTIAO = "toutiao"

# =========================================================
# 平台配置中心 (保持 5 元组结构绝对不动)
# 格式: "主分类": [("软件显示名", "平台代号", "模块代号", "网页官方文字", [别名...])]
# =========================================================
PLATFORM_CONFIG = {
    "百度投诉": [
        ("百度网盘", PLATFORM_BAIDU, MODULE_NETDISK, "百度网盘", []),
        ("百度知道", PLATFORM_BAIDU, MODULE_FORUM, "百度知道", []),
        ("百度贴吧", PLATFORM_BAIDU, MODULE_FORUM, "百度贴吧", []),
        ("百度搜索", PLATFORM_BAIDU, MODULE_SEARCH, "百度搜索", [])
    ],
    "夸克投诉": [
        ("夸克网盘", PLATFORM_QUARK, MODULE_NETDISK, "夸克网盘", []),
        ("夸克搜索", PLATFORM_QUARK, MODULE_SEARCH, "夸克搜索", [])
    ],
    "uc投诉": [
        ("uc网盘", PLATFORM_UC, MODULE_NETDISK, "UC网盘", []),
        ("uc搜索", PLATFORM_UC, MODULE_SEARCH, "神马搜索", [])  # 统一为小写
    ],
    "迅雷投诉": [
        ("迅雷网盘", PLATFORM_XUNLEI, MODULE_NETDISK, "迅雷云盘", [])
    ],
    "其他": [
        # ★ 纯人工分类入口，不承接自动域名匹配。
        ("其他", PLATFORM_OTHER, MODULE_OTHER, "其他", [])
    ],
    "暂未开通": [
        # ★ module 填 MODULE_OTHER 仅为结构占位，业务判断请用 domain_matched + target_platform。
        #   以后往这里加微博/知乎/豆瓣等，module 统一填 MODULE_OTHER，不要新增 module 常量。
        ("暂未开通", PLATFORM_OTHER, MODULE_OTHER, "暂未开通", [])
    ]
}

# =========================================================
# 平台域名映射 (合并了原来的 DOMAIN_RULES)
# 用于链接解析和特征提取，键必须是 PLATFORM_CONFIG 中的 display_name
# =========================================================
PLATFORM_DOMAINS = {
    "百度网盘": ["pan.baidu.com"],
    "百度知道": ["zhidao.baidu.com"],
    "百度贴吧": ["tieba.baidu.com"],
    "夸克网盘": ["pan.quark.cn"],
    "uc网盘": ["drive.uc.cn"],
    "迅雷网盘": ["pan.xunlei.com"],
    # ★ 暂未开通：有明确域名但业务未开通，统一归入“暂未开通”分类。
    #   以后某个域名开通了业务，就从这里移出，在 PLATFORM_CONFIG 注册正式子分类并加入上方对应位置。
    "暂未开通": ["aliyundrive.com", "lanzou", "123pan.com", "115.com"],
}


# 投诉执行顺序，一定要加进来
PLATFORM_EXECUTION_ORDER = [
    PLATFORM_QUARK,
    PLATFORM_UC,
    PLATFORM_XUNLEI,
    PLATFORM_BAIDU,
    PLATFORM_OTHER,  # 兜底放最后
]


# =========================================================
# 自动推导区
# =========================================================

# 1. 给界面下拉框用的全量软件显示名
ALL_SUB_PLATFORMS = []

# 2. 给数据提取用的代号和网页文字映射表
CAT_TO_CODE_MAP = {}

# 3. 别名到软件标准显示名的纠正表 (例如: "迅雷云" -> "迅雷网盘")
CAT_TO_STANDARD_NAME = {}

for main_cat, sub_list in PLATFORM_CONFIG.items():
    for display_name, p_code, m_code, web_text, aliases in sub_list:
        code_info = {
            "platform": p_code,
            "module": m_code,
            "web_text": web_text
        }

        if display_name not in ALL_SUB_PLATFORMS:
            ALL_SUB_PLATFORMS.append(display_name)

        CAT_TO_CODE_MAP[display_name] = code_info
        CAT_TO_STANDARD_NAME[display_name] = display_name

        for alias in aliases:
            if alias not in CAT_TO_CODE_MAP:
                CAT_TO_CODE_MAP[alias] = code_info
                CAT_TO_STANDARD_NAME[alias] = display_name

# =========================================================
# 启动校验
# =========================================================
# PLATFORM_DOMAINS 的键必须都是 PLATFORM_CONFIG 中注册过的显示名，
# 防止以后加域名时忘了在 PLATFORM_CONFIG 注册，导致 target_platform 写出下拉里不存在的名字。
_invalid_domains = set(PLATFORM_DOMAINS) - set(ALL_SUB_PLATFORMS)
if _invalid_domains:
    raise RuntimeError(
        f"complaint_platform_consts.py 中 PLATFORM_DOMAINS 存在未在 PLATFORM_CONFIG 注册的平台名：{_invalid_domains}"
    )


# =========================================================
# UI 展示控制（仅控制顶部按钮栏是否渲染，不影响任何业务逻辑）
# =========================================================
# 不在顶部"快捷分组"和"具体平台"按钮栏中显示的分类。
#
# ★ 红线：不要删除 PLATFORM_CONFIG / PLATFORM_DOMAINS 里的对应键，
#   否则 ALL_SUB_PLATFORMS 缺项，会导致本文件底部的启动校验
#   raise RuntimeError（PLATFORM_DOMAINS 存在未注册的平台名）。
#   本集合只用于 UI 层过滤，业务侧（spider / 域名匹配 / 入库）照常走。
#
# 以后某个平台业务开通时，从本集合移除该字符串，按钮自动恢复显示。
HIDDEN_MAIN_CATEGORIES = {"暂未开通"}



# 仅提取已经正式开通的网盘域名（用于后期打标签）
ACTIVE_NETDISK_DOMAINS = []

for main_cat, sub_list in PLATFORM_CONFIG.items():
    for display_name, p_code, m_code, web_text, aliases in sub_list:
        # 只认明确标记为 MODULE_NETDISK 的分类
        if m_code == MODULE_NETDISK:
            if display_name in PLATFORM_DOMAINS:
                ACTIVE_NETDISK_DOMAINS.extend(PLATFORM_DOMAINS[display_name])

# 去重，保证性能
ACTIVE_NETDISK_DOMAINS = list(set(ACTIVE_NETDISK_DOMAINS))

