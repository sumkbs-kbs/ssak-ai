import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('chatStore model preference', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it('restores the selection after reload when no conversation has been started', async () => {
    const { useChatStore } = await import('../chatStore');
    useChatStore.getState().setSelectedModel('qwen3.8:latest');
    vi.resetModules();
    const { useChatStore: reloaded } = await import('../chatStore');

    reloaded.getState().loadFromStorage();

    expect(reloaded.getState().selectedModel).toBe('qwen3.8:latest');
  });

  it('restores the latest selection when an earlier model was selected', async () => {
    const { useChatStore } = await import('../chatStore');
    useChatStore.getState().setSelectedModel('mlx-community/Qwen3.8-125B-A10B-4bit');
    useChatStore.getState().setSelectedModel('qwen3.8:latest');
    vi.resetModules();
    const { useChatStore: reloaded } = await import('../chatStore');

    reloaded.getState().loadFromStorage();

    expect(reloaded.getState().selectedModel).toBe('qwen3.8:latest');
  });

  it('keeps the selection after reload when the active project changes', async () => {
    const { useChatStore } = await import('../chatStore');
    const { useProjectStore } = await import('../projectStore');
    useProjectStore.getState().applyActiveProject({ id: 'project-a', name: 'A', path: '/a' });
    useChatStore.getState().setSelectedModel('qwen3.8:latest');
    useProjectStore.getState().applyActiveProject({ id: 'project-b', name: 'B', path: '/b' });
    useChatStore.getState().clearForProjectSwitch();
    vi.resetModules();
    const { useChatStore: reloaded } = await import('../chatStore');

    reloaded.getState().loadFromStorage();

    expect(reloaded.getState().selectedModel).toBe('qwen3.8:latest');
  });

  it('uses the default when no model preference was saved', async () => {
    const { useChatStore } = await import('../chatStore');

    useChatStore.getState().loadFromStorage();

    expect(useChatStore.getState().selectedModel).toBe('default');
  });

  it('restores the preference alongside the authoritative server snapshot', async () => {
    const { useChatStore } = await import('../chatStore');
    useChatStore.getState().setSelectedModel('qwen3.8:latest');
    useChatStore.getState().createNewSession();
    useChatStore.getState().applyServerSnapshot({
      conversation_id: 'server-conversation',
      revision: 9,
      messages: [{ role: 'assistant', content: 'server answer', id: 'server-message' }],
    });
    vi.resetModules();
    const { useChatStore: reloaded } = await import('../chatStore');

    reloaded.getState().loadFromStorage();

    expect(reloaded.getState().selectedModel).toBe('qwen3.8:latest');
    expect(reloaded.getState().activeSessionId).toBe('server-conversation');
    expect(reloaded.getState().conversationRevision).toBe(9);
    expect(reloaded.getState().messages).toEqual([
      { role: 'assistant', content: 'server answer', id: 'server-message' },
    ]);
  });
});
