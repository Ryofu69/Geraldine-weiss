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

st.page_link("pages/1_Analizar_Empresa.py", label="1. Analizar Empresa", icon="🔍", use_container_width=True)
st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/2_Radar.py", label="2. Radar Watchlist", icon="📡", use_container_width=True)
st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/3_Cartera.py", label="3. Mi Cartera Privada", icon="💼", use_container_width=True)
st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y bola de nieve.")

st.divider()
st.info("💡 **Navegación:** Puedes usar estos botones o desplegar el menú lateral tocando la flecha superior izquierda (**>**) para cambiar de módulo.")
