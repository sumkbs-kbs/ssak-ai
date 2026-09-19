#!/usr/bin/env python3
"""호스트 전역 브라우저 상한 시험용 **자식 프로세스** (task 16 후속).

시험이 재고 싶은 것은 "진짜 프로세스 둘이 같은 원장을 두고 다투는가" 이다. 그래서 이 파일은
자식이 하는 일만 갖는다: 자리를 열고, 결과를 JSON 한 줄로 보고하고, 부모가 시키면 죽는다.

모드:

  - `hold` — `CHILD_COUNT` 개의 자리를 열고 결과를 찍은 뒤 stdin 한 줄을 기다린다. **거절되면
    바로 끝난다**(자리를 못 잡은 자식이 매달려 있으면 시험이 교착한다). 기다린 뒤
    `CHILD_EXIT=crash` 면 정리 없이 죽고(`os._exit`), 아니면 `close_all()` 한다.
  - `once` — 자리 하나를 시도하고 결과만 찍는다(부모가 이미 자리를 쥐고 있는지 확인용).
  - `recheck` — 자리 하나를 연 뒤 stdin 을 기다렸다가 **다시 begin()** 한다. 다른 프로세스가
    그 사이 자리를 걷어갔으면 소유자는 그 세션을 닫고 새로 잡아야 한다(협조적 회수).

자리마다 owner 를 **따로** 준다: 같은 owner 로 두 번 부르면 소유자는 그 세션을 **재사용**하므로
(정상 동작이다) 자리 수가 늘지 않는다 — 그 함정을 시험용 자식이 되풀이하지 않도록 여기서 가른다.

출력은 한 줄에 JSON 하나(`{"event": ..., ...}`)이고, 부모는 그 줄만 읽는다.
"""

from __future__ import annotations

import json
import os
import sys

from antigravity_k.tools.browser_session_owner import (
    BrowserOwner,
    BrowserSessionLimitError,
    BrowserSessionOwner,
)


class Page:
    """페이지의 최소 계약. 여기서 보는 것은 닫혔는지뿐이다."""

    def __init__(self) -> None:
        self.url = "about:blank"
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


PAGES: list[Page] = []


def who_for(index: int) -> BrowserOwner:
    """자리마다 다른 owner — 같은 owner 는 재사용되어 자리 수가 늘지 않는다."""
    return BrowserOwner(subject="child@example.com", scope=f"web-{index + 1}", task_id=f"t-{index + 1}")


def emit(event: str, **payload: object) -> None:
    print(json.dumps({"event": event, **payload}), flush=True)


def closed_pages() -> int:
    return sum(page.closed for page in PAGES)


def open_slots(owner: BrowserSessionOwner, count: int) -> tuple[list[str], str]:
    """자리를 `count` 개 요청한다. 거절되면 그때까지 연 것과 이유를 돌려준다."""
    slots: list[str] = []
    for index in range(count):
        try:
            reservation = owner.begin(who_for(index), purpose="child")
        except BrowserSessionLimitError as error:
            return slots, str(error)
        page = Page()
        PAGES.append(page)
        lease = owner.commit(reservation, page=page, close=page.close)
        slots.append(lease.slot)
    return slots, ""


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    owner = BrowserSessionOwner.from_env()
    slots, error = open_slots(owner, int(os.environ.get("CHILD_COUNT", "1")))
    emit("result", mode=mode, slots=slots, error=error, closed=closed_pages())

    if mode == "once" or error:
        return 0
    line = sys.stdin.readline()

    if mode == "recheck":
        # 다른 프로세스가 우리 자리를 걷어갔는가? 그렇다면 소유자는 **닫고 새로 잡아야** 한다.
        reservation = owner.begin(who_for(0), purpose="recheck")
        if reservation.is_reuse:
            emit("recheck", reuse=True, slot=reservation.slot, closed=closed_pages())
        else:
            page = Page()
            PAGES.append(page)
            lease = owner.commit(reservation, page=page, close=page.close)
            emit("recheck", reuse=False, slot=lease.slot, closed=closed_pages())
        owner.close_all()
        return 0

    if mode == "hold":
        if os.environ.get("CHILD_EXIT") == "crash":
            # 정리도 close_all 도 아니고 — 자리를 붙잡은 채 죽은 앱을 흉내낸다.
            os._exit(0)
        owner.close_all()
        emit("done", closed=closed_pages(), stdin=line.strip())
        return 0

    emit("error", message=f"unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
