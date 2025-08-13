import re
import requests
import json
from datetime import datetime
from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.log import logger
from app.schemas import Response
from app.utils.string import StringUtils

class WeCom115Transfer(_PluginBase):
    # 插件基本信息
    plugin_name = "企业微信115转存通知"
    plugin_desc = "监听企业微信的115链接(支持115cdn.com)，转存后发送电影信息通知"
    plugin_icon = "wechat.png"
    plugin_version = "2.0"
    plugin_author = "YourName"
    author_url = "https://github.com/yourusername"
    plugin_config_prefix = "wecom115_"
    plugin_order = 10
    auth_level = 1

    # 配置参数
    _enabled = False
    _api_key = ""
    _wecom_webhook = ""
    _mp_url = "http://localhost:3001"
    _history = []

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._api_key = config.get("api_key", "")
            self._wecom_webhook = config.get("wecom_webhook", "")
            self._mp_url = config.get("mp_url", "http://localhost:3001")
            
            # 初始化历史记录
            self._history = config.get("history", [])[:20]  # 保留最近20条记录

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> dict:
        return {}

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/transfer_history",
                "endpoint": self.get_transfer_history,
                "methods": ["GET"],
                "summary": "获取转存历史记录",
                "description": "获取最近的转存操作记录"
            }
        ]

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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'mp_url',
                                            'label': 'MoviePilot地址',
                                            'placeholder': 'http://localhost:3001'
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
            "wecom_webhook": "",
            "mp_url": "http://localhost:3001",
            "history": []
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
                self.add_history(url, "失败", sender)
                return

            # 获取媒体信息
            media_info = self.get_media_info(transfer_result.get("media_id"))
            if not media_info:
                logger.error("获取媒体信息失败")
                self.add_history(url, "成功(无媒体信息)", sender)
                return

            # 发送企业微信通知
            success = self.send_wecom_notify(media_info, sender, original_url)
            if success:
                logger.info(f"转存通知已发送: {media_info.get('title')}")
                self.add_history(url, "成功", sender, media_info.get('title'))
            else:
                self.add_history(url, "成功(通知失败)", sender, media_info.get('title'))
        except Exception as e:
            logger.error(f"处理过程出错: {str(e)}")
            self.add_history(url, f"错误: {str(e)}", sender)

    def add_history(self, url: str, status: str, sender: str, title: str = ""):
        """添加转存历史记录"""
        history_item = {
            "url": url,
            "status": status,
            "sender": sender,
            "title": title,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._history.insert(0, history_item)
        self._history = self._history[:20]  # 只保留最近20条
        self.update_config(config={
            "enabled": self._enabled,
            "api_key": self._api_key,
            "wecom_webhook": self._wecom_webhook,
            "mp_url": self._mp_url,
            "history": self._history
        })

    def transfer_115(self, url: str) -> dict:
        """调用MoviePilot转存接口"""
        api_url = f"{self._mp_url.rstrip('/')}/api/v1/transfer"
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
        api_url = f"{self._mp_url.rstrip('/')}/api/v1/media/{media_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            response = requests.get(api_url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json().get("data")
            logger.error(f"媒体信息接口错误 ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"获取媒体信息失败: {str(e)}")
        return None

    def send_wecom_notify(self, media_info: dict, sender: str, original_url: str) -> bool:
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
                return True
            else:
                logger.error(f"通知发送失败 ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.error(f"通知请求失败: {str(e)}")
            return False

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """
        仪表盘展示转存历史
        """
        if not self._history:
            return None
            
        cols = {"cols": 12, "md": 6}
        attrs = {}
        
        # 创建历史记录表格
        headers = [
            {'text': '时间', 'class': 'text-start ps-4'},
            {'text': '提交者', 'class': 'text-start ps-4'},
            {'text': '标题', 'class': 'text-start ps-4'},
            {'text': '状态', 'class': 'text-start ps-4'}
        ]
        
        # 表头
        header_row = {
            'component': 'thead',
            'content': [{
                'component': 'tr',
                'content': [{
                    'component': 'th',
                    'props': {'class': header['class']},
                    'text': header['text']
                } for header in headers]
            }]
        }
        
        # 数据行
        rows = []
        for item in self._history[:5]:  # 只显示最近5条
            status_color = "text-success" if "成功" in item["status"] else "text-error"
            rows.append({
                'component': 'tr',
                'content': [
                    {'component': 'td', 'text': item.get('time', '')},
                    {'component': 'td', 'text': item.get('sender', '')},
                    {'component': 'td', 'text': item.get('title', '')[:20] + '...' if item.get('title') else '-'},
                    {'component': 'td', 'props': {'class': status_color}, 'text': item.get('status', '')}
                ]
            })
        
        # 表格组件
        table = {
            'component': 'VTable',
            'props': {
                'density': 'compact',
                'hover': True
            },
            'content': [
                header_row,
                {
                    'component': 'tbody',
                    'content': rows
                }
            ]
        }
        
        # 卡片组件
        card = {
            'component': 'VCard',
            'content': [
                {
                    'component': 'VCardTitle',
                    'props': {'class': 'pa-2'},
                    'text': '最近转存记录'
                },
                {
                    'component': 'VDivider'
                },
                {
                    'component': 'VCardText',
                    'props': {'class': 'pa-0'},
                    'content': [table]
                }
            ]
        }
        
        elements = [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [card]
                    }
                ]
            }
        ]
        
        return cols, attrs, elements

    def get_page(self) -> List[dict]:
        """
        详情页展示完整转存历史
        """
        if not self._history:
            return [
                {
                    'component': 'div',
                    'text': '暂无转存记录',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
            
        # 表头
        headers = [
            {'text': '时间', 'class': 'text-start ps-4'},
            {'text': '提交者', 'class': 'text-start ps-4'},
            {'text': '链接', 'class': 'text-start ps-4'},
            {'text': '标题', 'class': 'text-start ps-4'},
            {'text': '状态', 'class': 'text-start ps-4'}
        ]
        
        # 表头行
        header_row = {
            'component': 'thead',
            'content': [{
                'component': 'tr',
                'content': [{
                    'component': 'th',
                    'props': {'class': header['class']},
                    'text': header['text']
                } for header in headers]
            }]
        }
        
        # 数据行
        rows = []
        for item in self._history:
            status_color = "text-success" if "成功" in item["status"] else "text-error"
            url_short = item["url"].split("?")[0][:30] + "..." if len(item["url"]) > 30 else item["url"]
            
            rows.append({
                'component': 'tr',
                'content': [
                    {'component': 'td', 'text': item.get('time', '')},
                    {'component': 'td', 'text': item.get('sender', '')},
                    {
                        'component': 'td', 
                        'content': [{
                            'component': 'a',
                            'props': {
                                'href': item["url"],
                                'target': '_blank',
                                'class': 'text-blue'
                            },
                            'text': url_short
                        }]
                    },
                    {'component': 'td', 'text': item.get('title', '')[:50] + '...' if item.get('title') else '-'},
                    {'component': 'td', 'props': {'class': status_color}, 'text': item.get('status', '')}
                ]
            })
        
        # 表格组件
        table = {
            'component': 'VTable',
            'props': {'hover': True},
            'content': [
                header_row,
                {
                    'component': 'tbody',
                    'content': rows
                }
            ]
        }
        
        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [
                            {
                                'component': 'VCard',
                                'content': [
                                    {
                                        'component': 'VCardTitle',
                                        'text': '转存历史记录'
                                    },
                                    {
                                        'component': 'VDivider'
                                    },
                                    {
                                        'component': 'VCardText',
                                        'content': [table]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def get_transfer_history(self) -> Response:
        """
        获取转存历史记录API
        """
        return Response(
            success=True,
            data={
                "history": self._history
            }
        )

    def stop_service(self):
        pass
