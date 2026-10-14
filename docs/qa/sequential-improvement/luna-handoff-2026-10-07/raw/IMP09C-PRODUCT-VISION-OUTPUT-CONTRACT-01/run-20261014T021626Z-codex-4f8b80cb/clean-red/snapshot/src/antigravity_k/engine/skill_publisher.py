"""Skill Publisher — 로컬 스킬을 npm 레지스트리 또는 GitHub PR로 배포합니다.

==========================================================
Phase 1 D17: 로컬 스킬 디렉토리(.agent/skills/market/<name>/)를
npm 패키지로 publish하거나 GitHub PR로 제출.

사용법:
    publisher = SkillPublisher(project_root=".")
    result = publisher.publish_to_npm("my-skill")
    result = publisher.publish_to_github("my-skill", repo="org/skills-repo")
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, cast

logger = logging.getLogger(__name__)

# ─── 상수 ─────────────────────────────────────────────────────────────

AGK_SKILL_SCOPE = "@antigravity-k/skill-"
MARKET_DIR = ".agent/skills/market"
LOCAL_SKILLS_DIR = ".agent/skills"
PUBLISH_TEMPLATE_VERSION = "1.0.0"

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _as_json_map(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {str(key): cast(JsonValue, item) for key, item in mapping.items()}


# ─── 데이터 모델 ──────────────────────────────────────────────────────


@dataclass
class PublishValidation:
    """publish 전 검증 결과."""

    valid: bool = False
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    skill_name: str = ""
    package_name: str = ""
    version: str = PUBLISH_TEMPLATE_VERSION
    has_skill_md: bool = False
    has_readme: bool = False
    has_agk_meta: bool = False
    tool_count: int = 0


@dataclass
class PublishResult:
    """publish 결과."""

    success: bool = False
    action: str = ""  # "npm_publish" | "github_pr"
    skill_name: str = ""
    package_name: str = ""
    version: str = ""
    npm_url: str = ""
    pr_url: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    publish_path: str = ""

    @property
    def has_error(self) -> bool:
        return bool(self.errors) or not self.success

    def summary(self) -> str:
        """사용자 친화적인 결과 요약."""
        if not self.success:
            return f"❌ `{self.skill_name}` publish 실패: {'; '.join(self.errors)}"

        if self.action == "npm_publish":
            parts = [f"✅ `{self.package_name}@{self.version}` npm publish 완료"]
            if self.npm_url:
                parts.append(f"   📦 {self.npm_url}")
            return "\n".join(parts)

        if self.action == "github_pr":
            parts = [f"✅ `{self.skill_name}` GitHub PR 생성 완료"]
            if self.pr_url:
                parts.append(f"   🔀 {self.pr_url}")
            return "\n".join(parts)

        return f"✅ `{self.skill_name}` publish 완료"


# ─── 메인 클래스 ──────────────────────────────────────────────────────


class SkillPublisher:
    """로컬 스킬을 npm 레지스트리 또는 GitHub PR로 배포합니다.

    npm publish:
        1. 로컬 스킬 디렉토리 검증
        2. 임시 디렉토리에 패키지 구조 생성 (package.json + SKILL.md 등)
        3. npm publish 실행
        4. 정리

    GitHub PR:
        1. 로컬 스킬 디렉토리 검증
        2. 대상 리포지토리 clone/fetch
        3. 브랜치 생성 + 스킬 파일 복사
        4. commit + push + PR 생성
        5. 정리
    """

    SKILL_REQUIRED_FILES: Final = {"SKILL.md"}

    def __init__(self, project_root: str | None = None):
        """Initialize the SkillPublisher.

        Args:
            project_root: 프로젝트 루트 (기본: 현재 디렉토리)
        """
        self.project_root: Path = Path(project_root or os.getcwd())
        self.market_dir: Path = self.project_root / MARKET_DIR
        self.skills_dir: Path = self.project_root / LOCAL_SKILLS_DIR

    # ─── Public API ────────────────────────────────────────────────

    def publish_to_npm(
        self,
        skill_name: str,
        *,
        version: str | None = None,
        tag: str = "latest",
        dry_run: bool = False,
    ) -> PublishResult:
        """로컬 스킬을 npm 레지스트리에 publish합니다.

        Args:
            skill_name: 스킬 이름 (디렉토리명, e.g. "code-review")
            version: publish할 버전 (기본: SKILL.md frontmatter 또는 1.0.0)
            tag: npm dist-tag (기본: "latest")
            dry_run: 실제 publish 없이 검증만 수행

        Returns:
            PublishResult
        """
        result = PublishResult(action="npm_publish", skill_name=skill_name)
        package_name = f"{AGK_SKILL_SCOPE}{skill_name}"
        result.package_name = package_name

        # 0. 패키지명 검증
        if not self._validate_package_name(skill_name):
            result.errors.append(f"유효하지 않은 스킬명: '{skill_name}' — 소문자와 하이픈만 허용됩니다.")
            return result

        # 1. 스킬 디렉토리 찾기
        skill_dir = self._find_skill_dir(skill_name)
        if not skill_dir:
            result.errors.append(
                f"스킬 '{skill_name}'을(를) 찾을 수 없습니다. "
                + f"{MARKET_DIR}/{skill_name}/ 또는 {LOCAL_SKILLS_DIR}/{skill_name}/ 경로를 확인하세요."
            )
            return result

        # 2. 검증
        validation = self._validate_for_publish(skill_dir, skill_name)
        result.version = validation.version or version or PUBLISH_TEMPLATE_VERSION
        result.warnings.extend(validation.warnings)
        if not validation.valid:
            result.errors.append(validation.reason)
            return result

        # 3. 임시 디렉토리에 패키지 준비
        tmp_dir = None
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix=f"agk-publish-{skill_name}-"))
            success, err = self._prepare_package(skill_dir, tmp_dir, package_name, result.version, validation)
            if not success:
                result.errors.append(f"패키지 준비 실패: {err}")
                return result

            result.publish_path = str(tmp_dir)

            # 4. npm publish
            if dry_run:
                result.success = True
                result.warnings.append("✅ dry-run 모드 — 실제 publish되지 않았습니다.")
                return result

            npm_ok, npm_err, npm_url = self._npm_publish(tmp_dir, package_name, tag)
            if not npm_ok:
                result.errors.append(f"npm publish 실패: {npm_err}")
                return result

            result.npm_url = npm_url or f"https://www.npmjs.com/package/{package_name}"
            result.success = True
            logger.info("[SkillPublisher] Published %s@%s → npm", package_name, result.version)

        except Exception as e:
            logger.exception("[SkillPublisher] npm publish error: %s", e)
            result.errors.append(str(e))
        finally:
            # 임시 디렉토리 정리 (publish_path 참조용으로 남겨두지 않음)
            if tmp_dir and not dry_run:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

        return result

    def publish_to_github(
        self,
        skill_name: str,
        *,
        repo: str,
        base_branch: str = "main",
        draft: bool = False,
        title: str | None = None,
        body: str | None = None,
        dry_run: bool = False,
    ) -> PublishResult:
        """로컬 스킬을 GitHub PR로 제출합니다.

        Args:
            skill_name: 스킬 이름 (디렉토리명)
            repo: 대상 GitHub 리포지토리 (e.g. "org/skills-repo")
            base_branch: PR 대상 브랜치 (기본: "main")
            draft: Draft PR로 생성
            title: PR 타이틀 (기본: 자동 생성)
            body: PR 설명 (기본: 자동 생성)
            dry_run: 실제 PR 생성 없이 검증만 수행

        Returns:
            PublishResult
        """
        result = PublishResult(action="github_pr", skill_name=skill_name)

        # 1. gh CLI 확인
        if not dry_run:
            gh_ok, gh_err = self._check_gh_cli()
            if not gh_ok:
                result.errors.append(f"GitHub CLI (gh) 필요: {gh_err}")
                return result

        # 2. 스킬 디렉토리 찾기
        skill_dir = self._find_skill_dir(skill_name)
        if not skill_dir:
            result.errors.append(
                f"스킬 '{skill_name}'을(를) 찾을 수 없습니다. "
                + f"{MARKET_DIR}/{skill_name}/ 또는 {LOCAL_SKILLS_DIR}/{skill_name}/ 경로를 확인하세요."
            )
            return result

        # 3. 검증
        validation = self._validate_for_publish(skill_dir, skill_name)
        result.warnings.extend(validation.warnings)
        if not validation.valid:
            result.errors.append(validation.reason)
            return result

        # 4. PR 타이틀/바디 자동 생성
        pr_title = title or f"feat(skills): add `{skill_name}` skill (v{result.version or PUBLISH_TEMPLATE_VERSION})"
        pr_body = body or self._generate_pr_body(skill_name, validation)
        branch_name = f"add-skill-{skill_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if dry_run:
            result.success = True
            result.warnings.append(
                f"✅ dry-run 모드 — 생성될 PR 정보:\n  Title: {pr_title}\n  Branch: {branch_name}\n  Repo: {repo}"
            )
            return result

        # 5. GitHub PR 생성
        try:
            pr_url = self._create_github_pr(repo, branch_name, base_branch, skill_dir, pr_title, pr_body, draft)
            if pr_url:
                result.pr_url = pr_url
                result.success = True
                logger.info("[SkillPublisher] PR created: %s", pr_url)
            else:
                result.errors.append("PR 생성 실패 (URL이 반환되지 않음)")

        except Exception as e:
            logger.exception("[SkillPublisher] GitHub PR error: %s", e)
            result.errors.append(str(e))

        return result

    # ─── 검증 ──────────────────────────────────────────────────────

    def _validate_for_publish(self, skill_dir: Path, skill_name: str) -> PublishValidation:
        """스킬 디렉토리가 publish 가능한 상태인지 검증합니다.

        Checks:
            - SKILL.md 존재
            - SKILL.md에 frontmatter name 필드
            - README.md 존재 (권장)
            - .agk_meta.json 존재 (market 스킬인 경우)

        Args:
            skill_dir: 스킬 디렉토리 경로
            skill_name: 스킬 이름

        Returns:
            PublishValidation
        """
        warnings: list[str] = []
        version = PUBLISH_TEMPLATE_VERSION
        tool_count = 0

        # SKILL.md
        skill_md = skill_dir / "SKILL.md"
        has_skill_md = skill_md.exists()
        if not has_skill_md:
            return PublishValidation(
                valid=False,
                reason=f"SKILL.md not found in {skill_dir}",
                skill_name=skill_name,
            )

        # SKILL.md frontmatter 파싱
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            fm = self._parse_frontmatter(content)
            if fm.get("name"):
                # 이름 일치 확인
                expected = skill_name.replace("-", "_").upper()
                actual = str(fm["name"]).replace("-", "_").upper()
                if expected != actual:
                    warnings.append(
                        f"SKILL.md frontmatter name('{fm['name']}')이 디렉토리명('{skill_name}')과 일치하지 않습니다."
                    )
            if fm.get("version"):
                version = str(fm["version"])
            # allowed-tools / tools 카운트
            tools = fm.get("allowed-tools", fm.get("tools", []))
            if isinstance(tools, list):
                tool_count = len(tools)
            elif isinstance(tools, str):
                tool_count = 1
        except Exception as e:
            warnings.append(f"SKILL.md frontmatter 파싱 실패: {e}")

        # README.md
        readme = skill_dir / "README.md"
        has_readme = readme.exists()
        if not has_readme:
            warnings.append("README.md가 없습니다 — npm 패키지에 포함하는 것을 권장합니다.")

        # .agk_meta.json
        meta = skill_dir / ".agk_meta.json"
        has_agk_meta = meta.exists()

        return PublishValidation(
            valid=True,
            skill_name=skill_name,
            package_name=f"{AGK_SKILL_SCOPE}{skill_name}",
            version=version,
            has_skill_md=has_skill_md,
            has_readme=has_readme,
            has_agk_meta=has_agk_meta,
            tool_count=tool_count,
            warnings=warnings,
        )

    def _validate_package_name(self, name: str) -> bool:
        """유효한 @antigravity-k/skill-* 패키지명인지 확인."""
        return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name))

    # ─── 패키지 준비 ──────────────────────────────────────────────

    def _prepare_package(
        self,
        src: Path,
        dest: Path,
        package_name: str,
        version: str,
        validation: PublishValidation,
    ) -> tuple[bool, str]:
        """npm publish용 패키지 구조를 임시 디렉토리에 생성합니다.

        구조:
            <dest>/
            ├── package.json       # antigravityK 메타데이터 포함
            ├── SKILL.md           # 스킬 메인 문서
            ├── README.md          # (있으면) 패키지 README
            ├── .agk_meta.json     # (있으면) 설치 메타데이터
            └── references/        # (있으면) 참고 문서

        Args:
            src: 소스 스킬 디렉토리
            dest: 대상 임시 디렉토리
            package_name: npm 패키지명
            version: 버전
            validation: 검증 결과

        Returns:
            (성공여부, 오류메시지)
        """
        try:
            # package.json 생성
            pkg_json = self._generate_package_json(src, package_name, version, validation)
            pkg_json_path = dest / "package.json"
            _ = pkg_json_path.write_text(
                json.dumps(pkg_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # SKILL.md 복사
            skill_md_src = src / "SKILL.md"
            if skill_md_src.exists():
                _ = shutil.copy2(skill_md_src, dest / "SKILL.md")

            # README.md (없으면 SKILL.md에서 생성)
            readme_src = src / "README.md"
            if readme_src.exists():
                _ = shutil.copy2(readme_src, dest / "README.md")
            else:
                self._generate_readme(dest, validation)

            # .agk_meta.json (있으면)
            meta_src = src / ".agk_meta.json"
            if meta_src.exists():
                _ = shutil.copy2(meta_src, dest / ".agk_meta.json")

            # references/ (있으면)
            ref_src = src / "references"
            if ref_src.exists() and ref_src.is_dir():
                _ = shutil.copytree(ref_src, dest / "references", dirs_exist_ok=True)

            # tests/ (있으면)
            tests_src = src / "tests"
            if tests_src.exists() and tests_src.is_dir():
                _ = shutil.copytree(tests_src, dest / "tests", dirs_exist_ok=True)

            # .npmignore (보안용)
            npmignore_path = dest / ".npmignore"
            _ = npmignore_path.write_text(
                "node_modules/\n.npmignore\n.agk_meta.json\n",
                encoding="utf-8",
            )

            return True, ""

        except OSError as e:
            return False, str(e)

    def _generate_package_json(
        self,
        src: Path,
        package_name: str,
        version: str,
        validation: PublishValidation,
    ) -> dict[str, JsonValue]:
        """package.json 콘텐츠를 생성합니다.

        기존 package.json이 있으면 병합하고,
        없으면 AGK 스킬 기본 템플릿을 사용합니다.

        Args:
            src: 스킬 디렉토리
            package_name: npm 패키지명
            version: 버전
            validation: 검증 결과

        Returns:
            package.json dict
        """
        existing: dict[str, JsonValue] = {}
        pkg_json_path = src / "package.json"
        if pkg_json_path.exists():
            try:
                loaded = cast(object, json.loads(pkg_json_path.read_text(encoding="utf-8")))
                existing = _as_json_map(loaded)
            except (json.JSONDecodeError, OSError):
                logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

        # 기본 정보
        skill_name = validation.skill_name
        display_name = skill_name.replace("-", " ").title()

        # SKILL.md에서 description 추출
        description_value = existing.get("description", "")
        description = str(description_value)
        if not description:
            try:
                skill_md = src / "SKILL.md"
                if skill_md.exists():
                    content = skill_md.read_text(encoding="utf-8", errors="replace")
                    fm = self._parse_frontmatter(content)
                    description = str(fm.get("description", ""))
            except Exception:
                logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

        # antigravityK 메타데이터
        agk_meta = _as_json_map(existing.get("antigravityK", {}))
        _ = agk_meta.setdefault("skill", True)
        _ = agk_meta.setdefault("displayName", display_name)
        _ = agk_meta.setdefault("minAgentVersion", "0.1.0")
        _ = agk_meta.setdefault("riskLevel", "safe")
        _ = agk_meta.setdefault("trustLevel", "experimental")
        _ = agk_meta.setdefault("requiresApproval", False)

        # allowed-tools → requiredTools
        tools: JsonValue = []
        try:
            skill_md = src / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                fm = self._parse_frontmatter(content)
                tools = fm.get("allowed-tools", fm.get("tools", []))
                if isinstance(tools, str):
                    tools = [tools]
                if isinstance(tools, list):
                    agk_meta["requiredTools"] = tools
        except Exception:
            logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

        package: dict[str, JsonValue] = {
            "name": package_name,
            "version": version,
            "description": description or f"Ssak-Ai skill: {display_name}",
            "keywords": [
                "antigravity-k",
                "skill",
                skill_name,
            ],
            "license": existing.get("license", "MIT"),
            "author": existing.get("author", ""),
            "homepage": existing.get(
                "homepage", f"https://github.com/ssak-comp/antigravity-k/tree/main/{LOCAL_SKILLS_DIR}/{skill_name}"
            ),
            "repository": existing.get(
                "repository",
                {
                    "type": "git",
                    "url": "git+https://github.com/ssak-comp/antigravity-k.git",
                },
            ),
            "antigravityK": agk_meta,
            "private": False,
        }

        # 기존 package.json에서 추가 필드 병합 (충돌 방지)
        for key in ["bugs", "engines", "os", "cpu", "type", "main", "bin", "scripts"]:
            if key in existing:
                package[key] = existing[key]

        return package

    def _generate_readme(self, dest: Path, validation: PublishValidation) -> None:
        """README.md가 없을 경우 자동 생성합니다."""
        skill_name = validation.skill_name
        display_name = skill_name.replace("-", " ").title()

        readme = f"""# {display_name}

