"""
Gemeinsame Logik für die Pricing-Seiten (Seite 3: Pricing, Seite 4: Masterdatei-Analyse).

Enthält Konstanten, Parser für Quote-/Channel-/Master-Dateien sowie die
Drive-Zugriffe (Ordner, Snapshots, Download). Reine Funktionen ohne Streamlit-
Caching/UI — die Caching-Wrapper (st.cache_data) liegen in den jeweiligen Seiten.
"""

import io
import json
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

# Orderlines (Abverkauf)
ORDERLINES_FILE = "orderlines.csv"
ORDERLINES_COLS = ["productId", "productname", "type", "source", "order_id", "date",
                   "quantity", "net", "ek", "margin"]

# Konfiguration (Channel-Bezeichnungen + Source-Zuordnung), persistent in Drive
CONFIG_FILE = "pricing_config.json"
REF_QUOTE = "quote"          # interner Schlüssel für die Quote-Preisreihe
QUOTE_LABEL = "Quote"        # Anzeigename der Quote-Preisreihe

# Interne Channel-Schlüssel = Snapshot-Spalten (channelPrice1..5); Labels sind nur Anzeige.
DEFAULT_CHANNEL_LABELS = {c: f"Channel {i + 1}" for i, c in enumerate(CHANNEL_COLS)}
# Default-Zuordnung Marketing-Source → Channel-Schlüssel (Rest → Quote)
DEFAULT_SOURCE_MAP = {
    "googleph": "channelPrice1",
    "bing": "channelPrice1",
    "idealo": "channelPrice2",
    "medizinfuchs": "channelPrice3",
}

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    "jan": 1, "feb": 2, "mrz": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "okt": 10, "nov": 11, "dez": 12,
}


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
        name = f["name"].lower()
        kind = ("quote_id" if name.startswith("quote") else
                "channel_id" if name.startswith("channel") else
                "master_id" if name.startswith("master") else None)
        if kind is None:  # report_/config/orderlines etc. erzeugen keinen Snapshot
            continue
        d = parse_date_from_filename(f["name"])
        if d is None:
            continue
        entry = snaps.setdefault(d.isoformat(),
                                 {"quote_id": None, "channel_id": None, "master_id": None})
        entry[kind] = f["id"]
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


# ─── Orderlines (Abverkauf) ──────────────────────────────────────────────────────

