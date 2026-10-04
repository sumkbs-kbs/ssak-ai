import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, createEvent, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChatPage from '../ChatPage';
import * as client from '../../../api/client';
import { useChatStore } from '../../../stores/chatStore';
import { useUiStore } from '../../../stores/uiStore';

async function renderDraft() {
  await act(async () => { render(<MemoryRouter><ChatPage /></MemoryRouter>); });
  const textarea = screen.getByRole('textbox', { name: '메시지 입력' });
  fireEvent.change(textarea, { target: { value: '한글 입력' } });
  return textarea;
}

describe('ChatPage composer keyboard submission', () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({ toasts: [] });
    useChatStore.setState({
      messages: [],
      sessions: [],
      activeSession: null,
      activeSessionId: null,
      isStreaming: false,
      isAdaptiveMode: false,
    });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    vi.spyOn(client, 'streamChatCompletion').mockResolvedValue(undefined);
    vi.spyOn(client, 'fetchModels').mockResolvedValue([]);
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({ ok: true, total: 0, models: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    useChatStore.setState({ messages: [], isStreaming: false });
    localStorage.clear();
  });

  it('preserves the draft when Enter confirms an active IME composition', async () => {
    // Given
    const textarea = await renderDraft();
    const event = createEvent.keyDown(textarea, { key: 'Enter', isComposing: true });
    // When
    fireEvent(textarea, event);
    // Then
    expect(client.streamChatCompletion).not.toHaveBeenCalled();
    expect(textarea).toHaveValue('한글 입력');
    expect(event.defaultPrevented).toBe(false);
  });

  it('preserves the draft when an IME reports legacy key code 229', async () => {
    // Given
    const textarea = await renderDraft();
    const event = createEvent.keyDown(textarea, { key: 'Enter', keyCode: 229 });
    // When
    fireEvent(textarea, event);
    // Then
    expect(client.streamChatCompletion).not.toHaveBeenCalled();
    expect(textarea).toHaveValue('한글 입력');
    expect(event.defaultPrevented).toBe(false);
  });

  it('allows the native newline action when Shift+Enter is pressed', async () => {
    // Given
    const textarea = await renderDraft();
    const event = createEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    // When
    fireEvent(textarea, event);
    // Then
    expect(client.streamChatCompletion).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it('submits the draft once when plain Enter is pressed', async () => {
    // Given
    const textarea = await renderDraft();
    const event = createEvent.keyDown(textarea, { key: 'Enter' });
    // When
    fireEvent(textarea, event);
    // Then
    await waitFor(() => expect(client.streamChatCompletion).toHaveBeenCalledTimes(1));
    expect(client.streamChatCompletion).toHaveBeenCalledWith(
      expect.objectContaining({ new_turn: { role: 'user', content: '한글 입력' } }),
      expect.any(Object),
      expect.any(AbortSignal),
    );
    expect(event.defaultPrevented).toBe(true);
  });

  it('preserves read-only mode and reports an error when the permission request fails', async () => {
    // Given
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => (
      init?.method === 'POST'
        ? new Response('{}', { status: 503 })
        : new Response(JSON.stringify({ mode: 'read_only', label: '읽기 전용' }), { status: 200 })
    )));
    await renderDraft();
    fireEvent.click(screen.getByRole('button', { name: '읽기 전용', expanded: false }));
    // When
    fireEvent.click(screen.getByRole('button', { name: '전체 액세스' }));
    // Then
    await waitFor(() => expect(screen.getByRole('button', { name: '읽기 전용', expanded: false })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '전체 액세스' })).not.toBeInTheDocument();
    expect(useUiStore.getState().toasts.some((toast) => toast.type === 'error')).toBe(true);
  });
});
