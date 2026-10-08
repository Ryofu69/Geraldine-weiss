import streamlit as st

# Configuración global de la aplicación
st.set_page_config(
    page_title="Sistema Geraldine Weiss & Cartera DGI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Identidad visual y encabezado en la barra lateral
with st.sidebar:
    st.title("📊 Geraldine Weiss")
    st.caption("Estrategia Dividend Yield Theory & DGI")
    st.markdown("---")

# Definición del enrutador estructurado por secciones
paginas = {
    "🎯 Análisis Fundamental": [
        st.Page(
            "pages/1_Analizar_Empresa.py",
            title="Análisis de Francotirador",
            icon="🔍",
            default=True
        ),
        st.Page(
            "pages/2_Radar.py",
            title="Screener Múltiple (Radar)",
            icon="📑"
        ),
    ],
    "💼 Mi Cartera": [
        st.Page(
            "pages/3_Cartera.py",
            title="Control de Cartera DGI",
            icon="💼"
        ),
    ]
}

# Inicializar y ejecutar la navegación
enrutador = st.navigation(paginas)

# Pie de página informativo en la barra lateral
with st.sidebar:
    st.markdown("---")
    st.caption("Conectado a Yahoo Finance • Datos en tiempo real")

enrutador.run()
