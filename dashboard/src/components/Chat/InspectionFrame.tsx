import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useModalDialog } from '../../hooks/useModalDialog';
import { useUiStore } from '../../stores/uiStore';
import { isMonacoFocused } from '../../utils/domHelpers';
import { AppIcon } from '../UI/AppIcon';
import type { EnvPanelTab } from './EnvironmentPanel';

const TABS = [
  { id: 'env', label: '환경' },
  { id: 'code', label: '코드' },
  { id: 'changes', label: '변경' },
] as const;
const COMPACT_QUERY = '(max-width: 1279px)';

interface InspectionFrameProps {
  readonly open: boolean;
  readonly tab: EnvPanelTab;
  readonly onTabChange: (tab: EnvPanelTab) => void;
  readonly onClose: () => void;
  readonly changeCount: number;
  readonly children: ReactNode;
}

export function InspectionFrame({ open, tab, onTabChange, onClose, changeCount, children }: InspectionFrameProps) {
  const [compact, setCompact] = useState(() => window.matchMedia(COMPACT_QUERY).matches);
  const foregroundDialogVisible = useUiStore((state) => state.commandPaletteVisible || state.folderBrowserVisible);
  const containerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const tabRefs = useRef<Partial<Record<EnvPanelTab, HTMLButtonElement | null>>>({});
  const id = useId();

  useEffect(() => {
    const media = window.matchMedia(COMPACT_QUERY);
    const updateCompact = () => setCompact(media.matches);
    media.addEventListener('change', updateCompact);
    return () => media.removeEventListener('change', updateCompact);
  }, []);

  useModalDialog({ active: open && compact && !foregroundDialogVisible, containerRef, initialFocusRef: closeRef });

  useEffect(() => {
    if (open && compact && foregroundDialogVisible) onClose();
  }, [open, compact, foregroundDialogVisible, onClose]);

  useEffect(() => {
    if (!open || !compact) return undefined;
    const handOffToShortcutGuide = (event: globalThis.KeyboardEvent) => {
      const opensGuide = ((event.metaKey || event.ctrlKey) && event.key === '/') ||
        (event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !isMonacoFocused());
      if (opensGuide) onClose();
    };
    document.addEventListener('keydown', handOffToShortcutGuide);
    return () => document.removeEventListener('keydown', handOffToShortcutGuide);
  }, [open, compact, onClose]);

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    const currentIndex = TABS.findIndex((option) => option.id === tab);
    let nextIndex: number;
    switch (event.key) {
      case 'ArrowRight': nextIndex = (currentIndex + 1) % TABS.length; break;
      case 'ArrowLeft': nextIndex = (currentIndex + TABS.length - 1) % TABS.length; break;
      case 'Home': nextIndex = 0; break;
      case 'End': nextIndex = TABS.length - 1; break;
      default: return;
    }
    event.preventDefault();
    const next = TABS[nextIndex];
    if (!next) return;
    onTabChange(next.id);
    tabRefs.current[next.id]?.focus();
  }

  if (!open) return null;

  return (
    <div
      ref={containerRef}
      className={`workspace-inspection-container ${compact ? 'is-compact' : ''}`}
      role={compact ? 'dialog' : undefined}
      aria-modal={compact ? true : undefined}
      aria-labelledby={compact ? `${id}-title` : undefined}
      onKeyDown={(event) => {
        if (!compact || event.key !== 'Escape' || event.defaultPrevented) return;
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }}
    >
      {compact && <div className="workspace-inspection-backdrop" aria-hidden="true" onPointerDown={onClose} />}
      <aside className="agk-env-panel" aria-labelledby={`${id}-title`}>
        <div className="workspace-inspection-header">
          <h2 id={`${id}-title`} className="workspace-inspection-title">검사</h2>
          <button ref={closeRef} type="button" className="env-close-btn" onClick={onClose} aria-label="패널 닫기">
            <AppIcon name="close" size={18} />
          </button>
        </div>
        <div className="env-tab-bar" role="tablist" aria-label="검사 항목">
          {TABS.map((option) => (
            <button
              key={option.id}
              ref={(element) => { tabRefs.current[option.id] = element; }}
              type="button"
              role="tab"
              id={`${id}-${option.id}-tab`}
              aria-controls={tab === option.id ? `${id}-${option.id}-panel` : undefined}
              aria-selected={tab === option.id}
              tabIndex={tab === option.id ? 0 : -1}
              className={`env-tab ${tab === option.id ? 'active' : ''}`}
              onClick={() => onTabChange(option.id)}
              onKeyDown={handleTabKeyDown}
            >
              {option.label}
              {option.id === 'changes' && changeCount > 0 && <span className="env-tab-count">{changeCount}</span>}
            </button>
          ))}
        </div>
        <div
          className="workspace-inspection-tabpanel"
          id={`${id}-${tab}-panel`}
          role="tabpanel"
          aria-labelledby={`${id}-${tab}-tab`}
          tabIndex={0}
        >
          {children}
        </div>
      </aside>
    </div>
  );
}
