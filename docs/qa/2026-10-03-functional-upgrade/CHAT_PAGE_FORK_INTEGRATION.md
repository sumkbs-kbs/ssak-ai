---
title: ChatPage conversation fork integration evidence
date: 2026-10-03
tags: [qa, chat, conversation, fork]
---

# ChatPage conversation fork integration

## Surface scenarios

`dashboard/src/components/Chat/__tests__/ChatPageFork.test.tsx` drives the actual
`ChatPage`, hook, store, native top-bar button, and browser command event. It proves:

1. native fork action adopts the canonical fork history, converts a tool message to
   the visible system role, and preserves the original session's id, title, history,
   and revision;
2. `agk:conversation-fork` takes the same hook/store adoption path;
3. while a deferred fork is pending, draft text survives and Enter, send, and compact
   cannot start a competing action;
4. an empty conversation disables the native fork button; and
5. streaming disables the native button and the command event cannot start a fork.

## Direct verification

From `dashboard/`:

```sh
./node_modules/.bin/vitest run src/components/Chat/__tests__/ChatPageFork.test.tsx src/components/Chat/__tests__/ChatPageComposer.test.tsx src/hooks/useConversationFork.test.tsx src/api/client.test.ts
./node_modules/.bin/tsc -b --pretty false
```

Observed results: Vitest exited `0` with `4` test files and `48` tests passing;
TypeScript exited `0` with no diagnostics.
