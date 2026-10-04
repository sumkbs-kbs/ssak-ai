"""Ssak-Ai: 사용자 의도 모델러 (UserIntentModeler).

====================================================
E-4: 사용자의 행동 패턴과 선호도를 학습하여 개인화된 응답을 제공합니다.
"""

import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import datetime
from typing import TypedDict, final

from pydantic import TypeAdapter, ValidationError

from antigravity_k.engine.gbrain import global_gbrain
from antigravity_k.engine.preference_memory import extract_explicit_preference_facts
from antigravity_k.engine.tool_policy import request_allows_side_effects

logger = logging.getLogger(__name__)

_PROFILE_FILE = ".antigravity/user_profile.json"


class _Interaction(TypedDict):
    message: str
    task_type: str
    tools: list[str]
    time: str


class _UserProfile(TypedDict, total=False):
    stats: dict[str, dict[str, int]]
    tool_preferences: dict[str, int]
    created_at: str
    updated_at: str


_PROFILE_ADAPTER: TypeAdapter[_UserProfile] = TypeAdapter(_UserProfile)


@final
class UserIntentModeler:
    """사용자의 소통 스타일, 기술 수준, 선호도를 학습합니다.

    학습 항목:
    - 선호 언어 (한국어/영어/혼합)
    - 기술 수준 (beginner/intermediate/expert)
    - 소통 스타일 (concise/detailed)
    - 자주 사용하는 도구/패턴
    - 작업 도메인 (web/backend/ml/devops 등)
    """

    def __init__(self, project_root: str = "."):
        """Initialize the UserIntentModeler.

        Args:
            project_root (str): str project root.

        """
        self.project_root: str = project_root
        self._profile_path: str = os.path.join(project_root, _PROFILE_FILE)
        self._profile: _UserProfile = self._load_profile()
        self._session_interactions: list[_Interaction] = []
        self._explicit_preferences: dict[str, str] = {}

    def observe(self, user_message: str, task_type: str, tools_used: list[str] | None = None) -> None:
        """사용자 인터랙션을 관찰하고 프로필을 업데이트합니다."""
        self._explicit_preferences.update(extract_explicit_preference_facts(user_message))
        self._session_interactions.append(
            {
                "message": user_message[:200],
                "task_type": task_type,
                "tools": tools_used or [],
                "time": datetime.now().astimezone().replace(tzinfo=None).isoformat(),
            },
        )

        # 언어 감지
        ko_chars = len(re.findall(r"[가-힣]", user_message))
        en_chars = len(re.findall(r"[a-zA-Z]", user_message))
        if ko_chars > en_chars:
            self._update_stat("language_pref", "korean")
        elif en_chars > ko_chars * 3:
            self._update_stat("language_pref", "english")
        else:
            self._update_stat("language_pref", "mixed")

        # 기술 수준 추론
        tech_indicators = [
            "refactor",
            "architecture",
            "optimization",
            "performance",
            "concurrency",
            "async",
            "microservice",
            "CICD",
            "kubernetes",
            "리팩토링",
            "아키텍처",
            "최적화",
            "동시성",
        ]
        basic_indicators = [
            "how to",
            "어떻게",
            "방법",
            "tutorial",
            "설치",
            "install",
            "기초",
            "beginner",
            "초보",
        ]

        msg_lower = user_message.lower()
        expert_hits = sum(1 for t in tech_indicators if t.lower() in msg_lower)
        basic_hits = sum(1 for t in basic_indicators if t.lower() in msg_lower)

        if expert_hits >= 2:
            self._update_stat("skill_level", "expert")
        elif basic_hits >= 2:
            self._update_stat("skill_level", "beginner")
        else:
            self._update_stat("skill_level", "intermediate")

        # 소통 스타일 추론
        if len(user_message) < 50:
            self._update_stat("comm_style", "concise")
        elif len(user_message) > 300:
            self._update_stat("comm_style", "detailed")

        # 도메인 감지
        domain_map = {
            "web": ["react", "vue", "html", "css", "frontend", "next.js", "vite"],
            "backend": ["fastapi", "django", "flask", "api", "server", "database"],
            "ml": ["model", "training", "dataset", "neural", "pytorch", "tensorflow"],
            "devops": ["docker", "kubernetes", "ci/cd", "deploy", "nginx"],
            "system": ["os", "kernel", "driver", "performance", "memory"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in msg_lower for kw in keywords):
                self._update_stat("domain", domain)
                break

        # 도구 선호도
        if tools_used:
            tool_prefs = self._profile.get("tool_preferences", {})
            for tool in tools_used:
                tool_prefs[tool] = tool_prefs.get(tool, 0) + 1
            self._profile["tool_preferences"] = tool_prefs

        # 주기적 저장
        if len(self._session_interactions) % 5 == 0:
            self._save_profile()

    def build_context(self, preference_overrides: Mapping[str, str] | None = None) -> str:
        """에이전트 시스템 프롬프트에 주입할 사용자 컨텍스트."""
        p = self._profile
        stats = p.get("stats", {})
        if not stats:
            return ""

        lines = ["\n<user_profile>"]

        # 결정된 프로필 정보만 주입
        overrides = dict(self._explicit_preferences)
        if preference_overrides:
            overrides.update(preference_overrides)
        lang = overrides.get("response_language") or self._get_dominant("language_pref", stats)
        skill = overrides.get("explanation_level") or self._get_dominant("skill_level", stats)
        style = overrides.get("response_detail") or self._get_dominant("comm_style", stats)
        domain = overrides.get("task_domain") or self._get_dominant("domain", stats)

        if lang:
            lang_map = {
                "korean": "한국어",
                "english": "영어",
                "mixed": "한국어+영어 혼합",
                "ko": "한국어",
                "en": "영어",
            }
            lines.append(f"선호 언어: {lang_map.get(lang, lang)}")
        if skill:
            skill_map = {
                "expert": "전문가",
                "advanced": "전문가",
                "intermediate": "중급",
                "beginner": "초보",
            }
            lines.append(f"기술 수준: {skill_map.get(skill, skill)}")
        if style:
            style_map = {"concise": "간결한 응답 선호", "detailed": "상세한 응답 선호"}
            lines.append(f"소통 스타일: {style_map.get(style, style)}")
        if domain:
            lines.append(f"주 작업 도메인: {domain}")

        # 자주 사용하는 도구
        tool_prefs = p.get("tool_preferences", {})
        if tool_prefs:
            top_tools = sorted(tool_prefs, key=lambda item: tool_prefs[item], reverse=True)[:5]
            lines.append(f"자주 사용하는 도구: {', '.join(top_tools)}")

        lines.append("이 프로필에 맞춰 응답 깊이와 스타일을 조절하세요.")
        lines.append("</user_profile>")

        return "\n".join(lines) if len(lines) > 3 else ""

    def _update_stat(self, key: str, value: str) -> None:
        stats = self._profile.get("stats")
        if stats is None:
            stats = {}
            self._profile["stats"] = stats
        counts = stats.setdefault(key, {})
        counts[value] = counts.get(value, 0) + 1

    def _get_dominant(self, key: str, stats: dict[str, dict[str, int]]) -> str | None:
        counts = stats.get(key, {})
        if not counts:
            return None
        return max(counts, key=lambda item: counts[item])

    def _load_profile(self) -> _UserProfile:
        if os.path.exists(self._profile_path):
            try:
                with open(self._profile_path, "rb") as profile_file:
                    return _PROFILE_ADAPTER.validate_json(profile_file.read())
            except (OSError, UnicodeError, ValidationError):
                logger.exception("Unhandled exception")
        return {
            "stats": {},
            "tool_preferences": {},
            "created_at": datetime.now().astimezone().replace(tzinfo=None).isoformat(),
        }

    def _save_profile(self) -> None:
        if not request_allows_side_effects():
            return
        try:
            os.makedirs(os.path.dirname(self._profile_path), exist_ok=True)
            self._profile["updated_at"] = datetime.now().astimezone().replace(tzinfo=None).isoformat()

            # GBrain 동기화
            global_gbrain.add_node(
                node_id="user_profile_main",
                label="user_profile",
                content=json.dumps(self._profile, ensure_ascii=False),
                metadata={"updated_at": self._profile["updated_at"]},
            )

            # 파일 폴백 저장
            with open(self._profile_path, "w", encoding="utf-8") as f:
                json.dump(self._profile, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError):
            logger.exception("[UserModel] Failed to save profile")
