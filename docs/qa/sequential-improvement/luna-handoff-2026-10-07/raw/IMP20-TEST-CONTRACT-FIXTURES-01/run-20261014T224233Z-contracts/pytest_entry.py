import json
import os
from pathlib import Path
import socket
import sys
import pytest
original_connect = socket.socket.connect
def guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        with Path(os.environ['TASK_NETWORK_LOG']).open('a') as log:
            log.write(json.dumps({'blocked': True, 'address': str(address)}) + '\n')
        raise OSError('Network disabled for isolated contract tests')
    return original_connect(self, address)
socket.socket.connect = guarded_connect
raise SystemExit(pytest.main(sys.argv[1:]))
