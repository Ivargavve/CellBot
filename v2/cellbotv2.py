# cellbotv2.py
# Cyklisk bot med neutrala kontexter (Context 1..4) och tabs (Tab 1/2/3).
# Ordning per cykel: Menu Toggle -> (valfritt) Tab 1 -> (valfritt) Tab 2 -> (valfritt) Tab 3 -> Boost (om due).
# Hotkey: F6 start/stop.
#
# deps: pyautogui, pynput, pillow

import time
import threading
import tkinter as tk
from tkinter import ttk

import pyautogui
from pynput import keyboard, mouse

# snabba PyAutoGUI-inställningar
pyautogui.PAUSE = 0
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0

# -------------------- defaults --------------------
DEFAULT_MENU_TOGGLE = (35, 427)
DEFAULT_TAB1_POS = (47, 40)  
DEFAULT_TAB2_POS = (139, 41)  
DEFAULT_TAB3_POS = (223, 36)  
DEFAULT_BOOST_POINT = (654, 1028)

# Context 1 (Event) standardpunkter
CTX1_TAB1_POINTS = []  # inga default
CTX1_TAB2_POINTS = [
    (480, 246), (480, 341), (480, 442),
    (480, 542), (480, 642), (480, 742),
]
CTX1_TAB3_POINTS = [
    (480, 192), (480, 290), (480, 390),
    (480, 490), (480, 590), (480, 690),
]

# Context 2 (Primary) standardpunkter
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

# -------------------- app --------------------
class CellBotV2:
    def __init__(self, root):
        self.root = root
        self.root.title("CellBot v2")
        self.root.minsize(1120, 640)

        # state
        self.running = False
        self.bot_thread = None

        # fasta positioner
        self.menu_toggle = DEFAULT_MENU_TOGGLE
        self.tab1_pos    = DEFAULT_TAB1_POS
        self.tab2_pos    = DEFAULT_TAB2_POS
        self.tab3_pos    = DEFAULT_TAB3_POS
        self.boost_point = DEFAULT_BOOST_POINT

        # per-kontext punkter (t1/t2/t3)
        self.points = {
            "Context 1": {"t1": list(CTX1_TAB1_POINTS), "t2": list(CTX1_TAB2_POINTS), "t3": list(CTX1_TAB3_POINTS)},
            "Context 2": {"t1": list(CTX2_TAB1_POINTS), "t2": list(CTX2_TAB2_POINTS), "t3": list(CTX2_TAB3_POINTS)},
            "Context 3": {"t1": [], "t2": [], "t3": []},
            "Context 4": {"t1": [], "t2": [], "t3": []},
        }
        self.active_context = tk.StringVar(value="Context 1")

        # config
        self.loop_interval_var   = tk.StringVar(value="60.0")   # sek/cykel
        self.boost_interval_var  = tk.StringVar(value="965.0")  # sek/boost
        self.use_click_delay_var = tk.BooleanVar(value=True)    # checkbox för delay
        self.click_delay_var     = tk.StringVar(value="0.03")   # delay mellan klick (standard 0.03)
        self.boost_on_start_var  = tk.BooleanVar(value=True)

        # nya toggles för vilka tabs som används
        self.use_tab1_var = tk.BooleanVar(value=False)
        self.use_tab2_var = tk.BooleanVar(value=True)
        self.use_tab3_var = tk.BooleanVar(value=True)

        self.status_var          = tk.StringVar(value="status: idle  •  press F6 to start/stop")

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
        ttk.Label(header, text="CellBot v2", font=("Segoe UI", 14)).pack(side="left")
        ttk.Label(header, textvariable=self.status_var, foreground="#555").pack(side="right")

        # vänster: Menu/Tab-pickers + timing + toggles
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

        # notebook med kontexter
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

            # tre listor: t1, t2, t3
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

            # fyll listor
            self._refresh_ctx_lists(ctx)

        # boost
        boost_box = ttk.Labelframe(wrap, text="Boost")
        boost_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10,0))
        self.boost_label = ttk.Label(boost_box, text=f"{self.boost_point[0]},{self.boost_point[1]}", foreground="#222")
        self.boost_label.pack(side="right", padx=8, pady=6)
        ttk.Button(boost_box, text="Pick Boost point", command=self._pick_boost).pack(side="left", padx=8, pady=6)

        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_columnconfigure(2, weight=1)

        self._update_click_delay_state()

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

    # ---------- context ----------
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

    # ---------- picking ----------
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
        if not sel: return
        for i in reversed(sel):
            listbox.delete(i)
            del self.points[ctx][kind][i]

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

    # ---------- hotkey ----------
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

    # ---------- main loop ----------
    def _run(self):
        try:
            try:
                loop_iv = max(0.2, float(self.loop_interval_var.get()))
            except:
                loop_iv = 60.0
            try:
                boost_iv = max(5.0, float(self.boost_interval_var.get()))
            except:
                boost_iv = 965.0

            if self.use_click_delay_var.get():
                try:
                    click_delay = float(self.click_delay_var.get())
                    if click_delay < 0.0:
                        click_delay = 0.0
                except:
                    click_delay = 0.03
            else:
                click_delay = 0.0

            now = time.perf_counter()
            next_cycle = now
            next_boost = now if self.boost_on_start_var.get() else now + boost_iv
            boost_due = False

            while self.running:
                now = time.perf_counter()
                ctx = self._current_context()
                pts_t1 = list(self.points[ctx]["t1"])
                pts_t2 = list(self.points[ctx]["t2"])
                pts_t3 = list(self.points[ctx]["t3"])

                if self.boost_point and now >= next_boost:
                    boost_due = True

                if now >= next_cycle:
                    # Menu Toggle
                    click_xy(*self.menu_toggle, settle=click_delay)

                    # Tab 1 (valfri)
                    if self.use_tab1_var.get():
                        click_xy(*self.tab1_pos, settle=click_delay)
                        for (x, y) in pts_t1:
                            click_xy(x, y, settle=click_delay)

                    # Tab 2 (valfri)
                    if self.use_tab2_var.get():
                        click_xy(*self.tab2_pos, settle=click_delay)
                        for (x, y) in pts_t2:
                            click_xy(x, y, settle=click_delay)

                    # Tab 3 (valfri)
                    if self.use_tab3_var.get():
                        click_xy(*self.tab3_pos, settle=click_delay)
                        for (x, y) in pts_t3:
                            click_xy(x, y, settle=click_delay)

                    # Boost sist
                    if boost_due and self.boost_point:
                        click_xy(*self.boost_point, settle=click_delay)
                        next_boost = time.perf_counter() + boost_iv
                        boost_due = False

                    next_cycle = now + loop_iv

                time.sleep(0.005)

        finally:
            self.running = False
            self.status_var.set("status: idle  •  press F6 to start/stop")

# ---------- run ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = CellBotV2(root)
    root.mainloop()
