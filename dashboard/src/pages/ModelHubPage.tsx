/**
 * ModelHubPage — Unsloth Desktop Inspired Model Hub & Discovery
 * ===============================================================
 * Explore, download, swap, and manage state-of-the-art LLMs, Vision,
 * and MLX/GGUF models with automatic VRAM requirements & quantizations.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useUiStore } from '../stores/uiStore';
import { fetchLocalModels, loadModel, type LocalModelItem } from '../api/client';
import { quantQuality, type QuantQualityLevel } from '../utils/quantQuality';
import { QuantBadge } from '../components/shared';

export type QuantTierFilter = 'any' | 'balanced-up' | 'high-up' | 'premium-only';

export type HubSortKey = 'default' | 'name' | 'disk-asc' | 'disk-desc' | 'vram-asc' | 'vram-desc';

/** 디스크/VRAM 정렬 옵션 (Phase 43) */
const HUB_SORT_OPTIONS: { id: HubSortKey; label: string }[] = [
  { id: 'default', label: '기본순' },
  { id: 'disk-asc', label: '디스크 작은순' },
  { id: 'disk-desc', label: '디스크 큰순' },
  { id: 'vram-asc', label: 'VRAM 작은순' },
  { id: 'vram-desc', label: 'VRAM 큰순' },
  { id: 'name', label: '이름순' },
];

/** 등급 필터 프리셋 — quantQuality 레벨의 서열(unknown < compact < balanced < high < premium) 기반 */
const QUANT_TIER_FILTERS: { id: QuantTierFilter; label: string; title: string; levels: Set<QuantQualityLevel> | null }[] = [
  { id: 'any', label: '품질 전체', title: '모든 품질 등급 표시', levels: null },
  {
    id: 'balanced-up',
    label: '⭐ 균형 이상',
    title: 'balanced / high / premium — unsloth 권장 스위트스팟(Q4_K·IQ4·5bit 이상)',
    levels: new Set(['balanced', 'high', 'premium']),
  },
  {
    id: 'high-up',
    label: '⭐⭐ 높음 이상',
    title: 'high / premium — 품질 저하 미미(Q5_K·Q6_K·Q8·F16)',
    levels: new Set(['high', 'premium']),
  },
  { id: 'premium-only', label: '💎 프리미엄만', title: 'premium — 원본 손실 거의 없음(Q8_0·F16·BF16)', levels: new Set(['premium']) },
];

interface HubDisplayModel {
  id: string;
  name: string;
  provider: string;
  category: 'all' | 'running' | 'unsloth' | 'mlx' | 'embedding' | 'llm';
  params: string;
  context: string;
  quantization: string;
  quantLevel: QuantQualityLevel;
  vram: string;
  diskSize: string;
  diskSizeGb: number;
  vramGb: number;
  diskPath: string;
  description: string;
  status: LocalModelItem['status'];
  isLocal: boolean;
}

