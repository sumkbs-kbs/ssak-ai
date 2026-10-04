/**
 * EnvironmentPanel — Agent Monitoring Dashboard (Redesigned)
 * ==========================================================
 * Right-hand rail with three tabs:
 *  - 환경 (REDESIGNED): Agent status, live activity feed, token usage,
 *    file change tracker, error/warning log — "AI Agent DevTools"
 *  - 코드: Inspector editor + Git info (retained from legacy)
 *  - 변경: Diff / change panel (unchanged)
 */

import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchGitStatus, fetchGitBranches, fetchGitLog, checkoutGitBranch } from '../../stores/gitApi';
import type { GitBranch, GitCommit, GitFile } from '../../stores/gitSchema';
import { useChangeStore } from '../../stores/changeStore';
import { useUiStore } from '../../stores/uiStore';
import { useActivityStore, type ActivityItem } from '../../stores/activityStore';
import { useChatStore } from '../../stores/chatStore';

import { type McpServerItem } from '../../api/clientSchema';
import { useProjectStore } from '../../stores/projectStore';
import { AppIcon, type AppIconName } from '../UI/AppIcon';
import { InspectionFrame } from './InspectionFrame';

export type EnvPanelTab = 'env' | 'code' | 'changes';

export type McpServerInfo = McpServerItem;

interface Props {
  open: boolean;
  tab: EnvPanelTab;
  onTabChange: (tab: EnvPanelTab) => void;
  onClose: () => void;
  branch: string;
  workspacePath?: string;
  mcpServers: McpServerInfo[];
  editorContent: React.ReactNode;
  changesContent: React.ReactNode;
}

function getEffectiveWorkspacePath(propPath?: string): string {
  if (propPath && propPath !== '/') return propPath;
  const fromStore = useProjectStore.getState().activeProjectPath;
  if (fromStore && fromStore !== '/') return fromStore;
  const stored = localStorage.getItem('agk_active_project');
  if (stored && stored !== '/') return stored;
  return '.';
}

function shortFilePath(filePath: string): string {
  const parts = filePath.split(/[/\\]/);
  return parts.slice(-2).join('/');
}

/* ── Helper: relative time string ──────────────────────────────── */
function relativeTime(at: number, now: number): string {
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 5) return '방금';
  if (seconds < 60) return `${seconds}초 전`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  return `${Math.floor(minutes / 60)}시간 전`;
}

