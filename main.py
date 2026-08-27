import json
import os
import sys
import yaml
from pathlib import Path
import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.api.star import StarTools

# meme_generator reads MEME_HOME while its native module is being imported.
# Bootstrap it before importing any module under core, because those modules
# import meme_generator at module scope. StarTools supplies AstrBot's
# cross-platform, plugin-specific data directory. The explicit plugin name is
# required here because AstrBot has not registered this module's metadata yet.
PLUGIN_NAME = "astrbot_plugin_meme_generator"
MEME_HOME = Path(StarTools.get_data_dir(PLUGIN_NAME))
if "meme_generator" in sys.modules:
    logger.warning(
        "meme_generator 已在资源目录初始化前被加载，MEME_HOME 可能无法在本次运行中生效"
    )
os.environ["MEME_HOME"] = str(MEME_HOME)
logger.info("表情包资源目录: %s", MEME_HOME)

from .core.meme_manager import MemeManager
from .core.meme_manager import ResourceNotReadyError
from .utils.permission_utils import PermissionUtils
from .utils.render_fallback import (
    format_help_menu_text,
    format_plugin_status_text,
    render_with_fallback,
)


PLUGIN_DIR = Path(__file__).parent
STATIC_DIR = PLUGIN_DIR / "static"
STATIC_HTML_DIR = STATIC_DIR / "html"
STATIC_DATA_DIR = STATIC_DIR / "data"


def _load_static_template(template_name: str) -> str | None:
    template_path = STATIC_HTML_DIR / template_name
    if not template_path.exists() or not template_path.is_file():
        return None
    try:
        content = template_path.read_text(encoding="utf-8")
    except Exception:
        return None

    css_map = {
        "../css/meme_help.css": STATIC_DIR / "css" / "meme_help.css",
        "../css/meme_info.css": STATIC_DIR / "css" / "meme_info.css",
    }
    for relative_path, css_path in css_map.items():
        if relative_path not in content or not css_path.exists():
            continue
        try:
            css_content = css_path.read_text(encoding="utf-8")
        except Exception:
            continue
        css_link = f'<link rel="stylesheet" href="{relative_path}">'
        content = content.replace(css_link, f"<style>\n{css_content}\n</style>")
    return content


def _load_static_data(data_file_name: str) -> dict[str, object] | None:
    data_path = STATIC_DATA_DIR / data_file_name
    if not data_path.exists() or not data_path.is_file():
        return None
    try:
        return json.loads(data_path.read_text(encoding="utf-8"))
    except Exception:
        return None




class MemeConfig:
    """表情包生成器配置管理类"""

    DEPRECATED_KEYS = (
        "enable_auto_meme",
        "auto_meme_scope",
        "auto_meme_level",
    )

    def __init__(self, config: AstrBotConfig):
        self.config = config
        self._remove_deprecated_config()
        self._load_config()

    def _remove_deprecated_config(self) -> None:
        removed = [key for key in self.DEPRECATED_KEYS if key in self.config]
        if not removed:
            return
        for key in removed:
            self.config.pop(key, None)
        self.config.save_config()
        logger.info("已清理废弃配置项: %s", ", ".join(removed))

    def _load_config(self):
        """加载配置"""
        self.enable_plugin: bool = self.config.get("enable_plugin", True)
        self.trigger_prefix: str = str(self.config.get("trigger_prefix", "") or "")
        self.generation_timeout: int = self.config.get("generation_timeout", 30)
        self.cooldown_seconds: int = self.config.get("cooldown_seconds", 3)
        self.enable_avatar_cache: bool = self.config.get("enable_avatar_cache", True)
        self.cache_expire_hours: int = self.config.get("cache_expire_hours", 24)
        self.disabled_templates: list[str] = self.config.get("disabled_templates", [])

    def save_config(self):
        """保存配置 - 只写入改动的键，避免循环引用"""
        self.config["disabled_templates"] = self.disabled_templates
        self.config["enable_plugin"] = self.enable_plugin
        self.config.save_config()

    def _save_specific_config(self, key: str, value):
        """保存特定配置项的专用方法"""
        self.config[key] = value
        self.config.save_config()

    def is_template_disabled(self, template_name: str) -> bool:
        return template_name in self.disabled_templates

    def disable_template(self, template_name: str) -> bool:
        if template_name not in self.disabled_templates:
            self.disabled_templates.append(template_name)
            self._save_specific_config("disabled_templates", self.disabled_templates)
            return True
        return False

    def enable_template(self, template_name: str) -> bool:
        if template_name in self.disabled_templates:
            self.disabled_templates.remove(template_name)
            self._save_specific_config("disabled_templates", self.disabled_templates)
            return True
        return False

    def get_disabled_templates(self) -> list[str]:
        return self.disabled_templates.copy()

    def enable_plugin_func(self) -> bool:
        if not self.enable_plugin:
            self.enable_plugin = True
            self._save_specific_config("enable_plugin", True)
            return True
        return False

    def disable_plugin_func(self) -> bool:
        if self.enable_plugin:
            self.enable_plugin = False
            self._save_specific_config("enable_plugin", False)
            return True
        return False

    def is_plugin_enabled(self) -> bool:
        return self.enable_plugin


