"""参数收集模块"""

import base64
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Tuple, Union
from meme_generator import Meme
from meme_generator import Image as MemeImage
from astrbot.api import logger
from astrbot.core.platform import AstrMessageEvent
import astrbot.core.message.components as Comp
from ..utils.platform_utils import PlatformUtils

try:
    from astrbot.core.utils.quoted_message import extract_quoted_message_images
except Exception:  # pragma: no cover - fallback for older AstrBot versions
    extract_quoted_message_images = None


class ParamCollector:
    """参数收集器"""

    def __init__(self, network_utils=None):
        self.network_utils = network_utils

    async def collect_params(
            self,
            event: AstrMessageEvent,
            keyword: str,
            meme: Meme,
            keyword_prefix: str = "",
    ) -> Tuple[List[MemeImage], List[str], Dict[str, Union[bool, str, int, float]]]:
        """
        收集表情包生成所需的参数
        
        Args:
            event: 消息事件
            keyword: 触发关键词
            meme: 表情包模板
            
        Returns:
            (图片列表, 文本列表, 选项参数)
        """
        meme_images: List[MemeImage] = []
        texts: List[str] = []
        options: Dict[str, Union[bool, str, int, float]] = {}

        params = meme.info.params
        min_images: int = params.min_images  # noqa: F841
        max_images: int = params.max_images
        min_texts: int = params.min_texts
        max_texts: int = params.max_texts
        default_texts: List[str] = params.default_texts

        messages = event.get_messages()
        send_id: str = event.get_sender_id()
        self_id: str = event.get_self_id()
        sender_name: str = str(event.get_sender_name())

        target_ids: List[str] = []
        target_names: List[str] = []

        async def _process_segment(_seg, name):
            """解析消息组件并提取相关参数"""
            if isinstance(_seg, Comp.Image):
                await self._process_image_segment(_seg, name, meme_images)
            elif isinstance(_seg, Comp.At):
                await self._process_at_segment(_seg, event, self_id, target_ids, target_names, options, meme_images)
            elif isinstance(_seg, Comp.Plain):
                self._process_plain_segment(_seg, keyword, texts, keyword_prefix)

        reply_seg = next((seg for seg in messages if isinstance(seg, Comp.Reply)), None)
        await self._process_reply_segments(event, reply_seg, _process_segment, meme_images)

        # 处理当前消息内容
        for seg in messages:
            await _process_segment(seg, sender_name)

        # 获取发送者的详细信息
        if not target_ids:
            if result := await PlatformUtils.get_user_extra_info(event, send_id):
                nickname, sex = result
                options["name"], options["gender"] = nickname, sex
                target_names.append(nickname)

        if not target_names:
            target_names.append(sender_name)

        # 智能补全图片参数（优先使用用户头像）
        await self._auto_fill_images(event, send_id, self_id, sender_name, meme_images, max_images)

        # 智能补全文本参数（使用昵称和默认文本）
        self._auto_fill_texts(texts, target_names, default_texts, min_texts, max_texts)

        return meme_images, texts, options

    async def collect_auto_params(
            self,
            event: AstrMessageEvent,
            meme: Meme,
            text_candidates: List[str] | None = None
    ) -> Tuple[List[MemeImage], List[str], Dict[str, Union[bool, str, int, float]]]:
        """Collect parameters for auto meme rendering without keyword parsing."""
        meme_images: List[MemeImage] = []
        texts: List[str] = []
        options: Dict[str, Union[bool, str, int, float]] = {}

        params = meme.info.params
        max_images: int = params.max_images
        min_texts: int = params.min_texts
        max_texts: int = params.max_texts
        default_texts: List[str] = params.default_texts

        messages = event.get_messages()
        send_id: str = event.get_sender_id()
        self_id: str = event.get_self_id()
        sender_name: str = str(event.get_sender_name())

        target_ids: List[str] = []
        target_names: List[str] = []

        async def _process_segment(_seg, name):
            if isinstance(_seg, Comp.Image):
                await self._process_image_segment(_seg, name, meme_images)
            elif isinstance(_seg, Comp.At):
                await self._process_at_segment(
                    _seg,
                    event,
                    self_id,
                    target_ids,
                    target_names,
                    options,
                    meme_images,
                )

        reply_seg = next((seg for seg in messages if isinstance(seg, Comp.Reply)), None)
        await self._process_reply_segments(event, reply_seg, _process_segment, meme_images)

        for seg in messages:
            await _process_segment(seg, sender_name)

        if not target_ids:
            if result := await PlatformUtils.get_user_extra_info(event, send_id):
                nickname, sex = result
                options["name"], options["gender"] = nickname, sex
                target_names.append(nickname)

        if not target_names:
            target_names.append(sender_name)

        await self._auto_fill_images(
            event,
            send_id,
            self_id,
            sender_name,
            meme_images,
            max_images,
        )

        for candidate in text_candidates or []:
            candidate = (candidate or "").strip()
            if candidate:
                texts.append(candidate)

        self._auto_fill_texts(texts, target_names, default_texts, min_texts, max_texts)
        return meme_images, texts, options

    async def _process_image_segment(self, seg: Comp.Image, name: str, meme_images: List[MemeImage]):
        """处理图片组件"""
        if hasattr(seg, "url") and seg.url:
            await self._append_image_ref(seg.url, name, meme_images)
            return

        for attr in ("file", "path"):
            image_ref = getattr(seg, attr, None)
            if image_ref:
                await self._append_image_ref(image_ref, name, meme_images)
                return

    async def _process_reply_segments(
            self,
            event: AstrMessageEvent,
            reply_seg: Comp.Reply | None,
            process_segment: Callable[[object, str], Awaitable[None]],
            meme_images: List[MemeImage],
    ) -> None:
        """处理引用消息内容，必要时回退到引用消息提取器。"""
        if not reply_seg:
            return

        reply_image_count = len(meme_images)
        for attr in ("chain", "message", "origin", "content"):
            payload = getattr(reply_seg, attr, None)
            if isinstance(payload, list):
                for seg in payload:
                    await process_segment(seg, "引用用户")
                break

        if len(meme_images) > reply_image_count or extract_quoted_message_images is None:
            return

        try:
            image_refs = await extract_quoted_message_images(event, reply_seg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("引用图片回退提取失败: %s", exc)
            return

        for image_ref in image_refs:
            await self._append_image_ref(image_ref, "引用用户", meme_images)

    async def _append_image_ref(
            self,
            image_ref: str | bytes,
            name: str,
            meme_images: List[MemeImage],
    ) -> None:
        """把图片引用解析为图片字节后加入参数列表。"""
        file_content: bytes | None = None

        if isinstance(image_ref, bytes):
            file_content = image_ref
        elif isinstance(image_ref, str):
            if image_ref.startswith("base64://"):
                try:
                    file_content = base64.b64decode(image_ref[len("base64://"):])
                except Exception:  # noqa: BLE001
                    return
            elif image_ref.startswith(("http://", "https://")):
                if self.network_utils:
                    file_content = await self.network_utils.download_image(image_ref)
            else:
                image_path = Path(image_ref)
                if image_path.is_file():
                    try:
                        file_content = image_path.read_bytes()
                    except OSError:
                        return
                else:
                    try:
                        file_content = base64.b64decode(image_ref, validate=True)
                    except Exception:  # noqa: BLE001
                        return

        if isinstance(file_content, bytes):
            meme_images.append(MemeImage(name, file_content))

    async def _process_at_segment(
            self,
            seg: Comp.At,
            event: AstrMessageEvent,
            self_id: str,
            target_ids: List[str],
            target_names: List[str],
            options: Dict[str, Union[bool, str, int, float]],
            meme_images: List[MemeImage]
    ):
        """处理@组件"""
        seg_qq = str(seg.qq)
        if seg_qq != self_id:
            target_ids.append(seg_qq)
            if self.network_utils and (at_avatar := await self.network_utils.get_avatar(seg_qq)):
                # 获取被@用户的详细信息
                if result := await PlatformUtils.get_user_extra_info(event, seg_qq):
                    nickname, sex = result
                    options["name"], options["gender"] = nickname, sex
                    target_names.append(nickname)
                    meme_images.append(MemeImage(nickname, at_avatar))

    def _process_plain_segment(
            self,
            seg: Comp.Plain,
            keyword: str,
            texts: List[str],
            keyword_prefix: str = "",
    ):
        """处理纯文本组件"""
        plains: List[str] = seg.text.strip().split()
        prefixed_keyword = f"{keyword_prefix}{keyword}" if keyword_prefix else keyword
        for text in plains:
            if text not in {keyword, prefixed_keyword}:  # 排除关键词本身
                texts.append(text)

    async def _auto_fill_images(
            self,
            event: AstrMessageEvent,
            send_id: str,
            self_id: str,
            sender_name: str,
            meme_images: List[MemeImage],
            max_images: int
    ):
        """自动补全图片参数"""
        if self.network_utils and len(meme_images) < max_images:
            if use_avatar := await self.network_utils.get_avatar(send_id):
                meme_images.insert(0, MemeImage(sender_name, use_avatar))
        if self.network_utils and len(meme_images) < max_images:
            if bot_avatar := await self.network_utils.get_avatar(self_id):
                meme_images.insert(0, MemeImage("机器人", bot_avatar))
        # 截取到最大数量
        meme_images[:] = meme_images[:max_images]

    def _auto_fill_texts(
            self,
            texts: List[str],
            target_names: List[str],
            default_texts: List[str],
            min_texts: int,
            max_texts: int
    ):
        """自动补全文本参数"""
        if len(texts) < min_texts and target_names:
            texts.extend(target_names)
        if len(texts) < min_texts and default_texts:
            texts.extend(default_texts)
        # 截取到最大数量
        texts[:] = texts[:max_texts]
