from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import BaseModel, ConfigDict, Field


class UpstreamProvenance(BaseModel):
    repository: str
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    license_spdx: str
    copied_files: tuple[str, ...]
    integration: str


class EntrypointInventory(BaseModel):
    name: str
    kind: str
    command: tuple[str, ...] = Field(min_length=1)
    source_path: str


class DistributionInventory(BaseModel):
    source_roots: tuple[str, ...] = Field(min_length=1)
    manifest_roots: tuple[str, ...] = Field(min_length=1)
    prohibited_spdx: tuple[str, ...] = Field(min_length=1)
    prohibited_python_packages: tuple[str, ...] = Field(min_length=1)
    #: REL-03 — 플랫폼 마커 패키지 (win32 전용 등)로 현재 플랫폼에 설치되지
    #: 않아 license 메타데이터 판독이 불가한 lock 패키지. license gate는 이
    #: 목록에 있으면 unknown 대신 marker-allowed로 판정한다 (보고에는 남긴다).
    marker_platform_packages: tuple[str, ...] = ()


class ReleaseBaseline(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    schema_version: int
    pinned_at: str
    upstreams: tuple[UpstreamProvenance, ...] = Field(min_length=1)
    entrypoints: tuple[EntrypointInventory, ...] = Field(min_length=1)
    distribution: DistributionInventory


class ReleaseBaselineError(ValueError):
    """A release-baseline file or distribution violates release policy."""


_REQUIRED_FILES: Final[tuple[str, ...]] = (
    "THIRD_PARTY_PROVENANCE.toml",
    "NOTICE",
    "docs/RELEASE_POLICY.md",
    "docs/adr/0001-single-task-runtime-and-event-store.md",
    "data/benchmarks/held_out_v1.jsonl",
    "data/benchmarks/held_out_v1.freeze.json",
    "data/benchmarks/held_out_v2.jsonl",
    "data/benchmarks/held_out_v2.freeze.json",
)

_HELD_OUT_DATASETS: Final[tuple[str, ...]] = ("held_out_v1.jsonl", "held_out_v2.jsonl")
_JsonObject = dict[str, object]


def load_release_baseline(project_root: Path) -> ReleaseBaseline:
    path = project_root / "THIRD_PARTY_PROVENANCE.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        message = f"Could not read release baseline at {path}: {error}"
        raise ReleaseBaselineError(message) from error
    try:
        return ReleaseBaseline.model_validate(raw)
    except ValueError as error:
        message = f"Invalid release baseline at {path}: {error}"
        raise ReleaseBaselineError(message) from error


def validate_release_baseline(baseline: ReleaseBaseline, project_root: Path) -> None:
    if baseline.schema_version != 1:
        raise ReleaseBaselineError(f"Unsupported release baseline schema: {baseline.schema_version}")

    for relative_path in _REQUIRED_FILES:
        path = project_root / relative_path
        if not path.is_file():
            raise ReleaseBaselineError(f"Required release artifact is missing: {relative_path}")

    _validate_entrypoints(baseline, project_root)

    for root_name in (*baseline.distribution.manifest_roots, *baseline.distribution.source_roots):
        root = project_root / root_name
        if not root.is_dir():
            raise ReleaseBaselineError(f"Distribution root is missing: {root_name}")

    _validate_no_prohibited_source_text(baseline, project_root)
    _validate_python_lock(baseline, project_root)
    _validate_held_out_manifests(project_root)


def _extract_cli_command_paths(source_text: str, root_cmd: str = "agk") -> set[tuple[str, ...]]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return set()

    paths: set[tuple[str, ...]] = {(root_cmd,)}
    typer_groups: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "add_typer":
                if call.args and isinstance(call.args[0], ast.Name):
                    sub_var = call.args[0].id
                    group_name = None
                    for kw in call.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            group_name = str(kw.value.value)
                    if group_name is None and len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
                        group_name = str(call.args[1].value)
                    if group_name:
                        typer_groups[sub_var] = group_name

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "command":
                    app_var = dec.func.value.id if isinstance(dec.func.value, ast.Name) else None
                    cmd_name = None
                    for kw in dec.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            cmd_name = str(kw.value.value)
                    if cmd_name is None and dec.args and isinstance(dec.args[0], ast.Constant):
                        cmd_name = str(dec.args[0].value)
                    if cmd_name is None:
                        cmd_name = node.name.replace("_", "-")

                    if app_var == "app":
                        paths.add((root_cmd, cmd_name))
                    elif app_var in typer_groups:
                        paths.add((root_cmd, typer_groups[app_var], cmd_name))

    return paths


def _extract_http_routes(source_text: str) -> set[tuple[str, str]]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return set()

    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    method = dec.func.attr.upper()
                    if method in ("GET", "POST", "PUT", "DELETE", "PATCH", "WEBSOCKET"):
                        route_path = None
                        for kw in dec.keywords:
                            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                                route_path = str(kw.value.value)
                        if route_path is None and dec.args and isinstance(dec.args[0], ast.Constant):
                            route_path = str(dec.args[0].value)
                        if route_path is not None:
                            routes.add((method, route_path))
                    elif dec.func.attr == "api_route":
                        route_path = None
                        for kw in dec.keywords:
                            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                                route_path = str(kw.value.value)
                        if route_path is None and dec.args and isinstance(dec.args[0], ast.Constant):
                            route_path = str(dec.args[0].value)
                        if route_path is not None:
                            for kw in dec.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                                    for elt in kw.value.elts:
                                        if isinstance(elt, ast.Constant):
                                            routes.add((str(elt.value).upper(), route_path))
    return routes


def _validate_entrypoints(baseline: ReleaseBaseline, project_root: Path) -> None:
    pyproject_path = project_root / "pyproject.toml"
    pyproject_scripts: dict[str, str] = {}
    if pyproject_path.is_file():
        try:
            pyproject_data = cast(_JsonObject, tomllib.loads(pyproject_path.read_text(encoding="utf-8")))
            project_section = pyproject_data.get("project")
            if isinstance(project_section, dict):
                scripts_candidate = cast(_JsonObject, project_section).get("scripts")
                if isinstance(scripts_candidate, dict):
                    scripts_dict = cast(dict[str, object], scripts_candidate)
                    pyproject_scripts = {k: str(v) for k, v in scripts_dict.items()}
        except (OSError, tomllib.TOMLDecodeError):
            pass

    for entrypoint in baseline.entrypoints:
        path = project_root / entrypoint.source_path
        if not path.is_file():
            raise ReleaseBaselineError(f"Entrypoint source is missing: {entrypoint.source_path}")

        if entrypoint.kind == "cli":
            root_cmd = entrypoint.command[0]
            if pyproject_scripts and root_cmd not in pyproject_scripts:
                raise ReleaseBaselineError(
                    f"CLI entrypoint '{entrypoint.name}' command root '{root_cmd}' is not declared in pyproject.toml [project.scripts]"
                )
            source_text = path.read_text(encoding="utf-8")
            cli_paths = _extract_cli_command_paths(source_text, root_cmd=root_cmd)
            if entrypoint.command not in cli_paths:
                raise ReleaseBaselineError(
                    f"CLI entrypoint '{entrypoint.name}' command {list(entrypoint.command)} is not implemented in {entrypoint.source_path}"
                )

        elif entrypoint.kind == "server":
            source_text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source_text)
            except SyntaxError as error:
                raise ReleaseBaselineError(f"Server entrypoint source syntax error: {error}") from error
            has_asgi_app = any(
                isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
                for n in tree.body
            )
            if not has_asgi_app:
                raise ReleaseBaselineError(
                    f"Server entrypoint '{entrypoint.name}' does not define an ASGI app in {entrypoint.source_path}"
                )
            if len(entrypoint.command) >= 2 and entrypoint.command[0] in pyproject_scripts:
                cli_path = project_root / "src" / "antigravity_k" / "cli.py"
                if cli_path.is_file():
                    cli_paths = _extract_cli_command_paths(
                        cli_path.read_text(encoding="utf-8"), root_cmd=entrypoint.command[0]
                    )
                    if entrypoint.command not in cli_paths:
                        raise ReleaseBaselineError(
                            f"Server entrypoint '{entrypoint.name}' command {list(entrypoint.command)} is not implemented in CLI"
                        )

        elif entrypoint.kind == "http-api":
            if len(entrypoint.command) != 2:
                raise ReleaseBaselineError(
                    f"HTTP API entrypoint '{entrypoint.name}' must specify [METHOD, PATH] in command, got {list(entrypoint.command)}"
                )
            method, route_path = entrypoint.command[0].upper(), entrypoint.command[1]
            routes = _extract_http_routes(path.read_text(encoding="utf-8"))
            if (method, route_path) not in routes:
                raise ReleaseBaselineError(
                    f"HTTP API entrypoint '{entrypoint.name}' route {method} {route_path} is not implemented in {entrypoint.source_path}"
                )

        elif entrypoint.kind == "web-ui":
            try:
                pkg_data = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise ReleaseBaselineError(
                    f"Web UI entrypoint package manifest is invalid: {entrypoint.source_path}"
                ) from error
            scripts = cast(dict[str, str], pkg_data.get("scripts", {}))
            script_name = entrypoint.command[-1]
            if script_name not in scripts:
                raise ReleaseBaselineError(
                    f"Web UI entrypoint '{entrypoint.name}' script '{script_name}' is missing from {entrypoint.source_path}"
                )

        else:
            raise ReleaseBaselineError(f"Unsupported entrypoint kind '{entrypoint.kind}' for {entrypoint.name}")


