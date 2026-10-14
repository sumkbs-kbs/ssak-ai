from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(sys.argv[1]).resolve();sys.path.insert(0,sys.argv[2])
from startup_probe.guard import Guard
guard=Guard(ROOT);guard.install()
try:
    import chromadb
    import networkx as nx
    import numpy as np
    before=json.loads((ROOT/"before.json").read_bytes())
    observations=json.loads((ROOT/"observations.json").read_bytes())
    counts={}
    b_projection=None
    for label in ("a","b"):
        project=Path(observations["project_"+label]["root"])
        graph=nx.read_graphml(project/".antigravity/gbrain/knowledge_graph.graphml")
        client=chromadb.PersistentClient(path=str(project/".antigravity/rag_vectors"))
        collection=client.get_collection(name="project_code",embedding_function=None)
        graph_client=chromadb.PersistentClient(path=str(project/".antigravity/gbrain/chroma"))
        graph_collection=graph_client.get_collection(name="gbrain_nodes",embedding_function=None)
        counts[label]={"graph_nodes":len(graph.nodes),"graph_vectors":graph_collection.count(),"project_vectors":collection.count()}
        if label=="b":
            payload=collection.get(include=["documents","metadatas","embeddings"])
            b_projection={"ids":payload["ids"],"documents":payload["documents"],"metadatas":payload["metadatas"],"embeddings":np.asarray(payload["embeddings"]).tolist()}
    assert counts["a"]=={"graph_nodes":0,"graph_vectors":0,"project_vectors":0}
    assert counts["b"]=={"graph_nodes":2,"graph_vectors":1,"project_vectors":2}
    assert b_projection==before["b_vectors"]
    result={"classification":"PASS_SCOPED_FRESH_PROCESS_REOPEN","counts":counts,"b_logical_projection_equal":True,"product_requests":0,"model_calls":guard.model_calls,"guard_violations":guard.violations}
    (ROOT/"reopen-result.json").write_text(json.dumps(result,indent=2)+"\n")
finally:
    with (ROOT/"reopen-guard.json").open("x") as output:
        output.write(json.dumps({"violations":guard.violations,"binds":guard.binds,"model_calls":guard.model_calls},indent=2)+"\n")

