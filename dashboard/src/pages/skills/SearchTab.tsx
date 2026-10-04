import React from 'react';
import type { SearchResult } from './types';
import SearchResultCard from './SearchResultCard';

interface SearchTabProps {
  results: SearchResult[];
  installedNames: string[];
  onSearch: (query?: string) => void;
  onInstall: (pkgName: string) => void;
}

const EXAMPLE_QUERIES = ['code review', 'testing', 'rag', 'deploy'];

const SearchTab: React.FC<SearchTabProps> = ({
  results,
  installedNames,
  onSearch,
  onInstall,
}) => {
  if (results.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <span style={{ fontSize: 48, opacity: 0.4 }}>🔍</span>
        <h3 style={{ fontSize: 16, color: 'var(--text-secondary)' }}>npm 스킬 검색</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          npm 레지스트리에서 스킬을 검색하세요.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
          {EXAMPLE_QUERIES.map(q => (
            <button
              key={q}
              className="example-chip"
              onClick={() => onSearch(q)}
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        <span className="status-badge active" style={{ fontSize: 12 }}>
          {results.length} results
        </span>
      </div>
      <div className="skills-grid">
        {results.map(s => (
          <SearchResultCard
            key={s.name}
            result={s}
            installed={installedNames.includes(s.skill_name || s.name)}
            onInstall={onInstall}
          />
        ))}
      </div>
    </>
  );
};

export default SearchTab;
