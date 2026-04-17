"""表情包管理器模块"""

import asyncio
from pathlib import Path
from typing import Optional
from meme_generator.tools import MemeProperties, MemeSortBy, render_meme_list
from meme_generator.resources import check_resources_in_background
from astrbot.api import logger
from astrbot.core.platform import AstrMessageEvent
import astrbot.core.message.components as Comp

from .template_manager import TemplateManager
from .param_collector import ParamCollector
from .image_generator import ImageGenerator
from ..utils.image_utils import ImageUtils
from ..utils.cooldown_manager import CooldownManager
from ..utils.avatar_cache import AvatarCache
from ..utils.network_utils import NetworkUtils
from ..utils.cache_manager import CacheManager
from ..utils.resource_status import ResourceStatus


class ResourceNotReadyError(RuntimeError):
    """Raised when meme resources are not ready for user-triggered generation."""


class MemeManager:
    """表情包管理器 - 核心业务逻辑"""
    
    def __init__(self, config, data_dir: str = None):
        self.config = config
        self.template_manager = TemplateManager()
        self.image_generator = ImageGenerator()
        self.cooldown_manager = CooldownManager(config.cooldown_seconds)
        self.resource_status = ResourceStatus()

        # 初始化头像缓存和网络工具
        # 使用传入的数据目录，如果没有则使用默认路径
        if data_dir:
            cache_dir = Path(data_dir) / "cache" / "meme_avatars"
        else:
            cache_dir = Path("data/cache/meme_avatars")  # 默认路径

        self.avatar_cache = AvatarCache(
            cache_expire_hours=config.cache_expire_hours,
            enable_cache=config.enable_avatar_cache,
            cache_dir=str(cache_dir)
        )
        self.network_utils = NetworkUtils(self.avatar_cache)

        # 初始化缓存管理器，使用配置的缓存过期时间
        self.cache_manager = CacheManager(
            self.avatar_cache,
            cleanup_interval_hours=config.cache_expire_hours
        )

        # 初始化参数收集器（传入网络工具）
        self.param_collector = ParamCollector(self.network_utils)

        # 初始化资源检查（固定启用）
        logger.info("🎭 表情包插件正在初始化...")
        # 异步启动资源检查，并在完成后刷新模板
        asyncio.create_task(self._check_resources_and_refresh())

        # 启动缓存清理任务
        if config.enable_avatar_cache:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.cache_manager.start_cleanup_task())
            except RuntimeError:
                # 如果没有运行的事件循环，稍后启动
                pass

    async def _check_resources_and_refresh(self):
        """检查资源并在完成后刷新模板"""
        self.resource_status.mark_started()
        heartbeat_task = asyncio.create_task(self._log_resource_heartbeat())
        try:
            await asyncio.to_thread(check_resources_in_background)
            await self.template_manager.refresh_templates()
            all_memes = await self.template_manager.get_all_memes()
            self.resource_status.mark_ready(len(all_memes))
            if self.resource_status.ready:
                logger.info(
                    "✅ 表情包资源就绪 - 共 %d 个模板，耗时 %.1f 秒",
                    self.resource_status.total_memes,
                    self.resource_status.elapsed_seconds(),
                )
            else:
                logger.warning("⚠️ 表情包资源检查完成，但未加载到任何模板")
        except Exception as e:
            self.resource_status.mark_failed(str(e))
            logger.error(f"❌ 表情包资源检查失败: {e}")
            logger.warning("⚠️ 部分表情包模板可能无法正常使用，建议检查网络连接后重启插件")
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _log_resource_heartbeat(self, interval: float = 10.0):
        """资源下载期间，定期把进度打印到日志"""
        try:
            while self.resource_status.in_progress:
                await asyncio.sleep(interval)
                if not self.resource_status.in_progress:
                    break
                elapsed = self.resource_status.elapsed_seconds()
                logger.info(
                    "⏳ 表情包资源初始化中 - 已耗时 %.0f 秒，首次启动需下载资源包",
                    elapsed,
                )
        except asyncio.CancelledError:
            raise

    async def get_resource_block_message(self, message_str: str) -> str | None:
        keyword = await self.template_manager.find_keyword(message_str)
        return self.resource_status.get_block_message(keyword_matched=bool(keyword))
    
    async def generate_template_list(self) -> bytes | None:
        """
        生成表情包模板列表图片
        
        Returns:
            模板列表图片字节数据，失败返回None
        """
        sort_by = MemeSortBy.KeywordsPinyin

        meme_properties: dict[str, MemeProperties] = {}
        all_memes = await self.template_manager.get_all_memes()
        for meme in all_memes:
            properties = MemeProperties(disabled=False, hot=False, new=False)
            meme_properties[meme.key] = properties

        output: bytes | None = await asyncio.to_thread(
            render_meme_list,  # type: ignore
            meme_properties=meme_properties,
            exclude_memes=[],
            sort_by=sort_by,
            sort_reverse=False,
            text_template="{index}. {keywords}",
            add_category_icon=True,
        )
        return output
    
    async def get_template_info(self, keyword: str) -> Optional[dict]:
        """
        获取模板详细信息

        Args:
            keyword: 模板关键词

        Returns:
            模板信息字典，未找到返回None
        """
        if not await self.template_manager.keyword_exists(keyword):
            return None

        meme = await self.template_manager.find_meme(keyword)
        if not meme:
            return None
        
        info = meme.info
        params = info.params
        
        template_info = {
            "name": meme.key,
            "keywords": info.keywords,
            "min_images": params.min_images,
            "max_images": params.max_images,
            "min_texts": params.min_texts,
            "max_texts": params.max_texts,
            "default_texts": params.default_texts,
            "tags": list(info.tags),
        }

        # 不再生成预览图
        template_info["preview"] = None

        return template_info
    
    async def generate_meme(self, event: AstrMessageEvent) -> Optional[bytes]:
        """
        生成表情包主流程

        Args:
            event: 消息事件

        Returns:
            生成的表情包图片字节数据，失败返回None
        """
        # 检查用户冷却
        user_id = event.get_sender_id()
        if self.cooldown_manager.is_user_in_cooldown(user_id):
            # 用户在冷却期内，静默返回
            return None

        # 提取消息内容
        message_str = event.get_message_str()
        if not message_str:
            return None
        
        # 查找关键词
        keyword = await self.template_manager.find_keyword(message_str)
        if not keyword:
            return None

        block_message = self.resource_status.get_block_message(keyword_matched=True)
        if block_message:
            raise ResourceNotReadyError(block_message)

        if self.config.is_template_disabled(keyword):
            return None

        # 查找模板
        meme = await self.template_manager.find_meme(keyword)
        if not meme:
            return None
        
        # 收集生成参数
        meme_images, texts, options = await self.param_collector.collect_params(event, keyword, meme)
        
        # 生成表情包
        image: bytes = await self.image_generator.generate_image(
            meme, meme_images, texts, options, self.config.generation_timeout
        )
        
        # 自动压缩处理
        try:
            compressed = ImageUtils.compress_image(image)
            if compressed:
                image = compressed
        except Exception:
            pass  # 压缩失败时使用原图

        # 记录用户使用时间
        self.cooldown_manager.record_user_use(user_id)

        return image

    async def generate_meme_by_template_key(
        self,
        event: AstrMessageEvent,
        template_key: str,
        text_candidates: list[str] | None = None,
    ) -> Optional[bytes]:
        """Generate a meme directly from a selected template key."""
        meme = await self.template_manager.find_meme(template_key)
        if not meme:
            return None
        if self.config.is_template_disabled(template_key):
            return None

        meme_images, texts, options = await self.param_collector.collect_auto_params(
            event=event,
            meme=meme,
            text_candidates=text_candidates or [],
        )

        image: bytes = await self.image_generator.generate_image(
            meme,
            meme_images,
            texts,
            options,
            self.config.generation_timeout,
        )
        try:
            compressed = ImageUtils.compress_image(image)
            if compressed:
                image = compressed
        except Exception:
            pass
        return image
