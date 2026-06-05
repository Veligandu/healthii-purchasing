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

try:
    from streamlit_pdf_viewer import pdf_viewer
except Exception:
    pdf_viewer = None

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


def lade_monat_aus_drive(_drive, jahr, monat):
    """Lädt gespeicherten Monat aus Drive.
    Gibt (df_roh, totals, preise) zurück — df_roh=None falls keine Rohdaten vorhanden."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
        folder_id = get_gh_folder_id(_drive)
        name = f"gh_rechnung_{jahr}_{monat:02d}.xlsx"
        q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        res = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
        files = res.get("files", [])
        if not files:
            return None, {}, {}, {}, ""
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=files[0]["id"]))
        done = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)
        xls = pd.ExcelFile(buf)
        df_roh = (
            pd.read_excel(xls, "Rohdaten", dtype={"PZN": str, "Beleg": str})
            if "Rohdaten" in xls.sheet_names else None
        )
        totals = {}
        if "Summen" in xls.sheet_names:
            df_t = pd.read_excel(xls, "Summen", dtype={"Beleg": str})
            totals = dict(zip(df_t["Beleg"], df_t["Warenwert_Beleg"]))
        preise = {}
        if "Preise" in xls.sheet_names:
            df_p = pd.read_excel(xls, "Preise", dtype={"PZN": str})
            preise = dict(zip(df_p["PZN"], df_p["Preis"]))
        abr = {}
        if "Abrechnung" in xls.sheet_names:
            df_a = pd.read_excel(xls, "Abrechnung", dtype={"Rechnungsnr": str})
            for _, r in df_a.iterrows():
                datum = r["Datum"] if "Datum" in df_a.columns and pd.notna(r["Datum"]) else None
                if datum is not None:
                    datum = str(datum)[:10]
                abr[str(r["Rechnungsnr"])] = {"datum": datum, "betrag": r["Betrag"]}
        report = ""
        if "Report" in xls.sheet_names:
            df_rep = pd.read_excel(xls, "Report")
            if not df_rep.empty and "Report" in df_rep.columns:
                v = df_rep["Report"].iloc[0]
                report = "" if pd.isna(v) else str(v)
        return df_roh, totals, preise, abr, report
    except Exception:
        return None, {}, {}, {}, ""


def monat_existiert_in_drive(_drive, jahr, monat):
    """True, wenn für den Monat bereits eine gespeicherte Datei in Drive liegt."""
    try:
        folder_id = get_gh_folder_id(_drive)
        name = f"gh_rechnung_{jahr}_{monat:02d}.xlsx"
        q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        res = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
        return bool(res.get("files", []))
    except Exception:
        return False


def speichere_monat_in_drive(_drive, df_agg, df_roh, totals, preise, abr, report, jahr, monat):
    """Speichert Monatstabelle + Rohdaten + Summen + Preise + Abrechnung + Report als Excel."""
    from googleapiclient.http import MediaIoBaseUpload
    folder_id = get_gh_folder_id(_drive)
    name = f"gh_rechnung_{jahr}_{monat:02d}.xlsx"
    df_totals = pd.DataFrame(
        [{"Beleg": b, "Warenwert_Beleg": t} for b, t in (totals or {}).items()]
    )
    df_preise = pd.DataFrame(
        [{"PZN": p, "Preis": v} for p, v in (preise or {}).items()]
    )
    df_abr = pd.DataFrame(
        [{"Rechnungsnr": n, "Datum": _abr_norm(v)[0], "Betrag": _abr_norm(v)[1]}
         for n, v in (abr or {}).items()]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_agg.to_excel(w, index=False, sheet_name=f"Monat {monat:02d}-{jahr}")
        if df_roh is not None:
            df_roh.to_excel(w, index=False, sheet_name="Rohdaten")
        if not df_totals.empty:
            df_totals.to_excel(w, index=False, sheet_name="Summen")
        if not df_preise.empty:
            df_preise.to_excel(w, index=False, sheet_name="Preise")
        if not df_abr.empty:
            df_abr.to_excel(w, index=False, sheet_name="Abrechnung")
        if report:
            pd.DataFrame({"Report": [report]}).to_excel(w, index=False, sheet_name="Report")
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


def get_pdf_folder_id(_drive, jahr, monat, anlegen=True, prefix="pdfs"):
    """ID eines Monats-Unterordners in 'GH-Rechnungen'. None falls fehlend und anlegen=False."""
    parent = get_gh_folder_id(_drive)
    fname = f"{prefix}_{jahr}_{monat:02d}"
    q = (f"name='{fname}' and '{parent}' in parents "
         f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    if not anlegen:
        return None
    folder = _drive.files().create(
        body={"name": fname, "parents": [parent],
              "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]


def speichere_pdfs_in_drive(_drive, pdfs, jahr, monat):
    """Lädt nur noch nicht abgelegte Original-PDFs in den Monats-Unterordner hoch.
    Gibt die Anzahl neu hochgeladener PDFs zurück."""
    from googleapiclient.http import MediaIoBaseUpload
    if not pdfs:
        return 0
    folder_id = get_pdf_folder_id(_drive, jahr, monat, anlegen=True)
    neu = 0
    for beleg, raw in pdfs.items():
        name = f"INVOICE-{beleg}.pdf"
        q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        existing = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
        if existing:
            continue  # bereits vorhanden → überspringen
        media = MediaIoBaseUpload(io.BytesIO(raw), mimetype="application/pdf")
        _drive.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media, fields="id",
        ).execute()
        neu += 1
    return neu


def lade_pdfs_aus_drive(_drive, jahr, monat):
    """Lädt alle Original-PDFs des Monats. Gibt dict beleg → bytes zurück."""
    from googleapiclient.http import MediaIoBaseDownload
    out = {}
    try:
        folder_id = get_pdf_folder_id(_drive, jahr, monat, anlegen=False)
        if not folder_id:
            return out
        res = _drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            fields="files(id,name)", pageSize=200,
        ).execute()
        for f in res.get("files", []):
            m = re.search(r"INVOICE-(.+)\.pdf$", f["name"], re.IGNORECASE)
            beleg = m.group(1) if m else f["name"]
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=f["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
            out[beleg] = buf.getvalue()
    except Exception:
        pass
    return out


def speichere_abr_pdfs_in_drive(_drive, pdfs, jahr, monat):
    """Speichert nur noch nicht abgelegte Monatsabrechnungs-PDFs im Unterordner.
    Gibt die Anzahl neu hochgeladener PDFs zurück."""
    from googleapiclient.http import MediaIoBaseUpload
    if not pdfs:
        return 0
    folder_id = get_pdf_folder_id(_drive, jahr, monat, anlegen=True, prefix="abrechnungen")
    neu = 0
    for name, raw in pdfs.items():
        name = str(name).replace("'", "_")
        q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        existing = _drive.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
        if existing:
            continue  # bereits vorhanden → überspringen
        media = MediaIoBaseUpload(io.BytesIO(raw), mimetype="application/pdf")
        _drive.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media, fields="id",
        ).execute()
        neu += 1
    return neu


def lade_abr_pdfs_aus_drive(_drive, jahr, monat):
    """Lädt die Monatsabrechnungs-PDFs des Monats. Gibt dict dateiname → bytes zurück."""
    from googleapiclient.http import MediaIoBaseDownload
    out = {}
    try:
        folder_id = get_pdf_folder_id(_drive, jahr, monat, anlegen=False, prefix="abrechnungen")
        if not folder_id:
            return out
        res = _drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            fields="files(id,name)", pageSize=200,
        ).execute()
        for f in res.get("files", []):
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, _drive.files().get_media(fileId=f["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
            out[f["name"]] = buf.getvalue()
    except Exception:
        pass
    return out

# ─── PDF-Parser ───────────────────────────────────────────────────────────────

# Zeilenmuster: Lagerort  Menge  [Einheit/Name...]  [V-Dat]  Pos  PZN
#               VP_mit_MWSt  EK_ohne_MWSt  Warenwert_ohne_MWSt  CODE  S
# CODE = Warencode (FA, OA, FO, FE, FAE, … unterschiedlich lang, ggf. mit Leerzeichen);
#        wir verlangen nach dem Warenwert nur noch einen Großbuchstaben als Bestätigung.
_ZEILEN_RE = re.compile(
    r"^\s*\d+\s+\d+\s+(\d+)\s+.+?\b(\d{8})\b\s+[\d,]+\s+([\d,]+)\s+([\d,]+)\s+[A-Z]",
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


def beleg_aus_dateiname(name: str) -> str:
    m = re.search(r"INVOICE-(\d+)", name, re.IGNORECASE)
    return m.group(1) if m else name


def parse_pdf(datei_bytes: bytes, dateiname: str) -> tuple[pd.DataFrame, float | None]:
    """Gibt (DataFrame mit Positionen, Rechnungssumme aus PDF) zurück."""
    jahr, monat, _ = datum_aus_dateiname(dateiname)
    beleg = beleg_aus_dateiname(dateiname)
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

# ─── Preis-CSV-Parser ─────────────────────────────────────────────────────────

def _preis_zu_float(raw: str):
    raw = str(raw).strip().replace("€", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw:        # deutsches Format: 1.234,56 → 1234.56
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_preis_csv(datei_bytes: bytes, jahr: int, monat: int) -> dict:
    """Liest PZN → Healthii-EK-Preis aus CSV, gefiltert auf Gültigkeit im Monat.
    Gibt {PZN(str, 8-stellig): preis(float)}.

    Erkennt ; oder , als Trenner, deutsches/englisches Dezimalformat sowie
    optionale Spalten valid_from / valid_till (ISO-Datum). Liegt der Monat
    außerhalb der Gültigkeit, wird die PZN nicht bewertet."""
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = datei_bytes.decode(enc)
            break
        except Exception:
            continue
    if not text:
        return {}
    sep = ";" if text.count(";") >= text.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str).fillna("")
    if df.empty or len(df.columns) < 2:
        return {}

    cols = {str(c).lower(): c for c in df.columns}

    def _find(*keys, exclude=None):
        for k in keys:
            for low, orig in cols.items():
                if k in low and orig != exclude:
                    return orig
        return None

    pzn_col   = _find("pzn") or df.columns[0]
    preis_col = _find("price", "preis", "ek", "healthii", exclude=pzn_col)
    if preis_col is None:
        rest = [c for c in df.columns if c != pzn_col]
        preis_col = rest[-1] if rest else None
    if preis_col is None:
        return {}
    from_col = _find("valid_from", "gueltig_von", "von", exclude=pzn_col)
    till_col = _find("valid_till", "valid_to", "gueltig_bis", "bis", exclude=pzn_col)

    # Monatsfenster
    monatsstart = pd.Timestamp(year=int(jahr), month=int(monat), day=1)
    monatsende  = monatsstart + pd.offsets.MonthEnd(0)

    # je PZN den im Monat gültigen Eintrag mit jüngstem valid_from wählen
    best = {}   # pzn → (valid_from_ts, preis)
    for _, row in df.iterrows():
        pzn = re.sub(r"\D", "", str(row[pzn_col]))
        if not pzn:
            continue
        pzn = pzn.zfill(8)
        preis = _preis_zu_float(row[preis_col])
        if preis is None:
            continue

        vf = pd.to_datetime(row[from_col], errors="coerce") if from_col else pd.NaT
        vt = pd.to_datetime(row[till_col], errors="coerce") if till_col else pd.NaT

        # Gültigkeit prüfen: Überlappung mit dem Monat (offene Grenzen erlaubt)
        if from_col or till_col:
            if pd.notna(vf) and vf > monatsende:
                continue
            if pd.notna(vt) and vt < monatsstart:
                continue

        rank = vf if pd.notna(vf) else pd.Timestamp.min
        if pzn not in best or rank >= best[pzn][0]:
            best[pzn] = (rank, preis)

    return {pzn: preis for pzn, (_, preis) in best.items()}

# ─── Monatsabrechnung-Parser (GH) ─────────────────────────────────────────────

# Zeile: [--] DD.MM.YY  01  Rechnungsnr(6)  [Beträge…]  Gesamt  CODE(z.B. NO)
_ABR_RE = re.compile(
    r"^\s*(?:[-–]+\s*)?(\d{2}\.\d{2}\.\d{2})\s+\d+\s+(\d{6})\s+.*?([\d.]+,\d{2})\s+[A-Z]{2}\s*$",
    re.MULTILINE,
)

def parse_abrechnung(datei_bytes: bytes) -> dict:
    """Liest aus einer Phoenix-Monatsabrechnung die abgerechneten Rechnungsnummern.
    Gibt {rechnungsnr(str): {"datum": ISO-str|None, "betrag": float}} zurück."""
    out = {}
    with pdfplumber.open(io.BytesIO(datei_bytes)) as pdf:
        for seite in pdf.pages:
            text = seite.extract_text() or ""
            for m in _ABR_RE.finditer(text):
                betrag = _preis_zu_float(m.group(3))
                if betrag is None:
                    continue
                try:
                    datum = pd.to_datetime(m.group(1), format="%d.%m.%y").date().isoformat()
                except Exception:
                    datum = None
                out[m.group(2)] = {"datum": datum, "betrag": betrag}
    return out


def _abr_norm(v):
    """Normalisiert einen Abrechnungswert auf (datum, betrag) — auch altes Float-Format."""
    if isinstance(v, dict):
        return v.get("datum"), v.get("betrag")
    return None, v

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

    # Klick auf gespeicherten Monat: Auswahl vor Erzeugung der Widgets übernehmen
    if "gh_pending" in st.session_state:
        _pj, _pm = st.session_state.pop("gh_pending")
        st.session_state["gh_jahr"]  = _pj
        st.session_state["gh_monat"] = _pm
    if "gh_monat" not in st.session_state:
        st.session_state["gh_monat"] = heute.month
    if "gh_jahr" not in st.session_state:
        st.session_state["gh_jahr"] = heute.year

    col_m, col_j = st.columns(2)
    monat_auswahl = col_m.selectbox("Monat", list(range(1, 13)),
                                     key="gh_monat",
                                     format_func=lambda m: f"{m:02d}")
    jahr_auswahl  = col_j.number_input("Jahr", min_value=2020, max_value=2099,
                                        step=1, key="gh_jahr")

    if "gh_upl_nonce" not in st.session_state:
        st.session_state.gh_upl_nonce = 0
    uploads = st.file_uploader(
        "PDF-Rechnungen",
        type=["pdf"],
        accept_multiple_files=True,
        help="Mehrere Phoenix-Sammelrechnungen auf einmal auswählen",
        key=f"pdf_upl_{st.session_state.gh_upl_nonce}",
    )

    verarbeiten = st.button("▶ Rechnungen einlesen", use_container_width=True, type="primary",
                             disabled=not uploads)

    st.divider()

    # Healthii-EK-Preise (CSV: PZN + Preis) für den gewählten Monat
    st.header("💶 Healthii-EK-Preise")
    _preise_key = f"gh_preise_{jahr_auswahl}_{monat_auswahl:02d}"
    preis_csv = st.file_uploader(
        "Preisliste (CSV)",
        type=["csv"],
        help="CSV mit Spalten PZN und Preis (z. B. 'Healthii EK'). ; oder , als Trenner.",
        key=f"preis_csv_{jahr_auswahl}_{monat_auswahl:02d}",
    )
    if st.button("▶ Preise laden", use_container_width=True, disabled=not preis_csv):
        preise = parse_preis_csv(preis_csv.read(), int(jahr_auswahl), monat_auswahl)
        if preise:
            st.session_state[_preise_key] = preise
            st.success(f"✓ {len(preise)} im Monat gültige Preise geladen")
        else:
            st.error("Keine im Monat gültigen PZN/Preis-Paare erkannt. Spalten/Datum prüfen.")
    _akt_preise = st.session_state.get(_preise_key) or {}
    if _akt_preise:
        st.caption(f"Aktuell {len(_akt_preise)} Preise hinterlegt.")

    st.divider()

    # Monatsabrechnungen (GH): listen die abgerechneten Rechnungsnummern
    st.header("📑 Monatsabrechnungen")
    _abr_key = f"gh_abr_{jahr_auswahl}_{monat_auswahl:02d}"
    abr_uploads = st.file_uploader(
        "Abrechnungen (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        help="Die GH-Monatsabrechnungen (z. B. 10., 20., Ultimo) auf einmal auswählen.",
        key=f"abr_upload_{jahr_auswahl}_{monat_auswahl:02d}",
    )
    _abrpdf_key = f"gh_abrpdfs_{jahr_auswahl}_{monat_auswahl:02d}"
    if st.button("▶ Abrechnungen einlesen", use_container_width=True, disabled=not abr_uploads):
        abr_neu    = dict(st.session_state.get(_abr_key) or {})
        abrpdf_neu = dict(st.session_state.get(_abrpdf_key) or {})
        n_dok = 0
        for f in abr_uploads:
            try:
                raw = f.read()
                gefunden = parse_abrechnung(raw)
                abr_neu.update(gefunden)
                abrpdf_neu[f.name] = raw
                n_dok += 1
            except Exception as e:
                st.warning(f"❌ {f.name}: {e}")
        if abr_neu:
            st.session_state[_abr_key]    = abr_neu
            st.session_state[_abrpdf_key] = abrpdf_neu
            st.success(f"✓ {n_dok} Abrechnung(en) gelesen — {len(abr_neu)} Rechnungsnummern")
        else:
            st.error("Keine Rechnungsnummern erkannt.")
    _akt_abr = st.session_state.get(_abr_key) or {}
    if _akt_abr:
        st.caption(f"Aktuell {len(_akt_abr)} abgerechnete Rechnungsnummern.")
        if st.button("🗑 Abrechnungen zurücksetzen", use_container_width=True):
            st.session_state[_abr_key]    = {}
            st.session_state[_abrpdf_key] = {}
            st.rerun()

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
                st.caption("Zum Öffnen anklicken:")
                for _f in _archiv:
                    _m = re.search(r"gh_rechnung_(\d{4})_(\d{2})", _f["name"])
                    if _m:
                        _yy, _mm = int(_m.group(1)), int(_m.group(2))
                        _aktiv = (_yy == int(jahr_auswahl) and _mm == monat_auswahl)
                        if st.button(f"{'📂' if _aktiv else '✓'} {_mm:02d}/{_yy}",
                                     key=f"open_{_yy}_{_mm}",
                                     use_container_width=True,
                                     type="primary" if _aktiv else "secondary"):
                            st.session_state["gh_pending"] = (_yy, _mm)
                            st.rerun()
            else:
                st.caption("Noch keine gespeicherten Monate.")
        except Exception:
            pass

# ─── Haupt-Bereich ────────────────────────────────────────────────────────────

monat_label = f"{monat_auswahl:02d}/{jahr_auswahl}"

# Session State-Keys
roh_key    = f"gh_roh_{jahr_auswahl}_{monat_auswahl:02d}"    # Rohzeilen pro Beleg
totals_key = f"gh_totals_{jahr_auswahl}_{monat_auswahl:02d}" # PDF-Summen pro Beleg
agg_key    = f"gh_agg_{jahr_auswahl}_{monat_auswahl:02d}"    # aggregierte Monatstabelle
pdf_key    = f"gh_pdfs_{jahr_auswahl}_{monat_auswahl:02d}"   # Original-PDF-Bytes pro Beleg
preise_key = f"gh_preise_{jahr_auswahl}_{monat_auswahl:02d}" # PZN → Healthii-EK-Preis
abr_key    = f"gh_abr_{jahr_auswahl}_{monat_auswahl:02d}"    # Rechnungsnr → Betrag laut Abrechnung
abrpdf_key = f"gh_abrpdfs_{jahr_auswahl}_{monat_auswahl:02d}" # Abrechnungs-PDFs (dateiname → bytes)
report_key = f"gh_report_{jahr_auswahl}_{monat_auswahl:02d}"  # Freitext-Report zum Monat

for k in [roh_key, totals_key, agg_key, pdf_key, preise_key, abr_key, abrpdf_key]:
    if k not in st.session_state:
        st.session_state[k] = None
if report_key not in st.session_state:
    st.session_state[report_key] = ""

# ─── Gespeicherten Monat automatisch aus Drive laden (einmalig je Monat) ──────

load_flag = f"gh_loaded_{jahr_auswahl}_{monat_auswahl:02d}"
if drive and st.session_state[roh_key] is None and not st.session_state.get(load_flag):
    if monat_existiert_in_drive(drive, int(jahr_auswahl), monat_auswahl):
        df_roh_drive, totals_drive, preise_drive, abr_drive, report_drive = lade_monat_aus_drive(
            drive, int(jahr_auswahl), monat_auswahl
        )
        st.session_state[roh_key] = (
            df_roh_drive if df_roh_drive is not None
            else pd.DataFrame(columns=["PZN", "Menge", "EK_ohne_MWSt", "Warenwert", "Beleg", "Jahr", "Monat"])
        )
        st.session_state[totals_key] = totals_drive
        st.session_state[preise_key] = preise_drive
        st.session_state[abr_key]    = abr_drive
        st.session_state[report_key] = report_drive
        st.session_state[pdf_key]    = lade_pdfs_aus_drive(drive, int(jahr_auswahl), monat_auswahl)
        st.session_state[abrpdf_key] = lade_abr_pdfs_aus_drive(drive, int(jahr_auswahl), monat_auswahl)
    st.session_state[load_flag] = True

# ─── PDFs einlesen ────────────────────────────────────────────────────────────

# Einlese-Meldungen aus dem vorherigen Lauf anzeigen (nach Upload-Reset)
for _lvl, _txt in st.session_state.pop("gh_upl_msgs", []):
    getattr(st, _lvl)(_txt)

if verarbeiten and uploads:
    alle_zeilen = []
    totals_neu  = {}   # beleg → total_pdf
    pdfs_neu    = {}   # beleg → original PDF-Bytes
    fehler = []

    fortschritt = st.progress(0, text="Lese PDFs …")

    for i, pdf_file in enumerate(uploads):
        fortschritt.progress((i + 1) / len(uploads), text=pdf_file.name)
        try:
            raw = pdf_file.read()
            df_pdf, total_pdf = parse_pdf(raw, pdf_file.name)
            beleg = df_pdf["Beleg"].iloc[0] if not df_pdf.empty else beleg_aus_dateiname(pdf_file.name)
            if not df_pdf.empty:
                alle_zeilen.append(df_pdf)
            # Beleg in jedem Fall führen (auch ohne Positionen) und PDF mitsichern
            totals_neu[beleg] = total_pdf
            pdfs_neu[beleg]   = raw
        except Exception as e:
            fehler.append(f"❌ {pdf_file.name}: {e}")

    fortschritt.empty()

    msgs = []
    if alle_zeilen or totals_neu:
        df_neu = pd.concat(alle_zeilen, ignore_index=True) if alle_zeilen else None

        # Mit bestehendem Monat zusammenführen (Duplikat-Belege ersetzen)
        df_alt = st.session_state[roh_key]
        belege_neu = set(totals_neu.keys())
        if df_alt is not None and not df_alt.empty:
            df_alt = df_alt[~df_alt["Beleg"].isin(belege_neu)]
            df_gesamt = pd.concat([df_alt, df_neu], ignore_index=True) if df_neu is not None else df_alt
        else:
            df_gesamt = df_neu

        totals_alt = st.session_state[totals_key] or {}
        totals_alt.update(totals_neu)

        pdfs_alt = st.session_state[pdf_key] or {}
        pdfs_alt.update(pdfs_neu)

        st.session_state[roh_key]    = df_gesamt
        st.session_state[totals_key] = totals_alt
        st.session_state[pdf_key]    = pdfs_alt

        msgs.append(("success", f"✓ {len(totals_neu)} Beleg(e) eingelesen."))
        for f in fehler:
            msgs.append(("warning", f))
    else:
        msgs.append(("error", "Keine Daten konnten extrahiert werden."))
        for f in fehler:
            msgs.append(("warning", f))

    # Meldungen merken, Upload-Bereich leeren (neuer Key) und neu rendern
    st.session_state["gh_upl_msgs"] = msgs
    st.session_state.gh_upl_nonce += 1
    st.rerun()

# ─── Daten laden & in Tabs darstellen ─────────────────────────────────────────

df_roh = st.session_state.get(roh_key)
if df_roh is None:
    df_roh = pd.DataFrame(columns=["PZN", "Menge", "EK_ohne_MWSt", "Warenwert", "Beleg", "Jahr", "Monat"])
totals = st.session_state.get(totals_key) or {}
pdfs   = st.session_state.get(pdf_key) or {}
preise = st.session_state.get(preise_key) or {}
abr    = st.session_state.get(abr_key) or {}

# Alle bekannten Belege (inkl. solcher ohne erkannte Positionen)
belege_alle = sorted(set(df_roh["Beleg"].unique()) | set(totals.keys()) | set(pdfs.keys()))

if not belege_alle and not abr:
    st.markdown("""
    <div style='text-align:center;padding:80px 0;color:#9CA3AF;'>
        <div style='font-size:48px;'>📄</div>
        <div style='font-size:16px;margin-top:12px;'>
            Monat auswählen und PDFs hochladen — oder gespeicherten Monat links anklicken
        </div>
    </div>""", unsafe_allow_html=True)
else:
    # Aggregierte Monatstabelle (auch fürs Speichern benötigt)
    df_agg = (
        df_roh
        .groupby("PZN", as_index=False)
        .agg(Menge=("Menge", "sum"), Warenwert=("Warenwert", "sum"))
        .sort_values("Warenwert", ascending=False)
        .reset_index(drop=True)
    )
    st.session_state[agg_key] = df_agg

    # ─── Globale Speichern-Leiste (über allen Tabs sichtbar) ───────────────────
    def _speichern_ausfuehren():
        abr_session    = st.session_state.get(abr_key) or {}
        abrpdf_session = st.session_state.get(abrpdf_key) or {}
        report_session = st.session_state.get(report_key) or ""
        speichere_monat_in_drive(
            drive, df_agg, df_roh, totals, preise, abr_session, report_session,
            int(jahr_auswahl), monat_auswahl
        )
        pdfs_session = st.session_state.get(pdf_key) or {}
        n_neu  = speichere_pdfs_in_drive(drive, pdfs_session, int(jahr_auswahl), monat_auswahl)
        n_neu += speichere_abr_pdfs_in_drive(drive, abrpdf_session, int(jahr_auswahl), monat_auswahl)
        return n_neu

    def _speichern_mit_feedback(prefix="✓"):
        try:
            with st.spinner("Speichere in Drive …"):
                n_neu = _speichern_ausfuehren()
            st.success(f"{prefix} Stand gespeichert ({n_neu} neue PDF(s) hochgeladen)")
        except Exception as e:
            st.error(f"Drive-Fehler: {e}")

    confirm_key = f"gh_confirm_overwrite_{jahr_auswahl}_{monat_auswahl:02d}"

    if drive:
        _sp_l, _sp_r = st.columns([3, 1])
        with _sp_r:
            if st.button("💾 Aktuellen Stand speichern", use_container_width=True, type="primary"):
                if monat_existiert_in_drive(drive, int(jahr_auswahl), monat_auswahl):
                    st.session_state[confirm_key] = True
                    st.rerun()
                else:
                    _speichern_mit_feedback()
        if st.session_state.get(confirm_key):
            st.warning(f"Für **{monat_label}** existiert bereits eine Speicherung in Drive. Überschreiben?")
            _ow_l, _ow_r = st.columns([3, 1])
            with _ow_r:
                if st.button("Ja, überschreiben", type="primary",
                             use_container_width=True, key=f"ow_yes_{confirm_key}"):
                    st.session_state[confirm_key] = False
                    _speichern_mit_feedback(prefix="✓ Überschrieben —")
                if st.button("Abbrechen", use_container_width=True, key=f"ow_no_{confirm_key}"):
                    st.session_state[confirm_key] = False
                    st.rerun()

    tab_abgleich, tab_beleg, tab_monat = st.tabs(
        ["📑 Abgleich Monatsabrechnung", "🧾 Belegkontrolle", "📊 Monatstabelle"]
    )

    # ════ Tab 1: Abgleich Monatsabrechnung ════
    with tab_abgleich:
        if abr:
            st.divider()
            st.subheader(f"Abgleich Monatsabrechnung {monat_label}")

            # Vorhandene Belegnummern dieses Monats
            _df_roh = st.session_state.get(roh_key)
            belege_vorhanden = set()
            if _df_roh is not None and not _df_roh.empty:
                belege_vorhanden |= set(_df_roh["Beleg"].astype(str))
            belege_vorhanden |= {str(b) for b in (st.session_state.get(totals_key) or {})}
            belege_vorhanden |= {str(b) for b in (st.session_state.get(pdf_key) or {})}

            df_abr = pd.DataFrame(
                [{"Lieferdatum": _abr_norm(v)[0],
                  "Rechnungsnr": str(n),
                  "Betrag laut Abrechnung": _abr_norm(v)[1]}
                 for n, v in abr.items()]
            )
            df_abr["_dt"] = pd.to_datetime(df_abr["Lieferdatum"], errors="coerce")
            df_abr["Vorhanden"] = df_abr["Rechnungsnr"].apply(
                lambda n: "✅ vorhanden" if n in belege_vorhanden else "❌ fehlt"
            )
            df_abr = (
                df_abr.sort_values(["_dt", "Rechnungsnr"], na_position="last")
                .drop(columns="_dt")
                .reset_index(drop=True)
            )
            # Spaltenreihenfolge: Lieferdatum zuerst
            df_abr = df_abr[["Lieferdatum", "Rechnungsnr", "Betrag laut Abrechnung", "Vorhanden"]]

            fehlend  = df_abr[df_abr["Vorhanden"] == "❌ fehlt"]
            n_fehlend = len(fehlend)
            summe_fehlend = fehlend["Betrag laut Abrechnung"].sum()

            # Belege, die wir haben, aber die in keiner Abrechnung stehen (Gegenkontrolle)
            extra = sorted(belege_vorhanden - set(df_abr["Rechnungsnr"]))

            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Abgerechnet", len(df_abr))
            a2.metric("✅ Vorhanden", int((df_abr["Vorhanden"] == "✅ vorhanden").sum()))
            a3.metric("❌ Fehlend", n_fehlend)
            a4.metric("Summe fehlend", f"{summe_fehlend:,.2f} €")

            if n_fehlend:
                st.warning(f"{n_fehlend} laut Abrechnung berechnete Belege fehlen "
                           f"(Summe {summe_fehlend:,.2f} €) — siehe ❌ in der Tabelle.")
            else:
                st.success("Alle laut Abrechnung berechneten Belege sind vorhanden.")

            def _abr_stil(row):
                rot = "background-color: #FEE2E2"
                return [rot if row["Vorhanden"] == "❌ fehlt" else "" for _ in row]

            styler_abr = (
                df_abr.style.apply(_abr_stil, axis=1)
                .format({
                    "Betrag laut Abrechnung": lambda v: f"{v:,.2f} €",
                    "Lieferdatum": lambda v: "—" if not v or pd.isna(v)
                    else pd.to_datetime(v).strftime("%d.%m.%Y"),
                })
            )
            st.dataframe(styler_abr, use_container_width=True, hide_index=True)

            _abr_buf = io.BytesIO()
            df_abr.to_excel(_abr_buf, index=False, sheet_name="Abrechnungsabgleich")
            st.download_button(
                "📥 Abgleich als Excel",
                data=_abr_buf.getvalue(),
                file_name=f"abrechnungsabgleich_{jahr_auswahl}_{monat_auswahl:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_abr_{jahr_auswahl}_{monat_auswahl:02d}",
            )

            if extra:
                st.caption(f"ℹ️ {len(extra)} vorhandene Belege stehen in keiner Abrechnung: "
                           f"{', '.join(extra[:30])}{' …' if len(extra) > 30 else ''}")

            # Hinterlegte Abrechnungs-PDFs anzeigen/herunterladen
            abr_pdfs = st.session_state.get(abrpdf_key) or {}
            if abr_pdfs:
                with st.expander(f"📑 {len(abr_pdfs)} Abrechnungs-PDF(s)"):
                    for _name, _raw in abr_pdfs.items():
                        st.download_button(
                            f"📥 {_name}",
                            data=_raw,
                            file_name=_name,
                            mime="application/pdf",
                            key=f"dl_abrpdf_{jahr_auswahl}_{monat_auswahl:02d}_{_name}",
                        )

        else:
            st.info("Noch keine Monatsabrechnungen geladen — links in der Sidebar die Abrechnungen (PDF) hochladen und „▶ Abrechnungen einlesen“ klicken.")

    # ════ Tab 2: Belegkontrolle ════
    with tab_beleg:
        if belege_alle:
            st.subheader(f"Belegkontrolle {monat_label}")

            # Beleg-Übersicht aufbauen — auch Belege mit 0 Positionen
            df_belege = pd.DataFrame({"Beleg": belege_alle})
            if not df_roh.empty:
                grp = (
                    df_roh.groupby("Beleg", as_index=False)
                    .agg(Positionen=("PZN", "count"), Warenwert_berechnet=("Warenwert", "sum"))
                )
                df_belege = df_belege.merge(grp, on="Beleg", how="left")
            else:
                df_belege["Positionen"] = 0
                df_belege["Warenwert_berechnet"] = 0.0
            df_belege["Positionen"]          = df_belege["Positionen"].fillna(0).astype(int)
            df_belege["Warenwert_berechnet"] = df_belege["Warenwert_berechnet"].fillna(0.0)
            df_belege["Warenwert_Beleg"]     = df_belege["Beleg"].map(totals)
            df_belege["Differenz"]           = (
                df_belege["Warenwert_berechnet"] - df_belege["Warenwert_Beleg"]
            ).round(2)

            def _status(r):
                if r["Positionen"] == 0:
                    return "❌ Keine Positionen"
                d = r["Differenz"]
                if pd.notna(d) and abs(d) < 0.01:
                    return "✅"
                if pd.notna(d):
                    return "⚠️ Abweichung"
                return "❓"
            df_belege["Status"] = df_belege.apply(_status, axis=1)
            df_belege = df_belege.sort_values("Beleg").reset_index(drop=True)

            n_ok   = int((df_belege["Status"] == "✅").sum())
            n_abw  = int((df_belege["Status"] == "⚠️ Abweichung").sum())
            n_leer = int((df_belege["Positionen"] == 0).sum())
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Belege", len(df_belege))
            c2.metric("✅ OK", n_ok)
            c3.metric("⚠️ Abweichungen", n_abw)
            c4.metric("❌ Keine Pos.", n_leer)
            c5.metric("Gesamtwert", f"{df_belege['Warenwert_berechnet'].sum():,.2f} €")

            st.divider()

            # Übersichtstabelle — Zeile anklicken, um den Beleg zu prüfen/korrigieren
            st.caption("Zeile anklicken, um den Beleg gegen das PDF zu prüfen und zu korrigieren.")
            df_anzeige = df_belege[
                ["Status", "Beleg", "Positionen", "Warenwert_berechnet", "Warenwert_Beleg", "Differenz"]
            ].reset_index(drop=True)
            tabelle_event = st.dataframe(
                df_anzeige,
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
                on_select="rerun",
                selection_mode="single-row",
                key=f"belegtabelle_{jahr_auswahl}_{monat_auswahl:02d}",
            )

            # Belegkontrolle als Excel herunterladen
            _bk_buf = io.BytesIO()
            df_anzeige.rename(columns={
                "Warenwert_berechnet": "Berechnet (€)",
                "Warenwert_Beleg":     "Laut Beleg (€)",
                "Differenz":           "Differenz (€)",
                "Positionen":          "Pos.",
                "Beleg":               "Belegnr.",
            }).to_excel(_bk_buf, index=False, sheet_name="Belegkontrolle")
            st.download_button(
                "📥 Belegkontrolle als Excel",
                data=_bk_buf.getvalue(),
                file_name=f"belegkontrolle_{jahr_auswahl}_{monat_auswahl:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_belegkontrolle_{jahr_auswahl}_{monat_auswahl:02d}",
            )

            auswahl_zeilen = tabelle_event.selection.rows if tabelle_event.selection else []
            aktiver_beleg  = df_anzeige.iloc[auswahl_zeilen[0]]["Beleg"] if auswahl_zeilen else None

            # ─── Position korrigieren: ausgewählter Beleg + zugehöriges PDF ────────────
            if aktiver_beleg is not None:
                beleg = aktiver_beleg
                zeile = df_belege[df_belege["Beleg"] == beleg].iloc[0]
                diff      = zeile["Differenz"]
                beleg_wert = zeile["Warenwert_Beleg"]
                ist_ok    = zeile["Status"] == "✅"

                st.divider()
                st.subheader(f"{'✅' if ist_ok else '⚠️'} Beleg {beleg} korrigieren")

                m1, m2, m3 = st.columns(3)
                m1.metric("Berechnet", f"{zeile['Warenwert_berechnet']:,.2f} €")
                m2.metric("Laut Beleg", f"{beleg_wert:,.2f} €" if pd.notna(beleg_wert) else "—")
                m3.metric("Differenz",  f"{diff:+.2f} €" if pd.notna(diff) else "—")

                df_b = df_roh[df_roh["Beleg"] == beleg].copy()
                edit_cols = ["PZN", "Menge", "EK_ohne_MWSt", "Warenwert"]
                edited = st.data_editor(
                    df_b[edit_cols].reset_index(drop=True),
                    column_config={
                        "PZN":          st.column_config.TextColumn("PZN"),
                        "Menge":        st.column_config.NumberColumn("Menge",        min_value=0, step=1),
                        "EK_ohne_MWSt": st.column_config.NumberColumn("EK o. MWSt (€)", format="%.2f"),
                        "Warenwert":    st.column_config.NumberColumn("Warenwert (€)", format="%.2f"),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key=f"editor_beleg_{beleg}",
                )

                # Live-Hinweis, ob die Korrektur die Abweichung schließt
                neuer_wert = pd.to_numeric(edited["Warenwert"], errors="coerce").sum()
                if pd.notna(beleg_wert):
                    neue_diff = round(neuer_wert - beleg_wert, 2)
                    if abs(neue_diff) < 0.01:
                        st.success(f"Nach Korrektur stimmt der Warenwert überein ({neuer_wert:,.2f} €).")
                    else:
                        st.warning(f"Nach Korrektur weiterhin {neue_diff:+.2f} € Differenz "
                                   f"({neuer_wert:,.2f} € berechnet vs. {beleg_wert:,.2f} € laut Beleg).")

                if st.button("💾 Korrekturen übernehmen", key=f"save_{beleg}", type="primary"):
                    edited = edited[edited["PZN"].notna() & (edited["PZN"].astype(str) != "")]
                    edited["Beleg"] = beleg
                    edited["Jahr"]  = df_b["Jahr"].iloc[0]  if not df_b.empty else int(jahr_auswahl)
                    edited["Monat"] = df_b["Monat"].iloc[0] if not df_b.empty else monat_auswahl
                    df_rest = df_roh[df_roh["Beleg"] != beleg]
                    st.session_state[roh_key] = pd.concat([df_rest, edited], ignore_index=True)
                    st.success(f"✓ Beleg {beleg} aktualisiert")
                    st.rerun()

                # Zugehöriges Original-PDF anzeigen
                st.markdown("##### Zugehörige Rechnung (PDF)")
                pdfs = st.session_state.get(pdf_key) or {}
                pdf_bytes = pdfs.get(beleg)
                if pdf_bytes:
                    if pdf_viewer is not None:
                        pdf_viewer(
                            pdf_bytes,
                            width="100%",
                            height=820,
                            key=f"pdfview_{beleg}",
                        )
                    else:
                        # Fallback: base64-iframe (wird von manchen Browsern blockiert)
                        b64 = base64.b64encode(pdf_bytes).decode()
                        st.markdown(
                            f'<iframe src="data:application/pdf;base64,{b64}" '
                            f'width="100%" height="820px" '
                            f'style="border:1px solid #E5E7EB;border-radius:10px;"></iframe>',
                            unsafe_allow_html=True,
                        )
                    st.download_button(
                        "📥 PDF herunterladen",
                        data=pdf_bytes,
                        file_name=f"INVOICE-{beleg}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_{beleg}",
                    )
                else:
                    st.info("Das Original-PDF ist nur in der Sitzung verfügbar, in der es hochgeladen "
                            "wurde. Lade die Rechnung erneut hoch, um sie hier anzuzeigen.")

        else:
            st.info("Noch keine Belege für diesen Monat — links Sammelrechnungen hochladen.")

    # ════ Tab 3: Monatstabelle ════
    with tab_monat:
        if belege_alle:
            st.subheader(f"Monatstabelle {monat_label}")

            # Healthii-EK-Bewertung: Menge × hinterlegter Preis
            df_disp = df_agg.copy()
            df_disp["Healthii EK Preise"] = df_disp.apply(
                lambda r: round(r["Menge"] * preise[r["PZN"]], 2) if r["PZN"] in preise else pd.NA,
                axis=1,
            )
            # Relative Abweichung Warenwert vs. Healthii-EK-Bewertung
            _ww  = pd.to_numeric(df_disp["Warenwert"], errors="coerce")
            _hk  = pd.to_numeric(df_disp["Healthii EK Preise"], errors="coerce")
            df_disp["_abw"] = (_ww - _hk).abs() / _ww.where(_ww != 0)
            df_disp["_unbewertet"] = df_disp["Healthii EK Preise"].isna()
            # Auffällig: keine Bewertung ODER Abweichung > 50 %
            df_disp["_flag"] = df_disp["_unbewertet"] | (df_disp["_abw"] > 0.5)
            # Auffällige Zeilen nach oben, sonst nach Warenwert
            df_disp = (
                df_disp.sort_values(["_flag", "Warenwert"], ascending=[False, False])
                .reset_index(drop=True)
            )

            n_unbewertet = int(df_disp["_unbewertet"].sum())
            n_abw = int((df_disp["_abw"] > 0.5).sum())
            if n_abw:
                st.warning(f"{n_abw} PZN mit über 50 % Abweichung zwischen Warenwert und "
                           f"Healthii-EK-Bewertung — oben gelb markiert.")
            if preise and n_unbewertet:
                st.warning(f"{n_unbewertet} von {len(df_disp)} PZN konnten nicht bewertet werden "
                           f"(kein Preis hinterlegt) — oben gelb markiert.")
            elif not preise:
                st.info("Keine Healthii-EK-Preise geladen — Spalte bleibt leer. "
                        "CSV links in der Sidebar hochladen.")

            df_vis = df_disp.drop(columns=["_unbewertet", "_abw", "_flag"])

            summe_ww = df_vis["Warenwert"].sum()
            summe_hk = pd.to_numeric(df_vis["Healthii EK Preise"], errors="coerce").sum()
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Warenwert GH-Rechnungen", f"{summe_ww:,.2f} €")
            mc2.metric("Summe Healthii-EK-Preise",
                       f"{summe_hk:,.2f} €" if preise else "—")
            mc3.metric("Unterschiedliche PZN", f"{df_vis['PZN'].nunique():,}")
            st.divider()

            def _zeilen_stil(row):
                gelb = "background-color: #FEF9C3"
                hk = row["Healthii EK Preise"]
                ww = row["Warenwert"]
                auffaellig = (
                    pd.isna(hk)
                    or (pd.notna(ww) and ww != 0 and abs(ww - hk) / ww > 0.5)
                )
                return [gelb if auffaellig else "" for _ in row]

            styler = (
                df_vis.style
                .apply(_zeilen_stil, axis=1)
                .format({
                    "Menge":              "{:.0f}",
                    "Warenwert":          lambda v: f"{v:.2f} €",
                    "Healthii EK Preise": lambda v: "—" if pd.isna(v) else f"{v:.2f} €",
                })
            )

            st.caption("Zeile anklicken, um alle Einzelpositionen dieser PZN im Monat zu sehen.")
            monat_event = st.dataframe(
                styler, use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key=f"monatstabelle_{jahr_auswahl}_{monat_auswahl:02d}",
            )

            _msel = monat_event.selection.rows if monat_event.selection else []
            if _msel:
                _pzn = df_vis.iloc[_msel[0]]["PZN"]
                st.markdown(f"##### Einzelpositionen PZN {_pzn}")

                # Lieferdatum je Beleg aus den Abrechnungsdaten
                beleg_datum = {str(n): _abr_norm(v)[0] for n, v in abr.items()}
                det = df_roh[df_roh["PZN"] == _pzn].copy()
                det["Datum"] = det["Beleg"].astype(str).map(beleg_datum)
                det = det[["Datum", "Beleg", "Menge", "EK_ohne_MWSt"]]
                det["_dt"] = pd.to_datetime(det["Datum"], errors="coerce")
                det = det.sort_values(["_dt", "Beleg"], na_position="last").drop(columns="_dt")

                st.dataframe(
                    det.style.format({
                        "Datum":        lambda v: "—" if not v or pd.isna(v)
                        else pd.to_datetime(v).strftime("%d.%m.%Y"),
                        "Menge":        "{:.0f}",
                        "EK_ohne_MWSt": lambda v: "—" if pd.isna(v) else f"{v:.2f} €",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Beleg":        st.column_config.TextColumn("Belegnr."),
                        "EK_ohne_MWSt": st.column_config.Column("EK o. MWSt"),
                    },
                )
                st.caption(f"Summe Menge: {int(det['Menge'].sum())} · {len(det)} Position(en)")

            _buf = io.BytesIO()
            with pd.ExcelWriter(_buf, engine="openpyxl") as _w:
                _sheet = f"Monat {monat_auswahl:02d}-{jahr_auswahl}"
                df_vis.to_excel(_w, index=False, sheet_name=_sheet)
                df_belege.to_excel(_w, index=False, sheet_name="Belegkontrolle")
            st.download_button(
                label="📥 Excel herunterladen",
                data=_buf.getvalue(),
                file_name=f"gh_rechnung_{jahr_auswahl}_{monat_auswahl:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.divider()
            st.markdown(f"##### Report {monat_label}")
            st.text_area(
                "Notizen / Report zum Monat",
                key=report_key,
                height=200,
                placeholder="Auffälligkeiten, Klärungen, offene Punkte zum Monat …",
                label_visibility="collapsed",
            )
            st.caption("Wird mit „💾 Aktuellen Stand speichern“ oben in Drive gesichert.")

        else:
            st.info("Noch keine Belege für diesen Monat — links Sammelrechnungen hochladen.")
