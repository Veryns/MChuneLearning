"""Diagnosis model Pokédex. Taruh di samping server.py lalu jalankan:
    venv\\Scripts\\python.exe cek_model.py gambar1.png gambar2.jpg ...
Kirim seluruh output-nya ke Claude."""
import os, sys, json
BASE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.environ.get("POKEDEX_EXPORT_DIR") or os.path.join(BASE, "pokedex_export")
sys.path.insert(0, EXPORT)
os.environ["POKEDEX_EXPORT_DIR"] = EXPORT
import numpy as np
from PIL import Image
import pokedex_predictor as pp
pp.EXPORT_DIR = EXPORT
pp._STATE.clear()
pp._load()
S = pp._STATE
cfg = S["cfg"]

print("=== STRUKTUR ===")
print("img_size/bg   :", cfg["img_size"], cfg["bg_color"])
print("species input :", S["species_model"].input_shape, "-> output", S["species_model"].output_shape)
print("jumlah kelas spesies:", len(S["species_keys"]), "| contoh 5 pertama:", S["species_keys"][:5])
print("type input    :", S["type_model"].input_shape, "-> output", S["type_model"].output_shape)
print("kelas tipe    :", S["type_names"])
print("species OK?   :", S["species_model"].output_shape[-1] == len(S["species_keys"]))
print("type OK?      :", S["type_model"].output_shape[-1] == len(S["type_names"]))

for path in sys.argv[1:]:
    print("\n=== GAMBAR:", path, "===")
    img = Image.open(path)
    print("ukuran asli:", img.size, "mode:", img.mode, "frames:", getattr(img, "n_frames", 1))
    for nama, im in [("asli", img), ("flip horizontal", img.transpose(Image.FLIP_LEFT_RIGHT))]:
        r = pp.predict_pokemon(im, top_k=5)
        print(f"-- {nama}")
        print("   spesies:", [(s["name"], round(s["confidence"], 3)) for s in r["species"]])
        print("   tipe(model):", [(t["label"], round(t["confidence"], 3)) for t in r["types"]])
    x = np.asarray(pp.standardize_image(img, cfg["img_size"], tuple(cfg["bg_color"])), dtype="float32")
    print("input ke model: shape", x.shape, "min", x.min(), "max", x.max(), "mean", round(float(x.mean()), 1))