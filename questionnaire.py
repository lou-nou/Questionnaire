import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import gspread
#from google.oauth2.service_account import Credentials
import numpy as np
import uuid

# --- Fonction de sauvegarde Google Sheets ---
# --- Google Sheets (via Streamlit Secrets) ---
import json
from google.oauth2.service_account import Credentials as SACredentials

# (optionnel) ID par défaut si rien n'est défini dans les secrets
DEFAULT_SHEET_ID = "1HbregwmVT8-adMkFxWGBu_JNSfrmBHM3FJWCR3hI_dI"

# Lit l'ID depuis les secrets, sinon fallback sur DEFAULT_SHEET_ID
GOOGLE_SHEET_ID = st.secrets.get("gcp", {}).get("sheet_id", DEFAULT_SHEET_ID)

def _get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        info = json.loads(st.secrets["gcp"]["credentials"])  # JSON (string) -> dict
    except Exception as e:
        st.error("Secret `gcp.credentials` introuvable ou invalide dans Settings → Secrets.")
        raise
    creds = SACredentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def sauvegarder_reponses_google_sheets(df: pd.DataFrame, sheet_id: str | None = None,
                                       header_mode: str = "insert_if_missing"):
    """
    Envoie les données dans Google Sheets, avec gestion des en-têtes.
    header_mode ∈ {"insert_if_missing", "overwrite", "keep"}
    """
    if sheet_id is None:
        sheet_id = GOOGLE_SHEET_ID
    if not sheet_id:
        st.error("Aucun 'sheet_id' fourni et aucun 'gcp.sheet_id' dans les secrets.")
        return

    client = _get_gspread_client()
    sheet = client.open_by_key(sheet_id).sheet1

    # Nettoyage valeurs (inf/NaN) et datetimes -> string
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df.replace([np.nan, np.inf, -np.inf], "", regex=False)

    headers = [str(c) for c in df.columns.tolist()]

    # Gestion des en-têtes
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

    # Ajout des données
    rows = df.astype(object).values.tolist()
    if rows:
        sheet.append_rows(rows, value_input_option="USER_ENTERED")


# --- Config page ---
st.set_page_config(page_title="Évaluation de critères", page_icon="📊", layout="wide")

# --- Données ---
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
    "Visibilité et exemplarité"
]

axes = [
    "pertinence stratégique",
    "capacité discriminante",
    "fiabilité de l'évaluation",
    "Acceptabilité politique et sociale",
    "temporalité/Durabilité"
]

axes_definitions = {
    "pertinence stratégique": "Niveau de contribution directe du critère aux objectifs et priorités de l'établissement",
    "capacité discriminante": "Capacité du critère à distinguer clairement les différentes options",
    "fiabilité de l'évaluation": "Niveau de fiabilité et facilité d'obtention des données",
    "Acceptabilité politique et sociale": "Niveau d'acceptabilité et de soutien par les parties prenantes",
    "temporalité/Durabilité": "Stabilité de l'importance du critère dans le temps"
}

# --- Init session ---
if "page" not in st.session_state:
    st.session_state.page = 0
if "reponses" not in st.session_state:
    st.session_state.reponses = {}
if "fin" not in st.session_state:
    st.session_state.fin = False
if "id_participant" not in st.session_state:
    st.session_state.id_participant = str(uuid.uuid4())[:8]  # ID court et unique

# --- Fonctions ---
def enregistrer_reponse(notes, critere):
    st.session_state.reponses[critere] = notes

def sauvegarder_reponses_sqlite(df):
    conn = sqlite3.connect("evaluation.db")
    df.to_sql("evaluations", conn, if_exists="append", index=False)
    conn.close()

def transformer_reponses(reponses, autres_criteres, commentaires, id_participant, date_validation):
    # Pivotage : une ligne par axe, colonnes = critères + autres champs
    lignes = []
    for i, axe in enumerate(axes):
        ligne = {
            "id_participant": id_participant,
            "date_validation": date_validation,
            "critere_evaluation": axe
        }
        for critere in criteres:
            note = reponses.get(critere, {}).get(axe, "")
            ligne[critere] = note
        # Ajouter les champs ouverts seulement sur la première ligne
        if i == 0:
            ligne["Autres critères suggérés"] = autres_criteres
            ligne["Commentaires / Remarques"] = commentaires
        else:
            ligne["Autres critères suggérés"] = ""
            ligne["Commentaires / Remarques"] = ""
        lignes.append(ligne)
    return pd.DataFrame(lignes)

