"""
Gemeinsame Logik für die Pricing-Seiten (Seite 3: Pricing, Seite 4: Masterdatei-Analyse).

Enthält Konstanten, Parser für Quote-/Channel-/Master-Dateien sowie die
Drive-Zugriffe (Ordner, Snapshots, Download). Reine Funktionen ohne Streamlit-
Caching/UI — die Caching-Wrapper (st.cache_data) liegen in den jeweiligen Seiten.
"""

import io
import re
from datetime import date, datetime

import pandas as pd

# ─── Konstanten ────────────────────────────────────────────────────────────────

PRICING_FOLDER_NAME = "Pricing"

# Channel-Snapshot (channel_prices_*.csv, Preise in Cent)
CHANNEL_COLS = ["channelPrice1", "channelPrice2", "channelPrice3", "channelPrice4", "channelPrice5"]
CHANNEL_LABELS = ["Channel 1", "Channel 2", "Channel 3", "Channel 4", "Channel 5"]

# Masterdatei (channelpilot-Export, Preise in EUR)
MASTER_CHANNEL_COLS = ["channel_price_1", "channel_price_2", "channel_price_3",
                       "channel_price_4", "channel_price_5"]
MASTER_RAW_KEEP = ["product_id", "pzn", "manufacturer", "title", "price", "uvp", "aep",
                   "prescription_required", "vat_percent"] + MASTER_CHANNEL_COLS
MASTER_NUM_COLS = ["price", "uvp", "aep"] + MASTER_CHANNEL_COLS

# Preis-Cluster nach Preishöhe (EUR)
PRICE_EDGES = [0, 10, 25, 50, 100, float("inf")]
PRICE_LABELS = ["0–10 €", "10–25 €", "25–50 €", "50–100 €", "100+ €"]


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────────

def parse_date_from_filename(filename: str):
    """Erkennt DDMMYY am Ende des Dateinamens (z. B. quote_prices_110626.csv → 11.06.2026)."""
    m = re.search(r"(\d{2})(\d{2})(\d{2})(?:\.csv)?$", filename)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(2000 + y, mo, d)
    except ValueError:
        return None


def fmt_date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d.%m.%Y")


def assign_price_cluster(series_eur: pd.Series) -> pd.Series:
    return pd.cut(series_eur, bins=PRICE_EDGES, labels=PRICE_LABELS, right=False)


# ─── Parser ─────────────────────────────────────────────────────────────────────

def parse_quote_bytes(data: bytes) -> pd.DataFrame:
    """quote_prices CSV (productId|quote_price, Cent) → DataFrame[productId, quote] (EUR)."""
    df = pd.read_csv(io.BytesIO(data), sep="|", dtype={"productId": str})
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"quote_price": "quote"})
    df["quote"] = pd.to_numeric(df["quote"], errors="coerce") / 100.0
    df = df[(df["quote"].notna()) & (df["quote"] > 0)]
    return df[["productId", "quote"]].drop_duplicates("productId")


def parse_channel_bytes(data: bytes) -> pd.DataFrame:
    """channel_prices CSV (productId|channelPrice1..5, Cent) → DataFrame (EUR)."""
    df = pd.read_csv(io.BytesIO(data), sep="|", dtype={"productId": str})
    df.columns = df.columns.str.strip()
    for c in CHANNEL_COLS:
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
        df.loc[df[c] <= 0, c] = pd.NA
    return df[["productId"] + CHANNEL_COLS].drop_duplicates("productId")


def _coerce_master(df: pd.DataFrame) -> pd.DataFrame:
    """Typkonvertierung der Master-Spalten (Preise EUR, vat %, Rezeptpflicht bool)."""
    for c in MASTER_NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "vat_percent" in df.columns:
        df["vat_percent"] = pd.to_numeric(df["vat_percent"], errors="coerce").round(1)
    if "prescription_required" in df.columns:
        df["prescription_required"] = (
            df["prescription_required"].astype(str).str.strip().str.lower()
            .map({"true": True, "false": False})
        )
    return df


