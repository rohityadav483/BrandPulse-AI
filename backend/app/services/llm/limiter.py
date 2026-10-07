import threading


class LLMLimiter:
    def __init__(self, max_concurrency: int = 1, max_calls: int = 8):
        self._sem = threading.BoundedSemaphore(max_concurrency)
        self.max_calls = max_calls

    def slot(self):
        return self._sem
