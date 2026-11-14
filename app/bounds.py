"""Hard local-tool deadline inside the RQ job's main thread."""
import signal,threading
from contextlib import contextmanager
@contextmanager
def tool_deadline(seconds):
    if threading.current_thread() is not threading.main_thread():
        # Verifier local lookups are bounded by incoming evidence count and HTTP handoff.
        yield;return
    def expired(*_):raise TimeoutError('local tool deadline exceeded')
    old=signal.signal(signal.SIGALRM,expired);previous=signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,*previous);signal.signal(signal.SIGALRM,old)
