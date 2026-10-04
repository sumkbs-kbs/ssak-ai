import { useEffect, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { InspectionFrame } from '../InspectionFrame';
import CommandPalette from '../../UI/CommandPalette';
import KeyboardShortcutsModal from '../../UI/KeyboardShortcutsModal';
import { useGlobalCommandPalette } from '../../../hooks/useGlobalCommandPalette';
import { useUiStore } from '../../../stores/uiStore';
import { isMonacoFocused } from '../../../utils/domHelpers';

const commandSources = vi.hoisted(() => ({ commands: [] }));
vi.mock('../../../plugin/PluginManager', () => ({ usePluginCommands: () => commandSources.commands }));
vi.mock('../../../features/command-palette/commandRegistry', () => ({
  BUILTIN_COMMANDS: commandSources.commands,
  CommandSearchError: class CommandSearchError extends Error {},
  filterPaletteCommands: () => commandSources.commands,
  searchNoteCommands: async () => commandSources.commands,
}));

function ForegroundHarness() {
  const [open, setOpen] = useState(false);
  const [guideVisible, setGuideVisible] = useState(false);
  useGlobalCommandPalette();

  useEffect(() => {
    const handleGuide = (event: KeyboardEvent) => {
      if ((event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !isMonacoFocused()) ||
          ((event.metaKey || event.ctrlKey) && event.key === '/')) {
        event.preventDefault();
        setGuideVisible((visible) => !visible);
      }
    };
    window.addEventListener('keydown', handleGuide);
    return () => window.removeEventListener('keydown', handleGuide);
  }, []);

  return (
    <div>
      <main data-testid="background"><button onClick={() => setOpen(true)}>검사 열기</button></main>
      <InspectionFrame open={open} tab="env" onTabChange={() => undefined} onClose={() => setOpen(false)} changeCount={0}>
        <input aria-label="검사 입력" />
        <div className="monaco-editor"><textarea aria-label="Monaco 입력" /></div>
      </InspectionFrame>
      <CommandPalette />
      <KeyboardShortcutsModal visible={guideVisible} onClose={() => setGuideVisible(false)} />
    </div>
  );
}

beforeEach(() => {
  const media = window.matchMedia('(max-width: 1279px)');
  vi.spyOn(window, 'matchMedia').mockReturnValue({ ...media, matches: true });
  useUiStore.setState({ commandPaletteVisible: false, folderBrowserVisible: false });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useUiStore.setState({ commandPaletteVisible: false, folderBrowserVisible: false });
});

async function openInspector(): Promise<HTMLButtonElement> {
  render(<ForegroundHarness />);
  const opener = screen.getByRole('button', { name: '검사 열기' });
  opener.focus();
  fireEvent.click(opener);
  await waitFor(() => { expect(screen.getByRole('button', { name: '패널 닫기' })).toHaveFocus(); });
  if (!(opener instanceof HTMLButtonElement)) throw new TypeError('Expected an inspector opener button');
  return opener;
}

describe('InspectionFrame foreground handoff', () => {
  it('releases its modal before the actual command palette takes focus', async () => {
    // Given
    const opener = await openInspector();

    // When
    fireEvent.keyDown(screen.getByRole('button', { name: '패널 닫기' }), { key: 'k', metaKey: true });

    // Then
    await waitFor(() => { expect(screen.getByRole('combobox')).toHaveFocus(); });
    expect(screen.queryByRole('dialog', { name: '검사' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '명령 팔레트' }).closest('[inert]')).toBeNull();
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Tab' });
    expect(screen.getByRole('combobox')).toHaveFocus();
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    await waitFor(() => { expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); });
    expect(screen.getByTestId('background')).not.toHaveAttribute('inert');
    expect(opener).toHaveFocus();
  });

  it.each([
    { key: '?', metaKey: false, ctrlKey: false },
    { key: '/', metaKey: true, ctrlKey: false },
    { key: '/', metaKey: false, ctrlKey: true },
  ])('releases its modal for the actual shortcut guide on $key', async (shortcut) => {
    // Given
    const opener = await openInspector();

    // When
    fireEvent.keyDown(screen.getByRole('button', { name: '패널 닫기' }), shortcut);

    // Then
    const guide = screen.getByRole('dialog', { name: '키보드 단축키' });
    expect(screen.queryByRole('dialog', { name: '검사' })).not.toBeInTheDocument();
    expect(guide.closest('[inert]')).toBeNull();
    const close = screen.getByRole('button', { name: '키보드 단축키 대화상자 닫기' });
    await waitFor(() => expect(close).toHaveFocus());
    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    fireEvent(close, tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('background')).not.toHaveAttribute('inert');
    expect(opener).toHaveFocus();
  });

  it('closes the compact inspector when the folder browser becomes visible', async () => {
    // Given
    await openInspector();

    // When
    act(() => { useUiStore.setState({ folderBrowserVisible: true }); });

    // Then
    expect(screen.queryByRole('dialog', { name: '검사' })).not.toBeInTheDocument();
    expect(screen.getByTestId('background')).not.toHaveAttribute('inert');
  });

  it.each([
    { key: 'k', metaKey: true },
    { key: '?', metaKey: false },
  ])('keeps Monaco shortcuts inside the compact inspector for $key', async (shortcut) => {
    // Given
    await openInspector();
    const editor = screen.getByRole('textbox', { name: 'Monaco 입력' });
    editor.focus();

    // When
    fireEvent.keyDown(editor, shortcut);

    // Then
    expect(screen.getByRole('dialog', { name: '검사' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '명령 팔레트' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '키보드 단축키' })).not.toBeInTheDocument();
    expect(editor).toHaveFocus();
  });

  it('hands Ctrl slash from Monaco to the guide exactly as App does', async () => {
    // Given
    await openInspector();
    const editor = screen.getByRole('textbox', { name: 'Monaco 입력' });
    editor.focus();

    // When
    fireEvent.keyDown(editor, { key: '/', ctrlKey: true });

    // Then
    expect(screen.queryByRole('dialog', { name: '검사' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '키보드 단축키' }).closest('[inert]')).toBeNull();
  });
});
