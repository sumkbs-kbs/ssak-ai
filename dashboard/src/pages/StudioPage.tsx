/**
 * StudioPage — Unsloth Studio No-Code Fine-Tuning Interface
 * ==========================================================
 * Inspired by unslothai/unsloth Studio:
 * 5-step guided pipeline for running, training, monitoring, and exporting models.
 */

import React, { useState, useEffect } from 'react';
import './StudioPage.css';
import { createAccessPinHeaders } from '../utils/accessPinCredential';
import { useUiStore } from '../stores/uiStore';
import { fetchStudioCapabilities, type StudioCapabilities } from './studioCapabilities';
import {
  cancelTrainingJob,
  fetchTrainingJob,
  fetchTrainingRecipes,
  startTrainingJob,
  type TrainingRecipe,
} from '../api/client';

interface StudioModelOption {
  id: string;
  name: string;
  architecture: string;
  quant: string;
  vram: string;
  recommended: boolean;
}

const DEFAULT_MODELS: StudioModelOption[] = [
  { id: 'unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_XL', name: 'Qwen 3.8 27B', architecture: 'Qwen', quant: 'UD-Q4_K_XL', vram: '16.8 GB', recommended: true },
  { id: 'unsloth/gemma-4-27B-it-GGUF:Q5_K_M', name: 'Gemma 4 27B', architecture: 'Gemma', quant: 'Q5_K_M', vram: '18.4 GB', recommended: true },
  { id: 'unsloth/DeepSeek-V4-Lite-GGUF:Q4_K_M', name: 'DeepSeek V4 Lite', architecture: 'DeepSeek', quant: 'Q4_K_M', vram: '9.2 GB', recommended: false },
  { id: 'mlx-community/Llama-3.2-3B-Instruct-4bit', name: 'Llama 3.2 3B (MLX)', architecture: 'Llama', quant: '4-bit MLX', vram: '2.4 GB', recommended: false },
];

export interface ValidationResult {
  message: string;
  type: 'error' | 'warning' | 'hint';
}

/**
 * Learning Rate format and range validation.
 * Supports scientific notation (2e-4, 5e-5) or decimal (0.0002).
 */
export function validateLearningRate(lr: string): ValidationResult | null {
  const trimmed = lr.trim();
  if (!trimmed) {
    return { type: 'error', message: '학습률(Learning Rate)을 입력하세요.' };
  }
  const lrRegex = /^[+]?([0-9]*\.[0-9]+|[0-9]+)([eE][-+]?[0-9]+)?$/;
  if (!lrRegex.test(trimmed)) {
    return { type: 'error', message: '올바른 학습률 형식(예: 2e-4 또는 0.0002)을 입력하세요.' };
  }
  const num = Number(trimmed);
  if (Number.isNaN(num) || num <= 0) {
    return { type: 'error', message: '학습률은 0보다 커야 합니다.' };
  }
  if (num > 0.01) {
    return { type: 'warning', message: '⚠️ 학습률이 너무 높습니다 (> 0.01). 모델이 발산할 수 있습니다.' };
  }
  if (num < 1e-7) {
    return { type: 'warning', message: '⚠️ 학습률이 너무 낮습니다 (< 1e-7). 학습 속도가 정체될 수 있습니다.' };
  }
  return null;
}

/**
 * Batch size validation with power-of-two recommendation hint.
 */
export function validateBatchSize(bs: number): ValidationResult | null {
  if (!Number.isInteger(bs) || bs < 1) {
    return { type: 'error', message: '배치 크기는 1 이상의 정수여야 합니다.' };
  }
  const isPowerOfTwo = (bs & (bs - 1)) === 0;
  if (!isPowerOfTwo) {
    return {
      type: 'hint',
      message: '💡 힌트: GPU VRAM 정렬 및 처리량 최적화를 위해 2의 거듭제곱(1, 2, 4, 8, 16, 32...)을 권장합니다.',
    };
  }
  return null;
}

