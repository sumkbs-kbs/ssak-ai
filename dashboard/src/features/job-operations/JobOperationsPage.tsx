import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactElement } from 'react';

import type { JobHealth, JobRun, ScheduledJob } from './jobOperationsApi';
import { fetchJobHealth, fetchJobRuns, fetchScheduledJobs, retryJobRun } from './jobOperationsApi';

type RunStatus = JobRun['status'];

const assertNever = (value: never): never => {
  throw new Error(`Unexpected job run status: ${String(value)}`);
};

function runStatusLabel(status: RunStatus): string {
  switch (status) {
    case 'submitted': return 'Submitted';
    case 'running': return 'Running';
    case 'succeeded': return 'Succeeded';
    case 'failed': return 'Failed';
    default: return assertNever(status);
  }
}

function formatDate(value: Date | null): string {
  if (value === null) return '—';
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(value);
}

function formatSchedule(job: ScheduledJob): string {
  switch (job.schedule.kind) {
    case 'once': return `Once · ${formatDate(job.schedule.run_at)}`;
    case 'interval': return `Every ${Math.round((job.schedule.interval_seconds ?? 0) / 60)} min`;
    case 'cron': return `Cron · ${job.schedule.cron ?? '—'}`;
    default: return assertNever(job.schedule.kind);
  }
}

