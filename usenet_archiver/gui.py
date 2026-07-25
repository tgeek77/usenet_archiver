#!/usr/bin/env python3
"""Tkinter GUI for Usenet Archiver (githelper-style layout).

Long NNTP work runs in a background thread; the UI stays responsive and shows
a status line plus a scrollable log. Settings persist in ~/.usenet_archiverrc.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from .cli import pull_group
from .creds import resolve_credentials
from .nntp import NNTPClient
from . import __version__

CONFIG_PATH = Path.home() / ".usenet_archiverrc"


class QueueLogHandler(logging.Handler):
    """Forward log records to a callback on the Tk main thread."""

    def __init__(self, emit_fn: Callable[[str], None], root: tk.Tk):
        super().__init__()
        self._emit_fn = emit_fn
        self._root = root

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self._root.after(0, lambda m=msg: self._emit_fn(m))


class UsenetArchiverGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Usenet Archiver")
        self.root.geometry("920x720")

        self.config = self.load_config()
        self._active_tasks = 0
        self._stop_event = threading.Event()
        self._run_gen = 0
        self._log_handler: Optional[QueueLogHandler] = None

        self.status_var = tk.StringVar(value="Ready")
        self._build()
        self._load_fields_from_config()

    # --- config ------------------------------------------------------------

    def load_config(self) -> Dict[str, Any]:
        try:
            with CONFIG_PATH.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def save_config(self) -> None:
        data = {
            "server": self.server_var.get().strip(),
            "port": self.port_var.get().strip(),
            "username": self.user_var.get().strip(),
            "password_file": self.password_file_var.get().strip(),
            "use_ssl": bool(self.ssl_var.get()),
            "newsgroups": self._groups_from_listbox(),
            "start_date": self.start_var.get().strip(),
            "end_date": self.end_var.get().strip(),
            "connections": self.connections_var.get().strip(),
            "pipeline_depth": self.pipeline_var.get().strip(),
            "output_dir": self.output_var.get().strip(),
            "skip_completed": bool(self.skip_completed_var.get()),
            "timeout": self.timeout_var.get().strip(),
        }
        try:
            with CONFIG_PATH.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.chmod(CONFIG_PATH, 0o600)
        except OSError as e:
            self._append_log(f"Warning: could not save config: {e}")

    def _load_fields_from_config(self) -> None:
        c = self.config
        self.server_var.set(c.get("server", ""))
        self.port_var.set(str(c.get("port", "")))
        self.user_var.set(c.get("username", ""))
        self.password_file_var.set(c.get("password_file", ""))
        self.ssl_var.set(1 if c.get("use_ssl", True) else 0)
        groups = c.get("newsgroups")
        if not groups and c.get("newsgroup"):
            groups = [c.get("newsgroup")]
        self._set_groups_list(groups or [])
        self.start_var.set(c.get("start_date", ""))
        self.end_var.set(c.get("end_date", ""))
        self.connections_var.set(str(c.get("connections", "16")))
        self.pipeline_var.set(str(c.get("pipeline_depth", "32")))
        self.output_var.set(c.get("output_dir", str(Path.cwd())))
        self.skip_completed_var.set(1 if c.get("skip_completed", False) else 0)
        self.timeout_var.set(str(c.get("timeout", "60")))

    def _groups_from_listbox(self) -> List[str]:
        return list(self.groups_list.get(0, tk.END))

    def _set_groups_list(self, groups: List[str]) -> None:
        self.groups_list.delete(0, tk.END)
        for g in groups:
            g = (g or "").strip()
            if g:
                self.groups_list.insert(tk.END, g)
        self._update_job_preview()

    # --- UI helpers --------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text.rstrip() + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _run_in_background(self, label: str, work_fn, done_fn=None) -> None:
        self._active_tasks += 1
        active = self._active_tasks
        status = f"{label}… ({active} active)" if active > 1 else f"{label}…"
        self._set_status(status)
        self._append_log(f"[{label}] started")
        self.run_btn.configure(state=tk.DISABLED)
        self.dry_run_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        def runner():
            try:
                result = work_fn()
                error = None
            except Exception as e:
                result = None
                error = e

            def finish():
                self._active_tasks -= 1
                self.run_btn.configure(state=tk.NORMAL)
                self.dry_run_btn.configure(state=tk.NORMAL)
                self.stop_btn.configure(state=tk.DISABLED)
                if error is not None:
                    err_text = str(error)
                    self._set_status(f"{label} failed")
                    self._append_log(f"[{label}] ERROR: {err_text}")
                    messagebox.showerror("Error", f"{label} failed:\n{err_text}")
                    return
                self._set_status(f"{label} done")
                self._append_log(f"[{label}] done")
                if done_fn is not None:
                    done_fn(result)

            self.root.after(0, finish)

        threading.Thread(target=runner, daemon=True).start()

    # --- build UI ----------------------------------------------------------

    def _build(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.pull_frame = ttk.Frame(notebook)
        notebook.add(self.pull_frame, text="Pull")

        self._build_connection_frame(self.pull_frame)
        self._build_job_frame(self.pull_frame)
        self._build_actions(self.pull_frame)
        self._build_status_log(self.pull_frame)

        about = ttk.Frame(notebook)
        notebook.add(about, text="About")
        ttk.Label(
            about,
            text=(
                "Usenet Archiver GUI\n\n"
                "Fetches text newsgroups over NNTP into mbox files.\n"
                "Settings are saved to ~/.usenet_archiverrc (mode 0600).\n\n"
                "Password file: a plain-text file whose entire contents are\n"
                "the NNTP password. One line is best; a trailing newline is\n"
                "ignored. Prefer this over typing a password into the form.\n\n"
                f"Version {__version__}\n"
                "CLI: usenet-archiver -c pull …  |  Dev: ./bin/usenet-archiver -c pull"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=16, pady=16)

    def _row(self, parent, label: str, var: tk.Variable, width: int = 28):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _build_connection_frame(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Connection")
        frame.pack(fill=tk.X, padx=10, pady=8)

        self.server_var = tk.StringVar()
        self.port_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.password_file_var = tk.StringVar()
        self.ssl_var = tk.IntVar(value=1)
        self.timeout_var = tk.StringVar(value="60")

        host_row = ttk.Frame(frame)
        host_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(host_row, text="Server:", width=16).pack(side=tk.LEFT)
        ttk.Entry(host_row, textvariable=self.server_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Label(host_row, text="Port:").pack(side=tk.LEFT, padx=(8, 4))
        port_entry = ttk.Entry(host_row, textvariable=self.port_var, width=6)
        port_entry.pack(side=tk.LEFT)
        vcmd = (self.root.register(self._validate_port_digits), "%P")
        port_entry.configure(validate="key", validatecommand=vcmd)

        cred_row = ttk.Frame(frame)
        cred_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(cred_row, text="Username:", width=16).pack(side=tk.LEFT)
        ttk.Entry(cred_row, textvariable=self.user_var, width=18).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Label(cred_row, text="Password:").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Entry(cred_row, textvariable=self.password_var, show="*", width=18).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        pf_row = ttk.Frame(frame)
        pf_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(pf_row, text="Password file:", width=16).pack(side=tk.LEFT)
        ttk.Entry(pf_row, textvariable=self.password_file_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(pf_row, text="Browse…", command=self._browse_password_file).pack(
            side=tk.LEFT, padx=4
        )

        ttk.Label(
            frame,
            text="Password file = plain text containing only the NNTP password "
            "(one line; trailing newline OK).",
        ).pack(fill=tk.X, padx=5, pady=(0, 2))

        opts = ttk.Frame(frame)
        opts.pack(fill=tk.X, padx=5, pady=4)
        ttk.Checkbutton(opts, text="TLS (NNTPS)", variable=self.ssl_var).pack(side=tk.LEFT)
        ttk.Label(opts, text="Timeout (s):").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Entry(opts, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT)

    def _validate_port_digits(self, proposed: str) -> bool:
        if proposed == "":
            return True
        return proposed.isdigit() and len(proposed) <= 6

    def _build_job_frame(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Archive job")
        frame.pack(fill=tk.X, padx=10, pady=8)

        self.group_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.connections_var = tk.StringVar(value="16")
        self.pipeline_var = tk.StringVar(value="32")
        self.output_var = tk.StringVar(value=str(Path.cwd()))
        self.skip_completed_var = tk.IntVar(value=0)

        add_row = ttk.Frame(frame)
        add_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(add_row, text="Newsgroup:", width=16).pack(side=tk.LEFT)
        group_entry = ttk.Entry(add_row, textvariable=self.group_var)
        group_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        group_entry.bind("<Return>", lambda _e: self._add_group())
        ttk.Button(add_row, text="Add", command=self._add_group).pack(side=tk.LEFT, padx=4)

        list_row = ttk.Frame(frame)
        list_row.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Label(list_row, text="Queue:", width=16).pack(side=tk.LEFT, anchor=tk.N)
        list_wrap = ttk.Frame(list_row)
        list_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.groups_list = tk.Listbox(list_wrap, height=5, exportselection=False)
        scroll = ttk.Scrollbar(list_wrap, command=self.groups_list.yview)
        self.groups_list.configure(yscrollcommand=scroll.set)
        self.groups_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        btns = ttk.Frame(list_row)
        btns.pack(side=tk.LEFT, padx=4, anchor=tk.N)
        ttk.Button(btns, text="Import…", command=self._import_groups_file).pack(fill=tk.X, pady=1)
        ttk.Button(btns, text="Remove", command=self._remove_selected_groups).pack(fill=tk.X, pady=1)
        ttk.Button(btns, text="Clear", command=self._clear_groups).pack(fill=tk.X, pady=1)

        ttk.Label(
            frame,
            text="Import: one newsgroup per line (# comments allowed). "
            "Names containing “binary” (and common variants) are skipped.",
        ).pack(fill=tk.X, padx=5, pady=(0, 2))

        dates = ttk.Frame(frame)
        dates.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(dates, text="Start date:", width=16).pack(side=tk.LEFT)
        ttk.Entry(dates, textvariable=self.start_var, width=12).pack(side=tk.LEFT)
        ttk.Label(dates, text="End date:").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Entry(dates, textvariable=self.end_var, width=12).pack(side=tk.LEFT)
        ttk.Label(dates, text="(YYYY-MM-DD)").pack(side=tk.LEFT, padx=6)

        hint = ttk.Frame(frame)
        hint.pack(fill=tk.X, padx=5, pady=(0, 2))
        ttk.Label(
            hint,
            text="Blank end = through today (UTC). Same start tomorrow → new pull / new mbox.",
        ).pack(side=tk.LEFT, padx=(0, 0))

        self.job_preview_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.job_preview_var).pack(
            fill=tk.X, padx=5, pady=(0, 4)
        )
        self.start_var.trace_add("write", lambda *_: self._update_job_preview())
        self.end_var.trace_add("write", lambda *_: self._update_job_preview())
        self.root.after(0, self._update_job_preview)

        perf = ttk.Frame(frame)
        perf.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(perf, text="Connections:", width=16).pack(side=tk.LEFT)
        ttk.Entry(perf, textvariable=self.connections_var, width=6).pack(side=tk.LEFT)
        ttk.Label(perf, text="Pipeline depth:").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Entry(perf, textvariable=self.pipeline_var, width=6).pack(side=tk.LEFT)

        out = ttk.Frame(frame)
        out.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(out, text="Output dir:", width=16).pack(side=tk.LEFT)
        ttk.Entry(out, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(out, text="Browse…", command=self._browse_output_dir).pack(
            side=tk.LEFT, padx=4
        )

        skip_row = ttk.Frame(frame)
        skip_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Checkbutton(
            skip_row,
            text="Skip if this exact job was already completed "
            "(off = re-run to catch up on new posts via dedup)",
            variable=self.skip_completed_var,
        ).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=5, pady=6)

    def _build_actions(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=10, pady=4)
        self.run_btn = ttk.Button(row, text="Run pull", command=self.start_pull)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.dry_run_btn = ttk.Button(row, text="Dry run", command=self.start_dry_run)
        self.dry_run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(row, text="Stop", command=self.stop_pull, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="Save settings", command=self.save_config).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="Clear log", command=self._clear_log).pack(side=tk.LEFT)

    def _build_status_log(self, parent) -> None:
        ttk.Label(parent, textvariable=self.status_var).pack(
            fill=tk.X, padx=12, pady=(4, 0)
        )
        frame = ttk.LabelFrame(parent, text="Log")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.log_text = tk.Text(frame, height=14, wrap=tk.WORD)
        scroll = ttk.Scrollbar(frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Allow copy; block casual typing
        self.log_text.bind("<Key>", self._readonly_log_key)

    def _readonly_log_key(self, event):
        if event.state & 0x4 and event.keysym.lower() in ("c", "a"):
            return None
        if event.keysym in (
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        ):
            return None
        return "break"

    def _browse_password_file(self) -> None:
        path = filedialog.askopenfilename(title="Password file")
        if path:
            self.password_file_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Output directory")
        if path:
            self.output_var.set(path)

    def _add_group(self) -> None:
        from .policy import is_binary_newsgroup

        name = self.group_var.get().strip()
        if not name:
            return
        if is_binary_newsgroup(name):
            messagebox.showwarning(
                "Binary group",
                f"Skipping {name} (looks like a binary newsgroup).",
            )
            self.group_var.set("")
            return
        existing = set(self._groups_from_listbox())
        if name not in existing:
            self.groups_list.insert(tk.END, name)
        self.group_var.set("")
        self._update_job_preview()

    def _remove_selected_groups(self) -> None:
        for idx in reversed(self.groups_list.curselection()):
            self.groups_list.delete(idx)
        self._update_job_preview()

    def _clear_groups(self) -> None:
        self.groups_list.delete(0, tk.END)
        self._update_job_preview()

    def _import_groups_file(self) -> None:
        from .policy import is_binary_newsgroup, read_groups_file

        path = filedialog.askopenfilename(
            title="Import newsgroups (one per line)",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            lines = read_groups_file(path)
        except OSError as e:
            messagebox.showerror("Import failed", str(e))
            return
        existing = set(self._groups_from_listbox())
        added = 0
        skipped_bin = 0
        for line in lines:
            # Accept bare group or group>filename — queue uses the group name only
            # for display; filename override is CLI-oriented. Keep full line if
            # it has no '>', else group part for the list.
            group = line.split(">", 1)[0].strip()
            if not group:
                continue
            if is_binary_newsgroup(group):
                skipped_bin += 1
                self._append_log(f"Skipping binary newsgroup {group}")
                continue
            if group not in existing:
                self.groups_list.insert(tk.END, group)
                existing.add(group)
                added += 1
        self._update_job_preview()
        msg = f"Imported {added} newsgroup(s)."
        if skipped_bin:
            msg += f" Skipped {skipped_bin} binary name(s)."
        self._append_log(msg)

    def _update_job_preview(self) -> None:
        """Show the resolved date window and mbox name for the current fields."""
        from datetime import datetime

        from usenet_archiver.cli import mbox_name_for, normalize_date_range

        groups = self._groups_from_listbox()
        start_s = self.start_var.get().strip() or None
        end_s = self.end_var.get().strip() or None
        try:
            start = datetime.strptime(start_s, "%Y-%m-%d") if start_s else None
            end = datetime.strptime(end_s, "%Y-%m-%d") if end_s else None
            start, end = normalize_date_range(start, end)
        except ValueError:
            self.job_preview_var.set("Output: (fix date)")
            return
        if not groups:
            self.job_preview_var.set("Output: (add at least one newsgroup)")
            return
        sample = groups[0]
        name = mbox_name_for(sample, None, start, end)
        extra = f" (+{len(groups) - 1} more)" if len(groups) > 1 else ""
        if start and end:
            open_ended = not end_s and bool(start_s)
            note = " — end defaults to today UTC" if open_ended else ""
            self.job_preview_var.set(
                f"Output: {name}{extra}  ({start.date()} .. {end.date()}{note})"
            )
        else:
            self.job_preview_var.set(f"Output: {name}{extra}  (full group range)")

    # --- actions -----------------------------------------------------------

    def stop_pull(self) -> None:
        self._stop_event.set()
        try:
            import usenet_archiver.cli as cli_mod

            cli_mod._TERMINATED = True
        except Exception:
            pass
        self._append_log("[Stop] cancel requested")
        self._set_status("Stopping…")

    def _validate(self) -> Dict[str, Any]:
        from .creds import split_host
        from .policy import check_server_allowed, is_binary_newsgroup

        server = self.server_var.get().strip()
        groups = [g for g in self._groups_from_listbox() if g.strip()]
        # Allow typing a group without pressing Add.
        pending = self.group_var.get().strip()
        if pending and pending not in groups:
            if is_binary_newsgroup(pending):
                raise ValueError(f"Skipping {pending} (looks like a binary newsgroup).")
            groups.append(pending)
        if not server:
            raise ValueError("Server is required.")
        try:
            host, _ = split_host(server, default_port=None)
        except ValueError as e:
            raise ValueError(f"Invalid server: {e}") from e
        check_server_allowed(host)
        if not groups:
            raise ValueError("Add at least one newsgroup (or import a list).")
        port_s = self.port_var.get().strip()
        if port_s and (not port_s.isdigit() or len(port_s) > 6):
            raise ValueError("Port must be at most 6 digits.")
        port = int(port_s) if port_s else None
        if port is not None and not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535.")
        try:
            connections = int(self.connections_var.get().strip() or "8")
            pipeline = int(self.pipeline_var.get().strip() or "32")
            timeout = int(self.timeout_var.get().strip() or "60")
        except ValueError as e:
            raise ValueError("Connections, pipeline depth, and timeout must be integers.") from e
        if connections < 1 or pipeline < 1:
            raise ValueError("Connections and pipeline depth must be >= 1.")
        out = self.output_var.get().strip() or str(Path.cwd())
        if not Path(out).is_dir():
            raise ValueError(f"Output directory does not exist: {out}")

        start_s = self.start_var.get().strip() or None
        end_s = self.end_var.get().strip() or None
        from datetime import datetime

        from usenet_archiver.cli import normalize_date_range

        try:
            start_date = datetime.strptime(start_s, "%Y-%m-%d") if start_s else None
            end_date = datetime.strptime(end_s, "%Y-%m-%d") if end_s else None
        except ValueError as e:
            raise ValueError("Dates must be YYYY-MM-DD.") from e
        try:
            start_date, end_date = normalize_date_range(start_date, end_date)
        except ValueError as e:
            raise ValueError(str(e).capitalize() + ".") from e

        return {
            "server": server,
            "port": port,
            "username": self.user_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "password_file": self.password_file_var.get().strip() or None,
            "use_ssl": bool(self.ssl_var.get()),
            "groups": groups,
            "start_date": start_date,
            "end_date": end_date,
            "connections": connections,
            "pipeline_depth": pipeline,
            "timeout": timeout,
            "output_dir": out,
            "skip_completed": bool(self.skip_completed_var.get()),
        }

    def start_dry_run(self) -> None:
        self.start_pull(dry_run=True)

    def start_pull(self, dry_run: bool = False) -> None:
        try:
            opts = self._validate()
        except ValueError as e:
            messagebox.showwarning("Validation", str(e))
            return

        # Sync pending single-group entry into the listbox for persistence.
        self._set_groups_list(opts["groups"])
        self.group_var.set("")
        self.save_config()
        self._stop_event = threading.Event()
        self._run_gen += 1
        gen = self._run_gen
        self.progress.start(12)

        # Attach log handler for this run
        logger = logging.getLogger()
        if self._log_handler is not None:
            logger.removeHandler(self._log_handler)
        self._log_handler = QueueLogHandler(self._append_log, self.root)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._log_handler.setLevel(logging.INFO)
        logger.setLevel(logging.INFO)
        logger.addHandler(self._log_handler)

        label = "Dry run" if dry_run else "Pull"

        def work():
            # Import stop globals used by pull_group / fetch
            import usenet_archiver.cli as cli_mod
            from usenet_archiver.cli import TerminatedBySignal, mbox_name_for
            from usenet_archiver.policy import is_binary_newsgroup

            cli_mod._STOP_EVENT = self._stop_event
            cli_mod._TERMINATED = False

            cwd = os.getcwd()
            written = []
            try:
                os.chdir(opts["output_dir"])
                endpoint = resolve_credentials(
                    server=opts["server"],
                    port=opts["port"],
                    username=opts["username"],
                    password=opts["password"],
                    password_file=opts["password_file"],
                    use_netrc=True,
                    use_ssl=opts["use_ssl"],
                )
                client = NNTPClient(
                    server=endpoint.host,
                    port=endpoint.port,
                    username=endpoint.username,
                    password=endpoint.password,
                    use_ssl=opts["use_ssl"],
                    verbose=False,
                    timeout=opts["timeout"],
                )
                client.connect()
                try:
                    if self._stop_event.is_set() or gen != self._run_gen:
                        return "cancelled"
                    conn_kwargs = {
                        "server": endpoint.host,
                        "port": endpoint.port,
                        "username": endpoint.username,
                        "password": endpoint.password,
                        "use_ssl": opts["use_ssl"],
                        "verbose": False,
                        "timeout": opts["timeout"],
                    }
                    for group in opts["groups"]:
                        if self._stop_event.is_set() or gen != self._run_gen:
                            return "cancelled"
                        if is_binary_newsgroup(group):
                            logging.getLogger("usenet_archiver").info(
                                "Skipping binary newsgroup %s", group
                            )
                            continue
                        mbox_filename = mbox_name_for(
                            group, None, opts["start_date"], opts["end_date"]
                        )
                        if opts["start_date"] and opts["end_date"]:
                            logging.getLogger("usenet_archiver").info(
                                "Job window %s .. %s → %s",
                                opts["start_date"].date(),
                                opts["end_date"].date(),
                                mbox_filename,
                            )
                        try:
                            pull_group(
                                client=client,
                                group=group,
                                mbox_filename=mbox_filename,
                                start_date=opts["start_date"],
                                end_date=opts["end_date"],
                                overview_chunk=10000,
                                dedup=True,
                                plugins=[],
                                completed_log="completed_newsgroups.log",
                                logger=logging.getLogger("usenet_archiver"),
                                conn_kwargs=conn_kwargs,
                                connections=opts["connections"],
                                pipeline_depth=opts["pipeline_depth"],
                                skip_completed=opts["skip_completed"],
                                dry_run=dry_run,
                            )
                        except TerminatedBySignal:
                            return "cancelled"
                        written.append(mbox_filename)
                    if dry_run:
                        return {"dry_run": True, "jobs": written}
                    return ", ".join(written) if written else None
                finally:
                    try:
                        client.quit()
                    except Exception:
                        client.close()
            finally:
                os.chdir(cwd)

        def done(result):
            self.progress.stop()
            if self._log_handler is not None:
                logging.getLogger().removeHandler(self._log_handler)
                self._log_handler = None
            if result == "cancelled":
                self._set_status("Cancelled")
                return
            if isinstance(result, dict) and result.get("dry_run"):
                jobs = result.get("jobs") or []
                messagebox.showinfo(
                    "Dry run complete",
                    "No articles downloaded.\n"
                    f"Planned {len(jobs)} job(s).\n"
                    "See the log for overview / dedup counts.",
                )
                return
            if result:
                messagebox.showinfo("Done", f"Wrote {result}\nin {opts['output_dir']}")

        self._run_in_background(label, work, done_fn=done)


def main() -> None:
    root = tk.Tk()
    UsenetArchiverGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
