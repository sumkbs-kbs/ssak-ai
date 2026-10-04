import React, { useEffect, useId, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { loadMermaid } from '../../utils/mermaidRuntime';
import { AppIcon } from '../UI/AppIcon';
import { ChatCodeBlock, extractCodeText, extractLanguage } from './ChatCodeBlock';

const markdownSanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    'button',
    'details',
    'summary',
    'div',
    'span',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
  ],
  attributes: {
    ...defaultSchema.attributes,
    details: ['open', 'className', 'style'],
    summary: ['className', 'style'],
    div: ['className', 'style', 'data*'],
    span: ['className', 'style', 'data*'],
    button: [
      ...(defaultSchema.attributes?.button ?? []),
      'type',
      'className',
      'style',
      'data*',
    ],
    '*': [
      ...(defaultSchema.attributes?.['*'] ?? []),
      ['className', /^[A-Za-z0-9_-]+$/],
      'style',
      'data*',
    ],
  },
};

const MermaidDiagram: React.FC<{ code: string }> = ({ code }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const renderId = `mermaid-${useId().replaceAll(':', '')}`;

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      try {
        if (!containerRef.current) return;
        /*
         * CR-09(F05): CDN의 window.mermaid 대신 로컬 의존성을 지연 로드한다.
         * 로드 실패는 아래 catch가 그대로 사용자 오류 화면으로 보여준다.
         */
        const mermaid = await loadMermaid();
        if (!containerRef.current) return;
        containerRef.current.innerHTML = '';
        const { svg } = await mermaid.render(renderId, code);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : String(error);
          setError(message || 'Mermaid render failed');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    render();
    return () => { cancelled = true; };
  }, [code, renderId]);

  if (error) {
    return (
      <div className="mermaid-container">
        <div className="mermaid-error">
          <AppIcon name="activity" size={16} /> Mermaid 렌더링 오류: {error}
          <pre>{code}</pre>
        </div>
      </div>
    );
  }

  return (
    <div className="mermaid-container">
      {loading && <div className="mermaid-loading" role="status"><AppIcon name="refresh" size={16} /> 다이어그램 렌더링 중...</div>}
      <div ref={containerRef} style={{ minHeight: loading ? 0 : 40 }} />
    </div>
  );
};

// ─── Carousel Slideshow ───────────────────────────────────────────
const CarouselView: React.FC<{ slides: string[] }> = ({ slides }) => {
  const [current, setCurrent] = useState(0);

  if (slides.length === 0) return null;

  const slide = slides[current];
  const lines = slide.split('\n');
  const title = lines[0]?.replace(/^#+\s*/, '') || '';
  const body = lines.slice(1).join('\n');

  return (
    <div className="carousel-container">
      <div className="carousel-nav">
        <button
          type="button"
          className="carousel-nav-btn"
          disabled={current === 0}
          onClick={() => setCurrent(c => Math.max(0, c - 1))}
        >
          <AppIcon name="chevronRight" size={16} className="carousel-previous-icon" /> 이전
        </button>
        <div className="carousel-dots">
          {slides.map((_, i) => (
            <button
              key={slides[i]}
              type="button"
              className={`carousel-dot ${i === current ? 'active' : ''}`}
              onClick={() => setCurrent(i)}
              aria-label={`슬라이드 ${i + 1}로 이동`}
            />
          ))}
        </div>
        <button
          type="button"
          className="carousel-nav-btn"
          disabled={current === slides.length - 1}
          onClick={() => setCurrent(c => Math.min(slides.length - 1, c + 1))}
        >
          다음 <AppIcon name="chevronRight" size={16} />
        </button>
      </div>
      <div className="carousel-slide">
        {title && <h4>{title}</h4>}
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          rehypePlugins={[rehypeHighlight, rehypeRaw, [rehypeSanitize, markdownSanitizeSchema]]}
        >
          {body}
        </ReactMarkdown>
      </div>
    </div>
  );
};


export function ChatMarkdown({ content }: { readonly content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      rehypePlugins={[rehypeHighlight, rehypeRaw, [rehypeSanitize, markdownSanitizeSchema]]}
      components={{
        table({ children }) {
          return <div className="agk-table-container"><table className="agk-markdown-table">{children}</table></div>;
        },
        code({ children }) {
          return <code className="inline-code">{children}</code>;
        },
        pre({ children }) {
          const child = React.Children.toArray(children)[0];
          if (!React.isValidElement<{ className?: string; children?: React.ReactNode }>(child)) return <pre>{children}</pre>;
          const language = extractLanguage(child.props.className);
          const code = extractCodeText(child.props.children).replace(/\n$/, '');
          if (language === 'mermaid') return <MermaidDiagram code={code} />;
          if (language === 'carousel') {
            const slides = code.split(/<!--\s*slide\s*-->/).filter(Boolean).map(slide => slide.trim());
            return <CarouselView slides={slides} />;
          }
          return <ChatCodeBlock className={child.props.className}>{child.props.children}</ChatCodeBlock>;
        },
        blockquote({ children }) {
          return <blockquote>{children}</blockquote>;
        },
        a({ href, children }) {
          return <a href={href} target="_blank" rel="noopener noreferrer" className="agk-markdown-link">{children}</a>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
