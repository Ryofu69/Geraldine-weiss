import os
import streamlit as st

st.set_page_config(
    page_title="Sistema Geraldine Weiss",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- REPARACIÓN AUTOMÁTICA DE ESPACIOS Y CARACTERES ---
hubo_cambios = False

# 1. Asegurar que la carpeta raíz sea exactamente 'pages' sin espacios
for d in os.listdir("."):
    if os.path.isdir(d) and d.strip().lower() == "pages" and d != "pages":
        try:
            os.rename(d, "pages")
            hubo_cambios = True
        except Exception:
            pass

# 2. Normalizar los nombres de los módulos eliminando espacios de emojis
if os.path.exists("pages"):
    for f in os.listdir("pages"):
        ruta_origen = os.path.join("pages", f)
        if "Analizar" in f and f != "1_Analizar_Empresa.py":
            try:
                os.rename(ruta_origen, "pages/1_Analizar_Empresa.py")
                hubo_cambios = True
            except Exception:
                pass
        elif "Radar" in f and f != "2_Radar.py":
            try:
                os.rename(ruta_origen, "pages/2_Radar.py")
                hubo_cambios = True
            except Exception:
                pass
        elif "Cartera" in f and f != "3_Cartera.py":
            try:
                os.rename(ruta_origen, "pages/3_Cartera.py")
                hubo_cambios = True
            except Exception:
                pass

if hubo_cambios:
    st.rerun()

# --- PORTADA Y NAVEGACIÓN ---
st.title("🏛️ Sistema de Inversión DGI")
st.markdown("Bienvenido al panel central de Geraldine Weiss. Selecciona el módulo al que deseas acceder:")
st.divider()

# Botones directos a pantalla completa
try:
    st.page_link("pages/1_Analizar_Empresa.py", label="🔍 1. Analizar Empresa", use_container_width=True)
except Exception:
    st.button("🔍 1. Analizar Empresa (Sincronizando...)", disabled=True, use_container_width=True)
st.caption("Suelo fundamental, canales históricos de Weiss, Chowder y timing técnico MACD.")

st.markdown("<br>", unsafe_allow_html=True)

try:
    st.page_link("pages/2_Radar.py", label="📡 2. Radar Watchlist", use_container_width=True)
except Exception:
    st.button("📡 2. Radar Watchlist (Sincronizando...)", disabled=True, use_container_width=True)
st.caption("Escaneo masivo de múltiples acciones y ordenación automática por nivel de ganga.")

st.markdown("<br>", unsafe_allow_html=True)

try:
    st.page_link("pages/3_Cartera.py", label="💼 3. Mi Cartera Privada", use_container_width=True)
except Exception:
    st.button("💼 3. Mi Cartera Privada (Sincronizando...)", disabled=True, use_container_width=True)
st.caption("Control de dividendos netos, rentabilidad en euros, impacto divisa y bola de nieve.")

st.divider()
st.info("💡 **Navegación táctil:** Pulsa directamente sobre los botones superiores o despliega el menú lateral con la flecha (**>**) en la esquina superior izquierda.")
