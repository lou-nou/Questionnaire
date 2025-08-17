import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os

print("Dossier courant :", os.getcwd())
print("Contenu :", os.listdir(os.getcwd()))

pages_dir = os.path.join(os.getcwd(), "pages")
if os.path.exists(pages_dir):
    print("pages/ existe")
    print("Contenu de pages :", os.listdir(pages_dir))
    print("'remerciements.py' trouvé ?", "remerciements.py" in os.listdir(pages_dir))
else:
    print("pages/ n'existe pas")
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

axes = {
    "Pertinence stratégique": "Niveau de contribution directe du critère aux objectifs et priorités de l'établissement",
    "Capacité discriminante": "Capacité du critère à distinguer clairement les différentes options",
    "Fiabilité de l’évaluation": "Niveau de fiabilité et facilité d'obtention des données",
    "Acceptabilité politique ou sociale": "Niveau d'acceptabilité et de soutien par les parties prenantes",
    "Temporalité / Durabilité": "Stabilité de l'importance du critère dans le temps"
}

# --- Init session ---
if "page" not in st.session_state:
    st.session_state.page = 0
if "reponses" not in st.session_state:
    st.session_state.reponses = []
if "fin" not in st.session_state:
    st.session_state.fin = False

# --- Fonctions ---
def enregistrer_reponse(notes, critere):
    existing = next((r for r in st.session_state.reponses if r.get("Critère") == critere), None)
    if existing:
        existing.update(notes)
    else:
        notes["Critère"] = critere
        st.session_state.reponses.append(notes)

def sauvegarder_reponses_sqlite():
    df = pd.DataFrame(st.session_state.reponses)
    df["Date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("evaluation.db")
    df.to_sql("evaluations", conn, if_exists="append", index=False)
    conn.close()
    return df

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
        for axe, definition in axes.items():
            st.markdown(f"**{axe}** — *{definition}*")
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

    # 🔹 Bloc récapitulatif
        st.markdown("---")
        st.subheader("📋 Récapitulatif de vos évaluations")
        reponses = st.session_state.get("reponses", [])
        if reponses:
            df = pd.DataFrame(reponses)
            cols = ['Critère'] + [c for c in df.columns if c != 'Critère']
            df = df[cols]
            st.dataframe(df, use_container_width=True)
        else:
            st.write("Aucune réponse enregistrée pour l'instant.")

        def valider_questionnaire():
            # Enregistrer les réponses ouvertes
            st.session_state.reponses.append({
                "Critère": "Autres critères suggérés",
                "Réponse": autre_critere
            })
            st.session_state.reponses.append({
                "Critère": "Commentaires / Remarques",
                "Réponse": commentaires
            })
            # Sauvegarde SQLite
            sauvegarder_reponses_sqlite()
            # Marquer questionnaire comme terminé
            st.session_state.fin = True  # le flag suffit pour afficher la page finale

        st.button("✅ Valider le questionnaire", on_click=valider_questionnaire)

# --- Bloc redirection / message de fin ---
if st.session_state.fin:
    st.title("🎉 Merci de votre participation !")
    st.write("""
    Nous reviendrons vers vous rapidement avec le deuxième tour de l'évaluation, 
    accompagné de la synthèse des résultats du premier tour.
    """)

