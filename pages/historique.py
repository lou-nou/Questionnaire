# pages/historique.py
import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.graph_objects as go

st.set_page_config(page_title="Historique des réponses", page_icon="📈", layout="wide")

DB_PATH = "evaluation.db"
TABLE = "evaluations"

# 0) Sécurité: base présente ?
if not Path(DB_PATH).exists():
    st.error(f"Base introuvable : {DB_PATH}")
    st.stop()

# 1) Lecture DB
with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql(f"SELECT * FROM {TABLE}", conn)

if df.empty:
    st.info("Aucune donnée pour le moment.")
    st.stop()

# 2) Harmoniser quelques noms
df = df.rename(columns={
    "date_validation": "Date",
    "critere_evaluation": "Axe",
})

# 3) Colonnes méta exactes d’après ton schéma
meta_cols = {
    "id_participant",
    "Date",
    "Axe",
    "Autres critères suggérés",
    "Commentaires / Remarques",
}

# 4) Colonnes critères (tout ce qui n’est pas méta)
critere_cols = [c for c in df.columns if c not in meta_cols]

# 5) Long format → colonnes: Date, Axe, id_participant, Critère, Note
long = df.melt(
    id_vars=[c for c in ["Date", "Axe", "id_participant"] if c in df.columns],
    value_vars=critere_cols,
    var_name="Critère",
    value_name="Note",
)

# 6) Nettoyage / types
long["Note"] = pd.to_numeric(long["Note"], errors="coerce")
long = long.dropna(subset=["Note"])
if "Date" in long.columns:
    long["Date"] = pd.to_datetime(long["Date"], errors="coerce")

# 7) Stats par Critère et par Axe (avec Médiane)
stats_crit = (
    long.groupby("Critère", as_index=False)["Note"]
        .agg(N="count", Moyenne="mean", Médiane="median", ÉcartType="std", Min="min", Max="max")
        .sort_values("Moyenne", ascending=False)
)

stats_axes = (
    long.groupby("Axe", as_index=False)["Note"]
        .agg(N="count", Moyenne="mean", Médiane="median", ÉcartType="std", Min="min", Max="max")
        .sort_values("Moyenne", ascending=False)
)

# 8) UI
st.title("📈 Historique des réponses")
col_top1, col_top2 = st.columns(2)
with col_top1:
    st.subheader("Métrique à visualiser")
    metric = st.selectbox("Choisir la métrique pour les radars", ["Moyenne", "Médiane"], index=0)
with col_top2:
    lock_range = st.checkbox("Fixer l’échelle 1–10", value=True)

# 9) Radar Critères
st.subheader(f"Radar par **critère** ({metric})")
if not stats_crit.empty:
    r_vals = stats_crit[metric].tolist()
    theta_vals = stats_crit["Critère"].tolist()
    fig_crit = go.Figure()
    fig_crit.add_trace(go.Scatterpolar(
        r=r_vals, theta=theta_vals,
        fill='toself', name=metric, hovertemplate="%{theta}<br>"+metric+"=%{r:.2f}<extra></extra>"
    ))
    fig_crit.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
        polar=dict(radialaxis=dict(visible=True, range=[1,10] if lock_range else None)),
        showlegend=False,
        title=f"Métrique : {metric}"
    )
    st.plotly_chart(fig_crit, use_container_width=True)
else:
    st.info("Pas de données critère.")

# 10) Radar Axes
st.subheader(f"Radar par **axe** ({metric})")
if "Axe" in long.columns and not stats_axes.empty:
    r_vals = stats_axes[metric].tolist()
    theta_vals = stats_axes["Axe"].tolist()
    fig_axes = go.Figure()
    fig_axes.add_trace(go.Scatterpolar(
        r=r_vals, theta=theta_vals,
        fill='toself', name=metric, hovertemplate="%{theta}<br>"+metric+"=%{r:.2f}<extra></extra>"
    ))
    fig_axes.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
        polar=dict(radialaxis=dict(visible=True, range=[1,10] if lock_range else None)),
        showlegend=False,
        title=f"Métrique : {metric}"
    )
    st.plotly_chart(fig_axes, use_container_width=True)
else:
    st.info("Pas de données axe.")

# 11) Tables détaillées
st.subheader("📋 Statistiques détaillées")
tabs = st.tabs(["Par critère", "Par axe", "Brut (5 dernières lignes)"])
with tabs[0]:
    st.dataframe(stats_crit, use_container_width=True)
with tabs[1]:
    st.dataframe(stats_axes, use_container_width=True)
with tabs[2]:
    st.dataframe(df.tail(5), use_container_width=True)
