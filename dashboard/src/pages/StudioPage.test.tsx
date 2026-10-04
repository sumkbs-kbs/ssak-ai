import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StudioPage, { validateLearningRate, validateBatchSize } from './StudioPage';
import ToastContainer from '../components/UI/ToastContainer';

/** fetch 목 — URL별로 다른 응답 (Phase 59: 실제 잡 시작/폴링 검증). */
const mockFetchByUrl = (routes: Record<string, unknown>) => {
  const responses: Readonly<Record<string, unknown>> = {
    '/v1/integrations/unsloth/capabilities': {
      system: { memory: { total_bytes: 32 * 1024 ** 3, available_bytes: 12 * 1024 ** 3 } },
      capabilities: [{ operation: 'training', provider: 'mlx', status: 'available', detail: 'fixture' }],
    },
    ...routes,
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      // 가장 구체적인(긴) 경로가 우선 — job 폴링이 시작 POST보다 우선
      const match = Object.keys(responses)
        .sort((a, b) => b.length - a.length)
        .find(k => url.includes(k));
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(match ? responses[match] : {}),
      });
    }),
  );
};

describe('StudioPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ data: [{ id: 'unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_XL' }] }),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Studio title, pipeline stepper, and step 1 by default', () => {
    render(<StudioPage />);

    expect(screen.getByText('Unsloth Studio')).toBeInTheDocument();
    expect(screen.getByText('FAST NO-CODE LLM FINE-TUNING')).toBeInTheDocument();
    expect(screen.getByText('1. 기본 모델 선택 (Select Base Model)')).toBeInTheDocument();
    expect(screen.getByText('다음: 학습 방법 선택 →')).toBeInTheDocument();
  });

  it('navigates through steps when clicking step buttons or action buttons', () => {
    render(<StudioPage />);

    // Click next
    fireEvent.click(screen.getByText('다음: 학습 방법 선택 →'));
    expect(screen.getByText('2. 학습 방법론 선택 (Training Method)')).toBeInTheDocument();

    // Click next again to dataset
    fireEvent.click(screen.getByText('다음: 데이터셋 로드 →'));
    expect(screen.getByText('3. 데이터셋 로드 & 포맷 (Dataset & Data Recipes)')).toBeInTheDocument();

    // Step 4
    fireEvent.click(screen.getByText('다음: 하이퍼파라미터 설정 →'));
    expect(screen.getByText('4. 하이퍼파라미터 튜닝 (Hyperparameters)')).toBeInTheDocument();

    // Step 5
    fireEvent.click(screen.getByText('다음: 모니터링 & 학습 시작 →'));
    expect(screen.getByText(/5\. 실시간 학습 모니터링/)).toBeInTheDocument();
    expect(screen.getByText('🚀 파인튜닝 시작 (Start Training)')).toBeInTheDocument();
  });

  it('starts a real backend job and reflects actual progress/loss from polling (Phase 59)', async () => {
    mockFetchByUrl({
      '/v1/models': { data: [{ id: 'unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_XL' }] },
      '/api/recipes': { ok: true, recipes: [] },
      '/api/training-jobs': { ok: true, job_id: 'train_abc123' },
      '/api/training-jobs/train_abc123': {
        job_id: 'train_abc123',
        status: 'completed',
        recipe: 'chat-sft',
        platform: 'mlx',
        dataset_path: 'data/training_jobs/x/recipe_dataset.jsonl',
        config_path: 'data/training_jobs/x/lora_config.json',
        records: 12,
        sufficient: true,
        progress: 100,
        loss: 0.87,
        log_tail: ['iter 5: loss=0.87'],
        error: '',
        started_at: 0,
        finished_at: 1,
      },
    });
    render(
      <>
        <StudioPage />
        <ToastContainer />
      </>,
    );

    // STEP 5까지 이동
    fireEvent.click(screen.getByText('다음: 학습 방법 선택 →'));
    fireEvent.click(screen.getByText('다음: 데이터셋 로드 →'));
    fireEvent.click(screen.getByText('다음: 하이퍼파라미터 설정 →'));
    fireEvent.click(screen.getByText('다음: 모니터링 & 학습 시작 →'));

    await waitFor(() => expect(screen.getByText('🚀 파인튜닝 시작 (Start Training)')).toBeEnabled());
    fireEvent.click(screen.getByText('🚀 파인튜닝 시작 (Start Training)'));

    // 실제 잡 폴링 결과가 반영된다 — 시뮬레이션과 달리 loss/progress가 백엔드 값
    await waitFor(() => {
      expect(screen.getByText('0.870')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('100%')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(/학습 완료 — 12건/)).toBeInTheDocument();
    });
  });

  it('reports a failed backend job with its error message', async () => {
    mockFetchByUrl({
      '/v1/models': { data: [{ id: 'm' }] },
      '/api/recipes': { ok: true, recipes: [] },
      '/api/training-jobs': { ok: true, job_id: 'train_fail' },
      '/api/training-jobs/train_fail': {
        job_id: 'train_fail',
        status: 'failed',
        recipe: 'chat-sft',
        platform: 'mlx',
        dataset_path: '',
        config_path: '',
        records: 0,
        sufficient: false,
        progress: 5,
        loss: null,
        log_tail: [],
        error: 'mlx-lm 미설치',
        started_at: 0,
        finished_at: 1,
      },
    });
    render(
      <>
        <StudioPage />
        <ToastContainer />
      </>,
    );

    fireEvent.click(screen.getByText('다음: 학습 방법 선택 →'));
    fireEvent.click(screen.getByText('다음: 데이터셋 로드 →'));
    fireEvent.click(screen.getByText('다음: 하이퍼파라미터 설정 →'));
    fireEvent.click(screen.getByText('다음: 모니터링 & 학습 시작 →'));
    await waitFor(() => expect(screen.getByText('🚀 파인튜닝 시작 (Start Training)')).toBeEnabled());
    fireEvent.click(screen.getByText('🚀 파인튜닝 시작 (Start Training)'));

    await waitFor(() => {
      expect(screen.getByText(/학습 실패: mlx-lm 미설치/)).toBeInTheDocument();
    });
  });

  it('validates learning-rate format and displays inline warnings', () => {
    render(<StudioPage />);

    // Step 1 -> 2 -> 3 -> 4
    fireEvent.click(screen.getByText('다음: 학습 방법 선택 →'));
    fireEvent.click(screen.getByText('다음: 데이터셋 로드 →'));
    fireEvent.click(screen.getByText('다음: 하이퍼파라미터 설정 →'));

    const lrInput = screen.getByLabelText('Learning Rate');

    // Invalid format
    fireEvent.change(lrInput, { target: { value: 'invalid_lr' } });
    expect(screen.getByText(/올바른 학습률 형식/)).toBeInTheDocument();

    // Value <= 0
    fireEvent.change(lrInput, { target: { value: '0' } });
    expect(screen.getByText(/학습률은 0보다 커야 합니다/)).toBeInTheDocument();

    // Unusually high (> 0.01) warning
    fireEvent.change(lrInput, { target: { value: '0.05' } });
    expect(screen.getByText(/학습률이 너무 높습니다/)).toBeInTheDocument();

    // Valid scientific notation
    fireEvent.change(lrInput, { target: { value: '2e-4' } });
    expect(screen.queryByText(/올바른 학습률 형식/)).not.toBeInTheDocument();
    expect(screen.queryByText(/학습률이 너무 높습니다/)).not.toBeInTheDocument();
  });

  it('provides a power-of-two batch size hint with inline feedback', () => {
    render(<StudioPage />);

    // Step 1 -> 2 -> 3 -> 4
    fireEvent.click(screen.getByText('다음: 학습 방법 선택 →'));
    fireEvent.click(screen.getByText('다음: 데이터셋 로드 →'));
    fireEvent.click(screen.getByText('다음: 하이퍼파라미터 설정 →'));

    const batchInput = screen.getByLabelText('Batch Size (per device)');

    // Non-power-of-two (3) -> should render hint
    fireEvent.change(batchInput, { target: { value: '3' } });
    expect(screen.getByText(/2의 거듭제곱.*권장합니다/)).toBeInTheDocument();

    // Invalid batch size (0) -> should render error
    fireEvent.change(batchInput, { target: { value: '0' } });
    expect(screen.getByText(/배치 크기는 1 이상의 정수여야 합니다/)).toBeInTheDocument();

    // Valid power-of-two (8) -> no warning/hint
    fireEvent.change(batchInput, { target: { value: '8' } });
    expect(screen.queryByText(/2의 거듭제곱.*권장합니다/)).not.toBeInTheDocument();
  });

  it('pure helper tests for validateLearningRate and validateBatchSize', () => {
    expect(validateLearningRate('2e-4')).toBeNull();
    expect(validateLearningRate('0.0002')).toBeNull();
    expect(validateLearningRate('5e-5')).toBeNull();
    expect(validateLearningRate('abc')?.type).toBe('error');
    expect(validateLearningRate('')?.type).toBe('error');
    expect(validateLearningRate('-1e-4')?.type).toBe('error');
    expect(validateLearningRate('0.05')?.type).toBe('warning');
    expect(validateLearningRate('1e-9')?.type).toBe('warning');

    expect(validateBatchSize(1)).toBeNull();
    expect(validateBatchSize(2)).toBeNull();
    expect(validateBatchSize(4)).toBeNull();
    expect(validateBatchSize(8)).toBeNull();
    expect(validateBatchSize(16)).toBeNull();
    expect(validateBatchSize(32)).toBeNull();
    expect(validateBatchSize(3)?.type).toBe('hint');
    expect(validateBatchSize(5)?.type).toBe('hint');
    expect(validateBatchSize(6)?.type).toBe('hint');
    expect(validateBatchSize(0)?.type).toBe('error');
    expect(validateBatchSize(-2)?.type).toBe('error');
  });
});
