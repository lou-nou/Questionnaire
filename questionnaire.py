import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import gspread
from google.oauth2.service_account import Credentials as SACredentials
import numpy as np
import uuid
import json
import re
import time
from contextlib import closing

# =========================
# CONFIG / CONSTANTES
# =========================
st.set_page_config(page_title="Évaluation de critères", page_icon="📊", layout="wide")

GSPREAD_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DEFAULT_DB_PATH = "evaluation.db"
DEFAULT_TABLE = "evaluations"
GOOGLE_SHEET_ID = "1HbregwmVT8-adMkFxWGBu_JNSfrmBHM3FJWCR3hI_dI"  # <-- remplace si besoin

# =========================
# CREDENTIALS GCP (sécurisé)
# =========================
def load_gcp_credentials(
    scopes=GSPREAD_SCOPES,
    secrets_path=("gcp", "credentials"),
    env_var="GOOGLE_APPLICATION_CREDENTIALS",
    fallback_local_path="credentials.json",
) -> SACredentials:
    """
    Charge les credentials GCP dans cet ordre:
      1) st.secrets['gcp']['credentials'] : JSON string multi-ligne (recommandé, Cloud & local .streamlit/secrets.toml)
      2) variable d'env GOOGLE_APPLICATION_CREDENTIALS : chemin vers un fichier JSON
      3) fichier local 'credentials.json' (pour dev local, ignoré par git)

    Retourne un objet google.oauth2.service_account.Credentials
    """
    # 1) Streamlit secrets
    try:
        sect, key = secrets_path
        raw = st.secrets[sect][key]
        info = json.loads(raw)
        return SACredentials.from_service_account_info(info, scopes=scopes)
    except Exception:
        pass

    # 2) Variable d'environnement (chemin vers le fichier JSON)
    cred_path = os.getenv(env_var)
    if cred_path and os.path.exists(cred_path):
        return SACredentials.from_service_account_file(cred_path, scopes=scopes)

    # 3) Fallback local (non versionné)
    if os.path.exists(fallback_local_path):
        st.warning("⚠️ Utilisation d’un credentials.json local (non recommandé en production).")
        return SACredentials.from_service_account_file(fallback_local_path, scopes=scopes)

    st.error(
        "Aucun identifiant GCP trouvé. Ajoute ta clé dans **Settings → Secrets** "
        "sous `gcp.credentials` (JSON), ou définis `GOOGLE_APPLICATION_CREDENTIALS`, "
        "ou place un fichier local `credentials.json` (ignoré par git)."
    )
    st.stop()

def get_gspread_client():
    creds = load_gcp_credentials()
    return gspread.authorize(creds)

# =========================
# SQLite robuste
# =========================
def _snake(s: str) -> str:
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^\w]", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()

def _sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # noms sûrs & uniques
    new_cols, seen = [], set()
    for c in df.columns.map(str):
        base, name, i = _snake(c), None, 1
        name = base
        while name in seen:
            i += 1
            name = f"{base}_{i}"
        seen.add(name)
        new_cols.append(name)
    df.columns = new_cols

    # types
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_bool_dtype(df[c]):
            df[c] = df[c].astype("int64")
        elif pd.api.types.is_object_dtype(df[c]):
            df[c] = df[c].apply(lambda x: None if (pd.isna(x) or x == "") else str(x))
        elif pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = df[c].astype("string")

    df = df.where(pd.notna(df), None)  # NaN -> NULL
    return df

