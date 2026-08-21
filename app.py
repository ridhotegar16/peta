"""
Peta Sebaran Wilayah per Tahun — Streamlit app
=====================================================
Cara jalanin lokal:
    1. Buat folder .streamlit/secrets.toml berisi: APP_PASSWORD = "password_anda"
    2. pip install -r requirements.txt
    3. streamlit run app.py

Cara deploy:
    Push app.py + requirements.txt ke repo GitHub. 
    Abaikan folder .streamlit via .gitignore.
    Set password di Streamlit Cloud: App Settings -> Secrets -> APP_PASSWORD = "password_anda"
"""

import hashlib
import unicodedata

import numpy as np
import pandas as pd
import requests
import streamlit as st
import folium
import folium.plugins
from streamlit_folium import st_folium

# ============================================================
# 0. KONFIGURASI & AUTENTIKASI PASSWORD
# ============================================================
st.set_page_config(page_title="Peta Wilayah per Tahun", layout="wide", page_icon="🗺️")

def check_password():
    """Mengembalikan nilai True jika pengguna memasukkan password yang benar."""
    
    # Mengambil password dari Streamlit Secrets (lokal: .streamlit/secrets.toml | Cloud: App Settings)
    try:
        PASSWORD = st.secrets["APP_PASSWORD"]
    except KeyError:
        st.error("🔑 Sistem password belum dikonfigurasi. Harap tambahkan 'APP_PASSWORD' pada Streamlit Secrets.")
        return False

    def password_entered():
        """Memeriksa kebenaran password yang dimasukkan."""
        if st.session_state["pwd_input"] == PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["pwd_input"]  # Hapus password dari session demi keamanan
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # Tampilan pertama kali buka
        st.title("🔒 Akses Terbatas")
        st.text_input(
            "Masukkan Password untuk mengakses Dashboard:", 
            type="password", 
            on_change=password_entered, 
            key="pwd_input"
        )
        return False
    
    elif not st.session_state["password_correct"]:
        # Tampilan jika password salah
        st.title("🔒 Akses Terbatas")
        st.text_input(
            "Masukkan Password untuk mengakses Dashboard:", 
            type="password", 
            on_change=password_entered, 
            key="pwd_input"
        )
        st.error("😕 Password salah. Silakan coba lagi.")
        return False
    
    else:
        # Password benar
        return True

# Hentikan eksekusi script jika password belum benar
if not check_password():
    st.stop()

# ============================================================
# 0.1 KONFIGURASI APLIKASI
# ============================================================
TOPOJSON_URL = "https://raw.githubusercontent.com/tvalentius/Indonesia-topojson/master/indonesia-topojson-city-regency.json"

# Dipakai HANYA sebagai daftar wilayah untuk mode data dummy (kalau belum upload file).
DEFAULT_DAERAH_LIST = [
    "Kab. Buleleng","Kab. Sleman","Kab. Wonosobo","Kab. Purworejo","Kab. Banjarnegara",
    "Kab. Karanganyar","Kota Medan","Kab. Rembang","Kota Pekalongan","Kab. Wonogiri",
    "Kab. Temanggung","Kab. Pemalang","Kab. Batang","Kab. Boyolali","Kota Magelang",
    "Kab. Kendal","Kab. Jepara","Kab. Brebes","Kab. Tegal","Kab. Gianyar","Kab. Kudus",
    "Kab. Sragen","Kota Surabaya","Kota Cilegon","Kab. Badung","Kota Tegal","Kota Denpasar",
    "Kab. Grobogan","Kab. Magelang","Kab. Serang","Kab. Purbalingga","Kab. Lebak","Kab. Pati",
    "Kab. Kebumen","Kota Sukabumi","Kab. Sukabumi","Kota Yogyakarta","Kab. Indramayu",
    "Kota Cimahi","Kab. Banyumas","Kab. Pandeglang","Kota Jakarta Utara","Kab. Demak",
    "Kota Serang","Kab. Bekasi","Kab. Cianjur","Kota Bogor","Kab. Tangerang","Kab. Bogor",
    "Kab. Klaten","Kab. Karawang","Kota Bandung","Kab. Sukoharjo","Kab. Purwakarta",
    "Kab. Bandung Barat","Kota Tangerang","Kab. Cirebon","Kab. Semarang","Kab. Pekalongan",
    "Kota Bekasi","Kab. Cilacap","Kab. Bandung","Kota Tasikmalaya","Kab. Kuningan",
    "Kab. Tasikmalaya","Kab. Garut","Kab. Sumedang","Kab. Subang","Kota Surakarta",
    "Kab. Majalengka","Kota Jakarta Barat","Kota Tangerang Selatan","Kota Jakarta Pusat",
    "Kota Depok","Kab. Pangandaran","Kota Cirebon","Kota Jakarta Timur","Kab. Blora",
    "Kab. Ciamis","Kota Jakarta Selatan","Kab. Klungkung","Kota Banjar","Kab. Tabanan",
]

