import React, { useCallback } from 'react';
import type { ChatMessage as ChatMessageType } from '../../stores/chatStore';
import { formatResponseMarkdown, presentResponse } from '../../utils/responsePresentation';
import { searchFailureNotice } from '../../utils/searchFailure';
import { CopyButton } from './CopyButton';
import { MessageMetadata } from './MessageMetadata';
import { ChatMarkdown } from './ChatMarkdown';

interface Props {
  readonly message: ChatMessageType;
}

declare global {
  interface Window {
    previewArtifact?: (filePath: string, fileName: string) => Promise<void>;
  }
}

// ─── Message Action Buttons ─────────────────────────────────────────
const MessageActions: React.FC<{ content: string }> = ({ content }) => {
  const clean = content.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

  return (
    <div className="message-actions">
      <CopyButton content={clean} label="응답 복사" />
    </div>
  );
};

function ChatMessageComponent({ message }: Props) {
  const { role, content } = message;
  const handleBubbleClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target instanceof Element
      ? event.target.closest<HTMLElement>('[data-agk-action]')
      : null;
    if (!target || !event.currentTarget.contains(target)) return;

    const action = target.dataset.agkAction;
    if (action === 'approval') {
      const text = target.dataset.response;
      if (text) {
        window.dispatchEvent(new CustomEvent('agk:approval-response', { detail: { text } }));
      }
      return;
    }

    if (action === 'preview') {
      const filePath = target.dataset.path;
      const fileName = target.dataset.name;
      if (filePath && fileName) {
        void window.previewArtifact?.(filePath, fileName);
      }
    }
  }, []);

  const handleBubbleKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const target = event.target instanceof Element
      ? event.target.closest<HTMLElement>('[data-agk-action]')
      : null;
    if (target && !(target instanceof HTMLButtonElement)) target.click();
  }, []);

  if (!content && role === 'assistant') return null;
  if (!content) return null;

  // 사용자 발화는 절대 실패로 재해석하지 않는다(사용자가 "Search Error:" 를 인용할 수 있다).
  const presentation = role === 'assistant' ? presentResponse(content) : { body: content, details: [] };
  const failure = role === 'user' ? null : searchFailureNotice(content) ?? searchFailureNotice(presentation.body);
  const displayContent = role === 'assistant' ? formatResponseMarkdown(presentation.body) : content;

  return (
    <article className={`message ${role}`} aria-label={role === 'user' ? '내 메시지' : 'SSAK-AI 응답'}>
      <div
        className={`bubble ${role === 'assistant' ? 'antigravity-assistant-bubble' : 'antigravity-user-bubble'}`}
        role={role === 'assistant' ? 'group' : undefined}
        onClick={role === 'assistant' ? handleBubbleClick : undefined}
        onKeyDown={role === 'assistant' ? handleBubbleKeyDown : undefined}
      >
        {role === 'user' ? (
          <span className="user-message-text">{content}</span>
        ) : failure ? (
          <div
            role="alert"
            data-testid="chat-error-notice"
            data-error-code={failure.code}
            className="message-error-notice"
          >
            <span className="message-error-title">
              이 응답은 실패했습니다 ({failure.code})
            </span>
            <span className="message-error-detail">{failure.detail}</span>
            {/* 원문은 접어 둔다 — 진단에는 필요하고, 답변처럼 읽히면 안 된다. */}
            <details>
              <summary>원문 보기</summary>
              <pre>
                {content}
              </pre>
            </details>
          </div>
        ) : (
          <div className="antigravity-markdown-body">
            <ChatMarkdown content={displayContent} />
          </div>
        )}
        {role === 'assistant' && (message.agentMeta || presentation.details.length > 0 || !failure) && (
          <div className="message-footer">
            {!failure && <MessageActions content={presentation.body} />}
            <MessageMetadata
              metadata={message.agentMeta}
              details={presentation.details}
              original={presentation.details.length > 0 ? content : null}
            />
          </div>
        )}
      </div>
    </article>
  );
}

/**
 * Custom comparator: only re-render if the message content/role/id actually changed.
 * This prevents ALL chat messages from re-rendering when a new message is added.
 */
export function chatMessageAreEqual(prevProps: Props, nextProps: Props): boolean {
  const a = prevProps.message;
  const b = nextProps.message;
  if (a.id !== b.id) return false;
  if (a.role !== b.role) return false;
  if (a.content !== b.content) return false;
  if (a.agentMeta !== b.agentMeta) return false;
  return true;
}

const ChatMessage = React.memo(ChatMessageComponent, chatMessageAreEqual);
ChatMessage.displayName = 'ChatMessage';

export default ChatMessage;