def _safe_chunksize(n_cols: int) -> int:
    # Respect limite SQLite ~999 variables → marge
    return max(1, 900 // max(1, n_cols))

def sauvegarder_reponses_sqlite(df: pd.DataFrame, db_path: str = DEFAULT_DB_PATH, table: str = DEFAULT_TABLE) -> None:
    if df is None or df.empty:
        raise ValueError("Aucune donnée à enregistrer.")

    df2 = _sanitize_dataframe(df)
    chunksize = _safe_chunksize(len(df2.columns))
    max_retries, delay = 5, 0.5

    with closing(sqlite3.connect(db_path, timeout=30, check_same_thread=False)) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        for attempt in range(1, max_retries + 1):
            try:
                df2.to_sql(
                    table,
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=chunksize,
                )
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                msg = str(e)
                if "has no column named" in msg or "no such column" in msg:
                    raise RuntimeError(
                        f"Schéma incompatible avec la table '{table}'. "
                        f"Supprime/renomme la base ou migre le schéma. Détails: {msg}"
                    ) from e
                if "no such table" in msg:
                    df2.head(0).to_sql(table, conn, if_exists="fail", index=False)
                    continue
                if "database is locked" in msg:
                    if attempt < max_retries:
                        time.sleep(delay * attempt)
                        continue
                    raise RuntimeError("Base verrouillée. Réessaie plus tard.") from e
                if "too many SQL variables" in msg:
                    new_chunksize = max(1, chunksize // 2)
                    if new_chunksize == chunksize:
                        raise
                    chunksize = new_chunksize
                    continue
                raise RuntimeError(f"Erreur SQLite: {msg}") from e
            except sqlite3.IntegrityError as e:
                raise RuntimeError(f"Contrainte UNIQUE/NOT NULL violée : {e}") from e

# =========================
# Google Sheets
# =========================
def sauvegarder_reponses_google_sheets(df: pd.DataFrame, sheet_id: str, header_mode: str = "insert_if_missing"):
    """
    Envoie les données + en-têtes dans Google Sheets.
    header_mode ∈ {"insert_if_missing", "overwrite", "keep"}
    """
    client = get_gspread_client()
    sheet = client.open_by_key(sheet_id).sheet1

    # Nettoyage valeurs (et datetimes → string)
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df.replace([np.nan, np.inf, -np.inf], "", regex=False)

    headers = [str(c) for c in df.columns.tolist()]

    if header_mode != "keep":
        try:
            first_row = sheet.row_values(1)
        except Exception:
            first_row = []
        if not first_row:
            sheet.update("A1", [headers])
        else:
            if first_row != headers:
                if header_mode == "insert_if_missing":
                    sheet.insert_row(headers, 1)
                elif header_mode == "overwrite":
                    sheet.update("1:1", [headers])

    rows = df.astype(object).values.tolist()
    if rows:
        sheet.append_rows(rows, value_input_option="USER_ENTERED")

# =========================
# DONNÉES QUESTIONNAIRE
# =========================
criteres = [
    "Impact énergie-climat",
    "Coût d’investissement (CAPEX)",
    "Aide-subvention",
    "Retour sur investissement (ROI)",
    "Temps de retour sur investissement",
    "Facilité de mise en œuvre",
    "Effet levier ou structurant",
    "Durée de vie de l’action",
    "Acceptabilité pour les utilisateurs",
    "Visibilité et exemplarité",
]

axes = [
    "pertinence stratégique",
    "capacité discriminante",
    "fiabilité de l'évaluation",
    "Acceptabilité politique et sociale",
    "temporalité/Durabilité",
]

axes_definitions = {
    "pertinence stratégique": "Niveau de contribution directe du critère aux objectifs et priorités de l'établissement",
    "capacité discriminante": "Capacité du critère à distinguer clairement les différentes options",
    "fiabilité de l'évaluation": "Niveau de fiabilité et facilité d'obtention des données",
    "Acceptabilité politique et sociale": "Niveau d'acceptabilité et de soutien par les parties prenantes",
    "temporalité/Durabilité": "Stabilité de l'importance du critère dans le temps",
}

# =========================
# SESSION STATE
# =========================
if "page" not in st.session_state:
    st.session_state.page = 0
if "reponses" not in st.session_state:
    st.session_state.reponses = {}
if "fin" not in st.session_state:
    st.session_state.fin = False
if "id_participant" not in st.session_state:
    st.session_state.id_participant = str(uuid.uuid4())[:8]  # ID court et unique

# =========================
# FONCTIONS MÉTIER
# =========================
def enregistrer_reponse(notes, critere):
    st.session_sta_


try:
    sa_email = json.loads(st.secrets["gcp"]["credentials"])["client_email"]
    st.caption(f"Service account détecté : {sa_email}")
except Exception as e:
    st.warning(f"Secret GCP introuvable : {e}")