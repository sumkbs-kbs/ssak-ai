import type { LocalModelItem, ModelInfo } from '../../api/client';
import { QuantBadge } from '../shared';
import { AppIcon } from '../UI/AppIcon';

const modelAmountFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

export function formatModelAmount(amount: number): string {
  return modelAmountFormatter.format(amount);
}

type ChatModelSelectorProps = {
  readonly label: string;
  readonly selectedModel: string;
  readonly open: boolean;
  readonly scanning: boolean;
  readonly localModels: readonly LocalModelItem[];
  readonly availableModels: readonly ModelInfo[];
  readonly onToggle: () => void;
  readonly onRefresh: () => void;
  readonly onLocalChoice: (modelId: string) => void;
  readonly onCloudChoice: (modelId: string) => void;
};

export function ChatModelSelector({
  label, selectedModel, open, scanning, localModels, availableModels,
  onToggle, onRefresh, onLocalChoice, onCloudChoice,
}: ChatModelSelectorProps) {
  const groups = [
    { title: '실행 중 모델', models: localModels.filter((model) => model.status === 'running') },
    { title: 'Unsloth 다운로드 모델 (GGUF)', models: localModels.filter((model) => model.status !== 'running' && model.provider === 'unsloth') },
    { title: 'MLX / 로컬 캐시 모델', models: localModels.filter((model) => model.status !== 'running' && model.provider !== 'unsloth') },
  ];
  const cloudModels = availableModels
    .filter((model) => !model.is_local && !localModels.some((local) => local.id === model.id))
    .slice(0, 8);

  return (
    <div className="model-selector-wrap codex-model-selector-wrap">
      <button
        type="button"
        className="model-pill-trigger model-select-trigger"
        onClick={onToggle}
        aria-label="모델 선택"
        aria-expanded={open}
        aria-controls="chat-model-options"
        title={label}
      >
        <span className="model-name-text">{label}</span>
        <AppIcon name="chevronDown" size={14} />
      </button>
      {open && (
        <div id="chat-model-options" className="model-selection-popover" aria-label="사용할 모델">
          <div className="model-dropdown-header-row">
            <span className="popover-sec-title">본 PC 전체 로컬 모델 ({localModels.length}개)</span>
            <button
              type="button"
              className="model-refresh-btn"
              title="본 PC 로컬 모델 다시 검색"
              disabled={scanning}
              onClick={(event) => { event.stopPropagation(); onRefresh(); }}
            >
              <AppIcon name="refresh" size={14} />
              {scanning ? '검색 중…' : '다시 검색'}
            </button>
          </div>
          {localModels.length === 0 ? (
            <div className="model-empty-notice">
              {scanning ? '로컬 모델을 검색하고 있습니다…' : '실행 중이거나 다운로드된 로컬 모델을 찾을 수 없습니다.'}
            </div>
          ) : groups.map((group) => group.models.length > 0 && (
            <div key={group.title} className="model-group-section">
              <div className="model-group-title">{group.title}</div>
              {group.models.map((model) => (
                <button
                  key={model.id}
                  type="button"
                  className={`model-choice-row ${model.id === selectedModel ? 'selected' : ''}`}
                  aria-pressed={model.id === selectedModel}
                  onClick={() => onLocalChoice(model.id)}
                >
                  <span className="model-row-left">
                    <span className="model-row-title-line">
                      <span className={`status-dot ${model.status === 'running' ? 'running' : 'cached'}`} aria-hidden="true" />
                      <span className="model-name-text">{model.name || model.id}</span>
                    </span>
                    <span className="model-chip-badges">
                      <span className={`badge-provider ${model.provider}`}>{model.provider}</span>
                      {model.status === 'running' && model.parameter_count_b > 0 && (
                        <span className="badge-param">{formatModelAmount(model.parameter_count_b)}B</span>
                      )}
                      {model.status !== 'running' && model.disk_size_gb > 0 && (
                        <span className="badge-disk">{formatModelAmount(model.disk_size_gb)} GB</span>
                      )}
                      {model.status !== 'running' && model.quantization && (
                        <QuantBadge quantization={model.quantization} variant="chip" />
                      )}
                      {model.role && <span className="badge-role">{model.role}</span>}
                    </span>
                  </span>
                  {model.id === selectedModel && <span className="tag-recommended">현재 선택</span>}
                </button>
              ))}
            </div>
          ))}
          {cloudModels.length > 0 && (
            <>
              <div className="model-dropdown-divider" />
              <div className="popover-sec-title subhead">외부 / 클라우드 모델</div>
              {cloudModels.map((model) => (
                <button
                  key={model.id}
                  type="button"
                  className={`model-choice-row ${model.id === selectedModel ? 'selected' : ''}`}
                  aria-pressed={model.id === selectedModel}
                  onClick={() => onCloudChoice(model.id)}
                >
                  <span>{model.description || model.id}</span>
                  {model.id === selectedModel && <span className="tag-recommended">현재 선택</span>}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
