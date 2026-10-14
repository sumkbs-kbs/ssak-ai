from pathlib import Path


class UnsafeProjectMemoryPathError(ValueError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Project memory path escapes project root: {path}")


def _project_subdir(project_root: str | Path, *parts: str, create: bool = True) -> Path:
    root = Path(project_root).resolve()
    target = (root.joinpath(*parts)).resolve()
    if not target.is_relative_to(root):
        raise UnsafeProjectMemoryPathError(target)
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def project_memory_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "memory")


def project_sessions_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "sessions")


def project_vault_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "vault_data")


def project_rag_vector_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "rag_vectors")


def project_wiki_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "wiki")


def project_gbrain_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "gbrain")


def project_search_cache_dir(project_root: str | Path) -> Path:
    return _project_subdir(project_root, ".antigravity", "search_cache")


__all__ = [
    "UnsafeProjectMemoryPathError",
    "project_gbrain_dir",
    "project_memory_dir",
    "project_rag_vector_dir",
    "project_search_cache_dir",
    "project_sessions_dir",
    "project_vault_dir",
    "project_wiki_dir",
]
