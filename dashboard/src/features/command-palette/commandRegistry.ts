import { z } from 'zod';

import { apiRequestPath, isAuthRequiredError } from '../../api/client';
import { getProjectIdentitySnapshot, isIdentityCurrent } from '../../api/projectIdentity';
import { useChatStore } from '../../stores/chatStore';
import { useUiStore } from '../../stores/uiStore';
import { useWikiStore } from '../../stores/wikiStore';
import { readStoredAccessToken } from '../../utils/accessPinCredential';

export type CommandIconName =
  | 'automation'
  | 'chat'
  | 'note'
  | 'plugin'
  | 'search'
  | 'settings'
  | 'sync'
  | 'test'
  | 'warning';

export type PaletteCommand = Readonly<{
  id: string;
  title: string;
  subtitle: string | null;
  icon: CommandIconName;
  keywords: readonly string[];
  disabled: boolean;
  execute: () => void | Promise<void>;
}>;

const NoteSearchResponseSchema = z.object({
  semantic_results: z.array(z.object({
    id: z.string(),
    text: z.string(),
    metadata: z.object({ source: z.string().optional() }).optional(),
  })).default([]),
  keyword_results: z.array(z.string()).default([]),
});

export class CommandSearchError extends Error {
  readonly cause: Error;

  constructor(cause: Error) {
    super('Command palette note search failed.');
    this.name = 'CommandSearchError';
    this.cause = cause;
  }
}