COLOR_LOW_HIGH = ["#E2574C", "#E8A33D", "#3FB88F"]  # merah (rendah) -> hijau (tinggi)


# ============================================================
# 1. TOPOJSON -> GEOJSON
# ============================================================
@st.cache_data(show_spinner=False)
def load_boundaries():
    topo = requests.get(TOPOJSON_URL, timeout=30).json()
    object_name = list(topo["objects"].keys())[0]
    obj = topo["objects"][object_name]
    transform = topo.get("transform")

    def decode_arc(arc):
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            if transform:
                pts.append([
                    x * transform["scale"][0] + transform["translate"][0],
                    y * transform["scale"][1] + transform["translate"][1],
                ])
            else:
                pts.append([x, y])
        return pts

    arcs = [decode_arc(a) for a in topo["arcs"]]

    def arc_coords(i):
        return list(arcs[i]) if i >= 0 else list(reversed(arcs[~i]))

    def ring(idx_list):
        coords = []
        for k, idx in enumerate(idx_list):
            pts = arc_coords(idx)
            if k > 0:
                pts = pts[1:]
            coords.extend(pts)
        return coords

    def to_geom(g):
        if g["type"] == "Polygon":
            return {"type": "Polygon", "coordinates": [ring(a) for a in g["arcs"]]}
        if g["type"] == "MultiPolygon":
            return {"type": "MultiPolygon", "coordinates": [[ring(a) for a in poly] for poly in g["arcs"]]}
        return None

    features = []
    for g in obj["geometries"]:
        geom = to_geom(g)
        if geom:
            features.append({"type": "Feature", "properties": dict(g.get("properties", {})), "geometry": geom})

    return {"type": "FeatureCollection", "features": features}


# ============================================================
# 2. MATCHING NAMA DAERAH <-> GEOJSON
# ============================================================
def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def parse_daerah(raw):
    raw = str(raw).strip()
    if raw.lower().startswith("kota "):
        return "kota", strip_diacritics(raw[5:]).lower().strip()
    if raw.lower().startswith("kab."):
        name = raw[4:].strip()
        return "kabupaten", strip_diacritics(name).lower().strip()
    if raw.lower().startswith("kab "):
        return "kabupaten", strip_diacritics(raw[4:]).lower().strip()
    return "kabupaten", strip_diacritics(raw).lower().strip()


def norm_geo_name(name2, type2):
    n = strip_diacritics(str(name2 or "")).lower()
    for prefix in ("kota adm. ", "kota administrasi ", "kota ", "kabupaten ", "kab. "):
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    n = n.strip()
    gtype = "kota" if "kota" in str(type2 or "").lower() else "kabupaten"
    return n, gtype


@st.cache_data(show_spinner=False)
def match_daerah_to_geo(_geojson, daerah_list):
    index = {}
    for f in _geojson["features"]:
        p = f["properties"]
        norm, gtype = norm_geo_name(p.get("NAME_2"), p.get("TYPE_2"))
        index.setdefault(norm, []).append((f, gtype))

    for i, f in enumerate(_geojson["features"]):
        f["properties"]["_idx"] = i

    matched, unmatched = {}, []
    for d in daerah_list:
        dtype, norm = parse_daerah(d)
        candidates = index.get(norm)
        if not candidates:
            keys = [k for k in index if norm in k or k in norm]
            candidates = [c for k in keys for c in index[k]] if keys else None
        if candidates:
            pick = next((c for c in candidates if c[1] == dtype), candidates[0])
            matched[d] = pick[0]["properties"]["_idx"]
        else:
            unmatched.append(d)
    return matched, unmatched


