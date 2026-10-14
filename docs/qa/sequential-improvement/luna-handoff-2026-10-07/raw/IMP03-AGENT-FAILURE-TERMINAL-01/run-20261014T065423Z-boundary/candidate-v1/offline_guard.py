import socket, os, json, sys, hashlib
from pathlib import Path
attempts=[]
def pytest_sessionstart(session):
    def deny(*args, **kwargs):
        attempts.append("socket connection")
        raise AssertionError("network connection forbidden in offline boundary validation")
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
def pytest_sessionfinish(session, exitstatus):
    output=Path(os.environ["CANDIDATE_CHECK_DIR"])
    repo=Path.cwd().resolve()
    modules={}
    for name,module in list(sys.modules.items()):
        file=getattr(module,"__file__",None)
        if not file: continue
        path=Path(file)
        try: rel=path.resolve().relative_to(repo)
        except ValueError: continue
        if path.is_file() and str(rel).startswith(("src/", "tests/")):
            modules[name]={"path":str(path.resolve()),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    (output/"module-socket-binding.json").write_text(json.dumps({"socket_connection_attempts":attempts,"exitstatus":int(exitstatus),"modules":modules},indent=2))
