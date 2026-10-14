/**
 * AgentMonitorPanel — AI Agent Monitoring Dashboard
 * ===================================================
 * Comprehensive real-time monitoring panel showing:
 * - Agent status card (state, active tool, uptime, system metrics)
 * - Live log stream with level coloring and auto-scroll
 * - Task progress bars with animated indicators
 * - Execution history timeline
 * - Log source filtering
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useAgentMonitorStore, type AgentStatus } from '../../stores/agentMonitorStore';

/* ─── Constants ────────────────────────────────────────────── */

const STATUS_CONFIG: Record<AgentStatus, { icon: string; label: string; color: string }> = {
  idle:     { icon: '💤', label: '대기 중', color: '#7c82a8' },
  running:  { icon: '⚡', label: '실행 중', color: '#7c6aef' },
  planning: { icon: '📋', label: '계획 중', color: '#e0af68' },
  thinking: { icon: '🤔', label: '추론 중', color: '#7aa2f7' },
  error:    { icon: '❌', label: '오류', color: '#f7768e' },
};

const LOG_LEVEL_CONFIG: Record<string, { icon: string; color: string }> = {
  info:    { icon: '·', color: '#7aa2f7' },
  success: { icon: '✓', color: '#9ece6a' },
  warn:    { icon: '⚠', color: '#e0af68' },
  error:   { icon: '✕', color: '#f7768e' },
  debug:   { icon: '·', color: '#7c82a8' },
};

const TASK_STATUS_ICONS: Record<string, string> = {
  queued: '⏳',
  running: '🔄',
  completed: '✅',
  failed: '❌',
  cancelled: '🛑',
};

/* ─── Helpers ──────────────────────────────────────────────── */

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '--:--:--';
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/* ─── Agent Status Card ────────────────────────────────────── */

