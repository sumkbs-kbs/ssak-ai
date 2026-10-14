import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { streamChatCompletion } from './client';

function stream(frames: readonly unknown[]): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(`data: ${JSON.stringify(frame)}\n\n`));
      controller.close();
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('chat stream status and final channels', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('delivers status through its own handler without appending answer content', async () => {
    // Given
    fetchMock.mockResolvedValue(stream([{ agk_status: { text: 'running-stage' } }]));
    const events: string[] = [];

    // When
    await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
      onChunk: (text) => events.push(`chunk:${text}`),
      onStatus: (text) => events.push(`status:${text}`),
      onDone: () => events.push('done'),
      onError: (error) => events.push(`error:${error.message}`),
    });

    // Then
    expect(events).toEqual(['status:running-stage', 'done']);
  });

  it('delivers an authoritative final independently while preserving legacy delta compatibility', async () => {
    // Given
    fetchMock.mockResolvedValue(stream([
      { choices: [{ delta: { content: 'draft' } }] },
      { agk_final_content: '{"ok":true}' },
    ]));
    const events: string[] = [];

    // When
    await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
      onChunk: (text) => events.push(`chunk:${text}`),
      onFinalContent: (text) => events.push(`final:${text}`),
      onDone: () => events.push('done'),
      onError: (error) => events.push(`error:${error.message}`),
    });

    // Then
    expect(events).toEqual(['chunk:draft', 'final:{"ok":true}', 'done']);
  });

  it.each([
    { agk_status: null },
    { agk_status: { text: 42 } },
    { agk_status: {} },
    { agk_final_content: null },
    { agk_final_content: { text: 'invalid' } },
    { agk_final_content: 42 },
  ])('ignores malformed channel data %j', async (frame) => {
    // Given
    fetchMock.mockResolvedValue(stream([frame]));
    const events: string[] = [];

    // When
    await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
      onChunk: (text) => events.push(`chunk:${text}`),
      onStatus: (text) => events.push(`status:${text}`),
      onFinalContent: (text) => events.push(`final:${text}`),
      onDone: () => events.push('done'),
      onError: (error) => events.push(`error:${error.message}`),
    });

    // Then
    expect(events).toEqual(['done']);
  });
});
