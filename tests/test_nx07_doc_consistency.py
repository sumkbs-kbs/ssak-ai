"""NX-07 — 문서·지원 범위가 **하나의 현재 상태**를 가리키도록 계약으로 고정한다.

왜 계약인가
===========
NX-07 의 수용 기준은 문장이 아니라 **관계**다:

  * '남은 것은 사람뿐'과 실제 기술 TODO 가 **동시에** 현재 상태로 읽히지 않는다.
  * 지원표에 Supported / Experimental / Unsupported / **Not evaluated** 와 근거가 있다.
  * 새 고객이 README 의 설치·접속 안내를 그대로 따라가고 **맞는 화면**을 본다.
  * `23/23` 은 어느 후보·지문·**범위**인지와 함께 표기된다.
  * 현재 상태 배너는 한 문서가 소유하고(중복 누적 금지), 나머지는 그 문서를 가리킨다.

문자열을 복사해 두면 다음 사람이 한쪽만 고쳐 검사가 갈라진다(F-18·F-24·F-27·F-28 과 같은 병).
그래서 여기서는 **값을 만드는 곳에서 값을 읽어** 비교한다: 포트는 `config.py` 의
`ServerConfig.port` 와 `dashboard/vite.config.ts` 에서, 열린 카드는 `docs/19` 의 상태 표에서.
README 에는 값이 없으므로(그것이 F-22 의 요구다) README 에 대해 검사하는 것은
"값이 있는가"가 아니라 "값이 가리키는 것과 일치하는가"다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CURRENT_STATUS = "docs/20_CURRENT_STATUS.md"
README = "README.md"
SUPPORT_MATRIX = "docs/ga/GA_SUPPORT_MATRIX.md"
LEDGER = "docs/ga/CR14_EX_EXECUTION_LEDGER.md"
CHECKLIST = "docs/19_RELIABILITY_AND_CONNECTOME_CHECKLIST.md"
CONFIG = "src/antigravity_k/config.py"
VITE_CONFIG = "dashboard/vite.config.ts"

# 현재 상태 배너를 들고 있었지만 그 값의 소유자가 아닌 문서들 — 전부 소유자를 가리켜야 한다.
HISTORY_DOCUMENTS = (
    README,
    "docs/10_FINAL_READINESS_REPORT.md",
    "docs/11_COMMERCIAL_GA_100_PLAN.md",
    "docs/12_COMMERCIAL_GA_100_CHECKLIST.md",
    "docs/13_COMMERCIAL_GA_100_PROGRESS.md",
    "docs/14_FINAL_REVIEW_REMEDIATION_PLAN.md",
    "docs/15_FINAL_REVIEW_REMEDIATION_CHECKLIST.md",
    "docs/16_COMMERCIAL_RELIABILITY_DEVELOPMENT_PLAN.md",
    "docs/17_COMMERCIAL_RELIABILITY_CHECKLIST.md",
    "docs/18_RELIABILITY_AND_CONNECTOME_DEVELOPMENT_PLAN.md",
    CHECKLIST,
)

# `23/23` 줄에 붙어 있어야 하는 범위/귀속 표기(게이트 인벤토리임을 밝히는 말).
GATE_COUNT_CONTEXT = ("attempt", "후보", "지문", "inventory", "인벤토리")

# 사람 축만 남았다고 말할 때 함께 있어야 하는 범위 한정 표기.
HUMAN_AXIS_SCOPE_MARKERS = ("후보 범위", "이 후보", "NX", "20_CURRENT_STATUS")

# 지원표가 정의해야 하는 네 단계(그 밖의 말은 분류로 쓰지 않는다).
SUPPORT_LEVELS = ("**Supported**", "**Experimental**", "**Unsupported**", "**Not evaluated**")

# soak 세 단계를 구분하는 표식 — 1차 FAIL 의 수치가 사라지면 PASS 만 남아 이력이 지워진다.
SOAK_MARKERS = ("SC-6 FAIL", "1654.9", "all_pass", "UNVERIFIED", "exit:141")

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_ENV_ROW_RE = re.compile(r"^\|[^|]*`AGK_SERVER_PORT`[^|]*\|[^|\n]*`(\d+)`", re.M)
_SERVE_PORT_RE = re.compile(r"--port\s+(\d+)")
_DOC_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1):(\d+)/(?:docs|redoc|openapi\.json)(?=[)\s`#]|$)")
_OPEN_CARD_RE = re.compile(r"^\|\s*(NX-\d+(?:-F\d+)?)\s*\|([^|]*)\|", re.M)
_DMG_ROW_MARKER = "Ssak-Ai-0.1.0.dmg"


def _read(relative: str, root: Path = REPO_ROOT) -> str:
    return (root / relative).read_text(encoding="utf-8")


def code_default_port(root: Path = REPO_ROOT) -> int:
    """제품 서버 기본 포트 — `ServerConfig` 안의 `port` 필드에서 읽는다(복사하지 않는다)."""
    text = _read(CONFIG, root)
    block = re.search(r"class ServerConfig\(BaseSettings\):(.*?)(?:\nclass |\Z)", text, re.S)
    assert block is not None, "ServerConfig 선언을 찾지 못했다 — 포트 계약의 출처가 사라졌다"
    match = re.search(r"^\s*port:\s*int\s*=\s*Field\(\s*default=(\d+)", block.group(1), re.M)
    assert match is not None, "ServerConfig.port 기본값을 읽지 못했다"
    return int(match.group(1))


def dev_ui_port(root: Path = REPO_ROOT) -> int:
    """대시보드 dev 서버 포트 — 제품 포트와 **다른 역할**이다."""
    text = _read(VITE_CONFIG, root)
    match = re.search(r"^\s*port:\s*(\d+)", text, re.M)
    assert match is not None, "vite dev 포트를 읽지 못했다"
    return int(match.group(1))


def open_cards(checklist_text: str) -> set[str]:
    """아직 열려 있는 카드(TODO/BLOCKED) — '사람뿐' 주장의 반증 목록."""
    cards: set[str] = set()
    for card, status in _OPEN_CARD_RE.findall(checklist_text):
        if "TODO" in status or "BLOCKED" in status:
            cards.add(card)
    return cards


def readme_port_violations(text: str, code_port: int, ui_port: int) -> list[str]:
    """README 의 실행·접속 안내가 **코드 기본값**과 어긋나면 보고한다(빈 목록 = 통과)."""
    problems: list[str] = []

    serve_ports = sorted({int(value) for value in _SERVE_PORT_RE.findall(text)})
    if serve_ports != [code_port]:
        problems.append(f"README 의 `agk serve --port` 예시가 코드 기본값과 다르다: {serve_ports} vs {code_port}")

    doc_ports = sorted({int(value) for value in _DOC_URL_RE.findall(text)})
    if doc_ports != [code_port]:
        problems.append(f"README 의 API 문서 주소가 서버 포트를 가리키지 않는다: {doc_ports} vs {code_port}")

    env_defaults = {int(value) for value in _ENV_ROW_RE.findall(text)}
    if env_defaults != {code_port}:
        problems.append(f"README 의 `AGK_SERVER_PORT` 기본값이 코드와 다르다: {sorted(env_defaults)} vs {code_port}")

    if ui_port == code_port:
        problems.append("dev UI 포트와 제품 포트가 같다 — 역할 구분 자체가 성립하지 않는다")
    if "8400" in text:
        problems.append("README 가 레거시 8400 을 다시 들여왔다(Vite 프록시와 어긋나는 값이다)")
    return problems


def gate_count_context_violations(text: str, label: str) -> list[str]:
    """문맥 없는 `23/23` 은 판정 근거로 쓸 수 없다(빈 목록 = 통과)."""
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if "23/23" in line and not any(marker in line for marker in GATE_COUNT_CONTEXT):
            problems.append(f"{label}:{number} — 후보/지문/범위 표기 없는 23/23")
    return problems


def human_axis_violations(readme_text: str, open_card_ids: set[str]) -> list[str]:
    """열린 기술 TODO 가 있는 동안 '사람뿐'을 한정 없이 주장하면 보고한다(빈 목록 = 통과)."""
    if not open_card_ids:
        return []

    problems: list[str] = []
    if "기술 축은 모두 닫혔" in readme_text:
        problems.append("README 가 기술 축 전체를 닫힌 것으로 주장한다(범위 한정 없음)")

    # '사람 축'을 언급하는 모든 줄이 주장은 아니다 — 남은 차단 사유로 세우는 줄만 본다.
    axis_lines = [
        line
        for line in readme_text.splitlines()
        if ("사람의 영역" in line or "사람 축" in line) and ("차단" in line or "남은" in line or "only" in line)
    ]
    if not axis_lines:
        problems.append("README 가 남은 차단 사유(사람 축)를 아예 말하지 않는다")
    if any(not any(marker in line for marker in HUMAN_AXIS_SCOPE_MARKERS) for line in axis_lines):
        problems.append(
            f"README 의 사람 축 주장이 범위 한정·현재 상태 링크 없이 서 있다 (열린 카드 {len(open_card_ids)}개)"
        )
    return problems


def owner_link_violations(relative: str, text: str, root: Path = REPO_ROOT) -> list[str]:
    """현재 상태 배너를 든 문서가 **실재하는 링크**로 소유자를 가리키는가(빈 목록 = 통과)."""
    owner_name = Path(CURRENT_STATUS).name
    targets = [
        target.partition("#")[0].split(" ", 1)[0]
        for target in _LINK_RE.findall(text)
        if not target.startswith(("http://", "https://", "mailto:"))
    ]
    owner_targets = [target for target in targets if target and Path(target).name == owner_name]
    if not owner_targets:
        return [f"{relative} 가 현재 상태 소유자를 링크로 가리키지 않는다"]

    unresolved = [target for target in owner_targets if not ((root / relative).parent / target).is_file()]
    if unresolved:
        return [f"{relative} 의 소유자 링크가 실재하지 않는다: {unresolved}"]
    return []


def support_matrix_violations(matrix: str) -> list[str]:
    """지원표가 네 단계를 정의하고, DMG 사실을 **판정과 분리**하는가(빈 목록 = 통과)."""
    problems: list[str] = []

    missing = [level for level in SUPPORT_LEVELS if level not in matrix]
    if missing:
        problems.append("지원표에 정의되지 않은 분류 단계: " + ", ".join(missing))

    dmg_rows = [line for line in matrix.splitlines() if line.startswith("|") and _DMG_ROW_MARKER in line]
    if not dmg_rows:
        problems.append("지원표가 DMG 산출물 행을 들고 있지 않다")
    for row in dmg_rows:
        if "Not evaluated" not in row:
            problems.append("DMG 산출물 행이 'Not evaluated' 로 분류되지 않았다(존재를 검증으로 읽게 된다)")
        for marker in ("codesign", "깨끗한"):
            if marker not in row:
                problems.append(f"DMG 산출물 행이 미완 검증({marker})을 밝히지 않는다")
        if "Supported" in row:
            problems.append("DMG 산출물 행이 지원으로 승격됐다 — 소유자 승인 없이는 금지다")

    if "no package/distribution evidence establishes a native desktop app" in matrix:
        problems.append("지원표가 여전히 '패키징 산출물 없음'이라는 낡은 근거를 들고 있다")
    return problems


def _ex05_status_cell(ledger: str) -> str | None:
    for line in ledger.splitlines():
        if line.startswith("| EX-05"):
            cells = line.split("|")
            if len(cells) > 3:
                return cells[3]
    return None


def soak_phase_violations(status_doc: str, ledger: str) -> list[str]:
    """soak 의 FAIL·PASS·미확정이 한 덩어리로 뭉개지지 않았는가(빈 목록 = 통과)."""
    problems: list[str] = []

    missing = [marker for marker in SOAK_MARKERS if marker not in status_doc]
    if missing:
        problems.append("현재 상태 문서가 soak 단계 표식을 빠뜨렸다: " + ", ".join(missing))

    cell = _ex05_status_cell(ledger)
    if cell is None:
        problems.append("EX 대장에서 EX-05 행을 찾지 못했다")
        return problems
    if "INCONCLUSIVE" not in cell:
        problems.append("EX-05 상태 셀이 종료·귀속 미확정(INCONCLUSIVE)을 말하지 않는다")
    if re.search(r"\bDONE\b", cell) and "DONE 아님" not in cell:
        problems.append("EX-05 가 DONE 으로 기록됐다 — 종료·귀속이 미확정인 채로는 승격할 수 없다")
    if "UNVERIFIED" not in ledger:
        problems.append("EX 대장이 재soak 후보 귀속 미확정(UNVERIFIED)을 밝히지 않는다")
    return problems


# --------------------------------------------------------------------------- 계약


def test_code_default_port_is_read_from_code() -> None:
    """포트 계약의 출처는 코드다 — 문서가 아니라 `ServerConfig.port`."""
    port = code_default_port()
    assert port == 8000, f"제품 기본 포트가 바뀌었다({port}) — 문서도 함께 고쳐야 한다"


def test_readme_guidance_matches_the_code_default_port() -> None:
    """새 고객이 README 를 그대로 따라가면 **서버가 서는 포트**에 도착해야 한다."""
    problems = readme_port_violations(_read(README), code_default_port(), dev_ui_port())
    assert not problems, " / ".join(problems)


def test_current_status_distinguishes_the_three_port_roles() -> None:
    """제품 포트 · dev UI 포트 · 패키징 주소를 한 표에서 구분하고, 무조건 치환을 금지한다."""
    text = _read(CURRENT_STATUS)
    port = code_default_port()
    ui = dev_ui_port()

    for token in (str(port), str(ui), "SSAK_HOST_URL", "ServerConfig", "vite.config.ts"):
        assert token in text, f"현재 상태 문서가 포트 역할 구분에서 {token} 을(를) 빠뜨렸다"
    assert "AGK_VLLM_API_BASE" in text, "8000 을 다른 서비스도 쓴다는 사실(무조건 치환 금지의 근거)이 빠졌다"


def test_no_gate_count_claim_without_candidate_or_scope() -> None:
    """`23/23` 은 후보·지문·범위와 함께만 쓴다 — 범위 없는 수는 판정 근거가 아니다."""
    named = (
        README,
        CURRENT_STATUS,
        SUPPORT_MATRIX,
        LEDGER,
        CHECKLIST,
        "docs/08_CHANGELOG.md",
        "docs/10_FINAL_READINESS_REPORT.md",
        "docs/13_COMMERCIAL_GA_100_PROGRESS.md",
        "docs/16_COMMERCIAL_RELIABILITY_DEVELOPMENT_PLAN.md",
        "docs/17_COMMERCIAL_RELIABILITY_CHECKLIST.md",
    )

    problems: list[str] = []
    for relative in named:
        problems.extend(gate_count_context_violations(_read(relative), relative))
    for path in sorted((REPO_ROOT / "docs/ga").glob("*.md")):
        relative = str(path.relative_to(REPO_ROOT))
        problems.extend(gate_count_context_violations(path.read_text(encoding="utf-8"), relative))
    assert not problems, "문맥 없는 23/23: " + " | ".join(problems)


def test_history_documents_point_at_the_single_status_owner() -> None:
    """현재 상태 배너는 한 문서가 소유한다 — 나머지는 그 문서를 **링크로** 가리킨다."""
    problems: list[str] = []
    for relative in HISTORY_DOCUMENTS:
        problems.extend(owner_link_violations(relative, _read(relative)))
    assert not problems, " / ".join(problems)


def test_current_status_document_owns_the_open_axes() -> None:
    """현재 상태 문서가 포트·판정·soak·열린 기술 축·사람 축을 모두 자기 안에 들고 있다."""
    text = _read(CURRENT_STATUS)

    for heading in (
        "## 1. 제품 접속",
        "## 2. 판정",
        "## 3. 8시간 soak",
        "## 4. 열려 있는 기술 TODO",
        "## 5. 사람",
    ):
        assert heading in text, f"현재 상태 문서에 {heading} 절이 없다"

    open_ids = open_cards(_read(CHECKLIST))
    assert len(open_ids) >= 3, f"체크리스트에서 열린 카드를 읽지 못했다: {sorted(open_ids)}"
    mentioned = {card for card in open_ids if card in text}
    assert len(mentioned) >= 3, (
        "현재 상태 문서가 열린 기술 카드를 구체적으로 나열하지 않는다 — '사람뿐'으로 읽히게 된다"
    )


def test_readme_does_not_claim_that_only_the_human_axis_remains() -> None:
    """열린 기술 TODO 가 있는 동안 '사람뿐'은 범위 한정 없이 설 수 없다(NX-07 수용 기준)."""
    problems = human_axis_violations(_read(README), open_cards(_read(CHECKLIST)))
    assert not problems, " / ".join(problems)


def test_support_matrix_separates_the_dmg_artifact_from_its_verification() -> None:
    """DMG 가 **존재한다**와 **검증됐다**를 구분한다 — 분류는 Not evaluated 다."""
    problems = support_matrix_violations(_read(SUPPORT_MATRIX))
    assert not problems, " / ".join(problems)


def test_soak_phases_stay_separated() -> None:
    """1차 FAIL · 교정 · 재soak JSON PASS · 종료/귀속 미확정을 한 값으로 뭉개지 않는다."""
    problems = soak_phase_violations(_read(CURRENT_STATUS), _read(LEDGER))
    assert not problems, " / ".join(problems)


# --------------------------------------------------------------------------- 이빨


def test_teeth_readme_port_drift_is_detected() -> None:
    healthy = _read(README)
    port = code_default_port()
    cases = {
        "serve 포트 불일치": healthy.replace(f"--port {port}", "--port 9999"),
        "Swagger 포트 불일치": healthy.replace(f":{port}/docs", ":9999/docs"),
        "OpenAPI 포트 불일치": healthy.replace(f":{port}/openapi.json", ":9999/openapi.json"),
        "환경변수 기본값 불일치": healthy.replace(f"`{port}`", "`9999`"),
        "문서 주소 누락": _DOC_URL_RE.sub("", healthy),
        "환경변수 기본값 누락": _ENV_ROW_RE.sub("", healthy),
    }
    assert not readme_port_violations(healthy, port, dev_ui_port()), "기준 README 가 이미 어긋난다"
    for label, text in cases.items():
        assert text != healthy, f"변이 적용 실패 — {label}"
        assert readme_port_violations(text, port, dev_ui_port()), f"이빨 없음 — {label}"


def test_teeth_unscoped_human_axis_claim_is_detected() -> None:
    healthy = _read(README)
    open_ids = open_cards(_read(CHECKLIST))
    assert open_ids, "전제 불성립 — 열린 카드가 하나도 없으면 이 계약은 공허하다"
    assert not human_axis_violations(healthy, open_ids), "기준 README 가 이미 위반이다"

    unscoped = healthy + "\n**기술 축은 모두 닫혔고** 남은 차단 사유는 **사람의 영역**이다 — 미배정, 승인 없음.\n"
    assert human_axis_violations(unscoped, open_ids), "이빨 없음 — 한정 없는 '사람뿐' 주장을 놓쳤다"
    assert human_axis_violations(healthy, set()) == [], "열린 카드가 없으면 주장을 막지 않는다"


def test_teeth_contextless_gate_count_is_detected() -> None:
    assert not gate_count_context_violations("측정(attempt-034 · 후보 `b1f3af5a…`): **23/23 PASS**", "합성")
    flagged = gate_count_context_violations("측정: required **23/23**", "합성")
    assert flagged, "이빨 없음 — 문맥 없는 23/23 을 통과시켰다"


def test_teeth_dmg_overclaim_is_detected() -> None:
    healthy = _read(SUPPORT_MATRIX)
    assert not support_matrix_violations(healthy), "기준 지원표가 이미 위반이다"

    lines = healthy.splitlines()
    index = next(i for i, line in enumerate(lines) if _DMG_ROW_MARKER in line)
    overclaimed = "\n".join(lines[:index] + ["| macOS DMG artifact | Supported | dist 에 있다 |"] + lines[index + 1 :])
    problems = support_matrix_violations(overclaimed)
    assert any("DMG 산출물 행" in problem for problem in problems), problems


def test_teeth_soak_done_promotion_is_detected() -> None:
    status = _read(CURRENT_STATUS)
    ledger = _read(LEDGER)
    assert not soak_phase_violations(status, ledger), "기준선이 이미 위반이다"

    lines = ledger.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("| EX-05"))
    promoted = "\n".join(
        lines[:index] + ["| EX-05 | 8h soak | **DONE** | SC-1~6 all_pass · UNVERIFIED |"] + lines[index + 1 :]
    )
    problems = soak_phase_violations(status, promoted)
    assert problems, "이빨 없음 — EX-05 를 DONE 으로 승격해도 통과했다"

    dropped_marker = soak_phase_violations(status.replace("SC-6 FAIL", "SC-6 PASS"), ledger)
    assert dropped_marker, "이빨 없음 — 1차 FAIL 표식을 지워도 통과했다"


def test_teeth_owner_pointer_must_resolve(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "20_CURRENT_STATUS.md").write_text("# 현재\n", encoding="utf-8")

    assert owner_link_violations("docs/x.md", "산문에서 이름만 말한다\n", root=tmp_path)
    assert owner_link_violations("docs/x.md", "[현재](20_CURRENT_STATUS.md)\n", root=tmp_path) == []
    assert owner_link_violations("docs/sub/x.md", "[현재](20_CURRENT_STATUS.md)\n", root=tmp_path)


@pytest.mark.parametrize("relative", HISTORY_DOCUMENTS)
def test_history_document_owner_link_resolves_relative_to_itself(relative: str) -> None:
    """링크는 그 문서 기준 상대경로다 — 이름만 맞고 경로가 틀리면 가리킴이 아니다."""
    assert owner_link_violations(relative, _read(relative)) == [], relative
