/**
 * ChatActivity — Codex/Ssak-Ai-style activity feed pieces
 * ===========================================================
 * - WorkingIndicator: live "Working…" row with elapsed time
 * - StreamErrorBanner: Ssak-Ai error card ("exceeded retry limit…")
 * - FileEditCard: "파일 N개를 편집했습니다 +A −D" summary with
 *   expandable per-file rows, 실행 취소 / 리뷰 actions
 * - QueuedMessagesCard: Codex queued-messages card
 *   ("Sends after agent finishes working")
 */

import React, { useState } from 'react';
import { useChangeStore, type ProposedChange } from '../../stores/changeStore';

/* ─── Working indicator ─────────────────────────────────────── */

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

export const WorkingIndicator: React.FC<Readonly<{ elapsed: number; status?: string | null }>> = ({ elapsed, status }) => (
  <div className="agk-working-row" role="status" aria-label="에이전트 작업 중">
    <span className="working-dots" aria-hidden="true"><i /><i /><i /></span>
    <span className="working-label" title={status ?? undefined}>{status ?? 'Working…'}</span>
    <span className="working-elapsed">{formatElapsed(elapsed)}</span>
  </div>
);

/* ─── Stream error banner ───────────────────────────────────── */

export const StreamErrorBanner: React.FC<{ message: string; onRetry?: () => void }> = ({
  message,
  onRetry,
}) => (
  <div className="agk-error-banner" role="alert">
    <span className="error-banner-icon">⚠</span>
    <span className="error-banner-text">{message}</span>
    {onRetry && (
      <button type="button" className="error-banner-retry" onClick={onRetry}>
        다시 시도
      </button>
    )}
  </div>
);

/* ─── File edit summary card ────────────────────────────────── */

interface FileEditCardProps {
  onReview: () => void;
  onDiscard: () => void;
}

export const FileEditCard: React.FC<FileEditCardProps> = ({ onReview, onDiscard }) => {
  const changes = useChangeStore((s) => s.changes);
  const [expanded, setExpanded] = useState<boolean>(false);

  if (changes.length === 0) return null;

  const adds = changes.reduce((sum, c) => sum + (c.diffStats?.additions ?? 0), 0);
  const dels = changes.reduce((sum, c) => sum + (c.diffStats?.deletions ?? 0), 0);
  const visible: ProposedChange[] = expanded ? changes.slice(0, 12) : changes.slice(0, 3);
  const hiddenCount = changes.length - visible.length;

  return (
    <div className="agk-file-edit-card">
      <div className="file-edit-header">
        <span className="file-edit-icon">⎘</span>
        <div className="file-edit-title-wrap">
          <span className="file-edit-title">파일 {changes.length}개를 편집했습니다</span>
          <span className="file-edit-stats">
            <span className="stat-add">+{adds.toLocaleString()}</span>
            <span className="stat-del">−{dels.toLocaleString()}</span>
          </span>
        </div>
        <div className="file-edit-actions">
          <button type="button" className="file-edit-btn ghost" onClick={onDiscard}>
            실행 취소
          </button>
          <button type="button" className="file-edit-btn outline" onClick={onReview}>
            리뷰 ↩
          </button>
        </div>
      </div>

      <div className="file-edit-rows">
        {visible.map((c) => (
          <div key={c.id} className="file-edit-row" title={c.filePath}>
            <span className="file-edit-path">{c.filePath}</span>
            <span className="file-edit-row-stats">
              <span className="stat-add">+{c.diffStats?.additions ?? 0}</span>
              <span className="stat-del">−{c.diffStats?.deletions ?? 0}</span>
            </span>
          </div>
        ))}
      </div>

      {changes.length > 3 && (
        <button
          type="button"
          className="file-edit-expand"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '접기' : `${hiddenCount}개 파일 더 보기`} {expanded ? '⌃' : '⌄'}
        </button>
      )}
    </div>
  );
};

/* ─── Queued messages card ──────────────────────────────────── */

interface QueuedMessagesCardProps {
  items: string[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onSendNow: (index: number) => void;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onMoveUp?: (index: number) => void;
  onMoveDown?: (index: number) => void;
  onReorder?: (fromIndex: number, toIndex: number) => void;
  onClearAll?: () => void;
}

export const QueuedMessagesCard: React.FC<QueuedMessagesCardProps> = ({
  items,
  collapsed,
  onToggleCollapse,
  onSendNow,
  onEdit,
  onDelete,
  onMoveUp,
  onMoveDown,
  onReorder,
  onClearAll,
}) => {
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = React.useState<number | null>(null);

  if (items.length === 0) return null;

  return (
    <div className="agk-queued-card">
      <button
        type="button"
        className="queued-header"
        onClick={onToggleCollapse}
        aria-expanded={!collapsed}
      >
        <span className="queued-title">Queued Messages</span>
        <span className="queued-count">{items.length}</span>
        <span className="queued-subtitle">Sends after agent finishes working</span>
        <span className={`env-chevron ${collapsed ? '' : 'open'}`}>⌄</span>
      </button>
      {!collapsed && (
        <>
          <div className="queued-rows">
            {items.map((text, i) => (
              <div
                key={`${i}:${text.slice(0, 24)}`}
                className={`queued-row ${dragIndex === i ? 'dragging' : ''} ${dragOverIndex === i ? 'drag-over' : ''}`}
                draggable={Boolean(onReorder)}
                onDragStart={(e) => {
                  e.dataTransfer.setData('text/plain', String(i));
                  setDragIndex(i);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (dragOverIndex !== i) setDragOverIndex(i);
                }}
                onDragLeave={() => setDragOverIndex(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOverIndex(null);
                  const from = dragIndex;
                  if (from !== null && from !== i && onReorder) {
                    onReorder(from, i);
                  }
                  setDragIndex(null);
                }}
                onDragEnd={() => {
                  setDragIndex(null);
                  setDragOverIndex(null);
                }}
              >
                {onReorder && items.length > 1 && (
                  <span className="queued-drag-handle" title="드래그하여 순서 변경" aria-hidden="true">
                    ⋮⋮
                  </span>
                )}
                <span className="queued-text" title={text}>{text}</span>
                <span className="queued-actions">
                  {onMoveUp && i > 0 && (
                    <button
                      type="button"
                      className="queued-action-btn"
                      title="위로 이동"
                      aria-label="위로 이동"
                      onClick={() => onMoveUp(i)}
                    >
                      ↑
                    </button>
                  )}
                  {onMoveDown && i < items.length - 1 && (
                    <button
                      type="button"
                      className="queued-action-btn"
                      title="아래로 이동"
                      aria-label="아래로 이동"
                      onClick={() => onMoveDown(i)}
                    >
                      ↓
                    </button>
                  )}
                  <button
                    type="button"
                    className="queued-action-btn"
                    title="지금 보내기"
                    aria-label="지금 보내기"
                    onClick={() => onSendNow(i)}
                  >
                    →
                  </button>
                  <button
                    type="button"
                    className="queued-action-btn"
                    title="편집"
                    aria-label="대기 메시지 편집"
                    onClick={() => onEdit(i)}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="queued-action-btn danger"
                    title="삭제"
                    aria-label="대기 메시지 삭제"
                    onClick={() => onDelete(i)}
                  >
                    🗑
                  </button>
                </span>
              </div>
            ))}
          </div>
          {onClearAll && items.length > 1 && (
            <div className="queued-footer">
              <button
                type="button"
                className="queued-clear-btn"
                onClick={onClearAll}
                title="모든 대기 메시지 삭제"
              >
                대기열 모두 비우기
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};