class TemplateHandlers:
    """模板相关命令处理器"""

    def __init__(self, meme_manager: MemeManager, config: MemeConfig):
        self.meme_manager = meme_manager
        self.config = config

    async def handle_template_list(self, event: AstrMessageEvent):
        output = await self.meme_manager.generate_template_list()
        if output:
            yield event.chain_result([Comp.Image.fromBytes(output)])
        else:
            yield event.plain_result("表情包列表生成失败")

    async def handle_template_info(
        self,
        event: AstrMessageEvent,
        keyword: str | int | None = None,
    ):
        if not keyword:
            yield event.plain_result("请指定要查看的模板关键词")
            return

        template_info = await self.meme_manager.get_template_info(str(keyword))
        if not template_info:
            yield event.plain_result("未找到相关模板")
            return

        yield event.plain_result(self._build_template_info_text(template_info))

    async def handle_disable_template(
        self,
        event: AstrMessageEvent,
        template_name: str | None = None,
    ):
        if not template_name:
            yield event.plain_result("请指定要禁用的模板名称")
            return
        if not await self.meme_manager.template_manager.keyword_exists(template_name):
            yield event.plain_result(f"模板 {template_name} 不存在")
            return
        if self.config.is_template_disabled(template_name):
            yield event.plain_result(f"模板 {template_name} 已被禁用")
            return
        if self.config.disable_template(template_name):
            yield event.plain_result(f"✅ 已禁用模板: {template_name}")
        else:
            yield event.plain_result(f"❌ 禁用模板失败: {template_name}")

    async def handle_enable_template(
        self,
        event: AstrMessageEvent,
        template_name: str | None = None,
    ):
        if not template_name:
            yield event.plain_result("请指定要启用的模板名称")
            return
        if not await self.meme_manager.template_manager.keyword_exists(template_name):
            yield event.plain_result(f"模板 {template_name} 不存在")
            return
        if not self.config.is_template_disabled(template_name):
            yield event.plain_result(f"模板 {template_name} 未被禁用")
            return
        if self.config.enable_template(template_name):
            yield event.plain_result(f"✅ 已启用模板: {template_name}")
        else:
            yield event.plain_result(f"❌ 启用模板失败: {template_name}")

    async def handle_list_disabled(self, event: AstrMessageEvent):
        disabled_templates = self.config.get_disabled_templates()
        if not disabled_templates:
            yield event.plain_result("📋 当前没有禁用的模板")
            return
        yield event.plain_result(
            self._format_template_list(
                disabled_templates,
                title="🔒 禁用模板列表",
                empty_message="当前没有禁用的模板",
            )
        )

    def _format_template_list(
        self,
        templates: list,
        title: str,
        empty_message: str,
        items_per_page: int = 20,
    ) -> str:
        if not templates:
            return f"{title}\n{empty_message}"

        total_items = len(templates)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        result = f"{title}\n📊 总计: {total_items} 个模板\n"

        if total_pages > 1:
            result += f"📄 分页显示 (每页 {items_per_page} 个，共 {total_pages} 页)\n"

        result += "─" * 30 + "\n"
        page_templates = templates[:items_per_page]
        max_index_width = len(str(len(page_templates)))
        for i, template in enumerate(page_templates, 1):
            result += f"{i:>{max_index_width}}. {template}\n"

        if total_pages > 1:
            result += "─" * 30 + "\n"
            result += f"💡 提示: 当前显示第 1/{total_pages} 页"
            if total_items > items_per_page:
                result += f"，还有 {total_items - items_per_page} 个模板未显示"

        return result

    @staticmethod
    def _build_template_info_text(template_info: dict) -> str:
        meme_info = ""
        if template_info["name"]:
            meme_info += f"名称：{template_info['name']}\n"
        if template_info["keywords"]:
            meme_info += f"别名：{template_info['keywords']}\n"

        max_images = template_info["max_images"]
        min_images = template_info["min_images"]
        if max_images > 0:
            meme_info += (
                f"所需图片：{min_images}张\n"
                if min_images == max_images
                else f"所需图片：{min_images}~{max_images}张\n"
            )

        max_texts = template_info["max_texts"]
        min_texts = template_info["min_texts"]
        if max_texts > 0:
            meme_info += (
                f"所需文本：{min_texts}段\n"
                if min_texts == max_texts
                else f"所需文本：{min_texts}~{max_texts}段\n"
            )

        if template_info["default_texts"]:
            meme_info += f"默认文本：{template_info['default_texts']}\n"
        if template_info["tags"]:
            meme_info += f"标签：{template_info['tags']}\n"
        return meme_info