def _build_prohibited_license_matchers(
    prohibited_spdx: tuple[str, ...],
) -> tuple[list[tuple[str, re.Pattern[bytes]]], re.Pattern[bytes]]:
    matchers: list[tuple[str, re.Pattern[bytes]]] = []
    combined_parts: list[bytes] = []

    has_agpl = any(spdx.upper().startswith("AGPL") for spdx in prohibited_spdx)
    has_gpl = any(spdx.upper().startswith("GPL") for spdx in prohibited_spdx)

    for spdx in prohibited_spdx:
        p1 = rf"\b{re.escape(spdx)}\b".encode("ascii")
        matchers.append((spdx, re.compile(p1, flags=re.IGNORECASE)))
        combined_parts.append(p1)

        p2 = rf"SPDX-License-Identifier:\s*{re.escape(spdx)}".encode("ascii")
        matchers.append((spdx, re.compile(p2, flags=re.IGNORECASE)))
        combined_parts.append(p2)

    if has_agpl:
        p_agpl_readable = rb"GNU[\s\.]+AFFERO[\s\.]+GENERAL[\s\.]+PUBLIC[\s\.]+LICENSE"
        matchers.append(("AGPL", re.compile(p_agpl_readable, flags=re.IGNORECASE)))
        combined_parts.append(p_agpl_readable)

        p_agpl_header = rb"SPDX-License-Identifier:\s*AGPL"
        matchers.append(("AGPL", re.compile(p_agpl_header, flags=re.IGNORECASE)))
        combined_parts.append(p_agpl_header)

    if has_gpl:
        p_gpl_readable = rb"GNU[\s\.]+GENERAL[\s\.]+PUBLIC[\s\.]+LICENSE"
        matchers.append(("GPL", re.compile(p_gpl_readable, flags=re.IGNORECASE)))
        combined_parts.append(p_gpl_readable)

        p_gpl_header = rb"SPDX-License-Identifier:\s*GPL"
        matchers.append(("GPL", re.compile(p_gpl_header, flags=re.IGNORECASE)))
        combined_parts.append(p_gpl_header)

    combined = re.compile(rb"(?:" + rb"|".join(combined_parts) + rb")", flags=re.IGNORECASE)
    return matchers, combined


