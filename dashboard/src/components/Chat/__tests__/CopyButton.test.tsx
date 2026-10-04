import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { CopyButton } from '../CopyButton';

const originalClipboard = navigator.clipboard;

afterEach(() => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: originalClipboard });
});

function setClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
}

describe('CopyButton', () => {
  it('reports copied only when the clipboard write resolves', async () => {
    // Given
    let complete: () => void = () => undefined;
    const writing = new Promise<void>((resolve) => { complete = resolve; });
    const writeText = vi.fn(() => writing);
    setClipboard(writeText);
    render(<CopyButton content="selected code" label="코드 복사" />);

    // When
    fireEvent.click(screen.getByRole('button', { name: '코드 복사' }));

    // Then
    expect(writeText).toHaveBeenCalledWith('selected code');
    expect(screen.getByRole('button', { name: '코드 복사 중' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '코드 복사됨' })).not.toBeInTheDocument();
    await act(async () => { complete(); await writing; });
    expect(screen.getByRole('button', { name: '코드 복사됨' })).toBeEnabled();
  });

  it('announces a failed clipboard write without claiming success', async () => {
    // Given
    setClipboard(vi.fn().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError')));
    render(<CopyButton content="response" label="응답 복사" />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '응답 복사' })); });

    // Then
    expect(screen.getByRole('button', { name: '응답 복사 실패, 다시 시도' })).toBeEnabled();
    expect(screen.getByRole('status')).toHaveTextContent('복사하지 못했습니다');
    expect(screen.queryByRole('button', { name: '응답 복사됨' })).not.toBeInTheDocument();
  });

  it('offers retry when the clipboard API is unavailable', async () => {
    // Given
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    render(<CopyButton content="response" label="응답 복사" />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '응답 복사' })); });

    // Then
    expect(screen.getByRole('button', { name: '응답 복사 실패, 다시 시도' })).toBeEnabled();
  });

  it('ignores a completed write after the content changes', async () => {
    // Given
    let complete: () => void = () => undefined;
    const writing = new Promise<void>((resolve) => { complete = resolve; });
    setClipboard(() => writing);
    const { rerender } = render(<CopyButton content="first" label="응답 복사" />);
    fireEvent.click(screen.getByRole('button', { name: '응답 복사' }));
    rerender(<CopyButton content="second" label="응답 복사" />);

    // When
    await act(async () => { complete(); await writing; });

    // Then
    expect(screen.getByRole('button', { name: '응답 복사' })).toBeEnabled();
  });
});