class GenerationHandler:
    """表情包生成命令处理器"""

    def __init__(self, meme_manager: MemeManager):
        self.meme_manager = meme_manager

    async def handle_generate_meme(self, event: AstrMessageEvent):
        try:
            image = await self.meme_manager.generate_meme(event)
            if image:
                user_id = event.get_sender_id()
                message_str = event.get_message_str()
                logger.info(
                    f"表情包生成成功 - 用户: {user_id}, 消息: "
                    f"{message_str[:50]}{'...' if len(message_str) > 50 else ''}"
                )
                yield event.chain_result([Comp.Image.fromBytes(image)])
        except ResourceNotReadyError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            user_id = event.get_sender_id()
            message_str = event.get_message_str()
            logger.error(
                f"表情包生成异常 - 用户: {user_id}, 消息: "
                f"{message_str[:50]}{'...' if len(message_str) > 50 else ''}, 错误: {e}"
            )


class AdminHandlers:
    """管理员命令处理器"""

    def __init__(self, config: MemeConfig):
        self.config = config

    async def handle_enable_plugin(self, event: AstrMessageEvent):
        if self.config.enable_plugin_func():
            yield event.plain_result("✅ 表情包生成功能已启用")
        else:
            yield event.plain_result("ℹ️ 表情包生成功能已经是启用状态")

    async def handle_disable_plugin(self, event: AstrMessageEvent):
        if self.config.disable_plugin_func():
            yield event.plain_result("🔒 表情包生成功能已禁用")
        else:
            yield event.plain_result("ℹ️ 表情包生成功能已经是禁用状态")




def load_metadata_from_yaml():
    """从metadata.yaml加载插件元数据"""
    try:
        metadata_path = Path(__file__).parent / "metadata.yaml"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


_metadata = load_metadata_from_yaml()


