import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AgentStartPage from './AgentStartPage';
import { useChatStore } from '../stores/chatStore';
import { useUiStore } from '../stores/uiStore';

const chatSnapshot = useChatStore.getState();
const uiSnapshot = useUiStore.getState();
const writeText = vi.fn<(text: string) => Promise<void>>();

beforeEach(() => {
  writeText.mockReset().mockResolvedValue();
  vi.stubGlobal('navigator', Object.create(navigator, { clipboard: { value: { writeText } } }));
  vi.stubGlobal('location', new URL('http://127.0.0.1:50816/start'));
  vi.stubEnv('VITE_API_BASE', '');
  useChatStore.setState({ selectedModel: 'qa-model-contract' });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  useChatStore.setState(chatSnapshot);
  useUiStore.setState(uiSnapshot);
});

describe('AgentStartPage', () => {
  it('exposes an unverified tunnel state when no status capability exists', () => {
    // Given: the page has no read-only tunnel status capability.
    render(<AgentStartPage />);

    // When / Then: the visible status has the actual machine state rather than a ready claim.
    expect(screen.getByRole('status')).toHaveAttribute('data-state', 'unverified');
  });

  it('uses the signed token variable and protocol-specific base URLs in manual configuration', () => {
    // Given: the user opens the manual connection instructions.
    const { container } = render(<AgentStartPage />);
    const assignments = [...container.querySelectorAll('.env-line code')].map(code => code.textContent ?? '');

    // When / Then: each machine credential assignment comes from the named access-token variable.
    const credentials = assignments.filter(line => /export (ANTHROPIC_AUTH_TOKEN|OPENAI_API_KEY)=/.test(line));
    expect(credentials).toHaveLength(4);
    expect(credentials.every(line => line.includes('${SSAK_ACCESS_TOKEN:?'))).toBe(true);
    expect(assignments.filter(line => line === 'unset ANTHROPIC_API_KEY')).toHaveLength(2);
    expect(assignments.some(line => line.startsWith('export ANTHROPIC_API_KEY='))).toBe(false);
    expect(assignments).toContain('export ANTHROPIC_BASE_URL=http://127.0.0.1:50816');
    expect(assignments).toContain('export OPENAI_BASE_URL=http://127.0.0.1:50816/v1');
  });

  it('copies the selected model command without launching any network request', async () => {
    // Given: a selected model and a working clipboard.
    render(<AgentStartPage />);
    const wire = vi.spyOn(globalThis, 'fetch');

    // When: the user copies the Claude bridge command.
    const copy = screen.getAllByRole('button', { name: /복사/ })[0];
    if (copy === undefined) throw new TypeError('Bridge copy control is missing.');
    fireEvent.click(copy);

    // Then: the command is copied and nothing is started.
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('agk start claude --model qa-model-contract --api-base http://127.0.0.1:50816'));
    expect(wire).not.toHaveBeenCalled();
  });

  it('reports clipboard failure without success feedback', async () => {
    // Given: clipboard permission is denied.
    writeText.mockRejectedValue(new DOMException('Denied', 'NotAllowedError'));
    const toast = vi.spyOn(useUiStore.getState(), 'addToast');
    render(<AgentStartPage />);

    // When: the user tries to copy the tunnel command.
    fireEvent.click(screen.getByRole('button', { name: '터널 커맨드 복사' }));

    // Then: only an error is reported.
    await waitFor(() => expect(toast.mock.calls.map(([, level]) => level)).toEqual(['error']));
  });
  it('copies shell metacharacters in the selected model as a single quoted argument', async () => {
    useChatStore.setState({ selectedModel: "qa model; $(printf injected) 'quoted'" });
    render(<AgentStartPage />);
    const wire = vi.spyOn(globalThis, 'fetch');
    const command = "agk start claude --model 'qa model; $(printf injected) '\\''quoted'\\''' --api-base http://127.0.0.1:50816";

    expect(screen.getByText(command)).toBeInTheDocument();
    const copy = screen.getAllByRole('button', { name: /복사/ })[0];
    if (copy === undefined) throw new TypeError('Bridge copy control is missing.');
    fireEvent.click(copy);

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(command));
    expect(wire).not.toHaveBeenCalled();
  });
  it('copies a named tunnel command without launching or changing the verification state', async () => {
    // Given: the existing tunnel must be explicitly named by the user.
    render(<AgentStartPage />);
    const wire = vi.spyOn(globalThis, 'fetch');

    // When: the user copies the tunnel command.
    fireEvent.click(screen.getByRole('button', { name: '터널 커맨드 복사' }));

    // Then: only the guarded command is copied and readiness stays unverified.
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('cloudflared tunnel run --url http://127.0.0.1:50816 "${SSAK_TUNNEL_NAME:?set an existing tunnel name}"'));
    expect(wire).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveAttribute('data-state', 'unverified');
  });
  it('renders unsloth start title, local endpoint, and agent integrations', () => {
    render(<AgentStartPage />);

    expect(screen.getByText('Unsloth Start')).toBeInTheDocument();
    expect(screen.getByText('LOCAL AGENT BRIDGE')).toBeInTheDocument();
    expect(screen.getByText('http://127.0.0.1:50816/v1')).toBeInTheDocument();
    expect(screen.getByText('Claude Code CLI')).toBeInTheDocument();
    expect(screen.getByText('OpenAI Codex CLI')).toBeInTheDocument();
    expect(screen.getByText('Hermes Agent')).toBeInTheDocument();
  });

  it.each([
    ['https://gateway.example/ssak/v1/', 'https://gateway.example/ssak'],
    ['/v1', 'http://127.0.0.1:50816'],
    ['/proxy/v1/', 'http://127.0.0.1:50816/proxy'],
    ['   ', 'http://127.0.0.1:50816'],
  ])('uses configured API base %s consistently while preserving its prefix', async (configured, root) => {
    vi.stubEnv('VITE_API_BASE', configured);
    const { container } = render(<AgentStartPage />);
    const wire = vi.spyOn(globalThis, 'fetch');
    const assignments = [...container.querySelectorAll('.env-line code')].map(code => code.textContent ?? '');

    expect(screen.getByText(`${root}/v1`)).toBeInTheDocument();
    expect(assignments).toContain(`export ANTHROPIC_BASE_URL=${root}`);
    expect(assignments).toContain(`export OPENAI_BASE_URL=${root}/v1`);
    const commands = [...container.querySelectorAll('.cmd-text code')].map(code => code.textContent ?? '');
    expect(commands).toHaveLength(4);
    expect(commands.every(command => command.endsWith(`--api-base ${root}`))).toBe(true);
    const copy = screen.getAllByRole('button', { name: /복사/ })[0];
    if (copy === undefined) throw new TypeError('Bridge copy control is missing.');
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(`agk start claude --model qa-model-contract --api-base ${root}`));
    expect(wire).not.toHaveBeenCalled();
  });

  it('quotes a configured base containing shell metacharacters in copied commands', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://gateway.example/api;segment/v1/');
    render(<AgentStartPage />);
    const copy = screen.getAllByRole('button', { name: /복사/ })[0];
    if (copy === undefined) throw new TypeError('Bridge copy control is missing.');
    fireEvent.click(copy);

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("agk start claude --model qa-model-contract --api-base 'https://gateway.example/api;segment'"));
  });
});
