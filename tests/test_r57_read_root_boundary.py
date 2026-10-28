"""호출자가 확인한 읽기 루트 자체의 링크 교체를 실제 파일 핸들로 검사한다.

프로젝트 등록부나 권한 결정을 대신 검증하지 않는다. 호출자가 정규화한 루트 경로를
전달한 뒤 그 폴더가 외부 합성 폴더 링크로 바뀌는 보조 함수 경계를 분리한다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import pytest

from antigravity_k.tools.verified_read import VerifiedReadError, open_verified, read_text_under

ReadOperation = Literal["handle", "text"]
RELATIVE_FILE = Path("nested") / "ordinary-note.txt"
INSIDE_CONTENT = "R57-CHECKED-ROOT-CONTENT-1428"
OUTSIDE_CONTENT = "R57-OUTSIDE-ROOT-CONTENT-9073"


@pytest.fixture
def read_roots(tmp_path: Path) -> tuple[Path, Path]:
    checked = tmp_path / "checked-project"
    outside = tmp_path / "synthetic-outside"
    for root, content in ((checked, INSIDE_CONTENT), (outside, OUTSIDE_CONTENT)):
        target = root / RELATIVE_FILE
        target.parent.mkdir(parents=True)
        target.write_text(content, encoding="utf-8")
    return checked.resolve(strict=True), outside.resolve(strict=True)


def _read(operation: ReadOperation, path: Path, root: Path) -> str:
    if operation == "text":
        return read_text_under(str(path), str(root))
    descriptor, _identity = open_verified(str(path), str(root))
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.mark.parametrize("operation", ["handle", "text"])
def test_canonical_project_root_keeps_nested_read_working(
    read_roots: tuple[Path, Path], operation: ReadOperation
) -> None:
    root, outside = read_roots
    assert not root.is_symlink()
    assert root == root.resolve(strict=True)
    assert not outside.is_relative_to(root)

    assert _read(operation, root / RELATIVE_FILE, root) == INSIDE_CONTENT
    assert (outside / RELATIVE_FILE).read_text(encoding="utf-8") == OUTSIDE_CONTENT


@pytest.mark.parametrize("operation", ["handle", "text"])
def test_root_replaced_after_canonical_check_is_refused(
    read_roots: tuple[Path, Path], operation: ReadOperation
) -> None:
    root, outside = read_roots
    canonical_root = root.resolve(strict=True)
    target = canonical_root / RELATIVE_FILE
    assert canonical_root.is_dir() and not canonical_root.is_symlink()
    assert target.read_text(encoding="utf-8") == INSIDE_CONTENT

    moved = root.with_name("original-checked-project")
    root.rename(moved)
    root.symlink_to(outside, target_is_directory=True)
    assert root.is_symlink()
    assert (moved / RELATIVE_FILE).read_text(encoding="utf-8") == INSIDE_CONTENT

    with pytest.raises(VerifiedReadError):
        observed = _read(operation, target, canonical_root)
        pytest.fail(f"교체된 루트의 읽기가 허용됐습니다: {observed!r}")
