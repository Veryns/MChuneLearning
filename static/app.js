"use strict";

const TYPE_COLORS = {
  Normal: "#A8A77A", Fire: "#EE8130", Water: "#6390F0", Electric: "#F7D02C",
  Grass: "#7AC74C", Ice: "#96D9D6", Fighting: "#C22E28", Poison: "#A33EA1",
  Ground: "#E2BF65", Flying: "#A98FF3", Psychic: "#F95587", Bug: "#A6B91A",
  Rock: "#B6A136", Ghost: "#735797", Dragon: "#6F35FC", Dark: "#705746",
  Steel: "#B7B7CE", Fairy: "#D685AD",
};
const ACCENT_GRADIENT = "linear-gradient(90deg, #e60012, #ff4d5a)";
const CONF_THRESHOLD = 0.5;
const SKIP_INFO = new Set(["name_key", "types_list", "in_species_scope"]);

const $ = (sel) => document.querySelector(sel);
const HISTORY_SIZE = 6;
const TOP_K = 5;
const state = {
  ready: false, busy: false, pending: false, dataUrl: null,
  history: Array(HISTORY_SIZE).fill(null), // {dataUrl, name, result}
  active: null, next: 0,
};

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function show(id, visible) {
  const node = $(id);
  if (node) node.hidden = !visible;
}

/* ---------------- status model ---------------- */
function setStatus(s) {
  const lens = $("#lens");
  lens.classList.toggle("ready", s.state === "ready"); // biru = model siap, merah = belum
  lens.title =
    s.state === "ready" ? "Model siap" + (s.scope ? " · " + s.scope : "")
    : s.state === "loading" ? "Memuat model…"
    : s.message;
  state.ready = s.state === "ready";
  if (s.state === "error") showError(s.message);
}

async function pollStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    const wasReady = state.ready;
    setStatus(s);
    if (s.state === "loading") setTimeout(pollStatus, 1200);
    if (s.state === "ready" && !wasReady && state.dataUrl) predict();
  } catch (e) {
    setStatus({ state: "error", message: "Server tidak terjangkau" });
  }
}

/* unggah gambar */
function showImage(url) {
  state.dataUrl = url;
  $("#preview").src = url;
  show("#preview", true);
  show("#drop-hint", false);
  show("#reset", true);
  show("#dec-dot", false);
}

function handleFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    showError("File yang dipilih bukan gambar.");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const slot = state.next;
    state.next = (state.next + 1) % HISTORY_SIZE;
    state.history[slot] = { dataUrl: reader.result, name: file.name || "tempel", result: null };
    state.active = slot;
    showImage(reader.result);
    renderHistory();
    predict();
  };
  reader.readAsDataURL(file);
}

function resetAll() {
  state.dataUrl = null;
  state.active = null;
  $("#file").value = "";
  show("#preview", false);
  show("#drop-hint", true);
  show("#reset", false);
  show("#dec-dot", true);
  show("#result", false);
  show("#error", false);
  show("#loading", false);
  show("#empty", true);
  renderHistory();
}

/* riwayat */
function renderHistory() {
  document.querySelectorAll("#history .blue-key").forEach((k, i) => {
    const e = state.history[i];
    k.classList.toggle("filled", !!e);
    k.classList.toggle("active", !!e && state.active === i);
    k.replaceChildren();
    if (e) {
      const img = document.createElement("img");
      img.src = e.dataUrl;
      img.alt = e.name;
      k.title = e.name;
      k.append(img);
    } else {
      k.removeAttribute("title");
      k.append(el("span", "ball-mark"));
    }
  });
}

function selectSlot(i) {
  const e = state.history[i];
  if (!e) return;
  state.active = i;
  showImage(e.dataUrl);
  renderHistory();
  if (e.result) {
    show("#loading", false); show("#error", false); show("#empty", false);
    render(e.result);
  } else {
    predict();
  }
}

/* prediksi */
function showError(msg) {
  show("#loading", false);
  show("#empty", false);
  show("#result", false);
  const box = $("#error");
  box.textContent = msg;
  box.hidden = false;
}

