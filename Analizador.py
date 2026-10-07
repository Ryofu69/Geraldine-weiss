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

# Botones de navegación directa
st.page_link("pages/1_🔍_Analizar_Empresa.py", label="🔍 1. Analizar Empresa", use_container_width=True)
st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/2_📡_Radar.py", label="📡 2. Radar Watchlist", use_container_width=True)
st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")

st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/3_💼_Cartera.py", label="💼 3. Mi Cartera Privada", use_container_width=True)
st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y bola de nieve.")

st.divider()
st.info("💡 **Navegación:** Puedes usar estos botones o desplegar el menú lateral de Streamlit tocando la flecha superior izquierda (**>**) para cambiar de módulo en cualquier momento.")
