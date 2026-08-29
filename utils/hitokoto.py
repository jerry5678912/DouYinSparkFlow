import requests
from utils.config import get_config

hitokotoApi = "https://v1.hitokoto.cn/"

allHitokotoTypes = {
    "动画": "a",
    "漫画": "b",
    "游戏": "c",
    "文学": "d",
    "原创": "e",
    "来自网络": "f",
    "其他": "g",
    "影视": "h",
    "诗词": "i",
    "哲学": "k",
    "抖机灵": "l",
}


def request_hitokoto():
    """请求一言 API 获取一句话"""
    config = get_config()
    params = [
        ("c", code)
        for quote_type, code in allHitokotoTypes.items()
        if quote_type in config["hitokotoTypes"]
    ]

    try:
        response = requests.get(
            hitokotoApi,
            params=params,
            timeout=10,
            allow_redirects=False,
        )
        if isinstance(response.status_code, int) and 300 <= response.status_code < 400:
            raise ValueError("redirects are not accepted from the quote service")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("quote response must be a JSON object")

        quote = data.get("hitokoto")
        source = data.get("from") or "未知来源"
        author = data.get("from_who") or "未知作者"
        fields = ((quote, 500), (source, 100), (author, 100))
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > maximum
            for value, maximum in fields
        ):
            raise ValueError("quote response contains invalid text")

        return f"{quote.strip()} —— {source.strip()} ({author.strip()})"
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return "[error] 无法获取一言内容"
