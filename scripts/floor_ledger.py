#!/usr/bin/env python
"""하한 원장 — 이 저장소의 탐지력 하한을 **한 자리에서** 물어볼 수 있게 한다.

하한은 다섯 harness 의 코드 상수와 네 개의 기록 artifact 에 흩어져 있고, “이 저장소에는 어떤 하한이 있고 무엇을 보고
정해졌는가” 를 묻는 자리는 사람의 기억뿐이었다. 그 물음이 중요한 까닭은 하한이 **판단**이기 때문이다 — 값만 있으면 나중에
누구도 그것을 낮춰도 되는지 판단할 수 없다. 그래서 이 도구는 층마다 하한을 모아 **관측·하한값·여유·근거(`why`)** 와
**승인(무엇을 보고 언제 누가)** 을 한 표로 낸다.

어디서 값을 가져오는가: 하한은 **카나리아와 같은 눈**으로 읽는다(`harness_canary.harness_floors`) — 기록이 있는 층은
저장본(마지막으로 승인된 실행의 관측), 나머지는 저장소를 직접 재서. 두 번째 구현을 만들면 표와 판정이 갈라지므로,
기록 artifact 가 승인 문장(`method`)·날짜를 담고 있으면 그것을, 담고 있지 않으면 **그 근거 파일의 마지막 커밋**(날짜·사람·해시)을
승인으로 적는다. 커밋은 하한 자체의 변경이 아닐 수도 있으므로 그 사실도 행마다 함께 적는다(모르는 것을 아는 척하지 않는다).

실패로 보는 것:

  * **하한이 없는 harness** — 하한 없는 층은 빈손으로도 결과를 통과시킨다(그 층의 하한을 원장이 말할 수 없다).
  * **근거 없는 하한** — 왜 그 값인지 물을 수 없는 하한은 나중에 내려도 되는지 판단할 수 없다.
  * **읽지 못한 기록 artifact** — 그 층의 하한을 원장이 말할 수 없다(기록이 깨졌거나 사라졌다).
  * **아무도 읽지 않는 기록** — `floors` 를 담았는데 어떤 harness 도 그것을 읽지 않으면, 그 기록은 다음 결함을 가리는
    면죄부다(기록을 남긴 층이 사라져도 아무도 모른다).
  * **승인 날짜를 읽지 못함** — git 이 없거나 근거가 추적되지 않으면 “언제 누가” 를 말할 수 없다(원장의 답이 추측이 된다).
  * **원장에 실린 하한이 너무 적음** — 모든 출처가 망가져 빈 표가 되면 “빠진 하한 없음” 과 구별되지 않는다.
  * **표 밖의 하한** — 이름이 하한처럼 생긴 상수인데 어떤 층의 하한 목록에도 안 실렸으면, 그 층은 하한이 없는 것과같다
    (카나리아가 눈멀게 한 사본으로 시험하지도, 표가 그것을 말하지도 못한다). 하한이면 그 층의 `coverage_floors` 에 실어
    카나리아 앞에 세우고, 아니면 **선언부**(`OUTSIDE` — 근거·소유자·재검토 기한)에 왜 아닌지 적어야 한다. 선언은
    양방향이다: 이제 하한 목록에 실린 것·사라진 상수는 “낡은 선언” 으로 실패한다(낡은 면죄부는 다음 결함을 가린다).
  * **사람이 승인한 목록과 다른 표** — 하한은 **판단**이므로 “지금 이렇다” 만으로는 부족하다: 어제 승인된 목록에서 하한을
    지우거나·내리거나·근거를 바꾸면 그 사실이 어디에도 안 남는다(커밋 메시지에만 남는 것은 기록이 아니다). 그래서 표는
    **기록**(`evidence/floor_ledger.json`, `--record --method`)과 대조한다: 기록에서 **사라진 하한** · **내려간 하한값** ·
    **바뀐 근거** · **기록에 없는 새 하한**은 실패다(내려간 하한은 이름·옛값·새값을 함께 낸다). **관측**은 대조하지 않는다 —
    관측은 매 회차 움직이고, 각 층의 하한값이 실제로 무는지는 그 층의 게이트가 판정한다(원장은 목록의 승인을 맡는다).
    관측 이동은 **보고**일 뿐이고(안전한 쪽으로 틀리는 것을 실패로 만들면 기록이 잡음이 된다), 하한을 늘린 것도 보고다.
  * **승인 없는 면제** — 면제(`OUTSIDE` 선언)도 **판단**이다(“이 상수는 하한이 아니다”). 그러므로 기록은 면제를
    **이름만이 아니라 약속까지**(왜 하한이 아닌지·누가 소유하는지·**언제 확인했고** 언제 다시 볼지) 담고, 표는 그 기록과
    대조한다: 기록에 없는 **새 면제** · 기록이 승인했는데 표에 없는 **거둔 면제** · **바뀐 근거·소유자** · **미룬 재검토 기한**은
    실패다. 기한을 미루는 것이 이 자리의 핵심이다 — 날짜를 뒤로 미는 것은 “그 도구가 층이 되었는지 다시 본다” 는 약속을
    한 회차 더 미루는 결정인데, 표는 날짜가 있으면 통과시키므로 승인 없이는 그 결정이 어디에도 안 남는다(면죄부가 스스로
    갱신된다). 그래서 기한은 **확인일**(`reviewed_on`)을 들고 있다: 확인일보다 앞설 수 없고, 확인일로부터 **창**
    (`_MAX_REVIEW_WINDOW_DAYS`)을 넘을 수 없으며(한 번의 확인으로 두 해를 미루지 못하게), 기한을 미루면서 확인일을
    그대로 두면 그것은 연장이 아니라 날짜 미루기이므로 **검토 없이 미룬 것**과 **검토하고 미룬 것**을 다른 문장으로 말한다.
    창 자체도 기록이 승인하는 값이라, 창을 넓히려면 상수를 고치고 `--record` 로 다시 기록해야 한다(둘이 갈라지면 기록이 먼저 실패한다).
    기한을 **앞당기거나** 확인일만 새로 잡은 것은 안전한 쪽이므로 보고만 하고, 옛 이름이 사라지고 새 이름이 생겼는데 약속이
    그대로면 한 문장으로 “이름만 바뀐 것으로 보인다” 고 말한다(**보인다** 까지만 — 원장은 상수의 동일성을 모른다).
    기한이 움직인 순간은 기록이 **스스로 적어 이어 가고**(`deadline_moves` — 미룬 횟수는 주장이 아니라 계산된 사실이다),
    그 이력은 기록이 자기 기한과 맞는지 검사받는다(마지막 이동의 새 기한이 지금 승인된 기한과 다르거나 이력이 이어지지
    않으면 실패다). 그리고 검토 없이 미룬 면제가 있는 실행은 **기록을 거부한다** — 그대로 기록하면 옛 기한이 덮여 그 사실이
    사라지기 때문이다(지우는 기록을 막는 자리). 재검토는 `--review` 가 기한 순서로 낸다: 면제마다 남은 날·창 사용량·
    미룬 횟수와 두 가지 답(층으로 세우거나, 확인일·기한을 다시 적어 기록으로 남기거나)을 붙여서.

```sh
.venv/bin/python scripts/floor_ledger.py --gate        # 표 + 판정(하나라도 어긋나면 exit 1)
.venv/bin/python scripts/floor_ledger.py --emit-json   # 리뷰·게이트 stage 가 읽는다(판정은 종료 코드)
.venv/bin/python scripts/floor_ledger.py --self-test   # 자기시험만(저장소를 읽지 않는다)
.venv/bin/python scripts/floor_ledger.py --review      # 면제 재검토 시트(기한이 가까운 것부터 · 두 가지 답)
.venv/bin/python scripts/floor_ledger.py --record --method "무엇을 보고 승인했는가"  # 지금 목록을 승인으로 남긴다
```
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_contract import (  # noqa: E402
    Cases,
    Floor,
    Probe,
    describe_self_test,
    floor_problems,
    floor_records,
    probe_problems,
)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EVIDENCE_DIR: Final[Path] = REPO_ROOT / "docs" / "ssak-ai-core" / "evidence"
# 하한 기록 — “이 하한들과 이 근거를 사람이 승인했다” 는 문장. 표는 이 기록과 대조해 **판단의 이동**을 묻는다.
# 이름을 `floor_ledger.json` 으로 둔 까닭은 증거 디렉터리의 다른 기록과 같은 관행(층 이름 = 파일 이름)이다.
RECORD: Final[Path] = EVIDENCE_DIR / "floor_ledger.json"
KIND_RECORDED: Final[str] = "기록"
KIND_MEASURED: Final[str] = "직접 측정"
KIND_SELF: Final[str] = "자기 판정"
# 자기 자신을 카나리아 루프에서 빼는 자리 — 하한을 만들려고 자기를 부르면 무한 재귀다.
# 대신 자기 하한을 **표의 마지막 행**으로 싣고 스스로 판정한다(자기시험·게이트도 같은 값을 본다).
SELF_NAME: Final[str] = "floor_ledger"
# 카나리아 script — 원장이 **신뢰하는 유일한 roster 출처**이므로 자기시험의 커밋 확인도 여기에 건다.
CANARY_SCRIPT: Final[Path] = SCRIPTS_DIR / "harness_canary.py"
# 이 원장 자신의 하한 — 표에 실린 하한이 이 수보다 적으면 “하한을 못 본 것” 이다. 모든 출처가 실패하면 표가 비는데,
# 빈 표는 “빠진 하한 없음” 과 구별되지 않는다.
_MIN_FLOORS: Final[int] = 15
_WHY_MIN_FLOORS: Final[str] = (
    "2026-09-24 기준 관측: 다른 층을 보는 하한 19개가 실린다(기록 넷: digest 2 · 회귀 원장 2 · 상태 주장 2 · "
    "배포 산출물 6 = 12, 직접 여섯: 열거 1 · namespace 1 · 도달 2 · 게이트 1 · 리허설 1 · 리뷰 1 = 7). 하한 15는 **한 층이 "
    "roster 에서 빠져도 정상 측정을 막지 않지만**(가장 큰 층이 6개를 들고 있다) **둘 이상 빠지면(≤ 12) 표를 내주면서 "
    "‘빠진 하한 없음’ 이라고 말하지 못하게** 한다 — 하한이나 출처가 망가지면 여기서 드러난다."
)
# 하한처럼 **생겼는가** — 이름이 이 꼴이면서 값이 숫자인 모듈 수준 상수만 후보로 삼는다(문자열 상수 `_WHY_*` 는 빠진다).
FLOOR_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"(^|_)(MIN|FLOOR|MINIMUM)(_|$)", re.IGNORECASE)
# 표 밖 스캔의 하한 — 스캔이 깨져 0 을 보고 “표 밖에 아무것도 없다” 로 통과하는 순간을 잡는다.
# 2026-09-24 기준 관측: 후보 32개(배선 22 · 선언 10). 하한 24 는 스캔이 절반쯤 눈멀거나 파일 몇 개를 놓쳤을 때 문다.
_MIN_CANDIDATES: Final[int] = 24
_WHY_MIN_CANDIDATES: Final[str] = (
    "2026-09-24 기준 관측: 이름이 하한처럼 생긴 숫자 상수가 32개고, 그중 22개는 어떤 층의 `coverage_floors` 가 읽는다."
    "하한 24 는 ‘얼마나 많이 찾았나’ 가 아니라 ‘스캔이 살아 있나’ 를 재다 — AST 파싱이 깨지거나 파일 몇 개가 사라지면 "
    "관측이 그 아래로 떨어지고, 그때 ‘표 밖에 아무것도 없다’ 가 ‘한 번도 안 봤다’ 와 구별된다. 후보가 줄어드는 것이 "
    "정상인 경우(상수를 지우는 리팩터링)에는 근거를 적고 이 값을 내린다."
)


# 면제의 재검토 창 — **한 번의 확인**으로 이 기간까지만 기한을 줄 수 있다(그보다 긴 창은 한 번의 확인으로 두 해를 미루는 것이다).
# 2026-09-24 기준 관측: 선언 10개의 기한이 모두 2026-12-31 이고 이 회차의 확인일이 2026-09-24 이므로 지금 창은 98일이다.
_MAX_REVIEW_WINDOW_DAYS: Final[int] = 366
_WHY_MAX_REVIEW_WINDOW: Final[str] = (
    "2026-09-24 기준 관측: 선언 10개의 기한이 모두 2026-12-31 이고 그 판단을 마지막으로 확인한 날이 2026-09-24 다(창 98일). "
    "366 은 ‘한 번의 확인이 일 년을 넘지 않는다’ 는 뜻이다 — 기한을 미루는 것 자체는 결정이지만(기록을 지나야 한다) 그 결정의 "
    "크기에도 상한이 있어야 한 번의 확인으로 면죄부를 두 해·세 해로 늘리지 못한다. 창을 넓히는 것은 이 상수를 고치고 **다시 "
    "기록하는** 일이다(기록도 창을 담고 있으므로 둘이 갈라지면 기록이 먼저 실패한다)."
)

# 기록이 담은 면제의 모양 — 이름만 담은 옛 기록과 약속(근거·소유자·확인일·기한)까지 담은 기록을 구별한다.
# 이름만 아는 기록으로는 “기한을 미뤘다” 를 물을 수 없고, 확인일 없는 기록으로는 “검토 없이 미뤘다” 를 물을 수 없다.
OUTSIDE_SHAPE_FULL: Final[str] = "full"
OUTSIDE_SHAPE_UNDATED: Final[str] = "undated"
OUTSIDE_SHAPE_NAMES: Final[str] = "names"
OUTSIDE_SHAPE_ABSENT: Final[str] = "absent"
OUTSIDE_SHAPE_NONE: Final[str] = "no-record"


@dataclass(frozen=True, slots=True)
class OutsideFloor:
    """표 밖의 하한 하나 — 이름·왜 아닌지·누가 소유하는지·**언제 확인했고** 언제 다시 볼지.

    면죄부가 되지 않도록 등록은 양방향이고 기한이 있다: 상수가 하한 목록에 실리거나 사라지면 낡은 선언으로,
    기한이 지나도 실패한다(그 사이 그 도구가 게이트에 들어왔는지 다시 보라는 뜻이다).
    기한은 **미루는 것도 결정**이고, 미루려면 그 결정을 받치는 **확인일**이 있어야 한다 — 날짜만 뒤로 미는 일은
    검토가 아니므로 원장은 “기한이 확인일로부터 창을 넘는가” 와 “확인일이 갱신됐는가” 를 함께 묻는다.
    """

    name: str
    reason: str
    owner: str
    reviewed_on: str
    review_by: str

    @property
    def promise(self) -> tuple[str, str, str, str]:
        """이 면제가 하는 약속 — 왜 하한이 아닌지·누가 소유하는지·언제 확인했고 언제 다시 볼지."""

        return (self.reason, self.owner, self.reviewed_on, self.review_by)

    @property
    def window(self) -> int | None:
        """확인일에서 기한까지의 창(일) — 둘 중 하나라도 못 읽으면 `None`(그 사실은 문장으로 난다)."""

        start, end = _as_day(self.reviewed_on), _as_day(self.review_by)
        return (end - start).days if start is not None and end is not None else None

    def as_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "reason": self.reason,
            "owner": self.owner,
            "reviewed_on": self.reviewed_on,
            "review_by": self.review_by,
        }


@dataclass(frozen=True, slots=True)
class RecordedOutside:
    """기록이 승인한 면제들 — 모양(`shape`)과 이름별 약속, 그리고 그 기록이 승인한 재검토 창.

    `entries` 의 값이 `None` 이면 그 이름은 **이름만** 승인된 것이다(약속을 비교할 근거가 없다). 기록이 없으면
    `shape` 는 `OUTSIDE_SHAPE_NONE` 이고, 그 사실은 `record_problems` 가 말한다(같은 사실을 두 번 말하지 않는다).
    """

    shape: str
    entries: dict[str, tuple[str, str, str, str] | None]
    window_days: int = 0
    window_why: str = ""

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self.entries)

    @property
    def promises(self) -> dict[str, tuple[str, str, str, str]]:
        """약속까지 아는 면제만 — 이름만 아는 기록에서는 빈 사전이다."""

        return {name: promise for name, promise in self.entries.items() if promise is not None}


# 선언부. 여기 없는 후보를 스캔이 찾으면 원장이 그 이름을 대며 실패한다 — 표 밖은 침묵이 아니라 목록이다.
OUTSIDE: Final[tuple[OutsideFloor, ...]] = (
    OutsideFloor(
        name="scripts/benchmark_ssak_search.py:LATENCY_NOISE_FLOOR_MS",
        reason=(
            "탐지력 하한이 아니라 **읽는 임계**다 — “이보다 작은 차이는 잡음이다” 라는 판정 기준이라, "
            "무엇을 봤는지가 아니라 결과를 어떻게 읽는지를 정한다(관측 대상이 없다)"
        ),
        owner="search",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/benchmark_ssak_search.py:VALID_SOURCE_AUTHORITY_MIN",
        reason="벤치마크 입력의 유효성 조건(권위 점수 하한) — 관측량이 아니라 fixture 선택 규칙이다",
        owner="search",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/evidence_bundle.py:DEFAULT_MIN_SOAK_SECONDS",
        reason="정책 기본값(soak 창의 길이) — 하한이 아니라 기본 인자다. 무엇을 봤는지가 아니라 무엇을 요청했는지다",
        owner="evidence",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:RSS_WARMUP_MIN_S",
        reason="창 길이의 하한(워밍업 제외 구간) — 입력 구간 선택 임계며, nx10 QA 도구의 계약 시험이 지킨다",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:THROUGHPUT_MIN_RUN_S",
        reason="실행 길이의 하한 — 그보다 짧으면 중간값이 성립하지 않는다는 표본 조건이다(하한이 아니라 유효성)",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:THROUGHPUT_BLOCK_MIN_S",
        reason="블록 길이의 하한 — 잡음 실측으로 정한 값이며 nx10 QA 도구의 계약 시험이 지킨다",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:THROUGHPUT_MIN_BLOCKS_PER_QUARTER",
        reason="분기당 표본 수의 하한 — 관측을 세지만 이 저장소의 증거 게이트 roster 밖에 있는 도구다",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:ATTRIBUTION_MIN_DELTA_RATIO",
        reason="귀속 판단의 임계(“증가가 2% 미만이면 귀속할 증거가 없다”) — 관측량이 아니라 판정 기준이다",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:DEEP_MIN_WINDOWS",
        reason=(
            "**하한처럼 쓰이지만 roster 밖이다** — “이보다 적으면 함수 순위를 말하지 않는다” 는 주장 하한인데, "
            "그 도구가 아직 어떤 게이트의 층도 아니다(층으로 세우는 일은 nx10 QA 트랙의 결정이다)"
        ),
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
    OutsideFloor(
        name="scripts/val02_staging.py:PATH_MIN_CALLER_SHARE",
        reason="경로 지목의 임계(한 호출자가 절반 이상일 때만 지목한다) — 판정 기준이지 탐지량이 아니다",
        owner="nx10-qa",
        reviewed_on="2026-09-24",
        review_by="2026-12-31",
    ),
)

# 자기시험용 합성 승인 — git 을 읽지 않고 행 규칙만 묻는다.
_COMMIT_SAMPLE: Final[dict[str, str]] = {
    "on": "2026-01-01",
    "by": "tester",
    "hash": "abc1234",
    "path": "scripts/probe.py",
}
# 커밋에서 “언제 누가” 를 읽는 자리 — 하한 자체의 변경이 아닐 수 있으므로 그 사실을 행마다 적는다.
COMMIT_NOTE: Final[str] = (
    "그 하한을 담은 파일의 마지막 커밋이다(하한만 바뀐 커밋이 아닐 수 있다 — 기록 artifact 는 그 커밋이 곧 승인이다)"
)


def load_canary() -> ModuleType:
    """카나리아를 불러온다 — **roster 와 하한을 읽는 눈의 단일 출처**(원장이 자기 눈을 만들지 않는다)."""

    spec = importlib.util.spec_from_file_location("ledger_canary", CANARY_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{CANARY_SCRIPT.name} 를 불러오지 못했다")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def commit_of(path: Path, *, repo: Path = REPO_ROOT) -> dict[str, str] | None:
    """그 파일의 마지막 커밋(날짜·사람·해시) — git 이 없거나 추적되지 않으면 None(호출자가 실패로 처리)."""

    try:
        relative = str(path.resolve().relative_to(repo.resolve()))
    except ValueError:  # 저장소 밖 — 커밋을 말할 수 없다
        return None
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cs%x09%an%x09%h", "--", relative],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    fields = result.stdout.strip().split("\t")
    if result.returncode != 0 or len(fields) != 3 or not all(fields):
        return None
    return {"on": fields[0], "by": fields[1], "hash": fields[2], "path": relative, "note": COMMIT_NOTE}


def orphan_records(evidence_dir: Path, known: Sequence[Path]) -> tuple[str, ...]:
    """`floors` 를 담았는데 아무도 읽지 않는 기록 — 순수 함수라 합성 입력으로 시험한다.

    읽는 자리(`known`)는 roster 가 가리키는 artifact 경로다. 기록을 남긴 층이 roster 에서 사라지면 여기서 걸린다.
    """

    known_paths = {path.resolve() for path in known}
    found: list[str] = []
    for path in sorted(evidence_dir.glob("*.json")):
        if path.resolve() in known_paths:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # 못 읽는 파일은 이 검사의 대상이 아니다(그 파일을 읽는 층이 따로 실패한다)
        floors = payload.get("floors") if isinstance(payload, dict) else None
        if isinstance(floors, list) and floors:
            found.append(_display(path))
    return tuple(found)


def _display(path: Path) -> str:
    """사람이 읽는 경로 — 저장소 안이면 상대 경로(다른 기계에서는 절대 경로가 틀린다)."""

    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def floor_candidates(directory: Path = SCRIPTS_DIR) -> tuple[str, ...]:
    """이름이 하한처럼 생긴 **숫자 상수** — `scripts/<파일>.py:<이름>` 꼴로.

    AST 로 읽는다: 주석이나 문자열 안의 이름에 속지 않고, 값이 숫자 리터럴이 아닌 것(`_WHY_*` 같은 근거 문장)은
    후보가 아니다. 이름 패턴(`MIN|FLOOR|MINIMUM`)은 **추측**이므로 완전하지 않다 — 후보가 아닌 임계값
    (`ATTRIBUTION_DOMINANCE` 처럼)이나 다른 이름으로 넘긴 하한은 이 스캔이 못 본다. 그 한계는 문서에 적었다.

    돌려주는 순서는 **이름순**이다(파일 순회 순서·정의 순서가 아니다) — 같은 저장소에 같은 답을 내야 판정이 흔들리지 않는다.
    """

    found: list[str] = []
    for path in sorted(directory.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue  # 못 읽는 파일은 이 검사의 대상이 아니다(그 파일을 돌리는 층이 따로 실패한다)
        for node in tree.body:
            name = ""
            value: ast.expr | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, value = node.target.id, node.value
            if not name or value is None or not FLOOR_NAME_PATTERN.search(name):
                continue
            if not isinstance(value, ast.Constant) or isinstance(value.value, bool):
                continue
            if not isinstance(value.value, (int, float)):
                continue
            found.append(f"{_display(path)}:{name}")
    return tuple(sorted(found))


def wired_constants(sources: Iterable[Path]) -> frozenset[str]:
    """표가 **실제로 읽는** 상수 — `Floor(..., minimum=<상수>)` 의 그 상수만이다.

    위치 인수 셋째 자리와 `minimum=` 키워드 둘 다 본다. 상수를 다른 이름으로 넘기거나 계산해서 넘기면 이 눈은
    못 보므로, 그때는 선언부가 그 사실을 밝힌다(스캔의 침묵을 선언이 덮는다).
    """

    wired: set[str] = set()
    for path in sources:
        try:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_floor_call(node):
                continue
            argument: ast.expr | None = None
            for keyword in node.keywords:
                if keyword.arg == "minimum":
                    argument = keyword.value
            if argument is None and len(node.args) >= 3:
                argument = node.args[2]
            if isinstance(argument, ast.Name):
                wired.add(f"{_display(Path(path))}:{argument.id}")
    return frozenset(wired)


def _is_floor_call(node: ast.Call) -> bool:
    """`Floor(...)` 호출인가 — `harness_contract` 의 하한 생성자 이름을 본다(별칭은 못 본다)."""

    return (isinstance(node.func, ast.Name) and node.func.id == "Floor") or (
        isinstance(node.func, ast.Attribute) and node.func.attr == "Floor"
    )


def outside_floors(
    candidates: Sequence[str],
    wired: Iterable[str],
    declared: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(선언 없는 후보, 낡은 선언) — 순수 함수라 합성 입력으로 시험한다.

    낡은 선언은 둘이다: 이제 하한 목록에 실린 것(등록할 이유가 사라졌다)과 아예 사라진 상수(그 선언이 가리키는
    것이 없다). 둘 다 면죄부가 되므로 실패다.
    """

    wired_set = set(wired)
    declared_set = set(declared)
    undeclared = tuple(name for name in candidates if name not in wired_set and name not in declared_set)
    stale = tuple(sorted(name for name in declared_set if name in wired_set or name not in set(candidates)))
    return undeclared, stale


