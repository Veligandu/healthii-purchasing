"""
Healthii – GH-Rechnungskontrolle
Parsed Phoenix-Sammelrechnungen (PDF) und erstellt eine Monatstabelle: PZN × Menge.
"""

import base64
import io
import json
import os
import re
from datetime import date

import pandas as pd
import pdfplumber
import streamlit as st

# ─── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="GH-Rechnungskontrolle | Healthii",
    page_icon="📄",
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

# ─── Google Drive verbinden ────────────────────────────────────────────────────

def is_cloud():
    try:
        return "GOOGLE_TOKEN" in st.secrets
    except Exception:
        return False

@st.cache_resource
def verbinde_drive():
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

if "gh_drive" not in st.session_state:
    st.session_state.gh_drive = verbinde_drive()

drive = st.session_state.gh_drive

# ─── Drive-Hilfsfunktionen ────────────────────────────────────────────────────

GH_FOLDER_NAME = "GH-Rechnungen"

@st.cache_data(ttl=120, show_spinner=False)
def get_gh_folder_id(_drive):
    """Gibt ID des 'GH-Rechnungen'-Ordners in Drive zurück (legt ihn an falls nötig)."""
    q = f"name='{GH_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    res = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    folder = _drive.files().create(
        body={"name": GH_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]


def lade_monatstabelle_aus_drive(_drive, jahr, monat):
    """Lädt gespeicherte Monatstabelle aus Drive, gibt DataFrame oder None zurück."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
        folder_id = get_gh_folder_id(_drive)
        name = f"gh_rechnung_{jahr}_{monat:02d}.xlsx"
        q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        res = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
        files = res.get("files", [])
        if not files:
            return None
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=files[0]["id"]))
        done = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)
        return pd.read_excel(buf, dtype={"PZN": str})
    except Exception:
        return None


def speichere_monatstabelle_in_drive(_drive, df, jahr, monat):
    """Speichert Monatstabelle als Excel in Drive (überschreibt bestehende)."""
    from googleapiclient.http import MediaIoBaseUpload
    folder_id = get_gh_folder_id(_drive)
    name = f"gh_rechnung_{jahr}_{monat:02d}.xlsx"
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    media = MediaIoBaseUpload(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
    existing = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if existing:
        _drive.files().update(fileId=existing[0]["id"], media_body=media).execute()
    else:
        _drive.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()

# ─── PDF-Parser ───────────────────────────────────────────────────────────────

# Zeilenmuster: Lagerort  Menge  [Einheit/Name...]  [V-Dat]  Pos  PZN
#               VP_mit_MWSt  EK_ohne_MWSt  Warenwert_ohne_MWSt  OA/FA  S
_ZEILEN_RE = re.compile(
    r"^\s*1\s+\d+\s+(\d+)\s+.+?\b(\d{8})\b\s+[\d,]+\s+([\d,]+)\s+([\d,]+)\s+[OF]A",
    re.MULTILINE,
)
# Rechnungssumme: letzte Zahl vor "DAFUE" in der Summenzeile
_TOTAL_RE = re.compile(r"([\d]+,\d+)\s+DAFUE")

def _preis(s: str) -> float:
    return float(s.replace(",", "."))

def datum_aus_dateiname(name: str):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.search(r"_(\d{2})-(\d{2})-(\d{2})_", name)
    if m:
        tag, monat, jahr_kurz = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return 2000 + jahr_kurz, monat, tag
    return None, None, None


def parse_pdf(datei_bytes: bytes, dateiname: str) -> tuple[pd.DataFrame, float | None]:
    """Gibt (DataFrame mit Positionen, Rechnungssumme aus PDF) zurück."""
    jahr, monat, _ = datum_aus_dateiname(dateiname)
    m_beleg = re.search(r"INVOICE-(\d+)", dateiname, re.IGNORECASE)
    beleg = m_beleg.group(1) if m_beleg else dateiname
    zeilen = []
    total_pdf = None
    with pdfplumber.open(io.BytesIO(datei_bytes)) as pdf:
        for seite in pdf.pages:
            text = seite.extract_text() or ""
            for m in _ZEILEN_RE.finditer(text):
                zeilen.append({
                    "PZN":          m.group(2),
                    "Menge":        int(m.group(1)),
                    "EK_ohne_MWSt": _preis(m.group(3)),
                    "Warenwert":    _preis(m.group(4)),
                    "Beleg":        beleg,
                    "Jahr":         jahr,
                    "Monat":        monat,
                })
            m_total = _TOTAL_RE.search(text)
            if m_total:
                total_pdf = _preis(m_total.group(1))
    return pd.DataFrame(zeilen), total_pdf

# ─── Header ───────────────────────────────────────────────────────────────────

logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png")
logo_b64 = ""
if os.path.exists(logo_path):
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
logo_html = (f"<img src='data:image/png;base64,{logo_b64}' style='height:36px;' />"
             if logo_b64 else "<span style='font-size:24px;'>healthii</span>")

drive_status_color = "#0D9488" if drive else "#EF4444"
drive_status_text  = "Drive verbunden" if drive else "Drive nicht verbunden"

st.markdown(f"""
<div style='display:flex;align-items:center;justify-content:space-between;
            padding:0 0 20px 0;border-bottom:1px solid #E5E7EB;margin-bottom:24px;'>
    <div style='display:flex;align-items:center;gap:14px;'>
        {logo_html}
        <span style='background:#F0FDF9;color:#0D9488;font-size:10px;font-weight:600;
                     padding:3px 10px;border-radius:20px;letter-spacing:0.8px;
                     border:1px solid #CCFBF1;'>GH-RECHNUNGSKONTROLLE</span>
    </div>
    <span style='font-size:12px;color:{drive_status_color};font-weight:500;'>
        ● {drive_status_text}
    </span>
