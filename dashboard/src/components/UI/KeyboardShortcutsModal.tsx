/**
 * KeyboardShortcutsModal — Keyboard shortcuts reference guide
 * ============================================================
 * Shows all available keyboard shortcuts organized by category.
 * Triggered by pressing `?` or `Cmd+/`.
 * Inspired by VS Code, Cursor, and GitHub keyboard shortcuts.
 */

import React, { useCallback, useEffect, useRef } from 'react';
import { useModalDialog } from '../../hooks/useModalDialog';

export interface ShortcutEntry {
  keys: string[];
  description: string;
  category: 'editor' | 'navigation' | 'git' | 'general' | 'chat' | 'debug';
}

const ALL_SHORTCUTS: ShortcutEntry[] = [
  // Editor
  { keys: ['Ctrl+S'], description: '파일 저장', category: 'editor' },
  { keys: ['Ctrl+K'], description: '인라인 편집 (Cursor 스타일)', category: 'editor' },
  { keys: ['Ctrl+F'], description: '파일 내 검색', category: 'editor' },
  { keys: ['Ctrl+H'], description: '파일 내 찾아바꾸기', category: 'editor' },
  { keys: ['Ctrl+D'], description: '다음 선택 추가', category: 'editor' },
  { keys: ['Alt+↑/↓'], description: '라인 위/아래 이동', category: 'editor' },
  { keys: ['Shift+Alt+↑/↓'], description: '라인 위/아래 복사', category: 'editor' },
  { keys: ['Ctrl+Shift+F'], description: '파일 전체 검색 (Search in Files)', category: 'editor' },
  { keys: ['Ctrl+Enter'], description: '인라인 제안 적용/요청', category: 'editor' },
  { keys: ['Tab'], description: '인라인 제안 승인', category: 'editor' },
  { keys: ['Esc'], description: '인라인 제안 취소 / 팔레트 닫기', category: 'editor' },

  // Navigation
  { keys: ['Ctrl+K'], description: '명령 팔레트 열기 (Monaco 밖에서)', category: 'navigation' },
  { keys: ['?', 'Cmd+/'], description: '키보드 단축키 가이드', category: 'navigation' },
  { keys: ['Ctrl+Tab'], description: '다음 탭으로 전환', category: 'navigation' },
  { keys: ['Ctrl+Shift+Tab'], description: '이전 탭으로 전환', category: 'navigation' },
  { keys: ['Ctrl+W'], description: '현재 탭 닫기', category: 'navigation' },
  { keys: ['Ctrl+`', 'Ctrl+J'], description: '터미널 토글', category: 'navigation' },
  { keys: ['Ctrl+B'], description: '사이드바 토글', category: 'navigation' },
  { keys: ['Ctrl+Shift+E'], description: '파일 탐색기 포커스', category: 'navigation' },

  // Chat
  { keys: ['Enter'], description: '메시지 전송', category: 'chat' },
  { keys: ['Shift+Enter'], description: '새 줄 삽입', category: 'chat' },
  { keys: ['Ctrl+↑'], description: '이전 메시지 불러오기', category: 'chat' },
  { keys: ['Ctrl+Shift+P'], description: '새 채팅 세션 생성', category: 'chat' },

  // Git
  { keys: ['Ctrl+Shift+G'], description: 'Git 패널 열기', category: 'git' },
  { keys: ['Ctrl+Enter'], description: '커밋 메시지 제출 (커밋 다이얼로그)', category: 'git' },
  { keys: ['Ctrl+Shift+`'], description: 'Git Graph 보기', category: 'git' },

  // General
  { keys: ['Ctrl+P'], description: '빠른 파일 열기', category: 'general' },
  { keys: ['Ctrl+Shift+P'], description: '명령 팔레트 (모든 명령)', category: 'general' },
  { keys: ['Ctrl+,', 'Cmd+,'], description: '설정 열기', category: 'general' },
  { keys: ['Ctrl+Shift+I'], description: '개발자 도구', category: 'general' },
  { keys: ['?', 'Cmd+/'], description: '키보드 단축키 보기', category: 'general' },
];

/* ─── KeyboardShortcutsModal ───────────────────────────────── */

interface KeyboardShortcutsModalProps {
  visible: boolean;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  editor: '⌨️ 에디터',
  navigation: '🧭 네비게이션',
  chat: '💬 채팅',
  git: '🐙 Git',
  general: '⚙️ 일반',
  debug: '🔧 디버그',
};

const KeyboardShortcutsModal: React.FC<KeyboardShortcutsModalProps> = ({ visible, onClose }) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useModalDialog({ active: visible, containerRef: dialogRef, initialFocusRef: closeButtonRef });

  // Close on Escape
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, onClose]);

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  }, [onClose]);

  // Group by category
  const grouped = ALL_SHORTCUTS.reduce<Record<string, ShortcutEntry[]>>((acc, entry) => {
    if (!acc[entry.category]) acc[entry.category] = [];
    acc[entry.category].push(entry);
    return acc;
  }, {});

  if (!visible) return null;

  return (
    <div className="modal-overlay" onClick={handleOverlayClick} role="presentation">
      <div
        ref={dialogRef}
        className="modal-content glass-panel shortcuts-modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="키보드 단축키"
        tabIndex={-1}
      >
        {/* Header */}
        <div className="shortcuts-header">
          <h3>⌨️ 키보드 단축키</h3>
          <button ref={closeButtonRef} className="icon-btn" onClick={onClose} aria-label="키보드 단축키 대화상자 닫기" style={{ fontSize: 12, padding: '4px 8px', color: 'var(--text-secondary)' }}>✕</button>
        </div>

        <div className="shortcuts-body">
          {Object.entries(grouped).map(([category, shortcuts]) => (
            <div key={category} className="shortcuts-group">
              <div className="shortcuts-group-title">{CATEGORY_LABELS[category] || category}</div>
              {shortcuts.map(shortcut => (
                <div key={`${shortcut.description}:${shortcut.keys.join('|')}`} className="shortcut-row">
                  <span className="shortcut-desc">{shortcut.description}</span>
                  <span className="shortcut-keys">
                    {shortcut.keys.map(keyCombo => (
                      <span key={keyCombo}>
                        <kbd className="shortcut-kbd">{keyCombo}</kbd>
                        {keyCombo !== shortcut.keys[shortcut.keys.length - 1] && <span className="shortcut-or">or</span>}
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="shortcuts-footer">
          <span className="shortcuts-footer-text">
            <kbd>Esc</kbd> to close
          </span>
        </div>
      </div>
    </div>
  );
};

export default KeyboardShortcutsModal;
