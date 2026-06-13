"""
Healthii – Pricing
Preisvergleich / EK-Preispflege.
"""

import base64
import io
import os
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from purchasing_agent import upload_bytes_to_drive

# ─── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Pricing | Healthii",
    page_icon="💰",
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
[data-baseweb="tab-highlight"] { background-color: #0D9488 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #0D9488 !important; }
button[data-baseweb="tab"]:hover { color: #0D9488 !important; }
</style>
""", unsafe_allow_html=True)

# ─── Google Drive verbinden ────────────────────────────────────────────────────

def is_cloud():
    try:
        return "GOOGLE_TOKEN" in st.secrets
    except Exception:
        return False

def verbinde_drive():
    """Baut pro Rerun eine frische Drive-Verbindung auf.

    httplib2 ist nicht thread-safe und persistente Verbindungen werden bei
    Leerlauf serverseitig geschlossen. Eine über @st.cache_resource/session_state
    geteilte Verbindung führt deshalb zu BrokenPipeError. Die eigentlichen
    Drive-Abfragen sind über @st.cache_data(ttl=…) gepuffert, daher ist der
    Neuaufbau pro Rerun praktisch kostenlos."""
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

# ─── Konstanten ────────────────────────────────────────────────────────────────

PRICING_FOLDER_NAME = "Pricing"
CHANNEL_COLS = ["channelPrice1", "channelPrice2", "channelPrice3", "channelPrice4", "channelPrice5"]
CHANNEL_LABELS = ["Channel 1", "Channel 2", "Channel 3", "Channel 4", "Channel 5"]

# Preis-Cluster nach Preishöhe (EUR)
PRICE_EDGES = [0, 10, 25, 50, 100, float("inf")]
PRICE_LABELS = ["0–10 €", "10–25 €", "25–50 €", "50–100 €", "100+ €"]

# Veränderungs-Cluster (prozentuale Preisänderung zwischen zwei Zeitpunkten)
def change_cluster(pct):
    if pd.isna(pct):
        return "unbekannt"
    if pct > 0.10:
        return "stark gestiegen"
    if pct > 0.02:
        return "gestiegen"
    if pct >= -0.02:
        return "stabil"
    if pct >= -0.10:
        return "gesunken"
    return "stark gesunken"

CHANGE_ORDER = ["stark gestiegen", "gestiegen", "stabil", "gesunken", "stark gesunken"]

# ─── Drive: Ordner / Snapshots ─────────────────────────────────────────────────

def _waehle_ordner(_drive, files):
    """Bei mehreren gleichnamigen Ordnern: den mit Inhalt bevorzugen, sonst den ältesten."""
    if len(files) == 1:
        return files[0]["id"]
    for f in files:
        kids = _drive.files().list(
            q=f"'{f['id']}' in parents and trashed=false",
            fields="files(id)", pageSize=1,
        ).execute(num_retries=3).get("files", [])
        if kids:
            return f["id"]
    return files[0]["id"]


@st.cache_data(ttl=120, show_spinner=False)
def get_pricing_folder_id(_drive):
    """ID des Ordners 'Pricing' (legt ihn an falls nötig)."""
    q = (f"name='{PRICING_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false")
    res = _drive.files().list(q=q, fields="files(id)", orderBy="createdTime",
                              pageSize=10).execute(num_retries=3)
    files = res.get("files", [])
    if files:
        return _waehle_ordner(_drive, files)
    folder = _drive.files().create(
        body={"name": PRICING_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute(num_retries=3)
    return folder["id"]


def parse_date_from_filename(filename: str):
    """Erkennt das Datum DDMMYY am Ende des Dateinamens (z. B. quote_prices_110626.csv → 11.06.2026)."""
    m = re.search(r"(\d{2})(\d{2})(\d{2})(?:\.csv)?$", filename)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(2000 + y, mo, d)
    except ValueError:
        return None


def _download_bytes(_drive, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = dl.next_chunk(num_retries=3)
    buf.seek(0)
    return buf.getvalue()


@st.cache_data(ttl=60, show_spinner=False)
def list_snapshots(_drive):
    """Listet alle in Drive gespeicherten Snapshots.
    Rückgabe: dict {iso_datum: {quote_id, channel_id}} – sortiert."""
    folder_id = get_pricing_folder_id(_drive)
    res = _drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name)", pageSize=1000,
    ).execute(num_retries=3)
    snaps = {}
    for f in res.get("files", []):
        d = parse_date_from_filename(f["name"])
        if d is None:
            continue
        key = d.isoformat()
        entry = snaps.setdefault(key, {"quote_id": None, "channel_id": None})
        if f["name"].lower().startswith("quote"):
            entry["quote_id"] = f["id"]
        elif f["name"].lower().startswith("channel"):
            entry["channel_id"] = f["id"]
    return dict(sorted(snaps.items()))


def parse_quote_bytes(data: bytes) -> pd.DataFrame:
    """quote_prices CSV → DataFrame[productId, quote] (Preis in EUR)."""
    df = pd.read_csv(io.BytesIO(data), sep="|", dtype={"productId": str})
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"quote_price": "quote"})
    df["quote"] = pd.to_numeric(df["quote"], errors="coerce") / 100.0
    df = df[(df["quote"].notna()) & (df["quote"] > 0)]
    return df[["productId", "quote"]].drop_duplicates("productId")


def parse_channel_bytes(data: bytes) -> pd.DataFrame:
    """channel_prices CSV → DataFrame[productId, channelPrice1..5] (Preise in EUR)."""
    df = pd.read_csv(io.BytesIO(data), sep="|", dtype={"productId": str})
    df.columns = df.columns.str.strip()
    for c in CHANNEL_COLS:
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
        df.loc[df[c] <= 0, c] = pd.NA
    return df[["productId"] + CHANNEL_COLS].drop_duplicates("productId")


@st.cache_data(ttl=60, show_spinner="Snapshot wird geladen …")
def load_snapshot(_drive, iso_datum: str) -> pd.DataFrame:
    """Lädt Quote- und Channel-Preise eines Zeitpunkts und merged sie auf productId."""
    snaps = list_snapshots(_drive)
    entry = snaps.get(iso_datum)
    if not entry:
        return pd.DataFrame()
    quote_df = parse_quote_bytes(_download_bytes(_drive, entry["quote_id"])) if entry["quote_id"] else \
        pd.DataFrame(columns=["productId", "quote"])
    chan_df = parse_channel_bytes(_download_bytes(_drive, entry["channel_id"])) if entry["channel_id"] else \
        pd.DataFrame(columns=["productId"] + CHANNEL_COLS)
    merged = quote_df.merge(chan_df, on="productId", how="outer")
    return merged


def assign_price_cluster(series_eur: pd.Series) -> pd.Series:
    return pd.cut(series_eur, bins=PRICE_EDGES, labels=PRICE_LABELS, right=False)


def fmt_date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d.%m.%Y")


# ─── Seiteninhalt ──────────────────────────────────────────────────────────────

st.title("💰 Pricing")
st.caption("Preisanalyse – Quote-Preise vs. Channel-Preise, geclustert nach Preishöhe")

if drive is None:
    st.error("Keine Verbindung zu Google Drive. Bitte Anmeldedaten prüfen.")
    st.stop()

# ════════════════════════════════════════════════════════════════════════════════
# SIDEBAR – Preisdateien hochladen
# ════════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("📥 Preise hochladen")
    st.caption("Quote- und Channel-Preisdatei eines Zeitpunkts. Datum wird aus dem Dateinamen erkannt.")

    quote_file = st.file_uploader("Quote-Preise (CSV)", type=["csv"], key="up_quote")
    channel_file = st.file_uploader("Channel-Preise (CSV)", type=["csv"], key="up_channel")

    # Datum vorbelegen aus Dateinamen
    erkanntes_datum = None
    for f in (quote_file, channel_file):
        if f is not None:
            erkanntes_datum = parse_date_from_filename(f.name) or erkanntes_datum

    snap_datum = st.date_input(
        "Datum des Snapshots", value=erkanntes_datum or date.today(), format="DD.MM.YYYY"
    )

    # Vorschau
    if quote_file is not None:
        try:
            q_prev = parse_quote_bytes(quote_file.getvalue())
            st.success(f"Quote: {len(q_prev):,} Produkte".replace(",", "."))
        except Exception as e:
            st.error(f"Quote-Datei nicht lesbar: {e}")
    if channel_file is not None:
        try:
            ch_prev = parse_channel_bytes(channel_file.getvalue())
            abdeckung = {lbl: int(ch_prev[c].notna().sum()) for c, lbl in zip(CHANNEL_COLS, CHANNEL_LABELS)}
            st.success(f"Channel: {len(ch_prev):,} Produkte".replace(",", "."))
            st.caption("Abdeckung: " + " · ".join(f"{k}: {v:,}".replace(",", ".") for k, v in abdeckung.items()))
        except Exception as e:
            st.error(f"Channel-Datei nicht lesbar: {e}")

    if st.button("💾 In Drive speichern", type="primary", use_container_width=True,
                 disabled=(quote_file is None and channel_file is None)):
        folder_id = get_pricing_folder_id(drive)
        ddmmyy = snap_datum.strftime("%d%m%y")
        gespeichert = []
        if quote_file is not None:
            upload_bytes_to_drive(drive, quote_file.getvalue(), f"quote_prices_{ddmmyy}.csv", folder_id, "text/csv")
            gespeichert.append("Quote-Preise")
        if channel_file is not None:
            upload_bytes_to_drive(drive, channel_file.getvalue(), f"channel_prices_{ddmmyy}.csv", folder_id, "text/csv")
            gespeichert.append("Channel-Preise")
        list_snapshots.clear()
        load_snapshot.clear()
        st.success(f"Gespeichert ({snap_datum.strftime('%d.%m.%Y')}): {', '.join(gespeichert)}")

    # Vorhandene Snapshots anzeigen
    st.divider()
    st.markdown("##### Gespeicherte Zeitpunkte")
    _snaps = list_snapshots(drive)
    if not _snaps:
        st.caption("Noch keine Snapshots gespeichert.")
    else:
        rows = [{
            "Datum": fmt_date(k),
            "Quote": "✅" if v["quote_id"] else "—",
            "Channel": "✅" if v["channel_id"] else "—",
        } for k, v in _snaps.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

tab_snap, tab_cmp, tab_sales = st.tabs(
    ["📊 Momentaufnahme", "🔀 Vergleich", "🛒 Abverkauf"]
)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 – Momentaufnahme (ein Zeitpunkt)
# ════════════════════════════════════════════════════════════════════════════════
with tab_snap:
    snaps = list_snapshots(drive)
    if not snaps:
        st.info("Noch keine Daten vorhanden. Bitte links in der Seitenleiste Preise hochladen.")
    else:
        keys = list(snaps.keys())
        sel = st.selectbox("Zeitpunkt", keys, index=len(keys) - 1,
                           format_func=fmt_date, key="snap_sel")
        df = load_snapshot(drive, sel).copy()
        df = df[df["quote"].notna()]  # Cluster basiert auf Quote-Preis

        if df.empty:
            st.warning("Für diesen Zeitpunkt sind keine Quote-Preise hinterlegt.")
        else:
            df["Cluster"] = assign_price_cluster(df["quote"])

            # KPIs: Produktzahl Quote + Anzahl je Channel-Preis
            cols = st.columns(1 + len(CHANNEL_COLS))
            cols[0].metric("Produkte (Quote)", f"{len(df):,}".replace(",", "."))
            for i, (c, lbl) in enumerate(zip(CHANNEL_COLS, CHANNEL_LABELS), start=1):
                cols[i].metric(lbl, f"{int(df[c].notna().sum()):,}".replace(",", "."))

            st.divider()

            # ── Channel-Vergleich gesamt ──
            st.markdown("##### Channel-Preise im Vergleich zum Quote-Preis")
            ch_rows = []
            for c, lbl in zip(CHANNEL_COLS, CHANNEL_LABELS):
                sub = df[df[c].notna()]
                if sub.empty:
                    ch_rows.append({"Channel": lbl, "Abdeckung": 0, "Ø Preis": None,
                                    "Ø Diff zu Quote": None, "Ø Diff %": None, "Anteil < Quote": None})
                    continue
                diff = sub[c] - sub["quote"]
                diff_pct = (diff / sub["quote"])
                ch_rows.append({
                    "Channel": lbl,
                    "Abdeckung": len(sub),
                    "Ø Preis": round(sub[c].mean(), 2),
                    "Ø Diff zu Quote": round(diff.mean(), 2),
                    "Ø Diff %": round(diff_pct.mean() * 100, 1),
                    "Anteil < Quote": round((sub[c] < sub["quote"]).mean() * 100, 1),
                })
            ch_df = pd.DataFrame(ch_rows)
            st.dataframe(
                ch_df, use_container_width=True, hide_index=True,
                column_config={
                    "Abdeckung": st.column_config.NumberColumn(format="%d"),
                    "Ø Preis": st.column_config.NumberColumn(format="%.2f €"),
                    "Ø Diff zu Quote": st.column_config.NumberColumn(format="%.2f €"),
                    "Ø Diff %": st.column_config.NumberColumn(format="%.1f %%"),
                    "Anteil < Quote": st.column_config.NumberColumn(format="%.1f %%"),
                },
            )

            st.divider()

            # ── Cluster-Übersicht: Ø prozentuale Differenz Channel vs. Quote je Cluster ──
            st.markdown("##### Ø Differenz zum Quote-Preis je Preis-Cluster (%)")
            tmp = df.copy()
            for c in CHANNEL_COLS:
                tmp[c + "_pct"] = (tmp[c] - tmp["quote"]) / tmp["quote"] * 100
            g = tmp.groupby("Cluster", observed=False)
            cl = pd.DataFrame({"Anzahl": g.size()})
            for c, lbl in zip(CHANNEL_COLS, CHANNEL_LABELS):
                cl[lbl] = g[c + "_pct"].mean().round(1)
            cl = cl.reset_index()
            st.dataframe(
                cl, use_container_width=True, hide_index=True,
                column_config={
                    "Anzahl": st.column_config.NumberColumn(format="%d"),
                    **{lbl: st.column_config.NumberColumn(format="%.1f %%") for lbl in CHANNEL_LABELS},
                },
            )
            st.caption("Negativ = Channel im Schnitt günstiger als Quote, positiv = teurer.")

            # Verteilung der Produkte über die Cluster
            st.markdown("##### Anzahl Produkte je Preis-Cluster")
            verteilung = df.groupby("Cluster", observed=False).size().reindex(PRICE_LABELS).fillna(0)
            st.bar_chart(verteilung, color="#0D9488")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 – Vergleich (zwei Zeitpunkte)
# ════════════════════════════════════════════════════════════════════════════════
with tab_cmp:
    snaps = list_snapshots(drive)
    if len(snaps) < 2:
        st.info("Für einen Vergleich werden mindestens zwei gespeicherte Zeitpunkte benötigt.")
    else:
        keys = list(snaps.keys())
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            von = st.selectbox("Von", keys, index=len(keys) - 2, format_func=fmt_date, key="cmp_von")
        with c2:
            bis = st.selectbox("Bis", keys, index=len(keys) - 1, format_func=fmt_date, key="cmp_bis")
        with c3:
            metrik = st.selectbox("Preisart", ["Quote"] + CHANNEL_LABELS, key="cmp_metrik")

        col_map = {"Quote": "quote", **{lbl: c for lbl, c in zip(CHANNEL_LABELS, CHANNEL_COLS)}}
        col = col_map[metrik]

        if von == bis:
            st.warning("Bitte zwei unterschiedliche Zeitpunkte wählen.")
        else:
            da = load_snapshot(drive, von)[["productId", col]].rename(columns={col: "preis_a"})
            db = load_snapshot(drive, bis)[["productId", col]].rename(columns={col: "preis_b"})
            m = da.merge(db, on="productId", how="outer")

            beide = m[(m["preis_a"].notna()) & (m["preis_b"].notna())].copy()
            neu = m[(m["preis_a"].isna()) & (m["preis_b"].notna())]
            entfernt = m[(m["preis_a"].notna()) & (m["preis_b"].isna())]

            if beide.empty:
                st.warning("Keine in beiden Zeitpunkten vergleichbaren Produkte für diese Preisart.")
            else:
                beide["abs"] = beide["preis_b"] - beide["preis_a"]
                beide["pct"] = beide["abs"] / beide["preis_a"]
                beide["Cluster"] = assign_price_cluster(beide["preis_a"])
                beide["Veränderung"] = beide["pct"].apply(change_cluster)

                # KPIs
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Vergleichbar", f"{len(beide):,}".replace(",", "."))
                k2.metric("Ø Änderung", f"{beide['pct'].mean() * 100:+.1f} %")
                k3.metric("Neu", f"{len(neu):,}".replace(",", "."))
                k4.metric("Entfernt", f"{len(entfernt):,}".replace(",", "."))

                st.caption(f"Vergleich {metrik}: {fmt_date(von)} → {fmt_date(bis)}")
                st.divider()

                # ── Veränderung je Preis-Cluster ──
                st.markdown("##### Veränderung je Preis-Cluster")
                beide["_up"] = beide["pct"] > 0.02
                beide["_down"] = beide["pct"] < -0.02
                g = beide.groupby("Cluster", observed=False)
                cl = pd.DataFrame({
                    "Anzahl": g.size(),
                    "Ø Preis vorher": g["preis_a"].mean().round(2),
                    "Ø Preis nachher": g["preis_b"].mean().round(2),
                    "Ø Änderung %": (g["pct"].mean() * 100).round(1),
                    "gestiegen": g["_up"].sum().astype(int),
                    "gesunken": g["_down"].sum().astype(int),
                }).reset_index()
                st.dataframe(
                    cl, use_container_width=True, hide_index=True,
                    column_config={
                        "Anzahl": st.column_config.NumberColumn(format="%d"),
                        "Ø Preis vorher": st.column_config.NumberColumn(format="%.2f €"),
                        "Ø Preis nachher": st.column_config.NumberColumn(format="%.2f €"),
                        "Ø Änderung %": st.column_config.NumberColumn(format="%.1f %%"),
                    },
                )

                # ── Verteilung der Veränderungs-Cluster ──
                st.markdown("##### Verteilung der Preisänderungen")
                vt = beide["Veränderung"].value_counts().reindex(CHANGE_ORDER).fillna(0)
                st.bar_chart(vt, color="#0D9488")

                st.divider()

                # ── Stärkste Bewegungen ──
                st.markdown("##### Stärkste Veränderungen")
                anzahl = st.slider("Anzahl je Richtung", 5, 50, 15, step=5, key="cmp_top")

                def movers_table(sub):
                    out = sub[["productId", "preis_a", "preis_b", "abs", "pct", "Cluster"]].copy()
                    out["pct"] = (out["pct"] * 100).round(1)
                    out["abs"] = out["abs"].round(2)
                    out["preis_a"] = out["preis_a"].round(2)
                    out["preis_b"] = out["preis_b"].round(2)
                    return out.rename(columns={
                        "productId": "PZN", "preis_a": "Vorher", "preis_b": "Nachher",
                        "abs": "Δ €", "pct": "Δ %",
                    })

                colcfg = {
                    "Vorher": st.column_config.NumberColumn(format="%.2f €"),
                    "Nachher": st.column_config.NumberColumn(format="%.2f €"),
                    "Δ €": st.column_config.NumberColumn(format="%.2f €"),
                    "Δ %": st.column_config.NumberColumn(format="%.1f %%"),
                }
                cu, cd = st.columns(2)
                with cu:
                    st.markdown("**📈 Stärkste Steigerungen**")
                    st.dataframe(movers_table(beide.nlargest(anzahl, "pct")),
                                 use_container_width=True, hide_index=True, column_config=colcfg)
                with cd:
                    st.markdown("**📉 Stärkste Senkungen**")
                    st.dataframe(movers_table(beide.nsmallest(anzahl, "pct")),
                                 use_container_width=True, hide_index=True, column_config=colcfg)

                # ── Export ──
                st.divider()
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    cl.to_excel(w, index=False, sheet_name="Cluster")
                    movers_table(beide.sort_values("pct", ascending=False)).to_excel(
                        w, index=False, sheet_name="Alle Änderungen")
                st.download_button(
                    "📥 Vergleich als Excel",
                    data=buf.getvalue(),
                    file_name=f"pricing_vergleich_{metrik}_{von}_{bis}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 – Abverkauf (später)
# ════════════════════════════════════════════════════════════════════════════════
with tab_sales:
    st.subheader("Abverkaufsdaten")
    st.info(
        "Dieser Bereich ist für die Abverkaufsanalyse vorgesehen: Schnelldreher vs. Langsamdreher "
        "sowie wichtige Produkte, die durch Preisänderungen gewonnen oder verloren wurden.\n\n"
        "Sobald du die Abverkaufsdaten bereitstellst, wird er aktiviert."
    )
