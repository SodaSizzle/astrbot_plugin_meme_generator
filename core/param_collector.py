"""参数收集模块"""

import base64
from typing import List, Dict, Union, Tuple
from meme_generator import Meme
from meme_generator import Image as MemeImage
from astrbot.core.platform import AstrMessageEvent
import astrbot.core.message.components as Comp
from ..utils.platform_utils import PlatformUtils


class ParamCollector:
    """参数收集器"""

    def __init__(self, network_utils=None):
        self.network_utils = network_utils

    async def collect_params(
            self,
            event: AstrMessageEvent,
            keyword: str,
            meme: Meme
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
                self._process_plain_segment(_seg, keyword, texts)

        # 处理引用消息内容
        reply_seg = next((seg for seg in messages if isinstance(seg, Comp.Reply)), None)
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                await _process_segment(seg, "引用用户")

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
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                await _process_segment(seg, "引用用户")

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
            img_url = seg.url
            if self.network_utils and (file_content := await self.network_utils.download_image(img_url)):
                meme_images.append(MemeImage(name, file_content))

        elif hasattr(seg, "file"):
            file_content = seg.file
            if isinstance(file_content, str):
                if file_content.startswith("base64://"):
                    file_content = file_content[len("base64://"):]
                file_content = base64.b64decode(file_content)
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

    def _process_plain_segment(self, seg: Comp.Plain, keyword: str, texts: List[str]):
        """处理纯文本组件"""
        plains: List[str] = seg.text.strip().split()
        for text in plains:
            if text != keyword:  # 排除关键词本身
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
