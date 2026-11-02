"""A small desktop control panel: start the server, reseed, run tests, watch the logs.

Optional and standard-library only. Run ``python launcher.py`` from the virtualenv.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import scrolledtext, ttk

ROOT = Path(__file__).resolve().parent
PORT = 5000
SITE = f"http://127.0.0.1:{PORT}"

BACKGROUND = "#0d1b3e"
PANEL = "#16264f"
TEXT = "#eef1fb"
ACCENT = "#ffb347"
LOG_BACKGROUND = "#060c1e"


class Launcher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.server: subprocess.Popen | None = None
        self.lines: queue.Queue[str] = queue.Queue()
        root.title("Anga Air control panel")
        root.geometry("780x520")
        root.configure(bg=BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._drain_logs()

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Panel.TButton", background=PANEL, foreground=TEXT, borderwidth=0, padding=8
        )
        style.map("Panel.TButton", background=[("active", "#27407f"), ("disabled", "#10193a")])

        tk.Label(
            self.root,
            text="Anga Air",
            bg=BACKGROUND,
            fg=ACCENT,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 0))
        self.status = tk.StringVar(value="Server stopped")
        tk.Label(self.root, textvariable=self.status, bg=BACKGROUND, fg=TEXT).pack(
            anchor="w", padx=14
        )

        bar = tk.Frame(self.root, bg=BACKGROUND)
        bar.pack(fill="x", padx=10, pady=10)
        self.start_button = self._button(bar, "Start server", self.start)
        self.stop_button = self._button(bar, "Stop server", self.stop)
        self.stop_button.state(["disabled"])
        self._button(bar, "Open site", lambda: webbrowser.open(SITE))
        self._button(bar, "Open admin", lambda: webbrowser.open(f"{SITE}/admin/"))
        self._button(bar, "Reseed", self.reseed)
        self._button(bar, "Run tests", self.run_tests)

        self.log = scrolledtext.ScrolledText(
            self.root,
            bg=LOG_BACKGROUND,
            fg=TEXT,
            insertbackground=TEXT,
            font=("Cascadia Mono", 9),
            state="disabled",
            borderwidth=0,
        )
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def _button(self, parent: tk.Frame, text: str, command) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style="Panel.TButton")
        button.pack(side="left", padx=4)
        return button

    def _follow(self, process: subprocess.Popen, done: str | None = None) -> None:
        """Forward a process's output to the log from a background thread."""

        def pump() -> None:
            for line in process.stdout:
                self.lines.put(line)
            process.wait()
            if done:
                self.lines.put(f"{done} (exit code {process.returncode})\n")

        threading.Thread(target=pump, daemon=True).start()

    def _spawn(self, *args: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-m", *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def start(self) -> None:
        if self.server is not None:
            return
        self.server = self._spawn("flask", "--app", "anga", "run", "--port", str(PORT))
        self._follow(self.server, "Server stopped")
        self.status.set(f"Server running at {SITE}")
        self.start_button.state(["disabled"])
        self.stop_button.state(["!disabled"])

    def stop(self) -> None:
        if self.server is None:
            return
        self.server.terminate()
        self.server = None
        self.status.set("Server stopped")
        self.start_button.state(["!disabled"])
        self.stop_button.state(["disabled"])

    def reseed(self) -> None:
        self.lines.put("Reseeding...\n")
        self._follow(self._spawn("flask", "--app", "anga", "seed", "--reset"), "Reseed finished")

    def run_tests(self) -> None:
        self.lines.put("Running tests...\n")
        self._follow(self._spawn("pytest", "-q", "--cov"), "Tests finished")

    def _drain_logs(self) -> None:
        self.log.configure(state="normal")
        while not self.lines.empty():
            self.log.insert("end", self.lines.get())
            self.log.see("end")
        self.log.configure(state="disabled")
        self.root.after(150, self._drain_logs)

    def close(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