# ============================================================
# 3. PARSER FORMAT "BLOK TAHUN BERDAMPINGAN"
# ============================================================
def _clean_numeric(series):
    s = series.astype(str).str.strip()
    s = s.str.replace("%", "", regex=False)
    s = s.str.replace(r"[^0-9,.\-]", "", regex=True)
    has_both = s.str.contains(",") & s.str.contains(r"\.")
    s = s.where(~has_both, s.str.replace(".", "", regex=False))
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def find_year_blocks(raw, year_row_idx, header_row_idx):
    year_row = raw.iloc[year_row_idx].ffill()
    header_row = raw.iloc[header_row_idx]
    ncols = raw.shape[1]

    blocks = []
    col = 0
    while col < ncols:
        label = str(header_row[col]).strip().lower()
        if label.startswith("wilayah") or label.startswith("daerah"):
            metric_cols = []
            c = col + 1
            while c < ncols:
                nxt = str(header_row[c]).strip().lower()
                if nxt in ("nan", "") or nxt.startswith("wilayah") or nxt.startswith("daerah"):
                    break
                metric_cols.append(c)
                c += 1
            if metric_cols:
                year_val = year_row[metric_cols[0]]
                try:
                    year_label = str(int(float(year_val)))
                except (ValueError, TypeError):
                    year_label = str(year_val).strip()
                blocks.append({
                    "year": year_label,
                    "wilayah_col": col,
                    "metric_cols": metric_cols[:2],
                    "metric_names": [str(header_row[m]).strip() for m in metric_cols[:2]],
                })
            col = c if c > col else col + 1
        else:
            col += 1
    return blocks


def build_longdata(raw, blocks, header_row_idx):
    if not blocks:
        return pd.DataFrame(columns=["Daerah", "Tahun", "metrik1", "metrik2"]), (None, None)

    label1, label2 = blocks[0]["metric_names"][0], (
        blocks[0]["metric_names"][1] if len(blocks[0]["metric_names"]) > 1 else "metrik2"
    )

    data = raw.iloc[header_row_idx + 1:].reset_index(drop=True)
    frames = []
    for b in blocks:
        cols = [b["wilayah_col"]] + b["metric_cols"]
        sub = data.iloc[:, cols].copy()
        sub.columns = ["Daerah"] + [f"m{i}" for i in range(len(b["metric_cols"]))]
        sub = sub.dropna(subset=["Daerah"])
        sub["Daerah"] = sub["Daerah"].astype(str).str.strip()
        sub = sub[(sub["Daerah"] != "") & (sub["Daerah"].str.lower() != "nan")]
        if sub.empty:
            continue
        sub["Tahun"] = b["year"]
        sub["metrik1"] = _clean_numeric(sub["m0"]) if "m0" in sub.columns else np.nan
        sub["metrik2"] = _clean_numeric(sub["m1"]) if "m1" in sub.columns else np.nan
        frames.append(sub[["Daerah", "Tahun", "metrik1", "metrik2"]])

    long_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["Daerah", "Tahun", "metrik1", "metrik2"]
    )
    return long_df, (label1, label2)


# ============================================================
# 4. DATA DUMMY
# ============================================================
def _hash_seed(text):
    return int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**31 - 1)


def generate_dummy_data(years):
    rows = []
    for yi, y in enumerate(years):
        for d in DEFAULT_DAERAH_LIST:
            rng = np.random.default_rng(_hash_seed(d + y))
            drift = (yi - 1) * 0.06
            metrik1 = round(max(0, 10 + rng.random() * 60 + drift * 10), 1)
            metrik2 = round(max(0, min(100, rng.random() * 30 + drift * 15)), 2)
            rows.append({"Daerah": d, "Tahun": y, "metrik1": metrik1, "metrik2": metrik2})
    return pd.DataFrame(rows), ("Metrik 1 (dummy)", "Metrik 2 % (dummy)")


# ============================================================
# 5. WARNA
# ============================================================
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def color_scale(t, stops):
    t = min(1, max(0, t))
    n = len(stops) - 1
    seg = min(n - 1, int(t * n))
    local_t = (t * n) - seg
    c0, c1 = hex_to_rgb(stops[seg]), hex_to_rgb(stops[seg + 1])
    rgb = tuple(c0[i] + (c1[i] - c0[i]) * local_t for i in range(3))
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def norm_minmax(value, vmin, vmax):
    if pd.isna(value) or vmax == vmin:
        return 0.5
    return (value - vmin) / (vmax - vmin)


# ============================================================
# 6. SIDEBAR — UPLOAD & KONFIGURASI
# ============================================================
st.sidebar.header("Data")
uploaded = st.sidebar.file_uploader(
    "Upload CSV/Excel (format blok tahun seperti sheet 'Sheet Daerah')", type=["csv", "xlsx", "xls"]
)

