/**
 * DataExtractionPage — Data Extraction Dashboard
 * ================================================
 * Orchestrator component — delegates to sub-components in ./dex/
 */

import React, { useState, useCallback, useEffect } from 'react';
import { ZodError } from 'zod';
import { ApiHttpError, isAuthRequiredError } from '../api/client';
import type { ExtractionData, MetricsData, ABTestReport } from './dex/types';
import { ExtractionDataSchema, loadExtractionMetrics, searchExtraction, runExtractionABTest } from './dex/extractionApi';
import MetricsBar from './dex/MetricsBar';
import SearchHeader from './dex/SearchHeader';
import ABTestSection from './dex/ABTestSection';
import PipelineStatus from './dex/PipelineStatus';
import StockPanel from './dex/StockPanel';
import WeatherExchangePanel from './dex/WeatherExchangePanel';
import BottomPanels from './dex/BottomPanels';

function describeError(error: unknown): string {
  if (isAuthRequiredError(error)) return '인증이 필요합니다. PIN 인증을 완료한 뒤 다시 시도하세요.';
  if (error instanceof ApiHttpError) return `요청에 실패했습니다 (HTTP ${error.status}). 다시 시도하세요.`;
  if (error instanceof ZodError) return '서버 응답을 읽을 수 없습니다. 다시 시도하세요.';
  return error instanceof Error ? error.message : '요청에 실패했습니다. 다시 시도하세요.';
}

function readStoredResult(): ExtractionData | null {
  try {
    const saved = sessionStorage.getItem('dex_last_result');
    if (!saved) return null;
    const parsed: unknown = JSON.parse(saved);
    const result = ExtractionDataSchema.safeParse(parsed);
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

const DataExtractionPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<ExtractionData | null>(readStoredResult);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [abtestResults, setAbtestResults] = useState<ABTestReport | null>(null);
  const [abtestRunning, setAbtestRunning] = useState(false);
  const [abtestError, setAbtestError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      setMetrics(await loadExtractionMetrics());
    } catch (error) {
      setMetricsError(describeError(error));
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadMetrics(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMetrics]);

  const handleSearch = useCallback(async () => {
    if (!query.trim() || searching) return;
    setSearching(true);
    setSearchError(null);
    try {
      const data = await searchExtraction(query);
      setResult(data);
      sessionStorage.setItem('dex_last_result', JSON.stringify(data));
    } catch (error: unknown) {
      setSearchError(describeError(error));
    } finally {
      setSearching(false);
    }
  }, [query, searching]);

  const handleABTest = async () => {
    if (abtestRunning) return;
    setAbtestRunning(true);
    setAbtestError(null);
    try {
      setAbtestResults(await runExtractionABTest());
    } catch (error) {
      setAbtestError(describeError(error));
    } finally {
      setAbtestRunning(false);
    }
  };

  const sp = result?.extracted?.stock_prices || [];
  const weather = result?.extracted?.weather || [];
  const exchange = result?.extracted?.exchange_rates || [];

  return (
    <div className="dex-page" style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      overflowY: 'auto', paddingBottom: 60,
    }}>
      <section aria-label="추출 메트릭" aria-busy={metricsLoading}>
        {metricsError ? <FailureNotice title="메트릭" error={metricsError} onRetry={loadMetrics} />
          : metricsLoading || metrics ? <MetricsBar metrics={metricsLoading ? null : metrics} />
            : <p role="status" className="dex-metrics-bar">메트릭 데이터가 없습니다.</p>}
      </section>
      <section aria-label="데이터 추출 검색" aria-busy={searching}>
        <SearchHeader
          query={query}
          searching={searching}
          onQueryChange={setQuery}
          onSearch={handleSearch}
        />
        {searchError && <FailureNotice title="데이터 추출" error={searchError} onRetry={handleSearch} />}
      </section>
      <section aria-label="추출 A/B 테스트" aria-busy={abtestRunning}>
        <ABTestSection
          results={abtestRunning || abtestError ? null : abtestResults}
          running={abtestRunning}
          onRun={handleABTest}
        />
        {abtestError && <FailureNotice title="A/B 테스트" error={abtestError} onRetry={handleABTest} />}
      </section>

      {/* Main Content */}
      <div id="dex-content" style={{ flex: 1, padding: '24px 32px' }}>
        {!result && !searching && !searchError ? (
          <div className="empty-state-container">
            <span style={{ fontSize: 64, opacity: 0.3 }}>🔬</span>
            <h2 className="empty-state-title">데이터 추출 대시보드</h2>
            <p className="empty-state-subtitle">
              위 검색창에 질문을 입력하면<br />
              <strong>TOP 1 JSON 추출</strong> → <strong>종목명 검증</strong> → <strong>만원/억원 변환</strong> 과정을 실시간으로 시각화합니다.
            </p>
          </div>
        ) : searching ? (
          <LoadingState />
        ) : result ? (
          <ResultView result={result} stocks={sp} weather={weather} exchange={exchange} />
        ) : null}
      </div>
    </div>
  );
};

/* ─── Loading State ──────────────────────────────────────────── */

const LoadingState: React.FC = () => (
  <div style={{
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    height: '50vh', gap: 24,
  }}>
    <div style={{
      width: 48, height: 48,
      border: '3px solid var(--glass-border)',
      borderTopColor: 'var(--accent-color)',
      borderRadius: '50%',
      animation: 'dex-spin 0.8s linear infinite',
    }} />
    <div style={{ textAlign: 'center' }}>
      <p style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>검색 + 데이터 추출 중...</p>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
        WebSearchTool → DataExtractor → 구조화 데이터
      </p>
    </div>
    {/* Skeleton Cards */}
    <div style={{ width: '100%', maxWidth: 600, marginTop: 8 }}>
      <div className="skeleton skeleton-card" style={{ height: 60 }} />
      <div className="skeleton skeleton-card" style={{ height: 80 }} />
      <div className="skeleton skeleton-card" style={{ height: 60, width: '70%' }} />
    </div>
  </div>
);

const FailureNotice: React.FC<{ readonly title: string; readonly error: string; readonly onRetry: () => void }> = ({ title, error, onRetry }) => (
  <div role="alert" style={{ padding: 'var(--space-3) var(--space-6)', color: 'var(--error-color)', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--space-3)' }}>
    <span style={{ flex: 1, overflowWrap: 'anywhere' }}>{title}: {error}</span>
    <button type="button" className="ghost-btn" aria-label={`${title} 다시 시도`} onClick={onRetry}>다시 시도</button>
  </div>
);

/* ─── Result View ────────────────────────────────────────────── */

interface ResultViewProps {
  result: ExtractionData;
  stocks: ExtractionData['extracted']['stock_prices'];
  weather: ExtractionData['extracted']['weather'];
  exchange: ExtractionData['extracted']['exchange_rates'];
}

const ResultView: React.FC<ResultViewProps> = ({ result, stocks, weather, exchange }) => (
  <>
    <div className="dex-card-enter">
      <PipelineStatus result={result} />
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }} className="dex-card-enter">
      <StockPanel stocks={stocks} />
      <WeatherExchangePanel weather={weather} exchange={exchange} />
    </div>
    <div className="dex-card-enter">
      <BottomPanels result={result} />
    </div>
  </>
);

export default DataExtractionPage;
