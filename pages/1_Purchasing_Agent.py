"""
Healthii Purchasing Agent – Leopold
Streamlit Web App

Starten: streamlit run app.py
"""

import base64
import io
import os
from datetime import date

import pandas as pd
import streamlit as st

from purchasing_agent import (
    BASE_DIR,
    DRIVE_ROOT,
    berechne_bestellvorschlag,
    erstelle_bestellsheet,
    finde_letzte_bestellung_excel,
    get_or_create_folder,
    get_services,
    get_stammdaten_folder_id,
    get_week_folder_id,
    lade_letzte_bestellung,
    speichere_bestellhistorie,
    upload_bytes_to_drive,
    download_csv_from_drive,
)


def is_cloud() -> bool:
    """Erkennt ob die App in der Streamlit Cloud läuft."""
    try:
        return 'GOOGLE_TOKEN' in st.secrets
    except Exception:
        return False


def lade_letzte_bestellung_fuer_berechnung(drive=None):
    """Gibt letzte_bestellung_df für berechne_bestellvorschlag zurück.
    Bevorzugt Drive (Cloud), fällt auf lokale Datei zurück."""
    # Erst lokal versuchen
    pfad = finde_letzte_bestellung_excel()
    if pfad is not None:
        return lade_letzte_bestellung(pfad)
    # Cloud: aus Drive laden
    if drive is None:
        return None
    try:
        _, df_hist = finde_letzte_bestellung(drive)
        if df_hist is None:
            return None
        df_hist["Pzn"] = df_hist["Pzn"].astype(str)
        nicht_eingelagert = df_hist[
            df_hist["eingelagert"].astype(str).str.strip().str.lower() == "nein"
        ].copy()
        if nicht_eingelagert.empty:
            return None
        return nicht_eingelagert[["Pzn", "Bestellmenge"]].rename(
            columns={"Bestellmenge": "Bestellmenge_letzte_Woche"}
        )
    except Exception:
        return None


def finde_letzte_bestellung(drive=None):
    """Gibt (pfad_oder_none, df_oder_none) zurück — lokal oder aus Drive."""
    if is_cloud() and drive:
        # Drive: neueste bestellhistorie-*.xlsx suchen
        results = drive.files().list(
            q="name contains 'bestellhistorie' and trashed=false",
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=1,
        ).execute()
        files = results.get('files', [])
        if not files:
            return None, None
        buf = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(buf, drive.files().get_media(fileId=files[0]['id']))
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        df = pd.read_excel(buf)
        return files[0]['name'], df
    else:
        # Lokal
        pfad = finde_letzte_bestellung_excel()
        if pfad is None:
            return None, None
        return os.path.basename(pfad), pd.read_excel(pfad)


_ALGO_DEFAULTS = {
    "algo_w30":              0.7,
    "algo_w90":              0.3,
    "algo_ziel_tage":        60,
    "algo_mbw_standard":     2000.0,
    "algo_krit_pos":         0.0,
    "algo_mindestreichweite": 30,
}

def _auto_save_algo():
    """Callback: speichert Algo-Einstellungen sofort nach Änderung in Drive."""
    # algo_w90 von w30 ableiten
    st.session_state["algo_w90"] = round(1.0 - st.session_state.get("algo_w30", 0.7), 10)
    drive = st.session_state.get("drive")
    if drive:
        try:
            speichere_algo_config(drive, {
                k: st.session_state.get(k, d)
                for k, d in _ALGO_DEFAULTS.items()
            })
        except Exception:
            pass


def lade_algo_config(drive):
    """Lädt Algorithmus-Einstellungen aus Drive (algo_config.json im Stammdaten-Ordner)."""
    try:
        import json as _json
        from googleapiclient.http import MediaIoBaseDownload as _MIBD
        sid = get_stammdaten_folder_id(drive)
        q   = f"name='algo_config.json' and '{sid}' in parents and trashed=false"
        res = drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
        files = res.get("files", [])
        if not files:
            return {}
        buf = io.BytesIO()
        dl  = _MIBD(buf, drive.files().get_media(fileId=files[0]["id"]))
        done = False
        while not done:
            _, done = dl.next_chunk()
        return _json.loads(buf.getvalue().decode())
    except Exception:
        return {}

def speichere_algo_config(drive, config: dict):
    """Speichert Algorithmus-Einstellungen als JSON in Drive."""
    import json as _json
    from googleapiclient.http import MediaIoBaseUpload as _MIU
    sid   = get_stammdaten_folder_id(drive)
    data  = _json.dumps(config, indent=2).encode()
    media = _MIU(io.BytesIO(data), mimetype="application/json")
    q     = f"name='algo_config.json' and '{sid}' in parents and trashed=false"
    ex    = drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if ex:
        drive.files().update(fileId=ex[0]["id"], media_body=media).execute()
    else:
        drive.files().create(
            body={"name": "algo_config.json", "parents": [sid]},
            media_body=media, fields="id",
        ).execute()


def _stelle_mbw_wieder_her(df: pd.DataFrame, ergebnis: dict) -> pd.DataFrame:
    """Stellt die MBW-Spalte in df wieder her, falls sie fehlt — per Hersteller-Mapping."""
    if "MBW" in df.columns:
        return df
    df = df.copy()
    _ref = ergebnis.get("bestellen", pd.DataFrame())
    if "MBW" in _ref.columns and "Hersteller" in _ref.columns and "Hersteller" in df.columns:
        _mbw_map = _ref.drop_duplicates("Hersteller").set_index("Hersteller")["MBW"]
        df["MBW"] = df["Hersteller"].map(_mbw_map)
    if "MBW" not in df.columns or df["MBW"].isna().any():
        from purchasing_agent import CONFIG as _C
        df["MBW"] = df.get("MBW", pd.Series(dtype=float)).fillna(_C.get("mbw_standard", 2000.0))
    return df


