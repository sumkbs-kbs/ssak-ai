import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EnvironmentPanel, type EnvPanelTab } from '../EnvironmentPanel';
import { useActivityStore } from '../../../stores/activityStore';

function setCompact(matches: boolean): void {
  const media = window.matchMedia('(max-width: 1279px)');
  vi.spyOn(window, 'matchMedia').mockReturnValue({ ...media, matches });
}

function PanelHarness() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<EnvPanelTab>('env');
  return (
    <div>
      <div data-testid="background"><button onClick={() => setOpen(true)}>검사 열기</button></div>
      <EnvironmentPanel
        open={open}
        tab={tab}
        onTabChange={setTab}
        onClose={() => setOpen(false)}
        branch="main"
        mcpServers={[]}
        editorContent={<div>Editor content</div>}
        changesContent={<button>Change content</button>}
      />
    </div>
  );
}

beforeEach(() => { useActivityStore.getState().clear(); });
afterEach(() => { vi.restoreAllMocks(); });

describe('EnvironmentPanel compact modal', () => {
  it('focuses its close button and restores focus after Escape', async () => {
    // Given
    setCompact(true);
    render(<PanelHarness />);
    const opener = screen.getByRole('button', { name: '검사 열기' });
    opener.focus();

    // When
    fireEvent.click(opener);
    await waitFor(() => { expect(screen.getByRole('button', { name: '패널 닫기' })).toHaveFocus(); });

    // Then
    expect(screen.getByRole('dialog', { name: '검사' })).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: '패널 닫기' })).toHaveFocus();
    expect(screen.getByTestId('background')).toHaveAttribute('inert');
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    expect(screen.getByTestId('background')).not.toHaveAttribute('inert');
  });

  it('wraps Tab focus within the compact panel', async () => {
    // Given
    setCompact(true);
    render(<PanelHarness />);
    fireEvent.click(screen.getByRole('button', { name: '검사 열기' }));
    await waitFor(() => { expect(screen.getByRole('button', { name: '패널 닫기' })).toHaveFocus(); });
    const closeButton = screen.getByRole('button', { name: '패널 닫기' });
    const errorsToggle = screen.getByRole('button', { name: /에러 \/ 경고/ });
    errorsToggle.focus();

    // When
    fireEvent.keyDown(errorsToggle, { key: 'Tab' });

    // Then
    expect(closeButton).toHaveFocus();
    fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey: true });
    expect(errorsToggle).toHaveFocus();
  });
});

describe('EnvironmentPanel desktop tabs', () => {
  it('keeps the desktop rail nonmodal and the background interactive', () => {
    // Given
    setCompact(false);
    render(<PanelHarness />);

    // When
    fireEvent.click(screen.getByRole('button', { name: '검사 열기' }));

    // Then
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: '검사' })).toBeInTheDocument();
    expect(screen.getByTestId('background')).not.toHaveAttribute('inert');
  });

  it('selects and focuses a tab with arrow keys and renders actual parent content', () => {
    // Given
    setCompact(false);
    render(<PanelHarness />);
    fireEvent.click(screen.getByRole('button', { name: '검사 열기' }));
    const environment = screen.getByRole('tab', { name: '환경' });
    environment.focus();

    // When
    fireEvent.keyDown(environment, { key: 'End' });

    // Then
    expect(screen.getByRole('tab', { name: '변경' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: '변경' })).toHaveFocus();
    expect(screen.getByRole('tabpanel', { name: '변경' })).toContainElement(screen.getByRole('button', { name: 'Change content' }));
  });
});
