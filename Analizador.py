import streamlit as st

st.set_page_config(
    page_title="Sistema Geraldine Weiss",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🏛️ Sistema de Inversión DGI")
st.markdown("Selecciona el módulo al que deseas acceder:")

st.divider()

# Botones directos a pantalla completa para móvil
st.page_link("pages/1_🔍_Analizar_Empresa.py", label="🔍 1. Analizar Empresa", icon="🔍", use_container_width=True)
st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/2_📡_Radar.py", label="📡 2. Radar Watchlist", icon="📡", use_container_width=True)
st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/3_💼_Cartera.py", label="💼 3. Mi Cartera Privada", icon="💼", use_container_width=True)
st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y efecto bola de nieve.")

st.divider()
st.info("💡 Consejo para móvil: Puedes volver a este menú en cualquier momento tocando la flecha superior o recargando la página de inicio.")
