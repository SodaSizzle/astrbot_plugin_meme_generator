"""头像缓存管理模块"""

import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional
from astrbot.api import logger


class AvatarCache:
    """头像缓存管理器"""

    def __init__(self, cache_expire_hours: int = 24, enable_cache: bool = True, cache_dir: str = "data/cache/avatars"):
        self.cache_expire_hours = cache_expire_hours
        self.enable_cache = enable_cache
        self.cache_dir = Path(cache_dir)
        self.metadata_file = self.cache_dir / "metadata.json"

        # 创建缓存目录
        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 加载元数据
        self._metadata: Dict[str, float] = self._load_metadata()

    def _load_metadata(self) -> Dict[str, float]:
        """加载缓存元数据"""
        if not self.enable_cache or not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"加载头像缓存元数据失败: {e}")
            return {}

    def _save_metadata(self):
        """保存缓存元数据"""
        if not self.enable_cache:
            return

        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self._metadata, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONEncodeError) as e:
            logger.error(f"保存头像缓存元数据失败: {e}")

    def get_cache_key(self, user_id: str) -> str:
        """
        生成缓存键

        Args:
            user_id: 用户ID

        Returns:
            缓存键
        """
        return hashlib.md5(user_id.encode()).hexdigest()

    def _detect_image_format(self, image_data: bytes) -> str:
        """
        检测图片格式并返回对应的文件扩展名

        Args:
            image_data: 图片字节数据

        Returns:
            文件扩展名（如 .jpg, .png, .gif）
        """
        try:
            # 通过文件头字节检测图片格式
            if len(image_data) < 12:
                return '.jpg'  # 数据太短，默认jpg

            # JPEG格式检测
            if image_data[:2] == b'\xff\xd8':
                return '.jpg'

            # PNG格式检测
            elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
                return '.png'

            # GIF格式检测
            elif image_data[:6] in (b'GIF87a', b'GIF89a'):
                return '.gif'

            # BMP格式检测
            elif image_data[:2] == b'BM':
                return '.bmp'

            # WebP格式检测
            elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
                return '.webp'

            # 默认使用jpg
            else:
                return '.jpg'

        except (OSError, ValueError):
            # 检测失败时默认使用.jpg
            return '.jpg'

    def get_avatar(self, user_id: str) -> Optional[bytes]:
        """
        从缓存获取头像

        Args:
            user_id: 用户ID

        Returns:
            头像字节数据，未找到或过期返回None
        """
        if not self.enable_cache:
            return None

        cache_key = self.get_cache_key(user_id)

        # 查找对应的缓存文件（可能有不同的扩展名）
        cache_file = None
        possible_extensions = ['.jpg', '.png', '.gif', '.bmp', '.webp']

        for ext in possible_extensions:
            potential_file = self.cache_dir / f"{cache_key}{ext}"
            if potential_file.exists():
                cache_file = potential_file
                break

        # 检查文件是否存在
        if not cache_file or cache_key not in self._metadata:
            return None

        # 检查是否过期
        timestamp = self._metadata[cache_key]
        current_time = time.time()
        expire_time = self.cache_expire_hours * 3600  # 转换为秒

        if (current_time - timestamp) > expire_time:
            # 过期，删除缓存
            self._remove_cache_file(cache_key)
            return None

        # 读取头像数据
        try:
            with open(cache_file, 'rb') as f:
                return f.read()
        except (OSError, IOError) as e:
            logger.error(f"读取头像缓存失败: {e}")
            self._remove_cache_file(cache_key)
            return None

    def set_avatar(self, user_id: str, avatar_data: bytes):
        """
        设置头像缓存

        Args:
            user_id: 用户ID
            avatar_data: 头像字节数据
        """
        if not self.enable_cache:
            return

        cache_key = self.get_cache_key(user_id)

        # 检测图片格式并生成对应的文件名
        image_ext = self._detect_image_format(avatar_data)
        cache_file = self.cache_dir / f"{cache_key}{image_ext}"
        current_time = time.time()

        try:
            # 先删除可能存在的旧格式文件
            self._remove_old_cache_files(cache_key)

            # 保存头像数据到文件
            with open(cache_file, 'wb') as f:
                f.write(avatar_data)

            # 更新元数据
            self._metadata[cache_key] = current_time
            self._save_metadata()

        except (OSError, IOError) as e:
            logger.error(f"保存头像缓存失败: {e}")
            # 清理可能的部分文件
            if cache_file.exists():
                cache_file.unlink(missing_ok=True)

    def _remove_old_cache_files(self, cache_key: str):
        """删除指定cache_key的所有可能格式的旧文件"""
        possible_extensions = ['.jpg', '.png', '.gif', '.bmp', '.webp']

        for ext in possible_extensions:
            old_file = self.cache_dir / f"{cache_key}{ext}"
            if old_file.exists():
                old_file.unlink(missing_ok=True)

    def _remove_cache_file(self, cache_key: str):
        """移除缓存文件和元数据"""
        # 删除所有可能格式的文件
        self._remove_old_cache_files(cache_key)

        # 删除元数据
        self._metadata.pop(cache_key, None)
        self._save_metadata()

    def remove_avatar(self, user_id: str):
        """
        移除指定用户的头像缓存

        Args:
            user_id: 用户ID
        """
        cache_key = self.get_cache_key(user_id)
        self._remove_cache_file(cache_key)

    def clear_expired_cache(self):
        """清理过期的缓存"""
        if not self.enable_cache:
            return

        current_time = time.time()
        expire_time = self.cache_expire_hours * 3600
        expired_keys = []

        for cache_key, timestamp in self._metadata.items():
            if (current_time - timestamp) > expire_time:
                expired_keys.append(cache_key)

        for key in expired_keys:
            self._remove_cache_file(key)

    def clear_all_cache(self):
        """清空所有缓存"""
        if not self.enable_cache:
            return

        # 删除所有缓存文件
        for cache_key in list(self._metadata.keys()):
            self._remove_cache_file(cache_key)

        # 清空元数据
        self._metadata.clear()
        self._save_metadata()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息

        Returns:
            缓存统计信息字典
        """
        # 计算缓存目录大小
        total_size = 0
        if self.cache_dir.exists():
            # 统计所有图片格式的缓存文件
            patterns = ["*.jpg", "*.png", "*.gif", "*.bmp", "*.webp"]
            for pattern in patterns:
                for file_path in self.cache_dir.glob(pattern):
                    try:
                        total_size += file_path.stat().st_size
                    except OSError:
                        pass

        return {
            "total_cached": len(self._metadata),
            "cache_enabled": self.enable_cache,
            "expire_hours": self.cache_expire_hours,
            "cache_size_bytes": total_size,
            "cache_dir": str(self.cache_dir)
        }

    def update_settings(self, cache_expire_hours: int, enable_cache: bool):
        """
        更新缓存设置

        Args:
            cache_expire_hours: 缓存过期时间(小时)
            enable_cache: 是否启用缓存
        """
        self.cache_expire_hours = cache_expire_hours
        self.enable_cache = enable_cache

        if not enable_cache:
            self.clear_all_cache()
        else:
            # 如果启用缓存，确保目录存在
            self.cache_dir.mkdir(parents=True, exist_ok=True)
