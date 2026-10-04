/**
 * ChatMessage Tests (Phase 12 — memoization)
 * =============================================
 * Tests the chatMessageAreEqual comparator and React.memo behavior.
 */

import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import ChatMessage, { chatMessageAreEqual } from '../ChatMessage';

/*
 * CR-09(F05): mermaid는 CDN 전역(`window.mermaid`)이 아니라 로컬 런타임 모듈에서
 * 지연 로드된다. 이 테스트는 그 계약을 검증한다.
 */
const mermaidRuntimeMock = vi.hoisted(() => ({
  loadMermaid: vi.fn(),
  peekMermaid: vi.fn(() => null),
  resetMermaidRuntimeForTests: vi.fn(),
  MERMAID_CONFIG: Object.freeze({}),
}));

vi.mock('../../../utils/mermaidRuntime', () => mermaidRuntimeMock);

/* ─── Fixtures ─────────────────────────────────────────────── */

const createMessage = (overrides: Partial<{ id: string; role: string; content: string }> = {}) => ({
  id: overrides.id ?? 'msg-1',
  role: (overrides.role ?? 'assistant') as 'user' | 'assistant',
  content: overrides.content ?? 'Hello world',
});

/* ─── ChatMessage Module ───────────────────────────────────── */

describe('ChatMessage module', () => {
  it('has displayName set', () => {
    expect(ChatMessage.displayName).toBe('ChatMessage');
  });
});

/* ─── ChatMessage Rendering ────────────────────────────────── */