/* ── Helper: format elapsed time ───────────────────────────────── */
function formatElapsed(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}초`;
  const minutes = Math.floor(seconds / 60);
  const remainSec = seconds % 60;
  return `${minutes}분 ${remainSec}초`;
}

/* ── Helper: format token count ────────────────────────────────── */
function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10_000) return `${(n / 1000).toFixed(1)}K`;
  return `${Math.round(n / 1000)}K`;
}

/* ── Kind icons for activity items ─────────────────────────────── */
const KIND_ICONS: Record<ActivityItem['kind'], AppIconName> = {
  tool: 'terminal',
  file_read: 'file',
  file_edit: 'edit',
  error: 'activity',
  plan: 'layers',
};

const STATUS_CLASSES: Record<string, string> = {
  running: 'status-running',
  done: 'status-done',
  failed: 'status-failed',
};

/* ═══════════════════════════════════════════════════════════════════
 * AgentMonitorTab — the redesigned 환경 tab content
 * ═══════════════════════════════════════════════════════════════════ */
const AgentMonitorTab: React.FC = () => {
  const items = useActivityStore((s) => s.items);
  const tokenUsage = useActivityStore((s) => s.tokenUsage);
  const sessionStartedAt = useActivityStore((s) => s.sessionStartedAt);
  const sessionEndedAt = useActivityStore((s) => s.sessionEndedAt);
  const activeTool = useActivityStore((s) => s.activeTool);
  const errorCount = useActivityStore((s) => s.errorCount);
  const toolCallCount = useActivityStore((s) => s.toolCallCount);
  const fileEditCount = useActivityStore((s) => s.fileEditCount);
  const fileReadCount = useActivityStore((s) => s.fileReadCount);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const [now, setNow] = useState(Date.now());
  const [activityExpanded, setActivityExpanded] = useState(true);
  const [errorsExpanded, setErrorsExpanded] = useState(true);

  // Tick every second for live timers
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const isRunning = isStreaming || activeTool !== null;
  const elapsed = sessionStartedAt
    ? (sessionEndedAt ?? now) - sessionStartedAt
    : 0;

  // Filter file edits for the file changes section
  const fileEdits = useMemo(
    () => items.filter((i) => i.kind === 'file_edit'),
    [items],
  );

  // Filter errors
  const errors = useMemo(
    () => items.filter((i) => i.kind === 'error'),
    [items],
  );

  // Recent activity (last 15 items)
  const recentActivity = useMemo(
    () => items.slice(-15).reverse(),
    [items],
  );

  return (
    <div className="env-scroll-area agent-monitor-scroll">
      {/* ── ① Agent Status Card ────────────────────────────── */}
      <div className={`agent-status-card ${isRunning ? 'running' : 'idle'}`}>
        <div className="agent-status-header">
          <AppIcon name="activity" size={18} className="agent-status-icon" />
          <span className="agent-status-title">에이전트 상태</span>
          <span className={`agent-status-badge ${isRunning ? 'badge-running' : 'badge-idle'}`}>
            {isRunning ? '실행 중' : '대기 중'}
          </span>
        </div>
        {isRunning && activeTool && (
          <div className="agent-active-tool">
            <AppIcon name="terminal" size={16} className="active-tool-icon" />
            <span className="active-tool-name">{activeTool.name}</span>
            <span className="active-tool-elapsed">
              {formatElapsed(now - activeTool.startedAt)}
            </span>
          </div>
        )}
        <div className="agent-status-stats">
          <div className="status-stat">
            <span className="stat-value">{formatElapsed(elapsed)}</span>
            <span className="stat-label">경과</span>
          </div>
          <div className="status-stat">
            <span className="stat-value">{toolCallCount}</span>
            <span className="stat-label">도구 호출</span>
          </div>
          <div className="status-stat">
            <span className="stat-value">{fileEditCount}</span>
            <span className="stat-label">파일 수정</span>
          </div>
          <div className="status-stat">
            <span className="stat-value">{fileReadCount}</span>
            <span className="stat-label">파일 읽기</span>
          </div>
        </div>
      </div>

      {/* ── ② Live Activity Feed ──────────────────────────── */}
      <div className="agent-section">
        <button
          type="button"
          className="agent-section-header"
          onClick={() => setActivityExpanded((v) => !v)}
          aria-expanded={activityExpanded}
        >
          <AppIcon name="activity" size={16} className="agent-section-icon" />
          <span className="agent-section-title">실시간 활동</span>
          <span className="agent-section-count">{items.length}개</span>
          <AppIcon name={activityExpanded ? 'chevronUp' : 'chevronDown'} size={16} className="env-chevron" />
        </button>
        {activityExpanded && (
          <div className="agent-activity-feed">
            {recentActivity.length === 0 ? (
              <div className="agent-empty">아직 활동이 없습니다.</div>
            ) : (
              recentActivity.map((item) => (
                <div
                  key={item.id}
                  className={`agent-activity-item ${STATUS_CLASSES[item.status] ?? ''}`}
                >
                  <AppIcon name={KIND_ICONS[item.kind]} size={16} className="activity-item-icon" />
                  <div className="activity-item-body">
                    <span className="activity-item-label">{item.label}</span>
                    {item.detail && (
                      <span className="activity-item-detail" title={item.detail}>
                        {shortFilePath(item.detail)}
                      </span>
                    )}
                  </div>
                  <div className="activity-item-meta">
                    {item.status === 'running' && (
                      <span className="activity-running-dot" />
                    )}
                    <span className="activity-item-time">{relativeTime(item.at, now)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* ── ③ Token Usage ─────────────────────────────────── */}
      <details className="agent-section token-usage-details">
        <summary className="agent-section-header static" tabIndex={0}>
          <AppIcon name="layers" size={16} className="agent-section-icon" />
          <span className="agent-section-title">토큰 사용량</span>
          <span className="agent-section-count">{formatTokens(tokenUsage.totalTokens)}</span>
        </summary>
        <div className="token-usage-card">
          <div className="token-row">
            <span className="token-label">입력 (Prompt)</span>
            <span className="token-value prompt">{formatTokens(tokenUsage.promptTokens)}</span>
          </div>
          <div className="token-row">
            <span className="token-label">출력 (Completion)</span>
            <span className="token-value completion">{formatTokens(tokenUsage.completionTokens)}</span>
          </div>
          <div className="token-divider" />
          <div className="token-row total">
            <span className="token-label">총 사용량</span>
            <span className="token-value total">{formatTokens(tokenUsage.totalTokens)}</span>
          </div>
          {tokenUsage.totalTokens > 0 && (
            <div className="token-bar-container">
              <div
                className="token-bar-fill prompt-fill"
                style={{
                  width: `${Math.min(100, (tokenUsage.promptTokens / Math.max(1, tokenUsage.totalTokens)) * 100)}%`,
                }}
              />
              <div
                className="token-bar-fill completion-fill"
                style={{
                  width: `${Math.min(100, (tokenUsage.completionTokens / Math.max(1, tokenUsage.totalTokens)) * 100)}%`,
                }}
              />
            </div>
          )}
        </div>
      </details>

      {/* ── ④ File Changes ────────────────────────────────── */}
      <div className="agent-section">
        <div className="agent-section-header static">
          <AppIcon name="edit" size={16} className="agent-section-icon" />
          <span className="agent-section-title">파일 변경 추적</span>
          {fileEdits.length > 0 && (
            <span className="agent-section-count">{fileEdits.length}개</span>
          )}
        </div>
        <div className="agent-file-changes">
          {fileEdits.length === 0 ? (
            <div className="agent-empty">변경된 파일이 없습니다.</div>
          ) : (
            fileEdits.slice(-10).reverse().map((item) => (
              <div key={item.id} className="agent-file-item">
                <AppIcon name="edit" size={16} className="file-item-icon" />
                <span className="file-item-name" title={item.detail}>
                  {shortFilePath(item.detail)}
                </span>
                <span className="file-item-time">{relativeTime(item.at, now)}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── ⑤ Error / Warning Log ─────────────────────────── */}
      <div className="agent-section">
        <button
          type="button"
          className="agent-section-header"
          onClick={() => setErrorsExpanded((v) => !v)}
          aria-expanded={errorsExpanded}
        >
          <AppIcon name="activity" size={16} className="agent-section-icon" />
          <span className="agent-section-title">에러 / 경고</span>
          {errorCount > 0 && (
            <span className="agent-section-count error-count">{errorCount}개</span>
          )}
          <AppIcon name={errorsExpanded ? 'chevronUp' : 'chevronDown'} size={16} className="env-chevron" />
        </button>
        {errorsExpanded && (
          <div className="agent-error-log">
            {errors.length === 0 ? (
              <div className="agent-empty success">에러 없음</div>
            ) : (
              errors.slice(-8).reverse().map((item) => (
                <div key={item.id} className="agent-error-item">
                  <AppIcon name="activity" size={16} className="error-item-icon" />
                  <div className="error-item-body">
                    <span className="error-item-msg" title={item.detail}>
                      {item.detail.length > 80 ? `${item.detail.slice(0, 80)}…` : item.detail}
                    </span>
                    <span className="error-item-time">{relativeTime(item.at, now)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};


/* ═══════════════════════════════════════════════════════════════════
 * CodeTabWithGit — retained Git info, now in the 코드 tab
 * ═══════════════════════════════════════════════════════════════════ */
const CodeTabWithGit: React.FC<{
  branch: string;
  workspacePath?: string;
  mcpServers: McpServerInfo[];
  editorContent: React.ReactNode;
}> = ({ branch, workspacePath, mcpServers, editorContent }) => {
  const navigate = useNavigate();
  const { addToast } = useUiStore();

  const [logOpen, setLogOpen] = useState<boolean>(false);
  const [branchOpen, setBranchOpen] = useState<boolean>(false);
  const [gitFiles, setGitFiles] = useState<GitFile[]>([]);
  const [branches, setBranches] = useState<GitBranch[]>([]);
  const [commits, setCommits] = useState<GitCommit[]>([]);

  const effectivePath = getEffectiveWorkspacePath(workspacePath);
  const currentBranchName = branches.find((b) => b.is_current)?.name || branch || 'main';

  useEffect(() => {
    const path = effectivePath;
    fetchGitStatus(path)
      .then((res) => { if (res.ok) setGitFiles(res.files); })
      .catch(() => {});
    fetchGitBranches(path)
      .then((res) => {
        if (res.ok) {
          setBranches(res.branches);
          const active = res.branches.find((b) => b.is_current)?.name || branch;
          fetchGitLog(path, 5, active).then((lr) => { if (lr.ok) setCommits(lr.commits); }).catch(() => {});
        }
      })
      .catch(() => {});
  }, [branch, effectivePath]);

  const goGit = (note: string) => {
    addToast(note, 'info');
    navigate('/git');
  };

  const handleCheckoutBranch = async (b: GitBranch) => {
    if (b.is_current) return;
    const confirmed = window.confirm(`'${b.name}' 브랜치로 전환하시겠습니까?\n작업 트리의 변경사항이 변경될 수 있습니다.`);
    if (!confirmed) return;
    const path = effectivePath;
    try {
      const res = await checkoutGitBranch(b.name, path);
      if (res.ok) {
        addToast(`'${b.name}' 브랜치로 전환되었습니다.`, 'success');
        fetchGitBranches(path).then((r) => { if (r.ok) setBranches(r.branches); });
        fetchGitStatus(path).then((r) => { if (r.ok) setGitFiles(r.files); });
        fetchGitLog(path, 5, b.name).then((r) => { if (r.ok) setCommits(r.commits); });
      } else {
        addToast('브랜치 전환 실패: 오류가 발생했습니다.', 'error');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      addToast(`브랜치 전환 실패: ${msg}`, 'error');
    }
  };

  return (
    <div className="env-content-area">
      {/* Editor content */}
      {editorContent}

      {/* Git info section (moved from 환경 tab) */}
      <div className="env-scroll-area code-tab-git">
        <div className="env-divider" />
        <div className="env-section">
          <div className="env-section-header">
            <span className="env-section-title">Git</span>
          </div>

          {/* Branch row */}
          <div className="env-row-group">
            <button
              type="button"
              className="env-row"
              onClick={() => setBranchOpen((v) => !v)}
              aria-expanded={branchOpen}
            >
              <AppIcon name="git" size={16} className="env-row-icon" />
              <span className="env-row-label branch-name">{currentBranchName}</span>
              <AppIcon name={branchOpen ? 'chevronUp' : 'chevronDown'} size={16} className="env-chevron" />
            </button>
            {branchOpen && (
              <div className="env-sub-list">
                {branches.length === 0 ? (
                  <div className="env-sub-empty">브랜치 목록을 불러올 수 없습니다.</div>
                ) : (
                  branches.slice(0, 8).map((b) => (
                    <button
                      key={b.name}
                      type="button"
                      className={`env-branch-row ${b.is_current ? 'current' : ''}`}
                      onClick={() => { void handleCheckoutBranch(b); }}
                      title={b.is_current ? '현재 브랜치' : `${b.name} 브랜치로 전환`}
                    >
                      <span className="env-branch-name">{b.name}</span>
                      {b.is_current && <span className="env-branch-current">현재</span>}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Log row */}
          <div className="env-row-group">
            <button
              type="button"
              className="env-row"
              onClick={() => setLogOpen((v) => !v)}
              aria-expanded={logOpen}
            >
              <AppIcon name="history" size={16} className="env-row-icon" />
              <span className="env-row-label">커밋 로그</span>
              <AppIcon name={logOpen ? 'chevronUp' : 'chevronDown'} size={16} className="env-chevron" />
            </button>
            {logOpen && (
              <div className="env-sub-list">
                {commits.length === 0 ? (
                  <div className="env-sub-empty">커밋 로그를 불러올 수 없습니다.</div>
                ) : (
                  commits.map((c) => (
                    <div key={c.hash} className="env-log-row" title={c.message}>
                      <span className="env-log-hash">{c.short_hash}</span>
                      <span className="env-log-msg">{c.message}</span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Action rows */}
          <button type="button" className="env-row" onClick={() => goGit('커밋·푸시는 Git 페이지에서 진행합니다.')}>
            <AppIcon name="refresh" size={16} className="env-row-icon" />
            <span className="env-row-label">커밋 또는 푸시</span>
          </button>
          <button type="button" className="env-row" onClick={() => goGit('풀 리퀘스트는 Git 페이지에서 만들 수 있습니다.')}>
            <AppIcon name="git" size={16} className="env-row-icon" />
            <span className="env-row-label">풀 리퀘스트 만들기</span>
          </button>
        </div>

        {/* File activity — always visible so clean trees still expose empty-state (CR-14 F-47) */}
        <div className="env-divider" />
        <div className="env-section" data-testid="env-file-activity">
          <div className="env-section-header">
            <span className="env-section-title">파일 상태</span>
          </div>
          {gitFiles.length === 0 ? (
            <div className="env-sub-empty">변경된 파일이 없습니다.</div>
          ) : (
            <>
              {gitFiles.slice(0, 8).map((f) => (
                <button
                  key={`${f.file_path}-${f.x}${f.y}`}
                  type="button"
                  className="env-file-row"
                  onClick={() => goGit('파일 상태는 Git 페이지 Changes 탭에서 확인합니다.')}
                  title={f.file_path}
                >
                  <span className="env-file-name">{shortFilePath(f.file_path)}</span>
                  <span className="env-file-status-letter">
                    {(f.staged_status && f.staged_status !== ' ') ? f.staged_status : f.unstaged_status}
                  </span>
                </button>
              ))}
              <div className="env-file-footer">
                파일 {gitFiles.length}개
              </div>
            </>
          )}
        </div>

        {/* MCP Sources */}
        <div className="env-divider" />
        <div className="env-section">
          <div className="env-section-header">
            <span className="env-section-title">소스 (MCP)</span>
          </div>
          {mcpServers.length === 0 ? (
            <div className="env-sub-empty">구성된 MCP 서버가 없습니다 (.mcp.json)</div>
          ) : (
            mcpServers.map((server) => (
              <div key={server.name} className="env-mcp-row">
                <AppIcon name="puzzle" size={16} className="env-mcp-icon" />
                <div className="env-mcp-text">
                  <span className="env-mcp-name">{server.name}</span>
                  <span className="env-mcp-status">{server.transport} · 구성됨</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};


/* ═══════════════════════════════════════════════════════════════════
 * EnvironmentPanel — Main component
 * ═══════════════════════════════════════════════════════════════════ */
export const EnvironmentPanel: React.FC<Props> = ({
  open,
  tab,
  onTabChange,
  onClose,
  branch,
  workspacePath,
  mcpServers,
  editorContent,
  changesContent,
}) => {
  const changes = useChangeStore((s) => s.changes);

  return (
    <InspectionFrame open={open} tab={tab} onTabChange={onTabChange} onClose={onClose} changeCount={changes.length}>
      {tab === 'env' && <AgentMonitorTab />}

      {tab === 'code' && (
        <CodeTabWithGit
          branch={branch}
          workspacePath={workspacePath}
          mcpServers={mcpServers}
          editorContent={editorContent}
        />
      )}

      {tab === 'changes' && (
        <div className="env-content-area">
          {changesContent}
        </div>
      )}
    </InspectionFrame>
  );
};

export default EnvironmentPanel;
