"""Pokédex AI — server web lokal (tanpa library tambahan selain yang dipakai model).

Jalankan:  python server.py      lalu browser terbuka otomatis (http://127.0.0.1:8000)

Butuh folder `pokedex_export/` (hasil notebook) di samping file ini.
Opsional: POKEDEX_EXPORT_DIR=<path>, PORT=<angka>, NO_BROWSER=1
"""
import os
import sys
import io
import json
import math
import base64
import mimetypes
import threading
import importlib
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_DIR = os.path.join(BASE_DIR, "static")
EXPORT_DIR = os.environ.get("POKEDEX_EXPORT_DIR") or os.path.join(BASE_DIR, "pokedex_export")
MAX_BODY = 25 * 1024 * 1024   # batas ukuran unggahan (25 MB)

STATE = {"state": "loading", "message": "Memuat TensorFlow & model...", "scope": ""}
PP = None
CFG = None
LOCK = threading.Lock()       # model dipakai satu permintaan pada satu waktu


def load_model():
    """Muat model di thread terpisah supaya halaman web bisa langsung terbuka."""
    global PP, CFG
    try:
        if not os.path.isfile(os.path.join(EXPORT_DIR, "app_config.json")):
            raise FileNotFoundError(
                f"Folder model tidak ditemukan: {EXPORT_DIR}. "
                "Taruh folder 'pokedex_export' di samping server.py.")
        if EXPORT_DIR not in sys.path:
            sys.path.insert(0, EXPORT_DIR)
        os.environ["POKEDEX_EXPORT_DIR"] = EXPORT_DIR
        import pokedex_predictor as pp
        importlib.reload(pp)
        pp.EXPORT_DIR = EXPORT_DIR
        pp._STATE.clear()
        pp._load()
        with open(os.path.join(EXPORT_DIR, "app_config.json"), encoding="utf-8") as f:
            CFG = json.load(f)
        PP = pp
        STATE.update(state="ready", message="Model siap", scope=CFG.get("species_scope", ""))
        print("[server] model siap")
    except Exception as e:  # noqa: BLE001
        STATE.update(state="error", message=f"{type(e).__name__}: {e}")
        print("[server] GAGAL memuat model:", STATE["message"])


def clean(o):
    """Ubah hasil prediksi jadi JSON valid (NaN -> null, tipe numpy -> python)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:  # noqa: BLE001
            return str(o)
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def png_data_url(pil):
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def types_from_info(info):
    """Ambil daftar tipe resmi dari pokemon_info.json (kolom types / primary_type / secondary_type)."""
    if not isinstance(info, dict):
        return []
    raw = info.get("types")
    if isinstance(raw, str) and raw.strip():
        parts = [t for t in raw.replace(",", "|").replace("/", "|").split("|")]
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        parts = [info.get("primary_type"), info.get("secondary_type")]
    out = []
    for t in parts:
        t = str(t).strip() if t is not None else ""
        if t and t.lower() not in ("nan", "none", "null") and t.capitalize() not in out:
            out.append(t.capitalize())
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "PokedexAI/1.0"

    # ------------------------------------------------------------ util
    def send_json(self, obj, status=200):
        body = json.dumps(clean(obj), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, url_path):
        rel = url_path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not (full == STATIC_DIR or full.startswith(STATIC_DIR + os.sep)) or not os.path.isfile(full):
            self.send_json({"error": "Tidak ditemukan"}, 404)
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------ routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self.send_json(STATE)
        else:
            self.send_static(path)

    def do_POST(self):
        if urlparse(self.path).path != "/api/predict":
            self.send_json({"error": "Tidak ditemukan"}, 404)
            return
        if STATE["state"] != "ready":
            self.send_json({"error": STATE["message"]}, 503)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self.send_json({"error": "Ukuran unggahan tidak valid (maks 25 MB)."}, 413)
            return
        try:
            data = json.loads(self.rfile.read(length))
            b64 = str(data["image"])
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            top_k = max(1, min(5, int(data.get("top_k", 3))))
            img = Image.open(io.BytesIO(base64.b64decode(b64)))
            img.load() if getattr(img, "n_frames", 1) == 1 else None
        except (KeyError, ValueError, UnidentifiedImageError, OSError):
            self.send_json({"error": "File bukan gambar yang valid."}, 400)
            return
        try:
            with LOCK:
                out = PP.predict_pokemon(img, top_k=top_k)
                processed = PP.standardize_image(img, CFG["img_size"], CFG["bg_color"])
            # Model tipe akurasinya rendah (~28%), spesies ~96%. Kalau spesies yakin,
            # ambil tipe resmi dari data Pokédex, bukan dari tebakan model tipe.
            sp0 = out["species"][0]
            official = types_from_info(sp0.get("info") or out.get("info"))
            if official and sp0["confidence"] >= 0.5:
                out["types_model"] = out["types"]
                out["types"] = [{"label": t, "confidence": sp0["confidence"]} for t in official]
                out["types_from_species"] = True
            out["processed"] = png_data_url(processed)
            out["scope"] = CFG.get("species_scope", "")
            self.send_json(out)
        except Exception as e:  # noqa: BLE001
            print("[server] prediksi gagal:", type(e).__name__, e)
            self.send_json({"error": f"Prediksi gagal: {type(e).__name__}: {e}"}, 500)

    def log_message(self, fmt, *args):
        if "/api/status" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    threading.Thread(target=load_model, daemon=True).start()
    start = int(os.environ.get("PORT", "8000"))
    httpd = None
    for port in range(start, start + 10):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit(f"Port {start}-{start + 9} semua terpakai. Tutup aplikasi lain atau set PORT=...")
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"Pokédex AI berjalan di {url}  (tekan Ctrl+C untuk berhenti)")
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()