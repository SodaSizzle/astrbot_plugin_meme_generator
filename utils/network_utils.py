"""网络请求工具模块"""

import aiohttp
from typing import Optional
from astrbot.api import logger
from .avatar_cache import AvatarCache


class NetworkUtils:
    """网络请求工具类"""

    def __init__(self, avatar_cache: Optional[AvatarCache] = None):
        self.avatar_cache = avatar_cache

    async def download_image(self, url: str) -> bytes | None:
        """
        下载图片
        
        Args:
            url: 图片URL
            
        Returns:
            图片字节数据，失败返回None
        """
        url = url.replace("https://", "http://")
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                img_bytes = await response.read()
                return img_bytes
        except Exception as e:
            logger.error(f"图片下载失败: {e}")
            return None

    async def get_avatar(self, user_id: str) -> bytes | None:
        """
        下载用户头像(支持缓存)

        Args:
            user_id: 用户ID

        Returns:
            头像字节数据，失败返回None
        """
        # QQ 头像接口只接受数字 QQ 号。其他平台的用户 ID 不应随机
        # 映射到陌生 QQ 用户，否则同一用户每次可能得到不同头像。
        if not user_id.isascii() or not user_id.isdigit():
            logger.debug("跳过非 QQ 用户 ID 的头像下载: %s", user_id)
            return None

        # 只读取有效 QQ 号对应的缓存，避免沿用历史异常缓存。
        if self.avatar_cache:
            cached_avatar = self.avatar_cache.get_avatar(user_id)
            if cached_avatar:
                return cached_avatar

        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(avatar_url, timeout=10)
                response.raise_for_status()
                avatar_data = await response.read()

                # 缓存头像数据
                if self.avatar_cache and avatar_data:
                    self.avatar_cache.set_avatar(user_id, avatar_data)

                return avatar_data
        except Exception as e:
            logger.error(f"下载头像失败: {e}")
            return None
