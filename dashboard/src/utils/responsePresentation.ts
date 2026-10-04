import DOMPurify from 'dompurify';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import { escapeHTML, preprocessContent } from './formatContent';

export interface ResponseDetail {
  readonly label: string;
  readonly value: string;
}

export interface ResponsePresentation {
  readonly body: string;
  readonly details: readonly ResponseDetail[];
}

interface SourceRange {
  readonly start: number;
  readonly end: number;
}

interface MarkdownSourceNode {
  readonly type: string;
  readonly position?: {
    readonly start: { readonly offset?: number };
    readonly end: { readonly offset?: number };
  };
  readonly children?: readonly MarkdownSourceNode[];
}

const markdownParser = unified().use(remarkParse).use(remarkGfm);
const MODE_PREFIXES = [
  { prefix: '🛡️ **[정밀 엔지니어링 모드]**\n\n', label: '정밀 엔지니어링 모드' },
  { prefix: '🚀 **[빠른 프로토타이핑 모드]**\n\n', label: '빠른 프로토타이핑 모드' },
] as const;

function markdownRanges(content: string, types: readonly string[]): readonly SourceRange[] {
  const ranges: SourceRange[] = [];
  const visit = (node: MarkdownSourceNode): void => {
    if (types.includes(node.type)) {
      const start = node.position?.start.offset;
      const end = node.position?.end.offset;
      if (start !== undefined && end !== undefined) ranges.push({ start, end });
      return;
    }
    node.children?.forEach(visit);
  };
  visit(markdownParser.parse(content));
  return ranges;
}

/** Only the producer's exact head banner and contiguous successful footer are metadata. */
export function presentResponse(content: string): ResponsePresentation {
  const details: ResponseDetail[] = [];
  const mode = MODE_PREFIXES.find(({ prefix }) => content.startsWith(prefix));
  let body = mode ? content.slice(mode.prefix.length) : content;
  if (mode) details.push({ label: '모드', value: mode.label });
  const modeAgent = mode !== undefined && body.startsWith('🏢 ');
  if (modeAgent) {
    details.push({ label: '에이전트', value: 'CEO' });
    body = body.slice('🏢 '.length);
  }

  const ranges = markdownRanges(body, ['code', 'inlineCode']);
  // Unfinished backticks keep metadata visible while streaming; they never bypass HTML sanitation.
  const unfinishedTicks = [...body.matchAll(/`+/g)].reduce<string | null>(
    (open, run) => open === run[0] ? null : open ?? run[0], null,
  );
  const tokens = /(?:^|\n)📊 \*\*\[Token Usage\]\*\* In: (\d+) tokens \| Out: (\d+) tokens\n*$/.exec(body);
  const tokenStart = tokens ? tokens.index + tokens[0].indexOf('📊') : -1;
  if (tokens && unfinishedTicks === null && !ranges.some(({ start, end }) => tokenStart >= start && tokenStart < end)) {
    details.push({ label: '토큰', value: `입력 ${tokens[1]} · 출력 ${tokens[2]}` });
    body = body.slice(0, tokens.index).replace(/\n+$/, '');
  }
  const quality = /(?:^|\n)📊 \*품질: (good|excellent) \((100|[1-9]?\d)%\)\*\n*$/.exec(body);
  const qualityStart = quality ? quality.index + quality[0].indexOf('📊') : -1;
  if (quality && unfinishedTicks === null && !ranges.some(({ start, end }) => qualityStart >= start && qualityStart < end)) {
    details.push({ label: '품질', value: `${quality[1]} (${quality[2]}%)` });
    body = body.slice(0, quality.index).replace(/\n+$/, '');
  }
  if (!modeAgent && details.length > 0 && body.startsWith('🏢 ')) {
    details.push({ label: '에이전트', value: 'CEO' });
    body = body.slice('🏢 '.length);
  }
  return { body, details };
}

export function formatResponseMarkdown(content: string): string {
  const ranges = markdownRanges(content, ['code', 'inlineCode']);
  let nonce = 0;
  while (content.includes(`%%SSAK_RESPONSE_${nonce}_`)) nonce += 1;
  let cursor = 0;
  let protectedContent = '';
  const segments = ranges.map(({ start, end }, index) => {
    const token = `%%SSAK_RESPONSE_${nonce}_CODE_${index}%%`;
    const source = content.slice(start, end);
    protectedContent += content.slice(cursor, start) + token;
    cursor = end;
    return { token, source, beforeFormatting: /^`[^`\n<>]*`$/.test(source) };
  });
  protectedContent += content.slice(cursor);
  const thoughtTags: { readonly token: string; readonly source: string }[] = [];
  protectedContent = protectedContent.replace(/<\/?think>/gi, source => {
    const token = `%%SSAK_RESPONSE_${nonce}_THINK_${thoughtTags.length}%%`;
    thoughtTags.push({ token, source });
    return token;
  });
  let sanitized = DOMPurify.sanitize(protectedContent, { USE_PROFILES: { html: true }, FORBID_ATTR: ['style'] });
  for (const { token, source } of thoughtTags) sanitized = sanitized.replace(token, () => source);
  for (const { token, source, beforeFormatting } of segments) {
    if (beforeFormatting) sanitized = sanitized.replace(token, () => source);
  }
  const formatted = preprocessContent(sanitized);
  const remaining = segments.filter(({ beforeFormatting }) => !beforeFormatting)
    .map(segment => ({ ...segment, offset: formatted.indexOf(segment.token) }))
    .filter(({ offset }) => offset >= 0)
    .sort((left, right) => left.offset - right.offset);
  const escaped = new Set<string>();
  // Sanitization can decode delimiters; only final AST code ranges permit raw restoration.
  for (;;) {
    let restored = '';
    let cursor = 0;
    const literalRanges: (SourceRange & { readonly token: string })[] = [];
    for (const { token, source, offset } of remaining) {
      restored += formatted.slice(cursor, offset);
      const start = restored.length;
      restored += escaped.has(token) ? escapeHTML(source) : source;
      if (!escaped.has(token)) literalRanges.push({ token, start, end: restored.length });
      cursor = offset + token.length;
    }
    restored += formatted.slice(cursor);
    const finalCode = markdownRanges(restored, ['code', 'inlineCode']);
    const unsafe = literalRanges.filter(literal => !finalCode.some(code => literal.start >= code.start && literal.end <= code.end));
    if (unsafe.length === 0) return restored;
    for (const { token } of unsafe) escaped.add(token);
  }
}