with st.sidebar.expander("Konfigurasi posisi baris (kalau beda dari default)", expanded=False):
    year_row_idx = st.number_input("Baris label tahun (index, 0=baris 1)", min_value=0, value=0, step=1)
    header_row_idx = st.number_input("Baris header kolom (index)", min_value=0, value=1, step=1)
    sheet_name = st.text_input("Nama sheet (kosongkan = sheet pertama, khusus file Excel)", "")
    csv_sep = st.text_input("Pemisah kolom CSV (kosongkan = auto-detect)", "")

flip_colors = st.sidebar.checkbox("Balik arah warna (nilai tinggi = merah)", value=False)

use_dummy = uploaded is None
if use_dummy:
    st.sidebar.info("Belum ada file — dashboard jalan pakai data dummy dulu.")

# Option untuk Logout / Hapus sesi password saat dibuka
if st.sidebar.button("🔒 Lock Dashboard (Logout)"):
    del st.session_state["password_correct"]
    st.rerun()

# ============================================================
# 7. LOAD & PARSE DATA
# ============================================================
if use_dummy:
    years = ["2024", "2025", "2026"]
    long_df, (label1, label2) = generate_dummy_data(years)
else:
    try:
        fname = uploaded.name.lower()
        if fname.endswith(".csv"):
            raw = pd.read_csv(
                uploaded, header=None, sep=(csv_sep or None), engine="python", dtype=str
            )
        else:
            raw = pd.read_excel(uploaded, header=None, sheet_name=sheet_name or 0)
        blocks = find_year_blocks(raw, year_row_idx, header_row_idx)
        if not blocks:
            st.error(
                "Tidak ketemu blok 'wilayah' di baris header. Cek nomor baris header di sidebar, "
                "atau pastikan tiap blok tahun punya kolom berlabel 'wilayah'/'Daerah'."
            )
            st.stop()
        long_df, (label1, label2) = build_longdata(raw, blocks, header_row_idx)
        years = sorted(long_df["Tahun"].unique().tolist())
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")
        st.stop()

if long_df.empty:
    st.error("Data hasil parsing kosong. Cek format file / posisi baris header.")
    st.stop()

daerah_list = sorted(long_df["Daerah"].unique().tolist())
geojson = load_boundaries()
matched, unmatched = match_daerah_to_geo(geojson, daerah_list)

# ============================================================
# 8. HEADER
# ============================================================
st.title("🗺️ Peta Sebaran Wilayah per Tahun")
st.caption(
    f"{len(matched)}/{len(daerah_list)} wilayah berhasil dipetakan ke batas wilayah."
    + (f" Belum cocok: {', '.join(unmatched)}" if unmatched else "")
)

# ============================================================
# 9. URUTAN TAHUN
# ============================================================
def _year_sort_key(y):
    y = str(y).strip()
    if y.lower() == "total":
        return (1, 0, y)
    try:
        return (0, int(float(y)), y)
    except (ValueError, TypeError):
        return (1, 1, y)


years = sorted(years, key=_year_sort_key)
is_total_label = lambda y: str(y).strip().lower() == "total"
actual_years = [y for y in years if not is_total_label(y)]
total_label = next((y for y in years if is_total_label(y)), None)

# ============================================================
# 10. OVERVIEW TOTAL
# ============================================================
st.subheader("📊 Overview Total (Seluruh Data)")

if total_label is not None:
    df_total_block = long_df[long_df["Tahun"] == total_label].dropna(subset=["Daerah"])
    df_total_block = df_total_block.groupby("Daerah", as_index=False).mean(numeric_only=True)
    ov_jumlah_wilayah = df_total_block.shape[0]
    ov_rata1 = df_total_block["metrik1"].mean()
    ov_rata2 = df_total_block["metrik2"].mean()
else:
    df_all = long_df[~long_df["Tahun"].apply(is_total_label)].dropna(subset=["Daerah"])
    ov_jumlah_wilayah = df_all["Daerah"].nunique()
    ov_rata1 = df_all["metrik1"].mean()
    ov_rata2 = df_all["metrik2"].mean()

df_non_total = long_df[~long_df["Tahun"].apply(is_total_label)]
o1, o2, o3, o4, o5 = st.columns(5)
o1.metric("Jumlah Wilayah (Total)", f"{ov_jumlah_wilayah}")
o2.metric(f"Rata-rata {label1} (Total)", f"{ov_rata1:.2f}")
o3.metric(f"Rata-rata {label2} (Total)", f"{ov_rata2:.2f}")
o4.metric("Jumlah Tahun Terdata", f"{len(actual_years)}")
o5.metric("Total Baris Data (semua tahun)", f"{len(df_non_total)}")

