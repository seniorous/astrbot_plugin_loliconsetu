from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import httpx
import json
import asyncio
import re

@register("loliconsetu", "rikka", "支持参数自选的涩图插件", "2.0.0")
class LoliconSetuPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.cd = 10
        self.last_usage = {}
        
    def parse_setu_params(self, params: str) -> dict:
        """解析用户输入的参数 返回API请求参数"""
        args = {
            "r18": 0,
            "size": "regular",
            "num": 1,
            "tag": "",
            "author": ""
        }
        
        # 使用正则匹配参数
        matches = re.findall(r'(r18|size|num|tag|author)=([^&\s]+)', params)
        for key, value in matches:
            value = value.strip('"\'')  # 去除引号
            if key == "r18":
                args["r18"] = 1 if value.lower() in ["true", "yes", "1"] else 0
            elif key == "size":
                if value.lower() in ["original", "regular", "small"]:
                    args["size"] = value.lower()
            elif key == "num":
                try:
                    num = int(value)
                    args["num"] = max(1, min(num, 10))  # 限制1-10张
                except ValueError:
                    pass
            elif key == "tag":
                args["tag"] = value
            elif key == "author":
                args["author"] = value
        
        return args

    @filter.command("setu {{params}}")
    async def setu(self, event: AstrMessageEvent, params: str = ""):
        user_id = event.get_sender_id()
        now = asyncio.get_event_loop().time()

        if user_id in self.last_usage and (now - self.last_usage[user_id]) < self.cd:
            remaining_time = self.cd - (now - self.last_usage[user_id])
            yield event.plain_result(f"冷却中，请等待 {remaining_time:.1f} 秒后重试。")
            return

        try:
            # 解析参数
            api_params = self.parse_setu_params(params)
            query_params = {
                "r18": api_params['r18'],
                "size": api_params['size'],
                "num": api_params['num']
            }
            if api_params['tag']:
                query_params["tag"] = api_params['tag']
            if api_params['author']:
                query_params["author"] = api_params['author']
            
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.lolicon.app/setu/v2", params=query_params)
                resp.raise_for_status()
                data = resp.json()
                
                if data['data']:
                    chains = []
                    for setu_data in data['data'][:api_params['num']]:  # 限制最大返回数量
                        image_url = setu_data['urls'][api_params['size']]
                        chain = [
                            At(qq=event.get_sender_id()),
                            Plain(f"参数设置：R18={'开启' if api_params['r18'] else '关闭'} 尺寸={api_params['size']}\n"),
                            Plain(f"PID：{setu_data['pid']} | 作者：{setu_data['author']} | 标签：{', '.join(setu_data['tags'])}\n"),
                            Image.fromURL(image_url, size=api_params['size']),
                        ]
                        chains.append(chain)
                    
                    # 发送所有结果（自动间隔0.5秒）
                    for i, chain in enumerate(chains):
                        if i > 0:
                            await asyncio.sleep(0.5)  # 防止消息轰炸
                        yield event.chain_result(chain)
                    self.last_usage[user_id] = now
                else:
                    yield event.plain_result("没有找到符合要求的涩图。")
        except httpx.HTTPError as e:
            yield event.plain_result(f"API请求失败: {e}")
        except json.JSONDecodeError as e:
            yield event.plain_result(f"响应解析错误: {e}")
        except KeyError as e:
            yield event.plain_result(f"无效的参数组合: {e}")

    @filter.command("setucd <cd_time>")
    async def set_setu_cd(self, event: AstrMessageEvent, cd_time: int):
        if cd_time <= 0:
            yield event.plain_result("冷却时间必须大于 0")
            return
        self.cd = cd_time
        yield event.plain_result(f"冷却时间已设置为 {cd_time} 秒")

    @filter.command("setu_help")
    async def setu_help(self, event: AstrMessageEvent):
        help_text = """
        **高级涩图插件帮助**
        
        /setu [参数] - 获取定制涩图
        可选参数：
        • r18=yes/no - R18模式开关
        • size=small/regular/original - 图片尺寸
        • num=1-10 - 获取数量
        • tag=标签 - 指定标签
        • author=作者 - 指定画师
        
        示例：
        /setu r18=yes size=original num=3
        /setu tag=白丝 author=画师A
        /setu size=small num=5
        
        /setucd <秒数> - 设置指令冷却时间
        /setu_help - 显示本帮助
        """
        yield event.chain_result([Plain(help_text)])