describe('ChatMessage rendering', () => {
  it('labels the user message', () => {
    render(<ChatMessage message={createMessage({ role: 'user', content: 'How are you?' })} />);
    expect(screen.getByRole('article', { name: '내 메시지' })).toBeInTheDocument();
    expect(screen.getByText('How are you?')).toBeInTheDocument();
  });

  it('labels the assistant response', () => {
    render(<ChatMessage message={createMessage({ role: 'assistant', content: 'I am fine!' })} />);
    expect(screen.getByRole('article', { name: 'SSAK-AI 응답' })).toBeInTheDocument();
    expect(screen.getByText('I am fine!')).toBeInTheDocument();
  });

  it('renders null when content is empty for assistant', () => {
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content: '' })} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders null when content is empty for user', () => {
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'user', content: '' })} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders assistant content with copy button', () => {
    render(<ChatMessage message={createMessage({ role: 'assistant', content: 'Some response' })} />);
    expect(screen.getByRole('button', { name: '응답 복사' })).toBeInTheDocument();
  });

  it('renders user content without copy button', () => {
    render(<ChatMessage message={createMessage({ role: 'user', content: 'Some question' })} />);
    expect(screen.queryByRole('button', { name: '응답 복사' })).not.toBeInTheDocument();
  });

  it('renders user message wrapped in user-message-text span', () => {
    const { container } = render(<ChatMessage message={createMessage({ role: 'user', content: '안녕' })} />);
    const userSpan = container.querySelector('.user-message-text');
    expect(userSpan).toBeInTheDocument();
    expect(userSpan?.textContent).toBe('안녕');
  });

  it('formats unicode bullets and tip callouts in assistant messages', () => {
    const content = '안내 말씀:\n• 📁 src/test/ - 테스트 파일\n• 📁 src/engine/ - 코어 엔진\n💡 팁: 설정은 http://localhost:8000 에서 확인하세요.';
    const { container } = render(<ChatMessage message={createMessage({ role: 'assistant', content })} />);
    const listItems = container.querySelectorAll('li');
    expect(listItems.length).toBe(2);
    expect(listItems[0]?.textContent).toContain('src/test/');
    expect(listItems[1]?.textContent).toContain('src/engine/');
    const callout = container.querySelector('.tip-callout');
    expect(callout).toBeInTheDocument();
    expect(callout?.textContent).toContain('팁:');
    expect(callout?.textContent).toContain('http://localhost:8000');
    const link = callout?.querySelector('a');
    expect(link).toBeInTheDocument();
    expect(link?.getAttribute('href')).toBe('http://localhost:8000');
  });

  it('renders compact token badge with comma values', () => {
    const content = '📊 Tokens Used: In: 1,234 | Out: 567';
    const { container } = render(<ChatMessage message={createMessage({ role: 'assistant', content })} />);
    const tokenBadge = container.querySelector('.tool-timeline-badge.token');
    expect(tokenBadge).toBeInTheDocument();
    expect(tokenBadge?.textContent).toContain('In: 1,234');
    expect(tokenBadge?.textContent).toContain('Out: 567');
  });

  it('renders assistant message without actions when content is empty', () => {
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content: '' })} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('sanitizes raw HTML before rendering', () => {
    const content = '<img src="x" onerror="window.__agkXss = true"><script>window.__agkXss = true</script>';
    const { container } = render(<ChatMessage message={createMessage({ role: 'assistant', content })} />);
    expect(container.querySelector('script')).not.toBeInTheDocument();
    expect(container.querySelector('[onerror]')).not.toBeInTheDocument();
  });

  it('delegates approval actions without inline handlers', () => {
    const handler = vi.fn();
    window.addEventListener('agk:approval-response', handler);
    const content = "[APPROVAL REQUIRED] Please approve this change\nWait for their 'Yes' before retrying.";

    render(<ChatMessage message={createMessage({ role: 'assistant', content })} />);
    const approveButton = screen.getByRole('button', { name: /승인/ });
    expect(approveButton).not.toHaveAttribute('onclick');
    fireEvent.click(approveButton);

    expect(handler).toHaveBeenCalledTimes(1);
    expect((handler.mock.calls[0]?.[0] as CustomEvent<{ text: string }>).detail.text).toBe('승인합니다');
    window.removeEventListener('agk:approval-response', handler);
  });

  it('delegates artifact preview actions through the window API', () => {
    const previewArtifact = vi.fn().mockResolvedValue(undefined);
    const originalPreviewArtifact = window.previewArtifact;
    window.previewArtifact = previewArtifact;
    const content = '[ARTIFACT GENERATED: report.html (Type: html)]\nSuccessfully saved to /tmp/report.html.';

    render(<ChatMessage message={createMessage({ role: 'assistant', content })} />);
    fireEvent.click(screen.getByRole('button', { name: /View Preview/ }));

    expect(previewArtifact).toHaveBeenCalledWith('/tmp/report.html', 'report.html');
    window.previewArtifact = originalPreviewArtifact;
  });
});

/* ─── chatMessageAreEqual Comparator ────────────────────────── */

describe('chatMessageAreEqual comparator', () => {
  it('updates disclosure when metadata arrives after the response', () => {
    // Given
    const message = createMessage({ content: 'Complete' });
    const { rerender, container } = render(<ChatMessage message={message} />);

    // When
    rerender(<ChatMessage message={{ ...message, agentMeta: { steps: 7, passed: false } }} />);

    // Then
    expect(container.querySelector('.assistant-agent-meta')).toHaveTextContent('7단계');
    expect(container.querySelector('.badge-fail')).toHaveTextContent('검증 실패');
  });

  it('returns true for identical messages', () => {
    const msg = { id: 'msg-1', role: 'assistant' as const, content: 'Hello' };
    expect(chatMessageAreEqual(
      { message: msg },
      { message: { ...msg } },
    )).toBe(true);
  });

  it('renders correctly for identical messages', () => {
    const msg = createMessage({ id: 'msg-1', role: 'assistant', content: 'Hello' });
    const { container: c1 } = render(<ChatMessage message={msg} />);
    expect(c1.querySelector('.bubble')?.textContent).toBeTruthy();
  });

  it('detects different role', () => {
    const msg1 = createMessage({ id: 'msg-1', role: 'user', content: 'Hello' });
    const msg2 = createMessage({ id: 'msg-1', role: 'assistant', content: 'Hello' });
    const { container: c1 } = render(<ChatMessage message={msg1} />);
    const { container: c2 } = render(<ChatMessage message={msg2} />);
    expect(c1.querySelector('article')).toHaveAccessibleName('내 메시지');
    expect(c2.querySelector('article')).toHaveAccessibleName('SSAK-AI 응답');
  });

  it('detects different content', () => {
    const msg1 = createMessage({ id: 'msg-1', role: 'assistant', content: 'Hello' });
    const msg2 = createMessage({ id: 'msg-1', role: 'assistant', content: 'World' });
    const { container: c1 } = render(<ChatMessage message={msg1} />);
    const { container: c2 } = render(<ChatMessage message={msg2} />);
    expect(c1.textContent).toContain('Hello');
    expect(c2.textContent).toContain('World');
  });
});

