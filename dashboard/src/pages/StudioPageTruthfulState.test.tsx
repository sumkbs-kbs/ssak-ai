import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { StudioPage } from './StudioPage';
import { useUiStore } from '../stores/uiStore';

const capabilitySnapshot = (status: 'available' | 'unavailable') => ({
  platform: 'darwin_arm64',
  system: { memory: { total_bytes: 32 * 1024 ** 3, available_bytes: 12 * 1024 ** 3 } },
  capabilities: [
    { operation: 'training', provider: 'mlx', status, is_default: true, detail: 'fixture' },
    { operation: 'export', provider: 'mlx', status: 'available', is_default: true, detail: 'fixture' },
  ],
  write_tools_enabled: false,
});

function serve(capabilities: unknown, jobStatus = 'completed') {
  const fetchMock = vi.fn<typeof fetch>((input) => {
    const url = String(input);
    let response: unknown = {};
    if (url.endsWith('/capabilities')) response = capabilities;
    else if (url.endsWith('/api/recipes')) response = { ok: true, recipes: [] };
    else if (url.endsWith('/v1/models')) response = { data: [{ id: 'fixture-model' }] };
    else if (url.endsWith('/api/training-jobs')) response = { ok: true, job_id: 'fixture-job' };
    else if (url.endsWith('/api/training-jobs/fixture-job')) response = {
      job_id: 'fixture-job', status: jobStatus, progress: 100, loss: 0.7,
      records: 3, config_path: 'fixture-config', log_tail: [], error: '',
    };
    return Promise.resolve(new Response(JSON.stringify(response)));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function openMonitor() {
  fireEvent.click(screen.getByRole('button', { name: /Monitor & Export/ }));
}

describe('Studio backend truth', () => {
  beforeEach(() => useUiStore.setState({ toasts: [] }));
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('keeps export unavailable before training and creates no success state when clicked', () => {
    // Given: no backend job or artifact exists.
    serve(capabilitySnapshot('available'));
    const { container } = render(<StudioPage />);
    openMonitor();
    const exportButton = screen.getByRole('button', { name: /GGUF Q4_K_M/ });
    // When: the pretraining export action is attempted.
    fireEvent.click(exportButton);
    // Then: the unavailable operation cannot create an artifact or success toast.
    expect(exportButton).toBeDisabled();
    expect(container.querySelector('.unsloth-success-box')).toBeNull();
    expect(useUiStore.getState().toasts).toEqual([]);
  });

  it('does not mark unperformed pipeline steps complete when navigating directly to monitoring', () => {
    // Given: a fresh Studio session.
    serve(capabilitySnapshot('available'));
    render(<StudioPage />);
    // When: monitoring is opened directly.
    openMonitor();
    // Then: navigation alone completes no backend work.
    const steps = within(screen.getByRole('navigation', { name: 'Studio Pipeline Steps' })).getAllByRole('button');
    steps.forEach((step, index) => expect(step).toHaveAccessibleName(new RegExp(`^${index + 1} `)));
    expect(screen.getByRole('button', { name: /Monitor & Export/ })).toHaveAttribute('aria-current', 'step');
  });

  it('shows no measured loss or plotted samples before a backend job reports them', () => {
    // Given: a fresh session with no job metrics.
    serve(capabilitySnapshot('available'));
    const { container } = render(<StudioPage />);
    // When: monitoring is opened.
    openMonitor();
    // Then: unavailable measurements cannot appear as observed training data.
    expect(container.querySelector('.hud-val.loss')).toHaveTextContent('—');
    expect(container.querySelectorAll('.unsloth-loss-svg circle')).toHaveLength(0);
  });

  it('uses live memory and enables the existing local training path when MLX is available', async () => {
    // Given: the capability API confirms local MLX and observed system memory.
    serve(capabilitySnapshot('available'));
    const { container } = render(<StudioPage />);
    // When: the capability snapshot arrives.
    openMonitor();
    // Then: the launch affordance and displayed memory come from that snapshot.
    await waitFor(() => expect(container.querySelector('[data-capability-status]')).toHaveAttribute('data-capability-status', 'available'));
    expect(screen.getByRole('button', { name: /Start Training/ })).toBeEnabled();
    expect(container.querySelector('[data-testid="studio-memory"]')).toHaveTextContent('12.0 / 32.0 GB');
  });

  it('disables training when the capability API reports MLX unavailable', async () => {
    // Given: local MLX is unavailable.
    serve(capabilitySnapshot('unavailable'));
    const { container } = render(<StudioPage />);
    // When: the capability snapshot arrives.
    openMonitor();
    // Then: no local launch can be submitted.
    await waitFor(() => expect(container.querySelector('[data-capability-status]')).toHaveAttribute('data-capability-status', 'unavailable'));
    expect(screen.getByRole('button', { name: /Start Training/ })).toBeDisabled();
  });

  it('keeps training and telemetry unknown when capability data is invalid', async () => {
    // Given: the API does not return its declared capability shape.
    serve({ capabilities: [] });
    const { container } = render(<StudioPage />);
    // When: the invalid response is parsed.
    openMonitor();
    // Then: malformed data cannot imply readiness or hardware measurements.
    await waitFor(() => expect(container.querySelector('[data-capability-status]')).toHaveAttribute('data-capability-status', 'unknown'));
    expect(screen.getByRole('button', { name: /Start Training/ })).toBeDisabled();
    expect(container.querySelector('[data-testid="studio-memory"]')).toHaveTextContent('—');
  });

  it('prevents editing unsupported epochs and unconnected optimizer controls', () => {
    serve(capabilitySnapshot('available'));
    render(<StudioPage />);
    fireEvent.click(screen.getByRole('button', { name: /Parameters/ }));
    expect(screen.getByLabelText('Epochs')).toBeDisabled();
    expect(screen.getByLabelText('Optimizer')).toBeDisabled();
  });

  it('reflects backend training completion without declaring model export or registration', async () => {
    // Given: a real job endpoint reports successful training but no exported artifact.
    const fetchMock = serve(capabilitySnapshot('available'));
    const { container } = render(<StudioPage />);
    openMonitor();
    await waitFor(() => expect(screen.getByRole('button', { name: /Start Training/ })).toBeEnabled());
    // When: the local job start is confirmed and its result is polled.
    fireEvent.click(screen.getByRole('button', { name: /Start Training/ }));
    // Then: actual progress is displayed, and export remains unavailable.
    await waitFor(() => expect(container.querySelector('.hud-val.loss')).toHaveTextContent('0.700'));
    expect(container.querySelector('.unsloth-success-box')).toBeNull();
    expect(screen.getByRole('button', { name: /GGUF Q4_K_M/ })).toBeDisabled();
    const startCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/training-jobs'));
    expect(startCall).toBeDefined();
    expect(JSON.parse(String(startCall?.[1]?.body))).toMatchObject({
      platform: 'auto', hyperparameters: { iterations: 600 },
    });
    expect(JSON.parse(String(startCall?.[1]?.body)).hyperparameters).not.toHaveProperty('num_train_epochs');
  });
});
