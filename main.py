import json
import sys
import threading
import time
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode, Listener
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

from src.read_input import read_user_input
from src.stats import get_all_time_clicks, insert_all_time_clicks

# ── Appearance ────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULTS = {
    "time_delay": 1.0,
    "start_keybind": "z",
    "stop_keybind": "x",
    "click_button": "space",
}

_KEY_MAP = {
    "space": Key.space,
    "enter": Key.enter,
    "tab": Key.tab,
    "esc": Key.esc,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "backspace": Key.backspace,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
}

_mouse = MouseController()
_keyboard = KeyboardController()


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            data = json.load(f)
        for key, default_value in DEFAULTS.items():
            data.setdefault(key, default_value)
        return data
    return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    with CONFIG_PATH.open("w") as f:
        json.dump(cfg, f, indent=4)


def resolve_button(s: str):
    if s == "left":
        return Button.left, "mouse"
    if s == "right":
        return Button.right, "mouse"
    if s in _KEY_MAP:
        return _KEY_MAP[s], "keyboard"
    if len(s) == 1:
        return KeyCode(char=s), "keyboard"
    # Unrecognised multi-char string (e.g. "unknown" from read_key on Wayland)
    # — fall back to the default so the thread doesn't crash.
    return _KEY_MAP[DEFAULTS["click_button"]], "keyboard"


# ── Clicker Thread ────────────────────────────────────────────────────────────
class ClickerThread(threading.Thread):
    def __init__(self, cfg: dict, on_state_change=None):
        super().__init__(daemon=True)
        self._clicking = False
        self._alive = True
        self.click_count = 0
        self.on_state_change = on_state_change
        self._listener: Listener | None = None
        self.apply_config(cfg)

    def apply_config(self, cfg: dict):
        self.delay = float(cfg.get("time_delay", DEFAULTS["time_delay"]))
        self.button, self.input_type = resolve_button(
            cfg.get("click_button", DEFAULTS["click_button"])
        )
        sc = cfg.get("start_keybind", DEFAULTS["start_keybind"])
        ec = cfg.get("stop_keybind", DEFAULTS["stop_keybind"])
        self._start_key = KeyCode(char=sc) if len(sc) == 1 else None
        self._stop_key = KeyCode(char=ec) if len(ec) == 1 else None

    def _on_press(self, key):
        if key == self._start_key:
            self.start_clicking()
        elif key == self._stop_key:
            self.stop_clicking()

    @property
    def clicking(self):
        return self._clicking

    def start_clicking(self):
        self._clicking = True
        if self.on_state_change:
            self.on_state_change(True)

    def stop_clicking(self):
        self._clicking = False
        insert_all_time_clicks(self.click_count)
        if self.on_state_change:
            self.on_state_change(False)

    def toggle(self):
        self.stop_clicking() if self._clicking else self.start_clicking()

    def shutdown(self):
        self._clicking = False
        self._alive = False
        if self._listener:
            self._listener.stop()

    def run(self):
        self._listener = Listener(on_press=self._on_press)
        self._listener.start()
        while self._alive:
            if self._clicking:
                if self.input_type == "mouse":
                    _mouse.click(self.button)
                else:
                    _keyboard.tap(self.button)
                self.click_count += 1
                time.sleep(max(0.01, self.delay))
            else:
                time.sleep(0.05)
        self._listener.stop()