/* ─── GitHubAlert Fallback ───────────────────────────────── */

describe('GitHubAlert', () => {
  it('renders blockquote fallback for unmatched alert syntax', () => {
    const content = '> Regular blockquote without alert syntax';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    expect(container.textContent).toMatch(/Regular blockquote/);
    const blockquote = container.querySelector('blockquote');
    expect(blockquote).toBeInTheDocument();
  });
});

/* ─── Mermaid Diagram ──────────────────────────────────────── */

function mermaidContent(): string {
  return '```mermaid\ngraph TD;\nA-->B;\n```';
}

describe('ChatMessage Mermaid diagram', () => {
  beforeEach(() => {
    mermaidRuntimeMock.loadMermaid.mockReset();
  });

  it('CR-09: window.mermaid CDN 전역에 의존하지 않는다', () => {
    expect('mermaid' in window).toBe(false);
  });

  it('CR-09: 다이어그램이 없으면 mermaid 런타임을 로드하지 않는다', () => {
    render(<ChatMessage message={createMessage({ role: 'assistant', content: 'plain text only' })} />);
    expect(mermaidRuntimeMock.loadMermaid).not.toHaveBeenCalled();
  });

  it('shows a load error when the local mermaid runtime cannot be loaded', async () => {
    mermaidRuntimeMock.loadMermaid.mockRejectedValue(new Error('Failed to fetch dynamically imported module: mermaid'));
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content: mermaidContent() })} />,
    );
    await screen.findByText(/mermaid/i);
    expect(container.textContent).toMatch(/mermaid/i);
  });

  it('renders mermaid diagram when the local runtime is available', async () => {
    mermaidRuntimeMock.loadMermaid.mockResolvedValue({
      initialize: vi.fn(),
      render: vi.fn().mockResolvedValue({ svg: '<svg>test</svg>' }),
    });

    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: mermaidContent() })} />,
    );

    const copyBtns = await screen.findAllByRole('button', { name: /복사$/ });
    expect(copyBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('shows loading state while rendering diagram', async () => {
    mermaidRuntimeMock.loadMermaid.mockResolvedValue({
      initialize: vi.fn(),
      render: vi.fn().mockReturnValue(new Promise(() => {})),
    });

    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: mermaidContent() })} />,
    );

    // ReactMarkdown + MermaidDiagram are async; wait for the loading text
    await screen.findByText(/다이어그램 렌더링 중/);
  });

  it('shows error message when mermaid render throws', async () => {
    mermaidRuntimeMock.loadMermaid.mockResolvedValue({
      initialize: vi.fn(),
      render: vi.fn().mockRejectedValue(new Error('Syntax error in graph')),
    });

    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: mermaidContent() })} />,
    );

    await screen.findByText(/Syntax error in graph/);
  });

  it('handles cleanup on unmount during render', async () => {
    const renderDeferred: { resolve: (value: { svg: string }) => void } = { resolve: () => {} };
    const renderPromise = new Promise<{ svg: string }>(resolve => { renderDeferred.resolve = resolve; });

    mermaidRuntimeMock.loadMermaid.mockResolvedValue({
      initialize: vi.fn(),
      render: vi.fn().mockReturnValue(renderPromise),
    });

    const { unmount } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content: mermaidContent() })} />,
    );

    // Wait for ReactMarkdown to mount MermaidDiagram
    await screen.findByText(/다이어그램 렌더링 중/);

    // Unmount and let the cancelled flag handle cleanup
    unmount();
    renderDeferred.resolve({ svg: '<svg>test</svg>' });

    await new Promise(r => setTimeout(r, 50));
    expect(screen.queryByText(/다이어그램/)).not.toBeInTheDocument();
  });
});

