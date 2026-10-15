import json
import os
from pathlib import Path
import socket

import pytest

counts = {'blocked_connect': 0, 'mock_connect_ex': 0, 'blocked_bind': 0, 'blocked_listen': 0}


@pytest.fixture(autouse=True)
def _guard(monkeypatch):
    def deny_connect(*args, **kwargs):
        counts['blocked_connect'] += 1
        raise AssertionError('Actual network is forbidden in Doctor fixture validation')

    def mock_connect_ex(*args, **kwargs):
        counts['mock_connect_ex'] += 1
        return 61

    def deny_bind(*args, **kwargs):
        counts['blocked_bind'] += 1
        raise AssertionError('Actual bind is forbidden')

    def deny_listen(*args, **kwargs):
        counts['blocked_listen'] += 1
        raise AssertionError('Actual listen is forbidden')

    monkeypatch.setattr(socket.socket, 'connect', deny_connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', mock_connect_ex)
    monkeypatch.setattr(socket.socket, 'bind', deny_bind)
    monkeypatch.setattr(socket.socket, 'listen', deny_listen)


def pytest_sessionfinish():
    Path(os.environ['DOCTOR_GUARD_OUTPUT']).write_text(json.dumps(counts, indent=2) + '\n')
