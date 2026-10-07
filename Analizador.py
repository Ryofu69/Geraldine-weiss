import os
import streamlit as st

st.set_page_config(
    page_title="Sistema Geraldine Weiss",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================================
# 1. DETECCIÓN AUTOMÁTICA DE ARCHIVOS (ANTI-ERRORES)
# ========================================================
def localizar_modulo(termino_clave):
    """Localiza el archivo sin importar si tiene emojis, espacios o subcarpetas."""
    # Prioridad 1: Buscar en la carpeta pages/
    if os.path.exists("pages"):
        for f in os.listdir("pages"):
            if termino_clave.lower() in f.lower() and f.endswith(".py"):
                return os.path.join("pages", f).replace("\\", "/")
    # Prioridad 2: Rastreo recursivo completo
    for raiz, dirs, archivos in os.walk("."):
        if ".git" not in raiz and not raiz.startswith("./."):
            for f in archivos:
                if termino_clave.lower() in f.lower() and f.endswith(".py") and f not in ["Analizador.py", "Analizador_5A.py"]:
                    return os.path.join(raiz, f).replace("\\", "/")
    return None

ruta_analizar = localizar_modulo("analizar") or localizar_modulo("francotirador")
ruta_radar = localizar_modulo("radar")
ruta_cartera = localizar_modulo("cartera")

# Comprobación de seguridad
archivos_listos = bool(ruta_analizar and ruta_radar and ruta_cartera)

if not archivos_listos:
    st.error("⚠️ No se han encontrado todos los módulos en el repositorio:")
    st.write("🔍 **Analizar Empresa:**", ruta_analizar if ruta_analizar else "❌ No encontrado")
    st.write("📡 **Radar Watchlist:**", ruta_radar if ruta_radar else "❌ No encontrado")
    st.write("💼 **Mi Cartera:**", ruta_cartera if ruta_cartera else "❌ No encontrado")
    st.info("Revisa en GitHub que los tres archivos existan dentro de la carpeta `pages`.")
    st.stop()

# ========================================================
# 2. DEFINICIÓN DE PÁGINAS Y MENÚ NATIVO
# ========================================================
pag_analizar = st.Page(ruta_analizar, title="1. Analizar Empresa", icon="🔍")
pag_radar = st.Page(ruta_radar, title="2. Radar Watchlist", icon="📡")
pag_cartera = st.Page(ruta_cartera, title="3. Mi Cartera Privada", icon="💼")

def vista_portada():
    st.title("🏛️ Sistema de Inversión DGI")
    st.markdown("Bienvenido al panel central de Geraldine Weiss. Selecciona el módulo al que deseas acceder:")
    st.divider()

    st.page_link(pag_analizar, label="1. Analizar Empresa", icon="🔍", use_container_width=True)
    st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")
    st.markdown("<br>", unsafe_allow_html=True)

    st.page_link(pag_radar, label="2. Radar Watchlist", icon="📡", use_container_width=True)
    st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")
    st.markdown("<br>", unsafe_allow_html=True)

    st.page_link(pag_cartera, label="3. Mi Cartera Privada", icon="💼", use_container_width=True)
    st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y bola de nieve.")
    st.divider()
    st.info("💡 **Navegación:** Puedes usar estos botones principales o desplegar el menú lateral tocando la flecha superior izquierda (**>**) para alternar entre herramientas.")

pag_inicio = st.Page(vista_portada, title="Inicio", icon="🏛️", default=True)

# Enrutador nativo de Streamlit
enrutador = st.navigation([pag_inicio, pag_analizar, pag_radar, pag_cartera])
enrutador.run()
