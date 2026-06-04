"""
Healthii Purchasing Agent – Leopold
Streamlit Web App

Starten: streamlit run app.py
"""

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

    # Login-Seite im Healthii-Stil
    st.markdown("""
    <div style='max-width:420px;margin:80px auto 0;'>
        <div style='text-align:center;margin-bottom:32px;'>
            <span style='font-size:28px;font-weight:700;color:#111827;letter-spacing:-0.5px;'>healthii</span>
            <span style='display:inline-block;margin-left:10px;background:#F0FDF9;color:#0D9488;
                         font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;
                         letter-spacing:0.5px;vertical-align:middle;'>PURCHASING</span>
        </div>
        <div style='background:white;border:1px solid #E5E7EB;border-radius:16px;
                    padding:32px;box-shadow:0 4px 16px rgba(0,0,0,0.06);'>
            <h3 style='margin:0 0 6px;color:#111827;font-size:20px;'>Anmelden</h3>
            <p style='color:#6B7280;font-size:14px;margin:0 0 24px;'>
                Bitte melde dich an um fortzufahren.
            </p>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        pw = st.text_input("Passwort", type="password",
                           label_visibility="collapsed",
                           placeholder="Passwort eingeben …")
        if st.button("Anmelden", use_container_width=True, type="primary"):
            if pw == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Falsches Passwort. Bitte erneut versuchen.")

    st.markdown("</div></div>", unsafe_allow_html=True)
    st.stop()

check_password()

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Hintergrund */
    [data-testid="stAppViewContainer"] { background: #F9FAFB; }
    [data-testid="stMain"] { background: #F9FAFB; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #FFFFFF;
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

# ─── Header ───────────────────────────────────────────────────────────────────

heute = date.today()
kw    = heute.isocalendar()[1]
year  = heute.year

# Header im Healthii-Stil
drive_status_color = "#0D9488" if st.session_state.drive else "#EF4444"
drive_status_text  = "Drive verbunden" if st.session_state.drive else "Drive nicht verbunden"

st.markdown(f"""
<div style='display:flex;align-items:center;justify-content:space-between;
            padding:0 0 20px 0;border-bottom:1px solid #E5E7EB;margin-bottom:24px;'>
    <div style='display:flex;align-items:center;gap:12px;'>
        <span style='font-size:24px;font-weight:700;color:#111827;letter-spacing:-0.5px;'>healthii</span>
        <span style='background:#F0FDF9;color:#0D9488;font-size:11px;font-weight:600;
                     padding:3px 10px;border-radius:20px;letter-spacing:0.5px;'>PURCHASING</span>
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
    )

    if uploaded:
        excel_bytes = uploaded.read()

        with st.spinner("Berechne Bestellvorschlag …"):
            letzte_excel         = finde_letzte_bestellung_excel()
            letzte_bestellung_df = lade_letzte_bestellung(letzte_excel)

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

            ergebnis = berechne_bestellvorschlag(excel_bytes, letzte_bestellung_df, mbw_ausnahmen)
            st.session_state.ergebnis         = ergebnis
            st.session_state.excel_bytes_input = excel_bytes
            if not ergebnis["bestellen"].empty:
                st.session_state.df_bestellen_edit = ergebnis["bestellen"].copy()
            else:
                st.session_state.df_bestellen_edit = pd.DataFrame()

        st.success(f"✓ {uploaded.name}")

    st.divider()

    # ── Letzte Bestellung Status ──
    st.header("📋 Letzte Bestellung")
    hist_name, df_hist_sidebar = finde_letzte_bestellung(st.session_state.drive)
    if df_hist_sidebar is not None:
        n_gesamt = len(df_hist_sidebar)
        n_offen  = len(df_hist_sidebar[
            df_hist_sidebar["eingelagert"].astype(str).str.strip().str.lower() == "nein"
        ])
        st.caption(f"📄 {hist_name}")
        c1, c2 = st.columns(2)
        c1.metric("Offen", n_offen, help="Noch nicht eingelagert")
        c2.metric("Eingelagert", n_gesamt - n_offen)
    else:
        st.info("Keine Bestellhistorie gefunden")

# ─── Kein Upload → Hinweis ────────────────────────────────────────────────────

