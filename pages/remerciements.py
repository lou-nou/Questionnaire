import streamlit as st

st.set_page_config(page_title="Merci 🙏", page_icon="✅", layout="centered")

st.title("🎉 Merci de votre participation !")
st.write("""
Nous reviendrons vers vous rapidement avec **le deuxième tour de l'évaluation**, 
accompagné de la **synthèse des résultats du premier tour**, 
afin de vous permettre de **réajuster votre première évaluation si nécessaire**.
""")

st.success("Vos réponses ont bien été enregistrées.")
st.balloons()
