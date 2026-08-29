import os, sys
from enum import Enum
import json
import logging
from utils.logger import setup_logger
from utils import norm

logger = setup_logger(level=logging.INFO)

SUPPORTED_HITOKOTO_TYPES = {
    "动画", "漫画", "游戏", "文学", "原创", "来自网络",
    "其他", "影视", "诗词", "哲学", "抖机灵",
}
MAX_TASKS = 20
MAX_TARGETS_PER_TASK = 100
MAX_COOKIES_PER_TASK = 250
MAX_COOKIE_JSON_BYTES = 256 * 1024

"""
是否启用调试模式
更详细的日志打印，浏览器操作可视化等
"""
DEBUG = True
config = None
userData = None


class Environment(Enum):
    GITHUBACTION = "GITHUB_ACTION"  # GitHub Action 运行
    LOCAL = "LOCAL"  # 本地代码运行
    PACKED = "PACKED"  # PyInstaller 打包运行

    def __str__(self):
        return self.value


def get_environment():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Environment.PACKED
    elif os.getenv("GITHUB_ACTIONS") == "true":
        return Environment.GITHUBACTION
    else:
        return Environment.LOCAL


def _parse_json_environment(name, default):
    raw_value = os.getenv(name, default)
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must contain valid JSON") from exc


def _parse_bounded_integer(name, default, minimum, maximum):
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def get_config():
    """
    获取配置信息
    :return: 配置字典
    """
    global config

    if config:
        return config

    hitokoto_types = _parse_json_environment(
        "HITOKOTO_TYPES", '["文学","影视","诗词","哲学"]'
    )
    if (
        not isinstance(hitokoto_types, list)
        or len(hitokoto_types) > len(SUPPORTED_HITOKOTO_TYPES)
        or any(item not in SUPPORTED_HITOKOTO_TYPES for item in hitokoto_types)
    ):
        raise ValueError("HITOKOTO_TYPES must be a list of supported values")

    message_template = os.getenv(
        "MESSAGE_TEMPLATE",
        "[盖瑞]今日火花[加一]\\n—— [右边] 每日一言 [左边] ——\\n[API]",
    )
    if not 1 <= len(message_template) <= 2000:
        raise ValueError("MESSAGE_TEMPLATE must contain between 1 and 2000 characters")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")

    config = {
        "proxyAddress": os.getenv("PROXY_ADDRESS", ""),
        "messageTemplate": message_template,
        "hitokotoTypes": hitokoto_types,
        "browserTimeout": _parse_bounded_integer(
            "BROWSER_TIMEOUT", 120000, 1000, 300000
        ),
        "friendListTimeout": _parse_bounded_integer(
            "FRIEND_LIST_WAIT_TIME", 2000, 100, 60000
        ),
        "taskRetryTimes": _parse_bounded_integer("TASK_RETRY_TIMES", 3, 1, 10),
        "logLevel": log_level,
    }

    return config


def sanitize_cookies(cookies):
    for cookie in cookies:
        if "sameSite" in cookie:
            cookie.pop("sameSite")  # 移除 sameSite 字段，Playwright 可能不支持该字段
    return cookies


def get_userData():
    """
    获取用户数据目录
    :return: 用户数据目录路径
    """
    global userData

    if userData:
        return userData

    tasks = _parse_json_environment("TASKS", "[]")
    if not isinstance(tasks, list):
        raise ValueError("TASKS must be a JSON list")
    if len(tasks) > MAX_TASKS:
        raise ValueError(f"TASKS cannot contain more than {MAX_TASKS} accounts")

    userData = []

    for task_index, task in enumerate(tasks, start=1):
        account_label = f"account-{task_index}"
        if not isinstance(task, dict):
            logger.warning(f"{account_label} 的任务格式不正确，已跳过")
            continue
        username = task.get("username", "未知用户")
        unique_id = task.get("unique_id")
        if not isinstance(unique_id, str) or not 1 <= len(unique_id) <= 128:
            logger.warning(f"{account_label} 缺少有效 unique_id 字段，已跳过")
            continue
        cookies_key = f"cookies_{unique_id}".upper()
        cookies_str = (
            os.getenv(cookies_key, "").encode("utf-8").decode("unicode_escape")
        )
        if not cookies_str:
            logger.warning(f"{account_label} 缺少 Cookies 环境变量，已跳过")
            continue
        if len(cookies_str.encode("utf-8")) > MAX_COOKIE_JSON_BYTES:
            logger.warning(f"{account_label} 的 Cookies 数据过大，已跳过")
            continue
        try:
            cookies = json.loads(cookies_str)
        except json.JSONDecodeError:
            logger.warning(f"{account_label} 的 Cookies 格式不正确，已跳过")
            continue
        if (
            not isinstance(cookies, list)
            or len(cookies) > MAX_COOKIES_PER_TASK
            or any(not isinstance(cookie, dict) for cookie in cookies)
        ):
            logger.warning(f"{account_label} 的 Cookies 必须是有效 JSON 列表，已跳过")
            continue

        targets = task.get("targets", [])
        if (
            not isinstance(targets, list)
            or len(targets) > MAX_TARGETS_PER_TASK
            or any(not isinstance(target, str) or len(target) > 128 for target in targets)
        ):
            logger.warning(f"{account_label} 的目标好友列表格式不正确，已跳过")
            continue

        userData.append(
            {
                "unique_id": unique_id,
                "username": username,
                "cookies": sanitize_cookies(cookies),
                "targets": [norm(t) for t in targets], # 标准化目标列表
            }
        )

    return userData
