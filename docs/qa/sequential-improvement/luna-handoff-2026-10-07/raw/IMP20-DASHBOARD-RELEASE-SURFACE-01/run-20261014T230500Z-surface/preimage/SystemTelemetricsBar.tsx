import { useEffect, useRef, useState, type FC } from 'react';
import { useUiStore, type SystemConnectionState } from '../../stores/uiStore';
import { getUiBuildInfo } from '../../utils/uiBuildInfo';
import { AppIcon } from '../UI/AppIcon';

export const STALE_AFTER_MS = 30_000;
const UNKNOWN = 'UNKNOWN';
const CONNECTION_LABEL: Record<SystemConnectionState, string> = {
  unknown: 'UNKNOWN', live: 'LIVE', stale: 'STALE', disconnected: 'OFFLINE',
};
const CONNECTION_CLASS: Record<SystemConnectionState, string> = {
  unknown: 'telemetrics-stat-dim', live: 'telemetrics-stat-green',
  stale: 'telemetrics-stat-amber', disconnected: 'telemetrics-stat-amber',
};

export function formatUptime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (value: number) => String(value).padStart(2, '0');
  if (days > 0) return `${days}D ${pad(hours)}H ${pad(minutes)}M`;
  if (hours > 0) return `${hours}H ${pad(minutes)}M`;
  return `${minutes}M ${pad(secs)}S`;
}

export function formatAge(observedAt: number, now: number): string {
  const elapsed = Math.max(0, now - observedAt);
  if (elapsed < 1000) return 'now';
  const seconds = Math.floor(elapsed / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export function deriveConnectionState(base: SystemConnectionState, observedAt: number | null, now: number): SystemConnectionState {
  if (base === 'disconnected') return 'disconnected';
  if (observedAt === null || base === 'unknown') return 'unknown';
  return now - observedAt > STALE_AFTER_MS ? 'stale' : 'live';
}

export const SystemTelemetricsBar: FC = () => {
  const systemStatus = useUiStore(state => state.systemStatus);
  const [now, setNow] = useState(() => Date.now());
  const [disclosureOpen, setDisclosureOpen] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const summaryRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!disclosureOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || detailsRef.current?.closest('[inert]')) return;
      event.preventDefault();
      if (detailsRef.current) detailsRef.current.open = false;
      setDisclosureOpen(false);
      summaryRef.current?.focus();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [disclosureOpen]);

  const { observedAt, state: baseState, healthy, version, buildId, processId } = systemStatus;
  const connection = deriveConnectionState(baseState, observedAt, now);
  const isLive = connection === 'live';
  const ui = getUiBuildInfo();
  const serverBuild = version ? `v${version}${buildId ? ` · ${buildId}` : ''}` : null;
  const buildLabel = serverBuild === null ? UNKNOWN : ui.version === version ? serverBuild : `${serverBuild} (ui v${ui.version})`;
  const uptimeLabel = systemStatus.uptimeSeconds === null ? UNKNOWN : formatUptime(systemStatus.uptimeSeconds + (isLive && observedAt !== null ? (now - observedAt) / 1000 : 0));
  const healthState = healthy === null ? UNKNOWN : healthy ? 'NOMINAL' : 'DEGRADED';
  const nodeLabel = processId === null ? UNKNOWN : `PID-${processId} · ${healthState}`;
  const cpuLabel = systemStatus.cpuPercent === null ? UNKNOWN : `${systemStatus.cpuPercent.toFixed(1)}%`;
  const memLabel = systemStatus.memoryPercent === null ? UNKNOWN : `${systemStatus.memoryPercent.toFixed(1)}%`;
  const vaultLabel = systemStatus.ragFiles === null ? UNKNOWN : `${systemStatus.ragFiles} INDEXED`;
  const linkDetail = observedAt === null ? '' : ` · ${formatAge(observedAt, now)}`;

  return (
    <header className="workspace-status-bar telemetrics-bar" aria-label="시스템 상태">
      <span className="workspace-status-label">워크스페이스</span>
      <details ref={detailsRef} className="workspace-status-disclosure" onToggle={event => setDisclosureOpen(event.currentTarget.open)}>
        <summary ref={summaryRef} className="workspace-status-summary" aria-label="서버 연결 및 시스템 지표">
          <span className="workspace-status-dot" data-connection={connection} aria-hidden="true" />
          <span className="workspace-status-name">서버</span>
          <span className={CONNECTION_CLASS[connection]} data-testid="telemetrics-link" data-connection={connection}>{CONNECTION_LABEL[connection]}{linkDetail}</span>
          <AppIcon name="chevronDown" size={16} />
        </summary>
        <section className="workspace-status-popover" aria-label="시스템 상세 지표">
          <h2>시스템 상태</h2>
          <dl className="workspace-status-metrics">
            <dt>서버 빌드</dt><dd data-testid="telemetrics-build">{buildLabel}</dd>
            <dt>서버 가동 시간</dt><dd data-testid="telemetrics-uptime">{uptimeLabel}</dd>
            <dt>프로세스</dt><dd className={healthy === true ? 'telemetrics-stat-green' : 'telemetrics-stat-dim'} data-testid="telemetrics-node" data-health={healthy === null ? 'unknown' : String(healthy)}>{nodeLabel}</dd>
            <dt>CPU</dt><dd data-testid="telemetrics-cpu">{cpuLabel}</dd>
            <dt>메모리</dt><dd data-testid="telemetrics-mem">{memLabel}</dd>
            <dt>볼트</dt><dd data-testid="telemetrics-vault">{vaultLabel}</dd>
          </dl>
          <p className="workspace-status-note">마지막 성공 관측 기준 · 서버 지표 10초마다 갱신</p>
        </section>
      </details>
    </header>
  );
};

export default SystemTelemetricsBar;
