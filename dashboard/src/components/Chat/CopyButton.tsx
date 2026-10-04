import { useCallback, useEffect, useRef, useState } from 'react';
import { AppIcon } from '../UI/AppIcon';

type CopyState = 'idle' | 'pending' | 'copied' | 'error';

interface CopyButtonProps {
  readonly content: string;
  readonly label: string;
  readonly className?: string;
}

export function CopyButton({ content, label, className = 'msg-action-btn' }: CopyButtonProps) {
  const [result, setResult] = useState<{ readonly content: string; readonly state: CopyState }>({ content, state: 'idle' });
  const state = result.content === content ? result.state : 'idle';
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current += 1;
    return () => { requestVersion.current += 1; };
  }, [content]);

  useEffect(() => {
    if (state !== 'copied') return undefined;
    const timer = setTimeout(() => setResult({ content, state: 'idle' }), 2000);
    return () => clearTimeout(timer);
  }, [content, state]);

  const handleCopy = useCallback(async () => {
    if (!navigator.clipboard?.writeText) {
      setResult({ content, state: 'error' });
      return;
    }
    const version = requestVersion.current;
    setResult({ content, state: 'pending' });
    try {
      await navigator.clipboard.writeText(content);
      if (requestVersion.current === version) setResult({ content, state: 'copied' });
    } catch (error) {
      if (!(error instanceof Error) && !(error instanceof DOMException)) throw error;
      if (requestVersion.current === version) setResult({ content, state: 'error' });
    }
  }, [content]);

  const accessibleLabel = state === 'copied' ? `${label}됨`
    : state === 'pending' ? `${label} 중`
    : state === 'error' ? `${label} 실패, 다시 시도`
    : label;

  return (
    <>
      <button
        type="button"
        className={`${className} ${state === 'copied' ? 'copied' : ''}`}
        onClick={() => { void handleCopy(); }}
        disabled={state === 'pending'}
        aria-label={accessibleLabel}
        title={accessibleLabel}
        aria-live="polite"
      >
        <AppIcon name={state === 'copied' ? 'check' : 'copy'} size={16} />
        <span>{state === 'copied' ? '복사됨' : state === 'pending' ? '복사 중' : '복사'}</span>
      </button>
      {state === 'error' && (
        <span className="message-copy-feedback" role="status">복사하지 못했습니다. 다시 시도해 주세요.</span>
      )}
    </>
  );
}
