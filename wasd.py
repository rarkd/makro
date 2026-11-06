"""
Makro Hentikan WASD (Windows)
Saat tombol pemicu ditekan -> W A S D dilepas dan diblokir.

Install dulu:  pip install pynput
Jalankan    :  python stop_wasd.py
Kalau game tidak merespons, jalankan terminal/CMD sebagai Administrator.
"""
import ctypes
import json
import os
import threading
import time
from ctypes import POINTER, Structure, Union, c_long, c_ulong, c_ushort, byref, sizeof

from pynput import keyboard, mouse

user32 = ctypes.windll.user32
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_stopwasd.json")

DEFAULT = {
    "trigger": None,          # {"type":"k","vk":81,"name":"Q"} atau {"type":"m","name":"x1"}
    "keys": ["w", "a", "s", "d"],  # key yang dihentikan (bisa diubah di menu)
    "mode": "hold",           # "hold" = diblok selama tombol ditahan, "timed" = diblok X milidetik
    "block_ms": 150,          # durasi blok untuk mode "timed"
    "restore": True,          # setelah selesai, tekan lagi key yang masih ditahan fisik
}

NAMED_KEYS = {
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "space": 0x20, "tab": 0x09, "lshift": 0xA0, "lctrl": 0xA2, "lalt": 0xA4,
}
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}

# ---------- SendInput (keyboard) ----------
class KEYBDINPUT(Structure):
    _fields_ = [("wVk", c_ushort), ("wScan", c_ushort), ("dwFlags", c_ulong),
                ("time", c_ulong), ("dwExtraInfo", POINTER(c_ulong))]

class MOUSEINPUT(Structure):
    _fields_ = [("dx", c_long), ("dy", c_long), ("mouseData", c_ulong),
                ("dwFlags", c_ulong), ("time", c_ulong), ("dwExtraInfo", POINTER(c_ulong))]

