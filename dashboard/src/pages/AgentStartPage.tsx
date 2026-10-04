/**
 * AgentStartPage — Unsloth Start & Agent Bridge
 * ===============================================
 * Inspired by `unsloth start`:
 * Instant 1-click bridge connecting Claude Code, OpenAI Codex, Hermes Agent,
 * OpenClaw, and MCP clients to local Ssak-Ai inference.
 */

import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useUiStore } from '../stores/uiStore';

interface AgentIntegration {
  id: string;
  name: string;
  command: string;
  tag: string;
  icon: string;
  description: string;
  protocol: 'anthropic' | 'openai';
  envVars: string[];
}

const quoteShellArgument = (value: string): string =>
  /^[A-Za-z0-9_@%+=:,./-]+$/.test(value) ? value : `'${value.replace(/'/g, "'\\''")}'`;

const resolveBridgeApiBase = (): string => {
  const configured: unknown = import.meta.env.VITE_API_BASE;
  const base = typeof configured === 'string' && configured.trim() ? configured.trim() : globalThis.location.origin;
  const url = new URL(base, globalThis.location.origin);
  url.pathname = url.pathname.replace(/\/+$/, '').replace(/\/v1$/, '') || '/';
  url.search = '';
  url.hash = '';
  return url.href.replace(/\/+$/, '');
};

const INTEGRATIONS: AgentIntegration[] = [
  {
    id: 'claude-code',
    name: 'Claude Code CLI',
    command: 'agk start claude',
    tag: '가장 인기',
    icon: '⚡',
    description: 'Anthropic Claude Code CLI를 로컬 Ssak-Ai 프록시에 연결하여 토큰 비용 없이 오프라인 코딩 에이전트를 구동합니다.',
    protocol: 'anthropic',
    envVars: [
      'unset ANTHROPIC_API_KEY',
      'export ANTHROPIC_AUTH_TOKEN="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"',
    ],
  },
  {
    id: 'codex',
    name: 'OpenAI Codex CLI',
    command: 'agk start codex',
    tag: '공식 지원',
    icon: '💻',
    description: 'OpenAI 호환 규격의 코덱스 터미널 도구를 로컬 루프백 엔드포인트에 즉시 바인딩합니다.',
    protocol: 'openai',
    envVars: [
      'export OPENAI_API_KEY="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"',
    ],
  },
  {
    id: 'hermes',
    name: 'Hermes Agent',
    command: 'agk start hermes',
    tag: '자율 에이전트',
    icon: '🪽',
    description: '자가 치유(Self-healing) 도구 호출 및 복합 리서치 역량을 갖춘 Hermes 에이전트를 기동합니다.',
    protocol: 'openai',
    envVars: [
      'export OPENAI_API_KEY="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"',
    ],
  },
  {
    id: 'openclaw',
    name: 'OpenClaw / OpenCode',
    command: 'agk start openclaw',
    tag: '오픈소스',
    icon: '🦀',
    description: '오픈소스 에이전트 프레임워크와 직접 통신하며 컨텍스트 롤링 및 RAG를 공급합니다.',
    protocol: 'anthropic',
    envVars: [
      'unset ANTHROPIC_API_KEY',
      'export ANTHROPIC_AUTH_TOKEN="${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"',
    ],
  },
];

