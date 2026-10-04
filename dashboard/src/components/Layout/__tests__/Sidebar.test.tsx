import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from '../Sidebar';
import { useChatStore, type ChatSession } from '../../../stores/chatStore';
import { useProjectStore } from '../../../stores/projectStore';
import { useGitStore } from '../../../stores/gitStore';
import { useUiStore } from '../../../stores/uiStore';
import { useGlobalCommandPalette } from '../../../hooks/useGlobalCommandPalette';
import SystemTelemetricsBar from '../SystemTelemetricsBar';

const chatInitial = useChatStore.getState();
const projectInitial = useProjectStore.getState();
const gitInitial = useGitStore.getState();
const uiInitial = useUiStore.getState();
const session = { id: 'conversation-one', title: '테스트 대화', updatedAt: '2026-10-03', messages: [], conversationRevision: 0 } satisfies ChatSession;

function setCompactViewport(): void {
  vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
    matches: query === '(max-width: 1023px)', media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
    removeEventListener: vi.fn(), dispatchEvent: () => false,
  }));
}

function NavigationHarness() {
  useGlobalCommandPalette();
  return <div><SystemTelemetricsBar /><Sidebar toggleTerminal={vi.fn()} /><main><button type="button">작업 영역</button></main></div>;
}

function renderSidebar(): void {
  render(<MemoryRouter initialEntries={['/chat']}><NavigationHarness /></MemoryRouter>);
}

beforeEach(() => {
  useChatStore.setState({ ...chatInitial, sessions: [session], activeSessionId: session.id });
  useProjectStore.setState({ ...projectInitial, projects: [], hydrateFromServer: vi.fn().mockResolvedValue(undefined) });
  useGitStore.setState({ ...gitInitial, fetchStatus: vi.fn().mockResolvedValue(undefined) });
  useUiStore.setState({ commandPaletteVisible: false, folderBrowserVisible: false });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useChatStore.setState(chatInitial);
  useProjectStore.setState(projectInitial);
  useGitStore.setState(gitInitial);
  useUiStore.setState(uiInitial);
});

describe('Workspace navigation', () => {
  it('exposes each genuine destination when the desktop navigation is rendered', () => {
    // Given
    renderSidebar();
    // When
    fireEvent.click(screen.getByText('더 보기'));
    // Then
    const destinations = screen.getAllByRole('link').map(link => link.getAttribute('href'));
    expect(destinations).toEqual(expect.arrayContaining(['/chat', '/studio', '/models', '/start', '/wiki', '/agent', '/skills', '/data-extraction', '/git', '/history', '/plugins', '/mutation', '/settings']));
  });

  it('shows a conversation once with native selection and named actions', () => {
    // Given
    // When
    renderSidebar();
    // Then
    expect(screen.getAllByText(session.title)).toHaveLength(1);
    expect(screen.getByRole('button', { name: session.title })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: `${session.title} 제목 수정` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${session.title} 삭제` })).toBeInTheDocument();
  });

  it('returns focus to the opener when Escape closes compact navigation', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    const opener = screen.getByRole('button', { name: '탐색 메뉴 열기' });
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    // When
    fireEvent.keyDown(document, { key: 'Escape' });
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(screen.getByRole('main')).not.toHaveAttribute('inert');
  });

  it('traps Tab inside compact navigation while the workspace is inert', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: '탐색 메뉴 열기' }));
    const dialog = screen.getByRole('dialog', { name: 'SSAK-AI 탐색' });
    const first = within(dialog).getByRole('button', { name: '탐색 메뉴 닫기' });
    const last = within(dialog).getByRole('button', { name: '터미널 열기 또는 닫기' });
    await waitFor(() => expect(first).toHaveFocus());
    last.focus();
    // When
    fireEvent.keyDown(document, { key: 'Tab' });
    // Then
    expect(first).toHaveFocus();
    expect(document.querySelector('main')).toHaveAttribute('inert');
  });

  it('dismisses compact navigation after selecting a destination', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    const opener = screen.getByRole('button', { name: '탐색 메뉴 열기' });
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    // When
    fireEvent.click(screen.getByRole('link', { name: '모델' }));
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('closes the drawer after selecting a conversation on the current chat route', async () => {
    // Given
    setCompactViewport();
    useChatStore.setState({ activeSessionId: null });
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: '탐색 메뉴 열기' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    // When
    fireEvent.click(screen.getByRole('button', { name: session.title }));
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(useChatStore.getState().activeSessionId).toBe(session.id);
  });

  it('returns focus to the opener when the compact drawer backdrop is clicked', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    const opener = screen.getByRole('button', { name: '탐색 메뉴 열기' });
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    const backdrop = document.querySelector('.workspace-nav-backdrop');
    if (backdrop === null) throw new Error('Navigation backdrop is missing');
    // When
    fireEvent.click(backdrop);
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('releases the drawer modal when the global command palette shortcut is used', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: '탐색 메뉴 열기' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    // When
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    // Then
    expect(useUiStore.getState().commandPaletteVisible).toBe(true);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('main')).not.toHaveAttribute('inert');
  });

  it('closes the drawer with Escape while an open status disclosure is inert behind it', async () => {
    // Given
    setCompactViewport();
    renderSidebar();
    const summary = screen.getByLabelText('서버 연결 및 시스템 지표');
    fireEvent.click(summary);
    await waitFor(() => expect(summary.closest('details')).toHaveAttribute('open'));
    fireEvent.click(screen.getByRole('button', { name: '탐색 메뉴 열기' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '탐색 메뉴 닫기' })).toHaveFocus());
    // When
    fireEvent.keyDown(document, { key: 'Escape' });
    // Then
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(summary.closest('details')).toHaveAttribute('open');
  });
});
