"""World Engine: a window that shows whether the world engine runs, with buttons to start, stop, open, upgrade,
rebuild, reset and delete it. It runs on the system's Python with tkinter (standard library only), before the engine's
environment .venv exists; all its work is done by control.py, which the launchers of scripts/ do the rest for.

    python panel/world_engine_panel.py                    open the window (scripts/panel.cmd, scripts/panel.command)
    python panel/world_engine_panel.py --install-shortcut make "World Engine" on the Desktop and in the Start menu
                                                          (Windows), or ~/Applications/World Engine.app (macOS)
           [--dest FOLDER]                                ... in FOLDER instead
    python panel/world_engine_panel.py --self-test        open the window, show every state, close; exit code 0 if
                                                          all went well (for the workflow)
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import control  # noqa: E402
import icons  # noqa: E402
from control import (BUILDING, ERROR, INSTALLING, RUNNING, STARTING, STOPPED, STOPPING, WORKING,  # noqa: E402
                     ControlError, Status, button_states)

TKINTER_MISSING = """This Python has no tkinter, which the World Engine panel needs:
  {exe}
  macOS with Homebrew:  brew install python-tk@{v}
  macOS, other:         the installer from https://www.python.org/downloads/ (it includes tkinter)
  Windows:              run the Python installer again, choose Modify, and tick "tcl/tk and IDLE"
  Ubuntu:               sudo apt install python3-tk
