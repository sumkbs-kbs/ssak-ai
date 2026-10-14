import json
import os
import socket
import sys
from pathlib import Path

BASE = Path(os.environ["RECHECK_TRACE_DIR"])


def record(event, **fields):
    with (BASE / f"events-{os.getpid()}.jsonl").open("a") as sink:
        sink.write(json.dumps({"event": event, "pid": os.getpid(), **fields}) + "\n")


record("python-start", executable=sys.executable, prefix=sys.prefix)
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_listen = socket.socket.listen


def owned_listen(sock, backlog=128):
    address = sock.getsockname()
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] != "127.0.0.1" or os.environ.get("RECHECK_ALLOW_SERVER") != "1":
            record("listen-denied")
            raise PermissionError("Probe forbids unowned listener")
        with (BASE / "owned-ports.jsonl").open("a") as sink:
            sink.write(json.dumps({"pid": os.getpid(), "port": address[1]}) + "\n")
        record("owned-listen", port=address[1])
    return original_listen(sock, backlog)


def check_connect(sock, address):
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return
    ports_path = BASE / "owned-ports.jsonl"
    ports = {json.loads(line)["port"] for line in ports_path.read_text().splitlines()} if ports_path.exists() else set()
    allowed = address[0] == "127.0.0.1" and address[1] in ports
    record("socket-connect", host=address[0], port=address[1], allowed=allowed)
    if not allowed:
        raise PermissionError("Probe forbids provider or external connection")


def owned_connect(sock, address):
    check_connect(sock, address)
    return original_connect(sock, address)


def owned_connect_ex(sock, address):
    check_connect(sock, address)
    return original_connect_ex(sock, address)


socket.socket.connect = owned_connect
socket.socket.connect_ex = owned_connect_ex
socket.socket.listen = owned_listen
