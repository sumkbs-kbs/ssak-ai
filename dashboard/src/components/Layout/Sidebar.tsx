import { useCallback, useEffect, useRef, useState, type FC } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useUiStore } from '../../stores/uiStore';
import { useChatStore, type ChatSession } from '../../stores/chatStore';
import { useFileStore } from '../../stores/fileStore';
import { useProjectStore } from '../../stores/projectStore';
import { useGitStore } from '../../stores/gitStore';
import type { ProjectRecord } from '../../api/clientSchema';
import { useModalDialog } from '../../hooks/useModalDialog';
import { isMonacoFocused } from '../../utils/domHelpers';
import { AppIcon } from '../UI/AppIcon';
import { WorkspaceNavigation } from './WorkspaceNavigation';
import { WorkspaceProjects } from './WorkspaceProjects';
import { WorkspaceThreads } from './WorkspaceThreads';

export const Sidebar: FC<{ readonly toggleTerminal?: () => void }> = ({ toggleTerminal }) => {
  const { commandPaletteVisible, folderBrowserVisible, setCommandPaletteVisible, setFolderBrowserVisible, addToast } = useUiStore();
  const { sessions, activeSessionId, createNewSession, switchSession, deleteSession, updateSessionTitle, saveToStorage } = useChatStore();
  const { setWorkspacePath, refreshTree } = useFileStore();
  const projects = useProjectStore(state => state.projects);
  const activeProjectId = useProjectStore(state => state.activeProjectId);
  const activeProjectPath = useProjectStore(state => state.activeProjectPath);
  const hydrateFromServer = useProjectStore(state => state.hydrateFromServer);
  const switchToProject = useProjectStore(state => state.switchToProject);
  const removeProject = useProjectStore(state => state.removeProject);
  const gitStatus = useGitStore(state => state.status);
  const fetchGitStatus = useGitStore(state => state.fetchStatus);
  const location = useLocation();
  const navigate = useNavigate();
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 1023px)').matches);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [routeKey, setRouteKey] = useState(location.key);
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  if (routeKey !== location.key) {
    setRouteKey(location.key);
    setDrawerOpen(false);
  }
  if (drawerOpen && (commandPaletteVisible || folderBrowserVisible)) setDrawerOpen(false);

  useModalDialog({ active: compact && drawerOpen, containerRef: overlayRef, initialFocusRef: closeRef });

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)');
    const handleChange = (event: MediaQueryListEvent) => {
      setCompact(event.matches);
      setDrawerOpen(false);
    };
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    if (!compact || !drawerOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const shortcutGuide = ((event.metaKey || event.ctrlKey) && event.key === '/') ||
        (event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !isMonacoFocused());
      if (shortcutGuide) { closeDrawer(); return; }
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault();
        closeDrawer();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [compact, drawerOpen, closeDrawer]);

  useEffect(() => { void fetchGitStatus(); }, [fetchGitStatus]);

  useEffect(() => {
    void hydrateFromServer();
    const handleProjectsChanged = () => { void hydrateFromServer(); };
    window.addEventListener('agk:projects-changed', handleProjectsChanged);
    return () => window.removeEventListener('agk:projects-changed', handleProjectsChanged);
  }, [hydrateFromServer]);

  useEffect(() => {
    if (!activeProjectId || location.pathname === '/' || location.pathname === '/chat' || location.pathname === '/chat/') return;
    const chat = useChatStore.getState();
    if (
      chat.sessions.length > 0 || chat.activeSessionId || chat.activeSession ||
      chat.messages.length > 0 || chat.isStreaming
    ) return;
    chat.loadFromStorage();
  }, [activeProjectId, activeProjectPath, location.pathname]);

  const handleSwitchProject = async (project: ProjectRecord) => {
    closeDrawer();
    if (project.id === activeProjectId) return;
    const result = await switchToProject(project);
    if (result.ok) {
      setWorkspacePath(result.project?.path || project.path);
      addToast(`'${project.name}' 프로젝트로 전환되었습니다.`, 'success');
      refreshTree();
    } else {
      addToast(result.detail ? `프로젝트 전환 실패: ${result.detail}` : '프로젝트 전환에 실패했습니다.', 'error');
    }
  };

  const handleDeleteProject = async (project: ProjectRecord) => {
    if (!window.confirm(`'${project.name}' 프로젝트를 목록에서 제외하시겠습니까?\n(실제 로컬 파일은 삭제되지 않습니다)`)) return;
    const result = await removeProject(project);
    if (result.ok) {
      addToast(`'${project.name}' 프로젝트가 목록에서 제외되었습니다.`, 'info');
      const next = useProjectStore.getState();
      if (next.activeProjectPath) {
        setWorkspacePath(next.activeProjectPath);
        refreshTree();
      }
    } else {
      addToast(result.detail ? `프로젝트 제거 실패: ${result.detail}` : '프로젝트 제거에 실패했습니다.', 'error');
    }
  };

  const handleRename = (sessionId: string, title: string) => {
    updateSessionTitle(sessionId, title);
    addToast('대화 제목이 변경되었습니다.', 'info');
  };

  const handleDeleteSession = (session: ChatSession) => {
    if (window.confirm(`'${session.title || '대화'}' 대화를 삭제하시겠습니까?`)) {
      deleteSession(session.id);
      addToast('대화가 삭제되었습니다.', 'info');
    }
  };

  const handleNewChat = () => {
    closeDrawer();
    createNewSession();
    navigate('/chat');
  };

  const handleSelectSession = (sessionId: string) => {
    closeDrawer();
    switchSession(sessionId);
    saveToStorage();
    navigate('/chat');
  };

  const handleSearch = () => { closeDrawer(); setCommandPaletteVisible(true); };
  const handleOpenProject = () => { closeDrawer(); setFolderBrowserVisible(true); };

  return (
    <>
      <button type="button" className="workspace-nav-toggle workspace-icon-button" hidden={!compact} aria-label="탐색 메뉴 열기" aria-expanded={drawerOpen} aria-controls="workspace-sidebar" onClick={() => setDrawerOpen(true)}><AppIcon name="panelLeft" /></button>
      <div ref={overlayRef} className="workspace-nav-layer" data-open={drawerOpen} data-compact={compact} hidden={compact && !drawerOpen}>
        {compact && drawerOpen && <button type="button" className="workspace-nav-backdrop" aria-hidden="true" tabIndex={-1} onClick={closeDrawer} />}
        <aside id="workspace-sidebar" className="workspace-sidebar codex-desktop-sidebar" aria-label="SSAK-AI 탐색" role={compact ? 'dialog' : undefined} aria-modal={compact ? true : undefined}>
          <header className="workspace-brand-row">
            <span className="workspace-brand">SSAK-AI</span>
            {compact && <button ref={closeRef} type="button" className="workspace-nav-close workspace-icon-button" aria-label="탐색 메뉴 닫기" title="탐색 메뉴 닫기" onClick={closeDrawer}><AppIcon name="close" /></button>}
          </header>
          <div className="workspace-nav-scroll codex-sidebar-scroll-area" role="region" aria-label="프로젝트와 대화 탐색" tabIndex={0}>
            <WorkspaceNavigation onNewChat={handleNewChat} onSearch={handleSearch} onNavigate={closeDrawer} />
            <WorkspaceProjects projects={projects} activeProjectId={activeProjectId} branch={gitStatus.branch} changedFiles={gitStatus.counts.total} sessionCount={sessions.length} onOpen={handleOpenProject} onSelect={project => { void handleSwitchProject(project); }} onRemove={project => { void handleDeleteProject(project); }} />
            <WorkspaceThreads sessions={sessions} activeSessionId={activeSessionId} onNewChat={handleNewChat} onSelect={handleSelectSession} onRename={handleRename} onDelete={handleDeleteSession} />
          </div>
          <footer className="workspace-sidebar-footer">
            <NavLink to="/settings" onClick={closeDrawer} className={({ isActive }) => `workspace-nav-link ${isActive ? 'active' : ''}`}><AppIcon name="settings" /><span>설정</span></NavLink>
            {toggleTerminal && <button type="button" className="workspace-icon-button" aria-label="터미널 열기 또는 닫기" title="터미널 (⌘` / Ctrl+`)" onClick={() => { closeDrawer(); toggleTerminal(); }}><AppIcon name="terminal" /></button>}
          </footer>
        </aside>
      </div>
    </>
  );
};

export default Sidebar;
