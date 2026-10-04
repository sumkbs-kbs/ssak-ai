import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SystemTelemetricsBar from '../SystemTelemetricsBar';

afterEach(cleanup);

describe('System status disclosure', () => {
  it('keeps the observed connection visible while metrics remain in a closed native disclosure', () => {
    // Given
    render(<SystemTelemetricsBar />);
    // When
    const summary = screen.getByLabelText('서버 연결 및 시스템 지표');
    // Then
    expect(summary).toContainElement(screen.getByTestId('telemetrics-link'));
    expect(summary.closest('details')).not.toHaveAttribute('open');
    expect(screen.getByLabelText('시스템 상세 지표')).not.toBeVisible();
  });

  it('closes the native disclosure and focuses its summary when Escape is pressed', async () => {
    // Given
    render(<SystemTelemetricsBar />);
    const summary = screen.getByLabelText('서버 연결 및 시스템 지표');
    fireEvent.click(summary);
    await waitFor(() => expect(summary.closest('details')).toHaveAttribute('open'));
    await waitFor(() => expect(screen.getByLabelText('시스템 상세 지표')).toBeVisible());
    // When
    fireEvent.keyDown(document, { key: 'Escape' });
    // Then
    expect(summary.closest('details')).not.toHaveAttribute('open');
    expect(summary).toHaveFocus();
    expect(screen.getByLabelText('시스템 상세 지표')).not.toBeVisible();
  });
});
