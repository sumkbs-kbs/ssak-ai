import { NavLink, useLocation } from 'react-router-dom';
import { AppIcon } from '../UI/AppIcon';

const PRIMARY_ROUTES = [
  { to: '/chat', label: '대화', icon: 'chat' },
  { to: '/studio', label: '스튜디오', icon: 'code' },
  { to: '/models', label: '모델', icon: 'layers' },
] as const;

const MORE_ROUTES = [
  { to: '/start', label: '에이전트 시작', icon: 'plus' },
  { to: '/agent', label: '에이전트', icon: 'activity' },
  { to: '/wiki', label: '위키', icon: 'file' },
  { to: '/skills', label: '스킬', icon: 'sparkles' },
  { to: '/data-extraction', label: '데이터 추출', icon: 'layers' },
  { to: '/git', label: 'Git', icon: 'git' },
  { to: '/history', label: '파일 변경 기록', icon: 'history' },
  { to: '/plugins', label: '플러그인', icon: 'puzzle' },
  { to: '/mutation', label: '변이 대시보드', icon: 'activity' },
] as const;

interface WorkspaceNavigationProps {
  readonly onNewChat: () => void;
  readonly onSearch: () => void;
  readonly onNavigate: () => void;
}

export function WorkspaceNavigation({ onNewChat, onSearch, onNavigate }: WorkspaceNavigationProps) {
  const location = useLocation();
  const moreActive = MORE_ROUTES.some(route => location.pathname.startsWith(route.to));
  return (
    <nav className="workspace-primary-nav" aria-label="주요 메뉴">
      <button type="button" className="workspace-nav-link workspace-new-chat" onClick={onNewChat}>
        <AppIcon name="plus" /><span>새 채팅</span>
      </button>
      <button type="button" className="workspace-nav-link" onClick={onSearch} title="검색 (⌘K / Ctrl+K)">
        <AppIcon name="search" /><span>검색</span><kbd className="workspace-nav-shortcut">⌘K</kbd>
      </button>
      {PRIMARY_ROUTES.map(route => (
        <NavLink key={route.to} to={route.to} onClick={onNavigate} className={({ isActive }) => `workspace-nav-link ${isActive ? 'active' : ''}`}>
          <AppIcon name={route.icon} /><span>{route.label}</span>
        </NavLink>
      ))}
      <details className="workspace-more-nav" open={moreActive || undefined}>
        <summary className="workspace-nav-link"><AppIcon name="more" /><span>더 보기</span><span className="workspace-nav-chevron"><AppIcon name="chevronDown" size={16} /></span></summary>
        <div className="workspace-more-links">
          {MORE_ROUTES.map(route => (
            <NavLink key={route.to} to={route.to} onClick={onNavigate} className={({ isActive }) => `workspace-nav-link ${isActive ? 'active' : ''}`}>
              <AppIcon name={route.icon} /><span>{route.label}</span>
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}
