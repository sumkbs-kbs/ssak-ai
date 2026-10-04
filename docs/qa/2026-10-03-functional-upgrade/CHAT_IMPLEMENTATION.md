---
title: Conversation run ownership implementation evidence
date: 2026-10-03
tags: [qa, conversation, streaming, queue, dashboard]
---

# Conversation run ownership

## Scope

- `ChatPage.tsx` binds every asynchronous run callback to one captured conversation,
  project, project epoch, and monotonic run identity. Session navigation and Stop
  invalidate that identity synchronously through the Zustand subscription before
  abort completion can race a later run.
- History refresh, conflict recovery, adaptive completion, compaction, and component
  unmount use the same transition-generation rule. An A-to-B-to-A transition cannot
  make an older A operation current again.
- SSE chunks update the one assistant message as they arrive. The transcript follows
  output only while the reader is near its end and otherwise exposes the named
  `최신 응답 보기` action.
- Queued turns are immutable in-memory records containing their text, captured image
  bytes, owning session, and project scope. Reorder, edit, delete, and clear operate
  on the whole record. Base64 bytes are not persisted or rendered.
- Adaptive mode rejects an attached turn before either its draft or attachment is
  removed.

## Red evidence

Invocation:

```sh
cd dashboard
./node_modules/.bin/vitest run src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx
```

Before implementation Vitest exited `1`: three of four initial regressions failed.
Two SSE chunks were absent from the visible transcript, switching conversations did
not abort ownership, and a stopped stream's late finalization set the new run to
idle. The attachment assertions were then strengthened with two queued images and
a full-record reorder before the implementation was accepted.

## Green evidence

Invocation:

```sh
cd dashboard
./node_modules/.bin/vitest run \
  src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx \
  src/components/Chat/__tests__/ChatPageComposer.test.tsx \
  src/components/Chat/__tests__/ChatPageHydration.test.tsx \
  src/components/Chat/__tests__/QueuedMessagesCard.test.tsx
./node_modules/.bin/tsc -b --pretty false
```

Binary result: Vitest exited `0` with `4` files and `24` tests passing; TypeScript
exited `0` with no diagnostics.

The programming skill's optional TypeScript 7 AST audit script exited `2` because
this dashboard's installed TypeScript 5 package has no `typescript/unstable/*`
entrypoint. Dependencies were not changed. A scoped forbidden-pattern scan over the
three changed TypeScript paths returned no matches; `tsc` remains the typed gate.

The focused scenarios prove these observable boundaries:

1. two chunks appear before completion in exactly one assistant message;
2. A-to-B-to-A navigation, deletion, and new-conversation creation reject late
   chunks and finalizers without resurrecting or altering another conversation;
3. Stop followed by a new send leaves the new run streaming when the stopped
   request resolves late;
4. two queued images keep their own bytes after record reordering, while single
   delete and clear prevent removed records from being sent;
5. stale compaction and server-history results are ignored after navigating away
   and back;
6. scrolling away preserves the reading position and exposes an operable latest
   response action;
7. existing IME, initial hydration, and queue-card interaction regressions remain
   green.

## Pre-integration history race repair

A focused deferred-history regression was added after integration review. Before the
repair, a history request triggered by the first locally-created conversation could
complete after SSE published revision 1 and replace it with revision 0; the targeted
suite exited `1` with `expected 0 to be 1` at the revision assertion.

The repair prevents history refresh from starting while a run is streaming, requires
the captured source revision to remain current after the await, and resets
`currentAssistantContent` when each run starts. A second deferred test proves an idle
revision-2 response cannot replace a revision-3 snapshot even when session and project
identity remain unchanged.

Fresh current-tree invocation after root fork wiring:

```sh
cd dashboard
./node_modules/.bin/vitest run \
  src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx \
  src/components/Chat/__tests__/ChatPageComposer.test.tsx \
  src/components/Chat/__tests__/ChatPageHydration.test.tsx \
  src/components/Chat/__tests__/QueuedMessagesCard.test.tsx
./node_modules/.bin/tsc -b --pretty false
```

Binary result: Vitest exited `0` with `4` files and `26` tests passing; TypeScript
exited `0` with no diagnostics. Scoped `git diff --check` also exited `0`.

## Failed-parent queue gate

A deferred regression then reproduced a dependent-turn ordering bug: after the
parent stream reported an error, completion unconditionally removed the next queued
record and issued a second request. The targeted test exited `1` with
`expected "streamChatCompletion" to be called 1 times, but got 2 times`.

Queue continuation now requires successful parent completion. Generic SSE errors,
conversation-revision conflicts, and Adaptive failures leave every dependent record
in the queue and show an explicit edit-or-resend notice. The attachment regression
opens the retained record in the composer and verifies both its prompt and captured
`dependent.png` bytes remain owned by that turn.

Fresh scoped invocation on the shared tree after the conversation-fork header wiring:

```sh
cd dashboard
./node_modules/.bin/vitest run \
  src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx \
  src/components/Chat/__tests__/ChatPageComposer.test.tsx \
  src/components/Chat/__tests__/ChatPageHydration.test.tsx \
  src/components/Chat/__tests__/QueuedMessagesCard.test.tsx
./node_modules/.bin/tsc -b --pretty false
```

Binary result: Vitest exited `0` with `4` files and `29` tests passing; TypeScript
exited `0` with no diagnostics.

## Changed paths

- `dashboard/src/components/Chat/ChatPage.tsx`
- `dashboard/src/components/Chat/chatRunOwnership.ts`
- `dashboard/src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx`

Full dashboard suite, production build, and live-browser interaction evidence remain
owned by the root integration pass.
