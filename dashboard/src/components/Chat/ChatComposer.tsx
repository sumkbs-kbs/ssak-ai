import type { ChangeEvent, KeyboardEvent, ReactNode, RefObject } from 'react';
import { AppIcon } from '../UI/AppIcon';

type ChatComposerAttachment = {
  readonly name: string;
  readonly mime_type: string;
  readonly bytes: number;
};

type ChatComposerProps = {
  readonly inputText: string;
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly attachments: readonly ChatComposerAttachment[];
  readonly isStreaming: boolean;
  readonly isTransitioning?: boolean;
  readonly tools: ReactNode;
  readonly modelSelector: ReactNode;
  readonly onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  readonly onRemoveAttachment: (name: string, bytes: number) => void;
  readonly onSend: () => void;
  readonly onStop: () => void;
};

export function ChatComposer({
  inputText, textareaRef, attachments, isStreaming, isTransitioning = false, tools, modelSelector,
  onChange, onKeyDown, onRemoveAttachment, onSend, onStop,
}: ChatComposerProps) {
  return (
    <div className="agk-composer-card">
      <div className="agk-input-main-card">
        {attachments.length > 0 && (
          <div className="agk-attachment-chips" data-testid="chat-attachment-chips">
            {attachments.map((attachment) => (
              <span
                key={`${attachment.name}:${attachment.bytes}`}
                className="agk-attachment-chip"
                data-testid="chat-attachment-chip"
                data-attachment-name={attachment.name}
                data-attachment-mime={attachment.mime_type}
                data-attachment-bytes={attachment.bytes}
              >
                <AppIcon name="paperclip" size={14} />
                <span>{attachment.name} ({(attachment.bytes / 1024).toFixed(0)}KB)</span>
                <button
                  type="button"
                  aria-label={`${attachment.name} 첨부 제거`}
                  onClick={() => onRemoveAttachment(attachment.name, attachment.bytes)}
                >
                  <AppIcon name="close" size={14} />
                </button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={textareaRef}
          id="chat-input"
          className="codex-textarea"
          placeholder="질문이나 작업 내용을 입력하세요"
          rows={1}
          value={inputText}
          onChange={onChange}
          onKeyDown={onKeyDown}
          aria-label="메시지 입력"
          aria-describedby="chat-composer-hint"
        />
        <div className="agk-chip-toolbar">
          {tools}
          <div className="agk-chip-group agk-composer-actions">
            {modelSelector}
            <button type="button" className="mic-action-btn" disabled title="음성 입력 미연결" aria-label="음성 입력 미연결">
              <AppIcon name="microphone" size={18} />
            </button>
            {isStreaming ? (
              <button type="button" className="soundwave-circle-btn stop send-btn" onClick={onStop} title="생성 중단" aria-label="생성 중단">
                <AppIcon name="stop" size={18} />
              </button>
            ) : (
              <button
                type="button"
                className="soundwave-circle-btn send-mode send-btn"
                onClick={onSend}
                disabled={isTransitioning || !inputText.trim()}
                title={isTransitioning ? '대화 동기화 중' : '메시지 전송'}
                aria-label="메시지 전송"
              >
                <AppIcon name="arrowUp" size={20} />
              </button>
            )}
          </div>
        </div>
      </div>
      <span id="chat-composer-hint" className="visually-hidden">Enter로 전송, Shift+Enter로 줄바꿈</span>
    </div>
  );
}
