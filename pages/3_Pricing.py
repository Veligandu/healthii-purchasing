"""
Healthii – Pricing
Preisvergleich / EK-Preispflege.
"""

import base64
import calendar
import io
import math
import os
import re
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

from purchasing_agent import upload_bytes_to_drive

# ─── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Pricing | Healthii",
    page_icon=":material/payments:",
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
span[data-testid="stIconMaterial"] { color: #2C2C2A; vertical-align: middle; }
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

# ─── Gemeinsame Logik (pricing_lib) ─────────────────────────────────────────────
# importlib.reload erzwingt das Neu-Einlesen von pricing_lib: Streamlit Cloud hält
# importierte Hilfsmodule in sys.modules über Deploys hinweg im Cache, wodurch nach
# Änderungen an pricing_lib sonst ein ImportError auftritt (alte Modulversion).
import importlib
import pricing_lib as pl
importlib.reload(pl)
from pricing_lib import (
    CHANNEL_COLS, MASTER_CHANNEL_COLS, PRICE_EDGES, PRICE_LABELS,
    REF_QUOTE, QUOTE_LABEL,
    parse_date_from_filename, parse_quote_bytes, parse_channel_bytes,
    parse_master_bytes, parse_orderlines_bytes, ref_for_source, ref_label,
    channel_label_list, assign_price_cluster, fmt_date,
)

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

# Cache-Wrapper um die Drive-Zugriffe (Verbindung wird pro Rerun neu aufgebaut,
# deshalb _drive nicht als Cache-Key verwenden → führender Unterstrich)
@st.cache_data(ttl=120, show_spinner=False)
def get_pricing_folder_id(_drive):
    return pl.get_pricing_folder_id(_drive)

@st.cache_data(ttl=60, show_spinner=False)
def list_snapshots(_drive):
    return pl.list_snapshots(_drive)

@st.cache_data(ttl=60, show_spinner="Snapshot wird geladen …")
def load_snapshot(_drive, iso_datum: str):
    return pl.load_snapshot(_drive, iso_datum)

@st.cache_data(ttl=60, show_spinner="Masterdatei wird geladen …")
def load_master(_drive, iso_datum: str):
    return pl.load_master(_drive, iso_datum)

@st.cache_data(ttl=60, show_spinner="Channel-Preise werden geladen …")
def load_channel(_drive, iso_datum: str):
    return pl.load_channel(_drive, iso_datum)

@st.cache_data(ttl=60, show_spinner="Orderlines werden geladen …")
def load_orderlines(_drive):
    df = pl.load_orderlines(_drive)
    df["d"] = pd.to_datetime(df["date"], errors="coerce")  # einmalig je Cache, nicht je Rerun
    return df

@st.cache_data(ttl=60, show_spinner=False)
def load_config(_drive):
    return pl.load_config(_drive)

@st.cache_data(ttl=60, show_spinner=False)
def load_report(_drive, iso_datum):
    return pl.load_report(_drive, iso_datum)


# ─── Orderlines-Verwaltung (Sidebar-Upload, Kalender-/Einstellungen-Popover) ─────

def render_orderlines_calendar(drive):
    """Kalender-Jahresansicht der vorhandenen Tage + Zeitraum löschen (im Popover)."""
    ol = load_orderlines(drive)
    if ol.empty:
        st.info("Noch keine Orderlines gespeichert.")
        return
    tage = ol.groupby("date").size()
    d_all = ol["d"]
    st.caption(
        f"Gespeichert: {len(ol):,} Zeilen · {d_all.min():%d.%m.%Y} – {d_all.max():%d.%m.%Y} "
        f"· {ol['date'].nunique()} Tage".replace(",", ".")
    )
    jahre = sorted({d.year for d in d_all}, reverse=True)
    jahr = st.selectbox("Jahr", jahre, index=0, key="ol_cal_y")
    counts = {k: int(v) for k, v in tage.items()}

    def _month_html(year, month):
        head = "".join(f"<th style='padding:2px;color:#9CA3AF;font-size:9px;font-weight:600'>{d}</th>"
                       for d in ["M", "D", "M", "D", "F", "S", "S"])
        body = ""
        for wk in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
            cells = ""
            for day in wk:
                if day == 0:
                    cells += "<td></td>"
                    continue
                n = counts.get(f"{year:04d}-{month:02d}-{day:02d}", 0)
                if n > 0:
                    cells += (f"<td title='{n} Orderlines' style='padding:3px;text-align:center;"
                              f"font-size:10px;font-weight:600;background:#CCFBF1;color:#0F766E;"
                              f"border:1px solid #99F6E4;border-radius:4px'>{day}</td>")
                else:
                    cells += (f"<td style='padding:3px;text-align:center;font-size:10px;"
                              f"color:#D1D5DB'>{day}</td>")
            body += f"<tr>{cells}</tr>"
        return (f"<div style='font-weight:600;font-size:12px;color:#374151;margin-bottom:4px'>"
                f"{calendar.month_name[month]}</div>"
                f"<table style='border-collapse:separate;border-spacing:2px'>"
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")

    for row_start in range(1, 13, 4):
        mcols = st.columns(4)
        for i, month in enumerate(range(row_start, min(row_start + 4, 13))):
            mcols[i].markdown(_month_html(jahr, month), unsafe_allow_html=True)
    st.caption("Eingefärbte Tage enthalten Daten (Tooltip = Anzahl Orderlines).")

    st.divider()
    st.markdown("##### Zeitraum löschen")
    dmin_d, dmax_d = d_all.min().date(), d_all.max().date()
    dc1, dc2 = st.columns(2)
    with dc1:
        del_von = st.date_input("Von", value=dmin_d, min_value=dmin_d, max_value=dmax_d,
                                format="DD.MM.YYYY", key="ol_del_von")
    with dc2:
        del_bis = st.date_input("Bis", value=dmax_d, min_value=dmin_d, max_value=dmax_d,
                                format="DD.MM.YYYY", key="ol_del_bis")
    betroffen = int(ol[(ol["date"] >= del_von.isoformat()) & (ol["date"] <= del_bis.isoformat())].shape[0])
    st.caption(f"Betroffen: {betroffen:,} Zeilen".replace(",", "."))
    if st.button(":material/delete: Zeitraum löschen", disabled=betroffen == 0, key="ol_del_btn"):
        rest = pl.delete_orderlines_range(pl.load_orderlines(drive),
                                          del_von.isoformat(), del_bis.isoformat())
        folder_id = get_pricing_folder_id(drive)
        upload_bytes_to_drive(drive, rest.to_csv(index=False).encode("utf-8"),
                              pl.ORDERLINES_FILE, folder_id, "text/csv")
        load_orderlines.clear()
        st.success(f"{betroffen:,} Zeilen gelöscht.".replace(",", "."))
        st.rerun()


def render_pricing_settings(drive, cfg):
    """Channel-Bezeichnungen + Source-Zuordnung (im Popover, als Form)."""
    ol = load_orderlines(drive)
    opt_refs = [REF_QUOTE] + CHANNEL_COLS
    sources = set(cfg["source_map"].keys())
    if not ol.empty:
        sources |= set(ol["source"].dropna().unique())
    sources = sorted(s for s in sources if s)

    with st.form("settings_form"):
        st.markdown("##### Channel-Bezeichnungen")
        st.caption("Sprechende Namen für die Channel-Preisreihen – werden überall verwendet.")
        new_labels = {}
        lcols = st.columns(len(CHANNEL_COLS))
        for i, c in enumerate(CHANNEL_COLS):
            new_labels[c] = lcols[i].text_input(
                f"channelPrice{i + 1}",
                value=cfg["channel_labels"].get(c, f"Channel {i + 1}"), key=f"set_lbl_{c}")

        st.markdown("##### Source-Zuordnung")
        st.caption("Welche Preisreihe gilt je Marketing-Source? Nicht zugeordnete → Quote. "
                   "Geänderte Channel-Namen erscheinen in den Dropdowns nach dem Speichern.")

        def _opt_label(r):
            return QUOTE_LABEL if r == REF_QUOTE else (cfg["channel_labels"].get(r) or r)

        new_map = {}
        scols = st.columns(3)
        for i, s in enumerate(sources):
            cur = cfg["source_map"].get(s, REF_QUOTE)
            idx = opt_refs.index(cur) if cur in opt_refs else 0
            sel = scols[i % 3].selectbox(s, opt_refs, index=idx,
                                         format_func=_opt_label, key=f"set_src_{s}")
            if sel != REF_QUOTE:
                new_map[s] = sel

        submitted = st.form_submit_button("💾 Einstellungen speichern", type="primary")

    if submitted:
        new_cfg = {"channel_labels": new_labels, "source_map": new_map}
        folder_id = get_pricing_folder_id(drive)
        upload_bytes_to_drive(drive, pl.config_to_bytes(new_cfg),
                              pl.CONFIG_FILE, folder_id, "application/json")
        load_config.clear()
        st.success("Einstellungen gespeichert.")
        st.rerun()


# ─── Seiteninhalt ──────────────────────────────────────────────────────────────

st.title(":material/payments: Pricing")
st.caption("Preisanalyse – Quote-Preise vs. Channel-Preise, geclustert nach Preishöhe")

if drive is None:
    st.error("Keine Verbindung zu Google Drive. Bitte Anmeldedaten prüfen.")
    st.stop()

# Konfiguration: Channel-Anzeigenamen + Source-Zuordnung (persistent in Drive)
cfg = load_config(drive)
CH_LABELS = channel_label_list(cfg)          # Anzeigenamen, ausgerichtet an CHANNEL_COLS
source_map = cfg["source_map"]

# ════════════════════════════════════════════════════════════════════════════════
# SIDEBAR – Preisdateien hochladen
# ════════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header(":material/upload: Daten Upload")
    st.caption("Quote-, Channel-, Masterdatei (eines Zeitpunkts) und Orderlines. "
               "Datum für Preise/Master wird aus dem Dateinamen erkannt.")

    quote_file = st.file_uploader("Quote-Preise (CSV)", type=["csv"], key="up_quote",
                                  help="Quelle: Google Drive › Pricing")
    channel_file = st.file_uploader("Channel-Preise (CSV)", type=["csv"], key="up_channel",
                                    help="Quelle: Google Drive › Pricing")
    master_file = st.file_uploader("Masterdatei (CSV)", type=["csv"], key="up_master",
                                   help="Quelle: Download aus Channelpilot")
    orderlines_file = st.file_uploader("Orderlines (CSV)", type=["csv"], key="up_orderlines",
                                       help="Quelle: Metabase › Produkte & Hersteller › Pricing")
    ic1, ic2, _ic = st.columns([1, 1, 3])
    if ic1.button(":material/calendar_month:", key="btn_cal", help="Vorhandene Tage anzeigen"):
        st.session_state["pricing_panel"] = (
            None if st.session_state.get("pricing_panel") == "calendar" else "calendar")
    if ic2.button(":material/settings:", key="btn_set", help="Einstellungen anzeigen"):
        st.session_state["pricing_panel"] = (
            None if st.session_state.get("pricing_panel") == "settings" else "settings")
    ol_modus = st.radio(
        "Orderlines-Modus", ["Nur neue Tage anhängen", "Doppelte Tage ersetzen"], key="up_ol_mode",
        help="Anhängen: vorhandene Tage bleiben unverändert. "
             "Ersetzen: für Tage in der neuen Datei werden alte Zeilen überschrieben.",
    )

    # Datum vorbelegen aus Dateinamen (Preise/Master)
    erkanntes_datum = None
    for f in (quote_file, channel_file, master_file):
        if f is not None:
            erkanntes_datum = parse_date_from_filename(f.name) or erkanntes_datum

    snap_datum = st.date_input(
        "Datum des Snapshots (Preise/Master)", value=erkanntes_datum or date.today(),
        format="DD.MM.YYYY"
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
            abdeckung = {lbl: int(ch_prev[c].notna().sum()) for c, lbl in zip(CHANNEL_COLS, CH_LABELS)}
            st.success(f"Channel: {len(ch_prev):,} Produkte".replace(",", "."))
            st.caption("Abdeckung: " + " · ".join(f"{k}: {v:,}".replace(",", ".") for k, v in abdeckung.items()))
        except Exception as e:
            st.error(f"Channel-Datei nicht lesbar: {e}")
    master_reduced = None
    if master_file is not None:
        try:
            master_reduced = parse_master_bytes(master_file.getvalue())
            st.success(f"Master: {len(master_reduced):,} Produkte".replace(",", "."))
        except Exception as e:
            st.error(f"Masterdatei nicht lesbar: {e}")
    ol_new = None
    if orderlines_file is not None:
        try:
            ol_new = parse_orderlines_bytes(orderlines_file.getvalue())
            st.success(f"Orderlines: {len(ol_new):,} Zeilen "
                       f"({ol_new['date'].min()} – {ol_new['date'].max()})".replace(",", "."))
        except Exception as e:
            st.error(f"Orderlines nicht lesbar: {e}")

    if st.button(":material/save: In Drive speichern", type="primary", use_container_width=True,
                 disabled=(quote_file is None and channel_file is None
                           and master_file is None and orderlines_file is None)):
        folder_id = get_pricing_folder_id(drive)
        ddmmyy = snap_datum.strftime("%d%m%y")
        gespeichert = []
        if quote_file is not None:
            upload_bytes_to_drive(drive, quote_file.getvalue(), f"quote_prices_{ddmmyy}.csv", folder_id, "text/csv")
            gespeichert.append("Quote-Preise")
        if channel_file is not None:
            upload_bytes_to_drive(drive, channel_file.getvalue(), f"channel_prices_{ddmmyy}.csv", folder_id, "text/csv")
            gespeichert.append("Channel-Preise")
        if master_file is not None and master_reduced is not None:
            master_csv = master_reduced.to_csv(index=False).encode("utf-8")
            upload_bytes_to_drive(drive, master_csv, f"master_{ddmmyy}.csv", folder_id, "text/csv")
            gespeichert.append("Masterdatei")
        if orderlines_file is not None and ol_new is not None:
            mode = "replace" if ol_modus == "Doppelte Tage ersetzen" else "append"
            combined = pl.apply_orderlines(pl.load_orderlines(drive), ol_new, mode)
            upload_bytes_to_drive(drive, combined.to_csv(index=False).encode("utf-8"),
                                  pl.ORDERLINES_FILE, folder_id, "text/csv")
            load_orderlines.clear()
            gespeichert.append(f"Orderlines ({len(combined):,} ges.)".replace(",", "."))
        list_snapshots.clear()
        load_snapshot.clear()
        st.success(f"Gespeichert: {', '.join(gespeichert)}")

    # Vorhandene Snapshots anzeigen
    st.divider()
    st.markdown("##### Gespeicherte Zeitpunkte")
    _snaps = list_snapshots(drive)
    if not _snaps:
        st.caption("Noch keine Snapshots gespeichert.")
    else:
        rows = [{
            "Datum": fmt_date(k),
            "Quote": "Ja" if v["quote_id"] else "—",
            "Channel": "Ja" if v["channel_id"] else "—",
            "Master": "Ja" if v.get("master_id") else "—",
        } for k, v in _snaps.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Info-Panel (Kalender / Einstellungen) – über die Icons links geöffnet ──
_panel = st.session_state.get("pricing_panel")
if _panel:
    with st.container(border=True):
        pc1, pc2 = st.columns([6, 1])
        pc1.markdown("#### " + ("Vorhandene Tage (Orderlines)" if _panel == "calendar"
                                else "Einstellungen"))
        if pc2.button(":material/close: Schließen", key="panel_close", use_container_width=True):
            st.session_state["pricing_panel"] = None
            st.rerun()
        if _panel == "calendar":
            render_orderlines_calendar(drive)
        else:
            render_pricing_settings(drive, cfg)

tab_snap, tab_cmp, tab_master, tab_renner, tab_wirkung, tab_produkt = st.tabs(
    [":material/bar_chart: Momentaufnahme", ":material/compare_arrows: Vergleich", ":material/folder_open: Masterdatei-Analyse", ":material/leaderboard: Rennerliste", ":material/insights: Preisänderungs-Wirkung", ":material/search: Produktansicht"]
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
        full = load_snapshot(drive, sel)
        df = full[full["quote"].notna()].copy()  # Cluster/Vergleiche basieren auf Quote-Preis

        if df.empty:
            st.warning("Für diesen Zeitpunkt sind keine Quote-Preise hinterlegt.")
        else:
            df["Cluster"] = assign_price_cluster(df["quote"])

            # KPIs: Produktzahl Quote + Anzahl je Channel-Preis (+ davon mit Quote)
            cols = st.columns(1 + len(CHANNEL_COLS))
            cols[0].metric("Produkte (Quote)", f"{int(full['quote'].notna().sum()):,}".replace(",", "."))
            for i, (c, lbl) in enumerate(zip(CHANNEL_COLS, CH_LABELS), start=1):
                tot = int(full[c].notna().sum())
                mit_quote = int((full[c].notna() & full["quote"].notna()).sum())
                cols[i].metric(lbl, f"{tot:,}".replace(",", "."))
                cols[i].caption(f"davon mit Quote: {mit_quote:,}".replace(",", "."))

            st.divider()

            # ── Channel-Vergleich gesamt (nur PZNs mit Channel- UND Quote-Preis) ──
            st.markdown("##### Channel-Preise im Vergleich zum Quote-Preis")
            st.caption("Nur PZNs, die sowohl einen Channel- als auch einen Quote-Preis haben "
                       "(= Spalte „Abdeckung“).")
            ch_rows = []
            for c, lbl in zip(CHANNEL_COLS, CH_LABELS):
                sub = df[df[c].notna() & df["quote"].notna()]
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

            # ── Umsatzgewichtete Preisabweichung (Orderlines, letzte 30 Tage) ──
            st.markdown("##### Preisabweichung umsatzgewichtet")
            ol_all = load_orderlines(drive)
            if ol_all.empty:
                st.caption("Für die Umsatzgewichtung werden Orderlines benötigt "
                           "(Upload links in der Seitenleiste).")
            else:
                olw = ol_all.copy()
                olw["ref"] = olw["source"].map(lambda s: ref_for_source(s, source_map))
                olw["d"] = pd.to_datetime(olw["date"], errors="coerce")
                olw = olw[olw["d"].notna()]
                # 30 Tage vor dem Snapshot-Datum (sel), nicht vor heute
                w_bis = pd.Timestamp(sel)
                w_von = w_bis - pd.Timedelta(days=30)
                olw = olw[(olw["d"] > w_von) & (olw["d"] <= w_bis)]
                rev = olw.groupby(["productId", "ref"])["net"].sum().reset_index()

                w_rows = []
                for c, lbl in zip(CHANNEL_COLS, CH_LABELS):
                    sub = df[df[c].notna() & df["quote"].notna()][["productId", c, "quote"]].copy()
                    sub["pct"] = (sub[c] - sub["quote"]) / sub["quote"] * 100
                    merged = sub.merge(rev[rev["ref"] == c][["productId", "net"]],
                                       on="productId", how="inner")
                    merged = merged[merged["net"] > 0]
                    if merged.empty:
                        w_rows.append({"Channel": lbl, "Gew. Ø Diff %": None,
                                       "Ø Diff % (ungew.)": round(sub["pct"].mean(), 1) if not sub.empty else None,
                                       "Umsatzbasis €": 0.0, "PZNs (mit Umsatz)": 0})
                        continue
                    w = (merged["pct"] * merged["net"]).sum() / merged["net"].sum()
                    w_rows.append({
                        "Channel": lbl,
                        "Gew. Ø Diff %": round(w, 1),
                        "Ø Diff % (ungew.)": round(sub["pct"].mean(), 1),
                        "Umsatzbasis €": round(merged["net"].sum(), 0),
                        "PZNs (mit Umsatz)": len(merged),
                    })
                st.dataframe(
                    pd.DataFrame(w_rows), use_container_width=True, hide_index=True,
                    column_config={
                        "Gew. Ø Diff %": st.column_config.NumberColumn(format="%.1f %%"),
                        "Ø Diff % (ungew.)": st.column_config.NumberColumn(format="%.1f %%"),
                        "Umsatzbasis €": st.column_config.NumberColumn(format="%.0f €"),
                        "PZNs (mit Umsatz)": st.column_config.NumberColumn(format="%d"),
                    },
                )
                st.caption(
                    f"Gewichtung mit Netto-Umsatz je Channel aus Orderlines der 30 Tage vor dem Snapshot "
                    f"({(w_von + pd.Timedelta(days=1)):%d.%m.%Y} – {w_bis:%d.%m.%Y}). "
                    "Je Channel zählen nur PZNs mit Channel- und Quote-Preis sowie Umsatz auf diesem Channel."
                )

            st.divider()

            # ── Cluster-Übersicht: Ø prozentuale Differenz Channel vs. Quote je Cluster ──
            st.markdown("##### Ø Differenz zum Quote-Preis je Preis-Cluster (%)")
            tmp = df.copy()
            for c in CHANNEL_COLS:
                tmp[c + "_pct"] = (tmp[c] - tmp["quote"]) / tmp["quote"] * 100
            g = tmp.groupby("Cluster", observed=False)
            cl = pd.DataFrame({"Anzahl": g.size()})
            for c, lbl in zip(CHANNEL_COLS, CH_LABELS):
                cl[lbl] = g[c + "_pct"].mean().round(1)
            cl = cl.reset_index()
            st.dataframe(
                cl, use_container_width=True, hide_index=True,
                column_config={
                    "Anzahl": st.column_config.NumberColumn(format="%d"),
                    **{lbl: st.column_config.NumberColumn(format="%.1f %%") for lbl in CH_LABELS},
                },
            )
            st.caption("Negativ = Channel im Schnitt günstiger als Quote, positiv = teurer.")

            st.divider()

            # ── Kritische Preise ──
            st.markdown("##### Kritische Preise")
            f1, f2 = st.columns([2, 1])
            with f1:
                art = st.radio(
                    "Filter",
                    ["Unter Quote", "Über Quote", "Beide"],
                    horizontal=True, key="krit_art",
                    help="Channel-Preise, die deutlich unter dem Quote-Preis liegen "
                         "oder über dem Quote-Preis liegen.",
                )
            with f2:
                schwelle = st.slider("Schwelle „unter Quote“ (%)", 1, 50, 10, key="krit_schwelle")

            # Long-Format: eine Zeile je Produkt × Channel
            long = df.melt(
                id_vars=["productId", "quote", "Cluster"],
                value_vars=CHANNEL_COLS, var_name="ChannelCol", value_name="ChannelPreis",
            )
            long = long[long["ChannelPreis"].notna()].copy()
            long["Channel"] = long["ChannelCol"].map(dict(zip(CHANNEL_COLS, CH_LABELS)))
            long["pct"] = (long["ChannelPreis"] - long["quote"]) / long["quote"] * 100

            unter = long[long["pct"] < -schwelle].copy()
            unter["Kategorie"] = f"> {schwelle} % unter Quote"
            ueber = long[long["pct"] > 0].copy()
            ueber["Kategorie"] = "über Quote"

            if art == "Unter Quote":
                krit = unter
            elif art == "Über Quote":
                krit = ueber
            else:
                krit = pd.concat([unter, ueber])

            if krit.empty:
                st.success("Keine kritischen Preise für diese Auswahl.")
            else:
                krit = krit.sort_values("pct")  # stärkste Unterschreitung zuerst
                out = krit[["productId", "Channel", "quote", "ChannelPreis", "pct", "Cluster", "Kategorie"]].copy()
                out["quote"] = out["quote"].round(2)
                out["ChannelPreis"] = out["ChannelPreis"].round(2)
                out["pct"] = out["pct"].round(1)
                out = out.rename(columns={
                    "productId": "PZN", "quote": "Quote", "ChannelPreis": "Channel-Preis", "pct": "Δ %",
                })
                st.caption(
                    f"{len(out):,} kritische Preise".replace(",", ".")
                    + (f" · {len(unter):,} unter Quote".replace(",", ".") if art != "Über Quote" else "")
                    + (f" · {len(ueber):,} über Quote".replace(",", ".") if art != "Unter Quote" else "")
                )
                st.dataframe(
                    out, use_container_width=True, hide_index=True,
                    column_config={
                        "Quote": st.column_config.NumberColumn(format="%.2f €"),
                        "Channel-Preis": st.column_config.NumberColumn(format="%.2f €"),
                        "Δ %": st.column_config.NumberColumn(format="%.1f %%"),
                    },
                )
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    out.to_excel(w, index=False, sheet_name="Kritische Preise")
                st.download_button(
                    ":material/download: Kritische Preise als Excel",
                    data=buf.getvalue(),
                    file_name=f"kritische_preise_{sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            # ── Report zu dieser Momentaufnahme ────────────────────────────────
            st.divider()
            st.markdown(f"##### Report – {fmt_date(sel)}")
            saved_report = load_report(drive, sel)
            with st.form(f"report_form_{sel}"):
                report_txt = st.text_area(
                    "Kurzer Report zu diesem Zeitpunkt", value=saved_report, height=160,
                    key=f"report_txt_{sel}",
                    placeholder="Notizen / Einschätzung zu dieser Momentaufnahme …",
                )
                report_submit = st.form_submit_button(":material/save: Report speichern", type="primary")
            if report_submit:
                folder_id = get_pricing_folder_id(drive)
                upload_bytes_to_drive(drive, report_txt.encode("utf-8"),
                                      pl.report_filename(sel), folder_id, "text/plain")
                load_report.clear()
                st.success("Report gespeichert.")

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
            metrik = st.selectbox("Preisart", ["Quote"] + CH_LABELS + ["Alle"], key="cmp_metrik")

        col_map = {"Quote": "quote", **{lbl: c for lbl, c in zip(CH_LABELS, CHANNEL_COLS)}}

        # Hat ein Datum keine Channel-Datei (nur Quote), werden dessen Quote-Preise
        # als Channel-Preise verwendet.
        def _preis_series(date_iso, zielname, col_):
            snap = load_snapshot(drive, date_iso)
            fallback = col_ != "quote" and not snaps[date_iso].get("channel_id")
            quelle = "quote" if fallback else col_
            return snap[["productId", quelle]].rename(columns={quelle: zielname}), fallback

        if von == bis:
            st.warning("Bitte zwei unterschiedliche Zeitpunkte wählen.")
        elif metrik == "Alle":
            st.caption(f"Alle Preisarten: {fmt_date(von)} → {fmt_date(bis)}")
            ol_all = load_orderlines(drive)
            w_bis = pd.Timestamp(bis)
            w_von = w_bis - pd.Timedelta(days=30)
            rev_by_ref = {}
            if not ol_all.empty:
                olw = ol_all.copy()
                olw["ref"] = olw["source"].map(lambda s: ref_for_source(s, source_map))
                olw["d"] = pd.to_datetime(olw["date"], errors="coerce")
                olw = olw[(olw["d"] > w_von) & (olw["d"] <= w_bis)]
                for ref_key, grp in olw.groupby("ref"):
                    rev_by_ref[ref_key] = grp.groupby("productId")["net"].sum()

            def _wavg(sub):
                rs = sub["_rev"].sum()
                return round((sub["pct"] * sub["_rev"]).sum() / rs, 1) if rs > 0 else None

            rows = []
            for col_, lbl in [("quote", QUOTE_LABEL)] + list(zip(CHANNEL_COLS, CH_LABELS)):
                da, _fa = _preis_series(von, "preis_a", col_)
                db, _fb = _preis_series(bis, "preis_b", col_)
                mm = da.merge(db, on="productId", how="inner")
                mm = mm[(mm["preis_a"].notna()) & (mm["preis_b"].notna()) & (mm["preis_a"] > 0)].copy()
                if mm.empty:
                    continue
                mm["pct"] = (mm["preis_b"] - mm["preis_a"]) / mm["preis_a"] * 100
                mm["_rev"] = mm["productId"].map(rev_by_ref.get(col_, pd.Series(dtype=float))).fillna(0.0)
                rows.append({
                    "Preisart": lbl,
                    "Änderung Gesamt %": round(mm["pct"].mean(), 1),
                    "Umsatzgew. Gesamt %": _wavg(mm),
                    "Umsatzgew. 0–25 € %": _wavg(mm[mm["preis_a"] < 25]),
                    "Umsatzgew. >25 € %": _wavg(mm[mm["preis_a"] >= 25]),
                })
            if not rows:
                st.warning("Keine vergleichbaren Daten für diesen Zeitraum.")
            else:
                pct_cols = ["Änderung Gesamt %", "Umsatzgew. Gesamt %",
                            "Umsatzgew. 0–25 € %", "Umsatzgew. >25 € %"]
                st.dataframe(
                    pd.DataFrame(rows), use_container_width=True, hide_index=True,
                    column_config={c: st.column_config.NumberColumn(format="%.1f %%") for c in pct_cols},
                )
                st.caption(
                    "Umsatzgewichtung: Netto-Umsatz je Preisart der 30 Tage vor dem neueren Datum. "
                    "Cluster nach Preis am Startdatum (0–25 € bzw. >25 €). "
                    "Nur PZNs mit Preis in beiden Zeitpunkten."
                )
        else:
            col = col_map[metrik]
            da, fb_von = _preis_series(von, "preis_a", col)
            db, fb_bis = _preis_series(bis, "preis_b", col)
            if fb_von or fb_bis:
                hinweis = [fmt_date(d) for d, fb in [(von, fb_von), (bis, fb_bis)] if fb]
                st.info(f"Nur Quote-Preise vorhanden für {', '.join(hinweis)} – "
                        f"dort werden die Quote-Preise als „{metrik}“ verwendet.")
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

                # Umsatz je PZN für die gewählte Preisreihe (ref=col), 30 Tage vor dem neueren Datum
                ol_all = load_orderlines(drive)
                w_bis = pd.Timestamp(bis)
                w_von = w_bis - pd.Timedelta(days=30)
                rev = pd.Series(dtype=float)
                if not ol_all.empty:
                    olw = ol_all.copy()
                    olw["ref"] = olw["source"].map(lambda s: ref_for_source(s, source_map))
                    olw["d"] = pd.to_datetime(olw["date"], errors="coerce")
                    olw = olw[(olw["d"] > w_von) & (olw["d"] <= w_bis) & (olw["ref"] == col)]
                    rev = olw.groupby("productId")["net"].sum()
                beide["_rev"] = beide["productId"].map(rev).fillna(0.0)
                beide["_pw"] = beide["pct"] * beide["_rev"]
                rev_sum = beide["_rev"].sum()
                w_change = (beide["_pw"].sum() / rev_sum * 100) if rev_sum > 0 else None

                # KPIs
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Vergleichbar", f"{len(beide):,}".replace(",", "."))
                k2.metric("Ø Änderung", f"{beide['pct'].mean() * 100:+.1f} %")
                k3.metric("Ø Änderung (umsatzgew.)",
                          f"{w_change:+.1f} %" if w_change is not None else "—")
                k4.metric("Neu", f"{len(neu):,}".replace(",", "."))
                k5.metric("Entfernt", f"{len(entfernt):,}".replace(",", "."))

                st.caption(f"Vergleich {metrik}: {fmt_date(von)} → {fmt_date(bis)}")
                st.divider()

                # ── Veränderung je Preis-Cluster (inkl. umsatzgewichtet) ──
                st.markdown("##### Veränderung je Preis-Cluster")

                g = beide.groupby("Cluster", observed=False)
                rsum = g["_rev"].sum()
                wmean = (g["_pw"].sum() / rsum.replace(0, pd.NA)) * 100
                cl = pd.DataFrame({
                    "Anzahl": g.size(),
                    "Ø Änderung %": (g["pct"].mean() * 100).round(1),
                    "Ø Änderung % (umsatzgew.)": wmean.round(1),
                }).reset_index()
                st.dataframe(
                    cl, use_container_width=True, hide_index=True,
                    column_config={
                        "Anzahl": st.column_config.NumberColumn(format="%d"),
                        "Ø Änderung %": st.column_config.NumberColumn(format="%.1f %%"),
                        "Ø Änderung % (umsatzgew.)": st.column_config.NumberColumn(format="%.1f %%"),
                    },
                )
                st.caption(
                    f"Nur PZNs mit Preis in beiden Zeitpunkten. Umsatzgewichtung mit Netto-Umsatz "
                    f"({metrik}) der 30 Tage vor dem neueren Datum "
                    f"({(w_von + pd.Timedelta(days=1)):%d.%m.%Y} – {w_bis:%d.%m.%Y})."
                )

                st.divider()

                # ── Bedeutendste Veränderungen (umsatzgewichtet) ──
                st.markdown("##### Bedeutendste Veränderungen")
                st.caption("Sortiert nach Bedeutung = |Preisänderung| × Umsatz der letzten 30 Tage "
                           f"({metrik}, vor dem neueren Datum). Nur PZNs mit Umsatz in diesem Fenster.")
                anzahl = st.slider("Anzahl", 5, 100, 20, step=5, key="cmp_top")

                namen_cmp = (ol_all.groupby("productId")["productname"].first()
                             if not ol_all.empty else pd.Series(dtype=str))
                bed = beide[beide["_rev"] > 0].copy()
                bed["Name"] = bed["productId"].map(namen_cmp)
                bed["impact"] = bed["pct"].abs() * bed["_rev"]
                bed = bed.sort_values("impact", ascending=False)

                def bed_table(sub):
                    o = sub[["productId", "Name", "pct", "_rev"]].copy()
                    o["pct"] = (o["pct"] * 100).round(1)
                    o["_rev"] = o["_rev"].round(2)
                    return o.rename(columns={"productId": "PZN", "pct": "% Preisänderung",
                                             "_rev": "Umsatz 30 Tage €"})

                if bed.empty:
                    st.info("Keine Umsatzdaten im 30-Tage-Fenster für diese Preisart – "
                            "umsatzgewichtete Bewertung nicht möglich.")
                else:
                    st.dataframe(
                        bed_table(bed.head(anzahl)), use_container_width=True, hide_index=True,
                        column_config={
                            "% Preisänderung": st.column_config.NumberColumn(format="%.1f %%"),
                            "Umsatz 30 Tage €": st.column_config.NumberColumn(format="%.2f €"),
                        },
                    )

                # ── Export ──
                st.divider()
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    cl.to_excel(w, index=False, sheet_name="Cluster")
                    bed_table(bed).to_excel(w, index=False, sheet_name="Bedeutendste Änderungen")
                st.download_button(
                    ":material/download: Vergleich als Excel",
                    data=buf.getvalue(),
                    file_name=f"pricing_vergleich_{metrik}_{von}_{bis}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                # ── Indexierter Preisverlauf über alle Zeitpunkte im Zeitraum ──
                st.divider()
                st.markdown("##### Indexierter Preisverlauf")
                range_dates = [d for d in keys
                               if von <= d <= bis and (snaps[d].get("quote_id") or snaps[d].get("channel_id"))]
                serien = {}
                for d in range_dates:
                    snap_d = load_snapshot(drive, d)
                    q = "quote" if (col != "quote" and not snaps[d].get("channel_id")) else col
                    if q not in snap_d.columns:
                        continue
                    s = snap_d[["productId", q]].rename(columns={q: d}).dropna(subset=[d])
                    serien[d] = s.set_index("productId")[d]
                mat = pd.DataFrame(serien).dropna()  # gemeinsamer Warenkorb (an allen Zeitpunkten vorhanden)
                if mat.shape[1] < 2 or mat.empty:
                    st.info("Nicht genügend gemeinsame Preispunkte im Zeitraum für einen Indexverlauf.")
                else:
                    w = rev.reindex(mat.index).fillna(0.0)
                    gewichtet = w.sum() > 0
                    if not gewichtet:
                        w = pd.Series(1.0, index=mat.index)
                    avg = mat.mul(w, axis=0).sum() / w.sum()          # (gew.) Ø-Preis je Zeitpunkt
                    index_ser = (avg / avg.iloc[0])

                    # Y-Achse um 1,0 zentriert, „nett" gerundet auf die Schwankung
                    dev = max(abs(index_ser.max() - 1), abs(index_ser.min() - 1), 0.01)

                    def _nice_ceil(x):
                        base = 10 ** math.floor(math.log10(x))
                        for mlt in (1, 2, 2.5, 5, 10):
                            if x <= mlt * base:
                                return mlt * base
                        return 10 * base

                    nd = _nice_ceil(dev * 1.1)
                    domain = [round(1 - nd, 4), round(1 + nd, 4)]
                    chart_df = pd.DataFrame({"Datum": pd.to_datetime(index_ser.index),
                                             "Index": index_ser.values})
                    line = alt.Chart(chart_df).mark_line(point=True, color="#0D9488").encode(
                        x=alt.X("Datum:T", title=None),
                        y=alt.Y("Index:Q", scale=alt.Scale(domain=domain, nice=False, zero=False),
                                title="Index (Start = 1,00)"),
                        tooltip=[alt.Tooltip("Datum:T", title="Datum"),
                                 alt.Tooltip("Index:Q", format=".3f", title="Index")],
                    )
                    rule = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
                        color="#9CA3AF", strokeDash=[4, 4]).encode(y="y:Q")
                    st.altair_chart(line + rule, use_container_width=True)
                    st.caption(
                        f"Indexierter {metrik}-Preis (Start {fmt_date(von)} = 1,00), "
                        f"{'umsatzgewichtet' if gewichtet else 'ungewichtet'}, gemeinsamer Warenkorb "
                        f"von {len(mat):,} PZN über {mat.shape[1]} Zeitpunkte.".replace(',', '.')
                    )

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 – Masterdatei-Analyse (Abgleich Master-Channelpreise vs. Channel-Snapshot)
# ════════════════════════════════════════════════════════════════════════════════
with tab_master:
    snaps = list_snapshots(drive)
    vergleichbar = {k: v for k, v in snaps.items() if v.get("master_id") and v.get("channel_id")}
    if not vergleichbar:
        st.info(
            "Für keinen Zeitpunkt liegen Master- **und** Channel-Datei vor. "
            "Beide werden für den Abgleich benötigt (Upload links in der Seitenleiste)."
        )
    else:
        keys_m = list(vergleichbar.keys())
        cm1, cm2 = st.columns([1, 1])
        with cm1:
            sel_m = st.selectbox("Zeitpunkt", keys_m, index=len(keys_m) - 1,
                                 format_func=fmt_date, key="ma_sel")
        with cm2:
            toleranz = st.number_input(
                "Toleranz für „abweichend“ (€)", min_value=0.0, max_value=1.0,
                value=0.01, step=0.01, format="%.2f", key="ma_tol",
                help="Abweichungen unterhalb dieses Betrags gelten als Übereinstimmung (Rundung).",
            )

        master = load_master(drive, sel_m)
        channel = load_channel(drive, sel_m)

        if master.empty or channel.empty:
            st.warning("Master- oder Channel-Daten für diesen Zeitpunkt konnten nicht geladen werden.")
        else:
            info_cols = [c for c in ["title", "manufacturer"] if c in master.columns]
            m = master[["productId"] + MASTER_CHANNEL_COLS + info_cols].merge(
                channel[["productId"] + CHANNEL_COLS], on="productId", how="inner"
            )

            # Long-Format: je Produkt × Channel ein Master/Snapshot-Paar
            teile = []
            for mc, sc, lbl in zip(MASTER_CHANNEL_COLS, CHANNEL_COLS, CH_LABELS):
                sub = m[["productId"] + info_cols + [mc, sc]].copy()
                sub = sub.rename(columns={mc: "master", sc: "snapshot"})
                sub["Channel"] = lbl
                teile.append(sub)
            long = pd.concat(teile, ignore_index=True)

            both = long[long["master"].notna() & long["snapshot"].notna()].copy()
            both["diff"] = both["master"] - both["snapshot"]
            both["absdiff"] = both["diff"].abs()
            both["pct"] = both["diff"] / both["snapshot"] * 100
            both["abweichend"] = both["absdiff"] >= toleranz

            # KPIs gesamt
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Produkte (in beiden)", f"{m['productId'].nunique():,}".replace(",", "."))
            k2.metric("Preis-Paare verglichen", f"{len(both):,}".replace(",", "."))
            k3.metric("Übereinstimmend", f"{int((~both['abweichend']).sum()):,}".replace(",", "."))
            k4.metric("Abweichend", f"{int(both['abweichend'].sum()):,}".replace(",", "."))

            st.divider()

            # Zusammenfassung je Channel
            st.markdown("##### Abgleich je Channel")
            g = both.groupby("Channel", observed=False)
            summary = pd.DataFrame({
                "Verglichen": g.size(),
                "Übereinstimmend": g["abweichend"].apply(lambda s: int((~s).sum())),
                "Abweichend": g["abweichend"].sum().astype(int),
                "Ø Δ €": g["diff"].mean().round(3),
                "Max |Δ| €": g["absdiff"].max().round(2),
            }).reindex(CH_LABELS).reset_index().rename(columns={"index": "Channel"})
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
            st.caption("Δ = Masterpreis − Snapshot-Preis (Momentaufnahme). Positiv = Master teurer.")

            st.divider()

            # Abweichungen im Detail
            st.markdown("##### Abweichungen im Detail")
            fc1, fc2 = st.columns([1, 2])
            with fc1:
                nur_abw = st.toggle("Nur Abweichungen", value=True, key="ma_nur")
            with fc2:
                ch_filter = st.multiselect("Channel filtern", CH_LABELS,
                                           default=CH_LABELS, key="ma_chfilter")

            tab = both[both["Channel"].isin(ch_filter)].copy()
            if nur_abw:
                tab = tab[tab["abweichend"]]

            if tab.empty:
                st.success("Keine Abweichungen für diese Auswahl. Master- und Snapshot-Preise stimmen überein.")
            else:
                tab = tab.reindex(tab["diff"].abs().sort_values(ascending=False).index)
                out = tab[["productId"] + info_cols + ["Channel", "master", "snapshot", "diff", "pct"]].copy()
                for c in ["master", "snapshot", "diff"]:
                    out[c] = out[c].round(2)
                out["pct"] = out["pct"].round(1)
                out = out.rename(columns={
                    "productId": "PZN", "title": "Titel", "manufacturer": "Hersteller",
                    "master": "Master", "snapshot": "Snapshot", "diff": "Δ €", "pct": "Δ %",
                })
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
                    ":material/download: Abgleich als Excel",
                    data=buf.getvalue(),
                    file_name=f"masterabgleich_{sel_m}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 – Abverkauf (Orderlines)
# ════════════════════════════════════════════════════════════════════════════════
ol = load_orderlines(drive)
if not ol.empty:
    ol = ol.copy()
    ol["ref"] = ol["source"].map(lambda s: ref_for_source(s, source_map))
    ol = ol[ol["d"].notna()]
    namen = ol.groupby("productId")["productname"].first()


# ── A) Rennerliste je Channel (nach Umsatz) ────────────────────────────────
with tab_renner:
    if ol.empty:
        st.info("Noch keine Orderlines vorhanden. Bitte links in der Seitenleiste hochladen.")
    else:
        dmin, dmax = ol["d"].min().date(), ol["d"].max().date()
        default_von = max(dmin, (ol["d"].max() - pd.Timedelta(days=29)).date())
        r1, r2, r3 = st.columns([1, 1, 1])
        with r1:
            von_r = r1.date_input("Von", value=default_von, min_value=dmin, max_value=dmax,
                                  format="DD.MM.YYYY", key="ab_rl_von")
        with r2:
            bis_r = r2.date_input("Bis", value=dmax, min_value=dmin, max_value=dmax,
                                  format="DD.MM.YYYY", key="ab_rl_bis")
        with r3:
            topn = st.slider("Top N", 10, 200, 50, step=10, key="ab_rl_n")

        ol_range = ol[(ol["d"] >= pd.Timestamp(von_r)) & (ol["d"] <= pd.Timestamp(bis_r))]
        st.caption(
            f"Datenbasis: {len(ol_range):,} Orderlines · {von_r:%d.%m.%Y} – {bis_r:%d.%m.%Y}".replace(",", ".")
        )
        present_refs = [r for r in (CHANNEL_COLS + [REF_QUOTE]) if r in set(ol_range["ref"])]
        label_to_ref = {ref_label(r, cfg): r for r in present_refs}
        ch = st.selectbox("Channel", ["Alle Channels"] + list(label_to_ref.keys()), key="ab_rl_ch")

        data = ol_range if ch == "Alle Channels" else ol_range[ol_range["ref"] == label_to_ref[ch]]
        renner = data.groupby("productId").agg(
            Produkt=("productname", "first"),
            Umsatz=("net", "sum"),
            Menge=("quantity", "sum"),
            Bestellungen=("quantity", "count"),
        ).reset_index().sort_values("Umsatz", ascending=False)

        # Ø CM2 je Warenkorb pro Produkt (Warenkorb-CM2 im gewählten Zeitraum, alle Channels)
        prod_cm2 = pd.Series(dtype=float)
        if "order_id" in ol_range.columns and ol_range["order_id"].notna().any():
            olc = ol_range[ol_range["order_id"].notna()].copy()
            cm2_order = pl.basket_cm2(olc)
            occ = olc.drop_duplicates(["productId", "order_id"]).copy()
            occ["cm2"] = occ["order_id"].map(cm2_order)
            prod_cm2 = occ.groupby("productId")["cm2"].mean()
        renner["Ø CM2 / Warenkorb"] = renner["productId"].map(prod_cm2).round(2)

        k1, k2, k3 = st.columns(3)
        k1.metric("Produkte", f"{len(renner):,}".replace(",", "."))
        k2.metric("Umsatz netto", f"{renner['Umsatz'].sum():,.0f} €".replace(",", "."))
        k3.metric("Einheiten", f"{int(renner['Menge'].sum()):,}".replace(",", "."))

        show = renner.head(topn).rename(columns={"productId": "PZN"}).copy()
        show.insert(0, "Rang", range(1, len(show) + 1))
        show["Umsatz"] = show["Umsatz"].round(2)
        st.dataframe(
            show[["Rang", "PZN", "Produkt", "Umsatz", "Menge", "Bestellungen", "Ø CM2 / Warenkorb"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Rang": st.column_config.NumberColumn(format="%d"),
                "Umsatz": st.column_config.NumberColumn(format="%.2f €"),
                "Menge": st.column_config.NumberColumn(format="%d"),
                "Bestellungen": st.column_config.NumberColumn(format="%d"),
                "Ø CM2 / Warenkorb": st.column_config.NumberColumn(
                    format="%.2f €",
                    help="Durchschnittlicher Warenkorb-CM2 der Warenkörbe im gewählten Zeitraum, "
                         "die dieses Produkt enthalten. CM2 = Rohmarge € − 6 % × Netto − 4 €."),
            },
        )
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            renner.rename(columns={"productId": "PZN"}).to_excel(
                w, index=False, sheet_name="Rennerliste")
        st.download_button(
            ":material/download: Als Excel (vollständig)", data=buf.getvalue(),
            file_name=f"rennerliste_{ch.replace(' ', '_').lower()}.xlsx", key="ab_dl_a",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # ── Ø Warenkorb-CM2 je Produkt-Preisklasse ──
        if "order_id" in ol_range.columns and ol_range["order_id"].notna().any():
            st.markdown("##### Ø Warenkorb-CM2 je Produkt-Preisklasse")
            olc2 = ol_range[ol_range["order_id"].notna() & (ol_range["quantity"] > 0)].copy()
            cm2_order2 = pl.basket_cm2(olc2)
            occ2 = olc2.drop_duplicates(["productId", "order_id"]).copy()
            occ2["unit"] = pd.to_numeric(occ2["net"], errors="coerce") / occ2["quantity"]
            occ2["cm2"] = occ2["order_id"].map(cm2_order2)
            pk_edges = [1, 5, 10, 15, 20, 25, 30, 35, 40, 50, 75, 100, float("inf")]
            pk_labels = ["1–5", "5–10", "10–15", "15–20", "20–25", "25–30",
                         "30–35", "35–40", "40–50", "50–75", "75–100", ">100"]
            occ2["Preisklasse"] = pd.cut(occ2["unit"], bins=pk_edges, labels=pk_labels, right=False)
            pk = occ2.groupby("Preisklasse", observed=False).agg(
                cm2=("cm2", "mean"), n=("cm2", "size")).reset_index()
            bars = alt.Chart(pk).mark_bar(color="#0D9488").encode(
                x=alt.X("Preisklasse:N", sort=pk_labels, title="Produktpreis (netto/Stück, €)"),
                y=alt.Y("cm2:Q", title="Ø CM2 / Warenkorb (€)"),
                tooltip=[alt.Tooltip("Preisklasse:N", title="Klasse"),
                         alt.Tooltip("cm2:Q", format=".2f", title="Ø CM2 €"),
                         alt.Tooltip("n:Q", title="Produkt-Warenkörbe")],
            )
            st.altair_chart(bars, use_container_width=True)
            st.caption("Produkte im gewählten Zeitraum nach Netto-Stückpreis klassifiziert; "
                       "je Produktvorkommen der CM2 des gesamten Warenkorbs.")

        # ── Ø CM2 pro Order je Tag ──
        if "order_id" in ol_range.columns and ol_range["order_id"].notna().any():
            st.markdown("##### Ø CM2 pro Order je Tag")
            olc3 = ol_range[ol_range["order_id"].notna()].copy()
            cm2_o = pl.basket_cm2(olc3)
            per_order = olc3.groupby("order_id").agg(d=("d", "max"), net=("net", "sum"))
            per_order["cm2"] = cm2_o
            per_order["tag"] = per_order["d"].dt.normalize()
            tag = per_order.groupby("tag").agg(
                Umsatz=("net", "sum"), Orders=("net", "size"), CM2=("cm2", "mean")
            ).reset_index().sort_values("tag")
            tag["Datum"] = tag["tag"].dt.strftime("%d.%m.%Y")
            tag["Umsatz"] = tag["Umsatz"].round(2)
            tag["CM2"] = tag["CM2"].round(2)
            st.dataframe(
                tag[["Datum", "Umsatz", "Orders", "CM2"]].rename(
                    columns={"Orders": "Anzahl Orders", "CM2": "Ø CM2 / Order €"}),
                use_container_width=True, hide_index=True,
                column_config={
                    "Umsatz": st.column_config.NumberColumn(format="%.2f €"),
                    "Anzahl Orders": st.column_config.NumberColumn(format="%d"),
                    "Ø CM2 / Order €": st.column_config.NumberColumn(format="%.2f €"),
                },
            )

    # ── B) Preisänderungs-Wirkung ──────────────────────────────────────────
with tab_wirkung:
    if ol.empty:
        st.info("Noch keine Orderlines vorhanden. Bitte links in der Seitenleiste hochladen.")
    else:
        snaps = list_snapshots(drive)
        price_snaps = [k for k, v in snaps.items() if v.get("quote_id") or v.get("channel_id")]
        if len(price_snaps) < 2:
            st.info("Für die Preisänderungs-Wirkung werden mindestens zwei Preis-Snapshots benötigt.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                von = st.selectbox("Preis vorher", price_snaps, index=len(price_snaps) - 2,
                                   format_func=fmt_date, key="ab_von")
            with c2:
                bis = st.selectbox("Preis nachher", price_snaps, index=len(price_snaps) - 1,
                                   format_func=fmt_date, key="ab_bis")
            with c3:
                pth = st.slider("Min. Preisänderung %", 0, 50, 5, key="ab_pth")
            with c4:
                qth = st.slider("Min. Mengenänderung %", 0, 90, 30, key="ab_qth")

            if von >= bis:
                st.warning("„Preis vorher“ muss vor „Preis nachher“ liegen.")
            else:
                # Preisreihen je Produkt zu beiden Zeitpunkten (Quote + Channel 1–3)
                pv = pl.price_table(load_snapshot(drive, von)).rename(columns={"price": "preis_vorher"})
                pb = pl.price_table(load_snapshot(drive, bis)).rename(columns={"price": "preis_nachher"})
                preise = pv.merge(pb, on=["productId", "ref"], how="inner")
                preise = preise[preise["preis_vorher"] > 0].copy()
                preise["preis_pct"] = ((preise["preis_nachher"] - preise["preis_vorher"])
                                       / preise["preis_vorher"] * 100)

                # Verkaufsfenster: vor vs. nach dem Datum „bis", normiert auf Ø/Tag
                one = pd.Timedelta(days=1)
                von_d, bis_d = pd.Timestamp(von), pd.Timestamp(bis)
                first, last = ol["d"].min(), ol["d"].max()
                before = ol[(ol["d"] >= von_d) & (ol["d"] < bis_d)]
                after = ol[ol["d"] >= bis_d]
                before_days = max(1, (min(bis_d, last + one) - max(von_d, first)).days)
                after_days = max(1, (last + one - max(bis_d, first)).days)

                def grp(d):
                    return d.groupby(["productId", "ref"]).agg(
                        menge=("quantity", "sum"), net=("net", "sum")).reset_index()

                both = grp(before).merge(grp(after), on=["productId", "ref"],
                                         how="outer", suffixes=("_v", "_n")).fillna(0)
                both = both[both["menge_v"] > 0].copy()  # nur Produkte mit Verkäufen vorher
                both["vor_rate"] = both["menge_v"] / before_days
                both["nach_rate"] = both["menge_n"] / after_days
                both["qty_pct"] = (both["nach_rate"] - both["vor_rate"]) / both["vor_rate"] * 100
                both["eppu"] = both["net_v"] / both["menge_v"]
                # Effekt-Einheiten je Richtung (geschätzt über after_days)
                both["lost_units"] = (both["vor_rate"] - both["nach_rate"]).clip(lower=0) * after_days
                both["gained_units"] = (both["nach_rate"] - both["vor_rate"]).clip(lower=0) * after_days
                both["lost_net"] = both["lost_units"] * both["eppu"]
                both["gained_net"] = both["gained_units"] * both["eppu"]

                res = both.merge(preise[["productId", "ref", "preis_vorher", "preis_nachher", "preis_pct"]],
                                 on=["productId", "ref"], how="inner")
                res["Produkt"] = res["productId"].map(namen)

                st.caption(
                    f"Fenster: vorher {before_days} Tage (ab {fmt_date(von)}) · "
                    f"nachher {after_days} Tage (ab {fmt_date(bis)}). "
                    "Mengen als Ø/Tag normiert."
                )

                def render_wirkung(verlust):
                    if verlust:
                        sig = res[(res["preis_pct"] >= pth) & (res["qty_pct"] <= -qth)].copy()
                        eff_units, eff_net = "lost_units", "lost_net"
                        lbl_units, lbl_net = "Verlust Stk.", "Verlust € (netto)"
                        kpi_units, kpi_net = "Verlorene Einheiten (gesch.)", "Verlorener Umsatz (gesch.)"
                        titel = ":red[:material/trending_down:] Verluste – Preiserhöhung → Mengenrückgang"
                        leer = "Keine signifikanten Abverkaufsverluste durch Preiserhöhungen für diese Auswahl."
                        tag = "verluste"
                    else:
                        sig = res[(res["preis_pct"] <= -pth) & (res["qty_pct"] >= qth)].copy()
                        eff_units, eff_net = "gained_units", "gained_net"
                        lbl_units, lbl_net = "Mehrabsatz Stk.", "Mehrumsatz € (netto)"
                        kpi_units, kpi_net = "Gewonnene Einheiten (gesch.)", "Mehrumsatz (gesch.)"
                        titel = ":green[:material/trending_up:] Gewinne – Preissenkung → Mengenzuwachs"
                        leer = "Keine signifikanten Mengenzuwächse durch Preissenkungen für diese Auswahl."
                        tag = "gewinne"

                    st.markdown(f"##### {titel}")
                    sig = sig.sort_values(eff_net, ascending=False)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Betroffene Produkte/Reihen", f"{len(sig):,}".replace(",", "."))
                    m2.metric(kpi_units, f"{int(sig[eff_units].sum()):,}".replace(",", "."))
                    m3.metric(kpi_net, f"{sig[eff_net].sum():,.0f} €".replace(",", "."))

                    if sig.empty:
                        st.info(leer)
                        return
                    out = sig[["productId", "Produkt", "ref", "preis_vorher", "preis_nachher",
                               "preis_pct", "vor_rate", "nach_rate", "qty_pct", eff_units, eff_net]].copy()
                    out["ref"] = out["ref"].map(lambda r: ref_label(r, cfg))
                    for c in ["preis_vorher", "preis_nachher", "vor_rate", "nach_rate", eff_net]:
                        out[c] = out[c].round(2)
                    out["preis_pct"] = out["preis_pct"].round(1)
                    out["qty_pct"] = out["qty_pct"].round(1)
                    out[eff_units] = out[eff_units].round(0).astype(int)
                    out = out.rename(columns={
                        "productId": "PZN", "ref": "Preisreihe",
                        "preis_vorher": "Preis vorher", "preis_nachher": "Preis nachher",
                        "preis_pct": "Preis Δ%", "vor_rate": "Menge/Tag vorher",
                        "nach_rate": "Menge/Tag nachher", "qty_pct": "Menge Δ%",
                        eff_units: lbl_units, eff_net: lbl_net,
                    })
                    st.dataframe(
                        out, use_container_width=True, hide_index=True,
                        column_config={
                            "Preis vorher": st.column_config.NumberColumn(format="%.2f €"),
                            "Preis nachher": st.column_config.NumberColumn(format="%.2f €"),
                            "Preis Δ%": st.column_config.NumberColumn(format="%.1f %%"),
                            "Menge/Tag vorher": st.column_config.NumberColumn(format="%.2f"),
                            "Menge/Tag nachher": st.column_config.NumberColumn(format="%.2f"),
                            "Menge Δ%": st.column_config.NumberColumn(format="%.1f %%"),
                            lbl_units: st.column_config.NumberColumn(format="%d"),
                            lbl_net: st.column_config.NumberColumn(format="%.2f €"),
                        },
                    )
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as w:
                        out.to_excel(w, index=False, sheet_name="Preiswirkung")
                    st.download_button(
                        ":material/download: Als Excel", data=buf.getvalue(),
                        file_name=f"abverkauf_preiswirkung_{tag}_{von}_{bis}.xlsx", key=f"ab_dl_{tag}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                render_wirkung(True)
                st.divider()
                render_wirkung(False)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 5 – Produktansicht (eine PZN: aktuelle Preise + Preisverlauf je Channel)
# st.fragment: Eingaben (PZN/Datum) rendern nur diesen Bereich neu, nicht alle Tabs.
# ════════════════════════════════════════════════════════════════════════════════
@st.fragment
def render_produktansicht():
    snaps = list_snapshots(drive)
    if not snaps:
        st.info("Noch keine Daten vorhanden. Bitte links in der Seitenleiste Preise hochladen.")
    else:
        pzn_raw = st.text_input("PZN", key="pv_pzn", placeholder="z. B. 03441621")
        pzn = pzn_raw.strip()
        if pzn.isdigit():
            pzn = pzn.zfill(8)

        if not pzn:
            st.caption("PZN eingeben, um aktuelle Preise und den Preisverlauf anzuzeigen.")
        else:
            rows = []
            for d in snaps.keys():  # aufsteigend sortiert
                snap = load_snapshot(drive, d)
                r = snap[snap["productId"] == pzn]
                if r.empty:
                    continue
                r = r.iloc[0]
                if "quote" in snap.columns and pd.notna(r.get("quote")):
                    rows.append({"Datum": d, "Reihe": QUOTE_LABEL, "Preis": float(r["quote"])})
                for c, lbl in zip(CHANNEL_COLS, CH_LABELS):
                    v = r.get(c)
                    if pd.notna(v):
                        rows.append({"Datum": d, "Reihe": lbl, "Preis": float(v)})
            hist = pd.DataFrame(rows)

            if hist.empty:
                st.warning(f"Keine Preisdaten für PZN {pzn} gefunden.")
            else:
                # Produktname aus Orderlines (falls vorhanden)
                ol_p = load_orderlines(drive)
                name = None
                if not ol_p.empty:
                    nm = ol_p[ol_p["productId"] == pzn]["productname"]
                    if not nm.empty:
                        name = nm.iloc[0]
                st.markdown(f"#### PZN {pzn}" + (f" — {name}" if name else ""))

                reihen_order = [QUOTE_LABEL] + CH_LABELS

                # Aktuelle Preise = jüngstes Datum mit Daten für diese PZN
                letztes = hist["Datum"].max()
                akt = hist[hist["Datum"] == letztes]
                vorhanden = [r for r in reihen_order if r in set(akt["Reihe"])]
                akt_idx = akt.set_index("Reihe")
                st.markdown(f"##### Aktuelle Preise ({fmt_date(letztes)})")
                pcols = st.columns(len(vorhanden))
                for i, reihe in enumerate(vorhanden):
                    pcols[i].metric(reihe, f"{akt_idx.loc[reihe, 'Preis']:.2f} €")

                # Preisverlauf-Diagramm – alle Reihen in unterschiedlichen Farben
                st.markdown("##### Preisverlauf")
                hist_chart = hist.copy()
                hist_chart["Datum"] = pd.to_datetime(hist_chart["Datum"])
                line = alt.Chart(hist_chart).mark_line(point=True).encode(
                    x=alt.X("Datum:T", title=None),
                    y=alt.Y("Preis:Q", title="Preis (€)", scale=alt.Scale(zero=False)),
                    color=alt.Color("Reihe:N", title="Preisreihe", sort=reihen_order),
                    tooltip=[alt.Tooltip("Datum:T", title="Datum"),
                             alt.Tooltip("Reihe:N", title="Reihe"),
                             alt.Tooltip("Preis:Q", format=".2f", title="Preis (€)")],
                )
                st.altair_chart(line, use_container_width=True)

                # ── Warenkörbe mit diesem Produkt ──
                st.divider()
                st.markdown("##### Warenkörbe mit diesem Produkt")
                if ol_p.empty or "order_id" not in ol_p.columns or ol_p["order_id"].isna().all():
                    st.info("Keine Bestellnummern in den Orderlines – bitte Orderlines mit "
                            "OrderNumber-Spalte (neu) hochladen.")
                else:
                    pdmin, pdmax = ol_p["d"].min().date(), ol_p["d"].max().date()
                    pdef_von = max(pdmin, (ol_p["d"].max() - pd.Timedelta(days=29)).date())
                    pr1, pr2 = st.columns(2)
                    with pr1:
                        pv_von = st.date_input("Von", value=pdef_von, min_value=pdmin, max_value=pdmax,
                                               format="DD.MM.YYYY", key="pv_basket_von")
                    with pr2:
                        pv_bis = st.date_input("Bis", value=pdmax, min_value=pdmin, max_value=pdmax,
                                               format="DD.MM.YYYY", key="pv_basket_bis")
                    olb = ol_p[(ol_p["d"] >= pd.Timestamp(pv_von)) & (ol_p["d"] <= pd.Timestamp(pv_bis))
                               & ol_p["order_id"].notna()]
                    st.caption(f"Datenbasis: {len(olb):,} Orderlines · "
                               f"{pv_von:%d.%m.%Y} – {pv_bis:%d.%m.%Y}".replace(",", "."))
                    orders = olb[olb["productId"] == pzn]["order_id"].unique()
                    if len(orders) == 0:
                        st.info("Dieses Produkt kommt in keinem Warenkorb mit Bestellnummer vor.")
                    else:
                        sub = olb[olb["order_id"].isin(orders)].copy()
                        # relative Marge ist ein Anteil (margin × net = Rohmarge €)
                        sub["_marge_eur"] = pd.to_numeric(sub["margin"], errors="coerce") * sub["net"]
                        basket = sub.groupby("order_id").agg(
                            datum=("date", "max"), wert=("net", "sum"), pos=("productId", "count"),
                            marge_eur=("_marge_eur", "sum"))
                        thisv = sub[sub["productId"] == pzn].groupby("order_id")["net"].sum()
                        basket["andere"] = basket["wert"] - basket.index.map(thisv).fillna(0.0)
                        basket["rel_marge"] = basket["marge_eur"] / basket["wert"]

                        basket["cm2"] = pl.basket_cm2(sub)

                        cm2_hilfe = (
                            "CM2 je Warenkorb = Rohmarge € − (4 % variable Operationskosten + 2 % Payment) "
                            "× Netto-Warenkorbwert − 4 € (Verpackung & Versand); "
                            "+ 2,44 € Versandgebühr, wenn der Brutto-Warenkorbwert (Netto+MwSt) < 25 € ist. "
                            "Rohmarge € = Σ Marge × Netto je Artikel. "
                            "Der KPI ist der Durchschnitt über alle Warenkörbe mit diesem Produkt."
                        )

                        b1, b2, b3, b4, b5 = st.columns(5)
                        b1.metric("Warenkörbe mit Produkt", f"{len(basket):,}".replace(",", "."))
                        b2.metric("Ø Warenkorbwert (netto)", f"{basket['wert'].mean():.2f} €")
                        b3.metric("Ø mitgekaufter Wert (netto)", f"{basket['andere'].mean():.2f} €")
                        b4.metric("Ø relative Marge", f"{basket['rel_marge'].mean() * 100:.1f} %")
                        b5.metric("Ø CM2 / Warenkorb", f"{basket['cm2'].mean():.2f} €", help=cm2_hilfe)

                        co = (sub[sub["productId"] != pzn].groupby("order_id")["productname"]
                              .apply(lambda s: ", ".join(s.dropna().astype(str))))
                        st.markdown("##### Letzte 50 Warenkörbe")
                        last = basket.sort_values("datum", ascending=False).head(50).reset_index()
                        last["Mitgekaufte Artikel"] = last["order_id"].map(co).fillna("—")
                        last["datum"] = pd.to_datetime(last["datum"]).dt.strftime("%d.%m.%Y")
                        last["wert"] = last["wert"].round(2)
                        last["cm2"] = last["cm2"].round(2)
                        last = last.rename(columns={
                            "order_id": "Bestellnr.", "datum": "Datum", "pos": "Positionen",
                            "wert": "Warenkorbwert netto €", "cm2": "CM2 €"})
                        st.caption("Zeile anklicken, um alle Positionen des Warenkorbs zu sehen. "
                                   "Alle Warenkorbwerte sind Netto-Werte (TotalNet).")
                        ev = st.dataframe(
                            last[["Datum", "Bestellnr.", "Positionen", "Warenkorbwert netto €", "CM2 €", "Mitgekaufte Artikel"]],
                            use_container_width=True, hide_index=True,
                            on_select="rerun", selection_mode="single-row", key="pv_basket_sel",
                            column_config={
                                "Positionen": st.column_config.NumberColumn(format="%d"),
                                "CM2 €": st.column_config.NumberColumn(format="%.2f €"),
                                "Warenkorbwert netto €": st.column_config.NumberColumn(format="%.2f €"),
                            },
                        )
                        if ev.selection.rows:
                            oid = last.iloc[ev.selection.rows[0]]["Bestellnr."]
                            pos = sub[sub["order_id"] == oid][
                                ["productId", "productname", "quantity", "net"]].copy()
                            pos.insert(0, "", pos["productId"].apply(lambda p: "▶" if p == pzn else ""))
                            pos = pos.rename(columns={
                                "productId": "PZN", "productname": "Produkt",
                                "quantity": "Menge", "net": "Netto €"})
                            st.markdown(f"**Warenkorb {oid} — {len(pos)} Positionen**")
                            st.dataframe(
                                pos, use_container_width=True, hide_index=True,
                                column_config={
                                    "": st.column_config.TextColumn(width="small"),
                                    "Menge": st.column_config.NumberColumn(format="%d"),
                                    "Netto €": st.column_config.NumberColumn(format="%.2f €"),
                                },
                            )

                        # ── Source-Verteilung der Warenkörbe ──
                        st.divider()
                        st.markdown("##### Warenkörbe nach Source")
                        src = sub.groupby("order_id")["source"].first()
                        src_counts = (src.value_counts().rename_axis("Source")
                                      .reset_index(name="Warenkörbe"))
                        src_counts["Anteil"] = (src_counts["Warenkörbe"]
                                                / src_counts["Warenkörbe"].sum() * 100).round(1)
                        pie = alt.Chart(src_counts).mark_arc().encode(
                            theta=alt.Theta("Warenkörbe:Q", stack=True),
                            color=alt.Color("Source:N", title="Source"),
                            tooltip=[alt.Tooltip("Source:N", title="Source"),
                                     alt.Tooltip("Warenkörbe:Q", title="Warenkörbe"),
                                     alt.Tooltip("Anteil:Q", format=".1f", title="Anteil %")],
                        )
                        st.altair_chart(pie, use_container_width=True)


with tab_produkt:
    render_produktansicht()
