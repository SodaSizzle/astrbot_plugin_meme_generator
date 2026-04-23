import json
import random
import re
import time
import yaml
from dataclasses import dataclass
from pathlib import Path
import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.api.star import StarTools

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


def _plugin_path(filename: str) -> Path:
    return PLUGIN_DIR / filename


def _static_data_path(filename: str) -> Path:
    return STATIC_DATA_DIR / filename


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


@dataclass(slots=True)
class AnalysisResult:
    should_attempt: bool
    block_reason: str | None
    primary_scene: str | None
    secondary_scene: str | None
    primary_emotion: str | None
    secondary_emotion: str | None
    confidence: float
    scene_scores: dict[str, float]
    emotion_scores: dict[str, float]


@dataclass(slots=True)
class TemplateCandidate:
    template_key: str
    auto_weight: float
    risk_level: str
    cooldown_group: str
    aliases: list[str]
    metadata: dict[str, object]


@dataclass(slots=True)
class AutoMemeDecision:
    template_key: str
    confidence: float
    analysis: AnalysisResult
    candidates: list[TemplateCandidate]


@dataclass(slots=True)
class PendingAutoMeme:
    session_id: str
    unified_msg_origin: str
    reply_text: str
    decision: AutoMemeDecision
    created_at: float


class EmotionAnalyzer:
    """Analyze whether a reply is suitable for an automatic meme."""

    def __init__(
        self,
        rule_file: str | Path | None = None,
        user_weight: float | None = None,
        reply_weight: float | None = None,
        attempt_threshold: float | None = None,
    ):
        path = Path(rule_file) if rule_file else _static_data_path("emotion_rules.json")
        self.rules = json.loads(path.read_text(encoding="utf-8"))
        self.scene_rules = self.rules.get("scene_rules", {})
        self.emotion_rules = self.rules.get("emotion_rules", {})
        self.hard_blocks = self.rules.get("hard_blocks", {})
        self.mapping_rules = self.rules.get("mapping_rules", {})
        self.emotion_to_scene = self.mapping_rules.get("emotion_to_scene", {})
        self.scene_to_emotion = self.mapping_rules.get("scene_to_emotion", {})
        self.text_shape_hints = self.rules.get("text_shape_hints", {})
        self.dynamic_threshold_hints = self.rules.get("dynamic_threshold_hints", {})
        user_hints = self.rules.get("user_hints", {})
        reply_hints = self.rules.get("reply_hints", {})
        self.user_emotion_hints = user_hints.get("emotion_tags", {})
        self.user_pattern_hints = user_hints.get("patterns", [])
        self.reply_emotion_hints = reply_hints.get("emotion_tags", {})
        self.reply_scene_hints = reply_hints.get("scene_tags", {})
        self.reply_pattern_hints = reply_hints.get("patterns", [])
        self.emoji_emotion_hints = reply_hints.get("emoji_hints", {})
        self.weights = self.rules.get("confidence_weights", {})
        self.thresholds = self.rules.get("thresholds", {})
        self.reply_weight = float(
            self.weights.get("reply_text", 0.7)
            if reply_weight is None
            else reply_weight
        )
        self.user_weight = float(
            self.weights.get("user_text", 0.3)
            if user_weight is None
            else user_weight
        )
        self.attempt_threshold = float(
            self.thresholds.get("attempt", 0.55)
            if attempt_threshold is None
            else attempt_threshold
        )

    def analyze(self, user_text: str, reply_text: str) -> AnalysisResult:
        user_text = self._normalize(user_text)
        reply_text = self._normalize(reply_text)

        if not reply_text:
            return self._blocked("empty_reply")

        if self._contains_any(reply_text, self.hard_blocks.get("code_block", [])):
            return self._blocked("code_block")

        if self._looks_technical(reply_text):
            return self._blocked("technical_reply")

        user_scene_scores = self._score_rules(
            text=user_text,
            weight=self.user_weight,
            rules=self.scene_rules,
        )
        reply_scene_scores = self._score_rules(
            text=reply_text,
            weight=self.reply_weight,
            rules=self.scene_rules,
        )
        user_emotion_scores = self._score_rules(
            text=user_text,
            weight=self.user_weight,
            rules=self.emotion_rules,
        )
        reply_emotion_scores = self._score_rules(
            text=reply_text,
            weight=self.reply_weight,
            rules=self.emotion_rules,
        )

        self._apply_user_hints(
            user_text,
            user_scene_scores,
            user_emotion_scores,
        )
        self._apply_reply_hints(
            reply_text,
            reply_scene_scores,
            reply_emotion_scores,
        )

        scene_scores = dict(user_scene_scores)
        self._merge_scores(scene_scores, reply_scene_scores)
        emotion_scores = dict(user_emotion_scores)
        self._merge_scores(emotion_scores, reply_emotion_scores)

        self._apply_text_shape_hints(user_text, reply_text, scene_scores, emotion_scores)

        primary_scene, secondary_scene = self._top_two(scene_scores)
        primary_emotion, secondary_emotion = self._top_two(emotion_scores)
        primary_scene = self._resolve_scene(primary_scene, primary_emotion)
        primary_emotion = self._resolve_emotion(primary_emotion, primary_scene)

        if primary_scene and primary_scene not in scene_scores:
            scene_scores[primary_scene] = 0.18
        if primary_emotion and primary_emotion not in emotion_scores:
            emotion_scores[primary_emotion] = 0.18

        scene_score = scene_scores.get(primary_scene, 0.0) if primary_scene else 0.0
        emotion_score = (
            emotion_scores.get(primary_emotion, 0.0) if primary_emotion else 0.0
        )
        user_signal = self._top_score(user_scene_scores) + self._top_score(user_emotion_scores)
        reply_signal = self._top_score(reply_scene_scores) + self._top_score(reply_emotion_scores)
        consistency_score = self._consistency_score(
            primary_scene, primary_emotion, secondary_emotion
        )
        confidence = min(
            1.0,
            0.26 * min(scene_score, 1.0)
            + 0.28 * min(emotion_score, 1.0)
            + 0.16 * consistency_score
            + 0.17 * min(user_signal, 1.0)
            + 0.08 * min(reply_signal, 1.0)
            + 0.08,
        )
        if len(reply_text) <= 4 and user_signal >= 0.45:
            confidence = min(1.0, confidence + 0.08)
        if any(token in reply_text for token in self.emoji_emotion_hints):
            confidence = min(1.0, confidence + 0.08)

        return AnalysisResult(
            should_attempt=bool(
                primary_scene and primary_emotion and confidence >= self.attempt_threshold
            ),
            block_reason=None,
            primary_scene=primary_scene,
            secondary_scene=secondary_scene,
            primary_emotion=primary_emotion,
            secondary_emotion=secondary_emotion,
            confidence=confidence,
            scene_scores=scene_scores,
            emotion_scores=emotion_scores,
        )

    def _blocked(self, reason: str) -> AnalysisResult:
        return AnalysisResult(
            should_attempt=False,
            block_reason=reason,
            primary_scene=None,
            secondary_scene=None,
            primary_emotion=None,
            secondary_emotion=None,
            confidence=0.0,
            scene_scores={},
            emotion_scores={},
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = (text or "").strip().lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _merge_scores(target: dict[str, float], source: dict[str, float]) -> None:
        for key, value in source.items():
            target[key] = target.get(key, 0.0) + value

    @staticmethod
    def _contains_any(text: str, patterns: list[str]) -> bool:
        return any(pattern.lower() in text for pattern in patterns)

    @staticmethod
    def _top_score(scores: dict[str, float]) -> float:
        return max(scores.values(), default=0.0)

    def _looks_technical(self, text: str) -> bool:
        if self._contains_any(text, self.hard_blocks.get("technical_reply", [])):
            return True
        if self._contains_any(text, self.hard_blocks.get("path_like", [])):
            return True
        if re.search(r"\b\d+\.", text):
            return True
        return False

    @staticmethod
    def _score_rules(
        text: str,
        weight: float,
        rules: dict[str, list[str]],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for tag, patterns in rules.items():
            for pattern in patterns:
                if pattern.lower() in text:
                    scores[tag] = scores.get(tag, 0.0) + weight
        return scores

    def _apply_user_hints(
        self,
        user_text: str,
        scene_scores: dict[str, float],
        emotion_scores: dict[str, float],
    ) -> None:
        for emotion, patterns in self.user_emotion_hints.items():
            if self._contains_any(user_text, patterns):
                emotion_scores[emotion] = emotion_scores.get(emotion, 0.0) + 0.42
                mapped_scene = self.emotion_to_scene.get(emotion)
                if mapped_scene:
                    scene_scores[mapped_scene] = scene_scores.get(mapped_scene, 0.0) + 0.32
        self._apply_pattern_hints(
            user_text,
            self.user_pattern_hints,
            scene_scores,
            emotion_scores,
        )

    def _apply_reply_hints(
        self,
        reply_text: str,
        scene_scores: dict[str, float],
        emotion_scores: dict[str, float],
    ) -> None:
        for emotion, patterns in self.reply_emotion_hints.items():
            if self._contains_any(reply_text, patterns):
                emotion_scores[emotion] = emotion_scores.get(emotion, 0.0) + 0.24
        for scene, patterns in self.reply_scene_hints.items():
            if self._contains_any(reply_text, patterns):
                scene_scores[scene] = scene_scores.get(scene, 0.0) + 0.22
        self._apply_emoji_hints(reply_text, scene_scores, emotion_scores)
        self._apply_pattern_hints(
            reply_text,
            self.reply_pattern_hints,
            scene_scores,
            emotion_scores,
        )

    def _apply_emoji_hints(
        self,
        text: str,
        scene_scores: dict[str, float],
        emotion_scores: dict[str, float],
    ) -> None:
        for token, payload in self.emoji_emotion_hints.items():
            if token not in text:
                continue
            emotion = payload.get("emotion")
            scene = payload.get("scene")
            if emotion:
                emotion_scores[emotion] = emotion_scores.get(emotion, 0.0) + float(
                    payload.get("emotion_score", 0.28)
                )
            if scene:
                scene_scores[scene] = scene_scores.get(scene, 0.0) + float(
                    payload.get("scene_score", 0.2)
                )

    @staticmethod
    def _apply_pattern_hints(
        text: str,
        patterns: list[dict],
        scene_scores: dict[str, float],
        emotion_scores: dict[str, float],
    ) -> None:
        for item in patterns:
            pattern = item.get("pattern")
            if not pattern or not re.search(pattern, text):
                continue
            scene = item.get("scene")
            emotion = item.get("emotion")
            if scene:
                scene_scores[scene] = scene_scores.get(scene, 0.0) + float(
                    item.get("scene_score", 0.0)
                )
            if emotion:
                emotion_scores[emotion] = emotion_scores.get(emotion, 0.0) + float(
                    item.get("emotion_score", 0.0)
                )

    def _apply_text_shape_hints(
        self,
        user_text: str,
        reply_text: str,
        scene_scores: dict[str, float],
        emotion_scores: dict[str, float],
    ) -> None:
        combined = f"{user_text} {reply_text}"
        if any(
            token in combined
            for token in self.text_shape_hints.get("question_tokens", [])
        ):
            emotion_scores["疑惑"] = emotion_scores.get("疑惑", 0.0) + 0.15
        if any(
            token in combined
            for token in self.text_shape_hints.get("surprise_tokens", [])
        ):
            emotion_scores["惊讶"] = emotion_scores.get("惊讶", 0.0) + 0.15
        if any(
            token in combined
            for token in self.text_shape_hints.get("laugh_tokens", [])
        ):
            scene_scores["聊天"] = scene_scores.get("聊天", 0.0) + 0.1
            emotion_scores["调侃"] = emotion_scores.get("调侃", 0.0) + 0.1
        if any(
            token in reply_text
            for token in self.text_shape_hints.get("comfort_reply_tokens", [])
        ):
            scene_scores["安抚"] = scene_scores.get("安抚", 0.0) + 0.2
            emotion_scores["安慰"] = emotion_scores.get("安慰", 0.0) + 0.2
        if len(reply_text) <= 4 and any(
            token in user_text
            for token in self.text_shape_hints.get("short_reply_support_user_tokens", [])
        ):
            scene_scores["安抚"] = scene_scores.get("安抚", 0.0) + 0.12
            emotion_scores["安慰"] = emotion_scores.get("安慰", 0.0) + 0.16
        if len(reply_text) <= 4 and any(
            token in user_text
            for token in self.text_shape_hints.get("short_reply_tease_user_tokens", [])
        ):
            scene_scores["调侃"] = scene_scores.get("调侃", 0.0) + 0.12
            emotion_scores["吐槽"] = emotion_scores.get("吐槽", 0.0) + 0.16

    @staticmethod
    def _top_two(scores: dict[str, float]) -> tuple[str | None, str | None]:
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary = ranked[0][0] if ranked else None
        secondary = ranked[1][0] if len(ranked) > 1 else None
        return primary, secondary

    def _resolve_scene(
        self,
        primary_scene: str | None,
        primary_emotion: str | None,
    ) -> str | None:
        if primary_scene:
            return primary_scene
        if primary_emotion:
            return self.emotion_to_scene.get(primary_emotion)
        return None

    def _resolve_emotion(
        self,
        primary_emotion: str | None,
        primary_scene: str | None,
    ) -> str | None:
        if primary_emotion:
            return primary_emotion
        if primary_scene:
            return self.scene_to_emotion.get(primary_scene)
        return None

    @staticmethod
    def _consistency_score(
        primary_scene: str | None,
        primary_emotion: str | None,
        secondary_emotion: str | None,
    ) -> float:
        if not primary_scene or not primary_emotion:
            return 0.0
        if primary_scene == "安抚" and primary_emotion == "安慰":
            return 1.0
        if primary_scene == "鼓励" and primary_emotion in {"鼓励", "认可"}:
            return 0.9
        if primary_scene == "调侃" and primary_emotion in {"吐槽", "调侃", "无语"}:
            return 0.8
        if secondary_emotion and secondary_emotion == primary_emotion:
            return 0.85
        return 0.6


class TemplateSelector:
    """Pick templates from the full emotion pool."""

    def __init__(self, template_file: str | Path | None = None):
        path = (
            Path(template_file)
            if template_file
            else _static_data_path("emotion_templates.json")
        )
        self.template_map = json.loads(path.read_text(encoding="utf-8"))

    def select_candidates(
        self,
        primary_emotion: str,
        secondary_emotion: str | None,
        scene_tags: list[str],
        recent_groups: list[str],
        disabled_templates: list[str],
        limit: int = 5,
    ) -> list[TemplateCandidate]:
        disabled_set = set(disabled_templates)
        recent_group_set = set(recent_groups)
        scored: list[tuple[float, TemplateCandidate]] = []

        for template_key, metadata in self.template_map.items():
            if not metadata.get("enabled_for_auto", True):
                continue

            aliases = list(metadata.get("aliases", []))
            if template_key in disabled_set or disabled_set.intersection(aliases):
                continue

            cooldown_group = metadata.get("cooldown_group", template_key)
            if cooldown_group in recent_group_set:
                continue

            emotion_tags = set(metadata.get("emotion_tags", []))
            scene_pool = set(metadata.get("scene_tags", []))
            if primary_emotion not in emotion_tags and (
                not secondary_emotion or secondary_emotion not in emotion_tags
            ):
                continue

            score = float(metadata.get("auto_weight", 0.0))
            if primary_emotion in emotion_tags:
                score += 0.3
            if secondary_emotion and secondary_emotion in emotion_tags:
                score += 0.15
            if scene_pool.intersection(scene_tags):
                score += 0.1
            score += self._risk_bonus(metadata.get("risk_level", "medium"))

            candidate = TemplateCandidate(
                template_key=template_key,
                auto_weight=float(metadata.get("auto_weight", 0.0)),
                risk_level=metadata.get("risk_level", "medium"),
                cooldown_group=cooldown_group,
                aliases=aliases,
                metadata=metadata,
            )
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored[:limit]]

    @staticmethod
    def _risk_bonus(risk_level: str) -> float:
        if risk_level == "low":
            return 0.15
        if risk_level == "high":
            return -0.25
        return 0.0


class AutoMemeState:
    """Track pending auto-meme decisions and cooldown groups."""

    def __init__(self):
        self._pending: dict[str, PendingAutoMeme] = {}
        self._last_sent_at: dict[str, float] = {}
        self._session_send_count: dict[str, int] = {}
        self._recent_groups: dict[str, list[str]] = {}
        self._recent_emotions: dict[str, list[str]] = {}
        self._recent_scenes: dict[str, list[str]] = {}

    def set_pending(
        self,
        session_id: str,
        unified_msg_origin: str,
        reply_text: str,
        decision: AutoMemeDecision,
    ) -> None:
        self._pending[session_id] = PendingAutoMeme(
            session_id=session_id,
            unified_msg_origin=unified_msg_origin,
            reply_text=reply_text,
            decision=decision,
            created_at=time.time(),
        )

    def get_pending(self, session_id: str) -> PendingAutoMeme | None:
        return self._pending.get(session_id)

    def clear_pending(self, session_id: str) -> None:
        self._pending.pop(session_id, None)

    def get_recent_groups(self, session_id: str) -> list[str]:
        return list(self._recent_groups.get(session_id, []))

    def get_recent_emotions(self, session_id: str) -> list[str]:
        return list(self._recent_emotions.get(session_id, []))

    def get_recent_scenes(self, session_id: str) -> list[str]:
        return list(self._recent_scenes.get(session_id, []))

    def get_last_sent_at(self, session_id: str) -> float:
        return self._last_sent_at.get(session_id, 0.0)

    def record_analysis(
        self,
        session_id: str,
        emotion: str | None,
        scene: str | None,
    ) -> None:
        if emotion:
            recent_emotions = self._recent_emotions.setdefault(session_id, [])
            recent_emotions.append(emotion)
            if len(recent_emotions) > 5:
                del recent_emotions[:-5]
        if scene:
            recent_scenes = self._recent_scenes.setdefault(session_id, [])
            recent_scenes.append(scene)
            if len(recent_scenes) > 5:
                del recent_scenes[:-5]

    def can_send(
        self,
        session_id: str,
        cooldown_seconds: int,
        max_per_session: int,
    ) -> bool:
        return self.get_send_block_reason(
            session_id=session_id,
            cooldown_seconds=cooldown_seconds,
            max_per_session=max_per_session,
        ) is None

    def get_send_block_reason(
        self,
        session_id: str,
        cooldown_seconds: int,
        max_per_session: int,
    ) -> str | None:
        now = time.time()
        last_sent_at = self._last_sent_at.get(session_id, 0.0)
        if cooldown_seconds > 0 and (now - last_sent_at) < cooldown_seconds:
            return "cooldown"

        count = self._session_send_count.get(session_id, 0)
        if count >= max_per_session:
            return "session_limit"
        return None

    def record_send(self, session_id: str, cooldown_group: str) -> None:
        self._last_sent_at[session_id] = time.time()
        self._session_send_count[session_id] = self._session_send_count.get(
            session_id, 0
        ) + 1
        recent_groups = self._recent_groups.setdefault(session_id, [])
        recent_groups.append(cooldown_group)
        if len(recent_groups) > 3:
            del recent_groups[:-3]


class AutoMemeService:
    """Prepare automatic meme decisions without extra LLM calls."""

    def __init__(
        self,
        template_file: str | Path | None = None,
        rule_file: str | Path | None = None,
        base_probability: float = 0.35,
        user_weight: float | None = None,
        reply_weight: float | None = None,
        attempt_threshold: float | None = None,
    ):
        self.analyzer = EmotionAnalyzer(
            rule_file=rule_file,
            user_weight=user_weight,
            reply_weight=reply_weight,
            attempt_threshold=attempt_threshold,
        )
        self.selector = TemplateSelector(template_file=template_file)
        self.base_probability = base_probability

    def prepare_auto_meme(
        self,
        user_text: str,
        reply_text: str,
        recent_groups: list[str],
        recent_emotions: list[str],
        recent_scenes: list[str],
        disabled_templates: list[str],
        last_sent_at: float = 0.0,
    ) -> AutoMemeDecision | None:
        analysis = self.analyzer.analyze(user_text=user_text, reply_text=reply_text)
        if not analysis.should_attempt or not analysis.primary_emotion:
            logger.info(
                "自动补图未命中 - block_reason=%s scene=%s emotion=%s confidence=%.2f",
                analysis.block_reason or "rule_skip",
                analysis.primary_scene,
                analysis.primary_emotion,
                analysis.confidence,
            )
            return None

        scene_tags = [
            scene
            for scene in (analysis.primary_scene, analysis.secondary_scene)
            if scene
        ]
        candidates = self.selector.select_candidates(
            primary_emotion=analysis.primary_emotion,
            secondary_emotion=analysis.secondary_emotion,
            scene_tags=scene_tags,
            recent_groups=recent_groups,
            disabled_templates=disabled_templates,
        )
        if not candidates:
            logger.info(
                "自动补图无候选模板 - scene=%s emotion=%s secondary=%s disabled=%s recent=%s",
                analysis.primary_scene,
                analysis.primary_emotion,
                analysis.secondary_emotion,
                len(disabled_templates),
                recent_groups,
            )
            return None

        lead = candidates[0]
        probability = self._compute_send_probability(
            reply_text=reply_text,
            analysis=analysis,
            lead=lead,
            recent_emotions=recent_emotions,
            recent_scenes=recent_scenes,
            last_sent_at=last_sent_at,
        )
        dice = random.random()
        if dice >= probability:
            logger.info(
                "自动补图骰子未过 - dice=%.2f prob=%.2f scene=%s emotion=%s template=%s",
                dice,
                probability,
                analysis.primary_scene,
                analysis.primary_emotion,
                lead.template_key,
            )
            return None

        logger.info(
            "自动补图命中 - scene=%s emotion=%s prob=%.2f dice=%.2f template=%s candidates=%s",
            analysis.primary_scene,
            analysis.primary_emotion,
            probability,
            dice,
            lead.template_key,
            [candidate.template_key for candidate in candidates[:3]],
        )
        return AutoMemeDecision(
            template_key=lead.template_key,
            confidence=probability,
            analysis=analysis,
            candidates=candidates,
        )

    def _compute_send_probability(
        self,
        reply_text: str,
        analysis: AnalysisResult,
        lead: TemplateCandidate,
        recent_emotions: list[str],
        recent_scenes: list[str],
        last_sent_at: float,
    ) -> float:
        prob = self.base_probability

        # 情绪信号越强，概率越高
        if analysis.confidence >= 0.85:
            prob += 0.25
        elif analysis.confidence >= 0.7:
            prob += 0.15
        elif analysis.confidence >= 0.55:
            prob += 0.05

        # 高强度情绪加成
        if analysis.primary_emotion in {"安慰", "惊讶", "吐槽"}:
            prob += 0.12
        if analysis.primary_scene in {"安抚", "调侃"}:
            prob += 0.08

        # 用户带强烈信号
        if any(
            token in analysis.scene_scores or token in analysis.emotion_scores
            for token in ("安抚", "安慰")
        ) and analysis.emotion_scores.get("安慰", 0) >= 0.6:
            prob += 0.1

        # 回复长度：短回复更适合配图，长篇说明少配
        reply_len = len(reply_text.strip())
        if reply_len <= 15:
            prob += 0.08
        elif reply_len >= 120:
            prob -= 0.1

        # 模板风险等级
        if lead.risk_level == "low":
            prob += 0.05
        elif lead.risk_level == "high":
            prob -= 0.12

        # 情绪/场景重复惩罚（避免同类刷屏）
        if analysis.primary_emotion in recent_emotions[-3:]:
            prob -= 0.08
        if analysis.primary_scene in recent_scenes[-3:]:
            prob -= 0.05

        # 最近 30 秒已经发过，强制降概率
        if last_sent_at > 0 and (time.time() - last_sent_at) < 30:
            prob -= 0.2

        return max(0.05, min(0.85, prob))


AUTO_MEME_PRESETS: dict[str, dict] = {
    "保守": {
        "base_probability": 0.15,
        "cooldown": 300,
        "max_per_session": 1,
        "reply_weight": 0.75,
        "user_weight": 0.25,
    },
    "平衡": {
        "base_probability": 0.35,
        "cooldown": 120,
        "max_per_session": 1,
        "reply_weight": 0.70,
        "user_weight": 0.30,
    },
    "活跃": {
        "base_probability": 0.55,
        "cooldown": 60,
        "max_per_session": 2,
        "reply_weight": 0.65,
        "user_weight": 0.35,
    },
}


class MemeConfig:
    """表情包生成器配置管理类"""

    def __init__(self, config: AstrBotConfig):
        self.config = config
        self._load_config()

    def _load_config(self):
        """加载配置"""
        self.enable_plugin: bool = self.config.get("enable_plugin", True)
        self.trigger_prefix: str = str(self.config.get("trigger_prefix", "") or "")
        self.generation_timeout: int = self.config.get("generation_timeout", 30)
        self.cooldown_seconds: int = self.config.get("cooldown_seconds", 3)
        self.enable_avatar_cache: bool = self.config.get("enable_avatar_cache", True)
        self.cache_expire_hours: int = self.config.get("cache_expire_hours", 24)
        self.disabled_templates: list[str] = self.config.get("disabled_templates", [])
        self.enable_auto_meme: bool = self.config.get("enable_auto_meme", False)
        self.auto_meme_scope: str = self.config.get("auto_meme_scope", "all")
        self.auto_meme_level: str = self.config.get("auto_meme_level", "平衡")
        preset = AUTO_MEME_PRESETS.get(self.auto_meme_level, AUTO_MEME_PRESETS["平衡"])
        self.auto_meme_base_probability: float = preset["base_probability"]
        self.auto_meme_cooldown_seconds: int = preset["cooldown"]
        self.auto_meme_max_per_session: int = preset["max_per_session"]
        self.auto_meme_reply_weight: float = preset["reply_weight"]
        self.auto_meme_user_weight: float = preset["user_weight"]

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


class AutoMemeHandler:
    """Coordinate LLM reply analysis and delayed meme sending."""

    def __init__(self, context, meme_manager: MemeManager, config: MemeConfig):
        self.context = context
        self.meme_manager = meme_manager
        self.config = config
        self.state = AutoMemeState()
        self.service = AutoMemeService(
            base_probability=config.auto_meme_base_probability,
            user_weight=config.auto_meme_user_weight,
            reply_weight=config.auto_meme_reply_weight,
        )

    async def capture_llm_response(
        self,
        event: AstrMessageEvent,
        resp: LLMResponse,
    ) -> None:
        block_reason = self._get_event_block_reason(event)
        if block_reason is not None:
            logger.info(
                "自动补图跳过捕获 - session=%s reason=%s",
                event.session_id,
                block_reason,
            )
            return
        if event.get_extra("enable_streaming") is True:
            logger.info("自动补图跳过捕获 - session=%s reason=streaming", event.session_id)
            return

        reply_text = (resp.completion_text or "").strip()
        user_text = (event.get_message_str() or "").strip()
        if not reply_text or not user_text:
            logger.info(
                "自动补图跳过捕获 - session=%s reason=empty_text user_len=%s reply_len=%s",
                event.session_id,
                len(user_text),
                len(reply_text),
            )
            return

        logger.info(
            "自动补图开始判断 - session=%s user=%s reply=%s",
            event.session_id,
            self._preview_text(user_text),
            self._preview_text(reply_text),
        )
        decision = self.service.prepare_auto_meme(
            user_text=user_text,
            reply_text=reply_text,
            recent_groups=self.state.get_recent_groups(event.session_id),
            recent_emotions=self.state.get_recent_emotions(event.session_id),
            recent_scenes=self.state.get_recent_scenes(event.session_id),
            disabled_templates=self.config.get_disabled_templates(),
            last_sent_at=self.state.get_last_sent_at(event.session_id),
        )
        if decision is None:
            self.state.clear_pending(event.session_id)
            logger.debug("自动补图未生成待发送任务 - session=%s", event.session_id)
            return

        self.state.record_analysis(
            event.session_id,
            decision.analysis.primary_emotion,
            decision.analysis.primary_scene,
        )
        self.state.set_pending(
            session_id=event.session_id,
            unified_msg_origin=event.unified_msg_origin,
            reply_text=reply_text,
            decision=decision,
        )
        logger.info(
            "自动补图已加入待发送 - session=%s template=%s confidence=%.2f",
            event.session_id,
            decision.template_key,
            decision.confidence,
        )

    async def handle_after_message_sent(self, event: AstrMessageEvent) -> None:
        block_reason = self._get_event_block_reason(event)
        if block_reason is not None:
            logger.info(
                "自动补图跳过发送 - session=%s reason=%s",
                event.session_id,
                block_reason,
            )
            return
        pending = self.state.get_pending(event.session_id)
        if pending is None:
            logger.debug("自动补图无待发送任务 - session=%s", event.session_id)
            return
        send_block_reason = self.state.get_send_block_reason(
            session_id=event.session_id,
            cooldown_seconds=self.config.auto_meme_cooldown_seconds,
            max_per_session=self.config.auto_meme_max_per_session,
        )
        if send_block_reason is not None:
            logger.info(
                "自动补图发送取消 - session=%s reason=%s template=%s",
                event.session_id,
                send_block_reason,
                pending.decision.template_key,
            )
            self.state.clear_pending(event.session_id)
            return

        decision = pending.decision
        text_candidates = [pending.reply_text, event.get_message_str()]
        logger.info(
            "自动补图开始发送 - session=%s templates=%s",
            event.session_id,
            [candidate.template_key for candidate in decision.candidates],
        )
        for candidate in decision.candidates:
            try:
                image = await self.meme_manager.generate_meme_by_template_key(
                    event=event,
                    template_key=candidate.template_key,
                    text_candidates=text_candidates,
                )
            except Exception as exc:
                logger.warning(f"自动补图渲染失败({candidate.template_key}): {exc}")
                continue

            if not image:
                logger.info(
                    "自动补图候选未产出图片 - session=%s template=%s",
                    event.session_id,
                    candidate.template_key,
                )
                continue

            await self.context.send_message(
                pending.unified_msg_origin,
                MessageChain([Comp.Image.fromBytes(image)]),
            )
            self.state.record_send(event.session_id, candidate.cooldown_group)
            self.state.clear_pending(event.session_id)
            logger.info(
                "自动补图发送成功 - session=%s template=%s confidence=%.2f cooldown_group=%s",
                event.session_id,
                candidate.template_key,
                decision.confidence,
                candidate.cooldown_group,
            )
            return

        logger.info(
            "自动补图发送失败 - session=%s reason=no_rendered_image template=%s",
            event.session_id,
            decision.template_key,
        )
        self.state.clear_pending(event.session_id)

    def _is_enabled_for_event(self, event: AstrMessageEvent) -> bool:
        return self._get_event_block_reason(event) is None

    def _get_event_block_reason(self, event: AstrMessageEvent) -> str | None:
        if not self.config.is_plugin_enabled():
            return "plugin_disabled"
        if not self.config.enable_auto_meme:
            return "auto_meme_disabled"
        if self.config.auto_meme_scope == "group":
            return None if event.get_group_id() else "scope_group_only"
        if self.config.auto_meme_scope == "private":
            return None if event.is_private_chat() else "scope_private_only"
        return None

    @staticmethod
    def _preview_text(text: str, limit: int = 48) -> str:
        text = " ".join((text or "").split())
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."


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
        logger.info(
            "表情插件初始化 - auto_meme_enabled=%s scope=%s level=%s base_prob=%.2f cooldown=%ss max_per_session=%s",
            self.meme_config.enable_auto_meme,
            self.meme_config.auto_meme_scope,
            self.meme_config.auto_meme_level,
            self.meme_config.auto_meme_base_probability,
            self.meme_config.auto_meme_cooldown_seconds,
            self.meme_config.auto_meme_max_per_session,
        )

        # 获取插件数据目录

        data_dir = str(StarTools.get_data_dir())

        # 初始化核心管理器
        self.meme_manager = MemeManager(self.meme_config, data_dir)

        # 初始化命令处理器
        self.template_handlers = TemplateHandlers(self.meme_manager, self.meme_config)
        self.generation_handler = GenerationHandler(self.meme_manager)
        self.admin_handlers = AdminHandlers(self.meme_config)
        self.auto_meme_handler = AutoMemeHandler(
            self.context,
            self.meme_manager,
            self.meme_config,
        )

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

    @filter.on_llm_response()
    async def on_llm_response(
        self,
        event: AstrMessageEvent,
        resp: LLMResponse,
    ) -> None:
        """Capture the final LLM reply for optional auto meme sending."""
        try:
            await self.auto_meme_handler.capture_llm_response(event, resp)
        except Exception as e:
            logger.error(f"自动补图捕获 LLM 响应失败: {e}")

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """Send one extra auto meme after AstrBot finishes a normal reply."""
        try:
            await self.auto_meme_handler.handle_after_message_sent(event)
        except Exception as e:
            logger.error(f"自动补图发送失败: {e}")