"""

LIGHTS = {STOPPED: "#8b959f", INSTALLING: "#e2a21b", BUILDING: "#e2a21b", STARTING: "#e2a21b", RUNNING: "#2fb34f",
          STOPPING: "#e2a21b", WORKING: "#e2a21b", ERROR: "#d63a30"}
INSTALL_LABEL = "Install app" if control.ON_MAC else "Install shortcut"
HINTS = {"start": "Start the world engine: install it and build the world the first time, then serve it.",
         "stop": "Stop the world engine (also one started from a terminal with scripts/run.sh).",
         "browser": "Open the viewer in your browser.",
         "upgrade": "Fetch the new version (git pull) and build the default world again with it.",
         "rebuild": "Delete the selected world and build it again.",
         "reset": "Delete the environment .venv; the next start installs the packages again.",
         "delete": "Remove the environment, the worlds and the panel's files from this computer.",
         "folder": "Show the world-engine folder.",
         "install": ("Put World Engine in your Applications folder." if control.ON_MAC else
                     "Put a World Engine shortcut on the Desktop and in the Start menu."),
         "copy": "Copy the launcher's output, to send to someone who helps."}


def set_windows_dpi_awareness():
    """Draw sharply on screens scaled above 100 % (Windows). Python's own programs do not declare that they handle
    scaling, so Windows would stretch the window's bitmap; IDLE asks for it the same way [DOCUMENTED: CPython,
    Lib/idlelib/util.py, fix_win_hidpi]."""
    if control.ON_WINDOWS:
        try:
            import ctypes
            ctypes.OleDLL("shcore").SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass


class Panel:
    def __init__(self, root, controller, poll=True):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root, self.c = tk, ttk, root, controller
        self.queue = queue.Queue()
        self.action = None                                  # the name of the action that runs, if one does
        self.status = Status(STOPPED)
        self.details_open = False
        self._wake = threading.Event()
        self._closing = False

        root.title(control.APP_NAME)
        root.geometry("540x440")
        root.minsize(480, 380)
        self._set_theme()
        self._load_images()
        self._build()
        self.render(self.status)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._drain)
        if poll:
            threading.Thread(target=self._poll, daemon=True).start()

    # ------------------------------------------------------------------ looks
    def _set_theme(self):
        style = self.ttk.Style(self.root)
        names = style.theme_names()
        for theme in (("aqua",) if control.ON_MAC else ("vista", "xpnative") if control.ON_WINDOWS else ("clam",)):
            if theme in names:
                style.theme_use(theme)
                break
        from tkinter import font
        base = font.nametofont("TkDefaultFont", root=self.root)
        size = abs(int(base.cget("size"))) or 10
        self.fonts = {"title": base.copy(), "state": base.copy(), "log": font.nametofont("TkFixedFont", root=self.root).copy()}
        self.fonts["title"].configure(size=-round(size * 1.75) if base.cget("size") < 0 else round(size * 1.6), weight="bold")
        self.fonts["state"].configure(size=-round(size * 1.35) if base.cget("size") < 0 else round(size * 1.25), weight="bold")
        style.configure("Title.TLabel", font=self.fonts["title"])
        style.configure("State.TLabel", font=self.fonts["state"])
        style.configure("Small.TLabel", foreground="#5b6670")
        style.configure("Link.TLabel", foreground="#1f63c6")
        style.configure("Panel.TButton", padding=(6, 4))

    def _load_images(self):
        tk = self.tk
        scale = 1.0
        if not control.ON_MAC:                              # macOS draws images in points and scales them itself
            try:
                scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
            except tk.TclError:
                pass
        size = int(round(20 * scale))
        self.images = {}
        for name in icons.ICONS:
            self.images[name] = icons.photo(tk, icons.icon_png(name, size), self.root)
            self.images[name + "-off"] = icons.photo(tk, icons.icon_png(name, size, disabled=True), self.root)
        light = int(round(18 * scale))
        self.lights = {colour: icons.photo(tk, icons.light_png(colour, light), self.root) for colour in set(LIGHTS.values())}
        assets = HERE / "assets"
        try:
            self.app_icon = tk.PhotoImage(master=self.root, file=str(assets / "world-engine.png"))
            self.logo = tk.PhotoImage(master=self.root, file=str(assets / "world-engine-64.png"))
            self.root.iconphoto(True, self.app_icon, self.logo)
            if control.ON_WINDOWS:
                self.root.iconbitmap(default=str(assets / "world-engine.ico"))
        except tk.TclError:
            self.logo = None

    def _build(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        outer = ttk.Frame(root, padding=(16, 14, 16, 10))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        if self.logo is not None:
            ttk.Label(head, image=self.logo).grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, 14))
        ttk.Label(head, text=control.APP_NAME, style="Title.TLabel").grid(row=0, column=1, sticky="w")
        line = ttk.Frame(head)
        line.grid(row=1, column=1, sticky="w", pady=(4, 0))
        self.light = ttk.Label(line)
        self.light.pack(side="left", padx=(0, 6))
        self.state_label = ttk.Label(line, style="State.TLabel")
        self.state_label.pack(side="left")
        self.url_label = ttk.Label(head, style="Link.TLabel", cursor="hand2")
        self.url_label.grid(row=2, column=1, sticky="w")
        self.url_label.bind("<Button-1>", lambda e: self.on_browser())
        self.detail_label = ttk.Label(head, style="Small.TLabel", wraplength=400, justify="left")
        self.detail_label.grid(row=3, column=1, sticky="w")
        head.bind("<Configure>", lambda e: self.detail_label.configure(wraplength=max(200, e.width - 100)))

        ttk.Separator(outer).grid(row=1, column=0, sticky="ew", pady=10)
        grid = ttk.Frame(outer)
        grid.grid(row=2, column=0, sticky="ew")
        layout = (("start", "Start", self.on_start), ("stop", "Stop", self.on_stop), ("browser", "Open in browser", self.on_browser),
                  ("upgrade", "Upgrade…", self.on_upgrade), ("rebuild", "Rebuild world…", self.on_rebuild),
                  ("reset", "Reset environment…", self.on_reset),
                  ("folder", "Open folder", self.on_folder), ("install", INSTALL_LABEL, self.on_install),
                  ("delete", "Delete…", self.on_delete))
        self.buttons = {}
        for i, (name, text, command) in enumerate(layout):
            b = ttk.Button(grid, text=text, command=command, compound="left", style="Panel.TButton",
                           image=(self.images[name], "disabled", self.images[name + "-off"]))
            b.grid(row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
            b.bind("<Enter>", lambda e, n=name: self.hint.configure(text=HINTS[n]))
            b.bind("<Leave>", lambda e: self.hint.configure(text=""))
            self.buttons[name] = b
        for col in range(3):
            grid.columnconfigure(col, weight=1, uniform="buttons")
        if not (control.ON_WINDOWS or control.ON_MAC):
            self.buttons["install"].state(["disabled"])

        settings = ttk.LabelFrame(outer, text="Settings", padding=(10, 6))
        settings.grid(row=3, column=0, sticky="ew", pady=(12, 4))
        settings.columnconfigure(3, weight=1)
        ttk.Label(settings, text="Port").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value=str(self.c.port))
        self.port_entry = ttk.Entry(settings, textvariable=self.port_var, width=7)
        self.port_entry.grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(settings, text="World").grid(row=0, column=2, sticky="w")
        self.world_var = tk.StringVar(value=self.c.world)
        self.world_box = ttk.Combobox(settings, textvariable=self.world_var, values=self._worlds())
        self.world_box.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        for w in (self.port_entry, self.world_box):
            w.bind("<FocusOut>", lambda e: self.apply_settings(quiet=True))
            w.bind("<Return>", lambda e: self.apply_settings())
        self.world_box.bind("<<ComboboxSelected>>", lambda e: self.apply_settings())
        self.world_box.bind("<Button-1>", lambda e: self.world_box.configure(values=self._worlds()), add="+")
        self.magic_var = tk.BooleanVar(value=self.c.magic)        # the invented layer magic, for a world that is built
        self.magic_box = ttk.Checkbutton(settings, text="Magic (invented physics)", variable=self.magic_var, command=self.on_magic)
        self.magic_box.grid(row=1, column=2, columnspan=2, sticky="w", pady=(4, 0))

        bar = ttk.Frame(outer)
        bar.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.details_button = ttk.Button(bar, text="▸ Details", command=self.toggle_details, style="Toolbutton")
        self.details_button.pack(side="left")
        self.buttons["copy"] = ttk.Button(bar, text="Copy log", command=self.on_copy, compound="left",
                                          image=(self.images["copy"], "disabled", self.images["copy-off"]))
        self.buttons["copy"].pack(side="right")
        ttk.Button(bar, text="Open log", command=self.on_open_log).pack(side="right", padx=(0, 6))
        self.hint = ttk.Label(outer, style="Small.TLabel")
        self.hint.grid(row=6, column=0, sticky="w", pady=(4, 0))

        self.details = ttk.Frame(outer)
        outer.rowconfigure(5, weight=1)
        self.text = tk.Text(self.details, height=10, wrap="word", font=self.fonts["log"], relief="flat",
                            background="#f6f7f8", foreground="#222222", borderwidth=1, highlightthickness=0)
        scroll = ttk.Scrollbar(self.details, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.append_output(self.c.take_output())

    def _worlds(self):
        found = control.worlds(self.c.repo)
        default = control.MAGIC_WORLD if self.c.magic else control.DEFAULT_WORLD
        return found if default in found else [default] + found

    # ------------------------------------------------------------------ showing the state
    def render(self, st: Status):
        self.status = st
        self.light.configure(image=self.lights[LIGHTS.get(st.state, LIGHTS[STOPPED])])
        words = st.state
        if st.state == RUNNING and st.uptime:
            words += f" for {st.uptime}"
        self.state_label.configure(text=words)
        url = st.url if st.state == RUNNING and st.url else ""
        self.url_label.configure(text=url)
        if url:
            self.url_label.grid()
        else:
            self.url_label.grid_remove()
        bits = []
        if st.state == RUNNING:
            if st.world:
                bits.append(f"world {st.world}")
            if st.pid:
                bits.append(f"process {st.pid}")
            if st.version:
                bits.append(f"engine {st.version}")
        detail = st.detail or ""
        if st.state == STOPPED and not detail:
            detail = f"Not running. Start serves {self.c.world} on port {self.c.port}."
        self.detail_label.configure(text="   ".join(bits) + ("\n" if bits and detail else "") + detail)
        allowed = button_states(st, self.action)
        for name, b in self.buttons.items():
            on = allowed.get(name, True) and not (name == "install" and not (control.ON_WINDOWS or control.ON_MAC))
            b.state(["!disabled"] if on else ["disabled"])
        for w in (self.port_entry, self.world_box, self.magic_box):
            w.state(["!disabled"] if allowed["settings"] else ["disabled"])
        return allowed

    def append_output(self, text):
        if not text:
            return
        self.text.configure(state="normal")
        self.text.insert("end", text if text.endswith("\n") else text + "\n")
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > 3000:
            self.text.delete("1.0", f"{lines - 3000}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def toggle_details(self):
        self.details_open = not self.details_open
        if self.details_open:
            self.details.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
            self.details_button.configure(text="▾ Details")
            if self.root.winfo_height() < 600:
                self.root.geometry(f"{self.root.winfo_width()}x{max(self.root.winfo_height() + 200, 620)}")
        else:
            self.details.grid_remove()
            self.details_button.configure(text="▸ Details")

    # ------------------------------------------------------------------ threads
    def _poll(self):
        """Ask for the state every 2 s (every half second while something starts or stops), off the window's thread."""
        while not self._closing:
            try:
                st = self.c.status()
                self.queue.put(("status", st))
                out = self.c.take_output()
                if out:
                    self.queue.put(("output", out))
            except Exception as e:                           # keep polling whatever one round met
                self.queue.put(("output", f"(the state could not be read: {type(e).__name__}: {e})\n"))
                st = Status(ERROR)
            quick = st.state in (INSTALLING, BUILDING, STARTING, STOPPING, WORKING) or self.action is not None
            self._wake.wait(0.5 if quick else 2.0)
            self._wake.clear()

    def _drain(self):
        try:
            while True:
                kind, *rest = self.queue.get_nowait()
                if kind == "status":
                    self.render(rest[0])
                elif kind == "output":
                    self.append_output(rest[0])
                elif kind == "done":
                    self._finish(*rest)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(150, self._drain)

    def run_action(self, name, work, done=None, title=None):
        """Run `work` on a worker thread; then, on the window's thread, `done(result)`, or show the error."""
        if self.action is not None:
            return
        self.action = name
        self.render(self.status)

        def worker():
            try:
                result, error = work(), None
            except Exception as e:                           # shown to the person, whatever it is
                result, error = None, e
                if not isinstance(e, ControlError):
                    self.queue.put(("output", traceback.format_exc()))
            self.queue.put(("done", name, result, error, done, title))
            self._wake.set()
        threading.Thread(target=worker, daemon=True).start()
        self._wake.set()

    def _finish(self, name, result, error, done, title):
        from tkinter import messagebox
        self.action = None
        self.render(self.status)
        if error is not None:
            messagebox.showerror(title or f"{name} did not work", str(error) if isinstance(error, ControlError) else
                                 f"{type(error).__name__}: {error}", parent=self.root)
            return
        if done is not None:
            done(result)

    def post_output(self, text):
        self.queue.put(("output", text))

    # ------------------------------------------------------------------ settings
    def apply_settings(self, quiet=False) -> bool:
        from tkinter import messagebox
        if not button_states(self.status, self.action)["settings"]:
            return True
        try:
            self.c.set_settings(port=self.port_var.get(), world=self.world_var.get())
        except ControlError as e:
            if not quiet:
                messagebox.showerror("Settings", str(e), parent=self.root)
            self.port_var.set(str(self.c.port))
            return False
        self._wake.set()
        return True

    def on_magic(self):
        """The box "Magic (invented physics)": a world built from now on gets the invented layer magic, and the default
        world gives way to worlds/first-magic.zarr (and back)."""
        if not button_states(self.status, self.action)["settings"]:
            self.magic_var.set(self.c.magic)
            return
        self.c.set_settings(world=self.world_var.get(), magic=self.magic_var.get())
        self.world_var.set(self.c.world)
        self._wake.set()

    # ------------------------------------------------------------------ buttons
    def on_start(self):
        if self.apply_settings():
            self.run_action("Start", self.c.start)

    def on_stop(self):
        from tkinter import messagebox
        if self.c.building() and not messagebox.askokcancel("Stop the build?", self.c.build_stop_warning() + "\n\nStop it?",
                                                            icon="warning", parent=self.root):
            return
        self.run_action("Stop", self.c.stop, lambda said: self.post_output(f"Stopped: {said}\n"))

    def on_browser(self):
        if self.status.state == RUNNING:
            self.c.open_browser()

    def on_upgrade(self):
        from tkinter import messagebox
        text = ("The panel will:\n\n"
                "1. stop the world engine, if it runs;\n"
                "2. fetch the new version with git pull --ff-only;\n"
                f"3. if the version changed, delete the default world {control.DEFAULT_WORLD}, so that the next start "
                "builds it again with the new engine (one to two minutes). Other worlds are kept.\n\nUpgrade now?")
        if not messagebox.askokcancel("Upgrade the world engine?", text, parent=self.root):
            return
        if not self.details_open:
            self.toggle_details()

        def done(result):
            if result.changed:
                if messagebox.askyesno("Upgraded", result.message + "\n\nStart the world engine now?", parent=self.root):
                    self.on_start()
            else:
                messagebox.showinfo("Upgrade", result.message, parent=self.root)
        self.run_action("Upgrade", lambda: self.c.upgrade(log=self.post_output), done, title="The upgrade did not work")

    def on_rebuild(self):
        from tkinter import messagebox
        world = self.c.world
        if not messagebox.askokcancel(
                "Rebuild the world?", f"Delete the world {world} and build it again?\n\nThe engine is stopped first if it "
                f"runs. Building the preview world takes one to two minutes; the standard one 40 to 80.",
                icon="warning", parent=self.root):
            return

        def work():
            self.c.delete_world()
            self.c.start()
        self.run_action("Rebuild", work)

    def on_reset(self):
        from tkinter import messagebox
        if not messagebox.askokcancel(
                "Reset the environment?", "Delete the environment .venv (about 450 MB)?\n\nDo this when the packages are "
                "broken (after an upgrade, for example). The next start makes it again and downloads the packages "
                "(90 to 120 MB). The worlds are kept.", icon="warning", parent=self.root):
            return
        self.run_action("Reset", self.c.reset_environment,
                        lambda removed: messagebox.showinfo("Reset", "The environment .venv was deleted. Start installs it "
                                                                     "again." if removed else "There was no .venv to delete.",
                                                            parent=self.root))

    def on_delete(self):
        from tkinter import messagebox
        gone, kept = self.c.delete_plan()
        text = "This removes:\n" + ("\n".join(f"  •  {p}\n      {what}" for p, what in gone) or "  (nothing: it is all gone already)")
        text += "\n\nThis does not remove:\n" + "\n".join(f"  •  {what}: {p}" for p, what in kept)
        text += "\n\nDelete now? This cannot be undone."
        if not messagebox.askyesno("Delete the world engine from this computer?", text, icon="warning", default="no",
                                   parent=self.root):
            return
        repo = self.c.repo

        def done(removed):
            how = (f'Remove-Item -Recurse -Force "{repo}"' if control.ON_WINDOWS else f"rm -rf '{repo}'")
            messagebox.showinfo("Deleted", f"Removed {len(removed)} item(s). The panel closes now.\n\nTo remove the rest, "
                                f"delete the folder {repo} (in Explorer or the Finder, or with: {how}). docs/RUNNING.md, "
                                f"section 5, says how to remove Python and Git if nothing else uses them.", parent=self.root)
            self._quit()
        self.run_action("Delete", self.c.delete_everything, done)

    def on_folder(self):
        control.open_folder(self.c.repo)

    def on_open_log(self):
        if self.c.log_path.exists():
            control.open_folder(self.c.log_path)
        else:
            from tkinter import messagebox
            messagebox.showinfo("Log", "Nothing was started from the panel yet, so there is no log.", parent=self.root)

    def on_copy(self):
        text = self.text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.hint.configure(text=f"Copied {len(text.splitlines())} lines of output.")

    def on_install(self):
        from tkinter import messagebox
        self.run_action(INSTALL_LABEL, self.c.install_shortcut,
                        lambda made: messagebox.showinfo(INSTALL_LABEL, "Made:\n" + "\n".join(map(str, made)) + (
                            "\n\nOpen World Engine from there from now on." if made else ""), parent=self.root))

    # ------------------------------------------------------------------ closing
    def on_close(self):
        from tkinter import messagebox
        if self.action is not None:
            messagebox.showinfo(control.APP_NAME, f"Wait until “{self.action}” has finished.", parent=self.root)
            return
        st = self.status
        if st.state in (RUNNING, INSTALLING, BUILDING, STARTING) and st.can_stop:
            choice = ask_choice(self.root, "Leave the world engine running?",
                                "The world engine is " + ("running" if st.state == RUNNING else "starting") + ". It can "
                                "keep running after the panel closes; open the panel again to stop it.",
                                ("Keep running", "Stop and quit", "Cancel"))
            if choice == "Stop and quit":
                self.run_action("Stop", self.c.stop, lambda said: self._quit())
                return
            if choice != "Keep running":
                return
        self._quit()

    def _quit(self):
        self._closing = True
        self._wake.set()
        self.root.destroy()