class _U(Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

class INPUT(Structure):
    _fields_ = [("type", c_ulong), ("u", _U)]

def send_key(vk, up):
    """Kirim key down/up berbasis scancode (terbaca oleh kebanyakan game)."""
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0x0008                      # KEYEVENTF_SCANCODE
    if up:
        flags |= 0x0002                 # KEYEVENTF_KEYUP
    if vk in EXTENDED:
        flags |= 0x0001                 # KEYEVENTF_EXTENDEDKEY
    inp = INPUT(1, _U(ki=KEYBDINPUT(vk, scan, flags, 0, None)))
    user32.SendInput(1, byref(inp), sizeof(inp))

# ---------- Config ----------
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return {**DEFAULT, **{k: v for k, v in data.items() if k in DEFAULT}}
        except Exception:
            pass
    return dict(DEFAULT)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def name_to_vk(name):
    name = name.strip().lower()
    if name in NAMED_KEYS:
        return NAMED_KEYS[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    return None

def pretty_trigger(t):
    if not t:
        return "(belum diatur)"
    return f"Keyboard [{t['name'].upper()}]" if t["type"] == "k" else f"Mouse [{t['name'].upper()}]"

# ---------- Tangkap tombol pemicu ----------
def capture_trigger():
    result, done = {}, threading.Event()

    def on_key(key):
        if isinstance(key, keyboard.KeyCode):
            vk, name = key.vk, (key.char or f"vk{key.vk}")
        else:
            vk, name = key.value.vk, key.name
        result["v"] = {"type": "k", "vk": vk, "name": name}
        done.set()
        return False

    def on_click(x, y, btn, pressed):
        if pressed:
            result["v"] = {"type": "m", "name": btn.name}
            done.set()
            return False

    kl = keyboard.Listener(on_press=on_key)
    ml = mouse.Listener(on_click=on_click)
    kl.start(); ml.start()
    done.wait()
    kl.stop(); ml.stop()
    time.sleep(0.3)
    return result["v"]

# ---------- Logika blokir ----------
class Blocker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.vks = {v for v in (name_to_vk(n) for n in cfg["keys"]) if v}
        t = cfg["trigger"]
        self.trigger_vk = t["vk"] if t["type"] == "k" else None
        self.phys = set()          # key (dari daftar) yang sedang ditahan secara fisik
        self.blocking = False
        self.trigger_down = False
        self.timer = None

    def start_block(self):
        self.blocking = True
        for vk in self.vks:        # lepas dulu semua key yang sedang tertekan
            send_key(vk, up=True)

    def stop_block(self):
        if not self.blocking:
            return
        self.blocking = False
        if self.cfg["restore"]:
            for vk in list(self.phys):
                send_key(vk, up=False)

    def press_trigger(self):
        if self.trigger_down:      # abaikan auto-repeat
            return
        self.trigger_down = True
        if self.timer:
            self.timer.cancel()
        self.start_block()
        if self.cfg["mode"] == "timed":
            self.timer = threading.Timer(self.cfg["block_ms"] / 1000, self.stop_block)
            self.timer.start()

    def release_trigger(self):
        self.trigger_down = False
        if self.cfg["mode"] == "hold":
            self.stop_block()

def run(cfg):
    if not cfg["trigger"]:
        print("Tombol pemicu belum diatur!")
        return
    ctrl = Blocker(cfg)
    if ctrl.trigger_vk in ctrl.vks or ctrl.trigger_vk == 0xC0:
        print("Tombol pemicu tidak boleh sama dengan key yang diblokir atau tombol `.")
        return

    holder = {}

    def kb_filter(msg, data):
        if data.flags & 0x10:                 # abaikan input buatan sendiri
            return True
        vk = data.vkCode
        down = msg in (0x100, 0x104)
        up = msg in (0x101, 0x105)
        if vk == 0xC0 and down:               # tombol ` = berhenti
            holder["kl"].stop()
            return True
        if vk == ctrl.trigger_vk:
            if down: ctrl.press_trigger()
            elif up: ctrl.release_trigger()
            return True
        if vk in ctrl.vks:
            if down:
                ctrl.phys.add(vk)
                if ctrl.blocking:
                    holder["kl"].suppress_event()   # blokir key saat makro aktif
            elif up:
                ctrl.phys.discard(vk)
        return True

    def on_click(x, y, btn, pressed):
        t = cfg["trigger"]
        if t["type"] == "m" and btn.name == t["name"]:
            ctrl.press_trigger() if pressed else ctrl.release_trigger()

    print(f"\nMakro AKTIF. Pemicu: {pretty_trigger(cfg['trigger'])} | "
          f"Key diblok: {' '.join(k.upper() for k in cfg['keys'])} | "
          f"Mode: {cfg['mode']} | Tekan [`] untuk berhenti.")
    ml = mouse.Listener(on_click=on_click)
    ml.start()
    with keyboard.Listener(win32_event_filter=kb_filter) as kl:
        holder["kl"] = kl
        kl.join()
    ml.stop()
    if ctrl.timer:
        ctrl.timer.cancel()
    ctrl.blocking = False
    print("Berhenti.")

# ---------- Menu ----------
def main():
    cfg = load_config()
    while True:
        print("\n=== MAKRO HENTIKAN WASD ===")
        print(f"1. Atur tombol pemicu : {pretty_trigger(cfg['trigger'])}")
        print(f"2. Atur key yang dihentikan: {' '.join(k.upper() for k in cfg['keys'])}")
        mode_txt = "tahan (diblok selama pemicu ditahan)" if cfg["mode"] == "hold" \
            else f"sekali tekan (diblok {cfg['block_ms']} ms)"
        print(f"3. Mode               : {mode_txt}")
        print(f"4. Pulihkan key yang masih ditahan setelah selesai: {'YA' if cfg['restore'] else 'TIDAK'}")
        print("5. MULAI makro (tombol ` untuk berhenti)")
        print("0. Keluar")
        c = input("Pilih: ").strip()

        if c == "1":
            print("Tekan tombol keyboard / mouse yang ingin dijadikan pemicu (selain `)...")
            t = capture_trigger()
            if t["type"] == "k" and t["vk"] == 0xC0:
                print("Tombol ` dipakai untuk berhenti. Pilih tombol lain.")
            else:
                cfg["trigger"] = t
                print("Pemicu diset ke:", pretty_trigger(t)); save_config(cfg)
        elif c == "2":
            print("Ketik key dipisah spasi. Contoh: w a s d   atau   w a s d space")
            print("Nama khusus: up down left right space tab lshift lctrl lalt")
            raw = input("Key: ").split()
            valid = [k.lower() for k in raw if name_to_vk(k)]
            if valid:
                cfg["keys"] = valid; save_config(cfg)
            else:
                print("Tidak ada key valid, tidak diubah.")
        elif c == "3":
            m = input("Mode: 1 = tahan, 2 = sekali tekan (timed): ").strip()
            if m == "1":
                cfg["mode"] = "hold"
            elif m == "2":
                cfg["mode"] = "timed"
                v = input(f"Durasi blok (ms) [{cfg['block_ms']}]: ").strip()
                if v.isdigit():
                    cfg["block_ms"] = int(v)
            save_config(cfg)
        elif c == "4":
            cfg["restore"] = not cfg["restore"]; save_config(cfg)
        elif c == "5":
            run(cfg)
        elif c == "0":
            break

if __name__ == "__main__":
    main()