export const StudioPage: React.FC = () => {
  const { addToast } = useUiStore();
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [capabilities, setCapabilities] = useState<StudioCapabilities | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);
  const localTraining = capabilities?.capabilities.find(c => c.operation === 'training' && c.provider === 'mlx');
  const canStartTraining = localTraining?.status === 'available';
  const capabilityStatus = capabilityLoading ? 'loading' : localTraining?.status ?? 'unknown';
  const [selectedModel, setSelectedModel] = useState<string>(DEFAULT_MODELS[0].id);

  // Hyperparameters
  const [loraRank, setLoraRank] = useState<number>(16);
  const [loraAlpha, setLoraAlpha] = useState<number>(32);
  const [learningRate, setLearningRate] = useState<string>('2e-4');
  const [batchSize, setBatchSize] = useState<number>(4);

  // Recipe presets (Phase 24): 백엔드 카탈로그의 감사된 하이퍼파라미터
  const [recipes, setRecipes] = useState<TrainingRecipe[]>([]);
  const [selectedRecipeName, setSelectedRecipeName] = useState<string>('');

  useEffect(() => {
    fetchTrainingRecipes()
      .then(res => setRecipes(res.recipes))
      .catch(() => setRecipes([])); // 카탈로그 조회 실패 시 프리셋 없이 수동 입력만 허용
  }, []);

  useEffect(() => {
    let active = true;
    fetchStudioCapabilities()
      .then(snapshot => { if (active) setCapabilities(snapshot); })
      .catch(() => { if (active) setCapabilities(null); })
      .finally(() => { if (active) setCapabilityLoading(false); });
    return () => { active = false; };
  }, []);

  const selectedRecipe = recipes.find(r => r.name === selectedRecipeName);

  const applyRecipePreset = (name: string) => {
    setSelectedRecipeName(name);
    const recipe = recipes.find(r => r.name === name);
    if (!recipe) return;
    const hp = recipe.hyperparameters;
    if (typeof hp.learning_rate === 'string' || typeof hp.learning_rate === 'number') {
      setLearningRate(String(hp.learning_rate));
    }
    if (typeof hp.batch_size === 'number') setBatchSize(hp.batch_size);
    if (typeof hp.lora_rank === 'number') setLoraRank(hp.lora_rank);
    if (typeof hp.lora_alpha === 'number') setLoraAlpha(hp.lora_alpha);
    if (typeof hp.iterations === 'number' || typeof hp.iterations === 'string') {
      setIterations(Number(hp.iterations));
    }
  };

  // Hyperparameter Validation (with inline warnings & power-of-two hints)
  const lrValidation = validateLearningRate(learningRate);
  const batchValidation = validateBatchSize(batchSize);

  const handleGoToStep5 = () => {
    if (lrValidation && lrValidation.type === 'error') {
      addToast(`Learning Rate 오류: ${lrValidation.message}`, 'error');
      return;
    }
    if (batchValidation && batchValidation.type === 'error') {
      addToast(`Batch Size 오류: ${batchValidation.message}`, 'error');
      return;
    }
    setCurrentStep(5);
  };

  const [iterations, setIterations] = useState<number>(600);

  // Dataset
  const [datasetName, setDatasetName] = useState<string>('sample_instruction_dataset.jsonl');

  // Training status & Live Loss
  const [isTraining, setIsTraining] = useState<boolean>(false);
  const [trainingProgress, setTrainingProgress] = useState<number>(0);
  const [currentLoss, setCurrentLoss] = useState<number | null>(null);
  const [lossHistory, setLossHistory] = useState<number[]>([]);

  // Phase 59: 시뮬레이션 타이머 제거 — 실제 백엔드 잡 폴링으로 대체 (activeJobId useEffect)

  // Load models from API if available
  useEffect(() => {
    fetch('/v1/models', { headers: createAccessPinHeaders() })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && Array.isArray(data.data) && data.data.length > 0) {
          const apiModel = data.data[0].id;
          if (apiModel) setSelectedModel(apiModel);
        }
      })
      .catch(() => {});
  }, []);

  /** 마지막으로 시작한 실제 백엔드 학습 잡 (Phase 59). */
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  /** 백엔드 잡 폴링 — progress/loss를 실제 값으로 갱신 (시뮬레이션 아님). */
  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    const poll = async () => {
      try {
        const job = await fetchTrainingJob(activeJobId);
        if (stopped) return;
        setTrainingProgress(job.progress);
        if (typeof job.loss === 'number' && Number.isFinite(job.loss)) {
          const loss = job.loss;
          setCurrentLoss(loss);
          setLossHistory(hist => [...hist.slice(-15), loss]);
        }
        if (job.status === 'completed') {
          setActiveJobId(null);
          setIsTraining(false);
          addToast(`🎉 학습 완료 — ${job.records}건 데이터셋, config: ${job.config_path}`, 'success');
        } else if (job.status === 'failed') {
          setActiveJobId(null);
          setIsTraining(false);
          addToast(`학습 실패: ${job.error || '원인 불명'}`, 'error');
        }
      } catch {
        // 폴링 실패는 다음 틱에서 재시도 (백엔드 일시 응답 없음)
      }
    };
    void poll();
    const interval = setInterval(poll, 1500);
    return () => {
      stopped = true;
      clearInterval(interval);
    };
  }, [activeJobId, addToast]);

  const handleStartTraining = async () => {
    if (!canStartTraining || lrValidation?.type === 'error' || batchValidation?.type === 'error') return;
    setIsTraining(true);
    setTrainingProgress(0);
    setCurrentLoss(null);
    setLossHistory([]);
    addToast('Unsloth Studio: 백엔드 학습 잡을 시작합니다 (apply_recipe → mlx-lm).', 'info');

    try {
      const hyperparameters: Record<string, number | string> = {
        lora_rank: loraRank,
        lora_alpha: loraAlpha,
        learning_rate: learningRate,
        batch_size: batchSize,
        iterations,
      };
      const { job_id } = await startTrainingJob({
        recipe: selectedRecipe?.name ?? 'chat-sft',
        base_model: selectedModel,
        source: datasetName === 'harvest' ? 'harvest' : datasetName,
        platform: 'auto',
        hyperparameters,
      });
      setActiveJobId(job_id);
    } catch (err) {
      setIsTraining(false);
      const message = err instanceof Error ? err.message : String(err);
      addToast(`학습 시작 실패: ${message}`, 'error');
    }
  };

  const handleCancelTraining = async () => {
    if (activeJobId) {
      try {
        await cancelTrainingJob(activeJobId);
      } catch {
        // 취소 실패 — 잡 상태는 폴링이 정리
      }
      setActiveJobId(null);
    }
    setIsTraining(false);
  };

  return (
    <div className="unsloth-studio-container">
      {/* Studio Header */}
      <header className="unsloth-studio-header">
        <div className="unsloth-studio-title-block">
          <div className="unsloth-logo-badge">🦥</div>
          <div>
            <div className="unsloth-badge-row">
              <h1 className="unsloth-studio-title">Unsloth Studio</h1>
              <span className="unsloth-tag-pro">FAST NO-CODE LLM FINE-TUNING</span>
              <span className="unsloth-tag-accel">LOCAL MLX TRAINING</span>
            </div>
            <p className="unsloth-studio-subtitle">
              로컬 MLX 학습 작업을 시작하고 백엔드가 보고한 진행률과 손실을 확인합니다. GGUF 내보내기와 모델 등록은 현재 연결되어 있지 않습니다.
            </p>
          </div>
        </div>

        {/* Global Hardware Pill */}
        <div className="unsloth-telemetry-card">
          <div className="telemetry-item">
            <span className="telemetry-label">Backend</span>
            <span className="telemetry-val highlight">{canStartTraining ? 'MLX' : '확인되지 않음'}</span>
          </div>
          <div className="telemetry-item">
            <span className="telemetry-label">System Memory (Available / Total)</span>
            <span className="telemetry-val" data-testid="studio-memory">
              {capabilities ? `${(capabilities.system.memory.available_bytes / 1024 ** 3).toFixed(1)} / ${(capabilities.system.memory.total_bytes / 1024 ** 3).toFixed(1)} GB` : '—'}
            </span>
          </div>
          <div className="telemetry-item">
            <span className="telemetry-label">Status</span>
            <span className={`telemetry-val status ${isTraining ? 'training' : canStartTraining ? 'ready' : ''}`} data-capability-status={capabilityStatus} role="status">
              <span className="dot" /> {isTraining ? 'Training Active' : capabilityLoading ? '확인 중' : canStartTraining ? 'MLX 사용 가능' : localTraining ? 'MLX 사용 불가' : '상태 확인 불가'}
            </span>
          </div>
        </div>
      </header>

      {/* Stepper Bar */}
      <nav className="unsloth-stepper-bar" aria-label="Studio Pipeline Steps">
        {[
          { num: 1, label: 'Base Model', desc: '모델 선택 & 양자화' },
          { num: 2, label: 'Method', desc: 'LoRA / QLoRA / DPO' },
          { num: 3, label: 'Dataset', desc: '데이터 로드 & 검증' },
          { num: 4, label: 'Parameters', desc: '하이퍼파라미터' },
          { num: 5, label: 'Monitor & Export', desc: '학습 & GGUF 내보내기' },
        ].map(step => (
          <button
            key={step.num}
            type="button"
            className={`unsloth-step-btn ${currentStep === step.num ? 'active' : ''}`}
            aria-current={currentStep === step.num ? 'step' : undefined}
            onClick={() => setCurrentStep(step.num)}
          >
            <span className="step-num">{step.num}</span>
            <div className="step-text">
              <span className="step-title">{step.label}</span>
              <span className="step-desc">{step.desc}</span>
            </div>
          </button>
        ))}
      </nav>

      {/* Step Content Area */}
      <div className="unsloth-step-body">
        {/* STEP 1: Model Selection */}
        {currentStep === 1 && (
          <section className="unsloth-card">
            <div className="card-header">
              <h2>1. 기본 모델 선택 (Select Base Model)</h2>
              <p>아래 모델은 선택 예시이며 설치·학습 호환성은 확인되지 않았습니다. 학습 시작 시 백엔드에서 모델과 소스를 검증합니다.</p>
            </div>
            <div className="unsloth-model-grid">
              {DEFAULT_MODELS.map(m => (
                <div
                  key={m.id}
                  className={`unsloth-model-card ${selectedModel === m.id ? 'selected' : ''}`}
                  onClick={() => setSelectedModel(m.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter') setSelectedModel(m.id); }}
                >
                  <div className="model-card-header">
                    <span className="model-name">{m.name}</span>
                    {m.recommended && <span className="chip-recommended">선택 예시</span>}
                  </div>
                  <div className="model-chips">
                    <span className="chip-pill">{m.architecture}</span>
                    <span className="chip-pill quant">{m.quant}</span>
                    <span className="chip-pill vram">예상 메모리 {m.vram}</span>
                  </div>
                  <div className="model-id">{m.id}</div>
                </div>
              ))}
            </div>
            <div className="step-actions">
              <button type="button" className="unsloth-btn-primary" onClick={() => setCurrentStep(2)}>
                다음: 학습 방법 선택 →
              </button>
            </div>
          </section>
        )}

        {/* STEP 2: Training Method */}
        {currentStep === 2 && (
          <section className="unsloth-card">
            <div className="card-header">
              <h2>2. 학습 방법론 선택 (Training Method)</h2>
              <p>이 화면은 로컬 MLX 레시피 학습을 사용합니다. 학습 방법 선택은 현재 시작 API에 연결되어 있지 않습니다.</p>
            </div>
            <div className="unsloth-method-grid">
              {[
                { id: 'qlora', title: 'QLoRA (4-bit Quantized)', desc: '최소 VRAM 소비로 대규모 27B 모델까지 일반 맥북에서 학습 가능.', tag: '가장 인기' },
                { id: 'lora', title: 'Standard LoRA (16-bit)', desc: '원형 16-bit 정밀도를 유지하며 빠른 수렴 속도를 제공.', tag: '고정밀' },
                { id: 'dpo', title: 'DPO (Direct Preference)', desc: 'Chosen/Rejected 선호도 쌍 데이터를 사용한 인간 선호 정렬 학습.', tag: '선호 정렬' },
                { id: 'full', title: 'Full Fine-Tuning', desc: '모든 레이어의 가중치를 직접 업데이트 (고성능 다중 GPU 권장).', tag: '최대 표현력' },
              ].map(m => (
                <div
                  key={m.id}
                  className="unsloth-method-card"
                >
                  <div className="method-header">
                    <span className="method-title">{m.title}</span>
                    <span className="method-tag">선택 연결 안 됨</span>
                  </div>
                  <p className="method-desc">{m.desc}</p>
                </div>
              ))}
            </div>
            <div className="step-actions">
              <button type="button" className="unsloth-btn-secondary" onClick={() => setCurrentStep(1)}>
                ← 이전
              </button>
              <button type="button" className="unsloth-btn-primary" onClick={() => setCurrentStep(3)}>
                다음: 데이터셋 로드 →
              </button>
            </div>
          </section>
        )}

        {/* STEP 3: Dataset Ingestion */}
        {currentStep === 3 && (
          <section className="unsloth-card">
            <div className="card-header">
              <h2>3. 데이터셋 로드 &amp; 포맷 (Dataset &amp; Data Recipes)</h2>
              <p>백엔드가 읽을 수 있는 데이터 파일 경로나 harvest 소스를 입력하세요. 파일 업로드는 현재 연결되어 있지 않습니다.</p>
            </div>
            <div className="unsloth-dropzone">
              <span className="drop-icon">📂</span>
              <p className="drop-prompt">파일 업로드 연결 안 됨</p>
              <span className="drop-sub">아래 소스 경로 입력을 사용하세요.</span>
            </div>

            <div className="dataset-meta-row">
              <div className="meta-field">
                <label htmlFor="ds-name">소스 (파일 경로 또는 'harvest')</label>
                <input
                  id="ds-name"
                  type="text"
                  value={datasetName}
                  onChange={e => setDatasetName(e.target.value)}
                  className="unsloth-input"
                  placeholder="data/harvest.csv 또는 harvest"
                />
              </div>
              <div className="meta-field">
                <label htmlFor="ds-tokens">추정 토큰 수 (확인·전달 안 됨)</label>
                <input
                  id="ds-tokens"
                  type="number"
                  value=""
                  className="unsloth-input"
                  disabled
                />
              </div>
              <div className="meta-field">
                <label htmlFor="ds-split">Train / Validation 분할 (설정 전달 안 됨)</label>
                <input
                  id="ds-split"
                  type="range"
                  min="70"
                  max="95"
                  value={90}
                  className="unsloth-range"
                  disabled
                />
              </div>
            </div>

            <div className="step-actions">
              <button type="button" className="unsloth-btn-secondary" onClick={() => setCurrentStep(2)}>
                ← 이전
              </button>
              <button type="button" className="unsloth-btn-primary" onClick={() => setCurrentStep(4)}>
                다음: 하이퍼파라미터 설정 →
              </button>
            </div>
          </section>
        )}

        {/* STEP 4: Hyperparameters */}
        {currentStep === 4 && (
          <section className="unsloth-card">
            <div className="card-header">
              <h2>4. 하이퍼파라미터 튜닝 (Hyperparameters)</h2>
              <p>레시피 프리셋(감사된 값)을 불러오거나 Unsloth 권장 설정 위에서 세부 수치를 조정할 수 있습니다.</p>
            </div>

            {/* 레시피 프리셋 선택기 — 백엔드 카탈로그(/api/recipes)의 감사된 하이퍼파라미터를 필드에 채움 */}
            <div className="recipe-preset-row">
              <label htmlFor="recipe-preset">데이터 레시피 프리셋</label>
              <select
                id="recipe-preset"
                className="unsloth-select"
                value={selectedRecipeName}
                onChange={e => applyRecipePreset(e.target.value)}
              >
                <option value="">— 프리셋 없이 직접 입력 —</option>
                {recipes.map(r => (
                  <option key={r.name} value={r.name}>
                    {r.title} ({r.name})
                  </option>
                ))}
              </select>
              {selectedRecipe && (
                <span className="recipe-preset-values">
                  레시피 참고값 (활성 입력 항목만 전달): {Object.entries(selectedRecipe.hyperparameters).map(([k, v]) => `${k}=${v}`).join(' · ')}
                </span>
              )}
            </div>

            <div className="param-grid">
              <div className="param-group">
                <label htmlFor="p-rank">LoRA Rank (r)</label>
                <select id="p-rank" value={loraRank} onChange={e => setLoraRank(Number(e.target.value))} className="unsloth-select">
                  <option value={8}>8 (초경량)</option>
                  <option value={16}>16 (기본 권장)</option>
                  <option value={32}>32 (복잡한 추론/코딩)</option>
                  <option value={64}>64 (대규모 변환)</option>
                </select>
                <span className="param-help">낮을수록 적은 VRAM을 사용하며 학습 속도가 빨라집니다.</span>
              </div>

              <div className="param-group">
                <label htmlFor="p-alpha">LoRA Alpha</label>
                <input id="p-alpha" type="number" value={loraAlpha} onChange={e => setLoraAlpha(Number(e.target.value))} className="unsloth-input" />
                <span className="param-help">가중치 스케일링 계수 (보통 rank의 2배 권장).</span>
              </div>

              <div className="param-group">
                <label htmlFor="p-lr">Learning Rate</label>
                <input
                  id="p-lr"
                  type="text"
                  value={learningRate}
                  onChange={e => setLearningRate(e.target.value)}
                  className={`unsloth-input ${lrValidation ? (lrValidation.type === 'error' ? 'input-error' : 'input-warning') : ''}`}
                  aria-invalid={lrValidation?.type === 'error'}
                  aria-describedby="p-lr-feedback"
                />
                {lrValidation ? (
                  <div
                    id="p-lr-feedback"
                    className={`param-inline-warning ${lrValidation.type}`}
                    role={lrValidation.type === 'error' ? 'alert' : 'status'}
                  >
                    {lrValidation.message}
                  </div>
                ) : (
                  <span id="p-lr-feedback" className="param-help">권장: 2e-4 (LoRA), 5e-5 (Full fine-tune).</span>
                )}
              </div>

              <div className="param-group">
                <label htmlFor="p-batch">Batch Size (per device)</label>
                <input
                  id="p-batch"
                  type="number"
                  value={batchSize}
                  onChange={e => setBatchSize(Number(e.target.value))}
                  className={`unsloth-input ${batchValidation ? (batchValidation.type === 'error' ? 'input-error' : 'input-warning') : ''}`}
                  aria-invalid={batchValidation?.type === 'error'}
                  aria-describedby="p-batch-feedback"
                />
                {batchValidation ? (
                  <div
                    id="p-batch-feedback"
                    className={`param-inline-warning ${batchValidation.type}`}
                    role={batchValidation.type === 'error' ? 'alert' : 'status'}
                  >
                    {batchValidation.message}
                  </div>
                ) : (
                  <span id="p-batch-feedback" className="param-help">메모리 오버플로우 방지를 위해 적정값 유지.</span>
                )}
              </div>

              <div className="param-group">
                <label htmlFor="p-epochs">Epochs</label>
                <input id="p-epochs" type="number" value="" className="unsloth-input" disabled aria-describedby="studio-epochs-unavailable" />
                <span id="studio-epochs-unavailable" className="param-help">로컬 MLX는 Epochs를 지원하지 않습니다. Iterations를 사용하세요.</span>
                <span className="param-help">전체 데이터셋 반복 학습 횟수.</span>
              </div>

              <div className="param-group">
                <label htmlFor="p-iters">Iterations (mlx)</label>
                <input id="p-iters" type="number" value={iterations} onChange={e => setIterations(Number(e.target.value))} className="unsloth-input" />
                <span className="param-help">mlx-lm 학습 반복 수 (레시피 프리셋 선택 시 감사된 값 적용).</span>
              </div>

              <div className="param-group">
                <label htmlFor="p-opt">Optimizer</label>
                <select id="p-opt" value="" className="unsloth-select" disabled aria-describedby="studio-optimizer-unavailable">
                  <option value="">연결 안 됨</option>
                  <option value="adamw_8bit">AdamW 8-bit (75% VRAM 절감)</option>
                  <option value="paged_adamw_8bit">Paged AdamW 8-bit (스파이크 방지)</option>
                  <option value="adamw_torch">Standard AdamW 16-bit</option>
                </select>
                <span id="studio-optimizer-unavailable" className="param-help">Optimizer 선택은 현재 학습 시작 API에 연결되어 있지 않습니다.</span>
              </div>
            </div>

            <div className="step-actions">
              <button type="button" className="unsloth-btn-secondary" onClick={() => setCurrentStep(3)}>
                ← 이전
              </button>
              <button
                type="button"
                className="unsloth-btn-primary"
                onClick={handleGoToStep5}
                disabled={Boolean(lrValidation?.type === 'error' || batchValidation?.type === 'error')}
              >
                다음: 모니터링 &amp; 학습 시작 →
              </button>
            </div>
          </section>
        )}

        {/* STEP 5: Live Monitor & Loss Curve */}
        {currentStep === 5 && (
          <section className="unsloth-card monitor-card">
            <div className="card-header">
              <div className="flex-between">
                <div>
                  <h2>5. 실시간 학습 모니터링 &amp; 모델 내보내기 (Monitor &amp; Export)</h2>
                  <p>학습 작업이 보고한 손실과 진행률을 표시합니다. {localTraining?.detail ?? '로컬 학습 가능 여부를 확인해야 합니다.'}</p>
                </div>
                {!isTraining && trainingProgress < 100 && (
                  <button type="button" className="unsloth-btn-launch" onClick={handleStartTraining} disabled={!canStartTraining || lrValidation?.type === 'error' || batchValidation?.type === 'error'}>
                    🚀 파인튜닝 시작 (Start Training)
                  </button>
                )}
                {isTraining && (
                  <button type="button" className="unsloth-btn-danger" onClick={() => { void handleCancelTraining(); }}>
                    ⏹ 학습 중단
                  </button>
                )}
              </div>
            </div>

            {/* Metrics HUD */}
            <div className="unsloth-hud-row">
              <div className="hud-metric">
                <span className="hud-lbl">Current Loss</span>
                <span className="hud-val loss">{currentLoss?.toFixed(3) ?? '—'}</span>
              </div>
              <div className="hud-metric">
                <span className="hud-lbl">Progress</span>
                <span className="hud-val">{trainingProgress}%</span>
              </div>
              <div className="hud-metric">
                <span className="hud-lbl">Speed</span>
                <span className="hud-val speed">—</span>
              </div>
              <div className="hud-metric">
                <span className="hud-lbl">Target Model</span>
                <span className="hud-val model">{selectedModel.split('/').pop()?.split(':')[0]}</span>
              </div>
            </div>

            {/* Loss Curve SVG Visualization */}
            <div className="unsloth-loss-chart-container">
              <div className="chart-header">
                <span>실시간 손실 곡선 (Training Loss Curve)</span>
                <span className="chart-legend">● Step Loss</span>
              </div>
              <svg className="unsloth-loss-svg" viewBox="0 0 600 180" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="lossGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7c6aef" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#7c6aef" stopOpacity="0.0" />
                  </linearGradient>
                </defs>
                {/* Horizontal Grid lines */}
                <line x1="0" y1="30" x2="600" y2="30" stroke="rgba(255,255,255,0.06)" strokeDasharray="4" />
                <line x1="0" y1="80" x2="600" y2="80" stroke="rgba(255,255,255,0.06)" strokeDasharray="4" />
                <line x1="0" y1="130" x2="600" y2="130" stroke="rgba(255,255,255,0.06)" strokeDasharray="4" />

                {/* Plot line & Area */}
                {lossHistory.length > 0 && (() => {
                  const points = lossHistory.map((val, idx) => {
                    const x = (idx / (lossHistory.length - 1 || 1)) * 580 + 10;
                    const y = 160 - ((val - 0.4) / (3.0 - 0.4)) * 140;
                    return `${x},${y}`;
                  }).join(' ');

                  const areaPoints = `10,170 ${points} 590,170`;

                  return (
                    <>
                      <polygon points={areaPoints} fill="url(#lossGradient)" />
                      <polyline fill="none" stroke="#7c6aef" strokeWidth="2.5" points={points} />
                      {lossHistory.map((val, idx) => {
                        const cx = (idx / (lossHistory.length - 1 || 1)) * 580 + 10;
                        const cy = 160 - ((val - 0.4) / (3.0 - 0.4)) * 140;
                        return (
                          <circle
                            key={idx}
                            cx={cx}
                            cy={cy}
                            r={idx === lossHistory.length - 1 ? 4 : 2}
                            fill={idx === lossHistory.length - 1 ? '#06b6d4' : '#7c6aef'}
                          />
                        );
                      })}
                    </>
                  );
                })()}
              </svg>
            </div>

            {/* Export & Deployment Section */}
            <div className="unsloth-export-bar">
              <div className="export-info">
                <h3>📦 원클릭 모델 배포 &amp; 내보내기 (Export &amp; Deploy)</h3>
                <p id="studio-export-unavailable" role="status">현재 백엔드에는 GGUF 파일 내보내기와 Ollama 등록 API가 연결되어 있지 않습니다. 학습 완료만으로 배포 파일이 생성되지는 않습니다.</p>
              </div>
              <div className="export-btns">
                <button
                  type="button"
                  className="unsloth-btn-export"
                  disabled
                  aria-describedby="studio-export-unavailable"
                >
                  GGUF Q4_K_M 내보내기
                </button>
                <button
                  type="button"
                  className="unsloth-btn-export"
                  disabled
                  aria-describedby="studio-export-unavailable"
                >
                  GGUF Q8_0 (고정밀)
                </button>
                <button
                  type="button"
                  className="unsloth-btn-export highlight"
                  disabled
                  aria-describedby="studio-export-unavailable"
                >
                  🦥 로컬 모델로 즉시 등록
                </button>
              </div>
            </div>

          </section>
        )}
      </div>
    </div>
  );
};

export default StudioPage;
