"""
Makro Putar Balik (Windows) - diatur langsung dalam PIKSEL
Install dulu:  pip install pynput
Jalankan    :  python turn180.py
Kalau game tidak merespons, jalankan terminal/CMD sebagai Administrator.
"""
import ctypes
import json
import os
import threading
import time
from ctypes import POINTER, Structure, Union, c_long, c_ulong, byref, sizeof

from pynput import keyboard, mouse

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULT = {
    "trigger": None,   # contoh: "k:q", "k:f8", "m:x1"
    "pixels_x": 1600,  # gerak horizontal (positif = kanan, negatif = kiri)
    "pixels_y": 0,     # gerak vertikal (positif = bawah, negatif = atas)
    "steps": 1,        # 1 = instan, >1 = halus
    "duration": 0.0,   # total durasi gerakan (detik) jika steps > 1
}

# ---------- Mouse relatif via SendInput ----------
class MOUSEINPUT(Structure):
    _fields_ = [("dx", c_long), ("dy", c_long), ("mouseData", c_ulong),
                ("dwFlags", c_ulong), ("time", c_ulong),
                ("dwExtraInfo", POINTER(c_ulong))]

class _U(Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(Structure):
    _fields_ = [("type", c_ulong), ("u", _U)]

MOUSEEVENTF_MOVE = 0x0001

def move_relative(dx, dy=0):
    inp = INPUT(0, _U(mi=MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, None)))
    ctypes.windll.user32.SendInput(1, byref(inp), sizeof(inp))

def turn(cfg):
    tx, ty = int(cfg["pixels_x"]), int(cfg["pixels_y"])
    steps = max(1, int(cfg["steps"]))
    if steps == 1:
        move_relative(tx, ty)
        return
    delay = cfg["duration"] / steps
    done_x = done_y = 0
    for i in range(1, steps + 1):
        nx, ny = round(tx * i / steps), round(ty * i / steps)
        move_relative(nx - done_x, ny - done_y)
        done_x, done_y = nx, ny
        time.sleep(delay)

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

# ---------- Penerjemah tombol ----------
def key_to_str(key):
    if isinstance(key, keyboard.KeyCode):
        return "k:" + (key.char.lower() if key.char else f"vk{key.vk}")
    return "k:" + key.name

def btn_to_str(btn):
    return "m:" + btn.name

def pretty(s):
    if not s:
        return "(belum diatur)"
    kind, name = s.split(":", 1)
    return f"Keyboard [{name.upper()}]" if kind == "k" else f"Mouse [{name.upper()}]"

def capture_trigger():
    result, done = {}, threading.Event()

    def on_key(key):
        result["v"] = key_to_str(key); done.set(); return False

    def on_click(x, y, btn, pressed):
        if pressed:
            result["v"] = btn_to_str(btn); done.set(); return False

    kl = keyboard.Listener(on_press=on_key)
    ml = mouse.Listener(on_click=on_click)
    kl.start(); ml.start()
    done.wait()
    kl.stop(); ml.stop()
    time.sleep(0.3)
    return result["v"]

# ---------- Mode jalan ----------
def run(cfg):
    if not cfg["trigger"]:
        print("Tombol makro belum diatur!")
        return
    if cfg["trigger"] == "k:esc":
        print("ESC dipakai untuk berhenti, pilih tombol makro lain.")
        return
    held = {"down": False}

    def fire():
        if not held["down"]:        # cegah auto-repeat saat tombol ditahan
            held["down"] = True
            threading.Thread(target=turn, args=(cfg,), daemon=True).start()

    def on_press(key):
        s = key_to_str(key)
        if s == "k:esc":
            print("Berhenti."); return False
        if s == cfg["trigger"]:
            fire()

    def on_release(key):
        if key_to_str(key) == cfg["trigger"]:
            held["down"] = False

    def on_click(x, y, btn, pressed):
        if btn_to_str(btn) == cfg["trigger"]:
            if pressed: fire()
            else: held["down"] = False

    print(f"\nMakro AKTIF. Tombol: {pretty(cfg['trigger'])} | "
          f"Gerak: X={cfg['pixels_x']} Y={cfg['pixels_y']} piksel | Tekan [ESC] untuk berhenti.")
    ml = mouse.Listener(on_click=on_click)
    ml.start()
    with keyboard.Listener(on_press=on_press, on_release=on_release) as kl:
        kl.join()
    ml.stop()

# ---------- Menu ----------
def ask_number(prompt, cast, current):
    v = input(f"{prompt} [{current}]: ").strip()
    try:
        return cast(v.replace(",", ".")) if v else current
    except ValueError:
        print("Input tidak valid."); return current

def main():
    cfg = load_config()
    while True:
        print("\n=== MAKRO PUTAR BALIK ===")
        print(f"1. Atur tombol makro  : {pretty(cfg['trigger'])}")
        print(f"2. Atur piksel X      : {cfg['pixels_x']}  (negatif = kiri)")
        print(f"3. Atur piksel Y      : {cfg['pixels_y']}  (negatif = atas)")
        print(f"4. Mode halus         : steps={cfg['steps']}, durasi={cfg['duration']} dtk")
        print("5. Tes gerakan (3 detik setelah dipilih, fokus ke game)")
        print("6. MULAI makro (ESC untuk berhenti)")
        print("0. Keluar")
        c = input("Pilih: ").strip()

        if c == "1":
            print("Tekan tombol keyboard / mouse yang ingin dijadikan makro (selain ESC)...")
            t = capture_trigger()
            if t == "k:esc":
                print("ESC dipakai untuk berhenti. Pilih tombol lain.")
            else:
                cfg["trigger"] = t
                print("Tombol diset ke:", pretty(t)); save_config(cfg)
        elif c == "2":
            cfg["pixels_x"] = ask_number("Piksel X (mis. 800, 1600, -1600)", int, cfg["pixels_x"])
            save_config(cfg)
        elif c == "3":
            cfg["pixels_y"] = ask_number("Piksel Y", int, cfg["pixels_y"])
            save_config(cfg)
        elif c == "4":
            cfg["steps"] = ask_number("Jumlah steps (1 = instan)", int, cfg["steps"])
            cfg["duration"] = ask_number("Durasi total (detik)", float, cfg["duration"])
            save_config(cfg)
        elif c == "5":
            print("Pindah ke game... gerakan dimulai dalam 3 detik")
            time.sleep(3); turn(cfg)
        elif c == "6":
            run(cfg)
        elif c == "0":
            break

if __name__ == "__main__":
    main()