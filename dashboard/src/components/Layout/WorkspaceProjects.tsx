import { useId, useState } from 'react';
import type { ProjectRecord } from '../../api/clientSchema';
import { AppIcon } from '../UI/AppIcon';

interface WorkspaceProjectsProps {
  readonly projects: readonly ProjectRecord[];
  readonly activeProjectId: string | null;
  readonly branch: string;
  readonly changedFiles: number;
  readonly sessionCount: number;
  readonly onOpen: () => void;
  readonly onSelect: (project: ProjectRecord) => void;
  readonly onRemove: (project: ProjectRecord) => void;
}

export function WorkspaceProjects({ projects, activeProjectId, branch, changedFiles, sessionCount, onOpen, onSelect, onRemove }: WorkspaceProjectsProps) {
  const sectionId = useId();
  const [expanded, setExpanded] = useState<Readonly<Record<string, boolean>>>({});
  return (
    <section className="workspace-projects" aria-labelledby={`${sectionId}-heading`}>
      <div className="workspace-section-heading">
        <h2 id={`${sectionId}-heading`}>프로젝트</h2>
        <button type="button" className="workspace-icon-button" title="프로젝트 폴더 열기" aria-label="새 프로젝트 추가" onClick={onOpen}><AppIcon name="plus" size={16} /></button>
      </div>
      {projects.length === 0 ? (
        <button type="button" className="workspace-nav-link workspace-empty-project workspace-sidebar-empty" onClick={onOpen}><AppIcon name="folder" /><span>프로젝트 열기</span></button>
      ) : (
        <ul className="workspace-project-list">
          {projects.map((project, index) => {
            const selected = activeProjectId ? project.id === activeProjectId : project.is_active;
            const open = expanded[project.id] ?? false;
            const detailId = `${sectionId}-${index}`;
            return (
              <li key={project.id} className="workspace-project" data-selected={selected}>
                <div className="workspace-project-row">
                  <button type="button" className="workspace-icon-button workspace-project-expand" aria-label={`${project.name} 프로젝트 ${open ? '접기' : '펼치기'}`} aria-expanded={open} aria-controls={detailId} onClick={() => setExpanded(current => ({ ...current, [project.id]: !open }))}><AppIcon name={open ? 'chevronDown' : 'chevronRight'} size={16} /></button>
                  <button type="button" className="workspace-project-select" aria-pressed={selected} title={`${project.name} (${project.path})`} onClick={() => onSelect(project)}><AppIcon name={selected ? 'folderOpen' : 'folder'} size={18} /><span>{project.name}</span></button>
                  {projects.length > 1 && <button type="button" className="workspace-icon-button workspace-project-remove" aria-label={`${project.name} 프로젝트 제거`} title="프로젝트 목록에서 제외" onClick={() => onRemove(project)}><AppIcon name="close" size={16} /></button>}
                </div>
                <div id={detailId} className="workspace-project-detail" hidden={!open}>
                  <p className="workspace-project-path" title={project.path}>{project.path}</p>
                  {selected && <div className="workspace-project-context"><span>대화 {sessionCount}개</span>{branch && <span className="workspace-project-branch"><AppIcon name="git" size={14} />{branch}{changedFiles > 0 && <span> · 변경 {changedFiles}</span>}</span>}</div>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
