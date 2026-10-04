import React from 'react';
import { AppIcon } from '../UI/AppIcon';
import { CopyButton } from './CopyButton';

export function extractCodeText(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (React.isValidElement<{ children?: React.ReactNode }>(children)) {
    return extractCodeText(children.props.children);
  }
  if (Array.isArray(children)) return children.map(extractCodeText).join('');
  return '';
}

function trimTrailingNewline(children: React.ReactNode): React.ReactNode {
  if (typeof children === 'string') return children.replace(/\n$/, '');
  if (Array.isArray(children)) {
    const last = children.at(-1);
    if (typeof last === 'string') return [...children.slice(0, -1), last.replace(/\n$/, '')];
  }
  return children;
}

export function extractLanguage(className?: string): string {
  return className?.match(/language-([\w-]+)/)?.[1] ?? '';
}

interface CodeBlockProps {
  readonly className?: string;
  readonly children: React.ReactNode;
}

export function ChatCodeBlock({ className, children }: CodeBlockProps) {
  const language = extractLanguage(className);
  const code = extractCodeText(children).replace(/\n$/, '');
  return (
    <div className="code-block">
      <div className="code-block-header">
        <div className="code-block-lang">
          <AppIcon name="code" size={16} />
          <span>{language || 'code'}</span>
        </div>
        <CopyButton content={code} label="코드 복사" className="code-block-copy-btn" />
      </div>
      <pre>
        <code className={className}>{trimTrailingNewline(children)}</code>
      </pre>
    </div>
  );
}
