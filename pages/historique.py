import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Historique des réponses", page_icon="📂", layout="wide")

st.title("📂 Historique et statistiques des évaluations")

# Charger la base
conn = sqlite3.connect("evaluation.db")
df = pd.read_sql("SELECT * FROM evaluations", conn)
conn.close()

if df.empty:
    st.warning("Aucune donnée enregistrée pour le moment.")
    st.stop()

# # Affichage brut
# st.subheader("📋 Données enregistrées")
# st.dataframe(df, use_container_width=True)

# Stats descriptives
st.subheader("📊 Statistiques descriptives")
stats = df.drop(columns=["Date"], errors="ignore").groupby("Critère").agg(
    Moyenne=pd.NamedAgg(column="Pertinence stratégique", aggfunc="mean")
)

# Pour chaque axe, calculer stats
axes = [c for c in df.columns if c not in ["Critère", "Date", "Réponse"]]
summary = {}
for axe in axes:
    grouped = df.groupby("Critère")[axe].agg([
        "mean", "std", "median", 
        lambda x: np.percentile(x, 25), 
        lambda x: np.percentile(x, 75)
    ])
    grouped.columns = ["Moyenne", "Écart-type", "Médiane", "P25", "P75"]
    summary[axe] = grouped

# Affichage des stats
for axe, table in summary.items():
    st.markdown(f"### 🔎 {axe}")
    st.dataframe(table.round(2), use_container_width=True)

# Radar

import numpy as np
import matplotlib.pyplot as plt

st.subheader("📈 Visualisation radar")
criteres = df["Critère"].unique()
axes_eval = [a for a in df.columns if a not in ["Critère", "Date", "Réponse"]]

if axes_eval:
    mean_values = df.groupby("Critère")[axes_eval].mean()

    for critere in mean_values.index:
        values = mean_values.loc[critere].values.flatten().tolist()
        values += values[:1]  # fermeture du polygone

        # angles pour chaque axe original
        angles = np.linspace(0, 2*np.pi, len(axes_eval), endpoint=False)
        angles = np.concatenate((angles, [angles[0]]))  # fermeture

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.plot(angles, values, linewidth=2, label=critere)
        ax.fill(angles, values, alpha=0.25)

        # ticks : seulement sur les axes originaux, pas le point répété
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(axes_eval)

        ax.set_title(f"Radar des notes pour {critere}")
        ax.legend(loc="upper right", bbox_to_anchor=(1.1, 1.1))
        st.pyplot(fig)

st.info("💡 Les graphiques et statistiques vous permettent de comparer les critères et d'identifier les points forts et faibles.")
