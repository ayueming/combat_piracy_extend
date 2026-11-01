import os
import time

from app_paths import get_user_subdir, DIR_ERROR_SHOTS

# 统一的投诉长文本模板
DESC_TEMPLATE = (
    "晋江文学城授权作品{name_str}，首发网址：{url_str}，"
    "被盗文网站非法获取，贵站出现大量盗文txt分享，持续侵犯作者的个人利益。"
    "作者已经按照规则提交了作者的作品授权书，首发平台截图和后台截图，"
    "希望贵站能够严肃处理这一问题，删除原帖和txt分享链接。"
)


def take_error_screenshot(page, user_dir: str, platform_name: str) -> str | None:
    """
    统一报错截图保存功能
    :param page: Playwright Page
    :param user_dir: 当前用户根目录（用于定位 error_screenshots 子目录）
    :param platform_name: 传 'baidu' / 'xunlei' / 'quark' / 'uc'
    """
    try:
        screenshot_dir = os.path.join(user_dir, DIR_ERROR_SHOTS)
        os.makedirs(screenshot_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(screenshot_dir, f"error_{platform_name}_{ts}.png")
        page.screenshot(path=screenshot_path, full_page=True)
        return screenshot_path
    except Exception as e:
        print(f"⚠️ 截图保存失败: {e}")
        return None