/* ─── Carousel Slideshow ──────────────────────────────────── */

function carouselContent(): string {
  return '```carousel\n# Slide 1\nContent 1\n<!-- slide -->\n# Slide 2\nContent 2\n```';
}

describe('ChatMessage Carousel', () => {
  it('renders carousel container for valid slides', async () => {
    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: carouselContent() })} />,
    );
    const container = await screen.findByRole('button', { name: '이전' });
    expect(container).toBeInTheDocument();
  });

  it('returns null for empty slides', () => {
    const content = '```carousel\n```';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    expect(container.querySelector('.carousel-container')).toBeNull();
  });

  it('disables prev button on first slide', async () => {
    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: carouselContent() })} />,
    );

    const prevBtn = await screen.findByRole('button', { name: '이전' });
    expect(prevBtn).toBeDisabled();

    const nextBtn = await screen.findByRole('button', { name: '다음' });
    expect(nextBtn).not.toBeDisabled();
  });

  it('disables next button on last slide', async () => {
    render(
      <ChatMessage message={createMessage({ role: 'assistant', content: carouselContent() })} />,
    );

    const nextBtn = await screen.findByRole('button', { name: '다음' });
    await act(async () => { fireEvent.click(nextBtn); });

    expect(nextBtn).toBeDisabled();
    const prevBtn = await screen.findByRole('button', { name: '이전' });
    expect(prevBtn).not.toBeDisabled();
  });

  it('extracts title from first slide heading', async () => {
    const content = '```carousel\n# Slide 1 Title\nContent 1\n<!-- slide -->\n# Slide 2\nContent 2\n```';
    render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );

    await screen.findByText('Slide 1 Title');
    expect(screen.getByText('Content 1')).toBeInTheDocument();
  });
});

/* ─── Inline Code ──────────────────────────────────────────── */

describe('ChatMessage inline code', () => {
  it('renders inline code with backtick syntax', () => {
    const content = 'Use the `const` keyword to declare variables.';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    expect(container.textContent).toMatch(/const/);
  });

  it('renders inline-code class for backtick content', () => {
    const content = 'Run `npm install` in the terminal.';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const inlineCode = container.querySelector('code.inline-code');
    expect(inlineCode).toBeInTheDocument();
    expect(inlineCode?.textContent).toMatch(/npm install/);
  });
});

/* ─── Blockquote (GitHub Alert) ───────────────────────────── */

describe('ChatMessage blockquote', () => {
  it('renders blockquote content', () => {
    const content = '> This is a quote';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    expect(container.textContent).toMatch(/This is a quote/);
  });
});

/* ─── Clipboard Copy ───────────────────────────────────────── */

