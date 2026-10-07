import streamlit as st

st.set_page_config(
    page_title="Sistema Geraldine Weiss",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Sistema de Inversión DGI — Método Geraldine Weiss")

st.markdown("""
Bienvenido al panel central de valoración y gestión de dividendos crecientes (*Dividend Growth Investing*). 
Esta plataforma automatiza los criterios de calidad y valoración histórica descritos por **Geraldine Weiss** para identificar empresas *Blue Chip* en zona de infravaloración fundamental.
""")

st.divider()

st.subheader("🧭 Módulos Disponibles")
st.markdown("Selecciona la herramienta que necesitas desde el **menú lateral izquierdo**:")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 🔍 1. Analizar Empresa
    * **Canal Histórico de Rendimiento**: Detección de Suelo (Infravaloración) y Techo (Sobrevaloración).
    * **Decálogo Blue Chip**: Score de solvencia, Payout FCF/BPA y consistencia de beneficios.
    * **Lupa de Francotirador**: Análisis de timing técnico (MACD/Volumen) y proyecciones de YoC a 15 años.
    """)

with col2:
    st.markdown("""
    ### 📡 2. Radar Watchlist
    * **Escaneo Masivo**: Rastreo simultáneo de múltiples acciones en tiempo real.
    * **Detección de Gangas**: Tabla clasificada por distancia al Suelo Fundamental.
    * **Exportación Rápida**: Descarga de datos en formato CSV para Google Sheets.
    """)

with col3:
    st.markdown("""
    ### 💼 3. Mi Cartera Privada
    * **Rendimiento Real en Euros (€)**: Desglose entre revalorización de cotización y dividendos netos.
    * **Impacto Divisa**: Ajuste por tipo de cambio histórico en compras internacionales.
    * **Radiografía y Bola de Nieve**: Calendario de cobros mensuales y comparativa YoY.
    """)

st.divider()

st.info("💡 **Rendimiento optimizado:** La aplicación ahora funciona de manera modular. Cada sección carga únicamente los datos que necesita al acceder a ella, reduciendo drásticamente los tiempos de espera.")
