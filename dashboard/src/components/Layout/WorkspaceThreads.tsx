import { useId, useState } from 'react';
import type { ChatSession } from '../../stores/chatStore';
import { AppIcon } from '../UI/AppIcon';

interface ThreadActions {
  readonly onSelect: (id: string) => void;
  readonly onRename: (id: string, title: string) => void;
  readonly onDelete: (session: ChatSession) => void;
}

interface WorkspaceThreadProps extends ThreadActions {
  readonly session: ChatSession;
  readonly selected: boolean;
}

function WorkspaceThread({ session, selected, onSelect, onRename, onDelete }: WorkspaceThreadProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);
  const saveTitle = () => {
    const value = title.trim();
    if (value && value !== session.title) onRename(session.id, value);
    setEditing(false);
  };
  return (
    <li className="workspace-thread" data-selected={selected}>
      {editing ? (
        <input className="workspace-thread-edit session-title-edit-input" aria-label="대화 제목" value={title} autoFocus onChange={event => setTitle(event.target.value)} onBlur={saveTitle} onKeyDown={event => {
          if (event.key === 'Enter' && !event.nativeEvent.isComposing) { event.preventDefault(); saveTitle(); }
          if (event.key === 'Escape') { event.stopPropagation(); setEditing(false); }
        }} />
      ) : (
        <>
          <button type="button" className="workspace-thread-link" aria-current={selected ? 'page' : undefined} title={session.title || '새 대화'} onClick={() => onSelect(session.id)}><AppIcon name="chat" size={16} /><span>{session.title || '새 대화'}</span></button>
          <div className="workspace-thread-actions">
            <button type="button" className="workspace-icon-button" aria-label={`${session.title || '대화'} 제목 수정`} title="대화 제목 수정" onClick={() => { setTitle(session.title); setEditing(true); }}><AppIcon name="edit" size={14} /></button>
            <button type="button" className="workspace-icon-button" aria-label={`${session.title || '대화'} 삭제`} title="대화 삭제" onClick={() => onDelete(session)}><AppIcon name="trash" size={14} /></button>
          </div>
        </>
      )}
    </li>
  );
}

interface WorkspaceThreadsProps extends ThreadActions {
  readonly sessions: readonly ChatSession[];
  readonly activeSessionId: string | null;
  readonly onNewChat: () => void;
}

export function WorkspaceThreads({ sessions, activeSessionId, onNewChat, ...actions }: WorkspaceThreadsProps) {
  const headingId = useId();
  return (
    <section className="workspace-threads" aria-labelledby={headingId}>
      <div className="workspace-section-heading"><h2 id={headingId}>최근 대화</h2></div>
      {sessions.length === 0 ? <button type="button" className="workspace-nav-link workspace-empty-threads workspace-sidebar-empty" onClick={onNewChat}><AppIcon name="plus" size={16} /><span>첫 대화 시작하기</span></button> : <ul className="workspace-thread-list">{sessions.map(session => <WorkspaceThread key={session.id} session={session} selected={activeSessionId === session.id} {...actions} />)}</ul>}
    </section>
  );
}
