import { Fragment } from 'react';
import type { ChatMessage } from '../../stores/chatStore';
import type { ResponseDetail } from '../../utils/responsePresentation';
import { AppIcon } from '../UI/AppIcon';

interface MessageMetadataProps {
  readonly metadata: ChatMessage['agentMeta'];
  readonly details: readonly ResponseDetail[];
  readonly original: string | null;
}

export function MessageMetadata({ metadata, details, original }: MessageMetadataProps) {
  if (!metadata && details.length === 0) return null;
  return (
    <details className="message-details">
      <summary>
        <span>응답 정보</span>
        <AppIcon name="chevronDown" size={14} />
      </summary>
      {metadata && <div className="assistant-agent-meta">
        <span className="badge badge-mode">{metadata.mode || 'adaptive'}</span>
        {metadata.used_web && <span className="badge badge-web" title="Ssak-Search 웹 검색 참조">웹 검색</span>}
        {metadata.used_graphify && <span className="badge badge-graphify" title="Graphify 코드베이스 하이브리드 검색">코드 검색</span>}
        {metadata.passed !== null && metadata.passed !== undefined && (
          <span className={`badge ${metadata.passed ? 'badge-pass' : 'badge-fail'}`}>
            {metadata.passed ? '검증 통과' : '검증 실패'}
          </span>
        )}
        {metadata.steps !== undefined && <span>{metadata.steps}단계</span>}
        {metadata.total_seconds !== undefined && <span>{metadata.total_seconds.toFixed(1)}초</span>}
      </div>}
      {details.length > 0 && (
        <dl className="response-system-meta">
          {details.map(({ label, value }) => <Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>)}
        </dl>
      )}
      {original !== null && (
        <details className="response-original">
          <summary>원문 보기</summary>
          <pre>{original}</pre>
        </details>
      )}
    </details>
  );
}
