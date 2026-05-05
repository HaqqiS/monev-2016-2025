"""
MONEV MONITOR
=============
Fix utama v3:
- make_key() kini strip nama wilayah (region) dari dalam nama badan
  sehingga "dinas sosial kabupaten badung" dan "dinas sosial" dengan
  region=Badung menghasilkan key yang sama → ter-cluster dengan benar.
- Entity resolution menggunakan composite (badan_key + region) 
  sebagai unit pencocokan, bukan hanya nama.
"""

import streamlit as st
import pandas as pd
import re
from difflib import SequenceMatcher
from collections import defaultdict

st.set_page_config(page_title="MONEV MONITOR", layout="wide", page_icon="📊")

# ════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ════════════════════════════════════════════════════════════════════

# Semua nama wilayah Bali yang mungkin muncul di dalam nama badan
WILAYAH_BALI = [
    'badung', 'buleleng', 'gianyar', 'tabanan', 'klungkung',
    'karangasem', 'bangli', 'jembrana', 'denpasar', 'bali',
]

SINGKATAN_MAP = {
    r'\bbappeda\b': 'badan perencanaan pembangunan daerah',
    r'\bbalitbang\b': 'badan penelitian dan pengembangan',
    r'\bbkpsdm\b': 'badan kepegawaian dan pengembangan sumber daya manusia',
    r'\bdpmptsp\b': 'dinas penanaman modal dan pelayanan terpadu satu pintu',
    r'\bdpmd\b': 'dinas pemberdayaan masyarakat desa',
    r'\bbapenda\b': 'badan pendapatan daerah',
    r'\bdiskominfo\b': 'dinas komunikasi dan informatika',
    r'\batr/bpn\b': 'kantor pertanahan badan pertanahan nasional',
    r'\bsatpol pp\b': 'satuan polisi pamong praja',
    r'\bbpbd\b': 'badan penanggulangan bencana daerah',
    r'\bbpkad\b': 'badan pengelola keuangan dan aset daerah',
    r'\bbakeuda\b': 'badan keuangan daerah',
    r'\bbapedalibang\b': 'badan perencanaan penelitian dan pengembangan',
    r'\bdprd\b': 'dewan perwakilan rakyat daerah',
}

KUALIFIKASI_ORDER = [
    'Informatif', 'Menuju Informatif', 'Cukup Informatif',
    'Kurang Informatif', 'Tidak Informatif', 'Tidak Diketahui',
]
KUAL_ICON = {
    'Informatif': '🟢',
    'Menuju Informatif': '🔵',
    'Cukup Informatif': '🟡',
    'Kurang Informatif': '🟠',
    'Tidak Informatif': '🔴',
    'Tidak Diketahui': '⚪',
}

# ════════════════════════════════════════════════════════════════════
# 1. LOAD DATA
# ════════════════════════════════════════════════════════════════════
@st.cache_data
def load_data(path="dataterbaru.csv"):
    try:
        df = pd.read_csv(path, sep=None, engine='python', on_bad_lines='skip')
        return df, None
    except Exception as e:
        return None, str(e)

df_raw, err = load_data()
if err or df_raw is None:
    st.error(f"❌ Gagal membaca CSV: {err}")
    st.stop()

