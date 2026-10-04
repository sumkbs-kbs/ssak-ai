import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { persistAccessToken } from '../utils/accessPinCredential';
import { useProjectStore } from '../stores/projectStore';
import { CLIENT_SESSION_STORAGE_KEY } from '../api/clientSession';
import DataExtractionPage from './DataExtractionPage';

const identity = { token: 'synthetic-extraction-token', project: 'synthetic-project', revision: 37, session: 'synthetic-session' };
const query = 'synthetic structured extraction';
const metrics = { total_calls: 42, success_rates: { overall: 95 } };
const stock = { name: 'synthetic-stock', ticker: 'QA-STOCK', close_price: 12345 };
const result = {
  ok: true, query, search_length: 81, has_top1_json: true,
  extracted: { stock_prices: [stock], weather: [], exchange_rates: [], dates_found: [] },
};
const report = { avg_accuracy: 91, avg_duration_ms: 27, total_cases: 3, passed: 2, failed: 1 };
const contracts = [
  { operation: 'metrics', path: '/api/search/extraction-metrics', method: 'GET', payload: { ok: true, metrics } },
  { operation: 'search', path: '/api/search/extract', method: 'POST', payload: result },
  { operation: 'ab', path: '/api/search/ab-test/run', method: 'POST', payload: { ok: true, report } },
] as const;
const initialProject = useProjectStore.getState();
const authRequired = vi.fn();

function trigger(operation: string): void {
  if (operation === 'search') {
    fireEvent.change(screen.getByRole('textbox'), { target: { value: query } });
    fireEvent.click(screen.getByRole('button', { name: /검색 및 추출/ }));
  }
  if (operation === 'ab') fireEvent.click(screen.getByRole('button', { name: /A\/B 테스트 실행/ }));
}

function wire(targetPath: string, targetResponse?: () => Response) {
  const calls: { path: string; method: string; headers: Headers; body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    const path = String(input);
    const headers = new Headers(options?.headers);
    const method = options?.method ?? 'GET';
    calls.push({ path, method, headers, body: typeof options?.body === 'string' ? JSON.parse(options.body) : null });
    if (headers.get('Authorization') !== `Bearer ${identity.token}`
      || headers.get('X-AGK-Project-Id') !== identity.project) {
      return Response.json({ ok: false }, { status: 401, statusText: 'Unauthorized' });
    }
    if (path === targetPath && targetResponse) return targetResponse();
    const contract = contracts.find(candidate => candidate.path === path);
    return Response.json(contract?.payload ?? { ok: false }, { status: contract ? 200 : 404 });
  }));
  return calls;
}

