"""Skill Market Registry — 설치된 마켓 스킬 관리 통합 API.

==========================================================
Phase 1 D10: SkillMarketClient + SkillInstaller + SkillLoader 통합.

SkillMarketRegistry는 마켓 스킬의 전체 라이프사이클을 관리하는
단일 진입점입니다. CLI/Slash 명령어가 이 레지스트리를 통해
모든 Marketplace 작업을 수행합니다.

사용법:
    registry = SkillMarketRegistry(project_root, market_client, installer, skill_loader)
    installed = registry.list_installed()
    result = registry.install("@antigravity-k/skill-code-review")
    result = registry.remove("code-review")
    updates = registry.check_updates()
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, TypedDict, final

from antigravity_k.engine.skill_installer import InstallResult
from antigravity_k.engine.skill_market_client import InstalledSkill, SkillDetail, SkillListing

JsonObject: TypeAlias = Mapping[str, object]


class InstallResponse(TypedDict, total=False):
    success: bool
    error: str
    action: str
    package_name: str
    skill_name: str
    version: str
    install_path: str
    errors: list[str]
    warnings: list[str]
    summary: str


class SearchResponse(TypedDict, total=False):
    error: str
    name: str
    skill_name: str
    version: str
    description: str
    keywords: list[str]
    publisher: str
    date: str
    npm_url: str
    homepage: str
    repository: str
    is_installed: bool


class MarketClientProtocol(Protocol):
    def search(self, query: str, limit: int = 20) -> list[SkillListing]: ...

    def get_detail(self, package_name: str) -> SkillDetail | None: ...

    def get_installed(self, project_root: str | None = None) -> list[InstalledSkill]: ...


class InstallerProtocol(Protocol):
    def install(self, package_name: str) -> InstallResult: ...

    def remove(self, package_name: str) -> InstallResult: ...

    def update(self, package_name: str) -> InstallResult: ...


class LoaderProtocol(Protocol):
    active_skills: list[str]

    def list_skills(self) -> list[dict[str, object]]: ...


logger = logging.getLogger(__name__)

# ─── 상수 ─────────────────────────────────────────────────────────────

AGK_SKILL_SCOPE = "@antigravity-k/skill-"
MARKET_DIR = ".agent/skills/market"


# ─── 데이터 모델 ──────────────────────────────────────────────────────


@dataclass
class RegistrySkillInfo:
    """레지스트리가 관리하는 설치된 스킬의 상세 정보."""

    # 기본 식별
    skill_name: str
    """스킬 짧은 이름 (e.g. 'code-review')."""

    package_name: str
    """npm 패키지 전체 이름 (e.g. '@antigravity-k/skill-code-review')."""

    version: str
    """현재 설치된 버전."""

    description: str = ""
    """설명."""

    # 설치 상태
    install_path: str = ""
    """로컬 설치 경로 (.agent/skills/market/<name>/)."""

    installed_at: str = ""
    """최초 설치 일시."""

    updated_at: str = ""
    """최근 업데이트 일시."""

    # 메타데이터
    risk_level: str = "safe"
    """위험도."""

    trust_level: str = "verified"
    """신뢰 수준."""

    requires_approval: bool = False
    """사용자 승인 필요 여부."""

    mcp_server_id: str = ""
    """연결된 MCP 서버 ID (MCP 스킬인 경우)."""

    # 최신 버전 정보 (check_updates()로 설정)
    latest_version: str = ""
    """npm 레지스트리의 최신 버전."""

    is_outdated: bool = False
    """최신 버전이 설치 버전보다 높은지 여부."""

    # SkillLoader 연동 상태
    is_loaded: bool = False
    """SkillLoader가 이 스킬을 로드했는지 여부."""

    is_active: bool = False
    """현재 대화 세션에서 활성화되었는지 여부."""

    security_passed: bool = True
    """최근 보안 스캔 통과 여부."""

    security_findings: list[dict[str, object]] = field(default_factory=list)
    """보안 스캔 결과 상세."""

    def to_dict(self) -> JsonObject:
        return {
            "skill_name": self.skill_name,
            "package_name": self.package_name,
            "version": self.version,
            "latest_version": self.latest_version,
            "description": self.description,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "risk_level": self.risk_level,
            "trust_level": self.trust_level,
            "requires_approval": self.requires_approval,
            "mcp_server_id": self.mcp_server_id,
            "is_outdated": self.is_outdated,
            "is_loaded": self.is_loaded,
            "is_active": self.is_active,
            "security_passed": self.security_passed,
        }


# ─── 레지스트리 메인 클래스 ──────────────────────────────────────────


@final
class SkillMarketRegistry:
    """마켓 스킬 레지스트리.

    SkillMarketClient (검색/상태) + SkillInstaller (설치/제거) + SkillLoader (로드)
    를 통합하여 CLI/Slash 명령어에 단일 API를 제공합니다.

    통합 포인트:
      - search / get_detail          → SkillMarketClient
      - install / update / remove    → SkillInstaller
      - list_installed / check_loaded → SkillMarketClient + SkillLoader
    """

    def __init__(
        self,
        project_root: str | None = None,
        market_client: MarketClientProtocol | None = None,
        installer: InstallerProtocol | None = None,
        skill_loader: LoaderProtocol | None = None,
    ):
        """Initialize the SkillMarketRegistry.

        Args:
            project_root: 프로젝트 루트
            market_client: SkillMarketClient 인스턴스
            installer: SkillInstaller 인스턴스
            skill_loader: SkillLoader 인스턴스
        """
        self.project_root = project_root or "."
        self.market_client: MarketClientProtocol | None = market_client
        self.installer: InstallerProtocol | None = installer
        self.skill_loader: LoaderProtocol | None = skill_loader

    # ─── 검색 ───────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> list[SearchResponse]:
        """npm 레지스트리에서 스킬을 검색합니다.

        Args:
            query: 검색어
            limit: 최대 결과 수

        Returns:
            검색 결과 리스트 (설치 상태 포함)
        """
        if not self.market_client:
            logger.warning("[SkillRegistry] MarketClient not configured")
            return [{"error": "MarketClient not configured"}]

        try:
            results = self.market_client.search(query, limit)
            response: list[SearchResponse] = []
            for listing in results:
                item: SearchResponse = {
                    "name": listing.name,
                    "skill_name": listing.skill_name,
                    "version": listing.version,
                    "description": listing.description,
                    "keywords": listing.keywords,
                    "publisher": listing.publisher,
                    "date": listing.date,
                    "npm_url": listing.npm_url,
                    "homepage": listing.homepage,
                    "repository": listing.repository,
                    "is_installed": self._is_installed(listing.skill_name),
                }
                response.append(item)
            return response
        except Exception as e:
            logger.exception("[SkillRegistry] Search failed")
            return [{"error": str(e)}]

    def get_detail(self, package_name: str) -> JsonObject | None:
        """패키지 상세 정보를 조회합니다. (설치 상태 포함)

        Args:
            package_name: npm 패키지 전체 이름

        Returns:
            상세 정보 딕셔너리 또는 None
        """
        if not self.market_client:
            logger.warning("[SkillRegistry] MarketClient not configured")
            return None

        try:
            detail = self.market_client.get_detail(package_name)
            if not detail:
                return None

            installed = self._get_installed_skill(detail.skill_name)

            result: dict[str, object] = {**detail.to_dict()}
            result["is_installed"] = installed is not None
            if installed:
                result["installed_version"] = installed.version
                result["installed_path"] = installed.install_path
                result["is_outdated"] = installed.is_outdated

            return result
        except Exception:
            logger.exception("[SkillRegistry] get_detail failed")
            return None

    # ─── 설치 / 제거 / 업데이트 ────────────────────────────────────

    def install(self, package_name: str) -> InstallResponse:
        """스킬을 설치합니다.

        SkillInstaller.install()에 위임하고, 설치 후
        레지스트리 캐시를 갱신합니다.

        Args:
            package_name: npm 패키지 전체 이름

        Returns:
            설치 결과 딕셔너리
        """
        if not self.installer:
            return {"success": False, "error": "Installer not configured"}

        try:
            result = self.installer.install(package_name)
            return {
                "success": result.success,
                "action": result.action,
                "package_name": result.package_name,
                "skill_name": result.skill_name,
                "version": result.version,
                "install_path": result.install_path,
                "errors": result.errors,
                "warnings": result.warnings,
                "summary": result.summary(),
            }
        except Exception as e:
            logger.exception("[SkillRegistry] Install failed")
            return {"success": False, "error": str(e)}

    def remove(self, skill_name: str) -> InstallResponse:
        """설치된 스킬을 제거합니다.

        Args:
            skill_name: 스킬 이름 (e.g. "code-review")

        Returns:
            제거 결과 딕셔너리
        """
        if not self.installer:
            return {"success": False, "error": "Installer not configured"}

        package_name = f"{AGK_SKILL_SCOPE}{skill_name}" if not skill_name.startswith(AGK_SKILL_SCOPE) else skill_name

        try:
            result = self.installer.remove(package_name)
            return {
                "success": result.success,
                "action": result.action,
                "skill_name": result.skill_name,
                "errors": result.errors,
                "summary": result.summary(),
            }
        except Exception as e:
            logger.exception("[SkillRegistry] Remove failed")
            return {"success": False, "error": str(e)}

    def update(self, skill_name: str) -> InstallResponse:
        """설치된 스킬을 최신 버전으로 업데이트합니다.

        Args:
            skill_name: 스킬 이름 (e.g. "code-review")

        Returns:
            업데이트 결과 딕셔너리
        """
        if not self.installer:
            return {"success": False, "error": "Installer not configured"}

        package_name = f"{AGK_SKILL_SCOPE}{skill_name}" if not skill_name.startswith(AGK_SKILL_SCOPE) else skill_name

        try:
            result = self.installer.update(package_name)
            return {
                "success": result.success,
                "action": result.action,
                "package_name": result.package_name,
                "skill_name": result.skill_name,
                "version": result.version,
                "errors": result.errors,
                "warnings": result.warnings,
                "summary": result.summary(),
            }
        except Exception as e:
            logger.exception("[SkillRegistry] Update failed")
            return {"success": False, "error": str(e)}

    def update_all(self) -> list[JsonObject]:
        """모든 설치된 스킬을 최신 버전으로 업데이트합니다.

        먼저 check_updates()로 최신 버전을 확인한 후,
        outdated 스킬만 업데이트합니다.

        Returns:
            각 스킬의 업데이트 결과 리스트
        """
        outdated = self.check_updates()
        results: list[JsonObject] = []

        for skill in outdated:
            logger.info(
                "[SkillRegistry] Updating %s (%s -> %s)...", skill.skill_name, skill.version, skill.latest_version
            )
            result = self.update(skill.skill_name)
            results.append(result)

        if not results:
            logger.info("[SkillRegistry] All skills are up to date")

        return results

    # ─── 설치 상태 조회 ────────────────────────────────────────────

    def list_installed(self) -> list[RegistrySkillInfo]:
        """설치된 모든 마켓 스킬 목록을 반환합니다.

        SkillMarketClient.get_installed()와 SkillLoader의 상태를
        결합하여 완전한 RegistrySkillInfo를 생성합니다.

        Returns:
            RegistrySkillInfo 리스트
        """
        installed_map: dict[str, RegistrySkillInfo] = {}

        # 1. SkillMarketClient에서 설치 목록 가져오기
        client_installed = self._get_client_installed()
        for skill in client_installed:
            installed_map[skill.skill_name] = skill

        # 2. SkillLoader skill_id와 매칭 (market/ 디렉토리 스캔)
        loaded_ids = self._get_loaded_skill_ids()
        active_ids = self._get_active_skill_ids()

        for skill_name, info in installed_map.items():
            info.is_loaded = skill_name in loaded_ids
            info.is_active = skill_name in active_ids

        return list(installed_map.values())

    def get_info(self, skill_name: str) -> RegistrySkillInfo | None:
        """특정 스킬의 상세 정보를 반환합니다.

        설치되지 않은 스킬이면 None 반환.

        Args:
            skill_name: 스킬 이름 (e.g. "code-review")

        Returns:
            RegistrySkillInfo 또는 None
        """
        installed = self.list_installed()
        for skill in installed:
            if skill.skill_name == skill_name:
                return skill
        return None

    def check_updates(self) -> list[RegistrySkillInfo]:
        """모든 설치된 스킬의 최신 버전을 확인합니다.

        각 스킬의 latest_version과 is_outdated를 업데이트합니다.

        Returns:
            업데이트가 필요한 스킬 목록 (최신 버전 포함)
        """
        installed = self.list_installed()
        needs_update: list[RegistrySkillInfo] = []

        for skill in installed:
            if not self.market_client:
                continue

            try:
                package_name = skill.package_name or f"{AGK_SKILL_SCOPE}{skill.skill_name}"
                detail = self.market_client.get_detail(package_name)
                if detail and detail.version:
                    skill.latest_version = detail.version
                    skill.is_outdated = (
                        self._version_gte(skill.latest_version, skill.version) and skill.latest_version != skill.version
                    )
                    if skill.is_outdated:
                        needs_update.append(skill)
            except Exception as e:
                logger.debug("[SkillRegistry] Update check failed for %s: %s", skill.skill_name, e)
                continue

        return needs_update

    # ─── 포맷팅 ────────────────────────────────────────────────────

    def format_list(self, skills: list[RegistrySkillInfo] | None = None) -> str:
        """설치된 스킬 목록을 사용자 친화적인 마크다운으로 포맷팅합니다.

        Args:
            skills: 포맷팅할 스킬 목록 (기본: 전체 설치 목록)

        Returns:
            마크다운 문자열
        """
        if skills is None:
            skills = self.list_installed()

        if not skills:
            return (
                "📦 설치된 마켓 스킬이 없습니다.\n"
                "`agk market search <query>`로 스킬을 검색하거나 "
                "`agk market install <package>`로 설치하세요."
            )

        lines = [
            "📦 **Installed Marketplace Skills**",
            "",
        ]

        for skill in skills:
            # 상태 아이콘
            if not skill.is_active:
                status_icon = "💤"
            elif skill.is_outdated:
                status_icon = "⚠️"
            else:
                status_icon = "✅"

            version_str = skill.version
            if skill.latest_version and skill.is_outdated:
                version_str += f" → {skill.latest_version} (available)"

            desc = (skill.description[:70] + "...") if len(skill.description) > 70 else skill.description

            lines.append(f"  {status_icon} **{skill.skill_name}** `v{skill.version}`")
            if skill.latest_version and skill.is_outdated:
                lines.append(f"       ⬆️ `{skill.latest_version}` available")
            if desc:
                lines.append(f"       {desc}")
            if skill.mcp_server_id:
                lines.append(f"       🔌 MCP: `{skill.mcp_server_id}`")
            lines.append("")

        return "\n".join(lines)

    def format_info(self, skill: RegistrySkillInfo) -> str:
        """개별 스킬의 상세 정보를 마크다운으로 포맷팅합니다.

        Args:
            skill: 표시할 스킬 정보

        Returns:
            마크다운 문자열
        """
        status_emoji = "✅" if skill.is_active else ("⚠️" if skill.is_outdated else "💤")
        lines = [
            f"{status_emoji} **{skill.skill_name}**",
            "",
            "| 항목 | 값 |",
            "|:---|---:|",
            f"| 패키지 | `{skill.package_name}` |",
            f"| 버전 | `{skill.version}` |",
            f"| 설명 | {skill.description} |",
            f"| 설치 경로 | `{skill.install_path}` |",
            f"| 위험도 | `{skill.risk_level}` |",
            f"| 신뢰 수준 | `{skill.trust_level}` |",
            f"| 승인 필요 | {'✅' if skill.requires_approval else '❌'} |",
            f"| 보안 검사 | {'✅ 통과' if skill.security_passed else '⚠️ 이슈 있음'} |",
            f"| 로드됨 | {'✅' if skill.is_loaded else '❌'} |",
            f"| 활성화 | {'✅' if skill.is_active else '❌'} |",
        ]

        if skill.mcp_server_id:
            lines.append(f"| MCP 서버 | `{skill.mcp_server_id}` |")

        if skill.latest_version:
            if skill.is_outdated:
                lines.append(f"| 업데이트 | ⬆️ `{skill.version}` → `{skill.latest_version}` |")
            else:
                lines.append(f"| 최신 버전 | `{skill.latest_version}` (최신) |")

        if skill.installed_at:
            lines.append(f"| 설치 일시 | {skill.installed_at[:19]} |")
        if skill.updated_at:
            lines.append(f"| 업데이트 | {skill.updated_at[:19]} |")

        if skill.security_findings:
            lines.append("")
            lines.append("**보안 검사 상세:**")
            for finding in skill.security_findings[:5]:
                severity = finding.get("severity")
                severity_key = severity if isinstance(severity, str) else ""
                severity_icon = {"error": "🔴", "warning": "🟡", "info": "ℹ️"}.get(severity_key, "ℹ️")
                message = finding.get("message")
                message_text = message if isinstance(message, str) else ""
                line = finding.get("line")
                line_number = line if isinstance(line, int) else 0
                lines.append(f"  {severity_icon} {message_text} ({finding.get('file', '')}:{line_number})")

        lines.append("")
        lines.append(f"**CLI 명령어:** `agk market info {skill.skill_name}`")
        lines.append(f"**제거:** `agk market remove {skill.skill_name}`")

        return "\n".join(lines)

    # ─── 상태 요약 ─────────────────────────────────────────────────

    def summary(self) -> str:
        """레지스트리 전체 상태 요약을 반환합니다."""
        installed = self.list_installed()
        outdated = [s for s in installed if s.is_outdated]
        active = [s for s in installed if s.is_active]

        lines = [
            "## 📊 Skill Marketplace Status",
            "",
            f"- **총 설치 스킬:** {len(installed)}개",
            f"- **활성화:** {len(active)}개",
            f"- **업데이트 가능:** {len(outdated)}개",
        ]

        if outdated:
            lines.append("")
            lines.append("**업데이트 필요:**")
            for skill in outdated:
                lines.append(f"  - `{skill.skill_name}`: {skill.version} → {skill.latest_version}")

        if active:
            lines.append("")
            lines.append("**활성 스킬:**")
            for skill in active:
                lines.append(f"  - `{skill.skill_name}`")

        return "\n".join(lines)

    # ─── 내부 ───────────────────────────────────────────────────────

    def _is_installed(self, skill_name: str) -> bool:
        """스킬 설치 여부 확인."""
        return self.get_info(skill_name) is not None

    def _get_client_installed(self) -> list[RegistrySkillInfo]:
        """SkillMarketClient.get_installed() → RegistrySkillInfo 변환."""
        if not self.market_client:
            return []

        try:
            installed = self.market_client.get_installed(self.project_root)
            return [
                RegistrySkillInfo(
                    skill_name=s.skill_name,
                    package_name=s.name,
                    version=s.version,
                    description=s.description,
                    install_path=s.install_path,
                    installed_at=s.installed_at,
                    updated_at=s.updated_at,
                    risk_level=s.risk_level,
                    trust_level=s.trust_level,
                    requires_approval=s.requires_approval,
                    mcp_server_id=s.mcp_server_id,
                )
                for s in installed
            ]
        except Exception:
            logger.exception("[SkillRegistry] Failed to get client installed")
            return []

    def _get_loaded_skill_ids(self) -> set[str]:
        """SkillLoader가 로드한 스킬 ID 집합.

        참고: SkillLoader.list_skills()는 모든 소스 디렉토리(글로벌, 로컬 .agent/skills/,
        .agent/skills/market/)의 스킬을 반환합니다. 동일한 이름의 로컬 스킬이 있으면
        마켓 스킬의 is_loaded가 정확하지 않을 수 있습니다. (Phase 1 D10 한계)
        추후 SkillLoader에 source 필터링 기능이 추가되면 개선 예정.
        """
        if not self.skill_loader:
            return set()
        try:
            loaded_ids: set[str] = set()
            for skill in self.skill_loader.list_skills():
                skill_id = skill.get("id")
                if isinstance(skill_id, str):
                    loaded_ids.add(skill_id)
            return loaded_ids
        except Exception:
            return set()

    def _get_active_skill_ids(self) -> set[str]:
        """SkillLoader의 활성 스킬 ID 집합."""
        if not self.skill_loader:
            return set()
        try:
            return set(self.skill_loader.active_skills)
        except Exception:
            return set()

    def _get_installed_skill(self, skill_name: str) -> RegistrySkillInfo | None:
        """이름으로 설치된 스킬 정보 조회 (내부용)."""
        installed = self._get_client_installed()
        for s in installed:
            if s.skill_name == skill_name:
                return s
        return None

    @staticmethod
    def _version_gte(a: str, b: str) -> bool:
        """semver 비교: a >= b"""

        def _parse(v: str) -> tuple[int, int, int]:
            parts = v.split(".")
            return (
                int(parts[0]) if len(parts) > 0 else 0,
                int(parts[1]) if len(parts) > 1 else 0,
                int(parts[2]) if len(parts) > 2 else 0,
            )

        return _parse(a) >= _parse(b)
