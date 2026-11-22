"""pokedex_predictor.py — dihasilkan oleh notebook UAS Klasifikasi Pokémon.

Pemakaian:
    from pokedex_predictor import predict_pokemon
    hasil = predict_pokemon("gambar.png", top_k=3)
"""
import os
import json
import numpy as np
from PIL import Image
import tensorflow as tf
try:
    import keras
    from keras import layers
except ImportError:
    from tensorflow import keras
    from tensorflow.keras import layers

EXPORT_DIR = os.environ.get("POKEDEX_EXPORT_DIR", os.path.dirname(os.path.abspath(__file__)))
_STATE = {}


@keras.utils.register_keras_serializable(package="pokedex")
class ResNetPreprocess(layers.Layer):
    def call(self, x):
        x = x[..., ::-1]
        return x - tf.constant([103.939, 116.779, 123.68], dtype=x.dtype)


def standardize_image(img, size, bg=(255, 255, 255)):
    bg = tuple(bg)
    if isinstance(img, (str, os.PathLike)):
        img = Image.open(img)
    elif not isinstance(img, Image.Image):
        raise TypeError("Input harus path file atau PIL.Image, bukan %s" % type(img))
    try:
        img.seek(0)
    except (EOFError, AttributeError):
        pass
    img = img.convert("RGBA")
    img = Image.alpha_composite(Image.new("RGBA", img.size, bg + (255,)), img).convert("RGB")
    w, h = img.size
    scale = size / max(w, h)
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    img = img.resize(new_size, getattr(Image, "Resampling", Image).LANCZOS)
    canvas = Image.new("RGB", (size, size), bg)
    canvas.paste(img, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
    return canvas


def _load():
    if _STATE:
        return _STATE
    p = lambda f: os.path.join(EXPORT_DIR, f)
    with open(p("app_config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    with open(p(cfg["type_classes"]), encoding="utf-8") as f:
        type_names = json.load(f)
    with open(p(cfg["species_classes"]), encoding="utf-8") as f:
        species_names = json.load(f)
    with open(p(cfg["info_json"]), encoding="utf-8") as f:
        info = {r["name_key"]: r for r in json.load(f)}
    _STATE.update(
        cfg=cfg, type_names=type_names["classes"],
        species_keys=species_names["classes"], species_display=species_names["display_names"],
        info=info,
        type_model=keras.models.load_model(p(cfg["type_model"]), compile=False),
        species_model=keras.models.load_model(p(cfg["species_model"]), compile=False))
    return _STATE


def _topk(probs, k):
    idx = np.argsort(probs)[::-1][:k]
    return [(int(i), float(probs[i])) for i in idx]


def predict_pokemon(image_path_or_pil, top_k=3):
    st = _load()
    size = st["cfg"]["img_size"]
    pil = standardize_image(image_path_or_pil, size, st["cfg"]["bg_color"])
    x = np.asarray(pil, dtype="float32")[None]
    p_type = st["type_model"](x, training=False).numpy()[0]
    p_sp = st["species_model"](x, training=False).numpy()[0]
    k_t, k_s = min(top_k, len(p_type)), min(top_k, len(p_sp))
    types = [{"label": st["type_names"][i], "confidence": c} for i, c in _topk(p_type, k_t)]
    species = []
    for i, c in _topk(p_sp, k_s):
        key = st["species_keys"][i]
        species.append({"key": key, "name": st["species_display"][i], "confidence": c, "info": st["info"].get(key)})
    return {"types": types, "species": species, "info": species[0]["info"] if species else None}
