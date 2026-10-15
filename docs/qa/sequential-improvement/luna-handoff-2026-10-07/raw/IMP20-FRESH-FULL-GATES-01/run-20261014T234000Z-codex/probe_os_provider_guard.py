from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = '/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python'
with socket.socket() as denied, socket.socket() as allowed:
    for listener in (denied, allowed):
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(1)
    blocked_port = denied.getsockname()[1]
    allowed_port = allowed.getsockname()[1]
    profile = f'(version 1)(allow default)(deny network-outbound (remote tcp "localhost:{blocked_port}"))'
    code = '''import json,socket,sys
result={}
for label,port in (("blocked",int(sys.argv[1])),("allowed",int(sys.argv[2]))):
 try:
  with socket.create_connection(("127.0.0.1",port),timeout=2) as connection:
   connection.sendall(b"owned-control")
  result[label]="connected"
 except OSError as error:
  result[label]={"errno":error.errno,"type":type(error).__name__}
print(json.dumps(result))
'''
    command = ['/usr/bin/sandbox-exec', '-p', profile, PYTHON, '-B', '-c', code, str(blocked_port), str(allowed_port)]
    child = subprocess.run(command, capture_output=True, text=True, timeout=10)
    result = {'exit_code': child.returncode, 'stdout': child.stdout, 'stderr': child.stderr, 'profile': profile}
    assert child.returncode == 0, result
    values = json.loads(child.stdout)
    assert values['blocked']['errno'] == 1, result
    assert values['allowed'] == 'connected', result
    with allowed.accept()[0] as connection:
        assert connection.recv(32) == b'owned-control'
    try:
        unexpected, _ = denied.accept()
    except TimeoutError:
        result['blocked_listener_accepts'] = 0
    else:
        unexpected.close()
        raise AssertionError('Denied listener received a connection')
    result['allowed_listener_accepts'] = 1
    target = BASE / 'os-guard-control.json'
    assert not target.exists()
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
