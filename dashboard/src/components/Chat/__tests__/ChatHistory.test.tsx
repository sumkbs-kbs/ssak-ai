import { useEffect, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ChatHistory from '../ChatHistory';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useUiStore } from '../../../stores/uiStore';
import KeyboardShortcutsModal from '../../UI/KeyboardShortcutsModal';

const chatInitial = useChatStore.getState();
const uiInitial = useUiStore.getState();
const session = { id: 'history-one', title: '저장된 대화', updatedAt: '2026-10-03T00:00:00Z', messages: [], conversationRevision: 4 } satisfies ChatSession;

function HistoryHarness() {
  const [visible, setVisible] = useState(false);
  const [guideVisible, setGuideVisible] = useState(false);
  useEffect(() => {
    const openGuide = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === '/') setGuideVisible(true);
    };
    window.addEventListener('keydown', openGuide);
    return () => window.removeEventListener('keydown', openGuide);
  }, []);
  return <div><button type="button" onClick={() => setVisible(true)}>대화 기록 열기</button><main>작업 영역</main><ChatHistory visible={visible} onClose={() => setVisible(false)} /><KeyboardShortcutsModal visible={guideVisible} onClose={() => setGuideVisible(false)} /></div>;
}

async function openHistory(): Promise<HTMLElement> {
  const opener = screen.getByRole('button', { name: '대화 기록 열기' });
  opener.focus();
  fireEvent.click(opener);
  await waitFor(() => expect(screen.getByRole('button', { name: '대화 기록 닫기' })).toHaveFocus());
  return opener;
}

beforeEach(() => {
  useChatStore.setState({ ...chatInitial, sessions: [session], activeSessionId: session.id, activeSession: session });
  useUiStore.setState({ commandPaletteVisible: false, folderBrowserVisible: false });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useChatStore.setState(chatInitial);
  useUiStore.setState(uiInitial);
});

describe('Conversation history drawer', () => {
  it('returns focus to its opener when Escape dismisses the labelled drawer', async () => {
    // Given
    render(<HistoryHarness />);
    const opener = await openHistory();
    expect(screen.getByRole('dialog', { name: '대화 기록' })).toHaveAttribute('aria-modal', 'true');
    // When
    fireEvent.keyDown(document, { key: 'Escape' });
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(screen.getByRole('main')).not.toHaveAttribute('inert');
  });

  it('selects the existing conversation through a native button and closes', async () => {
    // Given
    useChatStore.setState({ activeSessionId: null, activeSession: null });
    render(<HistoryHarness />);
    await openHistory();
    // When
    fireEvent.click(screen.getByRole('button', { name: session.title }));
    // Then
    expect(useChatStore.getState().activeSessionId).toBe(session.id);
    expect(useChatStore.getState().conversationRevision).toBe(session.conversationRevision);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('cancels title editing with Escape before dismissing the drawer', async () => {
    // Given
    render(<HistoryHarness />);
    await openHistory();
    fireEvent.click(screen.getByRole('button', { name: `${session.title} 제목 수정` }));
    const input = screen.getByRole('textbox', { name: '대화 제목' });
    fireEvent.change(input, { target: { value: '취소할 제목' } });
    // When
    fireEvent.keyDown(input, { key: 'Escape' });
    // Then
    expect(useChatStore.getState().sessions[0]?.title).toBe(session.title);
    expect(screen.getByRole('dialog', { name: '대화 기록' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('wraps keyboard focus inside the drawer', async () => {
    // Given
    render(<HistoryHarness />);
    await openHistory();
    const dialog = screen.getByRole('dialog', { name: '대화 기록' });
    const last = within(dialog).getByRole('button', { name: `${session.title} 삭제` });
    last.focus();
    // When
    fireEvent.keyDown(document, { key: 'Tab' });
    // Then
    expect(within(dialog).getByRole('button', { name: '대화 기록 닫기' })).toHaveFocus();
  });

  it('releases history focus before the shortcut guide opens', async () => {
    // Given
    render(<HistoryHarness />);
    const opener = await openHistory();
    fireEvent.keyDown(document, { key: '/', metaKey: true });
    const guide = screen.getByRole('dialog', { name: '키보드 단축키' });
    const close = within(guide).getByRole('button', { name: '키보드 단축키 대화상자 닫기' });
    await waitFor(() => expect(close).toHaveFocus());
    // When
    const defaultAllowed = fireEvent.keyDown(close, { key: 'Tab' });
    // Then
    expect(screen.queryByRole('dialog', { name: '대화 기록' })).toBeNull();
    expect(guide.closest('[inert]')).toBeNull();
    expect(defaultAllowed).toBe(false);
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(screen.getByRole('main')).not.toHaveAttribute('inert');
  });
});
