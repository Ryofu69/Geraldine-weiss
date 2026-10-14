import streamlit as st
from pathlib import Path

# Configuración global de la aplicación
st.set_page_config(
    page_title="Sistema Geraldine Weiss & Cartera DGI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# MEMORIA GLOBAL COMPARTIDA ENTRE LAS NUEVAS PESTAÑAS
# ==========================================
st.session_state.setdefault("ticker_activo", "MKC")
st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("capital_activo", 500.0)
st.session_state.setdefault("merma_activa", True)
st.session_state.setdefault("analizar_activo", False)

# Identidad visual y encabezado en la barra lateral
with st.sidebar:
    st.title("📊 Geraldine Weiss")
    st.caption("Estrategia Dividend Yield Theory & DGI")
    
    # Muestra en la barra lateral qué empresa tienes cargada al moverte entre pestañas
    if st.session_state.analizar_activo:
        st.markdown(f"""
        <div style="background: rgba(0, 212, 255, 0.08); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 6px; padding: 8px 12px; margin-top: 8px; font-size: 0.85rem;">
            📌 <strong>Empresa activa:</strong> <span style="color:#00d4ff; font-weight:bold;">{st.session_state.ticker_activo}</span> ({st.session_state.años_activo}A)<br>
            💶 <strong>Orden:</strong> {st.session_state.capital_activo:,.0f} | <strong>IRPF:</strong> {st.session_state.impuesto_activo:.0f}%
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")

# ==========================================
# 1. TUS PÁGINAS ORIGINALES (CONSERVADAS AL 100%)
# ==========================================
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
    ]
}

# ==========================================
# 2. NUEVAS PESTAÑAS MODULARES (WEISS + BOGLE)
# ==========================================
definicion_nuevas_pestañas = [
    ("pages/4_Valoracion_Bogle.py", "1. Valoración, Bogle y Timing", "🎯"),
    ("pages/5_Salud_Financiera.py", "2. Salud Financiera (Gráficos)", "📊"),
    ("pages/6_Chowder_Proyeccion.py", "3. Regla Chowder y YoC 15A", "🥣"),
    ("pages/7_Decalogo_Weiss.py", "4. Decálogo DGI (20 Pts)", "📋"),
]

lista_nuevas = [
    st.Page(ruta, title=titulo, icon=icono)
    for ruta, titulo, icono in definicion_nuevas_pestañas
    if Path(ruta).exists()
]

# Si ya has creado al menos uno de los archivos nuevos, añade la sección al menú lateral
if lista_nuevas:
    paginas["🚀 Analizador Weiss + Bogle"] = lista_nuevas

# ==========================================
# 3. TU CARTERA ORIGINAL (CONSERVADA AL 100%)
# ==========================================
paginas["💼 Mi Cartera"] = [
    st.Page(
        "pages/3_Cartera.py",
        title="Control de Cartera DGI",
        icon="💼"
    ),
]

# Inicializar y ejecutar la navegación
enrutador = st.navigation(paginas)

# Pie de página informativo en la barra lateral
with st.sidebar:
    st.markdown("---")
    st.caption("Conectado a Yahoo Finance • Datos en tiempo real")

enrutador.run()
