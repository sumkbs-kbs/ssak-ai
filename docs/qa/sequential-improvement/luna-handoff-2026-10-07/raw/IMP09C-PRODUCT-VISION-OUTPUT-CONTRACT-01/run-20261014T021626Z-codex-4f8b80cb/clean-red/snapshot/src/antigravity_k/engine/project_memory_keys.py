from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_CANONICAL_KEY_BY_ALIAS: Final[dict[str, str]] = {
    "db": "database",
    "db_engine": "database",
    "dbms": "database",
    "database_engine": "database",
    "frontend_framework": "frontend",
    "ui_framework": "frontend",
    "backend_framework": "backend",
    "server_framework": "backend",
    "package_mgr": "package_manager",
    "pkg_manager": "package_manager",
    "testing_framework": "test_framework",
    "test_runner": "test_framework",
    "deployment_target": "deployment",
    "deploy_target": "deployment",
}
_BUILTIN_CANONICAL_KEYS: Final[frozenset[str]] = frozenset(
    {*_CANONICAL_KEY_BY_ALIAS, *_CANONICAL_KEY_BY_ALIAS.values()},
)
_PROJECT_REFERENCE = re.compile(r"프로젝트|\b(?:project|workspace|repo(?:sitory)?)\b", re.IGNORECASE)
_RECALL_INTENT = re.compile(
    r"뭐|무엇|어떤|알려|답해|기억|결정|이름|\?|\b(?:what|which|tell|remember|decid|name)\w*\b",
    re.IGNORECASE,
)
_ACTION_INTENT = re.compile(
    r"바꿔|변경|수정|전환|교체|마이그레이션|적용|구현|설치|추가|삭제|실행|검색|조사|"
    + r"생성|작성|만들|고쳐|업데이트|"
    + r"설정(?:해|하|으로|을)|구성(?:해|하)|"
    + r"\b(?:change|update|modify|apply|implement|install|add|remove|delete|run|search|research|"
    + r"configure|edit|switch|replace|migrate|create|write|fix)\w*\b",
    re.IGNORECASE,
)
_DECLARATION = re.compile(r"(?:프로젝트\s*(?:결정|사실)|project\s+(?:decision|fact))\s*:|=")
_QUERY_KEY_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "database": re.compile(r"데이터\s*베이스|\b(?:db|dbms|database(?:_engine)?|db_engine)\b", re.IGNORECASE),
    "frontend": re.compile(r"프론트\s*엔드|\b(?:frontend|frontend_framework|ui_framework)\b", re.IGNORECASE),
    "backend": re.compile(r"백\s*엔드|\b(?:backend|backend_framework|server_framework)\b", re.IGNORECASE),
    "package_manager": re.compile(
        r"패키지\s*매니저|\b(?:package_manager|package_mgr|pkg_manager)\b",
        re.IGNORECASE,
    ),
    "test_framework": re.compile(
        r"테스트\s*(?:프레임워크|러너)|\b(?:test_framework|testing_framework|test_runner)\b",
        re.IGNORECASE,
    ),
    "deployment": re.compile(
        r"배포\s*(?:대상|환경)?|\b(?:deployment|deployment_target|deploy_target)\b",
        re.IGNORECASE,
    ),
}
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EXPLICIT_KEY_PATTERN = re.compile(
    r"(?P<prefix>(?:프로젝트\s*(?:결정|사실)|project\s+(?:decision|fact))\s*:\s*)"
    + r"(?P<key>[a-z][a-z0-9_]{0,63})(?P<suffix>\s*=)",
    re.IGNORECASE,
)
_PROJECT_MARKER_KEY_PATTERN = re.compile(
    r"(?P<prefix>\[project:(?:decision|fact):)(?P<key>[a-z][a-z0-9_]{0,63})(?P<suffix>])",
    re.IGNORECASE,
)


class ProjectAliasSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    aliases: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, groups: dict[str, list[str]]) -> dict[str, list[str]]:
        if len(groups) > 64:
            raise ValueError("too many project alias groups")
        canonicals = set(groups)
        assigned: dict[str, str] = {}
        normalized: dict[str, list[str]] = {}
        for canonical, aliases in groups.items():
            if _KEY_PATTERN.fullmatch(canonical) is None or canonical_project_key(canonical) != canonical:
                raise ValueError(f"invalid canonical project alias key: {canonical}")
            if not aliases:
                raise ValueError(f"empty project alias group: {canonical}")
            unique: list[str] = []
            for alias in aliases:
                if _KEY_PATTERN.fullmatch(alias) is None or alias == canonical:
                    raise ValueError(f"invalid project alias: {alias}")
                builtin = _CANONICAL_KEY_BY_ALIAS.get(alias)
                if builtin is not None and builtin != canonical:
                    raise ValueError(f"project alias redefines built-in key: {alias}")
                if alias in _BUILTIN_CANONICAL_KEYS and alias != canonical:
                    raise ValueError(f"project alias redefines built-in key: {alias}")
                owner = assigned.get(alias)
                if owner is not None and owner != canonical:
                    raise ValueError(f"ambiguous project alias: {alias}")
                assigned[alias] = canonical
                if alias not in unique:
                    unique.append(alias)
            normalized[canonical] = unique
        if canonicals.intersection(assigned):
            raise ValueError("project alias chains are not allowed")
        if len(assigned) > 256:
            raise ValueError("too many project aliases")
        return normalized