@register(
    _metadata.get("name"),
    _metadata.get("author"),
    _metadata.get("desc"),
    _metadata.get("version"),
    _metadata.get("repo"),
)
class MemeGeneratorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # 初始化配置管理器
        self.meme_config = MemeConfig(config)
        logger.info("表情插件初始化")

        # MEME_HOME 和插件缓存共用 AstrBot 分配的跨平台插件数据目录。
        data_dir = str(MEME_HOME)

        # 初始化核心管理器
        self.meme_manager = MemeManager(self.meme_config, data_dir)

        # 初始化命令处理器
        self.template_handlers = TemplateHandlers(self.meme_manager, self.meme_config)
        self.generation_handler = GenerationHandler(self.meme_manager)
        self.admin_handlers = AdminHandlers(self.meme_config)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口 - 清理资源"""
        await self.cleanup()
        return False  # 不抑制异常

    async def cleanup(self):
        """清理资源"""
        try:
            # 停止缓存清理任务
            await self.meme_manager.cache_manager.stop_cleanup_task()
        except (AttributeError, RuntimeError) as e:
            logger.error(f"清理缓存管理器时出错: {e}")

    @filter.command("表情帮助", alias={"meme帮助", "meme菜单"})
    async def meme_help_menu(self, event: AstrMessageEvent):
        """查看meme插件帮助菜单"""
        # 检查插件是否启用
        if not self.meme_config.is_plugin_enabled():
            if PermissionUtils.is_bot_admin(event):
                yield event.plain_result(PermissionUtils.get_plugin_disabled_message())
            return

        meme_help_tmpl = _load_static_template("meme_help.html")

        template_data = _load_static_data("meme_help.json")

        # 如果加载失败，使用默认的空数据
        if template_data is None:
            template_data = {
                "basic_commands": [],
                "admin_commands": []
            }

        if not PermissionUtils.is_bot_admin(event):
            template_data["admin_commands"] = []

        # 从metadata.yaml加载版本和作者信息
        metadata = load_metadata_from_yaml()
        template_data["version"] = metadata.get("version")
        template_data["author"] = metadata.get("author")
        template_data["trigger_prefix"] = self.meme_config.trigger_prefix

        fallback_text = format_help_menu_text(template_data)

        async def _render_help_menu() -> str:
            return await self.html_render(meme_help_tmpl, template_data)

        mode, payload = await render_with_fallback(_render_help_menu, fallback_text)
        if mode == "image":
            yield event.image_result(payload)
        else:
            logger.warning("表情帮助菜单渲染失败，已回退到纯文本输出。")
            yield event.plain_result(payload)

    @filter.command("表情列表", alias={"meme列表"})
    async def template_list(self, event: AstrMessageEvent):
        """查看所有可用的表情包模板"""
        # 检查插件是否启用
        if not self.meme_config.is_plugin_enabled():
            if PermissionUtils.is_bot_admin(event):
                yield event.plain_result(PermissionUtils.get_plugin_disabled_message())
            return

        async for result in self.template_handlers.handle_template_list(event):
            yield result

    @filter.command("表情信息", alias={"meme信息"})
    async def template_info(
            self, event: AstrMessageEvent, keyword: str | int | None = None
    ):
        """查看指定表情包模板的详细信息"""
        # 检查插件是否启用
        if not self.meme_config.is_plugin_enabled():
            if PermissionUtils.is_bot_admin(event):
                yield event.plain_result(PermissionUtils.get_plugin_disabled_message())
            return

        async for result in self.template_handlers.handle_template_info(event, keyword):
            yield result

    @filter.command("单表情禁用", alias={"单meme禁用"})
    async def disable_template(
            self, event: AstrMessageEvent, template_name: str | None = None
    ):
        """禁用指定的表情包模板（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        async for result in self.template_handlers.handle_disable_template(event, template_name):
            yield result

    @filter.command("单表情启用", alias={"单meme启用"})
    async def enable_template(
            self, event: AstrMessageEvent, template_name: str | None = None
    ):
        """启用指定的表情包模板（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        async for result in self.template_handlers.handle_enable_template(event, template_name):
            yield result

    @filter.command("禁用列表")
    async def list_disabled(self, event: AstrMessageEvent):
        """查看被禁用的模板列表（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        async for result in self.template_handlers.handle_list_disabled(event):
            yield result

    @filter.command("表情启用", alias={"meme启用"})
    async def enable_plugin(self, event: AstrMessageEvent):
        """启用表情包生成功能（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        async for result in self.admin_handlers.handle_enable_plugin(event):
            yield result

    @filter.command("表情禁用", alias={"meme禁用"})
    async def disable_plugin(self, event: AstrMessageEvent):
        """禁用表情包生成功能（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        async for result in self.admin_handlers.handle_disable_plugin(event):
            yield result

    @filter.command("表情资源", alias={"meme资源", "表情资源状态"})
    async def resource_status(self, event: AstrMessageEvent):
        """查看表情包资源的初始化/下载进度"""
        if not PermissionUtils.is_bot_admin(event):
            return
        status = self.meme_manager.resource_status
        yield event.plain_result(status.format_status())

    @filter.command("表情状态", alias={"meme状态"})
    async def plugin_info(self, event: AstrMessageEvent):
        """查看表情状态（仅限Bot管理员）"""
        # 检查管理员权限
        if not PermissionUtils.is_bot_admin(event):
            return

        # 获取统计信息
        total_templates = 0
        total_keywords = 0
        try:
            all_memes = await self.meme_manager.template_manager.get_all_memes()
            total_templates = len(all_memes)
            all_keywords = await self.meme_manager.template_manager.get_all_keywords()
            total_keywords = len(all_keywords)
        except Exception:
            pass

        # 尝试加载外部模板
        template_content = _load_static_template("meme_info.html")

        # 从metadata.yaml加载版本和作者信息
        metadata = load_metadata_from_yaml()

        # 准备模板数据
        template_data = {
            "plugin_enabled": self.meme_config.is_plugin_enabled(),
            "avatar_cache_enabled": self.meme_config.enable_avatar_cache,
            "cooldown_seconds": self.meme_config.cooldown_seconds,
            "generation_timeout": self.meme_config.generation_timeout,
            "cache_expire_hours": self.meme_config.cache_expire_hours,
            "trigger_prefix": self.meme_config.trigger_prefix,
            "disabled_templates_count": len(self.meme_config.disabled_templates),
            "total_templates": total_templates,
            "total_keywords": total_keywords,
            "version": metadata.get("version", "v1.1.0"),
            "author": metadata.get("author", "SodaSizzle")
        }

        fallback_text = format_plugin_status_text(template_data)

        async def _render_plugin_info() -> str:
            return await self.html_render(template_content, template_data)

        mode, payload = await render_with_fallback(_render_plugin_info, fallback_text)
        if mode == "image":
            yield event.image_result(payload)
        else:
            logger.warning("表情状态页面渲染失败，已回退到纯文本输出。")
            yield event.plain_result(payload)

    @filter.event_message_type(EventMessageType.ALL)
    async def generate_meme(self, event: AstrMessageEvent):
        """
        表情包生成主流程处理器
        """
        # 检查是否是管理员命令，如果是则不处理
        message_str = event.message_str.strip()
        admin_commands = [
            "启用表情包", "meme启用", "启用插件",
            "禁用表情包", "meme禁用", "禁用插件", "关闭表情包",
            "表情状态", "meme状态",
            "表情帮助", "meme帮助",
            "表情列表", "meme列表",
            "禁用列表"
        ]

        # 如果消息以管理员命令开头，则不处理
        for cmd in admin_commands:
            if message_str.startswith(cmd):
                return

        # 检查插件是否启用
        if not self.meme_config.is_plugin_enabled():
            # 插件被禁用时不响应普通用户，但Bot管理员可以看到提示
            if PermissionUtils.is_bot_admin(event):
                yield event.plain_result(PermissionUtils.get_plugin_disabled_message())
            return

        async for result in self.generation_handler.handle_generate_meme(event):
            yield result
