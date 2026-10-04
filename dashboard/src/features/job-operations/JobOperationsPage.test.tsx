import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { JobOperationsPage } from './JobOperationsPage';
import { fetchJobHealth, fetchJobRuns, fetchScheduledJobs, retryJobRun } from './jobOperationsApi';

vi.mock('./jobOperationsApi', () => ({
  fetchJobHealth: vi.fn(),
  fetchJobRuns: vi.fn(),
  fetchScheduledJobs: vi.fn(),
  retryJobRun: vi.fn(),
}));

const health = {
  generated_at: new Date('2026-08-27T04:00:00Z'),
  run_window: 20,
  active_jobs: 1,
  paused_jobs: 0,
  open_runs: 0,
  completed_runs: 4,
  succeeded_runs: 3,
  failed_runs: 1,
  delivery_failed_runs: 0,
  stale_runs: 0,
  success_rate: 0.75,
  healthy: false,
  reasons: ['failure rate exceeds policy'],
};

const job = {
  job_id: 'job-1',
  name: 'Nightly benchmark',
  prompt: 'Run the benchmark',
  model: 'qwen3.8',
  context: {},
  context_mode: 'fresh' as const,
  use_worktree: false,
  execution: { kind: 'agent' as const, command: [] },
  delivery: { kind: 'none' as const, target: '', secret_env: '' },
  schedule: { kind: 'interval' as const, run_at: null, interval_seconds: 3600, cron: null },
  status: 'active' as const,
  created_at: new Date('2026-08-26T04:00:00Z'),
  updated_at: new Date('2026-08-26T04:00:00Z'),
  next_run_at: new Date('2026-08-27T05:00:00Z'),
  last_run_at: new Date('2026-08-27T03:00:00Z'),
};

const failedRun = {
  run_id: 'run-1',
  job_id: 'job-1',
  status: 'failed' as const,
  task_id: 'task-1',
  output: '',
  error: 'provider unavailable',
  delivery_status: 'not_configured' as const,
  delivery_error: '',
  started_at: new Date('2026-08-27T03:00:00Z'),
  completed_at: new Date('2026-08-27T03:01:00Z'),
};

describe('JobOperationsPage', () => {
  beforeEach(() => {
    vi.mocked(fetchJobHealth).mockResolvedValue(health);
    vi.mocked(fetchScheduledJobs).mockResolvedValue([job]);
    vi.mocked(fetchJobRuns).mockResolvedValue([failedRun]);
    vi.mocked(retryJobRun).mockResolvedValue({
      source_run_id: 'run-1',
      run: { ...failedRun, run_id: 'run-2', status: 'submitted' },
    });
  });

  it.each([true, false])('shows no measured success rate when no runs are completed and scheduler health is %s', async (healthy) => {
    // Given: the API supplies its nominal rate with an empty completed-run window.
    vi.mocked(fetchJobHealth).mockResolvedValue({
      ...health,
      completed_runs: 0,
      succeeded_runs: 0,
      failed_runs: 0,
      open_runs: healthy ? 0 : 1,
      stale_runs: healthy ? 0 : 1,
      success_rate: 1,
      healthy,
      reasons: healthy ? [] : ['stale run exceeds policy'],
    });
    vi.mocked(fetchScheduledJobs).mockResolvedValue([]);

    // When: the loaded snapshot is presented.
    render(<JobOperationsPage />);
    const summary = within(await screen.findByRole('region', { name: 'Job health summary' }));

    // Then: the rate is unmeasured while the scheduler keeps its reported health.
    expect(summary.getByText('—', { selector: 'strong' })).toBeInTheDocument();
    expect(summary.getByText('No completed runs', { selector: 'small' })).toBeInTheDocument();
    expect(summary.queryByText('100%')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(healthy ? 'Healthy' : 'Needs attention');
    if (!healthy) {
      expect(screen.getByRole('alert')).toHaveTextContent('No completed runs');
      expect(screen.getByRole('alert')).not.toHaveTextContent('100% success');
    }
  });

  it.each([0, 0.75, 1])('shows the measured success rate %s when runs are completed', async (successRate) => {
    // Given: the window contains completed runs, including the zero-success boundary.
    vi.mocked(fetchJobHealth).mockResolvedValue({ ...health, success_rate: successRate });

    // When: the loaded snapshot is presented.
    render(<JobOperationsPage />);
    const summary = within(await screen.findByRole('region', { name: 'Job health summary' }));

    // Then: the actual rate and completed-run denominator remain visible.
    expect(summary.getByText(`${Math.round(successRate * 100)}%`, { selector: 'strong' })).toBeInTheDocument();
    expect(summary.getByText('4 completed runs')).toBeInTheDocument();
  });

  it('shows policy risk, selected job history, and retries failed runs', async () => {
    render(<JobOperationsPage />);

    expect(await screen.findByRole('heading', { name: 'Job Operations' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('failure rate exceeds policy');
    expect(screen.getByRole('button', { name: 'Nightly benchmark' })).toBeInTheDocument();
    expect(await screen.findByText('provider unavailable')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /retry run-1/i }));

    await waitFor(() => expect(retryJobRun).toHaveBeenCalledWith('job-1', 'run-1'));
    expect(await screen.findByText(/retry submitted/i)).toBeInTheDocument();
  });

  it('exposes a recoverable error when the initial snapshot fails', async () => {
    vi.mocked(fetchJobHealth).mockRejectedValueOnce(new Error('API unavailable'));

    render(<JobOperationsPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable');
    expect(screen.getByRole('button', { name: /retry loading/i })).toBeInTheDocument();
  });
});
