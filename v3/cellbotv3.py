# cellbotv3.py
# Kombinerar CellBot v2 (cyklisk sekvens med tabs/boost) med en "idle"-klickare
# som beter sig som CellBot v1 mellan cyklerna.
#
# När den INTE kör sin cykel (loop every X s) så klickar den enligt bakgrunds-
# klickarens inställningar: frekvens (Hz), läge (current eller fixed X/Y) och
# med koordinat-picking. Nödstopp: flytta musen till övre vänstra hörnet (<5 px).
#
# Hotkey: F6 start/stop (samma som tidigare). Fönster: Tkinter.
#
# deps:
#   pip install pynput pyautogui pillow
#
# OBS: På Windows används WinMM timeBeginPeriod(1) + SendInput för exakt klick.

import time
import threading
import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes

import pyautogui
from pynput import keyboard, mouse

# PyAutoGUI snabba inställningar (för v2-delens klick/move)
pyautogui.PAUSE = 0
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0

# -------------------- WinAPI high-res timer --------------------
try:
    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod(1)
except Exception:
    winmm = None

# -------------------- WinAPI SendInput för v1-aktig klick --------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ('dx',          wintypes.LONG),
        ('dy',          wintypes.LONG),
        ('mouseData',   wintypes.DWORD),
        ('dwFlags',     wintypes.DWORD),
        ('time',        wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p),
    )

class INPUT(ctypes.Structure):
    _fields_ = (( 'type', wintypes.DWORD ), ('mi', MOUSEINPUT))

class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))

def send_left_click():
    events = (INPUT * 2)()
    events[0].type, events[0].mi = INPUT_MOUSE, MOUSEINPUT(0,0,0,MOUSEEVENTF_LEFTDOWN,0,None)
    events[1].type, events[1].mi = INPUT_MOUSE, MOUSEINPUT(0,0,0,MOUSEEVENTF_LEFTUP,  0,None)
    user32.SendInput(2, ctypes.byref(events), ctypes.sizeof(INPUT))

def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))

# -------------------- defaults (från v2 + v1) --------------------
DEFAULT_LOOP_S = 60.0
DEFAULT_BOOST_S = 965.0
DEFAULT_CLICK_DELAY = 0.03
DEFAULT_IDLE_HZ = 50.0
EMERGENCY_MARGIN = 5  # px (övre vänstra hörnet)

DEFAULT_MENU_TOGGLE = (35, 427)
DEFAULT_TAB1_POS = (47, 40)
DEFAULT_TAB2_POS = (139, 41)
DEFAULT_TAB3_POS = (223, 36)
DEFAULT_BOOST_POINT = (654, 1028)

CTX1_TAB1_POINTS = []
CTX1_TAB2_POINTS = [
    (480, 246), (480, 341), (480, 442),
    (480, 542), (480, 642), (480, 742),
]
CTX1_TAB3_POINTS = [
    (480, 192), (480, 290), (480, 390),
    (480, 490), (480, 590), (480, 690),
]

CTX2_TAB1_POINTS = [
    (477, 184), (478, 284), (468, 384), (467, 486), (481, 581),
    (482, 678), (479, 776), (470, 880), (467, 977), (465, 1051),
]
CTX2_TAB2_POINTS = list(CTX2_TAB1_POINTS)
CTX2_TAB3_POINTS = list(CTX2_TAB1_POINTS)

CONTEXTS = ["Context 1", "Context 2", "Context 3", "Context 4"]

# -------------------- PyAutoGUI helpers (v2-del) --------------------

def click_xy(x, y, settle=0.05):
    pyautogui.moveTo(int(x), int(y), duration=0)
    pyautogui.click()
    if settle and settle > 0:
        time.sleep(settle)

