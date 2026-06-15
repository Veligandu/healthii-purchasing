"""
Healthii – Masterdatei-Analyse
Vergleicht die Channel-Preise aus der Masterdatei (channel_price_1..5) mit den
Channel-Preisen aus dem Channel-Snapshot (Momentaufnahme) je Zeitpunkt.
"""

import base64
import io
import os

import pandas as pd
import streamlit as st

import pricing_lib as pl
from pricing_lib import (
    CHANNEL_COLS, CHANNEL_LABELS, MASTER_CHANNEL_COLS, fmt_date,
)

# ─── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Masterdatei-Analyse | Healthii",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Passwortschutz (identisch mit Hauptseite) ────────────────────────────────

def check_password():
    try:
        app_password = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        app_password = None
    if not app_password:
        return True
    if st.session_state.get("authenticated"):
        return True

    _logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png")
    _logo_b64 = ""
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _f:
            _logo_b64 = base64.b64encode(_f.read()).decode()

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #F3F4F6; }
    [data-testid="stMain"]             { background: #F3F4F6; }
    [data-testid="stSidebar"]          { display: none; }
    [data-testid="stForm"] {
        background: white;
        border: 1px solid #E5E7EB !important;
        border-radius: 16px;
        padding: 32px !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    }
    </style>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
        if _logo_b64:
            st.markdown(
                f"<div style='text-align:center;margin-bottom:8px;'>"
                f"<img src='data:image/png;base64,{_logo_b64}' style='height:44px;' /></div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            "<div style='text-align:center;margin-bottom:20px;'>"
            "<span style='background:#F0FDF9;color:#0D9488;font-size:10px;font-weight:600;"
            "padding:3px 10px;border-radius:20px;letter-spacing:0.8px;"
            "border:1px solid #CCFBF1;'>PURCHASING-AGENT</span></div>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            st.markdown(
                "<h3 style='margin:0 0 4px;color:#111827;font-size:20px;font-weight:600;'>Anmelden</h3>"
                "<p style='color:#6B7280;font-size:14px;margin:0 0 16px;'>"
                "Bitte melde dich an um fortzufahren.</p>",
                unsafe_allow_html=True,
            )
            pw = st.text_input("Passwort", type="password",
                               label_visibility="collapsed",
                               placeholder="Passwort eingeben …")
            submitted = st.form_submit_button("Anmelden", use_container_width=True, type="primary")
        if submitted:
            if pw == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                with col:
                    st.error("Falsches Passwort. Bitte erneut versuchen.")
    st.stop()

check_password()

# ─── Styling ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
[data-testid="stAppViewContainer"] { background: #FFFFFF; }
[data-testid="stMain"] { background: #FFFFFF; }
[data-testid="stSidebar"] { background: #F9FAFB; border-right: 1px solid #E5E7EB; }
h1 { color: #111827 !important; font-weight: 700 !important; font-size: 2rem !important; }
h2 { color: #111827 !important; font-weight: 600 !important; }
h3 { color: #374151 !important; font-weight: 600 !important; }
.stButton > button { border-radius: 8px; font-weight: 500; font-size: 14px; border: 1px solid #D1D5DB; background: #FFFFFF; color: #374151; }
.stButton > button:hover { border-color: #0D9488; color: #0D9488; background: #F0FDF9; }
.stButton > button[kind="primary"] { background: #0D9488; color: white; border: none; }
.stButton > button[kind="primary"]:hover { background: #0B7A70; }
.stDownloadButton > button { background: #0D9488; color: white; border: none; border-radius: 8px; font-weight: 500; }
.stDownloadButton > button:hover { background: #0B7A70; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border: 1px solid #E5E7EB; border-radius: 10px; overflow: hidden; }
div[data-testid="metric-container"] { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
</style>
""", unsafe_allow_html=True)

# ─── Google Drive ────────────────────────────────────────────────────────────

def verbinde_drive():
    """Frische Drive-Verbindung pro Rerun (siehe pricing_lib / 3_Pricing.py)."""
    try:
        import sys
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _base not in sys.path:
            sys.path.insert(0, _base)
        from purchasing_agent import get_services
        _, drive = get_services()
        return drive
    except Exception:
        return None

drive = verbinde_drive()

@st.cache_data(ttl=60, show_spinner=False)
def list_snapshots(_drive):
    return pl.list_snapshots(_drive)

@st.cache_data(ttl=60, show_spinner="Masterdatei wird geladen …")
def load_master(_drive, iso_datum):
    return pl.load_master(_drive, iso_datum)

@st.cache_data(ttl=60, show_spinner="Channel-Preise werden geladen …")
def load_channel(_drive, iso_datum):
    return pl.load_channel(_drive, iso_datum)

# ─── Seiteninhalt ──────────────────────────────────────────────────────────────

st.title("🗂️ Masterdatei-Analyse")
st.caption("Abgleich der Channel-Preise aus der Masterdatei mit den Channel-Preisen aus der Momentaufnahme")

if drive is None:
    st.error("Keine Verbindung zu Google Drive. Bitte Anmeldedaten prüfen.")
    st.stop()

snaps = list_snapshots(drive)
# Nur Zeitpunkte mit Masterdatei UND Channel-Snapshot sind vergleichbar
vergleichbar = {k: v for k, v in snaps.items() if v.get("master_id") and v.get("channel_id")}

if not snaps:
    st.info("Noch keine Daten vorhanden. Bitte zuerst auf der Pricing-Seite Dateien hochladen.")
    st.stop()
if not vergleichbar:
    st.warning(
        "Für keinen Zeitpunkt liegen Master- **und** Channel-Datei vor. "
        "Beide werden für den Abgleich benötigt (Upload auf der Pricing-Seite)."
    )
    st.stop()

keys = list(vergleichbar.keys())
c1, c2 = st.columns([1, 1])
with c1:
    sel = st.selectbox("Zeitpunkt", keys, index=len(keys) - 1, format_func=fmt_date, key="ma_sel")
with c2:
    toleranz = st.number_input(
        "Toleranz für „abweichend“ (€)", min_value=0.0, max_value=1.0,
        value=0.01, step=0.01, format="%.2f",
        help="Abweichungen unterhalb dieses Betrags gelten als Übereinstimmung (Rundung).",
    )

master = load_master(drive, sel)
channel = load_channel(drive, sel)

if master.empty or channel.empty:
    st.warning("Master- oder Channel-Daten für diesen Zeitpunkt konnten nicht geladen werden.")
    st.stop()

# Zusatzspalten aus Master für Kontext
info_cols = [c for c in ["title", "manufacturer"] if c in master.columns]
m = master[["productId"] + MASTER_CHANNEL_COLS + info_cols].merge(
    channel[["productId"] + CHANNEL_COLS], on="productId", how="inner"
)

# Long-Format: je Produkt × Channel ein Master/Snapshot-Paar
teile = []
for mc, sc, lbl in zip(MASTER_CHANNEL_COLS, CHANNEL_COLS, CHANNEL_LABELS):
    sub = m[["productId"] + info_cols + [mc, sc]].copy()
    sub = sub.rename(columns={mc: "master", sc: "snapshot"})
    sub["Channel"] = lbl
    teile.append(sub)
long = pd.concat(teile, ignore_index=True)

both = long[long["master"].notna() & long["snapshot"].notna()].copy()
both["diff"] = both["master"] - both["snapshot"]
both["pct"] = both["diff"] / both["snapshot"] * 100
both["abweichend"] = both["diff"].abs() >= toleranz

# ── KPIs gesamt ──
k1, k2, k3, k4 = st.columns(4)
k1.metric("Produkte (in beiden)", f"{m['productId'].nunique():,}".replace(",", "."))
k2.metric("Preis-Paare verglichen", f"{len(both):,}".replace(",", "."))
k3.metric("Übereinstimmend", f"{int((~both['abweichend']).sum()):,}".replace(",", "."))
k4.metric("Abweichend", f"{int(both['abweichend'].sum()):,}".replace(",", "."))

st.divider()

# ── Zusammenfassung je Channel ──
st.markdown("##### Abgleich je Channel")
g = both.groupby("Channel", observed=False)
summary = pd.DataFrame({
    "Verglichen": g.size(),
    "Übereinstimmend": g["abweichend"].apply(lambda s: int((~s).sum())),
    "Abweichend": g["abweichend"].sum().astype(int),
    "Ø Δ €": g["diff"].mean().round(3),
    "Max |Δ| €": g["diff"].abs().max().round(2),
}).reindex(CHANNEL_LABELS).reset_index().rename(columns={"index": "Channel"})
summary["Abweichend %"] = (summary["Abweichend"] / summary["Verglichen"] * 100).round(1)
st.dataframe(
    summary, use_container_width=True, hide_index=True,
    column_config={
        "Verglichen": st.column_config.NumberColumn(format="%d"),
        "Übereinstimmend": st.column_config.NumberColumn(format="%d"),
        "Abweichend": st.column_config.NumberColumn(format="%d"),
        "Abweichend %": st.column_config.NumberColumn(format="%.1f %%"),
        "Ø Δ €": st.column_config.NumberColumn(format="%.3f €"),
        "Max |Δ| €": st.column_config.NumberColumn(format="%.2f €"),
    },
)
st.caption("Δ = Masterpreis − Snapshot-Preis (Momentaufnahme). Positiv = Master teurer als Snapshot.")

st.divider()

# ── Abweichungen im Detail ──
st.markdown("##### Abweichungen im Detail")
nur_abw = st.toggle("Nur Abweichungen anzeigen", value=True)
ch_filter = st.multiselect("Channel filtern", CHANNEL_LABELS, default=CHANNEL_LABELS)

tab = both[both["Channel"].isin(ch_filter)].copy()
if nur_abw:
    tab = tab[tab["abweichend"]]

if tab.empty:
    st.success("Keine Abweichungen für diese Auswahl. Master- und Snapshot-Preise stimmen überein.")
else:
    tab = tab.reindex(tab["diff"].abs().sort_values(ascending=False).index)
    out = tab[["productId"] + info_cols + ["Channel", "master", "snapshot", "diff", "pct"]].copy()
    out["master"] = out["master"].round(2)
    out["snapshot"] = out["snapshot"].round(2)
    out["diff"] = out["diff"].round(2)
    out["pct"] = out["pct"].round(1)
    rename = {"productId": "PZN", "title": "Titel", "manufacturer": "Hersteller",
              "master": "Master", "snapshot": "Snapshot", "diff": "Δ €", "pct": "Δ %"}
    out = out.rename(columns=rename)
    st.caption(f"{len(out):,} Zeilen".replace(",", "."))
    st.dataframe(
        out, use_container_width=True, hide_index=True,
        column_config={
            "Master": st.column_config.NumberColumn(format="%.2f €"),
            "Snapshot": st.column_config.NumberColumn(format="%.2f €"),
            "Δ €": st.column_config.NumberColumn(format="%.2f €"),
            "Δ %": st.column_config.NumberColumn(format="%.1f %%"),
        },
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, index=False, sheet_name="Zusammenfassung")
        out.to_excel(w, index=False, sheet_name="Abweichungen")
    st.download_button(
        "📥 Abgleich als Excel",
        data=buf.getvalue(),
        file_name=f"masterabgleich_{sel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