st.markdown("---")

# ============================================================
# 11. FILTER / SLICER
# ============================================================
default_idx = years.index(total_label) if total_label is not None else len(years) - 1
tahun_pilih = st.selectbox("Filter Tahun (pilih 'Total' untuk lihat peta gabungan semua tahun)", years, index=default_idx)
df_tahun = long_df[long_df["Tahun"] == tahun_pilih].dropna(subset=["Daerah"])
df_tahun = df_tahun.groupby("Daerah", as_index=False).mean(numeric_only=True)
df_tahun = df_tahun.set_index("Daerah")

st.subheader(f"📌 Detail — {tahun_pilih}")
d1, d2, d3 = st.columns(3)
d1.metric("Jumlah Wilayah", f"{df_tahun.shape[0]}")
d2.metric(f"Rata-rata {label1}", f"{df_tahun['metrik1'].mean():.2f}")
d3.metric(f"Rata-rata {label2}", f"{df_tahun['metrik2'].mean():.2f}")

st.markdown("---")


# ============================================================
# 12. FUNGSI RENDER PETA + TABEL
# ============================================================
def render_metric(metric_col, label, key_prefix):
    stops = list(reversed(COLOR_LOW_HIGH)) if flip_colors else COLOR_LOW_HIGH
    vmin, vmax = df_tahun[metric_col].min(), df_tahun[metric_col].max()

    for f in geojson["features"]:
        f["properties"]["tooltip"] = "-"
        f["properties"]["fillcolor"] = "#1B2438"

    for daerah, idx in matched.items():
        if daerah not in df_tahun.index:
            continue
        val = df_tahun.loc[daerah, metric_col]
        props = geojson["features"][idx]["properties"]
        props["tooltip"] = f"{daerah} | {label}: {val:.2f}"
        t = norm_minmax(val, vmin, vmax)
        props["fillcolor"] = color_scale(t, stops)

    m = folium.Map(location=[-2.5, 118], zoom_start=5, tiles="CartoDB dark_matter")
    folium.plugins.Fullscreen(
        position="topright", title="Perbesar peta", title_cancel="Keluar layar penuh", force_separate_button=True
    ).add_to(m)
    folium.GeoJson(
        geojson,
        style_function=lambda feature: {
            "fillColor": feature["properties"]["fillcolor"],
            "color": "#0B1220",
            "weight": 1,
            "fillOpacity": 0.82 if feature["properties"]["fillcolor"] != "#1B2438" else 0.4,
        },
        tooltip=folium.GeoJsonTooltip(fields=["tooltip"], aliases=[""], labels=False),
    ).add_to(m)

    matched_coords = []
    for daerah, idx in matched.items():
        geom = geojson["features"][idx]["geometry"]
        for ring_ in (geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]):
            matched_coords.extend(ring_)
    if matched_coords:
        lats = [c[1] for c in matched_coords]
        lons = [c[0] for c in matched_coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    left, right = st.columns([2, 1])
    with left:
        st_folium(m, height=700, use_container_width=True, key=f"{key_prefix}_map")
    with right:
        st.markdown(f"**Top 10 — {label} tertinggi**")
        ranked = df_tahun[[metric_col]].sort_values(metric_col, ascending=False).head(10)
        ranked.columns = [label]
        st.dataframe(ranked, use_container_width=True)
        st.markdown(f"**Bottom 10 — {label} terendah**")
        ranked_low = df_tahun[[metric_col]].sort_values(metric_col, ascending=True).head(10)
        ranked_low.columns = [label]
        st.dataframe(ranked_low, use_container_width=True)


# ============================================================
# 13. DUA TAB PETA
# ============================================================
tab1, tab2 = st.tabs([f"🗺️ {label1}", f"🗺️ {label2}"])
with tab1:
    render_metric("metrik1", label1, "m1")
with tab2:
    render_metric("metrik2", label2, "m2")

st.markdown("---")
with st.expander("Lihat data mentah hasil parsing"):
    st.dataframe(long_df, use_container_width=True)

st.caption(
    "Batas administrasi: GADM (via tvalentius/Indonesia-topojson) · "
    "Basemap: CARTO Dark Matter © OpenStreetMap contributors."
)