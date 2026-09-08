#!/usr/bin/env python3
"""
Wallpaper Studio -- local helper server.

Run this once (python3 wallpaper_server.py) and leave it running.
The Wallpaper Studio web app talks to it on http://127.0.0.1:8765 to:
  1. back up your CURRENT wallpaper on every launch (kept: 10 newest),
  2. save every generated image straight to a folder you choose (kept: 10 newest),
  3. keep up to 5 named save states,
  4. apply a generated image as your wallpaper,
  5. open those folders in your file manager, in the foreground.

No third-party dependencies -- pure standard library.
Works on Windows, macOS, and Linux (GNOME / most XDG desktops).
"""

import base64
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765
HOME = os.path.expanduser("~")

# Everything this program writes lives in subfolders of the folder holding the
# app, so the whole thing can be moved, copied or deleted as one unit.
#
# Frozen (PyInstaller) builds need care: __file__ points into a temporary
# extraction directory that is deleted on exit, so writable data has to hang off
# sys.executable instead. Read-only bundled files come from sys._MEIPASS.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", SCRIPT_DIR)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = SCRIPT_DIR


def resource(name):
    """A file the user may have dropped next to the app, else the bundled copy.

    Looking beside the app first means an edited wallpaper-studio.html wins over
    the one baked into the executable."""
    beside = os.path.join(SCRIPT_DIR, name)
    if os.path.isfile(beside):
        return beside
    return os.path.join(BUNDLE_DIR, name)


COMMAND_FILE = os.path.join(SCRIPT_DIR, "start.command")

APP_DIR = os.path.join(SCRIPT_DIR, "data")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "project-state.json")   # rolling autosave
STATES_DIR = os.path.join(APP_DIR, "states")               # up to 5 named slots
APPLIED_DIR = os.path.join(APP_DIR, "applied")             # what's actually on the desktop

DEFAULT_WALLPAPER_DIR = os.path.join(SCRIPT_DIR, "Wallpaper Backups")
DEFAULT_GENERATED_DIR = os.path.join(SCRIPT_DIR, "Generated")

LEGACY_APP_DIR = os.path.join(HOME, "WallpaperStudio")     # where earlier versions wrote

MAX_IMAGES = 10       # per folder: wallpaper backups, generated images
MAX_STATES = 5        # named save slots
MAX_APPLIED = 5       # copies of what we've set as the wallpaper

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".jfif", ".gif")

os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(STATES_DIR, exist_ok=True)
os.makedirs(APPLIED_DIR, exist_ok=True)


