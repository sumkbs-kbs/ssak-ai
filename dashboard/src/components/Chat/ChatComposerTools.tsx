import type { McpServerItem } from '../../api/clientSchema';
import { AppIcon } from '../UI/AppIcon';

type ChatComposerToolsProps = {
  readonly actionMenuOpen: boolean;
  readonly accessDropdownOpen: boolean;
  readonly mcpMenuOpen: boolean;
  readonly accessMode: 'full_access' | 'restricted';
  readonly webSearch: boolean;
  readonly codeMode: boolean;
  readonly mcpServers: readonly McpServerItem[];
  readonly mcpAllowlist: readonly string[];
  readonly onToggleActionMenu: () => void;
  readonly onAttach: () => void;
  readonly onToggleAccessMenu: () => void;
  readonly onAccessChoice: (mode: 'full_access' | 'restricted') => void;
  readonly onToggleSearch: () => void;
  readonly onToggleCode: () => void;
  readonly onToggleMcpMenu: () => void;
  readonly onToggleMcpServer: (name: string) => void;
};

export function ChatComposerTools({
  actionMenuOpen, accessDropdownOpen, mcpMenuOpen, accessMode,
  webSearch, codeMode, mcpServers, mcpAllowlist, onToggleActionMenu,
  onAttach, onToggleAccessMenu, onAccessChoice, onToggleSearch,
  onToggleCode, onToggleMcpMenu, onToggleMcpServer,
}: ChatComposerToolsProps) {
  return (
    <div className="agk-chip-group agk-composer-tools">
      <div className="codex-action-plus-wrap">
        <button
          type="button"
          className={`plus-action-circle-btn ${actionMenuOpen ? 'open' : ''}`}
          onClick={onToggleActionMenu}
          title="옵션 및 파일 첨부"
          aria-label="옵션 및 파일 첨부"
          aria-expanded={actionMenuOpen}
          aria-controls="chat-attachment-options"
        >
          <AppIcon name="plus" />
        </button>
        {actionMenuOpen && (
          <div id="chat-attachment-options" className="plus-popover-dropdown">
            <button type="button" className="popover-row" onClick={onAttach}>
              <AppIcon name="paperclip" size={16} />
              <span>파일 및 사진 첨부</span>
            </button>
          </div>
        )}
      </div>
      <div className="codex-access-pill-wrap">
        <button
          type="button"
          className={`access-chip ${accessMode === 'full_access' ? 'amber' : 'safe'}`}
          onClick={onToggleAccessMenu}
          aria-expanded={accessDropdownOpen}
          aria-controls="chat-access-options"
        >
          <AppIcon name="shield" size={16} />
          <span className="chip-label">{accessMode === 'full_access' ? '전체 액세스' : '읽기 전용'}</span>
          <AppIcon name="chevronDown" size={12} />
        </button>
        {accessDropdownOpen && (
          <div id="chat-access-options" className="access-dropdown-menu">
            <button
              type="button"
              className={`access-opt ${accessMode === 'full_access' ? 'selected' : ''}`}
              aria-pressed={accessMode === 'full_access'}
              onClick={() => onAccessChoice('full_access')}
            >
              <AppIcon name="shield" size={16} /> 전체 액세스
            </button>
            <button
              type="button"
              className={`access-opt ${accessMode === 'restricted' ? 'selected' : ''}`}
              aria-pressed={accessMode === 'restricted'}
              onClick={() => onAccessChoice('restricted')}
            >
              <AppIcon name="shield" size={16} /> 읽기 전용
            </button>
          </div>
        )}
      </div>
      <button
        type="button"
        className={`tool-chip ${webSearch ? 'active' : ''}`}
        onClick={onToggleSearch}
        aria-pressed={webSearch}
        title="웹 검색 도구 사용"
      >
        <AppIcon name="globe" size={16} /><span className="chip-label">검색</span>
      </button>
      <button
        type="button"
        className={`tool-chip ${codeMode ? 'active' : ''}`}
        onClick={onToggleCode}
        aria-pressed={codeMode}
        title="코드 인터프리터 사용"
      >
        <AppIcon name="code" size={16} /><span className="chip-label">코드</span>
      </button>
      <div className="agk-mcp-chip-wrap">
        <button
          type="button"
          className={`tool-chip ${mcpAllowlist.length > 0 ? 'active' : ''}`}
          onClick={onToggleMcpMenu}
          aria-expanded={mcpMenuOpen}
          aria-controls="chat-mcp-options"
          title="MCP 서버 선택"
        >
          <AppIcon name="puzzle" size={16} /><span className="chip-label">MCP</span>
          <AppIcon name="chevronDown" size={12} />
        </button>
        {mcpMenuOpen && (
          <div id="chat-mcp-options" className="mcp-dropdown-menu">
            {mcpServers.length === 0 ? (
              <div className="mcp-opt mcp-empty-row">
                <span>구성된 MCP 서버가 없습니다</span><span className="mcp-opt-status">.mcp.json</span>
              </div>
            ) : mcpServers.map((server) => (
              <button
                key={server.name}
                type="button"
                className={`mcp-opt ${mcpAllowlist.includes(server.name) ? 'selected' : ''}`}
                aria-pressed={mcpAllowlist.includes(server.name)}
                onClick={() => onToggleMcpServer(server.name)}
              >
                <span>{mcpAllowlist.includes(server.name) && <AppIcon name="check" size={14} />} {server.name}</span>
                <span className="mcp-opt-status">{server.transport}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
