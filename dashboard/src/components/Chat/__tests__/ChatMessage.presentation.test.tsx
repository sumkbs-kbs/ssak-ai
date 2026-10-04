import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ChatMessage as Message } from '../../../stores/chatStore';
import ChatMessage from '../ChatMessage';

const banner = '🛡️ **[정밀 엔지니어링 모드]**';
const quality = '📊 *품질: good (70%)*';
const tokens = '📊 **[Token Usage]** In: 25 tokens | Out: 27 tokens';
const envelope = (body: string) => `${banner}\n\n🏢 ${body}\n\n${quality}\n\n${tokens}\n`;
const message = (content: string, role: Message['role'] = 'assistant'): Message => ({ id: 'presentation', role, content });
const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

afterEach(() => {
  if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
  else Reflect.deleteProperty(navigator, 'clipboard');
});

describe('ChatMessage response presentation', () => {
  it.each([
    '- item\n\n    <span style="position:fixed" onclick="danger()">safe text</span>',
    '`first paragraph\n\n<span style="position:fixed" onclick="danger()">safe text</span>\n\nlast paragraph`',
    '<div>\n~~~\n<span style="position:fixed" onclick="danger()">safe text</span>\n~~~\n</div>',
    '[^note]: item\n\n    <span style="position:fixed" onclick="danger()">safe text</span>\n\nreference[^note]',
    '<i>x</i>&#96;`<span style="position:fixed" onclick="danger()">safe text</span>`',
  ])('sanitizes active HTML when Markdown-like decoration is ordinary content: %s', content => {
    // Given
    const input = message(content);

    // When
    const { container } = render(<ChatMessage message={input} />);

    // Then
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
    expect(container.querySelector('.antigravity-markdown-body')).toHaveTextContent('safe text');
  });

  it.each(['fenced', 'indented'])('preserves literal HTML and token examples in true %s code', kind => {
    // Given
    const literal = `<span style="position:fixed" onclick="danger()">safe text</span>\n${tokens}`;
    const content = kind === 'fenced'
      ? `~~~html\n${literal}\n~~~`
      : literal.split('\n').map(line => `    ${line}`).join('\n');

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.code-block pre code')?.textContent).toBe(literal);
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
    expect(screen.queryByText('응답 정보')).not.toBeInTheDocument();
  });

  it('keeps an unfinished thought streaming while sanitizing its inner HTML', () => {
    // Given
    const content = '<think>Still checking <span style="position:fixed" onclick="danger()">safe text</span>';

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.thought-status-badge.streaming')).toHaveTextContent('사고 중');
    expect(container.querySelector('.thought-body')).toHaveTextContent('Still checking');
    expect(container.querySelector('.thought-body')).toHaveTextContent('safe text');
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
    expect(container.querySelector('.thought-body')).not.toHaveTextContent('position:fixed');
  });

  it('keeps literal HTML from a code block inside a completed thought inert', () => {
    // Given
    const content = '<think>Checking code\n\n```html\n<span style="position:fixed" onclick="danger()">safe text</span>\n```\n</think>Done';

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.thought-status-badge')).toHaveTextContent('완료');
    expect(container.querySelector('.thought-body')).toHaveTextContent('<span style="position:fixed" onclick="danger()">safe text</span>');
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
    expect(container.querySelector('.antigravity-markdown-body')).toHaveTextContent('Done');
  });

  it('keeps a fenced code example inside a standalone thought inert', () => {
    // Given
    const content = '<think>\n\n```html\n<span style="position:fixed" onclick="danger()">example</span>\n```\n</think>\n\nanswer';

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.thought-status-badge')).toHaveTextContent('완료');
    expect(container.querySelector('.thought-body')).toHaveTextContent('example');
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
    expect(container.querySelector('.thought-body')).toHaveTextContent('<span style="position:fixed" onclick="danger()">example</span>');
    expect(container.querySelector('.antigravity-markdown-body')).toHaveTextContent('answer');
  });

  it('keeps a protected code span inert when the formatter wraps it in a GitHub alert', () => {
    // Given
    const literal = '<span style="position:fixed" onclick="danger()">example</span>';
    const content = `> [!WARNING]\n> \`\`${literal}\`\``;

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.github-alert-header')).toHaveTextContent('Warning');
    expect(container.querySelector('blockquote')).toHaveTextContent(literal);
    expect(container.querySelector('span[style]')).not.toBeInTheDocument();
    expect(container.querySelector('[onclick]')).not.toBeInTheDocument();
  });

  it('shows only answer prose when a server envelope is present', () => {
    // Given
    const raw = envelope('분석을 마쳤습니다. 🎉');

    // When
    const { container } = render(<ChatMessage message={message(raw)} />);

    // Then
    expect(container.querySelector('.antigravity-markdown-body')).toHaveTextContent('분석을 마쳤습니다. 🎉');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('정밀 엔지니어링 모드');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('품질:');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('Token');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('🏢');
    const details = screen.getByText('응답 정보').closest('details');
    expect(details).not.toHaveAttribute('open');
    expect(details).toHaveTextContent('정밀 엔지니어링 모드');
    expect(details).toHaveTextContent('good (70%)');
    expect(details).toHaveTextContent('입력 25');
    expect(details).toHaveTextContent('출력 27');
    expect(details?.querySelector('pre')?.textContent).toBe(raw);
  });

  it('copies answer Markdown when envelope metadata is present', async () => {
    // Given
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const body = '**결과** 🎉\n\n- 정상\n\n```\necho ok\n```';
    render(<ChatMessage message={message(envelope(body))} />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '응답 복사' })); });

    // Then
    expect(writeText).toHaveBeenCalledWith(body);
  });

  it('renders and copies a code-first answer after removing its corroborated CEO prefix', async () => {
    // Given
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const body = '```typescript\nconst x = 1;\n```';
    const { container } = render(<ChatMessage message={message(envelope(body))} />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '응답 복사' })); });

    // Then
    expect(container.querySelector('.code-block pre code')?.textContent).toBe('const x = 1;');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('품질:');
    expect(container.querySelector('.antigravity-markdown-body')).not.toHaveTextContent('Token Usage');
    expect(screen.getByText('응답 정보').closest('details')).not.toHaveAttribute('open');
    expect(writeText).toHaveBeenCalledWith(body);
  });

  it('copies unlabelled fenced code when no language is specified', async () => {
    // Given
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const { container } = render(<ChatMessage message={message('```\nplain code\nsecond line\n```')} />);

    // When
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '코드 복사' })); });

    // Then
    expect(writeText).toHaveBeenCalledWith('plain code\nsecond line');
    expect(container.querySelector('.code-block pre code')).toHaveTextContent('plain code');
    expect(container.querySelector('.code-block code')).not.toHaveClass('inline-code');
  });

  it('preserves quoted decorations and code when they belong to an answer', () => {
    // Given
    const content = `> ${banner}\n\n\`${quality}\`\n\n\`\`\`text\n${tokens}\n\`\`\``;

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('blockquote')).toHaveTextContent('정밀 엔지니어링 모드');
    expect(container.querySelector('code.inline-code')).toHaveTextContent(quality);
    expect(container.querySelector('.code-block')).toHaveTextContent(tokens);
    expect(screen.queryByText('응답 정보')).not.toBeInTheDocument();
  });

  it('preserves a footer example in an unclosed code fence', () => {
    // Given
    const content = `코드 예시:\n\n\`\`\`text\n\n${tokens}\n`;

    // When
    const { container } = render(<ChatMessage message={message(content)} />);

    // Then
    expect(container.querySelector('.antigravity-markdown-body')).toHaveTextContent('Token Usage');
    expect(screen.queryByText('응답 정보')).not.toBeInTheDocument();
  });

  it('preserves ordinary answer emoji when no server envelope is present', () => {
    // Given
    const content = '🏢 사무실 설명입니다. 🎉';

    // When
    render(<ChatMessage message={message(content)} />);

    // Then
    expect(screen.getByText(content)).toBeInTheDocument();
    expect(screen.queryByText('응답 정보')).not.toBeInTheDocument();
  });

  it('preserves user text when it happens to match a server envelope', () => {
    // Given
    const content = envelope('사용자가 인용한 답변');

    // When
    const { container } = render(<ChatMessage message={message(content, 'user')} />);

    // Then
    expect(container.querySelector('.user-message-text')?.textContent).toBe(content);
    expect(screen.queryByText('응답 정보')).not.toBeInTheDocument();
  });

  it('retains approval actions when metadata surrounds the approval request', () => {
    // Given
    const handler = vi.fn();
    window.addEventListener('agk:approval-response', handler);
    render(<ChatMessage message={message(envelope("[APPROVAL REQUIRED] Allow this change\nWait for their 'Yes' before retrying."))} />);

    // When
    fireEvent.click(screen.getByRole('button', { name: /승인 \(Approve\)/ }));

    // Then
    expect(handler).toHaveBeenCalledOnce();
    window.removeEventListener('agk:approval-response', handler);
  });

  it('shows failure alerts when a failure is surrounded by server metadata', () => {
    // Given
    const raw = envelope('Search Error: unavailable');

    // When
    render(<ChatMessage message={message(raw)} />);

    // Then
    expect(screen.getByRole('alert')).toHaveAttribute('data-error-code', 'SEARCH_FAILED');
    expect(screen.getByRole('alert')).toHaveTextContent('unavailable');
    expect(screen.queryByRole('button', { name: '응답 복사' })).not.toBeInTheDocument();
  });
});