class ProjectAliasConfigError(ValueError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"invalid project alias schema: {path}")


class ProjectAliasNotFoundError(ValueError):
    def __init__(self, alias: str) -> None:
        super().__init__(f"project alias not found: {alias}")


@dataclass(frozen=True, slots=True)
class ProjectKeyAliases:
    entries: tuple[tuple[str, str], ...] = ()

    def canonical_key(self, key: str) -> str:
        normalized = canonical_project_key(key)
        return dict(self.entries).get(normalized, normalized)

    def canonical_record_key(self, record_key: str) -> str:
        kind, separator, key = record_key.partition(":")
        if not separator or kind not in {"decision", "fact"}:
            return record_key
        return f"{kind}:{self.canonical_key(key)}"

    def canonicalize_text(self, text: str) -> str:
        def replace_explicit(match: re.Match[str]) -> str:
            return f"{match.group('prefix')}{self.canonical_key(match.group('key'))}{match.group('suffix')}"

        def replace_marker(match: re.Match[str]) -> str:
            return f"{match.group('prefix')}{self.canonical_key(match.group('key'))}{match.group('suffix')}"

        return _PROJECT_MARKER_KEY_PATTERN.sub(replace_marker, _EXPLICIT_KEY_PATTERN.sub(replace_explicit, text))

    def query_keys(self, query: str) -> tuple[str, ...]:
        matches: set[str] = set()
        by_canonical: dict[str, list[str]] = {}
        for alias, canonical in self.entries:
            by_canonical.setdefault(canonical, []).append(alias)
        for canonical, aliases in by_canonical.items():
            terms = (canonical, *aliases)
            if any(re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", query, re.I) for term in terms):
                matches.add(canonical)
        return tuple(sorted(matches))


def load_project_key_aliases(memory_dir: Path) -> ProjectKeyAliases:
    path = memory_dir / "project_aliases.json"
    if not path.exists():
        return ProjectKeyAliases()
    if not path.resolve().is_relative_to(memory_dir.resolve()):
        raise ProjectAliasConfigError(path)
    try:
        schema = ProjectAliasSchema.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        raise ProjectAliasConfigError(path) from None
    entries = tuple(sorted((alias, canonical) for canonical, aliases in schema.aliases.items() for alias in aliases))
    return ProjectKeyAliases(entries=entries)


def read_project_alias_schema(memory_dir: Path) -> ProjectAliasSchema:
    path = memory_dir / "project_aliases.json"
    if not path.exists():
        return ProjectAliasSchema()
    if not path.resolve().is_relative_to(memory_dir.resolve()):
        raise ProjectAliasConfigError(path)
    try:
        return ProjectAliasSchema.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        raise ProjectAliasConfigError(path) from None


def write_project_alias_schema(memory_dir: Path, schema: ProjectAliasSchema) -> Path:
    path = memory_dir / "project_aliases.json"
    temporary = memory_dir / ".project_aliases.json.tmp"
    try:
        _ = temporary.write_text(
            json.dumps(schema.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _ = temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise ProjectAliasConfigError(path) from None
    return path


def set_project_alias(memory_dir: Path, canonical: str, alias: str) -> ProjectAliasSchema:
    current = read_project_alias_schema(memory_dir)
    groups = {key: list(values) for key, values in current.aliases.items()}
    group = groups.setdefault(canonical, [])
    if alias not in group:
        group.append(alias)
    updated = ProjectAliasSchema.model_validate({"aliases": groups})
    _ = write_project_alias_schema(memory_dir, updated)
    return updated


def remove_project_alias(memory_dir: Path, alias: str) -> ProjectAliasSchema:
    current = read_project_alias_schema(memory_dir)
    if not any(alias in values for values in current.aliases.values()):
        raise ProjectAliasNotFoundError(alias)
    groups = {canonical: [value for value in values if value != alias] for canonical, values in current.aliases.items()}
    updated = ProjectAliasSchema.model_validate(
        {"aliases": {canonical: values for canonical, values in groups.items() if values}},
    )
    _ = write_project_alias_schema(memory_dir, updated)
    return updated


def canonical_project_key(key: str) -> str:
    normalized = key.strip().lower()
    return _CANONICAL_KEY_BY_ALIAS.get(normalized, normalized)


def canonical_project_record_key(record_key: str) -> str:
    kind, separator, key = record_key.partition(":")
    if not separator or kind not in {"decision", "fact"}:
        return record_key
    return f"{kind}:{canonical_project_key(key)}"


def project_read_query_target(
    query: str,
    aliases: ProjectKeyAliases | None = None,
) -> tuple[str | None, str] | None:
    if len(query) > 240 or _PROJECT_REFERENCE.search(query) is None:
        return None
    if _RECALL_INTENT.search(query) is None or _ACTION_INTENT.search(query) is not None:
        return None
    if _DECLARATION.search(query) is not None:
        return None
    keys = {key for key, pattern in _QUERY_KEY_PATTERNS.items() if pattern.search(query) is not None}
    if aliases is not None:
        keys.update(aliases.query_keys(query))
    if len(keys) != 1:
        return None
    kind = "decision" if re.search(r"결정|decid", query, re.IGNORECASE) else None
    if re.search(r"사실|\bfact\b", query, re.IGNORECASE):
        kind = "fact"
    return kind, next(iter(keys))
