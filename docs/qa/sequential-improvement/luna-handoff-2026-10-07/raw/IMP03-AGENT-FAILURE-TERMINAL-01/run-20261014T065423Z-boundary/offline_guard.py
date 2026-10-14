import socket

def pytest_sessionstart(session):
    def deny(*args, **kwargs):
        raise AssertionError("network connection forbidden in offline boundary validation")
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
