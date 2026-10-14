"""Skill Installer — npm 패키지를 설치/업데이트/제거합니다.

==========================================================
Phase 1 D9: npm install → package.json 검증 → 보안 스캔 →
.agent/skills/market/<name>/ 복사 → MCP 설정 → SkillLoader.refresh()

사용법:
    installer = SkillInstaller(project_root, market_client, skill_loader)
    result = installer.install("@antigravity-k/skill-code-review")
    result = installer.update("@antigravity-k/skill-code-review")
    success = installer.remove("code-review")
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast, final

logger = logging.getLogger(__name__)

# ─── 상수 ─────────────────────────────────────────────────────────────

AGK_SKILL_SCOPE = "@antigravity-k/skill-"
MARKET_DIR = ".agent/skills/market"


def _as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


# ─── 데이터 모델 ──────────────────────────────────────────────────────


@dataclass
class InstallValidation:
    """패키지 검증 결과."""

    valid: bool = False
    """검증 통과 여부."""

    reason: str = ""
    """실패 사유 (valid=False일 때)."""

    warnings: list[str] = field(default_factory=list)
    """경고 메시지 목록."""

    package_name: str = ""
    """npm 패키지명."""

    version: str = ""
    """설치할 버전."""

    risk_level: str = "safe"
    """위험도 (package.json antigravityK.riskLevel)."""

    trust_level: str = "experimental"
    """신뢰 수준 (package.json antigravityK.trustLevel)."""

    requires_approval: bool = False
    """설치/활성화 시 사용자 승인 필요 여부."""

    mcp_server_id: str = ""
    """MCP 스킬인 경우 MCP 서버 ID."""


@dataclass
class SecurityFinding:
    """보안 스캔 결과 하나."""

    severity: str  # "error" | "warning" | "info"
    message: str
    file: str = ""
    line: int = 0


@dataclass
class SecurityReport:
    """보안 스캔 결과."""

    passed: bool = True
    findings: list[SecurityFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[SecurityFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[SecurityFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def summary(self) -> str:
        parts: list[str] = []
        if self.errors:
            parts.append(f"🔴 {len(self.errors)} errors")
        if self.warnings:
            parts.append(f"🟡 {len(self.warnings)} warnings")
        if not parts:
            return "✅ 보안 검사 통과"
        return ", ".join(parts)


@dataclass
class InstallResult:
    """설치/업데이트/제거 결과."""

    success: bool = False
    """작업 성공 여부."""

    action: str = ""
    """수행한 작업 (install / update / remove)."""

    package_name: str = ""
    """npm 패키지명."""

    skill_name: str = ""
    """스킬 짧은 이름."""

    version: str = ""
    """설치/업데이트된 버전."""

    install_path: str = ""
    """설치 경로 (market/<name>/)."""

    validation: InstallValidation | None = None
    """패키지 검증 결과."""

    security: SecurityReport | None = None
    """보안 스캔 결과."""

    errors: list[str] = field(default_factory=list)
    """오류 메시지 목록."""

    warnings: list[str] = field(default_factory=list)
    """경고 메시지 목록."""

    @property
    def has_error(self) -> bool:
        return bool(self.errors) or not self.success

    def summary(self) -> str:
        """사용자 친화적인 결과 요약 문자열."""
        if self.action == "remove":
            if self.success:
                return f"🗑️  `{self.skill_name}` 제거 완료"
            return f"❌ `{self.skill_name}` 제거 실패: {'; '.join(self.errors)}"

        if not self.success:
            return f"❌ {self.package_name} 설치 실패: {'; '.join(self.errors)}"

        parts = [f"✅ `{self.package_name}@{self.version}` 설치 완료"]
        if self.install_path:
            parts.append(f"   📍 {self.install_path}")
        if self.security and not self.security.passed:
            parts.append(f"   ⚠️  {self.security.summary()}")
        if self.validation and self.validation.requires_approval:
            parts.append("   🔒 사용자 승인 필요 (requiresApproval=true)")
        if self.warnings:
            for w in self.warnings[:3]:
                parts.append(f"   ⚠️  {w}")
        return "\n".join(parts)


# ─── 위험 패턴 (보안 스캔용) ─────────────────────────────────────────


_SUSPICIOUS_PATTERNS: list[tuple[str, str, str]] = [
    ("error", r"(?i)(rm\s+-rf|sudo\s+.*|chmod\s+777|curl\s+.*\||wget\s+.*\||eval\s+|exec\s+)", "위험한 셸 명령어 감지"),
    ("error", r"(?i)(base64\.(b64)?decode|exec\(|eval\(|__import__|compile\()", "동적 코드 실행 패턴 감지"),
    (
        "warning",
        r"(?i)(API[_-]?KEY|api[_-]?key|SECRET|password|token|credential|auth_token)",
        "민감정보 참조 패턴 감지",
    ),
    ("warning", r"(?i)(http[s]?://[^\s]*\.(exe|sh|bat|ps1|dmg|pkg))\b", "외부 바이너리 다운로드 패턴"),
    ("info", r"(?i)(requires_approval|risk_level|trust_level)", "보안 정책 설정 감지"),
]


# ─── 메인 클래스 ──────────────────────────────────────────────────────


@final
class SkillInstaller:
    """npm 패키지 기반 스킬 설치/업데이트/제거 관리자.

    설치 플로우:
        1. npm install --no-save → node_modules/ 다운로드
        2. package.json 검증 (antigravityK.skill, minAgentVersion, platforms)
        3. 보안 스캔 (SKILL.md + references/)
        4. .agent/skills/market/<name>/ 로 복사
        5. (MCP 스킬) .mcp.json 자동 설정
        6. SkillLoader.refresh() 호출
        7. node_modules 정리
    """

    def __init__(
        self,
        project_root: str | None = None,
        market_client: object | None = None,
        skill_loader: object | None = None,
    ):
        """Initialize the SkillInstaller.

        Args:
            project_root: 프로젝트 루트 (기본: 현재 디렉토리)
            market_client: SkillMarketClient 인스턴스 (설치 기록 관리용)
            skill_loader: SkillLoader 인스턴스 (설치 후 refresh용)
        """
        self.project_root = Path(project_root or os.getcwd())
        self.market_dir = self.project_root / MARKET_DIR
        self.market_client = market_client
        self.skill_loader = skill_loader

    # ─── 공개 API ──────────────────────────────────────────────────

    def install(self, package_name: str) -> InstallResult:
        """npm 패키지를 설치합니다.

        Args:
            package_name: npm 패키지 전체 이름 (e.g. "@antigravity-k/skill-code-review")

        Returns:
            InstallResult
        """
        result = InstallResult(action="install", package_name=package_name)
        skill_name = self._parse_skill_name(package_name)
        result.skill_name = skill_name

        # Step 1: npm install
        logger.info("[SkillInstaller] Installing %s...", package_name)
        npm_ok, npm_path, _npm_version, npm_err = self._npm_install(package_name)
        if not npm_ok:
            result.errors.append(f"npm install 실패: {npm_err}")
            return result

        # Step 2: Validate package.json
        validation = self._validate_package(npm_path, package_name)
        result.validation = validation
        result.version = validation.version
        if not validation.valid:
            result.errors.append(validation.reason)
            self._cleanup_npm(npm_path)
            return result

        # Step 3: Security scan (best-effort, non-blocking)
        security = self._security_scan(npm_path, skill_name)
        result.security = security
        if security and not security.passed and security.errors:
            logger.warning(
                "[SkillInstaller] Security findings for %s: %s",
                package_name,
                security.summary(),
            )

        # Step 4: Copy to market directory
        dest_dir = self.market_dir / skill_name
        copy_ok, copy_err = self._copy_to_market(npm_path, dest_dir)
        if not copy_ok:
            result.errors.append(f"복사 실패: {copy_err}")
            self._cleanup_npm(npm_path)
            return result
        result.install_path = str(dest_dir)

        # Step 5: MCP setup (if applicable)
        if validation.mcp_server_id:
            mcp_warnings = self._setup_mcp(dest_dir, validation)
            result.warnings.extend(mcp_warnings)

        # Step 6: Write .agk_meta.json
        self._write_meta(dest_dir, package_name, validation, security)

        # Step 7: Record installation in market client
        if self.market_client is not None:
            record_installation = getattr(self.market_client, "record_installation", None)
            if not callable(record_installation):
                record_installation = None
        else:
            record_installation = None
        if record_installation is not None:
            try:
                _ = cast(Callable[[str, str, str], object], record_installation)(
                    package_name, validation.version, str(dest_dir)
                )
            except (AttributeError, TypeError, ConnectionError) as e:
                logger.warning("[SkillInstaller] Failed to record installation: %s", e)

        # Step 8: Refresh SkillLoader
        if self.skill_loader is not None:
            refresh = getattr(self.skill_loader, "refresh", None)
            if not callable(refresh):
                refresh = None
        else:
            refresh = None
        if refresh is not None:
            try:
                _ = cast(Callable[[], object], refresh)()
            except (AttributeError, TypeError, ConnectionError) as e:
                logger.warning("[SkillInstaller] SkillLoader refresh failed: %s", e)

        # Step 9: Cleanup npm artifacts
        self._cleanup_npm(npm_path)

        # Collect warnings
        if validation.warnings:
            result.warnings.extend(validation.warnings)
        if validation.requires_approval:
            result.warnings.append("이 스킬은 활성화 시 사용자 승인이 필요합니다.")

        result.success = True
        logger.info("[SkillInstaller] Installed %s@%s → %s", package_name, validation.version, dest_dir)
        return result

    def update(self, package_name: str) -> InstallResult:
        """설치된 스킬을 최신 버전으로 업데이트합니다.

        기존 설치 디렉토리를 삭제하고 새로 설치합니다.

        Args:
            package_name: npm 패키지 전체 이름

        Returns:
            InstallResult
        """
        skill_name = self._parse_skill_name(package_name)

        # 기존 설치 제거
        existing_path = self.market_dir / skill_name
        if existing_path.exists():
            shutil.rmtree(existing_path)
            logger.info("[SkillInstaller] Removed old installation: %s", existing_path)

        # 새로 설치
        result = self.install(package_name)
        result.action = "update"
        return result

    def remove(self, package_name: str) -> InstallResult:
        """설치된 스킬을 제거합니다.

        .agent/skills/market/<name>/ 디렉토리 + 글로벌 상태 파일 기록을 삭제합니다.

        Args:
            package_name: npm 패키지 전체 이름 또는 스킬 짧은 이름

        Returns:
            InstallResult
        """
        skill_name = self._parse_skill_name(package_name) or package_name
        result = InstallResult(action="remove", package_name=package_name, skill_name=skill_name)

        dest_dir = self.market_dir / skill_name

        # 디렉토리 제거
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
            logger.info("[SkillInstaller] Removed directory: %s", dest_dir)
        else:
            logger.info("[SkillInstaller] Directory not found: %s", dest_dir)

        # 글로벌 상태 파일에서 제거
        if self.market_client is not None:
            remove_installation = getattr(self.market_client, "remove_installation", None)
            if not callable(remove_installation):
                remove_installation = None
        else:
            remove_installation = None
        if remove_installation is not None:
            try:
                _ = cast(Callable[[str], object], remove_installation)(skill_name)
            except (AttributeError, TypeError, ConnectionError) as e:
                logger.warning("[SkillInstaller] Failed to remove installation record: %s", e)

        # SkillLoader refresh
        if self.skill_loader is not None:
            refresh = getattr(self.skill_loader, "refresh", None)
            if not callable(refresh):
                refresh = None
        else:
            refresh = None
        if refresh is not None:
            try:
                _ = cast(Callable[[], object], refresh)()
            except (AttributeError, TypeError, ConnectionError) as e:
                logger.warning("[SkillInstaller] SkillLoader refresh failed: %s", e)

        result.success = True
        return result

    # ─── 설치 서브스텝 ─────────────────────────────────────────────

    def _npm_install(self, package_name: str) -> tuple[bool, Path, str, str]:
        """Step 1: npm install --no-save를 실행하고 임시 경로를 반환합니다.

        Returns:
            (성공여부, node_modules/<pkg>/ 경로, 버전, 오류메시지)
        """
        try:
            result = subprocess.run(
                ["npm", "install", "--no-save", "--prefix", str(self.project_root), package_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                return False, Path(), "", stderr

            # 설치된 패키지 경로 탐색
            npm_pkg_dir = self.project_root / "node_modules" / package_name
            if not npm_pkg_dir.exists():
                return False, Path(), "", f"npm install completed but package not found at {npm_pkg_dir}"

            # 버전 확인
            pkg_json_path = npm_pkg_dir / "package.json"
            if pkg_json_path.exists():
                try:
                    pkg_json = _as_mapping(cast(object, json.loads(pkg_json_path.read_text(encoding="utf-8"))))
                    version = _as_text(pkg_json.get("version"), "0.0.0")
                except (json.JSONDecodeError, OSError):
                    version = "0.0.0"
            else:
                version = "0.0.0"

            return True, npm_pkg_dir, version, ""

        except subprocess.TimeoutExpired:
            return False, Path(), "", "npm install timed out (120s)"
        except FileNotFoundError:
            return False, Path(), "", "npm CLI not found. Install Node.js/npm first."
        except (OSError, ValueError) as e:
            return False, Path(), "", str(e)

    def _validate_package(self, npm_path: Path, package_name: str) -> InstallValidation:
        """Step 2: 패키지의 package.json을 검증합니다.

        검증 항목:
          - package.json 존재
          - antigravityK.skill === true
          - minAgentVersion <= 현재 AGK 버전 (선택)
          - platforms (현재 플랫폼 포함되어 있는지)

        Args:
            npm_path: node_modules/<package>/ 경로
            package_name: npm 패키지명

        Returns:
            InstallValidation
        """
        pkg_json_path = npm_path / "package.json"
        if not pkg_json_path.exists():
            return InstallValidation(valid=False, reason=f"package.json not found in {npm_path}")

        try:
            pkg_json = _as_mapping(cast(object, json.loads(pkg_json_path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as e:
            return InstallValidation(valid=False, reason=f"package.json parse error: {e}")

        version = _as_text(pkg_json.get("version"), "0.0.0")
        agk = _as_mapping(pkg_json.get("antigravityK"))

        # (2-1) 스킬 패키지 여부 — 완화된 검증
        # 다음 중 하나를 만족하면 스킬로 인정:
        #   a. antigravityK.skill === true (공식 AGK 스킬)
        #   b. @antigravity-k/skill-* 스코프
        #   c. package.json에 "skills" 또는 "skill" 키워드 포함
        #   d. 패키지 내에 SKILL.md 파일 존재
        skill_flag = bool(agk.get("skill", False)) or package_name.startswith(AGK_SKILL_SCOPE)
        if not skill_flag:
            # 키워드 기반 완화 검증
            keywords = _as_str_list(pkg_json.get("keywords"))
            has_skill_keyword = any(
                kw in keywords
                for kw in ["skill", "skills", "agent", "ai-agent", "claude", "antigravity", "agentic", "prompt", "mcp"]
            )
            has_skill_md = (npm_path / "SKILL.md").exists() or any(
                (npm_path / d / "SKILL.md").exists() for d in ["skills", "src", "dist"] if (npm_path / d).is_dir()
            )
            if has_skill_keyword or has_skill_md:
                skill_flag = True
            else:
                return InstallValidation(
                    valid=False,
                    package_name=package_name,
                    version=version,
                    reason=(
                        f"'{package_name}'는 스킬 패키지가 아닙니다. "
                        "스킬 패키지는 antigravityK.skill=true, skill 키워드, "
                        "또는 SKILL.md 파일을 포함해야 합니다."
                    ),
                )

        # (2-2) minAgentVersion 검증 (선택)
        min_version = _as_text(agk.get("minAgentVersion"))
        if min_version:
            current_version = self._get_agk_version()
            if current_version and not self._version_gte(current_version, min_version):
                return InstallValidation(
                    valid=False,
                    package_name=package_name,
                    version=version,
                    reason=f"AGK 버전 {current_version}이(가) 필요 버전 {min_version}보다 낮습니다",
                )

        # (2-3) platforms 검증 (선택)
        platforms = _as_str_list(agk.get("platforms"))
        if platforms:
            current_platform = self._get_current_platform()
            if current_platform not in platforms and "all" not in platforms:
                return InstallValidation(
                    valid=False,
                    package_name=package_name,
                    version=version,
                    reason=f"현재 플랫폼({current_platform})이 지원되지 않습니다 (지원: {', '.join(platforms)})",
                )

        # (2-4) 위험도 / 신뢰도
        risk_level = _as_text(agk.get("riskLevel"), "safe") or "safe"
        trust_level = _as_text(agk.get("trustLevel"), "experimental") or "experimental"
        requires_approval = bool(agk.get("requiresApproval", False))

        # (2-5) MCP 설정 (선택)
        mcp = _as_mapping(agk.get("mcp"))
        mcp_server_id = _as_text(mcp.get("serverId"))

        warnings: list[str] = []
        if risk_level in ("high", "critical"):
            warnings.append(f"위험도 '{risk_level}' — 설치 전 검토 필요")
        if trust_level == "experimental":
            warnings.append("신뢰 수준 'experimental' — 공식 검증되지 않은 스킬입니다")
        if requires_approval:
            warnings.append("이 스킬은 사용자 승인 없이 자동 활성화되지 않습니다")

        return InstallValidation(
            valid=True,
            package_name=package_name,
            version=version,
            risk_level=risk_level,
            trust_level=trust_level,
            requires_approval=requires_approval,
            mcp_server_id=mcp_server_id,
            warnings=warnings,
        )

    def _security_scan(self, npm_path: Path, skill_name: str) -> SecurityReport:
        """Step 3: SKILL.md + references/ 의심스러운 패턴 스캔.

        Args:
            npm_path: node_modules/<package>/ 경로
            skill_name: 스킬 짧은 이름

        Returns:
            SecurityReport
        """
        _ = skill_name
        findings: list[SecurityFinding] = []

        scan_targets: list[Path] = []
        skill_md = npm_path / "SKILL.md"
        if skill_md.exists():
            scan_targets.append(skill_md)

        ref_dir = npm_path / "references"
        if ref_dir.exists() and ref_dir.is_dir():
            for ref_file in sorted(ref_dir.iterdir()):
                if ref_file.suffix in (".md", ".txt", ".yaml", ".yml"):
                    scan_targets.append(ref_file)

        for target in scan_targets:
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")

                for severity, pattern, message in _SUSPICIOUS_PATTERNS:
                    for line_no, line in enumerate(lines, 1):
                        if re.search(pattern, line):
                            findings.append(
                                SecurityFinding(
                                    severity=severity,
                                    message=message,
                                    file=str(target.relative_to(npm_path)),
                                    line=line_no,
                                )
                            )
            except (OSError, UnicodeDecodeError):
                continue

        passed = not any(f.severity == "error" for f in findings)
        return SecurityReport(passed=passed, findings=findings)

    def _copy_to_market(self, src: Path, dest: Path) -> tuple[bool, str]:
        """Step 4: node_modules/<pkg>/ → .agent/skills/market/<name>/ 복사.

        package.json, SKILL.md, references/, tests/, .agkignore 기준 필터링.

        Args:
            src: node_modules/<package>/ 경로
            dest: .agent/skills/market/<name>/ 경로

        Returns:
            (성공여부, 오류메시지)
        """
        try:
            # 대상 디렉토리가 이미 존재하면 제거 후 생성
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)

            # 복사할 항목
            items_to_copy = ["package.json", "SKILL.md", "references", "tests"]
            agkignore = src / ".agkignore"
            if agkignore.exists():
                try:
                    ignore_list = [
                        line.strip()
                        for line in agkignore.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.strip().startswith("#")
                    ]
                    items_to_copy = [i for i in items_to_copy if i not in ignore_list]
                except OSError:
                    logger.warning("[SkillInstaller] 스킬 설치 단계 실패 (non-critical)", exc_info=True)

            for item in items_to_copy:
                src_item = src / item
                if src_item.exists():
                    if src_item.is_dir():
                        _ = shutil.copytree(src_item, dest / item, dirs_exist_ok=True)
                    else:
                        _ = shutil.copy2(src_item, dest / item)

            return True, ""

        except OSError as e:
            return False, str(e)

    def _setup_mcp(self, dest_dir: Path, validation: InstallValidation) -> list[str]:
        """Step 5: MCP 스킬인 경우 .mcp.json에 서버 설정을 추가합니다.

        Phase 1 D11: MCPServerRegistry에 스킬 MCP 서버를 등록하고,
        .mcp.json에도 자동 추가합니다.

        Args:
            dest_dir: 스킬 설치 경로
            validation: 패키지 검증 결과

        Returns:
            경고 메시지 목록
        """
        warnings: list[str] = []
        server_id = validation.mcp_server_id
        if not server_id:
            return warnings

        mcp_json_path = self.project_root / ".mcp.json"

        try:
            # MCPServerRegistry에 스킬 MCP 서버 등록 (Phase 1 D11)
            try:
                from antigravity_k.tools.mcp_tool_loader import MCPServerRegistry

                registry = MCPServerRegistry()
                catalog = registry.get_all()

                # 스킬명 추출
                skill_name = self._parse_skill_name(validation.package_name) or server_id

                # 카탈로그 또는 다른 스킬이 등록한 서버인지 확인
                existing_config = _as_mapping(catalog.get(server_id))

                if existing_config:
                    # 이미 존재하는 서버 — 스킬 소유권 등록
                    if existing_config.get("source") != "skill":
                        # 카탈로그 서버를 스킬 소유로 등록
                        _ = registry.register_skill_mcp(
                            skill_name,
                            {
                                "serverId": server_id,
                                "command": _as_text(existing_config.get("command")),
                                "args": _as_str_list(existing_config.get("args")),
                                "env": _as_mapping(existing_config.get("env")),
                                "name": _as_text(existing_config.get("name"), skill_name),
                                "description": _as_text(existing_config.get("description")),
                            },
                        )

                    # .mcp.json에 추가
                    mcp_config: dict[str, object] = {"mcpServers": {}}
                    if mcp_json_path.exists():
                        try:
                            mcp_config = _as_mapping(
                                cast(object, json.loads(mcp_json_path.read_text(encoding="utf-8")))
                            )
                        except json.JSONDecodeError:
                            warnings.append(".mcp.json 파싱 실패 — 덮어씁니다")

                    mcp_servers = _as_mapping(mcp_config.get("mcpServers"))
                    mcp_config["mcpServers"] = mcp_servers
                    if server_id not in mcp_servers:
                        server_entry: dict[str, object] = {
                            "command": _as_text(existing_config.get("command")),
                            "args": _as_str_list(existing_config.get("args")),
                        }
                        env_value = _as_mapping(existing_config.get("env"))
                        if env_value:
                            server_entry["env"] = env_value
                        mcp_servers[server_id] = server_entry

                        _ = mcp_json_path.write_text(
                            json.dumps(mcp_config, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        logger.info(
                            "[SkillInstaller] MCP server '%s' added to .mcp.json (skill=%s)",
                            server_id,
                            skill_name,
                        )
                    else:
                        warnings.append(f"MCP 서버 '{server_id}'는 이미 .mcp.json에 등록되어 있습니다")

                else:
                    # 카탈로그에 없는 서버 — dest_dir/package.json에서 직접 MCP 설정 읽기
                    # (install flow: step 4 _copy_to_market 후, step 6 _write_meta 전이므로
                    #  .agk_meta.json은 아직 없고 package.json은 복사되어 있음)
                    pkg_json_path = dest_dir / "package.json"
                    mcp_skill_config: dict[str, object] | None = None

                    if pkg_json_path.exists():
                        try:
                            pkg_json = _as_mapping(cast(object, json.loads(pkg_json_path.read_text(encoding="utf-8"))))
                            agk = _as_mapping(pkg_json.get("antigravityK"))
                            if agk:
                                mcp_raw = _as_mapping(agk.get("mcp"))
                                if mcp_raw and mcp_raw.get("serverId") == server_id:
                                    mcp_skill_config = {
                                        "command": mcp_raw.get("command", ""),
                                        "args": _as_str_list(mcp_raw.get("args")),
                                        "env": _as_mapping(mcp_raw.get("env")),
                                    }
                        except (json.JSONDecodeError, OSError):
                            logger.warning("[SkillInstaller] 스킬 설치 단계 실패 (non-critical)", exc_info=True)

                    if mcp_skill_config and _as_text(mcp_skill_config.get("command")):
                        # 스킬 package.json의 antigravityK.mcp 설정 사용
                        _ = registry.register_skill_mcp(
                            skill_name,
                            {
                                "serverId": server_id,
                                **mcp_skill_config,
                                "name": mcp_skill_config.get("name", skill_name),
                                "description": mcp_skill_config.get(
                                    "description", f"MCP server from skill '{skill_name}'"
                                ),
                            },
                        )

                        # .mcp.json에 추가
                        mcp_config = {"mcpServers": {}}
                        if mcp_json_path.exists():
                            try:
                                mcp_config = _as_mapping(
                                    cast(object, json.loads(mcp_json_path.read_text(encoding="utf-8")))
                                )
                            except json.JSONDecodeError:
                                warnings.append(".mcp.json 파싱 실패 — 덮어씁니다")

                        mcp_servers = _as_mapping(mcp_config.get("mcpServers"))
                        mcp_config["mcpServers"] = mcp_servers
                        if server_id not in mcp_servers:
                            server_entry = {
                                "command": _as_text(mcp_skill_config.get("command")),
                                "args": _as_str_list(mcp_skill_config.get("args")),
                            }
                            env_value = _as_mapping(mcp_skill_config.get("env"))
                            if env_value:
                                server_entry["env"] = env_value
                            mcp_servers[server_id] = server_entry

                            _ = mcp_json_path.write_text(
                                json.dumps(mcp_config, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            logger.info(
                                "[SkillInstaller] MCP server '%s' added to .mcp.json (from package.json)",
                                server_id,
                            )
                    else:
                        # 설정을 찾을 수 없음 — 안내
                        warnings.append(
                            f"MCP 서버 '{server_id}' 설정을 찾을 수 없습니다. 스킬 패키지의 "
                            + "package.json > antigravityK.mcp에 command/args/env가 포함되어 있는지 "
                            + "확인하거나 .mcp.json에 수동으로 설정해주세요."
                        )

            except ImportError:
                warnings.append(f"MCP 서버 '{server_id}' 자동 설정 불가 (MCPServerRegistry import 실패)")
                return warnings

        except (OSError, json.JSONDecodeError, KeyError) as e:
            warnings.append(f".mcp.json 설정 중 오류: {e}")

        return warnings

    def _write_meta(
        self,
        dest_dir: Path,
        package_name: str,
        validation: InstallValidation,
        security: SecurityReport | None,
    ) -> None:
        """Step 6: .agk_meta.json 메타데이터 파일 작성.

        SkillMarketClient.get_installed()가 이 파일을 읽습니다.

        Args:
            dest_dir: 스킬 설치 경로
            package_name: npm 패키지명
            validation: 패키지 검증 결과
            security: 보안 스캔 결과
        """
        now = datetime.now().astimezone().replace(tzinfo=None).isoformat()
        meta: dict[str, object] = {
            "name": package_name,
            "version": validation.version,
            "description": "",
            "installed_at": now,
            "updated_at": now,
            "risk_level": validation.risk_level,
            "trust_level": validation.trust_level,
            "requires_approval": validation.requires_approval,
            "mcp_server_id": validation.mcp_server_id,
            "security_passed": security.passed if security else True,
            "findings": [
                {"severity": f.severity, "message": f.message, "file": f.file, "line": f.line}
                for f in (security.findings if security else [])
            ]
            if security
            else [],
        }

        # Phase 1 D11: package.json의 antigravityK.mcp 설정을 meta에 저장
        # (SkillInstaller._setup_mcp()에서 MCP 서버 설정을 읽을 수 있음)
        try:
            pkg_json_path = dest_dir / "package.json"
            if pkg_json_path.exists():
                pkg_json = _as_mapping(cast(object, json.loads(pkg_json_path.read_text(encoding="utf-8"))))
                agk = _as_mapping(pkg_json.get("antigravityK"))
                mcp = _as_mapping(agk.get("mcp"))
                if mcp.get("serverId") == validation.mcp_server_id:
                    # mcp 필드에 command/args/env가 포함되어 있으면 저장
                    mcp_config: dict[str, object] = {}
                    command = _as_text(mcp.get("command"))
                    if command:
                        mcp_config["command"] = command
                    args = _as_str_list(mcp.get("args"))
                    if args:
                        mcp_config["args"] = args
                    env = _as_mapping(mcp.get("env"))
                    if env:
                        mcp_config["env"] = env
                    if mcp_config:
                        meta["mcp_config"] = mcp_config
        except (json.JSONDecodeError, OSError):
            logger.warning("[SkillInstaller] 스킬 설치 단계 실패 (non-critical)", exc_info=True)

        try:
            meta_path = dest_dir / ".agk_meta.json"
            _ = meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("[SkillInstaller] Failed to write .agk_meta.json: %s", e)

    def _cleanup_npm(self, npm_path: Path) -> None:
        """Step 9: node_modules/<pkg>/ 디렉토리 정리.

        npm install --no-save로 생성된 node_modules 항목을 제거합니다.
        """
        try:
            if npm_path.exists() and npm_path.is_dir():
                shutil.rmtree(npm_path)
                logger.debug("[SkillInstaller] Cleaned up: %s", npm_path)
        except OSError as e:
            logger.warning("[SkillInstaller] Cleanup failed for %s: %s", npm_path, e)

    # ─── 유틸리티 ──────────────────────────────────────────────────

    @staticmethod
    def _parse_skill_name(package_name: str) -> str:
        """패키지명에서 스킬 짧은 이름을 추출합니다.

        "@antigravity-k/skill-code-review" → "code-review"
        "code-review"                          → "code-review" (그대로)
        """
        if package_name.startswith(AGK_SKILL_SCOPE):
            return package_name[len(AGK_SKILL_SCOPE) :]
        return package_name

    @staticmethod
    def _get_agk_version() -> str:
        """현재 AGK 버전을 반환합니다."""
        try:
            from antigravity_k import __version__

            return str(__version__)
        except (ImportError, AttributeError):
            logger.warning("[SkillInstaller] 스킬 설치 단계 실패 (non-critical)", exc_info=True)
        try:
            # pyproject.toml에서 버전 읽기
            pyproject = Path(os.getcwd()) / "pyproject.toml"
            if pyproject.exists():
                for line in pyproject.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("version ="):
                        return line.split("=")[1].strip().strip('"').strip("'")
        except OSError:
            logger.warning("[SkillInstaller] 스킬 설치 단계 실패 (non-critical)", exc_info=True)
        return ""

    @staticmethod
    def _get_current_platform() -> str:
        """현재 플랫폼 식별자를 반환합니다. (darwin, linux, win32)"""
        import sys

        return sys.platform

    @staticmethod
    def _version_gte(current: str, required: str) -> bool:
        """current >= required 버전 비교 (semver).

        Args:
            current: 현재 AGK 버전 (e.g. "1.2.3")
            required: 필요 버전 (e.g. "1.0.0")

        Returns:
            current >= required
        """

        def _parse(v: str) -> tuple[int, int, int]:
            parts = v.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)

        return _parse(current) >= _parse(required)
