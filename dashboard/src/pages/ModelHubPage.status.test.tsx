import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ModelHubPage from './ModelHubPage';
import * as client from '../api/client';
import { useChatStore } from '../stores/chatStore';

describe('Model Hub runtime status', () => {
  beforeEach(() => {
    useChatStore.setState({ selectedModel: 'qa-unknown' });
    vi.spyOn(client, 'fetchLocalModels').mockResolvedValue({
      ok: true,
      total: 4,
      models: ['running', 'installed', 'cached', 'unknown'].map((status) => ({
        id: `qa-${status}`,
        name: `qa-${status}`,
        provider: 'ollama',
        role: 'reasoning',
        parameter_count_b: 1,
        is_local: true,
        status,
        disk_path: '',
        disk_size_gb: 1,
        quantization: 'Q4_K_M',
        source: 'ollama',
      })),
    });
  });

  it('distinguishes installed, cached and unknown status when runtime inventory is partial', async () => {
    // Given installed inventory with four distinct runtime states.
    render(<ModelHubPage />);
    // When the inventory is rendered.
    await screen.findByRole('heading', { name: 'qa-unknown' });
    // Then unknown runtime readiness is visible, including on a selected model.
    const heading = screen.getByRole('heading', { name: 'qa-unknown' });
    const card = heading.closest('.hub-card');
    if (!(card instanceof HTMLElement)) throw new Error('Model card missing');
    expect(within(card).getAllByText('실행 상태 미확인')).toHaveLength(2);
    expect(within(card).queryByText('✓ 로컬 준비됨')).not.toBeInTheDocument();
    expect(screen.getByText('설치됨')).toBeInTheDocument();
    expect(screen.getByText('로컬 캐시')).toBeInTheDocument();
  });

  it('counts only running status when selected model has unknown runtime readiness', async () => {
    // Given one running model and a selected model whose status is unknown.
    render(<ModelHubPage />);
    // When the running filter is selected.
    await screen.findByRole('heading', { name: 'qa-running' });
    fireEvent.click(screen.getByRole('button', { name: /실행 중 \(1\)/ }));
    // Then only the resident model remains visible.
    await waitFor(() => expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1));
    expect(screen.getByRole('heading', { name: 'qa-running' })).toBeInTheDocument();
  });
});