def _validate_no_prohibited_source_text(baseline: ReleaseBaseline, project_root: Path) -> None:
    matchers, combined_pattern = _build_prohibited_license_matchers(baseline.distribution.prohibited_spdx)
    validator_path = Path(__file__).resolve()

    for root_name in baseline.distribution.source_roots:
        root = project_root / root_name
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if path.resolve() == validator_path or path.name == "release_baseline.py":
                continue
            content = path.read_bytes()
            if combined_pattern.search(content):
                for spdx, pattern in matchers:
                    if pattern.search(content):
                        relative = path.relative_to(project_root).as_posix()
                        message = f"Prohibited license marker {spdx} found in {relative}"
                        raise ReleaseBaselineError(message)


def _validate_python_lock(baseline: ReleaseBaseline, project_root: Path) -> None:
    lock_path = project_root / "uv.lock"
    if not lock_path.is_file():
        raise ReleaseBaselineError("Python lockfile is missing: uv.lock")
    lock_text = lock_path.read_text(encoding="utf-8").lower()
    for package_name in baseline.distribution.prohibited_python_packages:
        if f'name = "{package_name}"' in lock_text:
            message = f"Prohibited Python package is locked: {package_name}"
            raise ReleaseBaselineError(message)


def _validate_held_out_manifests(project_root: Path) -> None:
    benchmark_root = project_root / "data" / "benchmarks"
    for dataset_name in _HELD_OUT_DATASETS:
        dataset_path = benchmark_root / dataset_name
        freeze_path = dataset_path.with_suffix(".freeze.json")
        try:
            manifest_value = cast(object, json.loads(freeze_path.read_text(encoding="utf-8")))
            lines = tuple(line for line in dataset_path.read_text(encoding="utf-8").splitlines() if line)
            row_values = tuple(cast(object, json.loads(line)) for line in lines)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ReleaseBaselineError(f"Held-out evaluation asset is invalid: {dataset_name}") from error

        if not isinstance(manifest_value, dict) or any(not isinstance(row_value, dict) for row_value in row_values):
            raise ReleaseBaselineError(f"Held-out evaluation asset is invalid: {dataset_name}")
        manifest = cast(_JsonObject, manifest_value)
        rows = tuple(cast(_JsonObject, row_value) for row_value in row_values)
        if Path(str(manifest.get("dataset_path", ""))).name != dataset_name:
            raise ReleaseBaselineError(f"Held-out freeze manifest names a different dataset: {dataset_name}")
        digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        if manifest.get("sha256") != digest:
            raise ReleaseBaselineError(f"Held-out dataset digest mismatch: {dataset_name}")
        if manifest.get("row_count") != len(rows):
            raise ReleaseBaselineError(f"Held-out dataset row count mismatch: {dataset_name}")

        case_ids = tuple(row.get("id") for row in rows)
        if any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
            raise ReleaseBaselineError(f"Held-out dataset contains an invalid case ID: {dataset_name}")
        if len(set(case_ids)) != len(case_ids):
            raise ReleaseBaselineError(f"Held-out dataset contains duplicate case IDs: {dataset_name}")
        if any(row.get("forbidden_for_training") is not True for row in rows):
            raise ReleaseBaselineError(f"Held-out dataset permits training: {dataset_name}")
        manifest_case_ids_value = manifest.get("case_ids")
        if not isinstance(manifest_case_ids_value, list):
            raise ReleaseBaselineError(f"Held-out freeze case IDs mismatch: {dataset_name}")
        manifest_case_ids_items = cast(list[object], manifest_case_ids_value)
        if any(not isinstance(case_id, str) for case_id in manifest_case_ids_items):
            raise ReleaseBaselineError(f"Held-out freeze case IDs mismatch: {dataset_name}")
        manifest_case_ids = tuple(case_id for case_id in manifest_case_ids_items if isinstance(case_id, str))
        if manifest_case_ids != case_ids:
            raise ReleaseBaselineError(f"Held-out freeze case IDs mismatch: {dataset_name}")


validate_entrypoints = _validate_entrypoints
validate_no_prohibited_source_text = _validate_no_prohibited_source_text
validate_held_out_manifests = _validate_held_out_manifests