const AgentStatusCard: React.FC = () => {
  const {
    agentStatus, activeTool, uptime, uptimeObservedAt, memoryPercent, cpuPercent, totalTokens,
  } = useAgentMonitorStore();
  const cfg = STATUS_CONFIG[agentStatus];

  // Live tool duration counter
  const [toolDuration, setToolDuration] = useState(0);
  useEffect(() => {
    if (!activeTool || activeTool.status !== 'running') {
      return;
    }
    const interval = setInterval(() => {
      const start = new Date(activeTool.startedAt).getTime();
      setToolDuration(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [activeTool]);

  return (
    <div className="agent-status-card glass-panel">
      <div className="agent-status-header">
        <span className="agent-status-icon" style={{ fontSize: 24 }}>{cfg.icon}</span>
        <div className="agent-status-info">
          <span className="agent-status-label" style={{ color: cfg.color }}>{cfg.label}</span>
          <span className="agent-status-subtitle">
            {activeTool ? `🔧 ${activeTool.name} (${formatDuration(toolDuration)})` : 'No active tool'}
          </span>
        </div>
        <span className="agent-status-dot" style={{
          background: cfg.color,
          boxShadow: `0 0 8px ${cfg.color}`,
          animation: agentStatus === 'running' || agentStatus === 'thinking' ? 'pulse 1.5s infinite' : 'none',
        }} />
      </div>
      <div className="agent-status-metrics">
        <div className="metric-item">
          <span className="metric-icon">⏱</span>
          {/* CR-10: API 서버 프로세스 가동 시간이다(탭 열린 시간이 아님). 미관측이면 UNKNOWN. */}
          <span className="metric-label">API Uptime</span>
          <span className="metric-value" data-testid="agent-uptime">
            {uptimeObservedAt === null ? 'UNKNOWN' : formatUptime(uptime)}
          </span>
        </div>
        <div className="metric-item">
          <span className="metric-icon">🧠</span>
          <span className="metric-label">Tokens</span>
          <span className="metric-value">{totalTokens.toLocaleString()}</span>
        </div>
        <div className="metric-item">
          <span className="metric-icon">💾</span>
          <span className="metric-label">RAM</span>
          <span className="metric-value">{memoryPercent}%</span>
        </div>
        <div className="metric-item">
          <span className="metric-icon">⚙️</span>
          <span className="metric-label">CPU</span>
          <span className="metric-value">{cpuPercent}%</span>
        </div>
      </div>
    </div>
  );
};

/* ─── Live Log Stream ───────────────────────────────────────── */

const LiveLogStream: React.FC = () => {
  const logs = useAgentMonitorStore(s => s.logs);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevel, setFilterLevel] = useState<string | null>(null);

  const filteredLogs = filterLevel ? logs.filter(l => l.level === filterLevel) : logs;

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLogs.length, autoScroll]);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  }, []);

  const levelFilters = ['all', 'info', 'success', 'warn', 'error'];

  return (
    <div className="agent-log-stream">
      <div className="agent-log-toolbar">
        <span className="agent-panel-title">📋 Live Log</span>
        <div className="agent-log-filters">
          {levelFilters.map(lv => (
            <button
              key={lv}
              className={`agent-log-filter-btn ${(lv === 'all' && !filterLevel) || lv === filterLevel ? 'active' : ''}`}
              onClick={() => setFilterLevel(lv === 'all' ? null : lv)}
              aria-label={lv === 'all' ? '전체 로그 레벨' : `${lv} 로그만 표시`}
              aria-pressed={(lv === 'all' && !filterLevel) || lv === filterLevel}
            >
              {lv === 'all' ? 'All' : lv}
            </button>
          ))}
        </div>
        <span className="agent-log-count">{filteredLogs.length} entries</span>
      </div>
      <div className="agent-log-entries" ref={scrollRef} onScroll={handleScroll}>
        {filteredLogs.length === 0 ? (
          <div className="agent-log-empty">에이전트 활동 대기 중...</div>
        ) : (
          filteredLogs.map(entry => {
            const lc = LOG_LEVEL_CONFIG[entry.level] || LOG_LEVEL_CONFIG.info;
            return (
              <div key={entry.id} className="agent-log-entry" style={{ borderLeftColor: lc.color }}>
                <span className="agent-log-time">{formatTime(entry.timestamp)}</span>
                <span className="agent-log-icon" style={{ color: lc.color }}>{lc.icon}</span>
                <span className="agent-log-source">[{entry.source}]</span>
                <span className="agent-log-message">{entry.message}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

/* ─── Task Progress ─────────────────────────────────────────── */

const TaskProgressList: React.FC = () => {
  const currentTasks = useAgentMonitorStore(s => s.currentTasks);

  if (currentTasks.length === 0) {
    return (
      <div className="agent-task-section">
        <span className="agent-panel-title">📊 Tasks</span>
        <div className="agent-task-empty">No active tasks</div>
      </div>
    );
  }

  return (
    <div className="agent-task-section">
      <span className="agent-panel-title">📊 Tasks ({currentTasks.length})</span>
      <div className="agent-task-list">
        {currentTasks.map(task => (
          <div key={task.id} className="agent-task-item glass-panel">
            <div className="agent-task-header">
              <span className="agent-task-icon">{TASK_STATUS_ICONS[task.status] || '📋'}</span>
              <span className="agent-task-title">{task.title}</span>
              <span className={`agent-task-status-badge status-${task.status}`}>
                {task.status === 'running' ? `${task.progress}%` : task.status}
              </span>
            </div>
            {task.status === 'running' && (
              <div className="agent-task-progress-wrap">
                <div
                  className="agent-task-progress-bar"
                  style={{
                    width: `${task.progress}%`,
                    transition: 'width 0.5s ease',
                  }}
                />
              </div>
            )}
            {task.startedAt && (
              <div className="agent-task-meta">
                <span>Started: {formatTime(task.startedAt)}</span>
                {task.completedAt && <span> · Completed: {formatTime(task.completedAt)}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* ─── Execution Timeline ────────────────────────────────────── */

const TIMELINE_EVENT_COLORS: Record<string, string> = {
  tool_start: '#7aa2f7',
  tool_end: '#9ece6a',
  task_start: '#7aa2f7',
  task_end: '#9ece6a',
  error: '#f7768e',
  plan: '#e0af68',
  approval: '#e0af68',
  mode_change: '#7c82a8',
  agent_turn: '#7aa2f7',
  quality: '#e0af68',
  anti_pattern: '#f7768e',
};

const ExecutionTimeline: React.FC = () => {
  const timeline = useAgentMonitorStore(s => s.timeline);

  return (
    <div className="agent-timeline-section">
      <span className="agent-panel-title">📜 Timeline ({timeline.length})</span>
      <div className="agent-timeline-list">
        {timeline.length === 0 ? (
          <div className="agent-timeline-empty">No events yet</div>
        ) : (
          timeline.slice(0, 30).map(event => (
            <div key={event.id} className="agent-timeline-event">
              <span className="agent-timeline-dot" style={{
                background: TIMELINE_EVENT_COLORS[event.type] ?? '#7c82a8',
              }} />
              <span className="agent-timeline-time">{formatTime(event.timestamp)}</span>
              <span className="agent-timeline-label">{event.label}</span>
              {event.detail && <span className="agent-timeline-detail">{event.detail}</span>}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

/* ─── Main Panel ────────────────────────────────────────────── */

const AgentMonitorPanel: React.FC = () => {
  return (
    <div className="agent-monitor-dashboard">
      {/* Top Row: Status */}
      <AgentStatusCard />

      {/* Middle: Two-column layout */}
      <div className="agent-monitor-columns">
        <div className="agent-monitor-left">
          <LiveLogStream />
        </div>
        <div className="agent-monitor-right">
          <TaskProgressList />
        </div>
      </div>

      {/* Bottom: Timeline */}
      <ExecutionTimeline />
    </div>
  );
};

export default AgentMonitorPanel;
