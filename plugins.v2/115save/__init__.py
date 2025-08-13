# -*- coding: utf-8 -*-
"""
115 Saver 插件
监听企业微信消息，自动转存115分享链接
转存成功后，通过企业微信推送电影信息（标题、简介、海报）
"""

from mbot.core.plugins import plugin, PluginContext, PluginMeta
from .main import run
import re

meta = PluginMeta(
    name='115 Saver',
    description='自动转存115分享链接，转存成功通过企业微信通知电影详情',
    version='1.3',
    author='YourName',
    config_params=[
        {
            "name": "cookie",
            "title": "115账户Cookie",
            "type": "textarea",
            "placeholder": "请填写115网盘登录Cookie",
            "required": True
        },
        {
            "name": "save_pid",
            "title": "保存目录ID",
            "type": "int",
            "default": 0,
            "description": "转存到115网盘目录ID"
        }
    ]
)

@plugin.on_message()
def on_message(ctx: PluginContext, message: dict):
    """
    监听到企业微信消息，自动处理115分享链接并转存
    """
    cookie = ctx.get_config("cookie")
    save_pid = ctx.get_config("save_pid", 0)

    if not cookie:
        ctx.logger.warning("115 Saver插件未配置Cookie，无法转存")
        return

    text = message.get("text") or message.get("content") or ""
    if not text:
        return

    match = re.search(r'(https://115(?:cdn)?\.com/s/[^\s#]+)', text)
    if not match:
        return

    link = match.group(1)
    ctx.logger.info(f"检测到115分享链接，开始转存: {link}")

    # 调用转存并返回MoviePilot识别的电影信息
    result = run(link, cookie, save_pid)

    ctx.logger.info(f"转存结果: {result}")

    # 判断转存成功且返回电影信息
    if result.get("state") and result.get("data") and "movie_info" in result["data"]:
        movie_info = result["data"]["movie_info"]
        title = movie_info.get("title", "未知电影")
        summary = movie_info.get("summary", "")
        poster = movie_info.get("poster", "")

        # 构造企业微信图文消息格式
        articles = [{
            "title": title,
            "description": summary,
            "url": "",  # 可放电影详情页链接，若有
            "picurl": poster
        }]

        # 发送企业微信通知，利用 MoviePilot 内置通知接口
        try:
            ctx.notify(
                msgtype="news",
                news={"articles": articles}
            )
            ctx.logger.info("已通过企业微信通知发送电影详情")
        except Exception as e:
            ctx.logger.error(f"企业微信通知发送失败: {e}")

@plugin.command(name='save115', title='115转存', desc='输入分享链接转存到115网盘', icon='CloudDownload')
def save115(ctx: PluginContext, link: str):
    """
    手动命令调用转存115分享链接
    """
    cookie = ctx.get_config("cookie")
    save_pid = ctx.get_config("save_pid", 0)

    if not cookie:
        return "⚠️ 请先在插件配置界面填写115账号Cookie"

    result = run(link, cookie, save_pid)
    if result.get("state"):
        return f'✅ 转存成功: {result}'
    else:
        return f'❌ 转存失败: {result}'
