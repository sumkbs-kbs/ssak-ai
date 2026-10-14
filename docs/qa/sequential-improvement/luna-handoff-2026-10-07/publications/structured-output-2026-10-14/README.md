---
title: 구조화 출력 기능 및 후속 증거 게시 범위
date: 2026-10-14
tags: [publication, structured-output, evidence]
---

기능 커밋 d3c107b04624ec2a655f5e3dee19e58c8856bab6은 HEAD agent-stream 구현을 보존하며 구조화 출력 소유 hunk만 포함한다. 필수 이미지 content 보존 prerequisite와 PNG b64 fixture를 명시적으로 포함했다. 다른 agent streaming refactor/helper와 config/model_registry 변경은 제외했다.

Clean candidate v3에서79개(집중36+translator43) 통과, 정적4개 및 커밋 hook전체mypy571source가 통과했다. 처음 metadata fixture 누락 실패와 parsed 명시 타입 주석 누락 hook실패는 별도 원문/진단과 함께 보존했다. 새 체크는 후보 소스가 바뀐 데 따른 검증이며 실제 model/HTTP는 실행하지 않았다.

게시용 manifest는 전체 로컬 봉인 inventory 중 Git에 게시하는 subset을 식별한다. 실제 ephemeral auth material, runtime DB/lock/cache, nested Git state, local symlink 및 ignored files는 게시하지 않으며 원본은 로컬에 보존한다. Full sealed manifests의 제외 파일은 이 게시 manifest로 확인한다.

공용 STATUS/tasks 최신절은 별도 상태 커밋에 포함한다. 옛 JSON 필드와 STATUS 본문은 역사snapshot으로 보존하고, 유실 JSONL 원장을 복원했다고 주장하지 않는다. 기존 staged97개는 이 게시 범위에 포함하지 않는다.