export const AgentStartPage: React.FC = () => {
  const { selectedModel } = useChatStore();
  const { addToast } = useUiStore();
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const apiBase = resolveBridgeApiBase();
  const openaiBase = `${apiBase}/v1`;

  useEffect(() => () => {
    if (copyTimer.current !== null) clearTimeout(copyTimer.current);
  }, []);

  const handleCopy = async (text: string, id: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      addToast('명령어를 클립보드에 복사했습니다.', 'info');
      if (copyTimer.current !== null) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopiedId(null), 2000);
    } catch (error) {
      if (!(error instanceof Error || error instanceof DOMException)) throw error;
      addToast(`복사하지 못했습니다: ${error.message}`, 'error');
    }
  };

  return (
    <div className="unsloth-start-container">
      {/* Header */}
      <header className="unsloth-start-header">
        <div className="start-title-box">
          <div className="start-icon">🚀</div>
          <div>
            <div className="flex-align-center gap-8">
              <h1 className="start-title">Unsloth Start</h1>
              <span className="start-badge">LOCAL AGENT BRIDGE</span>
            </div>
            <p className="start-sub">
              선택한 로컬 모델에 연결하는 CLI 설정 안내를 확인합니다. agk start는 연결 계획을 출력하며, 에이전트 실행은 터미널에서 진행합니다.
            </p>
          </div>
        </div>

        {/* Global Endpoint Info Card */}
        <div className="endpoint-hud-card">
          <div className="endpoint-row">
            <span className="ep-lbl">Local Endpoint</span>
            <code className="ep-code">{openaiBase}</code>
          </div>
          <div className="endpoint-row">
            <span className="ep-lbl">Active Target Model</span>
            <span className="ep-model">{selectedModel.split('/').pop()}</span>
          </div>
          <div className="endpoint-row">
            <span className="ep-lbl">Cloudflare Tunnel</span>
            <span className="ep-tunnel-status" role="status" data-state="unverified" style={{ color: 'var(--text-secondary)' }}>상태 미확인</span>
          </div>
        </div>
      </header>

      <p className="start-sub">
        PIN이 설정된 서버는 /api/auth/login에서 발급한 토큰을 터미널의 SSAK_ACCESS_TOKEN 변수로 지정하세요.
        아래 설정과 CLI 안내는 이 변수를 참조하며, 로그인 토큰을 출력하지 않습니다.
        Codex는 agk start codex가 안내하는 provider 설정도 필요합니다.
      </p>

      {/* Integration Cards Grid */}
      <div className="integrations-grid">
        {INTEGRATIONS.map(item => (
          <div key={item.id} className="integration-card">
            <div className="card-top-row">
              <div className="icon-title-cluster">
                <span className="item-icon">{item.icon}</span>
                <div>
                  <h2 className="item-name">{item.name}</h2>
                  <span className="item-tag">{item.tag}</span>
                </div>
              </div>
            </div>

            <p className="item-description">{item.description}</p>

            {/* Quick Command Snippet */}
            <div className="cmd-box">
              <div className="cmd-header">
                <span>Start Command</span>
                <button
                  type="button"
                  className="copy-btn"
                  onClick={() => handleCopy(`${item.command} --model ${quoteShellArgument(selectedModel)} --api-base ${quoteShellArgument(apiBase)}`, item.id)}
                >
                  {copiedId === item.id ? '✓ 복사됨' : '📋 복사'}
                </button>
              </div>
              <pre className="cmd-text">
                <code>{item.command} --model {quoteShellArgument(selectedModel)} --api-base {quoteShellArgument(apiBase)}</code>
              </pre>
            </div>

            {/* Env Vars Snippet */}
            <div className="env-box">
              <span className="env-title">환경 변수 (Manual Setup):</span>
              {[
                `export ${item.protocol === 'anthropic' ? 'ANTHROPIC' : 'OPENAI'}_BASE_URL=${quoteShellArgument(item.protocol === 'anthropic' ? apiBase : openaiBase)}`,
                ...item.envVars,
              ].map((env, i) => (
                <div key={i} className="env-line">
                  <code>{env}</code>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Network & Cloudflare Tunnel Banner */}
      <div className="tunnel-banner-card">
        <div className="tunnel-info">
          <h3>🌐 원격 &amp; 모바일 접속 (Serve Anywhere via Cloudflare / LAN)</h3>
          <p>
            터널의 실행 여부와 외부 접속은 이 화면에서 확인할 수 없습니다. 복사 버튼은 터미널에서 검토할 명령어만 복사합니다.
          </p>
        </div>
        <div className="tunnel-actions">
          <button
            type="button"
            className="unsloth-btn-primary"
            onClick={() => handleCopy(`cloudflared tunnel run --url ${quoteShellArgument(apiBase)} ` + '"${SSAK_TUNNEL_NAME:?set an existing tunnel name}"', 'tunnel')}
          >
            터널 커맨드 복사
          </button>
        </div>
      </div>
    </div>
  );
};

export default AgentStartPage;