if st.session_state.ergebnis is None:
    st.markdown("""
    <div style='text-align:center;padding:60px 0;color:#aaa;'>
        <div style='font-size:48px;'>📄</div>
        <div style='font-size:18px;margin-top:12px;'>
            Bitte <b>wiederbestellung.xlsx</b> in der Seitenleiste hochladen
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─── Ergebnis ─────────────────────────────────────────────────────────────────

ergebnis       = st.session_state.ergebnis
df_bestellen   = st.session_state.df_bestellen_edit
df_unter_mbw   = ergebnis["unter_mbw"] if ergebnis else pd.DataFrame()

# KPI-Leiste
c1, c2, c3, c4 = st.columns(4)
if df_bestellen is not None and not df_bestellen.empty:
    c1.metric("Gesamtbestellwert",  f"{df_bestellen['Bestellwert'].sum():,.0f} €")
    c2.metric("Hersteller",         df_bestellen["Hersteller"].nunique())
    c3.metric("Positionen",         len(df_bestellen))
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
    if df_bestellen is None or df_bestellen.empty:
        st.info("Keine Bestellungen über MBW.")
    else:
        with st.expander("🔍 Berechnungslog"):
            for eintrag in ergebnis["log"]:
                farbe = "green" if "✓" in eintrag else "red"
                st.markdown(f"<span style='color:{farbe}'>{eintrag}</span>", unsafe_allow_html=True)

        st.subheader("Bestellmengen anpassen")
        st.caption("Nur die Spalte **Bestellmenge** ist editierbar. Bestellwert aktualisiert sich automatisch.")

        # Anzeigespalten
        basis_spalten = [
            "Hersteller", "Pzn", "Artikelname", "Bestellmenge",
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

        edited = st.data_editor(
            df_display,
            column_config=col_config,
            use_container_width=True,
            hide_index=True,
            key="editor_tab1",
        )

        # Bestellwert nach Mengenänderung neu berechnen
        edited["Bestellwert"] = edited["Bestellmenge"] * edited["Rechnungs Netto Ek Ve1"]
        st.session_state.df_bestellen_edit.loc[edited.index, "Bestellmenge"] = edited["Bestellmenge"]
        st.session_state.df_bestellen_edit.loc[edited.index, "Bestellwert"]  = edited["Bestellwert"]

        st.divider()

        # Excel vorbereiten
        ergebnis_export = dict(ergebnis)
        ergebnis_export["bestellen"] = st.session_state.df_bestellen_edit
        excel_out = erstelle_bestellsheet(ergebnis_export, kw, year)

        col_dl, col_save = st.columns(2)

        with col_dl:
            if excel_out:
                st.download_button(
                    label="📥 Purchase-Order herunterladen",
                    data=excel_out,
                    file_name=f"Purchase-Order-KW{kw:02d}-{year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )

        with col_save:
            if st.button("💾 Abschließen & in Drive archivieren", use_container_width=True):
                with st.spinner("Speichere …"):
                    try:
                        df_final   = st.session_state.df_bestellen_edit
                        drive_conn = st.session_state.drive

                        # Bestellhistorie speichern (lokal + Drive)
                        speichere_historie(ergebnis["df_input"], df_final, drive_conn)

                        # Purchase-Order lokal speichern + Drive
                        order_name = f"Purchase-Order-KW{kw:02d}-{year}.xlsx"
                        order_path = os.path.join(BASE_DIR, order_name)
                        with open(order_path, "wb") as f:
                            f.write(excel_out)
                        if drive_conn:
                            week_folder_id = get_week_folder_id(drive_conn, kw, year)
                            upload_bytes_to_drive(
                                drive_conn, excel_out, order_name, week_folder_id,
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
    if df_unter_mbw.empty:
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
    hist_name_t3, df_hist = finde_letzte_bestellung(st.session_state.drive)

    if df_hist is None:
        st.info("Noch keine Bestellhistorie vorhanden.")
    else:
        letzte_excel = finde_letzte_bestellung_excel()  # für lokales Speichern
        st.subheader(f"📄 {hist_name_t3}")

        df_hist["Pzn"] = df_hist["Pzn"].apply(
            lambda x: str(int(float(x))) if pd.notna(x) else ""
        )

        hist_cols = [
            "eingelagert", "Pzn", "Artikelname", "Hersteller",
            "Bestellmenge", "Lagerbestand", "Verkaeufe L30", "Verkaeufe L90",
        ]
        hist_cols = [c for c in hist_cols if c in df_hist.columns]

        n_offen = (df_hist["eingelagert"].astype(str).str.strip().str.lower() == "nein").sum()
        st.caption(f"{n_offen} von {len(df_hist)} Positionen noch nicht eingelagert")

        edited_hist = st.data_editor(
            df_hist[hist_cols],
            column_config={
                "eingelagert": st.column_config.SelectboxColumn(
                    "Eingelagert",
                    options=["nein", "ja"],
                    required=True,
                    width="small",
                ),
                "Pzn":         st.column_config.TextColumn("PZN",        disabled=True, width="small"),
                "Artikelname": st.column_config.TextColumn("Artikelname", disabled=True, width="large"),
                "Hersteller":  st.column_config.TextColumn("Hersteller",  disabled=True),
                "Bestellmenge":st.column_config.NumberColumn("Bestellmenge", disabled=True),
                "Lagerbestand":st.column_config.NumberColumn("Lagerbestand", disabled=True),
                "Verkaeufe L30":st.column_config.NumberColumn("L30",         disabled=True),
                "Verkaeufe L90":st.column_config.NumberColumn("L90",         disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="editor_historie",
        )

        if st.button("💾 Änderungen speichern", type="primary"):
            df_hist[hist_cols] = edited_hist
            df_hist.to_excel(letzte_excel, index=False, sheet_name="Abfrageergebnis")
            st.success("✓ Bestellhistorie aktualisiert")
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
