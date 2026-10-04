import { useState } from 'react';
import AllSkillsTab from './skills/AllSkillsTab';
import MarketplaceTab from './skills/MarketplaceTab';
import SearchTab from './skills/SearchTab';
import MCPTab from './skills/MCPTab';
import PublishTab from './skills/PublishTab';
import { useSkillsCatalog } from './skills/useSkillsCatalog';
import type { SkillsTab } from './skills/useSkillsCatalog';

const TABS = [
  { id: 'all', label: 'All Skills' },
  { id: 'marketplace', label: 'Marketplace' },
  { id: 'search', label: 'Search npm' },
  { id: 'publish', label: 'Publish' },
  { id: 'mcp', label: 'MCP Servers' },
] as const;

function SkillsPage() {
  const [activeTab, setActiveTab] = useState<SkillsTab>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const catalog = useSkillsCatalog(activeTab);
  const counts = { all: catalog.skills?.length, marketplace: catalog.marketSkills?.length, mcp: catalog.mcpServers?.length };
  const installedNames = (catalog.marketSkills ?? []).map(skill => skill.skill_name || skill.name);
  const handleSearch = (query = searchQuery) => {
    setSearchQuery(query);
    setActiveTab('search');
    void catalog.search(query);
  };
  const refresh = () => {
    if (activeTab === 'search') handleSearch();
    else void catalog.loadTab(activeTab);
  };
  const hasData = activeTab === 'all' ? catalog.skills !== null
    : activeTab === 'marketplace' ? catalog.marketSkills !== null
      : activeTab === 'mcp' ? catalog.mcpServers !== null : activeTab === 'search' ? catalog.searchResults.length > 0 : true;

  return (
    <div className="page-container" style={{ maxWidth: 1100 }} aria-busy={catalog.status.loading}>
      <div className="page-header" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
          <div className="page-header-hero">
            <div className="hero-eyebrow">SKILL MANAGEMENT</div>
            <h2>Skills Browser</h2>
            <p className="page-subtitle">로드된 스킬, 마켓플레이스 설치 현황, npm 검색, MCP 서버를 한눈에 확인합니다.</p>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {catalog.silentLoading && <span role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>확인 중...</span>}
            <button className="glass-btn primary" onClick={refresh} disabled={catalog.status.loading || activeTab === 'publish'}>새로고침</button>
          </div>
        </div>
      </div>
      <div className="skills-tabs">
        {TABS.map(tab => (
          <button key={tab.id} className={`skills-tab ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)} aria-pressed={activeTab === tab.id}>
            {tab.label}
            {tab.id in counts && <span className="skills-count">{tab.id === 'all' ? counts.all ?? '미확인' : tab.id === 'marketplace' ? counts.marketplace ?? '미확인' : counts.mcp ?? '미확인'}</span>}
          </button>
        ))}
      </div>
      {activeTab === 'search' && (
        <form className="skills-search-bar" style={{ marginBottom: 'var(--space-5)' }} onSubmit={event => { event.preventDefault(); handleSearch(); }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <input type="text" className="glass-input" aria-label="npm 스킬 검색" placeholder="npm 스킬 패키지 검색..." value={searchQuery} onChange={event => setSearchQuery(event.target.value)} style={{ flex: 1, minWidth: 0 }} />
            <button type="submit" className="glass-btn primary" disabled={catalog.status.loading || !searchQuery.trim()}>검색</button>
          </div>
        </form>
      )}
      {catalog.status.error && (
        <div className="glass-panel" role="alert" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)', color: 'var(--error-color)' }}>
          <p>{catalog.status.error}</p>
          {hasData && <p style={{ color: 'var(--text-secondary)' }}>이전에 불러온 정보를 표시합니다.</p>}
          <button className="glass-btn" onClick={refresh}>다시 시도</button>
        </div>
      )}
      {activeTab === 'marketplace' && catalog.recommendationStatus.loading && <p role="status">추천 스킬을 검색하는 중...</p>}
      {activeTab === 'marketplace' && catalog.recommendationStatus.error && (
        <div className="glass-panel" role="alert" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)', color: 'var(--error-color)' }}>
          <p>추천 스킬 검색: {catalog.recommendationStatus.error}</p>
          <button className="glass-btn" onClick={refresh}>추천 다시 시도</button>
        </div>
      )}
      {catalog.status.loading ? <div className="skills-loading" role="status">데이터를 불러오는 중...</div> : (!catalog.status.error || hasData) && (
        <>
          {activeTab === 'all' && catalog.skills !== null && <AllSkillsTab skills={catalog.skills} />}
          {activeTab === 'marketplace' && catalog.marketSkills !== null && <MarketplaceTab skills={catalog.marketSkills} recommended={catalog.recommendations} installedNames={installedNames} onRemove={catalog.remove} onInstall={catalog.install} />}
          {activeTab === 'search' && <SearchTab results={catalog.searchResults} installedNames={installedNames} onSearch={handleSearch} onInstall={catalog.install} />}
          {activeTab === 'publish' && <PublishTab />}
          {activeTab === 'mcp' && catalog.mcpServers !== null && <MCPTab servers={catalog.mcpServers} />}
        </>
      )}
    </div>
  );
}

export default SkillsPage;