describe('ChatMessage clipboard copy', () => {
  it('copies highlighted code without its trailing newline', async () => {
    // Given
    const writeText = vi.fn().mockResolvedValue(undefined);
    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ChatMessage message={createMessage({ content: '```typescript\nconst x = 1;\n```' })} />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '코드 복사' })); });

    // Then
    expect(writeText).toHaveBeenCalledWith('const x = 1;');
    Object.defineProperty(navigator, 'clipboard', { value: originalClipboard, configurable: true });
  });

  it('copies the final response while retaining original visible content', async () => {
    // Given
    const writeText = vi.fn().mockResolvedValue(undefined);
    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ChatMessage message={createMessage({ content: '<think>private analysis</think>  Final response 🎉  ' })} />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '응답 복사' })); });

    // Then
    expect(writeText).toHaveBeenCalledWith('Final response 🎉');
    expect(screen.getByText(/Final response 🎉/)).toBeInTheDocument();
    Object.defineProperty(navigator, 'clipboard', { value: originalClipboard, configurable: true });
  });

  it('renders copy buttons that can be clicked without error', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      writable: true,
      configurable: true,
    });

    render(
      <ChatMessage
        message={createMessage({ role: 'assistant', content: 'Test content for copy' })}
      />,
    );

    const copyBtns = screen.getAllByRole('button', { name: /복사$/ });
    expect(copyBtns.length).toBeGreaterThanOrEqual(1);

    for (const btn of copyBtns) {
      await act(async () => { fireEvent.click(btn); });
    }

    expect(writeText).toHaveBeenCalled();

    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      writable: true,
      configurable: true,
    });
  });
});

/* ─── Code Block ───────────────────────────────────────────── */

describe('ChatMessage code block', () => {
  it('renders code block with copy buttons', async () => {
    const content = '```typescript\nconst x = 1;\n```';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const copyBtns = await screen.findAllByRole('button', { name: /복사$/ });
    expect(copyBtns.length).toBeGreaterThanOrEqual(1);
    expect(container.textContent).toMatch(/typescript/i);
  });

  it('shows default language label when no language specified', async () => {
    const content = '```\nplain code block\n```';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    expect(screen.getByText('code', { selector: '.code-block-lang span' })).toBeInTheDocument();
    expect(container.querySelector('.code-block pre code')).toHaveTextContent('plain code block');
  });

  it('renders pre element via passthrough', async () => {
    const content = '```typescript\nconst x = 1;\n```';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const pres = container.querySelectorAll('pre');
    expect(pres.length).toBeGreaterThanOrEqual(1);
    const codeInPre = pres[0]?.querySelector('code');
    expect(codeInPre).toBeInTheDocument();
  });

  it('CR-09: 하이라이트 토큰 span을 평문으로 치환하지 않는다', async () => {
    const content = '```typescript\nconst x = 1;\n```';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    await screen.findAllByRole('button', { name: /복사$/ });

    // 로컬로 가져온 하이라이트 테마가 색을 칠할 수 있도록 토큰 span을 유지한다.
    const keyword = container.querySelector('.code-block code .hljs-keyword');
    expect(keyword).not.toBeNull();
    expect(keyword?.textContent).toBe('const');
    // 토큰 트리를 그대로 렌더하면서도 마지막 개행은 남기지 않는다.
    expect(container.querySelector('.code-block code')?.textContent).not.toMatch(/\n$/);
  });

  it('renders Ssak-Ai thinking box when think tags are present', () => {
    const content = '<think>이것은 시스템 아키텍처에 대한 심층 사고 과정입니다.</think>최종 분석 결과입니다.';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const thoughtBox = container.querySelector('.antigravity-thought-box');
    expect(thoughtBox).toBeInTheDocument();
    expect(thoughtBox?.textContent).toContain('생각 과정 (Thinking Process)');
    expect(thoughtBox?.textContent).toContain('이것은 시스템 아키텍처에 대한 심층 사고 과정입니다.');
    expect(container.textContent).toContain('최종 분석 결과입니다.');
  });

  it('renders Ssak-Ai tool cards for tool execution pattern', () => {
    const content = '**도구 실행** (step 1/3): `run_command`\n완료되었습니다.';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const toolCard = container.querySelector('.antigravity-tool-card');
    expect(toolCard).toBeInTheDocument();
    expect(toolCard?.textContent).toContain('Executing Tool');
    expect(toolCard?.textContent).toContain('run_command');
    expect(toolCard?.textContent).toContain('Step 1/3');
  });

  it('renders Ssak-Ai markdown tables in responsive container', () => {
    const content = '| 항목 | 설명 |\n|---|---|\n| 토큰 | 1500 |\n| 지연시간 | 120ms |';
    const { container } = render(
      <ChatMessage message={createMessage({ role: 'assistant', content })} />,
    );
    const tableContainer = container.querySelector('.agk-table-container');
    expect(tableContainer).toBeInTheDocument();
    const table = container.querySelector('.agk-markdown-table');
    expect(table).toBeInTheDocument();
    expect(table?.textContent).toContain('항목');
    expect(table?.textContent).toContain('120ms');
  });

  it('renders agentMeta badges when agentMeta is present', () => {
    const msg = {
      id: 'msg-agent',
      role: 'assistant' as const,
      content: 'Task completed successfully',
      agentMeta: {
        mode: 'adaptive',
        used_web: true,
        used_graphify: true,
        steps: 3,
        total_seconds: 1.2,
        passed: true,
      },
    };
    const { container } = render(<ChatMessage message={msg} />);
    const metaContainer = container.querySelector('.assistant-agent-meta');
    expect(metaContainer).toBeInTheDocument();
    expect(metaContainer?.textContent).toContain('adaptive');
    expect(metaContainer?.textContent).toContain('웹 검색');
    expect(metaContainer?.textContent).toContain('코드 검색');
    expect(metaContainer?.textContent).toContain('검증 통과');
    expect(metaContainer?.textContent).toContain('3단계');
    expect(metaContainer?.textContent).toContain('1.2초');
  });
});