def outside_problems(
    candidates: Sequence[str],
    wired: Iterable[str],
    declared: Sequence[OutsideFloor],
    *,
    today: date | None = None,
    renamed: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """표 밖 하한의 판정 — 선언 없는 후보·낡은 선언·근거 없는 선언·기한 경과를 모두 실패로 만든다.

    `renamed` 는 “이름만 바뀐 것으로 보이는” 짝이다(그 판단은 `outside_record_problems` 가 문장으로 낸다) —
    그 옛 이름은 낡은 선언으로 한 번 더 말하지 않는다(하나의 결정이 두 문장으로 보이지 않게).
    """

    as_of = today or date.today()
    undeclared, stale = outside_floors(candidates, wired, [item.name for item in declared])
    paired = {old for old, _new in renamed}
    stale = tuple(name for name in stale if name not in paired)
    problems: list[str] = []
    if undeclared:
        problems.append(
            f"하한처럼 생긴 상수인데 어떤 층의 하한 목록에도 없고 선언도 없다: {', '.join(undeclared)} — "
            "하한이면 그 층의 `coverage_floors` 에 실어 카나리아 앞에 세우고, 아니면 이 원장의 `OUTSIDE` 에 왜 아닌지 적어라"
        )
    if stale:
        problems.append(f"낡은 선언(이미 하한 목록에 실렸거나 사라진 상수): {', '.join(stale)} — 면죄부는 지운다")
    for item in declared:
        if not item.reason.strip() or not item.owner.strip():
            problems.append(
                f"표 밖 선언에 근거 또는 소유자가 비었다: {item.name} — 왜 하한이 아닌지 물을 수 없으면 면죄부다"
            )
        reviewed = _as_day(item.reviewed_on)
        if reviewed is None:
            problems.append(
                f"표 밖 선언의 확인일을 읽지 못했다: {item.name}({item.reviewed_on!r}) — 언제 확인한 판단인지 말할 수 없는 "
                "면제는 “검토 없이 미룬 것” 과 구별되지 않는다"
            )
        elif reviewed > as_of:
            problems.append(
                f"표 밖 선언의 확인일이 아직 오지 않았다: {item.name}({item.reviewed_on}) — 확인은 미래의 일이 아니다"
            )
        due = _as_day(item.review_by)
        if due is None:
            problems.append(f"표 밖 선언의 재검토 기한을 읽지 못했다: {item.name}({item.review_by!r})")
        elif due < as_of:
            problems.append(
                f"표 밖 선언의 재검토 기한이 지났다: {item.name}({item.review_by}, 확인일 {item.reviewed_on}) — "
                "그 도구가 층이 되었는지 다시 보라(`--review` 가 검토 순서를 낸다)"
            )
        window = item.window
        if window is None:
            continue  # 못 읽는 날짜는 위에서 이미 문장으로 냈다(같은 사실을 두 번 말하지 않는다)
        if window < 0:
            problems.append(
                f"표 밖 선언의 기한이 확인일보다 앞서 있다: {item.name}({item.reviewed_on} → {item.review_by}) — "
                "기한은 확인보다 뒤의 일이다(둘 중 하나가 잘못 적렸다)"
            )
        elif window > _MAX_REVIEW_WINDOW_DAYS:
            problems.append(
                f"표 밖 선언의 기한이 확인일로부터 **창을 넘는다**: {item.name}(확인 {item.reviewed_on} → 기한 "
                f"{item.review_by}, {window}일 > 창 {_MAX_REVIEW_WINDOW_DAYS}일) — 한 번의 확인으로 그만큼 길게 줄 수 "
                "없다: 기한을 당기거나 창을 넓히는 결정을 `--record` 로 남겨라"
            )
    return problems


def _as_day(text: str) -> date | None:
    """날짜로 읽히면 그 날짜, 아니면 `None` — 못 읽는 기한은 표 쪽 규칙이 이미 문장으로 낸다(여기서 또 말하지 않는다)."""

    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def recorded_outside(stored: dict[str, object] | None) -> RecordedOutside:
    """기록이 승인한 면제를 읽는다 — 모양(없음·이름만·날짜만·약속까지)·이름별 약속·승인된 재검토 창.

    기록은 두 번 자라났고 그 둘 다 “물을 수 없는 것” 을 문장으로 만들기 위해 남겼다:
    옛 기록은 면제를 **이름으로만** 담았으므로 “기한을 미뤘다” 를 물을 자리가 없고, 이 회차 이전의 기록은 약속을 담았지만
    **확인일이 없어** “검토 없이 미뤘다” 를 물을 자리가 없다. 모르는 것을 통과로 삼키지 않으려고 모양을 함께 돌려준다.
    """

    if stored is None:
        return RecordedOutside(OUTSIDE_SHAPE_NONE, {})
    block = stored.get("outside")
    if not isinstance(block, dict):
        return RecordedOutside(OUTSIDE_SHAPE_ABSENT, {})
    declared = block.get("declared")
    if not isinstance(declared, list):
        return RecordedOutside(OUTSIDE_SHAPE_ABSENT, {})
    window = block.get("review_window")
    days = int(window.get("days", 0)) if isinstance(window, dict) else 0
    why = str(window.get("why", "")) if isinstance(window, dict) else ""
    entries: dict[str, tuple[str, str, str, str] | None] = {}
    named_only = dated = False
    for item in declared:
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            dated = dated or not str(item.get("reviewed_on", "")).strip()
            entries[str(item["name"])] = (
                str(item.get("reason", "")),
                str(item.get("owner", "")),
                str(item.get("reviewed_on", "")),
                str(item.get("review_by", "")),
            )
        elif isinstance(item, str) and item.strip():
            entries[item] = None
            named_only = True
    if not entries:
        return RecordedOutside(OUTSIDE_SHAPE_ABSENT, {})
    shape = OUTSIDE_SHAPE_NAMES if named_only else OUTSIDE_SHAPE_UNDATED if dated else OUTSIDE_SHAPE_FULL
    return RecordedOutside(shape, entries, days, why)


def renamed_declarations(
    declared: Sequence[OutsideFloor],
    recorded: RecordedOutside,
    *,
    candidates: Sequence[str],
    wired: Iterable[str],
) -> tuple[tuple[str, str], ...]:
    """이름만 바뀐 것으로 **보이는** 면제 짝 — (기록의 옛 이름, 표의 새 이름).

    짝의 조건은 좁다: 옛 이름이 기록이 승인한 면제인데 표에서 사라졌거나 낡은 선언이고, 새 이름은 **실재하는 후보**이며
    표가 선언했는데 기록은 모르며, 약속(근거·소유자·기한)이 **토씨 하나 안 틀리고 같을 때**만 말한다. 일부라도 다르면
    짝짓지 않는다 — 그것은 이름 변경이 아니라 다른 판단일 수 있고, 원장은 상수의 동일성을 아는 것이 아니다(추측을
    사실처럼 말하지 않는다). 옛 면제 하나를 두 새 면제가 나눠 가질 수는 없으므로 먼저 온 짝이 가져간다.
    """

    if recorded.shape != OUTSIDE_SHAPE_FULL:
        return ()  # 약속을 모르는 기록으로는 “이름만 바뀌었다” 를 말할 근거가 없다
    promised = recorded.promises
    now = {item.name: item.promise for item in declared}
    _undeclared, stale = outside_floors(candidates, wired, list(now))
    live = set(candidates)
    fresh = sorted(name for name in now if name not in promised and name in live)
    pairs: list[tuple[str, str]] = []
    claimed: set[str] = set()
    for old in sorted(promised):
        if old in now and old not in set(stale):
            continue  # 옛 이름이 아직 표에 살아 있다 — 이름이 바뀐 자리가 아니다
        for new in fresh:
            if new in claimed or now[new] != promised[old]:
                continue
            pairs.append((old, new))
            claimed.add(new)
            break
    return tuple(pairs)


def outside_record_problems(
    declared: Sequence[OutsideFloor],
    recorded: RecordedOutside,
    *,
    renamed: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """기록이 승인한 **면제**와 지금 표의 면제가 같은가 — 면제의 생성·거둠·근거 변경·기한 연장을 승인으로 묶는다.

    하한이 아니라 면제를 묻는 까닭은 면제가 “이 상수는 하한이 아니다” 라는 **판단**이기 때문이다. 그중에서도
    **기한을 미루는 것**이 이 자리의 핵심이다: 날짜를 뒤로 미는 것은 “그 도구가 층이 되었는지 다시 본다” 는 약속을
    한 회차 더 미루는 결정인데, 표는 날짜가 있으면 통과시키므로 승인 없이는 그 결정이 어디에도 안 남는다.
    그리고 **검토 없이 미룬 것**과 **검토하고 미룬 것**은 다른 사건이므로 다른 문장으로 말한다: 기한만 뒤로 가고
    확인일이 그대로면 그것은 연장이 아니라 날짜 미루기고, 둘이 함께 움직였으면 그 결정을 `--record` 로 남기게 한다.
    """

    if recorded.shape == OUTSIDE_SHAPE_NONE:
        return []  # “기록이 없다” 는 문장은 `record_problems` 가 낸다
    if recorded.shape == OUTSIDE_SHAPE_ABSENT:
        return [
            "기록에 면제 목록(`outside`)이 없다 — 무엇이 면제됐는지 승인하지 않은 기록은 면제의 목록이 아니다"
            "(`--record --method` 로 다시 기록하라)"
        ]
    paired = {name for pair in renamed for name in pair}
    problems: list[str] = []
    if recorded.shape == OUTSIDE_SHAPE_NAMES:
        problems.append(
            f"기록이 면제를 **이름으로만** 담고 있다({len(recorded.entries)}개) — 왜 하한이 아닌지·누가 소유하는지·"
            "언제까지인지를 승인한 적이 없으므로 “기한을 미뤘다” 를 물을 자리가 없다: `--record --method` 로 약속까지 담아 "
            "다시 기록하라"
        )
    if recorded.shape == OUTSIDE_SHAPE_UNDATED:
        problems.append(
            "기록이 면제의 **확인일**을 담고 있지 않다 — 언제의 확인으로 이 기한을 준 것인지 말하지 못하므로 “검토 없이 "
            "미뤘다” 와 “검토하고 미뤘다” 를 가를 자리가 없다: `--record --method` 로 확인일까지 담아 다시 기록하라"
        )
    if recorded.shape == OUTSIDE_SHAPE_FULL and recorded.window_days != _MAX_REVIEW_WINDOW_DAYS:
        problems.append(
            f"기록된 재검토 창이 지금 규칙과 다르다(기록 {recorded.window_days}일 ≠ 지금 {_MAX_REVIEW_WINDOW_DAYS}일) — "
            "기록은 그 창으로 승인된 것이므로 창을 넓히는 결정은 근거와 함께 `--record --method` 로 다시 기록해야 한다"
        )
    names_now = {item.name for item in declared}
    appeared = sorted(name for name in names_now - recorded.names if name not in paired)
    if appeared:
        problems.append(
            f"기록에 없는 면제가 있다: {', '.join(appeared)} — 면제를 만드는 것도 결정이다: 왜 하한이 아닌지·누가 "
            "소유하는지·언제까지를 `--record --method` 로 승인하라(면제는 승인된 목록에 실려야 한다)"
        )
    withdrawn = sorted(name for name in recorded.names - names_now if name not in paired)
    if withdrawn:
        problems.append(
            f"기록이 승인한 면제가 표에 없다: {', '.join(withdrawn)} — 면제를 거두는 것(하한으로 승격했거나 그 상수를 "
            "지운 것)도 결정이다: `--record --method` 로 남겨라"
        )
    if recorded.shape == OUTSIDE_SHAPE_FULL:
        changes, deferred, bare = _outside_moves(declared, recorded, paired)
        if changes:
            problems.append(
                f"기록과 근거·소유자가 달라진 면제가 있다: {', '.join(changes)} — 면제의 근거가 바뀌면 그것은 다른 "
                "판단이다(`--record --method` 로 다시 기록하라)"
            )
        if bare:
            seen = {item.name: item.reviewed_on for item in declared}
            moved = "; ".join(
                f"{name} {was} → {now}(확인일 {seen.get(name, '못 읽음')} 그대로)" for name, was, now in bare
            )
            problems.append(
                f"면제의 기한만 미뤘다({moved}) — 확인일이 그대로인 연장은 검토가 아니다: 언제 다시 본 것인지"
                "(`reviewed_on`)를 함께 적어라"
            )
        if deferred:
            moved = "; ".join(f"{name} {was} → {now}" for name, was, now in deferred)
            problems.append(
                f"면제의 재검토 기한을 미뤘다({moved}) — “그 도구가 층이 되었는지 다시 본다” 는 약속을 뒤로 미루는 "
                "것도 결정이다: 무엇을 보고 미뤘는지 `--record --method` 로 남겨라"
            )
    for old, new in renamed:
        was = recorded.promises.get(old)
        owner, review_by = (was[1], was[2]) if was else ("", "")
        problems.append(
            f"기록의 면제 {old} 가 표의 {new} 로 **이름만 바뀐 것으로 보인다**(근거·소유자·재검토 기한이 그대로다: "
            f"소유자 {owner} · 재검토 {review_by}) — 상수 이름을 바꾸는 것도 결정이다: 옛 이름의 선언을 정리하고 "
            "`--record --method` 로 그 결정을 남겨라. 이름이 바뀐 것이 아니라면 왜 옛 이름이 사라지고 새 이름이 생겼는지 "
            "남겨라 — 원장은 상수의 동일성을 모른다"
        )
    return problems


def _outside_moves(
    declared: Sequence[OutsideFloor], recorded: RecordedOutside, paired: set[str]
) -> tuple[tuple[str, ...], tuple[tuple[str, str, str], ...], tuple[tuple[str, str, str], ...]]:
    """기록과 달라진 면제 — (근거·소유자가 바뀐 이름들, 검토하고 미룬 것들, **검토 없이** 미룬 것들).

    기한을 당긴 것은 안전한 쪽이므로 여기 안 든다(`outside_pulled` 가 보고만 한다). 근거·소유자가 바뀐 면제는
    그 자체가 다른 판단이므로 기한 이동으로 한 번 더 말하지 않는다. 기한을 미룬 것 중에서도 확인일이 함께
    움직였는지로 나뉜다 — 그 둘은 다른 사건이고(검토한 연장·검토 없는 연장을 같은 문장으로 말하면 둘 다 같은
    초록으로 보인다), 원장이 말할 수 있는 것은 “날짜가 함께 움직였나” 까지다(확인이 정말 있었는지는 사람의 몫이다).
    """

    changes: list[str] = []
    deferred: list[tuple[str, str, str]] = []
    bare: list[tuple[str, str, str]] = []
    for item in declared:
        was = recorded.promises.get(item.name)
        if was is None or item.name in paired:
            continue
        if (was[0], was[1]) != (item.reason, item.owner):
            changes.append(item.name)
            continue
        before, after = _as_day(was[3]), _as_day(item.review_by)
        if before is None or after is None or after <= before:
            continue
        was_review, now_review = _as_day(was[2]), _as_day(item.reviewed_on)
        refreshed = was_review is not None and now_review is not None and now_review > was_review
        entry = (item.name, was[3], item.review_by)
        (deferred if refreshed else bare).append(entry)
    return tuple(sorted(changes)), tuple(sorted(deferred)), tuple(sorted(bare))


def outside_reviewed(
    declared: Sequence[OutsideFloor], recorded: RecordedOutside, *, paired: Iterable[str] = ()
) -> tuple[str, ...]:
    """기록보다 **확인일이 뒤로 간** 면제 — 실패가 아니라 보고다(더 자주 본 것을 실패로 만들면 아무도 다시 보지 않는다).

    기한을 미룬 면제는 여기 안 실린다(그것은 결정이므로 위의 문장과 `--record` 가 맡는다) — 이 목록은 기한을 그대로
    둔 채 확인만 새로 한 경우다.
    """

    skipped = set(paired)
    reviewed: list[str] = []
    for item in declared:
        was = recorded.promises.get(item.name)
        if was is None or item.name in skipped:
            continue
        before, after = _as_day(was[2]), _as_day(item.reviewed_on)
        if before is None or after is None or after <= before:
            continue
        was_due, now_due = _as_day(was[3]), _as_day(item.review_by)
        deferred = was_due is not None and now_due is not None and now_due > was_due
        if not deferred:  # 기한을 미룬 확인은 연장의 문장이 맡는다(같은 결정을 두 번 세지 않는다)
            reviewed.append(f"{item.name} {was[2]} → {item.reviewed_on}")
    return tuple(sorted(reviewed))


def outside_pulled(
    declared: Sequence[OutsideFloor], recorded: RecordedOutside, *, paired: Iterable[str] = ()
) -> tuple[str, ...]:
    """기록보다 기한을 **앞당긴** 면제 — 실패가 아니라 보고다(더 자주 보는 쪽은 안전한 쪽이다)."""

    skipped = set(paired)
    pulled: list[str] = []
    for item in declared:
        was = recorded.promises.get(item.name)
        if was is None or item.name in skipped:
            continue
        before, after = _as_day(was[3]), _as_day(item.review_by)
        if before is not None and after is not None and after < before:
            pulled.append(f"{item.name} {was[3]} → {item.review_by}")
    return tuple(sorted(pulled))


@dataclass(frozen=True, slots=True)
class LayerRow:
    """한 층의 하한 묶음 — 어디서 읽었고, 무엇으로 승인됐고, 하한이 무엇인가."""

    name: str
    kind: str
    source: str
    floors: tuple[Floor, ...]
    approval: dict[str, str]
    commit: dict[str, str] | None
    note: str = ""

    @property
    def approval_text(self) -> str:
        """사람이 읽는 승인(전문) — 기록이 승인 문장을 담고 있으면 그것, 아니면 그 근거 파일의 마지막 커밋."""

        method = self.approval.get("method", "").strip()
        recorded = f"{self.approval.get('recorded_on', '')} {method}".strip()
        if method and method.startswith(self.approval.get("recorded_on", "")):
            recorded = method  # 기록이 이미 날짜로 시작하면 두 번 적지 않는다
        if recorded:
            return recorded
        if self.commit is None:
            return "**못 읽음**"
        return f"{self.commit['on']} {self.commit['by']} {self.commit['hash']}"

    @property
    def approval_short(self) -> str:
        """표 칸에 들어갈 승인 — 날짜와 지문만(전문은 층별 각주에 있다)."""

        if self.approval:
            return f"{self.approval.get('recorded_on', '?')} 기록"
        if self.commit is None:
            return "**못 읽음**"
        return f"{self.commit['on']} {self.commit['hash']}"

    def as_mapping(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "floors": floor_records(self.floors),
            "approval": dict(self.approval),
            "commit": dict(self.commit) if self.commit else None,
            "approval_text": self.approval_text,
            "approval_short": self.approval_short,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Ledger:
    """이 실행이 읽은 원장 — 층·고아 기록·표 밖 스캔·문제."""

    rows: tuple[LayerRow, ...]
    orphans: tuple[str, ...]
    problems: tuple[str, ...]
    seconds: float
    candidates: tuple[str, ...] = ()
    covered: tuple[str, ...] = ()
    outside: tuple[OutsideFloor, ...] = ()
    # 기록 대조의 상태(경로·승인·이동·문제) — JSON 보고에 그대로 실린다.
    record: dict[str, object] = field(default_factory=dict)

    @property
    def canvas(self) -> int:
        """이 원장이 **다른 층에서 본** 하한 수 — 자기 하한이 재는 값이다(자기를 세면 저절로 참이 된다)."""

        return sum(len(row.floors) for row in self.rows if row.kind != KIND_SELF)

    @property
    def floors(self) -> int:
        return sum(len(row.floors) for row in self.rows)

    @property
    def ok(self) -> bool:
        """표와 **기록** 전체의 판정 — 게이트가 종료 코드로 말하는 것과 같아야 한다(JSON 의 `verdict` 가 이것을 쓴다)."""

        return not self.problems and not self.record.get("problems")

    def as_mapping(self, probe: Probe) -> dict[str, object]:
        return {
            "command": ["python", "scripts/floor_ledger.py"],
            "layers": [row.as_mapping() for row in self.rows],
            "orphans": list(self.orphans),
            "counts": {
                "layers": len(self.rows),
                "floors": self.floors,
                "canvas": self.canvas,
                "recorded": sum(1 for row in self.rows if row.kind == KIND_RECORDED),
                "measured": sum(1 for row in self.rows if row.kind == KIND_MEASURED),
                "self": sum(1 for row in self.rows if row.kind == KIND_SELF),
                "orphans": len(self.orphans),
                "outside_scanned": len(self.candidates),
                "outside_silent": len(set(self.candidates) - set(self.covered) - {item.name for item in self.outside}),
                "outside_declared": len(self.outside),
                "without_basis": sum(1 for row in self.rows for floor in row.floors if not floor.why.strip()),
                "undated": sum(1 for row in self.rows if row.commit is None),
                "recorded_floors": _record_int(self.record, "floors"),
                "record_lowered": _record_int(self.record, "lowered"),
                "record_moved": len(_record_lines(self.record, "moves")),
                "record_layers_moved": len(_record_lines(self.record, "vanished_layers"))
                + len(_record_lines(self.record, "added_layers")),
                "record_layers_renamed": len(_record_lines(self.record, "renamed_layers")),
                "record_renames": len(_record_lines(self.record, "renames")),
                "record_exemptions": _record_int(_record_dict(self.record, "outside"), "recorded"),
                "record_exemptions_window": _record_int(_record_dict(self.record, "outside"), "recorded_window_days"),
                "record_exemptions_pulled": len(_record_lines(_record_dict(self.record, "outside"), "pulled")),
                "record_exemptions_reviewed": len(_record_lines(_record_dict(self.record, "outside"), "reviewed")),
                "record_exemptions_moves": len(_record_lines(_record_dict(self.record, "outside"), "deadline_moves")),
            },
            "record": dict(self.record),
            "outside": {
                "scanned": len(self.candidates),
                "wired": len(self.covered),
                "declared": [item.as_mapping() for item in self.outside],
                # 기록이 승인한 면제와의 대조 — 읽는 사람이 선언과 승인을 같은 자리에서 본다.
                "record": _record_dict(self.record, "outside"),
                "min_candidates": _MIN_CANDIDATES,
                "note": (
                    "이름이 하한처럼 생긴 숫자 상수만 본다(AST) — 다른 이름으로 넘긴 하한·다른 패턴의 임계값은 이 스캔이 못 본다"
                ),
            },
            # 소요 시간은 **판정 수치에 넣지 않는다** — 게이트의 추이에 그날의 기계 속도가 섞이면 움직임이 안 보인다.
            "runtime": {"seconds": round(self.seconds, 1)},
            "coverage": {
                "canvas": self.canvas,
                "floors": self.floors,
                "min_floors": _MIN_FLOORS,
                "candidates": len(self.candidates),
                "min_candidates": _MIN_CANDIDATES,
            },
            "floors": floor_records(coverage_floors(self)),
            "probe": probe.as_mapping(),
            "problems": list(self.problems),
            "verdict": "PASS" if self.ok else "FAIL",
        }


def _record_dict(record: dict[str, object], key: str) -> dict[str, object]:
    """기록 보고에서 객체 하나 — 없거나 객체가 아니면 빈 사전."""

    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _record_int(record: dict[str, object], key: str) -> int:
    """기록 보고에서 수 하나 — 없거나 수가 아니면 0(이 값들은 보고에만 쓰이고 판정은 문장으로 한다)."""

    value = record.get(key)
    return value if isinstance(value, int) else 0


def _record_lines(record: dict[str, object], key: str) -> list[str]:
    """기록 보고에서 문장 목록 — 없으면 빈 목록."""

    value = record.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


def ledger_floor(observed: int) -> Floor:
    """이 원장의 하한 — 표에 실린 하한 수(값 + 근거)."""

    return Floor("원장에 실린 하한", observed, _MIN_FLOORS, why=_WHY_MIN_FLOORS)


def coverage_floors(ledger: Ledger | None = None) -> list[Floor]:
    """이 원장의 탐지력 하한 — ① 다른 층에서 본 하한 수(자가 참조면 아무것도 말하지 않는다) ② 표 밖 스캔이 본 후보 수."""

    canvas = ledger.canvas if ledger is not None else _MIN_FLOORS
    scanned = len(ledger.candidates) if ledger is not None else _MIN_CANDIDATES
    return [
        ledger_floor(canvas),
        Floor("하한 후보 스캔", scanned, _MIN_CANDIDATES, why=_WHY_MIN_CANDIDATES),
    ]


def judged_floors(ledger: Ledger) -> tuple[tuple[str, str, int, str], ...]:
    """표가 **지금 판단하는 것** — (층, 하한 이름, 하한값, 근거). 관측(`observed`)은 여기 없다.

    기록과 대조하는 것이 이 목록이다. 관측을 대조하면 기록이 매 회차 낡는다 — 표가 말하는 판단(무엇을 몇 개로 정했고
    왜인가)과 그날의 관측은 다른 것이고, 관측은 이미 게이트의 추이와 각 층의 게이트가 본다.
    """

    return tuple((row.name, floor.label, floor.minimum, floor.why) for row in ledger.rows for floor in row.floors)


def read_record(path: Path = RECORD) -> dict[str, object] | None:
    """하한 기록을 읽는다 — 없거나 깨졌으면 None(호출자가 실패로 처리한다)."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def recorded_floors(stored: dict[str, object] | None) -> dict[tuple[str, str], tuple[int, str]]:
    """기록에 담긴 판단 — (층, 하한 이름) → (하한값, 근거).

    층 이름까지 키에 넣는 까닭은 “어느 층의 어느 하한이 사라졌나” 를 말할 수 있어야 하기 때문이다(이름만 보면 다른 층의
    같은 이름과 묶인다).
    """

    if stored is None:
        return {}
    items = stored.get("floors")
    if not isinstance(items, list):
        return {}
    return {
        (str(item.get("layer")), str(item.get("label"))): (int(item.get("minimum", 0)), str(item.get("why", "")))
        for item in items
        if isinstance(item, dict)
    }


def recorded_observations(stored: dict[str, object] | None) -> dict[tuple[str, str], int]:
    """기록에 담긴 **그때의 관측** — 판정에 안 쓴다. 오직 이동을 보고하려고 읽는다."""

    if stored is None:
        return {}
    items = stored.get("floors")
    if not isinstance(items, list):
        return {}
    return {
        (str(item.get("layer")), str(item.get("label"))): int(item.get("observed", 0))
        for item in items
        if isinstance(item, dict)
    }


def record_moves(ledger: Ledger, stored: dict[str, object] | None) -> tuple[str, ...]:
    """기록된 관측 대비 움직임 — **실패가 아니라 보고**다(각 층의 게이트가 판정하고, 원장은 목록의 승인을 맡는다)."""

    before = recorded_observations(stored)
    moves: list[str] = []
    for row in ledger.rows:
        for floor in row.floors:
            was = before.get((row.name, floor.label))
            if was is None or was == floor.observed:
                continue
            arrow = "▲" if floor.observed > was else "▼"
            moves.append(f"{row.name} · {floor.label} {was} → {floor.observed} {arrow}")
    return tuple(moves)


@dataclass(frozen=True, slots=True)
class RecordChanges:
    """기록과 지금 표의 차이 — **판단의 이동**만 담는다(관측은 `record_moves` 가 보고로 낸다).

    넷을 나눠 담는 까닭은 실패 문장이 달라야 하기 때문이다: **내려간 하한값**(승인 없는 하향) · **사라진 하한**(지운 것도
    결정이다) · **기록에 없는 새 하한**(승인된 목록이 지금을 대표하지 않는다) · **근거만 바뀐 하한**(같은 값이라도 판단이다).
    """

    lowered: tuple[tuple[str, str, int, int], ...] = ()
    vanished: tuple[tuple[str, str], ...] = ()
    added: tuple[tuple[str, str], ...] = ()
    reasons: tuple[tuple[str, str], ...] = ()
    # 층 단위 이동 — **하나의 결정이 열두 문장으로 흩어지지 않게** 한다. 층 하나가 roster 에서 빠지면 그 층의
    # 하한이 한꺼번에 사라지는데, 그것을 하한 개수만큼의 실패 문장으로 내면 읽는 사람이 결정을 다시 세어야 한다.
    vanished_layers: tuple[str, ...] = ()
    added_layers: tuple[str, ...] = ()
    # 층 **이름이 바뀐 것으로 보이는** 짝 — 사라진 층과 새 층이 **같은 하한 이름**을 들고 있으면, 그것은 두 결정
    # (하나를 빼고 하나를 더함)이 아니라 하나(이름을 바꿈)일 수 있다. 원장은 층의 동일성을 모르므로 단정하지 않고
    # **짝과 근거(그대로인 하한 이름들)** 를 남긴다 — 읽는 사람이 그 근거를 보고 판단한다.
    renamed_layers: tuple[tuple[str, str, tuple[str, ...]], ...] = ()

    @property
    def judged_moves(self) -> int:
        """판단이 움직인 하한 수 — 0 이어야 기록이 지금을 대표한다."""

        return len(self.lowered) + len(self.vanished) + len(self.added) + len(self.reasons)

    @property
    def layer_moves(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(표에서 사라진 층, 표에 새로 생긴 층)."""

        return self.vanished_layers, self.added_layers

    def partial(self, keys: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
        """층이 통째로 움직인 것이 **아닌** 하한만 — 층 단위 문장과 하한 단위 문장이 같은 결정을 두 번 말하지 않게."""

        whole = set(self.vanished_layers) | set(self.added_layers)
        return tuple(key for key in keys if key[0] not in whole)


def record_changes(judged: Sequence[tuple[str, str, int, str]], stored: dict[str, object] | None) -> RecordChanges:
    """기록 대비 판단의 이동 — 관측(`observed`)은 보지 않는다.

    관측을 대조하면 기록이 매 회차 잡음으로 낡고, 기록이 낡는 진짜 순간(하한을 지우거나 내리는 순간)이 그 잡음에 묻힌다.
    """

    stored_map = recorded_floors(stored)
    fresh = {(layer, label): (minimum, why) for layer, label, minimum, why in judged}
    shared = sorted(set(stored_map) & set(fresh))
    stored_layers = {layer for layer, _label in stored_map}
    fresh_layers = {layer for layer, _label in fresh}
    return RecordChanges(
        renamed_layers=renamed_layers(
            stored_map, fresh, vanished_layers=stored_layers - fresh_layers, added_layers=fresh_layers - stored_layers
        ),
        lowered=tuple(
            (layer, label, stored_map[(layer, label)][0], fresh[(layer, label)][0])
            for layer, label in shared
            if fresh[(layer, label)][0] < stored_map[(layer, label)][0]
        ),
        vanished=tuple(sorted(key for key in stored_map if key not in fresh)),
        added=tuple(sorted(key for key in fresh if key not in stored_map)),
        reasons=tuple(
            (layer, label) for layer, label in shared if fresh[(layer, label)][1] != stored_map[(layer, label)][1]
        ),
        vanished_layers=tuple(sorted(stored_layers - fresh_layers)),
        added_layers=tuple(sorted(fresh_layers - stored_layers)),
    )


def renamed_layers(
    stored_map: dict[tuple[str, str], tuple[int, str]],
    fresh: dict[tuple[str, str], tuple[int, str]],
    *,
    vanished_layers: set[str],
    added_layers: set[str],
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """이름이 바뀐 것으로 **보이는** 층 짝 — 하한 이름 집합이 **그대로**인 경우만 짝지어 말한다.

    일부만 겹치는 경우는 짝으로 말하지 않는다: 그것은 이름 변경일 수도, 층이 갈라진 것일 수도 있고, 원장이 층의
    동일성을 아는 것이 아니므로 추측을 사실처럼 말하지 않는다(겹침이 전부일 때만 “그대로” 라고 말할 수 있다).
    새 층 하나를 두 옛 층이 차지할 수는 없으므로 먼저 온 짝이 가져가고, 나머지는 사라진 층·새 층으로 남는다.
    """

    labels_by_layer: dict[str, set[str]] = {}
    for layer, label in stored_map:
        labels_by_layer.setdefault(layer, set()).add(label)
    fresh_labels: dict[str, set[str]] = {}
    for layer, label in fresh:
        fresh_labels.setdefault(layer, set()).add(label)
    pairs: list[tuple[str, str, tuple[str, ...]]] = []
    claimed: set[str] = set()
    for old in sorted(vanished_layers):
        old_labels = labels_by_layer.get(old, set())
        if not old_labels:
            continue
        for new in sorted(added_layers - claimed):
            if fresh_labels.get(new) == old_labels:
                pairs.append((old, new, tuple(sorted(old_labels))))
                claimed.add(new)
                break
    return tuple(pairs)


def _by_layer(keys: Sequence[tuple[str, str]]) -> str:
    """(층, 이름) 목록을 층별로 묶어 한 줄로 — 층 하나의 결정이 하한 개수만큼의 문장으로 흩어지지 않게."""

    grouped: dict[str, list[str]] = {}
    for layer, label in keys:
        grouped.setdefault(layer, []).append(label)
    return "; ".join(f"{layer}: {', '.join(labels)}" for layer, labels in sorted(grouped.items()))


def _count_by_layer(keys: Sequence[tuple[str, str]]) -> str:
    """층별 하한 개수 — 층 하나가 통째로 움직였을 때 “몇 개가 함께 갔나” 를 말한다."""

    grouped: dict[str, int] = {}
    for layer, _label in keys:
        grouped[layer] = grouped.get(layer, 0) + 1
    return "; ".join(f"{layer} {count}개" for layer, count in sorted(grouped.items()))


def rename_claim_problems(stored: dict[str, object] | None) -> list[str]:
    """기록이 **스스로** 모순되지 않는가 — 이름 변경 이력은 기록 안에서 자기 자리를 갖아야 한다.

    하한 기록의 `floors` 는 **지금** 이름을 담으므로 그것만으로는 “이 하한들이 처음부터 이 층에 있었다” 로 읽힌다.
    `renames` 가 그 사실을 따로 담는 이상, 기록은 자기 안에서 그 사실과 맞아야 한다: 새 이름은 기록의 하한에 있고
    옛 이름은 거기에 없어야 한다. 그렇지 않으면 기록은 이력과 하한을 한꺼번에 들고 있으면서 서로 다른 말을 하는 것이다.
    “같은 새 이름으로 두 번 바뀌었다” 도 모순이다(두 층이 한 이름으로 합쳐졌다는 말이 되는데, 그러면 그 사실을 적어야 한다).
    """

    facts = recorded_renames(stored)
    if not facts:
        return []
    layers = {layer for layer, _label in recorded_floors(stored)}
    froms = {old for old, _new, _labels, _on in facts}
    problems: list[str] = []
    for old, new, _labels, on in facts:
        stamp = f"({old} → {new}, {on or '날짜 없음'})"
        if new not in layers and new not in froms:
            problems.append(
                f"기록이 층 이름 변경을 주장하는데 {stamp} 의 새 이름 `{new}` 은 기록의 하한에도 없고 또 바뀐 것도 아니다 "
                "— 그 하한은 기록에서 어느 층의 것인가"
            )
        if old in layers:
            problems.append(
                f"기록이 {stamp} 이름을 바꿨다고 하면서 옛 이름 `{old}` 의 하한도 그대로 들고 있다 — 둘 중 하나는 틀렸다"
            )
    seen: set[str] = set()
    for _old, new, _labels, _on in facts:
        if new in seen:
            problems.append(
                f"기록이 같은 새 이름 `{new}` 으로 두 번 바뀌었다고 말한다 — 두 층이 한 이름으로 모우면 그 사실을 적어야 한다"
            )
        seen.add(new)
    for start in sorted(froms):
        walk, seen_chain, cursor = start, set(), start
        while cursor in froms:
            nxt = next(new for old, new, _labels, _on in facts if old == cursor)
            if nxt in seen_chain or nxt == start:
                problems.append(
                    f"기록의 이름 변경 이력이 고리를 이룬다({walk} 에서 시작해 `{nxt}` 로 돌아온다) — 층 이름이 제자리로 도는 것은 "
                    "이름 변경이 아니라 다른 사실이다"
                )
                break
            seen_chain.add(cursor)
            cursor = nxt
    return problems


def record_problems(
    judged: Sequence[tuple[str, str, int, str]],
    stored: dict[str, object] | None,
    *,
    record: Path = RECORD,
    roster: Sequence[str] = (),
) -> list[str]:
    """기록된 **판단**이 지금 표와 같은가 — 사라진·내려간·근거 바뀜·새 하한을 모두 실패로 만든다.

    문장은 **층 단위로 묶는다**: 층 하나가 roster 에서 빠지면 그 층의 하한이 한꺼번에 사라지는데(예: 하한 6개),
    그것을 하한 개수만큼의 문장으로 내면 읽는 사람이 하나의 결정을 다시 세어야 한다. 그래서 층이 통째로 움직인
    것과 층 안의 일부만 움직인 것을 나눠 말하고, **그 층이 아직 카나리아 roster 에 있는가**까지 물어 “그 층이
    빠진 결정” 과 “표가 그 층을 읽지 못한 결함” 을 구분한다 — 같은 문장이 되면 둘은 같은 초록으로 보인다.
    """

    if stored is None:
        return [
            f"하한 기록이 없거나 읽히지 않는다({_display(record)}) — 사람이 승인한 목록이 없으면 “내려도 되는 하한인가” 를 "
            "물을 자리가 없다: `--record --method` 로 기록해야 한다"
        ]
    problems: list[str] = []
    if not str(stored.get("method", "")).strip():
        problems.append("하한 기록에 승인 문장(`method`)이 없다 — 무엇을 보고 승인했는지 없는 기록은 기록이 아니다")
    if not str(stored.get("recorded_on", "")).strip():
        problems.append("하한 기록에 날짜(`recorded_on`)가 없다 — 언제의 판단인지 모르는 하한은 낡았는지도 알 수 없다")
    if not recorded_floors(stored):
        return [
            *problems,
            "하한 기록에 `floors` 가 없다 — 기록이 무엇을 승인했는지 말하지 않는다(`--record --method` 로 다시 기록)",
        ]
    problems.extend(rename_claim_problems(stored))
    problems.extend(deadline_move_problems(stored))  # 기록이 자기 기한 이력과 맞는가(면제)
    changes = record_changes(judged, stored)
    lowered, reasons = changes.lowered, changes.reasons
    vanished = changes.partial(changes.vanished)
    added = changes.partial(changes.added)
    vanished_layers, added_layers = changes.layer_moves
    known = set(roster)
    # 이름이 바뀐 것으로 보이는 짝은 **roster 에서도 빠진 층**에만 적용한다: 아직 roster 에 있는 층은 결정이 아니라
    # 표가 읽지 못한 결함이므로, 이름 변경이라는 말로 덮으면 그 결함이 조용해진다.
    renames = tuple(pair for pair in changes.renamed_layers if pair[0] not in known)
    renamed_old = {old for old, _new, _labels in renames}
    renamed_new = {new for _old, new, _labels in renames}
    if vanished_layers:
        # 층 하나가 통째로 사라졌다 — 그 층이 아직 roster 에 있으면 그것은 결정이 아니라 결함이다(표가 읽지 못했다).
        still_alive = [layer for layer in vanished_layers if layer in known]
        left_roster = [layer for layer in vanished_layers if layer not in known and layer not in renamed_old]
        if still_alive:
            live_floors = tuple(key for key in changes.vanished if key[0] in set(still_alive))
            problems.append(
                f"기록의 층 {', '.join(still_alive)}(하한 {_count_by_layer(live_floors)})의 하한이 통째로 표에서 사라졌다 — 그 층은 **아직 카나리아 roster 에 "
                "있다**: 표가 그 층을 읽지 못한 것이다(읽지 못한 이유는 표의 다른 문장에 있다). 그 층이 빠진 결정이라면 "
                "roster 에서도 빼라"
            )
        if left_roster:
            gone_floors = tuple(key for key in changes.vanished if key[0] in set(left_roster))
            problems.append(
                f"기록의 층 {', '.join(left_roster)}(하한 {_count_by_layer(gone_floors)})가 roster 에서도 표에서도 "
                "사라졌다 — 층을 빼는 것도 결정이다: `--record --method` 로 그 결정을 남겨라"
            )
    new_layers = [layer for layer in added_layers if layer not in renamed_new]
    if new_layers:
        new_floors = tuple(key for key in changes.added if key[0] in set(new_layers))
        problems.append(
            f"기록에 없는 새 층 {', '.join(new_layers)}(하한 {_count_by_layer(new_floors)})이 표에 들어왔다 — 층 이름이 "
            "바뀐 것이라면 그 결정을, 새 층이라면 그 층의 하한을 `--record --method` 로 기록하라(기록은 승인된 목록이다)"
        )
    for old, new, shared in renames:
        # 하나의 결정일 수 있는 사건은 한 문장으로 — 다만 **단정하지 않는다**(짝과 근거만 내고 판단은 사람에게 남긴다).
        problems.append(
            f"기록의 층 {old} 가 표에서 {new} 로 **이름만 바뀐 것으로 보인다**(하한 이름 {len(shared)}개가 그대로다: "
            f"{', '.join(shared)}) — 층 이름을 바꾸는 것도 결정이다: 그 결정이라면 `--record --method` 로 기록하라. "
            "이름이 바뀐 것이 아니라면 왜 사라지고 왜 생겼는지를 남겨라(원장은 층의 동일성을 모른다)"
        )
    judged_layers = {layer for layer, _label, _minimum, _why in judged}
    for old, _new, _labels, on in recorded_renames(stored):
        # 기록이 **이미 승인한** 이름 변경 — 옛 이름이 표에 돌아오면 그것도 결정이므로 다시 승인받아야 한다.
        if old in judged_layers:
            problems.append(
                f"기록이 층 {old} 를 다른 이름으로 바꿨다고 승인했는데({on or '날짜 없음'}) 표에 옛 이름 `{old}` 가 돌아왔다 — "
                "되돌리는 것도 결정이다: `--record --method` 로 그 결정을 남겨라"
            )
    if lowered:
        by_layer = "; ".join(f"{layer}: {label} {was} → {now}" for layer, label, was, now in lowered)
        problems.append(
            f"기록보다 **내려간 하한**이 있다({by_layer}) — 하한을 내리는 것은 판단이므로 승인 문장과 함께 다시 기록해야 "
            "한다(`--record --method`): 지금은 그 판단이 어디에도 남지 않는다"
        )
    if vanished:
        problems.append(
            f"기록에서 사라진 하한이 있다(층 {_by_layer(vanished)}) — 그 층은 표에 남아 있는데 하한만 빠졌다: 지웠으면 "
            "`--record --method` 로 다시 기록하라(면죄부는 지운다)"
        )
    if added:
        problems.append(
            f"기록에 없는 하한이 생겼다(층 {_by_layer(added)}) — 그 층은 이미 기록에 있는데 하한만 새로 들였다: 승인된 "
            "목록이 지금을 대표하지 않는다(`--record --method` 로 기록하라)"
        )
    if reasons:
        problems.append(
            f"기록과 근거가 바뀐 하한이 있다(층 {_by_layer(reasons)}) — 근거가 바뀌면 그것은 다른 판단이다"
            "(`--record --method` 로 다시 기록하라)"
        )
    return problems


def record_raised(ledger: Ledger, stored: dict[str, object] | None) -> tuple[str, ...]:
    """기록보다 **올라간** 하한 — 실패가 아니라 보고다(안전한 쪽으로 틀리는 것을 실패로 만들면 기록이 잡음이 된다)."""

    before = recorded_floors(stored)
    raised: list[str] = []
    for row in ledger.rows:
        for floor in row.floors:
            was = before.get((row.name, floor.label))
            if was is None or floor.minimum <= was[0]:
                continue
            raised.append(f"{row.name} · {floor.label} {was[0]} → {floor.minimum}")
    return tuple(raised)


def recorded_renames(stored: dict[str, object] | None) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    """기록이 **사실로** 남긴 층 이름 변경 이력 — (옛 이름, 새 이름, 그대로인 하한 이름들, 승인 날짜).

    하한 기록의 `floors` 는 **지금** 이름을 담으므로, 그것만으로는 그 하한들이 처음부터 이 층에 있었던 것처럼 보인다
    — 이름 변경이 있었다는 사실 자체가 사라진다(층 q 의 하한이 그대로 r 로 옮겨갔는데도 다음 회차는 q 를 모른다).
    그래서 기록은 그 사실을 따로 담고, 다음 기록으로 **이어진다**.
    """

    value = stored.get("renames") if stored else None
    if not isinstance(value, list):
        return ()
    facts: list[tuple[str, str, tuple[str, ...], str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        old, new = str(item.get("from", "")), str(item.get("to", ""))
        if not old.strip() or not new.strip():
            continue
        shared = item.get("shared")
        labels = tuple(str(label) for label in shared) if isinstance(shared, list) else ()
        facts.append((old, new, labels, str(item.get("on", ""))))
    return tuple(facts)


def recorded_deadline_moves(stored: dict[str, object] | None) -> tuple[tuple[str, str, str, str], ...]:
    """기록이 **사실로** 남긴 면제 기한 이동 이력 — (이름, 옛 기한, 새 기한, 승인 날짜).

    `outside.declared` 는 **지금** 기한만 담으므로, 그것만으로는 그 면제가 몇 번 미뤄졌는지 알 수 없다 — 한 번
    미룬 면제도, 세 번 미룬 면제도 같은 줄로 읽히고 검토는 매번 “첫 번째” 처럼 보인다(이름 변경이 `renames` 로
    사실이 된 것과 같은 자리다). 그래서 기한이 움직인 순간을 **기록이 스스로 적어 이어 간다** — 사람이 적는 것이
    아니라 대조가 찾아낸 이동이므로, 미룬 횟수는 주장이 아니라 계산된 사실이다.
    """

    value = _record_dict(stored or {}, "outside").get("deadline_moves")
    if not isinstance(value, list):
        return ()
    facts: list[tuple[str, str, str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name, was, now = str(item.get("name", "")), str(item.get("from", "")), str(item.get("to", ""))
        if not name.strip() or not was.strip() or not now.strip():
            continue
        facts.append((name, was, now, str(item.get("on", ""))))
    return tuple(facts)


def deadline_move_problems(stored: dict[str, object] | None) -> list[str]:
    """기록이 **자기 기한 이력과 모순되지 않는가** — 이력은 이어져야 하고 지금 기한과 맞아야 한다.

    이름 변경 이력과 같은 규칙이다: 이력의 마지막 기한은 지금 승인된 기한이어야 하고(아니면 기록이 자기 이력과
    다른 말을 한다), 이어지는 고리는 `to` 와 `from` 이 맞물려야 하며, 한 면제가 같은 기한에서 두 번 출발할 수 없다
    (손으로 고친 이력은 여기서 멈춘다 — 이력은 “몇 번 미뤘나” 를 세는 근거이므로 틀린 이력은 틀린 수를 낳는다).
    그리고 약속을 담은 기록은 **이력 칸도 담아야 한다**: 칸이 없는 기록에서는 “한 번도 미룬 적 없다” 와 “이력을 적지
    않았다” 가 같은 줄로 읽힌다(이름만 담긴 기록에게 “기한을 물을 자리가 없다” 고 말하는 것과 같은 자리다).
    """

    problems: list[str] = []
    if recorded_outside(stored).shape == OUTSIDE_SHAPE_FULL and not isinstance(
        _record_dict(stored or {}, "outside").get("deadline_moves"), list
    ):
        problems.append(
            "기록이 면제의 **기한 이동 이력**(`outside.deadline_moves`)을 담고 있지 않다 — 그 사실이 없으면 “한 번도 "
            "미룬 적 없다” 와 “이력을 적지 않았다” 가 같은 줄로 읽히고, 몇 번째 재검토인지 셀 수 없다: "
            "`--record --method` 로 이력 칸까지 담아 다시 기록하라"
        )
    facts = recorded_deadline_moves(stored)
    if not facts:
        return problems
    promised = recorded_outside(stored).promises
    chains: dict[str, list[tuple[str, str, str]]] = {}
    for name, was, now, on in facts:
        chains.setdefault(name, []).append((was, now, on))
    for name, steps in sorted(chains.items()):
        for index, (was, now, on) in enumerate(steps):
            start, end = _as_day(was), _as_day(now)
            stamp = f"({name}, {was} → {now}, {on or '날짜 없음'})"
            if start is None or end is None:
                problems.append(f"기록의 기한 이동 이력에 날짜로 읽히지 않는 것이 있다: {stamp}")
                continue
            if end <= start:
                problems.append(
                    f"기록의 기한 이동 이력에 제자리거나 되돌아간 이동이 있다: {stamp} — 이동이 아니라 다른 사실이다"
                )
            if index and steps[index - 1][1] != was:
                problems.append(
                    f"기록의 기한 이동 이력이 이어지지 않는다: {stamp} 앞의 기한이 {steps[index - 1][1]} 이다 — "
                    "이력은 옛 기한에서 새 기한으로 이어져야 한다"
                )
        current = promised.get(name)
        if current is not None and steps[-1][1] != current[3]:
            problems.append(
                f"기록이 {name} 의 기한을 마지막으로 {steps[-1][1]} 로 옮겼다고 하면서 지금은 {current[3]} 을 승인한다 — "
                "둘 중 하나는 틀렸다(기한 이동은 기록을 지나야 한다)"
            )
    return problems


def record_refusals(ledger: Ledger) -> tuple[str, ...]:
    """이 실행을 기록하면 **지워지는 사실** — 그래서 기록을 거부하는 이유.

    `--record` 는 이미 두 가지를 거부한다: 승인 문장이 없으면 쓰지 않고(무엇을 보고 승인했는지 없는 기록은 기록이
    아니다), 표가 실패한 실행은 쓰지 않는다(기록은 통과의 승인이다). 셋째는 성질이 다르다 — **기록이 사실을 지우는**
    경우다: 확인일 없이 기한만 미룬 면제를 그대로 기록하면 옛 기한이 새 기한으로 덮여 “검토 없이 미뤘다” 는 사실
    자체가 사라진다(면죄부가 스스로를 씻는다). 그래서 그 사실을 가진 실행은 기록하지 않고, 무엇을 적거나 되돌려야
    하는지 말한다 — 지우는 기록을 막는 자리는 게이트의 기준 기록에도 이미 있다.
    """

    bare = _record_dict(ledger.record, "outside").get("bare_deferred")
    names = [
        str(item.get("name"))
        for item in (bare if isinstance(bare, list) else [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    if not names:
        return ()
    return (
        f"기록하지 않았다 — 확인일 없이 기한만 미룬 면제가 있다: {', '.join(sorted(names))}. 그대로 기록하면 "
        "옛 기한이 새 기한으로 덮여 “검토 없이 미뤘다” 는 사실이 사라진다: 언제 다시 본 것인지(`reviewed_on`)를 "
        "함께 적거나 기한을 되돌려라",
    )


def record_payload(
    ledger: Ledger,
    probe: Probe,
    *,
    method: str,
    on: str,
    previous: dict[str, object] | None = None,
) -> dict[str, object]:
    """기록의 내용 — **판단과 관측을 함께 남긴다**(관측은 판정이 아니라 다음 회차의 보고 기준이다).

    소요 시간은 담지 않는다: 기록은 판단이지 그날의 속도가 아니다.
    **이름 변경 이력**은 두 곳에서 모은다: 앞 기록이 이미 승인한 사실(새 이름이 표에 살아 있는 것만)과, 이번 대조가
    찾아낸 짝(옛 기록의 하한과 지금 표가 하한 이름 집합을 그대로 공유하는 층)이다 — 기록을 쓰는 순간이 곧 그
    이름으로 바꾸겠다는 승인이므로, 사실을 적지 않을 이유가 없다.
    """

    before = recorded_floors(previous)
    fresh = {(layer, label): (minimum, why) for layer, label, minimum, why in judged_floors(ledger)}
    names = {layer for layer, _label in fresh}
    stored_names = {layer for layer, _label in before}
    # 앞 기록이 승인한 사실은 **그대로 이어진다** — 중간에 또 이름이 바뀌면 그 사실의 새 이름은 지금 층이 아니지만
    # (p → r → s), 그 사실이 사라지면 `floors` 는 그 하한들이 처음부터 s 에 있었던 것처럼 남는다. 판정(모순 검사)이
    # “이어진 고리인가” 를 보므로, 이어지는 사실을 여기서 지우지 않는다.
    history: list[tuple[str, str, tuple[str, ...], str]] = list(recorded_renames(previous))
    known = {fact[1] for fact in history}
    for old, new, labels in renamed_layers(
        before,
        fresh,
        vanished_layers=stored_names - names,
        added_layers=names - stored_names,
    ):
        if new not in known:
            history.append((old, new, labels, on))
            known.add(new)
    # 면제의 **기한 이동도 사실로 이어진다** — 앞 기록이 승인한 이력은 그대로 두고, 이번에 움직인 기한을 덧붙인다.
    # (확인일 없이 기한만 미룬 것은 `record_refusals` 가 기록을 거부하므로 여기까지 오지 않는다 — 지우는 기록을 막는다.)
    was_outside = recorded_outside(previous)
    moves: list[tuple[str, str, str, str]] = list(recorded_deadline_moves(previous))
    for item in ledger.outside:
        was = was_outside.promises.get(item.name)
        if was is None or was[3] == item.review_by:
            continue
        was_due, now_due = _as_day(was[3]), _as_day(item.review_by)
        was_review, now_review = _as_day(was[2]), _as_day(item.reviewed_on)
        if was_due is None or now_due is None:
            continue  # 못 읽는 날짜는 표가 문장으로 낸다(그 실행은 기록되지 않는다)
        refreshed = was_review is not None and now_review is not None and now_review > was_review
        if now_due > was_due and not refreshed:
            continue  # 검토 없이 미룬 것은 사실로 적지 않는다(그리고 `record_refusals` 가 기록을 거부한다)
        moves.append((item.name, was[3], item.review_by, on))
    return {
        "command": ["python", "scripts/floor_ledger.py", "--record"],
        "recorded_on": on,
        "method": method,
        "layers": len(ledger.rows),
        "renames": [
            {"from": old, "to": new, "shared": list(labels), "on": declared_on}
            for old, new, labels, declared_on in history
        ],
        "counts": {
            "layers": len(ledger.rows),
            "floors": ledger.floors,
            "canvas": ledger.canvas,
            "candidates": len(ledger.candidates),
        },
        "floors": [
            {**floor.as_mapping(), "layer": row.name, "kind": row.kind, "source": row.source}
            for row in ledger.rows
            for floor in row.floors
        ],
        # 면제는 **이름만이 아니라 약속까지** 담는다: 이름만 담으면 다음 기록이 “기한을 미뤘다” 를 물을 자리가 없고,
        # 확인일이 없으면 “검토 없이 미뤘다” 를 물을 자리가 없다. 창도 함께 담는다(창을 넓히는 것도 결정이다).
        "outside": {
            "scanned": len(ledger.candidates),
            "review_window": {"days": _MAX_REVIEW_WINDOW_DAYS, "why": _WHY_MAX_REVIEW_WINDOW},
            "declared": [item.as_mapping() for item in ledger.outside],
            # 기한이 움직인 순간 — 기록이 스스로 적어 이어 간다(대조가 찾아낸 이동이다).
            "deadline_moves": [
                {"name": name, "from": was, "to": now, "on": declared_on} for name, was, now, declared_on in moves
            ],
        },
        "probe": probe.as_mapping(),
        "verdict": "PASS",
    }


def write_record(path: Path, payload: dict[str, object]) -> None:
    """기록을 저장소에 남긴다(부모 디렉터리는 만든다)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_report(
    record: Path,
    stored: dict[str, object] | None,
    ledger: Ledger,
    issues: list[str],
    *,
    renamed: Sequence[tuple[str, str]] = (),
) -> dict[str, object]:
    """기록의 상태를 JSON 보고에 싣는다 — 게이트와 리뷰가 읽는 출력에서 “왜 실패했나” 를 읽을 수 있어야 한다."""

    changes = record_changes(judged_floors(ledger), stored)
    recorded = recorded_outside(stored)
    paired_names = {name for pair in renamed for name in pair}
    moved, deferred, bare = _outside_moves(ledger.outside, recorded, paired_names)
    if recorded.shape != OUTSIDE_SHAPE_FULL:  # 약속을 모르는 기록에서는 이동을 물을 수 없다
        moved, deferred, bare = (), (), ()
    return {
        "path": _display(record),
        "present": stored is not None,
        "recorded_on": str(stored.get("recorded_on", "")) if stored else "",
        "method": str(stored.get("method", "")) if stored else "",
        "floors": len(recorded_floors(stored)),
        "judged": len(judged_floors(ledger)),
        "lowered": len(changes.lowered),
        "vanished": len(changes.vanished),
        "added": len(changes.added),
        "reasons": len(changes.reasons),
        "vanished_layers": list(changes.vanished_layers),
        "added_layers": list(changes.added_layers),
        "renamed_layers": [
            {"from": old, "to": new, "shared": list(labels)} for old, new, labels in changes.renamed_layers
        ],
        "renames": [
            {"from": old, "to": new, "shared": list(labels), "on": on}
            for old, new, labels, on in recorded_renames(stored)
        ],
        "moves": list(record_moves(ledger, stored)),
        "raised": list(record_raised(ledger, stored)),
        # 면제 — 기록이 승인한 면제와 지금 표의 면제를 같은 자리에서 읽을 수 있게 싣는다.
        "outside": {
            "declared": len(ledger.outside),
            "recorded": len(recorded.entries),
            "shape": recorded.shape,
            "window_days": _MAX_REVIEW_WINDOW_DAYS,
            "recorded_window_days": recorded.window_days,
            "changed": list(moved),
            # 검토한 연장과 검토 없는 연장은 **다른 사실**이다 — 앞은 결정(승인이 필요하다), 뒤는 기록을 거부하는 이유다.
            "deferred": [{"name": name, "from": was, "to": now} for name, was, now in deferred],
            "bare_deferred": [{"name": name, "from": was, "to": now} for name, was, now in bare],
            "reviewed": list(outside_reviewed(ledger.outside, recorded, paired=paired_names)),
            "pulled": list(outside_pulled(ledger.outside, recorded, paired=paired_names)),
            "renamed": [{"from": old, "to": new} for old, new in renamed],
            "deadline_moves": [
                {"name": name, "from": was, "to": now, "on": declared_on}
                for name, was, now, declared_on in recorded_deadline_moves(stored)
            ],
        },
        "problems": list(issues),
    }


def read_floor_rows(name: str, canary: ModuleType) -> tuple[LayerRow, str]:
    """한 층의 하한과 승인을 읽는다 — (행, 문제). 읽지 못한 이유를 함께 돌려준다(추측하지 않는다)."""

    recorded = str(canary.ARTIFACT_FLOORS.get(name, ""))
    # 스크립트 이름을 원장이 따로 짐작하지 않는다 — 카나리아가 아는 대응을 그대로 쓴다(둘이 갈라지면 승인 날짜를 못 읽는다).
    source = recorded or _display(canary.script_for(name))
    if recorded:
        approval, payload_note = _record_approval(REPO_ROOT / recorded)
        try:
            recorded_floors = canary.artifact_floors(name)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - 못 읽은 이유도 판정이다
            recorded_floors = None
            payload_note = f"기록을 읽는 중 예외: {type(exc).__name__}: {exc}"
        if recorded_floors is None:
            return (
                LayerRow(name, KIND_RECORDED, source, (), approval, None, note=payload_note),
                f"기록 artifact 를 읽지 못했다({source}) — 이 원장은 그 층의 하한을 말할 수 없다",
            )
        floors = tuple(recorded_floors)
        return LayerRow(name, KIND_RECORDED, source, floors, approval, commit_of(REPO_ROOT / source), payload_note), ""
    try:
        module = canary.load_harness(name)
        floors = tuple(canary.harness_floors(name, module))
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - 못 읽은 이유도 판정이다
        return (
            LayerRow(name, KIND_MEASURED, source, (), {}, None, note="하한을 읽지 못했다"),
            f"{name} 의 하한을 읽지 못했다: {type(exc).__name__}: {exc}",
        )
    return LayerRow(name, KIND_MEASURED, source, floors, {}, commit_of(REPO_ROOT / source)), ""


def _record_approval(path: Path) -> tuple[dict[str, str], str]:
    """기록 artifact 의 승인 문장·날짜와, 그 사실에 대한 한 줄 설명."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "기록을 읽지 못했다"
    if not isinstance(payload, dict):
        return {}, "기록이 객체가 아니다"
    approval = {key: str(payload[key]) for key in ("method", "recorded_on") if str(payload.get(key, "")).strip()}
    note = (
        "기록 artifact 의 승인 문장·날짜를 그대로 실었다"
        if approval
        else "기록 artifact 에 승인 문장이 없다(리뷰가 저장본과 새 측정을 대조한다)"
    )
    return approval, note


def build(*, evidence_dir: Path = EVIDENCE_DIR, record: Path | None = None) -> Ledger:
    """원장을 만든다 — roster 는 카나리아가 알고, 하한은 카나리아의 눈으로 읽는다.

    하한 기록도 이 실행의 대상이다(판단의 이동을 묻는다). 기록의 자리는 증거 디렉터리에서 파생되므로, 다른 자리를
    넘겨 돌리는 호출(시험)은 그 자리의 기록을 본다 — 저장소의 기록을 우연히 읽거나 쓰지 않는다.
    """

    started = time.monotonic()
    record_path = record if record is not None else evidence_dir / RECORD.name
    canary = load_canary()
    # 하한 기록도 **아는 자리**다: 원장이 스스로 읽으므로, 고아 기록으로 세면 자기 기록을 면죄부로 탓하게 된다.
    known = [REPO_ROOT / str(path) for path in canary.ARTIFACT_FLOORS.values()] + [record_path]
    readings = [read_floor_rows(str(name), canary) for name in canary.HARNESSES if str(name) != SELF_NAME]
    # 자기 하한을 **표의 마지막 행**으로 싣는다 — “이 원장은 몇 개를 보나” 가 표 밖에 있으면 읽는 사람이 못 본다.
    # 자기 하한은 다른 층을 보는 수(캔버스)를 재므로, 자기 자신을 세면 저절로 참이 된다 — 그래서 자기 행은 캔버스에 안 든다.
    canvas = sum(len(row.floors) for row, _ in readings)
    readings.append(
        (
            LayerRow(
                SELF_NAME,
                KIND_SELF,
                "scripts/floor_ledger.py",
                (ledger_floor(canvas),),
                {},
                commit_of(Path(__file__).resolve()),
                note="이 원장 자신이다 — 자기 하한은 스스로 판정하고, 카나리아도 같은 눈으로 본다",
            ),
            "",
        )
    )
    problems = [problem for row, read_problem in readings for problem in row_problems(row, read_problem)]
    orphans = orphan_records(evidence_dir, known)
    for orphan in orphans:
        problems.append(
            f"{orphan} 에 `floors` 가 있는데 어떤 harness 도 읽지 않는다 — 아무도 읽지 않는 하한 기록은 면죄부다"
        )
    # 표 밖 스캔 — 하한처럼 생긴 상수가 어떤 하한 목록에도 안 실렸는데 선언도 없으면 이름을 대고 실패한다.
    candidates = floor_candidates()
    wired = wired_constants(canary.script_for(str(name)) for name in canary.HARNESSES)
    covered = tuple(name for name in candidates if name in wired)
    # 면제(선언)는 **판단**이다 — 기록이 그것을 승인했는지도 함께 묻는다. 기록을 여기서 먼저 읽는 까닭은 “이름만 바뀐 것으로
    # 보이는가” 가 기록이 아는 약속을 근거로 서기 때문이다(그 판단을 기록 읽기 뒤로 미루면 같은 일을 두 번 세게 된다).
    stored = read_record(record_path)
    recorded_outside_state = recorded_outside(stored)
    renamed_outside = renamed_declarations(OUTSIDE, recorded_outside_state, candidates=candidates, wired=wired)
    problems.extend(outside_problems(candidates, wired, OUTSIDE, renamed=renamed_outside))
    # 자기 행의 하한은 **자기 층의 전체 하한 목록**이다(캔버스 하한 + 표 밖 스캔 하한) — 자기 행을 먼저 만들고
    # 그 수로 다시 만든다. 하나만 실으면 표가 자기 하한을 절반만 말한다(“하한이 몇 개인가” 가 표 밖에 남는다).
    first_pass = tuple(row for row, _ in readings)
    provisional = Ledger(first_pass, orphans, (), 0.0, candidates, covered, OUTSIDE)
    rows = tuple(
        replace(row, floors=tuple(coverage_floors(provisional))) if row.name == SELF_NAME else row for row in first_pass
    )
    ledger = Ledger(rows, orphans, (), 0.0, candidates, covered, OUTSIDE)
    problems.extend(floor_problems(coverage_floors(ledger)))
    # 기록 대조 — 기록이 없거나 읽히지 않아도 “없음” 을 통과로 삼키지 않는다(그 사실이 판정이다).
    # 기록 문제를 `problems` 에 **합치지 않는** 까닭은 기록을 만드는 실행(`--record`)이 그 문제 때문에 자기 기록을 못 쓰게
    # 되기 때문이다(자기가 없어서 자기를 못 만드는 고리). 대신 보고에 따로 실어 호출자가 판정에 합친다.
    # 층 생사를 묻는 자리에는 roster 를 넘긴다 — “그 층이 빠진 결정” 과 “표가 그 층을 읽지 못한 결함” 은 다른 문장이어야 한다.
    record_issues = record_problems(
        judged_floors(ledger),
        stored,
        record=record_path,
        roster=tuple(str(name) for name in canary.HARNESSES),
    )
    # 면제의 이동도 **판단의 이동**이다(하한과 같은 자리에서 묻는다) — 면제를 만들고·거두고·기한을 미루면 승인이 필요하다.
    record_issues.extend(outside_record_problems(OUTSIDE, recorded_outside_state, renamed=renamed_outside))
    report = record_report(record_path, stored, ledger, record_issues, renamed=renamed_outside)
    return Ledger(
        rows,
        orphans,
        tuple(problems),
        time.monotonic() - started,
        candidates,
        covered,
        OUTSIDE,
        report,
    )


def all_problems(ledger: Ledger) -> list[str]:
    """호출자가 보는 전체 문제 — 표의 문제 + 기록 문제(기록 문제도 **실패**다: 게이트·리뷰가 같은 판정을 본다)."""

    return [*ledger.problems, *_record_lines(ledger.record, "problems")]


def row_problems(row: LayerRow, read_problem: str) -> list[str]:
    """한 행의 문제 — 읽지 못한 행은 그 한 문장으로 끝내고, 읽은 행은 하한·근거·승인을 각각 묻는다."""

    if read_problem:
        return [read_problem]
    problems: list[str] = []
    if not row.floors:
        problems.append(f"{row.name} 에 하한이 없다 — 하한 없는 층은 빈손으로도 결과를 통과시킨다")
    for floor in row.floors:
        if not floor.why.strip():
            problems.append(
                f"{row.name} 의 하한 `{floor.label}` 에 근거가 없다 — 왜 그 값인지 물을 수 없는 하한은 "
                "내려도 되는지 판단할 수 없다"
            )
    if row.commit is None:
        problems.append(
            f"{row.name} 의 승인 날짜를 읽지 못했다({row.source} — git 없음 또는 추적되지 않는 근거): "
            "“언제 누가” 를 모르면서 아는 척하지 않는다"
        )
    return problems


def self_probe() -> Probe:
    """판정 규칙을 합성 입력으로 다시 물어본다 — **저장소를 읽지 않는다**(리뷰가 돌릴 수 있어야 한다)."""

    cases = Cases()
    floors = coverage_floors()
    # 자기 하한은 **둘**이다(다른 층에서 본 하한 수 + 표 밖 스캔이 본 후보 수) — 하나만 실으면 “이 원장은 몇 개를
    # 보나” 가 표 밖에 남고, 스캔이 깨져 0 을 봐도 아무도 묻지 않는다.
    cases.equal(
        "원장 자신의 하한이 둘이다(다른 층에서 본 하한 수 + 표 밖 스캔이 본 후보 수)",
        [floor.label for floor in coverage_floors()],
        ["원장에 실린 하한", "하한 후보 스캔"],
    )
    cases.check("하한에 근거가 기록돼 있다", all(floor.why.strip() for floor in floors))
    cases.check("하한이 지금 관측을 넘지 않는다", not floor_problems(floors))
    cases.check(
        "눈멀게 한 하한(관측 0)은 문다", bool(floor_problems([Floor("원장에 실린 하한", 0, _MIN_FLOORS, why="근거")]))
    )
    empty = Ledger((), (), (), 1.5).as_mapping(Probe(cases=0, failures=()))
    empty_counts = empty["counts"]
    cases.check(
        "counts 에 소요 시간을 넣지 않는다(추이에 그날의 속도가 섞이지 않게)",
        isinstance(empty_counts, dict) and "seconds" not in empty_counts,
    )
    cases.equal("소요 시간은 runtime 으로 뺀다", empty["runtime"], {"seconds": 1.5})
    # 행 판정 — 읽은 행·못 읽은 행·근거 없는 행·승인 못 읽은 행이 각각 다르게 판정돼야 한다.
    healthy = LayerRow("probe", KIND_MEASURED, "scripts/probe.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE)
    cases.equal("정상 행은 문제가 없다", row_problems(healthy, ""), [])
    cases.equal(
        "승인을 못 읽은 행은 실패한다(언제 누가 를 모르면서 아는 척하지 않는다)",
        len(row_problems(replace(healthy, commit=None), "")),
        1,
    )
    cases.equal(
        "근거 없는 하한은 실패한다",
        len(row_problems(replace(healthy, floors=(Floor("수", 3, 1, why="  "),)), "")),
        1,
    )
    cases.equal("하한이 없는 층은 실패한다", len(row_problems(replace(healthy, floors=()), "")), 1)
    cases.equal(
        "읽지 못한 행은 그 한 문장으로 끝난다(같은 자리를 두 번 탓하지 않는다)",
        row_problems(replace(healthy, floors=(), commit=None), "기록을 읽지 못했다"),
        ["기록을 읽지 못했다"],
    )
    # 고아 기록 — 아무도 읽지 않는 `floors` 는 면죄부다. 읽는 자리를 알면 조용하다.
    with tempfile.TemporaryDirectory() as work:
        evidence = Path(work)
        mine = evidence / "read.json"
        mine.write_text(json.dumps({"floors": [{"label": "a", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8")
        lonely = evidence / "lonely.json"
        lonely.write_text(json.dumps({"floors": [{"label": "b", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8")
        (evidence / "floorsless.json").write_text(json.dumps({"counts": {"a": 1}}), "utf-8")
        (evidence / "broken.json").write_text("{", "utf-8")
        names = lambda found: [Path(item).name for item in found]  # noqa: E731 - 시험용 한 줄
        cases.equal("아무도 읽지 않는 기록만 고아로 센다", names(orphan_records(evidence, [mine])), ["lonely.json"])
        cases.equal("`floors` 가 없는 artifact 는 고아가 아니다", names(orphan_records(evidence, [mine, lonely])), [])
        cases.equal(
            "roster 가 그 층을 잊으면 그 기록도 고아가 된다(면죄부가 남지 않는다)",
            names(orphan_records(evidence, [])),
            ["lonely.json", "read.json"],
        )
    # 커밋 읽기 — 저장소 밖이거나 추적되지 않으면 None(추측하지 않는다).
    cases.check("저장소 밖 경로는 커밋을 말하지 않는다", commit_of(Path("/tmp/없는파일.json")) is None)
    canary_commit = commit_of(CANARY_SCRIPT) or {}
    cases.check(
        "추적되는 파일은 커밋(날짜·사람·해시)을 읽는다", bool(canary_commit.get("by") and canary_commit.get("hash"))
    )
    # 표 밖 스캔 — 이름 패턴·AST 판독·배선 판독·선언 판정을 합성 입력으로 다시 물어본다.
    cases.check(
        "스캔 하한은 관측 0 에서 문다(스캔이 깨져 ‘표 밖에 아무것도 없다’ 로 통과하는 것을 잡는다)",
        bool(floor_problems([Floor("하한 후보 스캔", 0, _MIN_CANDIDATES, why="근거")])),
    )
    with tempfile.TemporaryDirectory() as work:
        probe_dir = Path(work)
        # 주석·문자열 안의 이름에 속지 않는지, 값이 숫자가 아닌 것은 빠지는지 보려고 일부러 섞어 둔다.
        (probe_dir / "sample.py").write_text(
            '# MIN_COMMENTED = 3\nNOTE = "MIN_QUOTED = 4"\n\n\ndef f():\n    MIN_INNER = 1\n\n',
            encoding="utf-8",
        )
        (probe_dir / "grid.py").write_text(
            "from harness_contract import Floor\n"
            "MIN_ALPHA = 10\n"
            "MIN_BETA = 20\n"
            'NOTE_MIN_GAMMA = "근거 문장"\n'
            "FLOOR_DELTA = 1.5\n"
            "\n"
            "def floors():\n"
            "    return [\n"
            '        Floor("a", 100, MIN_ALPHA, why="근거"),\n'
            '        Floor(label="b", observed=100, minimum=MIN_BETA, why="근거"),\n'
            '        Floor("c", 100, 7, why="근거"),\n'
            "    ]\n",
            encoding="utf-8",
        )
        (probe_dir / "broken.py").write_text("def (\n", encoding="utf-8")
        scanned = floor_candidates(probe_dir)
        cases.equal(
            "주석·문자열·함수 안의 이름은 후보가 아니다(숫자 상수만, 모듈 수준만)",
            list(scanned),
            ["grid.py:FLOOR_DELTA", "grid.py:MIN_ALPHA", "grid.py:MIN_BETA"],
        )
        cases.check("근거 문자열 상수(`_WHY_*`)는 후보가 아니다", all("NOTE_MIN_GAMMA" not in name for name in scanned))
        cases.check(
            "문을 못 여는 파일이 있어도 살아남는다(그 자리는 그 파일을 돌리는 층이 실패한다)",
            "grid.py:MIN_ALPHA" in scanned,
        )
        wired = wired_constants([probe_dir / "grid.py"])
        cases.equal(
            "위치 인수 셋째 자리와 `minimum=` 둘 다 배선으로 읽는다",
            sorted(wired),
            ["grid.py:MIN_ALPHA", "grid.py:MIN_BETA"],
        )
        cases.check(
            "하한에 안 넘긴 상수(`FLOOR_DELTA`)는 배선이 아니다 — 선언이나 하한 목록에 실려야 한다",
            "grid.py:FLOOR_DELTA" not in wired,
        )
        cases.check("숫자 리터럴을 그대로 넘긴 하한은 상수가 아니라 배선이 아니다", "grid.py:7" not in wired)
    undeclared, stale = outside_floors(
        ("scripts/a.py:MIN_X", "scripts/b.py:MIN_Y"),
        ("scripts/a.py:MIN_X",),
        (),
    )
    cases.equal("배선되지 않은 후보를 선언 없이 두면 잡힌다", list(undeclared), ["scripts/b.py:MIN_Y"])
    cases.equal(
        "배선된 후보는 선언이 필요 없다",
        list(outside_floors(("scripts/a.py:MIN_X",), ("scripts/a.py:MIN_X",), ())[0]),
        [],
    )
    cases.equal(
        "선언했지만 이제 하한 목록에 실린 것은 낡은 선언이다",
        list(outside_floors(("scripts/a.py:MIN_X",), ("scripts/a.py:MIN_X",), ("scripts/a.py:MIN_X",))[1]),
        ["scripts/a.py:MIN_X"],
    )
    cases.equal(
        "선언했지만 사라진 상수도 낡은 선언이다",
        list(outside_floors((), (), ("scripts/gone.py:MIN_Z",))[1]),
        ["scripts/gone.py:MIN_Z"],
    )
    healthy_declaration = OutsideFloor(
        "scripts/b.py:MIN_Y", "하한이 아니라 유효성 임계다", "tester", "2026-01-01", "2026-12-31"
    )
    window = (_MAX_REVIEW_WINDOW_DAYS, _WHY_MAX_REVIEW_WINDOW)  # 기록을 만들 때 함께 넘기는 승인된 창
    wind = {"days": _MAX_REVIEW_WINDOW_DAYS, "why": _WHY_MAX_REVIEW_WINDOW}
    cases.equal(
        "살아 있는 선언은 조용하다",
        outside_problems(("scripts/b.py:MIN_Y",), (), (healthy_declaration,)),
        [],
    )
    cases.check(
        "확인일에서 기한까지의 창을 읽는다(그 창이 “한 번의 확인으로 얼마나 미룰 수 있나” 다)",
        healthy_declaration.window is not None and healthy_declaration.window == 364,
    )
    cases.check(
        "한 번의 확인으로 창을 넘는 기한을 줄 수는 없다",
        any(
            "창을 넘는다" in problem
            for problem in outside_problems(
                ("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, review_by="2028-01-01"),)
            )
        ),
    )
    cases.check(
        "기한이 확인일보다 앞서면 그것은 기한이 아니다(둘 중 하나가 잘못 적렸다)",
        any(
            "기한이 확인일보다 앞서" in problem
            for problem in outside_problems(
                ("scripts/b.py:MIN_Y",),
                (),
                (replace(healthy_declaration, reviewed_on="2026-06-01", review_by="2026-01-01"),),
            )
        ),
    )
    cases.check(
        "확인이 미래일 수는 없다(확인은 이미 한 일이다)",
        any(
            "확인일이 아직 오지 않았다" in problem
            for problem in outside_problems(
                ("scripts/b.py:MIN_Y",),
                (),
                (replace(healthy_declaration, reviewed_on="2099-01-01", review_by="2099-06-01"),),
            )
        ),
    )
    cases.check(
        "확인일을 읽지 못하는 선언도 실패한다(그 면제는 검토와 구분되지 않는다)",
        bool(outside_problems(("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, reviewed_on="언젠가"),))),
    )
    named = outside_problems(("scripts/b.py:MIN_Y",), (), ())
    cases.check("선언 없는 후보는 이름을 대며 실패한다", len(named) == 1 and "scripts/b.py:MIN_Y" in named[0])
    cases.check(
        "근거 없는 선언은 실패한다",
        bool(outside_problems(("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, reason="  "),))),
    )
    cases.check(
        "소유자 없는 선언은 실패한다",
        bool(outside_problems(("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, owner=""),))),
    )
    cases.check(
        "기한이 지난 선언은 실패한다(그 사이 그 도구가 층이 되었는지 다시 보라)",
        bool(outside_problems(("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, review_by="2020-01-01"),))),
    )
    cases.check(
        "기한을 읽지 못하는 선언도 실패한다",
        bool(outside_problems(("scripts/b.py:MIN_Y",), (), (replace(healthy_declaration, review_by="언젠가"),))),
    )
    # 면제는 **판단**이다 — 기록이 “이 상수는 하한이 아니다” 를 약속까지 승인했는가.
    approved = RecordedOutside(OUTSIDE_SHAPE_FULL, {healthy_declaration.name: healthy_declaration.promise}, *window)
    approved_none = RecordedOutside(OUTSIDE_SHAPE_FULL, {}, *window)
    cases.equal(
        "기록이 승인한 면제와 지금 표가 같으면 조용하다", outside_record_problems((healthy_declaration,), approved), []
    )
    cases.check(
        "기록에 없는 면제는 승인 없이 못 들어온다(면제를 만드는 것도 결정이다)",
        bool(outside_record_problems((healthy_declaration,), approved_none)),
    )
    cases.check(
        "면제를 거두는 것도 결정이다(기록이 승인한 면제가 표에 없다)",
        bool(outside_record_problems((), approved)),
    )
    cases.check(
        "면제의 근거·소유자가 바뀌면 그것은 다른 판단이다",
        bool(outside_record_problems((replace(healthy_declaration, reason="다른 이유"),), approved)),
    )
    # 기한을 미루는 것과 **검토 없이** 미루는 것은 다른 사건이다 — 확인일이 함께 움직였는가로 갈린다.
    tight = replace(healthy_declaration, review_by="2026-06-01")
    tight_approved = RecordedOutside(OUTSIDE_SHAPE_FULL, {tight.name: tight.promise}, *window)
    relocated = replace(tight, reviewed_on="2026-06-01", review_by="2027-06-01")
    pushed = outside_record_problems((relocated,), tight_approved)
    cases.check(
        "검토하고 미룬 기한은 승인이 필요하다(면죄부가 스스로 갱신되지 않는다)",
        len(pushed) == 1 and "기한을 미뤘다" in pushed[0] and "2026-06-01 → 2027-06-01" in pushed[0],
    )
    bare = replace(tight, review_by="2026-12-31")  # 확인일은 그대로, 기한만 뒤로(창 안이다)
    cases.equal(
        "기한만 미룬 것은 창 안이라도 연장이 아니다",
        [],
        outside_problems(("scripts/b.py:MIN_Y",), (), (bare,)),  # 표 쪽 규칙은 통과한다
    )
    skipped_review = outside_record_problems((bare,), tight_approved)
    cases.check(
        "검토 없이 미룬 것과 검토하고 미룬 것은 다른 문장으로 말해진다",
        len(skipped_review) == 1
        and "기한만 미뤘다" in skipped_review[0]
        and "확인일 2026-01-01 그대로" in skipped_review[0]
        and "기한을 미뤘다" not in skipped_review[0],
    )
    earlier = replace(healthy_declaration, reviewed_on="2025-06-01", review_by="2026-06-01")
    cases.check(
        "기한을 앞당긴 면제는 실패가 아니라 보고다(더 자주 보는 쪽이 안전한 쪽이다)",
        not outside_record_problems((earlier,), approved)
        and outside_pulled((earlier,), approved) == ("scripts/b.py:MIN_Y 2026-12-31 → 2026-06-01",),
    )
    renewed = replace(healthy_declaration, reviewed_on="2026-06-01")
    cases.check(
        "기한을 그대로 둔 확인도 실패가 아니라 보고다(보기만 한 것을 벌하면 아무도 다시 보지 않는다)",
        not outside_record_problems((renewed,), approved)
        and outside_reviewed((renewed,), approved) == ("scripts/b.py:MIN_Y 2026-01-01 → 2026-06-01",),
    )
    cases.check(
        "기록된 창이 지금 규칙과 다르면 기록이 먼저 실패한다",
        bool(
            outside_record_problems(
                (healthy_declaration,), RecordedOutside(OUTSIDE_SHAPE_FULL, {tight.name: tight.promise}, 999, "넓혔다")
            )
        ),
    )
    cases.check(
        "기록이 면제를 이름으로만 담으면 그것은 승인이 아니다(기한을 물을 자리가 없다)",
        bool(
            outside_record_problems((healthy_declaration,), RecordedOutside(OUTSIDE_SHAPE_NAMES, {"x": None}, *window))
        ),
    )
    undated = RecordedOutside(
        OUTSIDE_SHAPE_UNDATED,
        {
            healthy_declaration.name: (
                healthy_declaration.reason,
                healthy_declaration.owner,
                "",
                healthy_declaration.review_by,
            )
        },
        *window,
    )
    undated_said = outside_record_problems((relocated,), undated)  # 확인일이 없는 기록 + 검토한 연장
    cases.check(
        "기록이 확인일을 빼고 담았으면 그 자리 하나로 다시 기록하게 한다",
        len(undated_said) == 1 and "확인일" in undated_said[0],
    )
    cases.check(
        "확인일을 모르는 기록에서는 연장 문장이 나오지 않는다(같은 사실을 두 번 말하지 않는다)",
        "재검토 기한을 미뤘다(" not in undated_said[0] and "기한만 미뤘다(" not in undated_said[0],
    )
    cases.check(
        "기록에 면제 목록이 없으면 그것도 실패다(무엇이 면제됐는지 말하지 않는 기록)",
        bool(outside_record_problems((healthy_declaration,), RecordedOutside(OUTSIDE_SHAPE_ABSENT, {}))),
    )
    cases.equal(
        "기록이 없으면 면제 이야기는 `record_problems` 한테 맡긴다(같은 사실을 두 번 말하지 않는다)",
        outside_record_problems((healthy_declaration,), RecordedOutside(OUTSIDE_SHAPE_NONE, {})),
        [],
    )
    # 기한 이동 이력 — 기록이 스스로 적어 이어 가는 사실이라야 “몇 번째 재검토인가” 를 계산할 수 있다.
    moved_once: dict[str, object] = {
        "outside": {
            "declared": [replace(healthy_declaration, review_by="2027-12-31").as_mapping()],
            "review_window": wind,
            "deadline_moves": [
                {"name": healthy_declaration.name, "from": "2026-12-31", "to": "2027-12-31", "on": "2026-12-20"}
            ],
        }
    }
    cases.equal("이어진 기한 이력은 조용하다", deadline_move_problems(moved_once), [])
    cases.equal(
        "약속을 담은 기록이 이력 칸을 비워 두면 이력 없는 기록이다(한 번도 안 미룬 것과 같지 않다)",
        len(
            deadline_move_problems({"outside": {"declared": [healthy_declaration.as_mapping()], "review_window": wind}})
        ),
        1,
    )
    cases.equal(
        "이력 칸이 있는데 비어 있는 기록은 조용하다(미룬 적이 없다는 사실은 사실이다)",
        deadline_move_problems(
            {"outside": {"declared": [healthy_declaration.as_mapping()], "review_window": wind, "deadline_moves": []}}
        ),
        [],
    )
    cases.equal(
        "이력의 마지막 기한이 지금 승인된 기한과 다르면 기록이 자기 이력과 다른 말을 한다",
        len(
            deadline_move_problems(
                {
                    "outside": {
                        "declared": [replace(healthy_declaration, review_by="2028-12-31").as_mapping()],
                        "review_window": wind,
                        "deadline_moves": [
                            {
                                "name": healthy_declaration.name,
                                "from": "2026-12-31",
                                "to": "2027-12-31",
                                "on": "2026-12-20",
                            }
                        ],
                    }
                }
            )
        ),
        1,
    )
    cases.equal(
        "이어지지 않거나 제자리인 이동은 이력이 아니다(이동은 옛 기한에서 이어지고 앞으로 간다)",
        len(
            deadline_move_problems(
                {
                    "outside": {
                        "declared": [
                            replace(
                                healthy_declaration, name="x", reviewed_on="2026-06-01", review_by="2027-06-30"
                            ).as_mapping()
                        ],
                        "review_window": wind,
                        "deadline_moves": [
                            {"name": "x", "from": "2026-12-31", "to": "2027-06-30", "on": "2026-12-20"},
                            {"name": "x", "from": "2027-07-01", "to": "2027-06-30", "on": "2027-06-20"},
                        ],
                    }
                }
            )
        ),
        2,
    )
    cases.equal(
        "이미 사라진 면제의 이동 이력은 이력으로 남는다(철회도 기록을 지나야 한다)",
        deadline_move_problems(
            {
                "outside": {
                    "declared": [],
                    "review_window": wind,
                    "deadline_moves": [{"name": "x", "from": "2026-12-31", "to": "2027-12-31", "on": "2026-12-20"}],
                }
            }
        ),
        [],
    )
    cases.equal(
        "검토 없이 미룬 면제가 있으면 기록을 거부한다(그대로 쓰면 그 사실이 지워진다)",
        len(
            record_refusals(
                Ledger((), (), (), 0.0, (), (), (), {"outside": {"bare_deferred": [{"name": "scripts/a.py:MIN_X"}]}})
            )
        ),
        1,
    )
    cases.equal(
        "거부할 것이 없는 보고는 조용하다",
        record_refusals(Ledger((), (), (), 0.0, (), (), (), {"outside": {"bare_deferred": []}})),
        (),
    )
    # 재검토 시트 — 기한이 가까운 것부터, 면제마다 그 면제의 사실(남은 날·창·미룸)을 붙여 낸다.
    sheet_row = Ledger(
        (),
        (),
        (),
        0.0,
        (),
        (),
        (
            replace(
                healthy_declaration, name="scripts/c.py:MIN_LATE", reviewed_on="2026-06-01", review_by="2027-06-01"
            ),
            replace(
                healthy_declaration, name="scripts/b.py:MIN_SOON", reviewed_on="2026-06-01", review_by="2026-10-01"
            ),
        ),
        {
            "outside": {
                "deadline_moves": [
                    {"name": "scripts/c.py:MIN_LATE", "from": "2026-06-01", "to": "2027-06-01", "on": "2026-05-20"}
                ]
            }
        },
    )
    sheet = review_sheet(sheet_row, today=date(2026, 9, 24))
    cases.check(
        "시트는 기한이 가까운 것부터 낸다(kind 순서는 순서가 아니다)", sheet.index("MIN_SOON") < sheet.index("MIN_LATE")
    )
    cases.check(
        "시트는 면제마다 남은 날·창·미룸 횟수와 두 답을 붙인다",
        "(7일 남음)" in sheet
        and "창 122/366일" in sheet
        and "미룸 0회" in sheet
        and "미룸 1회" in sheet
        and "그 도구가 층이 되었는가" in sheet
        and '--record --method "' in sheet
        and "`coverage_floors`" in sheet,
    )
    cases.check(
        "시트는 기한이 지난 것도 지남으로 셀 수 있게 말한다",
        "지남"
        in review_sheet(
            Ledger((), (), (), 0.0, (), (), (replace(healthy_declaration, review_by="2026-09-01"),), {}),
            today=date(2026, 9, 24),
        ),
    )
    cases.equal(
        "선언이 없으면 시트가 빈 목록을 빈 목록이라고 말한다(침묵과 없음은 다르다)",
        len(review_sheet(Ledger((), (), (), 0.0, (), (), (), {}), today=date(2026, 9, 24)).splitlines()),
        2,
    )
    cases.equal(
        "기록을 읽을 때 약속까지 담겼는지·확인일이 있는지를 모양으로 가른다",
        [
            recorded_outside(
                {"outside": {"declared": [healthy_declaration.as_mapping()], "review_window": wind}}
            ).shape,
            recorded_outside(
                {"outside": {"declared": [{"name": "x", "reason": "r", "owner": "o", "review_by": "2026-12-31"}]}}
            ).shape,
            recorded_outside({"outside": {"declared": ["scripts/b.py:MIN_Y"]}}).shape,
        ],
        [OUTSIDE_SHAPE_FULL, OUTSIDE_SHAPE_UNDATED, OUTSIDE_SHAPE_NAMES],
    )
    cases.equal(
        "기록이 승인한 창도 함께 읽는다(그 창이 지금 규칙과 갈라지면 문장이 난다)",
        recorded_outside(
            {"outside": {"declared": [healthy_declaration.as_mapping()], "review_window": wind}}
        ).window_days,
        _MAX_REVIEW_WINDOW_DAYS,
    )
    # 이름만 바뀐 것으로 **보이는** 면제 — 두 이름이 같은 약속을 들고 있을 때만(추측을 사실처럼 말하지 않는다).
    old_exemption = OutsideFloor(
        "scripts/a.py:MIN_OLD", "판정 기준이다(관측 대상이 없다)", "qa", "2026-01-01", "2026-12-31"
    )
    new_exemption = replace(old_exemption, name="scripts/a.py:MIN_NEW")
    recorded_old = RecordedOutside(OUTSIDE_SHAPE_FULL, {old_exemption.name: old_exemption.promise}, *window)
    live = ("scripts/a.py:MIN_NEW",)
    pairs = renamed_declarations((new_exemption,), recorded_old, candidates=live, wired=())
    cases.equal("약속이 그대로면 이름만 바뀐 것으로 보인다", list(pairs), [(old_exemption.name, new_exemption.name)])
    cases.equal(
        "짝의 옛 이름은 낡은 선언으로 두 번 말하지 않는다(하나의 결정이 두 문장이 되지 않는다)",
        outside_problems(live, (), (old_exemption, new_exemption), renamed=pairs),
        [],
    )
    renamed_said = outside_record_problems((new_exemption,), recorded_old, renamed=pairs)
    cases.check(
        "그래도 짝을 승인하기 전에는 초록이 아니다(보인다 — 단정하지 않는다)",
        len(renamed_said) == 1
        and "이름만 바뀐 것으로 보인다" in renamed_said[0]
        and "`--record --method`" in renamed_said[0],
    )
    cases.equal(
        "표가 아직 새 이름을 선언하지 않았으면 짝지을 근거가 없다(사라짐·선언 없음 두 문장이 맞다)",
        list(renamed_declarations((old_exemption,), recorded_old, candidates=live, wired=())),
        [],
    )
    cases.equal(
        "약속이 일부라도 다르면 짝짓지 않는다(이름 변경이 아니라 다른 판단일 수 있다)",
        list(
            renamed_declarations(
                (replace(new_exemption, review_by="2027-01-31"),), recorded_old, candidates=live, wired=()
            )
        ),
        [],
    )
    cases.equal(
        "약속을 모르는 기록으로는 이름이 바뀌었다고 말할 근거가 없다",
        list(
            renamed_declarations(
                (new_exemption,),
                RecordedOutside(OUTSIDE_SHAPE_NAMES, {old_exemption.name: None}),
                candidates=live,
                wired=(),
            )
        ),
        [],
    )
    # 하한 기록 — **판단의 이동**은 실패, 관측·올림은 보고. 합성 입력으로 다시 묻는다.
    probe_row = LayerRow("p", KIND_MEASURED, "scripts/p.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE)
    judged_row = judged_floors(Ledger((probe_row,), (), (), 0.0))
    recorded: dict[str, object] = {
        "method": "2026-01-01 시험 승인",
        "recorded_on": "2026-01-01",
        "floors": [{"layer": "p", "label": "수", "minimum": 1, "observed": 3, "why": "근거"}],
    }
    cases.equal("기록과 지금 판단이 같으면 조용하다", record_problems(judged_row, recorded), [])
    cases.check("기록이 없으면 실패한다", bool(record_problems(judged_row, None)))
    cases.check("승인 문장 없는 기록은 기록이 아니다", bool(record_problems(judged_row, {**recorded, "method": ""})))
    cases.check(
        "날짜 없는 기록은 낡았는지도 알 수 없다", bool(record_problems(judged_row, {**recorded, "recorded_on": ""}))
    )
    cases.check(
        "`floors` 없는 기록은 무엇을 승인했는지 말하지 않는다",
        bool(record_problems(judged_row, {**recorded, "floors": []})),
    )
    lowered = record_problems(judged_row, {**recorded, "floors": [{**recorded["floors"][0], "minimum": 2}]})  # type: ignore[index]
    cases.check(
        "내려간 하한은 실패하고 이름·옛값·새값을 남긴다(승인 없는 하향)",
        len(lowered) == 1 and "내려간 하한" in lowered[0] and "2 → 1" in lowered[0],
    )
    cases.check(
        "올린 하한은 실패가 아니다(안전한 쪽으로 틀리는 것을 실패로 만들면 기록이 잡음이 된다)",
        record_problems((("p", "수", 2, "근거"),), recorded) == [],
    )
    cases.check(
        "관측만 움직인 기록은 낡지 않는다(관측은 판정에 안 든다)",
        record_problems(judged_row, {**recorded, "floors": [{**recorded["floors"][0], "observed": 999}]}) == [],  # type: ignore[index]
    )
    # 층 단위 문장 — 하나의 결정(층이 통째로 움직임)이 하한 개수만큼의 문장으로 흩어지지 않아야 한다.
    wide: dict[str, object] = {
        "method": "2026-01-01 시험 승인",
        "recorded_on": "2026-01-01",
        "floors": [
            {"layer": "p", "label": "수", "minimum": 1, "observed": 3, "why": "근거"},
            {"layer": "p", "label": "다른 수", "minimum": 1, "observed": 5, "why": "근거"},
            {"layer": "q", "label": "수", "minimum": 2, "observed": 7, "why": "근거"},
        ],
    }
    alive = (("p", "수", 1, "근거"), ("q", "수", 2, "근거"))
    partial = record_problems((("p", "수", 1, "근거"), ("q", "수", 2, "근거"), ("p", "새 수", 1, "근거")), wide)
    cases.check(
        "층은 살아 있고 하한만 새로 생기면 그 층 이름으로 묶어 말한다",
        any("층 p: 새 수" in problem for problem in partial),
    )
    cases.check(
        "층은 살아 있고 하한만 사라져도 층 이름으로 묶는다(둘째 하한을 지운 경우)",
        any(
            "층 p: 다른 수" in problem
            for problem in record_problems((("p", "수", 1, "근거"), ("q", "수", 2, "근거")), wide)
        ),
    )
    only_q = (("q", "수", 2, "근거"),)  # 층 p 가 통째로 사라진 표
    whole_layer = record_problems(only_q, wide, roster=("p", "q"))
    cases.check(
        "층이 통째로 표에서 사라지면 하한 개수와 함께 한 문장으로 말한다",
        len(whole_layer) == 1 and "층 p" in whole_layer[0] and "2개" in whole_layer[0],
    )
    cases.check(
        "그 층이 아직 카나리아 roster 에 있으면 결정이 아니라 결함이라고 말한다(둘은 같은 초록으로 보이면 안 된다)",
        "아직 카나리아 roster 에" in whole_layer[0],
    )
    cases.check(
        "roster 에서도 빠진 층은 빠진 결정이므로 그 결정을 기록하라고 말한다",
        any("roster 에서도 표에서도" in problem for problem in record_problems(only_q, wide, roster=("q",))),
    )
    cases.check(
        "기록에 없는 새 층은 층 이름과 하한 개수로 말하고 이름이 바뀐 경우를 묻는다",
        any(
            "기록에 없는 새 층 r" in problem and "1개" in problem and "이름이 바뀐 것" in problem
            for problem in record_problems((*alive, ("r", "수", 1, "근거")), wide, roster=("p", "q", "r"))
        ),
    )
    # 하한 이름이 하나도 안 겹치면 이름 변경으로 보지 않는다 — 그때는 두 결정(사라짐·새로 생김)이 맞다.
    renamed = record_problems(
        (("p", "수", 1, "근거"), ("p", "다른 수", 1, "근거"), ("r", "새 이름", 1, "근거")), wide, roster=("p", "r")
    )
    cases.check(
        "층 이름이 사라지고 새 층이 생기면 두 결정으로 나눠 말한다 — 흩어진 문장으로 읽는 사람이 다시 세지 않게",
        any("roster 에서도 표에서도" in problem and "층 q" in problem for problem in renamed)
        and any("기록에 없는 새 층 r" in problem for problem in renamed),
    )
    # 하한 이름이 **그대로**인 층 짝은 이름만 바뀐 것으로 보인다 — 두 문장(사라짐·새로 생김)이 아니라 한 문장이다.
    # q(하한 1개) → r(하한 1개): 이름 집합이 그대로인 짝.
    swapped = record_problems(
        (("p", "수", 1, "근거"), ("p", "다른 수", 1, "근거"), ("r", "수", 2, "근거")), wide, roster=("p", "r")
    )
    cases.check(
        "하한 이름 집합이 그대로인 층은 “이름만 바뀐 것으로 보인다” 고 한 문장으로 말하고 짝과 근거를 남긴다",
        len(swapped) == 1 and "층 q 가 표에서 r 로" in swapped[0] and "하한 이름 1개가 그대로" in swapped[0],
    )
    cases.check(
        "이름 변경 후보는 사라짐·새 층 문장으로 **두 번 말하지 않는다**(하나의 결정이 두 문장으로 보이면 안 된다)",
        not any("roster 에서도 표에서도" in problem for problem in swapped)
        and not any("기록에 없는 새 층" in problem for problem in swapped),
    )
    cases.check(
        "이름 변경도 단정이 아니라 후보며, 그 결정을 기록하라고 말한다(원장은 층의 동일성을 모른다)",
        "`--record --method`" in swapped[0] and "보인다" in swapped[0] and "모른다" in swapped[0],
    )
    # p(하한 2개) → p2: 여러 하한이 함께 옮겨간 경우에도 이름을 모두 낸다.
    swapped_wide = record_problems(
        (("p2", "수", 1, "근거"), ("p2", "다른 수", 1, "근거"), ("q", "수", 2, "근거")), wide, roster=("p2", "q")
    )
    cases.check(
        "옮겨간 하한 이름을 모두 낸다(어느 판단이 함께 움직였는지 읽는 사람이 알 수 있게)",
        len(swapped_wide) == 1
        and "하한 이름 2개가 그대로" in swapped_wide[0]
        and "수" in swapped_wide[0]
        and "다른 수" in swapped_wide[0],
    )
    partial_overlap = record_problems(
        (("p", "수", 1, "근거"), ("p", "다른 수", 1, "근거"), ("r", "수", 2, "근거"), ("r", "새 이름", 1, "근거")),
        wide,
        roster=("p", "r"),
    )
    cases.check(
        "하한 이름이 일부만 겹치면 이름 변경이라고 단정하지 않는다(층이 갈라졌을 수도 있다)",
        any("roster 에서도 표에서도" in problem for problem in partial_overlap)
        and any("기록에 없는 새 층 r" in problem for problem in partial_overlap)
        and not any("이름만 바뀐 것으로 보인다" in problem for problem in partial_overlap),
    )
    still_in_roster = record_problems(
        (("p", "수", 1, "근거"), ("p", "다른 수", 1, "근거"), ("r", "수", 2, "근거")), wide, roster=("p", "q", "r")
    )
    cases.check(
        "층이 아직 roster 에 있으면 이름 변경으로 덮지 않는다 — 그것은 결정이 아니라 표가 못 읽은 결함이다",
        any("아직 카나리아 roster 에" in problem for problem in still_in_roster)
        and not any("이름만 바뀐 것으로 보인다" in problem for problem in still_in_roster),
    )
    cases.check(
        "값이 같아도 근거가 바뀌면 다른 판단이다",
        any("근거가 바뀐" in problem for problem in record_problems((("p", "수", 1, "다른 근거"),), recorded)),
    )
    cases.check(
        "판단 대조는 관측에 흔들리지 않는다(관측만 달라진 표는 같은 판단이다)",
        judged_row
        == judged_floors(Ledger((replace(probe_row, floors=(Floor("수", 99, 1, why="근거"),)),), (), (), 0.0)),
    )
    cases.equal("판단 목록은 (층·이름·값·근거) 네 칸이다", len(judged_row[0]), 4)
    payload = record_payload(
        Ledger((probe_row,), (), (), 0.0), Probe(cases=1, failures=()), method="시험", on="2026-01-01"
    )
    cases.equal("기록 왕복 — 지금 표를 기록하면 그 기록은 지금과 같다", record_problems(judged_row, payload), [])
    # 층 이름 변경은 **기록에 사실로 남는다** — floors 만 적으면 그 하한들이 처음부터 새 이름의 층에 있었던 것으로 읽힌다.
    old_ledger = Ledger(
        (LayerRow("p", KIND_MEASURED, "scripts/p.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE),),
        (),
        (),
        0.0,
    )
    old_payload = record_payload(old_ledger, Probe(cases=1, failures=()), method="옛 승인", on="2026-01-01")
    new_ledger = Ledger(
        (LayerRow("r", KIND_MEASURED, "scripts/r.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE),),
        (),
        (),
        0.0,
    )
    renamed_payload = record_payload(
        new_ledger, Probe(cases=1, failures=()), method="이름 변경 승인", on="2026-02-01", previous=old_payload
    )
    cases.equal(
        "기록은 이름 변경을 사실로 남긴다(짝·그대로인 하한 이름·승인 날짜)",
        list(recorded_renames(renamed_payload)),
        [("p", "r", ("수",), "2026-02-01")],
    )
    cases.equal(
        "이름 변경 이력은 다음 기록으로 이어진다(그 사이에 또 이름이 바뀌어도 옛 사실이 안 사라진다)",
        [
            fact[:3]
            for fact in recorded_renames(
                record_payload(
                    Ledger(
                        (
                            LayerRow(
                                "s", KIND_MEASURED, "scripts/s.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE
                            ),
                        ),
                        (),
                        (),
                        0.0,
                    ),
                    Probe(cases=1, failures=()),
                    method="또 이름 변경",
                    on="2026-03-01",
                    previous=renamed_payload,
                )
            )
        ],
        [("p", "r", ("수",)), ("r", "s", ("수",))],
    )
    cases.equal(
        "이름 변경 이력이 기록된 채로 게이트를 통과한다(이력 자체는 결함이 아니다)",
        record_problems(judged_floors(new_ledger), renamed_payload),
        [],
    )
    cases.check(
        "기록이 이름 변경을 주장하는데 새 이름의 하한이 기록에 없으면 자기 모순이다",
        any(
            "새 이름" in problem
            for problem in record_problems(
                (("p", "수", 1, "근거"),),
                {**payload, "renames": [{"from": "p", "to": "q", "shared": ["수"], "on": "2026-01-01"}]},
            )
        ),
    )
    cases.check(
        "기록이 이름을 바꿨다고 하면서 옛 이름의 하한도 들고 있으면 모순이다",
        any(
            "옛 이름" in problem
            for problem in record_problems(
                (("p", "수", 1, "근거"),),
                {**payload, "renames": [{"from": "p", "to": "r", "shared": ["수"], "on": "2026-01-01"}]},
            )
        ),
    )
    cases.check(
        "같은 새 이름으로 두 번 바뀌었다는 기록은 모순이다",
        any(
            "두 번" in problem
            for problem in rename_claim_problems(
                {
                    "floors": [{"layer": "s", "label": "수", "minimum": 1, "why": "근거"}],
                    "renames": [
                        {"from": "p", "to": "s", "shared": ["수"], "on": "2026-01-01"},
                        {"from": "q", "to": "s", "shared": ["수"], "on": "2026-01-02"},
                    ],
                }
            )
        ),
    )
    cases.check(
        "기록이 바꿨다고 승인한 층의 **옛 이름이 표에 돌아오면** 다시 승인받아야 한다",
        any(
            "옛 이름" in problem and "돌아왔다" in problem
            for problem in record_problems(
                (("p", "수", 1, "근거"), ("r", "수", 1, "근거")),
                {**payload, "renames": [{"from": "p", "to": "r", "shared": ["수"], "on": "2026-01-01"}]},
            )
        ),
    )
    cases.check("기록은 그날의 속도를 담지 않는다", "seconds" not in json.dumps(payload))
    cases.equal(
        "관측이 움직이면 보고로 낸다(판정 아님)",
        record_moves(Ledger((replace(probe_row, floors=(Floor("수", 7, 1, why="근거"),)),), (), (), 0.0), payload),
        ("p · 수 3 → 7 ▲",),
    )
    cases.equal(
        "올라간 하한도 보고로 낸다",
        record_raised(Ledger((replace(probe_row, floors=(Floor("수", 3, 2, why="근거"),)),), (), (), 0.0), payload),
        ("p · 수 1 → 2",),
    )
    return cases.probe()


def _probe_or_failure() -> Probe:
    """자기시험이 예외로 죽으면 그 사실을 **실패**로 바꾼다(사고는 판정이 아니다)."""

    try:
        return self_probe()
    except Exception as exc:  # noqa: BLE001
        return Probe(cases=0, failures=(f"자기시험이 예외로 죽었다: {type(exc).__name__}: {exc}",))


def _pad(text: str, width: int) -> str:
    """한글·한자·전각 기호를 두 칸으로 세어 자리를 맞춘다(글자 수로 맞추면 표가 어긋난다)."""

    cells = sum(2 if unicodedata.east_asian_width(char) in "WFA" else 1 for char in text)
    return text + " " * max(0, width - cells)


def _days_left(item: OutsideFloor, today: date) -> int | None:
    """기한까지 남은 날(지났으면 음수) — 못 읽으면 `None`(그 사실은 표 쪽 문장이 낸다)."""

    due = _as_day(item.review_by)
    return (due - today).days if due is not None else None


def _span(days: int | None) -> str:
    """남은 날을 한 마디로 — 오늘이 기한이면 ‘오늘’, 지났으면 ‘N일 지남’."""

    if days is None:
        return "기한 못 읽음"
    if days == 0:
        return "오늘"
    return f"{days}일 남음" if days > 0 else f"{-days}일 지남"


def _deadline_history(ledger: Ledger, name: str) -> tuple[str, int, int]:
    """한 면제의 기한 이동 이력 — (문장, 미룸 횟수, 당긴 횟수). 기록이 사실로 남긴 이동만 센다.

    미룸 횟수는 주장이 아니라 **계산된 사실**이다(기록이 대조로 찾아낸 이동을 이어 간다) — 검토 세션에서 “이 면제가
    몇 번째인가” 를 묻는 자리가 여기고, 세 번째·네 번째면 그 면제는 층이 될 때가 되었다는 신호다.
    """

    moves = _record_dict(ledger.record, "outside").get("deadline_moves")
    steps = [item for item in (moves if isinstance(moves, list) else []) if isinstance(item, dict)]
    mine = [item for item in steps if str(item.get("name")) == name]
    deferred = sum(1 for item in mine if str(item.get("to")) > str(item.get("from")))
    pulled = sum(1 for item in mine if str(item.get("to")) < str(item.get("from")))
    if not mine:
        return ("", deferred, pulled)
    history = "; ".join(f"{item.get('from')} → {item.get('to')}({item.get('on') or '날짜 없음'} 승인)" for item in mine)
    return (history, deferred, pulled)


def review_sheet(ledger: Ledger, *, today: date | None = None) -> str:
    """면제 재검토 시트 — 기한이 가까운 것부터, 각 면제에 두 가지 답과 그 편집을 붙여 낸다.

    원장의 실패 문장은 **기한이 지난 뒤에야** 나온다(“그 도구가 층이 되었는지 다시 보라”). 그때 열 개가 한꺼번에
    만료되면 읽는 사람은 열 문장과 열 개의 편집을 한 번에 마주한다 — 이 시트는 그 일을 **재검토 세션의 순서**로
    바꾼다: 남은 날이 적은 것부터, 각 면제가 몇 번째 재검토인지와 함께. 두 답은 모든 면제에 대해 같은 물음이라 한 번만
    적고(① 아직 아니다 → 확인일·기한을 다시 적고 `--record`, ② 되었다 → `coverage_floors` 에 실어라), 면제마다 다른 것은
    남은 날·창 사용량·미룬 횟수·근거다.
    """

    as_of = today or date.today()
    window = _MAX_REVIEW_WINDOW_DAYS
    lines = [
        f"[ledger] 면제 재검토 시트 — 선언 {len(ledger.outside)}개(기한이 가까운 것부터) · "
        f"오늘 {as_of.isoformat()} · 창 {window}일",
    ]
    if not ledger.outside:
        lines.append(
            "  재검토할 면제가 없다 — 표 밖 후보가 전부 하한 목록에 실렸거나, 스캔이 이름을 못 본 것이다"
            "(후자는 표 밖 스캔 하한이 따로 문다)"
        )
        return "\n".join(lines)
    order = sorted(
        ledger.outside, key=lambda item: (_days_left(item, as_of) is None, _days_left(item, as_of) or 0, item.name)
    )
    for index, item in enumerate(order, start=1):
        days = _days_left(item, as_of)
        used = item.window
        history, deferred, pulled = _deadline_history(ledger, item.name)
        counts = f"미룸 {deferred}회" + (f" · 당김 {pulled}회" if pulled else "")
        lines.append(
            f"[{index}] {item.name} — {item.owner} · 확인 {item.reviewed_on} → 기한 {item.review_by}("
            f"{_span(days)}) · 창 {used if used is not None else '못 읽음'}/{window}일 · {counts}"
        )
        lines.append(f"    왜 하한이 아닌가: {item.reason}")
        if history:
            lines.append(f"    기한 이동: {history}")
    lines.append("  물음은 모든 면제에 같다: **그 도구가 층이 되었는가?**")
    lines.append(
        f"    ① 아직 아니다 → `reviewed_on` 을 오늘({as_of.isoformat()})로, `review_by` 를 오늘 + {window}일 안으로 "
        '적고 `--record --method "무엇을 보고 미뤘는가"`'
    )
    lines.append(
        "    ② 되었다 → 그 상수를 그 층의 `coverage_floors` 에 실어 카나리아 앞에 세워라(그 선언은 낡은 선언이 되어 지워야 한다)"
    )
    deferred_total = sum(_deadline_history(ledger, item.name)[1] for item in ledger.outside)
    lines.append(
        f"  지금까지 미룬 횟수 {deferred_total}회 — 세 번째·네 번째 미룸은 그 도구를 층으로 세울 자리가 되었다는 신호다"
        "(기한을 미룬 사실은 기록이 계산해 이어 간다)"
    )
    return "\n".join(lines)


def describe(ledger: Ledger, probe: Probe) -> str:
    recorded = sum(1 for row in ledger.rows if row.kind == KIND_RECORDED)
    lines = [
        f"[ledger] 하한 원장 — {len(ledger.rows)}층 · 하한 {ledger.floors}개(기록 {recorded} · "
        f"직접 {len(ledger.rows) - recorded - 1} · 자기 1) · 다른 층에서 본 하한 {ledger.canvas}개 · "
        f"고아 기록 {len(ledger.orphans)}",
        f"  {_pad('층', 26)} {_pad('하한', 14)} {'관측':>6} {'하한값':>7} {'여유':>6} 승인",
    ]
    for row in ledger.rows:
        if not row.floors:
            lines.append(
                f"  {_pad(row.name, 26)} {_pad('**하한 없음**', 14)} {'-':>6} {'-':>7} {'-':>6} {row.approval_short}"
            )
            continue
        for floor in row.floors:
            lines.append(
                f"  {_pad(row.name, 26)} {_pad(floor.label, 14)} {floor.observed:>6d} {floor.minimum:>7d} "
                f"{floor.margin:>6d} {row.approval_short}"
            )
    lines.append("  출처와 승인(전문)")
    for row in ledger.rows:
        lines.append(f"    · {_pad(row.name, 26)} {row.kind} {row.source}")
        lines.append(f"      승인: {row.approval_text}")
        if row.note:
            lines.append(f"      각주: {row.note}")
    for orphan in ledger.orphans:
        lines.append(f"  고아기록  {orphan} — 어떤 harness 도 읽지 않는다")
    lines.append(
        f"  표 밖 스캔  후보 {len(ledger.candidates)}개(하한 {_MIN_CANDIDATES}) — 표가 읽는 것 {len(ledger.covered)} · "
        f"선언 {len(ledger.outside)}개(근거·소유자·재검토 기한 있음)"
    )
    today = date.today()
    for item in ledger.outside:
        window = item.window
        span = f"창 {window}일" if window is not None else "창 못 읽음"
        lines.append(
            f"    · {item.name}({item.owner}, 확인 {item.reviewed_on} · 재검토 {item.review_by}("
            f"{_span(_days_left(item, today))}) · {span}) — {item.reason}"
        )
    lines.append(
        f"  면제 창    한 번의 확인으로 줄 수 있는 기한은 {_MAX_REVIEW_WINDOW_DAYS}일까지다 — 창을 넓히는 것도 결정이다"
    )
    record = ledger.record
    exempted = _record_dict(record, "outside")
    if record.get("present"):
        lines.append(
            f"  면제 기록  선언 {len(ledger.outside)}개 · 기록이 승인한 면제 {exempted.get('recorded', 0)}개 "
            f"({exempted.get('shape', '')}, 창 {exempted.get('recorded_window_days', 0)}일) · 기록된 기한 이동 "
            f"{len(_record_lines(exempted, 'deadline_moves'))}회 — 면제를 만들거나·거두거나·기한을 미루면 승인이 필요하다"
        )
        moves = exempted.get("deadline_moves")
        for fact in moves if isinstance(moves, list) else []:
            if isinstance(fact, dict):
                lines.append(
                    f"    · 기한 이동 이력(기록이 사실로 남긴 것 — 몇 번째 재검토인지는 여기서 센다): "
                    f"{fact.get('name')} {fact.get('from')} → {fact.get('to')}({fact.get('on') or '날짜 없음'} 승인)"
                )
        for line in _record_lines(exempted, "reviewed"):
            lines.append(f"    · 면제 확인일을 새로 잡았다(보고만 — 더 자주 보는 쪽이다): {line}")
        for line in _record_lines(exempted, "pulled"):
            lines.append(f"    · 면제 기한을 앞당김(보고만 — 더 자주 보는 쪽이다): {line}")
        pairs = exempted.get("renamed")
        for pair in pairs if isinstance(pairs, list) else []:
            if isinstance(pair, dict):
                lines.append(
                    f"    · 이름만 바뀐 것으로 보이는 면제(단정하지 않는다 — 판단은 사람 몫): "
                    f"{pair.get('from')} → {pair.get('to')}"
                )
    if record.get("present"):
        lines.append(
            f"  하한 기록  {record.get('path')} · {record.get('recorded_on') or '날짜 없음'} 승인 · "
            f"기록된 하한 {record.get('floors')}개 · 판단 이동 내려감 {record.get('lowered')} · 사라짐 {record.get('vanished')} · "
            f"새 하한 {record.get('added')} · 근거 변경 {record.get('reasons')} · "
            f"층 이동 사라짐 {len(_record_lines(record, 'vanished_layers'))} · 새 층 {len(_record_lines(record, 'added_layers'))} · "
            f"이름만 바뀐 듯한 층 {len(_record_lines(record, 'renamed_layers'))} · "
            f"기록된 이름 변경 이력 {len(_record_lines(record, 'renames'))}"
        )
        lines.append(f"    승인 문장: {record.get('method')}")
        facts = record.get("renames")
        for fact in facts if isinstance(facts, list) else []:
            if not isinstance(fact, dict):
                continue
            shared = fact.get("shared") or []
            lines.append(
                f"    · 이름 변경 이력(기록이 사실로 남긴 것): {fact.get('from')} → {fact.get('to')} "
                f"({fact.get('on') or '날짜 없음'} 승인 · 하한 {len(shared)}개가 그대로)"
            )
        renamed = record.get("renamed_layers")
        for pair in renamed if isinstance(renamed, list) else []:
            if not isinstance(pair, dict):
                continue
            shared = pair.get("shared") or []
            lines.append(
                f"    · 이름 변경 후보(단정하지 않는다 — 판단은 사람 몫): {pair.get('from')} → {pair.get('to')} "
                f"(하한 {len(shared)}개가 그대로: {', '.join(str(item) for item in shared)})"
            )
    else:
        lines.append(
            f"  하한 기록  {record.get('path')} — **없다**(사람이 승인한 목록이 없으면 “내려도 되는 하한인가” 를 물을 자리가 없다)"
        )
    for move in _record_lines(record, "moves"):
        lines.append(f"    · 관측 이동(보고만 — 각 층의 게이트가 판정한다): {move}")
    for raised in _record_lines(record, "raised"):
        lines.append(f"    · 올라간 하한(보고만): {raised}")
    lines.append(
        f"  소요      {ledger.seconds:.1f}초 · 자기시험 {probe.cases}건 재판정 · 승인 = 기록의 승인 문장 또는 "
        "그 근거 파일의 마지막 커밋(하한만 바뀐 커밋이 아닐 수 있다)"
    )
    for problem in all_problems(ledger):
        lines.append(f"    - {problem}")
    lines.append(
        "* 이 표가 없으면 “이 저장소에 어떤 하한이 있고 무엇을 보고 정해졌는가” 는 열 개 파일을 손으로 열어야 알 수 있다."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="floor_ledger",
        description="탐지력 하한 원장 — 어떤 하한이 있고, 무엇을 보고, 언제 누가 승인했는가",
    )
    parser.add_argument("--gate", action="store_true", help="하나라도 어긋나면 exit 1")
    parser.add_argument("--emit-json", action="store_true", help="결과를 stdout JSON 으로 낸다(리뷰·게이트가 읽는다)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(저장소를 읽지 않는다)")
    parser.add_argument(
        "--evidence", type=Path, default=EVIDENCE_DIR, help="고아 기록을 찾을 자리(기본: 증거 디렉터리)"
    )
    parser.add_argument("--record", action="store_true", help="지금 하한 목록을 승인으로 남긴다(--method 필수)")
    parser.add_argument("--method", default="", help="--record 와 함께: 무엇을 보고 승인했는가")
    parser.add_argument("--review", action="store_true", help="면제 재검토 시트를 낸다(기한이 가까운 것부터)")
    args = parser.parse_args(argv)

    probe = _probe_or_failure()
    if args.self_test:
        print(describe_self_test("floor_ledger", probe))
        return EXIT_OK if probe.ok else EXIT_FAIL

    ledger = build(evidence_dir=args.evidence)
    problems = list(ledger.problems)
    problems.extend(probe_problems(probe, name="floor_ledger"))
    if args.record:
        # 기록은 **사람의 승인**이다 — 승인 문장 없이는 쓰지 않고, 이미 실패한 실행은 기록하지 않는다
        # (기록은 “지금의 하한 목록이 옳다” 는 승인이므로, 실패한 표를 승인하면 그 승인이 거짓이 된다).
        if not args.method.strip():
            print(
                "[FAIL] --record 에는 --method 가 필요하다 — 무엇을 보고 승인했는지 없는 기록은 “내려도 되는 하한인가” 에 답하지 못한다",
                file=sys.stderr,
            )
            return EXIT_FAIL
        if problems:
            print("[FAIL] 기록하지 않았다 — 이 실행이 이미 실패했다:", file=sys.stderr)
            for problem in problems:
                print(f"[FAIL] {problem}", file=sys.stderr)
            return EXIT_FAIL
        # 셋째 거부: **지워지는 사실**이 있는 실행은 기록하지 않는다(면죄부가 스스로를 씻지 못하게).
        refusals = record_refusals(ledger)
        if refusals:
            for refusal in refusals:
                print(f"[FAIL] {refusal}", file=sys.stderr)
            return EXIT_FAIL
        path = args.evidence / RECORD.name
        write_record(
            path,
            record_payload(
                ledger,
                probe,
                method=args.method.strip(),
                on=date.today().isoformat(),
                previous=read_record(path),
            ),
        )
        print(
            f"[ledger] 하한 기록을 남겼다: {_display(path)} (층 {len(ledger.rows)} · 하한 {ledger.floors}개 · "
            f"판단 이동 0 — 기록은 지금 목록의 승인이다)"
        )
        return EXIT_OK
    # 기록 문제도 여기서 합류한다 — 게이트·리뷰가 보는 판정과 JSON 의 `verdict` 가 같은 것을 말하도록.
    problems.extend(_record_lines(ledger.record, "problems"))
    if args.review:
        # 재검토 시트는 **진단**이다(작업 목록) — 판정은 여기서도 종료 코드가 말한다.
        print(review_sheet(ledger))
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return EXIT_FAIL if problems else EXIT_OK
    if args.emit_json:
        print(json.dumps(ledger.as_mapping(probe), ensure_ascii=False, indent=2))
        # JSON 을 내는 실행도 **판정을 종료 코드로** 말한다 — 진단은 stdout 에 그대로 남는다.
        return EXIT_FAIL if problems else EXIT_OK
    print(describe(ledger, probe))
    if not args.gate:
        return EXIT_OK if not problems else EXIT_FAIL
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_FAIL if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