def parse_master_bytes(data: bytes) -> pd.DataFrame:
    """Roher channelpilot-Export (Komma-CSV) → reduzierte, typisierte Master-Tabelle.
    `product_id` wird zu `productId` (8-stelliger PZN-Schlüssel, passend zu Quote/Channel)."""
    df = pd.read_csv(io.BytesIO(data), dtype=str)
    df.columns = df.columns.str.strip()
    keep = [c for c in MASTER_RAW_KEEP if c in df.columns]
    df = df[keep].rename(columns={"product_id": "productId"})
    df = _coerce_master(df)
    df = df[df["productId"].notna()]
    return df.drop_duplicates("productId")


def read_master_csv(data: bytes) -> pd.DataFrame:
    """Liest die in Drive gespeicherte (bereits reduzierte) Master-CSV zurück."""
    df = pd.read_csv(io.BytesIO(data), dtype={"productId": str, "pzn": str})
    df.columns = df.columns.str.strip()
    return _coerce_master(df)


# ─── Google Drive ────────────────────────────────────────────────────────────────

def waehle_ordner(drive, files):
    """Bei mehreren gleichnamigen Ordnern: den mit Inhalt bevorzugen, sonst den ältesten."""
    if len(files) == 1:
        return files[0]["id"]
    for f in files:
        kids = drive.files().list(
            q=f"'{f['id']}' in parents and trashed=false",
            fields="files(id)", pageSize=1,
        ).execute(num_retries=3).get("files", [])
        if kids:
            return f["id"]
    return files[0]["id"]


def get_pricing_folder_id(drive):
    """ID des Ordners 'Pricing' (legt ihn an falls nötig)."""
    q = (f"name='{PRICING_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false")
    res = drive.files().list(q=q, fields="files(id)", orderBy="createdTime",
                             pageSize=10).execute(num_retries=3)
    files = res.get("files", [])
    if files:
        return waehle_ordner(drive, files)
    folder = drive.files().create(
        body={"name": PRICING_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute(num_retries=3)
    return folder["id"]


def list_snapshots(drive):
    """Alle gespeicherten Snapshots → dict {iso_datum: {quote_id, channel_id, master_id}} (sortiert)."""
    folder_id = get_pricing_folder_id(drive)
    res = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name)", pageSize=1000,
    ).execute(num_retries=3)
    snaps = {}
    for f in res.get("files", []):
        d = parse_date_from_filename(f["name"])
        if d is None:
            continue
        key = d.isoformat()
        entry = snaps.setdefault(key, {"quote_id": None, "channel_id": None, "master_id": None})
        name = f["name"].lower()
        if name.startswith("quote"):
            entry["quote_id"] = f["id"]
        elif name.startswith("channel"):
            entry["channel_id"] = f["id"]
        elif name.startswith("master"):
            entry["master_id"] = f["id"]
    return dict(sorted(snaps.items()))


def download_bytes(drive, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = dl.next_chunk(num_retries=3)
    buf.seek(0)
    return buf.getvalue()


def load_snapshot(drive, iso_datum: str) -> pd.DataFrame:
    """Quote + Channel eines Zeitpunkts, gemerged auf productId (für Momentaufnahme/Vergleich)."""
    snaps = list_snapshots(drive)
    entry = snaps.get(iso_datum)
    if not entry:
        return pd.DataFrame()
    quote_df = parse_quote_bytes(download_bytes(drive, entry["quote_id"])) if entry["quote_id"] else \
        pd.DataFrame(columns=["productId", "quote"])
    chan_df = parse_channel_bytes(download_bytes(drive, entry["channel_id"])) if entry["channel_id"] else \
        pd.DataFrame(columns=["productId"] + CHANNEL_COLS)
    return quote_df.merge(chan_df, on="productId", how="outer")


def load_channel(drive, iso_datum: str) -> pd.DataFrame:
    """Nur die Channel-Snapshot-Preise eines Zeitpunkts (EUR)."""
    snaps = list_snapshots(drive)
    entry = snaps.get(iso_datum)
    if not entry or not entry["channel_id"]:
        return pd.DataFrame(columns=["productId"] + CHANNEL_COLS)
    return parse_channel_bytes(download_bytes(drive, entry["channel_id"]))


def load_master(drive, iso_datum: str) -> pd.DataFrame:
    """Reduzierte Master-Tabelle eines Zeitpunkts."""
    snaps = list_snapshots(drive)
    entry = snaps.get(iso_datum)
    if not entry or not entry["master_id"]:
        return pd.DataFrame()
    return read_master_csv(download_bytes(drive, entry["master_id"]))