def ask_choice(root, title, message, choices, auto=None):
    """A small dialog with buttons named for what they do; returns the text of the one pressed (None if closed).
    `auto` presses a button by itself after a moment (the self-test)."""
    import tkinter as tk
    from tkinter import ttk
    win = tk.Toplevel(root)
    win.title(title)
    win.transient(root)
    win.resizable(False, False)
    answer = [None]
    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=title, style="State.TLabel").pack(anchor="w")
    ttk.Label(frame, text=message, wraplength=360, justify="left").pack(anchor="w", pady=(6, 14))
    row = ttk.Frame(frame)
    row.pack(anchor="e")
    for i, text in enumerate(choices):
        def press(t=text):
            answer[0] = t
            win.destroy()
        b = ttk.Button(row, text=text, command=press, default="active" if i == 0 else "normal")
        b.pack(side="left", padx=(6, 0))
        if i == 0:
            b.focus_set()
            win.bind("<Return>", lambda e, p=press: p())
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")
    if auto is not None:
        win.after(200, lambda: (answer.__setitem__(0, auto), win.destroy()))
    try:
        win.grab_set()
    except tk.TclError:
        pass
    root.wait_window(win)
    return answer[0]


# ---------------------------------------------------------------------------------------------- the self-test
SELF_TEST_STATES = (
    Status(STOPPED),
    Status(INSTALLING, "Making the environment .venv and installing the packages", owned=True, can_stop=True),
    Status(BUILDING, "Building the world worlds/first.zarr: one to two minutes", owned=True, can_stop=True),
    Status(STARTING, "Starting the server", owned=True, can_stop=True),
    Status(RUNNING, url="http://127.0.0.1:8765/", world="worlds/first.zarr", pid=4242, version="0.1.0",
           started_at=time.time() - 754, owned=True, can_stop=True),
    Status(RUNNING, "started without a run file", url="http://127.0.0.1:8765/", world="seed 7"),
    Status(STOPPING, "Stopping the world engine", can_stop=True),
    Status(WORKING, "Upgrading: git pull --ff-only"),
    Status(ERROR, "refused: cannot listen on 127.0.0.1 port 8765 (the launcher ended with exit code 2)"),
)


