
import asyncio,hashlib,importlib.abc,json,os,sqlite3,sys,threading,types
from pathlib import Path
root=Path(sys.argv[1]).resolve();scenario=sys.argv[2]
receipt={"scenario":scenario,"denied_mutations":[],"socket_attempts":[],"forbidden_imports":[],"agency_paths":[],"rag_roots":[],"ide_roots":[]}
home_before=os.environ.get("HOME")
def audit(event,args):
    paths=[]
    if event=="open":
        path,mode,flags=args
        if isinstance(path,int):return
        if (isinstance(mode,str) and any(c in mode for c in "wax+")) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):paths=[path]
    elif event in ("os.mkdir","os.remove","os.rmdir","os.chmod","os.truncate","sqlite3.connect"):paths=[args[0]]
    elif event in ("os.rename","os.link","os.symlink"):paths=list(args[:2])
    for path in paths:
        if not Path(os.fsdecode(path)).resolve().is_relative_to(root):
            receipt["denied_mutations"].append({"event":event,"path":str(path)})
            raise AssertionError("Nonowned mutation: "+str(path))
    if event in ("socket.connect","socket.bind","subprocess.Popen"):
        receipt["socket_attempts"].append(event)
        raise AssertionError("Network/listener/process forbidden")
sys.addaudithook(audit)
class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".")[0] in {"chromadb","torch","mlx","sentence_transformers","transformers"}:
            receipt["forbidden_imports"].append(fullname)
            raise AssertionError("Native model import forbidden")
sys.meta_path.insert(0,NoModels())
os.environ["PYTHON_DOTENV_DISABLED"]="1"
os.environ["AGK_CONFIG_FILE"]=str(root/"absent-config.yaml")
os.environ["AGK_ENV_FILE"]=str(root/"absent.env")
os.environ["AGK_SERVER_HOST"]="127.0.0.1"
os.environ["AGK_HOOK_VAULT_DIR"]=str(root/"hooks")
for name in ("MODELS","DATA","DOCUMENTS","VECTORS","LOGS","WIKI"):
    os.environ["AGK_PATH_"+name+"_DIR"]=str(root/name.lower())
if scenario=="default":os.environ.pop("AGK_PATH_PROJECT_ROOT",None)
else:os.environ["AGK_PATH_PROJECT_ROOT"]="relative project" if scenario=="relative" else str(root/"owned project")
from fastapi import APIRouter,FastAPI
def module(name,**attrs):
    value=types.ModuleType(name)
    for key,item in attrs.items():setattr(value,key,item)
    sys.modules[name]=value
    return value
module("antigravity_k.api.routes",api_router=APIRouter())
module("antigravity_k.api.auth_routes",router=APIRouter())
module("antigravity_k.api.dependencies",bootstrap_cognitive_active=lambda app:None)
module("antigravity_k.engine.operational_metrics",compute_readiness=lambda: {})
module("antigravity_k.engine.session_manager",SessionPersistenceError=type("SessionPersistenceError",(RuntimeError,),{}))
class Hook:
    _initialized=False
    def __init__(self):self.callbacks=[]
    def subscribe_all(self,callback):self.callbacks.append(callback)
    def shutdown(self):receipt["hook_shutdown"]=True
hook=Hook()
module("antigravity_k.engine.hook_event_bus",init_hook_event_bus=lambda path:hook,get_hook_event_bus=lambda:hook)
audit_db=types.SimpleNamespace(close=lambda:receipt.update(audit_shutdown=True))
module("antigravity_k.engine.audit_db",init_audit_db=lambda path:audit_db,get_audit_db=lambda:audit_db)
module("antigravity_k.engine.panel_activity_tracker",init_panel_activity_tracker=lambda:None)
class Indexer:
    def __init__(self,project_root):receipt["rag_roots"].append(project_root)
    def index_project(self):return 0
module("antigravity_k.engine.rag_indexer",RAGIndexer=Indexer)
class IDE:
    def __init__(self,port,workspace_dir):receipt["ide_roots"].append(workspace_dir)
    def start(self):pass
    def stop(self):receipt["ide_shutdown"]=True
module("antigravity_k.engine.ide_server",IDEServer=IDE)
module("antigravity_k.tools.ssak_search_runtime",shutdown_ssak_search_runtime=lambda:None)
module("antigravity_k.tools.browser_session_owner",shutdown_browser_sessions=lambda:None)
try:
    from antigravity_k.api import server
    from antigravity_k.config import PROJECT_ROOT,PathConfig
    from antigravity_k.engine import event_bus
    from antigravity_k.engine.persistent_agency_store import PersistentAgencyStore
    from antigravity_k.engine import persistent_agency
    configured=PathConfig().project_root
    assert server.config.paths.project_root==configured
    source_root=str(Path(server.__file__).resolve().parents[3])
    receipt["configured_root"]=str(configured);receipt["source_workspace"]=source_root
    if scenario=="default":
        assert configured==PROJECT_ROOT==Path(source_root)
        def default_bridge(*,project_root):receipt["default_bridge_root"]=project_root
        event_bus.bridge_to_hook_event_bus=default_bridge
    else:
        original_init=PersistentAgencyStore.__init__
        def recording_init(self,db_path):
            receipt["agency_paths"].append(db_path)
            original_init(self,db_path)
        PersistentAgencyStore.__init__=recording_init
    async def run():
        app=FastAPI()
        async with server.lifespan(app):
            if scenario=="default":assert receipt["default_bridge_root"]==str(PROJECT_ROOT)
            else:
                expected=configured.resolve()/".antigravity_k"/"agency.db"
                assert receipt["agency_paths"]==[str(expected)]
                assert expected.is_file()
                for callback in tuple(hook.callbacks):callback(types.SimpleNamespace(kind="fixture-observation",payload={"result":"owned"}))
                with sqlite3.connect(expected) as conn:
                    rows=conn.execute("SELECT project_id,trajectory_id,event_type,payload_json FROM agency_events").fetchall()
                assert len(rows)==1 and rows[0][0]==str(configured.resolve()) and rows[0][1]=="hooks"
                receipt["persisted_events"]=rows
            app.state.rag_index_thread.join(timeout=2)
            assert not app.state.rag_index_thread.is_alive()
            assert receipt["rag_roots"]==[source_root] and receipt["ide_roots"]==[source_root]
    asyncio.run(run())
    assert receipt["hook_shutdown"] and receipt["audit_shutdown"] and receipt["ide_shutdown"]
    assert not receipt["denied_mutations"] and not receipt["socket_attempts"] and not receipt["forbidden_imports"]
    assert os.environ.get("HOME")==home_before
    receipt["modules"]={m.__name__:{"path":m.__file__,"sha256":hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()} for m in (server,event_bus,persistent_agency,sys.modules[PersistentAgencyStore.__module__])}
finally:
    (root/"receipt.json").write_text(json.dumps(receipt,indent=2))
