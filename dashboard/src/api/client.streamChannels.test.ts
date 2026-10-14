import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { streamChatCompletion } from './client';

function wireStream(chunks: readonly string[]): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

function stream(frames: readonly unknown[]): Response {
  return wireStream(frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`));
}

describe('chat stream status and final channels', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ['provider_protocol_error', 'incomplete_stream'],
    ['provider_protocol_error', 'invalid_stream'],
    ['provider_protocol_error', 'upstream_stream_error'],
    ['provider_transport_error', 'upstream_http_error'],
    ['provider_transport_error', 'provider_unavailable'],
    ['provider_transport_error', 'provider_timeout'],
  ])('reports %s/%s once after partial content without completing at EOF', async (type, code) => {
    // Given
    const message = 'The model provider failed.';
    fetchMock.mockResolvedValue(wireStream([
      `data: ${JSON.stringify({ choices: [{ delta: { content: 'partial' } }] })}\n\n`,
      `event: error\ndata: ${JSON.stringify({ error: { type, code, message } })}\n\n`,
    ]));
    const onChunk = vi.fn();
    const onError = vi.fn();
    const onDone = vi.fn();

    // When
    await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
      onChunk, onError, onDone,
    });

    // Then
    expect(onChunk.mock.calls).toEqual([['partial']]);
    expect(onError).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ message, type, code }));
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(Error);
    expect(onDone).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(['split', 'unterminated', 'trailing-success'])(
    'stops on a typed stream error with %s framing', async (framing) => {
      // Given
      const wire = 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        + 'event: error\ndata: {"error":{"type":"provider_protocol_error","code":"incomplete_stream","message":"Incomplete stream"}}';
      const chunks = framing === 'split'
        ? [...`${wire}\n\n`]
        : [framing === 'trailing-success'
          ? `${wire}\n\ndata: {"agk_final_content":"false success"}\n\ndata: [DONE]\n\n`
          : wire];
      fetchMock.mockResolvedValue(wireStream(chunks));
      const events: string[] = [];

      // When
      await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
        onChunk: (text) => events.push(`chunk:${text}`),
        onFinalContent: (text) => events.push(`final:${text}`),
        onDone: () => events.push('done'),
        onError: (error) => events.push(`error:${error.message}`),
      });

      // Then
      expect(events).toEqual(['chunk:partial', 'error:Incomplete stream']);
    },
  );

  it.each([
    'error',
    null,
    { type: 'other_error', code: 'incomplete_stream', message: 'not recognized' },
    { type: 'provider_protocol_error', code: 'other_code', message: 'not recognized' },
    { type: 'provider_protocol_error', code: 'incomplete_stream', message: 42 },
    { type: 'provider_protocol_error', code: 'incomplete_stream', message: '' },
    { type: 'provider_protocol_error', message: 'missing code' },
  ])('keeps legitimate content when an unrelated or malformed error field is %j', async (error) => {
    // Given
    fetchMock.mockResolvedValue(wireStream([
      `data: ${JSON.stringify({ error, choices: [{ delta: { content: 'error: incomplete_stream' } }] })}\n\n`,
      'data: [DONE]\n\n',
    ]));
    const events: string[] = [];

    // When
    await streamChatCompletion({ model: 'fixture', messages: [], stream: true }, {
      onChunk: (text) => events.push(`chunk:${text}`),
      onDone: () => events.push('done'),
      onError: (failure) => events.push(`error:${failure.message}`),
    });

    // Then
    expect(events).toEqual(['chunk:error: incomplete_stream', 'done']);
  });

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
