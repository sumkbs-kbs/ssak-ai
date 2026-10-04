---
title: Conversation fork consumer implementation evidence
date: 2026-10-03
tags: [qa, conversation, fork, dashboard]
---

# Conversation fork consumer

## Scope

- `dashboard/src/api/client.ts` sends only the fields accepted by
  `ConversationForkRequest` and `ConversationCompactRequest`; project identity and
  revision remain request headers.
- `dashboard/src/hooks/useConversationFork.ts` captures the active source session,
  project id, switch epoch, and source CAS revision. It fetches the fork's canonical
  history before `adoptForkedSession` activates a separate local session.
- The source session is not mutated by adoption. A stale result after selection,
  project switch, source deletion, a new stream, or compaction is not adopted.
- A CAS conflict refreshes only the still-active captured source session.

## Red evidence

Invocation:

```sh
cd dashboard
./node_modules/.bin/vitest run src/api/client.test.ts src/hooks/useConversationFork.test.tsx src/stores/__tests__/chatStore.revision.test.ts
```

Observed before implementation: Vitest exited `1`; the hook module did not exist and
the fork and compact API contract tests observed an extra `project_revision` JSON
field.

## Green evidence

The same invocation after implementation exited `0` with `3` test files and `41`
tests passing. The focused scenarios prove:

1. fork and compact POST bodies have only schema fields while identity headers include project revision;
2. canonical fork history is adopted with `tool` converted to the UI's `system` role;
3. source id, title, messages, and revision remain intact;
4. a late fork result after selecting another conversation is not adopted; and
5. returning from another conversation, a completed subsequent stream, Strict Mode
   effect replay, and unmount cannot adopt an old result; and
6. CAS conflict refreshes the captured active source to its authoritative revision.

## Integration note

`useConversationFork({ isCompacting, onStatus? })` returns
`forkActiveConversation`, `isForking`, and typed `status`. The chat surface owns the
visible button/command registration and passes its current compaction state.
If the server completed a fork after the client invalidated that attempt, the canonical
fork remains on the server; the client deliberately does not auto-delete it because
that would be an irreversible history operation.

At this checkpoint, `./node_modules/.bin/tsc -b --pretty false` is blocked by
concurrent, unrelated `ChatPage.tsx` queued-turn type changes and stale
`useTaskExecutionEvents` test expectations. It did not report a type error in the
new fork files. The root integration run must repeat typecheck after those parallel
edits settle.
