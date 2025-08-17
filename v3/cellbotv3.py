# cellbotv3.py
# Kompaktare UI + TopN på valfri tab + flyttad Idle in i högerkolumnen
#
# Nytt:
#  - Top N buy (standard N=1) istället för Top 3, justerbart i UI.
#  - TopN kan köras på valfri tab (t1/t2/t3) via UI.
#  - Ordningen mellan TopN Buy, Tab1, Tab2, Tab3 är ändringsbar i UI.
#  - Presets: spara/ladda/ta bort UI-inställningar. Autoladdar senaste preset vid start.
#  - UI mer kompakt: mindre paddings, lägre listbox-höjder, idle-fältet sitter direkt under presets.

import time
import threading
import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes
import json
import os
import pyautogui
from pynput import keyboard, mouse

# PyAutoGUI snabba inställningar
pyautogui.PAUSE = 0
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0

# -------------------- WinAPI high-res timer --------------------
try:
    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod(1)
except Exception:
    winmm = None

# -------------------- WinAPI SendInput --------------------
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
    _fields_ = (('type', wintypes.DWORD), ('mi', MOUSEINPUT))

class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))

def send_left_click():
    events = (INPUT * 2)()
    events[0].type, events[0].mi = INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    events[1].type, events[1].mi = INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP,   0, None)
    user32.SendInput(2, ctypes.byref(events), ctypes.sizeof(INPUT))

def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))

# -------------------- defaults --------------------
DEFAULT_LOOP_S = 60.0
DEFAULT_BOOST_S = 965.0
DEFAULT_CLICK_DELAY = 0.1
DEFAULT_IDLE_HZ = 50.0
EMERGENCY_MARGIN = 5  # px

DEFAULT_SKIP_AD_POS = (962, 712)
DEFAULT_MENU_TOGGLE = (35, 427)
DEFAULT_TAB1_POS = (47, 40)
DEFAULT_TAB2_POS = (139, 41)
DEFAULT_TAB3_POS = (223, 36)
DEFAULT_BOOST_POINT = (654, 1028)

# Buy-mode och x1-prepass
DEFAULT_BUYMODE_POS = (468, 108)
DEFAULT_SMART_TO_X1_CLICKS = 1
DEFAULT_X1_TO_SMART_CLICKS = 4
DEFAULT_TOPN_PREPASS = 1
PREPASS_TAB_KEY = "t2"

# Exempelkoordinater per tab och kontext
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

# -------------------- helpers --------------------
def click_xy(x, y, settle=0.05):
    pyautogui.moveTo(int(x), int(y), duration=0)
    pyautogui.click()
    if settle and settle > 0:
        time.sleep(settle)

# -------------------- Presets --------------------
def _user_config_dir():
    appdata = os.getenv("APPDATA")
    base = os.path.join(appdata, "CellBotV3") if appdata else os.path.join(os.path.expanduser("~"), ".cellbotv3")
    os.makedirs(base, exist_ok=True)
    return base

def _presets_path():
    return os.path.join(_user_config_dir(), "cellbotv3_presets.json")

