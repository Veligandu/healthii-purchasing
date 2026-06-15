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

# ─── Gemeinsame Logik (pricing_lib) ─────────────────────────────────────────────

import pricing_lib as pl
from pricing_lib import (
    CHANNEL_COLS, CHANNEL_LABELS, MASTER_CHANNEL_COLS, PRICE_EDGES, PRICE_LABELS,
    parse_date_from_filename, parse_quote_bytes, parse_channel_bytes,
    parse_master_bytes, assign_price_cluster, fmt_date,
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
    st.caption("Quote-, Channel- und Masterdatei eines Zeitpunkts. Datum wird aus dem Dateinamen erkannt.")

    quote_file = st.file_uploader("Quote-Preise (CSV)", type=["csv"], key="up_quote")
    channel_file = st.file_uploader("Channel-Preise (CSV)", type=["csv"], key="up_channel")
    master_file = st.file_uploader("Masterdatei (CSV)", type=["csv"], key="up_master")

    # Datum vorbelegen aus Dateinamen
    erkanntes_datum = None
    for f in (quote_file, channel_file, master_file):
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
    master_reduced = None
    if master_file is not None:
        try:
            master_reduced = parse_master_bytes(master_file.getvalue())
            st.success(f"Master: {len(master_reduced):,} Produkte".replace(",", "."))
        except Exception as e:
            st.error(f"Masterdatei nicht lesbar: {e}")

    if st.button("💾 In Drive speichern", type="primary", use_container_width=True,
                 disabled=(quote_file is None and channel_file is None and master_file is None)):
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
            "Master": "✅" if v.get("master_id") else "—",
        } for k, v in _snaps.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

tab_snap, tab_cmp, tab_master, tab_sales = st.tabs(
    ["📊 Momentaufnahme", "🔀 Vergleich", "🗂️ Masterdatei-Analyse", "🛒 Abverkauf"]
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
            long["Channel"] = long["ChannelCol"].map(dict(zip(CHANNEL_COLS, CHANNEL_LABELS)))
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
                    "📥 Kritische Preise als Excel",
                    data=buf.getvalue(),
                    file_name=f"kritische_preise_{sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

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
            st.caption("Δ = Masterpreis − Snapshot-Preis (Momentaufnahme). Positiv = Master teurer.")

            st.divider()

            # Abweichungen im Detail
            st.markdown("##### Abweichungen im Detail")
            fc1, fc2 = st.columns([1, 2])
            with fc1:
                nur_abw = st.toggle("Nur Abweichungen", value=True, key="ma_nur")
            with fc2:
                ch_filter = st.multiselect("Channel filtern", CHANNEL_LABELS,
                                           default=CHANNEL_LABELS, key="ma_chfilter")

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
                    "📥 Abgleich als Excel",
                    data=buf.getvalue(),
                    file_name=f"masterabgleich_{sel_m}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 – Abverkauf (später)
# ════════════════════════════════════════════════════════════════════════════════
with tab_sales:
    st.subheader("Abverkaufsdaten")
    st.info(
        "Dieser Bereich ist für die Abverkaufsanalyse vorgesehen: Schnelldreher vs. Langsamdreher "
        "sowie wichtige Produkte, die durch Preisänderungen gewonnen oder verloren wurden.\n\n"
        "Sobald du die Abverkaufsdaten bereitstellst, wird er aktiviert."
    )
