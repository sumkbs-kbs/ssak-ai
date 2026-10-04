/**
 * WikiPage — LLM Wiki (Vault Integration)
 * =========================================
 * Orchestrator component — delegates to sub-components in ./wiki/
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useWikiStore } from '../stores/wikiStore';
import { useNavigate, useSearchParams } from 'react-router-dom';
import WikiSidebar from './wiki/WikiSidebar';
import ContentPanel from './wiki/ContentPanel';
import VaultConfigModal from './wiki/VaultConfigModal';
import NewDocModal from './wiki/NewDocModal';

const WikiPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const newDocRequested = searchParams.get('new') === '1';
  const {
    vaultPath, treeData, currentDoc, isEditing, editContent, searchQuery, searchResults,
    setIsEditing, setEditContent, setSearchQuery, searchDocuments,
    loadTree, loadDocument, saveDocument,
  } = useWikiStore();

  const [showVaultModal, setShowVaultModal] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { loadTree(); }, [loadTree]);

  const handleSelect = useCallback((path: string) => loadDocument(path), [loadDocument]);

  const handleEdit = useCallback(() => {
    if (currentDoc) {
      setEditContent(currentDoc.content);
      setIsEditing(true);
    }
  }, [currentDoc, setEditContent, setIsEditing]);

  const handleSave = useCallback(async () => {
    if (currentDoc) {
      await saveDocument(currentDoc.path, editContent);
    }
  }, [currentDoc, editContent, saveDocument]);

  const handleCancel = useCallback(() => {
    setIsEditing(false);
    if (currentDoc) setEditContent(currentDoc.content);
  }, [currentDoc, setEditContent, setIsEditing]);

  const handleChatRef = useCallback(() => {
    if (!currentDoc) return;
    const snippet = currentDoc.content.length > 500
      ? currentDoc.content.substring(0, 500) + '...'
      : currentDoc.content;

    const wikiWindow = window as Window & { __wikiChatRef?: unknown };
    wikiWindow.__wikiChatRef = {
      path: currentDoc.path,
      content: currentDoc.content,
      metadata: currentDoc.metadata,
      refText: `[Wiki: ${currentDoc.path}]\n\n${snippet}`,
    };

    navigate('/chat');
    setTimeout(() => {
      const event = new CustomEvent('agk:wiki-ref', {
        detail: { text: `다음 Wiki 문서를 참고하여 답변해주세요:\n\n---\n📄 ${currentDoc.path}\n${snippet}\n---\n\n질문: ` }
      });
      window.dispatchEvent(event);
    }, 300);
  }, [currentDoc, navigate]);

  const handleSearchChange = useCallback((q: string) => {
    setSearchQuery(q);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => searchDocuments(q), 400);
  }, [setSearchQuery, searchDocuments]);

  return (
    <div className="page-container full-height-page">
      <div className="wiki-layout">
        <WikiSidebar
          vaultPath={vaultPath}
          treeData={treeData}
          searchQuery={searchQuery}
          searchResults={searchResults}
          onSearchChange={handleSearchChange}
          onSelectDoc={handleSelect}
          onOpenVaultModal={() => setShowVaultModal(true)}
          onOpenNewModal={() => setShowNewModal(true)}
        />
        <ContentPanel
          currentDoc={currentDoc}
          isEditing={isEditing}
          editContent={editContent}
          onEdit={handleEdit}
          onSave={handleSave}
          onCancel={handleCancel}
          onChatRef={handleChatRef}
          onEditContentChange={setEditContent}
        />
      </div>
      <VaultConfigModal visible={showVaultModal} onClose={() => setShowVaultModal(false)} />
      <NewDocModal visible={showNewModal || newDocRequested} onClose={() => {
        setShowNewModal(false);
        if (newDocRequested) setSearchParams({}, { replace: true });
      }} />
    </div>
  );
};

export default WikiPage;
