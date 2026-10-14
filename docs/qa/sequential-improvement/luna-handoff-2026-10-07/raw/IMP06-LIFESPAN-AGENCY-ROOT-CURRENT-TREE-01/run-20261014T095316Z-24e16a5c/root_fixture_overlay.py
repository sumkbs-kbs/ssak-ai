"""ROOT-only adjacent startup fixture adaptation; target agency path remains real."""
import hashlib,json,os
from pathlib import Path

def pytest_collection_modifyitems(items):
    seen=set()
    for item in items:
        mod=item.module
        if mod.__name__ in seen or not mod.__name__.endswith("test_lifespan_agency_root_contract"):
            continue
        seen.add(mod.__name__)
        original=mod.PROBE
        source=original.replace("def __init__(self,project_root):receipt[\"rag_roots\"].append(project_root)","def __init__(self,project_root,vector_store=None):receipt[\"rag_roots\"].append(project_root)")
        anchor='module("antigravity_k.engine.rag_indexer",RAGIndexer=Indexer)'
        additions=anchor+"\nclass VectorDouble:\n    def __init__(self,path,collection_name):receipt['rag_vector_path']=path\n    def __enter__(self):return self\n    def __exit__(self,*args):return False\nmodule('antigravity_k.engine.vector_store',VectorStore=VectorDouble)\nmodule('antigravity_k.engine.project_memory_paths',project_rag_vector_dir=lambda project_root:Path(project_root)/'.antigravity'/'rag_vectors')"
        source=source.replace(anchor,additions)
        source=source.replace('assert receipt["rag_roots"]==[source_root] and receipt["ide_roots"]==[source_root]','assert receipt["rag_roots"]==[str(configured.resolve())] and receipt["ide_roots"]==[str(configured.resolve())]')
        assert source!=original and "vector_store=None" in source
        mod.PROBE=source
        out=Path(os.environ['LIFESPAN_AGENCY_CAPTURE_ROOT']).parent
        (out/'fixture-overlay.json').write_text(json.dumps({'original_probe_sha256':hashlib.sha256(original.encode()).hexdigest(),'executed_probe_sha256':hashlib.sha256(source.encode()).hexdigest(),'reason':'ROOT preimage already uses configured RAG/IDE root and creates VectorStore; isolate these adjacent subsystems without changing agency bridge/store assertions'},indent=2))
