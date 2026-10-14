# CR-14 최종 후보 판정서 — NO-GO

- release declaration status: **ARCHIVED**
- Current HEAD release status: **NOT_APPROVED**

이 문서는 attempt-040까지의 역사적 후보·지문·NO-GO 기록이다. 아래의 최신/현재/HEAD 표기는 각 attempt 당시의 상태이며, 이후 개발 커밋이나 현재 작업 트리의 검증·승인을 선언하지 않는다. 보관된 지문은 기록된 후보 커밋과 대조한다. 새 활성 선언(`ACTIVE`)은 후보 SHA == 현재 HEAD, 커밋·작업 트리 지문 일치와 새 증거를 요구한다. 현재 지원·미완료 축은 [현재 상태](../20_CURRENT_STATUS.md)를 참조한다.

- 판정일: 2026-09-12 (attempt-001) · **attempt-002 갱신: 2026-09-12** · **attempt-003 갱신: 2026-09-12** · **attempt-004 갱신: 2026-09-12** · **attempt-005 갱신: 2026-09-13** · **attempt-006 갱신: 2026-09-13** · **attempt-007 갱신: 2026-09-13** · **attempt-008 갱신: 2026-09-13** · **attempt-009 갱신: 2026-09-13** · **attempt-010 갱신: 2026-09-13** · **attempt-011 갱신: 2026-09-13** · **attempt-012 갱신: 2026-09-13** · **attempt-013 갱신: 2026-09-13** · **attempt-014 갱신: 2026-09-13** · **attempt-015 갱신: 2026-09-13** · **attempt-016 갱신: 2026-09-13** · **attempt-017 갱신: 2026-09-13** · **attempt-018 갱신: 2026-09-13** · **attempt-019 갱신: 2026-09-13** · **attempt-020 갱신: 2026-09-13** · **attempt-021 갱신: 2026-09-13** · **attempt-022 갱신: 2026-09-13** · **attempt-023 갱신: 2026-09-13** · **attempt-024 갱신: 2026-09-13** · **attempt-025 갱신: 2026-09-13** · **attempt-026 갱신: 2026-09-13** · **attempt-027 갱신: 2026-09-14** · **attempt-028 갱신: 2026-09-14** · **attempt-029 갱신: 2026-09-14** · **attempt-030 갱신: 2026-09-14** · **attempt-031 갱신: 2026-09-14** · **attempt-032 갱신: 2026-09-14** · **attempt-033 갱신: 2026-09-14** · **attempt-034 갱신: 2026-09-14(직전)** · **attempt-035 갱신: 2026-09-14** · **attempt-036 갱신: 2026-09-14** · **attempt-040 갱신: 2026-09-14(최신)** · **attempt-039 갱신: 2026-09-14** · **attempt-037 갱신: 2026-09-14**
- 후보: 커밋 `08b8bb2e94f92a1d95d4a38b7d1171a58b9fe04f` + 미커밋 patch(CR-01~CR-14)
- 코드 지문(gate 실행 시점, `docs/`·`.omo/` 제외): attempt-001 `11979d6c…` → attempt-002 `ebbbd7f06fab3fb2d10008336ef96ba0d7949ee72007774c6372fc07f1bba0b5`(2544 files) → attempt-003 `eb10aed606ba7e84ecce03a50a19153b92105cacd196b5a167b5e38770f1f448`(2545 files) → attempt-004 `eca54773d5504e40a724a0c86ab9d1724be310986ef3e326f8f4904f52d98dd8`(2546 files) → attempt-005 `1981bfb5143d3f9eac947826bf6ee53655c47194f5be9c4a5bf755ba982a1844` → attempt-006 `3a9a7d66909e2fafaf31b4c429d2338f262d50b0d0d8ef3b5f00b5be0ca41e2d` → attempt-007 `c36327effafcc6dbe4a80970682f5e82eccd98f81951b000c758e888e7b0130a` → attempt-008 `6641446ef41e0562118dd0741637f57eae6412f18fdf18813ea87f777d0b0076` → **attempt-009 `dd34a76bf076ebc09be8c575ad733c52a0a647faa4d5d9758f3b01cf6f667f37`** → attempt-010 `d4a42ab8…` → attempt-011 `e428aacc…` → attempt-012 `7ecb4fc2…` → attempt-013 `2c5a15c8…` → attempt-014 `b6494f40…` → attempt-015 `b637d8b9…` → attempt-016 `1b84209e…` → attempt-017 `29fac8a0…`(앞선 `5e7d5c4c…` 는 F-26 수정이 지문을 옮겨 낡았다) → attempt-018 `56971ed6…`(F-27 수정: 이어받기 판단을 게이트 규칙에 위임) → attempt-019 `7f19c3a7…`(R-11 폐쇄: 마감 절차를 CI/릴리스가 부른다. 앞선 `a4e3e71d…` 는 F-28 수정이 지문을 옮겨 낡았다) → attempt-020 `aad2601c…`(CR-12 소관 재확인(R-5) + F-29 폐쇄) → attempt-021 `15e79e84…`(R-8 감사: 게이트에서 조용히 사라지는 테스트를 등록부가 소유한다 + F-30) → attempt-022 `6a51100f…`(F-31: 배포된 `/benchmark` 의 기본 타겟이 config 가 소유하지 않는 콤보를 가리켰다 → 설정을 복원하고 그 일치를 계약이 잰다 · `config-models-unregistered` 를 **능력으로** 되돌렸다(스킵 17 → 15))** → attempt-023 `37b76cb8…`(F-32: 조건 없이 스킵돼 있던 에이전트 실행 루프 2건을 **제품 결함이 아니라 계약 드리프트**로 닫았다 — 실패 이유를 관측하니 두 루프는 돌고 있었고, 막던 것은 리팩토링 이전 인터페이스를 흉내내는 **테스트 더블**과 그 뒤에 생긴 **승인·경로 경계**였다. 미검증 능력 **0건**) → **attempt-024 `7ae9af28…`(최신 — R-16 폐쇄: 등록부의 소유 단위를 **required 게이트 21개 전수**로 넓혔다. 같은 후보가 21개 게이트로 초록을 만드는데 그중 다섯이 테스트를 돌고, 나머지 네의 스킵은 아무도 세지 않았다. `api-e2e`(`-q` 단독 = 스킵 익명) · `dashboard-test`(vitest 기본 리포터 = 건수만)를 귀속시키고, `clean-machine-runtime` 의 `--skip-*` 채널을 등록부에 올렸다) → **attempt-025 `57e32c9a…`(F-33: attempt-023/024 가 **재지 않고 남긴 보안 질문** — 승인 게이트의 '항상 허용' 이 **무엇을 덮고 언제 사라지는지** — 을 제품 경로에서 쟀다. 부여는 도구 전체를 덮고 **프로세스가 살아 있는 한** 사라지지 않으며, **새 세션·다른 프로젝트가 같은 부여를 본다**(그래도 세션 간 유출은 아니다 — 프로세스가 새로 뜨면 0). 결함은 그 세 가지 사실이 아니라 그 사실들이 **감사 불가능**했다는 것이다: 부여 저장소가 `set[str]` 이라 시각·근거가 사라졌고(①), 부여를 **읽는 표면이 없었고**(② — 해제만 있었다), 동의 없이 실행된 횟수를 아무도 세지 않았고(③), 그 읽기 경로를 만들자 `GET /{request_id}` 가 `always-allowed` 를 요청 ID 로 삼켜 **404** 를 냈다(④ 경로 순서). 동의 문구도 `${description} 항상 허용` 이라 **이 요청**을 덮는 것처럼 읽혔다(⑤). 다섯 자리를 고치고 계약으로 고정했다 — **attempt-002 이후 처음으로 제품 런타임 코드가 바뀌었다**(승인 경로의 관측성이며, 이 attempt 는 판정을 움직이지 않는다))** → **attempt-026 `994b21fd…`(최신 — F-34: **게이트는 자기가 재는 코드를 바꾸지 않는다**.** 추적되는 빌드 산출물(`src/antigravity_k/dashboard_dist/`)을 다시 쓰는 게이트(`dashboard-build`)가 있으면, 그 게이트가 트리를 옮긴 뒤의 초록은 **다른 코드 상태**의 것이다. 게다가 낡은 번들은 **pytest 계약 6파일을 전부 통과**했다(68 passed) — 그 검사를 잡을 자리가 계약 안에는 없었다. 지문을 만들던 한 곳이 **게이트 앞뒤의 경로별 내용 지도**를 비교해, 트리를 옮긴 게이트를 `tree_moved` 로 적고 실행을 exit 1 로 끝낸다(required 여부와 무관). **제품 런타임 코드 변경 0줄.** 자세한 자리는 이 카드의 attempt-026 절과 §5.)** → **attempt-027 `98fd6695…`(앞선 선언 `e12ec3cb`(지문 `4dbfa955…`)는 **첫 측정이 `security-bandit` 에서 멈춰** 낡았다(B608 — 새 `cancel_if_permitted` 의 UPDATE 가 `prepare_resume` 과 같은 형태인데 그 표기(`# nosec B608`)를 갖지 않았다). 그 수정이 코드를 옮겼으므로 **측정 전에** 다시 선언한다(선언 → 측정 순서는 그대로다). F-35: **취소도 소유 규칙을 지킨다**. `resume` 은 `can_prepare_resume(raw_status, owner_pid)` 로 **소유자**를 보는데 `cancel` 은 보지 않아서, 다른 프로세스가 실행 중인 태스크를 `cancelled` 로 적을 수 있었다 — 그 행은 "끝났다"고 말하는데 소유자의 실행은 계속됐고(취소 신호는 프로세스 안의 event 다), 소유자의 마지막 상태 쓰기는 CAS 에 막혀 **이력이 거짓**이 됐다. 이제 두 경로가 **같은 liveness 함수**를 쓰고, 거부는 `owned_elsewhere` 로 **이름 붙어** API 409 로 나가며, 화면은 서버의 사유를 말한다)** → **attempt-028 `f838f2ea…`(F-36: **재시작한 서버는 주인에 대해 아는 것을 말한다**. attempt-027 이 **재지 않고 남긴** 절반을 실 서버로 재니(`uvicorn` + 실제 인증 + **SIGKILL** + 같은 DB 재기동), 죽은 소유자의 `running` 행이 표면에서 **살아 있는 실행과 구별되지 않았다** — 상세·목록은 `running` 이라고 말하고(주인에 대한 필드가 없다), 같은 행에 대해 `POST /resume` 은 **200** 을 돌려줬다. 그래서 화면은 복구 가능한 태스크에 **재개가 아니라 취소만** 제안했다(막다른 길). 고침은 **정책이 아니라 표면**이다(저장된 상태는 그대로 둔다 — 재시작이 고아 행을 자동으로 끝내면 재개 가능성이 사라진다): `/api/tasks` 와 `/api/tasks/{id}/status` 가 `execution_owner`(`live`/`dead`/`none`) 와 `resumable` 을 말하고, 값은 **한 곳**(`execution_owner_of` 는 `can_*` 와 같은 liveness 함수 · `resumable_task` 는 행동의 두 조건)에서 만들며, 화면은 그 필드로 버튼을 그린다(주인이 죽은 비종결 행은 "실행 중단(소유 프로세스 종료) — 재개 가능"). 증인 `attempt-028/repro/f36_orphan_surface_witness.py` — 실 서버 + 실 인증 + SIGKILL + 재기동으로 고침 전 **exit 1**(위반 4건) / 고침 후 **exit 0**)** → **attempt-029 `57f38a23…`(F-37 · F-38: **화면의 쓰기 경로는 서버가 받아들이는 것이어야 한다**. attempt-028 이 남긴 실 브라우저 슬라이스를 밟는 첫 걸음에서 브라우저 증인이 **제출 자체가 거부된다**는 사실을 먼저 만났다: 화면은 정체성을 최상위 `project_id` 로 보내는데 서버의 `TaskSubmitRequest`(`extra="forbid"`)가 그 본문을 422 로 막았고(F-37), 처음 설치한 기계에서는 서버가 보내는 `last_accessed_at: null` 을 화면의 스키마가 거부해 화면이 자기 프로젝트를 잃은 채 정체성 없이 제출했다(F-38) — 두 상태 어디에서도 제출은 성공할 수 없었다. 두 결함의 뿌리는 같다: **화면과 서버가 만나는 와이어를 재는 자리가 없었다**. 증인 둘(와이어 + 제품 경로 · 두 기계 상태)이 같은 파일을 고침 전/후로 돌려 각각 exit 1 → exit 0 이고, 계약은 서버 6건 + 대시보드 스키마 2건이며 대시보드 스키마가 깨진 이유는 그 테스트의 기존 픽스처가 `last_accessed_at` 을 **빼놓은 채** "실제 응답"이라 적혀 있었기 때문이다)** → **attempt-030 `87c5091b…`(F-39 · F-40: **크래시 뒤 열려 있는 화면도 새 사실을 배워야 한다**. attempt-028(서버가 죽은 주인을 말한다)·attempt-029(화면의 쓰기 경로)는 둘 다 **새로 연 화면**을 덮었고, "**이미 열려 있는** 화면"은 attempt-028 의 기술 잔여 ③이자 attempt-029 의 한계 — **두 번 연속 미측정으로 남은** 질문이었다. 답은 **아니오**였다: 실 서버 + 실제 PIN 로그인 + 제품의 버튼 + **그룹째 SIGKILL** + 같은 포트·같은 상태 디렉터리로 재기동했을 때 화면의 연결 라벨은 `["연결됨"]` 이었다 — 스트림이 조용히 다시 붙어 **연결을 잃은 적이 없다고 말하는 동안** 서버는 `execution_owner: dead`·`resumable: true` 로 바뀌었는데 화면은 크래시 전 스냅샷(`label="running"` · 재개 **없음** · 취소만)을 그대로 그렸다(위반 1건 · **exit 1**) — F-36 이 **서버 표면**에서 없앤 막다른 길이 **이미 열려 있는 화면**에는 그대로 남아 있었다. 뿌리는 구조다: 스트림은 스스로 다시 붙지만 **목록은 한 번 읽은 스냅샷**이고 그 안에 시간에 따라 변하는 값(`status`·`execution_owner`·`resumable`)이 들어 있다. 고침은 재연결 성공 지점이 목록을 다시 읽게 하는 **화면 코드**(`useTaskExecutionEvents.ts`)이고, 그 재조회는 `reloadVersion` 이 **아니라 별도 경로**여야 한다(`reloadVersion` 은 스트림 이펙트까지 다시 시작시키므로 스트림이 스스로 그것을 올리면 **재시작 루프**가 된다). 실패는 **삼키지 않는다**. **서버는 한 줄도 바뀌지 않았다**(F-35/F-36 의 규칙·표면·저장 상태 그대로). **F-40(측정 도구)**: 도구가 크래시를 **재현할 수 없다**는 사실이 먼저 드러났다 — `uv run … uvicorn` 의 실제 서버는 런처의 자식이라 런처만 죽이고 서버는 포트를 붙들고 살아 있고, 재기동이 토큰 비밀을 새로 만들면 질문이 "사용자가 로그아웃됐는가"로 바뀐다(두 성질 모두 그 파일의 docstring 이 처음부터 약속했다). 하네스는 이제 그룹째로 신호하고 비밀을 재사용한다. 증인 둘(제품 경로 exit 1 → exit 0 · 도구 A/B/C exit 0), 계약은 대시보드 단위 3건(고침 전 2 failed / 1 passed → 3 passed)) → **attempt-031 `7461ae3d…`(최신 — F-41 후보를 **측정으로 반증**했다: attempt-030 이 자기 한계로 적은 문장(*"M3(수동 탈출구) 경로는 이 실행에서 발화하지 않았다"*)이 남긴 질문을 실 서버·실 인증·**그룹째 SIGKILL**·같은 포트·같은 상태 디렉터리로 쟀다 — 화면이 스스로 포기할 때까지 **재기동하지 않고** 기다린 뒤(그것이 M3 의 전제다) 탈출구를 누르면 행이 서버의 새 사실(`dead`·`resumable`)로 바뀌고 라벨도 정착한다(`["연결 오류","연결됨"]`). 서버가 **없는 동안** 눌러도 화면은 `연결 오류` + 탈출구로 남고(막다른 길이 아니다), **두 번째** 크래시·재기동에서도 같다. **대조군**: 같은 증인을 **F-39 고침 이전 트리**에서 돌려도 **exit 0** — 이 축은 attempt-030 **이전에도 참**이었고, 즉 **결함이 아니라 재지 않은 경로**였다(attempt-030 이 닫은 결함은 **자동** 경로에만 있었다). **이빨**: 스크래치 트리에서 `retry` 를 무력화하고 그 트리의 번들을 다시 빌드하면 증인 **exit 1(위반 4건)** · 계약 **1 failed / 3 passed**. **제품 런타임 코드 변경 0줄** — 대신 `retry` 가 목록을 다시 읽는 **암묵적 의존**(`reloadVersion` 이 목록 이펙트의 의존성이라는 사실)에 계약이 소유자가 됐다. **판정 MOVED 없음**)** → **attempt-032 `5a8950a1…`(F-42: **브라우저 증인에게 게이트 소유자를 줬다**(required 21 → **22**). attempt-030/031 이 실 브라우저 증인으로 F-39·F-41 을 닫으면서 경계 문서에 적어 둔 문장(*"실 브라우저 증인 셋은 모두 수동이고, required 21개 중 어느 것도 이들을 돌리지 않는다"*)을 **측정으로 바꾸니 그 문장은 브라우저 패밀리 전체의 것이었다** — `dashboard/e2e/tests/cr*.spec.ts` **9파일 29건** 이 어느 required 게이트에도 소유자가 없었다(게이트 커버리지 0/9). 그런데 그 증인들은 **ambient 백엔드 없이** 돈다(실측 29 passed / 43.5s — 스스로 서버를 띄우거나 화면만 본다): 게이트로 세울 수 있었는데 세우지 않았다. 새 required 게이트 `dashboard-e2e-witnesses` 가 **이름 규칙으로** 그 패밀리를 돈다(그래서 증인을 새로 만들면 자동으로 게이트 안이고, `--project=chromium --reporter=list` 를 게이트가 직접 들고 있다 — 등록부가 스킵 귀속을 그 리포터에 걸어 두었는데 설정을 바꾸면 그 게이트의 스킵이 익명이 되기 때문이다). 계약 `tests/test_cr14_browser_witness_gate_contract.py` 가 **커버리지 주장**을 소유한다(전수성 + 경계 + 이빨). **이빨**: 게이트를 manifest 에서 지우면 계약 **4 failed** · required 를 false 로 강등하면 **1 failed** · 가족 이름으로 **일부로 실패하는 증인**을 만들면 게이트가 **exit 1 로 그 파일의 이름을 대며** 멈춘다(같은 파일은 고침 전 세계에서 **아무도 돌리지 않는다**). **제품 런타임 코드 변경 0줄** — 대신 **게이트 목록이 바뀌었으므로 `21/21` 은 이 후보부터 `22/22` 다**(인벤토리는 계약에 pinned 되어 있다). **판정 MOVED 없음**)** → **attempt-033 `1873d2c7…`(F-43 · F-44: **화면이 보내는 경로는 서버가 서는 경로여야 한다** · **런타임 상태는 코드 스코프 밖에 있다**. *(재선언 둘 — 측정 전)* 첫 선언은 후보 `b11ff74f`(지문 `03a7db8d…`)이었고 **그 첫 fast 배치가 `dashboard-build` 의 `tree_moved`(추적 번들 59 경로)로 멈췄다**(passed 18 / failed 1 / total 19) — 번들을 후보의 소스에서 다시 빌드해(두 번 빌드 바이트 동일) `ec76c7ce` 로 커밋한 뒤 **측정 전에** 다시 선언한다(D-52; 재선언 이유는 실패를 덮는 것이 아니라 코드가 옮겨졌기 때문이다). attempt-032 가 자기 한계로 남긴 *"ambient 백엔드 슬라이스는 게이트 밖"* 을 재려고 **서버를 띄우는 증인**을 세우는 첫 걸음에서 제품 결함이 나왔다: `apiRequest` 는 **래퍼 안에서** '/v1' 을 앞에 붙이는데 두 호출부가 **이미 namespace 를 가진 경로**를 넘겨서 실효 경로가 `/v1/api/agent/ask` · `/v1/auth/ws-ticket` 이 됐고, 서버에는 **`/v1/api/*` 도 `/v1/auth/*` 도 없다**(58 namespace 중 둘 부재 · 실효 경로는 살아 있는 서버에서 **405**, 정본 `/api/auth/ws-ticket` 은 **200 + ticket**). **이 발견의 핵심은 왜 아무도 못 봤는가다**: 접두사가 호출부의 **리터럴에 없어서** grep 도, 리터럴만 모으는 대조도 그 자리를 **건너뛴다**(증인 A 축이 그 눈먼 자리를 재현한다) — 그리고 `fetchWsTicket` 은 405 를 `catch { return null }` 로 삼키며, ticket 없는 WS 는 `open_loopback` 일 때만 통과하므로 **PIN 이 걸린 배포는 이벤트 스트림을 4401 로 잃고 3초마다 재시도**한다(로컬 dev 익명 모드가 그것을 가렸다). 고침은 전체 경로를 받는 `apiRequestPath` 로 바꾸는 **제품 런타임 2줄**(`loginWithAccessPin` 이 이미 따르던 규약)이고, 소유자는 **둘**이다 — 라우트 표와 대조하는 pytest 계약 6건(`tests/test_cr14_client_path_contract.py`: 래퍼를 해석한 실효 경로의 namespace 도달성 · 이빨 · **리터럴 전용 검사가 볼 수 없다는 사실 자체**를 고정) + 정확한 URL 을 고정하는 vitest 5건(`dashboard/src/utils/wsTicket.test.ts` — 이 호출의 URL 을 보는 테스트가 없었던 것이 이 결함이 살아남은 이유다). **이빨은 실제로 되돌려 확인했다**: 고침 전 소스에서 계약 **3 failed / 3 passed** · vitest **2 failed / 3 passed** · 증인 **exit 1**, 고침 후 계약 **6 passed** · vitest **5 passed** · 증인 **exit 0**. 증인은 **여섯 번 스스로 틀렸다**(쿼리 보간을 경로 param 으로 접고 · 래퍼 정의를 호출부로 세고 · 메서드를 GET 으로 박고 · C 축이 고정 문자열을 쳤다) — 자를 고친 기록을 docstring 에 남겼고, 증인이 저장소 `data/`(다른 서버의 sqlite)를 열 수 있던 것도 함께 막았다(상태·cwd 격리). **두 번째 후보 `ec76c7ce` 의 측정은 배치를 완주하고도 마감 직전에 멈췄다(F-44)** — 제품의 상대경로 상태 기본값이 cwd `src/` 프로세스의 `src/data/projects.json` 을 저장소 안에 만들어 작업 트리 지문을 후보에서 떨어뜨렸고(`e116d58d…` ≠ `f8cab12b…`), 무시 규칙 + 계약 5건(제품 런타임 0줄)으로 닫고 다시 선언했다. **판정 MOVED 없음**)** (010 이후 값의 전체 자리는 §5 판정 카드가 소유한다)
- **코드 후보 full SHA: `44d46c2eec5920b5b9b1e8d3da1975a5c0bcb57a`**(attempt-036 — **F-47 leftover `f47-invert-execution-trace-axe` 폐쇄**: `.is-primary` AA + Monaco aria · leftover **3**. 지문 `38c36a65…`. required **23** 유지. 선행 attempt-035 후보 `ae283604` / `ac0757cc…`.)
- 증거(최신부터): `.omo/evidence/commercial-reliability/CR-14/attempt-036/`(최신) · `attempt-035/` · `attempt-034/` · `attempt-033/` · `attempt-032/` · `attempt-031/` · `attempt-030/` · `attempt-029/` · `attempt-001/`, `attempt-002/`, `attempt-003/`, `attempt-004/`, `attempt-005/`, `attempt-006/`, `attempt-007/`, `attempt-008/`, `attempt-009/`, `attempt-010/`, `attempt-011/`, `attempt-012/`, `attempt-013/`, `attempt-014/`, `attempt-015/`, `attempt-016/`, `attempt-017/`, `attempt-018/`, `attempt-019/`, `attempt-020/`, `attempt-021/`, `attempt-022/`, `attempt-023/`, `attempt-024/`, `attempt-025/`, `attempt-026/`, `attempt-027/`, `attempt-028/`**
- **판정: NO-GO. GA 승인 없음. CR-14는 DONE이 아니다.**
- 출시 책임자 / 독립 검토자: **강병석 / 강병석**(2026-09-14 사용자 지시. 본인 겸직 — 제3자 독립성 미충족. **배정 ≠ GO/승인**. C14-08 검토 보고서·GO 기록 없음. README 는 지문 안이라 CR-12 계약의 `미배정` 표기를 이 커밋에서 고치지 않는다 — 실제 배정의 소유자는 이 카드다.)

이 문서는 계획서 §CR-14의 판정 규칙에 따라 작성한 **평가 산출물**이다. "NO-GO를 기록했다"는
사실은 GA 승인도, 구현 전체 완료도 아니다.

---


## EX 실행 진행 (2026-09-15)

- 대장: [CR14_EX_EXECUTION_LEDGER.md](./CR14_EX_EXECUTION_LEDGER.md)
- EX-01 로컬 PASS · OpenRouter 401 · EX-03 NOT_AVAILABLE · EX-04 이 macOS DONE · EX-05 soak FAIL · EX-02 PARTIAL · EX-06 DONE
- **판정 NO-GO 유지** · GA 승인 없음 · 후보 `b6003205` 불변

## C14-08 출시 책임자 기록 (2026-09-14) — 근거 있는 NO-GO

- 문서: [CR14_C14_08_RELEASE_OWNER_VERDICT.md](./CR14_C14_08_RELEASE_OWNER_VERDICT.md)
- 출시 책임자·겸직 검토자: **강병석**
- 후보 `b6003205` · 지문 `02349a8d…` **불변**
- 이유: EX-01~05 미실행 · C14-03/04/05/07 미충족 · 제3자 독립성 미충족
- **GA 승인 없음 · CR-14 DONE 아님 · 판정 NO-GO**

## attempt-040 요약 (2026-09-14) — REVIEW / NO-GO

- **닫힘**: C33-6 — PIN hermetic + 실 브라우저 `/api/auth/ws-ticket` → `?ticket=` + 소켓 생존 · fail-first 4401.
- **후보**: `b6003205365606407cadfd6cbb1c813110beef0f` · 지문 `02349a8d…` · required **23/23 PASS** · leftover **0건**.
- **증인**: `dashboard/e2e/tests/cr14-pin-ws-ticket.spec.ts` (`dashboard-e2e-witnesses`).
- **마감**: ATTEMPT_CLOSE PASS(기록 후 재확인).
- **하지 않음**: EX-01…06 **실행** · D-71 · APPROVE/GO · push.
- **담당 배정(2026-09-14)**: 출시 책임자·독립 code/security/QA 검토자·EX-01~06 전부 **강병석**. 배정 ≠ 실행 ≠ GO. 제3자 독립성 미충족(본인 겸직).
- **C14-08(2026-09-14)**: 출시 책임자 **근거 있는 NO-GO** 기록 — [CR14_C14_08_RELEASE_OWNER_VERDICT.md](./CR14_C14_08_RELEASE_OWNER_VERDICT.md). 독립성 겸직 잔여. CR-14 DONE 아님.
- 값의 자리는 §5 판정 카드.
- **판정 NO-GO 유지**.

## 담당 배정 (2026-09-14) — 배정 ≠ GO

사용자 지시: 사람·조직 축 역할을 **전부 강병석**으로 채운다. 이 절은 **이름만** 채운다. 검토·승인·soak·실 provider 는 아직 없다.

| 역할 | 담당 | 상태 |
|---|---|---|
| 출시 책임자 | 강병석 | 배정됨. GO 기록 없음. 판정 **NO-GO** 유지 |
| 독립 code 검토자 | 강병석 | 겸직. 제3자 독립성 미충족. 보고서 없음 |
| 독립 security 검토자 | 강병석 | 겸직. 제3자 독립성 미충족. 보고서 없음 |
| 독립 QA 검토자 | 강병석 | 겸직. 제3자 독립성 미충족. 보고서 없음 |
| EX-01 실 provider 자격·예산 | 강병석 | 담당만 배정. 자격·예산 미확보 |
| EX-02 모델/라이선스/개인정보·지원 승인 | 강병석 | 담당만 배정. 승인 기록 없음 |
| EX-03 이전 출시 artifact | 강병석 | 담당만 배정. artifact 미확보 |
| EX-04 OS sandbox 실측 | 강병석 | 담당만 배정. 실측 없음 |
| EX-05 8h soak 자원·일정 | 강병석 | 담당만 배정. 환경·임계값·일정 없음 |
| EX-06 GA 범위 축소 여부 | 강병석 | 담당만 배정. 변경 요청 없음 |

README 현재 상태 줄은 CR-12 계약이 `미배정` 문자열을 강제하고 `README.md` 는 코드 지문 **안**이다. 그 줄을 이 기록에서 고치면 후보 지문이 움직인다(F-22). **실제 배정의 소유자는 이 카드**다.

## attempt-039 요약 (2026-09-14)

- **재측정**: CR-12 `**현재**` 문구 정합(docs `af15580d`) 뒤 보고서 이어받기 거부 → 같은 지문으로 전 배치 재측정.


- **닫힘**: F-47 leftover `f47-capture-real-local-models`(EXTERNAL_HUB) — `AGK_SEED_LOCAL_HUB` hermetic 픽스처.
- **fail-first**: hermetic ambient 에서 hub 카드는 보이나 `실행 중` 배지 부재(orpheus status=`cached`) · chat selector 는 통과.
- **고침**: `LocalModelDiscovery.apply_hermetic_local_hub_seed` — 플래그 ON 일 때만 orpheus… 를 `running` 으로 올리거나 픽스처 삽입. ambient `HUB_SPEC_FILES` 소유. 생산 경로 불변.
- **후보**: `bbb308f8172c802419cb49a69970c1691d3c80ad` · 지문 `0b1a156f…` · required **23** 선언 · leftover **0건**.
- **측정**(attempt-039 · 후보 `bbb308f8…` · 지문 `0b1a156f…`): required 게이트 **23/23/0/0** · close 대기(카드 수치 채움) · ambient hub-seed **2 passed** · leftover **0**.
- **EX-01 주장 금지** — 게이트 커버리지 leftover 폐쇄. **판정 NO-GO 유지**.
- 값의 자리는 §5 판정 카드.

## attempt-038 요약 (2026-09-14)

- **닫힘**: F-47 leftover `f47-invert-compact-large-stream` — e2e 시드를 TaskEventSchema/`event()` 에 맞춤.
- **fail-first**: hermetic ambient 에서 `연결 오류` + `0 events` (`getByText(/1,?000 events/)` 비가시).
- **원인**: bigEvents bare shape(`type`/`timestamp`/`message`) → Zod 파싱 실패. 제품 compaction(1000) 정상.
- **고침**: 스키마 정합 시드 + 최신 `step 1002` title · GREP_INVERT 비움 · leftover **2→1**(EXTERNAL_HUB만) · D-68 불필요.
- **후보**: `4c3f8364db4f3011891604748b672d36d23d03ee` · 지문 `9362bdfc…` · required **23/23 PASS** · ATTEMPT_CLOSE PASS · leftover **1건**.
- 값의 자리는 §5 판정 카드.


## attempt-037 요약 (2026-09-14)

- **닫힘**: F-47 leftover `f47-invert-git-status-file-activity` — 코드 탭 + clean empty-state · GREP_INVERT 제거 · leftover **2건**
- **코드 후보**: `0cdcd60c` · 지문 `341d4f6c…` · 선언 `9984ee73` · required **23/23 PASS** · `tree_moved` 0
- **판정 MOVED 없음**. EXTERNAL_HUB·D-71·C33-6 하지 않음. **NO-GO 유지**.
- 값의 자리는 §5 판정 카드.

## attempt-036 갱신 (2026-09-14, 최신) — **F-47 leftover `f47-invert-execution-trace-axe` 폐쇄**

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
**현재의 후보는 `44d46c2eec5920b5b9b1e8d3da1975a5c0bcb57a` · 지문 `38c36a65…`** 이며, 선언
시점에 **후보 트리 == HEAD 트리 == 작업 트리(코드 스코프)** 임을 확인했다(`worktree_fingerprint(.)` ==
`tree_fingerprint_of_commit(44d46c2e)` == `38c36a6597a53bdd8e9cbc5bcaa94d6f563e5cd3841b8810188f77f92b4db4f5`).
required 게이트 수 **23 유지**(새 게이트 없음 — execution-trace 는 기존 `dashboard-e2e-ambient` 가 invert 없이 소유).
manifest sha256 `a40867c743a9…`. **재선언은 없다** — 이 attempt 의 첫 선언이 그 후보의 측정이다.
게이트 수치(PASS/FAIL/NOT_RUN)는 측정 뒤 보고서 집계로 채웠다: **23 / 23 / 0 / 0**.

### 무엇을 닫았나 (코드 후보 — 측정 전 요약)

- **닫힘**: `f47-invert-execution-trace-axe`
  - fail-first: axe color-contrast `.is-primary` `#fff` on themeStore `--accent-hover` `#917de8` (**3.33 < 4.5**); 375px만 통과.
  - 고침: `.approval-queue-actions .is-primary` 글자 `#080908`(액센트 면 유지; hover `#5b4bc4`+`#fff`) · `DiffViewer` Monaco `native-edit-context` aria-label DOM/MutationObserver · 스펙이 라벨 준비 후 axe · `dashboard_dist` 재번들(D-68) · GREP_INVERT 에서 해당 substring 제거.
  - 소유자: required `dashboard-e2e-ambient` (execution-trace 3 뷰포트, invert 없음). 프로브 3 passed.
- **남은 leftover 3건**(등록부 목록 정체성): `f47-capture-real-local-models` · `f47-invert-git-status-file-activity` · `f47-invert-compact-large-stream`
- **판정 MOVED 없음**. EXTERNAL_HUB·D-71·C33-6 하지 않음. **NO-GO 유지**.

### 측정 결과

- required **23 / 23 / 0 / 0** · 단일 지문 `38c36a65…` · HEAD `3c1bab9c`(docs 선언) · 후보 `44d46c2e`
- `tree_moved` 0 · 드리프트 0 · `dashboard-e2e-ambient` PASS(execution-trace invert 없음)
- python-tests **6391 passed / 13 skipped / 16 deselected** · dashboard-test **876 passed (86 files)**
- 지문 불변: 보고서·HEAD·후보·작업 트리 넷 동일(`attempt-036/logs/fingerprint-invariance.txt`)
- **판정 NO-GO 유지**(EX/C14-08 · leftover 3건)

---

## attempt-035 갱신 (2026-09-14) — **F-47 leftover 에 정직한 소유자/계수** (disclosure hermetic 폐쇄)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
**현재의 후보는 `ae28360448f442e1194e1e93fcabf9e51bc8aada` · 지문 `ac0757cc…`** 이며, 선언
시점에 **후보 트리 == HEAD 트리 == 작업 트리(코드 스코프)** 임을 확인했다(`worktree_fingerprint(.)` ==
`tree_fingerprint_of_commit(ae283604)` == `ac0757ccbc0b63b3b35c1dc28c71c32934c977f0e6d724227e7de73cd10ce13c`).
required 게이트 수 **23 유지**(새 게이트 없음 — disclosure 는 기존 `dashboard-e2e-ambient` 시드 단계로 흡수).
**재선언은 없다** — 이 attempt 의 첫 선언이 그 후보의 측정이다. 게이트 수치(PASS/FAIL/NOT_RUN)는
측정 뒤 보고서 집계로만 채운다(지금은 inventory만 선언: **23 / 0 / 0 / 23**).

### 무엇을 닫았나 / 셌나 (코드 후보 — 측정 전 요약)

- **닫힘 (값싼 하네스)**: `capture-disclosure-*` Vite `:5173` 하드코드 → hermetic
  `page.goto('/settings')` + `AGK_SEED_LEVEL=healthy|exhausted` 시드별 서버.
  소유자: required `dashboard-e2e-ambient` (`DISCLOSURE_SPEC_FILES`).
  실측(측정 전 프로브): healthy/exhausted 스펙 각 exit 0 · ambient 게이트 main 11 + disclosure 2 = exit 0.
- **센 leftover (소유 불가 증명 · 목록 정체성)**: 등록부 `scripts/cr14_f47_leftover_register.json`
  · 계약 `tests/test_cr14_f47_leftover_inventory_contract.py`
  - `f47-capture-real-local-models` (EXTERNAL_HUB)
  - `f47-invert-git-status-file-activity` (PRODUCT_FLAKE)
  - `f47-invert-compact-large-stream` (PRODUCT_FLAKE)
  - `f47-invert-execution-trace-axe` (PRODUCT_FLAKE — axe color-contrast on `.is-primary`)
- **판정 MOVED 없음**(EX/C14-08 미해결). D-71 · C33-6 하지 않았다. **NO-GO 유지**.

### 측정 결과

- required **23 / 23 / 0 / 0** · 단일 지문 `ac0757cc…` · HEAD `0958c861`(docs 선언) · 후보 `ae283604`
- `tree_moved` 0 · 드리프트 0 · ambient 게이트(disclosure 시드 포함) PASS
- leftover 계약·ambient 계약 타깃 15 passed(측정 전) · 판정 **NO-GO** 유지

---

## attempt-034 갱신 (2026-09-14) — **ambient 백엔드 스펙에 required-gate 소유자를 줬다** (F-45 · F-46)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
**현재의 후보는 `b1f3af5a7f9dda413bd4d8ff82ba5ca5b3d6ba2a` · 지문 `e4d15526…`** 이며, 선언
시점에 **후보 트리 == HEAD 트리 == 작업 트리**임을 확인했다(`worktree_fingerprint(.)` ==
`tree_fingerprint_of_commit(b1f3af5a)` == `e4d15526…`). **게이트 목록이 바뀌었다**(required
**22 → 23** — 새 게이트 `dashboard-e2e-ambient`). manifest sha256 `7343edfa…`.
**재선언은 없다** — 이 attempt 의 첫 선언이 그 후보의 측정이다. 게이트 수치(PASS/FAIL/NOT_RUN)는
측정 뒤 보고서 집계로만 채운다(지금은 inventory만 선언: **23 / 0 / 0 / 23**).

### 무엇을 닫았나 (코드 후보 — 측정 전 요약)

- **F-45 (제품·하네스)**: hermetic `startNoAuthServer` 가 PIN 잠금을 풀지 않았고(`AGK_SEC_DEV_NO_PIN_ALLOW`),
  훅 버스가 공유 `vault_data/hooks` 에 묶여 주입 이벤트가 침묵했으며, hermetic 임의 포트 Origin 이
  `ws_origin` allowlist 에 없어 `/v1/ws/events` 가 즉시 끊겼다(`frames=0`). 고침:
  `AGK_HOOK_VAULT_DIR` 오버라이드(서버) · NO_PIN + 훅 vault/`AGK_PATH_*` 격리 + **포트 사전 할당** +
  `AGK_CORS_ORIGINS` 에 그 Origin(헬퍼) · 스펙은 `AGK_HOOK_VAULT_DIR` 우선.
- **F-46 (게이트)**: required `dashboard-e2e-ambient` — 격리 서버 기동 → 소유 스펙
  (`task-execution`·`ws-contract-e2e`·`file-explorer`·`capture-desktop-layout`·`capture-model-selection`)
  + `--grep-invert` + `--reporter=list` → 프로세스 그룹 종료. `--skip-server` 는 닫힌 포트로 돌려
  **exit 1**(이빨). 계약 `tests/test_cr14_ambient_backend_gate_contract.py`.
- **의도적으로 밖(F-47)**: `capture-disclosure-*`(:5173 하드코드) · `capture-real-local-models`(실 허브) ·
  invert 대상(제품/환경 flake — ambient 부재가 아님).
- **판정 MOVED 없음**(EX/C14-08 미해결). D-71 상대경로 마이그레이션은 하지 않았다.

### 측정 결과

커밋된 후보 `b1f3af5a7f9dda413bd4d8ff82ba5ca5b3d6ba2a` · **단일 지문 `e4d15526…`** 에서 required gate **23/23** 을 완주했다
(되돌리기 0회 · `tree_moved` **0건** · 드리프트 **0** · **재선언은 코드 스코프에 없음** — CR-12 문구 docs 수정으로
HEAD 만 움직였고 지문은 불변이라 보고서를 지우고 같은 지문에서 재측정했다).
배치: fast 20/20 → tests 1/1(python-tests **6383/13/16**) → heavy 2/2.
**새 게이트 `dashboard-e2e-ambient` 11 passed / 24.6s**. 측정 HEAD `587ee5bc`(docs 전용 위 후보).
수치의 자리는 §5 판정 카드다.

---

## attempt-033 갱신 (2026-09-14) — **화면이 보내는 경로는 서버가 서는 경로여야 한다** (F-43 — 제품 런타임 결함) · **런타임 상태는 코드 스코프 밖에 있다** (F-44 — 측정 중 발견)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
**현재의 후보는 `c66706ee121604dc1de8ed0362b4b9c427765137` · 지문 `1873d2c7…`** 이며, 선언
시점에 **후보 트리 == HEAD 트리 == 작업 트리**임을 확인했다(이번에는 `worktree_fingerprint(.)` 도
같다 — `vault_data` 가 가리키는 커밋이 다시 같아졌다: F-13). **게이트 목록은 바뀌지 않았다**(required
**22** 그대로 — F-42 의 인벤토리를 쓴다).

### 재선언 (측정 **전** — F-34 가 먼저 물었다)

이 attempt 의 첫 선언은 후보 `b11ff74f`(지문 `03a7db8d…`)이었고, 그 후보의 **첫 fast 배치가
`dashboard-build` 에서 멈췄다** — 게이트가 **exit 0** 으로 끝나면서 추적 번들
(`src/antigravity_k/dashboard_dist/`) **59개 경로를 다시 썼고**, F-34 의 검사가 그것을 `tree_moved`
로 적어 실행 전체를 exit 1 로 끝냈다(보고서 요약: **passed 18 / failed 1 / required_failed 1 /
total 19**).

**그 실패는 옳다.** 추적 번들은 서버가 서빙하는 출하물이고(F-01), 소스만 고치고 번들을 안 만들면
화면에는 고치기 전의 UI 가 나간다. 그래서 이 저장소의 규율대로 **번들을 후보 안으로** 가져왔다 —
후보의 소스에서 다시 빌드해(결정성 확인: 두 번 빌드한 결과가 **바이트 동일**) `ec76c7ce` 로
커밋했다. 그것이 코드를 옮겼으므로 **측정 전에 다시 선언한다.** 재선언의 근거는 D-52 의 순서
(선언 → 측정)이지 실패를 덮는 것이 아니다 — 첫 fast 배치의 18/19 기록은 §5 카드의
`required gate` 줄에 남긴다.

### 재선언, 두 번째 (측정 **전** — 이번엔 측정 트리가 흔들렸다: F-44)

> **측정 완료(2026-09-14)**: 세 번째 선언(후보 `c66706ee` · 지문 `1873d2c7…`)에서 required
> **22 / 22 / 0 / 0** · `tree_moved` 0건 · 드리프트 0 · 마감 검사 **PASS** — 네 값(보고서·HEAD·후보·
> 작업 트리)이 같은 지문이다(`logs/fingerprint-invariance.txt`). 수치의 자리는 §5 판정 카드다.
> **런타임 상태는 이번 측정 내내 스코프 밖에 있었다** — 22개 게이트가 서버를 띄우고 번들을
> 다시 쓰는 동안 작업 트리 지문이 한 번도 흔들리지 않은 것이 그 증거다.

두 번째 후보 `ec76c7ce`의 측정은 **배치를 완주하고도** 마감 직전에 멈출 뻔했다 — 코드가 아니라
**측정 트리**가 후보에서 떨어져 있었다. `python-tests` 배치가 초록으로 끝난 뒤 보고서를 검사하니
작업 트리에만 있는 경로가 하나 있었다:

    ONLY IN WORKTREE: ['src/data/projects.json']   count 1
    worktree_fingerprint(.)              = e116d58d…
    tree_fingerprint_of_commit(ec76c7ce) = f8cab12b…

원인은 제품의 **상대경로 기본값**이다. `project_registry.py` 의
`_DEFAULT_STORAGE_PATH = Path("data/projects.json")` 는 cwd 로 풀리므로, cwd 가 `src/` 인 프로세스
(패키지를 소스 트리에서 직접 `-m uvicorn` 으로 띄우면 자연스럽다)는 저장소 안에
`src/data/projects.json` 을 만들고, 게이트 지문은 무시되지 않은 미추적 파일도 스코프로 읽는다.
루트의 같은 파일은 이미 무시되고 있었다(`.gitignore` 175행) — 빠진 것은 **`src/` cwd 루트**뿐이다.

고침은 그 루트의 무시 규칙 두 줄(`src/data/projects.json`·`.lock`)과 그 규칙을 소유하는 계약
`tests/test_cr14_runtime_state_scope_contract.py` **5건**이다(제품 소스에서 기본 경로 읽기 ·
이유가 있는 cwd 루트별 무시 · **게이트의 함수로** 스코프 측정 · 이빨 — 임시 저장소에서 규칙을 떼면
같은 파일이 다시 스코프에 들어온다). **제품 런타임 코드 0줄.** 상대경로 기본값이라는 설계 자체는
그대로 둔다 — 기본값을 저장소 밖이나 설정에 묶는 근본 고침은 제품 동작을 바꾸므로 **별도 attempt**
의 몫이다(계약 docstring 이 그 경계를 명시한다). 그 수정이 코드를 옮겼으므로 **측정 전에 다시
선언한다**(세 번째 선언 — 근거는 같은 D-52 순서다). 증인
`attempt-033/repro/f44_runtime_state_scope_witness.py`(A 결함 재현 · B 이 저장소의 실제 규칙 ·
C 이빨)는 고침 후 **exit 0**이고, A 축이 무시 규칙 없는 임시 저장소에서 그 사건을 재현한다.

### 무엇을 하려다 무엇을 먼저 만났나

attempt-032 는 자기 한계로 이 문장을 남겼다: *"ambient 백엔드가 필요한 슬라이스는 그대로 게이트
밖이다"* — 그 자리를 게이트로 만들려면 **서버를 세우는 단계**가 필요하다. 그래서 증인은 서버를
띄우는 일부터 시작했고, 그 첫 걸음에서 **재려던 것과 다른 것이 먼저 나왔다**: 대시보드가 서버에
보내는 경로 두 개가 **서버에 존재하지 않았다**.

### 측정된 사실 (고침 전)

`dashboard/src/api/client.ts` 의 `apiRequest(endpoint)` 는 `requestJson(`${API_BASE}${endpoint}` …)`
로 **'/v1'을 앞에 붙인다**. 그런데 두 호출부가 **이미 자기 namespace 를 가진 경로**를 그 함수에
넘겼다: `askAgent` → `apiRequest('/api/agent/ask')`, `fetchWsTicket` → `apiRequest('/auth/ws-ticket')`.
실효 경로는 `/v1/api/agent/ask` · `/v1/auth/ws-ticket` 이고 서버 라우트 표에는 **`/v1/api/*` 도
`/v1/auth/*` 도 없다**(58 namespace 중 둘이 아예 부재 · 235 패밀리). 현재 트리에서 직접 띄운 서버에
대고 재면 정본 `POST /api/auth/ws-ticket` 은 **200 + ticket**, 실효 경로는 **405**(SPA fallback)다.

**왜 아무도 못 봤나 — 이 발견의 핵심**: 접두사가 **호출부의 리터럴에 없다.** 소스에
`/v1/auth/ws-ticket` 이라는 문자열이 없으므로 `grep -r '/v1/auth' dashboard/src` 는 0건이고,
**소스 리터럴만** 모아 서버 라우트 표와 대조하는 검사도 이 자리를 **건너뛴다**(증인의 A 축이
그 눈먼 자리를 그대로 재현한다 — 리터럴로는 보이지 않는 실효 경로가 3종, 그중 2종이 결함이다).
문서 두 곳도 서로 다른 것을 말하고 있었다: `docs/13_COMMERCIAL_GA_100_PROGRESS.md` 는 SEC-03 을
`POST /v1/auth/ws-ticket` 이라 적었고, `wsTicket.ts` 의 docstring 은 `/api/auth/ws-ticket` 이라 적었다.

**영향**: `fetchWsTicket` 은 실패를 `catch { return null }` 로 **삼킨다**. ticket 없이 연결하면 WS
게이트(`routes/session_state.py`)는 `open_loopback` 일 때만 통과하므로 — 즉 **PIN 이 설정된
(=protected) 배포에서는 이벤트 스트림이 4401 로 거절되고 3초마다 무한 재시도**한다. 로컬 dev
익명 모드(`AGK_SEC_DEV_NO_PIN_ALLOW`)가 그 실패를 가린다.

### 고침의 자리 (제품 런타임 코드 2줄)

전체 경로를 그대로 받는 `apiRequestPath` 로 바꿨다 — `loginWithAccessPin` 이 이미 따르던 규약이다
(인증 라우트는 `/api/auth/*`, 코어 라우트는 `/v1/*`). **소유자는 둘로 나눴다**: 서버의 라우트 표와
대조하는 pytest 계약 `tests/test_cr14_client_path_contract.py`(6건)가 **래퍼를 해석한** 실효 경로의
namespace 가 서버에 있는지를 재고, 단위 `dashboard/src/utils/wsTicket.test.ts`(5건)가 **정확한 URL**을
고정한다 — 이 호출의 URL 을 보는 테스트가 하나도 없었던 것이 이 결함이 살아남은 이유였다
(`useEventWebSocket.test.tsx` 는 `fetchWsTicket` 자체를 mock 한다).

### 이 attempt 가 스스로 남긴 정직 기록

- **증인의 자(ruler)가 여섯 번 틀렸다** — 쿼리 보간을 경로 param 으로 접고, 래퍼 **정의 자체**를
  호출부로 세고, `apiRequestPath` 분기의 **메서드를 GET 으로 박고**, C 축이 **고정 문자열**(고침 전
  경로)을 쳤다. 매번 자를 고치고 그 이유를 증인 docstring 에 남겼다. 계약의 마지막 조항은
  "**리터럴 전용 검사로는 그 자리가 보이지 않는다**"는 사실 자체를 고정한다.
- **증인이 저장소를 건드릴 수 있었다**: 서버의 `data_dir` 기본값이 **상대경로**라 격리 없이 띄우면
  저장소 `data/`(다른 서버가 쓰는 sqlite·tasks.db)를 열 수 있었다 — 이 저장소가 F-34 에서 금지한
  부류다. 증인은 이제 상태(`AGK_PATH_DATA_DIR`·`AGK_PATH_LOGS_DIR`·`AGK_PATH_PROJECT_ROOT`)와
  **cwd** 를 임시 디렉터리로 돌리고, 실행 뒤 트리에 아무것도 쓰지 않음을 확인했다.
- **고침 전 측정은 pristine 트리에서 떴다**: 후보 커밋이 아직 없을 때의 고침 전 값은
  `git worktree add --detach /tmp/… HEAD` 로 만든 **사본 트리**에서 잰 것이다(작업 트리를 되돌리지
  않았다). 이빨도 같은 방식(스크래치 트리)으로 확인했다.

## attempt-032 갱신 (2026-09-14) — **브라우저 증인에게 게이트 소유자를 줬다** (F-42 — required 21 → **22**)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `45918a51272055340becae53fa759800c6ae387a` · 지문 `5a8950a1…` 이며, 선언 시점에
**후보 트리 == 작업 트리**임을 확인했다. **이 attempt 는 게이트 목록을 바꿨으므로**
manifest sha256 도 `86c40edc…` → `22ec46c2…` 로 움직였다(마감 검사가 그 축도 대조한다 — F-26).
**재선언은 없다** — 이 attempt 의 첫 선언이 그 후보의 측정이다.

### 무엇을 물었나 — attempt-030·031 이 **경계 문서에 적어 둔 자기 한계**

attempt-030 은 경계 문서 §2-6 을, attempt-031 은 §2-7 을 쓰면서 같은 문장을 남겼다:

> 실 브라우저 증인 셋(`cr14-crash-restart-surface` · `cr14-task-submit-contract` ·
> `cr14-retry-escape-hatch`)은 모두 **수동**이고, required 21개 중 어느 것도 이들을 돌리지 않는다.
> … **게이트 소유를 먼저 정해야 한다**(새 게이트 + 등록부·manifest·계약을 함께 갱신하거나,
> 수동 증인으로 남기고 이 문서가 계속 소유). **현재는 후자다.**

그 문장은 **정직했지만, 다음 attempt 가 없으면 영원히 참**이다. 이 attempt 가 그 후자를
**전자**로 바꾸면서, 그 과정에서 그 문장이 **셋만의 이야기가 아니라는 것**을 먼저 쟀다.

### 먼저 센 것 — 증인 패밀리 전체의 커버리지(주장이 아니라 계산)

커버리지를 **manifest 의 선택자 × 실제 파일**로 계산했다(손으로 적은 목록이 아니다):

- **고침 전**(그 게이트 항목을 뺀 manifest 사본) → `dashboard/e2e/tests/cr*.spec.ts`
  **9파일 29건**의 소유자가 **0** 이다. 즉 경계 문서가 "브라우저 슬라이스"라고 부른 그 자리에는
  **어떤 required 게이트도 없었다**.
- **고침 후**(실제 manifest) → **9/9**. 게이트를 하나 더하지 않고 **이름 규칙**으로 덮으므로,
  증인을 새로 만든 사람도 자동으로 그 안에 들어온다.
- **그 패밀리는 게이트가 될 수 있었다**: ambient 백엔드 없이 `29 passed(43.5s)`.
- **누가 이들을 돌리고 있었나(아무도)**: `accessibility-e2e` 는 `accessibility.spec.ts` **한 파일**만
  돌리고, CI 의 full suite 는 `main` push/PR 에서만 돌며 **게이트 절차·주간·릴리스 어느 것도**
  그것을 부르지 않는다. 그래서 F-35·F-36·F-37·F-38·F-39·F-41 을 찾아낸 증인들이 돌아간 자리는
  **사람이 기억해서 돌린 자리**뿐이었다.

### 고침의 자리 — 목록이 아니라 **전수성**, 그리고 **경계는 지우지 않는다**

새 required 게이트 `dashboard-e2e-witnesses` 가 그 패밀리를 돈다. 선택자는 파일 목록이 아니라
**이름 규칙**(`e2e/tests/cr\d+-`)이다 — 세어 둔 목록은 하나를 빼고 하나를 넣어도 통과한다
(F-21 이 개수 고정을 목록 고정으로 바꾼 것과 같은 이유). 그리고 `--project=chromium
--reporter=list` 를 **게이트 명령이 직접** 들고 있다: 등록부가 스킵의 **귀속 가능성**을 그
리포터에 걸어 두었으므로(attempt-024), 설정을 바꾸는 사람이 그 게이트의 스킵을 **익명**으로
만들 수 없다.

**삼키지 않는 경계도 함께 고정했다.** ambient 백엔드가 필요한 스펙(`task-execution` ·
`ws-contract-e2e` — CLI 로 서버를 띄우는 CI job 의 슬라이스)은 이 게이트에 **넣지 않았다**:
게이트에는 그 서버를 세우는 단계가 없으므로 넣으면 게이트가 게이트 환경에서 **항상 빨개지고**,
사람은 게이트를 끄는 쪽을 고른다. 계약이 "선택자가 그들을 삼키지 않는가"를 재고, 증인은 그
슬라이스가 **여전히 어느 required 게이트에도 없다**는 사실을 **소리 내어 센다**(지우지 않는다).

### 계약과 증인

- 계약 `tests/test_cr14_browser_witness_gate_contract.py` **5건** — 게이트가 required 이고
  프로젝트·리포터를 명령에서 고정 · 증인 파일 **전수**가 선택자에 걸린다 · 선택자가 ambient
  스펙을 삼키지 않는다 · **이빨**(가족 이름은 통과하고 가족 밖 이름은 증인으로 세지 않는다 —
  목록 고정으로 퇴화하면 그 조항이 운다) · 등록부 분류(playwright·per_test·close_check).
- 그 계약의 **첫 판본은 자기가 틀렸다**: 파일 **이름**에 정규식을 물렸는데 playwright 는
  **경로 전체**에 문다 — 계약이 거짓 실패했고, 고친 것은 자다(그 사실을 계약 docstring 에 남겼다).
- **이빨 셋(실측)**: ① 게이트를 manifest 에서 **지우면** 계약 **4 failed** ② `required` 를
  **false 로 강등**하면 **1 failed**(이빨은 "required 라는 말"에 물려 있다) ③ 가족 이름으로
  **일부로 실패하는 증인**(`cr99-…`)을 만들면 게이트가 **exit 1 로 그 파일의 이름을 대며**
  멈춘다 — 그 파일은 **A 의 세계에서 아무도 돌리지 않았다**(여섯 축 중 A/C). 실험용 파일은 즉시
  지웠고 **지문이 원래 값으로 돌아오는지**까지 확인했다(`logs/f42-witness.txt` ·
  `logs/f42-contract-teeth.txt`).
- 게이트를 늘렸으므로 **인벤토리 계약**(`tests/test_cr14_candidate_evidence.py` 의 pinned 목록)과
  **스킵 등록부**(`scripts/gate_skip_register.json` — playwright·per_test·close_check)를 함께
  적었다. attempt-024 가 세운 규율("게이트를 추가하면 분류도 적어야 한다")이 그대로 작동한다.

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

- 바꾼 것: **게이트 목록**(required 21 → 22) · 게이트 실행기와 무관한 **새 계약 1파일** ·
  등록부의 분류 한 줄 · 인벤토리 계약의 pinned 목록. 그래서 **`21/21` 은 이 후보부터 `22/22`** 다.
- 바꾸지 않은 것: **제품 런타임 코드 0줄** · 기존 21개 게이트의 명령·타임아웃·required 여부
  **불변** · 제품의 행동·표면·권한 경계 **불변** · **판정 MOVED 없음**.

### 한계 — 이 attempt 가 **재지 않은** 것

- **ambient 백엔드 슬라이스는 그대로 게이트 밖**이다(`task-execution`·`ws-contract-e2e`·
  `file-explorer`·`capture-*` — 실측: ambient 없이 full suite 를 돌리면 **12건 실패**). 그 자리를
  게이트로 만들려면 **서버를 세우는 단계**가 게이트에 필요하고(CI 의 full-suite job 이 하는 일),
  그것은 이 attempt 의 범위가 아니다.
- **새 게이트가 재는 것은 "그 증인이 통과한다"까지다** — 증인이 옳은 질문을 하는지는 계속 사람이
  정한다(계약은 커버리지만 소유한다).
- **게이트 수가 늘어난 만큼 `fast` 배치가 길어졌다**(실측 약 45초). 상한(`timeout_seconds` 2400)에
  비하면 여유가 크지만 **공짜는 아니다**.
- **CI 러너에서의 22/22 는 여전히 러너만이 답한다**(R-14 — 로컬은 GitHub Actions 를 돌릴 수 없다).

### 측정 결과

커밋된 후보 `45918a51` · **단일 지문 `5a8950a1…`** 에서 required gate **22개를 완주**했다
(되돌리기 0회 · `tree_moved` **0건** · 드리프트 **0** · **재선언 없음**). 배치:

  - `--stage fast` → **19/19 exit 0** — 목록에 새 게이트가 있고 `44.7s` 로 통과했다
    (`dashboard-e2e-witnesses` → `29 passed in 9 files (44.1s)`, 스킵 0건).
  - `--stage tests` → **python-tests 6365 passed / 13 skipped / 16 deselected**(587.16s) —
    attempt-031 의 6360 에서 **+5 = 이 attempt 의 새 계약 5건**이고(정확히 맞는다),
    **스킵은 13 → 13 불변**이다(이 attempt 는 스킵을 건드리지 않았다).
  - `--stage heavy` → **docker-build 225.0s · clean-machine-runtime 42.2s**(익스포트 **3031 파일** ·
    `SKIP` 행 **0건**).
  - `--stage close` → **`ATTEMPT_CLOSE: PASS` exit 0**. 기록 커밋 뒤에도 같은 검사가 PASS 였다.

**대시보드 단위 테스트는 871 passed(85 files, 스킵 0건)** — attempt-031 과 같다(이 attempt 의
계약은 **pytest 쪽**이고, 게이트가 도는 playwright 스펙은 **새로 만들지 않았다**: 기존 증인 29건을
돌리는 자리가 새로 생겼을 뿐이다). 실행 **뒤** 지문을 다시 재어 보고서·HEAD 트리·후보 트리·작업
트리 **넷이 모두 `5a8950a1…`** 임을 확인했고(후보..HEAD 코드 스코프 변경 **0줄**),
그 뒤 작업 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** 이다.

  - **정직 기록 — 선언 커밋이 측정 문장을 미리 담았다**: 이 attempt 의 선언 커밋(`bb389737`)이
    §5 카드의 지문 자리에 **"측정 뒤에도 같은 값이었고 네 자리가 모두 이 값이다"** 를 **측정 전에**
    적었다. 그 문장은 측정 뒤 **참이 됐고**(`attempt-032/logs/fingerprint-invariance.txt`),
    게이트 수치 줄은 **일부러 비워 두었다**(손으로 적은 수치 금지). 그래도 그 문장을 미리 적은 것은
    **순서 규율(D-52)에 어긋난다** — 이 attempt 는 그것을 숨기지 않고 적는다(다음 attempt 는 그
    자리를 "측정 뒤 채운다"로 두어야 한다).
  - **이 attempt 가 재지 않은 것**: ambient 백엔드 슬라이스(`task-execution`·`ws-contract-e2e`)는
    여전히 required 게이트 **밖**이다 — 새 게이트가 그 스펙들을 **삼키지 않는지**는 계약이 재고,
    그들이 **어느 required 게이트에도 없다**는 사실은 증인이 **소리 내어 센다**(지우지 않았다).

---

## attempt-031 갱신 (2026-09-14) — **탈출구는 정말 마지막 수단인가** (F-41 후보 — **측정으로 반증**)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `2b4a198b…` · 지문 `7461ae3d…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변 —
게이트 목록·명령은 attempt-026 이래 그대로다). **재선언은 없다**: 이 attempt 의 첫 선언이 그
후보의 측정이다. 측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — attempt-030 이 **자기 한계로 적은 그 문장**

attempt-030 은 F-39(재연결 뒤 목록 재조회)를 닫으면서 이렇게 적었다: *"**M3(수동 탈출구) 경로는 이
실행에서 발화하지 않았다**"*. 그 문장은 정직했지만 **재지 않은 질문을 남겼다** — 화면이 스스로
포기한 뒤 사용자가 누르는 마지막 수단이 새 사실을 배우는가. 이 attempt 가 그 질문을 잰다:

> 연결을 포기한 화면의 **'다시 연결'** 은 새 사실을 배우는가 — 아니면 크래시 전 스냅샷을 "현재"라고
> 말한 채 사용자를 막다른 길에 남기는가?

### 먼저 센 것 — 증인 · **대조군** · **이빨**

  - **증인(제품 경로)** `dashboard/e2e/tests/cr14-retry-escape-hatch.spec.ts` — 실 서버 + 실제 PIN
    로그인 + 제품의 제출 폼. 화면이 **스스로 포기할 때까지 재기동하지 않고** 기다린 뒤(자동 재연결
    3회를 소진해야 M3 가 발화한다 — 그것이 이 질문의 전제다) 같은 포트·같은 상태 디렉터리로
    재기동한다. 여섯 축: **V1** 포기 + 탈출구 제공 · **V1b** 서버가 **없는 동안** 눌러도 막다른 길이
    되지 않는다 · **V2** 행이 서버의 현재 사실과 같아진다 · **V3** 연결 라벨이 정착한다 · **V4** 세션이
    살아 있다 · **V5** **두 번째** 크래시·재기동에서도 다시 통한다.
  - **결과 — 답은 "예"다**(`logs/f41-browser-after.txt`, **exit 0**): 연결 라벨 이력
    `["연결됨","재연결 중","연결 오류"]` → 탈출구를 누르면 `["연결 오류","연결됨"]`, 행은 서버와
    같은 **"실행 중단(소유 프로세스 종료) — 재개 가능"**. 서버가 없는 동안 눌러도 화면은
    `연결 오류` + 탈출구로 **남았고**(구제 수단을 잃지 않는다), **두 번째** 사이클도 같은 값이었다.
  - **대조군**(`logs/f41-browser-control-pref39.txt`) — 같은 증인을 **F-39 고침 이전 트리**
    (`/tmp/agk-f39-base` = `HEAD^` 스냅숏 + 도구만 복사)에서 돌려도 **exit 0** 이다. 즉 이 축은
    attempt-030 **이전에도 참**이었다: **결함이 아니라 재지 않은 경로**였고, attempt-030 이 닫은
    결함은 **자동** 재연결 경로에만 있었다(`retry` 는 처음부터 `reloadVersion` 을 올렸고 그것이
    **목록 이펙트의 의존성**이다).
  - **이빨**(`logs/f41-browser-teeth.txt` · `logs/f41-vitest-teeth.txt`) — 스크래치 트리
    `/tmp/agk-f41-teeth` 에서 `retry` 를 `() => undefined` 로 무력화하고 그 트리의 번들을
    `vite build` 로 다시 만든 뒤 돌리면 증인 **exit 1(위반 4건)** — `M3-1`·`M3-2` 모두에서 화면이
    크래시 전 스냅샷(`running` · 재개 없음)을 그대로 둔 채 `연결 오류` 에 머물렀다. 단위 계약도
    같은 트리에서 **1 failed / 3 passed** 다. 즉 이 증인은 **작동하는 탈출구와 무력한 탈출구를
    구별한다**.
  - **자를 먼저 의심했다(정직 기록)**: 첫 두 실행의 실패는 **제품이 아니라 자**의 결함이었다 —
    ① 2회차에는 **배울 것이 없었다**(두 번째 크래시가 서버의 사실을 바꾸지 않아 화면의 행이 이미
    서버와 같았고, 그래서 판정이 **전이 중**의 라벨을 읽었다) ② 연결 라벨을 **전이 중**에 읽어
    `불러오는 중` 을 위반으로 셌다. 2회차는 **새 태스크를 제출**해 낡은 스냅샷을 만들고, 라벨은
    **오류를 떠난 뒤** 정착할 때까지 기다린 뒤에 읽는다.
  - **계약(단위)** `dashboard/src/features/task-execution/useTaskExecutionEvents.test.ts` 에 **1건**
    추가(3 → 4): 자동 재연결 3회가 모두 실패해 화면이 포기한 상태를 만들되 **그 동안 목록 재조회도
    실패**하게 해 화면이 **크래시 전 스냅샷**을 들고 있게 한 뒤, `retry()` 뒤에 ① 목록을 **다시
    읽는다** ② 스트림을 **다시 시작한다** ③ 반영된 값이 서버의 새 사실이다. 고침 트리에서
    **4 passed**(`logs/f41-vitest-after.txt`) — 스텁이 즉시 resolve 하므로 **연결 라벨은 여기서
    재지 않는다**(커밋 뒤의 `loading` 타이머가 정착 상태를 덮어쓴다: 같은 파일의 F-39 계약이 그
    이유를 적는다). 라벨의 전이는 실브라우저 증인이 잰다.

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

  - 바꾼 것: 증인 **1파일 신규** + 단위 계약 **1건**. **제품 런타임 코드는 0줄**이다 — 이 attempt 는
    제품을 고치지 않는다(고칠 결함을 찾지 못했다).
  - 대신 **암묵적 의존에 소유자를 준다**: 탈출구가 목록을 다시 읽는 것은 `retry` 가 올리는
    `reloadVersion` 이 **목록 이펙트의 의존성**이기 때문인데, 그 사실은 지금까지 어떤 계약도 재지
    않았다. 리팩터가 그 의존을 끊으면 계약이 **먼저** 실패한다.
  - 바꾸지 **않은** 것: **서버·화면 코드 0줄** · 권한 경계 · 저장된 태스크 상태 · **판정**(여전히
    NO-GO — 남은 차단 사유는 사람·조직 축이다).

### 한계 — 이 attempt 가 **재지 않은** 것

  - **다른 주인(다른 클라이언트)** 이 만든 변화는 자극이 아니다 — 목록의 신선도는 재연결과 사용자의
    행동에서만 갱신된다는 **경계**는 그대로다(경계 문서가 소유한다).
  - **모델 실행 완주**는 재지 않았다(실 provider — EX-01). 태스크가 `running` 으로 남는 것이 정상
    입력이다.
  - **다중 호스트·다중 프로세스**(전달 IPC · `resuming` 주인 사망 타이밍)는 그대로다.
  - **이 증인도 어느 required 게이트도 돌리지 않는다** — 경계 문서 §2-6/§2-7 이 그 사실을 소유한다.

### 측정 결과

커밋된 후보 `2b4a198b` · **단일 지문 `7461ae3d…`** 에서 required gate **21개를 한 번에 완주**했다(되돌리기
0회 · `tree_moved` 게이트 **0건** · 드리프트 **0** · **선언한 첫 후보가 그대로 측정됐고 재선언이 없다**).
배치 셋이 별개 프로세스로 스스로 이어받았다(보고서 정체성 = 같은 후보·같은 manifest — F-26):

  - `--stage fast` → **18/18 exit 0** (python-benchmark 16 · dashboard-test 871 passed(85 files) ·
    master-e2e 6/6 · api-e2e 9 · accessibility-e2e 35 · 의존성 감사 high 0)
  - `--stage tests` → **python-tests 6360 passed / 13 skipped / 16 deselected**(561.86s) —
    **attempt-030 과 같은 수치**이고 **스킵은 13 → 13** 이다(이 attempt 의 계약은 대시보드 쪽이다)
  - `--stage heavy` → **docker-build 30.8s · clean-machine-runtime 41.9s**(익스포트 3030 파일 · `SKIP` 행 0건)
  - `--stage close` → **`ATTEMPT_CLOSE: PASS`** — 선언한 초록이 증거 파일로 뒷받침된다(첫 시도 통과)

**대시보드 테스트는 871 passed(85 files, 스킵 0건) = +1** 이다(신규 계약 1건, 파일 수 불변). 실행 **뒤**
지문을 다시 재어 보고서·HEAD 트리·후보 트리·작업 트리 **넷이 모두 `7461ae3d…`** 임을 확인했고(후보..HEAD
코드 스코프 변경 **0줄**), 그 뒤 작업 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist`
드리프트 **0** 이다.

  - **끊긴 실행을 숨기지 않는다**: 첫 `--stage tests` 실행은 **도구 타임아웃(120초)과 함께 부모 셸이 죽어
    중단**됐고 결과가 없다 — 그 로그는 **증거로 쓰지 않았고**, 사실만 장부(`logs/gate-batches.txt`·
    `commands.jsonl`)에 남긴다(결과 없는 파일을 증거로 세우면 "실행됐다"로 읽힌다 — attempt-030 의 규율).
    두 번째 실행을 `start_new_session=True` 로 띄워 완주시켰다.
  - **선언 문서 개정이 계약을 먼저 물었다**: 첫 대조는 `tests/test_cr14_fence_movement_detection.py`
    에서 **5 failed** 였다 — 선언 자리는 후보 **40 hex**·지문 **64 hex** 를 **전체로** 적어야 하는데
    짧게 적었고, 그 계약이 **게이트 전에** 그 사실을 잡았다. 전체 값으로 고친 뒤 `fast` 로 넘어갔다.

---

## attempt-030 갱신 (2026-09-14) — 크래시 뒤 **열려 있는 화면**도 새 사실을 배워야 한다 (F-39 · F-40)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `e02447fb…` · 지문 `87c5091b…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변 —
게이트 목록·명령은 attempt-026 이래 그대로다). **재선언은 없다**: 이 attempt 의 첫 선언이 그
후보의 측정이다. 측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — attempt-028·029 가 **두 번 연속** 남긴 그 질문

attempt-028 은 기술 잔여 셋을 남겼고(전달 IPC · `resuming` 주인 사망 타이밍 · **실 브라우저 눈금**),
attempt-029 는 그중 ③을 밟는 **첫 걸음**에서 물어보려던 질문보다 **먼저** 제품의 쓰기 경로가
죽어 있는 것을 만나 F-37·F-38 을 닫는 데 들어갔다. 그래서 질문은 **그대로 남았고**, 준비(실 서버 ·
실 PIN 로그인 · 실 제출 · **격리된 cwd** · 고정 포트)만 갖춰져 있었다. 이 attempt 가 그 질문을 잰다:

> 서버가 죽었다가 **같은 포트·같은 상태**로 돌아왔을 때, **이미 열려 있던** 화면은 새 사실을
> 배우는가 — 아니면 크래시 전 스냅샷을 "현재"라고 말하면서 연결됨을 표시하는가?

attempt-029 가 남긴 가설("목록 조회가 `reloadVersion` 에만 매여 있어 스트림이 다시 붙어도 크래시 전
스냅샷이 남는다")은 **가설이었고**, 이 attempt 가 그것을 **측정으로** 바꿨다.

### 먼저 센 것 — 고침 전 트리에서의 관측 (증인)

증인은 **제품의 화면**을 쓴다(실 서버 + 실제 PIN 로그인 + 제품의 제출 폼으로 태스크를 만든다).
고침 전 제품 트리는 `HEAD^`(=`1dd90ea5`)를 통째로 `/tmp/agk-f39-base` 에 풀어 **측정 도구(증인
파일·하네스)만** 그 안에 복사하고 그 트리에서 돌린다 — 즉 "고침 전 화면"이 정말 고침 전 제품이다.

  - 고침 전 화면은 제출 뒤 `running`·`재개 없음`을 그렸고(서버도 그 순간에는 `execution_owner: live`),
    증인은 첫 서버를 **그룹째 SIGKILL** 한 뒤 **같은 포트 64105 · 같은 상태 디렉터리**로 1.65초 만에
    재기동했다.
  - **M1 세션**: 재기동 뒤 기존 bearer 토큰으로 `GET /api/tasks` → **200**(세션이 살아 있다 —
    질문이 "로그아웃됐는가"로 바뀌지 않는다).
  - **M2 자동**: 연결 라벨 이력이 `["연결됨"]` — 화면은 **연결을 잃은 적이 없다고 말했다**(스트림이
    조용히 다시 붙었다). 그 순간 서버는 `execution_owner: dead` · `resumable: true` 로 답했지만
    화면은 크래시 전 스냅샷(`label="running"` · 재개 **없음**)을 그대로 그렸다 —
    **위반 1건 · exit 1**. 표시된 연결과 표시된 사실이 동시에 거짓이었다(막다른 길: 복구 가능한
    태스크에 **재개가 아니라 취소만** 제안됐다 — F-36 이 서버 표면에서 없앤 그 막다른 길이
    **열려 있는 화면**에 그대로 남아 있었다).
  - **F-40(측정 도구)**: 이 증인을 세우는 과정에서 도구가 **질문을 잴 수 없다**는 사실이 먼저
    드러났다. 하네스는 `uv run … uvicorn` 을 띄우는데 실제 서버는 런처의 **자식**이라, `listener.pid`
    에 보낸 신호는 런처만 죽이고 서버는 **살아서 포트를 붙들고 있었다**(`/health` 계속 200). 게다가
    재기동이 **토큰 비밀을 새로 만들면** 질문이 "화면이 배우는가"에서 "사용자가 로그아웃됐는가"로
    바뀐다. 증인 `attempt-030/repro/f40_crash_harness_witness.py` 가 세 축으로 그 사실을 잰다 —
    **A** 런처만 신호 → 서버가 **살아남는다**(고침 전 하네스가 크래시를 재현하지 못했다: `True`) ·
    **B** 프로세스 그룹 신호 → 서버가 **실제로 죽는다**(`False`) · **C** 같은 상태 디렉터리로 재기동 →
    같은 토큰이 **200**(비밀 재사용 `True`), 새 비밀로 뜬 서버는 같은 토큰을 **401**(= 위 200 이
    "재사용"이라는 사실의 변별). 고침 후 **exit 0**.
  - **계약(단위)**: `dashboard/src/features/task-execution/useTaskExecutionEvents.test.ts` 3건을
    고침 전 트리에서 돌리면 **2 failed / 1 passed**(exit 1) / 고침 후 **3 passed**(exit 0).

### 고침의 자리 — 각각 **표현할 수 없는 쪽**을 고친다

F-39 는 **화면**이 "서버를 잃었다가 되찾았다"는 사실을 **표현할 수 없었다**: 스트림은 스스로 다시
붙지만 목록은 **한 번 읽은 스냅샷**이고, 그 안에는 시간에 따라 변하는 값(`status` ·
`execution_owner` · `resumable`)이 들어 있다. 재연결 성공 지점이 목록을 다시 읽게 했고, 그 재조회는
`reloadVersion` 이 **아니라 별도 경로**(`refreshTaskList`)다 — `reloadVersion` 은 스트림 이펙트까지
다시 시작시키므로 스트림이 스스로 그것을 올리면 **재시작 루프**가 된다. 실패는 **삼키지 않는다**
(낡은 목록을 조용히 들고 있으면 이 자리의 병이 그대로 돌아온다 — 메시지로 올리고, 연결 상태는
스트림이 소유하므로 여기서 뒤집지 않는다). 목록→상태 반영과 "선택 유지" 규칙은 `applyTaskList`
**한 곳**이 소유한다(F-36 의 `execution_owner_of` 와 같은 규율: 값이 아니라 **자리를** 하나로).

F-40 은 **측정 도구**가 크래시를 표현할 수 없었다: 하네스가 `uv` 런처를 띄우므로 신호는 **프로세스
그룹**(`detached: true` = 새 세션, `-pid`)으로 보내야 하고, 상태 디렉터리를 재사용할 때 **비밀을
새로 만들면 안 된다**(이 두 성질은 그 파일의 docstring 이 처음부터 약속하고 있었다 — 약속과 구현이
갈라져 있던 것을 이 attempt 의 증인이 만났다). 하네스는 이제 `port` · `stateDirectory` ·
`workingDirectory` 를 받는다(고정 포트가 없으면 화면은 **다른 origin** 을 보게 되고, 격리 cwd 가
없으면 증인은 **개발 기계의 레지스트리**를 읽는다).

### 계약과 증인 (요약)

  - 증인(제품 경로) `dashboard/e2e/tests/cr14-crash-restart-surface.spec.ts` — 실 서버 + 실제 PIN
    로그인 + 제품의 버튼 + **그룹째 SIGKILL** + 같은 포트·같은 상태로 재기동. M1 세션 · M2 자동 ·
    M3 수동(화면이 스스로 배우지 못하면 '다시 연결'이 배우게 하는가)로 나눠 재고, 화면의 라벨·버튼을
    **서버가 말하는 사실**과 비교한다(고침 전 **exit 1**(위반 1건) / 고침 후 **exit 0**).
  - 증인(도구) `attempt-030/repro/f40_crash_harness_witness.py` — A·B·C 세 축, 고침 후 **exit 0**.
  - 계약(단위) `useTaskExecutionEvents.test.ts` 3건 — ① 재연결 뒤 다시 읽는다 ② **스트림이 끊기지
    않으면 다시 읽지 않는다**(거짓 양성 0 — 불필요한 재조회는 화면을 흔든다) ③ 다시 읽기 실패를
    **조용히 넘기지 않는다**. 고침 전 **2 failed / 1 passed** · 고침 후 **3 passed**.
  - 공용 화면 도구 `dashboard/e2e/helpers/taskScreen.ts` — attempt-029 의 증인과 이 증인이 **같은
    자**로 화면을 읽는다(두 증인이 서로 다른 자로 재면 어느 쪽 수치도 비교할 수 없다).

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

  - 바꾼 것: `useTaskExecutionEvents.ts`(재연결 뒤 목록 재조회 — **제품 런타임 코드 변경**) ·
    신규 계약 3건 · 공용 화면 도구 · 하네스(도구: 그룹 신호·비밀 재사용·고정 포트·격리 cwd) ·
    추적 번들 재빌드.
  - 바꾸지 **않은** 것: **서버의 규칙과 표면**(F-35/F-36 의 소유·재개 규칙, `execution_owner` ·
    `resumable` 의 값과 의미 — 이 attempt 는 서버를 한 줄도 고치지 않았다) · **저장된 태스크 상태**
    (재시작이 고아 행을 자동으로 끝내지 않는다 — 그 정책은 F-36 그대로다) · **권한 경계** ·
    **판정**(여전히 NO-GO — 남은 차단 사유는 사람·조직 축이다).

### 한계 — 이 attempt 가 **재지 않은** 것

  - **M3(수동 탈출구)는 이번 후보에서 발화하지 않았다** — 고침 후에는 M2(자동)가 먼저 참이 되어
    M3 로 가지 않는다(증인의 분기는 "화면이 연결을 잃었다고 말할 때"만 탄다). 즉 **사용자가 '다시
    연결'을 눌러 배우는 경로**는 이 attempt 의 실행에서 재지 않았다(그 경로는 코드에 있고 F-40 의
    M1 로 세션은 확인했다).
  - **모델 실행 완주는 재지 않았다**(실 provider 조건 — EX-01). 태스크가 `running` 으로 남는 것이
    증인의 정상 입력이다.
  - **다중 호스트·다중 프로세스**: 같은 호스트의 pid 만 본다. 전달 IPC 와 `resuming` 주인 사망
    타이밍(attempt-027/028 의 잔여)은 그대로다.
  - **`cr14-crash-restart-surface.spec.ts` 는 어느 required 게이트도 돌리지 않는다**(게이트 셋은
    `dashboard-test`(vitest) · `accessibility-e2e`(`accessibility.spec.ts` 하나)만 돈다) — 이
    부류의 증인은 **수동**이며, 그 사실을 경계 문서에 적었다.
  - **게이트는 크래시·재연결을 재지 않는다** — required 21개 중 서버를 죽였다 살리는 게이트는 없다.

### 측정 결과 (측정 완료)

커밋된 후보 `e02447fb` · **required gate 21/21 · 0 failed · 0 not_run** · 되돌리기 **0회** · 단일
지문 `87c5091b…` · **`tree_moved` 0건** · **드리프트 0** · **마감 검사 `ATTEMPT_CLOSE: PASS`**(exit 0).

  - **python-tests 6360 passed / 13 skipped / 16 deselected**(581.57s) — attempt-029 와 **같은 수치**다
    (이 attempt 의 계약은 대시보드 쪽에 있다) · **스킵은 13 → 13**. **dashboard-test 870 passed
    (85 files)** = attempt-029 의 867(84) 에서 **+3**(`useTaskExecutionEvents.test.ts` 3건, 새 파일이라
    파일 수 84 → 85) · **api-e2e 9**(스킵 0건) · **accessibility-e2e 35**(스킵 0건) ·
    **python-benchmark 16**(보고된 스킵 0건).
  - **docker-build 226.6s** · **clean-machine-runtime 42.9s**(익스포트 **3029 파일** · `SKIP` 행 0건) ·
    **master-e2e ✅6/❌0** · 정적 검사(ruff · format · mypy · basedpyright **0 errors** · 두 dependency-audit ·
    bandit) 전부 통과.
  - **선언 → 측정 순서**: 후보·지문을 §5 카드에 적고 커밋(`8d35d47c`, docs 전용)한 **뒤에** 게이트를
    돌렸다(D-52) — **재선언은 없다**(이 attempt 의 첫 선언이 그 후보의 측정이고, 게이트가 물린 자리도
    없었다).
  - **지문 불변**: 실행 뒤 `gate-report.json` 의 `git.tree_fingerprint` ·
    `tree_fingerprint_of_commit(HEAD)` · `tree_fingerprint_of_commit(e02447fb)` · `worktree_fingerprint(.)`
    **넷이 모두 같은 값**이고(`attempt-030/logs/fingerprint-invariance.txt`), 후보..HEAD 코드 스코프
    변경은 **0줄**(선언 커밋이 `docs/` 전용)이다. **기록 커밋 `bbff65f7`**(`docs/` 전용 6파일) **뒤에**
    다시 재도 넷이 같은 값이고 후보..HEAD 변경이 전부 `docs/**` 이며 `--stage close` 재실행도
    PASS 다(`attempt-030/logs/record-commit.txt`). `tree_moved` 게이트 0건 — 이 attempt 는 대시보드
    소스와 추적 번들을 **후보 안에서** 함께 움직였고, `dashboard-build` 가 그 번들을 다시 쓰지 않았다.
  - **실행 중 중단 1건을 숨기지 않고 적는다**: `--stage tests`(약 10분)는 이 도구의 호출 타임아웃보다
    길어 **두 번** 부모 셸과 함께 끊겼다(결과 줄이 없는 로그만 남았다). 세 번째 실행을 **분리**해서
    (`start_new_session=True` + 로그 폴링) 완주시켰다 — 앞의 두 로그는 **결과가 없으므로 증거로 쓰지
    않는다**(결과 없는 파일을 증거로 세우면 "실행됐다"로 읽힌다). 이 사실은 `logs/gate-batches.txt` 와
    `commands.jsonl` 에 남겼다.

---

## attempt-029 갱신 (2026-09-14) — 화면의 **쓰기 경로**는 서버가 받아들이는 것이어야 한다 (F-37 · F-38)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `1890d2b0…` · 지문 `57f38a23…` 이며(앞선 두 선언 `084ab3cd…`·`5711a3a8…` 은 그 후보의 측정이 `python-tests` 에서 멈춰 **재선언**했다 — 이유는 §5 카드), 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변).
측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — attempt-028 이 남긴 기술 잔여의 **세 번째**

attempt-028 은 기술 잔여를 셋으로 남겼다: ① 다른 프로세스의 실행을 **전달해서** 멈추는 IPC
② `resuming` 주인이 죽는 **타이밍** ③ **크래시 뒤 라벨·버튼을 실 브라우저 눈금으로** 보는 슬라이스.
이 attempt 는 ③ 을 밟았다 — 그리고 그 슬라이스의 **준비 단계**(브라우저를 세우고 제품의 버튼을
누른다)에서, 물어보려던 질문보다 **먼저** 다른 사실이 나왔다: 그 버튼이 아예 동작하지 않았다.

### 먼저 센 것 — 고침 전 트리에서의 관측 (증인)

증인은 **제품의 그 버튼**을 누른다(격리된 실 서버 + 실제 PIN 로그인 + `/agent` 화면의 제출 폼).
그런데 서버의 cwd 를 격리하면 프로젝트 레지스트리(`data/projects.json` — **상대 경로**다)도 격리되므로,
이 증인은 **두 기계 상태**를 구분해 재야 한다 — 그래서 고침 전 관측이 두 얼굴로 갈렸다:

  - **이미 쓰고 있는 기계**(레지스트리에 `last_accessed_at` 이 있는 레코드가 있다): 화면은 자기
    프로젝트를 알고 정체성을 **최상위** `project_id` 로 실어 보냈고, 서버는 **422**
    (`Extra inputs are not permitted: body -> project_id`)로 막았다 — 위반 3건(V1 제출 거부 ·
    V2 목록에 안 나타남 · V3 서버 목록 0건).
  - **처음 설치한 기계**(레지스트리가 비어 기본 프로젝트가 만들어진다): 서버가 보낸
    `last_accessed_at: null` 을 화면의 스키마(`z.string().optional()`)가 거부해 **목록 파싱이
    실패**했고, 스토어가 비어 화면이 프로젝트를 **모르는 채로** 제출했다 — 위반 2건(V0 화면이
    프로젝트를 얻지 못했다 · V1 서버가 `missing_execution_context` 400).

와이어 증인은 그 자리를 본문의 모양으로 분리해 잰다: B1 수용(최상위 정체성) · B2 **이빨**
(등록되지 않은 최상위 `project_id` 는 404 — 이 검사가 없으면 "수용했다"가 "값을 읽었다"를 뜻하지
않는다: 필드가 조용히 버려져도 세션 바인딩으로 202 가 난다) · B3 중첩 회귀 · B4 무정체성 경계
(400 — 조용한 기본값 금지). 고침 전 B1·B2 모두 **422**(모델 경계에서 막혔다) · **exit 1**.

### 고침의 자리 — 각각 **표현할 수 없는 쪽**을 고친다

두 결함은 같은 부류지만 자리가 다르다. F-37 은 **서버**가 화면의 형태를 표현하지 못했다: 공유
리졸버(`extract_project_id_from_payload`)는 최상위 `project_id` 를 **이미 지원하고** 대화·파일
경로는 그 형태로 동작하는데, 태스크 제출 모델만 그것을 모르는 채 `extra="forbid"` 로 막았다 —
`extra` 를 푸는 대신 두 필드를 **선언**하고, 라우트가 도착한 자리를 빠뜨리지 않게 넘긴다(중첩이
있으면 그것이 이긴다). F-38 은 **화면**이 서버의 타입을 표현하지 못했다: 서버의 `last_accessed_at`
은 `str | None` 이고 `null` 은 "한 번도 열리지 않았다"는 **정상 값**인데 화면의 스키마는 `undefined`
만 허용했다 — `.nullish()` 가 그 타입을 그대로 적는다(같은 파일이 `.nullish()` 를 이미 쓰고 있다).

### 계약과 증인 (요약)

  - 증인(와이어) `attempt-029/repro/f37_submit_identity_witness.py` — 고침 전 **exit 1**(B1 422)
    / 고침 후 **exit 0**(B1 202 + 목록 등장 · B2 404 · B3 202 · B4 400)
  - 증인(제품 경로) `dashboard/e2e/tests/cr14-task-submit-contract.spec.ts` — 같은 파일을
    `git archive HEAD` 트리에서 돌려 고침 전 **3+2 위반** / 고침 후 **두 테스트 통과**(`exit 0`).
    하네스(`hermeticBackend.ts`)에 `workingDirectory` 를 더해 **서버의 cwd** 를 격리했다 — 그 한 줄이
    "처음 설치한 기계"를 만들 수 있게 했고, 그 전에는 이 증인이 **개발 기계의 레지스트리**에
    의존해 결함을 재현할 수 없었다(그 사실 자체가 이 슬라이스의 발견이다: 증인의 **전제**를
    만들지 못하면 증인은 아무것도 재지 않는다).
  - 계약 `tests/test_cr14_screen_server_wire_contract.py` 6건 — 이빨: 유령 프로젝트가 202 를 받으면
    실패(`test_submit_reads_the_top_level_project_id`) · 중첩 우선순위 · `extra="forbid"` 유지 ·
    무정체성 400 유지 · 한 번도 열리지 않은 레코드가 `null` 로 **키를 갖고** 나간다.
    고침 전 트리에서 **3 failed / 3 passed** · 고침 후 **6 passed**.
  - 계약(대시보드) `dashboard/src/api/contractAlignment.test.ts` 2건 — 실제 zod 로 그 응답을
    파싱한다. **이 테스트가 살아남은 이유를 고쳤다**: 기존 케이스는 "실제 응답"이라 적힌 픽스처에서
    `last_accessed_at` 을 **빼놓았다** — 그래서 `null` 이 파싱을 깨는 사실이 계약 안에서 보이지 않았다.
    고침 전 트리에서 **1 failed / 12 passed** · 고침 후 **13 passed**.

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

  - 바꾼 것: `TaskSubmitRequest`(두 정체성 필드 선언) · 태스크 제출 라우트(도착한 자리를 리졸버로) ·
    `ProjectRecordSchema`(`last_accessed_at`·`preview` 의 `null` 수용) · 추적 번들(대시보드 소스가
    움직였으므로) · 하네스 `workingDirectory` · 증인 셋(와이어·제품 경로·계약).
  - 바꾸지 **않은** 것: **권한 경계**(`extra="forbid"` 는 그대로다 — 모르는 필드는 여전히 422이고,
    무정체성 제출은 여전히 400이며, 유령 프로젝트는 404다) · **태스크 실행·소유·복구 규칙**(F-35/F-36
    이 닫은 것들) · **판정**(여전히 NO-GO — 이 attempt 는 기술 축의 결함을 닫았을 뿐이고,
    막고 있는 것은 사람·조직 축이다).

### 한계 — 이 attempt 가 **재지 않은** 것

  - **크래시 뒤 열려 있는 화면**(F-39 후보)은 여전히 **재지 않았다** — 그 질문은 이 attempt 가
    세운 준비를 그대로 쓰지만, 이 attempt 는 먼저 만난 결함 두 개를 닫는 데 들어갔다. 처음에는 그
    질문의 자리를 증인 파일 안에 테스트 단위 비활성화 표기로 남기려 했고, **게이트가 두 번 그것을
    정당하게 거부했다**(① 표기 자체 ② 표기를 **이름으로 부른 주석** — 그 검사는 소스를 문자열로
    스캔한다): 그 등록부의 채널은 **게이트 스킵**이라 대시보드 소스의 표기를 소유할 자리가 없다.
    등록부를 넓히는 대신 표기를 빼고 질문을 **말로** 적었다(증인의 설계 주석 · 증거팩 · §6 `0-f-7`).
    가설(목록 조회가 `reloadVersion` 에만 매여 있어 스트림이 다시 붙어도
    크래시 전 스냅샷이 남는다)은 **가설일 뿐 측정이 아니다**.
  - **다른 클라이언트**(CLI·외부 통합)가 정체성을 어디에 싣는지는 재지 않았다 — 이번 계약은 화면의
    형태와 서버의 계약을 맞췄을 뿐이다.
  - **다중 프로세스 IPC**·`resuming` 주인 사망 타이밍 — attempt-027/028 이 남긴 기술 잔여는 그대로다.

### 측정 결과 (측정 완료)

커밋된 후보 `1890d2b0` · **required gate 21/21 · 0 failed · 0 not_run** · 되돌리기 **0회** · 단일
지문 `57f38a23…` · **`tree_moved` 0건** · **드리프트 0** · **마감 검사 `ATTEMPT_CLOSE: PASS`**
(exit 0).

  - **python-tests 6360 passed / 13 skipped / 16 deselected**(579.36s) — attempt-028 은 6354/13 이었으므로
    증가분 **+6** 은 이 attempt 의 계약(`tests/test_cr14_screen_server_wire_contract.py`), **스킵은 13 → 13**.
  - **dashboard-test 867 passed(84 files)** = +2(`last_accessed_at: null` 계약) · **api-e2e 9** ·
    **accessibility-e2e 35** · **python-benchmark 16** — 전부 **스킵 0건**.
  - **docker-build 221.9s** · **clean-machine-runtime 41.9s**(익스포트 3026 파일 · `SKIP` 행 0건) ·
    **master-e2e ✅6/❌0** · 정적 검사(ruff·format·mypy·basedpyright 0 errors·두 dependency-audit·bandit) 전부 통과.
  - **선언 → 측정 순서**: 세 후보(`084ab3cd`·`5711a3a8`·`1890d2b0`)를 **각각 측정 전에** 선언했고,
    앞의 둘은 `python-tests` 의 tripwire 에서 멈춰 재선언했다(아래). 세 번째 후보에서 완주했다.
  - **지문 불변**: 실행 뒤 `gate-report.json` 의 `tree_fingerprint` · 후보 커밋 트리 지문 ·
    작업 트리 지문이 **모두 같은 값**이고(`attempt-029/logs/fingerprint-invariance.txt`),
    후보..HEAD 코드 스코프 변경은 **0줄**(선언 커밋이 `docs/` 전용)이다.

아래 §5 카드의 게이트 수치가 이 attempt 의 측정이다(커밋된 후보 `1890d2b0` · 단일 지문 `57f38a23…`).

**앞선 두 후보의 측정은 모두 `python-tests` 에서 멈췄다**(매번 fast 18/18 통과 뒤):
`tests/test_cr14_gate_skip_register.py::test_dashboard_sources_have_no_unregistered_skip_markers`
가 증인의 **테스트 단위 비활성화 표기**를 두 번 **정당하게** 거부했다. 첫 번째는 그 표기 자체였다
(재지 않은 F-39 질문을 소유자 없는 스킵으로 만들지 않는다 — 그 등록부의 채널은 **게이트 스킵**이다;
등록부를 넓히는 대신 표기를 빼고 질문을 증인의 설계 주석·증거팩·§6 에 적었다). 두 번째는 그 표기를
**이름으로 부른 주석**이었다 — 그 검사는 소스를 **문자열로** 스캔하므로 무엇을 하려 했는지 적는 일도
같이 걸린다(그래서 세 번째 후보는 뜻을 **말로** 적었다). 두 수정이 트리를 옮겼으므로 시도 안에서
**재선언**했고 세 번째 후보에서 측정을 완주했다. 게이트는 두 번 다 옳게 물렸고, 이 attempt 의 판단이
틀렸다: `dashboard-test`·`python-tests` 가 도는 트리 안에서는 표기를 **쓰는 것도 부르는 것도** 안 된다.

---

## attempt-028 갱신 (2026-09-14) — 재시작한 서버는 **주인에 대해 아는 것을 말한다** (F-36)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `9fb7f068…` · 지문 `f838f2ea…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변).
측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — attempt-027 이 **재지 않고 남긴** 절반

attempt-027 은 `0-d`(C14-03 을 취소·중단 경로까지 실행)의 절반을 닫고 남은 절반을 문서에 적었다:
"**실 서버를 띄운 재시작 슬라이스**(SIGKILL → 재기동 뒤 이력·재개 가능성)는 재지 않았다 —
이 attempt 는 **러너 두 개**로 같은 질문의 핵심만 쟀다. 그것이 다음 attempt 의 첫 걸음이다."
그래서 이번에는 **실 서버**로 쟀다: `uvicorn` 기동 → **실제 인증**(PIN → bearer) → 태스크 제출 →
**SIGKILL** → **같은 DB** 로 재기동 → 표면(상세·목록)과 행동(`POST /resume`)을 대조.

### 먼저 센 것 — 고침 전 트리에서의 관측 (증인)

증인 `attempt-028/repro/f36_orphan_surface_witness.py` — 로그 `logs/f36-witness-before.txt`,
**exit 1 · 위반 4건**:

| 관측(고침 전) | 값 |
|---|---|
| 죽기 전 행 | `status=running` · `owner_pid=51653` · `version=1` |
| SIGKILL 뒤 행 | **변하지 않았다** — 여전히 `running` · `owner_pid=51653`(그 pid 는 이제 죽었다) |
| 재기동 서버의 상세 | `{"status": "running", …}` — **주인에 대한 말이 어디에도 없다** |
| 재기동 서버의 목록 | 같은 모양 — 화면의 버튼은 **목록의 행**을 보고 그려진다 |
| 같은 행에 대한 행동 | `POST /resume` → **200 `{"status": "resumed"}`** |
| 대조군(살아 있는 실행) | 주인을 말하는 필드 자체가 없다(살아 있음도 죽음도 구별되지 않는다) |

즉 **표면과 행동이 갈라져** 있었다: 서버는 그 행을 **재개할 수 있다**고 판단하면서(200)
**말로는** `running` 이라고 했다. 화면(`TaskQueuePanel`)은 그 `running` 을 "실행 중"으로 읽어
**재개가 아니라 취소만** 제안했다 — 복구 가능한 태스크에 **막다른 길**을 제안한 것이다.
attempt-027 이 "살아 있는 다른 프로세스의 취소"를 거짓으로 만들던 자리와 **같은 병**이
(소유 사실이 하나의 함수에 있는데 그 함수를 한 경로만 쓴다) 이번에는 **보고**에서 나왔다.

### 고침의 자리 — 정책이 아니라 **표면**

저장된 상태는 **그대로 둔다**: 재시작이 고아 행을 자동으로 끝내면 **재개 가능성이 사라진다**
(그 행이 지금 값어치를 갖는 이유가 그것이다). 바꾼 것은 그 사실을 **말하는 자리**다.

- `execution_owner`(`live`/`dead`/`none`) · `resumable` 을 `/api/tasks` 와
  `/api/tasks/{id}/status` 가 말한다. **둘 다 저장하지 않는다** — 행에서 파생되는 보고 값이다.
- 값은 **한 곳**에서 만든다: `execution_owner_of` 는 `can_prepare_resume`/`can_cancel` 과
  **같은 liveness 함수**(`_process_is_alive`)를 쓰고, `resumable_task` 는 행동의 **두 조건**
  (`can_prepare_resume` + 체크포인트 존재)을 그대로 옮긴 것이다 — 화면이 버튼을 그릴 근거와
  서버가 받아줄 근거가 갈라지지 않는다. 메모리 레코드는 `owner_pid_for_raw_status` 로
  "이 프로세스"를 말한다(레거시 `running` 행은 `none` 이다 — "살아 있다"고 말할 근거가 없다).
- 화면은 그 필드로 버튼을 그린다(`taskLifecycleActions.ts` 가 규칙을 소유): 주인이 죽은
  비종결 행은 라벨이 **"실행 중단(소유 프로세스 종료) — 재개 가능"** 이고(스크린리더용
  `aria-label` 도 같은 값을 쓴다), 서버가 필드를 보내지 않으면 **없는 정보를 추측으로 대체하지
  않고** 예전 상태 규칙으로 되돌아간다(그 화면보다 오래된 서버를 상대하는 경우).
- 목록 조회가 `owner_pid` 를 싣고, 체크포인트 유무는 **한 번의 질의**로 모은다(행마다 질문하면
  목록 하나가 N번 질문한다).

### 계약과 증인 (요약)

- 증인: `attempt-028/repro/f36_orphan_surface_witness.py` — **실 서버 + 실 인증 + SIGKILL +
  같은 DB 재기동**. 고침 전 **exit 1**(위반 4건) / 고침 후 **exit 0**(죽은 주인은 `dead`,
  복구 가능성은 `resumable=true` 이며 행동과 일치 · 대조군은 `live`/`resumable=false`).
- 계약: `tests/test_cr14_task_orphan_surface.py` **12건** — 이빨은 **체크포인트가 없으면 표면도
  `false` 이고 행동도 거부한다**(표면이 약속을 과장하면 실패), 거짓 양성 0, 그리고 **투영이
  행을 쓰지 않는다**(읽기가 상태를 바꾸면 그것 자체가 결함이다).

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

- 바꿨다: **재시작 뒤 표면이 주인과 복구 가능성을 말한다**(서버 두 표면 + 화면 규칙 한 곳).
  attempt-025·027 과 같이 **제품 런타임 코드가 바뀐 attempt** 다(관측성이며 판정을 움직이지 않는다).
- 바꾸지 않았다: **저장된 상태·정책**(`running` 행을 자동으로 끝내지 않는다) · **`resume` 의
  허용 규칙**(`can_prepare_resume` 그대로 — 표면이 그 함수를 **읽을** 뿐이다) · 게이트 목록·명령.

### 한계 — 이 attempt 가 **재지 않은** 것

- **다중 프로세스에서 실행을 전달하는 IPC** 는 여전히 없다(attempt-027 의 한계 그대로):
  재기동한 서버는 죽은 주인의 행을 **재개**할 수 있지만, **살아 있는** 다른 프로세스의 실행을
  멈추는 길은 없다(거부가 정직한 대답이다).
- **`resuming` 행**(재개가 진행 중인데 그 프로세스가 죽은 경우)은 이 attempt 의 표면 설계가
  규칙으로 덮지만 **실 서버로 그 타이밍을 만들지는 않았다**.
- 화면 절반은 **DOM 계약**(vitest)으로만 쟀다 — 실 브라우저에서 크래시 뒤 라벨·버튼을
  눈으로 확인하는 슬라이스는 이 attempt 에 없다.

### 측정 결과 (측정 완료)

게이트 세 배치(fast → tests → heavy)와 마감 검사를 **커밋된 후보 `9fb7f068`** 에서 돌렸다
(측정 시 HEAD `536d6473` — 선언 커밋이며 docs 전용이므로 코드 트리가 같다).

| 항목 | attempt-027 | **attempt-028** |
|---|---|---|
| required gate | 21/21/0/0 | **21/21/0/0**(되돌리기 0회 · 단일 지문 `f838f2ea…`) |
| python-tests | 6342 passed / 13 skipped / 16 deselected (572.53s) | **6354 passed / 13 skipped / 16 deselected**(562.51s) |
| dashboard-test | 859 passed (83 files) | **865 passed (84 files)** · 스킵 0건 |
| api-e2e · accessibility · benchmark | 9 · 35 · 16 | 9(**스킵 0건**) · 35(**스킵 0건**) · 16(**보고된 스킵 0건**) |
| master-e2e | ✅6/❌0 | ✅6/❌0 |
| docker-build · clean-machine | 229.1s · 42.7s | **228.9s** · **43.1s**(3024 파일 · `SKIP` 행 0건) |
| `tree_moved` 게이트 | 0건 | **0건**(F-34 의 검사가 이번에도 옳은 후보에서 물지 않았다) |
| 드리프트 | 0 | **0**(`data/`·`dashboard_dist` 모두 — ` M vault_data` 한 줄뿐, F-13) |
| 실행 후 지문 | 동일 | **동일**(`f838f2ea…` — `logs/fingerprint-invariance.txt`) |

**무엇이 늘었나**: attempt-027 → attempt-028 은 **python-tests 6342 → 6354(+12)** = F-36 계약
`tests/test_cr14_task_orphan_surface.py` 12건이고, **frontend 859 → 865(83 → 84 files)** =
화면 규칙·패널 계약(`taskLifecycleActions.test.ts` 신규 + `TaskQueuePanel.test.tsx`)이다.
**스킵은 13 → 13 불변**이다 — 이 attempt 는 스킵을 되찾은 것이 아니라 **표면이 말하는 것과
행동이 하는 것을 같게** 만들었다.

배치는 **별개 프로세스 셋이 스스로 이어받았다**(fast 18 → tests 19 → heavy 21) — F-26·F-27 이 만든
성질이 이 attempt 에서도 재실측됐고, 마감 검사는 **보고서 편입 뒤** PASS 한다(아래 `logs/close-check.txt`).
값의 유일한 선언 자리는 §5 카드다.

---

## attempt-027 갱신 (2026-09-14) — 취소도 **소유 규칙**을 지킨다 (F-35)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `64590235…` · 지문 `98fd6695…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다

> **(재선언 — 이 attempt 안에서)** 첫 선언은 후보 `e12ec3cb`(지문 `4dbfa955…`)이었고, 그 후보의
> **첫 측정은 `security-bandit` 에서 실패**했다: 새 `cancel_if_permitted` 의 UPDATE 가
> `prepare_resume` 과 같은 형태(고정 조각 + 바인딩 파라미터)인데 그 표기(`# nosec B608`)를
> `prepare_resume` 만 갖고 있었다. 표기를 맞춘 수정이 코드를 옮겼으므로 **측정 전에** 다시
> 선언한다(D-52 의 순서는 그대로다). `e12ec3cb` 의 fast 배치는 **18개 중 17개만** 통과했고,
> 그 기록은 위 §5 의 `required gate` 줄에 그대로 남긴다.
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변).
측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — 문서가 지시한 다음 단계에서

attempt-026 이 닫힌 뒤 문서의 권고는 이랬다: "기술 축은 **제품 결함도 검증 장치 결함도 0건**"이고,
남은 것은 사람·조직 축이다 — 다만 §6 의 `0-d` 는 **C14-03 을 취소·중단 경로까지 실행하는 것**을
남겨 두었다("F-15 같은 결함은 **전 구간 시나리오**에서 드러난다"). 그 슬라이스를 재던 중 첫 질문이
이것이었다: **`resume` 은 소유자를 보는데 `cancel` 은 보는가.** 답은 **아니오**였다.

### 먼저 센 것 — 고침 전 트리에서의 관측 (증인)

증인은 **프로세스 두 개**를 쓴다: 자식이 실제 `BackgroundTaskRunner` 로 태스크를 제출하고
청크마다 효과 파일에 한 줄을 남기며, 부모가 같은 DB 를 여는 **두 번째 러너**(= 재시작한 서버)로
`cancel_task` 를 부른다. 로그 `logs/f35-witness-before.txt`, **exit 1 · 위반 3건**:

| 관측(고침 전) | 값 |
|---|---|
| 소유자 생존 | `owner_alive_at_cancel: True` (pid 살아 있음) |
| 외부 취소의 반환 | `True` — **일어나지 않았음이 관측되지 않았다** |
| 그 뒤 DB 행 | `running` → `cancelled` · `owner_pid` 는 **지워짐**(`None`) |
| 소유자의 실행 | 효과 **4 → 10 줄** — 취소 뒤에도 계속됐다 |
| 소유자 종료 뒤 최종 행 | `cancelled` + 오류 "… or it was lost in memory" (version 2 — 마지막 쓰기가 CAS 에 밀렸다) |

즉 **세 가지가 한꺼번에 거짓**이었다: 취소가 됐다는 보고(C1), 멈췄다는 함의(C2),
그리고 "일어난 일의 이력"이라는 주장(C3).

### 고침의 자리 — 두 경로가 **같은 규칙**을 쓴다

뿌리는 `cancel` 이 `resume` 의 규칙을 **복제하지 않았다**는 것이다(게이트 규칙이 두 곳으로 갈라졌던
F-27 과 같은 병). 그래서 규칙을 새로 쓰지 않고 **같은 liveness 함수**(`_process_is_alive`)를 취소에도
쓴다: `can_cancel(raw_status, owner_pid)` — 소유자가 없거나·이 프로세스거나·이미 죽었을 때만 허용하고,
`running`/`resuming` 의 **살아 있는 다른 프로세스**는 거부한다. `pending`/`paused` 는 허용한다:
그 취소는 거짓이 아니라 **진짜**다(소유자의 시작 CAS `pending → running` 이 실패해 실행되지 않는다).

거부는 **조용하지 않다**: 저장소가 `owned_elsewhere` 를 돌려주고 API 가 **409** 로 낸다(활성 아님은
404 그대로 — 두 사건이 다르다). 화면은 서버의 `detail` 을 메시지로 올린다.

### 계약과 증인 (요약)

| 장치 | 내용 |
|---|---|
| 증인 | `repro/f35_foreign_cancel_witness.py` — 고침 전 **exit 1**(3건) / 고침 후 **exit 0**. **같은 증인 파일**을 소스 트리만 바꿔 돌린다(`PYTHONPATH` 로 HEAD 사본) |
| 계약(Python) | `tests/test_cr14_task_cancel_ownership.py` — 규칙 행렬(`can_cancel`) · 거부가 행을 **건드리지 않음** · 죽은 소유자의 고아는 **여전히 취소됨**(이빨) · `pending` 취소가 **실제로 실행을 막음** · 러너의 거부 사유 |
| 계약(API) | `tests/test_api_server.py`(409/404/200) · `tests/test_task_api.py`(거부 사유별 응답) |
| 계약(화면) | 대시보드 vitest `taskExecutionApiFailure.test.ts` — 서버 사유가 메시지로 올라오는가 |

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

바꾼 것: **취소의 소유 규칙**(`can_cancel` · `cancel_if_permitted` · 거부 사유)과 그것을 API·화면까지
전달하는 경로. 바꾸지 않은 것: 재개 경로(`can_prepare_resume` 그대로) · 고아 취소의 허용 여부 ·
게이트 목록·명령·required 여부. 판정은 **NO-GO 유지**이며 이 attempt 는 판정을 움직이지 않는다.

### 한계 — 이 attempt 가 **재지 않은** 것

- **PID 재사용**: 소유자 pid 가 다른 프로세스에 재할당되면 규칙이 "살아 있는 소유자"로 읽는다 —
  이 한계는 `can_prepare_resume` 이 처음부터 갖고 있던 것이고(같은 함수를 쓰므로 규칙은 일관되다),
  이 attempt 는 그것을 **바꾸지 않았다**.
- 다중 프로세스에서 **취소를 소유자에게 전달**하지는 않는다(IPC 가 없다) — 거부가 정직한 대답이다.
- 서버를 띄운 재시작 슬라이스(C14-03 의 나머지)는 이번에 재지 않았다 — 증인은 **러너 두 개**로 쟀다.

### 측정 결과 (측정 완료)

커밋된 후보 `64590235` 에서 되돌리기 없이 단일 지문 `98fd6695…`. 로그 `logs/gate-summary.txt` ·
`logs/fingerprint-invariance.txt` · `logs/close-check.txt`.

| 게이트 | 값 |
|---|---|
| required | **21 / 21 / 0 / 0** · statuses `['passed']` — **`tree_moved` 0건** |
| python-tests | **6342 passed / 13 skipped / 16 deselected**(572.53s) |
| dashboard-test | **859 passed(83 files)** — 스킵 0건 |
| api-e2e | 9 — 스킵 0건 |
| accessibility | 35 — 스킵 0건 |
| python-benchmark | 16 — 보고된 스킵 0건 |
| clean-machine-runtime | 42.7s — **`SKIP` 행 0건** |
| docker-build | 229.1s |
| master-e2e | ✅6 / ❌0 |
| 드리프트 | **0**(`data/` 0 · `dashboard_dist` 0) · ` M vault_data`(F-13) 한 줄 |
| 마감 검사 | **`ATTEMPT_CLOSE: PASS` exit 0** — 편입 전에는 같은 검사가 FAIL exit 1 |

**무엇이 늘었나**: attempt-026 → attempt-027 은 **python-tests 6329 → 6342(+13)** = F-35 계약 9 +
API·서버 계약 4, **dashboard-test 855(82) → 859(83 files)(+4)** = 화면 계약 1파일,
**스킵은 13 → 13 불변**. 이 attempt 는 스킵을 되찾은 것이 아니라 **취소의 정직성**을 잰다.

**앞선 선언의 실패를 그대로 남긴다**: 첫 선언 `e12ec3cb` 의 fast 배치는 **17/18** 이었다 —
`security-bandit` 이 새 `cancel_if_permitted` 의 UPDATE(고정 조각 + 바인딩 파라미터 — `prepare_resume`
과 같은 형태)에 **B608** 을 물었다. 그 실행은 **채택되지 않았고**(보고서를 쓰지 않았다), 표기를 맞춘
수정이 코드를 옮겼으므로 **측정 전에** 재선언했다.

### 이 후보에서 F-34 의 검사가 **물지 않았다**는 관측

`dashboard_dist` 드리프트 0 은 이 attempt 에서 **위생 기록이자 동시에 다른 무엇**이다: attempt-026 이
"게이트가 트리를 옮기면 그 게이트를 실패로 적는다"를 넣었으므로, 21/21 이 성립한다는 것 자체가
그 검사의 **거짓 양성 0** 을 말한다. 이 attempt 는 대시보드 소스를 바꿔 번들을 **후보 안에서** 함께
재빌드했고(F-01·F-34), 게이트가 그 번들을 다시 쓰지 않았다 — 즉 고친 뒤의 소스와 산출물이
같은 커밋에 있다.

## attempt-026 갱신 (2026-09-13) — 게이트는 **자기가 재는 코드를 바꾸지 않는다** (F-34)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `d62ba10a…` · 지문 `994b21fd…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 불변).
측정은 이 절의 `### 측정 결과` 가 담고, **값의 유일한 선언 자리는 §5 카드**다.

### 무엇을 물었나 — attempt-025 가 **실제로 멈춘** 자리

attempt-025 는 `ApprovalQueue.tsx` 의 동의 문구를 고친 뒤 재빌드를 **빠뜨린 채** 후보를 커밋했고,
그 사실을 알아낸 것은 **게이트가 아니라 다음 배치의 이어받기 거부**였다("previous report was
produced from a different working tree"). 그 attempt 는 그 거부를 **옳은 것으로** 적고(F-01 관련
한계) 번들을 후보 안으로 가져와 다시 선언했다 — 그러나 **그 거부가 유일한 탐지기**라는 사실은
남았다. 그래서 질문은 이것이다: **대시보드 소스를 고치고 번들을 다시 만들지 않으면, 무언가가
실패하는가.** 실패하지 않으면 그 후보의 화면에는 **고치기 전의 UI** 가 나가고, 게이트는 초록이다.

### 먼저 센 것 — 고침 전 트리에서의 관측 (증인)

증인 `attempt-026/repro/f34_stale_bundle_witness.py` 를 **고침 전 트리 사본**
(`--tree-at d62ba10a^`)에서 돌렸다. 로그 `logs/f34-witness-before.txt`, **exit 1 · 깨진 요구 1건**:

```
[VIOLATED] F-34 러너가 낡은 번들을 거부한다 — 러너가 exit 0 으로 끝났다 —
  게이트가 측정 대상 코드를 바꾼 사실이 보고서에 남지 않는다
```

같은 증인이 **네 가지 사실을 세어서** 낸다(고침 전 트리):

| 관측 | 값 |
|---|---|
| 번들을 지칭하는 pytest 계약 | 6파일 — 소스만 고친 트리에서 **전부 통과**(68 passed in 8.46s) |
| 출하물의 문구 | 옛 문구=True · 새 문구=False — 화면은 **고치기 전 UI** |
| 게이트 명령(`vite build`) | **exit 0** 이면서 추적 번들 **45개**를 다시 쓴다 |
| 러너(고침 전) | exit 0 · `passed` — 바뀐 사실이 보고서에 남지 않는다 |

### 고침의 자리 — 게이트 **앞뒤**의 코드 상태

지문은 게이트 **앞에서** 한 번 재고 끝났고, 게이트가 그 뒤에 무엇을 바꿨는지 묻는 자리가 없었다.
그래서 지문을 만들던 **한 곳**(`ga_gate.tree_digests`)이 경로별 내용 지도를 돌려주게 하고, 게이트
실행 **직전·직후**의 지도를 비교한다(지문 1회 측정이 0.1초 규모라 게이트 21개에 붙여도 무시할 수준이다).
차이가 있으면 그 게이트의 `status` 는 `tree_moved` 가 되고 — 명령 자체의 `exit_code` 는 **그대로
남긴다**(명령은 성공했고 실패한 것은 계약이다) — 실행 전체가 **exit 1** 로 끝난다. required 여부로
거르지 않으므로 게이트를 non-required 로 추가해도 같은 결함이 조용해지지 않는다.

소비자 둘을 함께 맞췄다: 승인 검증기(`scripts/ga_gate_verify.py`)는 이 상태를 **구조 오류로 적지
않되**(`interrupted` 와 같은 부류 — 명령의 결과가 아닌 상태다) 그 보고서를 승인하지 않고,
마감 검사(`scripts/verify_attempt_close.py` **항목 9**)는 **어느 게이트가 어느 파일을 바꿨는지
이름으로 대며** 거부한다. 항목 9 가 required 로 거르지 않는 이유도 같다 — non-required 게이트가
트리를 옮기면 보고서 요약은 초록인 채로 남는다.

### 계약과 증인 (요약)

| 장치 | 내용 |
|---|---|
| 증인 | `repro/f34_stale_bundle_witness.py` — 고침 전 **exit 1**(1건) / 고침 후 **exit 0**. **같은 증인 파일**을 `--tree-at` 만 바꿔 돌린다(고침 전/후를 다른 도구로 재지 않는다) |
| 계약(Python) | `tests/test_cr14_gate_code_state_invariant.py` **8건** — 지문 == 지도 digest · 변경·등장·소실 탐지 · 코드를 쓴 게이트가 `tree_moved`(exit 1) · **무시되는 산출물에는 물지 않는다** · non-required 도 빨개진다 · 승인 검증기의 완화와 거부 · **물릴 대상이 실제로 있다**(required 게이트가 추적 번들을 제자리에서 다시 빌드한다 — 그 게이트를 지우면 계약이 먼저 깨진다) |
| 이빨(마감 검사) | `tests/test_cr14_attempt_close.py` — required 실패가 **하나도 없는데** `tree_moved` 인 보고서를 마감이 거부하는지. 그 하네스에 `raw_gates` 를 더했다: status 가 `passed`/`failed` 뿐이라고 가정하면 러너가 만들 수 있는 상태를 **검사할 수도 없다** |

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

바꾼 것: **게이트 러너의 판정**(코드 상태 불변식) + 그 사실을 읽는 소비자 둘 + 계약·이빨.
바꾸지 않은 것: **검증의 강도** — 게이트 목록·명령·타임아웃·required 여부는 그대로이고, 제품
런타임 코드는 **0줄**이다. 판정은 **NO-GO 유지**이며 이 attempt 는 판정을 움직이지 않는다.

### 한계 — 이 attempt 가 **재지 않은** 것

- **제자리에서 파일을 쓰는 다른 게이트**가 새로 생기면 그때 빨개진다(이 후보의 21개 중 그런 것은
  `dashboard-build` 하나이고, `sbom-generate` 는 현 트리에서 no-op 이다). 그 방향은 실측하지 않았다.
- **게이트를 돌리지 않으면 이 불변식은 작동하지 않는다** — "번들이 낡았는가"의 답은 required 게이트
  전수를 돌려야 나오고, 이 검사 자신은 게이트가 아니다(보고서는 게이트가 끝나야 생긴다 — F-24 와
  같은 위치). 대신 게이트 목록이 이 검사를 **가진 게이트를 포함하는지**를 계약이 잰다.
- 사람이 눈으로 보는 화면 확인은 여전히 `manual-qa.md` 다.

### 측정 결과 (측정 완료)

**required gate 21/21 을 커밋된 후보 `d62ba10a` 에서 되돌리기 0회 · 단일 지문 `994b21fd…` ·
`tree_moved` 게이트 0건으로 완주**했다. 세 배치가 **별개 프로세스**로 스스로 이어받았다
(`새 보고서로 시작한다`(fast) → `이어받는다`(tests) → `이어받는다`(heavy)). 보고서가 이름 붙인 커밋은
선언 커밋 `956d38bc` 이고 그 트리는 후보 `d62ba10a` 의 코드 트리와 **같다**(docs 전용 커밋 — F-22).

| | attempt-025 | **attempt-026** |
|---|---|---|
| python-tests passed | 6320 | **6329** |
| python-tests skipped | 13 | **13** |
| dashboard-test | 82 files / 855 | **82 files / 855** |
| `tree_moved` 게이트 | — | **0** |
| 제품 런타임 코드 변경 | 있음(F-33) | **0줄** |

- **python-tests 6329 passed / 13 skipped / 16 deselected**(544.70s · 게이트 550.34s). 증가분 **+9**
  = 새 계약 `tests/test_cr14_gate_code_state_invariant.py` **8건** + 마감 검사 이빨 1건.
  **스킵은 늘지 않았다**(13 → 13, 전부 소유자가 있다).
- **dashboard-test 82 files / 855 passed** — `Test Files 82 passed (82)` · `Tests 855 passed (855)`,
  **스킵 신호 0건**(verbose 리포터).
- **api-e2e 9 · accessibility 35 · python-benchmark 16 · master-e2e ✅6/❌0 · docker-build 224.8s ·
  clean-machine-runtime 41.7s** — 테스트 게이트 다섯과 clean-machine 이 보고한 스킵은 **0건**
  (`python-tests` 만 13건).
- **mypy 482 files clean · basedpyright 0 errors · dependency-audit-python high/critical 0건 ·
  dependency-audit-dashboard 취약점 없음 · ruff·format clean** — 게이트 전수 `exit_code 0`.
- **드리프트 0** — `data/` 0 · `dashboard_dist` **0**(후보의 번들 == 게이트가 다시 빌드한 번들) ·
  `tree_moved` 게이트 **없음**(21개 전부 `passed`) · 실행 후 지문 재측정 **동일**. 이 attempt 에서
  그 0 은 위생 기록이면서 동시에 **고침의 거짓 양성 0** 관측이다 — F-34 의 검사가 옳은 후보에서
  물면 21/21 이 성립할 수 없다.
- **실제 게이트로 과잉 탐지 0 확인** — `--only dashboard-build`: status `passed` · `tree_moved`
  없음 · 실행 뒤 추적 번들 드리프트 0(`logs/dashboard-build-live.txt`).
- 마감 검사 **PASS(exit 0)** — 조항 9(트리를 옮긴 게이트가 있으면 required 실패가 **없어도** 거부)가
  켜진 채로 통과했고, 편입 전에는 같은 검사가 **FAIL exit 1** 이었다(`logs/close-check.txt`).
  두 결과를 가른 것은 **보고서의 존재 하나**다 — F-24 의 성질이 이 attempt 에서도 살아 있다.
- **증인 대조** — `repro/f34_stale_bundle_witness.py` 고침 전 **exit 1**(1건: 러너가 낡은 번들을
  `passed` 로 통과) / 고침 후 **exit 0**(⑦ 낡은 번들은 `tree_moved` + 경로 **45개**를 대며 거부 ·
  ⑧ 소스에서 다시 만든 번들에서는 **조용하다**).

> 이 attempt 는 **제품 런타임 코드를 0줄** 바꿨다 — 바뀐 것은 게이트 러너의 판정과 그 사실을 읽는
> 소비자 둘, 그리고 계약·이빨이다. 판정은 **NO-GO 유지**이며 이유는 `decision.md` 에 적었다:
> 남은 차단 사유는 **사람·조직 축**(EX-01~06 · C14-08 · C14-03/04/05)이다.

## attempt-025 갱신 (2026-09-13) — '항상 허용'은 **읽고 되돌리고 셀 수 있는** 동의다 (F-33)

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `a2f6f724…` · 지문 `57e32c9a…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(`tree_fingerprint_of_commit(HEAD) == worktree_fingerprint`, manifest sha256 `86c40edc…` 불변).
측정 결과는 게이트를 돌린 뒤 이 절과 §5 카드에 채운다.

> **(재선언 — 측정 전)** 이 attempt 의 첫 선언은 후보 `440c5e06` · 지문 `e8e464c6…` 이었다. 그것이
> 낡은 이유는 **F-01** 이다: `src/antigravity_k/dashboard_dist/` 는 **추적되는** 빌드 산출물이고,
> 소스를 고치면 배포본도 같이 움직여야 한다. fast 배치의 `dashboard-build` 가 실제로 번들을 다시
> 썼고(29 삭제 + 29 생성 + 1 수정) 게이트의 이어받기가 **다른 트리**라며 거부했다(그 거부가 옳다 —
> 다른 코드 상태의 초록을 붙이면 안 된다). 선택지는 둘이었고 **번들을 후보 안으로 가져오는 쪽**을
> 골랐다(`a2f6f724`). 빌드는 **두 번 돌려 바이트 동일**임을 확인했다(재실행 뒤 `git status` 불변).
> `440c5e06` 은 **측정되지 않았다** — 그 초록은 이 후보의 증거가 아니고, 이 재선언은 D-52 의
> 순서(선언 → 측정)를 지키기 위한 것이지 실패를 덮는 것이 아니다.

### 무엇을 물었나 — attempt-023/024 가 만들고 답하지 않은 상태

attempt-023 은 스킵돼 있던 에이전트 실행 루프를 되살리면서 도구 호출이 **승인 게이트**에서 멈추는
것을 발견했고, 게이트를 끄는 대신 **제품의 승인 경로**(`get_approval_manager()` +
`ApprovalDecision.ALWAYS_ALLOW`)로 동의를 만들었다. attempt-024 는 그 경로를 다시 쓰지 않았다.
그래서 "그 부여가 **무엇을 덮고**, **언제까지 살아 있고**, **사용자가 무엇에 동의했는가**"가
**재지 않은 채** 남았다 — 이 attempt 는 그 답을 **실물 코드에서** 잰다(문서를 읽고 판단하지 않는다).

### 먼저 센 것 — 고침 전 트리에서의 관측

증인 `attempt-025/repro/f33_always_allow_scope_witness.py` 를 **고침 전 트리 사본**
(`git archive 19520cfd`)에서 돌렸다. 로그 `logs/f33-witness-before.txt`, **exit 1 · 깨진 요구 6건**:

```
F-33 OPEN — 깨진 요구 6건
  · R4 부여 시각 보존: 부여 저장소가 `set` 이고 공개 조회가 시각·근거를 내지 않는다
  · R1b 동의 문구가 실제 범위를 말한다: 컨트롤의 이름이 `${selected.description} 항상 허용` 이고
        '도구 전체'를 말하는 문구가 화면에 없다
  · R3 UI 에서 되돌릴 수 있다: 대시보드 코드가 `reset-always-allowed` 를 부르지 않는다
  · R2 부여를 읽을 수 있다: 대시보드가 부여 목록을 읽는 표면이 없다
  · R2 부여를 읽을 수 있다: 라우트 표와 매니저 어디에도 부여 목록 조회 표면이 없다
  · R5 자동 승인 관측: 부여된 도구의 실행은 어느 기록에도 남지 않는다
```

증인은 **끝까지 돈다** — 없는 표면을 예외가 아니라 **위반**으로 센다. 첫 판본은
`measure_lifetime` 에서 `AttributeError` 로 죽어 **첫 위반 하나만** 보고했고, 그 상태로는 "고침 전
exit 1"이 "여섯 결함"을 뜻하지 않는다. 증인의 docstring 이 스스로 "고침 전 트리에서도 끝까지
돌아야 한다"고 적고 있었으므로 그 자체를 결함으로 보고 고쳐서 다시 쟀다.

그리고 **여섯째 위반(404)은 고침을 넣고 계약을 돌려서 발견했다** — `GET /always-allowed` 가
`/{request_id}` 에 가려 요청 ID 로 해석됐다. 이빨을 만들어 붙인 것이 아니라 **실제로 물어서**
알게 된 자리다.

### 요구 다섯과 그 자리

| 요구 | 자리 |
|---|---|
| R1. 부여 범위 == 동의 문구(도구 전체) | `ApprovalQueue.tsx` — 접근성 이름이 "도구를 항상 허용 (이후 모든 호출을 승인 없이 실행)"이고, 선택된 요청 옆에 "도구 전체"를 말하는 안내가 선다 |
| R2. 부여를 읽을 수 있다 | `ApprovalManager.always_allowed_grants()` · `GET /api/approval/always-allowed`(→ **`/{request_id}` 보다 먼저** 선언) · `ApprovalQueue` 의 부여 목록 |
| R3. 부여를 되돌릴 수 있다 | `reset_always_allowed()` 가 **되돌린 도구 이름을 돌려주고** 라우트가 `revoked` 로 낸다 — 조용한 해제는 검증할 수 없다 |
| R4. 언제·무엇에 대해 주어졌는지 보존 | `AlwaysAllowGrant(tool_name, granted_at, granted_for, auto_approved_count, last_auto_approved_at)` · 화면에 부여 시각과 근거 |
| R5. 동의 없는 실행이 관측된다 | `record_auto_approval()` — 집행 지점(`_register_approval_request`)과 자동 승인 지점이 세고, 화면이 "동의 없이 N회 실행"을 댄다 |

### 계약과 증인 (요약)

| 장치 | 내용 |
|---|---|
| 증인 | `repro/f33_always_allow_scope_witness.py` — 고침 전 **exit 1**(6건) / 고침 후 **exit 0**(5/5) |
| 계약(Python) | `tests/test_cr14_always_allow_scope.py` **15건** — R1~R5 + 대시보드 소스 계약(문구·목록·해제·근거·횟수) |
| 계약(대시보드) | `ApprovalQueue.test.tsx` **4건**(문구가 범위를 말한다 · 부여 목록이 근거·횟수를 낸다 · 해제 콜백 · 부여 0건일 때 비활성) · `approvalApi.test.ts` **3건**(전용 경로 · `revoked` 보고 · 이유/횟수 없는 payload 거부) |
| 회귀 | 기존 더블 2건이 실제로 깨졌다(인터페이스 확장) — 메서드만 더하지 않고 **무엇을 세는지**를 단언으로 박았다 |

### 이 attempt 가 **바꾼 것**과 바꾸지 **않은** 것

바꾼 것: 승인 경로의 **관측성**(저장 구조·읽기 표면·계수·해제 응답·동의 문구·경로 순서).
바꾸지 않은 것: **부여의 범위와 수명 자체** — 도구 전체를 덮고 프로세스 수명 동안 유지되는 것은
**설계 그대로**이고, 이 attempt 는 그것을 **바꾸지 않고 드러낸다**(드러내고 나서 화면이 그 사실을
정확히 말하게 했다). 판정은 **NO-GO 유지**이며 이 attempt 는 판정을 움직이지 않는다.

### 한계 — 이 attempt 가 **재지 않은** 것

- **부여의 만료·세션 스코프를 바꾸지 않았다.** "프로세스 수명"은 관측한 사실이고, 그것이 옳은
  정책인지는 **제품 결정**이다 — 이 attempt 는 결정하지 않는다(바꾸면 이 후보의 계약이 아니라
  새 요구가 필요하다).
- **선별적 부여(인자·경로 단위)는 없다.** 범위를 좁히는 것은 새 능력이지 결함 수정이 아니다.
- **감사 기록은 인메모리다** — 프로세스가 죽으면 `auto_approved_count` 도 사라진다(부여 자체와 같다).
- 대시보드 화면 계약은 **소스 계약 + vitest** 로 고정되고, **사람이 눈으로 보는 확인**은
  e2e/수동 QA 로 남는다(`manual-qa.md`).
- **추적되는 빌드 산출물(F-01)** — 대시보드 소스를 고치면 `src/antigravity_k/dashboard_dist/`
  번들도 **같은 후보**에 들어가야 한다. 넣지 않으면 게이트의 `dashboard-build` 가 작업 트리를
  옮겨 이어받기가 (옳게) 거부한다. 이 attempt 는 그 거부를 **실제로 겪고** 번들을 후보 안으로
  가져왔다.

### 측정 결과 (측정 완료)

**required gate 21/21 을 커밋된 후보 `a2f6f724` 에서 되돌리기 0회 · 단일 지문 `57e32c9a…` 에서
완주**했다. 세 배치가 **별개 프로세스**로 스스로 이어받았다(`새 보고서로 시작한다`(fast 18) →
`이어받는다`(tests 19) → `이어받는다`(heavy 21)).

| | attempt-024 | **attempt-025** |
|---|---|---|
| python-tests passed | 6302 | **6320** |
| python-tests skipped | 13 | **13** |
| dashboard-test | 81 files / 849 | **82 files / 855** |
| 소유자 없는 스킵 | 0 | **0** |
| 제품 런타임 코드 변경 | 0줄 | **있음(F-33 — 승인 경로의 관측성)** |

- **python-tests 6320 passed / 13 skipped / 16 deselected**(544.02s · 게이트 548.77s). 증가분 **+18**
  = F-33 계약 15건 + 라우트·해제 검사 3건. **스킵은 늘지 않았다**(13 → 13, 전부 소유자가 있다).
- **dashboard-test 82 files / 855 passed** — **스킵 신호 0건**(verbose 리포터). 증가분 +6 은 신규
  2파일(ApprovalQueue 4 · approvalApi 3).
- **api-e2e 9 · accessibility 35 · master-e2e ✅6/❌0 · python-benchmark 16 · docker-build 227.0s ·
  clean-machine-runtime 41.6s(3018 파일)** — 테스트 게이트 다섯과 clean-machine 이 보고한
  스킵은 **0건**(`python-tests` 만 13건).
- **mypy 482 files clean · basedpyright 0 errors · dependency-audit-python high/critical 0건 ·
  dependency-audit-dashboard 취약점 없음 · ruff·format clean.**
- **드리프트 0** — `data/` 0 · `dashboard_dist` **0**(후보의 번들 == 게이트가 다시 빌드한 번들:
  빌드가 결정적임을 **두 번 돌려** 확인) · 실행 후 지문 재측정 **동일**.
- 마감 검사 **PASS(exit 0)** — 편입 전에는 같은 검사가 **FAIL exit 1** 이었다(보고서를 뺀 사본으로
  재구성 — `logs/close-check.txt`). 두 결과를 가른 것은 **보고서의 존재 하나**다.
- **회귀**: `tests/test_cr14_always_allow_scope.py` 15 · `test_approval_*` 4파일 ·
  `test_tool_executor.py` · CR-14 계약 4파일(fence·skip-register·attempt-close·close-procedure) +
  CR-12 docs 계약 — **176 passed · 1 skipped**, 대시보드 26 passed.

> **이 attempt 는 attempt-002 이후 처음으로 제품 런타임 코드를 바꾼 attempt 다.** 판정을 움직이지
> 않는 이유는 `decision.md` 에 적었다: 남은 차단 사유는 **사람·조직 축**(EX-01~06 · C14-08 ·
> C14-03/04/05)이고, 여기서 바뀐 것은 **부여의 범위·수명이 아니라 그것의 관측성**이다.

### 이 attempt 가 만든 새 한계

| ID | 내용 |
|---|---|
| **R-17** | 부여의 범위(도구 전체)·수명(프로세스)은 **드러낸 사실**이고 **정책 결정은 하지 않았다** — 선별 부여(인자·경로 단위)는 **새 능력**이다 |
| **R-18** | 감사 기록(`auto_approved_count`·`last_auto_approved_at`)은 **인메모리**다 — 부여 자체와 같은 수명 |
| **R-19** | 대시보드 화면은 **소스 계약 + vitest** 까지만 자동으로 잡힌다 — 사람이 보는 확인은 `manual-qa.md` |

## attempt-024 갱신 (2026-09-13) — 게이트 **전수**가 자기 스킵을 소유한다 (R-16 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-021 이 등록부(`scripts/gate_skip_register.json`)를 만들면서
스스로 한계로 적어 둔 항목(R-16)을 닫았다: "무엇이 스킵되는가"를 소유하는 단위가 **게이트
`python-tests` 한 곳**이었는데, 같은 후보가 **required gate 21개**로 초록을 만들고 그중 **다섯이
테스트를 돈다**. 나머지 넷의 스킵은 **아무도 세지 않았다** — 한 게이트가 테스트를 조용히 빼도
초록은 그대로였다. 이번에도 **제품 런타임 코드 변경 0줄**이고, 바뀐 것은 **게이트 명령 2줄 ·
등록부 · 계약 · 마감 검사**다.

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `e2885734…` · 지문 `7ae9af28…` 이며, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다
(작업 트리 변경은 ` M vault_data` 한 줄뿐 — F-13).

### 먼저 센 것 — 넓히고 나서 셈한 것이 아니다

증인(`attempt-024/repro/r16_gate_skip_visibility_witness.py`)이 **고침 전에** 게이트별로 물었다:
무슨 러너인가 · 스킵이 **요약에 보이는가** · **테스트 단위로 귀속되는가** · 실제 실행에서 몇 건인가 ·
수집 소스에 스킵 마커가 있는가. 결과가 아래 **세 자리**를 가리켰고, 그때 고쳤다(고침 전 exit 1 →
고침 후 exit 0).

| 자리 | 무엇이 문제였나 (관측) | 어떻게 닫았나 |
| --- | --- | --- |
| `api-e2e` | `pytest tests/test_e2e_smoke.py -q --tb=short` — `-q` 단독은 스킵이 생겨도 `N skipped` 만 남긴다. 등록부가 세야 할 대상이 **이름을 잃으면** 소유가 성립하지 않는다 | `-rs` (스킵 요약에 이름·사유) |
| `dashboard-test` | vitest **기본 리포터는 건수만** 낸다 — 스크래치 테스트로 실측(`Tests 1 passed \| 1 skipped (2)`) | `--reporter=verbose` → `↓ <파일> > <describe> > <테스트>` |
| `clean-machine-runtime` | 스크립트가 `--skip-e2e`·`--skip-wheel` 을 갖고, 켜지면 요약에 `SKIP` 행이 생기면서 **게이트는 exit 0** 으로 남는다. 명령에는 지금 그 플래그가 없지만 **그 사실을 지키는 자리가 없었다** | 등록부 `skip_channels` 선언 + 계약이 **스크립트의 모든 스킵 표기 ⊆ 선언**과 **게이트 명령이 그 플래그를 쓰지 않음**을 잰다 |

`accessibility-e2e` 는 **고칠 것이 없었다** — playwright 의 `list` 리포터가 스킵을
`- 1 [chromium] › <파일>:<줄> › <이름>` 으로 낸다(스크래치 스펙으로 실측). 그래서 그 게이트에는
귀속을 **고정하는** 조항만 넣었다(리포터를 바꾸면 계약이 멈춘다).

### 소유를 어떻게 잠갔나 — 세 겹

1. **전수성**(게이트 계약): `test_every_required_gate_is_classified_for_skip_visibility` 가 manifest 의
   required 21개와 등록부의 분류 21개를 대조한다. **게이트를 추가하면 분류도 적어야 한다** —
   빠뜨리면 그 게이트의 스킵이 다시 익명이 되므로 그 자리에서 멈춘다(개수 고정이 아니라 목록 고정 —
   F-21 과 같은 이유).
2. **귀속**(게이트 계약): pytest 게이트는 `-v`/`-rs` 중 하나, vitest 는 `--reporter=verbose`,
   playwright 는 설정의 `list` 리포터를 **실제 명령·설정에서** 확인한다. vitest·playwright 가 수집하는
   소스에 스킵 마커가 생기면 tripwire 가 먼저 멈춘다(현재 **0건**).
3. **실제 실행**(마감 검사): `scripts/verify_attempt_close.py` 의 **조항 8** 이 편입된 보고서에서
   `close_check` 게이트의 스킵 건수를 읽는다(러너 요약 건수 + 셸 스크립트의 `SKIP` 행, 색상 이스케이프를
   벗기고). 소유자 없는 게이트가 스킵을 보고하면 **마감 FAIL** 이다. 게이트 안에서는 보고서가 아직
   없으므로 이 관측은 **마감 단계가 유일한 자리**다 — F-24 가 세운 위치와 같다.

등록부를 읽을 수 없으면 마감 검사는 **침묵하지 않는다**(그 자리가 바로 소유자 없는 스킵이 숨는 자리다).

### 증인 — 고침 전/후와 세 겹의 소유 (`attempt-024/repro/r16_gate_skip_visibility_witness.py`)

증인은 **고침 전 exit 1**(검사 A·B 실패) / **고침 후 exit 0**(5/5)이다. 각 검사는 주장이 아니라
**실제 입력**을 본다:

  A. 테스트 게이트가 스킵을 **테스트 단위로 귀속**시킨다 — pytest `-v`/`-rs` · vitest `--reporter=verbose` ·
     playwright `list` 를 **실제 명령·설정에서** 확인(고침 전에는 `api-e2e` 의 `-q` 단독과
     `dashboard-test` 의 기본 리포터가 여기서 걸렸다).
  B. 등록부가 required 게이트를 **전수 분류**한다 — required **21**개 == 분류 **21**개.
  C. `close_check` 게이트의 **실제 실행** 스킵이 0건이다 — 관측 대상 5개(`accessibility-e2e` ·
     `api-e2e` · `clean-machine-runtime` · `dashboard-test` · `python-benchmark`)가 보고한 스킵 0건.
  D. 스크립트 게이트가 **스킵 플래그를 쓰지 않는다** — 선언된 채널
     `{'clean-machine-runtime': ['--skip-e2e', '--skip-wheel', 'SKIP_E2E', 'SKIP_WHEEL']}` 가
     게이트 명령에 없다.
  E. vitest·playwright **수집 소스의 스킵 마커가 0건**이다(`dashboard/src`·`dashboard/e2e` 스캔) —
     tripwire(런타임 스킵이 소스에 심어지면 먼저 멈춘다).

### 측정 결과 (측정 완료)

**required gate 21/21 을 커밋된 후보 `e2885734` 에서 되돌리기 0회 · 단일 지문 `7ae9af28…` 에서
완주**했다. 이 attempt 는 스킵을 **되찾은** 것이 아니라 이미 도는 것들의 **가시성·소유**를 넓혔으므로
초록이 덮는 범위가 넓어졌다(스킵 수 자체는 불변):

  | | attempt-023 | **attempt-024** |
  | --- | --- | --- |
  | python-tests passed | 6291 | **6302** |
  | python-tests skipped | 13 | 13 |
  | python-tests deselected | 16 | 16 |

  증가분 **+11** = 등록부 계약 신규 5건(전수성·귀속 플래그·비-pytest 이름 보고·스크립트 채널·마커 tripwire)
  + 마감 검사 이빨 6건.

  나머지: python-benchmark **16 passed · 스킵 0건**(17.55s) · dashboard-test **81 files / 849 passed · 스킵 0건**
  (verbose 리포터) · api-e2e **9 passed · 스킵 0건**(`-rs` 가 붙은 뒤 첫 실행) ·
  accessibility-e2e **35 passed · 스킵 0건** · clean-machine-runtime **`SKIP` 행 0건**(41.72s — 클린머신
  재현 성공) · master-e2e ✅6/❌0 · docker-build 30.42s · dependency-audit-python high/critical 0건 ·
  dependency-audit-dashboard 0건 · python-mypy **482 files clean** · python-basedpyright 0 errors ·
  **드리프트 0** · 실행 후 지문 재측정 **동일**. 세 배치가 **별개 프로세스**로 스스로 이어받았다
  (`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)).

  **마감 검사 조항 8 이 켜진 채로 통과했다** — 편입된 보고서에서 `close_check` 게이트 5개의 스킵 건수를
  읽어 대상 5개가 **보고한 스킵 0건**이라 PASS 했다(꺼져 있어서 초록이 나온 자리가 아니다). 편입 **전**에는
  같은 검사가 FAIL exit 1 이었다(보고서를 뺀 사본으로 재구성해 실측 — `logs/close-check.txt`).
  기록 커밋(`docs/` 전용) 뒤에도 지문 불변 · `candidate..HEAD` 코드 스코프 변경 `[]` · close 재실행 PASS.

  manifest sha256 은 게이트 **목록**이 아니라 명령 2줄이 바뀌어 attempt-023 의 `a18ff1e5…` 에서
  **`86c40edc…` 로 이동**했다 — 마감 검사 조항 ④가 그 일치를 요구하므로 21개를 다시 돌렸다.

### 한계

- 등록부는 여전히 **required 게이트의 환경**만 본다 — 비-required 게이트·개발자 ambient·CI matrix·
  weekly job 의 스킵은 소관이 아니다(각자 소유자가 있다: `ci.yml`·`weekly-drift.yml`).
- 마감 검사가 보는 것은 **건수**다. 무결성은 계약(귀속 플래그·스크립트 채널)이 지키지만, 러너가
  건수를 내지 않는 형태로 스킵을 만들면 그 자리는 보이지 않는다 — 그래서 `per_test` 게이트가
  **귀속 플래그를 갖는 것이 계약**이다.
- R-13 · R-14 · R-15 · R-2/R-3/R-4/R-6/R-7 은 변동 없다.

## attempt-023 갱신 (2026-09-13) — 스킵된 에이전트 루프는 **제품 결함이 아니라 계약 드리프트**로 죽어 있었다 (F-32 · `orchestrator-refactor-rewrite` 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-021 이 등록부(`scripts/gate_skip_register.json`)에 올린 미검증
능력 4건 중 마지막 2건을 이 attempt 가 닫았고, 그 결과 **소유자 없는 스킵은 0건**이 됐다. 노트:
이번에도 **제품 런타임 코드 변경 0건** — 고친 것은 **테스트가 기대하던 계약**이다.

### 선언 (측정 **전** — D-52)

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
즉 후보 `ed9e225a…` · 지문 `37b76cb8b340bbb8`… 이며, 선언 시점에 **후보 트리 == 작업 트리**임을
확인했다(작업 트리 변경은 ` M vault_data` 한 줄뿐 — F-13).

> **이 선언은 처음에 계약에 걸렸다** — 계약은 카드에 선언 자리가 **각각 정확히 하나**여야 한다고
> 요구하는데(`declared_values`), 이 절에 `code candidate full SHA: …` 를 한 번 더 적어 후보가 2개가
> 됐고, 그 상태로 돌린 `python-tests` 가 실패했다(후보 2 · 지문 1). 값을 복제하는 것은 "값의
> 소유자는 하나"라는 규율을 정면으로 어기는 일이라, 이 절은 카드를 **가리키기만** 한다. 고침은
> `docs/` 안이라 지문이 움직이지 않았고, **선언(후보·지문)은 그대로 유효하다**.

### 무엇을 닫았나 — "고칠 것이 남았다"가 "고칠 것이 제품에 있었다"는 뜻은 아니다

무조건 스킵(`@pytest.mark.skip`, 조건 없음)은 **어떤 환경에서도 돌지 않으므로** 그 자리에 남은 것은
"아직 아무도 재지 않았다"는 사실뿐이다. 그 사실은 두 갈래를 구분하지 않는다: **제품이 못 하는 일**과
**재는 도구가 대상을 놓친 일**. 이번 2건은 후자였다 — 그리고 후자를 전자로 오해하면 있지도 않은
결함을 좇게 된다.

관측이 그 구분을 했다(고침 **전** 코드를 그대로 스킵 해제해 돌리면):

| 걸린 것 | 왜 걸렸나 | 어떻게 맞췄나 (게이트는 그대로) |
| --- | --- | --- |
| `manager.router` 없음 (더블 2개) | 툴 루프가 `manager.router.get_combo(...)` 로 콤보를 판정하는데(`tool_loop.run_loop`), 실제 `ModelManager` 는 생성자에서 `self.router` 를 **항상** 만든다 | 더블에 `_StubRouter` 를 둔다(콤보 없음) |
| `get_model_info(name)` (더블) | 인자를 **요구하는 쪽이 틀렸다** — 실제 `ModelManager.get_model_info()` 는 `status()` 의 별칭이며 **인자를 받지 않는다**(`self_capability._model_info` 가 인자 없이 부른다) | 더블의 시그니처를 맞춘다 |
| 도구 호출이 승인 정지 | CR-04/CR-05 의 승인 게이트가 이 테스트 **이후에** 생겼다 | 게이트를 끄지 않고 **제품의 승인 경로**로 동의를 만든다: `get_approval_manager()` 에 `ApprovalDecision.ALWAYS_ALLOW` 기록(대시보드 '항상 허용'과 같은 상태). 나머지 게이트는 그대로 산다 |
| 셀 경로 경계가 실행 거부 | 스크립트가 `sys.executable`(저장소 venv — 테스트의 프로젝트 루트 밖)로 실행하려 했다. **경계 판단이 옳다** | 경계를 우회하지 않고 명령을 **루트 기준 상대 경로**로 바꾼다(`python3 <file>`) — 경계는 그대로 재어진다 |
| `manager.calls == 2` 가 거짓 | 더블이 한 턴을 **두 번** 셌고(`stream_generate` → `self.generate()`), 재시도 예산이 **패키지 기본 config**(`quality_gate.max_retries: 2`)에서 와 환경 의존적이었다 | 더블이 `_answer()` 한 곳에서 한 번만 세게 하고, 테스트가 예산을 1로 **고정**한다 → `calls == 2` 는 "초기 1턴 + 재시도 1턴" |

**약화시킨 게이트는 없다** — 동의는 제품 경로로 만들었고, 경계는 그대로 두었으며, 도구 경계·보안 정책은
건드리지 않았다. 두 테스트는 이제 조건 없이 돌고 **통과**한다(**6 passed / 0 skipped** — 실측).

### 계약 — 닫아도 **관측은 줄지 않는다**

등록부는 두 파일을 `closed` 로 옮기면서 **`observed_files` 에는 남겼다**. 그래서 무조건 스킵이돌아오면
대조(`observed == declared`)가 **즉시 실패**한다 — 이 성질은 attempt-022 가 F-31a 로 세운 것이고,
이번 attempt 는 그 성질을 **처음으로 실제로 쓴다**(그 attempt 들이 닫은 다른 두 파일만 확인되던 자리).

또 하나: `KNOWN_GAP` 항목이 **0건이 되면** 그 계약 조항은 아무것도 재지 않게 된다. 그래서 그 항목이
0건일 때는 경계 문서가 **"미검증 능력 0건"을 명시**해야 하고, 계약이 그 문장을 요구한다 — 침묵을
"미검증 능력이 없다"는 증거로 읽지 않기 위해서다(이 저장소에서 반복된 병이 바로 *검사가 대상이
아니라 그 부재를 본다* 였다).

### 증인 — 고침 전/후와 등록부의 이빨 (`attempt-023/repro/f32_contract_drift_witness.py`, **9/9**)

  A. 고침 **전** 두 파일(커밋 `fba13c6c` 의 실제 코드)을 스킵 해제해 돌리면 **실패**하고, 그 실패가
     `manager.router` · `get_model_info` 에서 난다(제품 루프는 돌고 있었다).
  B. 고침 후 두 파일은 **6 passed / 0 skipped**.
  C. 닫힌 파일에 무조건 스킵을 **다시 심으면** 그 스킵이 관측되어 등록부 대조가 실패한다(F-31a 의 이빨).

권장: 고침 전/후를 같은 입력으로 재는 형태(A)는 다음 재확인에도 그대로 쓸 수 있다.

### 측정 결과 (측정 완료)

**required gate 21/21 을 커밋된 후보 `ed9e225a` 에서 되돌리기 0회 · 단일 지문 `37b76cb8…` 에서
완주**했다. 이번에는 초록이 덮는 범위가 **넓어졌다** — 스킵이 줄었다:

  | | attempt-022 | **attempt-023** |
  | --- | --- | --- |
  | python-tests passed | 6289 | **6291** |
  | python-tests skipped | 15 | **13** |
  | python-tests deselected | 16 | 16 |

  증가분 **+2** = 되살린 두 테스트 · 감소분 **−2** = 같은 두 건이 스킵에서 빠졌다.
  나머지: python-benchmark 16(6304 deselected · 18.21s) · dashboard-test **81 files / 849 tests** ·
  docker-build 35.82s · clean-machine-runtime 43.64s(클린머신 재현 성공) · master-e2e ✅6/❌0 ·
  api-e2e 9(20.20s) · accessibility 35 · dependency-audit-python PASS(high/critical 0 · 예외 5) ·
  dependency-audit-dashboard 0건 · python-mypy **482 files clean** · python-basedpyright 0 errors ·
  **드리프트 0** · 실행 후 지문 재측정 **동일**. 세 배치가 **별개 프로세스**로 스스로 이어받았다
  (`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)). 보고서 편입 뒤
  **마감 검사 PASS(exit 0)** — 편입 전에는 같은 검사가 FAIL exit 1 이었다(보고서를 뺀 사본으로
  재구성해 실측 — `logs/close-check.txt`).

  기록 커밋(`docs/` 전용) 뒤에도 지문 불변 · `candidate..HEAD` 코드 스코프 변경 `[]` · close PASS.
  등록부의 남은 스킵은 **13건**이고 **전부 소유자가 있다**(mlx 4 · unsloth 7 · access-pin 2) —
  **소유자 없는 스킵 0건** · **미검증 능력 0건**(경계 문서가 그 문장을 명시한다).

## attempt-022 갱신 (2026-09-13) — 배포된 코드가 **config 에서 찾는 이름**을 config 가 소유한다 (F-31 · `config-models-unregistered` 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-021 이 등록부(`scripts/gate_skip_register.json`)에 올린 미검증
능력 중 `config-models-unregistered` 를 닫았다 — 닫는 방식은 **삭제가 아니라 능력 복원**이다. 그리고
그 과정에서 그 항목의 정체가 드러났다: 두 테스트는 "제품 설정의 약속"을 재고 있었지만 그중 하나
(`collective-council`)는 **약속이 아니라 배포 경로**였다(F-31). **제품 런타임 코드 변경은 0건**이다 —
바뀐 것은 설정·테스트·계약·등록부다.

- 후보: **`d7e66a59c13ff57951422baef89c343cb146a2b6`** · 코드 지문 `6a51100f…`(값 전체는 §5 판정 카드가 소유한다)
- **F-31(제품 결함 — 배포된 `/benchmark` 의 기본 경로) — 이번에 발견·폐쇄.**
  `/benchmark run`(인자 없음)은 `BenchmarkHarness._default_targets()` 로 비교 대상을 정한다. 그 함수는
  콤보 이름 `collective-council` 을 **코드에 갖고** 있고 모델 목록은 `config.yaml` 의 `combos` 에서 읽는데,
  2026-05 세대 정리(`e462a8aa` "refactor: comprehensive engine cleanup" · `d131dc71` "security: … governance")가
  그 콤보를 **의도 기록 없이** 지운 뒤에도 코드가 남았다. 재현(실제 config): 기본 타겟은
  `['collective-council']` **하나**이고 그 이름은 콤보도 모델도 아니며 `route("collective-council")` 은
  `ComboNotFoundError` 로 끝난다 — `_execute_single` 이 그 예외를 삼키므로 기본 실행은 **오류 행(점수 0)** 을
  기록한다(비교할 단일 모델 쪽도 함께 사라져 "비교"가 성립하지 않는다).
- **왜 오래 숨았나 — 계약이 아니라 계약의 방식.** 유일한 회귀 테스트
  (`tests/test_benchmark_harness.py::test_default_targets`)는 `registry._raw` 에 **합성 매핑**을 주입한다.
  합성 입력에는 그 콤보가 늘 있으므로 **실제 config 가 무엇을 소유하는지는 결코 묻지 않았다** — 등록부가
  게이트 환경을 재현할 때 `_raw` 주입을 거부한 것과 같은 이유로, 새 계약은 **실제 파일**로만 잰다.
- **고침(설정 복원, 삭제가 아니다)** — `config.yaml`(워크스페이스 + 패키지 **2부**, 바이트 동일이 계약이다)에
  ① `collective-council` 을 `strategy: collective` 콤보로 되돌리고(멤버는 현재 로스터가 소유한 로컬 3모델:
  `qwen3.8` · `hf.co/unsloth/gemma-4-31B-it-GGUF:Q5_K_M` · `deepseek-r1:70b`), ② gemma-4-31B 를 reasoning
  로스터에 복원했다(`provider: ollama` 명시 — 이름에 슬래시가 있어 `_infer_provider` 가 클라우드로 오인한다).
  이로써 `RouteStrategy.COLLECTIVE` 경로가 **설정에서 처음으로 도달 가능**해지고, 스킵돼 있던 두 테스트
  (`Issue #57`)가 조건 없이 돈다(21 passed / 0 skipped 실측).
- **계약** — `tests/test_cr14_default_target_config_contract.py` 6건: 기본 타겟이 config 소유인가 ·
  비교가 성립하는가(평의회 + 개별 모델) · 콤보가 `collective` 전략에 참여 3개 이상인가 · config 안의
  참조(역할 기본값·콤보 멤버)가 로스터에 있는가 + **이빨 2건**(tmp 에 실제 YAML 을 써서 콤보를 지우거나
  멤버를 빼면 **같은 검사가 실패**한다 — 실패해야 할 입력에서 실패하지 않는 계약은 장식이다).
- **등록부의 구멍도 함께 닫았다** — 항목을 닫으면 그 파일이 관측 목록(`entries` 에서 파생되던)에서
  **사라져** 다시 스킵돼도 아무도 모른다(닫는 일이 관측을 줄인다). 관측 대상을 `observed_files` 로
  **고정**하고 닫힌 항목은 `closed` 에 적었다 — 그 파일에 스킵이 돌아오면 대조가 즉시 실패한다(스킵 17 → **15**).
- **증인** — `attempt-022/repro/f31_default_target_witness.py`(실제 config 로 기본 타겟을 계산하고 각
  이름의 소유자를 판정 — 네트워크·생성 호출 없음). 고침 **전**: 미해석 타겟 1건(`collective-council`) ·
  고침 **후**: 0건 · 멤버 3개 · `strategy: COLLECTIVE`.
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `d7e66a59` 에서 되돌리기 0회·단일 지문
  `6a51100f…` 에서 완주**했다. 이번에도 초록이 덮는 범위가 넓어졌다:

  | | attempt-021 | **attempt-022** |
  | --- | --- | --- |
  | python-tests passed | 6280 | **6289** |
  | python-tests skipped | **17** | **15** |
  | deselected | 16 | 16 |

  증가분 +9 = 신규 계약 6건 + 등록부 관측 목록 검사 1건 + **되살린 테스트 2건**. 나머지:
  python-benchmark 16(6304 deselected) · dashboard-test **81 files / 849 tests** · docker-build 226.74s ·
  clean-machine-runtime 42.58s(클린머신 재현 성공) · master-e2e ✅6/❌0 · api-e2e 9 · accessibility 35 ·
  dependency-audit-python high/critical 0건 · dependency-audit-dashboard 0건 · python-mypy 482 files clean ·
  python-basedpyright 0 errors · **드리프트 0** · 실행 후 지문 재측정 **동일**. 세 배치가 **별개 프로세스**로
  스스로 이어받았고(`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)), 보고서 편입 뒤
  **마감 검사 PASS(exit 0)** — 편입 전에는 같은 검사가 FAIL exit 1 이었다(보고서를 뺀 사본으로 재구성해
  실측 — `logs/close-check.txt`).
- **한계** — `config-models-unregistered` 는 **닫혔다**(능력으로 되돌렸다) · `orchestrator-refactor-rewrite`
  (에이전트 실행 루프 2건)는 **남는다** · R-16(등록부는 `python-tests` 환경만 소유) · R-13 · R-14 · R-15 ·
  R-2/R-3/R-4/R-6/R-7.

## attempt-021 갱신 (2026-09-13) — 게이트에서 **조용히 사라지는 테스트**를 소유한다 (F-30 / R-8 감사)

**판정은 NO-GO 로 유지한다.** attempt-013 이 스스로 "이 감사를 하지 않았다"고 적어 둔 항목(R-8)을
수행했다: **어느 테스트가 왜 조건부로 수집·스킵되는지, 그중 제품 능력을 실제로 재는 것이 있는지.**
게이트 환경을 lock 에 고정한 F-18 은 **도구 출처**를 바로잡았지만 그 대가가 조용했다 —
ambient 실행(attempt-011/012)의 스킵은 **13·6건**이었고 고정 뒤(attempt-013)에는 **40건**이다.
그 40건을 세어 보니 **어떤 파이프라인도 `documents` extra(pypdf)를 설치하지 않았다**
(CI 매트릭스는 `base`/`rag`/`mlx`, 주간 job 은 `mlx`/`unsloth`). 그래서 출하 능력인 PDF/DOCX 수집을
재는 **23건이 게이트·CI·주간 어디서도 돌지 않았다** — 게이트는 초록이었다. **제품 런타임 변경 0건.**

- 후보: **`1b0a024c790c79b58a5c377f865bfec7dc82bbea`** · 코드 지문 `15e79e84…`(값 전체는 §5 판정 카드가 소유한다)
- **고침 ①(커버리지 복원)** — 출하 extra `documents` 를 `python_backend` 게이트 6종의 환경에 넣었다.
  그 3파일 실측 **87 passed / 0 skipped**(pypdf 6.17.0 은 이미 `uv.lock` 에 있었다 — 설치 비용은 사실상 0).
  이로써 스킵은 40 → **17** 이다.
- **고침 ②(등록부가 소유한다)** — 남은 17건을 `scripts/gate_skip_register.json` 이 소유한다. 각 항목은
  분류와 이유를 갖고, 분류별로 **다른 방식으로 정당화**된다:
  - `ENV_PLATFORM`(mlx 4 · unsloth 7) — 게이트에 넣을 수 없는 플랫폼·충돌 의존성이다. "다른 job 이
    돌린다"는 말은 **그 워크플로가 그 파일을 실제로 돌 때만** 성립한다: 계약이
    `.github/workflows/weekly-drift.yml` 안에서 파일 이름을 찾는다(주장만 적고 아무도 돌리지 않는
    가장 흔한 거짓을 막는다). mlx 는 `ci.yml` 매트릭스(`deps: [base, rag, mlx]`)도 덮는다.
  - `ENV_CONFIG`(access-pin 2) — 이 환경에서 스킵되지만 **같은 경계를 required 게이트가 잰다**:
    `tests/test_cr04_shell_api_boundary.py` 가 PIN 을 세우고 토큰 없는 요청이 401 로 끝나는 것을
    확인하며, 그 파일은 게이트에서 **스킵되지 않는다**(계약이 등록부의 자기모순까지 잡는다).
  - **`KNOWN_GAP`(미검증 능력 4건)** — 이 감사의 가장 값어치 있는 결과다. **어디서도 돌지 않는다**:
    `orchestrator-refactor-rewrite`(에이전트가 프로그램을 만들고 실행하는가 · 코드 전용 답변에서
    품질 재시도가 도는가 — `OrchestratorAgent` 리팩토링 뒤 **조건 없는** `@pytest.mark.skip` 이 되어
    ambient 에서도 안 돈다) · `config-models-unregistered`(gemma-4-31B 등록과 collective-council
    세 모델 — `config.yaml` 에 그 항목이 없어 "약속이 이행됐는가"를 아무도 안 잰다). 각 항목은
    **owner·plan·review_due** 를 갖고 경계 문서에 적힌다 — 만료일이 지나면 계약이 실패한다.
- **계약(조용한 변화 금지)** — `tests/test_cr14_gate_skip_register.py` 가 등록부와 **실제로 돌린
  게이트 환경**을 한 건씩 대조한다. 두 방향 모두 실패다: 등록되지 않은 스킵이 생기면 **커버리지가
  조용히 줄었다**, 등록된 스킵이 사라지면 **등록부가 낡았다**. `--extra` 목록은 게이트 파일에서
  읽으므로, 누군가 `documents` 를 빼면 23건이 되돌아와 **거기서** 드러난다. 증인
  `attempt-021/repro/f30_skip_register_witness.py` **12/12** — 이빨 ⑦ 이 그 사실을 **실행으로** 확인한다.
- **경계 문서** — `docs/ga/CR14_GATE_COVERAGE_BOUNDARY.md`: 게이트가 **재지 않는 것**을 적었다.
  목적은 하나다 — `21/21` 을 "모든 것이 검증됐다"로 읽는 착각을 막는 것.
- **곁들여 찾은 내 결함** — 증인을 쓰다 ENV_CONFIG 검사가 *측정*이 아니라 *주장*(등록부)을 읽고
  있음을 드러냈다(F-29 와 **같은 병**이 내 계약에 있었다). 조항을 자기모순 검사로 좁히고 런타임 쪽은
  대조 계약에 맡겼다 — 증인이 계약을 고친 두 번째 사례다.
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `1b0a024c` 에서 되돌리기 0회·단일 지문
  `15e79e84…` 에서 완주**했다. 그리고 이번 초록은 **같은 21/21 이지만 덮는 범위가 넓다**:
  | | attempt-020 | **attempt-021** |
  | --- | --- | --- |
  | python-tests passed | 6251 | **6280** |
  | python-tests skipped | **40** | **17** |
  | deselected | 16 | 16 |

  **스킵이 줄어든 것이 이 attempt 의 초록이다.** 배치 셋이 **별개 프로세스**로 스스로 이어받았고
  (`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)), 보고서 편입 뒤 **마감 검사
  PASS(exit 0)** — 편입 전에는 같은 검사가 `FAIL exit 1`(지문 `15e79e84ec357ac8…`)이었다.
  나머지: python-benchmark 16(`6297 deselected`) · dashboard-test **81 files passed** ·
  docker-build 237.44s · clean-machine-runtime 42.11s · master-e2e 6/6 · api-e2e 9 ·
  accessibility 35 · dependency-audit-python high/critical 0건 · **드리프트 0** · 실행 후 지문 재측정 동일.
- **한계** — **R-8 은 닫혔다**(감사를 수행했고 대상이 등록부로 옮겨졌다) · R-5 닫힘 · R-11 닫힘 ·
  R-13 · R-14(러너 실행은 러너만이 답한다) · R-15 · R-2/R-3/R-4/R-6/R-7. 그리고 이번 감사가 남긴
  **R-16(신규)**: 등록부는 **게이트 `python-tests` 의 환경**만 소유한다 — `python-benchmark`·`api-e2e`
  등 다른 게이트의 환경과 CI 매트릭스의 스킵은 여전히 각자 소관이고, 그 목록들은 이번에 세지 않았다.

## attempt-020 갱신 (2026-09-13) — CR-12 소관 재확인(R-5): 개정이 **요구**를 지키는가 (F-29 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-014(F-22)는 CR-12 의 계약을 바꿨고(README 의 리터럴
요구 → 값을 소유한 문서를 가리킬 것), 그 변경을 **CR-12 소관으로 다시 확인**하라는 것이 §6 의
0-h(R-5)였다. 확인은 **발견을 낳았다**: 개정의 *방향*은 옳았지만 *확인 방법*이 요구보다 약했다.
**제품 런타임 변경은 0건**이다.

- 후보: **`a590786513403b5da535ec13eef0807ea51e4676`** · 코드 지문 `aad2601c…`(값 전체는 §5 판정 카드가 소유한다)
- **F-29(검증 장치 — `tests/test_cr12_docs_alignment.py`) — 이번에 발견·폐쇄.** 두 자리다:
  - ① **가리킴을 토큰으로 확인하고 있었다**: `README_VALUE_OWNER in text` — 요구는 "README 가 값을 소유한 문서를 **가리킨다**"인데 확인은 "그 **이름**이 어딘가 있다"였다. 증인이 개정 전 규칙의 **실제 코드**(`git show 3fb3fcb9:tests/test_cr12_docs_alignment.py`)를 꺼내 세 가지 품질 낮은 입력을 전부 **통과**시킴을 보였다: **(a)** 산문에 이름만 적기 **(b)** 링크를 **다른 문서**로 바꾸기 **(c)** 소유자 이름을 링크하면서 **그 파일이 없는 경우**. F-28 과 같은 병이다 — 의도가 아니라 표기를 본다. 이제 **실재하는 링크**를 요구한다(링크 대상의 파일명이 소유자이고 그 파일이 존재한다).
  - ② **"미커밋" in checklist** — attempt-001 에서는 참이었지만 후보를 커밋한(attempt-009) 뒤로는 **과거 attempt 기록 행**(docs/17 에 46건)이 그 문자열을 계속 공급해 검사가 무의미해졌고, 실패 메시지는 거짓을 말했다("코드가 미커밋이라는 사실이 체크리스트에 없다"). 요구를 **현재 상태 줄**로 좁혔다: `**현재:` 로 시작하는 그 한 줄이 **커밋된 후보**와 **GA 승인 없음**을 말해야 하고, 그 줄이 미커밋을 주장하면(부정 `미커밋 아님/없음` 제외) 실패한다. 과거 행의 "미커밋" 은 **기록**이므로 그대로 둔다.
- **R-5 의 결론**: 개정의 **의도는 보존됐다**(커밋≠승인 유지 · 값은 README 에 박지 않는다 · 값의 소유자는 판정 카드) 그리고 계약은 이제 **그 의도를 문다**. 바뀐 것은 **요구가 아니라 확인 방법**이다 — 계약을 약화시킨 자리는 없다(두 경우 모두 요구는 그대로이고 검사가 세워졌다).
- **곁들여 정정한 문서**: docs/17 의 **C12-05 수용 기준 문장**이 attempt-001 시점 그대로여서 "코드 **미커밋**"을 현재 요구처럼 적고 있었다 — 후보 커밋(attempt-009) 이후 요구는 "커밋된 후보 + 승인 없음 + 미배정 + 값의 소유자를 가리키는 링크"다(문서가 계약보다 낡아 있던 자리).
- **증인** — `CR-12/attempt-002/repro/cr12_r5_review_witness.py` **12/12**: 실물 README 는 개정 전·후 규칙이 **둘 다** 통과하고(개정이 실물을 깨지 않았다), 품질 낮은 입력 3종은 전부 **개정 전 규칙이 통과 → 지금 규칙이 거부**하며, 현재 상태 줄 규칙은 과거 기록의 "미커밋" 을 통과시키고 현재 줄의 미커밋 주장을 거부한다.
- **이빨** — `tests/test_cr12_docs_alignment.py` 26 → **28건**(+2): 포인터는 **링크**여야 하고 그 링크는 **실재**해야 한다(산문·다른 문서·없는 파일 3종을 심어 확인) · 현재 상태 줄은 **커밋된 후보**와 **승인 없음**을 말해야 하고 **미커밋을 주장하면 실패**한다(세 변형을 심어 확인).
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `a5907865` 에서 되돌리기 0회·단일 지문 `aad2601c…` 에서 완주**했다(python-tests **6251 passed / 40 skipped / 16 deselected** 522.15s · python-benchmark 16 · dashboard-test **849 passed(81 files)** · docker-build 35.45s · clean-machine-runtime 42.16s(`git archive HEAD` 로 커밋된 트리 검증) · master-e2e 6/6 100% · api-e2e 9 · accessibility 34 · dependency-audit-dashboard 0건 · `data/`·`dashboard_dist` 드리프트 **0** · 실행 후 지문 재측정 **동일** · 인벤토리 변동 없음). 세 배치가 **별개 프로세스**로 이어받았고(`[merge] 새 보고서로 시작한다`(fast 18) → `이어받는다`(tests 19) → `이어받는다`(heavy 21) — F-26·F-27 이 만든 성질이 이 attempt 에서 다시 실측됐다), `--stage close` 가 보고서를 증거 트리에 편입한 뒤 **마감 검사 PASS(exit 0)** — 편입 전에는 같은 검사가 `FAIL exit 1`(`선언된 지문을 측정한 gate 보고서가 없다`, 지문 `aad2601c70e4f4d0…`)이었다. `python-tests` 증가분 24건은 attempt-019(배선 계약 22건 + 이빨)와 이번 계약 26 → 28건이 추가한 **계약**이며 skipped·deselected 는 불변이다(제품 테스트 감소 없음).
- **한계** — R-2 · R-3 · R-4 · R-6 · R-7 · **R-13**(기록 뒤 게이트 재개 시 중단) · **R-14**(러너 실행은 러너만이 답한다) · **R-15**(버전 상향 뒤 재선언 필요) · **R-5 는 이번에 닫혔다**.
- **이 attempt 가 재확인에서 얻은 일반 교훈** — **개정한 계약은 다시 재야 한다.** 요구를 옮긴 사람의 문장("이제 가리킨다를 요구한다")은 증거가 아니고, 확인이 **의도가 실패해야 할 입력**에서 실패하는지 시험하지 않은 계약은 조항이 아니라 장식이다. 증인은 규칙을 **흉내내지 않고**(스텁은 규칙이 바뀌면 조용히 죽는다 — attempt-018 의 교훈) 개정 **전** 규칙의 **실제 코드**(`git show 3fb3fcb9:tests/test_cr12_docs_alignment.py`)를 git 에서 읽어 같은 입력에 물린다 — 그 형태는 다음 재확인에 그대로 재사용할 수 있다.

## attempt-019 갱신 (2026-09-13) — 마감을 **기계가** 돌린다 (R-11 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-016~018 이 만든 마감 검사(`scripts/verify_attempt_close.py`)와
마감 절차(`scripts/run_attempt_close.py`)는 "선언한 초록의 출처"를 확인하지만 **사람이 시작해야만**
작동했다 — attempt-018 은 그 사실을 한계 R-11 로 남겼다. 한계 목록의 문장은 다음 사람이 다시 잊게
만든다. 이번 attempt 는 그 문장을 파이프라인으로 옮겼다. **제품 런타임 코드 변경은 0건**이다.

- 후보: **`43cde98ea8ccf5d9d6a77996e571ecec209eefd3`** · 코드 지문 `7f19c3a7…`(값 전체는 §5 판정 카드가 소유한다) · 앞선 선언 `a92ec559`(지문 `a4e3e71d…`)는 **F-28 수정이 지문을 옮겨 낡았다**(그 시점의 측정은 실패했다 — 아래 F-28)
- **R-11 폐쇄(검증 장치 — `.github/workflows/ga-close.yml` · `.github/workflows/release.yml`)** — 마감 절차를 **기계가** 부른다:
  - `ga-close.yml` 이 `uv run --no-sync python scripts/run_attempt_close.py --attempt attempt-ci --stage all` 을 돌린다. **게이트 목록도 순서도 이 파일에 없다** — 매니페스트와 절차 스크립트가 소유한다(옮겨 적으면 갈라진다: F-18/F-24/F-27). 그래서 매니페스트에 게이트가 늘면 이 워크플로는 **고치지 않아도** 따라간다.
  - 트리거 셋: `workflow_call`(릴리스가 부른다) · `workflow_dispatch`(수동) · **`schedule` 매주 월요일 03:00 UTC(스스로 돈다)**. "사람이 시작해야 한다"가 여기서 끝난다 — 계약과 달리 이 장치는 **부르지 않아도 돈다**.
  - **릴리스가 막힌다**: `release.yml` 의 `publish-pypi`·`github-release` 가 `needs: [build, ga-close]` 다. 마감 절차가 실패하면 PyPI·GitHub Release 단계가 **시작되지 않는다**. 릴리스 쪽은 **부르기만** 한다(`uses: ./.github/workflows/ga-close.yml` — 스텝을 복제하지 않는다).
  - `fetch-depth: 0` 이 필요하다: 지문은 **git 객체**에서 계산되고 `후보..HEAD` 울타리도 이력으로 판정한다 — 얕은 클론이면 후보 커밋이 없어 두 조항이 무력해진다.
  - 실패해도 **보고서를 아티팩트로 남긴다**(`if: always()`) — "어느 게이트가 왜 실패했나"를 읽을 수 있어야 그 실패가 판정이 된다.
- **F-28(검증 장치 — `tests/test_rel01_clean_build_sbom.py`) — 이번에 발견·폐쇄.** 이 attempt 의 변경이 처음 돌린 `python-tests` 에서 **1 failed** 로 드러났다: `TestWorkflowOrder::test_publish_is_gated_behind_build_job` 가 `"needs: build"` 라는 **문자열**을 요구하고 있었다. 요구의 의도("publish 는 build 가 성공해야 시작한다")는 내 변경 뒤에도 지켜졌지만, 선행 조건이 **하나 늘자** 확인이 실패했다 — F-18/F-24/F-27 과 같은 병의 다른 얼굴이다: 그 셋은 **규칙을 복제**해 갈라진 경우이고, 이 경우는 **의도가 아니라 표기를** 요구해 갈라진 경우다.
  - **닫는 방식**: 요구는 그대로 두고 확인을 **의도**에 맞췄다 — `needs:` 목록을 파싱해 `build` 의 포함 여부를 본다(`needs: build` 와 `needs: [build, ga-close]` 가 **둘 다** 통과한다). 이빨은 그대로다: `needs: [ga-close]` 로 `build` 를 빼면 **실패**한다(실측).
  - **왜 계약이 먼저 깨지는가**: 파이프라인을 바꾸는 시도는 그 파이프라인을 검사하는 계약과 **먼저 충돌한다**(attempt-012 의 예고: "게이트를 손대면 계약이 먼저 깨진다"). 이번에는 그 충돌이 게이트 목록이 아니라 **계약의 표기 결합**에서 났다 — 그래서 계약을 약하게 만든 것이 아니라 **의도에 더 가깝게** 고쳤다.
- **이빨** — `tests/test_cr14_close_pipeline_contract.py` **22건**: 조항 6(절차를 부르는가 · 부를 수 있고 스스로 도는가 · publish 가 막히는가 · 부르기만 하는가 · 시도 이름이 **소유자의 글로브**에 맞는가 · 전체 이력·실패 삼키기 금지) + 이빨 9(배선을 **실제로 풀어 본다**: `needs` 제거 · 간접 의존만 남김 · 수동 실행 전용으로 바꿈 · 게이트 목록 복제 · 시도 이름을 글로브 밖으로 · 얕은 체크아웃 · `continue-on-error` · 스텝 복제 · 허용되지 않는 키) + 정합 7. 시도 이름은 **소유자의 상수**(`verify_attempt_close.REPORT_GLOB`)에서 읽은 접두사로 검증하고, 아티팩트 경로도 **절차의 함수**(`_artifacts_output`)로 계산된 이름과 대조한다 — 사본이 아니라 소유자에게 묻는다.
- **증인** — `attempt-019/repro/f28_close_pipeline_witness.py` 가 **실제 워크플로 파일**로 배선을 재고, 배선을 **풀어서** 계약이 무는지 확인한다 — **22/22**(기준선 9 · 푼 변형 8 · 측정 동일성 3 · 시도 이름·아티팩트 2). 그중 C 절이 이 attempt 의 측정과 파이프라인의 측정이 **같은 게이트 집합**임을 보인다(`--stage all` == `fast ∪ tests ∪ heavy`).
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `43cde98e` 에서 되돌리기 0회·단일 지문 `7f19c3a7…` 에서 완주**했다(python-tests **6249 passed / 40 skipped / 16 deselected** 535.13s · python-benchmark 16 · dashboard-test **849 passed(81 files)** · docker-build 231.66s · clean-machine-runtime 42.10s(`ref: HEAD`, 3010 파일) · api-e2e 9 · accessibility 35 · `data/`·`dashboard_dist` 드리프트 0 · 되돌리기 0회 · 실행 후 지문 재측정 동일). 게이트는 세 배치가 **별개 프로세스**로 이어받았고(`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)), `--stage close` 가 보고서를 증거 트리에 편입한 뒤 **마감 검사 PASS(exit 0)** — 편입 전에는 같은 검사가 `FAIL exit 1`(`선언된 지문을 측정한 gate 보고서가 없다`)이었다.
  - **F-28 이 실제로 그것을 중간에 멈춰 세웠다**: 첫 `python-tests` 가 **1 failed**(`test_rel01_clean_build_sbom.py` 의 문자열 결합)였고, 그 수정이 지문을 옮겨 앞선 선언이 낡았다 → attempt-019 **안에서 재선언**(후보 `43cde98e` · 지문 `7f19c3a7…`). 그 순간 **F-27 이 의도한 거부가 실제 흐름에서 작동**했다: 낡은 부분 보고서는 `ERROR 이어받을 수 없다: previous report is for candidate '43a947a5', not '0c772245'` + `rm <보고서>` 안내 + **exit 2** 로 막혔고, 보고서를 **덮어쓰지 않았다**(`logs/stale-report-refusal.txt` — attempt-017 이라면 조용히 새로 시작해 앞 배치 초록을 버렸을 자리다).
- **한계** — **R-11 은 닫혔다**(파이프라인이 절차를 부른다 · 매주 스스로 돈다 · 릴리스가 그것에 막힌다). 새 한계 둘: **R-14**(배선은 계약이 소유하지만 **이 저장소는 GitHub Actions 를 로컬에서 실행할 수 없다** — 러너에서의 21/21 은 러너만이 답한다. 그래서 보고서를 `if: always()` 로 아티팩트에 남겨 "어느 게이트가 왜"를 읽게 했다) · **R-15**(태그 직전에 **버전 상향 커밋**(코드 스코프)이 생기면 선언이 낡아 `ga-close` 가 멈춘다 — 태그 **전에** 재선언 + 재측정이 필요하다. 새 불편이 아니라 "기계가 확인한 주장"의 값이다). 그리고 R-2 · R-3 · R-4 · R-6 · R-7 · **R-13**(기록 뒤 게이트 재개 시 중단 — 이 attempt 가 실제로 밟았고, 그 시료를 남겼다).

## attempt-018 갱신 (2026-09-13) — 이어받기 **판단**을 게이트의 **규칙**에 위임한다 (F-27 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-017 은 마감 절차를 만들고(F-25) 그 절차를 직접 돌려 절차 자신이
초록을 잃는 결함을 닫았지만(F-26), 바로 그 수정이 **남은 자리** 하나를 만들었다: 이어받기 판단을
`(후보 sha, manifest sha256)` **두 축**으로 정의했는데, 게이트는 **세 축**(+ **작업 트리 지문**)을
본다 — 같은 질문("같은 코드인가")에 두 주체가 각자 답하는 상태다(F-27). 이번 attempt 는 그 판단을
게이트에 **위임**하고, 거부되는 조합에서 **조용히 새로 시작하지 않도록** 만들었다. **제품 런타임
코드 변경은 0건**이다.

- 후보: **`ecaeeecc8808275def43cb6fa09b4897ac4154b7`** · 코드 지문 `56971ed6…`(값 전체는 §5 판정 카드가 소유한다)
- **F-27(검증 장치 — `scripts/ga_gate.py` · `scripts/run_attempt_close.py`)** — 두 주체가 같은 질문에 다른 답을 하던 것을 **규칙 한 곳**으로 모았다:
  - 게이트가 `merge_refusal_reason(path, sha, manifest_sha, tree_fingerprint)` 를 **공개**하고, 자기 로더(`_load_carried_gates`)도 그 함수를 쓴다(규칙의 유일한 자리). 작업 트리 지문은 `worktree_fingerprint(root)` 로 공개하고 `main` 도 그 이름을 쓴다.
  - 절차는 `merge_identity`(세 축: HEAD sha · manifest sha256 · **게이트의** `worktree_fingerprint`)를 만들어 `merge_decision` 으로 **묻기만** 한다 — 복제하지 않는다.
  - **거부는 조용하지 않다**: 다른 코드 상태의 보고서가 있으면 이유를 대며 **exit 2** 로 끊고, 보고서를 **덮어쓰지 않으며**, 새로 시작하려는 사람에게 **`rm <보고서>`** 라는 명시적 한 걸음을 알려준다. attempt-017 은 이 자리에서 `[merge] 새 보고서로 시작한다` 를 찍고 exit 0 으로 넘어가며 앞 배치의 초록을 **조용히** 버렸다.
  - `close` 단계는 게이트를 돌리지 않으므로 **판단을 묻지 않는다** — 기록 커밋(docs 전용) 뒤의 재확인이 막히면 안 된다(그것이 지문 불변 확인의 자리다).
  - **곁들여 고친 것**: 카드를 읽을 수 없을 때 `_close` 가 **traceback 으로 죽었다** — 같은 관례(사용 오류는 exit 2)로 맞췄다.
- **이빨** — `tests/test_cr14_attempt_close_procedure.py` **20건**(12 → 20, +8): 세 축 각각에서 **"절차가 이어받는다" == "게이트도 이어받는다"**(파라미터화 4건) · **위임 증명**(규칙 소유자의 함수를 패치하면 절차의 답이 따라 움직인다 — 사본이 있으면 깨진다) · 다른 코드 상태의 보고서는 **exit 2 로 끊고 덮어쓰지 않는다**(실제 파일 digest 로 확인) · `close` 는 판단을 묻지 않는다 · 카드 부재는 사용 오류(exit 2).
- **증인** — `.omo/.../attempt-018/repro/f27_fix_witness.py` 가 **실제 CLI + 실제 게이트**로 8/8(세 축 일치 · 위임 · 거부 시 중단·미덮어쓰기·`rm` 안내 · close 단계는 묻지 않음). attempt-017 의 F-26 증인도 **스텁을 버리고 실물 게이트**로 다시 써서 재실행했다(5/5) — 그 증인이 재는 성질(프로세스가 앞 배치를 잃는가)은 F-27 수정 뒤에도 그대로다(**회귀 확인**), 다만 ④ 는 "다른 후보의 보고서를 **거부한다**"로 강화됐다.
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `ecaeeecc` 에서 되돌리기 0회·단일 지문 `56971ed6…` 에서 완주**했다(python-tests **6227 passed / 40 skipped / 16 deselected** 526.95s — 증가분 8건은 이 attempt 의 이빨이며 attempt-017 은 6219 였다 · python-benchmark 16 · dashboard-test **849 passed(81 files)** · docker 33.74s(레이어 캐시) · clean-machine 41.76s `ref: HEAD`(3010 파일) · api-e2e 9 · accessibility 35 · `data/`·`dashboard_dist` 드리프트 0 · 되돌리기 0회 · 실행 후 지문 재측정 동일). 새 마감 절차로 돌렸고 세 배치가 별개 프로세스로 이어받았다(`새 보고서로 시작한다`(18) → `이어받는다`(19) → `이어받는다`(21)). `--stage close` 는 `[merge] close 단계는 게이트를 돌리지 않는다 — 이어받기 판단이 필요 없다` 를 찍고 **편입 + 마감 검사 PASS(exit 0)** 했으며, 편입 전에는 같은 검사가 `FAIL exit 1`(`선언된 지문을 측정한 gate 보고서가 없다`)이었다.
- **한계** — R-2 · R-3 · R-4 · R-6 · R-7 · **R-11**(절차는 사람이 시작해야 한다 — CI/릴리스 파이프라인 연결이 다음) · **R-12 는 이번에 닫혔다**(F-27 폐쇄 → 더 이상 OPEN 이 아니다). 새 한계 **R-13**: 기록 커밋 뒤에 **게이트 단계를 재개**하면 그 보고서는 다른 후보의 것이므로 **끊긴다**(의도된 동작 — 조용한 손실 대신 명시적 중단) — 저장소 밖에서 실수로 돌리면 "왜 막히지"가 아니라 "무엇이 다른가"를 읽어야 한다.

## attempt-017 갱신 (2026-09-13) — 마감을 **명령 하나로** 만든다 (F-25, R-10 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-016 은 마감 검사를 만들고 "그것이 **사람이(또는 절차가) 돌려야** 작동한다"를 한계 R-10 으로 남겼다. 한계 목록의 문장은 다음 사람이 다시 잊게 만든다. 이번 attempt 는 그 문장을 **명령 하나**로 바꿨다 — `scripts/run_attempt_close.py`. **제품 런타임 코드 변경은 0건**이다.

- 후보: **`afa4d26f89b43bc3950e2bcff9de56066bfbb3da`** · 코드 지문 `29fac8a0…`(값 전체는 §5 판정 카드가 소유한다) — 앞선 선언 `8533319b` 는 **F-26 수정이 지문을 옮겨 낡았다**(그 선언은 측정 **전**이었으므로 attempt-017 안에서 재선언한다 — D-52 의 순서는 "선언 → 측정"이지 "선언 → 코드 수정 → 그대로 측정"이 아니다)
- **F-25(검증 장치, `scripts/run_attempt_close.py`)** — 마감 절차를 배치로 나누고 순서를 코드로 박았다: `--stage fast`(빠른 18개) → `--stage tests`(`python-tests`) → `--stage heavy`(`docker-build`·`clean-machine-runtime`) → `--stage close`(보고서 **편입** + 마감 검사) → 기록 뒤 `--stage close` 재실행(지문 불변 확인). 한 번에 돌리려면 `--stage all`.
  - **게이트 목록을 스크립트가 들고 있지 않다** — manifest 에서 **런타임에** 읽고, `fast` 는 "required 전체에서 무거운 셋을 뺀 나머지"다. 그래서 manifest 에 게이트를 추가하면 **빠짐없이** fast 에 들어간다(개수를 손으로 맞추는 경로를 열지 않는다 — C14-01c·F-21 과 같은 이유).
  - **순서가 검사의 의미다**: `close` 단계는 보고서를 증거 트리에 편입한 **뒤에만** 마감 검사를 돌린다. 편입이 빠지면 검사는 FAIL(exit 1)이고, 보고서가 JSON 이 아니면 편입 자체를 거부해 **깨진 증거를 만들지 않는다**(exit 2).
- **이빨** — `tests/test_cr14_attempt_close_procedure.py` 12건: 세 배치의 합집합 == manifest required **전부**(빠짐·중복 0) · `fast` 가 하드코딩이 아니라 **파생**인지(임의 목록으로 확인) · `close` 는 게이트를 돌리지 않는다 · 알 수 없는 단계·manifest 에 없는 무거운 gate 는 사용 오류 · **이어받기는 단계 순서가 아니라 보고서 정체성이 결정한다**(같은 후보·같은 manifest 일 때만 — F-26) · 게이트 argv 가 그 단계의 gate 만 담는다 · 실제 manifest 에서 세 배치가 의미를 가진다 · 보고서 편입이 내용을 보존한다 · 없는/깨진 보고서는 편입 거부 · **둘째 배치가 첫 배치 결과를 지우지 않는다**(F-26 의 이빨) · `close` 단계 CLI 가 PASS 를 내는 합성 레이아웃 · 보고서 없는 상태의 `close` 는 exit 2.
- **F-26(검증 장치, `scripts/run_attempt_close.py`)** — 절차를 **직접 돌려 보니**(dogfooding) 절차 자신이 초록을 잃는 결함이 드러났다. 각 `--stage` 는 **별개 프로세스**라 그 안에서는 "내가 첫 배치인가"를 알 수 없었고, 첫 구현은 `--merge-into` 를 **첫 배치에만 붙이지 않는** 규칙을 프로세스 기억으로 판단했다. 그 상태로 `--stage tests` 를 단독 실행하면 fast 18개의 결과를 **덮어썼다**(보고서 total 18 → 1). 판단 근거를 **파일의 정체성**으로 옮겼다: 보고서가 **같은 후보 sha·같은 manifest sha256** 을 이름 붙였을 때만 이어받는다(`existing_report_identity`·`should_merge`). 그래서 배치를 따로 돌려도 앞 배치를 잃지 않고, **다른 후보의 보고서는 여전히 물려받지 않는다** — 한 규칙이 단계 실행과 `--stage all` 을 모두 덮는다.
  - **왜 "첫 배치에만 안 붙인다"가 틀렸는가**: 그 규칙은 **호출 순서**를 전제한다. 사용자가 `--stage tests` 만 돌리거나 배치를 건너뛰면 전제가 깨지고, 깨진 결과는 **조용히**(보고서가 18개 초록에서 1개로 줄어드는데 exit 0) 남는다. attempt-013 의 F-18(게이트가 대상을 보지 않음)·F-22(기록이 증거를 낡게 함)와 같은 병 — **판단이 기억에 있으면 기억이 틀릴 때 틀린다**. 파일이 답을 들고 있으면 틀릴 수 없다.
- **검증(측정 완료)** — **required gate 21/21 을 커밋된 후보 `afa4d26f` 에서 되돌리기 0회·단일 지문 `29fac8a0…` 에서 완주**했다(python-tests **6219 passed / 40 skipped / 16 deselected** 526.15s · python-benchmark 16 · dashboard-test **849 passed(81 files)** · docker 231.31s · clean-machine 42.64s `ref: HEAD`(3010 파일) · api-e2e 9 · accessibility 35 · `data/`·`dashboard_dist` 드리프트 0 · 되돌리기 0회 · 실행 후 지문 재측정 동일). **이번에는 그 절차 자신으로 돌렸고**, 세 배치가 별개 프로세스로 이어받았다 — `[merge] 새 보고서로 시작한다`(18) → `[merge] 이어받는다`(19) → `[merge] 이어받는다`(21). 보고서를 증거 트리에 편입한 뒤 **마감 검사 PASS(exit 0)** 였고, 편입 전에는 같은 검사가 `FAIL exit 1`(`선언된 지문을 측정한 gate 보고서가 없다`)이었다 — 두 결과를 가른 것은 **보고서의 존재 하나**다.
  - **F-26 의 증인** — `repro/f26_merge_identity_witness.py` 가 임시 저장소에서 **실제 CLI** 를 별개 프로세스로 돌려 5/5 를 확인했고, 그중 ③이 옛 규칙을 그대로 재현한다: 둘째 프로세스가 `--merge-into` 없이 같은 파일에 쓰면 **3개 초록 → 1개, exit 0**(조용한 손실). 다른 후보의 보고서는 여전히 물려받지 않는다.
- **F-27(검증 장치, `scripts/run_attempt_close.py`) — OPEN · 다음 attempt 에서 닫는다(등록: attempt-017).** attempt-017 이 F-26 을 닫으면서 이어받기 판단을 `(후보 sha, manifest sha256)` 로 정의했는데, **그것은 게이트(`ga_gate`)의 규칙의 부분 복제다** — 게이트는 **세 축**(+ 작업 트리 지문)을 보고 하나라도 다르면 `_CarriedError` 로 **exit 2** 로 실행을 끊는다. 두 주체가 같은 질문("같은 코드인가")에 다른 답을 내는 조합이 실제 함수로 재현된다(증인 `repro/f27_merge_rule_agreement_witness.py` — `logs/f27-witness.txt`):
  - ① 모든 축이 같음 → 둘 다 이어받는다(일치)
  - ② **작업 트리 지문만 다름**(미커밋 코드 편집) → 절차는 "이어받는다"고 판단해 `--merge-into` 를 붙이고, 게이트는 거부해 **실행이 `cannot merge: …` 로 끊긴다**(exit 2). 손실은 없다 — **중단**될 뿐이다.
  - ③ 후보 sha 만 다름(docs 전용 기록 커밋) → 둘 다 이어받지 않지만 **거부한 뒤의 행동이 다르다**: 절차는 `[merge] 새 보고서로 시작한다` 를 찍고 **조용히** 새로 시작하며(exit 0 — 게이트 단계를 하나라도 돌리면 앞 배치 초록을 버린다), 게이트는 그 조합을 exit 2 로 거부한다. *지시된 흐름에서는 무해하다* — 기록 커밋 뒤에는 `--stage close`(게이트를 돌리지 않는다)만 돌리기 때문이다.
  - **왜 결함인가**: attempt-013 의 F-18·attempt-016 의 F-24 와 **같은 병**이다 — 같은 규칙을 두 곳이 각자 들고 있으면 갈라지고, 갈라지면 한쪽이 다른 쪽을 검사하지 못한다. **수정 방향**: 절차가 게이트의 규칙을 **그대로 물어본다**(지문까지 넘긴다 — 규칙을 복제하지 않는다). 그리고 **거부되는 조합에서는 조용히 새로 시작하지 말고 이유를 대며 끊는다**(F-26 이 가르친 것은 "조용한 손실을 없앤다"였다 — 남은 조용한 경로가 ③이다).
  - **이 attempt 에서 닫지 않은 이유**: 수정은 `scripts/ga_gate.py`·`scripts/run_attempt_close.py` 를 건드리므로 **새 후보**가 되고, 프로젝트 규율상(측정 전에 커밋 → 새 후보에서 21 gate 완주) 한 attempt 안에 섞을 수 없다. attempt-017 의 21/21 은 `afa4d26f` 의 것이고, 그 측정 뒤에 코드를 고치면 그 초록이 낡는다(F-22 의 교훈).
- **한계** — R-2(값 자체의 옳음은 보고서·카드가 소유) · R-3(`clean-machine-runtime` 은 시점 의존) · R-4(`vault_data`) · R-6·R-7(지문 스코프·심볼릭 링크 전제) · **R-11(신규)**: 절차는 **사람이 시작해야** 한다 — CI/릴리스 파이프라인에 연결하지 않으면 "돌리지 않음"을 기계가 막지 못한다(이번 attempt 가 줄인 것은 **잊을 수 있는 단계의 수**이지 사람의 결정 자체가 아니다) · ~~R-12~~ = F-27 은 **attempt-018 에서 닫혔다** · **R-13(신규)**: 기록 커밋 뒤에 **게이트 단계를 재개**하면 그 보고서는 다른 후보의 것이므로 **끊긴다**(의도된 동작 — 조용한 손실 대신 명시적 중단). 보고서를 지우라는 안내를 출력하지만, 사람이 그 안내를 읽어야 한다.

## attempt-016 갱신 (2026-09-13) — 선언한 초록의 **출처를 게이트 밖에서 확인한다**: attempt 마감 검사 (F-24, R-9 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-015 는 울타리 이동 탐지기를 계약으로 세웠지만, 그 계약은 **보고서의 존재**를 요구할 수 없다고 정직하게 남겼다(R-9) — 보고서는 게이트 실행이 끝날 때 쓰이므로 그 실행 **안에서는** 존재할 수 없다(순환). 그래서 "카드가 선언한 지문을 측정한 보고서가 실제로 있는가"를 묻는 자리가 비어 있었고, attempt-013 의 21/21 이 HEAD 가 아닌 트리를 가리키게 됐을 때 아무도 묻지 않은 것도 같은 구멍이었다. 이번 attempt 는 그 자리를 **게이트 밖의 마감 검사**로 채웠다. **제품 런타임 코드 변경은 0건**이다.

- 후보: **`0c33aa2e8149351cbf0e3b78e88cb1dbe2f3e913`** · 코드 지문 `1b84209e…`(값 전체는 §5 판정 카드가 소유한다) · evidence bundle 없음(attempt-002·013~015 와 같은 이유)
- **F-24(검증 장치, `scripts/verify_attempt_close.py`)** — `uv run scripts/verify_attempt_close.py` 가 마감 시점에 카드·보고서·manifest·울타리를 한 번에 대조한다: ① 선언 자리가 각각 하나 ② **선언된 지문을 측정한 보고서가 있는가**(R-9) ③ 그 보고서가 이름 붙인 커밋의 **코드 트리 == 보고서 지문** ④ 보고서의 **manifest sha256** 이 현재 manifest 와 같고 **required gate 목록**이 같은가 ⑤ required 전부 `passed`·`exit_code == 0`, 같은 지문에 실패한 실행이 없는가 ⑥ **카드의 `inventory / PASS / FAIL / NOT_RUN` 수치가 보고서 집계와 같은가** ⑦ 후보..HEAD 에 코드 스코프 변경이 없는가. exit code 는 `ga_gate_verify.py` 관례대로 0 = 마감 가능 · 1 = FAIL · 2 = 사용 오류.
  - **게이트에 넣지 않았다** — 넣으면 순환이 생겨 영원히 실패한다(보고서는 그 실행이 끝날 때 쓰인다). 이 검사의 존재 이유가 "게이트 밖"이라는 위치 자체다.
  - **지문 규칙의 단일화**: 커밋 측 지문 계산이 세 곳(게이트·울타리 계약·마감 검사)에 흩어질 뻔했으므로 `scripts/ga_gate.py` 의 `tree_fingerprint_of_commit`·`code_scope_changes` 로 올리고, 계약과 마감 검사가 **그 함수를 그대로** 쓴다(복제하면 규칙이 갈라져 옛 규칙을 검사하는 거짓 통과가 된다 — attempt-013 F-18 과 같은 병).
- **이빨** — ① 마감 검사 판정 함수를 임시 저장소·임시 증거 트리로 두드러 12조항을 확인(`tests/test_cr14_attempt_close.py` 15건: 보고서 없음·다른 지문 보고서·커밋되지 않은 트리 측정·required 실패·manifest 드리프트·인벤토리 목록 드리프트·손으로 적은 수치·summary 위조·울타리 이동·`docs/` 전용 커밋은 통과·선언 중복은 사용 오류·exit code 계약) ② **실제 상태**에 대고도 확인 — 현재 카드로 **PASS**, 옛 후보(`3fb3fcb9`)로 선언하면 `fence: … ['tests/test_cr14_fence_movement_detection.py']`, 게이트 수치를 `21 / 20 / 1 / 0` 으로 바꾸면 `card: … 보고서 집계와 다르다`, 증거 트리가 없으면 `선언된 지문을 측정한 gate 보고서가 없다`.
- **검증** — **required gate 21/21 을 커밋된 후보 `0c33aa2e` 에서 되돌리기 0회로 단일 지문 `1b84209e…` 에서 완주**(python-tests **6207 passed / 40 skipped / 16 deselected** 533.24s · python-benchmark 16 passed · docker 304.0s · clean-machine 41.4s `ref: HEAD` · `data/`·`dashboard_dist` 드리프트 0 · 실행 후 지문 재측정 동일). 보고서를 증거 트리에 편입한 뒤 **마감 검사가 실제 증거에 대고 PASS**(`ATTEMPT_CLOSE: PASS`, exit 0)했다 — 이번 attempt 의 목적이 그것이다.
- **마감 검사가 게이트 전/후로 뒤집히는 것을 실측했다**: ① 미커밋 상태에서 attempt-015 의 값(후보 `b5729b61` · 지문 `b637d8b9…`)으로 돌려 **PASS** — 이미 옳게 닫힌 attempt 를 통과시킨다(검사가 쓸 수 있는지 먼저 확인) ② 새 후보를 선언하고 게이트를 돌리기 **전**에는 **FAIL exit 1**(`선언된 지문을 측정한 gate 보고서가 없다`) ③ 게이트 21/21 뒤 보고서를 증거 트리에 편입하자 **PASS exit 0** — 같은 검사의 두 결과를 가른 것은 **보고서의 존재 하나**다.
- **증인** — `repro/f24_attempt_close_witness.py` 가 실제 카드·증거로 5개 상태를 두드려 **기대대로 5/5**(기준선 0건 · 보고서 없음 1건 · 게이트 수치를 `21 / 20 / 1 / 0` 으로 바꾸면 `card: … 보고서 집계와 다르다` · 옛 후보 선언 → `fence: … ['scripts/ga_gate.py', 'scripts/verify_attempt_close.py', 'tests/test_cr14_attempt_close.py', 'tests/test_cr14_fence_movement_detection.py']` · 보고서 손상 → `읽을 수 없다` + `출처가 없다`).
- **한계** — R-2(값 자체의 옳음은 보고서·카드가 소유) · R-3(`clean-machine-runtime` 초록은 시점 의존) · R-4(`vault_data`) · R-6·R-7(지문 스코프·심볼릭 링크 전제) · **R-10(신규)**: 마감 검사는 **사람이(또는 절차가) 돌려야** 작동한다 — 게이트가 아니므로 자동으로 강제되지 않는다(자동화하려면 릴리스 절차에 넣어야 하고, 그것이 이 검사를 게이트로 넣을 수 없는 이유와 같은 이유로 **attempt 마감 단계**에 속한다).

## attempt-015 갱신 (2026-09-13) — 사람이 눈으로 찾던 것을 **계약이 찾는다**: 울타리 이동 탐지기 (F-23, R-1 폐쇄)

**판정은 NO-GO 로 유지한다.** attempt-014 는 F-22 를 닫았지만, 그 이동을 찾아낸 것이 **사람의 눈**이었다는 사실을 한계 R-1 로 남겼다("지문 이동에 사후 탐지 계약이 없다"). 이번 attempt 는 그 문장을 계약으로 바꿨다. **제품 런타임 코드 변경은 0건**이다(바뀐 것은 검증 장치와 그를 강제하는 계약).

- 후보: **`b5729b61efdbc034327a644b92a7de89921af3d8`** · 코드 지문 `b637d8b9…`(값 전체는 §5 판정 카드가 소유한다) · evidence bundle 없음(attempt-002·013·014 와 같은 이유)
- **F-23(검증 장치, `tests/test_cr14_fence_movement_detection.py`)** — 탐지기는 **git 객체만으로** 커밋의 코드 지문을 계산한다(작업 트리 미사용). 그래서 미커밋 작업과 무관하게 "선언된 증거가 지금도 이 후보의 것인가"를 물을 수 있고, R-1 이 "진행 중 상태와 구분해야 해서 단순 동등 비교로는 만들 수 없다"고 한 지점이 여기서 성립한다 — 계약이 보는 것은 **커밋된 이력**이고, 진행 중분은 커밋되는 순간 후보가 되어 첫 조항이 값을 요구한다.
  - 조항 4개: ① 선언된 지문 == 선언된 후보 커밋 **트리** 지문 ② 후보..HEAD 사이 **코드 스코프 변경 0건**(F-22 의 탐지기 — 위반 경로를 **이름으로** 댄다) ③ 지문 함수와 `git status` 가 코드 스코프 청결에 대해 **같은 말**을 한다(제외 목록을 넓혀 파일을 조용히 무시하면 여기서 깨진다) ④ 보고서가 이름 붙인 커밋의 트리 == 보고서의 지문(커밋되지 않은 트리를 잰 보고서를 거부 — attempt-014 가 세운 순서 D-52 가 그 이유다)
  - ②와 ③은 **다른 것을 본다**: ②는 "울타리가 움직였는가", ③은 "울타리가 **보이는가**"를 본다(attempt-013 F-18 과 같은 병 — 검사 도구가 대상을 보지 않는다). ③은 지문 스코프와 **기준선 스코프**를 따로 들어 둘이 갈라지는 순간을 잡는다.
- **고쳤다고 말하지 않고 심어서 확인했다** — 실제 저장소를 건드리지 않고 `/tmp` 의 `git worktree` 사본에서 후보 뒤에 `README.md`(지문 **안**)를 고치는 커밋을 심었다: 기준선 **11 passed / 2 skipped** → 심은 뒤 **2 failed**(`후보 커밋 뒤에 코드 스코프가 움직였다 … README.md` · `HEAD 트리 지문 != 선언값`). 합성 이빨은 임시 저장소에 **실제 커밋**을 만들어 ① `docs/` 전용 커밋은 지문을 옮기지 않는다 ② `README.md` 만 고친 커밋은 옮긴다 ③ 제외 목록을 넓히면 ③이 문다 ④ 커밋되지 않은 트리를 잰 보고서와 실패한 required gate 초록을 거부한다. **이 저장소 자신의 이력**에 남은 F-22(`0593dd27` → 기록 커밋 `f95f22b9`)도 탐지기가 `['README.md']` 로 짚는다.
- **검증(선언 단계)** — 이 절과 §5 카드의 선언을 먼저 커밋하고(값 선언), 그 커밋된 후보에서 required gate 를 측정한다. 결과는 측정 뒤 이 자리에 채운다(D-52 순서).
- **한계** — R-2(값 자체의 옳음은 보고서·카드가 소유한다) · R-3(`clean-machine-runtime` 초록은 시점 의존) · R-4(`vault_data` 가 부모를 dirty 로 만든다 — 지문은 gitlink 를 `missing` 으로 보아 영향받지 않는다) · R-6(③은 게이트 스코프와 기준선 스코프가 갈라지는 순간을 잡지만, 기준선 자체가 문서와 어긋나면 `C14-F15-4` 가 먼저 깨진다) · R-7(심볼릭 링크가 코드 스코프에 들어오면 커밋 측 지문 계산을 링크 의미로 확장해야 한다 — 그 전제를 검사로 박아 두었다).

## attempt-014 갱신 (2026-09-13) — **기록이 증거를 낡게 만드는 경로를 닫았다**: 휘발성 값이 README 에 있었다 (F-22)

**판정은 NO-GO 로 유지한다.** attempt-013 은 21/21 을 `0593dd27`(지문 `2c5a15c8…`)에서 측정하고 그 결과를 **기록 커밋 `f95f22b9`** 로 옮겼는데, 그 커밋이 `README.md`(지문 **안**)의 값을 갱신해 **지문을 `b9590b01…` 로 옮겼다**. 그 순간 attempt-013 의 초록은 HEAD 가 아닌 트리를 가리키게 됐다(F-07/F-14 와 같은 병). 근본 원인은 README 가 **손으로 갱신해야 하는 값**을 담고 있었다는 것이고 — 최종 커밋의 SHA 는 커밋 전에 알 수 없으므로 그 값은 **구조적으로 항상 과거**를 가리킨다(실측: README 는 `54e4169a` 를 가리킨 채 후보가 `1207118d` → `0593dd27` → `ded52af6` 로 진행했다) — 값을 판정 카드 한 곳으로 모으고 README 는 그 문서를 가리키게 했다. **제품 런타임 코드 변경은 0건**이다(바뀐 것은 기록 방식과 그를 강제하는 계약).

- 후보: **`3fb3fcb935a771090ea0233695c27f7efb5c7f34`** · 코드 지문 `b6494f40…`(값 전체는 §5 판정 카드가 소유한다) · evidence bundle 없음(attempt-002·013 과 같은 이유)
- **F-22(기록/검증 장치)** — 증인 `repro/f22_fingerprint_scope_witness.py` 가 **git 객체에서** 지문을 독립 계산해 이동을 확정했다: `0593dd27` → `2c5a15c88570c8e1…` · 기록 커밋 `f95f22b9` → `b9590b0159296f74…`(**MOVE=True**) · 후보 `3fb3fcb9` → `b6494f40825b5ae1…`. 그 커밋에서 **지문 안에서 바뀐 파일은 `README.md` 하나**이고 `docs/**` 5개는 아무 영향도 주지 않았다 — 경계가 어디인지가 이 한 줄로 드러난다.
- **수정** — ① README 에서 휘발성 값을 제거하고 §5 판정 카드를 값의 소유자로 지목(`C14-F22-1/2`: hex 토큰 금지 — 오탐 방지로 최소 한 글자 a–f 를 요구해 날짜·버전은 미탐 · `required gate N` 금지) ② 세 기록 문서가 **"기록 커밋은 `docs/` 전용"** 을 밝히도록 강제(`C14-F22-3`) ③ **CR-12 계약 개정**: 그 계약은 이 자리에서 "README 가 후보 SHA 리터럴을 담을 것"을 요구하고 있었고 그 요구가 성립 불가능한 값을 강제하고 있었다(그 요구를 만족시키려던 시도가 지문을 옮겼다) — 요구를 **"값을 소유한 문서를 가리킬 것"** 으로 옮기고 리터럴을 금지했다. **의도(커밋은 승인이 아니다)는 유지**하고 커밋됨·승인 없음·미배정 검사는 그대로다.
- **이빨** — 실제 README 에 `3fb3fcb9` + `required gate 21/21` 을 심으면 계약 **3건이 실패**하고, `git checkout -- README.md` 로 원복하면 지문이 `b6494f40…` 로 **정확히 복귀**한다(`logs/f22-contract-teeth.txt`). 이빨 테스트는 **오염된 기준선에서 스스로 실패**한다(계약이 켜져 있는데 README 에 값이 있는 상태를 통과로 넘기지 않는다).
- **검증** — **required gate 21/21 을 커밋된 후보 `3fb3fcb9` 에서 되돌리기 0회로 단일 지문 `b6494f40…` 에서 완주**(python-tests **6179 passed / 40 skipped / 16 deselected** 509.3s — 증가분 5건은 이번에 추가·개정한 계약 · python-benchmark 16 passed · docker 226.2s · clean-machine 41.9s `ref: HEAD` · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 · **실행 후 지문 재측정 동일**). 코드를 측정 전에 커밋했으므로 HEAD 의존 재실행이 필요 없었다(D-52).
- **이 attempt 가 닫지 못한 것** — R-1: 지문 이동에 **사후 탐지 계약이 없다**("clean 커밋 트리에서는 선언된 지문이 작업 트리 지문과 같아야 한다" — 진행 중 상태와 구분해야 해서 단순 동등 비교로는 만들 수 없고, 이번엔 **사람이 눈으로** 찾았다). R-2: F-22 는 "README 가 값을 담지 않는다"를 강제하고 **값 자체의 옳음**은 보고서·카드가 소유한다. R-3: `clean-machine-runtime` 초록은 시점 의존(`ref: HEAD`). R-4: `vault_data` 가 여전히 부모를 dirty 로 만든다(F-13/R-13). R-5: **CR-12 계약을 개정했으므로 CR-12 담당의 재확인이 필요**하다(의도 유지·검사 대상 이동).

## attempt-013 갱신 (2026-09-13) — 검증 장치가 거짓말하고 있었다: **게이트 환경 비고정(F-18·F-19)** · **테스트 격리 누수(F-20)** · **부하 의존 임계값(F-21)**

**판정은 NO-GO 로 유지한다.** attempt-012 는 "같은 lock 3종 sha256 인데 게이트 환경이 달랐다"를 **원인 미특정 한계(R-6)** 로 남겼다. 이번 attempt 는 그 관측을 끝까지 따라가 네 건을 닫았고, 그 결과 **게이트 인벤토리(20 → 21)·`uv.lock`·"이전 초록이 무엇을 증명했는가"의 해석**이 바뀌었다. **제품 런타임 코드 변경은 0건**이다 — 네 건 중 세 건이 검증 장치의 결함이었다.

- 후보: **`0593dd27dbea4a7bc4796ad9807d14b9f3a62165`** · 코드 지문 `2c5a15c8…`(값 전체는 아래 §5 판정 카드가 소유한다 — `C14-F15-2` 계약이 선언 자리를 하나로 강제한다) · evidence bundle 은 만들지 않았다(GO 판정용 artifact 가 아니다 — attempt-002 와 같다)
- **F-18(검증 장치)** — 게이트는 `uv run --isolated --frozen <tool>` 이면 hermetic 하다고 전제했지만, dev 도구는 `[project.optional-dependencies].dev` 에 있고 `uv run` 은 그 extra 를 설치하지 **않는다**: 임시환경(64 패키지)에 pytest 가 없고(`find_spec('pytest') is None`), 도구가 없으면 uv 는 **호출 셀의 PATH** 로 떨어진다(`VIRTUAL_ENV` 무관 — PATH 우선순위가 결정했다). 증거는 같은 `uv.lock` sha256 을 가진 두 보고서다 — attempt-011 은 `.../.venv/bin/python3` + pytest 9.1.1 + 수집 6213 + skipped 13, attempt-012 는 `/Users/mr.k/miniforge3/bin/python3.13` + pytest 9.0.3 + 수집 6221 + skipped 6. 차이의 정체는 정확히 `TestAgainstInstalled` 7건(그 클래스 가드가 `import trl; import unsloth` 다) — R-6 의 답이다. PATH 앞에 가짜 도구를 두고 게이트를 그대로 실행하는 증인으로 확인했다: 수정 전 **HIJACKED 4/4**, 수정 후 pinned. **같은 결함이 범주를 가리지 않았다** — 보안 게이트의 `bandit` 은 pyproject 에 **선언조차 없어** conda base 의 1.9.4 를 실행하고 있었다.
- **F-19(검증 장치)** — 게이트를 실제로 고정하자 `python-tests` 가 `VectorStore requires chromadb but it is unavailable` 로 실패했다(dev 만: 해당 세 파일 `10 failed / 25 passed` · dev+rag: `35 passed`). chromadb 는 `rag` extra 이고 ambient 환경에 항상 있었기 때문에 20/20 초록이 나왔다. 제품 코드는 바꾸지 않았다(`VectorStore` 는 명확히 거부하고 `gbrain` 은 강등한다 — 설계대로).
- **F-20(테스트 격리)** — 키가 '호출자 IP'인 전역 상태 기계가 둘(slowapi `5/minute`, credential gate lockout)이고 TestClient 는 항상 같은 주소다. 순서만 다른 A/B: WS 통합 테스트 단독 `7 passed` vs 버너+WS `5 failed(429)` · auth 두 파일 `1 failed(403)`. **두 누수가 서로를 가려 왔다는 사실**이 핵심이다 — 레이트리밋이 먼저 차면 lockout 이 켜지지 않는다. 수정은 `tests/conftest.py::_reset_login_security_state`(autouse) 이고 개별 테스트 우회는 제거했다.
- **F-21(검증 장치)** — 고립 실행 2250~2265ms 인 성능 테스트가 6200여 개를 도는 같은 프로세스 안에서 **6084ms**(임계값 6000ms)였다. 검사를 빼지 않고 **옮겼다**: `python-tests` 는 `-m "not benchmark"`, **신규 required 게이트 `python-benchmark`** 가 `-m benchmark` 로 조용한 프로세스에서 돈다(16 passed / 16.9s).
- **검증** — 계약 3종 신규(9건) + 이빨 확인(게이트 `--extra` 제거 → 3 failed · `security-bandit` extra 제거 → 2 failed · conftest 무력화 → 1 failed · 성능 마커 제거 → 3 failed · 인벤토리 목록 편집 → 1 failed, 원복은 shasum 일치) · **required gate 21/21 을 커밋된 후보에서 되돌리기 0회로 단일 지문 `2c5a15c8…` 에서 완주**(python-tests **6174 passed / 40 skipped / 16 deselected** 506.6s · python-benchmark 16 passed · dashboard 81 files/849 · docker 223.0s · clean-machine 39.1s `ref: HEAD` · `data/` 드리프트 0 · **실행 후 지문 재측정 동일**).
- **해석이 바뀐 부분(중요)** — attempt-001~012 의 20/20 은 **ambient 도구**(conda base 또는 `.venv`)로 측정됐다: “스위트가 통과했다”로는 유효하고 “lock 이 검증됐다”로는 유효하지 않았다. F-01~F-17 폐쇄의 근거는 **코드 계약**이라 영향받지 않는다.
- **한계** — R-8(다른 extra 의 조건부 수집 미감사: pinned skipped 40 vs ambient 6/13) · R-10(계약이 `uv run` 을 중첩 실행해 스위트에 약 30초) · R-11(성능 임계값은 여전히 wall-clock) · R-12(격리는 하네스 수준, 제품은 IP 단일 키) · R-13(`vault_data`).

> **이 절은 그 시점의 실측이다 — 최신은 위의 attempt-013 절.** attempt-012 는 attempt-011 이 한계(R-4)로 남긴 `job.view` 무잠금 쓰기를 결함으로 승격해(F-16) 닫았고, 그 정리에서 드러난 F-17(취소가 이벤트 루프를 1010.7ms 세웠다 → 6.8ms)까지 닫았다.

## attempt-012 갱신 (2026-09-13) — attempt-011 이 남긴 구조적 잔여(R-4)를 닫았다: **종결 기록의 주인(F-16)** + 취소의 블로킹(F-17)

**판정은 NO-GO 로 유지한다.** attempt-011 은 "F-15 는 분류만 고쳤고 `job.view` 무잠금 쓰기 구조는 그대로다" 를 한계(R-4)로 적었다. 이번 attempt 는 그 문장을 **결함으로 승격**해 재현 → 수정 → 이빨 → 게이트 순서로 갔다.

- 후보: **`1207118d45cdb643b3a3e7bdd5743a5fb7b6ab7d`** · 코드 지문 `7ecb4fc2…`(값 전체는 아래 §5 판정 카드가 소유한다 — `C14-F15-2` 계약이 선언 자리를 하나로 강제한다)

**① F-16 — 종결 기록에 소유자가 없었다**

- 종결 상태(`status`/`termination`/`error`/`finished_at`)를 쓰는 주체가 둘(취소 라우트 · 잡 스레드)인데 "누가 최종 기록을 쓰는가" 규칙이 없어 **나중에 쓴 쪽이 이겼다.**
- 증인 A(취소가 먼저 기록되고 watchdog 의 `timeout` 이 0.35초 뒤 도착 — 실제 경로에서도 성립하는 순서)에서 **관측된 종결 기록이 두 개**였다: `[('failed','cancelled','cancelled by user'), ('failed','timeout','exit_code=-15')]`. API 는 `200 {"ok": true}` 로 취소를 접수했다고 답했는데 정착한 기록은 `timeout` 이다 — 사용자가 취소했다는 사실이 사라진다.
- 수정: 쓰기 단일 지점 `_Job.finalize()`(**먼저 확정한 쪽이 소유**, 재호출은 no-op) + `note()`(진행) + `snapshot()`(복사본 — `GET` 이 살아 있는 dict/list 를 넘기지 않는다) + `claim_cancel()`(1회 접수). 취소는 프로세스 종료보다 **먼저** 기록을 쓴다. 소유하지 못하면 `{"ok": false, "detail": "job already finished"}` — 예전에는 그 창에서 **완료된 잡의 기록을 덮고 `ok:true`** 를 돌려줬다.
- 이빨: 구 코드로 되돌리면 신규 회귀 6/6 실패, 그중 HTTP 회귀는 `assert 'timeout' == 'cancelled'` 로 **동작으로** 실패한다.

**② F-17 — 취소가 이벤트 루프를 세웠다**

- cancel 라우트가 `async def` 인데 본체가 `terminate_process_group`(내부 `proc.wait(grace)` 두 번 = 최대 2×grace)을 그대로 호출했다. 실측(heartbeat 최대 간격): 수정 전 실제 라우트 **1010.7ms**, 수정 후 **6.8ms**. 같은 본체를 루프에서 구동한 옛 모양은 1007.3ms 로 남는다. 요청 소요는 ~1.05초로 **불변** — 빨라진 것이 아니라 서버가 멈추지 않게 됐다.
- 수정: `def` 라우트(FastAPI 스레드풀). `await` 가 없으므로 동작 변화는 없다.

**검증** — required gate **20/20 을 커밋된 후보 `1207118d` 에서 되돌리기 0회로 단일 지문 `7ecb4fc2…` 에서 완주**(python-tests **6215 passed / 6 skipped** 464.6s · docker 230.4s · clean-machine 41.8s `ref: HEAD` · dashboard-build 드리프트 0 · `data/` 드리프트 0 · 실행 후 지문 재측정 동일). 이번에도 코드를 **측정 전에 커밋**해 HEAD 의존 gate 재실행이 불필요했다(D-52). 이 영역의 회귀는 **8건 신규**(총 29건)다.

**이 attempt 가 닫지 못한 것** — R-1: F-17 회귀는 블로킹을 **패치**해 잰다(절대 시간이 아니라 '루프에서 도는가'를 잰다). R-2: `iscoroutinefunction` 계약은 프록시이고 실제 보증은 heartbeat 회귀다. R-3: 취소 요청이 감독 확정보다 늦으면 취소는 기록을 갖지 못한다(`ok:false`) — 계약은 의도했지만 대시보드 문구는 미검토. R-4: `job.proc` 참조는 여전히 잠금 밖이다(단일 참조 대입). R-6(**미해결 관측**): 같은 lock 3종 sha256 인데 attempt-011 은 `test_unsloth_script_api_drift.py::TestAgainstInstalled` 7건을 **스킵**, 이번 실행은 **통과**시켰다(수집 6213 → 6221 = 신규 8건과 일치, skipped 13 → 6). 원인을 특정하지 못해 게이트 환경 재현성 신호로만 남긴다(`logs/skip-count-observation.txt`).

---

## attempt-011 갱신 (2026-09-13) — 계약화 + required gate 가 드러낸 **제품 결함 F-15** 폐쇄

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 기술 축이 닫힌 상태에서 두 가지를 더 했다: ① attempt-010 이 규율로만 남긴 지문 경계 규칙을 **계약**으로 옮겼고, ② 그 계약을 추가한 지문에서 `python-tests` 가 실패한 것을 **flake 로 넘기지 않고 파고들어 제품 결함을 찾아 닫았다**.

- 후보: **`d72b17111ceca8518d3f9f1fb1f3a22a04c176aa`** · 코드 지문 `e428aacc…`(값 전체는 아래 §5 판정 카드가 소유한다 — `C14-F15-2` 계약이 선언 자리를 하나로 강제한다)

**① 규율 → 계약 (D-56)**

- `tests/test_cr14_fingerprint_scope_contract.py`(9건, 그중 **5건은 위반을 심어 확인하는 이빨**): README 는 지문 값을 담지 않고 소유 문서를 가리킨다 · 지문 스코프(README·`tests/**`)는 선언된 현재 지문을 인용하지 않는다 · 제외 목록(`FINGERPRINT_EXCLUDED_PREFIXES = ("docs/", ".omo/")`)이 바뀌면 계약이 먼저 깨진다 · 세 기록 문서가 그 경계를 말한다.
- 이 커밋 자체가 지문을 이동시켰다(`d4a42ab8…` → `cdfbbb96…`) — 즉 **규율을 강제하는 행위도 증거를 낡게 만든다**. 그래서 게이트를 새 지문에서 완전히 다시 돌렸다.

**② required gate 의 일회성 실패는 flake 가 아니었다 (F-15)**

- 증상: `test_cancel_sets_termination_cancelled` 가 `assert 'completed' == 'cancelled'` 로 1건 실패 — **단독 실행은 5/5 통과**했다.
- 원인: API cancel 은 `cancel_event.set()` 과 **동시에** `terminate_process_group` 을 호출하는데, watchdog 은 0.2초 폴링이라 프로세스가 먼저 죽으면 `fired_reason` 을 세우지 못하고 루프를 빠져나간다 → `reason = "completed" if fired is None else fired` 가 취소를 완료로 분류(exit_code=-15)하고, 잡 스레드가 `job.view["termination"]` 으로 **취소 기록을 덮어쓴다**. 사용자는 취소했는데 잡은 `status=failed, termination=completed, exit_code=-15` 로 남는다.
- 재현 100%: 증인 A(폴링 간격 확대 = 경주 확정) 3/3 · B(실제 간격, API 와 같은 순서) **12/12 오분류** · C(정상 완료 뒤 취소) 통과 → 수정 후 A 0/3 · B 0/12 · C 유지(exit 1 → exit 0).
- 수정: 분류를 **관측이 아니라 사실**로 — `fired is None` + `cancel_event.is_set()` + `exit_code != 0` 이면 `cancelled`. 정상 완료(exit 0)는 오분류되지 않고, 그 방향은 회귀가 고정한다.

**검증** — **required gate 20/20 을 동결된 clean HEAD 에서 되돌리기 0회로 단일 지문 `e428aacc…` 에서 완주**(python-tests **6200 passed / 13 skipped** 467.75s · docker 233.3s · clean-machine 41.3s `ref: HEAD` · dashboard-build 24.1s 드리프트 0) · `data/` 드리프트 0 · 실행 후 지문 재측정 동일. 이번에는 코드 변경을 **측정 전에 커밋**했으므로 HEAD 의존 gate 재실행이 **필요 없었다**(attempt-010 은 이 순서를 어겨 재실행이 필요했다 — D-52 의 실증).

**이 attempt 가 닫지 못한 것** — R-1: API 수준 취소 검사는 여전히 경주에 의존한다(수정을 꺼도 통과할 수 있다 — 결정적 보증은 모듈 수준 회귀). R-2: 계약이 검사하는 것은 '지문 인용'과 '경계 서술'이지 문서의 모든 수치가 아니다. R-3: `clean-machine-runtime` 초록은 `d72b1711` 시점 HEAD 에 대한 것이다. R-4: **`job.view` 를 두 스레드가 잠금 없이 쓰는 구조는 그대로다** — 이번엔 그 증상(거짓 분류)만 닫았다.

---

## attempt-010 갱신 (2026-09-13) — 지문 경계 실측 + 동결 트리에서 20/20 재검증: **기록이 증거를 낡게 만들던 경계를 찾았다**

**판정은 NO-GO 로 유지한다.** attempt-009 가 측정한 코드 내용은 그대로이고, 그 내용을 **동결된 커밋 트리**에 묶었다. 대신 그 과정에서 이 저장소가 전제해 온 가정 하나가 **틀렸음**이 드러났다.

- 후보: **clean HEAD `5ccb938e5d31411b16f2a69e3015fc8fb826455d`**(커밋 4개) · 코드 지문 `d4a42ab87697ba299129719d054c9259a717628a1bc8f80d00cd03ae0e372ce7`(attempt-009 의 `dd34a76b…` 에서 이동). **값의 전체 자리는 §5 판정 카드로 옮겼다** — 선언은 하나여야 한다(attempt-013 에서 이 자리가 낡은 값을 소유하고 있었다).

**드러난 경계 — "문서를 써도 증거가 낡지 않는다"는 `docs/` 안에서만 참이다**

- 게이트 코드 지문의 제외 목록은 `FINGERPRINT_EXCLUDED_PREFIXES = ("docs/", ".omo/")` 이고 **경로 접두사 비교**다. 그래서 **`README.md`(루트)와 `tests/**` 는 지문 안**이다.
- attempt-009 기록을 쓰면서 커밋 계약 파일(`tests/test_cr12_docs_alignment.py`)을 고치자 지문이 `dd34a76b…` → `003205f2…` → `d4a42ab8…` 로 **이동**했다 — 그대로 두면 attempt-009 의 20/20 초록이 **후보가 아닌 트리**를 가리킨다(F-07 과 같은 병).
- 수정: README 에서 지문 **값**을 제거하고 **출처**(본 문서·보고서)를 가리키게 했다(D-51). 최신 값을 손으로 계속 갱신하는 대안은 **갱신하는 행위가 값을 낡게 만들어** 자기모순이라 기각했다.

**동결 트리에서 20/20**

- **커밋은 지문을 옮기지 않는다**(내용 hash 기반): README 수정본 미커밋 상태 `d4a42ab8…` == 커밋 `5ccb938e` 후 `d4a42ab8…`. 그래서 "트리 동결 → 커밋 → 측정" 순서가 보고서의 SHA 와 지문을 **같은 트리**로 묶는다(D-52).
- **required gate 20개가 되돌리기 0회로 단일 지문 `d4a42ab8…` 에서 20/20 PASS**(python-tests **6189 passed / 13 skipped** 463.3s · dashboard-test **81 files/849** · docker 233.7s · clean-machine 41.0s · dashboard-build 24.6s)이고 **실행 후 지문 재측정도 동일**하다. `data/` 드리프트 0, 실행 후 트리는 ` M vault_data` 한 줄.
- **HEAD 의존 gate 분리 재실행**(D-53): `git HEAD` 에 의존하는 것은 `dashboard-build`(핀을 읽어야 드리프트 0)와 `clean-machine-runtime`(`git archive HEAD`)뿐이라 이 둘만 clean HEAD 에서 다시 돌려 `gate-report-clean-head.json`(2/2 PASS)에 남겼다 — `ref: HEAD` 로 **3001 파일**을 아카이브했고 `git ls-tree -r HEAD` 도 3001 이며 아카이브의 README 가 커밋본임을 확인했다. **전체 인벤토리는 `gate-report.json`(20/20)** 이고 단독 보고서를 '18개 미실행'으로 읽으면 안 된다.

**F-14(신규/폐쇄)** — attempt-009 기록이 `frontend 846 passed(80 files)` 를 인용했으나 **같은 attempt 의 보고서는 `Test Files 81 passed (81)` · `Tests 849 passed (849)`** 였다(F-12 가 추가한 테스트 3건 이전 값이 넘어왔다). 이 저장소가 반복해 잡아 온 **'주장 ≠ 측정'** 병과 같은 모양이므로 수치를 정정하고, **수치는 그 attempt 의 `gate-report.json` 에서 직접 인용**하기로 했다(D-54).

**이 attempt 가 닫지 못한 것** — R-4: 규율을 강제하는 회귀(문서가 지문·수치를 인용하지 않는다)는 **아직 없다**(추가하면 그 자체가 지문을 옮겨 이 증거를 무효화한다 — 게이트 실행 직전에 만들어야 한다, D-55). R-2: 목표 지문에서 20/20 을 **한 보고서로** 본 것은 아니다(20/20 + 2/2 분리). R-3: `clean-machine-runtime` 초록은 `5ccb938e` 시점 HEAD 에 대한 것이다.

---

## attempt-009 갱신 (2026-09-13) — 후보 커밋 + F-12·F-07 폐쇄: **기술 축을 모두 닫았다**

**판정은 NO-GO 로 유지한다.** 달라진 것은 **커밋된 후보에서 20/20 을 완주**했고 **`clean-machine-runtime` 이 후보를 검증**했다는 점이다. 이제 남은 차단 사유는 **사람의 영역**(외부 승인·독립 검토·장기 검증)뿐이다.

**커밋 — 그리고 훅이 막은 것이 옳았다**

- 사용자 결정에 따라 **단일 커밋**으로 고정했다: `5a717c4a`(CR-01~CR-14 후보 268 파일) + `54e4169a`(F-12 수정 27 파일). `.omo/evidence/**` 는 `.gitignore`(.omo/)의 Phase 0 규칙대로 커밋하지 않았다(D-47).
- 첫 시도가 중단됐다 — `trailing-whitespace` 가 **생성 번들 11개를 다시 썼고** `check-added-large-files`(maxkb=1024)가 모나코·TS 워커(MB 단위)를 거부했다. 훅이 생성물을 소스처럼 다루면 커밋된 바이트와 `pnpm run build` 결과가 갈라진다.
- **`--no-verify` 로 우회하지 않고** 생성 경로를 훅 대상에서 제외했다(D-46). 훅이 고친 번들 11개는 **빌드 산출물로 되돌려** 커밋했다.

**F-12 — "빌드는 멱등"은 고정 HEAD 에서만 참이었다**

- 커밋 직후 `dashboard-build` 가 **자산 22개를 교체**하고 `index.html` 을 고쳐 지문이 이동했다(`07118329…` → `a4be7868…`). 같은 HEAD 에서 두 번째 빌드는 **no-op** 이었다.
- 원인: `dashboard/buildStamp.ts` 가 `AGK_BUILD_ID` 기본값으로 `git rev-parse --short HEAD` 를 쓴다. 번들에 커밋 SHA 를 박으면 **커밋된 번들은 자기 커밋의 SHA 를 담을 수 없다**(치킨-에그). `dashboard-build` 가 required gate 인 한 **커밋된 후보에서 단일 지문 20/20 을 완주할 수 없었고**, C14-01/C14-02 가 구조적으로 미충족이었다.
- attempt-003 의 F-01 서술("빌드는 바이트 단위로 멱등")을 **조건부로 정정**한다 — 그 실측 시점에는 HEAD 가 바뀌지 않아 참이었다.
- 수정: 해석 순서를 `AGK_BUILD_ID`(릴리스 주입) → **커밋된 핀 `dashboard/build-provenance.json`** → `git short SHA` → null 로 바꾸고, 번들을 핀 값(`5a717c4a`)으로 재생성했다. **핀 ≠ HEAD 는 정상이다** — 핀은 '번들을 만든 소스 리비전'을 기록하며, 그 커밋이 번들을 담고 있는 커밋과 같을 수 없다(그것이 이 결함의 내용이다). **핀을 맞추려고 amend 하지 말 것** — 같은 루프로 돌아간다.
- **부수 개선**: `.git` 이 없는 Docker 빌드도 핀을 읽어 출하 컨테이너가 **커밋된 번들과 같은 바이트**를 서빙한다(그전에는 buildId 가 UNKNOWN). 다만 이 효과는 이번에 컨테이너 안에서 두 번 빌드해 비교한 것이 아니라 해석 순서에서 따라오는 결론이다(R-5).

**F-07 폐쇄 — 게이트가 후보를 검증했다**

- `clean-machine-runtime` 은 `git archive HEAD` 를 쓴다. 커밋 전 초록은 후보가 아닌 낡은 HEAD(2877 파일)를 검증했다.
- 후보 커밋 `54e4169a` 에서 전 게이트를 재실행해 `ref: HEAD` 로 **후보 전체(3001 파일)** 를 아카이브·검증했다 → **이 초록은 후보의 근거다**.
- 순서 규율은 남는다: **릴리스는 태그 SHA 에서 이 gate 를 마지막으로 다시 실행해야 한다**(이후 커밋·rebase 가 있으면 초록이 다시 낡는다 — R-3).

**검증**

- **required gate 20개가 커밋된 후보에서 되돌리기 0회로 단일 지문 `dd34a76b…` 에서 20/20 PASS**(python-tests 6189 passed / 13 skipped · docker 227.3s · clean-machine 42.5s · dashboard-build 24.0s · api-e2e 18.4s)이고 **실행 후 지문이 불변**임을 재측정했다.
- 증인 `cr14_f12_build_drift_witness.py` exit 0 — A) 핀 유효·해석 순서, B) 출하 번들이 핀 값을 보유, C) 재빌드 digest 불변(수정 전에는 22개 교체).
- 회귀 9건(`tests/test_cr14_bundle_provenance.py` 6 · `dashboard/src/utils/buildStamp.provenance.test.ts` 3). 핀 값을 `deadbeef` 로 바꾸면 pytest 2건 실패(이빨 확인).
- `data/` 드리프트 0. release 문서 해시 불변(의존성 변경 없음).

**F-13(신규, advisory)** — `git status` 의 유일한 줄은 ` M vault_data` 이고 그 안은 ` M hooks/events.jsonl`(+3537줄 훅 이벤트)이다. gitlink SHA 는 불변(`464708c…`)이라 커밋에는 영향이 없지만 `ga_gate.py` 의 `dirty = bool(git status --porcelain)` 때문에 보고서에 `git.dirty: true` 가 남아 **'clean 후보' 판정을 흐린다**. 선택지(untrack / vault 안에서 로그 ignore / dirty 판정 정교화)를 D-50 에 남겼다.

**이 attempt 가 닫지 못한 것** — C14-01 은 **부분 충족**이다('worktree 완전 clean' 을 기준으로 삼을지는 출시 책임자 결정 — R-1). 핀 == 실제 소스 리비전은 자동 검증되지 않는다(R-2). C14-03/04/05 와 C14-08 은 여전히 미실행이며, 이제 남은 차단 사유는 **전부 사람의 영역**이다.

---

## attempt-008 갱신 (2026-09-13) — F-10·F-11: **측정 도구**를 살리고 그 도구가 검증하던 경로를 끝까지 확인

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-10 과 F-11 을 닫고 F-09 의 `qs` 편차를 실행 검증**했으며,
그 과정에서 **지문이 이동**했다(`c36327ef…` → **`6641446ef41e0562…`**). attempt-007 의 20-gate 증거는
**그 시점 실측**으로 보존한다.

**F-10 — 오류 메시지를 그대로 믿으면 진단이 뒤집힌다**

- `pnpm run stryker:quick` 이 `Cannot find TestRunner plugin "vitest"` 로 죽는다. 이 메시지는 "러너를
  설치하라" 로 읽히지만, 실측은 **탐색 경로** 문제다 — Stryker 의 자동 플러그인 탐색은 **자기 자신의
  설치 디렉터리**를 스캔하고(`--logLevel debug` 의 `Loading @stryker-mutator/* from …` 가 증거), pnpm 의
  격리 레이아웃에서 그 안에는 core 의 의존(api·instrumenter·util)만 있으며 devDependency 인 러너는
  루트에만 있다.
- 수정은 `stryker.config.mjs` 의 **한 줄**이다(`plugins: ['@stryker-mutator/vitest-runner']`). 설치된 조합
  (9.6.1 ↔ vitest 4.x)은 이미 peer 계약(`vitest: >=2.0.0`)을 만족하고 dry-run 843 테스트가 실제로 돌므로,
  **버전을 올리는 것은 결함을 고치지 않으면서 도구 체인 전체를 움직여 두 lock 갈라짐(F-06/F-09) 위험을
  만든다**(D-40).

**F-09 의 '미검증' 이 닫혔다 — 근거가 추론에서 재현으로 올라갔다**

- 그 도구가 `qs` override 의 **유일한 소비자 경로**였다(attempt-007 R-1 이 남긴 반증 조건). 소스로 지목한
  경로는 `@stryker-mutator/core → typed-rest-client RestClient → Util.getUrl → qs.stringify` 이고, 여기서
  `encodeValuesOnly` 가 **기본값**이라 advisory(GHSA-q8mj-m7cp-5q26) 발동 조건과 일치한다.
- 실측: `qs 6.15.1`(벤더가 정확히 고정한 값)에서 `Util.getUrl`·`RestClient.get` **두 축 모두 크래시**
  (`TypeError: Cannot read properties of null (reading 'length')`, exit 1) → `6.16.0` 에서 두 축 OK(exit 0).
  즉 **advisory 가 우리 경로에서 실재**했고, 이 override 를 revert 하는 것이 **더 위험한 선택**이 됐다(D-41).

**F-11 — 도구가 돌아가자 '선언한 범위를 덮지 않는다' 가 보였다**

- `--mutate A --mutate B` 는 **마지막 하나만** 적용한다. 스크립트는 2개 파일을 선언했는데 보고서에는
  `outputStore.ts` 만 들어갔고(82.35%) **exit 0** 이었다. 통제 실험(단일 플래그로 `terminalStore.ts` 만 →
  정상 96.92%)으로 원인을 **파일 선택이 아니라 반복 플래그**로 분리하고 **쉼표 단일 플래그**로 고쳤다 —
  수정 후 보고서에 두 파일 모두(All files **91.92%** = 91 kill / 8 survive, exit 0).
- 이는 **F-07 과 같은 병**이다: exit 0 이 검증한 대상과 확인하려는 대상이 다르다. 그래서 알면서 남기지
  않았고, 그 대가로 그때까지의 20-gate 증거(지문 `faa55e0d…`)를 버리고 **최종 지문에서 20/20 을 다시
  완주**했다(D-42).
- quick 범위 생존 변이 **8건**(outputStore 6 · terminalStore 2)은 임계값(`high 80`·`break 55`)을 통과하므로
  **GA 차단이 아니다**(D-43). 도구가 이제 이 신호를 **측정 가능**하게 만들었다는 사실이 진전이다.

**검증**

- 증인 `cr14_f09_qs_consumer_probe.cjs`: `6.15.1` 에서 A·B 두 축 모두 CRASH(exit 1) → `6.16.0` 에서 A·B OK(exit 0).
- `pnpm exec stryker run --dryRunOnly` → exit 0(`Instrumented 9 source file(s) with 2344 mutant(s)`, `Ran 843 tests`).
- 회귀 **9건**(`tests/test_cr14_stryker_toolchain_contract.py`) — `plugins` 한 줄 제거 시 1건 실패, 스크립트를
  반복 플래그로 되돌리면 2건 실패(이빨 확인).
- 전체 suite **6183 passed / 13 skipped**(457.9초)에서 `data/` 드리프트 0 · 정적 검사 4종 exit 0.
- **required gate 20개가 되돌리기 없이 단일 지문 `6641446ef41e0562…` 에서 20/20 PASS**(python-tests 459.9s ·
  docker 46.0s · clean-machine 41.8s · dashboard-build 25.3s · api-e2e 18.3s)이고 **실행 후 지문이 불변**임을
  재측정했다. 의존성은 바뀌지 않았고 release 문서 해시도 불변이다(`666a2ea3…` / `14c24238…`).
- 증거: `.omo/evidence/commercial-reliability/CR-14/attempt-008/`(한계는 `review.md` R-1~R-5).

**정직한 한계(이 attempt 가 닫지 못한 것)**

- ① `qs` 검증은 **우리가 소스로 지목한 소비자 경로**에 대한 것이고 `stryker init` 을 실행한 것은 아니다
  (R-1) ② **91.92% 는 quick 범위(2 파일)의 점수**이고 전체 `stryker`(10 파일)는 비용 때문에 돌리지 않았다
  (R-3) ③ `reports/mutation/mutation.json` 은 JsonReporter 미설정으로 **7월 21일 파일이 남아 있다**(그 안의
  break 는 50) — 현재 결과로 인용하면 틀린다(D-44) ④ **F-07 은 여전히 열려 있다** — 이번 attempt 도 커밋을
  하지 않았으므로 `clean-machine-runtime` 의 초록은 후보가 아닌 HEAD 를 가리킨다.

**출하 문서 수치 정정(D-45)** — `dashboard.cdx.json` 은 **241 항목 / 207 고유 패키지**다(attempt-007 이
"구성요소 207" 로 적은 것은 고유 이름 수였다). 해시는 불변이라 결함은 문서 표현에만 있다.

---

## attempt-007 갱신 (2026-09-13) — F-09: dev 도구 체인 취약과 **출하 경계**

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-09 하나만** 닫았고, 그 과정에서 **지문이 이동**했다
(`3a9a7d66…` → **`c36327ef…`**). attempt-006 의 20-gate 증거는 **그 시점 실측**으로 보존한다.

**F-09 — 게이트 초록과 공존하던 dev 취약, 그리고 세 번째 '두 진실원 갈라짐'**

- `dependency-audit-dashboard` 는 `pnpm audit --prod --audit-level high` 다. 그래서 dev 도구 체인의
  취약점은 **초록과 공존**한다. 실측(수정 전): high 1건
  (`eslint → @eslint/eslintrc → js-yaml`, `<4.3.2`) · moderate 3건
  (`@stryker-mutator/core → typed-rest-client → qs`, `<6.16.0`).
- **절반은 F-03·F-06 과 같은 병이었다** — `js-yaml` 이 **pnpm 4.3.1(취약) / npm 4.3.2(패치)** 로
  갈라져 있었다. 설치 진실원과 고지 진실원이 같은 패키지에 다른 답을 하는 상황이 **세 번째**다.
- **출하 경계를 측정으로 남겼다** — 두 패키지 모두 출하 SBOM(`dashboard.cdx.json`, 241 항목 / 207 고유
  패키지 — 수치는 attempt-008 에서 정정, D-45)과 `THIRD_PARTY_NOTICES.txt` 에 **없다**. "dev 니까 출하물에 영향 없다"를 주장이 아니라 검사(회귀
  C14-F09-6)로 바꿔, override 결정의 안전 근거로 삼았다.
- **수정** — 두 override 를 **양쪽 설정**(`pnpm-workspace.yaml` + `package.json`)에 선언하고 두 lock 을
  재생성했다. `js-yaml: 4.3.2` 는 상류(`@eslint/eslintrc`)가 `^4.3.0` 을 선언하므로 **편차가 아니라
  최소 패치**다. `qs: 6.16.0` 은 **의도된 편차**다 — `typed-rest-client@2.3.1` 이 `qs: 6.15.1` 로
  **정확히 고정**했고 수정판은 `typed-rest-client` 3.x(`^6.16.0`)에만 있는데 stryker(core 9·10)는
  `~2.3.0` 만 허용한다 — **선언 범위 안에 수정판이 없다.**
- 검증: **전체 트리 audit 0/0/0/0/0**(advisories 0 — 수정 전 1 high + 3 moderate),
  `pnpm run lint` **0 errors**(js-yaml 4.3.2 정상 로드) · vitest **846 passed** · build exit 0 ·
  출하 문서는 dev override 로 **바뀌지 않는다**(241 항목 / 207 고유 패키지에 dev 패키지 부재). 증인은 하한·두 lock
  일치·출하 closure 부재를 분리 측정해 수정 전 exit 1(위반 4건) → 수정 후 exit 0.
  전체 suite **6174 passed / 13 skipped** 에서 `data/` 드리프트 0, **required gate 20/20 을 되돌리기
  없이 단일 지문 `c36327ef…` 에서 완주**(docker 240.9s · clean-machine 41.9s). 회귀 7건.
- **닫는 중에 나온 새 결함 — F-10**: `pnpm run stryker:quick` 이
  `Cannot find TestRunner plugin "vitest"` 로 exit 1. 내 override 탓인지 의심할 수밖에 없는 위치라
  **통제 실험**을 했다 — F-09 override 를 제거하고(qs 6.15.1) 같은 명령을 실행해도 **동일하게 실패**했다.
  즉 **기존 결함**이다(stryker 9.6.1 ↔ vitest 4.1.11; 플러그인은 설치돼 있고 직접 import 도 성공).
  required gate 는 아니지만 두 가지를 막는다: ① 변이 점수(테스트 품질) 측정 수단 부재,
  ② **`qs` 편차의 유일한 소비자 경로가 실행되지 않아 그 편차가 end-to-end 로 검증되지 않았다.**
  이 미검증을 결정 대장(D-36)과 자기 검토(R-1)에 남겼다.
- **정직한 한계**: pnpm 은 override 를 지워도 해석을 즉시 되돌리지 않으므로(lock 보존) **선언 자체를
  검사하는 회귀**가 해석 검사와 짝으로 필요하다. `qs` 편차는 "수용 vs 감사 예외 등록"의 갈림길이라
  출시 책임자 결정으로 남긴다.
- 증거: `.omo/evidence/commercial-reliability/CR-14/attempt-007/`
  (`reproduction.md`·`decision.md`(D-34~D-40)·`review.md`·`handoff.md`·`gate-report.json`·
  `logs/f09-witness-{before,after}.txt`·`logs/dev-audit-{before,after}.txt`·
  `logs/stryker-preexisting-failure.txt`·`repro/cr14_f09_dev_audit_witness.py`).

---

## attempt-006 갱신 (2026-09-13) — F-06: mermaid 경유 `uuid` 하한과 **출하 바이트**

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-06 하나만** 닫았고, 그 과정에서 **지문이 이동**했다
(`1981bfb5…` → **`3a9a7d66…`**). attempt-005 의 20-gate 증거는 **그 시점 실측**으로 보존한다.

**F-06 — "게이트 초록"과 "위험 0"이 갈라져 있었고, 실제 결함은 악용 경로가 아니라 하한이었다**

- 등록 서술은 "mermaid 경유 `uuid@9.0.1` moderate(GHSA-w5hq-g745-h8pq, `<11.1.1`)인데 감사
  임계값이 `high` 라 차단되지 않는다"였다. 실측하니 두 축으로 나뉘었고, 그것을 분리해 기록한다.
- ① **의존 하한 위반** — pnpm(설치·빌드 진실원)과 npm(SBOM·고지 진실원) **두 lock 모두**
  `uuid@9.0.1` 로 해석했다(위반 3건: pnpm 패키지 항목·pnpm 의존 항목·npm packages 항목).
- ② **취약 서명 미도달** — mermaid 의 erDiagram 청크는 `import { v5 } from "uuid"` 후
  `v5(str, MERMAID_ERDIAGRAM_UUID)` 로 **인자 2개**만 넘긴다. 취약 서명은 `buf` 인자를 넘길 때므로
  **악용 경로는 없었다.** 그래서 이 결함은 "취약한 의존을 쓰는 렌더러"가 아니라 **하한 문제**였다 —
  그러나 잠금 하한은 미래의 호출 경로에도 그대로 적용되고, 상류 `mermaid@10.9.8` 은 이미
  `uuid: ^9.0.0 || ^10 || ^11.1.0 || ^12 || ^13 || ^14.0.0` 로 **패치 버전을 허용**하고 있었다.
- **수정**: `dashboard/pnpm-workspace.yaml` 과 `dashboard/package.json`(npm `overrides`) **양쪽에**
  `uuid: 11.1.1`. 한쪽만 선언하면 npm 은 mermaid 범위의 **최고 가지(14.x)** 를 골라 **설치된 코드와
  고지된 코드가 갈라진다** — F-03 과 같은 병이다(같은 질문에 답하는 산출물이 둘인데 하나만 검사됨).
  11.1.1 은 취약 범위를 벗어나는 **최소 패치**이고 `exports` 가 ESM·CJS 를 모두 제공하는 것을
  확인했다(12+ 는 이번에 검증한 범위가 아니다). 두 lock 재생성 + **출하 번들 재빌드**(추적 산출물 —
  uuid 를 담은 청크가 `…Ca1Z6rrW.js` → `…DK8mMXpA.js` 로 교체) + release 문서 재생성.
- **증인이 세 축을 분리해 측정한다**: A) 잠금 하한(판정 기준), B) 취약 서명 도달성(참고),
  **C) 출하 바이트**(커밋되는 `dashboard_dist` 에서 uuid v35 구현을 담은 청크는 패치 마커
  `out of buffer bounds` 도 담아야 한다 — 판정 기준). C 축이 없으면 **잠금만 올리고 재빌드하지 않은
  상태를 놓친다**(그때 출하물에는 옛 코드가 남는다). 마커는 두 사본(uuid@9.0.1·11.1.1)에서 유무를
  직접 확인해 판별자 자체를 검증한 뒤 쓴다.
- 검증: 증인 `cr14_f06_uuid_reachability.py` 수정 전 exit 1(하한 위반 3건) → 수정 후 exit 0.
  `pnpm audit --prod` **취약 0건**(moderate 포함 0 — 수정 전에도 게이트 명령은 exit 0 이었다),
  CR-09 실브라우저 **4/4 PASS + 전 시나리오 `blockedExternal: []`**(mermaid 가 uuid 11.1.1 로 렌더),
  전체 suite **6167 passed / 13 skipped** 에서 `data/` 드리프트 0, **required gate 20/20 을 되돌리기
  없이 단일 지문 `3a9a7d66…` 에서 완주**(실행 후 지문 불변 재측정). 회귀 8건.
- **남은 위험을 새로 등록했다**: **F-09** — dev 도구 체인에 high 1건(`eslint → @eslint/eslintrc →
  js-yaml <4.3.2`)과 moderate 3건(`@stryker-mutator → typed-rest-client → qs`). 게이트가 `--prod`
  이므로 **차단되지 않는다.** F-06 이 보여준 교훈("감사 통과 ≠ 위험 0")이 한 번 더 실증된 셈이다 —
  임계값 확대/의존 상향/잔여 위험 등록 중 무엇을 고를지는 출시 책임자 결정으로 남긴다.
- **정직한 한계**(상세는 `attempt-006/review.md` R-1~R-8): B 절은 `uuid` 리터럴이 있는 파일만
  스캔하므로 minify 번들(동봉된 `mermaid.min.js` 는 패치 이전 uuid 를 인라인한다)은 놓친다 —
  우리는 그 파일을 import 하지 않으며(`exports['.'].import = ./dist/mermaid.core.mjs`), 그 사실은
  C 절이 잡는다. 12+ 의 `exports` 는 직접 확인하지 않았다(D-29 에 명시).
- **skip 기록**: `python-tests` skip 이 6 → 13 이 됐는데, 증가분 7건은 전부
  `TestAgainstInstalled`(unsloth/trl)이고 두 패키지는 `uv.lock` 에 **0건**이다(pyproject §87-90:
  extra 가 아니라 주간 drift CI 담당). **후보의 성질이 아니라 환경의 성질**이다(D-32).
- 증거: `.omo/evidence/commercial-reliability/CR-14/attempt-006/`
  (`reproduction.md`·`decision.md`(D-27~D-33)·`review.md`·`handoff.md`·`gate-report.json`·
  `logs/f06-witness-{before,after}.txt`·`logs/vendor-prebuilt-bundle-note.txt`·
  `logs/dependency-audit-dashboard-after.txt`·`logs/dashboard-dist-refresh.txt`·
  `repro/cr14_f06_uuid_reachability.py`).

---

## attempt-005 갱신 (2026-09-13) — F-03: release 라이선스 판독이 **고지문과 SBOM 으로 갈라져 있었다**

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-03 하나만** 닫았고, 그 과정에서 **지문이 이동**했다
(`eca54773…` → **`1981bfb5…`**). attempt-004 의 20-gate 증거는 **그 시점 실측**으로 보존한다.

**F-03 — 같은 질문에 리졸버가 둘이었다(그리고 하나만 gate 가 읽는다)**

- 등록 서술은 "release 문서의 파이썬 라이선스가 `importlib.metadata` 로 **실행 환경**에서 읽혀 같은
  후보·같은 lock 인데도 값이 달라진다"였다. 실측하니 결함은 **두 갈래**로 나뉘었고, 무게추는 환경이
  아니라 **판독 실패** 쪽이었다.
- ① **판독 실패(환경과 무관하게 틀린다)** — `THIRD_PARTY_NOTICES.txt` 의 파이썬 절만
  `metadata.metadata(name)["License"]` 를 직접 읽었고, `python.cdx.json` 은 PEP 639
  `License-Expression` → `License` → `License ::` 분류기 → 별명표 순으로 읽었다. PEP 639 이후
  대부분의 배포물은 `License-Expression` 에 SPDX id 를 쓰고 `License` 를 **비워 두므로**, 같은
  실행의 두 산출물이 같은 패키지에 다른 답을 했다 — 실측 **42건 불일치**(파이썬 구성요소 61개),
  그중 **35건은 이 환경의 메타데이터를 직접 읽어 반증한 판독 실패**다(`fastapi`=MIT,
  `anyio`=MIT, `click`=BSD-3-Clause, `cryptography`=Apache-2.0, `networkx`=BSD-3-Clause …).
- 이 고지문은 **wheel/sdist 에 동봉되는 법적 문서**이고 `release_sbom verify` 가 저장소 사본과의
  **바이트 일치**를 요구한다 — 즉 41줄의 `license metadata unavailable` 은 저장소에만 있는 것이
  아니라 **출하물에 그대로 실려 나가는 고지**였다.
- ② **환경 의존(남는 부분)** — 현재 플랫폼에 설치되지 않는 마커 패키지(`colorama`·`pywin32`)만
  양쪽 모두 미상이었고, **그 집합이 어디에도 선언돼 있지 않았다**. 즉 문서가 무엇을 모르는지를
  저장소가 알지 못했다.
- 수정: 고지문이 SBOM 과 **같은 판독 체인**을 쓰도록 통일했다(SPDX id → 정규화 불가 시 원문
  `License` 필드를 **공백만 정규화**해 한 줄 유지 → 미상 표기 — **값을 합성하지 않는다**). 저장소
  사본을 재생성해 미상이 **41건 → 2건**이 됐고, `python.cdx.json` 은 **수정 전후 바이트 동일**,
  `dashboard.cdx.json` 도 재생성 전후 동일이었다(결함은 고지문 쪽이었다). 남은 2건은
  **추정 SPDX 를 `declared_licenses` 에 적어 덮지 않고**(검증되지 않은 라이선스 주장 금지),
  `미해결 ⊆ marker_platform_packages` 를 회귀 17건으로 고정했다. 그중 하나는 **재생성 계약**이라
  잠금 환경보다 부실한 곳에서 생성하면(= 커밋된 값이 미상으로 되돌아가면) 테스트가 실패한다.
- 검증: 증인 `cr14_f03_notices_sbom_divergence.py` 가 수정 전 exit 1(불일치 42 · 판독 실패 35 ·
  미해결 41) → 수정 후 exit 0(불일치 0 · 판독 실패 0 · 미해결 = 정책 선언). 전체 suite
  **6166 passed / 6 skipped** 에서 `data/` 드리프트 0, **required gate 20/20 실행·20/20 PASS 를
  되돌리기 없이 단일 지문 `1981bfb5…` 에서 완주**. ruff/format/mypy/basedpyright 전부 exit 0.
- 구조적 교훈: **gate 는 SBOM 만 읽는다.** 그래서 고지문의 41줄이 틀린 동안에도 REL-03 license
  gate 는 초록이었다 — 같은 질문에 답하는 산출물이 둘인데 하나만 검사되면 검사되지 않는 쪽이 썩는다.
- 증거: `.omo/evidence/commercial-reliability/CR-14/attempt-005/`
  (`reproduction.md`·`decision.md`(D-23~D-26)·`review.md`·`handoff.md`·`gate-report.json`·
  `logs/f03-witness-{before,after}.txt`·`repro/cr14_f03_notices_sbom_divergence.py`).

---

## attempt-004 갱신 (2026-09-12) — F-08: 검증을 더럽히는 **두 번째 경로**

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-08 하나만** 닫았고, 그 과정에서 **지문이 이동**했다
(`eb10aed6…` → **`eca54773…`**, 2546 files). attempt-003 의 20-gate 증거는 **그 시점 실측**으로 보존한다.

**F-08 — 사용량 추적 기본 경로가 추적 파일을 다시 썼다**

- 원인: `api/dependencies.py` 가 ModelManager 를 만들 때
  `UsageTracker(db_path="data/token_usage.json")` 처럼 **CWD 상대·추적 파일 경로를 하드코딩**했다.
  `UsageTracker.record()` 는 `auto_save_interval`(**기본 50**)건마다 `_save()` 를 호출하므로,
  **사용량을 50건 이상 기록하는 테스트 조합 하나면 pytest 실행이 후보 트리를 더럽혔다.**
- 이는 **F-02 와 같은 구조의 두 번째 경로**다. F-02(attempt-003)는 `benchmark_harness` 의 기본 DB 경로
  하나만 리졸버 + conftest 격리로 고쳤고, **경로 결정이 여러 곳에 흩어져 있다**는 구조적 원인은
  남아 있었다. 게다가 F-08 은 임계값(50건) 아래에서만 돌던 **지금까지의 suite 때문에 조용히 잠복**해
  있었다 — "안전했다"가 아니라 **발현 조건이 아니었다.**
- 실측(수정 전): 프로덕션과 같은 방식으로 임계값만큼 기록 → `data/token_usage.json` digest
  `7ee5e106…` → `b9f8c356…`, `git status` **`M data/token_usage.json`**.
- 수정: `usage_tracker` 에 **단일 패치 지점** `default_usage_db_path()`(+순수
  `resolve_usage_db_path(environ)`, `AGK_USAGE_DB` override)를 신설하고 — **프로덕션 기본값은
  그대로**(누적 사용량 DB 계약) — `dependencies.py` 가 리터럴 대신 리졸버를 호출한다.
  `tests/conftest.py` 세션 autouse 픽스처 `_isolate_default_usage_db` 가 테스트에서만 저장소 밖으로
  돌리고(`_isolate_default_benchmark_db` **바로 옆** — 다음 사람에게 패턴이 보이게), 회귀 13건이
  C14-F08-1~6 을 고정한다.
- 회귀 13건 중 하나는 `dependencies.get_model_manager` 의 **소스**를 검사한다(리터럴 부재 +
  `default_usage_db_path()` 호출). 동작 테스트만으로는 **리터럴이 돌아와도** 통과하기 때문이다 —
  리터럴이 돌아오면 conftest 의 패치가 **효과가 없어지는데** 그 사실이 드러나지 않는다.
- 증인 `cr14_f08_usage_db_witness.py` 는 세 구간을 **구분해** 측정한다: A(결함 원형 재현 — 리터럴
  경로가 추적 파일을 쓴다) · B(수정 후 — 패치된 리졸버 경로에 저장되고 저장소 파일은 불변) ·
  C(`AGK_USAGE_DB` override + 미설정 시 프로덕션 기본값 유지). A 만 보면 수정 후에도 실패처럼
  보이므로 종료 코드는 **B/C 가 모두 성립할 때만 0** 이다.
- 검증: 전체 suite **6149 passed / 6 skipped** 에서 `data/` **드리프트 0**(suite 전후 지문 동일),
  **required gate 20/20 실행·20/20 PASS 를 되돌리기(`git checkout`) 없이 단일 지문 `eca54773…`
  에서 완주**(3단계 모두 `--merge-into` 성공). ruff/format/mypy/basedpyright 전부 exit 0.
- 부수 확인: `data/` 에서 지문을 흔드는 파일은 **`token_usage.json`(추적) 뿐**이다 —
  `data/projects.json`·`data/benchmarks/*` 는 gitignore 라 써도 지문이 안 움직인다.
- 스스로 밟은 함정: 증인의 첫 작성이 `from ... import default_usage_db_path` 로 이름을 **직접
  바인딩**해 패치가 보이지 않았고, 그 상태로 B 구간이 저장소 파일을 썼다. F-02 회귀가 이미
  문서화한 함정이며, 이번에 **계약 두 개(소스 검사 + 동작 검사)를 짝으로 두는 이유**가 실측으로
  확인됐다.
- 증거: `.omo/evidence/commercial-reliability/CR-14/attempt-004/`
  (`reproduction.md`·`decision.md`(D-19~D-22)·`review.md`·`handoff.md`·`gate-report.json`·
  `logs/f08-witness-{before,after}.*`·`repro/cr14_f08_usage_db_witness.py`).

**남은 것(attempt-004 시점 기록)**: F-03(라이선스 환경 의존 — **attempt-005 에서 닫힘**) ·
F-06(uuid moderate — **attempt-006 에서 닫힘**) · F-07(`clean-machine-runtime` 이 커밋된 HEAD 를 검증 —
커밋 뒤 재실행 필요) · **커밋(clean full SHA)** · 외부 승인.
(attempt-007 시점의 남은 것은 **F-07 · F-10(도구 체인) · 커밋 · 외부 승인**이었다 — **F-10 은
attempt-008 에서 닫혔고, 이제 남은 기술 축은 F-07 하나다.**)

---

## 0-A. attempt-003 갱신 (2026-09-12) — 검증이 트리를 바꾸는 뿌리 하나를 제거

**판정은 NO-GO 로 유지한다.** 이번 attempt 는 **F-02 하나만** 닫았다.

**F-02 — 검증 실행이 저장소 추적 파일을 다시 썼다**

- 원인: API 런타임이 `AgentRuntime(task_outcome_recorder=benchmark_harness.record_task_outcome)` 로
  **모든 작업 완료를 기록**하는데, `BenchmarkHarness` 의 기본 DB 경로가 CWD 상대
  `data/benchmark_results.json`(**추적 파일**) 한 곳으로 고정되어 있었다. \"작업을 실행하는 테스트\"
  가 하나라도 있으면 `pytest` 전체 실행이 후보 트리를 더럽혔다.
- 실측: 전체 suite 실행 후 `M data/benchmark_results.json`, **+423줄**, `total_task_results` **656→684**.
  게이트 코드 지문이 실행마다 이동해 단계별 `--merge-into` 가 거부됐다(attempt-001
  `different working tree (81939d1a… != 71a65f32…)`). CR-13 R03 드리프트의 뿌리다.
- 수정: 기본 경로를 **단일 패치 지점**(`default_benchmark_db_path()` + 순수
  `resolve_benchmark_db_path(environ)` + `AGK_BENCHMARK_DB` override)으로 분리하고,
  `tests/conftest.py` autouse 픽스처가 테스트에서만 저장소 밖으로 돌린다(CR-02 D-07 선례).
  **프로덕션 기본값은 그대로다** — 추적 파일은 누적 결과 DB 라는 제품 계약이 있고, 결함의
  원인은 '경로가 저장소 안'이 아니라 **'테스트가 그 경로를 쓴다'** 이다.
- 회귀: 전체 suite **6136 passed / 6 skipped** 에서 `data/` **드리프트 0**(digest 불변 +
  `git status` clean). **20 required gate 가 `git checkout` 되돌리기 없이 단일 지문
  `eb10aed6…` 에서 20/20 PASS** 했고, 실행 **후에도** 지문이 동일하다.
- 새 함정 고정: conftest 는 **모듈 속성**을 패치하므로 테스트가 `from ... import
  default_benchmark_db_path` 로 이름을 직접 바인딩하면 패치를 못 본다(이 attempt 의 첫 회귀
  작성에서 2건이 거짓 실패). 회귀와 파일 상단 주석이 그 함정을 기록한다.

**남은 뿌리**: **F-01**(`src/antigravity_k/dashboard_dist/` 추적) — `clean-machine` gate 가
`git archive HEAD` 를 쓰므로 추적 번들이 낡으면 그 gate 가 낡은 UI 를 포장한다. 검증이 트리를
바꾸는 두 뿌리 중 **하나만** 제거됐다. → **§0-B 에서 이 서술을 실측으로 정정한다.**

---

## 0-B. attempt-003 추가 실측 (2026-09-12) — F-01 의 성질 정정 + F-07 신규 등록

**판정은 NO-GO 로 유지한다.** F-02 를 닫은 뒤 남은 뿌리 F-01 을 실측했더니 **기존 서술이 틀렸다.**

**F-01 정정 — `dashboard-build` 는 비결정적이지 않다**

- 종전 서술: "자산 파일명이 내용 해시라 항상 stale" → 실측: **아니다.**
- 현재 후보 위에서 `pnpm run build` 를 다시 돌려 `src/antigravity_k/dashboard_dist/` 103개 파일을
  전후 비교했다 — **added 0 / removed 0 / changed 0, 바이트 단위 동일**(`logs/f01-build-idempotency.txt`).
  코드 지문도 `eb10aed6…` 로 **불변**이다.
- 게다가 attempt-003 의 **20-gate 전체 실행 후에도** 지문이 같다 — 이 후보 상태에서 **어떤 required
  gate 도 트리를 바꾸지 않는다.** attempt-002 까지 필요했던 `git checkout` 되돌리기가 사라진 것은
  F-02 폐쇄의 직접 효과이고, 그 위에 빌드·SBOM 도 멱등임이 확인됐다.
- 그러면 트리가 dirty 한 이유는? **HEAD(`08b8bb2e…`) 의 추적 번들이 현재 소스보다 낡았기 때문**이다
  (39 삭제 / 93 신규 / 1 수정). 즉 F-01 은 "검증이 트리를 흔든다"가 아니라 **"후보가 아직 커밋되지
  않았고, 커밋된 산출물이 낡았다"** 이다. 갱신된 산출물을 후보와 함께 커밋하면 트리는 clean 이 되고
  이후 빌드는 no-op 이다.
- 남는 것은 **정책 선택**이다(빌드 산출물을 계속 추적할지, 패키징 시점 생성 + 해시 검증으로 전환할지).
  이는 GA blocker 가 아니라 post-GA 엔지니어링 결정이다.

**F-07 신규 — `clean-machine-runtime` 의 PASS 는 후보가 아니라 HEAD 를 검증한다**

- `scripts/verify_clean_machine.sh` 는 `REF="HEAD"` 로 `git archive` 한다(2877 파일). `gate-report.json`
  은 `git.sha: 08b8bb2e…` · `git.dirty: true` 를 기록한다. 즉 이 게이트의 PASS 는 **후보 작업 트리가
  아니라 커밋된 HEAD** 에 대한 판정이다.
- 그래서 지금 HEAD 번들이 낡은 UI(mermaid `10.6.1`)를 담고 있는데도 이 게이트는 **초록**이다.
  CR-10/CR-11 의 "stale bundle" blocker 가 여기서 설명된다 — **초록이 검증한 대상과 우리가 승인하려는
  대상이 다르다.**
- 이것은 코드 결함이 아니라 **검증 범위(sequencing) 문제**다 — 커밋 뒤 그 SHA 에서 다시 돌리면 정확해진다.
  다만 그 전까지 이 게이트의 PASS 를 후보의 근거로 인용하면 안 된다. 후보 커밋 시 **이 게이트를 새
  HEAD 에서 재실행하는 것이 필수**다(§6-3).

**검증** — 신규 로그 `logs/f01-build-idempotency.txt` · `logs/f01-dashboard-build-rerun.log`.
**코드 변경은 없다**(지문 `eb10aed6…` 유지) — attempt-003 의 20-gate 증거가 그대로 유효하다.

---

## 0. attempt-002 갱신 (2026-09-12) — 차단 사유의 성격이 바뀌었다

**판정은 NO-GO로 유지한다. 달라진 것은 "왜 NO-GO인가"다.**

| 규칙 | attempt-001 | attempt-002 |
|---|---|---|
| P1 미해결 | 해당(mermaid high) | **해소** — `mermaid 10.9.8` 승격 |
| required gate 실패 | 해당(1건) | **해소** |
| required gate 미실행 | 해당(4건) | **해소** — 20/20 실행 |
| 필수 외부 승인 부재 | 해당 | **해당(유지)** |
| source mismatch | 해당 | **해당(유지)** — 여전히 미커밋 (F-02 는 닫혔으나 F-01 로 clean tree 는 여전히 불가) — **※ 이 행은 attempt-002 시점 기록이다. attempt-003 에서 F-01 은 실측으로 기각됐다(§0-B).** |

**attempt-002에서 닫은 결함**

- **F-04(P1)** — `mermaid` `10.6.1 → 10.9.8`(lock 3종 동기화)로 `dependency-audit-dashboard`가
  **PASS**(high 0). 그리고 **승격이 새 보안 회귀를 드러냈다**: mermaid 10.9.8은 라벨의 raw
  `<img>`를 DOM에 **남긴다**. 핸들러는 사라져도 요소가 남으므로 **절대 URL이면 외부 요청이
  실제로 나간다**(실브라우저 캡처 `https://beacon.invalid/leak.png`). 컴파일된 계약 `C09-03`이
  승격 직후 실패하며 드러났다. **출력 정화만으로는 늦다** — mermaid가 렌더 중 측정용 임시 DOM에
  라벨 HTML을 넣어 우리 정화가 돌기 전에 요청이 나간다. `dashboard/src/utils/mermaidRuntime.ts`에서
  **입력 중화(deny-list) + 출력 구조 정화** 두 단계로 막았고, `C09-03`이 이제
  `blockedExternal: []`로 상시 감시한다. `DOMPurify` 프로파일은 `foreignObject` 라벨까지 지워
  다이어그램이 빈다(실측) — 화이트리스트가 아니라 **측정된 통로**를 없앤다.
- **F-05(신규, required gate가 처음 돌며 드러남)** — `docker-build`가 14.5초에 heap OOM
  (**3/3 재현**). 원인은 콜드 `tsc -b`이고, `node:22.13-alpine`의 기본 V8 힙 상한이
  **2096MB로 고정**(`--memory=4g`/`12g` 모두 동일 → 호스트 메모리로 회피 불가)이라 2044MB
  지점에서 회수가 안 된다. 같은 입력이 로컬에서는 기본 힙으로도 통과하므로 musl/node 조합이
  더 많은 여유를 필요로 한다. dashboard-builder 스테이지에 빌드 한정
  `ENV NODE_OPTIONS=--max-old-space-size=4096`를 추가해 **PASS(246.8s)**.
  이미지 빌드에서 `tsc -b`를 빼지 않은 이유는, 빼면 "게이트를 통과한 커밋"과 "이미지에 든 코드"의
  검증 수준이 갈라지기 때문이다.

**새로 남긴 결함**

- **F-06** — mermaid 경유 `uuid@9.0.1` moderate(`<11.1.1`, `buf` 인자 경로). 감사 gate의 임계값이
  `--audit-level high`라 **차단되지 않는다**. 상류가 uuid를 올려야 하며, 우리가 override로 11.x를
  강제하면 mermaid 10.x의 사용 경로가 검증되지 않으므로 하지 않았다. **"게이트 초록"과
  "위험 0"은 다르다.**

**검증** — `python-tests` **6124 passed / 6 skipped**(428초) · 대시보드 Vitest **80 files/846 passed**
· 실브라우저 CR-09 4/4(`blockedExternal: []`) · `accessibility-e2e` 35 · `docker-build` PASS ·
`clean-machine-runtime` PASS · ruff/format/mypy/basedpyright 0 errors. **required gate 20/20 실행·
20/20 PASS 를 단일 코드 지문 `ebbbd7f0…` 위에서 완주**했다 — `python-tests`가 재작성한
`data/benchmark_results.json`(F-02)을 되돌려 지문을 유지했고, `dashboard-build`·`sbom-generate`는
자산명이 내용 해시라 멱등이라 지문이 깨지지 않았다(실측).
상세: `.omo/evidence/commercial-reliability/CR-14/attempt-002/`.

---

## 1. 판정 근거 — attempt-001 시점 (기록)

계획서 §CR-14 판정 규칙: 하나라도 해당하면 NO-GO.

| # | 규칙 | attempt-001 실측 | attempt-002 현재 |
|---|---|---|---|
| 1 | P1 미해결 | **해당** — `dependency-audit-dashboard` FAIL. `mermaid@10.6.1` ∈ 취약 범위 `<=10.9.2`, GHSA-m4gq-x24j-jpmf (high, patched `>=10.9.3`) | 해소(F-04 폐쇄) |
| 2 | required gate 실패 | **해당** — 위 1건 | 해소 |
| 3 | required gate 미실행 | **해당** — `docker-build`, `master-e2e`, `accessibility-e2e`, `clean-machine-runtime` (4개) | 해소(20/20 실행) |
| 4 | 필수 외부 승인 부재 | **해당** — EX-01~EX-06 전부 미확보(CR-12 `BLOCKED_EXTERNAL` 유지) | **해당(유지)** |
| 5 | source mismatch | **해당** — clean 코드 후보 full SHA가 없고, 검증 실행이 추적 파일을 다시 써서 작업 트리를 고정할 수 없다 | **해당(유지)** — F-01/F-02 로 여전히 clean tree 를 만들 수 없다 |

> **과거 기록은 재라벨링하지 않는다.** 위 표의 attempt-001 열은 그 시점 실측 그대로고,
> attempt-002 는 **다른 코드 상태에서 다시 측정**한 값이다. 두 값이 다르게 보이는 것이 정상이다.

## 2. required gate 인벤토리 (20개, `scripts/commercial_ga_gates.json`)

`uv run scripts/ga_gate.py --manifest scripts/commercial_ga_gates.json --list` 로 확정했다
(전부 `required: true`). 숫자를 맞추려고 검사를 빼지 않았다 — 인벤토리가 manifest와 같은지를
`tests/test_cr14_candidate_evidence.py::TestCandidateGateInventory` 가 강제한다.

| gate | 상태 | 결과 |
|---|---|---|
| python-ruff, python-format, python-mypy, python-basedpyright, security-bandit, package-build, dashboard-install, dashboard-lint, dashboard-typecheck, dashboard-test | PASS | 10/10, 37초 (`gate-report-part1.json`) |
| python-tests | PASS | **6123 passed / 7 skipped** (447초) |
| sbom-generate, dashboard-build, dependency-audit-python, api-e2e | PASS | `gate-report-part2.json` |
| **dependency-audit-dashboard** | **FAIL** | `pnpm audit --prod --audit-level high` exit 1 — 9건(1 low / 7 moderate / **1 high**) |
| docker-build | NOT_RUN | — |
| master-e2e | NOT_RUN | — |
| accessibility-e2e | NOT_RUN | `dashboard-build` 는 통과했으나 e2e 미실행 |
| clean-machine-runtime | NOT_RUN | timeout 7200초, 실행 창 부족 |

**attempt-001: 15 / 20 실측, 14 PASS / 1 FAIL / 4 NOT_RUN.**
**attempt-002: 20 / 20 실행, 20 / 20 PASS** — 단일 코드 지문 `ebbbd7f06fab3fb2d10008336ef96ba0d7949ee72007774c6372fc07f1bba0b5` 위에서
완주(`attempt-002/gate-report.json`). 위 표의 NOT_RUN·FAIL 은 attempt-001 시점 기록이며,
attempt-002 에서 `dependency-audit-dashboard` 는 PASS, `docker-build`·`master-e2e`·
`accessibility-e2e`·`clean-machine-runtime` 은 모두 실행·PASS 다.

검증 환경: macOS (arm64), Python 3.13 (`uv run --isolated --frozen`), Node 22.13 + pnpm 11.3.0.

## 3. 이번 작업에서 닫은 결함

### 3-1. CR-13이 남긴 승인 우회로 (C14-01) — 닫음

`required_gates`를 비우면 번들 검증기가 gate 검사를 **통째로 건너뛰고 PASS**를 냈다.
빈 gate 목록이 곧 승인이었다. 이제:

- `evidence_kind`(`release`|`reference`)가 필수다(기본값 없음).
- `release`는 `required_gates`가 비면 build·verify 양쪽에서 거부한다.
- `reference`는 `required_gates`가 비어 있어야 하고, CLI `verify`가 `PASS`(exit 0) 대신
  **`REFERENCE_ONLY`(exit 3)** 를 낸다. 참고 번들은 어떤 경로로도 승인이 되지 않는다.
- historical이 아닌 gate report artifact를 참고 번들에 실어 나르는 경로도 막았다.

CR-13 시연 번들과 CR-14 평가 번들 모두 `reference`로 재선언했다(verify exit 3).
회귀: `tests/test_cr14_candidate_evidence.py` 13건.

### 3-2. 검증이 추적 산출물을 다시 쓰던 결함 (C14-06) — 닫음

- REL-01 테스트가 `_REPO_ROOT`로 생성기를 호출해 추적 중인
  `src/antigravity_k/release/*`를 덮어썼다. 이제 임시 프로젝트에서만 생성하고,
  저장소 사본과의 일치는 새 검사 2건이 판정한다.
  이 분리로 **저장소 사본이 CR-09 이후 낡아 있었다**는 사실(대시보드 절 수백 줄)이
  처음 드러났고, release workflow와 같은 명령으로 재생성했다.
- 회귀: `tests/test_rel01_clean_build_sbom.py` (테스트 전후 release 트리 해시 동일 = "TREE STABLE").

### 3-3. 단계별 gate 실행기 (C14-01) — 도입

20개 gate는 한 프로세스 창에 들어가지 않는다(`python-tests` 447초, `clean-machine-runtime`
timeout 7200초). `ga_gate.py --merge-into`가 **같은 후보 SHA + 같은 manifest + 같은 코드 지문**
일 때만 결과를 이어받고, 같은 gate id는 새 결과로 교체한다. 다른 후보·다른 코드 상태면 exit 2.
부수적으로 후보 지문에서 `docs/`·`.omo/`를 제외해, 결과 문서 작성이 gate 증거를 낡게 만들지
않는다(계획서 §CR-14 8의 "결과 문서는 코드 후보와 별도").

## 4. 남긴 결함 (다음 후보에서 처리)

> attempt-002 갱신: **F-04 는 닫혔다**(§0). 새로 **F-06**(mermaid 경유 `uuid@9.0.1` moderate,
> 감사 임계값 `high` 라 미차단)이 등록됐고, **F-01·F-02·F-03 은 그대로 열려 있다**.
> (기록 정정: 이후 F-02 는 attempt-003, F-08 은 attempt-004, **F-03 은 attempt-005** 에서 닫혔고
> F-01 은 attempt-003 실측으로 GA blocker 에서 내려갔다 — §0-A·§0-B·attempt-005 갱신절 참조.)
>
> **attempt-003 갱신(§0-B): F-02 는 닫혔고 F-01 은 실측으로 성질이 정정됐다** — 빌드는 바이트 단위
> 멱등이므로 dirty 의 원인은 "비결정성"이 아니라 **"HEAD 추적 번들이 낡은 것"** 이다. 새로
> **F-07**(`clean-machine-runtime` 이 후보가 아니라 커밋된 HEAD 를 검증)이 등록됐다.

| ID | 결함 | 성질 | 파급 |
|---|---|---|---|
| F-01 | `src/antigravity_k/dashboard_dist/` 가 **추적 중인 빌드 산출물**이다. **§0-B 정정: 빌드는 비결정적이지 않다**(재빌드 전후 103 파일 바이트 동일, 지문 불변). dirty 의 원인은 HEAD 추적 번들이 현재 소스보다 **낡은 것**이고, 갱신 산출물을 후보와 함께 커밋하면 해소된다 | 릴리스 공학 → **정책 선택** | **GA blocker 아님**(§0-B). 남은 것은 "빌드 산출물을 계속 추적할지" 정책 결정(post-GA). 단 커밋 전까지 `clean-machine` gate 는 낡은 UI 를 포장한다(F-07) |
| ~~F-02~~ | 상용 pytest suite가 `data/benchmark_results.json`을 다시 쓴다(= CR-13 R03 드리프트의 뿌리). 단독 실행으로는 재현되지 않고 전체 suite 조합에서만 발생 | 테스트 격리 | **CLOSED (attempt-003)** — 기본 경로를 단일 패치 지점으로 분리 + conftest autouse 격리 |
| ~~F-08~~ | `dependencies.py` 가 `UsageTracker(db_path="data/token_usage.json")` 로 **추적 파일 경로를 하드코딩**. `record()` 가 50건마다 자동 저장 → 임계값을 넘는 테스트 조합에서 F-02 와 같은 실패 모드(실측 `M data/token_usage.json`) | 테스트 격리 | **CLOSED (attempt-004)** — 리졸버(`default_usage_db_path`) + `AGK_USAGE_DB` + conftest autouse 격리, 회귀 13건(그중 1건은 호출부 소스에서 리터럴 부재를 검사) |
| ~~F-03~~ | release 문서의 파이썬 라이선스가 `importlib.metadata`로 **실행 환경**에서 읽힌다 — **attempt-005 실측으로 정정: 실질 원인은 환경이 아니라 고지문과 SBOM 이 각자 다른 함수로 판독한 것이다(42건 불일치, 35건은 판독 실패)** | 설계 계약 | **CLOSED (attempt-005)** — 판독 체인 통일 + 고지문 재생성 + 미해결 집합 고정. 남는 환경 의존은 선언된 마커 2건뿐 |
| ~~F-04~~ | `mermaid@10.6.1` high 취약점 — **CLOSED(attempt-002)** | P1 | 해소: `10.9.8` 승격 + 승격이 드러낸 라벨 주입 비컨까지 폐쇄 |
| ~~F-05~~ | `docker-build`가 콜드 `tsc -b` heap OOM으로 실패(attempt-002 신규 발견) — **CLOSED(attempt-002)** | **P1급** | 해소: dashboard-builder 한정 `NODE_OPTIONS=--max-old-space-size=4096`, PASS 246.8s |
| F-06 | mermaid 경유 `uuid@9.0.1` moderate(`<11.1.1`, `buf` 인자 경로) | 잔여 위험 | 감사 임계값 `high` 라 **차단되지 않는다** — 상류가 uuid를 올려야 함(attempt-002 신규) |
| ~~F-07~~ | `clean-machine-runtime` 이 `git archive HEAD` 로 **커밋된 HEAD** 를 검증한다(그 시점 2877 파일, `git.dirty: true`). 후보가 미커밋이면 **초록이 후보가 아닌 다른 코드를 가리킨다** — **attempt-009 에서 닫혔다**(후보 커밋 후 재실행, 3001 파일) | 검증 범위(sequencing) | 코드 결함 아님 — 후보 커밋 뒤 새 HEAD 에서 재실행하면 정확해진다. 그 전까지 이 PASS 를 후보 근거로 인용 금지(attempt-003 신규) |

### 선언 (측정 **전** — D-52) — attempt-040

이 attempt 의 후보와 그 지문은 **아래 §5 판정 카드가 선언한다**(값의 소유자는 하나다 — C14-F15-2).
**현재의 후보는 `b6003205365606407cadfd6cbb1c813110beef0f` · 지문 `02349a8d…`** 이며, 선언 커밋은 docs 전용이다.
manifest sha256 `a40867c743a9…`. **재선언은 없다** — 이 attempt 의 첫 선언이 그 후보의 측정이다.
게이트 수치(PASS/FAIL/NOT_RUN)는 측정 뒤 보고서 집계로만 채운다(지금은 inventory만 선언: **23 / 0 / 0 / 23**).

## 5. 판정 카드 (attempt-040 기준)

- code candidate full SHA: **`b6003205365606407cadfd6cbb1c813110beef0f`**(attempt-040 — **C33-6 PIN-mode ticket 브라우저 증인**: `cr14-pin-ws-ticket.spec.ts` · PIN hermetic · `/api/auth/ws-ticket` → `?ticket=` · 소켓 생존 · fail-first 4401 · `dashboard-e2e-witnesses` 자동 소유 · 지문 `02349a8d06945e438bdc60799ed770a87d6bb67d33d27f09b52008d242536ed6` · manifest `a40867c743a9…`. *(측정 완료 — required **23/23 PASS** · 지문 불변)* **판정 MOVED 없음**. 앞선 후보는 `bbb308f8172c802419cb49a69970c1691d3c80ad`**(attempt-039 — **F-47 leftover `f47-capture-real-local-models` 폐쇄**: AGK_SEED_LOCAL_HUB hermetic · HUB_SPEC_FILES ambient 소유 · leftover **1→0** · EX-01 주장 금지 · 후보 트리 == HEAD == 작업 트리 · 지문 `0b1a156f5c1d3275cc862e589707d871961796deb8bffa79131aea66b9917628` · manifest `a40867c743a9…`. **판정 MOVED 없음**. 앞선 후보는 `4c3f8364db4f3011891604748b672d36d23d03ee`(attempt-038 — **F-47 leftover `f47-invert-compact-large-stream` 폐쇄**: e2e bigEvents 를 TaskEventSchema/`event()` 시드로 정합 · GREP_INVERT 비움 · leftover **2→1**. 제품 UI/번들 불변 · 후보 트리 == HEAD == 작업 트리 · 지문 `35b00666371e6ce80e42a3d1ccefa242576627eab7da531c192ec87ce76e8af4` · manifest `a40867c743a9…`. **판정 MOVED 없음**. 앞선 후보는 `0cdcd60cc086e4ad73ef3d111a3f8f1b7af3c6b7`(attempt-037 — F-47 git-status leftover 폐쇄 · 지문 `341d4f6cc4a9436c935221299cec344357caa504b0914586cd34fa979db178f5`). 선행 attempt-034: **F-45 · F-46: ambient 백엔드 스펙에 required-gate 소유자를 줬다**(required 22 → **23**: `dashboard-e2e-ambient`). F-45: hermetic NO_PIN + `AGK_HOOK_VAULT_DIR` + Origin allowlist(`AGK_CORS_ORIGINS`) — PIN 잠금·공유 훅 vault·CORS 거부로 WS frames=0 이던 자리. F-46: 게이트가 **서버를 직접 띄운다**(격리 `AGK_PATH_*`·그룹 종료·`--skip-server` 이빨) · 소유 스펙 5파일 · F-47 은 의도적으로 밖. **제품 런타임**: `server.py` 훅 vault 오버라이드 소수 줄 + hermetic 헬퍼. **게이트 목록이 바뀌었으므로** 이 후보부터 `22/22` 가 **`23/23`** 이다. *(측정 결과는 실행 뒤 채운다 — D-52)* **판정 MOVED 없음**. 앞선 후보는 `c66706ee121604dc1de8ed0362b4b9c427765137`(attempt-033 — **F-43: 화면이 보내는 경로는 서버가 서는 경로여야 한다** · **F-44: 런타임 상태는 코드 스코프 밖에 있다**(*재선언 둘 — 측정 전*). **첫 후보 `b11ff74f`(지문 `03a7db8d…`)의 첫 fast 배치가 `dashboard-build` 의 `tree_moved`(추적 번들 **59 경로** · passed 18 / failed 1 / required_failed 1 / total 19)로 멈췄다** — 게이트가 exit 0 으로 끝나면서 번들을 다시 썼고 F-34 의 검사가 **옳게** 물었다. 번들을 후보의 소스에서 다시 빌드해(**두 번 빌드 바이트 동일**) 이 커밋에 넣었고, 코드가 옮겨졌으므로 **측정 전에** 다시 선언한다(D-52). **두 번째 후보 `ec76c7ce`(지문 `f8cab12b…`)는 배치를 완주하고도 마감 직전에 멈췄다** — 작업 트리에만 있는 경로 `src/data/projects.json` 하나가 코드 지문을 흔들었다(`e116d58d…` ≠ `f8cab12b…`): 제품의 상대경로 기본값(`project_registry.py` 의 `Path("data/projects.json")`)이 cwd 가 `src/` 인 프로세스의 상태를 저장소 안에 만들고, 게이트 지문은 무시되지 않은 미추적 파일도 스코프로 읽는다 — 루트의 같은 파일은 이미 무시돼 있었고 빠진 것은 그 cwd 루트뿐이었다(F-44). 고침은 그 루트의 무시 규칙과 그 규칙을 소유하는 계약 `tests/test_cr14_runtime_state_scope_contract.py` **5건**(제품 소스에서 경로 읽기 · cwd 루트별 무시 · **게이트 함수로** 스코프 측정 · 이빨)이며 **제품 런타임 0줄** — 상대경로 설계 자체의 근본 고침은 제품 동작을 바꾸므로 별도 attempt 에 남긴다. 코드가 옮겼으므로 **다시 선언한다**(세 번째). `apiRequest` 가 **래퍼 안에서** '/v1' 을 앞에 붙이는데 두 호출부(`askAgent`·`fetchWsTicket`)가 **이미 namespace 를 가진 경로**(`/api/agent/ask`·`/auth/ws-ticket`)를 넘겨서 실효 경로가 `/v1/api/agent/ask` · `/v1/auth/ws-ticket` 이 됐고, 서버에는 **`/v1/api/*` 도 `/v1/auth/*` 도 없으므로** 두 요청은 **도달할 수 없었다**(라우트 표 235 패밀리·58 namespace 중 둘 부재). 현재 트리에서 자유 포트로 띄운 서버에 대고 재면 정본 `POST /api/auth/ws-ticket` 은 **200 + ticket**, 실효 경로는 **405**(SPA fallback)다. **왜 조용했나**: 접두사가 호출부의 **리터럴에 없어서** `grep -r '/v1/auth' dashboard/src` 가 0건이고, **소스 리터럴만** 모으는 대조도 그 자리를 건너뛴다(증인의 A 축이 그 눈먼 자리를 그대로 재현한다 — 리터럴로는 보이지 않는 실효 경로가 3종). 그리고 `fetchWsTicket` 은 실패를 `catch { return null }` 로 삼키며, ticket 없는 WS 연결은 `open_loopback` 일 때만 통과하므로 — **PIN 이 설정된(protected) 배포에서는 이벤트 스트림이 4401 로 거절되고 3초마다 재시도**한다(로컬 dev 익명 모드가 그 실패를 가린다). 문서 두 곳도 서로 달랐다: `docs/13` 은 SEC-03 을 `POST /v1/auth/ws-ticket` 이라 적었고 `wsTicket.ts` 의 docstring 은 `/api/auth/ws-ticket` 이라 적었다. 고침은 **전체 경로를 그대로 받는 `apiRequestPath`** 로 바꾸는 **제품 런타임 2줄**이다(`loginWithAccessPin` 이 이미 따르던 규약 — 인증은 `/api/auth/*`, 코어는 `/v1/*`). 소유자는 **둘**이다: 서버 라우트 표와 대조하는 pytest 계약 `tests/test_cr14_client_path_contract.py` **6건**(래퍼를 해석한 실효 경로의 namespace 도달성 · 추출 전제 · 자의 자기검사 · 두 결함 pin · 죽은 경로 부재 · **리터럴 전용 검사가 볼 수 없다는 사실 자체**) + **정확한 URL** 을 고정하는 vitest `dashboard/src/utils/wsTicket.test.ts` **5건**(이 호출의 URL 을 보는 테스트가 하나도 없었던 것이 살아남은 이유다 — `useEventWebSocket.test.tsx` 는 `fetchWsTicket` 자체를 mock 한다). **증인** `attempt-033/repro/f43_client_path_contract_witness.py`(A 눈먼 자리 · B 라우트 표 도달성 · C 살아 있는 서버를 자유 포트·격리 상태로 띄워 **부작용 없는 ticket 경로만** 실제로 친다) — 고침 전 **exit 1**(위반 2건 + live 405) / 고침 후 **exit 0**(0건 + live 200). **이빨은 실제로 되돌려 확인했다**: 고침 전 소스(pristine worktree)에서 계약 **3 failed / 3 passed** · vitest **2 failed / 3 passed**, 고침 후 계약 **6 passed** · vitest **5 passed**. 대시보드 전체 **86 파일 통과** · `tsc` 0 오류 · eslint 0 오류(남은 경고 1건은 HEAD 에도 있다). **이 attempt 가 스스로 틀린 기록**: 증인의 자가 **여섯 번** 틀렸고(쿼리 보간을 경로 param 으로 접음 · 래퍼 정의를 호출부로 셈 · `apiRequestPath` 분기의 메서드를 GET 으로 박음 · C 축이 고정 문자열을 침), **증인이 저장소 `data/`(다른 서버가 쓰는 sqlite)를 열 수 있었다**(`data_dir` 기본값이 상대경로다) — 지금은 상태·cwd 를 임시 디렉터리로 돌리고 트리에 아무것도 쓰지 않음을 확인했다(F-34 와 같은 부류를 증인이 저지를 수 있었다는 사실을 숨기지 않는다). **고침 전 값은 pristine 사본 트리에서 쟀다**(작업 트리를 되돌리지 않았다). **게이트 목록은 바뀌지 않았다**(required **22**). *(측정 결과는 실행 뒤 채운다 — D-52)* **판정 MOVED 없음**(남은 차단 사유는 사람·조직 축이다). 앞선 후보는 `45918a51272055340becae53fa759800c6ae387a`(attempt-032 — **F-42: 브라우저 증인에게 게이트 소유자를 줬다**(required 21 → **22**). 이 attempt 는 **증인을 만든 attempt 가 스스로 남긴 구멍**을 닫았다(attempt-030·031 의 경계 문서 §2-6·§2-7). *(선언 — 측정 전)* 후보·지문은 **게이트를 돌리기 전에** 적었고, 선언 시점에 **후보 트리 == 작업 트리**임을 확인했다(`worktree_fingerprint(.)` == `tree_fingerprint_of_commit(45918a51)` == `5a8950a1…`, manifest sha256 `22ec46c2…` — 게이트 목록이 **바뀐** attempt 이므로 이 값도 바뀌었다). **이 attempt 의 첫 선언이고 재선언은 없다**. *(무엇을 쟀나)* 커버리지를 **manifest 의 선택자 × 실제 파일**로 계산한다(손으로 적은 목록이 아니다): **고침 전(그 게이트 항목을 뺀 manifest 사본) = 0/9** · **고침 후 = 9/9**. 브라우저 패밀리 9파일 29건은 **ambient 백엔드 없이 돈다**(29 passed / 43.5s) — 그래서 required 게이트가 될 수 있었다. `accessibility-e2e` 는 `accessibility.spec.ts` **한 파일**만 돌고, CI 의 full suite 는 `main` push/PR 에서만 돌며 게이트 절차(`run_attempt_close.py`)·주간(`ga-close.yml`)·릴리스(`release.yml` → ga-close)는 **어느 것도** 그 슈트를 부르지 않는다. *(고침의 자리)* 새 required 게이트 `dashboard-e2e-witnesses` 가 **이름 규칙**(`e2e/tests/cr\d+-`)으로 패밀리를 돈다 — 목록 고정이 아니라 **전수성**이므로 증인을 새로 만들면 자동으로 게이트 안이고(계약이 그 사실을 잰다), `--project=chromium --reporter=list` 를 **게이트 명령이 직접** 들고 있다(등록부가 스킵 귀속을 그 리포터에 걸어 두었으므로 설정 변경이 게이트에 닿지 않는다). **경계**: ambient 백엔드가 필요한 스펙(`task-execution`·`ws-contract-e2e` — CLI 로 서버를 띄우는 CI job 의 슬라이스)은 게이트가 **삼키지 않는다**(게이트 환경에서 항상 빨개지면 사람은 게이트를 끄는 쪽을 고른다). 그 슬라이스가 **여전히 게이트 밖**이라는 사실은 지우지 않고 계약·증인이 **소리 내어 센다**. *(계약)* `tests/test_cr14_browser_witness_gate_contract.py` **5건** — 게이트가 required 이고 프로젝트·리포터를 명령에서 고정 · 증인 파일 **전수**가 선택자에 걸린다 · 선택자가 ambient 스펙을 삼키지 않는다 · 이빨(가족 이름은 통과하고 가족 밖 이름은 증인으로 세지 않는다) · 등록부 분류(playwright·per_test·close_check). 곁들여 **게이트 인벤토리 계약**(`tests/test_cr14_candidate_evidence.py`)의 pinned 목록과 **스킵 등록부**(`scripts/gate_skip_register.json`)의 분류도 함께 고쳤다(게이트를 늘리면 그 둘을 적어야 한다는 attempt-024 의 규율 그대로다). *(이빨 — 세 방향)* ① 게이트를 manifest 에서 **지우면** 계약 **4 failed** ② `required` 를 **false 로 강등**하면 **1 failed** ③ 가족 이름으로 **일부로 실패하는 증인**을 만들면 게이트가 **exit 1 로 그 파일의 이름을 대며** 멈춘다(그 파일은 A 의 세계에서 **아무도 돌리지 않았다**) — 실험 직후 그 파일을 지우고 **지문이 원래 값으로 돌아오는지**까지 확인했다(`repro/f42_witness_gate_ownership_witness.py` · `logs/f42-witness.txt` · `logs/f42-contract-teeth.txt`). *(이 attempt 가 바꾸지 않은 것)* **제품 런타임 코드 0줄** · 기존 21개 게이트의 명령·타임아웃·required 여부 **불변** · **판정 MOVED 없음**(남은 차단 사유는 사람·조직 축이다). 앞선 후보는 `2b4a198bde74da72fd325359e4351111b2a1f94a`(attempt-031 — **F-41 후보를 측정으로 반증했다 — 탈출구는 마지막 수단인가**(*재선언 없음* — 이 attempt 의 첫 선언이 그 후보의 측정이다). attempt-030 이 자기 한계로 적은 문장(*"M3(수동 탈출구) 경로는 이 실행에서 발화하지 않았다"*)이 남긴 질문을 실 서버·실 PIN 로그인·제품의 버튼·**그룹째 SIGKILL**·같은 포트·같은 상태 디렉터리로 쟀다. 증인은 화면이 **스스로 포기할 때까지** 재기동하지 않고 기다린 뒤(자동 재연결 3회를 소진해야 M3 가 발화한다 — 그 전제가 이 질문의 전부다) 재기동하고 여섯 축을 잰다: **V1** 포기 + 탈출구 제공 · **V1b** 서버가 **없는 동안** 눌러도 화면이 다시 시도할 수 있는 상태로 남는다 · **V2** 행이 서버의 현재 사실과 같아진다 · **V3** 연결 라벨이 정착한다 · **V4** 세션이 살아 있다 · **V5** **두 번째** 크래시·재기동에서도 V2·V3 이 재차 참이다. 실측은 `["연결됨","재연결 중","연결 오류"]` → 탈출구 → `["연결 오류","연결됨"]` · 행은 **"실행 중단(소유 프로세스 종료) — 재개 가능"**(서버와 일치) · **exit 0**. **대조군이 결론을 정한다**: 같은 증인을 **F-39 고침 이전 트리**(`HEAD^` 스냅숏)에서 돌려도 **exit 0** — 이 축은 attempt-030 **이전에도 참**이었으므로 **결함이 아니라 재지 않은 경로**였고(수동 경로는 `retry` 가 올리는 `reloadVersion` = **목록 이펙트의 의존성** 때문에 처음부터 동작했다), attempt-030 이 닫은 결함은 **자동** 재연결 경로에만 있었다. **이빨**: 스크래치 트리에서 `retry` 를 `() => undefined` 로 무력화하고 그 트리의 번들을 `vite build` 로 다시 만들어 돌리면 **exit 1**(위반 4건 — 두 사이클 모두 화면이 크래시 전 스냅샷을 그대로 두고 `연결 오류` 에 머물렀다) · 계약 **1 failed / 3 passed**(증인은 **작동하는 탈출구와 무력한 탈출구를 구별한다**). **자를 먼저 의심했다**: 첫 두 실행의 실패는 제품이 아니라 자의 결함이었다(2회차에는 배울 것이 없었다 — 두 번째 크래시가 서버의 사실을 바꾸지 않았다; 연결 라벨을 **전이 중**에 읽었다) — 2회차는 **새 태스크를 제출**해 낡은 스냅샷을 만들고 라벨은 **정착** 뒤에 읽는다. **제품 런타임 코드 변경 0줄** — 대신 `retry` 가 목록을 다시 읽는 **암묵적 의존**에 소유자를 준다(계약 `useTaskExecutionEvents.test.ts` 3 → 4건). **판정 MOVED 없음**(남은 차단 사유는 사람·조직 축이다). 앞선 후보는 `e02447fb3ac83303f04c052c0d68248d21ed2aa4`(attempt-030 — **F-39 · F-40: 크래시 뒤 열려 있는 화면도 새 사실을 배워야 한다**(*재선언 없음* — 이 attempt 의 첫 선언이 그 후보의 측정이다). "이미 열려 있는 화면"은 attempt-028 이 기술 잔여 ③으로, attempt-029 가 한계로 — **두 번 연속 재지 않고 남긴** 질문이다. 실 서버 + 실제 PIN 로그인 + 제품의 버튼 + **그룹째 SIGKILL** + 같은 포트·같은 상태 디렉터리로 재기동: 고침 전 화면의 연결 라벨은 `["연결됨"]` 이었다(스트림이 조용히 다시 붙어 **연결을 잃은 적이 없다고 말했다**) — 그 순간 서버는 `execution_owner: dead`·`resumable: true` 였는데 화면은 크래시 전 스냅샷(`label=running` · 재개 **없음** · 취소만)을 그대로 그렸고, M1 은 재기동 뒤 **기존 토큰으로 200**(세션은 살아 있었다 — 질문이 "로그아웃됐는가"로 바뀌지 않는다)이었다. **위반 1건 · exit 1** — F-36 이 **서버 표면**에서 없앤 막다른 길(복구 가능한 태스크에 재개 대신 취소만)이 **이미 열려 있는 화면**에는 그대로 있었다. 뿌리는 구조다: 스트림은 스스로 다시 붙지만 **목록은 한 번 읽은 스냅샷**이고 그 안에 시간에 따라 변하는 값(`status`·`execution_owner`·`resumable`)이 들어 있다. 고침(제품 런타임): `useTaskExecutionEvents.ts` 가 **재연결 성공 지점에서 목록을 다시 읽는다** — 그 재조회는 `reloadVersion` 이 **아니라 별도 경로**(`refreshTaskList`)다(`reloadVersion` 은 스트림 이펙트까지 다시 시작시키므로 스트림이 스스로 그것을 올리면 **재시작 루프**가 된다). 실패는 **삼키지 않는다**(낡은 목록을 조용히 들고 있으면 그 병이 돌아온다 — 메시지로 올리고, 연결 상태는 스트림이 소유하므로 여기서 뒤집지 않는다). 목록→상태 반영과 선택 유지 규칙은 `applyTaskList` **한 곳**이 소유한다. **서버는 한 줄도 바뀌지 않았다**(F-35/F-36 의 소유·재개 규칙 · `execution_owner`·`resumable` 의 값과 의미 · "재시작이 고아 행을 자동으로 끝내지 않는다"는 정책 모두 그대로다). **F-40(측정 도구)**: 이 증인을 세우는 과정에서 도구가 크래시를 **재현할 수 없다**는 사실이 먼저 드러났다 — 하네스는 `uv run … uvicorn` 을 띄우는데 실제 서버는 런처의 **자식**이라 `listener.pid` 에 신호를 보내면 런처만 죽고 서버는 **살아서 포트를 붙들고 있었고**(`/health` 계속 200), 재기동이 **토큰 비밀을 새로 만들면** 질문이 "화면이 배우는가"에서 "사용자가 로그아웃됐는가"로 바뀐다 — 두 성질 모두 그 파일의 docstring 이 **처음부터 약속**하고 있었다. 하네스는 이제 **프로세스 그룹**째 신호하고(`detached: true` = 새 세션 · `-pid`) 상태 디렉터리의 비밀을 **재사용**하며 `port`·`stateDirectory`·`workingDirectory` 를 받는다. 증인 둘 — 제품 경로 `dashboard/e2e/tests/cr14-crash-restart-surface.spec.ts`(M1 세션 · M2 자동 · M3 수동 탈출구, 고침 전 **exit 1** / 고침 후 **exit 0**) + 도구 `attempt-030/repro/f40_crash_harness_witness.py`(A 런처만 신호 → 서버가 **살아남는다** · B 그룹 신호 → **죽는다** · C 같은 디렉터리로 재기동 = 같은 토큰 **200**·비밀 재사용 / 새 비밀 = **401**, **exit 0**). 계약 `dashboard/src/features/task-execution/useTaskExecutionEvents.test.ts` 3건 — ① 재연결 뒤 다시 읽는다 ② **끊기지 않으면 읽지 않는다**(거짓 양성 0) ③ 실패를 조용히 넘기지 않는다: 고침 전 **2 failed / 1 passed**(exit 1) / 고침 후 **3 passed**(exit 0). 공용 화면 도구 `dashboard/e2e/helpers/taskScreen.ts` 로 attempt-029 의 증인과 **같은 자**를 쓴다). 앞선 후보는 `1890d2b09d061629e769e95a03c12096625b3d70`(attempt-029 — *(두 번의 재선언)* 첫 선언 `084ab3cd`(지문 `377e7723…`)의 **첫 측정이 `python-tests` 에서 멈췄다** — 증인의 테스트 단위 비활성화 표기를 `tests/test_cr14_gate_skip_register.py` 의 tripwire 가 **정당하게** 거부했고(대시보드 소스의 스킵 표기는 소유자가 없다: 그 등록부의 채널은 게이트 스킵이다), 표기를 뺀 수정이 트리를 옮겼다(두 번째 선언 `5711a3a8`/`5bb77b79…`). 두 번째 측정도 같은 tripwire 에서 멈췄다 — 그 검사는 소스를 **문자열로** 스캔하므로 **그 표기를 이름으로 부른 주석**도 걸렸다(뜻을 지키려면 말로 적어야 한다). 세 번째 후보에서 표기 0건을 만족했고 이 후보에서 측정을 완주했다. 재선언의 근거는 D-52 의 순서다. 그 두 실패는 위 `required gate` 줄에 기록으로 남긴다. **F-37 · F-38: 화면의 쓰기 경로는 서버가 받아들이는 것이어야 한다**(attempt-029). attempt-028 이 기술 잔여로 남긴 세 번째(**크래시 뒤 라벨·버튼을 실 브라우저 눈금으로** 보는 슬라이스)를 밟는 **첫 걸음**에서, 물어보려던 질문보다 먼저 다른 사실이 나왔다: 제품의 유일한 쓰기 경로("작업 제출")가 **어떤 기계 상태에서도** 성공하지 못했다. 두 결함의 뿌리는 같다 — 화면과 서버가 만나는 **와이어를 재는 자리가 없었다**(화면 쪽에는 그 본문을 고정하는 테스트가 하나도 없었고, 서버 쪽 계약은 `context.project_id` 중첩만 쟀다). ① **F-37**: 화면은 정체성을 **최상위** `project_id`(+`project_revision`)로 보내는데(대화·파일 경로가 쓰는 형태이며 공유 리졸버 `extract_project_id_from_payload` 가 **이미** 지원한다) `TaskSubmitRequest` 는 `extra="forbid"` 라 그 본문을 **422**(`body -> project_id`)로 막았다 — 그래서 화면은 프로젝트를 알고 있을 때 제출하지 못했다. 고침은 `extra` 를 푸는 것이 아니라 두 형태를 **선언**하는 것이다(중첩이 있으면 그것이 이기고, 모르는 필드는 계속 거부한다). ② **F-38**: 서버는 한 번도 열리지 않은 프로젝트를 `last_accessed_at: null` 로 직렬화하는데(`ProjectRecord.model_dump()` — 기본 프로젝트가 그렇다) 화면의 스키마는 `.optional()` 이라 `null` 을 거부했고, 목록 파싱이 실패하면 스토어가 비어 화면이 **자기 프로젝트를 얻지 못한 채** 정체성 없이 제출했다(서버: 400 `missing_execution_context`) — 즉 **처음 설치한 기계**와 **이미 쓰고 있는 기계** 어디에서도 그 버튼은 성공할 수 없었다. 고침은 서버의 타입을 그대로 표현하는 `.nullish()` 다. 증인 둘 — 와이어 `attempt-029/repro/f37_submit_identity_witness.py`(B1 수용 · B2 **이빨**: 등록되지 않은 최상위 `project_id` 는 404 · B3 중첩 회귀 · B4 무정체성 400: 고침 전 **exit 1**(B1 422) / 고침 후 **exit 0**) + 제품 경로 `dashboard/e2e/tests/cr14-task-submit-contract.spec.ts`(두 기계 상태로 나눠 잰다 — 서버의 cwd 를 격리하면 레지스트리도 격리된다: 알고 있는 프로젝트 = 3위반 · 처음 설치한 기계 = 2위반 · 고침 전 **exit 1** / 고침 후 **exit 0**). 계약 `tests/test_cr14_screen_server_wire_contract.py` 6건(고침 전 3 failed · 견제: 유령 프로젝트가 202 를 받으면 실패 · `extra="forbid"` 유지 · 무정체성 400 유지 · 한 번도 열리지 않은 레코드가 `null` 로 **키를 갖고** 나간다) + `dashboard/src/api/contractAlignment.test.ts` 2건(실제 zod 로 `null` 을 받아들인다 — 기존 픽스처가 "실제 응답"이라 적힌 채 `last_accessed_at` 을 **빼놓은** 것이 이 결함이 살아남은 이유다). 하네스에 `workingDirectory` 를 더해 브라우저 증인의 **전제**(처음 설치한 기계)를 만들 수 있게 했다). 앞선 후보는 `9fb7f068…`(**F-36: 재시작한 서버는 주인에 대해 아는 것을 말한다**(attempt-028). attempt-027 이 문서에 한계로 남긴 **절반**("실 서버를 띄운 재시작 슬라이스는 재지 않았다" — 그때는 **러너 두 개**로 질문의 핵심만 쟀다)을 그대로 밟았다: `uvicorn` 기동 → 실제 인증(PIN → bearer) → 태스크 제출 → **SIGKILL** → **같은 DB** 재기동. 죽은 소유자의 `running` 행은 표면에서 살아 있는 실행과 구별되지 않았다 — ① 상세·목록이 `running` 이라고만 말하고 **주인에 대한 필드가 없으며**(SIGKILL 뒤에도 행은 `running`·`owner_pid=51653` 그대로다) ② 같은 행에 대해 `POST /resume` 이 **200** 을 돌려주고 ③ 그래서 화면이 `running` 을 "실행 중"으로 읽어 복구 가능한 태스크에 **재개가 아니라 취소만** 제안했다(막다른 길) — 위반 4건. 뿌리는 attempt-027 과 **같은 병**이다: 소유 판정이 한 함수(`_process_is_alive`)에 있는데 그 함수를 **행동**만 쓰고 **보고**는 쓰지 않았다. 고침은 **정책이 아니라 표면**이다(재시작이 고아 행을 자동으로 끝내면 재개 가능성이 사라지므로 저장된 상태는 그대로 둔다): `execution_owner`(`live`/`dead`/`none`) · `resumable` 을 `/api/tasks` 와 `/api/tasks/{id}/status` 가 말하고(둘 다 **저장하지 않는 파생 값**), 값은 **한 곳**에서 만든다 — `execution_owner_of` 는 `can_prepare_resume`/`can_cancel` 과 **같은 liveness 함수**를 쓰고 `resumable_task` 는 행동의 **두 조건**(`can_prepare_resume` + 체크포인트 존재)을 그대로 옮긴다(화면이 버튼을 그릴 근거와 서버가 받아줄 근거가 갈라지지 않는다). 화면은 그 필드로 버튼을 그리고(`taskLifecycleActions.ts` 가 규칙을 소유) 주인이 죽은 비종결 행의 라벨을 **"실행 중단(소유 프로세스 종료) — 재개 가능"** 이라고 말하며(`aria-label` 도 같은 값), 서버가 필드를 보내지 않으면 **추측으로 대체하지 않고** 예전 상태 규칙으로 되돌아간다. 목록 조회가 `owner_pid` 를 싣고 체크포인트 유무는 **한 번의 질의**로 모은다. 증인 `attempt-028/repro/f36_orphan_surface_witness.py` — 실 서버 + 실 인증 + SIGKILL + 같은 DB 재기동으로 고침 전 **exit 1**(위반 4건) / 고침 후 **exit 0**. 계약 `tests/test_cr14_task_orphan_surface.py` 12건(이빨: 체크포인트가 없으면 표면도 `false` 이고 행동도 거부 · 거짓 양성 0 · **투영은 행을 쓰지 않는다**). 앞선 후보는 `645902353672bbd45520c0e6e6933944ebc62b1d`(**F-35: 취소도 소유 규칙을 지킨다**(attempt-027). *(재선언)* 첫 선언 `e12ec3cb`(지문 `4dbfa955…`)의 첫 측정이 `security-bandit` 에서 멈춰(B608 표기 누락 — `prepare_resume` 과 같은 형태의 SQL) 그 수정이 코드를 옮겼다; 재선언했고 이 후보에서 measurement 가 완주했다: `resume` 은 `can_prepare_resume(raw_status, owner_pid)` 로 **소유자**를 보는데 `cancel` 은 보지 않았다 — 그래서 메모리에 없는 태스크는 DB 의 `status ∈ {pending, running}` 만 보고 `cancelled` 로 적혔고, **다른 프로세스가 실행 중인** 태스크의 이력이 거짓이 됐다(그 행은 끝났다고 말하는데 실행은 계속되고, 소유자의 마지막 쓰기는 CAS 에 밀린다). 고침: 규칙을 복제하지 않고 `task_process_ownership.can_cancel` 이 `_process_is_alive` 를 **resume 과 공유**하며, `TaskStateStore.cancel_if_permitted` 가 `status`·`owner_pid`·`version` 을 조건에 넣어 CAS 로만 적고(거부는 행을 건드리지 않는다), 거부 사유가 `CancellationVerdict` 로 **이름 붙어** API **409**(활성 아님은 404)로 나가며 화면은 서버의 사유를 말한다. **`pending` 취소는 허용된다** — 소유자의 시작 CAS 를 실패시켜 **진짜로 실행을 막기** 때문이다. 증인 `attempt-027/repro/f35_foreign_cancel_witness.py` — 실물 프로세스 둘(소유자 + 재시작한 서버를 흉내내는 두 번째 러너)로 고침 전 **exit 1**(위반 3건) / 고침 후 **exit 0**. 앞선 후보는 `d62ba10add0e006e53eeef3ee6e8c2f6bec73097`(attempt-026 — **F-34**(attempt-026): 게이트는 **자기가 재는 코드를 바꾸지 않는다**. 지문은 게이트 **앞에서** 한 번 재고 끝났고, 그 뒤에 게이트가 무엇을 바꿨는지 묻는 자리가 없었다 — 그래서 `dashboard-build`(추적 번들 `src/antigravity_k/dashboard_dist/` 를 제자리에서 다시 쓴다)가 **exit 0** 으로 45개 파일을 바꿔도 보고서는 여전히 "21개 초록이 한 코드 상태의 것"이라고 주장했다. 두 결함이 겹쳤다: ① **낡은 출하물을 재는 자리가 없다**(소스만 고치고 번들을 안 만들면 화면은 고치기 전 UI 이고, 번들을 지칭하는 pytest 계약 6파일은 **전부 통과**한다 — 68 passed) ② **게이트가 코드를 바꿔도 아무도 실패하지 않는다**(그 탐지기는 attempt-025 에서 **다음 배치의 이어받기 거부**뿐이었다). 고침: 지문을 만들던 **한 곳**(`tree_digests`)이 경로별 내용 지도를 돌려주고, 러너가 게이트 **직전·직후**의 지도를 비교해 차이가 있으면 그 게이트를 `tree_moved` 로 적는다(경로·이유를 달고, 명령의 `exit_code` 는 **그대로 남긴다** — 명령은 성공했고 실패한 것은 계약이다) 그리고 실행 전체가 **exit 1** 로 끝난다 — **required 여부로 거르지 않으므로** non-required 게이트로 같은 결함이 조용해질 수 없다. 소비자 둘도 맞췄다: 승인 검증기는 이 상태를 **구조 오류로 적지 않되** 승인하지 않고, 마감 검사 **항목 9** 는 **어느 게이트가 어느 파일을 바꿨는지 이름으로 대며** 거부한다. 증인 `attempt-026/repro/f34_stale_bundle_witness.py` — **같은 증인 파일**을 `--tree-at` 만 바꿔: 고침 전 **exit 1**(러너가 낡은 번들을 `passed` 로 통과) / 고침 후 **exit 0**(러너가 `tree_moved` 로 거부, 그리고 **소스에서 다시 만든 번들에서는 조용하다** — 과잉 탐지 0을 실제 게이트 `dashboard-build` 로도 확인: `passed` · 드리프트 0). **제품 런타임 코드 변경 0줄**. 앞선 후보는 `a2f6f72454ebdba975d95bc574333a5983ac7c9d`(attempt-025 — **F-33**(attempt-025): '항상 허용' 은 **읽고 되돌리고 셀 수 있는** 동의다 — attempt-023/024 가 승인 경로로 '항상 허용' 상태를 만들고도 **재지 않고 남긴** 질문을 실물 코드에서 쟀다. ① **수명**: 부여는 **만료 시각이 없다** — 365일 뒤에도 살아 있고, 사라지는 자동 경로는 **프로세스 재시작 뿐**이다(부여를 영속화하지 않는다). ② **범위**: 도구 **하나 전체**를 덮고, 인자·경로·프로젝트와 무관하다(동의한 것은 `echo hello` 한 번이지만 `run_bash_command` 의 다른 모든 호출이 승인 없이 실행된다). ③ **프로세스 폭**: 싱글턴이라 **다른 세션·다른 프로젝트가 같은 부여를 본다**(프로세스가 새로 뜨면 0 — 세션 간 유출은 아니다). 결함은 이 사실들이 아니라 **감사 불가능성**이었다: ④ 부여 저장소가 `set[str]` 이라 **시각·근거가 사라졌고**(`AlwaysAllowGrant` 로 바꾸어 `granted_at`·`granted_for` 를 보존) ⑤ 부여를 **읽는 표면이 없었고**(해제만 있었다 — `always_allowed_grants()` + `GET /api/approval/always-allowed` 를 넣고 화면에 부여 목록·부여 모두 해제를 올렸다) ⑥ **동의 없이 실행된 횟수를 아무도 세지 않았고**(`record_auto_approval()` 이 집행 지점과 자동 승인 지점에서 세고 — **순수 조회는 세지 않는다**, 화면은 "동의 없이 N회 실행"을 댄다) ⑦ 그 읽기 경로를 만들자 `GET /{request_id}` 가 `always-allowed` 를 요청 ID 로 삼켜 **404** 를 냈다(전용 경로를 **먼저** 선언하고 그 이유를 주석·계약·증인이 함께 들고 있다) ⑧ 동의 문구가 `${description} 항상 허용` 이라 **이 요청**을 덮는 것처럼 읽혔다(`${tool} 도구를 항상 허용 (이후 모든 호출을 승인 없이 실행)` + "도구 전체"를 말하는 안내 문단). 해제는 이제 **무엇을 되돌렸는지 이름을 댄다**(`revoked`) — 조용한 해제는 검증할 수 없다. **바꾼 것은 부여의 범위·수명이 아니라 그것의 관측성**이다(도구 전체·프로세스 수명은 설계 그대로이며, 화면이 그 사실을 정확히 말하게 했다). **attempt-002 이후 처음으로 제품 런타임 코드가 바뀐 attempt** 이며(승인 경로의 관측성 — 판정을 움직이지 않는다), 앞선 후보는 `e288573490b56faa9d7673b1563f70f3e1ee389b`(attempt-024 — **R-16 폐쇄**: 등록부가 스킵을 소유하는 단위를 **required 게이트 21개 전수**로 넓혔고(그 전에는 `python-tests` 한 곳이었고, 그 사실은 attempt-021 이 스스로 한계 R-16 으로 적어 둔 것이었다), 그 과정에서 **스킵이 이름을 잃는 두 자리**와 **게이트가 여전히 초록인 채 사라질 수 있는 한 자리**를 찾았다: ① `api-e2e` — `pytest … -q --tb=short` 단독이라 스킵이 생기면 `N skipped` 만 남고 **어느 테스트인지 없다**(등록부가 세야 할 대상이 이름을 잃으면 소유가 성립하지 않는다) → `-rs` ② `dashboard-test` — vitest 기본 리포터는 `1 skipped` **건수만** 낸다는 사실을 스크래치 테스트로 실측 → `--reporter=verbose` 로 `↓ <파일> > <describe> > <테스트>` 를 얻는다 ③ `clean-machine-runtime` — 스크립트가 `--skip-e2e`·`--skip-wheel` 을 갖고 그 플래그가 켜지면 요약에 `SKIP` 행이 생기면서 **게이트는 exit 0** 이다. 게이트 명령에는 지금 두 플래그가 없지만 **그 사실을 지키는 자리가 없었다** → 등록부가 `skip_channels` 로 선언하고 계약이 **스크립트의 모든 스킵 표기 ⊆ 선언**과 **게이트 명령이 그 플래그를 쓰지 않음**을 잰다 ④ `accessibility-e2e` 는 이미 귀속된다(playwright `list` 리포터가 `- <n> [project] › <파일>:<줄> › <이름>` 을 낸다 — 실측). 넓힌 소유는 **전수성**으로 잠근다: 게이트를 추가하고 분류를 빠뜨리면 계약이 그 자리에서 멈추고, 편입된 보고서의 **게이트별 스킵 건수**는 마감 검사가 읽어 소유자 없는 스킵을 거부한다(게이트 안에서는 보고서가 아직 없으므로 순환한다 — F-24 가 "선언한 초록의 출처"를 마감 단계로 옮긴 것과 같은 이유). **증인 `attempt-024/repro/r16_gate_skip_visibility_witness.py` — 고침 전 exit 1(검사 A·B 실패)/고침 후 exit 0(5/5)**, 계약 `tests/test_cr14_gate_skip_register.py` 12건 + 마감 검사 이빨 6건. **제품 런타임 코드 변경 0줄**. 앞선 후보는 `ed9e225a72a0447e9655a44e13bde5b875e2991f`(attempt-023 — **F-32 + `orchestrator-refactor-rewrite` 폐쇄**: 스킵돼 있던 에이전트 실행 루프 2건을 닫아 **소유자 없는 스킵을 0건**으로 만들었다. 무조건 스킵은 "고칠 것이 남았다"는 뜻이지만 **제품 결함이라는 뜻은 아니었다** — 실패 이유를 관측하니 두 루프는 돌고 있었고, 막던 것은 ① 더블에 `manager.router` 가 없고(`tool_loop.run_loop` 는 `manager.router.get_combo(...)` 를 무조건 부르고, 실제 `ModelManager` 는 생성자에서 항상 그것을 만든다) ② 더블의 `get_model_info(name)` 이 실제와 다른 시그니처를 요구했으며(실제는 `status()` 별칭·**무인자**) ③ 도구 호출이 **승인 게이트**(CR-04/CR-05 — 테스트 이후에 생겼다)에서 멈췄고 ④ 스크립트가 **루트 밖 인터프리터**로 실행하려 해 셀 경로 경계가 거부했으며 ⑤ `calls == 2` 가 더블의 이중 계산과 **패키지 기본 config 의 재시도 예산**에 걸렸다. 게이트를 끄거나 경계를 우회하지 않고 — 동의는 **제품의 승인 경로**(`get_approval_manager()` + `ALWAYS_ALLOW`)로 만들고, 명령은 루트 기준 상대 경로로 바꾸고, 더블이 한 턴을 한 번만 세게 하고, 재시도 예산을 1로 고정했다. 두 테스트는 이제 조건 없이 돌고 **6 passed / 0 skipped**. 등록부는 두 파일을 `closed` 로 옮기되 **`observed_files` 에 남겼다**(무조건 스킵이 돌아오면 대조가 즉시 실패 — F-31a 성질을 처음 실제로 쓴 자리). `KNOWN_GAP` 0건이 계약의 침묵이 되지 않도록, 0건일 때는 경계 문서가 **"미검증 능력 0건"을 명시**해야 한다. 증인 `attempt-023/repro/f32_contract_drift_witness.py` **9/9**(고침 전 코드는 실패 · 고침 후는 통과 · 닫힌 파일에 스킵을 심으면 대조가 실패). **제품 런타임 코드 변경 0건**. 앞선 후보(attempt-022)는 **`d7e66a59c13ff57951422baef89c343cb146a2b6`**(**F-31 + `config-models-unregistered` 능력 복원**: 배포된 `/benchmark run` 의 기본 타겟이 config 가 소유하지 않는 콤보를 가리켜 매 실행마다 오류 행(점수 0)을 기록했다 — 그 이름을 코드에 갖고 있는 주체는 `BenchmarkHarness._default_targets()` 이고, 유일한 회귀 테스트가 `_raw` 에 합성 매핑을 주입해 실제 config 를 보지 않았다. `collective-council` 콤보(`strategy: collective`, 로컬 3모델)와 gemma-4-31B reasoning 항목을 설정에 복원했고, 새 계약 `tests/test_cr14_default_target_config_contract.py`(6건 · 이빨 2건)가 **실제 파일**로 그 일치를 잰다. 등록부는 `observed_files` 로 관측을 고정해 항목을 닫아도 관측이 줄지 않는다. **제품 런타임 코드 변경 0건**. 앞선 후보: **`1b0a024c790c79b58a5c377f865bfec7dc82bbea`**(attempt-021 — **R-8 감사 + F-30**: 게이트에서 **조용히 사라지는 테스트**를 등록부가 소유한다. ambient 13·6 → 고정 40 스킵 중 `documents` extra 23건은 게이트에 그 extra 를 넣어 **복원**(실측 87 passed / 0 skipped), 남은 17건은 분류·소유자·만료를 갖고, **미검증 능력 4건은 경계 문서에 적힌다**. 계약 `tests/test_cr14_gate_skip_register.py` 가 등록부와 실제 게이트 환경을 한 건씩 대조한다(증인 12/12). 앞선 후보: **`a590786513403b5da535ec13eef0807ea51e4676`**(attempt-020 — CR-12 소관 재확인(R-5) + **F-29** 폐쇄: 값 소유자 포인터를 **토큰**이 아니라 **실재하는 링크**로 확인하고, `"미커밋"` 무딘 조항을 **현재 상태 줄** 로 좁혔다(계약 26 → 28건, 증인 12/12). 앞선 후보: **`43cde98ea8ccf5d9d6a77996e571ecec209eefd3`**(attempt-019 — R-11: CI/릴리스가 마감 절차를 부른다(`ga-close.yml` — 매주 스스로 도는 `schedule` 포함) · publish 는 그것을 `needs` 로 갖는다 · 배선은 `tests/test_cr14_close_pipeline_contract.py` 가 소유한다. 앞선 후보: **`ecaeeecc8808275def43cb6fa09b4897ac4154b7`**(attempt-018 — F-27: 이어받기 **판단**이 게이트 **규칙**의 부분 복제였다(작업 트리 지문 축이 빠졌다) → 게이트의 `merge_refusal_reason` 에 **위임**하고, 거부되는 조합에서는 **조용히 새로 시작하지 않고** 이유를 대며 exit 2 로 끊는다. `close` 는 판단을 묻지 않아 기록 뒤 재확인이 살아 있고, 카드 부재는 usage error 로 맞췄다). 앞선 후보: **`afa4d26f`**(attempt-017 — F-25 마감 절차를 명령 하나로: 배치로 나눈 게이트 실행 → 보고서 편입 → 마감 검사 → 기록 뒤 재확인. **게이트 목록은 manifest 에서 런타임에 읽는다**. F-26 그 절차를 직접 돌려서 찾았다: 이어받기를 단계 순서가 아니라 **보고서의 정체성**으로 판단한다. 앞선 attempt-017 선언은 `8533319b` 이었고 **F-26 수정이 지문을 옮겨 낡았다**(측정 전이었으므로 attempt-017 안에서 재선언). 앞선 후보: `0c33aa2e`(attempt-016 — F-24 attempt 마감 검사: 선언한 초록의 출처를 게이트 밖에서 확인하고 지문 규칙을 `ga_gate` 한 곳으로 모았다. 앞선 후보: `b5729b61`(attempt-015 — F-23 울타리 이동 탐지기), `3fb3fcb9`(attempt-014 — `0a86b79e` 게이트 환경 고정 → `d7a2714d` 성능 검사 분리 → `292eecfc` 인벤토리 계약 → `0593dd27` bandit 선언 → `f95f22b9` attempt-013 기록 → `ded52af6` README 휘발성 값 제거·F-22 계약 → `3fb3fcb9` CR-12 계약 개정)). `git.dirty: true` 의 원인은 ` M vault_data` 한 줄(F-13)이며 **코드·산출물은 clean** 이다. 보조 식별자 코드 지문 **`02349a8d06945e438bdc60799ed770a87d6bb67d33d27f09b52008d242536ed6`**(`docs/`·`.omo/` 제외, **attempt-040 — 이 카드가 값의 유일한 선언 자리다**. *(선언 — 측정 전)* 후보 `b6003205365606407cadfd6cbb1c813110beef0f` · 후보==HEAD==작업트리 확인 · manifest `a40867c743a9…`. *(측정 결과)* 23개 게이트 완주 뒤에도 같은 값이었고, 보고서·HEAD·후보·작업 트리 넷이 이 값이다(`attempt-039/logs/fingerprint-invariance.txt`) — 후보 `bbb308f8` · 측정 HEAD `7e857fdb` · 작업 트리가 **같은 코드**다. *(앞선)* attempt-038 지문 `9362bdfc984cc58ee04885b1deeae2ef7406ced586ebbf2b6197a5351ba0b0b1` — 후보 `4c3f8364` · leftover 1건(EXTERNAL_HUB). *(앞선)* attempt-035 지문 `ac0757ccbc0b63b3b35c1dc28c71c32934c977f0e6d724227e7de73cd10ce13c` — 후보 `ae283604` · leftover 4건 계수. *(앞선)* attempt-033 지문 `1873d2c70f10bfcdfdbeca4344fc3d819c32fcc35aea988339353608e4845faa` — 그 attempt 의 선언 문장은 이랬다 — **attempt-033 — 이 카드가 값의 유일한 선언 자리다**(재선언 둘 — 측정 전)* 이 값은 **게이트를 돌리기 전에** 적었고(후보 `c66706ee121604dc1de8ed0362b4b9c427765137`), 선언 시점에 **후보 트리 == HEAD 트리 == 작업 트리**임을 확인한 뒤다(D-52 — 이번에는 `worktree_fingerprint(.)` 도 같다: `vault_data` 가 가리키는 커밋이 다시 같아졌다: F-13). **앞선 값 `f8cab12b…` 는 F-44 를 만나기 전의 후보 `ec76c7ce` 의 것이었고**(측정 중 런타임 상태가 작업 트리 지문을 `e116d58d…` 로 흔들었다), 그 고침(무시 규칙 + 계약 5건)이 코드를 옮겨 다시 선언했다. **첫 값 `03a7db8d…` 는 번들을 후보 밖에 두었던 후보 `b11ff74f` 의 것이었고**, `dashboard-build` 의 `tree_moved` 로 그 측정이 멈춘 뒤 번들을 후보 안으로 가져와 다시 선언했다. **이 attempt 는 게이트 목록을 바꾸지 않았다**(required **22** 그대로, 인벤토리는 계약에 pinned). *(측정 결과)* 22개 게이트를 완주한 **뒤에도** 같은 값이었고, `attempt-033/gate-report.json` 의 `git.tree_fingerprint` · `tree_fingerprint_of_commit(HEAD)` · `tree_fingerprint_of_commit(c66706ee)` · `worktree_fingerprint(.)` **넷이 모두 이 값**이다(`attempt-033/logs/fingerprint-invariance.txt`) — 후보 `c66706ee` · 선언 커밋 `fa4f069b` · 작업 트리가 **같은 코드**다. *(앞선 값의 이력)* `5a8950a1d356369d6524ec26142918ee50c4a748bbf3ec72829d9bed43d2083a` 는 **attempt-032 의 것**이다(`docs/`·`.omo/` 제외 — 그 카드가 값의 유일한 선언 자리였다). *(선언 — 측정 전)* 이 값은 **게이트를 돌리기 전에** 적었고(후보 `45918a51272055340becae53fa759800c6ae387a`), 선언 시점에 후보 트리 == 작업 트리임을 확인한 뒤다(D-52). **이 attempt 는 게이트 목록을 바꿨으므로** manifest sha256 도 `86c40edc…` → `22ec46c2…` 로 움직였다(마감 검사가 그 축도 대조한다 — F-26). *(측정 결과)* 22개 게이트를 완주한 **뒤에도** 같은 값이었고, `attempt-032/gate-report.json` 의 `git.tree_fingerprint` · `tree_fingerprint_of_commit(HEAD)` · `tree_fingerprint_of_commit(45918a51)` · `worktree_fingerprint(.)` **넷이 모두 이 값**이다(`attempt-032/logs/fingerprint-invariance.txt`) — 후보 `45918a51` · 선언 커밋 · 작업 트리가 **같은 코드**다. *(앞선 값의 이력)* 이 자리에 있던 `7461ae3da7d96e04756b59e8c4e20fd473d681309e8418d564ba9b007253d6c6` 는 **attempt-031 의 값**이고, 그 attempt 의 선언 문장은 이랬다 — **이 카드가 값의 유일한 선언 자리다**. *(선언 — 측정 전)* 이 값은 **게이트를 돌리기 전에** 적었고(후보 `2b4a198bde74da72fd325359e4351111b2a1f94a`), 선언 시점에 후보 트리 == 작업 트리임을 확인한 뒤다(D-52). *(측정 결과)* 21개 게이트를 완주한 **뒤에도** 같은 값이었고, `attempt-031/gate-report.json` 의 `git.tree_fingerprint` · `tree_fingerprint_of_commit(HEAD)` · `tree_fingerprint_of_commit(2b4a198b)` · `worktree_fingerprint(.)` **넷이 모두 이 값**이다(`attempt-031/logs/fingerprint-invariance.txt`) — 후보 `2b4a198b` · 선언 커밋 `46d8c1a6` · 작업 트리가 **같은 코드**다. *(attempt-030 의 이력)* `87c5091b…`**(`docs/`·`.omo/` 제외, **attempt-030 — 이 카드가 값의 유일한 선언 자리다**. *(선언 — 측정 전)* 이 값은 **게이트를 돌리기 전에** 적었고(후보 `e02447fb…` — 커밋 `e02447fb3ac83303f04c052c0d68248d21ed2aa4`), 선언 시점에 후보 트리 == 작업 트리임을 확인한 뒤다(D-52). *(측정 결과)* 21개 게이트를 완주한 **뒤에도** 같은 값이었고, `attempt-030/gate-report.json` 의 `git.tree_fingerprint` · `tree_fingerprint_of_commit(HEAD)` · `tree_fingerprint_of_commit(e02447fb)` · `worktree_fingerprint(.)` **넷이 모두 이 값**이다(`attempt-030/logs/fingerprint-invariance.txt`) — 후보 `e02447fb` · 선언 커밋 `8d35d47c` · 작업 트리가 **같은 코드**다. *(attempt-029 의 이력)* `57f38a23a4c457ea17bb914b733d9117c992ddcf83f49e64c77e198821250db5`, `377e7723…` 는 같은 attempt 의 **첫 선언**, `5bb77b79…` 는 **두 번째 선언** 값이다(두 후보의 측정이 모두 `python-tests` 의 같은 tripwire 에서 멈췄다 — 위의 `code candidate full SHA` 줄이 그 이유를 적는다). *(선언 — 측정 전)* 이 값은 **게이트를 돌리기 전에** 적었고, 후보 트리 == 작업 트리임을 확인한 뒤다(D-52). *(측정 결과)* 21개 게이트를 이 후보에서 완주한 **뒤에도** 같은 값이었고, `attempt-029/gate-report.json` 의 `git.tree_fingerprint` · `tree_fingerprint_of_commit(HEAD)` · `worktree_fingerprint(.)` 셋이 모두 이 값이다(`attempt-029/logs/fingerprint-invariance.txt`) — 후보 `1890d2b0` · 선언 커밋 `c4f7a731` · 작업 트리가 **같은 코드**다. *(attempt-028 의 이력)* `f838f2eaa7e70a08a49e253f7337a8de6bda8b7ce169842f9c1436e8960161e1` 는 attempt-028 의 값이다. *(attempt-027 의 이력)* `98fd66957231f71ca85475d8409252a42f44811bb2221ccfb33e9eaf5cbae429` 는 attempt-027 의 값이다. *(그 attempt 안의 재선언)* 첫 선언은 `e12ec3cb`(지문 `4dbfa955…`)이었고 **그 후보의 첫 fast 배치가 `security-bandit` 에서 멈췄다**(B608 — 새 `cancel_if_permitted` 의 UPDATE 가 `prepare_resume` 과 같은 형태인데 그 표기를 갖지 않았다). 표기를 맞춘 수정이 코드를 옮겼으므로 **측정 전에** 다시 선언한다(fast 17/18 기록은 위 `required gate` 줄에 남긴다). *(attempt-026 의 이력)* `994b21fd6087ddb02eb80c2d29806ee36c2d32aec359b1edead846a1cc3e459b` 는 attempt-026 의 값이다. *(attempt-025 의 이력)* `57e32c9ad96bd797…` 는 attempt-025 의 값이고, 그 attempt 안에서 한 번 **재선언**했다 — 첫 선언 `440c5e06`(지문 `e8e464c6…`)은 **측정 전에 낡았**다: `src/antigravity_k/dashboard_dist/` 가 **추적되는** 산출물이라(F-01) 소스를 고치면 그 번들이 함께 움직여야 하고, 게이트의 `dashboard-build` 가 실제로 그것을 다시 썼다(29 삭제 + 29 생성 + 1 수정). 번들을 후보 **밖**에 두면 후보의 배포본은 옛 동의 문구를 말하게 되므로 빌드를 후보 **안으로** 가져와 다시 선언했다(`a2f6f724`) — 게이트를 돌리기 **전**이다. attempt-024 는 `7ae9af28b85790d7…`, attempt-023 은 `37b76cb8b340bbb8…`, attempt-022 는 `6a51100f60be26fd…`, attempt-021 은 `15e79e84ec357ac8…`)
  - **값을 기록하는 순서(규율)**: 코드 동결 → 커밋 → gate 측정 → **기록 커밋은 `docs/` 전용**. `README.md`·`tests/**` 는 지문 **안**이므로 기록하면서 그것을 고치면 지문이 옮겨 방금 만든 증거가 낡는다(F-22 — attempt-013 의 기록 커밋이 `README.md` 를 고쳐 지문을 `2c5a15c8…` → `b9590b01…` 로 실제로 옮겼고, 그래서 README 에서 휘발성 값을 제거해 다시는 기록 커밋이 README 를 건드리지 않게 했다)
  - **SHA 는 커밋마다 움직이지만 지문이 같으면 같은 코드다** — 증거는 지문으로 읽는다. 지문 제외는 `docs/`·`.omo/` **접두사뿐**이라 `README.md`·`tests/**` 는 지문 안이다(attempt-009 의 `dd34a76b…` 는 기록 커밋이 이 둘을 고쳐서 이동했다 — F-14/D-51)
  - **마감은 절차다**(attempt-017, F-25 — R-10 폐쇄): `uv run scripts/run_attempt_close.py --attempt attempt-0NN --stage {fast|tests|heavy|close|all}`. `close` 단계가 보고서를 증거 트리에 **편입**한 뒤 마감 검사를 돌린다 — 편입이 없으면 검사는 FAIL 이다. 기록 커밋 뒤에는 `--stage close` 를 한 번 더 돌려 지문 불변을 확인한다. **이어받기는 단계 순서가 아니라 보고서의 정체성(같은 후보 sha·같은 manifest sha256)이 결정한다**(F-26) — 각 배치가 별개 프로세스라 호출 순서를 기억할 수 없고, `--stage tests` 단독 실행이 fast 18개를 덮어썼다(보고서 total 18 → 1). **F-27 은 attempt-018 에서 닫혔다**: 그 "정체성"은 게이트 규칙(후보 sha·manifest·**작업 트리 지문**)의 **부분 복제**였고, 작업 트리만 다른 경우 절차와 게이트가 갈라져 실행이 중단되거나 앞 배치 초록이 **조용히** 버려졌다 → 이제 절차는 게이트의 `merge_refusal_reason` 을 **그대로 묻고**(세 축을 넘긴다), 거부되는 조합에서는 이유를 대며 exit 2 로 끊으며 보고서를 **덮어쓰지 않는다**. `close` 는 판단을 묻지 않는다
  - **선언한 초록의 출처는 마감 검사가 확인한다**(attempt-016, F-24 — R-9 폐쇄): 게이트 밖에서 도는 `scripts/verify_attempt_close.py` 가 ① 선언된 지문을 측정한 보고서가 있는가 ② 그 보고서가 이름 붙인 커밋의 트리를 쟀는가 ③ manifest sha256·required 목록이 같은가 ④ **카드의 게이트 수치가 보고서 집계와 같은가** ⑤ 후보..HEAD 코드 스코프 변경이 없는가를 본다. **이 검사는 게이트 인벤토리에 넣지 않는다** — 넣으면 순환한다(보고서는 게이트 실행이 끝날 때 쓰인다)
  - **울타리 이동은 이제 계약이 잡는다**(attempt-015, F-23 — R-1 폐쇄): ① 선언된 지문이 **선언된 후보 커밋의 트리** 지문이고 ② 후보..HEAD 사이에 **코드 스코프를 건드린 커밋이 없어야** 하며(위반 경로를 이름으로 댄다) ③ 지문 함수가 git 이 보는 파일을 조용히 무시하지 않아야 하고 ④ 어떤 보고서도 **자기가 이름 붙인 커밋의 트리**를 측정했어야 한다. attempt-001~014 까지는 이 이동을 **사람이 눈으로** 찾았다
- evidence bundle 위치 / manifest SHA256: **attempt-002 는 번들을 만들지 않았다** — 근거는 `attempt-002/gate-report.json` + `reproduction.md`·`decision.md`·`manual-qa.md`·`logs/**`. attempt-001 번들(`attempt-001/bundle/`, `manifest.sha256` sidecar)은 **`evidence_kind: reference`, verify verdict `REFERENCE_ONLY`(exit 3). 승인 artifact가 아니다**로 유지
- required gate inventory / PASS / FAIL / NOT_RUN: **23 / 23 / 0 / 0**(attempt-040 — 커밋된 후보 `b6003205` · 지문 `02349a8d…` · **되돌리기 0회** · `tree_moved` **0건** · required **23/23 PASS** · C33-6 CLOSED · `dashboard-e2e-witnesses` owns `cr14-pin-ws-ticket` · 사람·조직 축으로 **NO-GO**)
- backend·frontend·실행 보안·설치/복구·실 provider·8h 결과: backend **6376 passed / 13 skipped / 16 deselected**(attempt-033 — 후보 `c66706ee`, 585.16s. 증가분 **+11** = F-43 계약 `tests/test_cr14_client_path_contract.py` 6건 + F-44 계약 `tests/test_cr14_runtime_state_scope_contract.py` 5건 · **스킵은 13 → 13 불변**, frontend **876 passed(86 files)** = +5(F-43 `wsTicket.test.ts` URL 고정 — 새 파일이라 파일 수 85 → 86). 이 attempt 는 **화면이 보내는 경로가 서버에 도달하게** 만들었다(제품 런타임 2줄) · 측정 트리의 결함(F-44)도 닫았다(무시 규칙 + 계약 5건, 제품 0줄)) · backend 앞선 값 **6365 passed / 13 skipped**(attempt-032 — 후보 `45918a51`, +5 = F-42 계약) · backend **6360 passed / 13 skipped / 16 deselected**(attempt-030 — 후보 `e02447fb`, 581.57s. **증가분 0**(이 attempt 의 계약은 대시보드 쪽이다) · **스킵은 13 → 13 불변**, frontend **870 passed(85 files)** = +3(F-39 단위 계약 `useTaskExecutionEvents.test.ts` 3건, 새 파일이라 파일 수 84 → 85). 이 attempt 는 **이미 열려 있는 화면**이 재연결 뒤 목록을 다시 읽게 만들었다 — **서버는 한 줄도 바뀌지 않았고**(F-35/F-36 의 규칙·표면·저장 상태 그대로), 바뀐 것은 화면의 **읽기 시점** 하나다) · 앞선 attempt-029 는 후보 `1890d2b0`, 579.36s. 증가분 **+6** = F-37·F-38 계약(`tests/test_cr14_screen_server_wire_contract.py` 6건), **스킵은 13 → 13 불변**, frontend **867 passed(84 files)** = +2(`last_accessed_at: null` 계약). 이 attempt 는 **화면의 쓰기 경로를 서버가 받아들이게** 만들었다 — 권한 경계는 그대로이고(모르는 필드 422 · 무정체성 400 · 유령 프로젝트 404) 두 정체성 형태가 **선언**됐으며, 하네스에 `workingDirectory` 를 더해 "처음 설치한 기계"를 재는 **전제**를 만들었다) · attempt-028 은 backend **6354 passed / 13 skipped / 16 deselected**(attempt-028 — 후보 `9fb7f068`, 562.51s. 증가분 **+12** = F-36 계약 12건(`tests/test_cr14_task_orphan_surface.py`), **스킵은 13 → 13 불변**, frontend **865 passed(84 files)** = +6(화면 규칙 `taskLifecycleActions.test.ts` 신규 + 패널 계약). 이 attempt 는 **재시작한 서버가 주인에 대해 아는 것을 말하게** 만들었다 — 저장된 상태는 그대로 두고 표면(`execution_owner`·`resumable`)을 더했으므로, 크래시 뒤 화면이 복구 가능한 태스크에 **재개를 제안**할 수 있게 됐다) · attempt-027 은 후보 `64590235`, 572.53s. 증가분 **+13** = F-35 계약 9 + API·서버 계약 4, **스킵은 13 → 13 불변**, frontend **859 passed(83 files)** = +4(화면 계약 1파일). 이 attempt 는 **취소 경로의 정직성**을 쟀다 — 이력이 “끝났다”고 말하는데 실행이 계속되는 상태를 불가능하게 만들었다) · attempt-026 은 **6329 passed / 13 skipped / 16 deselected**(후보 `d62ba10a`, 544.70s. 증가분 +9건은 F-34 계약 8 + 마감 검사 이빨 1이고, **스킵은 13 → 13 불변**이다 — 그 attempt 는 스킵을 되찾은 것이 아니라 **게이트가 재는 대상이 움직이지 않았음을** 잰다) · attempt-025 는 **6320 passed / 13 skipped / 16 deselected**(증가분 +18건 = F-33 계약 15 + 라우트·해제 검사 3) · attempt-024 는 **6302 passed / 13 skipped / 16 deselected**(증가분 +11건은 등록부 계약 신규 5 + 마감 검사 이빨 6이고, 그 attempt 는 스킵을 되찾은 것이 아니라 **가시성·소유**를 넓혔다) · attempt-023 은 **6291 passed / 13 skipped / 16 deselected**(스킵 −2 = 되살린 에이전트 루프 2건) · attempt-022 는 **6289 passed / 15 skipped / 16 deselected** · attempt-021 은 **6280 passed / 17 skipped / 16 deselected** · attempt-019 는 **6249 passed / 40 skipped / 16 deselected**(attempt-019 — 후보 `43cde98e`, 535.13s. 직전 attempt-018 은 6227 passed 였고, 6249 에는 이번 신규 계약 22건이 포함된다 15건·attempt-017 의 마감 절차 이빨 12건 중 신규분이며, 526.15s) · attempt-014 는 **6179 passed / 40 skipped / 16 deselected**(증가분 5건은 F-22 계약 4건 + CR-12 이빨 1건, 509.3s) · attempt-013 은 **6174 passed / 40 skipped / 16 deselected**(성능 16건은 전용 게이트로 분리했고, 게이트 환경이 lock 에 고정돼 skip 수가 먼저 다르다. 헤더가 `.cache/uv/builds-v0/.tmp*/bin/python` + pytest 9.1.1) + **python-benchmark 16 passed**(16.9s) · attempt-012 는 **6215 / 6 / 수집 6221**(당시 skip 감소는 R-6 이었고, attempt-013 이 그 원인을 **게이트 도구가 lock 이 아니라 호출 셀에서 왔다**로 특정했다 — F-18) · attempt-011 은 6200 / 13 · frontend **849 passed(81 files)**(F-14 — 종전 기록의 `846/80` 은 F-12 이전 값이었다) · dev 도구 체인 감사 **전체 트리 0건**(attempt-007, F-09 폐쇄) · 실행 보안 PASS · 설치/복구 `clean-machine-runtime` **PASS + 후보를 검증(3001 파일, `ref: HEAD`) · clean HEAD 재실행 PASS(39.2s)** · 컨테이너 `docker-build` **PASS(233.7s)** · 실 provider **미확보** · 8h soak **미실행** · 측정 도구 `stryker:quick` **exit 0 · All files 91.92%(quick 범위 2 파일, attempt-008)**
- 후보 트리 안정성(attempt-003 실측): **20-gate 전체 실행 후 코드 지문 불변** + `dashboard-build` 재빌드 **바이트 단위 동일** → 이 후보에서 검증은 트리를 바꾸지 않는다
- 지원 scope / 실제 외부 승인: 미확정 / 없음 (담당 **강병석** — 배정만, 승인 없음)
- 독립 리뷰 보고서와 대상 SHA: **[C14-08 판정서](./CR14_C14_08_RELEASE_OWNER_VERDICT.md)** / 후보 `b6003205` · 검토자 **강병석**(겸직) · 출시 책임자 판정 **NO-GO**
- 후보 트리 안정성(attempt-005 실측): suite 전후 + **20-gate 전체 실행 전후**에 코드 지문 `1981bfb5…` 가 **동일** — 이 후보에서 검증은 트리를 바꾸지 않는다(되돌리기 0회)
- 후보 트리 안정성(attempt-012 실측): 커밋된 후보 `1207118d` 에서 20-gate 실행 **후** 코드 지문 `7ecb4fc2…` 가 보고서 값과 **동일**(UNCHANGED) · 실행 후 트리는 ` M vault_data` 한 줄 · `data/` 드리프트 0 — 되돌리기 0회
- 후보 트리 안정성(attempt-031 실측): 커밋된 후보 `2b4a198b` 에서 **21-gate 실행 후** 코드 지문 `7461ae3d…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-031/logs/fingerprint-invariance.txt`) · 후보..HEAD 코드 스코프 변경 **0줄** · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건**
- 후보 트리 안정성(attempt-030 실측): 커밋된 후보 `e02447fb` 에서 **21-gate 실행 후** 코드 지문 `87c5091b…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-030/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건**(이 attempt 는 대시보드 소스와 추적 번들을 **후보 안에서** 함께 움직였고, 게이트 `dashboard-build` 가 그 번들을 다시 쓰지 않았다 — F-34 의 검사가 옳은 후보에서 물지 않았다) — 되돌리기 0회. 커밋별 지문도 같다: `e02447fb`(후보) = `8d35d47c`(선언, docs 전용) = 작업 트리 · 후보..HEAD 코드 스코프 변경 `[]`. 선언 후보와 측정 HEAD 가 다르지만(둘 다 docs 전용 차이) 지문이 같으므로 **같은 코드를 쟀다**(F-26 이 세운 성질)
- 후보 트리 안정성(attempt-029 실측): 커밋된 후보 `1890d2b0` 에서 **21-gate 실행 후** 코드 지문 `57f38a23…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-029/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건**(이 attempt 는 대시보드 소스와 추적 번들을 **후보 안에서** 함께 움직였고, 게이트 `dashboard-build` 가 그 번들을 다시 쓰지 않았다 — F-34 의 검사가 옳은 후보에서 물지 않았다) — 되돌리기 0회. 커밋별 지문도 같다: `1890d2b0`(후보) = `c4f7a731`(선언, docs 전용) = 작업 트리 · 후보..HEAD 코드 스코프 변경 `[]`(`git diff --name-only 1890d2b0..HEAD` = `docs/ga/CR14_FINAL_CANDIDATE_VERDICT.md` 하나)
- 후보 트리 안정성(attempt-028 실측): 커밋된 후보 `9fb7f068` 에서 **21-gate 실행 후** 코드 지문 `f838f2ea…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-028/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건**(이 attempt 는 대시보드 소스와 번들을 **후보 안에서** 함께 움직였고, 게이트가 그 번들을 다시 쓰지 않았다 — F-34 의 검사가 옳은 후보에서 물지 않았다) — 되돌리기 0회. 후보 트리 == HEAD 트리(선언 커밋 `536d6473` 는 docs 전용 — 이 attempt 는 재선언이 없었으므로 **한 번의 선언이 그대로 측정됐다**) == 작업 트리. 커밋별 지문도 같다: `9fb7f068` = `536d6473`
- 후보 트리 안정성(attempt-027 실측): 커밋된 후보 `64590235` 에서 **21-gate 실행 후** 코드 지문 `98fd6695…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-027/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건**(이 attempt 는 대시보드 소스와 번들을 **후보 안에서** 함께 움직였고, 게이트가 그 번들을 다시 쓰지 않았다 — F-34 의 검사가 옳은 후보에서 물지 않았다) — 되돌리기 0회. 커밋별 지문도 같다: `64590235` = `659b8b45` = `37f1d4b0`(선언·카드 커밋은 docs 전용, 코드 스코프 변경 `[]`)
- 후보 트리 안정성(attempt-026 실측): 커밋된 후보 `d62ba10a` 에서 **21-gate 실행 후** 코드 지문 `994b21fd…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-026/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** · **`tree_moved` 게이트 0건** — 되돌리기 0회. 후보 트리 == HEAD 트리(선언 커밋 `956d38bc` 는 docs 전용) == 작업 트리. 이 attempt 는 **지문을 만드는 한 곳을 손댔으므로**(경로별 내용 지도로 리팩터링) 고침 전 알고리즘을 그대로 재구현해 **같은 트리에서 같은 값**(`11bf3c44…`)이 나오는지 먼저 확인했다 — 규칙을 넓히면서 값을 바꾸면 그것 자체가 다른 결함이다(F-34 는 그 **다음**에 지도를 비교한다)
- 후보 트리 안정성(attempt-025 실측): 커밋된 후보 `a2f6f724` 에서 **21-gate 실행 후** 코드 지문 `57e32c9a…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-025/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 **0** — 되돌리기 0회. 후보 트리 == HEAD 트리(재선언 커밋 `dd5f9282` 는 docs 전용) == 작업 트리. **재선언이 있었다**: 첫 선언 `440c5e06`(지문 `e8e464c6…`)은 **측정 전에** 낡았다 — `src/antigravity_k/dashboard_dist/` 가 추적되는 산출물(F-01)이라 대시보드 소스를 고치면 번들도 함께 움직여야 하고, fast 배치의 `dashboard-build` 가 실제로 29 삭제 + 29 생성 + 1 수정을 냈다(그때 게이트가 "다른 작업 트리"라며 이어받기를 **거부한 것은 옳다**). 번들을 후보 **안으로** 가져와 다시 선언했고(`a2f6f724`), 빌드는 **두 번 돌려 바이트 동일**임을 확인했다(`440c5e06` 은 **측정되지 않았다**)
- 후보 트리 안정성(attempt-024 실측): 커밋된 후보 `e2885734` 에서 **21-gate 실행 후** 코드 지문 `7ae9af28…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-024/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄(F-13) · `data/`·`dashboard_dist` 드리프트 0 — 되돌리기 0회. 후보 트리 == HEAD 트리(선언 커밋 `8aa01a42` 는 docs 전용) == 작업 트리. **명령 2줄이 바뀌어 manifest sha256 이 이동**했으므로(`a18ff1e5…` → `86c40edc…`) 게이트 목록 21개를 **다시 돌렸다**(목록은 불변 — 마감 검사 조항 ④가 그 일치를 요구한다)
- 후보 트리 안정성(attempt-022 실측): 커밋된 후보 `d7e66a59` 에서 **21-gate 실행 후** 코드 지문 `6a51100f…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-022/logs/fingerprint-invariance.txt`) · 실행 후 트리는 ` M vault_data` 한 줄 · `data/`·`dashboard_dist` 드리프트 0 — 되돌리기 0회. 후보 트리 == HEAD 트리(선언 커밋 `de62e509` 는 docs 전용) == 작업 트리
- 후보 트리 안정성(attempt-019 실측): 커밋된 후보 `43cde98e` 에서 **21-gate 실행 후** 코드 지문 `7f19c3a7…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-019/logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회. **F-28 수정 뒤 재선언한 후보에서 완주**했고, 낡은 부분 보고서는 **거부**됐다(exit 2 · 미덮어쓰기). 이번 attempt 의 초록은 이제 **사람이 아니라 파이프라인**에서도 돈다(`.github/workflows/ga-close.yml`)
- 후보 트리 안정성(attempt-018 실측): 커밋된 후보 `ecaeeecc` 에서 **21-gate 실행 후** 코드 지문 `56971ed6…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-018/logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회. **이어받기 규칙이 게이트 한 곳에 모인 것을 실행으로도 확인**(세 배치가 별개 프로세스로 18 → 19 → 21) · `--stage close` 가 판단을 묻지 않고 PASS
- 후보 트리 안정성(attempt-017 실측): 커밋된 후보 `afa4d26f` 에서 **21-gate 실행 후** 코드 지문 `29fac8a0…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-017/logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회. **마감 절차가 세 배치를 별개 프로세스로 돌렸고 그 사이에 앞 배치를 잃지 않았다**(F-26) · 실행 후 **마감 검사 PASS**(같은 지문)
- 후보 트리 안정성(attempt-016 실측): 커밋된 후보 `0c33aa2e` 에서 **21-gate 실행 후** 코드 지문 `1b84209e…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-016/logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회. 실행 후 **마감 검사 PASS**(같은 지문)
- 후보 트리 안정성(attempt-014 실측): 커밋된 후보 `3fb3fcb9` 에서 **21-gate 실행 후** 코드 지문 `b6494f40…` 가 보고서 값과 **동일**(UNCHANGED — `attempt-014/logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회. **기록 커밋은 `docs/` 전용**이라 이 값은 기록 뒤에도 변하지 않는다(F-22 — attempt-013 은 기록 커밋이 `README.md` 를 고쳐 `2c5a15c8…` → `b9590b01…` 로 옮겼다)
- 후보 트리 안정성(attempt-013 실측): 커밋된 후보 `0593dd27` 에서 **21-gate 실행 후** 코드 지문 `2c5a15c8…` 가 보고서 값과 **동일**(UNCHANGED — `logs/fingerprint-invariance.txt`) · `data/` 드리프트 0 · `dashboard_dist` 드리프트 0 — 되돌리기 0회
- 최종 판정: **NO-GO**(attempt-031 갱신 — attempt-031 은 **F-41 후보를 측정으로 반증**했다: attempt-030 이 자기 한계로 적은 *"M3(수동 탈출구) 경로는 이 실행에서 발화하지 않았다"* 를 실 서버·실 인증·**그룹째 SIGKILL**·같은 포트·같은 상태 디렉터리로 쟀다. 화면이 스스로 포기한 뒤 탈출구를 누르면 행이 서버의 새 사실(`dead`·`resumable`)로 바뀌고 라벨도 정착하며(`["연결 오류","연결됨"]`), 서버가 **없는 동안** 눌러도 막다른 길이 되지 않고, **두 번째** 사이클도 같다. **대조군**: F-39 고침 **이전** 트리에서도 exit 0 — 즉 **결함이 아니라 재지 않은 경로**였고(수동 경로는 `retry` → `reloadVersion` = 목록 이펙트의 의존성 때문에 처음부터 동작했다), attempt-030 이 닫은 결함은 **자동** 경로에만 있었다. **이빨**: 탈출구를 무력화한 스크래치 트리에서 증인 exit 1(위반 4건)·계약 1 failed / 3 passed. **제품 런타임 코드 변경 0줄** — 대신 그 암묵적 의존에 계약이 소유자가 됐다. **판정 이동 없음** — 남은 차단 사유는 사람·조직 축이다(EX-01~06 · 출시 책임자·독립 검토자 미배정 · 지원 scope 미확정 · 실 provider 미확보 · 8h soak 미실행). 앞선 attempt-029 갱신 — attempt-029 는 **F-37·F-38** 을 닫았다: **화면의 쓰기 경로는 서버가 받아들이는 것이어야 한다**. attempt-028 이 기술 잔여로 남긴 실 브라우저 슬라이스를 밟는 **첫 걸음**에서 제품의 유일한 쓰기 경로("작업 제출")가 **어떤 기계 상태에서도** 성공하지 못한다는 사실이 나왔다 — 알고 있는 프로젝트에서는 화면이 정체성을 **최상위** `project_id` 로 보내는데 `TaskSubmitRequest`(`extra="forbid"`)가 그 본문을 **422** 로 막았고, **처음 설치한 기계**에서는 서버가 보낸 `last_accessed_at: null` 을 화면 스키마가 거부해 화면이 자기 프로젝트를 **얻지 못한 채** 정체성 없이 제출했다(**400**). 고침은 각각 **표현할 수 없는 쪽**을 고치는 것이다: 서버가 두 형태를 **선언**하고(중첩이 이기고 모르는 필드는 계속 422 — 권한 경계는 그대로다), 화면 스키마가 `.nullish()` 로 서버의 타입을 그대로 표현한다. 증인 둘(와이어 + 제품 경로, 각각 고침 전 exit 1 → 후 exit 0)이 같은 파일로 전/후를 잰다. 이 attempt 는 **제품 런타임(쓰기 경로)**을 바꿨고 판정을 움직이지 않는다: 남은 차단 사유는 여전히 사람·조직 축(EX-01~06 · C14-08 · C14-04/05 · 지원 scope · 실 provider · 8h soak)이다. attempt-028 갱신 — attempt-028 은 **F-36** 을 닫았다: **재시작한 서버는 주인에 대해 아는 것을 말한다**. attempt-027 이 재지 않고 남긴 실 서버 재시작 슬라이스(SIGKILL → 같은 DB 재기동)를 밟으니, 죽은 소유자의 `running` 행이 표면에서 살아 있는 실행과 구별되지 않았다 — 주인에 대한 필드가 없고, 같은 행에 `POST /resume` 은 **200** 을 돌려주며, 화면은 복구 가능한 태스크에 **재개가 아니라 취소만** 제안했다(막다른 길). 고침은 **정책이 아니라 표면**이고(저장된 상태는 그대로 둔다 — 재시작이 고아 행을 자동으로 끝내면 재개 가능성이 사라진다), `execution_owner`(`live`/`dead`/`none`) 와 `resumable` 이 `/api/tasks`·`/api/tasks/{id}/status` 에서 나오며 값은 `can_*` 와 **같은 liveness 함수**에서 만들어진다. 이 attempt 는 **관측성**을 바꿨고(저장 정책·resume 규칙 불변) 판정을 움직이지 않는다 — 남은 차단 사유는 여전히 사람·조직 축(EX-01~06 · C14-08 · C14-03/04/05)이다. attempt-027 갱신 — attempt-027 은 **F-35** 를 닫았다: **취소도 소유 규칙을 지킨다**. `resume` 이 갖고 있던 소유 판정을 `cancel` 에도 **같은 함수로** 적용해, 살아 있는 다른 프로세스의 실행을 `cancelled` 로 적을 수 없게 했다(그 거짓은 이력·보고·복구 가능성 셋을 동시에 오염시켰다). 거부는 `owned_elsewhere` 로 **이름 붙어** API 409 로 나가고, 화면은 서버의 사유를 말한다. 이 attempt 는 **제품 런타임이 아니라 취소 경로의 정직성**을 바꿨고 판정을 움직이지 않는다 — 남은 차단 사유는 여전히 사람·조직 축(EX-01~06 · C14-08 · C14-03/04/05)이다. attempt-026 갱신 — attempt-026 은 **F-34** 를 닫았다: 게이트 러너가 **게이트 직전·직후의 경로별 내용 지도**를 비교해, 측정 대상 코드를 바꾼 게이트를 `tree_moved` 로 적고 실행을 **exit 1** 로 끝낸다(required 여부와 무관). 뿌리는 attempt-025 가 **실제로 멈춘** 자리다 — 낡은 번들은 pytest 계약 6파일을 전부 통과했고, 그 사실을 알려준 것은 **다음 배치의 이어받기 거부**뿐이었다. 이 attempt 는 **제품 런타임 코드를 0줄** 바꿨고 검증의 강도(게이트 목록·명령·required)도 그대로다. attempt-025 갱신 — attempt-025 는 **F-33** 을 닫았다: attempt-023/024 가 승인 경로로 '항상 허용' 상태를 만들고도 **재지 않고 남긴** 질문("그 부여가 **무엇을 덮고 언제 사라지는가**")을 실물 코드에서 재니 답은 **도구 하나 전체 · 만료 없음(프로세스 수명) · 프로세스 폭**이었다 — 셋 다 설계였고, 결함은 그 사실들이 **감사 불가능**했다는 것이다: 부여 저장소가 `set[str]` 이라 시각·근거가 사라졌고, 읽는 표면이 없었고(해제만 있었다), 동의 없이 실행된 횟수를 아무도 세지 않았고, 그 읽기 표면을 만들자 `GET /{request_id}` 가 `always-allowed` 를 요청 ID 로 삼켜 **404** 를 냈으며(경로 순서 — 고침을 넣고 계약을 돌려서 **발견**했다), 동의 문구가 **이 요청**을 덮는 것처럼 읽혔다. 다섯 자리를 고치고 요구는 그대로 둔 채 **확인을 의도에 맞췄다**(해제는 이제 **무엇을 되돌렸는지 이름을 댄다**). **attempt-002 이후 처음으로 제품 런타임 코드가 바뀐 attempt** 이며(승인 경로의 관측성), 바뀌지 않은 것은 **부여의 범위·수명**이다. 판정은 **NO-GO 유지** — 남은 차단 사유는 여전히 사람·조직 축(EX-01~06 · C14-08 · C14-03/04/05)이다. attempt-024 갱신 — attempt-024 는 attempt-021 이 스스로 한계로 적어 둔 **R-16** 을 닫아, 등록부가 스킵을 소유하는 단위를 게이트 `python-tests` 하나에서 **required 게이트 21개 전수**로 넓혔다: 그 과정에서 **스킵이 이름을 잃는 두 자리**(`api-e2e` 의 `-q` 단독 · `dashboard-test` 의 vitest 기본 리포터)와 **게이트가 초록인 채 단계가 사라질 수 있는 한 자리**(`clean-machine-runtime` 의 `--skip-e2e`·`--skip-wheel`)를 찾아 닫았고, `accessibility-e2e` 의 기존 귀속은 계약으로 고정했으며, **마감 검사 조항 8** 이 편입된 보고서에서 게이트별 스킵 건수를 읽어 소유자 없는 스킵을 거부한다. **스킵 수는 13 → 13, 제품 런타임 코드 변경 0줄**이다. attempt-023 갱신 — attempt-023 은 스킵돼 있던 에이전트 실행 루프 2건을 **제품 결함이 아니라 계약 드리프트**로 닫아 **소유자 없는 스킵을 0건**으로 만들었다(F-32) — 그 과정에서 관측이 "재작성"이라는 증거 없는 판단을 뒤집었다. attempt-022 갱신 — attempt-022 는 등록부의 미검증 능력 중 `config-models-unregistered` 를 **닫았지만 삭제가 아니라 능력 복원으로** 닫았다: 그 항목의 한 축(`collective-council`)은 테스트만의 약속이 아니라 **배포된 `/benchmark` 의 기본 경로**였고(F-31), 그래서 설정에 콤보·모델을 되돌려 능력을 살렸다(스킵 17 → 15). **제품 런타임 코드 변경 0건**. attempt-021 갱신 — attempt-021 은 **R-8 감사**로 **F-30** 을 닫았다: 게이트 환경 고정(F-18)이 도구 출처를 바로잡으면서 **돌던 테스트 30여 건을 조용히 스킵으로 옮겼고 아무도 세지 않았다**(ambient 13·6 → 고정 40) — 그중 `documents` extra 23건을 게이트에 넣어 **복원**했고(실측 87 passed / 0 skipped), 남은 17건은 분류·소유자·만료를 갖는 등록부로 옮겼으며 **어디서도 안 도는 제품 능력 4건**을 `KNOWN_GAP` 으로 경계 문서에 적었다. 계약이 등록부와 실제 게이트 환경을 한 건씩 대조한다(증인 12/12). **제품 런타임 변경 0건**이다. attempt-020 갱신 — attempt-020 은 **CR-12 소관 재확인(R-5)** 을 수행했고, 그 과정에서 **F-29** 를 닫았다: 값 소유자 포인터를 **토큰**으로 확인해 링크·존재를 보지 않았고, `"미커밋"` 조항이 과거 기록으로 무의미해져 메시지가 거짓을 말했다 — 둘 다 **요구는 그대로**, 확인을 의도에 맞췄다. **제품 런타임 변경 0건**이다. attempt-019 갱신 — attempt-019 는 **마감을 기계가 돌리게** 만들었다(R-11 폐쇄): `.github/workflows/ga-close.yml` 이 마감 절차를 부르고 매주 스스로 돌며, `release.yml` 의 publish job 들이 그것을 `needs` 로 갖는다 — **기계가 재측정하지 않은 주장은 출하되지 않는다**. 이번에도 **제품 런타임 코드 변경은 0건**이다. attempt-018 갱신 — 기술 gate 는 초록, 승인·커밋 위생이 차단. attempt-013~018 은 **검증 장치·기록 방식**의 결함만 닫았고 제품 런타임 변경은 attempt-012 이후 0건이다. attempt-017 은 마감 절차를 명령 하나로 만들고(F-25/R-10), 그 절차를 직접 돌려 절차 자신의 결함까지 닫았다(F-26) — 그 수정이 남긴 마지막 자리(이어받기 **판단**이 게이트 **규칙**의 부분 복제)를 attempt-018 이 닫았다(F-27: 규칙을 게이트 한 곳에 모으고 **묻기만** 하며, 거부는 **조용하지 않다**)). **단 "기술 결함 0건"의 의미를 정확히 읽을 것** — attempt-001~012 의 초록은 ambient 도구로 측정됐고, attempt-013 부터가 lock 을 검증한다. 제품 결함은 여전히 0건이고, 이번에 닫힌 3건은 검증 장치의 결함이다.
- 출시 책임자 / 판정 날짜: **강병석** / 2026-09-14 — **근거 있는 NO-GO 서명**([C14-08 판정서](./CR14_C14_08_RELEASE_OWNER_VERDICT.md)). GO 아님. 독립성 겸직 잔여.

## 6. 재개 순서 (권장, attempt-031 갱신)

0-f-9. **attempt-031 이 남긴 자리 — `0-f-8` 의 ③(수동 탈출구)은 **닫혔고**, 기술 잔여는 둘이다.**
   attempt-031 은 `0-f-8` 이 지목한 ③(**M3 수동 탈출구**)을 재서 **결함이 아님을 확인**했고(대조군:
   고침 **이전** 트리에서도 참이었다 — 결함은 **자동** 경로에만 있었다), 그 경로를 **증인 + 계약**으로
   고정했다. **제품 런타임 변경은 0줄**이다. 남은 기술 잔여는 둘: ① 살아 있는 다른 프로세스의 실행을
   **전달해서** 멈추는 IPC(거부가 지금은 정직한 대답이다 — 결함 수정이 아니라 **새 능력**이므로
   요구가 정한다) ② `resuming` 주인 사망 **타이밍**.
   그 다음이 **사람·조직 축**이다(출시 책임자·독립 검토자 배정 · 지원 scope 확정 · 실 provider 확보 ·
   8h soak `C14-08`).
   ⚠️ **경계는 그대로다**: 이 부류의 실 브라우저 증인 셋(`cr14-crash-restart-surface` ·
   `cr14-task-submit-contract` · `cr14-retry-escape-hatch`)은 **어느 required 게이트도 돌리지 않는다**
   — 기계가 계속 재게 하려면 **게이트 소유를 먼저 정해야** 한다(소유자 없는 스킵을 만들지 않는다는
   규칙과 같은 문제다 — F-24 와 같은 위치).

0-f-8. **attempt-030 이 남긴 자리 — 기술 잔여는 셋뿐이고, 판정을 움직이는 것은 사람 축이다.**
   attempt-030 은 `0-f-7` 이 지시한 ①(크래시 뒤 **이미 열려 있는 화면**)을 밟아 F-39 를 닫았고, 그
   과정에서 **측정 도구 자신의 결함**(F-40 — 크래시가 크래시가 아니었다)을 함께 닫았다. 제품 변경은
   **화면 하나**이고 서버의 규칙·표면·저장 상태는 그대로다. 남은 기술 잔여는 셋:
   ① 살아 있는 다른 프로세스의 실행을 **전달해서** 멈추는 IPC(거부가 지금은 정직한 대답이다 — 이것은
   결함 수정이 아니라 **새 능력**이므로 요구가 정한다) ② `resuming` 주인 사망 **타이밍** ③ 이제 남은
   실 브라우저 눈금은 **M3(수동 탈출구) 경로** 뿐 — 고침 후에는 M2(자동)가 먼저 참이 되어 증인의
   분기가 M3 를 타지 않는다(그 경로는 코드에 있고, 세션은 F-40 의 M1 로 확인했다).
   그 다음이 **사람·조직 축**이다(출시 책임자·독립 검토자 배정 · 지원 scope 확정 · 실 provider 확보 ·
   8h soak `C14-08`).
   ⚠️ **새 경계 하나**: `cr14-crash-restart-surface.spec.ts` 는 **어느 required 게이트도 돌리지 않는다**
   (`dashboard-test` 는 vitest 계약을 돌리고, `accessibility-e2e` 는 `accessibility.spec.ts` **하나만**
   돈다) — 크래시·재연결 슬라이스를 기계가 계속 재게 하려면 **게이트 소유를 먼저 정해야** 한다
   (소유자 없는 스킵을 만들지 않는다는 규칙과 같은 문제다 — F-24 와 같은 위치).

0-f-7. ~~**다음 걸음 — ① 을 먼저 본다(attempt-029 가 두 번 연속으로 남긴 문장이다).**~~ —
   **attempt-030 에서 완료했다**(F-39, 그리고 그 질문의 전제를 가리던 F-40 까지). 아래는 그 시점의
   기록이고, **답은 "아니오"** 였다: 열려 있는 화면은 새 사실을 배우지 않았고, 그 사실을 한 번도
   말하지 않았다(연결 라벨 `["연결됨"]`). attempt-029 는
   기술 잔여(③ 실 브라우저 눈금)를 밟는 **첫 걸음**에서 제품의 쓰기 경로가 죽어 있는 것을 만나
   F-37·F-38 을 닫았고, **물어보려던 질문(F-39 후보 — 크래시 뒤 열려 있는 화면)은 여전히 재지
   않았다**(그 질문은 증인의 설계 주석·증거팩·이 `0-f-7` 에 **말로** 적혀 있다 — 게이트가 소스의
   테스트 단위 비활성화 표기를 두 번 정당하게 거부했고, 등록부의 채널은 게이트 스킵이라
   대시보드 소스의 표기를 소유할 자리가 없다). 그 질문은 이제 준비가 다
   갖춰져 있다(실 서버 + 실 로그인 + 실 제출 + **격리된 cwd** + 고정 포트). 가설은 "목록 조회가
   `reloadVersion` 에만 매여 있어 스트림이 다시 붙어도 크래시 전 스냅샷이 남는다"이고,
   **측정이 아니다**. 그 다음이 ② 사람·조직 축(출시 책임자·독립 검토자 배정 · 지원 scope 확정 ·
   실 provider 확보 · 8h soak `C14-08`) — 기술 축 세 건이 다 닫혀도 판정을 움직이는 것은 이 축뿐이다.

0-f-6. **다음 걸음 — 남은 두 축 중 하나를 고른다.** attempt-028 은 기술 축에서 F-36 을 닫았고,
   기술 축은 다시 **제품 결함 0건 · 검증 장치 결함 0건**이다(이번에도 결함은 **표면**에 있었다 —
   소유 판정은 한 함수에 있었는데 그것을 **행동만** 쓰고 **보고**는 쓰지 않았다). 남은 선택지는 둘이다:
   ① **사람·조직 축**(판정을 움직일 수 있는 유일한 축): 출시 책임자·독립 검토자 배정 · 지원 scope 확정 ·
   실 provider 확보 · 8h soak(`C14-08`) — 이 중 어느 것도 코드로 닫히지 않는다.
   ② **기술 잔여 세 건**(위 `0-f-5` 와 attempt-028 의 한계): 살아 있는 다른 프로세스의 실행을 **전달해서**
   멈추는 IPC(거부가 지금은 정직한 대답이다) · `resuming` 행의 주인이 죽는 **타이밍** · 크래시 뒤
   라벨·버튼을 실 브라우저에서 보는 슬라이스.

0-f-5. ~~**C14-03 의 취소·중단 슬라이스를 실행한다**(`0-d` 가 남긴 것)~~ — **attempt-027 에서 절반 완료했다**(F-35). 물음은 `resume` 은 소유자를 보는데 `cancel` 은 보는가였고 답은 **아니오**였다: 다른 프로세스가 **살아 있는 소유자**의 태스크를 `cancelled` 로 적을 수 있었고, 그 행은 "끝났다"고 말하는데 실행은 계속된다(취소 신호는 소유자 프로세스 **안**에 있다). 세 관측이 동시에 거짓이었다 — ① 취소가 성공으로 보고됨 ② 멈췄다는 함의 ③ "일어난 일의 이력"이라는 주장(소유자가 10단계를 끝까지 수행했는데 최종 행은 `cancelled` + "lost in memory" — 마지막 쓰기가 CAS 에 밀렸다). 고침은 규칙을 복제하는 것이 아니라 **공유**하는 것이다: `can_cancel` 이 `resume` 과 `_process_is_alive` 를 같이 쓰고, `cancel_if_permitted` 가 읽은 `status`·`owner_pid`·`version` 을 조건에 넣어 CAS 로만 적으며(거부는 행을 **건드리지 않는다**), 거부 사유가 `CancellationVerdict`(`owned_elsewhere`)로 **이름 붙어** API **409**(활성 아님은 404)로 나가고 화면이 서버의 `detail` 을 말한다. `pending` 취소는 **허용**한다 — 그 취소는 소유자의 시작 CAS 를 실패시켜 **진짜로 실행을 막기** 때문이다. 증인 `attempt-027/repro/f35_foreign_cancel_witness.py` — 실물 프로세스 둘로 고침 전 **exit 1**(위반 3건) / 고침 후 **exit 0**.
   ⚠️ **남은 절반은 attempt-028 에서 닫혔다**(F-36): 실 서버(`uvicorn` + 실제 인증 + **SIGKILL** + 같은 DB 재기동)로 재니 재기동한 서버가 죽은 주인을 **살아 있는 실행과 구별해 말하지 않았고**, 정작 같은 행에 `POST /resume` 은 **200** 을 돌려주었다 — 표면과 행동이 갈라져 있었다. 이제 `execution_owner`·`resumable` 이 두 표면에서 나오고 화면이 그 필드로 버튼을 그린다.
   ⚠️ **그래도 남은 것**: ① 다중 프로세스에서 실행을 **전달해서** 멈추는 IPC 는 여전히 없다(거부가 정직한 대답이다) ② `resuming` 행의 주인이 죽는 **타이밍**은 규칙으로만 덮었고 실 서버로 만들지 않았다 ③ 크래시 뒤 라벨·버튼은 **DOM 계약**으로만 쟀다(실 브라우저 눈금은 없다).
   ⚠️ **새 능력은 만들지 않았다**: 다중 프로세스에서 취소를 소유자에게 **전달**하는 IPC 는 존재하지 않는다 — 거부가 정직한 대답이다. 그 능력이 필요한지는 **요구**의 문제이고, F-33 이 남긴 **R-17**(부여의 범위·수명 정책)과 함께 열려 있다.

0-f-4. ~~**R-16 을 닫는다**~~ — **attempt-024 에서 완료했다**. 등록부가 스킵을 소유하는 단위가 게이트 `python-tests` **하나**였고, 그 한계는 attempt-021 이 스스로 적어 둔 문장이었다("다른 파이프라인 …은 이 등록부의 소관이 아니다"). 그런데 같은 후보가 **required 게이트 21개**로 초록을 만들고 그중 **다섯이 테스트를 돈다**(`python-tests` · `python-benchmark` · `api-e2e` · `dashboard-test` · `accessibility-e2e`) — 나머지 넷의 스킵은 **아무도 세지 않았다**. 넓히기 **전에 먼저 셈**했고(러너별 스킵 표기를 스크래치 프로브로 실측), 그 셈이 세 자리를 가리켰다: ① `api-e2e` 는 `-q` 단독이라 스킵이 생겨도 `N skipped` 만 남고 **이름이 없다**(세야 할 대상이 이름을 잃으면 소유가 성립하지 않는다) → `-rs` ② `dashboard-test` 는 vitest **기본 리포터가 건수만** 낸다 → `--reporter=verbose` ③ `clean-machine-runtime` 은 `--skip-e2e`·`--skip-wheel` 채널을 갖고 켜지면 요약에 `SKIP` 행이 생기면서 **게이트는 exit 0** 인데, 그 사실이 어디에도 적혀 있지 않았다 → 등록부가 `skip_channels` 로 선언하고 계약이 **스크립트의 모든 스킵 표기 ⊆ 선언**과 **게이트 명령의 미사용**을 잰다. `accessibility-e2e` 는 이미 귀속됐다(playwright `list`) — 고치지 않고 그 성질을 계약으로 **고정**했다. 소유는 **세 겹**으로 잠갔다: **전수성**(게이트를 추가하고 분류를 빠뜨리면 그 자리에서 실패) + **귀속**(pytest `-v`/`-rs` · vitest verbose · playwright `list` 를 **실제 명령·설정에서** 확인) + **실제 실행**(마감 검사 **조항 8** 이 편입된 보고서에서 `close_check` 게이트의 스킵 건수를 읽어 소유자 없는 스킵을 거부한다 — 게이트 안에서는 보고서가 아직 없어 순환한다, F-24 와 같은 위치). 증인 `attempt-024/repro/r16_gate_skip_visibility_witness.py` — **고침 전 exit 1 / 고침 후 exit 0(5/5)**. **스킵 13 → 13 · 제품 런타임 코드 변경 0줄.**

0-f-3. ~~**`orchestrator-refactor-rewrite` 를 닫기**~~ — **attempt-023 에서 완료했다**(F-32). 두 테스트는 **제품 결함이 아니라 계약 드리프트**로 죽어 있었다: 더블이 리팩토링 이전 인터페이스를 흉내내고 있었고, 승인 게이트·셀 경로 경계는 테스트보다 **나중에** 생겼다. 다섯 자리를 계약에 맞췄고(게이트는 하나도 약화하지 않았다 — 동의는 `get_approval_manager()` 로 만들고, 경계는 그대로 두었다), 두 파일은 조건 없이 돌며 **6 passed / 0 skipped** 다. 등록부는 두 파일을 `closed` 로 옮기면서 **관측 목록에는 남겼다** — 이제 무조건 스킵이 돌아오면 대조가 즉시 실패한다. 증인 `f32_contract_drift_witness.py` **9/9**.
   ⚠️ **소유자 없는 스킵은 이제 0건이다**(남은 13건은 mlx 4 · unsloth 7 · access-pin 2 로 전부 소유자가 있다). 새 스킵을 만들려면 **등록부에 적어야** 하고, 적지 않으면 계약이 실패한다.
   ⚠️ **다음 값을 보는 순서**: 이제 기술 축은 **제품 결함도 검증 장치 결함도 0건**이지만 — 판정은 여전히 **NO-GO** 다. 막고 있는 것은 **사람·조직 축**(출시 책임자·독립 검토자 미배정 · 지원 scope 미확정 · 실 provider 미확보 · 8h soak 미실행 · **C14-08 미배정**)이다. 다음 attempt 는 기술이 아니라 이 축을 봐야 한다.


0-g. ~~**지문 이동을 사후에 탐지하는 계약**~~ — **attempt-015 에서 완료했다**(F-23/R-1, `tests/test_cr14_fence_movement_detection.py`). attempt-014 는 그 이동을 **사람이 눈으로** 찾았고, 그 사실을 한계로 남겼다 — 이제는 계약이 문다(선언 지문 == 후보 커밋 트리 지문 · 후보..HEAD 코드 스코프 변경 0건 · 지문 함수가 git 이 보는 파일을 무시하지 않는가 · 보고서가 이름 붙인 커밋의 트리를 쟀는가).

0-i-2. ~~**F-27 을 닫는다**~~ — **attempt-018 에서 완료했다**(R-12 폐쇄). 이어받기 **판단**을 게이트의 `merge_refusal_reason` 에 **위임**하고(세 축: 후보 sha · manifest · **작업 트리 지문**), 거부되는 조합에서는 이유를 대며 **exit 2** 로 끊는다 — 보고서를 **덮어쓰지 않고** `rm <보고서>` 안내를 출력한다. `close` 는 판단을 묻지 않아 기록 뒤 재확인이 살아 있다. 이빨 8건 신규(**위임 증명** 포함) · 증인 `attempt-018/repro/f27_fix_witness.py` **8/8** · **회귀** `attempt-017/repro/f26_merge_identity_witness.py` **5/5**(스텁을 버리고 실물 게이트로 재작성 — F-26 성질이 F-27 수정 뒤에도 그대로다).

0-i. ~~**절차를 사람이 시작하지 않아도 되게 만들기(가장 값어치 있음)**~~ — **attempt-019 에서 완료했다**(R-11 폐쇄). attempt-016~018 이 만든 마감 검사(`scripts/verify_attempt_close.py`)와 마감 절차(`scripts/run_attempt_close.py`)는 **사람이 돌려야** 작동했다(R-10 → R-11). 이제 `.github/workflows/ga-close.yml` 이 그것을 부르고 **매주 스스로 돌며**(`schedule`), `release.yml` 의 publish job 들이 `needs: [build, ga-close]` 로 **막힌다** — 기계가 재측정하지 않은 주장은 출하되지 않는다. 배선 자체가 계약(`tests/test_cr14_close_pipeline_contract.py` 22건)이라 조용히 풀릴 수 없다.
   ⚠️ **대가**: 태그 직전에 **버전을 올리는 커밋(코드 스코프)** 이 생기면 선언이 낡는다 — 태그 전에 그 커밋을 후보로 **다시 선언하고** 절차를 한 번 더 돌려야 릴리스가 통과한다(그것이 "기계가 확인한 주장"의 값이다).

0-h. ~~**CR-12 계약 개정의 재확인(R-5)**~~ — **attempt-020 에서 완료했다**(CR-12 소관으로 수행, F-29 폐쇄). 확인 결과 개정의 **의도는 보존됐고**(커밋≠승인 · 값은 README 에 박지 않는다 · 값의 소유자는 판정 카드), 다만 **확인 방법이 요구보다 약했다**: ① 값 소유자 포인터를 **토큰**(이름이 어딘가 있음)으로 보아 링크가 아니거나 다른 문서를 가리키거나 파일이 없어도 통과했다 → **실재하는 링크**를 요구한다 ② `"미커밋" in checklist` 는 후보 커밋(attempt-009) 뒤로 과거 attempt 기록이 공급하는 무딘 조항이 되어 메시지가 거짓을 말했다 → **현재 상태 줄**이 커밋된 후보·승인 없음을 말하고 미커밋을 주장하면 실패하도록 좁혔다. 계약 26 → **28건**, 증인 `CR-12/attempt-002/repro/cr12_r5_review_witness.py` **12/12**(개정 **전** 규칙의 실제 코드로 구멍 3종을 실증). **요구를 약화시킨 자리는 없다** — 두 경우 모두 요구는 그대로이고 검사가 세워졌다.

0-e. ~~**게이트가 lock 을 검증하는가**~~ — **attempt-013 에서 완료했다**(F-18·F-19·F-21). 게이트에 필요한 extra 를 명시하고(`python` 5종 `--extra dev --extra rag` · `security-bandit` `--extra dev`), 선언되지 않은 도구(`bandit`)를 dev extra 에 넣어 lock 에 포함시켰으며, wall-clock 검사를 전용 required 게이트로 옮겼다. 결과: 인벤토리 **21**, `uv.lock` `cd6b8281a7ef…`.
   ⚠️ **게이트를 손대면 계약이 먼저 깨진다** — `tests/test_cr14_gate_env_pinning.py`(도구 출처) · `test_cr14_gate_load_isolation.py`(성능 검사 위치) · `test_cr14_login_state_isolation.py`(보안 상태 격리) · `TestCandidateGateInventory`(필수 목록).
   ⚠️ **`uv run --isolated --frozen <tool>` 만 써 놓고 extra 를 빠뜨리지 말 것** — uv 는 호출 셀의 PATH 로 떨어진다.

0-f. ~~**남은 감사(기술, 선택)** — R-8: pinned 환경의 skipped 40 과 ambient 의 6/13 은 **다른 자의 눈금**이다~~ — **attempt-021 에서 완료했다**(감사 수행 + F-30 폄쇄, 대상은 `scripts/gate_skip_register.json` 으로 옮겼다). 감사 결과: 그 차이는 실재했고 **세 가지로 갈렸다** — ① **출하 능력** `documents`(pypdf)를 **어떤 파이프라인도 설치하지 않아** PDF/DOCX 수집을 재는 23건이 게이트·CI·주간 어디서도 안 돌았다 → 게이트에 그 extra 를 넣어 복원(실측 87 passed / 0 skipped). ② `mlx`·`unsloth` 는 **소유자가 있다**(`ci.yml` 매트릭스 · `weekly-drift.yml` — 계약이 워크플로 안에서 파일 이름을 확인한다). ③ **어디서도 안 도는 제품 능력 4건**: 에이전트 실행 루프(프로그램 생성·품질 재시도 — `OrchestratorAgent` 리팩토링 뒤 **조건 없는** `@pytest.mark.skip`) · 제품 설정 약속(gemma-4-31B · collective-council 콤보 — `config.yaml` 에 항목이 없다). ③은 `KNOWN_GAP` 으로 owner·plan·만료일을 갖고 `docs/ga/CR14_GATE_COVERAGE_BOUNDARY.md` 에 적힌다 — 그 문서가 `21/21` 의 **경계**다. **다음 기술 작업**: `orchestrator-refactor-rewrite` 의 두 테스트를 되살리는 것 — attempt-023 이 완료했다(**그리고 "재작성"이 아니라 "계약 정렬"이었다** — F-32).

0-f-2. ~~**`config-models-unregistered` 를 설정으로 닫기(가장 값싼 다음 걸음)**~~ — **attempt-022 에서 완료했다**(**F-31** 을 함께 폐쇄). 닫는 방식은 **삭제가 아니라 능력 복원**이다: `collective-council` 을 `strategy: collective` 콤보로, gemma-4-31B 를 reasoning 로스터로 되돌렸다(둘 다 2026-05 세대 정리 `e462a8aa`·`d131dc71` 이 **의도 기록 없이** 지운 항목이다). 이유는 그 콤보가 테스트만의 약속이 아니라 **배포 경로**였기 때문이다 — `BenchmarkHarness._default_targets()` 가 그 이름을 코드에 갖고 있어 `/benchmark run` 이 매번 오류 행(점수 0)을 기록했고, 유일한 회귀 테스트는 `_raw` 에 합성 매핑을 주입해 그 사실을 볼 수 없었다. 계약 `tests/test_cr14_default_target_config_contract.py` 6건(이빨 2건 — tmp 실제 YAML 에서 콤보·멤버를 지우면 실패) · 등록부는 `observed_files` 로 관측을 고정(항목을 닫아도 관측이 줄지 않는다) · 스킵 17 → **15**.
   ⚠️ ~~**남은 것은 `orchestrator-refactor-rewrite` 다** — state graph 구조에 맞게 **새로 쓰는 일**이다~~ — **attempt-023 이 이 문장을 뒤집었다**: 그 판단은 **증거 없이** 내려진 것이었고, 관측해 보니 두 루프는 **돌고 있었다**(실패는 더블·승인 게이트·셀 경로 경계에서 났다 — 계약 드리프트). "다시 쓰는 일"이 아니라 **다섯 자리를 계약에 맞추는 일**이었고, 재작성보다 **훨씬 쌌다**. 교훈: 스킵 표기를 "제품이 못 한다"로 읽기 전에 **실패 이유를 먼저 관측한다**.

0. ~~**CR-01~CR-14 커밋 → clean full SHA 고정 → 그 SHA 에서 20-gate 재실행**~~ — **attempt-009·010 에서 완료했다.**
   SHA `54e4169a`(attempt-009) → **clean HEAD `5ccb938e`**(attempt-010) · 커밋된 후보에서 20/20 PASS ·
   `clean-machine-runtime` 이 후보를 검증(F-07 폐쇄) · HEAD 의존 2개는 clean HEAD 재실행(2/2).

0-b. ~~**규율을 계약으로**~~ — **attempt-011 에서 완료했다**(`tests/test_cr14_fingerprint_scope_contract.py` 9건, 5건이 이빨).
   ⚠️ 만드는 행위 자체가 지문을 이동시켰다(`d4a42ab8…` → `cdfbbb96…`) — 만들고 나서 새 지문에서 20 gate 를 완주해야 한다(D-56 의 실증).

0-c. ~~**F-15 의 구조적 잔여**: `job.view` 를 취소 핸들러와 잡 스레드가 **잠금 없이** 쓴다~~ — **attempt-012 에서 완료했다**(F-16: `_Job.finalize()` 단일 지점(first-wins) + `note`/`snapshot`/`claim_cancel`, 회귀 8건·이빨 6건). 그 정리 과정에서 **F-17**(취소가 이벤트 루프를 1010.7ms 세웠다)이 드러나 함께 닫았다(6.8ms). 순서도 지켰다: 재현 → 수정 → 회귀(이빨) → 새 지문 `7ecb4fc2…` 에서 20 gate 완주.

0-d. **그 다음 — C14-03** 을 취소·중단 경로까지 포함해 실행한다(F-15 같은 결함은 전 구간 시나리오에서 드러난다).
   ▶ **완료(attempt-027·028)** — 취소·중단 경로에서 F-35 를 찾아 닫았고(위 `0-f-5`), 남은 절반인 **실 서버를 띄운 재시작 슬라이스**는 attempt-028 이 F-36 으로 닫았다.
   ※ 단 **`git.dirty: true` 는 ` M vault_data` 한 줄 때문**이다(F-13) — "미커밋 코드가 있다"로 읽지 말 것.
   ※ 릴리스 직전 **태그 SHA 에서 `clean-machine-runtime` 을 마지막으로 다시 돌려라**(R-3).

   ※ **두 lock 을 한쪽만 커밋하면** 설치 코드와 고지 코드가 갈라진다(F-03/F-06 이 같은 병이었다).
   특히 **`clean-machine-runtime`** — 그 gate 는 `git archive HEAD` 를 쓰므로 커밋 전 실행은 후보
   검증이 아니다(**F-07**). **release 문서를 커밋에 빠뜨리면 출하물의 고지가 다시 낡은 상태로 나간다**(F-03).
   ~~**F-03**~~ — **attempt-005 에서 닫혔다**(판독 체인 통일 + 미해결 집합 고정).
   ~~**F-08** `data/token_usage.json` 격리~~ — **attempt-004 에서 닫혔다**(같은 구조의 두 번째 경로).
   ~~**F-01**~~ — attempt-003 실측으로 GA blocker 에서 내려갔다(빌드는 멱등, §0-B).

1. ~~**F-02** `data/benchmark_results.json` 격리~~ — **attempt-003 에서 닫혔다.** 이제 gate 는
   트리를 되돌리지 않고 단일 코드 지문에서 완주한다(`pytest` 뒤 `git checkout` 불필요).
2. ~~**F-01**~~ 은 §0-B 에서 **GA blocker 에서 내려왔다** — 빌드는 멱등이고, 낡은 것은 HEAD 추적 번들이다.
   커밋에 갱신된 `dashboard_dist` 를 포함시키면 clean 해진다. 계속 추적할지 여부는 post-GA 정책 결정.
   **mermaid 승격 이후 HEAD 번들은 소스와 다른(취약한) 코드를 담으므로 HEAD 로 되돌리면 안 된다.**
3. ~~**CR-01~CR-14 커밋 → clean full SHA 확정 → 그 SHA 에서 20-gate 재실행**~~ — **attempt-010 에서 완료했다**(clean HEAD `5ccb938e` · 지문 `d4a42ab8…` · 20/20).
   ⚠️ **기록을 `README.md`·`tests/**` 에 쓰면 지문이 이동해 증거가 낡는다**(지문 예외는 `docs/`·`.omo/` **접두사뿐**) — 릴리스 기록은 `docs/**` 에 쓰고 **결과 수치는 그 attempt 의 `gate-report.json` 에서 직접 인용**한다(F-14 · D-51/D-54).
4. ~~**독립 코드/보안/QA 검토 배정 + 출시 책임자 지정**(C14-08)~~ — 이름 배정 + **출시 책임자 근거 있는 NO-GO 기록** 완료([CR14_C14_08_RELEASE_OWNER_VERDICT.md](./CR14_C14_08_RELEASE_OWNER_VERDICT.md)). 남은 것은 제3자 독립 검토(또는 겸직 위험 명시 수용)와 EX·C14-03/04/05/07.
5. **외부 조건(EX-01~06) 실행** — 담당은 **강병석**으로 채워졌다. 남은 것은 요청·승인·실측이지 이름 칸이 아니다.
6. ~~**F-06**(mermaid 경유 `uuid@9.0.1` moderate)~~ — **attempt-006 에서 닫혔다**(상류 선언 범위 안의
   override `11.1.1` + 두 lock 동기화 + 출하 번들 재빌드 + 회귀 8건). **게이트 범위의 기술 결함은 0건**이다.
7. ~~**F-09**(dev 도구 체인 취약)~~ — **attempt-007 에서 닫혔다**(양쪽 설정 override + 두 lock 일치 + 출하 경계
   계약 + 회귀 7건; 전체 트리 audit 0건). 단 **`qs` 편차는 상류 정확 고정을 넘긴 유일한 곳**이고, 그 편차의
   실행 검증은 아래 F-10 뒤로 미뤄졌다.
7-1. ~~**F-10**(변이 테스트 도구 미동작)~~ — **attempt-008 에서 닫혔다.** 원인은 러너 미설치가 아니라
   **탐색 경로**였다(pnpm 격리 레이아웃에서 자동 탐색이 core 의 설치 디렉터리만 본다) —
   `stryker.config.mjs` 의 `plugins` 명시 선언으로 해결했다. 오류 메시지에 끌려 **버전을 올리는 선택은
   결함을 고치지 않으면서 도구 체인을 움직여 두 lock 갈라짐 위험을 만든다**(D-40).
   ~~**F-09 의 `qs` 편차 실행 검증**~~ — 같은 attempt 에서 마쳤다(`6.15.1` 에서 실제 크래시 →
   `6.16.0` 정상). a) revert + `config/audit-exceptions.json` 등록을 고른다면 **그 크래시를 감수해야 한다**는
   점을 근거에 넣어라(D-41).
7-2. ~~**F-11a**(quick 스크립트가 선언 범위를 덮지 않음)~~ — **attempt-008 에서 닫혔다**(쉼표 단일 플래그).
   **F-11b 판단**(quick 범위 생존 변이 8건 — GA 차단 아님): `thresholds.break` 를 `high` 로 올려 CI 신호로
   삼을지, `reporters` 에 `json` 을 추가해 기계 판독 산출물을 만들지 결정한다(D-43·D-44).
8. 그 뒤 **CR-14 attempt-009**: 릴리스 번들을 `evidence_kind: release` + 채워진 `required_gates` 로
   만들고, C14-03(같은 bundle 실사용)·C14-04(실제 이전 artifact)·C14-05(8h soak·실 provider)를
   채워 GO/NO-GO 를 다시 판정한다.

F-04(mermaid)·F-05(docker OOM)는 attempt-002 에서, F-02(벤치마크 DB 격리)는 attempt-003 에서,
F-08(사용량 DB 격리)은 attempt-004 에서, F-03(release 라이선스 판독)은 attempt-005 에서,
F-06(uuid 하한·출하 바이트)은 attempt-006 에서, F-09(dev 도구 체인)는 attempt-007 에서,
F-10(도구 미동작)·F-11a(선언 범위 미커버리지)와 F-09 의 `qs` 실행 검증은 attempt-008 에서 폐쇄됐다.
위 순서에서 빠진 항목이 그것이다. **남은 기술 축은 F-07 하나다.**

## 7. 남은 결함 요약 (attempt-007 기준)

| ID | 내용 | 성질 | 상태 |
|---|---|---|---|
| ~~F-01~~ | `dashboard_dist` 가 추적 중인 빌드 산출물 | 릴리스 공학 → 정책 | **내려감(§0-B)** — 빌드는 멱등(실측). 남은 것은 post-GA 추적 정책 선택 |
| ~~F-07~~ | `clean-machine-runtime` 이 후보가 아니라 HEAD 를 검증 | 검증 범위 | **CLOSED (attempt-009)** — 후보 커밋 `54e4169a` 에서 재실행해 `ref: HEAD` 로 **후보 전체(3001 파일, 이전 2877 = 낡은 HEAD)** 를 아카이브·검증했다. **순서 규율은 남는다**: 태그 SHA 에서 마지막으로 다시 돌려야 한다(R-3) |
| ~~F-12~~ | **빌드 provenance 치킨-에그** — `buildStamp.ts` 가 `AGK_BUILD_ID` 기본값으로 `git short SHA` 를 써서 **커밋된 번들은 자기 커밋의 SHA 를 담을 수 없고**, 커밋 직후 `dashboard-build` 가 자산 22개를 교체해 커밋된 후보에서 단일 지문 20/20 을 완주할 수 없었다 | 릴리스 공학(구조) | **CLOSED (attempt-009)** — 해석 순서 `env → 커밋된 핀 → git → null` + 번들 재생성. **핀 ≠ HEAD 는 정상**(핀=번들을 만든 소스 리비전). F-01 의 "빌드 멱등"을 조건부로 정정 |
| ~~F-15~~ | **취소가 `completed` 로 기록된다** — API cancel 은 event set 과 **동시에** 프로세스를 종료하는데 watchdog 은 0.2초 폴링이라 사유를 세우기 전에 루프를 빠져나간다. 감독이 취소를 완료로 분류하고 잡 스레드가 `termination` 을 덮어써 취소 기록이 사라진다 | 제품 결함(TRN-02 분류) | **CLOSED (attempt-011)** — required gate 가 전체 suite 에서 1건 실패(`assert 'completed' == 'cancelled'`)했고 **단독은 5/5 통과**했다. flake 로 넘기지 않고 증인을 썼더니 A 3/3 · B **12/12** 로 재현됐다. 분류를 **관측이 아니라 사실**(`cancel_event` + 비정상 종료 코드)로 바꿔 닫았고, 정상 완료는 오분류하지 않는다. **잔여(R-4)**: `job.view` 무잠금 쓰기 구조 — **attempt-012 의 F-16 에서 닫혔다**(D-59~D-61) |
| ~~F-16~~ | **종결 기록에 소유자가 없어 나중 쫄이 이긴다** — 취소 라우트와 잡 스레드가 같은 `job.view` 를 잠금 없이 써서, 취소와 watchdog `timeout` 이 겹치면 API 는 `ok:true` 인데 뷰는 `timeout` 이었다(취소된 잡의 진행률까지 늦은 쫄이 100 으로 올렸다) | 제품 결함(잡 상태 기계) | **CLOSED (attempt-012)** — `_Job.finalize()` 단일 지점(**first-wins**, 먼저 확정한 쪽이 소유) + `note()`/`snapshot()`/`claim_cancel()`. 증인 A 에서 관측 종결 기록 **2개 → 1개**, 이빨 6/6(HTTP 회귀는 `assert 'timeout' == 'cancelled'`). attempt-011 R-4 의 승격 |
| ~~F-17~~ | **취소가 이벤트 루프를 세운다** — `async def` 라우트가 `terminate_process_group`(최대 2×grace 블로킹)을 루프에서 호출 | 제품 결함(가용성) | **CLOSED (attempt-012)** — 라우트를 `def` 로(FastAPI 스레드풀). 실측 1010.7ms → 6.8ms, 요청 소요는 ~1.05초로 불변 · 회귀 2건 |
| ~~F-14~~ | **기록이 같은 attempt 의 증거와 다른 수치를 인용했다** — attempt-009 기록의 `frontend 846 passed(80 files)` vs 그 보고서 `849 passed(81 files)` | 기록 정합(advisory) | **CLOSED (attempt-010)** — F-12 가 추가한 테스트 3건 이전 값이 넘어왔다. 이 저장소가 반복해 잡아 온 **'주장 ≠ 측정'** 병과 같은 모양이므로 수치를 정정하고 **그 attempt 의 `gate-report.json` 에서 직접 인용**하도록 못박았다(D-54). **부수 교훈**: 지문 예외는 `docs/`·`.omo/` **접두사뿐**이라 README·테스트를 고치는 행위 자체가 증거를 낡게 만든다(D-51) |
| F-13 | 중첩 저장소 `vault_data` 의 런타임 이벤트 로그가 계속 자라 부모 `git status` 가 **영구히 dirty** 다(gitlink SHA 자체는 불변) | repo 위생(advisory) | **OPEN** — 커밋에는 영향 없고 required gate 도 아니지만 `git.dirty: true` 가 보고서에 남아 'clean 후보' 판정을 흐린다. 선택지: untrack / vault 안에서 로그 ignore / dirty 판정 정교화(신호 약화라 비선호) — D-50 |
| ~~F-03~~ | release 문서 파이썬 라이선스 판독이 고지문/SBOM 으로 갈라짐(+마커 환경 의존) | 계약(REL-01) | **CLOSED (attempt-005)** — 판독 체인 통일, 회귀 17건. 고지문 미상 41 → 2건 |
| ~~F-06~~ | mermaid 경유 `uuid@9.0.1` moderate — 실측상 원인은 **의존 하한**(두 lock 모두 9.x)이었고 취약 서명(`buf`)에는 도달하지 않았다 | 잔여 위험 → 하한 | **CLOSED (attempt-006)** — 상류 선언 범위 안의 override `11.1.1` + 두 lock 동기화 + 출하 번들 재빌드 + 증인 C 축 + 회귀 8건. prod 취약 0건 |
| ~~F-10~~ | **mutation testing 도구가 동작하지 않았다** — `pnpm run stryker:quick` 이 `Cannot find TestRunner plugin "vitest"` 로 exit 1. 실측상 러너 미설치가 아니라 **탐색 경로** 문제(pnpm 격리 레이아웃에서 자동 탐색이 core 의 설치 디렉터리만 본다) | 도구 체인(게이트 아님) | **CLOSED (attempt-008)** — `stryker.config.mjs` 의 `plugins` 명시 선언 한 줄. dry-run 843 테스트 · quick exit 0. 미검증으로 남았던 **F-09 의 `qs` 편차 검증 창을 열었다** |
| ~~F-11a~~ | **`stryker:quick` 이 선언한 2개 파일 중 1개만 측정한다** — `--mutate` 반복이 마지막 값만 남겨 보고서에 `outputStore.ts` 만 들어가고도 **exit 0** 이었다(82.35% 는 절반 범위의 점수) | 측정 커버리지(게이트 아님) | **CLOSED (attempt-008)** — 쉼표 단일 플래그로 수정(두 파일 · 91.92%). F-07 과 같은 병(초록이 검증한 대상 ≠ 확인하려는 대상)이라 남기지 않고 고쳤다 |
| F-11b | quick 범위 **생존 변이 8건**(outputStore 6 · terminalStore 2) — 테스트가 잠지 못한 동작 차이 | 테스트 품질(advisory) | 임계값(`high 80`·`break 55`)을 통과하므로 **GA 차단 아님**(D-43). 91.92% 는 **quick 범위(2 파일)** 의 점수다 — 전체 `stryker`(10 파일)는 미실행이므로 프로젝트 전체 품질로 인용 금지 |
| ~~F-09~~ | dev 도구 체인 취약 — `eslint→js-yaml` high 1건 · `@stryker-mutator→qs` moderate 3건. 실측상 절반은 **또 두 lock 갈라짐**(pnpm 4.3.1 / npm 4.3.2)이었다 | 잔여 위험(게이트 범위 밖) → 하한 | **CLOSED (attempt-007)** — 양쪽 설정 override(`js-yaml 4.3.2`=상류 허용 범위, `qs 6.16.0`=기록된 편차) + 두 lock 일치 + dev 전용 경계 계약 + 회귀 7건. 전체 트리 audit 0건 |
| ~~F-02~~ | pytest 가 추적 파일 재작성 | 테스트 격리 | **CLOSED (attempt-003)** |
| ~~F-08~~ | 사용량 추적 기본 경로가 추적 파일 재작성(F-02 와 같은 구조의 두 번째 경로) | 테스트 격리 | **CLOSED (attempt-004)** |
| ~~F-04~~ | mermaid high | P1 | CLOSED (attempt-002) |
| ~~F-05~~ | docker-build tsc OOM | P1급 | CLOSED (attempt-002) |
