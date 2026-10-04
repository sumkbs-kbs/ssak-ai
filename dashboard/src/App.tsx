/**
 * App — Root component with React Router v7
 * ===========================================
 * Provides the main layout shell with sidebar, terminal, command palette.
 */

import React, { Suspense, lazy, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { useUiStore, type SystemStatus } from './stores/uiStore';
import { useChatStore } from './stores/chatStore';
import { checkHealth, fetchSystemMetrics } from './api/client';
import ToastContainer from './components/UI/ToastContainer';
import { useGlobalCommandPalette } from './hooks/useGlobalCommandPalette';
import { useTerminalStore } from './stores/terminalStore';
import { useThemeStore } from './stores/themeStore';
import { useEditorStore } from './stores/editorStore';
import { useLocalHistoryStore } from './stores/localHistoryStore';
import { SessionDisclosureBanner } from './components/shared';
import { isMonacoFocused } from './utils/domHelpers';
import { PluginLifecycleDispatcher } from './plugin/PluginManager';
import { usePluginRegistry } from './plugin/pluginRegistry';
import { examplePlugin } from './plugin/examplePlugin';
import {
  clearAccessCredential,
  createAccessPinHeaders,
  loginWithAccessPin,
  readLegacyAccessPin,
  readStoredAccessToken,
} from './utils/accessPinCredential';
import AppErrorBoundary from './components/UI/AppErrorBoundary';
import { AppIcon } from './components/UI/AppIcon';

/* ─── Sidebar loading skeleton ──────────────────────────── */
const SidebarFallback: React.FC = () => (
  <aside className="sidebar" style={{
    display: 'flex', flexDirection: 'column',
    background: 'var(--sidebar-bg)',
    borderRight: '1px solid var(--glass-border)',
    width: 'var(--sidebar-width, 220px)',
    minWidth: 'var(--sidebar-width, 220px)',
    padding: 16, gap: 8, overflow: 'hidden',
  }}>
    <div style={{ height: 24, width: '60%', background: 'rgba(255,255,255,0.06)', borderRadius: 4, marginBottom: 12 }} />
    <div style={{ height: 16, width: '40%', background: 'rgba(255,255,255,0.04)', borderRadius: 4, marginBottom: 24 }} />
    {['70%', '62%', '54%', '46%', '38%'].map(width => (
      <div key={width} style={{ height: 14, width, background: 'rgba(255,255,255,0.03)', borderRadius: 4 }} />
    ))}
    <div style={{ flex: 1 }} />
    <div style={{ height: 14, width: '50%', background: 'rgba(255,255,255,0.03)', borderRadius: 4 }} />
    <div style={{ height: 14, width: '35%', background: 'rgba(255,255,255,0.03)', borderRadius: 4 }} />
  </aside>
);

/* ─── Page loading fallback ────────────────────────────────── */
const PageLoadingFallback: React.FC = () => (
  <div style={{
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    gap: 10,
    color: 'var(--text-muted)',
    fontSize: 14,
  }}>
    <span style={{
      display: 'inline-block', width: 18, height: 18,
      border: '2px solid var(--glass-border)',
      borderTopColor: 'var(--accent-color)',
      borderRadius: '50%',
      animation: 'dex-spin 0.8s linear infinite',
    }} />
    Loading...
  </div>
);

async function validateAccessCredential(
  storedToken: string | null,
  legacyPin: string | null,
): Promise<boolean> {
  if (storedToken === null && legacyPin !== null) {
    try {
      await loginWithAccessPin(legacyPin);
      return false;
    } catch {
      clearAccessCredential();
      return true;
    }
  }

  const response = await globalThis.fetch('/api/session/info', { headers: createAccessPinHeaders() });
  if (storedToken === null) return !response.ok;
  if (response.ok) return false;
  clearAccessCredential();
  return true;
}

// ─── Lazy-loaded page chunks ────────────────────────────────
const ChatPage = lazy(() => import('./components/Chat/ChatPage'));
const WikiPage = lazy(() => import('./pages/WikiPage'));
const AgentPage = lazy(() => import('./pages/AgentPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const SkillsPage = lazy(() => import('./pages/SkillsPage'));
const DataExtractionPage = lazy(() => import('./pages/DataExtractionPage'));
const GitPage = lazy(() => import('./pages/GitPage'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));
const PluginPage = lazy(() => import('./pages/PluginPage'));
const MutationDashboardPage = lazy(() => import('./pages/MutationDashboardPage'));
const StudioPage = lazy(() => import('./pages/StudioPage'));
const ModelHubPage = lazy(() => import('./pages/ModelHubPage'));
const AgentStartPage = lazy(() => import('./pages/AgentStartPage'));
/* CR-07: 없는 경로 안내(404). 오류 경계와 함께 라우팅 복구를 담당한다. */
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

// ─── Lazy-loaded layout chunks ────────────────────────────
const Sidebar = lazy(() => import('./components/Layout/Sidebar'));
const SystemTelemetricsBar = lazy(() => import('./components/Layout/SystemTelemetricsBar'));

// ─── Lazy-loaded modal / overlay chunks ─────────────────────
const MultiTerminalPanel = lazy(() => import('./components/UI/MultiTerminalPanel'));
const PluginPanelRoutes = lazy(() => import('./plugin/PluginPanelRoutes'));
const OutputPanel = lazy(() => import('./components/UI/OutputPanel'));
const CommandPalette = lazy(() => import('./components/UI/CommandPalette'));
const PinModal = lazy(() => import('./components/UI/PinModal'));
const FolderBrowser = lazy(() => import('./components/Editor/FolderBrowser'));
const KeyboardShortcutsModal = lazy(() => import('./components/UI/KeyboardShortcutsModal'));

type BottomPanelTab = 'terminal' | 'output';

const AppContent: React.FC = () => {
  const location = useLocation();
  const { setSystemStatus } = useUiStore();
  const { loadFromStorage } = useChatStore();
  const terminalVisible = useTerminalStore(s => s.visible);
  const toggleTerminal = useTerminalStore(s => s.toggleVisible);
  const addSession = useTerminalStore(s => s.addSession);
  const [shortcutsVisible, setShortcutsVisible] = useState(false);
  const [bottomTab, setBottomTab] = useState<BottomPanelTab>('terminal');

  // Register built-in plugins on mount
  useEffect(() => {
    const registry = usePluginRegistry.getState();
    if (!registry.plugins[examplePlugin.manifest.id]) {
      registry.register(examplePlugin);
    }
  }, []);

  // Load theme preferences on mount
  useEffect(() => {
    try {
      useThemeStore.getState().load();
    } catch (e) {
      console.warn('[Theme] Failed to load preferences:', e);
    }
  }, []);

  // Auto-snapshot file changes to local history
  useEffect(() => {
    const unsub = useEditorStore.subscribe((state, prevState) => {
      if (!state.openFiles.length) return;
      const lh = useLocalHistoryStore.getState();
      if (!lh.autoSaveEnabled) return;
      const previousFiles = new Map(prevState.openFiles.map(file => [file.path, file]));

      for (const file of state.openFiles) {
        const prev = previousFiles.get(file.path);
        // Snapshot NEW content when content changes (keeps current state in history)
        if (prev && prev.content !== file.content) {
          lh.addSnapshot({
            filePath: file.path,
            fileName: file.name,
            content: file.content,  // save current/new state
            source: file.isDirty ? 'auto' : 'manual',
            label: file.isDirty ? undefined : '수동 저장',
          });
        }
        // Snapshot on save transition: dirty → saved
        if (prev && prev.isDirty && !file.isDirty) {
          lh.addSnapshot({
            filePath: file.path,
            fileName: file.name,
            content: file.content,
            source: 'manual',
            label: '💾 저장 시점',
          });
        }
      }
    });
    return () => unsub();
  }, []);

  // Global Cmd+K handler (with Monaco conflict prevention)
  useGlobalCommandPalette();

  // Global `?` handler for Keyboard Shortcuts Guide (when NOT in Monaco)

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Cmd+Shift+F: Search in Files
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('agk:toggle-search'));
        return;
      }
      // Cmd+`: Toggle terminal
      if (e.key === '`' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        toggleTerminal();
        return;
      }
      // `?` or Cmd+/(Ctrl+/): Keyboard Shortcuts Guide
      if (e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey && !isMonacoFocused()) {
        e.preventDefault();
        setShortcutsVisible(v => !v);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setShortcutsVisible(v => !v);
        return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggleTerminal]);

  useEffect(() => {
    loadFromStorage();
    let chatSlashTimeout: ReturnType<typeof setTimeout> | null = null;

    const handlePinRequired = () => {
      // NX-05: 401은 "이 토큰은 현재 서버 세대가 아니다"라는 뜻이다(PIN 변경으로 전체
      // 폐기 포함). 거부된 토큰을 sessionStorage에 남기면 이후 모든 요청이 같은 401을
      // 반복하므로 여기서 지운다 — 모달에서 로그인하면 새 토큰이 저장된다.
      clearAccessCredential();
      // NX-09: 이유를 모달이 들고 간다 — 화면이 통째로 교체되므로 다른 곳의 안내는 사라진다.
      useUiStore.getState().setPinModalNotice(
        '세션이 만료되었거나 서버 세대가 바뀌었습니다. 다시 로그인하세요.',
      );
      useUiStore.getState().setPinModalVisible(true);
    };
    window.addEventListener('agk:pin-required', handlePinRequired);

    // CR-10: 실제 API 값만 반영한다. 미응답은 0/true로 뭉개지 않고 UNKNOWN/null로 남기며,
    // 마지막 성공 관측 시각(observedAt)을 기록해 화면이 stale을 구분할 수 있게 한다.
    const pollSystemStatus = async () => {
      let observed = false;
      let disconnected = false;

      try {
        const health = await checkHealth();
        setSystemStatus({
          healthy: health.status === 'ok',
          backends: health.backends || {},
          ragFiles: health.rag_index_files ?? null,
          covActive: health.cov_active || false,
          // /health는 이미 실제 버전을 준다 — 하드코딩 대신 연결한다.
          version: health.version ?? null,
          buildId: health.build?.build_id ?? null,
        });
        observed = true;
      } catch {
        disconnected = true;
        // 연결이 끊기면 health를 주장할 수 없다. 마지막 값을 healthy로 두지 않는다.
        setSystemStatus({ healthy: null });
      }

      try {
        const metrics = await fetchSystemMetrics();
        if (metrics.ok) {
          setSystemStatus({
            cpuPercent: metrics.cpu_percent ?? null,
            memoryPercent: metrics.memory_percent ?? metrics.memory_mb ?? null,
            totalTokens: metrics.total_tokens ?? null,
            uptimeSeconds: metrics.uptime_seconds ?? null,
            startedAt: metrics.uptime_started_at ?? null,
            processId: metrics.process_id ?? null,
            version: metrics.version ?? null,
            buildId: metrics.build?.build_id ?? null,
          });
          observed = true;
        }
      } catch {
        disconnected = true;
      }

      // 주의: 실패 시 observedAt을 undefined로 덮어쓰면 마지막 성공 시각이 지워진다.
      // 관측에 성공했을 때만 갱신한다.
      const connection: { state: SystemStatus['state']; observedAt?: number } = {
        state: observed ? 'live' : disconnected ? 'disconnected' : 'unknown',
      };
      if (observed) connection.observedAt = Date.now();
      setSystemStatus(connection);
    };

    pollSystemStatus();
    const interval = setInterval(pollSystemStatus, 10000);

    // Listen for global navigation events from CommandPalette / Wiki
    const handleNavigate = (e: CustomEvent) => {
      const path = e.detail;
      // Use window.location for simplicity across routes
      window.dispatchEvent(new CustomEvent('agk:pushstate', { detail: path }));
    };
    const handleChatSlash = (e: CustomEvent) => {
      // Navigate to chat and set input text
      const { text } = e.detail;
      window.dispatchEvent(new CustomEvent('agk:pushstate', { detail: '/chat' }));
      if (chatSlashTimeout !== null) clearTimeout(chatSlashTimeout);
      chatSlashTimeout = setTimeout(() => {
        window.dispatchEvent(new CustomEvent('agk:set-chat-input', { detail: { text } }));
      }, 300);
    };

    window.addEventListener('agk:navigate', handleNavigate as EventListener);
    window.addEventListener('agk:chat-slash', handleChatSlash as EventListener);

    return () => {
      window.removeEventListener('agk:pin-required', handlePinRequired);
      window.removeEventListener('agk:navigate', handleNavigate as EventListener);
      window.removeEventListener('agk:chat-slash', handleChatSlash as EventListener);
      clearInterval(interval);
      if (chatSlashTimeout !== null) clearTimeout(chatSlashTimeout);
    };
  }, [loadFromStorage, setSystemStatus]);

  // Simple pushstate-based routing for external events
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const path = e.detail as string;
      if (!path) return;
      window.history.pushState({}, '', path);
      window.dispatchEvent(new PopStateEvent('popstate'));
    };
    window.addEventListener('agk:pushstate', handler as EventListener);
    return () => window.removeEventListener('agk:pushstate', handler as EventListener);
  }, []);

  return (
    <div className="app-shell workspace-shell">
      <Suspense fallback={null}>
        <SystemTelemetricsBar />
      </Suspense>
      <div className="app-layout">
        <Suspense fallback={<SidebarFallback />}>
          <Sidebar toggleTerminal={toggleTerminal} />
        </Suspense>
        <div className="app-right-panel">
        <SessionDisclosureBanner />
        <main className="main-content">
          <h1 className="visually-hidden">Ssak-Ai Dashboard</h1>
          {/*
           * CR-07: route 수준 오류 경계. 페이지 하나가 던져도 셸(사이드바·배너)은
           * 살아남고, key가 경로라서 다른 화면으로 이동하면 경계가 초기화된다.
           * Suspense는 계속 loading만 담당한다.
           */}
          <AppErrorBoundary scope="route" key={location.pathname}>
          <Suspense fallback={<PageLoadingFallback />}>
            <Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/studio" element={<StudioPage />} />
              <Route path="/models" element={<ModelHubPage />} />
              <Route path="/start" element={<AgentStartPage />} />
              <Route path="/wiki" element={<WikiPage />} />
              <Route path="/agent" element={<AgentPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/data-extraction" element={<DataExtractionPage />} />
              <Route path="/git" element={<GitPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/plugins/*" element={<PluginPanelRoutes />} />
              <Route path="/plugins" element={<PluginPage />} />
              <Route path="/mutation" element={<MutationDashboardPage />} />
              {/* CR-07: 어떤 route에도 해당하지 않으면 안내와 홈 복귀를 보여준다. */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
          </AppErrorBoundary>
        </main>
        {/* Bottom Panel: Terminal + Output (toggleable) */}
        <div
          className="terminal-wrapper"
          style={{
            height: terminalVisible ? 220 : 0,
            minHeight: terminalVisible ? 180 : 0,
            transition: 'height 0.25s ease',
            overflow: 'hidden',
            borderTop: terminalVisible ? '1px solid var(--terminal-border)' : 'none',
            background: 'var(--bg-primary)',
          }}
        >
          {/* ── Bottom Panel Tab Bar ────────────────────────────── */}
          <div className="bottom-panel-tabs" role="tablist" aria-label="하단 패널" style={{
            display: terminalVisible ? 'flex' : 'none',
          }}>
            <button
              type="button"
              className={`bottom-panel-tab ${bottomTab === 'terminal' ? 'active' : ''}`}
              onClick={() => setBottomTab('terminal')}
              aria-label="터미널 탭"
              role="tab"
              aria-selected={bottomTab === 'terminal'}
            >
              <AppIcon name="terminal" size={16} /> 터미널
            </button>
            <button
              type="button"
              className={`bottom-panel-tab ${bottomTab === 'output' ? 'active' : ''}`}
              onClick={() => setBottomTab('output')}
              aria-label="출력 탭"
              role="tab"
              aria-selected={bottomTab === 'output'}
            >
              <AppIcon name="file" size={16} /> 출력
            </button>
            <div className="bottom-panel-spacer" />
            <button
              type="button"
              className="bottom-panel-tab add-terminal-btn"
              onClick={() => addSession()}
              title="새 터미널"
              aria-label="새 터미널 세션 추가"
            >
              <AppIcon name="plus" size={16} /> 새 터미널
            </button>
            <button
              type="button"
              className="bottom-panel-tab close-btn"
              onClick={toggleTerminal}
              title="닫기"
              aria-label="터미널 패널 닫기"
            >
              <AppIcon name="close" size={16} />
            </button>
          </div>
          {terminalVisible && bottomTab === 'terminal' && (
            <Suspense fallback={<div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 12 }}>터미널 로딩 중...</div>}>
              <MultiTerminalPanel />
            </Suspense>
          )}
          {terminalVisible && bottomTab === 'output' && (
            <Suspense fallback={<div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 12 }}>로딩 중...</div>}>
              <OutputPanel />
            </Suspense>
          )}
        </div>
      </div>
      <PluginLifecycleDispatcher />
      <Suspense fallback={null}>
        <CommandPalette />
      </Suspense>
      {shortcutsVisible && (
        <Suspense fallback={null}>
          <KeyboardShortcutsModal visible={shortcutsVisible} onClose={() => setShortcutsVisible(false)} />
        </Suspense>
      )}
      <ToastContainer />
      <Suspense fallback={null}>
        <FolderBrowser />
      </Suspense>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  const pinModalVisible = useUiStore(state => state.pinModalVisible);
  const setPinModalVisible = useUiStore(state => state.setPinModalVisible);
  const [checkingStoredPin, setCheckingStoredPin] = useState(true);

  useEffect(() => {
    const storedToken = readStoredAccessToken();
    const legacyPin = readLegacyAccessPin();
    let active = true;
    if (storedToken === null && legacyPin !== null) setPinModalVisible(true);
    void validateAccessCredential(storedToken, legacyPin)
      .then(showPinModal => {
        if (active) setPinModalVisible(showPinModal);
      })
      .catch(() => {
        if (!active) return;
        clearAccessCredential();
        setPinModalVisible(true);
      })
      .finally(() => {
        if (active) setCheckingStoredPin(false);
      });
    return () => {
      active = false;
    };
  }, [setPinModalVisible]);

  return (
    <BrowserRouter>
      {checkingStoredPin ? null : pinModalVisible ? (
        <Suspense fallback={null}>
          <PinModal />
        </Suspense>
      ) : (
        /* CR-07: 최상위 최후 boundary — 셸까지 실패해도 복구 UI를 보여준다.
         * PinModal은 이 경계 바깥이라 로그인 흐름이 fallback에 묻히지 않는다. */
        <AppErrorBoundary scope="app">
          <AppContent />
        </AppErrorBoundary>
      )}
    </BrowserRouter>
  );
};

export default App;