{AGK_SKILL_SCOPE}{skill_name}

## Description

Ssak-Ai skill: {display_name}

## Installation

```bash
agk market --install {AGK_SKILL_SCOPE}{skill_name}
```

## Usage

This skill provides {validation.tool_count} tool(s).

## License

MIT
"""
        readme_path = dest / "README.md"
        _ = readme_path.write_text(readme.strip() + "\n", encoding="utf-8")

    # ─── npm publish ─────────────────────────────────────────────

    def _npm_publish(self, pkg_dir: Path, package_name: str, tag: str) -> tuple[bool, str, str]:
        """npm publish를 실행합니다.

        Args:
            pkg_dir: 패키지 디렉토리 (package.json 위치)
            package_name: 패키지명 (로깅용)
            tag: npm dist-tag

        Returns:
            (성공여부, 오류메시지, npm URL)
        """
        try:
            result = subprocess.run(
                ["npm", "publish", str(pkg_dir), "--tag", tag, "--access", "public"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(pkg_dir),
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Already published → warning, not error
                if "cannot publish over the previously published version" in stderr:
                    return False, f"이미 동일 버전이 publish되어 있습니다: {stderr[:200]}", ""
                # Unauthorized
                if "ENEEDAUTH" in stderr or "npm ERR! code ENEEDAUTH" in stderr:
                    return False, "npm 인증 필요 — `npm login`을 먼저 실행하세요.", ""
                return False, stderr[:500], ""

            # 성공 URL 추출
            stdout = result.stdout.strip()
            npm_url = f"https://www.npmjs.com/package/{package_name}"
            for line in stdout.split("\n"):
                if "https://www.npmjs.com/package/" in line:
                    npm_url = line.strip()
                    break

            return True, "", npm_url

        except subprocess.TimeoutExpired:
            return False, "npm publish timed out (120s)", ""
        except FileNotFoundError:
            return False, "npm CLI not found. Install Node.js/npm first.", ""
        except Exception as e:
            return False, str(e), ""

    # ─── GitHub PR ────────────────────────────────────────────────

    def _check_gh_cli(self) -> tuple[bool, str]:
        """GitHub CLI (gh)가 설치되어 있고 인증되었는지 확인합니다.

        Returns:
            (성공여부, 오류메시지)
        """
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, "gh CLI not found. Install with: brew install gh"

            # 인증 확인
            auth_result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if auth_result.returncode != 0:
                return False, "gh not authenticated. Run: gh auth login"

            return True, ""

        except FileNotFoundError:
            return False, "gh CLI not found. Install with: brew install gh"
        except Exception as e:
            return False, str(e)

    def _create_github_pr(
        self,
        repo: str,
        branch_name: str,
        base_branch: str,
        skill_dir: Path,
        title: str,
        body: str,
        draft: bool,
    ) -> str | None:
        """GitHub PR을 생성합니다.

        플로우:
            1. 대상 리포지토리 clone (임시 디렉토리)
            2. 새 브랜치 생성
            3. skills/<name>/ 디렉토리에 파일 복사
            4. git add + commit + push
            5. gh pr create

        Args:
            repo: GitHub 리포지토리 (e.g. "org/skills-repo")
            branch_name: 새 브랜치명
            base_branch: PR 대상 브랜치
            skill_dir: 스킬 디렉토리 경로
            title: PR 타이틀
            body: PR 설명
            draft: Draft PR 여부

        Returns:
            PR URL (실패 시 None)
        """
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix=f"agk-pr-{branch_name}-")
            clone_dir = Path(tmp_dir) / "repo"

            # 1. Clone
            logger.info("[SkillPublisher] Cloning %s...", repo)
            clone_result = subprocess.run(
                ["gh", "repo", "clone", repo, str(clone_dir), "--", "--depth=1"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if clone_result.returncode != 0:
                logger.error("[SkillPublisher] Clone failed: %s", clone_result.stderr)
                return None

            # 2. 새 브랜치 생성 및 checkout
            _ = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )

            # 3. 스킬 디렉토리 생성 및 파일 복사
            skill_dest = clone_dir / "skills" / skill_dir.name
            skill_dest.mkdir(parents=True, exist_ok=True)

            for item in skill_dir.iterdir():
                if item.name.startswith(".") and item.name not in (".agk_meta.json",):
                    continue  # 숨김 파일 제외 (단, .agk_meta.json은 포함)
                if item.is_dir():
                    _ = shutil.copytree(item, skill_dest / item.name, dirs_exist_ok=True)
                else:
                    _ = shutil.copy2(item, skill_dest / item.name)

            # 4. git add + commit + push
            _ = subprocess.run(
                ["git", "add", "-A"],
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )

            commit_result = subprocess.run(
                ["git", "commit", "-m", title],
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if commit_result.returncode != 0:
                if "nothing to commit" in commit_result.stderr or "nothing to commit" in commit_result.stdout:
                    logger.warning("[SkillPublisher] Nothing to commit — skill files may already exist")
                    return None
                logger.error("[SkillPublisher] Commit failed: %s", commit_result.stderr)
                return None

            push_result = subprocess.run(
                ["git", "push", "origin", branch_name, "--force"],
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if push_result.returncode != 0:
                logger.error("[SkillPublisher] Push failed: %s", push_result.stderr)
                return None

            # 5. PR 생성
            pr_args = [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--body",
                body,
                "--base",
                base_branch,
                "--head",
                branch_name,
            ]
            if draft:
                pr_args.append("--draft")

            pr_result = subprocess.run(
                pr_args,
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pr_result.returncode != 0:
                logger.error("[SkillPublisher] PR creation failed: %s", pr_result.stderr)
                return None

            pr_url = pr_result.stdout.strip()
            return pr_url if pr_url else None

        except subprocess.TimeoutExpired:
            logger.error("[SkillPublisher] GitHub operation timed out")
            return None
        except Exception as e:
            logger.exception("[SkillPublisher] GitHub PR error: %s", e)
            return None
        finally:
            if tmp_dir:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

    # ─── 유틸리티 ─────────────────────────────────────────────────

    def _find_skill_dir(self, skill_name: str) -> Path | None:
        """스킬 디렉토리를 검색합니다.

        우선순위: market/<name>/ > .agent/skills/<name>/
        """
        # 1차: market 디렉토리
        market_path = self.market_dir / skill_name
        if market_path.exists() and market_path.is_dir():
            return market_path

        # 2차: 일반 skills 디렉토리
        skills_path = self.skills_dir / skill_name
        if skills_path.exists() and skills_path.is_dir():
            return skills_path

        return None

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, JsonValue]:
        """YAML frontmatter를 파싱합니다.

        Args:
            content: SKILL.md 전체 내용

        Returns:
            frontmatter dict (파싱 실패 시 빈 dict)
        """
        frontmatter: dict[str, JsonValue] = {}
        if not content.startswith("---"):
            return frontmatter

        try:
            import yaml

            parts = content.split("---", 2)
            if len(parts) >= 2:
                fm_content = parts[1].strip()
                if fm_content:
                    parsed = cast(object, yaml.safe_load(fm_content))
                    frontmatter = _as_json_map(parsed)
        except ImportError:
            # yaml 미설치 — 간단한 줄 기반 파싱
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("---"):
                    continue
                if ":" in line:
                    key, _, value = line.partition(":")
                    frontmatter[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            logger.warning("[SkillPublisher] 스킬 발행 단계 실패 (non-critical)", exc_info=True)

        return frontmatter

    @staticmethod
    def _generate_pr_body(skill_name: str, validation: PublishValidation) -> str:
        """PR 설명을 자동 생성합니다."""
        return (
            f"## 스킬 제안: `{skill_name}`\n\n"
            f"### 설명\n"
            f"`{AGK_SKILL_SCOPE}{skill_name}` 스킬을 추가합니다.\n\n"
            f"### 포함 파일\n"
            f"- SKILL.md: {'✅' if validation.has_skill_md else '❌'}\n"
            f"- README.md: {'✅' if validation.has_readme else '⚠️ 자동 생성'}\n"
            f"- package.json (antigravityK 메타데이터 포함)\n\n"
            f"### 도구 수\n"
            f"{validation.tool_count}개 도구\n\n"
            f"### 체크리스트\n"
            f"- [ ] npm publish 확인\n"
            f"- [ ] SKILL.md frontmatter 검증\n"
            f"- [ ] 라이선스 확인\n"
            f"- [ ] README 업데이트\n"
        )