# ── Main Window ───────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bobby Clicker 2")
        self.geometry("460x580")
        self.resizable(False, False)

        # App icon (taskbar, title bar, Alt-Tab, etc.)
        _icon_path = Path(__file__).parent / "src" / "assets" / "bobkata.ico"
        if _icon_path.exists():
            if sys.platform == "win32":
                self.iconbitmap(str(_icon_path))
            else:
                _icon_img = ImageTk.PhotoImage(Image.open(_icon_path))
                self.iconphoto(True, _icon_img)
                self._icon_img = _icon_img  # keep a reference so GC doesn't collect it

        self._cfg = load_config()
        self._clicker = ClickerThread(self._cfg, on_state_change=self._on_clicker_state)
        self._clicker.start()
        self._capturing = False  # guard against concurrent capture threads

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Title bar
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=24, pady=(24, 0))

        ctk.CTkLabel(
            title_frame,
            text="Bobby Clicker 2",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")

        self._status_dot = ctk.CTkLabel(
            title_frame,
            text="●  Idle",
            font=ctk.CTkFont(size=13),
            text_color="#6b7280",
        )
        self._status_dot.pack(side="right", pady=(4, 0))

        ctk.CTkFrame(self, height=2, fg_color="#2d2d2d").pack(
            fill="x", padx=24, pady=12
        )

        # Settings card
        card = ctk.CTkFrame(self, corner_radius=16)
        card.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(
            card,
            text="Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9ca3af",
        ).pack(anchor="w", padx=20, pady=(16, 8))

        # Delay
        self._delay_var = ctk.StringVar(value=str(self._cfg["time_delay"]))
        self._add_row(card, "Click Delay (s)", self._delay_var, "e.g. 0.5")

        # Click button
        self._button_var = ctk.StringVar(value=self._cfg["click_button"])
        self._add_row(
            card,
            "Click Button",
            self._button_var,
            "space / left / right / a",
            capture=True,
        )

        # Start keybind
        self._start_var = ctk.StringVar(value=self._cfg["start_keybind"])
        self._add_row(
            card,
            "Start Key",
            self._start_var,
            "single key, e.g. z",
            capture=True,
        )

        # Stop keybind
        self._stop_var = ctk.StringVar(value=self._cfg["stop_keybind"])
        self._add_row(
            card,
            "Stop Key",
            self._stop_var,
            "single key, e.g. x",
            last=True,
            capture=True,
        )

        # Save button
        self._save_btn = ctk.CTkButton(
            self,
            text="Save Settings",
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._save_settings,
        )
        self._save_btn.pack(fill="x", padx=24, pady=(0, 16))

        # Toggle button
        self._toggle_btn = ctk.CTkButton(
            self,
            text="▶  Start Clicking",
            height=56,
            corner_radius=14,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._toggle,
        )
        self._toggle_btn.pack(fill="x", padx=24, pady=(0, 16))

        # Keybind hint
        self._hint = ctk.CTkLabel(
            self,
            text=self._hint_text(),
            font=ctk.CTkFont(size=12),
            text_color="#6b7280",
        )
        self._hint.pack()

        # Click counter
        self._counter_label = ctk.CTkLabel(
            self,
            text="Clicks this session:  0",
            font=ctk.CTkFont(size=12),
            text_color="#6b7280",
        )
        self._counter_label.pack(pady=(8, 0))

        self._all_timecounter_label = ctk.CTkLabel(
            self,
            text="All time clicks:  0",
            font=ctk.CTkFont(size=12),
            text_color="#6b7280",
        )
        self._all_timecounter_label.pack(pady=(8, 0))

        self._start_counter_update()

    def _add_row(
        self,
        parent,
        label: str,
        var: ctk.StringVar,
        placeholder: str,
        last=False,
        capture=False,
    ):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 0 if last else 4))
        ctk.CTkLabel(
            row, text=label, width=150, anchor="w", font=ctk.CTkFont(size=13)
        ).pack(side="left")
        entry = ctk.CTkEntry(
            row,
            textvariable=var,
            placeholder_text=placeholder,
            height=34,
            corner_radius=8,
        )
        entry.pack(side="left", fill="x", expand=True, pady=6)
        if capture:
            entry.bind("<Key>", lambda e: "break")  # prevent direct typing
            entry.bind(
                "<ButtonRelease-1>",
                lambda e, v=var, en=entry: self._start_capture(v, en),
            )

    def _start_capture(self, var: ctk.StringVar, entry):
        """Run read_user_input() in a thread; populate *var* with the result."""
        if self._capturing:
            return  # ignore double-clicks while a capture is already running
        self._capturing = True

        original = var.get()
        var.set("")
        entry.configure(placeholder_text="Press a key…")
        entry.configure(state="disabled")

        def _capture():
            result = read_user_input()  # handles its own timing / button-release wait

            def _apply():
                var.set(result)
                entry.configure(placeholder_text=original or result)
                entry.configure(state="normal")
                # Delay clearing the flag so the ButtonRelease-1 from the
                # captured left-click doesn't immediately re-trigger capture.
                self.after(400, lambda: setattr(self, "_capturing", False))

            self.after(0, _apply)

        threading.Thread(target=_capture, daemon=True).start()

    # ── Logic ─────────────────────────────────────────────────────────────────
    def _hint_text(self) -> str:
        return (
            f"Press  [{self._cfg['start_keybind'].upper()}]  to start  ·  "
            f"[{self._cfg['stop_keybind'].upper()}]  to stop"
        )

    def _save_settings(self):
        try:
            delay = float(self._delay_var.get())
        except ValueError:
            self._flash_error("Delay must be a number")
            return

        self._cfg.update(
            {
                "time_delay": delay,
                "click_button": self._button_var.get().strip().lower(),
                "start_keybind": self._start_var.get().strip().lower(),
                "stop_keybind": self._stop_var.get().strip().lower(),
            }
        )
        save_config(self._cfg)
        self._clicker.apply_config(self._cfg)
        self._hint.configure(text=self._hint_text())
        self.focus_set()  # remove cursor from any focused entry field

        # Brief visual confirmation
        self._save_btn.configure(
            text="✓  Saved", fg_color="#16a34a", hover_color="#15803d"
        )
        self.after(
            1500,
            lambda: self._save_btn.configure(
                text="Save Settings", fg_color="#374151", hover_color="#4b5563"
            ),
        )

    def _flash_error(self, msg: str):
        self._save_btn.configure(
            text=f"⚠  {msg}", fg_color="#dc2626", hover_color="#dc2626"
        )
        self.after(
            2000,
            lambda: self._save_btn.configure(
                text="Save Settings", fg_color="#374151", hover_color="#4b5563"
            ),
        )

    def _toggle(self):
        self._clicker.toggle()

    def _on_clicker_state(self, running: bool):
        # Called from background thread — schedule on main thread
        self.after(0, self._update_ui_state, running)

    def _update_ui_state(self, running: bool):
        if running:
            self._toggle_btn.configure(
                text="■  Stop Clicking",
                fg_color="#dc2626",
                hover_color="#b91c1c",
            )
            self._status_dot.configure(text="●  Running", text_color="#22c55e")
        else:
            self._toggle_btn.configure(
                text="▶  Start Clicking",
                fg_color="#2563eb",
                hover_color="#1d4ed8",
            )
            self._status_dot.configure(text="●  Idle", text_color="#6b7280")

    # ── Counter ───────────────────────────────────────────────────────────────
    def _start_counter_update(self):
        self.after(200, self._refresh_counter)

    def _refresh_counter(self):
        if self.winfo_exists():
            self._counter_label.configure(
                text=f"Clicks this session:  {self._clicker.click_count:,}"
            )
            self._all_timecounter_label.configure(
                text=f"All time clicks:  {get_all_time_clicks()}"
            )
            self.after(200, self._refresh_counter)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _on_close(self):
        self._clicker.shutdown()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
