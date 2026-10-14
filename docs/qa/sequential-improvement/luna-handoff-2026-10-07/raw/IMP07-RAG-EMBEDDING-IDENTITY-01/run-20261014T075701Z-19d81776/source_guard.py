import hashlib,json,os,socket,sys
from pathlib import Path
out=Path(os.environ["BINDING_CHECK_DIR"])
repo=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
attempts=[]
def deny(*args,**kwargs):
    attempts.append("physical socket")
    raise AssertionError("Physical sockets forbidden in offline contract checks")
socket.socket.connect=deny
socket.socket.connect_ex=deny
socket.create_connection=deny
def pytest_sessionfinish(session,exitstatus):
    modules={}
    for name in ("antigravity_k.engine.vector_store","antigravity_k.engine.project_embedding_binding","antigravity_k.engine.rag_indexer","antigravity_k.api.dependencies","antigravity_k.engine.embeddings"):
        mod=sys.modules.get(name)
        path=Path(mod.__file__).resolve() if mod else None
        modules[name]={"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest() if path else None}
        if path is None or not path.is_relative_to(repo):
            session.exitstatus=1
    if attempts: session.exitstatus=1
    (out/"module-socket-binding.json").write_text(json.dumps({"modules":modules,"socket_attempts":attempts,"exitstatus":int(session.exitstatus)},indent=2))