def _load_all_presets():
    path = _presets_path()
    if not os.path.exists(path):
        return {"_last_used": None, "presets": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "presets" not in data or not isinstance(data["presets"], dict):
            return {"_last_used": None, "presets": {}}
        if "_last_used" not in data:
            data["_last_used"] = None
        return data
    except Exception:
        return {"_last_used": None, "presets": {}}

def _save_all_presets(data):
    path = _presets_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

# -------------------- App --------------------
class CellBotV3:
    def __init__(self, root):
        self.root = root
        self.root.title("CellBot v3")
        self.root.minsize(1120, 680)

        # Kompaktare ttk-styles
        style = ttk.Style(self.root)
        style.configure("TLabelframe", padding=(6,4,6,4))
        style.configure("TFrame", padding=0)
        style.configure("TButton", padding=(4,2))
        style.configure("TCheckbutton", padding=(2,0))
        style.configure("TLabel", padding=0)

        # run state
        self.running = False
        self.bot_thread = None

        # fasta pos
        self.skip_ad_pos = DEFAULT_SKIP_AD_POS
        self.menu_toggle = DEFAULT_MENU_TOGGLE
        self.tab1_pos    = DEFAULT_TAB1_POS
        self.tab2_pos    = DEFAULT_TAB2_POS
        self.tab3_pos    = DEFAULT_TAB3_POS
        self.boost_point = DEFAULT_BOOST_POINT

        # buy-mode och prepass
        self.buymode_btn = DEFAULT_BUYMODE_POS
        self.enable_x1_prep_var = tk.BooleanVar(value=True)
        self.smart_to_x1_clicks = DEFAULT_SMART_TO_X1_CLICKS
        self.x1_to_smart_clicks = DEFAULT_X1_TO_SMART_CLICKS
        self.prepass_tab_key = PREPASS_TAB_KEY
        self.topn_var = tk.IntVar(value=DEFAULT_TOPN_PREPASS)

        # punkter
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

        # ordning
        self.cycle_order = ["topn", "t1", "t2", "t3"]

        # idle
        self.idle_enable_var = tk.BooleanVar(value=True)
        self.idle_hz_var     = tk.StringVar(value=f"{DEFAULT_IDLE_HZ}")
        self.idle_mode_var   = tk.StringVar(value="fixed")
        self.idle_x_var      = tk.StringVar(value="1651")
        self.idle_y_var      = tk.StringVar(value="0")

        self.status_var = tk.StringVar(value="status: idle  •  press F6 to start/stop")

        # presets
        self._presets = _load_all_presets()
        self.preset_name_var = tk.StringVar(value="")
        self.auto_load_last_var = tk.BooleanVar(value=True)

        # hotkey
        self.kb_listener = keyboard.Listener(on_press=self._on_key)
        self.kb_listener.daemon = True
        self.kb_listener.start()

        # ui
        self._build_ui()
        self._center()

        # autoload senaste preset
        last = self._presets.get("_last_used")
        if self.auto_load_last_var.get() and last and last in self._presets["presets"]:
            self._apply_state(self._presets["presets"][last])
            self.preset_combo.set(last)
            self.preset_name_var.set(last)
            self.status_var.set(f"status: idle  •  loaded preset '{last}'  •  press F6 to start/stop")

    # ---------- UI ----------
    def _build_ui(self):
        wrap = ttk.Frame(self.root, padding=8)
        wrap.pack(fill="both", expand=True)

        header = ttk.Frame(wrap)
        header.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0,6))
        ttk.Label(header, text="CellBot v3", font=("Segoe UI", 13)).pack(side="left")
        ttk.Label(header, textvariable=self.status_var, foreground="#555").pack(side="right")

        # vänsterkolumn
        left = ttk.Frame(wrap)
        left.grid(row=1, column=0, sticky="nsew", padx=(0,8))

        lf_tabs = ttk.Labelframe(left, text="Menu & Tabs")
        lf_tabs.pack(fill="x", pady=(0,6))

        # Skip Ad
        srow = ttk.Frame(lf_tabs); srow.pack(fill="x", pady=3)
        ttk.Label(srow, text="Skip Ad").pack(side="left")
        self.skip_ad_label = ttk.Label(srow, text=f"{self.skip_ad_pos[0]},{self.skip_ad_pos[1]}", foreground="#222")
        self.skip_ad_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Skip Ad", command=self._pick_skip_ad).pack(fill="x")

        # Menu toggle
        mrow = ttk.Frame(lf_tabs); mrow.pack(fill="x", pady=3)
        ttk.Label(mrow, text="Menu toggle").pack(side="left")
        self.menu_label = ttk.Label(mrow, text=f"{self.menu_toggle[0]},{self.menu_toggle[1]}", foreground="#222")
        self.menu_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Menu toggle", command=self._pick_menu_toggle).pack(fill="x")

        # Buy mode button
        brow = ttk.Frame(lf_tabs); brow.pack(fill="x", pady=3)
        ttk.Label(brow, text="Buy mode button").pack(side="left")
        self.buymode_label = ttk.Label(brow, text=f"{self.buymode_btn[0]},{self.buymode_btn[1]}", foreground="#222")
        self.buymode_label.pack(side="right")
        ttk.Button(lf_tabs, text="Pick Buy mode", command=self._pick_buymode).pack(fill="x")

        # Tab 1..3
        for label_txt, key, getpos in (("Tab 1","t1",lambda: self.tab1_pos),
                                       ("Tab 2","t2",lambda: self.tab2_pos),
                                       ("Tab 3","t3",lambda: self.tab3_pos)):
            row = ttk.Frame(lf_tabs); row.pack(fill="x", pady=3)
            ttk.Label(row, text=label_txt).pack(side="left")
            pos = getpos()
            lbl = ttk.Label(row, text=f"{pos[0]},{pos[1]}", foreground="#222")
            if key=="t1": self.tab1_label = lbl
            elif key=="t2": self.tab2_label = lbl
            else: self.tab3_label = lbl
            lbl.pack(side="right")
            ttk.Button(lf_tabs, text=f"Pick {label_txt}", command=lambda k=key: self._pick_tab(k)).pack(fill="x")

        # Timing
        lf_cfg = ttk.Labelframe(left, text="Timing")
        lf_cfg.pack(fill="x", pady=(0,6))
        row_cfg1 = ttk.Frame(lf_cfg); row_cfg1.pack(fill="x", pady=3)
        ttk.Label(row_cfg1, text="Loop every (s)").pack(side="left")
        ttk.Entry(row_cfg1, width=7, textvariable=self.loop_interval_var).pack(side="left", padx=(6,12))
        ttk.Label(row_cfg1, text="Boost every (s)").pack(side="left")
        ttk.Entry(row_cfg1, width=7, textvariable=self.boost_interval_var).pack(side="left", padx=(6,0))
        row_cfg2 = ttk.Frame(lf_cfg); row_cfg2.pack(fill="x", pady=3)
        ttk.Checkbutton(row_cfg2, text="Use click delay", variable=self.use_click_delay_var,
                        command=self._update_click_delay_state).pack(side="left")
        ttk.Label(row_cfg2, text="Delay (s)").pack(side="left", padx=(8,4))
        self.click_delay_entry = ttk.Entry(row_cfg2, width=6, textvariable=self.click_delay_var)
        self.click_delay_entry.pack(side="left")

        # Toggles + TopN
        lf_tog = ttk.Labelframe(left, text="Behavior")
        lf_tog.pack(fill="x", pady=(0,6))
        ttk.Checkbutton(lf_tog, text="Use Tab 1", variable=self.use_tab1_var).pack(anchor="w", padx=6, pady=(4,0))
        ttk.Checkbutton(lf_tog, text="Use Tab 2", variable=self.use_tab2_var).pack(anchor="w", padx=6, pady=(2,0))
        ttk.Checkbutton(lf_tog, text="Use Tab 3", variable=self.use_tab3_var).pack(anchor="w", padx=6, pady=(2,4))

        row_topn = ttk.Frame(lf_tog); row_topn.pack(fill="x", pady=(0,2))
        ttk.Checkbutton(row_topn, text="Enable Top-N x1 pre-pass",
                        variable=self.enable_x1_prep_var,
                        command=self._update_topn_state).pack(side="left", padx=(6,6))
        ttk.Label(row_topn, text="N=").pack(side="left")
        self.topn_spin = tk.Spinbox(row_topn, from_=1, to=99, width=3, textvariable=self.topn_var)
        self.topn_spin.pack(side="left", padx=(4,8))
        ttk.Label(row_topn, text="Tab:").pack(side="left")
        self.topn_tab_var = tk.StringVar(value=self.prepass_tab_key)
        self.topn_tab_combo = ttk.Combobox(row_topn, state="readonly", width=4,
                                           values=["t1", "t2", "t3"],
                                           textvariable=self.topn_tab_var)
        self.topn_tab_combo.pack(side="left", padx=(4,6))
        self.topn_tab_combo.bind("<<ComboboxSelected>>",
                                 lambda e: setattr(self, "prepass_tab_key", self.topn_tab_var.get()))

        ttk.Checkbutton(lf_tog, text="Boost on start", variable=self.boost_on_start_var).pack(anchor="w", padx=6, pady=(2,2))
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
            colwrap = ttk.Frame(frame, padding=4)
            colwrap.pack(fill="both", expand=True)

            for i, key in enumerate(("t1", "t2", "t3")):
                box = ttk.Labelframe(colwrap, text=f"{ctx} • Tab {i+1} points")
                box.grid(row=0, column=i, sticky="nsew", padx=4)
                lb = tk.Listbox(box, height=14)  # lägre höjd
                lb.pack(fill="both", expand=True, padx=6, pady=6)
                row = ttk.Frame(box); row.pack(fill="x", padx=6, pady=(0,6))
                ttk.Button(row, text="Add (pick)",
                           command=lambda c=ctx, k=key, l=lb: self._pick_point_ctx(c, k, l)).pack(side="left")
                ttk.Button(row, text="Remove",
                           command=lambda c=ctx, k=key, l=lb: self._remove_selected_ctx(c, k, l)).pack(side="right")
                self.ctx_widgets.setdefault(ctx, {})[key] = lb

            self._refresh_ctx_lists(ctx)

        # Boost-pick direkt under notebook
        boost_box = ttk.Labelframe(wrap, text="Boost")
        boost_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(4,0))
        self.boost_label = ttk.Label(boost_box, text=f"{self.boost_point[0]},{self.boost_point[1]}", foreground="#222")
        self.boost_label.pack(side="right", padx=6, pady=4)
        ttk.Button(boost_box, text="Pick Boost point", command=self._pick_boost).pack(side="left", padx=6, pady=4)

        # Högerkolumn kompakt: container
        right_col = ttk.Frame(wrap)
        right_col.grid(row=1, column=3, sticky="n", padx=(8,0))

        # Cycle order kompakt
        order_box = ttk.Labelframe(right_col, text="Cycle order (TopN / Tab1 / Tab2 / Tab3)")
        order_box.pack(fill="x", expand=False, pady=(0,6))
        self.order_list = tk.Listbox(order_box, height=4)
        self.order_list.pack(fill="x", expand=False, padx=6, pady=6)
        btns = ttk.Frame(order_box); btns.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btns, text="Up", command=self._order_up).pack(side="left")
        ttk.Button(btns, text="Down", command=self._order_down).pack(side="left", padx=6)
        ttk.Button(btns, text="Reset", command=self._order_reset).pack(side="right")
        self._order_refresh()

        # Presets under
        presets_box = ttk.Labelframe(right_col, text="Presets")
        presets_box.pack(fill="x", expand=False, pady=(0,6))

        rowp1 = ttk.Frame(presets_box); rowp1.pack(fill="x", padx=6, pady=(6,3))
        ttk.Label(rowp1, text="Select").pack(side="left")
        self.preset_combo = ttk.Combobox(rowp1, state="readonly",
                                         values=sorted(list(self._presets["presets"].keys())))
        self.preset_combo.pack(side="left", fill="x", expand=True, padx=(6,6))
        ttk.Button(rowp1, text="Load", command=self._ui_load_preset).pack(side="left")

        rowp2 = ttk.Frame(presets_box); rowp2.pack(fill="x", padx=6, pady=3)
        ttk.Label(rowp2, text="Name").pack(side="left")
        ttk.Entry(rowp2, textvariable=self.preset_name_var, width=18).pack(side="left", padx=(6,6))
        ttk.Button(rowp2, text="Save/Overwrite", command=self._ui_save_preset).pack(side="left")
        ttk.Button(rowp2, text="Delete", command=self._ui_delete_preset).pack(side="left", padx=(6,0))

        rowp3 = ttk.Frame(presets_box); rowp3.pack(fill="x", padx=6, pady=(3,6))
        ttk.Checkbutton(rowp3, text="Auto-load last used on start", variable=self.auto_load_last_var).pack(side="left")
        ttk.Label(presets_box, text=f"Stored at: {_presets_path()}", foreground="#777")\
            .pack(anchor="w", padx=6, pady=(0,6))

        # Idle-klickare direkt efter presets i samma right_col (ingen stor glipa)
        idle_box = ttk.Labelframe(right_col, text="Idle clicker (v1-style between cycles)")
        idle_box.pack(fill="x", expand=False)

        ttk.Checkbutton(idle_box, text="Enable idle clicker", variable=self.idle_enable_var)\
            .pack(anchor="w", padx=6, pady=(6,2))

        row_idle1 = ttk.Frame(idle_box); row_idle1.pack(fill="x", padx=6, pady=2)
        ttk.Label(row_idle1, text="Frequency (Hz)").pack(side="left")
        ttk.Entry(row_idle1, width=7, textvariable=self.idle_hz_var).pack(side="left", padx=(6,0))

        row_idle2 = ttk.Frame(idle_box); row_idle2.pack(fill="x", padx=6, pady=2)
        ttk.Label(row_idle2, text="Click mode").pack(side="left")
        idle_mode = ttk.Combobox(row_idle2, state="readonly", values=["current", "fixed"],
                                 textvariable=self.idle_mode_var, width=9)
        idle_mode.pack(side="left", padx=(6,0))
        idle_mode.bind("<<ComboboxSelected>>", lambda e: self._update_idle_mode_state())

        pos_frame = ttk.Frame(idle_box); pos_frame.pack(fill="x", padx=6, pady=(2,6))
        ttk.Label(pos_frame, text="X:").pack(side="left")
        self.idle_x_entry = ttk.Entry(pos_frame, width=7, textvariable=self.idle_x_var)
        self.idle_x_entry.pack(side="left", padx=(4,10))
        ttk.Label(pos_frame, text="Y:").pack(side="left")
        self.idle_y_entry = ttk.Entry(pos_frame, width=7, textvariable=self.idle_y_var)
        self.idle_y_entry.pack(side="left", padx=(4,10))
        ttk.Button(pos_frame, text="Pick on screen", command=self._pick_idle_pos).pack(side="left")

        # Grid weights
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_rowconfigure(2, weight=0)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_columnconfigure(2, weight=1)
        wrap.grid_columnconfigure(3, weight=0)

        self._update_click_delay_state()
        self._update_idle_mode_state()
        self._update_topn_state()

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
        if fixed:
            self.idle_x_entry.state(["!disabled"])
            self.idle_y_entry.state(["!disabled"])
        else:
            self.idle_x_entry.state(["disabled"])
            self.idle_y_entry.state(["disabled"])

    def _update_topn_state(self):
        state = "normal" if self.enable_x1_prep_var.get() else "disabled"
        try:
            self.topn_spin.configure(state=state)
            self.topn_tab_combo.configure(state="readonly" if state == "normal" else "disabled")
        except Exception:
            pass

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

    # ---------- Order UI ----------
    def _order_labels(self):
        mapping = {"topn": "TopN Buy", "t1": "Tab 1", "t2": "Tab 2", "t3": "Tab 3"}
        return [mapping[k] for k in self.cycle_order]

    def _order_refresh(self):
        self.order_list.delete(0, "end")
        for label in self._order_labels():
            self.order_list.insert("end", label)
        if self.order_list.size() > 0:
            self.order_list.selection_clear(0, "end")
            self.order_list.selection_set(0)

    def _order_up(self):
        sel = self.order_list.curselection()
        if not sel: return
        i = sel[0]
        if i == 0: return
        self.cycle_order[i-1], self.cycle_order[i] = self.cycle_order[i], self.cycle_order[i-1]
        self._order_refresh()
        self.order_list.selection_clear(0, "end")
        self.order_list.selection_set(i-1)

    def _order_down(self):
        sel = self.order_list.curselection()
        if not sel: return
        i = sel[0]
        if i >= len(self.cycle_order) - 1: return
        self.cycle_order[i+1], self.cycle_order[i] = self.cycle_order[i], self.cycle_order[i+1]
        self._order_refresh()
        self.order_list.selection_clear(0, "end")
        self.order_list.selection_set(i+1)

    def _order_reset(self):
        self.cycle_order = ["topn", "t1", "t2", "t3"]
        self._order_refresh()

    # ---------- Picking ----------
    def _pick_skip_ad(self):
        self.status_var.set("pick: click Skip Ad…")
        self._pick_one(self._set_skip_ad)

    def _pick_menu_toggle(self):
        self.status_var.set("pick: click Menu toggle…")
        self._pick_one(self._set_menu_toggle)

    def _pick_buymode(self):
        self.status_var.set("pick: click Buy mode button…")
        self._pick_one(self._set_buymode)

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
        if not sel: return
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
    def _set_skip_ad(self, pt):
        self.skip_ad_pos = pt
        self.skip_ad_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

    def _set_menu_toggle(self, pt):
        self.menu_toggle = pt
        self.menu_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

    def _set_buymode(self, pt):
        self.buymode_btn = pt
        self.buymode_label.config(text=f"{pt[0]},{pt[1]}", foreground="#222")

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

    # ---------- Hjälpare ----------
    def _tab_pos_for_key(self, key):
        if key == "t1":
            return self.tab1_pos
        if key == "t2":
            return self.tab2_pos
        return self.tab3_pos

    def _click_buymode(self, times=1, delay=0.05):
        for _ in range(int(times)):
            click_xy(*self.buymode_btn, settle=delay)

    def _x1_prepass_topn(self, ctx, click_delay):
        self.prepass_tab_key = self.topn_tab_var.get() if self.topn_tab_var.get() in ("t1","t2","t3") else self.prepass_tab_key
        tab_key = self.prepass_tab_key
        tab_pos = self._tab_pos_for_key(tab_key)

        click_xy(*tab_pos, settle=click_delay)
        self._click_buymode(self.smart_to_x1_clicks, delay=click_delay)

        try:
            n = max(1, int(self.topn_var.get()))
        except:
            n = DEFAULT_TOPN_PREPASS
        rows = list(self.points[ctx][tab_key])[:n]
        for (x, y) in rows:
            click_xy(x, y, settle=click_delay)

        click_xy(*tab_pos, settle=click_delay)
        self._click_buymode(self.x1_to_smart_clicks, delay=click_delay)

    def _perform_tab_clicks(self, tab_key, pts, click_delay):
        if tab_key == "t1" and not self.use_tab1_var.get(): return
        if tab_key == "t2" and not self.use_tab2_var.get(): return
        if tab_key == "t3" and not self.use_tab3_var.get(): return
        click_xy(*self._tab_pos_for_key(tab_key), settle=click_delay)
        for (x, y) in pts:
            click_xy(x, y, settle=click_delay)

    # ---------- Preset state ----------
    def _collect_state(self):
        state = {
            "skip_ad_pos": list(self.skip_ad_pos),
            "menu_toggle": list(self.menu_toggle),
            "tab1_pos": list(self.tab1_pos),
            "tab2_pos": list(self.tab2_pos),
            "tab3_pos": list(self.tab3_pos),
            "boost_point": list(self.boost_point),
            "buymode_btn": list(self.buymode_btn),

            "enable_x1_prep": bool(self.enable_x1_prep_var.get()),
            "smart_to_x1_clicks": int(self.smart_to_x1_clicks),
            "x1_to_smart_clicks": int(self.x1_to_smart_clicks),
            "prepass_tab_key": str(self.prepass_tab_key),
            "topn": int(self.topn_var.get()),

            "loop_interval": float(self.loop_interval_var.get() or DEFAULT_LOOP_S),
            "boost_interval": float(self.boost_interval_var.get() or DEFAULT_BOOST_S),
            "use_click_delay": bool(self.use_click_delay_var.get()),
            "click_delay": float(self.click_delay_var.get() or DEFAULT_CLICK_DELAY),
            "boost_on_start": bool(self.boost_on_start_var.get()),

            "use_tab1": bool(self.use_tab1_var.get()),
            "use_tab2": bool(self.use_tab2_var.get()),
            "use_tab3": bool(self.use_tab3_var.get()),

            "cycle_order": list(self.cycle_order),

            "idle_enable": bool(self.idle_enable_var.get()),
            "idle_hz": float(self.idle_hz_var.get() or DEFAULT_IDLE_HZ),
            "idle_mode": str(self.idle_mode_var.get()),
            "idle_x": int(float(self.idle_x_var.get() or 0)),
            "idle_y": int(float(self.idle_y_var.get() or 0)),

            "points": {ctx: {k: [list(p) for p in self.points[ctx][k]] for k in ("t1","t2","t3")} for ctx in CONTEXTS},
        }
        return state

    def _apply_state(self, state):
        def _pair(v, default):
            try: return (int(v[0]), int(v[1]))
            except Exception: return default

        self.skip_ad_pos = _pair(state.get("skip_ad_pos"), self.skip_ad_pos)
        self.menu_toggle = _pair(state.get("menu_toggle"), self.menu_toggle)
        self.tab1_pos    = _pair(state.get("tab1_pos"), self.tab1_pos)
        self.tab2_pos    = _pair(state.get("tab2_pos"), self.tab2_pos)
        self.tab3_pos    = _pair(state.get("tab3_pos"), self.tab3_pos)
        self.boost_point = _pair(state.get("boost_point"), self.boost_point)
        self.buymode_btn = _pair(state.get("buymode_btn"), self.buymode_btn)

        self.skip_ad_label.config(text=f"{self.skip_ad_pos[0]},{self.skip_ad_pos[1]}")
        self.menu_label.config(text=f"{self.menu_toggle[0]},{self.menu_toggle[1]}")
        self.tab1_label.config(text=f"{self.tab1_pos[0]},{self.tab1_pos[1]}")
        self.tab2_label.config(text=f"{self.tab2_pos[0]},{self.tab2_pos[1]}")
        self.tab3_label.config(text=f"{self.tab3_pos[0]},{self.tab3_pos[1]}")
        self.boost_label.config(text=f"{self.boost_point[0]},{self.boost_point[1]}")
        self.buymode_label.config(text=f"{self.buymode_btn[0]},{self.buymode_btn[1]}")

        self.enable_x1_prep_var.set(bool(state.get("enable_x1_prep", self.enable_x1_prep_var.get())))
        self.smart_to_x1_clicks = int(state.get("smart_to_x1_clicks", self.smart_to_x1_clicks))
        self.x1_to_smart_clicks = int(state.get("x1_to_smart_clicks", self.x1_to_smart_clicks))
        key = state.get("prepass_tab_key", self.prepass_tab_key)
        if key in ("t1","t2","t3"):
            self.prepass_tab_key = key
            self.topn_tab_var.set(key)
        self.topn_var.set(int(state.get("topn", self.topn_var.get())))

        self.loop_interval_var.set(str(float(state.get("loop_interval", self.loop_interval_var.get()))))
        self.boost_interval_var.set(str(float(state.get("boost_interval", self.boost_interval_var.get()))))
        self.use_click_delay_var.set(bool(state.get("use_click_delay", self.use_click_delay_var.get())))
        self.click_delay_var.set(str(float(state.get("click_delay", self.click_delay_var.get()))))
        self.boost_on_start_var.set(bool(state.get("boost_on_start", self.boost_on_start_var.get())))

        self.use_tab1_var.set(bool(state.get("use_tab1", self.use_tab1_var.get())))
        self.use_tab2_var.set(bool(state.get("use_tab2", self.use_tab2_var.get())))
        self.use_tab3_var.set(bool(state.get("use_tab3", self.use_tab3_var.get())))

        order = state.get("cycle_order")
        if isinstance(order, list) and all(k in ("topn","t1","t2","t3") for k in order):
            self.cycle_order = list(order)
            self._order_refresh()

        self.idle_enable_var.set(bool(state.get("idle_enable", self.idle_enable_var.get())))
        self.idle_hz_var.set(str(float(state.get("idle_hz", self.idle_hz_var.get()))))
        self.idle_mode_var.set(str(state.get("idle_mode", self.idle_mode_var.get())))
        self.idle_x_var.set(str(int(state.get("idle_x", int(float(self.idle_x_var.get()))))))
        self.idle_y_var.set(str(int(state.get("idle_y", int(float(self.idle_y_var.get()))))))
        self._update_idle_mode_state()
        self._update_topn_state()
        self._update_click_delay_state()

        pts = state.get("points", {})
        for ctx in CONTEXTS:
            for k in ("t1","t2","t3"):
                if ctx in pts and k in pts[ctx]:
                    try:
                        self.points[ctx][k] = [(int(x), int(y)) for x,y in pts[ctx][k]]
                    except Exception:
                        pass
            self._refresh_ctx_lists(ctx)

    # ---------- Preset UI actions ----------
    def _ui_load_preset(self):
        name = self.preset_combo.get().strip()
        if not name or name not in self._presets["presets"]:
            self.status_var.set("status: idle  •  preset not found")
            return
        self._apply_state(self._presets["presets"][name])
        self.preset_name_var.set(name)
        self._presets["_last_used"] = name
        _save_all_presets(self._presets)
        self.status_var.set(f"status: idle  •  loaded preset '{name}'")

    def _ui_save_preset(self):
        name = self.preset_name_var.get().strip() or "Default"
        state = self._collect_state()
        self._presets["presets"][name] = state
        self._presets["_last_used"] = name if self.auto_load_last_var.get() else self._presets.get("_last_used")
        ok = _save_all_presets(self._presets)
        if ok:
            self.preset_combo["values"] = sorted(list(self._presets["presets"].keys()))
            self.preset_combo.set(name)
            self.status_var.set(f"status: idle  •  saved preset '{name}'")
        else:
            self.status_var.set("status: idle  •  failed to save preset")

    def _ui_delete_preset(self):
        name = self.preset_combo.get().strip() or self.preset_name_var.get().strip()
        if not name or name not in self._presets["presets"]:
            self.status_var.set("status: idle  •  preset not found")
            return
        del self._presets["presets"][name]
        if self._presets.get("_last_used") == name:
            self._presets["_last_used"] = None
        ok = _save_all_presets(self._presets)
        self.preset_combo["values"] = sorted(list(self._presets["presets"].keys()))
        self.preset_combo.set("")
        if ok:
            self.status_var.set(f"status: idle  •  deleted preset '{name}'")
        else:
            self.status_var.set("status: idle  •  failed to delete preset")

    # ---------- Main loop ----------
    def _run(self):
        try:
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
                idle_interval = 1.0 / idle_hz if idle_hz > 0 else 0.02
            except:
                idle_interval = 1.0 / DEFAULT_IDLE_HZ
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
                cx, cy = get_cursor_pos()
                if cx < EMERGENCY_MARGIN and cy < EMERGENCY_MARGIN:
                    break

                now = time.perf_counter()
                ctx = self._current_context()

                if now >= next_cycle:
                    pts_t1 = list(self.points[ctx]["t1"])
                    pts_t2 = list(self.points[ctx]["t2"])
                    pts_t3 = list(self.points[ctx]["t3"])

                    if self.skip_ad_pos:
                        click_xy(*self.skip_ad_pos, settle=click_delay)

                    click_xy(*self.menu_toggle, settle=click_delay)

                    for step in self.cycle_order:
                        if step == "topn":
                            if self.enable_x1_prep_var.get():
                                self._x1_prepass_topn(ctx, click_delay)
                        elif step == "t1":
                            self._perform_tab_clicks("t1", pts_t1, click_delay)
                        elif step == "t2":
                            self._perform_tab_clicks("t2", pts_t2, click_delay)
                        elif step == "t3":
                            self._perform_tab_clicks("t3", pts_t3, click_delay)

                    if now >= next_boost and self.boost_point:
                        click_xy(*self.boost_point, settle=click_delay)
                        next_boost = time.perf_counter() + boost_iv

                    next_cycle = now + loop_iv
                    next_idle_click = time.perf_counter()
                else:
                    if idle_enabled and now >= next_idle_click:
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
        if self.auto_load_last_var.get():
            name = self.preset_combo.get().strip() or self.preset_name_var.get().strip()
            if name and name in self._presets["presets"]:
                self._presets["_last_used"] = name
                _save_all_presets(self._presets)
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
