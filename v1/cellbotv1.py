# CellBot_v1 — auto clicker with two modes:
# 1) current cursor position
# 2) fixed position (pick on screen or type X/Y)
# Start/stop with F6 only.
# Dependency: pip install pynput
import threading, time, tkinter as tk
from tkinter import ttk
from pynput import keyboard, mouse
import ctypes
from ctypes import wintypes

# -------- High-resolution timer (reduce sleep jitter) --------
winmm = ctypes.WinDLL("winmm")
winmm.timeBeginPeriod(1)

# -------- WinAPI: SendInput, cursor pos/move --------
user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (('dx',          wintypes.LONG),
                ('dy',          wintypes.LONG),
                ('mouseData',   wintypes.DWORD),
                ('dwFlags',     wintypes.DWORD),
                ('time',        wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_void_p))

class INPUT(ctypes.Structure):
    _fields_ = (('type', wintypes.DWORD),
                ('mi',   MOUSEINPUT))

class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG),
                ("y", wintypes.LONG))

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

# -------- App --------
DEFAULT_HZ = 50.0
EMERGENCY_MARGIN = 5  # move mouse to top-left corner (<5px) for emergency stop

class CellBot_v1:
    def __init__(self, root):
        self.root = root
        self.root.title("CellBot_v1")
        self.root.minsize(360, 220)

        self.is_running = False
        self.stop_event = threading.Event()
        self.pick_listener = None

        # UI
        main = ttk.Frame(root, padding=15); main.pack(expand=True, fill="both")

        # Frequency
        ttk.Label(main, text="Frequency (Hz):").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.hz_var = tk.StringVar(value=str(DEFAULT_HZ))
        self.hz_spin = ttk.Spinbox(main, from_=0.1, to=1000.0, increment=1.0,
                                   textvariable=self.hz_var, width=10, command=self.update_calc)
        self.hz_spin.grid(row=0, column=1, sticky="w", pady=6)

        # Mode: current vs fixed
        ttk.Label(main, text="Click mode:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.mode_var = tk.StringVar(value="current")
        self.mode_combo = ttk.Combobox(main, state="readonly", values=["current", "fixed"],
                                       textvariable=self.mode_var, width=12)
        self.mode_combo.grid(row=1, column=1, sticky="w", pady=6)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self.update_mode_state())

        # Fixed position controls
        pos_frame = ttk.Frame(main); pos_frame.grid(row=2, column=0, columnspan=2, pady=6)
        ttk.Label(pos_frame, text="X:").grid(row=0, column=0, padx=(0,4))
        self.x_var = tk.StringVar(value="0")
        self.x_entry = ttk.Entry(pos_frame, textvariable=self.x_var, width=8)
        self.x_entry.grid(row=0, column=1, padx=(0,12))

        ttk.Label(pos_frame, text="Y:").grid(row=0, column=2, padx=(0,4))
        self.y_var = tk.StringVar(value="0")
        self.y_entry = ttk.Entry(pos_frame, textvariable=self.y_var, width=8)
        self.y_entry.grid(row=0, column=3, padx=(0,12))

        self.pick_btn = ttk.Button(pos_frame, text="Pick on screen", command=self.start_pick)
        self.pick_btn.grid(row=0, column=4)

        # Status + calc
        self.status_var = tk.StringVar(value="ready – press F6 to start/stop")
        ttk.Label(main, textvariable=self.status_var, justify="center").grid(row=3, column=0, columnspan=2, pady=(10,4))

        self.calc_var = tk.StringVar(value=self.calc_text(DEFAULT_HZ))
        ttk.Label(main, textvariable=self.calc_var, justify="center").grid(row=4, column=0, columnspan=2)

        # Center grid columns
        for i in range(2):
            main.grid_columnconfigure(i, weight=1)

        # Hotkey listener
        self.kb_listener = keyboard.Listener(on_press=self.on_key)
        self.kb_listener.daemon = True
        self.kb_listener.start()

        # Init state and window position
        self.update_mode_state()
        self.root.after(0, self.center_window)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI helpers ----------
    def center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def calc_text(self, hz):
        try:
            hz = float(hz)
            return f"{hz:.1f} clicks/sec\n{hz*60:,.0f} per min\n{hz*3600:,.0f} per hour"
        except:
            return ""

    def update_calc(self):
        self.calc_var.set(self.calc_text(self.hz_var.get()))

    def update_mode_state(self):
        fixed = self.mode_var.get() == "fixed"
        state = "normal" if fixed else "disabled"
        for w in (self.x_entry, self.y_entry, self.pick_btn):
            w.config(state=state)

    # ---------- Picking coordinates ----------
    def start_pick(self):
        if self.pick_listener:
            return
        self.status_var.set("Pick: click anywhere on screen to set X/Y…")
        # one-shot listener: first click sets coords, then stops
        def on_click(x, y, button, pressed):
            if pressed:
                self.x_var.set(str(int(x)))
                self.y_var.set(str(int(y)))
                self.update_calc()
                self.status_var.set(f"Picked ({int(x)}, {int(y)}). ready – press F6 to start/stop")
                # stop listener
                self.pick_listener.stop()
                self.pick_listener = None
                return False
            return True

        self.pick_listener = mouse.Listener(on_click=on_click)
        self.pick_listener.daemon = True
        self.pick_listener.start()

    # ---------- Hotkey ----------
    def on_key(self, key):
        if key == keyboard.Key.f6:
            self.root.after(0, self.toggle)

    def toggle(self):
        if self.is_running:
            self.stop_event.set()
        else:
            self.is_running = True
            self.stop_event.clear()
            self.status_var.set("clicking… press F6 to stop")
            threading.Thread(target=self.run, daemon=True).start()

    # ---------- Click loop ----------
    def run(self):
        try:
            # parse frequency
            try:
                hz = float(self.hz_var.get())
                interval = 1.0 / hz if hz > 0 else 0.02
            except:
                interval = 1.0 / DEFAULT_HZ
            self.update_calc()

            mode = self.mode_var.get()
            # if fixed, parse target coords upfront (ignore if invalid)
            if mode == "fixed":
                try:
                    target_x = int(float(self.x_var.get()))
                    target_y = int(float(self.y_var.get()))
                except:
                    target_x, target_y = 0, 0

            next_t = time.perf_counter()
            while not self.stop_event.is_set():
                # emergency stop: move to top-left corner
                cx, cy = get_cursor_pos()
                if cx < EMERGENCY_MARGIN and cy < EMERGENCY_MARGIN:
                    break

                now = time.perf_counter()
                if now < next_t:
                    time.sleep(max(0, next_t - now))

                if mode == "current":
                    send_left_click()
                else:
                    set_cursor_pos(target_x, target_y)
                    send_left_click()

                next_t += interval

            self.status_var.set("stopped – press F6 to start")
        finally:
            self.is_running = False

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()
        winmm.timeEndPeriod(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = CellBot_v1(root)
    root.mainloop()