# -------------------- App --------------------
class CellBotV3:
    def __init__(self, root):
        self.root = root
        self.root.title("CellBot v3")
        self.root.minsize(1180, 700)

        # run state
        self.running = False
        self.bot_thread = None

        # v2 fasta pos
        self.menu_toggle = DEFAULT_MENU_TOGGLE
        self.tab1_pos    = DEFAULT_TAB1_POS
        self.tab2_pos    = DEFAULT_TAB2_POS
        self.tab3_pos    = DEFAULT_TAB3_POS
        self.boost_point = DEFAULT_BOOST_POINT

        # v2 per-kontext punkter
        self.points = {
            "Context 1": {"t1": list(CTX1_TAB1_POINTS), "t2": list(CTX1_TAB2_POINTS), "t3": list(CTX1_TAB3_POINTS)},
            "Context 2": {"t1": list(CTX2_TAB1_POINTS), "t2": list(CTX2_TAB2_POINTS), "t3": list(CTX2_TAB3_POINTS)},
            "Context 3": {"t1": [], "t2": [], "t3": []},
            "Context 4": {"t1": [], "t2": [], "t3": []},
        }

        # aktiv kontext
        self.active_context = tk.StringVar(value="Context 1")

        # v2 config
        self.loop_interval_var   = tk.StringVar(value=f"{DEFAULT_LOOP_S}")
        self.boost_interval_var  = tk.StringVar(value=f"{DEFAULT_BOOST_S}")
        self.use_click_delay_var = tk.BooleanVar(value=True)
        self.click_delay_var     = tk.StringVar(value=f"{DEFAULT_CLICK_DELAY}")
        self.boost_on_start_var  = tk.BooleanVar(value=True)

        self.use_tab1_var = tk.BooleanVar(value=False)
        self.use_tab2_var = tk.BooleanVar(value=True)
        self.use_tab3_var = tk.BooleanVar(value=True)

        # v1-lik bakgrundsklickare (idle)
        self.idle_enable_var = tk.BooleanVar(value=True)
        self.idle_hz_var     = tk.StringVar(value=f"{DEFAULT_IDLE_HZ}")
        self.idle_mode_var   = tk.StringVar(value="current")  # current|fixed
        self.idle_x_var      = tk.StringVar(value="0")
        self.idle_y_var      = tk.StringVar(value="0")

        self.status_var = tk.StringVar(value="status: idle  •  press F6 to start/stop")

        # hotkey
        self.kb_listener = keyboard.Listener(on_press=self._on_key)
        self.kb_listener.daemon = True
        self.kb_listener.start()

        # ui
        self._build_ui()
        self._center()

    # ---------- UI ----------
    def _build_ui(self):
        wrap = ttk.Frame(self.root, padding=12)
        wrap.pack(fill="both", expand=True)

        header = ttk.Frame(wrap)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,10))
        ttk.Label(header, text="CellBot v3", font=("Segoe UI", 14)).pack(side="left")
        ttk.Label(header, textvariable=self.status_var, foreground="#555").pack(side="right")

        # vänsterkolumn: v2-konfig + toggles
        left = ttk.Frame(wrap)
        left.grid(row=1, column=0, sticky="nsew", padx=(0,10))

        lf_tabs = ttk.Labelframe(left, text="Menu & Tabs")
        lf_tabs.pack(fill="x", pady=(0,10))

        # menu toggle
        mrow = ttk.Frame(lf_tabs); mrow.pack(fill="x", pady=6)
        ttk.Label(mrow, text="Menu toggle").pack(side="left")
        self.menu_label = ttk.Label(mrow, text=f"{self.menu_toggle[0]},{self.menu_toggle[1]}", foreground="#222")
        self.menu_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Menu toggle", command=self._pick_menu_toggle).pack(fill="x")

        # Tab 1
        r1 = ttk.Frame(lf_tabs); r1.pack(fill="x", pady=6)
        ttk.Label(r1, text="Tab 1").pack(side="left")
        self.tab1_label = ttk.Label(r1, text=f"{self.tab1_pos[0]},{self.tab1_pos[1]}", foreground="#222")
        self.tab1_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Tab 1", command=lambda: self._pick_tab("t1")).pack(fill="x")

        # Tab 2
        r2 = ttk.Frame(lf_tabs); r2.pack(fill="x", pady=6)
        ttk.Label(r2, text="Tab 2").pack(side="left")
        self.tab2_label = ttk.Label(r2, text=f"{self.tab2_pos[0]},{self.tab2_pos[1]}", foreground="#222")
        self.tab2_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Tab 2", command=lambda: self._pick_tab("t2")).pack(fill="x")

        # Tab 3
        r3 = ttk.Frame(lf_tabs); r3.pack(fill="x", pady=6)
        ttk.Label(r3, text="Tab 3").pack(side="left")
        self.tab3_label = ttk.Label(r3, text=f"{self.tab3_pos[0]},{self.tab3_pos[1]}", foreground="#222")
        self.tab3_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Tab 3", command=lambda: self._pick_tab("t3")).pack(fill="x")

        # timing
        lf_cfg = ttk.Labelframe(left, text="Timing")
        lf_cfg.pack(fill="x", pady=(0,10))
        row_cfg1 = ttk.Frame(lf_cfg); row_cfg1.pack(fill="x", pady=6)
        ttk.Label(row_cfg1, text="Loop every (s)").pack(side="left")
        ttk.Entry(row_cfg1, width=8, textvariable=self.loop_interval_var).pack(side="left", padx=(6,16))
        ttk.Label(row_cfg1, text="Boost every (s)").pack(side="left")
        ttk.Entry(row_cfg1, width=8, textvariable=self.boost_interval_var).pack(side="left", padx=(6,16))
        row_cfg2 = ttk.Frame(lf_cfg); row_cfg2.pack(fill="x", pady=6)
        ttk.Checkbutton(row_cfg2, text="Use click delay", variable=self.use_click_delay_var,
                        command=self._update_click_delay_state).pack(side="left")
        ttk.Label(row_cfg2, text="Click delay (s)").pack(side="left", padx=(12,6))
        self.click_delay_entry = ttk.Entry(row_cfg2, width=8, textvariable=self.click_delay_var)
        self.click_delay_entry.pack(side="left")

        # toggles
        lf_tog = ttk.Labelframe(left, text="Behavior")
        lf_tog.pack(fill="x", pady=(0,10))
        ttk.Checkbutton(lf_tog, text="Use Tab 1", variable=self.use_tab1_var).pack(anchor="w", padx=6, pady=(6,0))
        ttk.Checkbutton(lf_tog, text="Use Tab 2", variable=self.use_tab2_var).pack(anchor="w", padx=6, pady=(2,0))
        ttk.Checkbutton(lf_tog, text="Use Tab 3", variable=self.use_tab3_var).pack(anchor="w", padx=6, pady=(2,6))
        ttk.Checkbutton(lf_tog, text="Boost on start", variable=self.boost_on_start_var).pack(anchor="w", padx=6, pady=(0,8))
        ttk.Label(left, text="Hotkey: F6 start/stop • F6 again to stop", foreground="#777").pack(pady=(0,0))

        # Notebook med kontexter och listor
        nb = ttk.Notebook(wrap)
        nb.grid(row=1, column=1, columnspan=2, sticky="nsew")
        self.notebook = nb
        nb.bind("<<NotebookTabChanged>>", self._on_context_changed)

        self.ctx_widgets = {}
        for ctx in CONTEXTS:
            frame = ttk.Frame(nb)
            nb.add(frame, text=ctx)
            colwrap = ttk.Frame(frame, padding=8)
            colwrap.pack(fill="both", expand=True)

            for i, key in enumerate(("t1", "t2", "t3")):
                box = ttk.Labelframe(colwrap, text=f"{ctx} • Tab {i+1} points")
                box.grid(row=0, column=i, sticky="nsew", padx=6)
                lb = tk.Listbox(box, height=18)
                lb.pack(fill="both", expand=True, padx=8, pady=8)
                row = ttk.Frame(box); row.pack(fill="x", padx=8, pady=(0,8))
                ttk.Button(row, text="Add (pick)",
                           command=lambda c=ctx, k=key, l=lb: self._pick_point_ctx(c, k, l)).pack(side="left")
                ttk.Button(row, text="Remove",
                           command=lambda c=ctx, k=key, l=lb: self._remove_selected_ctx(c, k, l)).pack(side="right")
                self.ctx_widgets.setdefault(ctx, {})[key] = lb

            self._refresh_ctx_lists(ctx)

        # Boost-pick
        boost_box = ttk.Labelframe(wrap, text="Boost")
        boost_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10,0))
        self.boost_label = ttk.Label(boost_box, text=f"{self.boost_point[0]},{self.boost_point[1]}", foreground="#222")
        self.boost_label.pack(side="right", padx=8, pady=6)
        ttk.Button(boost_box, text="Pick Boost point", command=self._pick_boost).pack(side="left", padx=8, pady=6)

        # Högerkolumn: Idle-klickare (v1-style)
        right = ttk.Labelframe(wrap, text="Idle clicker (v1-style between cycles)")
        right.grid(row=1, column=3, sticky="nsew", padx=(10,0))

        ttk.Checkbutton(right, text="Enable idle clicker", variable=self.idle_enable_var).pack(anchor="w", padx=8, pady=(8,4))

        row_idle1 = ttk.Frame(right); row_idle1.pack(fill="x", padx=8, pady=4)
        ttk.Label(row_idle1, text="Frequency (Hz)").pack(side="left")
        ttk.Entry(row_idle1, width=8, textvariable=self.idle_hz_var).pack(side="left", padx=(6,0))

        row_idle2 = ttk.Frame(right); row_idle2.pack(fill="x", padx=8, pady=4)
        ttk.Label(row_idle2, text="Click mode").pack(side="left")
        idle_mode = ttk.Combobox(row_idle2, state="readonly", values=["current", "fixed"],
                                 textvariable=self.idle_mode_var, width=10)
        idle_mode.pack(side="left", padx=(6,0))
        idle_mode.bind("<<ComboboxSelected>>", lambda e: self._update_idle_mode_state())

        pos_frame = ttk.Frame(right); pos_frame.pack(fill="x", padx=8, pady=4)
        ttk.Label(pos_frame, text="X:").pack(side="left")
        self.idle_x_entry = ttk.Entry(pos_frame, width=8, textvariable=self.idle_x_var)
        self.idle_x_entry.pack(side="left", padx=(4,12))
        ttk.Label(pos_frame, text="Y:").pack(side="left")
        self.idle_y_entry = ttk.Entry(pos_frame, width=8, textvariable=self.idle_y_var)
        self.idle_y_entry.pack(side="left", padx=(4,12))
        ttk.Button(pos_frame, text="Pick on screen", command=self._pick_idle_pos).pack(side="left")

        ttk.Label(right, text="Nödstopp: flytta musen till översta vänstra hörnet (<5 px)", foreground="#777").pack(anchor="w", padx=8, pady=(6,8))

        # Grid weights
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_columnconfigure(2, weight=1)
        wrap.grid_columnconfigure(3, weight=0)

        self._update_click_delay_state()
        self._update_idle_mode_state()

    def _center(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (sw - w)//2, (sh - h)//3
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _update_click_delay_state(self):
        if self.use_click_delay_var.get():
            self.click_delay_entry.state(["!disabled"])
        else:
            self.click_delay_entry.state(["disabled"])

    def _update_idle_mode_state(self):
        fixed = self.idle_mode_var.get() == "fixed"
        state = ("!disabled" if fixed else "disabled")
        if fixed:
            self.idle_x_entry.state(["!disabled"])
            self.idle_y_entry.state(["!disabled"])
        else:
            self.idle_x_entry.state(["disabled"])
            self.idle_y_entry.state(["disabled"])

    # ---------- Context utils ----------
    def _current_context(self):
        idx = self.notebook.index(self.notebook.select())
        return CONTEXTS[idx]

    def _on_context_changed(self, _e):
        self.active_context.set(self._current_context())

    def _refresh_ctx_lists(self, ctx):
        for key in ("t1", "t2", "t3"):
            lb = self.ctx_widgets[ctx][key]
            lb.delete(0, "end")
            for (x, y) in self.points[ctx][key]:
                lb.insert("end", f"{x},{y}")

    # ---------- Picking ----------
    def _pick_menu_toggle(self):
        self.status_var.set("pick: click Menu toggle…")
        self._pick_one(self._set_menu_toggle)

    def _pick_tab(self, which):
        label = {"t1": "Tab 1", "t2": "Tab 2", "t3": "Tab 3"}[which]
        self.status_var.set(f"pick: click {label}…")
        self._pick_one(lambda pt: self._set_tab_pos(which, pt))

    def _pick_boost(self):
        self.status_var.set("pick: click Boost point…")
        self._pick_one(self._set_boost)

    def _pick_point_ctx(self, ctx, kind, listbox):
        self.status_var.set(f"pick: click a point for {ctx} • {kind.upper()}…")
        def on_pick(pt):
            self.points[ctx][kind].append(pt)
            listbox.insert("end", f"{pt[0]},{pt[1]}")
            self.status_var.set("status: idle  •  press F6 to start/stop")
        self._pick_one(on_pick)

    def _remove_selected_ctx(self, ctx, kind, listbox):
        sel = list(listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            listbox.delete(i)
            del self.points[ctx][kind][i]

    def _pick_idle_pos(self):
        self.status_var.set("pick: click idle fixed point…")
        def on_pick(pt):
            self.idle_x_var.set(str(pt[0]))
            self.idle_y_var.set(str(pt[1]))
            self.status_var.set("status: idle  •  press F6 to start/stop")
        self._pick_one(on_pick)

    def _pick_one(self, on_pick):
        def on_click(x, y, button, pressed):
            if pressed:
                on_pick((int(x), int(y)))
                listener.stop()
                return False
            return True
        listener = mouse.Listener(on_click=on_click)
        listener.daemon = True
        listener.start()

    # setters
    def _set_menu_toggle(self, pt):
        self.menu_toggle = pt
        self.menu_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

    def _set_tab_pos(self, which, pt):
        if which == "t1":
            self.tab1_pos = pt
            self.tab1_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")
        elif which == "t2":
            self.tab2_pos = pt
            self.tab2_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")
        else:
            self.tab3_pos = pt
            self.tab3_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

    def _set_boost(self, pt):
        self.boost_point = pt
        self.boost_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

    # ---------- Hotkey ----------
    def _on_key(self, key):
        if key == keyboard.Key.f6:
            self.root.after(0, self._toggle)

    def _toggle(self):
        if self.running:
            self.running = False
            self.status_var.set("status: idle  •  press F6 to start/stop")
        else:
            self.running = True
            self.status_var.set("status: running  •  press F6 to stop")
            self.bot_thread = threading.Thread(target=self._run, daemon=True)
            self.bot_thread.start()

    # ---------- Main loop: v2-cykel + v1-idle ----------
    def _run(self):
        try:
            # v2-parametrar
            try:
                loop_iv = max(0.2, float(self.loop_interval_var.get()))
            except:
                loop_iv = DEFAULT_LOOP_S
            try:
                boost_iv = max(5.0, float(self.boost_interval_var.get()))
            except:
                boost_iv = DEFAULT_BOOST_S

            if self.use_click_delay_var.get():
                try:
                    click_delay = float(self.click_delay_var.get())
                    if click_delay < 0.0:
                        click_delay = 0.0
                except:
                    click_delay = DEFAULT_CLICK_DELAY
            else:
                click_delay = 0.0

            # idle-parametrar
            idle_enabled = self.idle_enable_var.get()
            try:
                idle_hz = float(self.idle_hz_var.get())
                idle_interval = 1.0/idle_hz if idle_hz > 0 else 0.02
            except:
                idle_interval = 1.0/DEFAULT_IDLE_HZ
            idle_mode = self.idle_mode_var.get()
            if idle_mode == "fixed":
                try:
                    idle_x = int(float(self.idle_x_var.get()))
                    idle_y = int(float(self.idle_y_var.get()))
                except:
                    idle_x, idle_y = 0, 0

            now = time.perf_counter()
            next_cycle = now
            next_boost = now if self.boost_on_start_var.get() else now + boost_iv
            next_idle_click = now

            while self.running:
                # nödstopp
                cx, cy = get_cursor_pos()
                if cx < EMERGENCY_MARGIN and cy < EMERGENCY_MARGIN:
                    break

                now = time.perf_counter()
                ctx = self._current_context()

                # 1) Kör cykeln när det är dags
                if now >= next_cycle:
                    pts_t1 = list(self.points[ctx]["t1"])  # kopior för trådtrygghet
                    pts_t2 = list(self.points[ctx]["t2"]) 
                    pts_t3 = list(self.points[ctx]["t3"]) 

                    # Menu Toggle
                    click_xy(*self.menu_toggle, settle=click_delay)

                    # Tab 1
                    if self.use_tab1_var.get():
                        click_xy(*self.tab1_pos, settle=click_delay)
                        for (x, y) in pts_t1:
                            click_xy(x, y, settle=click_delay)

                    # Tab 2
                    if self.use_tab2_var.get():
                        click_xy(*self.tab2_pos, settle=click_delay)
                        for (x, y) in pts_t2:
                            click_xy(x, y, settle=click_delay)

                    # Tab 3
                    if self.use_tab3_var.get():
                        click_xy(*self.tab3_pos, settle=click_delay)
                        for (x, y) in pts_t3:
                            click_xy(x, y, settle=click_delay)

                    # Boost sist om due
                    if now >= next_boost and self.boost_point:
                        click_xy(*self.boost_point, settle=click_delay)
                        next_boost = time.perf_counter() + boost_iv

                    # schemalägg nästa cykel
                    next_cycle = now + loop_iv

                    # efter cykeln: tryck ned idle-next så att idle kan börja direkt
                    next_idle_click = time.perf_counter()

                # 2) Annars idle-klicka i mellanrummen (v1-style)
                else:
                    if idle_enabled:
                        if now >= next_idle_click:
                            if idle_mode == "current":
                                send_left_click()
                            else:
                                set_cursor_pos(idle_x, idle_y)
                                send_left_click()
                            next_idle_click = now + idle_interval

                time.sleep(0.003)

        finally:
            self.running = False
            self.status_var.set("status: idle  •  press F6 to start/stop")

    # ---------- close ----------
    def on_close(self):
        self.running = False
        try:
            if winmm is not None:
                winmm.timeEndPeriod(1)
        except Exception:
            pass
        self.root.destroy()

# ---------- run ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = CellBotV3(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