/* ─── task 14: 실패 봉투는 답변처럼 보이지 않는다 ───────────── */

describe('ChatMessage 실패 봉투', () => {
  it('Search Error: 접두어는 오류 블록으로 그린다(마크다운 산문이 아니다)', () => {
    render(<ChatMessage message={createMessage({ content: 'Search Error: 결과를 가져오지 못했습니다' })} />);

    const notice = screen.getByTestId('chat-error-notice');
    expect(notice).toHaveAttribute('role', 'alert');
    expect(notice).toHaveAttribute('data-error-code', 'SEARCH_FAILED');
    expect(notice).toHaveTextContent('결과를 가져오지 못했습니다');
    // 답변용 액션(복사 등)을 붙이지 않는다 — 실패를 답변으로 대접하지 않는다.
    expect(screen.queryByRole('group', { name: /assistant markdown/i })).toBeNull();
  });

  it('오류 봉투 JSON 은 코드를 보여준다', () => {
    render(<ChatMessage message={createMessage({ content: '{"error":{"code":"AUTH_REQUIRED","detail":"자격 증명 필요"}}' })} />);

    const notice = screen.getByTestId('chat-error-notice');
    expect(notice).toHaveAttribute('data-error-code', 'AUTH_REQUIRED');
    expect(notice).toHaveTextContent('자격 증명 필요');
  });

  it('사용자가 쓴 메시지는 실패로 재해석하지 않는다', () => {
    render(<ChatMessage message={createMessage({ role: 'user', content: 'Search Error: 라고 나왔어' })} />);

    expect(screen.queryByTestId('chat-error-notice')).toBeNull();
    expect(screen.getByText('Search Error: 라고 나왔어')).toBeInTheDocument();
  });

  it('error 라는 단어가 있는 정상 답변은 그대로 산문으로 그린다', () => {
    render(<ChatMessage message={createMessage({ content: '이 함수는 error 를 반환하지 않습니다.' })} />);

    expect(screen.queryByTestId('chat-error-notice')).toBeNull();
    expect(screen.getByText(/error 를 반환하지 않습니다/)).toBeInTheDocument();
  });
});
