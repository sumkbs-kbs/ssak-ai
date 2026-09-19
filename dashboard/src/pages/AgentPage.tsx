/**
 * AgentPage — AI Agent Monitoring Dashboard
 * ===========================================
 * Replaces the old Kanban board with a comprehensive monitoring dashboard:
 * real-time log streaming, task progress bars, agent status panel,
 * execution timeline, and system metrics.
 */

import React, { useEffect } from 'react';
import AgentMonitorPanel from '../components/Agent/AgentMonitorPanel';
import { useAgentMonitorStore } from '../stores/agentMonitorStore';
import { useEventWebSocket } from '../hooks/useEventWebSocket';
import { useUiStore } from '../stores/uiStore';
import { checkHealth, fetchSystemMetrics } from '../api/client';
import { BrowserApprovalSection } from '../features/browser-approval/BrowserApprovalSection';
import { TaskExecutionPanel } from '../features/task-execution/TaskExecutionPanel';
import { PersistentAgencyPanel } from '../features/persistent-agency/PersistentAgencyPanel';

const AgentPage: React.FC = () => {
  const {
    setAgentStatus, addLog,
    addTimelineEvent, setActiveTool, updateMetrics, setUptime,
  } = useAgentMonitorStore();
  const { setSystemStatus } = useUiStore();

  // ── WebSocket integration for real-time monitoring ──────────
  useEventWebSocket({
    onToolExecutionStarted: (data) => {
      const toolName = data?.name || data?.tool_name || 'Unknown Tool';
      setActiveTool({
        name: toolName,
        startedAt: new Date().toISOString(),
        duration: 0,
        status: 'running',
      });
      setAgentStatus('running');
      addLog({ level: 'info', source: 'Tool', message: `▶ ${toolName} 실행 시작` });
      addTimelineEvent({ type: 'tool_start', label: `🔧 ${toolName}` });
    },

    onToolExecutionFinished: () => {
      // Read tool name BEFORE clearing
      const toolName = useAgentMonitorStore.getState().activeTool?.name || 'Tool';
      setAgentStatus('idle');
      setActiveTool(null);
      addLog({ level: 'success', source: 'Tool', message: `✓ ${toolName} 완료` });
      addTimelineEvent({ type: 'tool_end', label: `✅ ${toolName}` });
    },

    onFailureDetected: (data) => {
      setAgentStatus('error');
      addLog({ level: 'error', source: 'System', message: `❌ 오류 감지: ${data?.error || data?.message || 'Unknown error'}` });
      addTimelineEvent({ type: 'error', label: '❌ Failure', detail: data?.error });
    },

    onCognitiveAdaptation: (data) => {
      setAgentStatus('thinking');
      addLog({ level: 'info', source: 'Agent', message: `🧠 적응: ${data?.reason || data?.adaptation || ''}` });
    },

    onPlanningModeStarted: (data) => {
      setAgentStatus('planning');
      addLog({ level: 'info', source: 'Agent', message: `📋 계획 모드 시작: ${data?.goal || ''}` });
      addTimelineEvent({ type: 'plan', label: '📋 계획 시작', detail: data?.goal });
    },

    onApprovalRequired: (data) => {
      const tool = data?.tool || data?.request_id || '알 수 없는 도구';
      addLog({ level: 'warn', source: 'System', message: `🛑 승인 대기: ${tool} — ${data?.reason || '사용자 승인 필요'}` });
      addTimelineEvent({
        type: 'approval',
        label: `🛑 승인 대기: ${tool}`,
        detail: data?.reason || data?.request_id,
      });
    },

    onAgentTurnStarted: (data) => {
      const role = data?.role || 'WORKER';
      const taskType = data?.task_type || 'Task';
      addLog({ level: 'info', source: 'Agent', message: `🔄 턴 시작: [${role}] ${taskType}` });
      addTimelineEvent({ type: 'agent_turn', label: `🔄 턴 시작 [${role}]`, detail: taskType });
    },

    onAgentTurnEnded: (data) => {
      const role = data?.role || 'WORKER';
      addLog({ level: 'success', source: 'Agent', message: `✓ 턴 완료: [${role}]` });
      addTimelineEvent({ type: 'agent_turn', label: `✓ 턴 완료 [${role}]` });
    },

    onQualityCheckPassed: (data) => {
      const grade = data?.grade ? ` (${data.grade})` : '';
      addLog({ level: 'success', source: 'Quality', message: `🧪 품질 통과${grade}: ${data?.task_type || '작업'}` });
      addTimelineEvent({
        type: 'quality',
        label: `🧪 품질 통과${grade}`,
        detail: data?.score !== undefined ? `score=${data.score}` : undefined,
      });
    },

    onQualityCheckFailed: (data) => {
      setAgentStatus('error');
      const grade = data?.grade ? ` (${data.grade})` : '';
      addLog({ level: 'error', source: 'Quality', message: `❌ 품질 실패${grade}: ${data?.feedback || data?.task_type || '작업'}` });
      addTimelineEvent({
        type: 'quality',
        label: `❌ 품질 실패${grade}`,
        detail: data?.feedback || (data?.issues ?? []).join(', ') || undefined,
      });
    },

    onAntiPatternsDetected: (data) => {
      setAgentStatus('error');
      const patterns = (data?.patterns ?? []).join(', ');
      addLog({ level: 'warn', source: 'Agent', message: `⚠️ 안티패턴 감지: ${data?.reason || patterns || '반복 실패 패턴'}` });
      addTimelineEvent({
        type: 'anti_pattern',
        label: '⚠️ 안티패턴 감지',
        detail: patterns || data?.reason,
      });
    },

    onModeChanged: (data) => {
      const mode = data?.to_mode || 'interactive';
      addLog({ level: 'info', source: 'System', message: `🔄 모드 전환: ${mode.toUpperCase()}` });
      addTimelineEvent({ type: 'mode_change', label: `🔄 Mode: ${mode}` });
    },
  });

  // ── Poll system metrics ─────────────────────────────────────
  // CR-10: UPTIME은 **API 서버 프로세스**의 가동 시간이다. 대시보드 탭이 열린 시간을
  // 업타임으로 쓰지 않는다(둘을 섞지 않는다). 미응답이면 값을 조작하지 않고 그대로 둔다.
  useEffect(() => {
    const poll = async () => {
      try {
        const health = await checkHealth();
        setSystemStatus({
          healthy: health.status === 'ok',
          backends: health.backends || {},
        });

        const metrics = await fetchSystemMetrics();
        if (metrics.ok) {
          updateMetrics({
            memoryPercent: metrics.memory_percent ?? metrics.memory_mb ?? null,
            cpuPercent: metrics.cpu_percent ?? null,
            totalTokens: metrics.total_tokens ?? null,
          });
          if (metrics.uptime_seconds !== undefined) {
            setUptime(metrics.uptime_seconds);
          }
        }
      } catch (caught: unknown) {
        if (!(caught instanceof Error)) throw caught;
        // 연결이 끊기면 health를 주장할 수 없다.
        setSystemStatus({ healthy: null, backends: {} });
      }
    };

    poll();
    const interval = setInterval(poll, 5000);

    return () => {
      clearInterval(interval);
    };
  }, [setSystemStatus, setUptime, updateMetrics]);

  return (
    <div className="page-container full-height-page agent-page">
      <div className="page-header">
        <div className="page-header-hero">
          <div className="hero-eyebrow">AGENT MONITORING</div>
          <h2>에이전트 모니터링</h2>
          <p className="page-subtitle">AI 에이전트의 실시간 상태, 로그 스트림, 작업 진행 상황을 모니터링합니다.</p>
        </div>
      </div>
      <AgentMonitorPanel />
      <PersistentAgencyPanel />
      <TaskExecutionPanel />
      {/* task 18: 에이전트의 브라우저 **효과**는 사람이 승인한다(일반 도구 승인과 다른 계약). */}
      <BrowserApprovalSection />
    </div>
  );
};

export default AgentPage;