</div>
""", unsafe_allow_html=True)

# ─── Sidebar: Monatsauswahl + Upload ──────────────────────────────────────────

with st.sidebar:
    st.header("📄 Rechnungen hochladen")

    heute = date.today()
    col_m, col_j = st.columns(2)
    monat_auswahl = col_m.selectbox("Monat", list(range(1, 13)),
                                     index=heute.month - 1,
                                     format_func=lambda m: f"{m:02d}")
    jahr_auswahl  = col_j.number_input("Jahr", min_value=2020, max_value=2099,
                                        value=heute.year, step=1)

    uploads = st.file_uploader(
        "PDF-Rechnungen",
        type=["pdf"],
        accept_multiple_files=True,
        help="Mehrere Phoenix-Sammelrechnungen auf einmal auswählen",
    )

    verarbeiten = st.button("▶ Rechnungen einlesen", use_container_width=True, type="primary",
                             disabled=not uploads)

    st.divider()

    # Gespeicherte Monate aus Drive laden
    if drive:
        st.header("📁 Gespeicherte Monate")
        if st.button("🔄 Liste aktualisieren", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        try:
            folder_id = get_gh_folder_id(drive)
            _res = drive.files().list(
                q=f"'{folder_id}' in parents and trashed=false and name contains 'gh_rechnung'",
                fields="files(id,name)",
                orderBy="name desc",
                pageSize=24,
            ).execute()
            _archiv = _res.get("files", [])
            if _archiv:
                for _f in _archiv:
                    _m = re.search(r"gh_rechnung_(\d{4})_(\d{2})", _f["name"])
                    if _m:
                        _label = f"{_m.group(2)}/{_m.group(1)}"
                        st.caption(f"✓ {_label}")
        except Exception:
            pass

# ─── Haupt-Bereich ────────────────────────────────────────────────────────────

monat_label = f"{monat_auswahl:02d}/{jahr_auswahl}"

# Session State-Keys
roh_key    = f"gh_roh_{jahr_auswahl}_{monat_auswahl:02d}"    # Rohzeilen pro Beleg
totals_key = f"gh_totals_{jahr_auswahl}_{monat_auswahl:02d}" # PDF-Summen pro Beleg
agg_key    = f"gh_agg_{jahr_auswahl}_{monat_auswahl:02d}"    # aggregierte Monatstabelle

for k in [roh_key, totals_key, agg_key]:
    if k not in st.session_state:
        st.session_state[k] = None

# ─── PDFs einlesen ────────────────────────────────────────────────────────────

if verarbeiten and uploads:
    alle_zeilen = []
    totals_neu  = {}   # beleg → total_pdf
    fehler = []
    fortschritt = st.progress(0, text="Lese PDFs …")

    for i, pdf_file in enumerate(uploads):
        fortschritt.progress((i + 1) / len(uploads), text=pdf_file.name)
        try:
            df_pdf, total_pdf = parse_pdf(pdf_file.read(), pdf_file.name)
            if df_pdf.empty:
                fehler.append(f"⚠️ {pdf_file.name}: Keine Positionen gefunden")
            else:
                alle_zeilen.append(df_pdf)
                beleg = df_pdf["Beleg"].iloc[0]
                totals_neu[beleg] = total_pdf
        except Exception as e:
            fehler.append(f"❌ {pdf_file.name}: {e}")

    fortschritt.empty()

    if alle_zeilen:
        df_neu = pd.concat(alle_zeilen, ignore_index=True)

        # Mit bestehendem Monat zusammenführen (Duplikat-Belege ersetzen)
        df_alt = st.session_state[roh_key]
        if df_alt is not None:
            belege_neu = set(df_neu["Beleg"].unique())
            df_alt = df_alt[~df_alt["Beleg"].isin(belege_neu)]
            df_gesamt = pd.concat([df_alt, df_neu], ignore_index=True)
        else:
            df_gesamt = df_neu

        totals_alt = st.session_state[totals_key] or {}
        totals_alt.update(totals_neu)

        st.session_state[roh_key]    = df_gesamt
        st.session_state[totals_key] = totals_alt

        for f in fehler:
            st.warning(f)
    else:
        st.error("Keine Daten konnten extrahiert werden.")
        for f in fehler:
            st.warning(f)

# ─── Belegkontrolle ───────────────────────────────────────────────────────────

df_roh   = st.session_state.get(roh_key)
totals   = st.session_state.get(totals_key) or {}

if df_roh is not None and not df_roh.empty:
    st.subheader(f"Belegkontrolle {monat_label}")

    # Beleg-Übersicht aufbauen
    df_belege = (
        df_roh.groupby("Beleg", as_index=False)
        .agg(Positionen=("PZN", "count"), Warenwert_berechnet=("Warenwert", "sum"))
        .sort_values("Beleg")
    )
    df_belege["Warenwert_Beleg"] = df_belege["Beleg"].map(totals)
    df_belege["Differenz"]       = (
        df_belege["Warenwert_berechnet"] - df_belege["Warenwert_Beleg"]
    ).round(2)
    df_belege["Status"] = df_belege["Differenz"].apply(
        lambda d: "✅" if pd.notna(d) and abs(d) < 0.01 else ("⚠️ Abweichung" if pd.notna(d) else "❓")
    )

    n_ok  = (df_belege["Status"] == "✅").sum()
    n_err = len(df_belege) - n_ok
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Belege", len(df_belege))
    c2.metric("✅ OK", n_ok)
    c3.metric("⚠️ Abweichungen", n_err)
    c4.metric("Gesamtwert", f"{df_belege['Warenwert_berechnet'].sum():,.2f} €")

    st.divider()

    # Übersichtstabelle
    st.dataframe(
        df_belege[["Status", "Beleg", "Positionen", "Warenwert_berechnet", "Warenwert_Beleg", "Differenz"]],
        column_config={
            "Status":               st.column_config.TextColumn(""),
            "Beleg":                st.column_config.TextColumn("Belegnr."),
            "Positionen":           st.column_config.NumberColumn("Pos.", format="%d"),
            "Warenwert_berechnet":  st.column_config.NumberColumn("Berechnet (€)",  format="%.2f"),
            "Warenwert_Beleg":      st.column_config.NumberColumn("Laut Beleg (€)", format="%.2f"),
            "Differenz":            st.column_config.NumberColumn("Differenz (€)",  format="%.2f"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Editierbare Einzelzeilen bei Abweichungen
    belege_abweichend = df_belege[df_belege["Status"] != "✅"]["Beleg"].tolist()
    if belege_abweichend:
        st.divider()
        st.subheader("Positionen korrigieren")
        for beleg in belege_abweichend:
            diff = df_belege.loc[df_belege["Beleg"] == beleg, "Differenz"].iloc[0]
            with st.expander(f"⚠️ Beleg {beleg}  —  Differenz: {diff:+.2f} €"):
                df_b = df_roh[df_roh["Beleg"] == beleg].copy()
                edit_cols = ["PZN", "Menge", "EK_ohne_MWSt", "Warenwert"]
                edited = st.data_editor(
                    df_b[edit_cols].reset_index(drop=True),
                    column_config={
                        "PZN":          st.column_config.TextColumn("PZN"),
                        "Menge":        st.column_config.NumberColumn("Menge",        min_value=0, step=1),
                        "EK_ohne_MWSt": st.column_config.NumberColumn("EK o. MWSt (€)", format="%.2f"),
                        "Warenwert":    st.column_config.NumberColumn("Warenwert (€)", format="%.2f", disabled=True),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key=f"editor_beleg_{beleg}",
                )
                # Warenwert live neu berechnen
                edited["Warenwert"] = (edited["Menge"] * edited["EK_ohne_MWSt"]).round(2)

                if st.button("💾 Korrekturen übernehmen", key=f"save_{beleg}", type="primary"):
                    edited["Beleg"] = beleg
                    edited["Jahr"]  = df_b["Jahr"].iloc[0]
                    edited["Monat"] = df_b["Monat"].iloc[0]
                    df_rest = df_roh[df_roh["Beleg"] != beleg]
                    st.session_state[roh_key] = pd.concat([df_rest, edited], ignore_index=True)
                    st.success(f"✓ Beleg {beleg} aktualisiert")
                    st.rerun()

    # ─── Monatstabelle aggregieren & speichern ────────────────────────────────

    st.divider()
    st.subheader(f"Monatstabelle {monat_label}")

    df_agg = (
        df_roh
        .groupby("PZN", as_index=False)
        .agg(Menge=("Menge", "sum"), Warenwert=("Warenwert", "sum"))
        .sort_values("Warenwert", ascending=False)
        .reset_index(drop=True)
    )
    st.session_state[agg_key] = df_agg

    st.dataframe(
        df_agg,
        column_config={
            "PZN":      st.column_config.TextColumn("PZN"),
            "Menge":    st.column_config.NumberColumn("Menge",         format="%d"),
            "Warenwert": st.column_config.NumberColumn("Warenwert (€)", format="%.2f"),
        },
        use_container_width=True,
        hide_index=True,
    )

    col_save, col_dl = st.columns(2)

    with col_save:
        if drive and st.button("💾 In Drive speichern", use_container_width=True, type="primary"):
            try:
                speichere_monatstabelle_in_drive(drive, df_agg, int(jahr_auswahl), monat_auswahl)
                st.success("✓ In Drive gespeichert")
            except Exception as e:
                st.error(f"Drive-Fehler: {e}")

    with col_dl:
        _buf = io.BytesIO()
        with pd.ExcelWriter(_buf, engine="openpyxl") as _w:
            df_agg.to_excel(_w, index=False, sheet_name=f"Monat {monat_label}")
            df_belege.to_excel(_w, index=False, sheet_name="Belegkontrolle")
        st.download_button(
            label="📥 Excel herunterladen",
            data=_buf.getvalue(),
            file_name=f"gh_rechnung_{jahr_auswahl}_{monat_auswahl:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

else:
    st.markdown("""
    <div style='text-align:center;padding:80px 0;color:#9CA3AF;'>
        <div style='font-size:48px;'>📄</div>
        <div style='font-size:16px;margin-top:12px;'>
            Monat auswählen und PDFs hochladen — oder gespeicherten Monat links anklicken
        </div>
    </div>""", unsafe_allow_html=True)