function dispatchCommandEvent(name: string, detail?: unknown): void {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

let latestWikiSelection = 0;

async function openWikiNote(path: string): Promise<void> {
  const selection = ++latestWikiSelection;
  const { switchEpoch } = getProjectIdentitySnapshot();
  const credential = readStoredAccessToken();
  const ownsSelection = () => selection === latestWikiSelection
    && isIdentityCurrent(switchEpoch) && credential === readStoredAccessToken();
  try {
    const response = z.object({
      content: z.string(), metadata: z.record(z.string(), z.unknown()).default({}),
    }).parse(await apiRequestPath(`/api/vault/read?${new URLSearchParams({ path })}`, { skipPinModal: true }));
    if (!ownsSelection()) return;
    useWikiStore.setState({
      currentDoc: { path, content: response.content, metadata: response.metadata },
      editContent: response.content,
      isEditing: false,
    });
    dispatchCommandEvent('agk:navigate', '/wiki');
  } catch (error) {
    if (!ownsSelection()) return;
    if (isAuthRequiredError(error)) dispatchCommandEvent('agk:pin-required');
    throw error;
  }
}

async function syncVault(): Promise<void> {
  const addToast = useUiStore.getState().addToast;
  try {
    const payload = z.object({ ok: z.boolean(), commit: z.string().optional() }).parse(
      await apiRequestPath('/api/vault/sync', { method: 'POST' }),
    );
    if (payload.ok) {
      addToast(`Vault 동기화 완료 (commit: ${payload.commit?.slice(0, 7) ?? 'N/A'})`, 'success');
      return;
    }
    addToast('Vault 동기화 실패', 'error');
  } catch (error) {
    if (error instanceof Error) {
      addToast(`Vault 동기화 오류: ${error.message}`, 'error');
      return;
    }
    throw error;
  }
}

export const BUILTIN_COMMANDS = [
  {
    id: 'search', title: 'Search Notes', subtitle: 'Knowledge', icon: 'search',
    keywords: ['notes', '검색'], disabled: false,
    execute: () => dispatchCommandEvent('agk:navigate', '/wiki'),
  },
  {
    id: 'new_note', title: 'Create New Note', subtitle: 'Knowledge', icon: 'note',
    keywords: ['wiki', 'note'], disabled: false,
    execute: () => dispatchCommandEvent('agk:navigate', '/wiki?new=1'),
  },
  {
    id: 'chat', title: 'Open AI Chat', subtitle: 'Workspace', icon: 'chat',
    keywords: ['assistant', '대화'], disabled: false,
    execute: () => dispatchCommandEvent('agk:navigate', '/chat'),
  },
  {
    id: 'conversation_fork', title: '현재 대화 분기', subtitle: '원본을 보존하고 새 대화로 이어가기', icon: 'chat',
    keywords: ['fork', 'branch', '분기', '원본 보존'], disabled: false,
    execute: () => {
      if (window.location.pathname !== '/chat') {
        dispatchCommandEvent('agk:navigate', '/chat');
        useUiStore.getState().addToast('대화 내용을 확인한 뒤 상단의 대화 분기 버튼을 눌러 주세요.', 'info');
        return;
      }
      dispatchCommandEvent('agk:conversation-fork');
    },
  },
  {
    id: 'goal', title: 'Autonomous Goal (/goal)', subtitle: 'Agent', icon: 'automation',
    keywords: ['goal', 'agent'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/goal ' }),
  },
  {
    id: 'agentic', title: 'Agentic Upgrade Radar (/agentic)', subtitle: 'Agent', icon: 'automation',
    keywords: ['upgrade', 'radar'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/agentic ' }),
  },
  {
    id: 'mcp', title: 'MCP Upgrade Radar (/mcp)', subtitle: 'Agent', icon: 'plugin',
    keywords: ['tools', 'integration'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/mcp ' }),
  },
  {
    id: 'capabilities', title: 'Autonomous Capabilities (/capabilities)', subtitle: 'Agent', icon: 'automation',
    keywords: ['capability', 'tools'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/capabilities ' }),
  },
  {
    id: 'self', title: 'Self Capability Report (/self)', subtitle: 'Agent', icon: 'automation',
    keywords: ['report', 'self'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/self' }),
  },
  {
    id: 'codex', title: 'Codex Capability Transfer (/codex)', subtitle: 'Agent', icon: 'automation',
    keywords: ['codex', 'transfer'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/codex ' }),
  },
  {
    id: 'benchmark', title: 'Collective Benchmark Report (/benchmark)', subtitle: 'Evaluation', icon: 'test',
    keywords: ['benchmark', 'evaluation'], disabled: false,
    execute: () => dispatchCommandEvent('agk:chat-slash', { text: '/benchmark report' }),
  },
  {
    id: 'job_operations', title: 'Open Job Operations', subtitle: 'Operations', icon: 'automation',
    keywords: ['jobs', 'schedule', 'retry', 'health', '작업'], disabled: false,
    execute: () => dispatchCommandEvent('agk:navigate', '/plugins/job-operations'),
  },
  {
    id: 'settings', title: 'Preferences', subtitle: 'Workspace', icon: 'settings',
    keywords: ['settings', '환경 설정'], disabled: false,
    execute: () => dispatchCommandEvent('agk:navigate', '/settings'),
  },
  {
    id: 'sync', title: 'Sync Vault (Git)', subtitle: 'Repository', icon: 'sync',
    keywords: ['git', 'vault'], disabled: false, execute: syncVault,
  },
  {
    id: 'selftest', title: 'Self-Test', subtitle: '대시보드 실행 화면 미지원', icon: 'test',
    keywords: ['diagnostics', 'test'], disabled: true,
    execute: () => undefined,
  },
  {
    id: 'tdd_loop', title: 'Open Test-Driven Chat', subtitle: 'TDD 모드에서 입력 후 직접 전송', icon: 'test',
    keywords: ['tdd', 'test'], disabled: false,
    execute: () => {
      useChatStore.getState().setAdaptiveMode(false);
      useChatStore.getState().setTddMode(true);
      dispatchCommandEvent('agk:navigate', '/chat');
    },
  },
] as const satisfies readonly PaletteCommand[];

export function filterPaletteCommands(
  commands: readonly PaletteCommand[],
  query: string,
): readonly PaletteCommand[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (normalized.length === 0) return commands;
  return commands.filter((command) => [command.id, command.title, ...command.keywords]
    .some((value) => value.toLocaleLowerCase().includes(normalized)));
}

export async function searchNoteCommands(query: string): Promise<readonly PaletteCommand[]> {
  try {
    const response = NoteSearchResponseSchema.parse(
      await apiRequestPath(`/v1/notes/search?${new URLSearchParams({ q: query })}`),
    );
    const semantic = response.semantic_results.map((result) => ({
      id: `note-semantic:${result.id}`,
      title: `${result.text.slice(0, 40)}${result.text.length > 40 ? '…' : ''}`,
      subtitle: 'Semantic match',
      icon: 'note',
      keywords: [result.id],
      disabled: false,
      execute: () => openWikiNote(result.metadata?.source ?? result.id),
    } satisfies PaletteCommand));
    const keyword = response.keyword_results.map((path) => ({
      id: `note-keyword:${path}`,
      title: path,
      subtitle: 'Keyword match',
      icon: 'note',
      keywords: [path],
      disabled: false,
      execute: () => openWikiNote(path),
    } satisfies PaletteCommand));
    return [...semantic, ...keyword];
  } catch (error) {
    if (error instanceof Error) throw new CommandSearchError(error);
    throw error;
  }
}
