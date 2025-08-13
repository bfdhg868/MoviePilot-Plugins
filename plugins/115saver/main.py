import re
import requests
from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.log import logger

class WeCom115Transfer(_PluginBase):
    # 插件基本信息
    plugin_name = "企业微信115转存通知"
    plugin_desc = "监听企业微信的115链接(支持115cdn.com)，转存后发送电影信息通知"
    plugin_icon = "wechat.png"
    plugin_version = "1.1"

    # 配置参数
    _enabled = False
    _api_key = ""
    _wecom_webhook = ""
    _115_api = "https://115.com"

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._api_key = config.get("api_key")
            self._wecom_webhook = config.get("wecom_webhook")

    def get_state(self):
        return self._enabled

    @staticmethod
    def get_command() -> dict:
        return {}

    def get_api(self) -> dict:
        return {}

    def get_form(self) -> tuple:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'api_key',
                                            'label': 'MoviePilot API密钥',
                                            'placeholder': '在设置->安全->API密钥中获取'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'wecom_webhook',
                                            'label': '企业微信Webhook地址',
                                            'placeholder': 'https://qyapi.weixin.qq.com/...'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'text': '支持链接格式: https://115.com/... 和 https://115cdn.com/...',
                                            'variant': 'tonal'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "api_key": "",
            "wecom_webhook": ""
        }

    @eventmanager.register(EventType.WeComMessage)
    def handle_wecom_message(self, event: Event):
        if not self._enabled or not self._api_key or not self._wecom_webhook:
            return

        message = event.event_data.get("message")
        sender = event.event_data.get("sender")

        # 提取115链接 - 同时匹配115.com和115cdn.com
        url_pattern = r'https?://(?:115|115cdn)\.com/[^\s]+'
        match = re.search(url_pattern, message)
        if not match:
            return

        url = match.group(0)
        logger.info(f"检测到115链接: {url}, 发送者: {sender}")

        # 处理CDN链接的特殊情况
        original_url = url
        if "115cdn.com" in url:
            # 将CDN链接转换为标准115链接
            url = url.replace("115cdn.com", "115.com")
            logger.info(f"转换CDN链接 {original_url} → {url}")

        try:
            # 调用MoviePilot转存接口
            transfer_result = self.transfer_115(url)
            if not transfer_result:
                logger.error(f"转存失败: {url}")
                return

            # 获取媒体信息
            media_info = self.get_media_info(transfer_result.get("media_id"))
            if not media_info:
                logger.error("获取媒体信息失败")
                return

            # 发送企业微信通知
            self.send_wecom_notify(media_info, sender, original_url)
            logger.info(f"转存通知已发送: {media_info.get('title')}")

        except Exception as e:
            logger.error(f"处理过程出错: {str(e)}")

    def transfer_115(self, url: str) -> dict:
        """调用MoviePilot转存接口"""
        api_url = "http://localhost:3001/api/v1/transfer"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {"url": url, "type": "115"}

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json().get("data")
            logger.error(f"转存接口错误 ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"转存请求失败: {str(e)}")
        return None

    def get_media_info(self, media_id: str) -> dict:
        """获取媒体信息"""
        api_url = f"http://localhost:3001/api/v1/media/{media_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            response = requests.get(api_url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json().get("data")
            logger.error(f"媒体信息接口错误 ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"获取媒体信息失败: {str(e)}")
        return None

    def send_wecom_notify(self, media_info: dict, sender: str, original_url: str):
        """发送企业微信图文通知"""
        title = media_info.get("title", "未知标题")
        overview = media_info.get("overview", "暂无简介")
        poster = media_info.get("poster")
        year = media_info.get("year")
        media_type = media_info.get("type", "电影")

        # 处理简介长度
        max_overview_length = 120
        if overview and len(overview) > max_overview_length:
            overview = overview[:max_overview_length] + "..."

        # 构造消息卡片
        message = {
            "msgtype": "news",
            "news": {
                "articles": [
                    {
                        "title": f"{title} ({year})" if year else title,
                        "description": f"🎬 {media_type}转存成功\n👤 提交者: {sender}\n🔗 原始链接: {original_url}\n\n{overview}",
                        "url": poster,
                        "picurl": poster
                    }
                ]
            }
        }

        try:
            response = requests.post(self._wecom_webhook, json=message, timeout=30)
            if response.status_code == 200:
                logger.debug(f"通知发送成功: {response.json()}")
            else:
                logger.error(f"通知发送失败 ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"通知请求失败: {str(e)}")

    def stop(self):
        pass

    def get_page(self):
        pass