# --- Bloc questionnaire / questions ouvertes ---
if not st.session_state.fin:
    if st.session_state.page < len(criteres):
        # 🔹 Affichage d’un critère
        critere = criteres[st.session_state.page]
        st.title("📊 Évaluation de critères d'aide à la décision")
        st.subheader(f"Critère {st.session_state.page + 1} sur {len(criteres)} : {critere}")

        progress = (st.session_state.page + 1) / (len(criteres) + 1)
        st.progress(progress)
        st.caption(f"Progression : {st.session_state.page + 1}/{len(criteres)+1} étapes")

        notes = {}
        for axe in axes:
            st.markdown(f"**{axe.capitalize()}** — *{axes_definitions[axe]}*")
            note = st.slider(
                f"Note pour {axe}", 1, 10, 5,
                key=f"slider-{st.session_state.page}-{axe}"
            )
            notes[axe] = note

        st.markdown("---")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.session_state.page > 0:
                st.button("⬅️ Précédent", on_click=lambda: setattr(st.session_state, 'page', st.session_state.page - 1))
        with col2:
            if st.session_state.page < len(criteres) - 1:
                st.button("Suivant ➡️", on_click=lambda: (
                    enregistrer_reponse(notes, critere),
                    setattr(st.session_state, 'page', st.session_state.page + 1)
                ))
            else:
                st.button("📄 Questions ouvertes ➡️", on_click=lambda: (
                    enregistrer_reponse(notes, critere),
                    setattr(st.session_state, 'page', st.session_state.page + 1)
                ))

    else:
        # 🔹 Questions ouvertes
        st.title("📝 Questions ouvertes")
        autre_critere = st.text_area(
            "Quel(s) autre(s) critère(s) d'aide à la décision vous semble-t-il important à ajouter à ce questionnaire ?"
        )
        commentaires = st.text_area(
            "Merci de nous indiquer vos commentaires et remarques sur ce questionnaire :"
        )

        st.markdown("---")
        st.subheader("📋 Récapitulatif de vos évaluations")
        reponses = st.session_state.get("reponses", {})
        if reponses:
            df = pd.DataFrame(reponses).T
            st.dataframe(df, use_container_width=True)
        else:
            st.write("Aucune réponse enregistrée pour l'instant.")

        def valider_questionnaire():
            date_validation = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            id_participant = st.session_state.id_participant
            # Transformation au format cible
            df_final = transformer_reponses(
                st.session_state.reponses,
                autre_critere,
                commentaires,
                id_participant,
                date_validation
            )
            # Sauvegarde SQLite
            sauvegarder_reponses_sqlite(df_final)
            # Sauvegarde Google Sheets avec en-têtes
            sheet_id = "1HbregwmVT8-adMkFxWGBu_JNSfrmBHM3FJWCR3hI_dI"  # Remplace par l’ID de ta feuille Google Sheets
            sauvegarder_reponses_google_sheets(df_final, sheet_id, header_mode="insert_if_missing")
            # Marquer questionnaire comme terminé
            st.session_state.fin = True

        st.button("✅ Valider le questionnaire", on_click=valider_questionnaire)

# --- Bloc redirection / message de fin ---
if st.session_state.fin:
    st.title("🎉 Merci de votre participation !")
    st.write("""
    Nous reviendrons vers vous rapidement avec le deuxième tour de l'évaluation, 
    accompagné de la synthèse des résultats du premier tour.
    """)

# --- Bouton d'export de la base SQLite ---
if os.path.exists("evaluation.db"):
    with open("evaluation.db", "rb") as f:
        st.download_button(
            label="📥 Télécharger la base de données (evaluation.db)",
            data=f,
            file_name="evaluation.db",
            mime="application/octet-stream"
        )
else:
    st.info("Aucune base de données à télécharger pour le moment.")