describe('DataExtractionPage authenticated operations', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    persistAccessToken(identity.token);
    sessionStorage.setItem(CLIENT_SESSION_STORAGE_KEY, identity.session);
    useProjectStore.setState({ activeProjectId: identity.project, projectRevision: identity.revision });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    authRequired.mockClear();
    window.addEventListener('agk:pin-required', authRequired);
  });

  afterEach(() => {
    cleanup();
    useProjectStore.setState(initialProject);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.removeEventListener('agk:pin-required', authRequired);
  });

  it.each(contracts)('sends authenticated $method $path with the active project scope', async contract => {
    // Given a nonempty credential and project, the wire rejects missing identity.
    const calls = wire(contract.path);
    render(<DataExtractionPage />);
    // When the user starts the operation (metrics starts on mount).
    trigger(contract.operation);
    // Then its method, identity and payload reach the existing API contract.
    await waitFor(() => expect(calls.find(call => call.path === contract.path)).toBeDefined());
    const request = calls.find(call => call.path === contract.path);
    expect(request?.method).toBe(contract.method);
    expect(request?.headers.get('Authorization')).toBe(`Bearer ${identity.token}`);
    expect(request?.headers.get('X-AGK-Project-Id')).toBe(identity.project);
    expect(request?.headers.get('X-AGK-Project-Revision')).toBe(String(identity.revision));
    expect(request?.headers.get('X-AGK-Session-Id')).toBe(identity.session);
    if (contract.operation === 'search') expect(request?.body).toEqual({ query });
    if (contract.operation === 'ab') expect(request?.body).toEqual({ version_label: 'dashboard' });
    if (contract.operation === 'metrics') await screen.findByText(String(metrics.total_calls));
    if (contract.operation === 'search') await screen.findByText(stock.name);
    if (contract.operation === 'ab') await screen.findByText(`${report.avg_duration_ms}ms`);
  });

  it.each(contracts)('ends loading and shows a $operation failure after a controlled 401', async contract => {
    // Given an authenticated request denied by the server.
    wire(contract.path, () => Response.json({ ok: false }, { status: 401, statusText: 'Unauthorized' }));
    render(<DataExtractionPage />);
    if (contract.operation !== 'metrics') await screen.findByText(String(metrics.total_calls));
    // When the user starts an operation that is denied.
    trigger(contract.operation);
    // Then loading ends and an alert exposes a retry through the existing PIN flow.
    const alert = await screen.findByRole('alert');
    expect(alert).not.toBeEmptyDOMElement();
    expect(alert.closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
    expect(authRequired).toHaveBeenCalledTimes(1);
    expect(document.querySelector('.dex-spinner-mini')).not.toBeInTheDocument();
    expect(within(alert).getByRole('button')).toBeEnabled();
  });

  it.each(contracts)('retries a failed $operation operation successfully', async contract => {
    // Given a failed operation with the request identity still available.
    let denied = true;
    wire(contract.path, () => denied ? Response.json({ ok: false }, { status: 401 }) : Response.json(contract.payload));
    render(<DataExtractionPage />);
    if (contract.operation !== 'metrics') await screen.findByText(String(metrics.total_calls));
    trigger(contract.operation);
    const alert = await screen.findByRole('alert');
    denied = false;
    // When the user retries after the server accepts the credential.
    fireEvent.click(within(alert).getByRole('button'));
    // Then the successful response replaces the error.
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    if (contract.operation === 'metrics') await screen.findByText(String(metrics.total_calls));
    if (contract.operation === 'search') await screen.findByText(stock.name);
    if (contract.operation === 'ab') await screen.findByText(`${report.avg_duration_ms}ms`);
  });

  it.each(contracts)('shows $operation application errors returned with HTTP 200', async contract => {
    // Given a successful transport with a failed application envelope.
    wire(contract.path, () => Response.json({ ok: false, error: 'synthetic-operation-error' }));
    render(<DataExtractionPage />);
    // When the operation completes.
    trigger(contract.operation);
    // Then failure is announced and does not remain in progress.
    const alert = await screen.findByRole('alert');
    expect(alert).not.toBeEmptyDOMElement();
    expect(alert.closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
  });

  it('preserves the previous extraction after a failed replacement search', async () => {
    // Given a stored, valid result and a failed replacement request.
    sessionStorage.setItem('dex_last_result', JSON.stringify(result));
    wire('/api/search/extract', () => Response.json({ ok: false }, { status: 503 }));
    render(<DataExtractionPage />);
    // When the user searches again.
    trigger('search');
    // Then the previous data remains readable beside the failure.
    await screen.findByRole('alert');
    expect(screen.getByText(stock.name)).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem('dex_last_result') ?? 'null')).toEqual(result);
  });

  it('renders valid partial extraction fields and retains extra server data', async () => {
    // Given the server serializes unavailable numeric fields as null.
    const numericData = [{ label: 'synthetic-number', value: 7, unit: 'count' }];
    const partial = { ...result, extracted: { ...result.extracted,
      stock_prices: [{ ...stock, open_price: null, change_percent: null, volume: null }],
      weather: [{ location: 'synthetic-location', temperature: null, humidity: null }],
      exchange_rates: [{ currency_pair: 'QA/TEST', rate: null, change_percent: null }], numeric_data: numericData,
    }, pipeline_timings: { web_search_ms: 12 } };
    wire('/api/search/extract', () => Response.json(partial));
    render(<DataExtractionPage />);
    // When the user extracts partial structured data.
    trigger('search');
    // Then present fields render, absent fields do not fail parsing, and cache retains extra data.
    await screen.findByText(stock.name);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem('dex_last_result') ?? 'null')).toMatchObject({
      extracted: { numeric_data: numericData }, pipeline_timings: partial.pipeline_timings,
    });
  });

  it('ends metrics loading when the server has no metrics', async () => {
    // Given the server returns no metrics rather than a failure.
    wire('/api/search/extraction-metrics', () => Response.json({ ok: true, metrics: null }));
    // When the page loads.
    render(<DataExtractionPage />);
    // Then an empty status replaces the spinner without an error or a synthetic zero.
    const status = await screen.findByRole('status');
    expect(status).not.toBeEmptyDOMElement();
    expect(status.closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
    expect(document.querySelector('.dex-spinner-mini')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });
});
