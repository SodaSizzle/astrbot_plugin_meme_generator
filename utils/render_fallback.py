from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def render_with_fallback(
    render_func: Callable[[], Awaitable[str]],
    fallback_text: str,
) -> tuple[str, str]:
    """Render an image when possible, otherwise fall back to plain text."""
    try:
        return "image", await render_func()
    except Exception:
        return "text", fallback_text


def format_help_menu_text(template_data: dict[str, Any]) -> str:
    version = template_data.get("version") or "unknown"
    author = template_data.get("author") or "unknown"
    trigger_prefix = template_data.get("trigger_prefix") or ""
    basic_commands = _format_command_lines(template_data.get("basic_commands", []))
    admin_commands = _format_command_lines(template_data.get("admin_commands", []))
    has_admin_commands = bool(
        isinstance(template_data.get("admin_commands"), list)
        and template_data.get("admin_commands")
    )

    lines = [
        "Meme 表情菜单",
        f"版本：{version} | 作者：{author}",
        "",
        "基础命令：",
        *basic_commands,
    ]
    if has_admin_commands:
        lines.extend(
            [
                "",
                "管理员命令：",
                *admin_commands,
            ]
        )

    lines.extend(
        [
            "",
            "使用建议：",
            (
                "1. 直接发送表情包关键词即可生成，例如“加载中”或“挠头”。"
                if not trigger_prefix
                else f"1. 当前需携带触发前缀“{trigger_prefix}”生成，例如“{trigger_prefix}加载中”。"
            ),
            "2. 支持 @用户 自动获取头像，也可以上传图片作为输入。",
            "3. 引用他人消息时，可直接沿用对方头像与昵称信息。",
            "4. 帮助、列表、信息和管理命令不受表情触发前缀影响。",
        ]
    )
    return "\n".join(lines)


def format_plugin_status_text(template_data: dict[str, Any]) -> str:
    version = template_data.get("version") or "unknown"
    author = template_data.get("author") or "unknown"
    plugin_status = "启用" if template_data.get("plugin_enabled") else "禁用"
    avatar_cache_status = "开启" if template_data.get("avatar_cache_enabled") else "关闭"
    trigger_prefix = template_data.get("trigger_prefix") or ""
    trigger_prefix_display = trigger_prefix if trigger_prefix else "未启用"

    lines = [
        "Meme 插件状态",
        f"版本：{version} | 作者：{author}",
        "",
        "运行状态：",
        f"插件状态：{plugin_status}",
        f"头像缓存：{avatar_cache_status}",
        "",
        "配置参数：",
        f"触发前缀：{trigger_prefix_display}",
        f"冷却时间：{template_data.get('cooldown_seconds', 0)}秒",
        f"生成超时：{template_data.get('generation_timeout', 0)}秒",
        f"缓存过期：{template_data.get('cache_expire_hours', 0)}小时",
        f"禁用模板：{template_data.get('disabled_templates_count', 0)}个",
        "",
        "统计信息：",
        f"可用模板：{template_data.get('total_templates', 0)}",
        f"关键词数：{template_data.get('total_keywords', 0)}",
    ]
    return "\n".join(lines)


def _format_command_lines(commands: list[dict[str, Any]] | Any) -> list[str]:
    if not isinstance(commands, list) or not commands:
        return ["- 暂无数据"]

    lines: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            continue
        name = str(command.get("name") or "未命名命令")
        desc = str(command.get("desc") or "无说明")
        lines.append(f"- {name}：{desc}")

    return lines or ["- 暂无数据"]
