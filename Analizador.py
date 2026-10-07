import os
import streamlit as st

st.set_page_config(
    page_title="Sistema Geraldine Weiss",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Sistema de Inversión DGI")
st.markdown("Bienvenido al panel central de Geraldine Weiss. Selecciona el módulo al que deseas acceder:")
st.divider()

# Detección segura en disco para evitar errores de codificación con emojis
archivos = sorted(os.listdir("pages")) if os.path.exists("pages") else []

p_analizar = next((f"pages/{f}" for f in archivos if "Analizar" in f), None)
p_radar = next((f"pages/{f}" for f in archivos if "Radar" in f), None)
p_cartera = next((f"pages/{f}" for f in archivos if "Cartera" in f), None)

# 1. Analizar Empresa
if p_analizar:
    try:
        st.page_link(p_analizar, label="🔍 1. Analizar Empresa", use_container_width=True)
    except Exception:
        pass
st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")
st.markdown("<br>", unsafe_allow_html=True)

# 2. Radar Watchlist
if p_radar:
    try:
        st.page_link(p_radar, label="📡 2. Radar Watchlist", use_container_width=True)
    except Exception:
        pass
st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")
st.markdown("<br>", unsafe_allow_html=True)

# 3. Mi Cartera Privada
if p_cartera:
    try:
        st.page_link(p_cartera, label="💼 3. Mi Cartera Privada", use_container_width=True)
    except Exception:
        pass
st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y bola de nieve.")

st.divider()
st.info("💡 **Navegación:** Puedes usar estos botones o desplegar el menú lateral de Streamlit tocando la flecha superior izquierda (**>**) para cambiar de módulo en cualquier momento.")
