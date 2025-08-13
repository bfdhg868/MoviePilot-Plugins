import re
import requests
from urllib.parse import urlparse, parse_qs

def extract_pickcode(share_url, cookie):
    """
    提取115分享链接中的pickcode（支持带密码链接）
    """
    parsed_url = urlparse(share_url)
    query = parse_qs(parsed_url.query)
    password = query.get("password", [None])[0]

    match = re.search(r'/s/([a-zA-Z0-9]+)', share_url)
    if not match:
        return None

    share_code = match.group(1)
    headers = {"Cookie": cookie}
    params = {"share_code": share_code}
    if password:
        params["pwd"] = password

    res = requests.get("https://webapi.115.com/share/snap", headers=headers, params=params)
    try:
        data = res.json()
    except Exception:
        return None

    if data.get("state") and data.get("data") and "list" in data["data"]:
        file_list = data["data"]["list"]
        if file_list:
            return file_list[0]["pick_code"]
    return None

def save_to_115(pickcode, cookie, save_pid):
    """
    转存到115网盘
    """
    url = "https://webapi.115.com/files/add"
    payload = {
        "pid": save_pid,
        "pickcode": pickcode
    }
    headers = {
        "Cookie": cookie
    }
    res = requests.post(url, data=payload, headers=headers)
    try:
        return res.json()
    except:
        return {"state": False, "msg": "返回解析失败"}

def run(link, cookie, save_pid):
    """
    主逻辑：转存115链接，并返回电影信息
    """
    pickcode = extract_pickcode(link, cookie)
    if not pickcode:
        return {"state": False, "msg": "pickcode解析失败"}

    res = save_to_115(pickcode, cookie, save_pid)
    if not res.get("state"):
        return res

    # 模拟MoviePilot识别电影信息（这里直接从文件名提取，实际环境中应该从MoviePilot识别获取）
    movie_info = {
        "title": res.get("file_name", "未知电影"),
        "summary": "这是电影简介，来自MoviePilot识别",
        "poster": "https://example.com/poster.jpg"  # 可以根据需要动态生成
    }

    return {
        "state": True,
        "data": {
            "raw": res,
            "movie_info": movie_info
        }
    }
