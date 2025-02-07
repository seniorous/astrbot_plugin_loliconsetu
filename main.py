from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import httpx
import json
import asyncio
import re

@register("loliconsetu", "seniorous", "支持参数自选的涩图插件", "2.0.0")
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
            "tag": [],
            "author": "",
            "proxy": "i.pixiv.re",
            "ai": False,
            "anime": "",
            "character": ""
        }
        
        # 使用改进版正则匹配参数，支持带空格的引号值和数组参数
        # 增强版参数解析正则，支持更灵活的参数格式
        matches = re.findall(
            r'\b(r18|size|num|tag|author|proxy|ai|anime|character)\s*=\s*'
            r'("[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'|\[.*?\]|\S+)',
            params,
            re.IGNORECASE
        )
        
        for key, value in matches:
            key = key.lower()  # 统一转为小写
            # 去除引号并处理特殊字符
            value = value.strip('"\'').strip()
            
            if key == "r18":
                if value.lower() in ["true", "yes", "1"]:
                    args["r18"] = 1
                elif value.lower() in ["false", "no", "0"]:
                    args["r18"] = 0
                else:
                    raise ValueError(f"无效的R18参数值：{value}")
            elif key == "size":
                lower_val = value.lower()
                if lower_val in ["original", "regular", "small"]:
                    args["size"] = lower_val
                else:
                    raise ValueError(f"无效的尺寸参数：{value}，可选值：small/regular/original")
            elif key == "num":
                try:
                    num = int(value)
                    if 1 <= num <= 10:
                        args["num"] = num
                    else:
                        raise ValueError("数量超出范围 (1-10)")
                except ValueError as e:
                    raise ValueError(f"无效的数量参数：{value} ({str(e)})")
            elif key == "tag":
                # 支持逗号分隔的多个标签，并过滤空值
                args["tag"] = [tag.strip() for tag in value.split(',') if tag.strip()]
            elif key == "author":
                args["author"] = value
            elif key == "proxy":
                args["proxy"] = value
            elif key == "ai":
                args["ai"] = value.lower() in ["true", "yes", "1"]
            elif key == "anime":
                args["anime"] = value
            elif key == "character":
                args["character"] = value
        
        return args

    @filter.command("setu <params>")
    async def setu(self, event: AstrMessageEvent, params: str = ""):
        user_id = event.get_sender_id()
        now = asyncio.get_event_loop().time()
        debug_info = []  # 调试信息收集

        try:
            # 调试信息：记录原始参数
            debug_info.append(f"原始参数: {params}")

            # 检查冷却时间
            if user_id in self.last_usage and (now - self.last_usage[user_id]) < self.cd:
                remaining_time = self.cd - (now - self.last_usage[user_id])
                yield event.plain_result(f"冷却中，请等待 {remaining_time:.1f} 秒后重试。")
                return

            # 解析参数
            api_params = self.parse_setu_params(params)
            query_params = {
                "r18": api_params['r18'],
                "size": api_params['size'],
                "num": api_params['num'],
                "ai_illust": api_params['ai'],  # 使用直接取值代替get方法
                "anime": api_params['anime'],
                "character": api_params['character']
            }
            if api_params['tag']:
                query_params["tag"] = ",".join(api_params['tag'])  # 将列表转为逗号分隔字符串
                
            # 新增参数处理
            if api_params['anime']:
                query_params["anime"] = api_params['anime']
            if api_params['character']:
                query_params["character"] = api_params['character'] 
            if api_params['author']:
                query_params["author"] = api_params['author']
            if api_params['proxy']:
                query_params["proxy"] = api_params['proxy']
            
            # 配置超时和重试参数
            # 优化超时和重试配置
            timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0)
            retry_strategy = httpx.AsyncRetry(
                max_retries=3,
                status_forcelist=[500, 502, 503, 504, 524, 529],
                allowed_methods=["GET"],
                backoff_factor=1.5
            )
            
            async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=5)) as client:
                for attempt in range(3):  # 总尝试次数=重试次数+1
                    try:
                        resp = await client.get(
                            "https://api.lolicon.app/setu/v2",
                            params=query_params,
                            retries=retry_strategy
                        )
                        resp.raise_for_status()
                        break  # 请求成功则跳出重试循环
                    except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                        if attempt >= 2:
                            raise RuntimeError(f"API请求超时（尝试{attempt+1}次）") from e
                        await asyncio.sleep(1.5 * (attempt + 1))  # 指数退避
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code in [502, 503, 504] and attempt < 2:
                            await asyncio.sleep(2)
                            continue
                        raise
                data = resp.json()
                
                if data['data']:
                    chains = []
                    for setu_data in data['data'][:api_params['num']]:  # 限制最大返回数量
                        image_url = setu_data['urls'][api_params['size']].replace("i.pixiv.cat", api_params['proxy'])
                        chain = [
                            At(qq=event.get_sender_id()),
                            Plain(f"参数设置：R18={'开启' if api_params['r18'] else '关闭'} 尺寸={api_params['size']} AI生成={'是' if api_params['ai'] else '否'}\n"),
                            Plain(f"代理服务：{api_params['proxy']}\n"),
                            Plain(f"动画作品：{api_params['anime']} 角色：{api_params['character']}\n"),
                            Plain(f"PID：{setu_data['pid']} | 作者：{setu_data['author']} | 标签：{', '.join(setu_data['tags'])}\n"),
                            Image.fromURL(image_url, size=api_params['size'], file_type='image'),
                        ]
                        chains.append(chain)
                    
                    # 发送所有结果（自动间隔0.5秒）
                    for i, chain in enumerate(chains):
                        if i > 0:
                            await asyncio.sleep(0.5)  # 防止消息轰炸
                        yield event.chain_result(chain)  # 恢复使用yield返回消息结果
                    self.last_usage[user_id] = now
                else:
                    yield event.plain_result("没有找到符合要求的涩图。")
        except httpx.HTTPError as e:
            yield event.plain_result(f"API请求失败: {e}")
        except json.JSONDecodeError as e:
            yield event.plain_result(f"响应解析错误: {e}")
        except (KeyError, ValueError) as e:
            yield event.chain_result([
                Plain("参数解析错误：\n"),
                Plain(f"• 错误类型：{type(e).__name__}\n"),
                Plain(f"• 错误详情：{str(e)}\n"),
                Plain("常见错误原因：\n"),
                Plain("1. 参数格式不正确（缺少=号或值未加引号）\n"),
                Plain("2. 使用了不支持的参数值（如size=invalid）\n"), 
                Plain("3. 数值超出允许范围（如num=20）\n"),
                Plain("请参考帮助文档检查参数格式：\n"),
                Plain("/setu_help\n"),
                Plain("正确示例：/setu r18=yes size=original num=3")
            ])

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
        • r18=yes/no - R18模式开关（默认关闭）
        • size=small/regular/original - 图片尺寸（默认regular）
        • num=1-10 - 获取数量（默认1）
        • tag=标签1,标签2 - 指定多个标签（逗号分隔）
        • author=作者名 - 指定画师名称
        • proxy=代理地址 - 自定义图片代理（默认i.pixiv.re）
        • ai=yes/no - 是否AI生成（默认no）
        • anime=动画名 - 指定所属动画作品
        • character=角色名 - 指定角色名称
        
        示例：
        /setu r18=yes size=original num=3 ai=yes  # 获取3张R18原图AI生成
        /setu tag=白丝,女仆 author="画师A"  # 白丝女仆题材且指定画师
        /setu anime="刀剑神域" character="亚丝娜"  # 指定动画和角色
        /setu proxy=px2.rainchan.win num=5  # 使用指定代理获取5张
        /setu size=small ai=no  # 获取小尺寸非AI生成
        /setu tag=泳装,夏日 author="画师B" num=2  # 多标签组合查询
        
        /setucd <秒数> - 设置指令冷却时间（管理员权限）
        /setu_help - 显示本帮助
        
        注意：
        1. 带空格的参数值需要用引号包裹（如author="画师 A"）
        2. tag支持多个标签，用逗号分隔（如tag=白丝,女仆）
        3. 默认冷却时间10秒，管理员可修改
        """
        yield event.chain_result([Plain(help_text)])