def speichere_historie(df_input, df_bestellen, drive=None):
    """Speichert Bestellhistorie lokal und/oder in Drive."""
    historie_name, historie_pfad = speichere_bestellhistorie(df_input, df_bestellen)
    if drive:
        week_folder_id = get_week_folder_id(drive, date.today().isocalendar()[1], date.today().year)
        with open(historie_pfad, 'rb') as f:
            upload_bytes_to_drive(
                drive, f.read(), historie_name, week_folder_id,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
    return historie_name, historie_pfad

# ─── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Healthii Purchasing",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Passwortschutz ───────────────────────────────────────────────────────────

def check_password():
    """Gibt True zurück wenn das Passwort korrekt ist."""
    try:
        app_password = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        app_password = None

    if not app_password:
        return True

    if st.session_state.get("authenticated"):
        return True

    # Logo laden
    _logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png")
    _logo_b64 = ""
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _f:
            _logo_b64 = base64.b64encode(_f.read()).decode()

    # Hintergrund + Card-Styling via CSS auf st.form
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

        # Logo
        if _logo_b64:
            st.markdown(
                f"<div style='text-align:center;margin-bottom:8px;'>"
                f"<img src='data:image/png;base64,{_logo_b64}' style='height:44px;' />"
                f"</div>",
                unsafe_allow_html=True,
            )
        # Badge
        st.markdown(
            "<div style='text-align:center;margin-bottom:20px;'>"
            "<span style='background:#F0FDF9;color:#0D9488;font-size:10px;font-weight:600;"
            "padding:3px 10px;border-radius:20px;letter-spacing:0.8px;"
            "border:1px solid #CCFBF1;'>PURCHASING-AGENT</span></div>",
            unsafe_allow_html=True,
        )

        # Login-Form (echter Container → Card-CSS greift)
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

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Hintergrund */
    [data-testid="stAppViewContainer"] { background: #FFFFFF; }
    [data-testid="stMain"] { background: #FFFFFF; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #F9FAFB;
        border-right: 1px solid #E5E7EB;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #111827; }

    /* Überschriften */
    h1 { color: #111827 !important; font-weight: 700 !important; font-size: 2rem !important; }
    h2 { color: #111827 !important; font-weight: 600 !important; }
    h3 { color: #374151 !important; font-weight: 600 !important; }

    /* Metriken – weiße Cards */
    div[data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    div[data-testid="metric-container"] label { color: #6B7280 !important; font-size: 13px !important; }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #111827 !important;
        font-weight: 600 !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #FFFFFF;
        border-radius: 10px;
        padding: 4px;
        border: 1px solid #E5E7EB;
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-weight: 500;
        color: #6B7280;
        padding: 8px 16px;
    }
    .stTabs [data-baseweb="tab-highlight"] { background-color: transparent; }
    .stTabs [aria-selected="true"] {
        background: #F0FDF9 !important;
        color: #0D9488 !important;
        font-weight: 600 !important;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        font-size: 14px;
        border: 1px solid #D1D5DB;
        background: #FFFFFF;
        color: #374151;
        transition: all 0.15s;
    }
    .stButton > button:hover {
        border-color: #0D9488;
        color: #0D9488;
        background: #F0FDF9;
    }
    .stButton > button[kind="primary"] {
        background: #0D9488;
        color: white;
        border: none;
    }
    .stButton > button[kind="primary"]:hover {
        background: #0B7A70;
    }
    .stDownloadButton > button {
        background: #0D9488;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 500;
    }
    .stDownloadButton > button:hover { background: #0B7A70; }

    /* File Uploader */
    [data-testid="stFileUploader"] {
        border: 2px dashed #D1D5DB;
        border-radius: 12px;
        background: #FFFFFF;
        padding: 8px;
    }
    [data-testid="stFileUploader"]:hover { border-color: #0D9488; }

    /* number_input: +/- Buttons ausblenden */
    button[data-testid="stNumberInputStepDown"],
    button[data-testid="stNumberInputStepUp"] { display: none !important; }
    [data-testid="stNumberInput"] input { border-radius: 8px !important; }

    /* Divider */
    hr { border-color: #E5E7EB; }

    /* Alerts */
    .stAlert { border-radius: 10px; font-size: 14px; }

    /* Expander */
    .streamlit-expanderHeader {
        background: #FFFFFF;
        border-radius: 8px;
        border: 1px solid #E5E7EB;
        font-weight: 500;
    }

    /* DataEditor / DataFrame */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        overflow: hidden;
    }

    /* Caption text */
    .stCaption, [data-testid="stCaptionContainer"] { color: #9CA3AF; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── Session State initialisieren ─────────────────────────────────────────────

for key, default in [
    ("ergebnis", None),
    ("df_bestellen_edit", None),
    ("drive", None),
    ("drive_verbunden", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Google Drive verbinden (einmalig) ────────────────────────────────────────

@st.cache_resource
def verbinde_drive():
    try:
        _, drive = get_services()
        return drive
    except Exception:
        return None

if not st.session_state.drive_verbunden:
    drive = verbinde_drive()
    st.session_state.drive = drive
    st.session_state.drive_verbunden = True

    # Algorithmus-Einstellungen aus Drive laden
    if drive:
        _saved_config = lade_algo_config(drive)
        for _k, _default in _ALGO_DEFAULTS.items():
            if _k not in st.session_state:
                st.session_state[_k] = _saved_config.get(_k, _default)

    # Beim Start: letzten Stand aus Drive wiederherstellen
    if drive and not st.session_state.get("excel_bytes_input"):
        from googleapiclient.http import MediaIoBaseDownload

        with st.spinner("Letzten Stand wird geladen …"):
            _fehler = None
            try:
                # 1. wiederbestellung_aktuell.xlsx laden (im Stammdaten-Ordner suchen)
                _stammdaten_id = get_stammdaten_folder_id(drive)
                _q = f"name='wiederbestellung_aktuell.xlsx' and '{_stammdaten_id}' in parents and trashed=false"
                _res = drive.files().list(q=_q, fields="files(id,name)", pageSize=1).execute()
                _files = _res.get("files", [])
                if not _files:
                    _fehler = "Noch keine Wiederbestelldatei in Drive — bitte links hochladen."
                else:
                    _buf = io.BytesIO()
                    _dl = MediaIoBaseDownload(_buf, drive.files().get_media(fileId=_files[0]["id"]))
                    _done = False
                    while not _done:
                        _, _done = _dl.next_chunk()
                    excel_bytes = _buf.getvalue()

                    # 2. Bestellhistorie aufbereiten
                    letzte_bestellung_df = lade_letzte_bestellung_fuer_berechnung(drive)

                    # 3. MBW-Ausnahmen laden
                    mbw_ausnahmen = {}
                    try:
                        _stammdaten_id = get_stammdaten_folder_id(drive)
                        _mbw_df = download_csv_from_drive(drive, "mbw_exceptions.csv", _stammdaten_id)
                        if _mbw_df is not None:
                            mbw_ausnahmen = dict(zip(_mbw_df["Hersteller"], _mbw_df["MBW"]))
                    except Exception:
                        pass

                    # 4. Bestellvorschlag berechnen
                    ergebnis = berechne_bestellvorschlag(excel_bytes, letzte_bestellung_df, mbw_ausnahmen)
                    st.session_state.ergebnis          = ergebnis
                    st.session_state.excel_bytes_input = excel_bytes
                    st.session_state.uploaded_filename = "wiederbestellung_aktuell.xlsx"
                    if not ergebnis["bestellen"].empty:
                        st.session_state.df_bestellen_edit = ergebnis["bestellen"].copy()

            except Exception as e:
                _fehler = str(e)

        if _fehler:
            st.warning(f"Auto-Load fehlgeschlagen: {_fehler}")

# ─── Header ───────────────────────────────────────────────────────────────────

heute = date.today()
kw    = heute.isocalendar()[1]
year  = heute.year

# Header im Healthii-Stil
drive_status_color = "#0D9488" if st.session_state.drive else "#EF4444"
drive_status_text  = "Drive verbunden" if st.session_state.drive else "Drive nicht verbunden"

# Logo als Base64 laden
logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png")
logo_b64 = ""
if os.path.exists(logo_path):
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
logo_html = (f"<img src='data:image/png;base64,{logo_b64}' style='height:36px;' />"
             if logo_b64 else "<span style='font-size:24px;font-weight:300;'>healthii</span>")

st.markdown(f"""
<div style='display:flex;align-items:center;justify-content:space-between;
            padding:0 0 20px 0;border-bottom:1px solid #E5E7EB;margin-bottom:24px;'>
    <div style='display:flex;align-items:center;gap:14px;'>
        {logo_html}
        <span style='background:#F0FDF9;color:#0D9488;font-size:10px;font-weight:600;
                     padding:3px 10px;border-radius:20px;letter-spacing:0.8px;
                     border:1px solid #CCFBF1;'>PURCHASING-AGENT</span>
    </div>
    <div style='display:flex;align-items:center;gap:16px;'>
        <span style='color:#6B7280;font-size:13px;'>
            📅 {heute.strftime('%d.%m.%Y')} &nbsp;·&nbsp; KW{kw:02d}/{year}
        </span>
        <span style='font-size:12px;color:{drive_status_color};font-weight:500;'>
            ● {drive_status_text}
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Wiederbestellung")

    uploaded = st.file_uploader(
        "wiederbestellung.xlsx hochladen",
        type=["xlsx"],
        help="Metabase-Export hierher ziehen oder auswählen",
        accept_multiple_files=False,
    )

    # Datei in Drive speichern (ohne Berechnung)
    if uploaded:
        if st.session_state.get("uploaded_filename") != uploaded.name:
            excel_bytes = uploaded.read()
            with st.spinner("Speichere …"):
                if st.session_state.drive:
                    try:
                        stammdaten_id = get_stammdaten_folder_id(st.session_state.drive)
                        upload_bytes_to_drive(
                            st.session_state.drive, excel_bytes,
                            "wiederbestellung_aktuell.xlsx", stammdaten_id,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    except Exception:
                        pass
            st.session_state.excel_bytes_input = excel_bytes
            st.session_state.uploaded_filename = uploaded.name
            st.session_state.ergebnis          = None
            st.session_state.df_bestellen_edit = None
        st.caption(f"✅ {uploaded.name}")

    elif st.session_state.get("uploaded_filename"):
        st.caption(f"✅ {st.session_state.uploaded_filename} (aus Drive)")

    # Berechnen-Button
    if st.session_state.get("excel_bytes_input"):
        if st.button("▶ Berechnen", use_container_width=True, type="primary"):
            st.session_state["excel_out"] = None  # altes Excel verwerfen
            with st.spinner("Berechne …"):
                letzte_bestellung_df = lade_letzte_bestellung_fuer_berechnung(st.session_state.drive)
                mbw_ausnahmen = {}
                if st.session_state.drive:
                    try:
                        stammdaten_id = get_stammdaten_folder_id(st.session_state.drive)
                        mbw_df        = download_csv_from_drive(
                            st.session_state.drive, "mbw_exceptions.csv", stammdaten_id
                        )
                        if mbw_df is not None:
                            mbw_ausnahmen = dict(zip(mbw_df["Hersteller"], mbw_df["MBW"]))
                    except Exception:
                        pass
                # Algorithmus-Einstellungen aus Session State übernehmen
                from purchasing_agent import CONFIG as _CONFIG
                _CONFIG["gewichtung_l30"]             = st.session_state.get("algo_w30", 0.7)
                _CONFIG["gewichtung_l90"]             = st.session_state.get("algo_w90", 0.3)
                _CONFIG["ziel_tage"]                  = st.session_state.get("algo_ziel_tage", 60)
                _CONFIG["mbw_standard"]               = st.session_state.get("algo_mbw_standard", 2000.0)
                _CONFIG["kritische_positionsgroesse"] = st.session_state.get("algo_krit_pos", 0.0)
                _CONFIG["mindestreichweite"]          = st.session_state.get("algo_mindestreichweite", 30)


                ergebnis = berechne_bestellvorschlag(
                    st.session_state.excel_bytes_input, letzte_bestellung_df, mbw_ausnahmen
                )
                from datetime import datetime as _dt
                st.session_state.ergebnis            = ergebnis
                st.session_state.ergebnis_timestamp  = _dt.now().strftime("%d.%m.%Y %H:%M:%S")
                if not ergebnis["bestellen"].empty:
                    st.session_state.df_bestellen_edit = ergebnis["bestellen"].copy()
                else:
                    st.session_state.df_bestellen_edit = pd.DataFrame()
            st.rerun()

    st.divider()

    # ── Letzte Bestellung Status ──
    st.header("📋 Letzte Bestellung")
    try:
        hist_name, df_hist_sidebar = finde_letzte_bestellung(st.session_state.drive)
        st.session_state["_hist_cache"] = (hist_name, df_hist_sidebar)
    except Exception:
        _cached = st.session_state.get("_hist_cache")
        hist_name, df_hist_sidebar = _cached if _cached else (None, None)
    if df_hist_sidebar is not None:
        n_gesamt = len(df_hist_sidebar)
        n_offen  = len(df_hist_sidebar[
            df_hist_sidebar["eingelagert"].astype(str).str.strip().str.lower() == "nein"
        ])
        st.caption(f"📄 {hist_name}")
        c1, c2 = st.columns(2)
        c1.metric("Offen", n_offen, help="Noch nicht eingelagert")
        c2.metric("Eingelagert", n_gesamt - n_offen)
        if n_offen > 0:
            st.caption("✏️ Zum Bearbeiten → Tab **Bestellhistorie**")
    else:
        st.info("Keine Bestellhistorie gefunden")

# ─── Ergebnis & Tabs ──────────────────────────────────────────────────────────

ergebnis     = st.session_state.ergebnis
df_bestellen = st.session_state.df_bestellen_edit
df_unter_mbw = ergebnis["unter_mbw"] if ergebnis else pd.DataFrame()

# KPI-Leiste — nur wenn Ergebnis vorhanden
if ergebnis is not None:
    c1, c2, c3, c4 = st.columns(4)
    if df_bestellen is not None and not df_bestellen.empty:
        c1.metric("Gesamtbestellwert", f"{df_bestellen['Bestellwert'].sum():,.0f} €")
        c2.metric("Hersteller",        df_bestellen["Hersteller"].nunique())
        c3.metric("Positionen",        len(df_bestellen))
    if not df_unter_mbw.empty:
        c4.metric("Unter MBW",
                  f"{df_unter_mbw['Hersteller'].nunique()} Hersteller",
                  delta=f"{len(df_unter_mbw)} Pos.",
                  delta_color="off")
    st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "🛒 Bestellvorschläge",
    "⚠️ Unter MBW – nicht bestellt",
    "📋 Bestellhistorie",
    "📁 Bestellarchiv",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – Bestellvorschläge
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    # ── Algorithmus-Einstellungen ──────────────────────────────────────────────
    with st.expander("⚙️ Algorithmus"):

        # MBW-Ausnahmen laden (außerhalb des Forms — data_editor nicht in st.form möglich)
        _drive_mbw = st.session_state.get("drive")
        _mbw_df_current = None
        if _drive_mbw:
            try:
                _sid = get_stammdaten_folder_id(_drive_mbw)
                _mbw_df_current = download_csv_from_drive(_drive_mbw, "mbw_exceptions.csv", _sid)
            except Exception:
                pass
        if _mbw_df_current is None:
            _mbw_df_current = pd.DataFrame({"Hersteller": pd.Series([], dtype=str), "MBW": pd.Series([], dtype=float)})
        else:
            _mbw_df_current = _mbw_df_current[["Hersteller", "MBW"]].copy()
            _mbw_df_current["Hersteller"] = _mbw_df_current["Hersteller"].astype(str)
            _mbw_df_current["MBW"] = pd.to_numeric(_mbw_df_current["MBW"], errors="coerce").fillna(0.0)

        with st.form("algo_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                _w30_neu = st.slider(
                    "Gewichtung L30",
                    min_value=0, max_value=100,
                    value=int(st.session_state.get("algo_w30", 0.7) * 100),
                    step=10, format="%d%%",
                    help="Anteil der letzten 30 Tage am Tagesverbrauch",
                )
                st.caption(f"→ Tagesverbrauch = **{_w30_neu}% × L30/30** + **{100-_w30_neu}% × L90/90**")
            with col_b:
                _ziel_neu = st.number_input(
                    "Ziel-Reichweite (Tage)",
                    min_value=7, max_value=365,
                    value=int(st.session_state.get("algo_ziel_tage", 60)),
                    step=5,
                    help="Wie viele Tage soll der Bestand nach der Bestellung reichen?",
                )

            _mbw_neu = st.number_input(
                "Standard-MBW (€)",
                min_value=0, max_value=50000,
                value=int(st.session_state.get("algo_mbw_standard", 2000)),
                step=100,
                help="Gilt für alle Hersteller ohne eigenen Eintrag unten",
            )

            st.divider()
            st.markdown("**Kritische Positionsgröße**")
            st.caption("Ist der Bestellwert einer einzelnen Position größer als der Grenzwert, wird auf das Minimum für die Mindestreichweite reduziert.")
            col_c, col_d = st.columns(2)
            with col_c:
                _krit_neu = st.number_input(
                    "Grenzwert je Position (€)",
                    min_value=0, max_value=100000,
                    value=int(st.session_state.get("algo_krit_pos", 0)),
                    step=100,
                    help="0 = deaktiviert",
                )
            with col_d:
                _mind_neu = st.number_input(
                    "Mindestreichweite (Tage)",
                    min_value=0, max_value=365,
                    value=int(st.session_state.get("algo_mindestreichweite", 30)),
                    step=5,
                    help="Mindestreichweite die nach Reduktion noch erfüllt sein muss",
                )

            _submitted = st.form_submit_button("💾 Einstellungen speichern",
                                               use_container_width=True, type="primary")

        if _submitted:
            st.session_state["algo_w30"]              = _w30_neu / 100
            st.session_state["algo_w90"]              = 1 - _w30_neu / 100
            st.session_state["algo_ziel_tage"]        = int(_ziel_neu)
            st.session_state["algo_mbw_standard"]     = float(_mbw_neu)
            st.session_state["algo_krit_pos"]         = float(_krit_neu)
            st.session_state["algo_mindestreichweite"] = int(_mind_neu)
            if _drive_mbw:
                try:
                    _auto_save_algo()
                    st.success("✓ Einstellungen gespeichert")
                except Exception as _e:
                    st.error(f"Fehler: {_e}")
            else:
                st.warning("Drive nicht verbunden — nur lokal gespeichert")

        # MBW-Ausnahmen Tabelle (außerhalb des Forms)
        st.divider()
        st.caption("**Hersteller-Ausnahmen (mbw_exceptions.csv)**")
        _mbw_edited = st.data_editor(
            _mbw_df_current,
            column_config={
                "Hersteller": st.column_config.TextColumn("Hersteller", width="large"),
                "MBW":        st.column_config.NumberColumn("MBW (€)", format="%.0f", width="small"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="mbw_exceptions_editor",
        )
        if st.button("💾 MBW-Ausnahmen speichern", use_container_width=True):
            if _drive_mbw:
                try:
                    from googleapiclient.http import MediaIoBaseUpload as _MIU
                    _sid = get_stammdaten_folder_id(_drive_mbw)
                    _csv_bytes = _mbw_edited.to_csv(index=False).encode()
                    _media = _MIU(io.BytesIO(_csv_bytes), mimetype="text/csv")
                    _q = f"name='mbw_exceptions.csv' and '{_sid}' in parents and trashed=false"
                    _ex = _drive_mbw.files().list(q=_q, fields="files(id)", pageSize=1).execute().get("files", [])
                    if _ex:
                        _drive_mbw.files().update(fileId=_ex[0]["id"], media_body=_media).execute()
                    else:
                        _drive_mbw.files().create(
                            body={"name": "mbw_exceptions.csv", "parents": [_sid]},
                            media_body=_media, fields="id",
                        ).execute()
                    st.success("✓ MBW-Ausnahmen gespeichert")
                except Exception as _e:
                    st.error(f"Fehler: {_e}")
            else:
                st.warning("Drive nicht verbunden")

    st.divider()

    if ergebnis is None:
        st.markdown("""
        <div style='text-align:center;padding:60px 0;color:#9CA3AF;'>
            <div style='font-size:48px;'>📄</div>
            <div style='font-size:16px;margin-top:12px;'>
                Datei hochladen und <b>Berechnen</b> klicken
            </div>
        </div>""", unsafe_allow_html=True)
    elif df_bestellen is None or df_bestellen.empty:
        st.info("Keine Bestellungen über MBW.")
    else:
        st.subheader("Bestellmengen anpassen")
        st.caption("**Bestellmenge** editierbar · Zeilen über das Papierkorb-Icon löschen · Änderungen mit **Speichern** übernehmen.")

        # Anzeigespalten
        basis_spalten = [
            "Hersteller", "Pzn", "Artikelname", "Ve1", "Bestellmenge",
            "Rechnungs Netto Ek Ve1", "Bestellwert", "Aep",
            "Lagerbestand", "Verkaeufe L30", "Verkaeufe L90",
        ]
        if "Ve2" in df_bestellen.columns and df_bestellen["Ve2"].notna().any():
            basis_spalten += ["Ve2", "Rechnungs Netto Ek Ve2"]

        df_display = df_bestellen[[c for c in basis_spalten if c in df_bestellen.columns]].copy()

        col_config = {
            "Hersteller":              st.column_config.TextColumn("Hersteller",        disabled=True),
            "Pzn":                     st.column_config.TextColumn("PZN",               disabled=True),
            "Artikelname":             st.column_config.TextColumn("Artikelname",        disabled=True, width="large"),
            "Ve1":                     st.column_config.NumberColumn("Ve1",              format="%d", disabled=True),
            "Bestellmenge":            st.column_config.NumberColumn("Bestellmenge",     min_value=0, step=1),
            "Rechnungs Netto Ek Ve1":  st.column_config.NumberColumn("EK Ve1 (€)",       format="%.2f", disabled=True),
            "Bestellwert":             st.column_config.NumberColumn("Bestellwert (€)",  format="%.2f", disabled=True),
            "Aep":                     st.column_config.NumberColumn("AEP (€)",          format="%.2f", disabled=True),
            "Lagerbestand":            st.column_config.NumberColumn("Lagerbestand",     disabled=True),
            "Verkaeufe L30":           st.column_config.NumberColumn("L30",              disabled=True),
            "Verkaeufe L90":           st.column_config.NumberColumn("L90",              disabled=True),
            "Ve2":                     st.column_config.NumberColumn("Ve2",              disabled=True),
            "Rechnungs Netto Ek Ve2":  st.column_config.NumberColumn("EK Ve2 (€)",       format="%.2f", disabled=True),
        }

        # Ve1 sicherstellen
        if "Ve1" not in df_display.columns and "Ve1" in df_bestellen.columns:
            df_display.insert(3, "Ve1", df_bestellen["Ve1"])

        # Lösch-Spalte vorne einfügen
        df_display = df_display.reset_index(drop=True)
        df_display.insert(0, "🗑", False)

        col_config["🗑"] = st.column_config.CheckboxColumn(
            "🗑", help="Zeile zum Löschen markieren", width="small"
        )

        edited = st.data_editor(
            df_display,
            column_config=col_config,
            use_container_width=True,
            hide_index=True,
            key="editor_tab1",
        )

        # Bestellwert live neu berechnen
        edited["Bestellwert"] = edited["Bestellmenge"] * edited["Rechnungs Netto Ek Ve1"]

        _markiert = edited["🗑"].sum()
        _btn_label = f"💾 Änderungen übernehmen{f'  ({_markiert} Zeile(n) löschen)' if _markiert else ''}"
        if st.button(_btn_label, type="primary"):
            # edited und df_full haben gleichen 0-basierten Index durch reset_index oben
            _df_full = st.session_state.df_bestellen_edit.copy().reset_index(drop=True)
            _keep_mask = ~edited["🗑"].values  # boolean array, positionsbasiert
            # Bestellmenge + Bestellwert für beibehaltene Zeilen zurückschreiben
            _df_full.loc[_keep_mask, "Bestellmenge"] = edited.loc[_keep_mask, "Bestellmenge"].values
            _df_full.loc[_keep_mask, "Bestellwert"]  = edited.loc[_keep_mask, "Bestellwert"].values
            # Gelöschte Zeilen entfernen
            _df_full = _df_full[_keep_mask].reset_index(drop=True)
            _df_full = _stelle_mbw_wieder_her(_df_full, ergebnis)
            st.session_state.df_bestellen_edit = _df_full
            st.session_state["excel_out"] = None  # Excel invalidieren
            st.success(f"✓ Übernommen{f' — {_markiert} Position(en) entfernt' if _markiert else ''}")
            st.rerun()

        st.divider()

        # ── Berechnungslog strukturiert ───────────────────────────────────────
        _ts = st.session_state.get("ergebnis_timestamp", "")
        _hl = ergebnis.get("hersteller_log", {})
        _log_label = f"🔍 Berechnungslog{'  —  ' + _ts if _ts else ''}"

        with st.expander(_log_label, expanded=False):
            if not _hl:
                for eintrag in ergebnis["log"]:
                    farbe = "green" if "✓" in eintrag else ("orange" if "⚙" in eintrag else "red")
                    st.markdown(f"<span style='color:{farbe}'>{eintrag}</span>", unsafe_allow_html=True)
            else:
                for eintrag in ergebnis["log"]:
                    if eintrag.startswith("Artikel") or "⚙" in eintrag:
                        st.caption(eintrag)

                _reihenfolge = {"bestellen": 0, "unter_mbw": 1, "kein_bedarf": 2}
                _sorted = sorted(_hl.items(), key=lambda x: _reihenfolge.get(x[1]["status"], 9))

                for _hersteller, _info in _sorted:
                    _st   = _info["status"]
                    _icon = "✅" if _st == "bestellen" else ("⚠️" if _st == "unter_mbw" else "—")
                    _bw   = _info["bestellwert"]
                    _mbw  = _info["mbw"]
                    _fb   = _info["fehlbetrag"]

                    if _st == "bestellen":
                        _header = f"{_icon} **{_hersteller}** — {_bw:,.2f} € ≥ MBW {_mbw:,.0f} €"
                    elif _st == "unter_mbw":
                        _header = f"{_icon} **{_hersteller}** — {_bw:,.2f} € | fehlt {_fb:,.2f} € bis MBW {_mbw:,.0f} €"
                    else:
                        _header = f"{_icon} **{_hersteller}** — kein Bestellbedarf"

                    with st.expander(_header, expanded=False):
                        _df_pos = _info["df"].copy()
                        _df_pos["Reichweite (Tage)"] = _df_pos.apply(
                            lambda r: round((r["Effektiver_Bestand"] + r["Bestellmenge"]) / r["TV"], 1)
                            if r["TV"] > 0 else None, axis=1
                        )
                        st.dataframe(
                            _df_pos[[
                                "Artikelname", "Pzn",
                                "Lagerbestand", "Bestellmenge_letzte_Woche", "Effektiver_Bestand",
                                "Verkaeufe L30", "Verkaeufe L90", "TV",
                                "Ziel_Menge", "Bedarf_roh", "Ve1",
                                "Bestellmenge", "Rechnungs Netto Ek Ve1", "Bestellwert",
                                "Reichweite (Tage)",
                            ]],
                            column_config={
                                "Artikelname":               st.column_config.TextColumn("Artikel", width="large"),
                                "Pzn":                       st.column_config.TextColumn("PZN"),
                                "Lagerbestand":              st.column_config.NumberColumn("Lager", format="%d"),
                                "Bestellmenge_letzte_Woche": st.column_config.NumberColumn("Offen", format="%d",
                                    help="Bereits bestellt, noch nicht eingelagert"),
                                "Effektiver_Bestand":        st.column_config.NumberColumn("Eff. Bestand", format="%d"),
                                "Verkaeufe L30":             st.column_config.NumberColumn("L30", format="%d"),
                                "Verkaeufe L90":             st.column_config.NumberColumn("L90", format="%d"),
                                "TV":                        st.column_config.NumberColumn("TV/Tag", format="%.2f",
                                    help="Gewichteter Tagesverbrauch"),
                                "Ziel_Menge":                st.column_config.NumberColumn("Ziel", format="%d",
                                    help="Zielmenge für Ziel-Reichweite"),
                                "Bedarf_roh":                st.column_config.NumberColumn("Bedarf roh", format="%.1f"),
                                "Ve1":                       st.column_config.NumberColumn("Ve1", format="%d"),
                                "Bestellmenge":              st.column_config.NumberColumn("Bestellmenge", format="%d"),
                                "Rechnungs Netto Ek Ve1":    st.column_config.NumberColumn("EK (€)", format="%.2f"),
                                "Bestellwert":               st.column_config.NumberColumn("Bestellwert (€)", format="%.2f"),
                                "Reichweite (Tage)":         st.column_config.NumberColumn("Reichweite", format="%.1f",
                                    help="Tage Reichweite nach Bestellung"),
                            },
                            use_container_width=True,
                            hide_index=True,
                        )

        st.divider()

        col_dl, col_save = st.columns(2)

        with col_dl:
            if st.button("🔄 Excel erstellen", use_container_width=True, type="primary"):
                with st.spinner("Erstelle Excel …"):
                    ergebnis_export = dict(ergebnis)
                    _df_export = _stelle_mbw_wieder_her(
                        st.session_state.df_bestellen_edit.copy(), ergebnis
                    )
                    ergebnis_export["bestellen"] = _df_export
                    st.session_state["excel_out"] = erstelle_bestellsheet(ergebnis_export, kw, year)

            if st.session_state.get("excel_out"):
                st.download_button(
                    label="📥 Purchase-Order herunterladen",
                    data=st.session_state["excel_out"],
                    file_name=f"Purchase-Order-KW{kw:02d}-{year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        with col_save:
            if st.button("💾 Abschließen & in Drive archivieren", use_container_width=True):
                with st.spinner("Speichere …"):
                    try:
                        df_final   = st.session_state.df_bestellen_edit
                        drive_conn = st.session_state.drive

                        # Bestellhistorie speichern (lokal + Drive)
                        speichere_historie(ergebnis["df_input"], df_final, drive_conn)

                        # Excel aus Session State oder neu erstellen
                        _excel_bytes = st.session_state.get("excel_out")
                        if not _excel_bytes:
                            ergebnis_export = dict(ergebnis)
                            ergebnis_export["bestellen"] = _stelle_mbw_wieder_her(df_final.copy(), ergebnis)
                            _excel_bytes = erstelle_bestellsheet(ergebnis_export, kw, year)

                        # Purchase-Order lokal speichern + Drive
                        order_name = f"Purchase-Order-KW{kw:02d}-{year}.xlsx"
                        order_path = os.path.join(BASE_DIR, order_name)
                        with open(order_path, "wb") as f:
                            f.write(_excel_bytes)
                        if drive_conn:
                            week_folder_id = get_week_folder_id(drive_conn, kw, year)
                            upload_bytes_to_drive(
                                drive_conn, _excel_bytes, order_name, week_folder_id,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                            st.success(f"✓ Lokal & Drive gespeichert: {order_name}")
                        else:
                            st.success(f"✓ Lokal gespeichert: {order_name}")

                        # Session zurücksetzen
                        st.session_state.ergebnis          = None
                        st.session_state.df_bestellen_edit = None
                        st.rerun()

                    except Exception as e:
                        st.error(f"Fehler: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – Unter MBW
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    if ergebnis is None:
        st.markdown("""
        <div style='text-align:center;padding:60px 0;color:#9CA3AF;'>
            <div style='font-size:48px;'>📄</div>
            <div style='font-size:16px;margin-top:12px;'>
                Bitte <b>wiederbestellung.xlsx</b> in der Seitenleiste hochladen
            </div>
        </div>""", unsafe_allow_html=True)
    elif df_unter_mbw.empty:
        st.success("✅ Alle Hersteller erreichen den Mindestbestellwert.")
    else:
        gesamt_potential = df_unter_mbw["Bestellwert"].sum()
        st.warning(
            f"**{df_unter_mbw['Hersteller'].nunique()} Hersteller** unter MBW – "
            f"**{len(df_unter_mbw)} Positionen** – "
            f"potentieller Bestellwert: **{gesamt_potential:,.2f} €**"
        )

        anzeige_cols = [
            "Hersteller", "Pzn", "Artikelname", "Bestellmenge",
            "Rechnungs Netto Ek Ve1", "Bestellwert", "Aep",
            "MBW", "Fehlbetrag", "Lagerbestand", "Verkaeufe L30", "Verkaeufe L90",
        ]
        anzeige_cols = [c for c in anzeige_cols if c in df_unter_mbw.columns]

        st.dataframe(
            df_unter_mbw[anzeige_cols],
            column_config={
                "Pzn":                    st.column_config.TextColumn("PZN"),
                "Artikelname":            st.column_config.TextColumn("Artikelname", width="large"),
                "Rechnungs Netto Ek Ve1": st.column_config.NumberColumn("EK Ve1 (€)",      format="%.2f"),
                "Bestellwert":            st.column_config.NumberColumn("Bestellwert (€)",  format="%.2f"),
                "Aep":                    st.column_config.NumberColumn("AEP (€)",           format="%.2f"),
                "MBW":                    st.column_config.NumberColumn("MBW (€)",           format="%.0f"),
                "Fehlbetrag":             st.column_config.NumberColumn("Fehlbetrag (€)",    format="%.2f"),
                "Lagerbestand":           st.column_config.NumberColumn("Lagerbestand"),
                "Verkaeufe L30":          st.column_config.NumberColumn("L30"),
                "Verkaeufe L90":          st.column_config.NumberColumn("L90"),
            },
            use_container_width=True,
            hide_index=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – Bestellhistorie
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    # Cache aus Sidebar nutzen, nur bei Bedarf neu laden
    try:
        hist_name_t3, df_hist = finde_letzte_bestellung(st.session_state.drive)
        st.session_state["_hist_cache"] = (hist_name_t3, df_hist)
    except Exception:
        _cached = st.session_state.get("_hist_cache")
        hist_name_t3, df_hist = _cached if _cached else (None, None)

    if df_hist is None:
        st.info("Noch keine Bestellhistorie vorhanden.")
    else:
        st.subheader(f"📄 {hist_name_t3}")

        df_hist["Pzn"] = df_hist["Pzn"].apply(
            lambda x: str(int(float(x))) if pd.notna(x) else ""
        )

        df_hist = df_hist.sort_values("Hersteller").reset_index(drop=True)

        hist_cols = [
            "eingelagert", "Hersteller", "Pzn", "Artikelname",
            "Bestellmenge", "Lagerbestand", "Verkaeufe L30", "Verkaeufe L90",
        ]
        hist_cols = [c for c in hist_cols if c in df_hist.columns]

        n_offen = (df_hist["eingelagert"].astype(str).str.strip().str.lower() == "nein").sum()

        col_info, col_alle = st.columns([3, 1])
        col_info.caption(f"{n_offen} von {len(df_hist)} Positionen noch nicht eingelagert")

        def _speichere_historie_drive(df_speichern, name):
            """Speichert die Bestellhistorie als Excel in Drive, mit 3 Retry-Versuchen."""
            import time as _time
            _buf = io.BytesIO()
            df_speichern.to_excel(_buf, index=False, sheet_name="Abfrageergebnis")
            _bytes = _buf.getvalue()
            # Lokal speichern
            letzte_excel = finde_letzte_bestellung_excel()
            if letzte_excel:
                with open(letzte_excel, "wb") as _f:
                    _f.write(_bytes)
            # Drive mit Retry
            _drive = st.session_state.drive
            if not _drive:
                return
            from googleapiclient.http import MediaIoBaseUpload
            _last_exc = None
            for _attempt in range(3):
                try:
                    _q = f"name='{name}' and trashed=false"
                    _res = _drive.files().list(q=_q, fields="files(id)", pageSize=1).execute()
                    _existing = _res.get("files", [])
                    _media = MediaIoBaseUpload(
                        io.BytesIO(_bytes),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    if _existing:
                        _drive.files().update(fileId=_existing[0]["id"], media_body=_media).execute()
                    else:
                        _week_folder_id = get_week_folder_id(
                            _drive, date.today().isocalendar()[1], date.today().year
                        )
                        _drive.files().create(
                            body={"name": name, "parents": [_week_folder_id]},
                            media_body=_media,
                        ).execute()
                    return  # Erfolg
                except Exception as _e:
                    _last_exc = _e
                    _time.sleep(1)
            raise _last_exc  # Alle Versuche fehlgeschlagen

        with col_alle:
            if st.button("✅ Alle einlagern", use_container_width=True):
                df_hist["eingelagert"] = "ja"
                with st.spinner("Speichere …"):
                    _speichere_historie_drive(df_hist, hist_name_t3)
                st.success("✓ Alle Positionen eingelagert & in Drive gespeichert")
                st.rerun()

        edited_hist = st.data_editor(
            df_hist[hist_cols],
            column_config={
                "eingelagert":  st.column_config.SelectboxColumn(
                    "Eingelagert", options=["nein", "ja"], required=True, width="small",
                ),
                "Hersteller":   st.column_config.TextColumn("Hersteller",   disabled=True),
                "Pzn":          st.column_config.TextColumn("PZN",          disabled=True, width="small"),
                "Artikelname":  st.column_config.TextColumn("Artikelname",  disabled=True, width="large"),
                "Bestellmenge": st.column_config.NumberColumn("Bestellmenge", min_value=0, step=1),
                "Lagerbestand": st.column_config.NumberColumn("Lagerbestand", disabled=True),
                "Verkaeufe L30":st.column_config.NumberColumn("L30",          disabled=True),
                "Verkaeufe L90":st.column_config.NumberColumn("L90",          disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="editor_historie",
        )

        if st.button("💾 Änderungen speichern", type="primary"):
            df_hist[hist_cols] = edited_hist
            with st.spinner("Speichere …"):
                _speichere_historie_drive(df_hist, hist_name_t3)
            st.success("✓ Bestellhistorie in Drive gespeichert")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 – Bestellarchiv
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    drive = st.session_state.drive

    if not drive:
        st.warning("Drive nicht verbunden — Archiv nicht verfügbar.")
    else:
        @st.cache_data(ttl=60, show_spinner=False)
        def lade_archiv_liste(_drive):
            """Listet alle Purchase-Order Dateien aus Drive."""
            results = _drive.files().list(
                q="name contains 'Purchase-Order' and trashed=false",
                fields="files(id, name, modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=50,
            ).execute()
            return results.get("files", [])

        def lade_purchase_order(_drive, file_id):
            """Lädt eine Purchase-Order Excel aus Drive und gibt einen DataFrame zurück."""
            from googleapiclient.http import MediaIoBaseDownload
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            # Zeile 1 = Info-Banner überspringen, Zeile 2 = Header
            df = pd.read_excel(buf, skiprows=1)
            # Summenzeilen herausfiltern (PZN leer oder kein gültiger Wert)
            if "PZN" in df.columns:
                df = df[df["PZN"].notna() & (df["PZN"].astype(str).str.strip() != "")]
            return df

        dateien = lade_archiv_liste(drive)

        if not dateien:
            st.info("Noch keine Purchase-Orders in Drive archiviert.")
        else:
            # Auswahl-Dropdown
            datei_namen  = [f["name"] for f in dateien]
            datei_ids    = {f["name"]: f["id"] for f in dateien}
            datei_zeiten = {f["name"]: f["modifiedTime"][:10] for f in dateien}

            ausgewählt = st.selectbox(
                "Purchase-Order auswählen",
                options=datei_namen,
                format_func=lambda n: f"{n}  ({datei_zeiten[n]})",
            )

            if ausgewählt:
                with st.spinner("Lade …"):
                    df_archiv = lade_purchase_order(drive, datei_ids[ausgewählt])

                # KPIs
                if not df_archiv.empty and "Bestellwert (€)" in df_archiv.columns:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Bestellwert gesamt", f"{df_archiv['Bestellwert (€)'].sum():,.0f} €")
                    if "Hersteller" in df_archiv.columns:
                        c2.metric("Hersteller", df_archiv["Hersteller"].nunique())
                    c3.metric("Positionen", len(df_archiv))

                st.dataframe(
                    df_archiv,
                    use_container_width=True,
                    hide_index=True,
                )

                # Download-Button
                from googleapiclient.http import MediaIoBaseDownload
                buf_dl = io.BytesIO()
                dl = MediaIoBaseDownload(buf_dl, drive.files().get_media(fileId=datei_ids[ausgewählt]))
                done = False
                while not done:
                    _, done = dl.next_chunk()
                st.download_button(
                    label="📥 Excel herunterladen",
                    data=buf_dl.getvalue(),
                    file_name=ausgewählt,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
