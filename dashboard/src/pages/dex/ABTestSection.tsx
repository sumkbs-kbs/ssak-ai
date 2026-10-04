/**
 * ABTestSection — A/B Test runner + results
 * ===========================================
 */

import React from 'react';
import { ABTestReport, ABTestCase } from './types';

interface Props {
  results: ABTestReport | null;
  running: boolean;
  onRun: () => void;
}

const ABTestSection: React.FC<Props> = ({ results, running, onRun }) => {
  return (
    <div className="dex-abtest" style={{ padding: '12px 24px', borderBottom: '1px solid var(--glass-border)', background: 'rgba(124,106,239,0.03)' }}>
      <div className="dex-abtest-controls" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 16 }}>🧪</span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>추출 정확도 A/B 테스트</span>
        <span id="dex-abtest-status" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {results ? `✅ 완료 (${results.avg_accuracy}%)` : running ? '실행 중...' : '대기 중'}
        </span>
        <button
          onClick={onRun}
          disabled={running}
          style={{
            marginLeft: 'auto', padding: '6px 16px', borderRadius: 6,
            fontSize: 12, fontWeight: 600,
            background: 'linear-gradient(135deg,var(--accent-color),#8b5cf6)',
            border: 'none', color: 'white', cursor: 'pointer',
          }}
        >
          {running ? '⏳' : '▶'} A/B 테스트 실행
        </button>
      </div>
      {results && <ABTestReportPanel report={results} />}
    </div>
  );
};

/* ─── ABTestReportPanel ─────────────────────────────────────── */

const ABTestReportPanel: React.FC<{ report: ABTestReport }> = ({ report }) => {
  const { avg_accuracy, avg_duration_ms, total_cases, passed, failed, by_tag, comparisons } = report;
  const accuracyColor = avg_accuracy >= 80 ? '#10b981' : avg_accuracy >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ marginTop: 10 }}>
      {/* Summary Cards */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <SummaryCard value={`${avg_accuracy}%`} label="평균 정확도" valueColor={accuracyColor} />
        <SummaryCard value={String(total_cases)} label={`✅ ${passed} | ❌ ${failed}`} />
        <SummaryCard value={`${avg_duration_ms.toFixed(0)}ms`} label="평균 실행 시간" />
      </div>

      {/* Tags */}
      {by_tag && Object.keys(by_tag).length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
          {Object.entries(by_tag).map(([tag, acc]) => (
            <span key={tag} style={{
              padding: '3px 8px', borderRadius: 4, background: 'rgba(124,106,239,0.1)',
              color: (acc as number) >= 80 ? '#10b981' : '#f59e0b', fontSize: 11,
              border: '1px solid rgba(124,106,239,0.2)',
            }}>
              🏷️ {tag}: {acc}%
            </span>
          ))}
        </div>
      )}

      {/* Per-case Details */}
      {comparisons && comparisons.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
            케이스별 상세
          </div>
          {comparisons.map(c => <TestCaseRow key={c.case_name} testCase={c} />)}
        </div>
      )}
    </div>
  );
};

/* ─── SummaryCard ───────────────────────────────────────────── */

const SummaryCard: React.FC<{ value: string; label: string; valueColor?: string }> = ({ value, label, valueColor }) => (
  <div style={{
    flex: 1, minWidth: 100, padding: 12, borderRadius: 8,
    background: 'rgba(0,0,0,0.3)', border: '1px solid var(--glass-border)',
    textAlign: 'center',
  }}>
    <div style={{ fontSize: 28, fontWeight: 700, color: valueColor || 'var(--text-primary)' }}>{value}</div>
    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</div>
  </div>
);

/* ─── TestCaseRow ───────────────────────────────────────────── */

const TestCaseRow: React.FC<{ testCase: ABTestCase }> = ({ testCase: c }) => {
  const cColor = c.accuracy_pct >= 80 ? '#10b981' : c.accuracy_pct >= 50 ? '#f59e0b' : '#ef4444';
  const cIcon = !c.has_expected ? '⏭️' : c.accuracy_pct >= 100 ? '✅' : c.accuracy_pct >= 80 ? '🟡' : c.accuracy_pct >= 50 ? '🟠' : '❌';

  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: 6, background: 'rgba(0,0,0,0.2)',
        fontSize: 11, cursor: 'pointer', transition: 'background 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.4)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.2)'; }}
    >
      <span>{cIcon}</span>
      <span style={{ flex: 1 }}>{c.case_name}</span>
      <span style={{ color: cColor, fontWeight: 600 }}>{c.accuracy_pct}%</span>
      <span style={{ color: 'var(--text-muted)' }}>{c.fields_matched}/{c.fields_total}</span>
      <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{c.duration_ms.toFixed(0)}ms</span>
    </div>
  );
};

export default ABTestSection;
