    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        # Signals can only be listened to from the main thread.
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        # always use signal.signal, even if loop.add_signal_handler is available
        # this allows to restore previous signal handlers later on
        original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)
        # If we did gracefully shut down due to a signal, try to
        # trigger the expected behaviour now; multiple signals would be
        # done LIFO, see https://stackoverflow.com/questions/48434964
        for captured_signal in reversed(self._captured_signals):
            signal.raise_signal(captured_signal)