# ════════════════════════════════════════════════════════════════════
# 2. NORMALISASI
# ════════════════════════════════════════════════════════════════════
@st.cache_data
def normalize_data(df):
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df = df.rename(columns={
        'badan publik': 'badan',
        'provinsi/kabupaten/kota': 'region',
        'provinsi': 'region',
        'kabupaten/kota': 'region',
    })

    required = ['badan', 'region', 'tahun', 'kualifikasi']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return None, [f"Kolom tidak ditemukan: {missing}"]

    df = df[required].copy()

    # ── Nama badan: bersihkan untuk tampilan ──────────────────────
    def clean_display(name):
        if not isinstance(name, str):
            return ""
        name = re.sub(r'\s+', ' ', name)
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        return name.strip()

    # ── Region: seragamkan, strip "Kabupaten"/"Kota" prefix ───────
    def clean_region(r):
        if not isinstance(r, str):
            return "Unknown"
        r = re.sub(r'^(Kabupaten|Kota)\s+', '', r.strip(), flags=re.IGNORECASE)
        return r.strip().title() or "Unknown"

    # ── Kunci matching: strip wilayah dari nama badan ─────────────
    # INI INTI PERBAIKAN:
    # "Dinas Sosial Kabupaten Badung" + region=Badung → "dinas sosial"
    # "dinas sosial"                  + region=Badung → "dinas sosial"
    # Keduanya menghasilkan key identik → akan di-cluster menjadi satu.
    def make_key(name, region):
        if not isinstance(name, str):
            return ""
        key = name.lower()
        key = re.sub(r'\s+', ' ', key)
        key = re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
        # Hapus kata generik lokasi
        key = re.sub(r'\b(kabupaten|kota|provinsi)\b', '', key)
        # Hapus nama wilayah yang ada di kolom region
        if region and region != "Unknown":
            reg = region.lower().strip()
            key = re.sub(r'\b' + re.escape(reg) + r'\b', '', key)
        # Hapus semua nama wilayah Bali yang diketahui
        for w in WILAYAH_BALI:
            key = re.sub(r'\b' + re.escape(w) + r'\b', '', key)
        # Ekspansi singkatan setelah strip wilayah
        for pat, rep in SINGKATAN_MAP.items():
            key = re.sub(pat, rep, key)
        key = re.sub(r'\s+', ' ', key).strip()
        return key

    df['badan'] = df['badan'].astype(str).apply(clean_display)
    df['region'] = df['region'].apply(clean_region)
    df['badan_key'] = df.apply(lambda r: make_key(r['badan'], r['region']), axis=1)

    # ── Kualifikasi ────────────────────────────────────────────────
    kual_map = {
        'informatif': 'Informatif',
        'menuju informatif': 'Menuju Informatif',
        'cukup informatif': 'Cukup Informatif',
        'kurang informatif': 'Kurang Informatif',
        'tidak informatif': 'Tidak Informatif',
    }
    df['kualifikasi'] = (
        df['kualifikasi'].astype(str).str.strip().str.lower()
        .map(kual_map).fillna('Tidak Diketahui')
    )

    # ── Tahun ──────────────────────────────────────────────────────
    df['tahun'] = pd.to_numeric(df['tahun'], errors='coerce')
    n_bad = df['tahun'].isna().sum()
    df = df.dropna(subset=['tahun'])
    df['tahun'] = df['tahun'].astype(int)

    warnings = [f"⚠️ {n_bad} baris dibuang (tahun tidak valid)."] if n_bad else []
    return df, warnings

df, warnings = normalize_data(df_raw)
if df is None:
    st.error(warnings[0])
    st.stop()

