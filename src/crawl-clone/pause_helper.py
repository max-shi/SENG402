"""
pause_helper — non-blocking Space-to-pause for terminal scripts.

Usage:
    from pause_helper import PauseController

    pause = PauseController()
    pause.start()          # begin listening in background thread

    # inside your loop:
    pause.check()          # blocks here if paused, resumes on next Space

    pause.stop()           # call when done (stops the listener thread)

Press Space once to pause; press Space again to resume.
Works on macOS/Linux (uses termios raw mode). Gracefully no-ops if stdin
is not a TTY (e.g. when piped or run in CI).
"""

from __future__ import annotations

import sys
import threading


class PauseController:
    def __init__(self) -> None:
        self._paused = False
        self._lock = threading.Lock()
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._thread: threading.Thread | None = None
        self._active = False

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        self._active = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._active = False

    def check(self) -> None:
        """Call this in your main loop. Blocks while paused."""
        self._resume_event.wait()

    def _listen(self) -> None:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while self._active:
                ch = sys.stdin.read(1)
                if ch == " ":
                    with self._lock:
                        self._paused = not self._paused
                        if self._paused:
                            self._resume_event.clear()
                            sys.stderr.write("\n[PAUSED] Press Space to resume...\n")
                            sys.stderr.flush()
                        else:
                            self._resume_event.set()
                            sys.stderr.write("[RESUMED]\n")
                            sys.stderr.flush()
                elif ch in ("\x03", "\x04", "q"):
                    sys.stderr.write("\n[INTERRUPTED]\n")
                    sys.stderr.flush()
                    self._active = False
                    self._resume_event.set()
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