export function JobOperationsPage(): ReactElement {
  const [health, setHealth] = useState<JobHealth | null>(null);
  const [jobs, setJobs] = useState<readonly ScheduledJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [runs, setRuns] = useState<readonly JobRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);

  const loadRuns = useCallback(async (jobId: string): Promise<void> => {
    setRunsLoading(true);
    setError(null);
    try {
      setRuns(await fetchJobRuns(jobId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const loadSnapshot = useCallback(async (preferredJobId: string | null): Promise<void> => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const [nextHealth, nextJobs] = await Promise.all([fetchJobHealth(), fetchScheduledJobs()]);
      const nextJobId = preferredJobId ?? nextJobs[0]?.job_id ?? null;
      const nextRuns = nextJobId === null ? [] : await fetchJobRuns(nextJobId);
      setHealth(nextHealth);
      setJobs(nextJobs);
      setSelectedJobId(nextJobId);
      setRuns(nextRuns);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSnapshot(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSnapshot]);

  const selectedJob = useMemo(
    () => jobs.find(job => job.job_id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );

  const handleSelectJob = (jobId: string): void => {
    setSelectedJobId(jobId);
    void loadRuns(jobId);
  };

  const handleRetry = async (run: JobRun): Promise<void> => {
    if (selectedJobId === null) return;
    setRetryingRunId(run.run_id);
    setError(null);
    setNotice(null);
    try {
      await retryJobRun(selectedJobId, run.run_id);
      setNotice(`Retry submitted for ${run.run_id}.`);
      await loadRuns(selectedJobId);
      const nextHealth = await fetchJobHealth();
      setHealth(nextHealth);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRetryingRunId(null);
    }
  };

  if (loading && health === null) {
    return <section className="page-container job-operations-page" aria-busy="true" aria-label="Job operations"><p className="job-operations-loading">Loading job operations…</p></section>;
  }

  if (health === null) {
    return (
      <section className="page-container job-operations-page" aria-label="Job operations">
        <section className="glass-panel job-operations-error" role="alert">
          <h1>Job Operations</h1>
          <p>{error ?? 'The job operations snapshot could not be loaded.'}</p>
          <button className="btn-primary" type="button" aria-label="Retry loading job operations" onClick={() => void loadSnapshot(null)}>
            Retry loading
          </button>
        </section>
      </section>
    );
  }

  const successRate = health.completed_runs === 0 ? null : `${Math.round(health.success_rate * 100)}%`;

  return (
    <section className="page-container job-operations-page" aria-label="Job operations">
      <header className="job-operations-header">
        <div>
          <p className="hero-eyebrow">JOB OPERATIONS</p>
          <h1>Job Operations</h1>
          <p className="page-subtitle">Scheduled work, under control. 실패율·정체 실행·전달 오류를 한 화면에서 확인하고 안전하게 재시도합니다.</p>
        </div>
        <div className="job-operations-actions">
          <span className={`job-health-badge ${health.healthy ? 'is-healthy' : 'is-risk'}`} role="status">
            <span className="job-health-dot" aria-hidden="true" />
            {health.healthy ? 'Healthy' : 'Needs attention'}
          </span>
          <button className="btn-secondary" type="button" onClick={() => void loadSnapshot(selectedJobId)} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {!health.healthy && (
        <section className="job-operations-alert" role="alert" aria-labelledby="job-alert-title">
          <div>
            <p className="job-alert-kicker">Policy alert</p>
            <h2 id="job-alert-title">Scheduled work needs attention</h2>
            <ul>{health.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
          </div>
          <span className="job-alert-rate">{successRate === null ? 'No completed runs' : `${successRate} success`}</span>
        </section>
      )}

      {error !== null && <p className="job-operations-inline-error" role="alert">{error}</p>}
      {notice !== null && <p className="job-operations-notice" role="status" aria-live="polite">{notice}</p>}

      <section className="job-health-grid" aria-label="Job health summary">
        <article className="job-metric-tile"><span>Success rate</span><strong>{successRate ?? '—'}</strong><small>{health.completed_runs === 0 ? 'No completed runs' : `${health.completed_runs} completed runs`}</small></article>
        <article className="job-metric-tile"><span>Active jobs</span><strong>{health.active_jobs}</strong><small>{health.paused_jobs} paused</small></article>
        <article className="job-metric-tile"><span>Failed runs</span><strong className={health.failed_runs > 0 ? 'is-danger' : ''}>{health.failed_runs}</strong><small>{health.run_window} run window</small></article>
        <article className="job-metric-tile"><span>Open / stale</span><strong>{health.open_runs} / {health.stale_runs}</strong><small>{health.delivery_failed_runs} delivery failures</small></article>
      </section>

      <section className="job-operations-layout" aria-label="Scheduled jobs and run history">
        <div className="glass-panel job-list-panel">
          <div className="job-panel-heading"><div><p className="job-alert-kicker">Schedules</p><h2>Scheduled jobs</h2></div><span className="job-panel-count">{jobs.length}</span></div>
          {jobs.length === 0 ? <p className="job-empty-state">No scheduled jobs yet.</p> : (
            <div className="job-list" role="list">
              {jobs.map(job => (
                <div key={job.job_id} role="listitem">
                  <button className={`job-list-item ${job.job_id === selectedJobId ? 'is-selected' : ''}`} type="button" onClick={() => handleSelectJob(job.job_id)} aria-pressed={job.job_id === selectedJobId} aria-label={job.name}>
                    <span className={`job-status-mark ${job.status === 'active' ? 'is-active' : 'is-paused'}`} aria-hidden="true" />
                    <span className="job-list-copy"><strong>{job.name}</strong><small>{formatSchedule(job)}</small></span>
                    <span className="job-list-state">{job.status}</span>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="glass-panel job-runs-panel">
          <div className="job-panel-heading"><div><p className="job-alert-kicker">Execution history</p><h2>{selectedJob?.name ?? 'Select a job'}</h2></div><span className="job-panel-count">{runs.length}</span></div>
          {runsLoading ? <p className="job-empty-state">Loading run history…</p> : runs.length === 0 ? <p className="job-empty-state">No runs recorded for this job.</p> : (
            <ol className="job-run-list">
              {runs.map(run => (
                <li key={run.run_id} className={`job-run-row status-${run.status}`}>
                  <div className="job-run-main"><span className="job-run-status">{runStatusLabel(run.status)}</span><code>{run.run_id}</code><time dateTime={run.started_at.toISOString()}>{formatDate(run.started_at)}</time></div>
                  <div className="job-run-detail">{run.status === 'failed' ? <span className="job-run-error">{run.error || 'Run failed without an error message.'}</span> : <span>{run.output || 'No output recorded.'}</span>}
                    {run.status === 'failed' && <button className="btn-secondary job-retry-button" type="button" onClick={() => void handleRetry(run)} disabled={retryingRunId !== null} aria-label={`Retry ${run.run_id}`}>{retryingRunId === run.run_id ? 'Submitting…' : 'Retry run'}</button>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </section>
  );
}