export const ModelHubPage: React.FC = () => {
  const { selectedModel, setSelectedModel } = useChatStore();
  const { addToast } = useUiStore();
  const [filterCategory, setFilterCategory] = useState<'all' | 'running' | 'unsloth' | 'mlx' | 'embedding' | 'llm'>('all');
  const [quantTierFilter, setQuantTierFilter] = useState<QuantTierFilter>('any');
  const [sortBy, setSortBy] = useState<HubSortKey>('default');
  const [minDiskGb, setMinDiskGb] = useState<number>(0);
  const [minVramGb, setMinVramGb] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [localModels, setLocalModels] = useState<LocalModelItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingModelId, setLoadingModelId] = useState<string | null>(null);

  const loadModels = useCallback(async (refresh = false) => {
    setIsLoading(true);
    try {
      const res = await fetchLocalModels(refresh);
      if (res.ok && res.models) {
        setLocalModels(res.models);
      }
    } catch (err) {
      console.error('Failed to load local models in ModelHub:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadModels(false);
  }, [loadModels]);

  const handleSelectModel = async (modelId: string) => {
    setLoadingModelId(modelId);
    try {
      const res = await loadModel(modelId);
      if (res.ok) {
        setSelectedModel(modelId);
        addToast(`✅ 모델이 성공적으로 로드되었습니다: ${modelId.split('/').pop()}`, 'success');
        void loadModels(false);
      } else {
        addToast(`❌ 모델 로드 실패: ${res.message || '알 수 없는 오류'}`, 'error');
      }
    } catch (err) {
      addToast(`❌ 모델 로드 오류: ${err instanceof Error ? err.message : String(err)}`, 'error');
    } finally {
      setLoadingModelId(null);
    }
  };

  // Convert LocalModelItem to HubDisplayModel
  const displayModels: HubDisplayModel[] = localModels.map((m) => {
    let cat: 'all' | 'running' | 'unsloth' | 'mlx' | 'embedding' | 'llm' = 'llm';
    if (m.status === 'running') cat = 'running';
    else if (m.provider === 'unsloth') cat = 'unsloth';
    else if (m.provider === 'mlx') cat = 'mlx';
    else if (m.role === 'embedding') cat = 'embedding';

    const paramStr = m.parameter_count_b > 0
      ? `${m.parameter_count_b}B`
      : (m.disk_size_gb > 0 ? `${m.disk_size_gb} GB` : 'Local');

    return {
      id: m.id,
      name: m.name || m.id,
      provider: m.provider.toUpperCase(),
      category: cat,
      params: paramStr,
      context: m.context_length ? `${Math.round(m.context_length / 1024)}K` : 'Auto',
      quantization: m.quantization || (m.status === 'running' ? 'Active' : 'N/A'),
      quantLevel: quantQuality(m.quantization || (m.status === 'running' ? 'Active' : 'N/A')).level,
      vram: m.parameter_count_b > 0 ? `~${Math.round(m.parameter_count_b * 0.7)} GB` : (m.disk_size_gb > 0 ? `~${Math.round(m.disk_size_gb)} GB` : 'N/A'),
      diskSize: m.disk_size_gb > 0 ? `${m.disk_size_gb} GB` : (m.status === 'running' ? 'Ollama 메모리' : '로컬 디스크'),
      diskSizeGb: m.disk_size_gb > 0 ? m.disk_size_gb : 0,
      vramGb: m.parameter_count_b > 0 ? Math.round(m.parameter_count_b * 0.7) : (m.disk_size_gb > 0 ? Math.round(m.disk_size_gb) : 0),
      diskPath: m.disk_path || '',
      description: m.description || `본 PC에 설치된 ${m.provider} 로컬 모델.`,
      status: m.status,
      isLocal: true,
    };
  });

  const quantTierPreset = QUANT_TIER_FILTERS.find((t) => t.id === quantTierFilter);
  const filteredModels = displayModels.filter((m) => {
    if (filterCategory !== 'all') {
      if (filterCategory === 'running' && m.status !== 'running') return false;
      if (filterCategory === 'unsloth' && m.provider !== 'UNSLOTH') return false;
      if (filterCategory === 'mlx' && m.provider !== 'MLX') return false;
      if (filterCategory === 'embedding' && m.category !== 'embedding') return false;
      if (filterCategory === 'llm' && (m.category === 'embedding' || m.provider === 'MLX')) return false;
    }
    if (
      quantTierPreset?.levels &&
      m.status !== 'running' &&
      !quantTierPreset.levels.has(m.quantLevel)
    ) {
      // 실행 중 모델은 등급 필터에서 면제 — 활성 모델이 품질 브라우징 중 숨지 않도록.
      // (실행 중 모델은 quantization이 비어 unknown(?)으로 등급돼 '균형 이상' 필터에 걸리기 쉬움)
      return false;
    }
    if (minDiskGb > 0 && m.diskSizeGb > 0 && m.diskSizeGb < minDiskGb) {
      // 디스크 용량 하한 — 미지(0) 모델은 제외하지 않음 (용량 미보고 모델이 필터에 묻히지 않도록)
      return false;
    }
    if (minVramGb > 0 && m.vramGb > 0 && m.vramGb < minVramGb) {
      return false;
    }
    if (
      searchQuery.trim() &&
      !m.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !m.id.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !m.provider.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  const sortedModels: HubDisplayModel[] = sortBy === 'default'
    ? filteredModels
    : [...filteredModels].sort((a, b) => {
        switch (sortBy) {
          case 'disk-asc': return a.diskSizeGb - b.diskSizeGb;
          case 'disk-desc': return b.diskSizeGb - a.diskSizeGb;
          case 'vram-asc': return a.vramGb - b.vramGb;
          case 'vram-desc': return b.vramGb - a.vramGb;
          case 'name': return a.name.localeCompare(b.name);
          default: return 0;
        }
      });

  const hasResourceFilter = minDiskGb > 0 || minVramGb > 0 || sortBy !== 'default';

  return (
    <div className="unsloth-hub-container">
      {/* Header */}
      <header className="unsloth-hub-header">
        <div className="hub-title-section">
          <div className="hub-icon">📦</div>
          <div>
            <div className="flex-align-center gap-8">
              <h1 className="hub-title">Model Hub</h1>
              <span className="hub-badge">UNSLOTH & LOCAL ECOSYSTEM</span>
            </div>
            <p className="hub-sub">
              본 PC에 설치된 Ollama 모델, Unsloth GGUF 다운로드 모델, Apple MLX 캐시 모델을 실시간으로 감지하고 원클릭으로 로드합니다.
            </p>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="hub-filter-bar">
          <div className="hub-search-box">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder="모델명, 아키텍처 또는 공급자 검색..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="hub-search-input"
            />
          </div>

          <div className="hub-category-pills">
            {([
              { id: 'all', label: `전체 (${displayModels.length})` },
              { id: 'running', label: `🟢 실행 중 (${displayModels.filter((m) => m.status === 'running').length})` },
              { id: 'unsloth', label: `🦥 Unsloth GGUF (${displayModels.filter((m) => m.provider === 'UNSLOTH').length})` },
              { id: 'mlx', label: `Apple MLX (${displayModels.filter((m) => m.provider === 'MLX').length})` },
              { id: 'embedding', label: `Embedding (${displayModels.filter((m) => m.category === 'embedding').length})` },
            ] satisfies ReadonlyArray<{ readonly id: HubDisplayModel['category']; readonly label: string }>).map((cat) => (
              <button
                key={cat.id}
                type="button"
                className={`hub-cat-btn ${filterCategory === cat.id ? 'active' : ''}`}
                onClick={() => setFilterCategory(cat.id)}
              >
                {cat.label}
              </button>
            ))}

          </div>

          {/* 디스크/VRAM 정렬 + 최소 용량 범위 필터 (Phase 43) */}
          <div className="hub-resource-filter">
            <select
              className="hub-sort-select"
              aria-label="정렬 기준"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as HubSortKey)}
            >
              {HUB_SORT_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
            <label className="hub-min-gb-input" title="이 디스크 용량(GB) 이상 모델만 표시">
              <span className="hub-min-gb-label">디스크 ≥</span>
              <input
                type="number"
                min={0}
                step={1}
                aria-label="최소 디스크 용량 (GB)"
                value={minDiskGb}
                onChange={(e) => setMinDiskGb(Math.max(0, Number(e.target.value) || 0))}
              />
              <span className="hub-min-gb-label">GB</span>
            </label>
            <label className="hub-min-gb-input" title="이 VRAM 요구량(GB) 이상 모델만 표시">
              <span className="hub-min-gb-label">VRAM ≥</span>
              <input
                type="number"
                min={0}
                step={1}
                aria-label="최소 VRAM 요구량 (GB)"
                value={minVramGb}
                onChange={(e) => setMinVramGb(Math.max(0, Number(e.target.value) || 0))}
              />
              <span className="hub-min-gb-label">GB</span>
            </label>
            {hasResourceFilter && (
              <button
                type="button"
                className="hub-cat-btn"
                title="정렬·용량 필터 초기화"
                onClick={() => { setSortBy('default'); setMinDiskGb(0); setMinVramGb(0); }}
              >
                ✕ 초기화
              </button>
            )}
          </div>

          {/* 품질 등급 필터 pill row — 균형 이상 등 unsloth 품질 가이드 기반 브라우징 */}
          <div className="hub-quant-tier-pills">
            {QUANT_TIER_FILTERS.map((tier) => (
              <button
                key={tier.id}
                type="button"
                className={`hub-cat-btn hub-quant-tier-btn ${quantTierFilter === tier.id ? 'active' : ''}`}
                title={tier.title}
                onClick={() => setQuantTierFilter(tier.id)}
              >
                {tier.label}
              </button>
            ))}
            <span className="hub-quant-tier-count">
              {quantTierPreset?.levels ? `${filteredModels.length}개 표시` : ''}
            </span>
            <button
              type="button"
              className="hub-cat-btn"
              style={{ marginLeft: 'auto' }}
              disabled={isLoading}
              onClick={() => void loadModels(true)}
              title="본 PC 로컬 모델 다시 검색"
            >
              {isLoading ? '스캔 중...' : '↻ PC 모델 재검색'}
            </button>
            </div>
        </div>
      </header>

      {/* Model Grid */}
      <div className="hub-models-grid">
        {filteredModels.length === 0 ? (
          <div className="model-empty-notice" style={{ gridColumn: '1 / -1', padding: '40px 20px' }}>
            {isLoading
              ? '본 PC의 로컬 모델을 스캔하고 있습니다...'
              : '해당 조건에 맞는 로컬 모델을 찾을 수 없습니다.'}
          </div>
        ) : (
          sortedModels.map((model) => {
            const isActive = selectedModel === model.id;

            return (
              <div key={model.id} className={`hub-card ${isActive ? 'active-model' : ''}`}>
                <div className="hub-card-top">
                  <div className="hub-model-identity">
                    <span className={`provider-tag ${model.provider.toLowerCase()}`}>{model.provider}</span>
                    <h2 className="model-display-name">{model.name}</h2>
                  </div>
                  {model.status === 'running' ? (
                    <span className="popular-badge" style={{ background: '#dcfce7', color: '#15803d' }}>
                      🟢 실행 중
                    </span>
                  ) : (
                    <span className="spec-badge" style={{ fontSize: '10px' }}>
                      {model.status === 'installed' ? '설치됨' : model.status === 'cached' ? '로컬 캐시' : '실행 상태 미확인'}
                    </span>
                  )}
                  {isActive && <span className="active-badge">선택된 모델</span>}
                </div>

                <p className="model-desc-text">{model.description}</p>

                {/* Specs Chips */}
                <div className="model-specs-row">
                  <div className="spec-badge">
                    <span className="spec-key">Params</span>
                    <span className="spec-val">{model.params}</span>
                  </div>
                  <div className="spec-badge">
                    <span className="spec-key">디스크 용량</span>
                    <span className="spec-val highlight">{model.diskSize}</span>
                  </div>
                  <div className="spec-badge">
                    <span className="spec-key">VRAM 요구</span>
                    <span className="spec-val">{model.vram}</span>
                  </div>
                  <div className="spec-badge">
                    <span className="spec-key">양자화</span>
                    <span className="quant-quality-wrap">
                      <span className="spec-val">{model.quantization}</span>
                      <QuantBadge quantization={model.quantization} variant="grade" />
                    </span>
                  </div>
                </div>

                {/* Footer Actions */}
                <div className="hub-card-footer">
                  <div className="card-status-info">
                    <span className="status-indicator local">
                      {model.status === 'running' ? '런타임 실행 확인됨' : model.status === 'installed' ? '로컬 설치 확인됨' : model.status === 'cached' ? '로컬 캐시 확인됨' : '실행 상태 미확인'}
                    </span>
                  </div>
                  <div className="card-actions">
                    <button
                      type="button"
                      className={`hub-action-btn ${isActive ? 'current' : 'swap'}`}
                      disabled={loadingModelId === model.id}
                      onClick={() => void handleSelectModel(model.id)}
                    >
                      {loadingModelId === model.id
                        ? '⏳ 런타임 로딩 중...'
                        : (isActive ? '선택된 모델' : '⚡ 모델 활성화 (Load)')}
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default ModelHubPage;
