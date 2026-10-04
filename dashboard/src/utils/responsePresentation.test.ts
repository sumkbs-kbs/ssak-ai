import { describe, expect, it } from 'vitest';
import { formatResponseMarkdown, presentResponse } from './responsePresentation';

const tokenLine = '📊 **[Token Usage]** In: 25 tokens | Out: 27 tokens';
const qualityLine = '📊 *품질: good (70%)*';

describe('presentResponse', () => {
  it('recognizes the producer prototype mode when it starts the response', () => {
    // Given
    const content = '🚀 **[빠른 프로토타이핑 모드]**\n\n결과 🎉';

    // When
    const result = presentResponse(content);

    // Then
    expect(result).toEqual({ body: '결과 🎉', details: [{ label: '모드', value: '빠른 프로토타이핑 모드' }] });
  });

  it('extracts successful quality when the producer uses a single newline', () => {
    // Given
    const content = `결과\n${qualityLine}\n\n\n${tokenLine}\n`;

    // When
    const result = presentResponse(content);

    // Then
    expect(result.body).toBe('결과');
    expect(result.details).toEqual([{ label: '토큰', value: '입력 25 · 출력 27' }, { label: '품질', value: 'good (70%)' }]);
  });

  it('removes exactly one corroborated CEO prefix and retains an answer office emoji', () => {
    // Given
    const content = `🛡️ **[정밀 엔지니어링 모드]**\n\n🏢 🏢 사무실 설명\n\n${tokenLine}`;

    // When
    const result = presentResponse(content);

    // Then
    expect(result.body).toBe('🏢 사무실 설명');
    expect(result.details.filter(({ label }) => label === '에이전트')).toHaveLength(1);
  });

  it.each(['retry', 'fail'])('retains a quality signal when its grade is %s', grade => {
    // Given
    const content = `결과\n\n📊 *품질: ${grade} (20%)*\n\n${tokenLine}\n`;

    // When
    const result = presentResponse(content);

    // Then
    expect(result.body).toContain(`품질: ${grade} (20%)`);
    expect(result.details).toEqual([{ label: '토큰', value: '입력 25 · 출력 27' }]);
  });

  it.each([
    `> ${qualityLine}\n\n> ${tokenLine}`,
    `    ${qualityLine}\n\n    ${tokenLine}\n`,
    `~~~text\n\n${qualityLine}\n\n${tokenLine}\n~~~`,
    `\`\`\`\`text\n\`\`\`\n\n${tokenLine}\n`,
    `\`\`code\n\n${tokenLine}\n`,
    `알림: ${tokenLine}\n`,
  ])('preserves literal decoration when it is Markdown content: %s', content => {
    // Given
    const original = content;

    // When
    const result = presentResponse(original);

    // Then
    expect(result).toEqual({ body: original, details: [] });
  });

  it('keeps token and action content together when an action follows token usage', () => {
    // Given
    const content = `결과\n\n${tokenLine}\n\n[APPROVAL REQUIRED] Continue`;

    // When
    const result = presentResponse(content);

    // Then
    expect(result).toEqual({ body: content, details: [] });
  });

  it('extracts a footer when it follows an indented code block', () => {
    // Given
    const content = `    code sample\n\n${tokenLine}\n`;

    // When
    const result = presentResponse(content);

    // Then
    expect(result.body).toBe('    code sample');
    expect(result.details).toEqual([{ label: '토큰', value: '입력 25 · 출력 27' }]);
  });
});

describe('formatResponseMarkdown', () => {
  it.each([
    `\`\`\`text\n${tokenLine}\n\`\`\``,
    `~~~text\n${tokenLine}\n~~~`,
    `\`\`code\n${tokenLine}\n\`\``,
    `\`\`\`text\n${tokenLine}\n`,
    `    ${tokenLine}\n`,
  ])('preserves code text when it contains system decoration: %s', content => {
    // Given
    const original = content;

    // When
    const formatted = formatResponseMarkdown(original);

    // Then
    expect(formatted).toBe(original);
  });

  it('preserves caller text when it contains a code placeholder lookalike', () => {
    // Given
    const content = '%%SSAK_RESPONSE_0_CODE_0%%\n\n```\nactual code\n```';

    // When
    const formatted = formatResponseMarkdown(content);

    // Then
    expect(formatted).toBe(content);
  });

  it('sanitizes active HTML while retaining literal HTML in code', () => {
    // Given
    const code = '```html\n<script>example()</script>\n```';
    const content = `<script>danger()</script>\n\n${code}`;

    // When
    const formatted = formatResponseMarkdown(content);

    // Then
    expect(formatted).not.toContain('danger()');
    expect(formatted).toContain(code);
  });

  it('sanitizes HTML when an unfinished backtick is ordinary Markdown text', () => {
    // Given
    const content = '`<span style="position:fixed" onclick="danger()">text</span>';

    // When
    const formatted = formatResponseMarkdown(content);

    // Then
    expect(formatted).not.toContain('style=');
    expect(formatted).not.toContain('onclick=');
    expect(formatted).toContain('text');
  });
});
