import { useEffect, useId, useRef, useState, type FC } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useUiStore } from '../../stores/uiStore';
import { useModalDialog } from '../../hooks/useModalDialog';
import { isMonacoFocused } from '../../utils/domHelpers';
import { AppIcon } from '../UI/AppIcon';

interface ChatHistoryProps {
  readonly visible: boolean;
  readonly onClose: () => void;
}

const ChatHistory: FC<ChatHistoryProps> = ({ visible, onClose }) => {
  const { sessions, activeSessionId, switchSession, deleteSession, createNewSession, updateSessionTitle } = useChatStore();
  const commandPaletteVisible = useUiStore(state => state.commandPaletteVisible);
  const folderBrowserVisible = useUiStore(state => state.folderBrowserVisible);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const modalHandoff = commandPaletteVisible || folderBrowserVisible;
  const active = visible && !modalHandoff;

  useModalDialog({ active, containerRef: overlayRef, initialFocusRef: closeRef });

  useEffect(() => {
    if (visible && modalHandoff) onClose();
  }, [visible, modalHandoff, onClose]);

  useEffect(() => {
    if (!active) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const shortcutGuide = ((event.metaKey || event.ctrlKey) && event.key === '/') ||
        (event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !isMonacoFocused());
      if (shortcutGuide) { onClose(); return; }
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [active, onClose]);

  if (!active) return null;

  const saveTitle = (sessionId: string) => {
    const title = editTitle.trim();
    if (title) updateSessionTitle(sessionId, title);
    setEditingId(null);
  };

  return (
    <div ref={overlayRef} className="workspace-history-overlay">
      <button type="button" className="workspace-history-backdrop" aria-hidden="true" tabIndex={-1} onClick={onClose} />
      <aside className="workspace-history-drawer" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className="workspace-history-header">
          <button ref={closeRef} type="button" className="workspace-icon-button" aria-label="대화 기록 닫기" title="대화 기록 닫기" onClick={onClose}><AppIcon name="close" /></button>
          <div><h2 id={titleId}>대화 기록</h2><span className="workspace-history-count">대화 {sessions.length}개</span></div>
          <div className="workspace-history-actions"><button type="button" className="workspace-icon-button" aria-label="새 채팅" title="새 채팅" onClick={() => { createNewSession(); onClose(); }}><AppIcon name="plus" /></button></div>
        </header>
        <div className="workspace-history-scroll" role="region" aria-label="저장된 대화" tabIndex={0}>
          {sessions.length === 0 ? (
            <div className="workspace-history-empty"><AppIcon name="chat" size={28} /><h3>저장된 대화가 없습니다</h3><p>이 프로젝트의 대화 기록이 여기에 표시됩니다.</p><button type="button" className="workspace-nav-link" onClick={() => { createNewSession(); onClose(); }}><AppIcon name="plus" size={18} /><span>새 채팅 시작하기</span></button></div>
          ) : (
            <ul className="workspace-history-list">
              {sessions.map(session => (
                <li key={session.id} className="workspace-history-item" data-active={session.id === activeSessionId}>
                  {editingId === session.id ? (
                    <input type="text" className="workspace-history-title-input" aria-label="대화 제목" value={editTitle} autoFocus onChange={event => setEditTitle(event.target.value)} onBlur={() => saveTitle(session.id)} onKeyDown={event => {
                      if (event.key === 'Enter' && !event.nativeEvent.isComposing) { event.preventDefault(); saveTitle(session.id); }
                      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setEditingId(null); }
                    }} />
                  ) : (
                    <button type="button" className="workspace-history-select" aria-label={session.title || '새 대화'} aria-current={session.id === activeSessionId ? 'page' : undefined} onClick={() => { switchSession(session.id); onClose(); }}><span>{session.title || '새 대화'}</span><time dateTime={session.updatedAt}>{new Date(session.updatedAt).toLocaleString('ko-KR')}</time></button>
                  )}
                  <div className="workspace-history-item-actions">
                    <button type="button" className="workspace-icon-button" aria-label={`${session.title || '대화'} 제목 수정`} title="대화 제목 수정" onClick={() => { setEditingId(session.id); setEditTitle(session.title || '새 대화'); }}><AppIcon name="edit" size={16} /></button>
                    <button type="button" className="workspace-icon-button" aria-label={`${session.title || '대화'} 삭제`} title="대화 삭제" onClick={() => deleteSession(session.id)}><AppIcon name="trash" size={16} /></button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
};

export default ChatHistory;
