import { useCallback, useEffect, useRef, useState } from 'react';
import { useUiStore } from '../../stores/uiStore';
import type { MCPServer, MarketplaceSkill, SearchResult, Skill } from './types';
import { installSkill, loadInstalledSkills, loadMcpSkills, loadSkills, removeSkill, searchSkills, skillsErrorMessage } from './skillsApi';

export type SkillsTab = 'all' | 'marketplace' | 'search' | 'mcp' | 'publish';
type TabStatus = Readonly<{ loading: boolean; error: string | null }>;
const initialStatus: Record<SkillsTab, TabStatus> = {
  all: { loading: true, error: null }, marketplace: { loading: false, error: null },
  search: { loading: false, error: null }, mcp: { loading: false, error: null },
  publish: { loading: false, error: null },
};

export function useSkillsCatalog(activeTab: SkillsTab) {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [marketSkills, setMarketSkills] = useState<MarketplaceSkill[] | null>(null);
  const [mcpServers, setMcpServers] = useState<MCPServer[] | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [recommendations, setRecommendations] = useState<SearchResult[]>([]);
  const [recommendationStatus, setRecommendationStatus] = useState<TabStatus>({ loading: false, error: null });
  const [status, setStatus] = useState(initialStatus);
  const [silentLoading, setSilentLoading] = useState(false);
  const countRef = useRef<number | null>(null);
  const searchRevision = useRef(0);
  const loadRevision = useRef({ all: 0, marketplace: 0, mcp: 0 });
  const updateStatus = useCallback((tab: SkillsTab, next: TabStatus) => {
    setStatus(previous => ({ ...previous, [tab]: next }));
  }, []);

  const loadTab = useCallback(async (tab: SkillsTab, silent = false) => {
    if (tab === 'search' || tab === 'publish') return;
    const revision = ++loadRevision.current[tab];
    if (tab === 'marketplace') setRecommendationStatus({ loading: false, error: null });
    if (silent) setSilentLoading(true);
    else {
      if (tab === 'all') setSilentLoading(false);
      updateStatus(tab, { loading: true, error: null });
    }
    let recommend = false;
    try {
      switch (tab) {
        case 'all': {
          const data = await loadSkills();
          if (revision !== loadRevision.current[tab]) return;
          if (silent && countRef.current !== null && data.length !== countRef.current) {
            useUiStore.getState().addToast(`새 스킬 감지: ${data.length}개`, 'info');
          }
          countRef.current = data.length;
          setSkills(data);
          break;
        }
        case 'marketplace': {
          const data = await loadInstalledSkills();
          if (revision !== loadRevision.current[tab]) return;
          setMarketSkills(data);
          recommend = data.length === 0;
          if (!recommend) {
            setRecommendations([]);
            setRecommendationStatus({ loading: false, error: null });
          }
          break;
        }
        case 'mcp': {
          const data = await loadMcpSkills();
          if (revision !== loadRevision.current[tab]) return;
          setMcpServers(data);
          break;
        }
        default: tab satisfies never;
      }
      updateStatus(tab, { loading: false, error: null });
      if (recommend) {
        setRecommendationStatus({ loading: true, error: null });
        try {
          const results = await searchSkills('skill', 10);
          if (revision !== loadRevision.current[tab]) return;
          setRecommendations(results);
          setRecommendationStatus({ loading: false, error: null });
        } catch (error) {
          if (revision === loadRevision.current[tab]) setRecommendationStatus({ loading: false, error: skillsErrorMessage(error) });
        }
      }
    } catch (error) {
      if (revision === loadRevision.current[tab]) updateStatus(tab, { loading: false, error: skillsErrorMessage(error) });
    } finally {
      if (silent && revision === loadRevision.current[tab]) setSilentLoading(false);
    }
  }, [updateStatus]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadTab(activeTab); }, 0);
    return () => window.clearTimeout(timer);
  }, [activeTab, loadTab]);

  useEffect(() => {
    if (activeTab !== 'all') return;
    const interval = window.setInterval(() => { void loadTab('all', true); }, 20000);
    return () => window.clearInterval(interval);
  }, [activeTab, loadTab]);

  const search = useCallback(async (query: string) => {
    if (!query.trim()) return;
    const revision = ++searchRevision.current;
    updateStatus('search', { loading: true, error: null });
    try {
      const results = await searchSkills(query);
      if (revision !== searchRevision.current) return;
      setSearchResults(results);
      updateStatus('search', { loading: false, error: null });
    } catch (error) {
      if (revision === searchRevision.current) updateStatus('search', { loading: false, error: skillsErrorMessage(error) });
    }
  }, [updateStatus]);

  const install = useCallback(async (name: string) => {
    try {
      await installSkill(name);
      useUiStore.getState().addToast(`${name} installed`, 'success');
      void loadTab('marketplace');
    } catch (error) {
      updateStatus(activeTab, { loading: false, error: skillsErrorMessage(error) });
    }
  }, [activeTab, loadTab, updateStatus]);

  const remove = useCallback(async (name: string) => {
    if (!window.confirm(`"${name}" 스킬을 제거하시겠습니까?`)) return;
    try {
      await removeSkill(name);
      useUiStore.getState().addToast(`${name} removed`, 'success');
      void loadTab('marketplace');
    } catch (error) {
      updateStatus('marketplace', { loading: false, error: skillsErrorMessage(error) });
    }
  }, [loadTab, updateStatus]);

  return { skills, marketSkills, mcpServers, searchResults, recommendations, recommendationStatus, status: status[activeTab], silentLoading, loadTab, search, install, remove };
}