def self_test(root, panel, out=None) -> int:
    """Show every state and check that each button is enabled exactly when control.button_states says; open and close
    the details and the closing dialog; then close. Starts no server and changes no file."""
    problems = []
    for st in SELF_TEST_STATES:
        allowed = panel.render(st)
        root.update()
        for name, b in panel.buttons.items():
            shown = not b.instate(["disabled"])
            want = allowed.get(name, True) and not (name == "install" and not (control.ON_WINDOWS or control.ON_MAC))
            if shown != want:
                problems.append(f"{st.state}: the button {name} is {'enabled' if shown else 'disabled'}")
        if panel.state_label.cget("text").split(" for ")[0] != st.state:
            problems.append(f"{st.state}: the window says {panel.state_label.cget('text')!r}")
    panel.toggle_details()
    panel.append_output("== Serving worlds/first.zarr\nviewer at http://127.0.0.1:8765/  (stop with Ctrl+C)\n")
    root.update()
    if "viewer at" not in panel.text.get("1.0", "end"):
        problems.append("the details do not show the output")
    panel.toggle_details()
    choice = ask_choice(root, "Leave the world engine running?", "(self-test)", ("Keep running", "Stop and quit", "Cancel"),
                        auto="Keep running")
    if choice != "Keep running":
        problems.append(f"the closing dialog answered {choice!r}")
    panel.render(Status(STOPPED))
    said = ("self-test passed: " + f"{len(SELF_TEST_STATES)} states shown, Tk {root.tk.call('info', 'patchlevel')}, "
            f"theme {panel.ttk.Style(root).theme_use()}") if not problems else "self-test failed:\n  " + "\n  ".join(problems)
    print(said, flush=True)
    if out:
        Path(out).write_text(said + "\n", encoding="utf-8")
    root.after(1000, root.destroy)
    root.mainloop()
    return 0 if not problems else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="world_engine_panel", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install-shortcut", "--install-app", dest="install", action="store_true",
                    help="make the shortcuts (Windows) or the app (macOS), then end")
    ap.add_argument("--dest", default=None, help="with --install-shortcut: the folder to make it in")
    ap.add_argument("--self-test", action="store_true", help="show every state, close, exit 0 if all went well")
    ap.add_argument("--self-test-out", default=None, help="with --self-test: also write the result to this file")
    args = ap.parse_args(argv)

    if args.install:
        try:
            made = control.Controller().install_shortcut(args.dest)
        except ControlError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        for p in made:
            print(f"made {p}")
        return 0

    try:
        import tkinter as tk
    except ImportError:
        msg = TKINTER_MISSING.format(exe=sys.executable, v="%d.%d" % sys.version_info[:2])
        print(msg, file=sys.stderr)
        if args.self_test_out:
            Path(args.self_test_out).write_text(msg, encoding="utf-8")
        return 3
    set_windows_dpi_awareness()
    try:
        root = tk.Tk(className="WorldEngine")
    except tk.TclError as e:
        print(f"The window could not be opened: {e}", file=sys.stderr)
        return 3
    panel = Panel(root, control.Controller(), poll=not args.self_test)
    if args.self_test:
        return self_test(root, panel, args.self_test_out)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
