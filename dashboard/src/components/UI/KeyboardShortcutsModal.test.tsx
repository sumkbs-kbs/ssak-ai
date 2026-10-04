import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import KeyboardShortcutsModal from './KeyboardShortcutsModal';

const CLOSE_LABEL = '키보드 단축키 대화상자 닫기';

function ShortcutGuideShell() {
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <button type="button" onClick={() => setVisible(true)}>Open shortcuts</button>
      <button type="button">Background action</button>
      <KeyboardShortcutsModal visible={visible} onClose={() => setVisible(false)} />
    </div>
  );
}

function openGuide() {
  render(<ShortcutGuideShell />);
  const opener = screen.getByRole('button', { name: 'Open shortcuts' });
  opener.focus();
  fireEvent.click(opener);

  return {
    opener,
    dialog: screen.getByRole('dialog', { name: '키보드 단축키' }),
    closeButton: screen.getByRole('button', { name: CLOSE_LABEL }),
  };
}

afterEach(cleanup);

describe('KeyboardShortcutsModal keyboard access', () => {
  it('moves focus to the close button when the guide opens', async () => {
    // Given
    render(<ShortcutGuideShell />);
    const opener = screen.getByRole('button', { name: 'Open shortcuts' });
    opener.focus();

    // When
    fireEvent.click(opener);

    // Then
    await waitFor(() => expect(screen.getByRole('button', { name: CLOSE_LABEL })).toHaveFocus());
  });

  it('exposes a modal dialog when the guide opens', () => {
    // Given
    render(<ShortcutGuideShell />);
    const opener = screen.getByRole('button', { name: 'Open shortcuts' });

    // When
    fireEvent.click(opener);

    // Then
    expect(screen.getByRole('dialog', { name: '키보드 단축키' })).toHaveAttribute('aria-modal', 'true');
  });

  it.each([false, true])('contains Tab navigation when shiftKey is %s', (shiftKey) => {
    // Given
    const { closeButton } = openGuide();
    closeButton.focus();

    // When
    const defaultAllowed = fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey });

    // Then
    expect(defaultAllowed).toBe(false);
    expect(closeButton).toHaveFocus();
  });

  it('returns focus to the opener when Escape closes the guide', () => {
    // Given
    const { opener, closeButton } = openGuide();
    closeButton.focus();

    // When
    fireEvent.keyDown(closeButton, { key: 'Escape' });

    // Then
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('returns focus to the opener when the close button dismisses the guide', () => {
    // Given
    const { opener, closeButton } = openGuide();
    closeButton.focus();

    // When
    fireEvent.click(closeButton);

    // Then
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('returns focus to the opener when the backdrop dismisses the guide', () => {
    // Given
    const { opener, closeButton } = openGuide();
    closeButton.focus();

    // When
    fireEvent.click(screen.getByRole('presentation'));

    // Then
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