def migrate_legacy_data():
    """Earlier versions wrote to ~/WallpaperStudio. Bring that across once so
    nobody loses their save states when they update, then leave it alone."""
    if not os.path.isdir(LEGACY_APP_DIR) or os.path.abspath(LEGACY_APP_DIR) == os.path.abspath(APP_DIR):
        return
    moved = 0
    # config.json is deliberately not carried over: it holds folder paths from
    # the old layout, which pointed outside this folder.
    for name in ("project-state.json",):
        src, dst = os.path.join(LEGACY_APP_DIR, name), os.path.join(APP_DIR, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            moved += 1
    legacy_states = os.path.join(LEGACY_APP_DIR, "states")
    if os.path.isdir(legacy_states):
        for name in os.listdir(legacy_states):
            src, dst = os.path.join(legacy_states, name), os.path.join(STATES_DIR, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                moved += 1
    if moved:
        print(f"[ok] brought {moved} file(s) over from {LEGACY_APP_DIR}")


migrate_legacy_data()


def ensure_launcher_executable():
    """A downloaded start.command arrives without its executable bit, so Finder
    opens it in TextEdit instead of running it. Put the bit back."""
    if platform.system() == "Windows" or not os.path.isfile(COMMAND_FILE):
        return
    try:
        mode = os.stat(COMMAND_FILE).st_mode
        if not mode & 0o111:
            os.chmod(COMMAND_FILE, mode | 0o755)
            print("[ok] made start.command executable")
    except OSError as e:
        print(f"[warn] could not make start.command executable: {e}")


ensure_launcher_executable()


# --------------------------------------------------------------------------
# Config: where the user wants their wallpaper backups and generated images.
# --------------------------------------------------------------------------

def load_config():
    cfg = {"wallpaper_dir": DEFAULT_WALLPAPER_DIR, "generated_dir": DEFAULT_GENERATED_DIR}
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k in ("wallpaper_dir", "generated_dir"):
                v = saved.get(k)
                if isinstance(v, str) and v.strip():
                    p = os.path.expanduser(v.strip())
                    if not os.path.isabs(p):
                        p = os.path.join(SCRIPT_DIR, p)
                    cfg[k] = os.path.abspath(p)
        except Exception as e:
            print(f"[warn] could not read config, using defaults: {e}")
    return cfg


def save_config(cfg):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


CONFIG = load_config()


def wallpaper_dir():
    d = CONFIG["wallpaper_dir"]
    os.makedirs(d, exist_ok=True)
    return d


def generated_dir():
    d = CONFIG["generated_dir"]
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# Small file helpers
# --------------------------------------------------------------------------

def date_stamp():
    return time.strftime("%m-%d-%Y")


def list_images(folder):
    """Image files in `folder`, oldest first."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for n in names:
        p = os.path.join(folder, n)
        if os.path.isfile(p) and n.lower().endswith(IMAGE_EXTS):
            out.append(p)
    out.sort(key=lambda p: os.path.getmtime(p))
    return out


def prune_folder(folder, keep):
    """Delete oldest images until at most `keep` remain."""
    images = list_images(folder)
    removed = []
    while len(images) > keep:
        victim = images.pop(0)
        try:
            os.remove(victim)
            removed.append(victim)
            print(f"[ok] pruned oldest -> {os.path.basename(victim)}")
        except OSError as e:
            print(f"[warn] could not delete {victim}: {e}")
            break
    return removed


def unique_path(folder, base, ext):
    """`[09-08-2026] Generated.png`, then ` (2)`, ` (3)`, ... if taken."""
    candidate = os.path.join(folder, f"{base}{ext}")
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(folder, f"{base} ({n}){ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def file_digest(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


# --------------------------------------------------------------------------
# Reading / setting the desktop wallpaper
# --------------------------------------------------------------------------

def get_current_wallpaper_path():
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
            path, _ = winreg.QueryValueEx(key, "Wallpaper")
            return path
        elif system == "Darwin":
            out = subprocess.check_output([
                "osascript", "-e",
                'tell application "System Events" to get POSIX path of (get picture of desktop 1 as alias)'
            ]).decode().strip()
            return out
        elif system == "Linux":
            out = subprocess.check_output([
                "gsettings", "get", "org.gnome.desktop.background", "picture-uri"
            ]).decode().strip().strip("'\"")
            if out.startswith("file://"):
                return out[len("file://"):]
            return out
    except Exception as e:
        print(f"[warn] could not read current wallpaper: {e}")
    return None


def backup_current_wallpaper(reason="apply"):
    """Copy the current wallpaper into the backup folder, newest 10 kept.

    Skips wallpapers this app set itself, and skips an exact duplicate of the
    most recent backup -- otherwise every launch would burn a slot on the same
    image and push out the real originals.
    """
    current = get_current_wallpaper_path()
    if not current or not os.path.isfile(current):
        print("[info] no readable current wallpaper to back up (skipping)")
        return None

    folder = wallpaper_dir()
    current_abs = os.path.abspath(current)
    for own in (APPLIED_DIR, generated_dir(), folder):
        if current_abs.startswith(os.path.abspath(own) + os.sep):
            print("[info] current wallpaper is one of ours, not backing it up")
            return None

    existing = list_images(folder)
    if existing:
        newest = existing[-1]
        if os.path.getsize(newest) == os.path.getsize(current_abs) and \
                file_digest(newest) == file_digest(current_abs):
            print("[info] current wallpaper is already backed up (skipping)")
            return newest

    ext = os.path.splitext(current_abs)[1] or ".img"
    dest = unique_path(folder, f"[{date_stamp()}] Wallpaper", ext)
    shutil.copy2(current_abs, dest)
    print(f"[ok] backed up current wallpaper ({reason}) -> {dest}")
    prune_folder(folder, MAX_IMAGES)
    return dest


def apply_wallpaper(image_path):
    system = platform.system()
    if system == "Windows":
        import ctypes
        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDWININICHANGE = 0x02
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, image_path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
        )
    elif system == "Darwin":
        script = (
            'tell application "System Events" to tell every desktop '
            f'to set picture to "{image_path}"'
        )
        subprocess.run(["osascript", "-e", script], check=True)
    elif system == "Linux":
        uri = "file://" + image_path
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri], check=True)
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
            check=False,
        )
    else:
        raise RuntimeError(f"Unsupported OS: {system}")


# --------------------------------------------------------------------------
# Opening a folder -- and actually bringing it to the front on Windows
# --------------------------------------------------------------------------
# Windows refuses SetForegroundWindow to a process that doesn't own the
# foreground, so a plain `explorer <path>` from here opens the window behind
# the browser and just blinks in the taskbar. The fix is three-part:
#   1. AllowSetForegroundWindow(ASFW_ANY) before launching, so Explorer is
#      permitted to raise itself;
#   2. find the window Explorer actually opened (new one, or the reused one
#      whose title matches the folder);
#   3. AttachThreadInput to the current foreground thread, which makes our
#      SetForegroundWindow call legal, then restore + raise.

def _windows_explorer_hwnds():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    found = {}

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in ("CabinetWClass", "ExploreWClass"):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            found[hwnd] = title.value
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def _windows_force_foreground(hwnd):
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    SW_RESTORE = 9

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    cur_tid = kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    for tid in {fg_tid, tgt_tid}:
        if tid and tid != cur_tid and user32.AttachThreadInput(cur_tid, tid, True):
            attached.append(tid)
    try:
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
    finally:
        for tid in attached:
            user32.AttachThreadInput(cur_tid, tid, False)


def _open_folder_windows(path):
    import ctypes
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    ASFW_ANY = -1
    SW_SHOWNORMAL = 1

    before = _windows_explorer_hwnds()
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass
    shell32.ShellExecuteW(None, "open", path, None, None, SW_SHOWNORMAL)

    target = None
    wanted = os.path.basename(path.rstrip("\\/")).lower()
    deadline = time.time() + 4.0
    while time.time() < deadline:
        time.sleep(0.12)
        now = _windows_explorer_hwnds()
        new = [h for h in now if h not in before]
        if new:
            target = new[-1]
            break
        # Explorer may have reused an already-open window for this folder.
        for h, title in now.items():
            if title and title.lower() == wanted:
                target = h
                break
        if target:
            break

    if target:
        _windows_force_foreground(target)


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    system = platform.system()
    if system == "Windows":
        _open_folder_windows(path)
    elif system == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        try:
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"[warn] no xdg-open available; folder is at {path}")


# --------------------------------------------------------------------------
# Folder picker. Tk has to run on the main thread, so requests are handed
# over a queue and the main loop runs the dialog.
# --------------------------------------------------------------------------

DIALOG_QUEUE = queue.Queue()


class DialogJob:
    def __init__(self, title, initial):
        self.title = title
        self.initial = initial
        self.done = threading.Event()
        self.result = None
        self.error = None

    def run(self):
        try:
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.update()
            picked = filedialog.askdirectory(
                title=self.title,
                initialdir=self.initial if os.path.isdir(self.initial) else SCRIPT_DIR,
                mustexist=False,
                parent=root,
            )
            root.destroy()
            self.result = picked or None
        except Exception as e:
            self.error = str(e)
        finally:
            self.done.set()


def ask_for_folder(title, initial, timeout=180):
    job = DialogJob(title, initial)
    DIALOG_QUEUE.put(job)
    if not job.done.wait(timeout):
        raise RuntimeError("folder picker timed out")
    if job.error:
        raise RuntimeError(job.error)
    return job.result


# --------------------------------------------------------------------------
# Named save states
# --------------------------------------------------------------------------

SAFE_NAME = re.compile(r"[^A-Za-z0-9 _\-\.\(\)\[\]]+")


def slot_filename(name):
    clean = SAFE_NAME.sub("_", name).strip() or "state"
    return os.path.join(STATES_DIR, clean + ".json")


def list_slots():
    """Newest first."""
    out = []
    for n in os.listdir(STATES_DIR):
        if not n.lower().endswith(".json"):
            continue
        p = os.path.join(STATES_DIR, n)
        if not os.path.isfile(p):
            continue
        out.append({
            "name": os.path.splitext(n)[0],
            "saved_at": time.strftime("%m-%d-%Y %H:%M", time.localtime(os.path.getmtime(p))),
            "mtime": os.path.getmtime(p),
        })
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


def auto_slot_name():
    """Today's date; add a clock time if today already has a slot."""
    base = date_stamp()
    existing = {s["name"] for s in list_slots()}
    if base not in existing:
        return base
    stamped = f"{base} {time.strftime('%H-%M')}"
    if stamped not in existing:
        return stamped
    n = 2
    while f"{stamped} ({n})" in existing:
        n += 1
    return f"{stamped} ({n})"


def save_slot(name, data):
    path = slot_filename(name)
    is_new = not os.path.exists(path)
    dropped = None
    if is_new:
        slots = list_slots()
        while len(slots) >= MAX_STATES:
            oldest = slots.pop()
            try:
                os.remove(slot_filename(oldest["name"]))
                dropped = oldest["name"]
                print(f"[ok] state limit reached, removed oldest -> {oldest['name']}")
            except OSError:
                break
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return dropped


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---------------- GET ----------------

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/ping":
            self._json(200, {
                "status": "ok",
                "os": platform.system(),
                "frozen": FROZEN,
                "wallpaper_dir": CONFIG["wallpaper_dir"],
                "generated_dir": CONFIG["generated_dir"],
            })
        elif path == "/config":
            self._json(200, {
                "wallpaper_dir": CONFIG["wallpaper_dir"],
                "generated_dir": CONFIG["generated_dir"],
                "app_dir": SCRIPT_DIR,
                "defaults": {
                    "wallpaper_dir": DEFAULT_WALLPAPER_DIR,
                    "generated_dir": DEFAULT_GENERATED_DIR,
                },
                "max_images": MAX_IMAGES,
                "max_states": MAX_STATES,
            })
        elif path == "/state":
            self._get_autosave()
        elif path == "/states":
            self._json(200, {"states": list_slots(), "max": MAX_STATES})
        elif path == "/download/wallpaper_server.py":
            self._serve_file(resource("wallpaper_server.py"), "text/x-python", "wallpaper_server.py")
        elif path == "/download/start.bat":
            self._serve_file(resource("start.bat"), "application/octet-stream", "start.bat")
        elif path == "/download/start.command":
            self._serve_file(resource("start.command"), "application/octet-stream", "start.command")
        elif path in ("/", "/index.html", "/wallpaper-studio.html"):
            self._serve_app_html()
        else:
            self._json(404, {"error": "not found"})

    def _get_autosave(self):
        if os.path.isfile(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._json(200, {"exists": True, "data": data})
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(200, {"exists": False, "data": None})

    def _serve_file(self, path, ctype, download_name):
        if not os.path.isfile(path):
            self._json(404, {"error": f"{download_name} not found next to the server"})
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_app_html(self):
        html_file = resource("wallpaper-studio.html")
        if not os.path.isfile(html_file):
            body = (
                "<html><body style='font-family:sans-serif;padding:2rem;'>"
                "<h2>Wallpaper Studio helper is running \u2713</h2>"
                "<p>But <code>wallpaper-studio.html</code> wasn't found next to "
                "<code>wallpaper_server.py</code>. Put both files (and start.bat) "
                "in the same folder and restart.</p>"
                "</body></html>"
            ).encode()
        else:
            with open(html_file, "rb") as f:
                body = f.read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------------- POST ----------------

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = {
            "/apply": self._handle_apply,
            "/generate": self._handle_generate,
            "/state": self._handle_save_autosave,
            "/states/save": self._handle_slot_save,
            "/states/load": self._handle_slot_load,
            "/states/delete": self._handle_slot_delete,
            "/config": self._handle_set_config,
            "/pick-folder": self._handle_pick_folder,
            "/open-folder": self._handle_open_folder,
        }
        fn = routes.get(path)
        if fn:
            try:
                fn()
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def _decode_image(self, data):
        b64 = data["image_base64"].split(",")[-1]
        return base64.b64decode(b64)

    def _handle_generate(self):
        data = self._body()
        image_bytes = self._decode_image(data)
        folder = generated_dir()
        dest = unique_path(folder, f"[{date_stamp()}] Generated", ".png")
        with open(dest, "wb") as f:
            f.write(image_bytes)
        removed = prune_folder(folder, MAX_IMAGES)
        print(f"[ok] saved generated image -> {dest}")
        self._json(200, {
            "status": "saved",
            "path": dest,
            "folder": folder,
            "removed": [os.path.basename(p) for p in removed],
            "count": len(list_images(folder)),
        })

    def _handle_apply(self):
        data = self._body()
        source = data.get("source_path")

        os.makedirs(APPLIED_DIR, exist_ok=True)
        applied = os.path.join(APPLIED_DIR, f"wallpaper-{time.strftime('%Y%m%d-%H%M%S')}.png")
        if source and os.path.isfile(source):
            shutil.copy2(source, applied)
        else:
            with open(applied, "wb") as f:
                f.write(self._decode_image(data))

        backup_path = backup_current_wallpaper(reason="apply")
        apply_wallpaper(applied)
        prune_folder(APPLIED_DIR, MAX_APPLIED)

        self._json(200, {
            "status": "applied",
            "applied_path": applied,
            "backup_path": backup_path,
        })

    def _handle_save_autosave(self):
        data = self._body()
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, STATE_FILE)  # atomic-ish swap, avoids truncated files on crash
        self._json(200, {"status": "saved"})

    def _handle_slot_save(self):
        payload = self._body()
        name = (payload.get("name") or "").strip() or auto_slot_name()
        dropped = save_slot(name, payload.get("data") or {})
        self._json(200, {
            "status": "saved",
            "name": name,
            "dropped": dropped,
            "states": list_slots(),
        })

    def _handle_slot_load(self):
        name = (self._body().get("name") or "").strip()
        path = slot_filename(name)
        if not os.path.isfile(path):
            self._json(404, {"error": f"no saved state named {name}"})
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._json(200, {"status": "loaded", "name": name, "data": data})

    def _handle_slot_delete(self):
        name = (self._body().get("name") or "").strip()
        path = slot_filename(name)
        if os.path.isfile(path):
            os.remove(path)
        self._json(200, {"status": "deleted", "states": list_slots()})

    def _handle_set_config(self):
        payload = self._body()
        changed = {}
        if payload.get("reset"):
            CONFIG["wallpaper_dir"] = DEFAULT_WALLPAPER_DIR
            CONFIG["generated_dir"] = DEFAULT_GENERATED_DIR
            os.makedirs(DEFAULT_WALLPAPER_DIR, exist_ok=True)
            os.makedirs(DEFAULT_GENERATED_DIR, exist_ok=True)
            changed = dict(CONFIG)
        for key in ("wallpaper_dir", "generated_dir"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                folder = os.path.expanduser(v.strip())
                # A bare name like "Generated" means a subfolder of the app
                # folder, not of whatever directory the server was started from.
                if not os.path.isabs(folder):
                    folder = os.path.join(SCRIPT_DIR, folder)
                folder = os.path.abspath(folder)
                os.makedirs(folder, exist_ok=True)
                CONFIG[key] = folder
                changed[key] = folder
        if changed:
            save_config(CONFIG)
            print(f"[ok] folders updated: {changed}")
        self._json(200, {
            "status": "saved",
            "wallpaper_dir": CONFIG["wallpaper_dir"],
            "generated_dir": CONFIG["generated_dir"],
        })

    def _handle_pick_folder(self):
        which = self._body().get("which", "generated")
        key = "wallpaper_dir" if which == "wallpaper" else "generated_dir"
        label = "Choose a wallpaper backup folder" if which == "wallpaper" \
            else "Choose a folder for generated images"
        try:
            picked = ask_for_folder(label, CONFIG[key])
        except Exception as e:
            self._json(500, {"error": f"Folder picker unavailable ({e}). Type a path instead."})
            return
        if not picked:
            self._json(200, {"status": "cancelled", "path": None})
            return
        folder = os.path.abspath(picked)
        os.makedirs(folder, exist_ok=True)
        CONFIG[key] = folder
        save_config(CONFIG)
        self._json(200, {"status": "saved", "path": folder,
                         "wallpaper_dir": CONFIG["wallpaper_dir"],
                         "generated_dir": CONFIG["generated_dir"],
                         "app_dir": SCRIPT_DIR})

    def _handle_open_folder(self):
        which = self._body().get("which", "generated")
        folder = wallpaper_dir() if which == "wallpaper" else \
            (APP_DIR if which == "app" else generated_dir())
        # Answer immediately; raising the window can take a beat and the page
        # shouldn't sit there waiting on it.
        threading.Thread(target=open_folder, args=(folder,), daemon=True).start()
        self._json(200, {"status": "opening", "path": folder})

    def log_message(self, fmt, *args):
        print("[server] " + (fmt % args))


# --------------------------------------------------------------------------

def open_browser_soon(url, delay=1.0):
    """Give serve_forever a moment to be listening before the page loads."""
    def go():
        time.sleep(delay)
        try:
            if not webbrowser.open(url):
                print(f"No browser could be opened automatically. Visit {url}")
        except Exception as e:
            print(f"[warn] could not open a browser: {e}. Visit {url} yourself.")
    threading.Thread(target=go, daemon=True).start()


def pause_if_double_clicked():
    """A double-clicked window vanishes on exit, taking the error with it."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close this window.")
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    url = f"http://127.0.0.1:{PORT}/"
    quiet = "--no-browser" in sys.argv

    print("============================================================")
    print(" Wallpaper Studio")
    print(f" Local server at {url}")
    print()
    print(" Press Ctrl+C to stop, or just close this window.")
    print("============================================================")
    print()
    print(f"App folder        : {SCRIPT_DIR}")
    print(f"Wallpaper backups : {CONFIG['wallpaper_dir']}  (newest {MAX_IMAGES} kept)")
    print(f"Generated images  : {CONFIG['generated_dir']}  (newest {MAX_IMAGES} kept)")
    print(f"Settings & states : {APP_DIR}")
    print()

    try:
        server = HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98, 10048):   # address already in use
            print("Wallpaper Studio is already running in another window.")
            print("Opening the page there instead — close this window.")
            if not quiet:
                open_browser_soon(url, 0)
                time.sleep(1.5)
            return
        print(f"Could not start the server: {e}")
        pause_if_double_clicked()
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    if not quiet:
        open_browser_soon(url)

    # After binding, so a slow copy can't delay the page from loading.
    try:
        backup_current_wallpaper(reason="launch")
    except Exception as e:
        print(f"[warn] launch backup failed: {e}")

    # Main thread stays free so Tk folder dialogs can run on it.
    try:
        while True:
            try:
                job = DIALOG_QUEUE.get(timeout=0.4)
            except queue.Empty:
                continue
            job.run()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        pause_if_double_clicked()