def _de_num(series: pd.Series) -> pd.Series:
    """Deutsche Zahlen ('1.234,56') → float."""
    return pd.to_numeric(
        series.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def _parse_de_date(s):
    """Deutsches Datum 'DD Monat, YYYY' → ISO-String 'YYYY-MM-DD' (oder None)."""
    if not isinstance(s, str):
        return None
    parts = s.replace(",", " ").split()
    if len(parts) < 3:
        return None
    try:
        tag = int(parts[0])
        mon = GERMAN_MONTHS.get(parts[1].strip().lower())
        jahr = int(parts[2])
        if mon is None:
            return None
        return date(jahr, mon, tag).isoformat()
    except (ValueError, KeyError):
        return None


def ref_for_source(source: str, source_map: dict) -> str:
    """Marketing-Source → Preisreihen-Schlüssel (channelPriceN oder 'quote')."""
    return source_map.get(str(source).strip().lower(), REF_QUOTE)


def parse_orderlines_bytes(data: bytes) -> pd.DataFrame:
    """Roher Orderlines-Export → normalisierte Tabelle (Spalten = ORDERLINES_COLS)."""
    df = pd.read_csv(io.BytesIO(data), dtype=str)
    df.columns = df.columns.str.strip()
    src_col = next((c for c in df.columns if "source" in c.lower()), None)
    oid_col = next((c for c in df.columns if c.strip().lower() == "ordernumber"), None)
    out = pd.DataFrame()
    out["productId"] = df["Pzn"].astype(str).str.strip()
    out["productname"] = df.get("Productname")
    out["type"] = df.get("Type")
    out["source"] = (df[src_col].astype(str).str.strip().str.lower()
                     if src_col else "unbekannt")
    out["order_id"] = df[oid_col].astype(str).str.strip() if oid_col else pd.NA
    out["date"] = df["CreatedAt: Tag"].map(_parse_de_date)
    out["quantity"] = pd.to_numeric(df.get("Quantity"), errors="coerce")
    out["net"] = _de_num(df["TotalNet"]) if "TotalNet" in df.columns else pd.NA
    out["ek"] = _de_num(df["Unit Ek Net"]) if "Unit Ek Net" in df.columns else pd.NA
    out["margin"] = _de_num(df["Relative Margin (€)"]) if "Relative Margin (€)" in df.columns else pd.NA
    out = out[out["productId"].notna() & out["date"].notna() & out["quantity"].notna()]
    return out[ORDERLINES_COLS].reset_index(drop=True)


def load_orderlines(drive) -> pd.DataFrame:
    """Lädt die in Drive akkumulierten Orderlines (normalisiert)."""
    folder_id = get_pricing_folder_id(drive)
    q = f"name='{ORDERLINES_FILE}' and '{folder_id}' in parents and trashed=false"
    files = drive.files().list(q=q, fields="files(id)", pageSize=1).execute(num_retries=3).get("files", [])
    if not files:
        return pd.DataFrame(columns=ORDERLINES_COLS)
    df = pd.read_csv(io.BytesIO(download_bytes(drive, files[0]["id"])),
                     dtype={"productId": str, "order_id": str})
    if "order_id" not in df.columns:  # ältere Bestände ohne Bestellnummer
        df["order_id"] = pd.NA
    return df


def merge_orderlines(existing: pd.DataFrame, neu: pd.DataFrame) -> pd.DataFrame:
    """Akkumuliert neue Orderlines zu bestehenden, Dedup über alle Spalten."""
    combined = pd.concat([existing, neu], ignore_index=True)
    return combined.drop_duplicates().reset_index(drop=True)


def apply_orderlines(existing: pd.DataFrame, neu: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Fügt neue Orderlines hinzu.
    mode='append': nur Tage übernehmen, die noch nicht vorhanden sind.
    mode='replace': für Tage, die in `neu` vorkommen, alte Zeilen ersetzen."""
    if existing is None or existing.empty:
        return neu.drop_duplicates().reset_index(drop=True)
    neu_dates = set(neu["date"].unique())
    if mode == "replace":
        keep = existing[~existing["date"].isin(neu_dates)]
        combined = pd.concat([keep, neu], ignore_index=True)
    else:  # append
        existing_dates = set(existing["date"].unique())
        add = neu[~neu["date"].isin(existing_dates)]
        combined = pd.concat([existing, add], ignore_index=True)
    return combined.drop_duplicates().reset_index(drop=True)


def delete_orderlines_range(df: pd.DataFrame, von_iso: str, bis_iso: str) -> pd.DataFrame:
    """Entfernt alle Orderlines mit Datum in [von_iso, bis_iso] (ISO-Strings)."""
    if df is None or df.empty:
        return df
    mask = (df["date"] >= von_iso) & (df["date"] <= bis_iso)
    return df[~mask].reset_index(drop=True)


def price_table(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    """Snapshot (quote + channelPrice1..5) → Long-Tabelle [productId, ref, price].
    ref ist der interne Schlüssel: 'quote' oder channelPriceN."""
    parts = []
    if "quote" in snapshot_df.columns:
        p = snapshot_df[["productId", "quote"]].rename(columns={"quote": "price"})
        p["ref"] = REF_QUOTE
        parts.append(p)
    for col in CHANNEL_COLS:
        if col in snapshot_df.columns:
            q = snapshot_df[["productId", col]].rename(columns={col: "price"})
            q["ref"] = col
            parts.append(q)
    if not parts:
        return pd.DataFrame(columns=["productId", "ref", "price"])
    out = pd.concat(parts, ignore_index=True)
    return out[out["price"].notna()][["productId", "ref", "price"]]


# ─── Konfiguration (Channel-Labels + Source-Zuordnung) ───────────────────────────

def default_config() -> dict:
    return {
        "channel_labels": dict(DEFAULT_CHANNEL_LABELS),
        "source_map": dict(DEFAULT_SOURCE_MAP),
    }


def _merge_config(cfg: dict) -> dict:
    """Füllt fehlende Schlüssel mit Defaults auf (robust gegen Teil-Configs)."""
    base = default_config()
    if not isinstance(cfg, dict):
        return base
    labels = base["channel_labels"]
    labels.update({k: v for k, v in (cfg.get("channel_labels") or {}).items() if k in labels and v})
    src = {str(k).strip().lower(): v for k, v in (cfg.get("source_map") or {}).items()}
    return {"channel_labels": labels, "source_map": src or base["source_map"]}


def load_config(drive) -> dict:
    """Lädt die Pricing-Konfiguration aus Drive (oder Defaults)."""
    folder_id = get_pricing_folder_id(drive)
    q = f"name='{CONFIG_FILE}' and '{folder_id}' in parents and trashed=false"
    files = drive.files().list(q=q, fields="files(id)", pageSize=1).execute(num_retries=3).get("files", [])
    if not files:
        return default_config()
    try:
        return _merge_config(json.loads(download_bytes(drive, files[0]["id"]).decode("utf-8")))
    except Exception:
        return default_config()


def config_to_bytes(config: dict) -> bytes:
    return json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")


def channel_label_list(config: dict) -> list:
    """Liste der Channel-Anzeigenamen, ausgerichtet an CHANNEL_COLS."""
    labels = config.get("channel_labels", {})
    return [labels.get(c, DEFAULT_CHANNEL_LABELS[c]) for c in CHANNEL_COLS]


def ref_label(ref: str, config: dict) -> str:
    """Interner ref-Schlüssel ('quote'/channelPriceN) → Anzeigename."""
    if ref == REF_QUOTE:
        return QUOTE_LABEL
    return config.get("channel_labels", {}).get(ref, ref)


# ─── Report je Momentaufnahme ────────────────────────────────────────────────────

def report_filename(iso_datum: str) -> str:
    return "report_" + datetime.fromisoformat(iso_datum).strftime("%d%m%y") + ".txt"


def load_report(drive, iso_datum: str) -> str:
    """Lädt den gespeicherten Report-Text eines Zeitpunkts (oder '')."""
    folder_id = get_pricing_folder_id(drive)
    name = report_filename(iso_datum)
    q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
    files = drive.files().list(q=q, fields="files(id)", pageSize=1).execute(num_retries=3).get("files", [])
    if not files:
        return ""
    try:
        return download_bytes(drive, files[0]["id"]).decode("utf-8")
    except Exception:
        return ""