async function predict() {
  if (!state.dataUrl) return;
  if (!state.ready) {
    show("#empty", false); show("#error", false); show("#result", false); show("#loading", true);
    $("#loading p").textContent = "Menunggu model selesai dimuat…";
    return;
  }
  if (state.busy) { state.pending = true; return; }
  state.busy = true;
  show("#empty", false); show("#error", false); show("#result", false); show("#loading", true);
  $("#loading p").textContent = "Menganalisis gambar…";
  const url = state.dataUrl;
  const entry = state.history[state.active];
  try {
    const r = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: state.dataUrl, top_k: TOP_K }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Terjadi kesalahan.");
    if (entry) entry.result = data;
    if (state.dataUrl === url) render(data);
  } catch (e) {
    if (state.dataUrl === url) showError(e.message);
  } finally {
    state.busy = false;
    if (state.pending) { state.pending = false; predict(); }
  }
}

/* tampilkan hasil */
function bars(container, items) {
  container.replaceChildren();
  const fills = [];
  for (const it of items) {
    const row = el("div", "bar-row");
    const head = el("div", "bar-head");
    head.append(el("span", "", it.label), el("span", "", (it.conf * 100).toFixed(1) + "%"));
    const bar = el("div", "bar");
    const fill = el("div", "fill");
    fill.style.background = it.color;
    bar.append(fill);
    row.append(head, bar);
    container.append(row);
    fills.push([fill, Math.max(0, Math.min(1, it.conf))]);
  }
  requestAnimationFrame(() => requestAnimationFrame(() => {
    for (const [f, c] of fills) f.style.width = Math.max(1.5, c * 100) + "%";
  }));
}

function prettyKey(k) {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function render(d) {
  show("#loading", false);
  show("#error", false);
  show("#empty", false);

  const sp = d.species[0];
  const t0 = d.types[0];
  $("#name").textContent = sp.name;

  const badges = $("#badges");
  badges.replaceChildren();
  const shown = d.types_from_species ? d.types : [t0];
  for (const t of shown) {
    const b = el("span", "badge", t.label);
    b.style.background = TYPE_COLORS[t.label] || "#777";
    badges.append(b);
  }

  $("#conf-line").textContent =
    d.types_from_species
      ? `Spesies ${(sp.confidence * 100).toFixed(1)}% · Tipe dari data Pokédex`
      : `Spesies ${(sp.confidence * 100).toFixed(1)}% · Tipe (model) ${(t0.confidence * 100).toFixed(1)}%`;
  $("#processed").src = d.processed;

  const warn = $("#warn");
  if (sp.confidence < CONF_THRESHOLD) {
    warn.textContent = "Keyakinan rendah. Pokémon ini mungkin di luar cakupan model" +
      (d.scope ? ` (${d.scope})` : "") + " atau gambarnya berbeda dari data latih.";
    warn.hidden = false;
  } else {
    warn.hidden = true;
  }

  bars($("#type-bars"), d.types.map((t) => ({ label: t.label, conf: t.confidence, color: TYPE_COLORS[t.label] || "#888" })));
  bars($("#species-bars"), d.species.map((s) => ({ label: s.name, conf: s.confidence, color: ACCENT_GRADIENT })));

  const info = $("#info");
  info.replaceChildren();
  const entries = Object.entries(d.info || {}).filter(([k, v]) =>
    !SKIP_INFO.has(k) && v !== null && v !== "" && String(v).toLowerCase() !== "nan");
  if (!entries.length) {
    info.append(el("div", "muted", "Info tambahan tidak tersedia untuk spesies ini."));
  }
  for (const [k, v] of entries) {
    const item = el("div", "item");
    item.append(el("dt", "", prettyKey(k)), el("dd", "", String(v)));
    info.append(item);
  }

  const res = $("#result");
  const gs = document.querySelector(".grey-screen");
  if (gs) gs.scrollTop = 0;
  res.hidden = false;
  res.classList.remove("fade-in");
  void res.offsetWidth;
  res.classList.add("fade-in");
}

/* event */
const dz = $("#dropzone");
$("#file").addEventListener("change", (e) => handleFile(e.target.files[0]));
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#file").click(); } });
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => handleFile(e.dataTransfer.files[0]));
document.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item) handleFile(item.getAsFile());
});
$("#history").addEventListener("click", (e) => {
  const k = e.target.closest(".blue-key");
  if (k) selectSlot(Number(k.dataset.i));
});
$("#reset").addEventListener("click", (e) => { e.preventDefault(); resetAll(); });

pollStatus();