# ════════════════════════════════════════════════════════════════════
# 3. ENTITY RESOLUTION
# Karena make_key sudah strip wilayah, dua nama yang sama fungsinya
# di wilayah yang sama akan punya key identik atau sangat mirip.
# Union-Find menggabungkan cluster tersebut.
# ════════════════════════════════════════════════════════════════════
@st.cache_data
def entity_resolution(df, threshold=0.85):

    def ratio(a, b):
        return SequenceMatcher(None, a, b).ratio()

    # Unik per (badan_key, region) — ini unit pencocokan
    unique = (
        df[['badan_key', 'badan', 'region']]
        .drop_duplicates(subset=['badan_key', 'region'])
        .reset_index(drop=True)
    )

    parent = list(range(len(unique)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    keys    = unique['badan_key'].tolist()
    regions = unique['region'].tolist()
    names   = unique['badan'].tolist()

    for i in range(len(unique)):
        for j in range(i + 1, len(unique)):
            # Hanya bandingkan dalam wilayah yang sama
            if regions[i] != regions[j]:
                continue

            ka, kb = keys[i], keys[j]

            # Key identik → pasti sama
            if ka == kb:
                union(i, j)
                continue

            # Substring match dengan filter rasio panjang
            mn = min(len(ka), len(kb))
            mx = max(len(ka), len(kb))
            if mn >= 8 and mx > 0 and (ka in kb or kb in ka):
                if mn / mx >= 0.55:
                    union(i, j)
                    continue

            # Fuzzy match
            if ratio(ka, kb) >= threshold:
                union(i, j)

    # Bangun canonical map: key → nama canonical (terpanjang di cluster)
    clusters = defaultdict(list)
    for i in range(len(unique)):
        clusters[find(i)].append(i)

    # Mapping: (badan_key, region) → canonical_name
    canonical_map = {}
    for group in clusters.values():
        group_names = [names[i] for i in group]
        canonical = max(group_names, key=len)
        for i in group:
            canonical_map[(keys[i], regions[i])] = canonical

    df = df.copy()
    df['badan_canonical'] = df.apply(
        lambda r: canonical_map.get((r['badan_key'], r['region']), r['badan']),
        axis=1
    )
    return df

df = entity_resolution(df)

# Hapus duplikat sejati
df = df.drop_duplicates(subset=['badan_canonical', 'region', 'tahun'])

# ════════════════════════════════════════════════════════════════════
# 4. SUMMARY
# ════════════════════════════════════════════════════════════════════
@st.cache_data
def build_summary(df):
    rows = []
    for (nama, region), g in df.groupby(['badan_canonical', 'region']):
        tahun_unik  = sorted(g['tahun'].unique())
        info_tahun  = sorted(g.loc[g['kualifikasi'] == 'Informatif', 'tahun'].unique())
        last_kual   = g.sort_values('tahun').iloc[-1]['kualifikasi']
        rows.append({
            'Nama Badan Publik': nama,
            'Wilayah':           region,
            'Jumlah Monev':      len(tahun_unik),
            'Tahun Monev':       ', '.join(map(str, tahun_unik)),
            'Tahun Informatif':  ', '.join(map(str, info_tahun)) if info_tahun else '-',
            'Status Terakhir':   last_kual,
        })
    return (
        pd.DataFrame(rows)
        .sort_values(['Wilayah', 'Nama Badan Publik'])
        .reset_index(drop=True)
    )

summary_df = build_summary(df)

# ════════════════════════════════════════════════════════════════════
# 5. KPI HEADER
# ════════════════════════════════════════════════════════════════════
st.markdown("## 📊 MONEV MONITOR")
for w in warnings:
    st.warning(w)

tahun_list = sorted(df['tahun'].unique(), reverse=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("🏛️ Total Badan Publik",  f"{summary_df['Nama Badan Publik'].nunique():,}")
c2.metric("📋 Total Evaluasi",       f"{len(df):,}")
c3.metric("🟢 Informatif Rate",      f"{(df['kualifikasi']=='Informatif').mean()*100:.1f}%")
c4.metric("🏆 Pernah Informatif",    f"{(summary_df['Tahun Informatif']!='-').sum():,}")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 6. TABS
# ════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Ringkasan", "📈 Tren & Distribusi", "🗂️ Data Mentah", "🏛️ Profil Badan"
])

# ── TAB 1: RINGKASAN ─────────────────────────────────────────────
with tab1:
    st.subheader("Ringkasan per Badan Publik")

    f1, f2, f3 = st.columns(3)
    with f1:
        wil_sel    = st.selectbox("Filter Wilayah", ["Semua"] + sorted(summary_df['Wilayah'].unique()))
    with f2:
        status_sel = st.selectbox("Filter Status Terakhir", ["Semua"] + KUALIFIKASI_ORDER)
    with f3:
        info_sel   = st.selectbox("Riwayat Informatif", ["Semua", "Pernah", "Belum Pernah"])

    cari = st.text_input("🔍 Cari nama badan publik")

    filt = summary_df.copy()
    if wil_sel    != "Semua":     filt = filt[filt['Wilayah'] == wil_sel]
    if status_sel != "Semua":     filt = filt[filt['Status Terakhir'] == status_sel]
    if info_sel   == "Pernah":    filt = filt[filt['Tahun Informatif'] != '-']
    if info_sel   == "Belum Pernah": filt = filt[filt['Tahun Informatif'] == '-']
    if cari:
        filt = filt[filt['Nama Badan Publik'].str.contains(cari, case=False, na=False)]

    disp = filt.copy()
    disp['Status Terakhir'] = disp['Status Terakhir'].apply(
        lambda x: f"{KUAL_ICON.get(x,'⚪')} {x}"
    )
    disp = disp.reset_index(drop=True)
    disp.index += 1

    st.dataframe(disp, use_container_width=True)
    st.caption(f"Menampilkan {len(filt):,} dari {len(summary_df):,} badan publik")
    st.download_button(
        "⬇️ Download Ringkasan CSV",
        filt.to_csv(index=False).encode('utf-8'),
        "ringkasan_monev.csv", "text/csv"
    )

# ── TAB 2: TREN & DISTRIBUSI ──────────────────────────────────────
with tab2:
    st.subheader("Distribusi Kualifikasi per Tahun")
    dist = df.groupby(['tahun', 'kualifikasi']).size().reset_index(name='Jumlah')
    pivot = dist.pivot(index='tahun', columns='kualifikasi', values='Jumlah').fillna(0)
    pivot = pivot[[c for c in KUALIFIKASI_ORDER if c in pivot.columns]]
    st.bar_chart(pivot, use_container_width=True)

    st.subheader("Distribusi per Wilayah")
    thn_viz = st.selectbox("Pilih Tahun", tahun_list, key="viz_thn")
    dist_wil = (
        df[df['tahun'] == thn_viz]
        .groupby(['region', 'kualifikasi']).size().reset_index(name='Jumlah')
    )
    pivot_wil = dist_wil.pivot(index='region', columns='kualifikasi', values='Jumlah').fillna(0)
    pivot_wil = pivot_wil[[c for c in KUALIFIKASI_ORDER if c in pivot_wil.columns]]
    st.bar_chart(pivot_wil, use_container_width=True)

# ── TAB 3: DATA MENTAH ────────────────────────────────────────────
with tab3:
    st.subheader("Data Mentah (setelah normalisasi & entity resolution)")

    d1, d2 = st.columns(2)
    with d1:
        thn_raw = st.selectbox("Filter Tahun", ["Semua"] + tahun_list, key="raw_thn")
    with d2:
        reg_raw = st.selectbox("Filter Wilayah", ["Semua"] + sorted(df['region'].unique()), key="raw_reg")

    raw = df.copy()
    if thn_raw != "Semua": raw = raw[raw['tahun'] == thn_raw]
    if reg_raw != "Semua": raw = raw[raw['region'] == reg_raw]

    disp_raw = raw[['badan_canonical', 'region', 'tahun', 'kualifikasi']].rename(columns={
        'badan_canonical': 'Nama Badan Publik', 'region': 'Wilayah',
        'tahun': 'Tahun', 'kualifikasi': 'Kualifikasi',
    }).reset_index(drop=True)
    disp_raw.index += 1
    st.dataframe(disp_raw, use_container_width=True)
    st.caption(f"{len(disp_raw):,} records")

# ── TAB 4: PROFIL BADAN ───────────────────────────────────────────
with tab4:
    st.subheader("Profil Detail Badan Publik")

    p1, p2 = st.columns([1, 2])
    with p1:
        wil_p = st.selectbox("Wilayah", ["Semua"] + sorted(df['region'].unique()), key="prof_wil")
    pool = summary_df if wil_p == "Semua" else summary_df[summary_df['Wilayah'] == wil_p]
    with p2:
        badan_sel = st.selectbox("Badan Publik", sorted(pool['Nama Badan Publik'].unique()), key="prof_badan")

    if badan_sel:
        row   = summary_df[summary_df['Nama Badan Publik'] == badan_sel].iloc[0]
        bdata = df[df['badan_canonical'] == badan_sel].sort_values('tahun')

        st.markdown(f"### 🏛️ {badan_sel}")
        st.markdown(f"**Wilayah:** {row['Wilayah']}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Jumlah Monev",    row['Jumlah Monev'])
        m2.metric("Tahun Monev",     row['Tahun Monev'])
        m3.metric("Tahun Informatif",row['Tahun Informatif'])
        m4.metric("Status Terakhir", f"{KUAL_ICON.get(row['Status Terakhir'],'⚪')} {row['Status Terakhir']}")

        hist = bdata[['tahun', 'kualifikasi']].rename(
            columns={'tahun': 'Tahun', 'kualifikasi': 'Kualifikasi'}
        ).reset_index(drop=True)
        hist['Kualifikasi'] = hist['Kualifikasi'].apply(
            lambda x: f"{KUAL_ICON.get(x,'⚪')} {x}"
        )
        st.dataframe(hist, use_container_width=True, hide_index=True)

        # Tampilkan varian nama asli yang digabungkan
        variants = sorted(bdata['badan'].unique())
        if len(variants) > 1:
            with st.expander(f"ℹ️ {len(variants)} varian nama digabungkan (Entity Resolution)"):
                for v in variants:
                    st.write(f"• {v}")

st.divider()
st.caption("🔧 Region-Aware Normalisasi · Fuzzy Matching · Entity Resolution | MONEV MONITOR")