from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class ResourceStatus:
    in_progress: bool = True
    ready: bool = False
    last_error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    total_memes: int = 0

    def mark_started(self) -> None:
        self.in_progress = True
        self.ready = False
        self.last_error = None
        self.started_at = time.time()
        self.finished_at = 0.0
        self.total_memes = 0

    def mark_ready(self, total_memes: int) -> None:
        self.total_memes = total_memes
        self.ready = total_memes > 0
        self.in_progress = False
        self.finished_at = time.time()
        if not self.ready:
            self.last_error = "资源检查完成，但未加载到任何模板"

    def mark_failed(self, error: str) -> None:
        self.ready = False
        self.in_progress = False
        self.finished_at = time.time()
        self.last_error = error

    def elapsed_seconds(self) -> float:
        if self.finished_at > 0:
            return self.finished_at - self.started_at
        return time.time() - self.started_at

    def format_status(self) -> str:
        elapsed = self.elapsed_seconds()
        if self.ready:
            return (
                f"✅ 资源就绪\n"
                f"已加载模板：{self.total_memes} 个\n"
                f"初始化耗时：{elapsed:.1f} 秒"
            )
        if self.in_progress:
            return (
                f"⏳ 资源初始化中\n"
                f"已耗时：{elapsed:.1f} 秒\n"
                f"首次启动需下载资源包，请耐心等待"
            )
        return (
            f"❌ 资源未就绪\n"
            f"错误：{self.last_error or '未知错误'}\n"
            f"耗时：{elapsed:.1f} 秒"
        )

    def get_block_message(self, *, keyword_matched: bool) -> str | None:
        if not keyword_matched:
            return None
        if self.ready:
            return None
        elapsed = self.elapsed_seconds()
        if self.in_progress:
            return (
                f"表情包资源正在初始化或下载中（已耗时 {elapsed:.0f} 秒），请稍后再试。"
                "首次启动可能需要几分钟。"
            )
        if self.last_error:
            return (
                "表情包资源尚未准备完成，请稍后重试。"
                f"当前状态：{self.last_error}"
            )
        return "表情包资源尚未准备完成，请稍后重试。"
