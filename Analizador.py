
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN INICIAL DE LA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Geraldine Weiss & Regla de Chowder",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Empresas de ejemplo para selección rápida (EE. UU. y España)
EJEMPLOS_DGI = {
    "Johnson & Johnson (JNJ)": "JNJ",
    "Coca-Cola (KO)": "KO",
    "Procter & Gamble (PG)": "PG",
    "PepsiCo (PEP)": "PEP",
    "AbbVie (ABBV)": "ABBV",
    "Realty Income (O)": "O",
    "Microsoft (MSFT)": "MSFT",
    "Iberdrola (IBE.MC)": "IBE.MC",
    "Inditex (ITX.MC)": "ITX.MC",
    "Enagás (ENG.MC)": "ENG.MC",
    "Redeia (RED.MC)": "RED.MC",
    "Viscofan (VIS.MC)": "VIS.MC",
}

# Inicializar estado de sesión para el ticker activo
if "ticker_activo" not in st.session_state:
    st.session_state.ticker_activo = "JNJ"


def actualizar_desde_ejemplo():
    """Callback para sincronizar el selector de ejemplos rápidos con el ticker activo."""
    seleccion = st.session_state.selector_ejemplo
    if seleccion in EJEMPLOS_DGI:
        st.session_state.ticker_activo = EJEMPLOS_DGI[seleccion]
        st.session_state.input_ticker = EJEMPLOS_DGI[seleccion]


# ==============================================================================
# FUNCIONES DE DESCARGA Y CÁLCULO FINANCIERO
# ==============================================================================
def detectar_frecuencia_pagos(div_events: pd.Series) -> int:
    """
    Detecta de forma robusta cuántos pagos de dividendo realiza la empresa al año
    (1=Anual, 2=Semestral, 3=Cuatrimestral, 4=Trimestral, 12=Mensual).
    Usa la mediana de pagos en años naturales completos y valida con los días entre pagos.
    """
    if div_events.empty:
        return 4

    anio_actual = datetime.today().year
    primer_anio = div_events.index.year.min()

    # Contar pagos únicamente en años naturales completos
    pagos_por_anio = div_events.groupby(div_events.index.year).count()
    anios_completos = pagos_por_anio[
        (pagos_por_anio.index > primer_anio) & (pagos_por_anio.index < anio_actual)
    ]

    if len(anios_completos) >= 2:
        mediana_anual = int(round(float(anios_completos.median())))
        if mediana_anual in (1, 2, 3, 4, 6, 12):
            return mediana_anual
        if mediana_anual > 0:
            return mediana_anual

    # Alternativa: estimar a partir de la mediana de días entre pagos consecutivos
    gaps = div_events.index.to_series().diff().dt.days.dropna()
    gaps_validos = gaps[(gaps > 15) & (gaps < 450)]
    if not gaps_validos.empty:
        mediana_dias = float(gaps_validos.median())
        if mediana_dias <= 45:
            return 12
        elif mediana_dias <= 108:
            return 4
        elif mediana_dias <= 145:
            return 3
        elif mediana_dias <= 250:
            return 2
        else:
            return 1

    return 4


def consolidar_eventos_dividendo(div_series: pd.Series, ventana_dias: int = 7) -> pd.Series:
    """
    Agrupa pagos registrados en fechas separadas por pocos días (ajustes contables o
    dobles registros en Yahoo) para no distorsionar el conteo de los últimos N pagos.
    """
    eventos = div_series[div_series > 0].sort_index()
    if eventos.empty:
        return eventos

    fechas_agrupadas = []
    montos_agrupados = []

    fecha_actual = eventos.index[0]
    monto_actual = float(eventos.iloc[0])

    for fecha, monto in list(eventos.items())[1:]:
        if (fecha - fecha_actual).days <= ventana_dias:
            monto_actual += float(monto)
            fecha_actual = fecha
        else:
            fechas_agrupadas.append(fecha_actual)
            montos_agrupados.append(monto_actual)
            fecha_actual = fecha
            monto_actual = float(monto)

    fechas_agrupadas.append(fecha_actual)
    montos_agrupados.append(monto_actual)

    return pd.Series(montos_agrupados, index=pd.DatetimeIndex(fechas_agrupadas), name="Dividends")


def calcular_dividendo_anualizado_limpio(
    df_precios: pd.DataFrame,
    freq_override: int = 0
) -> tuple[pd.Series, int]:
    """
    Calcula el dividendo anualizado móvil sumando exactamente los últimos N pagos
    (donde N es la frecuencia anual de pago). Esto elimina por completo los picos
    artificiales causados por desplazamientos de 1 a 4 días en las fechas ex-dividendo
    que ocurren al usar ventanas fijas de 365 días.
    """
    div_events = consolidar_eventos_dividendo(df_precios["Dividends"])
    if div_events.empty:
        return pd.Series(np.nan, index=df_precios.index), 0

    freq = freq_override if freq_override > 0 else detectar_frecuencia_pagos(div_events)

    # Suma móvil exacta de los últimos N pagos consecutivos
    ttm_por_evento = div_events.rolling(window=freq, min_periods=freq).sum()

    # Proyectar hacia adelante sobre cada día de cotización
    ttm_diario = ttm_por_evento.reindex(df_precios.index, method="ffill")

    # Control de suspensión de dividendo: si pasan > 420 días sin ningún pago, se anula
    fechas_evento = pd.Series(div_events.index, index=div_events.index)
    ultima_fecha_pago = fechas_evento.reindex(df_precios.index, method="ffill")
    dias_sin_pago = (df_precios.index.to_series() - ultima_fecha_pago).dt.days
    ttm_diario = ttm_diario.where(dias_sin_pago <= 420, np.nan)

    return ttm_diario, freq


def calcular_cagr(valor_final: float, valor_inicial: float, anios: int):
    """Calcula la tasa de crecimiento anual compuesta (CAGR) en porcentaje."""
    if valor_inicial is None or valor_final is None:
        return None
    if valor_inicial <= 0 or valor_final <= 0 or anios <= 0:
        return None
    return ((valor_final / valor_inicial) ** (1.0 / anios) - 1.0) * 100.0


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_datos_yahoo(ticker: str, years: int):
    """
    Descarga precios de cierre SIN ajustar por dividendos (auto_adjust=False)
    desde el 1 de enero de un año suficientemente lejano para calcular tanto
    las bandas históricas como los DGR de 5 y 10 años completos sin distorsiones.
    """
    try:
        hoy = datetime.today()
        anios_necesarios = max(years, 11) + 2
        start_date = datetime(hoy.year - anios_necesarios, 1, 1)

        stock = yf.Ticker(ticker)
        df_full = stock.history(start=start_date, end=hoy + timedelta(days=1), auto_adjust=False)

        if df_full is None or df_full.empty:
            return None, {}

        # Eliminar zona horaria para operar limpiamente con fechas
        if df_full.index.tz is not None:
            df_full.index = df_full.index.tz_localize(None)

        # Limpiar posibles filas sin precio de cierre válido
        df_full = df_full[df_full["Close"].notna() & (df_full["Close"] > 0)].copy()

        try:
            info = stock.info or {}
        except Exception:
            info = {}

        return df_full, info

    except Exception as exc:
        return None, {"_error": str(exc)}


# ==============================================================================
# CABECERA Y SELECTOR DE EMPRESA EN PANTALLA PRINCIPAL (OPTIMIZADO PARA MÓVIL)
# ==============================================================================
st.title("📊 Geraldine Weiss & Regla de Chowder")
st.caption("Valoración DGI con precios históricos **sin ajustar por dividendos** (`auto_adjust=False`).")

# Panel superior siempre visible para elegir empresa y periodo
with st.container(border=True):
    col_busq, col_ej, col_per = st.columns([2, 2, 1])

    with col_busq:
        with st.form(key="form_ticker", border=False):
            c_in, c_btn = st.columns([3, 1.3])
            with c_in:
                ticker_escrito = st.text_input(
                    "Escribe cualquier Ticker (Yahoo Finance)",
                    value=st.session_state.ticker_activo,
                    key="input_ticker",
                    placeholder="Ej: JNJ, KO, IBE.MC, O"
                )
            with c_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                enviar = st.form_submit_button("Analizar", type="primary", use_container_width=True)

            if enviar and ticker_escrito.strip():
                st.session_state.ticker_activo = ticker_escrito.strip().upper()

    with col_ej:
        st.selectbox(
            "O elige una empresa rápida",
            options=["— Seleccionar ejemplo —"] + list(EJEMPLOS_DGI.keys()),
            key="selector_ejemplo",
            on_change=actualizar_desde_ejemplo
        )

    with col_per:
        years = st.selectbox(
            "Periodo (años)",
            options=[5, 7, 10, 15, 20],
            index=2
        )

    # Ajustes avanzados accesibles desde la pantalla principal sin usar sidebar
    with st.expander("⚙️ Ajustes avanzados (franjas, dividendo base, Chowder y gráficos)", expanded=False):
        adv1, adv2, adv3 = st.columns(3)

        with adv1:
            metodo_franjas = st.radio(
                "Extremos de Yield",
                options=["Percentiles (filtra atípicos)", "Mínimo / Máximo absoluto"],
                index=0
            )
            if metodo_franjas.startswith("Percentiles"):
                percentil = st.slider("Recorte en extremos (%)", 1, 15, 5)
            else:
                percentil = 0

            tipo_media = st.radio("Referencia central", ["Media aritmética", "Mediana"], index=0)

        with adv2:
            fuente_dividendo = st.radio(
                "Dividendo anual base (precios objetivo)",
                options=["TTM (últimos N pagos)", "Forward (estimado Yahoo)", "Manual"],
                index=0
            )
            div_manual = None
            if fuente_dividendo == "Manual":
                div_manual = st.number_input(
                    "Dividendo anual manual",
                    min_value=0.0001,
                    value=1.0,
                    step=0.05,
                    format="%.4f"
                )

            freq_opciones = {
                "Automática (recomendada)": 0,
                "Anual (1 pago/año)": 1,
                "Semestral (2 pagos/año)": 2,
                "Cuatrimestral (3 pagos/año)": 3,
                "Trimestral (4 pagos/año)": 4,
                "Mensual (12 pagos/año)": 12,
            }
            freq_seleccionada = st.selectbox(
                "Frecuencia de pagos del dividendo",
                options=list(freq_opciones.keys()),
                index=0
            )
            freq_override = freq_opciones[freq_seleccionada]

        with adv3:
            escala_log = st.checkbox("Escala logarítmica en precio", value=False)
            forzar_defensiva = st.checkbox(
                "Aplicar umbral Chowder defensivo (≥ 8% para Utilities/REITs)",
                value=False,
                help="Se detecta automáticamente por sector, pero puedes forzarlo aquí si Yahoo no informa el sector."
            )

ticker_actual = st.session_state.ticker_activo

# ==============================================================================
# CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
with st.spinner(f"Descargando datos históricos de {ticker_actual} desde Yahoo Finance..."):
    df_full, info = cargar_datos_yahoo(ticker_actual, years)

if df_full is None or df_full.empty:
    detalle_err = info.get("_error", "")
    st.error(
        f"No se pudieron cargar datos para **{ticker_actual}**. "
        "Verifica que el símbolo exista en Yahoo Finance (por ejemplo: `JNJ`, `KO`, `IBE.MC`, `ITX.MC`)."
    )
    if detalle_err:
        st.caption(f"Detalle técnico: {detalle_err}")
    st.stop()

# Calcular dividendo anualizado SIN picos (suma exacta de los últimos N pagos)
df_full["TTM_Div"], freq_usada = calcular_dividendo_anualizado_limpio(df_full, freq_override=freq_override)

if freq_usada == 0 or df_full["TTM_Div"].dropna().empty:
    st.error(
        f"**{ticker_actual}** no tiene suficiente historial de dividendos en Yahoo Finance "
        "para construir las bandas de Geraldine Weiss."
    )
    st.stop()

# Recortar la serie al periodo elegido por el usuario para el análisis de bandas
cutoff_date = datetime.today() - timedelta(days=years * 365)
df = df_full[df_full.index >= cutoff_date].copy()
df = df[(df["Close"] > 0) & (df["TTM_Div"].notna()) & (df["TTM_Div"] > 0)].copy()

if df.empty:
    st.error(f"No hay datos válidos con dividendo activo para **{ticker_actual}** en los últimos {years} años.")
    st.stop()

# Calcular Dividend Yield histórico real (%) sobre cierre SIN ajustar por dividendos
df["Yield"] = (df["TTM_Div"] / df["Close"]) * 100.0

# Metadatos de la empresa
nombre_empresa = info.get("longName") or info.get("shortName") or ticker_actual
moneda = info.get("currency", "")
sector = info.get("sector", "N/D")

# ==============================================================================
# CÁLCULO DE BANDAS DE GERALDINE WEISS
# ==============================================================================
if percentil == 0:
    yield_infra = float(df["Yield"].max())
    yield_sobre = float(df["Yield"].min())
    etiqueta_extremo = "Mín/Máx absoluto"
else:
    yield_infra = float(df["Yield"].quantile(1.0 - percentil / 100.0))
    yield_sobre = float(df["Yield"].quantile(percentil / 100.0))
    etiqueta_extremo = f"P{percentil} / P{100 - percentil}"

yield_medio = float(df["Yield"].mean()) if tipo_media == "Media aritmética" else float(df["Yield"].median())

if yield_sobre <= 0 or yield_medio <= 0 or yield_infra <= 0:
    st.error("Los niveles de Dividend Yield calculados no permiten construir bandas válidas.")
    st.stop()

# Franjas históricas dinámicas
df["Banda_Infra"] = df["TTM_Div"] / (yield_infra / 100.0)
df["Banda_Media"] = df["TTM_Div"] / (yield_medio / 100.0)
df["Banda_Sobre"] = df["TTM_Div"] / (yield_sobre / 100.0)

# Cotización actual y dividendo base seleccionado
precio_actual = float(df["Close"].iloc[-1])
fecha_ultimo_dato = df.index[-1].strftime("%Y-%m-%d")
ttm_actual = float(df["TTM_Div"].iloc[-1])
forward_yahoo = info.get("dividendRate")

if fuente_dividendo == "Manual" and div_manual is not None:
    div_actual = float(div_manual)
    etiqueta_div = "Manual"
elif fuente_dividendo == "Forward (estimado Yahoo)" and forward_yahoo and float(forward_yahoo) > 0:
    div_actual = float(forward_yahoo)
    etiqueta_div = "Forward Yahoo"
else:
    div_actual = ttm_actual
    etiqueta_div = f"TTM ({freq_usada} pagos)"
    if fuente_dividendo == "Forward (estimado Yahoo)":
        st.info("Yahoo no informa dividendo Forward para este ticker; se utiliza el dividendo TTM.")

yield_actual = (div_actual / precio_actual) * 100.0

# Precios objetivo actuales según Geraldine Weiss
precio_infra = div_actual / (yield_infra / 100.0)
precio_medio = div_actual / (yield_medio / 100.0)
precio_sobre = div_actual / (yield_sobre / 100.0)

dist_infra = ((precio_infra - precio_actual) / precio_actual) * 100.0
dist_medio = ((precio_medio - precio_actual) / precio_actual) * 100.0
dist_sobre = ((precio_sobre - precio_actual) / precio_actual) * 100.0

# Diagnóstico Geraldine Weiss
if precio_actual <= precio_infra:
    estado_weiss = "🟢 INFRAVALORADA (Zona de Compra)"
    tipo_alerta_weiss = "success"
elif precio_actual <= precio_medio:
    estado_weiss = "🟡 POR DEBAJO DE LA MEDIA (Atractiva)"
    tipo_alerta_weiss = "info"
elif precio_actual < precio_sobre:
    estado_weiss = "🟠 POR ENCIMA DE LA MEDIA (Esperar)"
    tipo_alerta_weiss = "warning"
else:
    estado_weiss = "🔴 SOBREVALORADA (Precaución / Venta)"
    tipo_alerta_weiss = "error"

# ==============================================================================
# CÁLCULO DE CRECIMIENTO DEL DIVIDENDO (DGR) Y REGLA DE CHOWDER
# ==============================================================================
anio_actual = datetime.today().year
div_por_anio = df_full["Dividends"].groupby(df_full.index.year).sum()
div_por_anio = div_por_anio[div_por_anio > 0]

# Años naturales completos (excluyendo el año actual en curso YTD)
anios_completos = div_por_anio[div_por_anio.index < anio_actual]

dgr_1y = dgr_3y = dgr_5y = dgr_10y = None
ultimo_anio_completo = None

if not anios_completos.empty:
    ultimo_anio_completo = int(anios_completos.index.max())
    div_ultimo = float(anios_completos.loc[ultimo_anio_completo])

    if (ultimo_anio_completo - 1) in anios_completos.index:
        dgr_1y = calcular_cagr(div_ultimo, float(anios_completos.loc[ultimo_anio_completo - 1]), 1)
    if (ultimo_anio_completo - 3) in anios_completos.index:
        dgr_3y = calcular_cagr(div_ultimo, float(anios_completos.loc[ultimo_anio_completo - 3]), 3)
    if (ultimo_anio_completo - 5) in anios_completos.index:
        dgr_5y = calcular_cagr(div_ultimo, float(anios_completos.loc[ultimo_anio_completo - 5]), 5)
    if (ultimo_anio_completo - 10) in anios_completos.index:
        dgr_10y = calcular_cagr(div_ultimo, float(anios_completos.loc[ultimo_anio_completo - 10]), 10)

# Regla de Chowder: Yield Actual (%) + DGR 5 años (%)
# Si no dispone de 5 años completos, usa 3Y o 1Y indicándolo claramente
if dgr_5y is not None:
    dgr_chowder = dgr_5y
    etiqueta_dgr_chowder = f"DGR 5Y ({ultimo_anio_completo - 5}–{ultimo_anio_completo})"
elif dgr_3y is not None:
    dgr_chowder = dgr_3y
    etiqueta_dgr_chowder = f"DGR 3Y ({ultimo_anio_completo - 3}–{ultimo_anio_completo})"
elif dgr_1y is not None:
    dgr_chowder = dgr_1y
    etiqueta_dgr_chowder = f"DGR 1Y ({ultimo_anio_completo - 1}–{ultimo_anio_completo})"
else:
    dgr_chowder = None
    etiqueta_dgr_chowder = "Sin historial suficiente"

chowder_number = (yield_actual + dgr_chowder) if dgr_chowder is not None else None

# Determinar umbral aplicable según la Regla de Chowder
sectores_defensivos = {"Utilities", "Real Estate", "Communication Services"}
es_defensiva = forzar_defensiva or (sector in sectores_defensivos)

if es_defensiva:
    objetivo_chowder = 8.0
    regla_chowder_texto = "≥ 8% (Utility / REIT / Telecom)"
elif yield_actual >= 3.0:
    objetivo_chowder = 12.0
    regla_chowder_texto = "≥ 12% (Yield ≥ 3%)"
else:
    objetivo_chowder = 15.0
    regla_chowder_texto = "≥ 15% (Yield < 3%)"

# ==============================================================================
# PRESENTACIÓN DE RESULTADOS: FICHA Y TARJETAS DE VALORACIÓN WEISS
# ==============================================================================
st.subheader(f"{nombre_empresa} ({ticker_actual})")
st.caption(
    f"Sector: **{sector}** | Moneda: **{moneda}** | "
    f"Frecuencia detectada: **{freq_usada} pagos/año** | "
    f"Dividendo base ({etiqueta_div}): **{div_actual:.4f} {moneda}** | "
    f"Cierre: **{fecha_ultimo_dato}**"
)

getattr(st, tipo_alerta_weiss)(estado_weiss)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        label=f"Precio Actual ({moneda})",
        value=f"{precio_actual:.2f}",
        delta=f"Yield: {yield_actual:.2f}%",
        delta_color="off"
    )
with c2:
    st.metric(
        label=f"🟢 Infravaloración ({yield_infra:.2f}%)",
        value=f"{precio_infra:.2f}",
        delta=f"{dist_infra:+.1f}% vs actual",
        delta_color="off"
    )
with c3:
    st.metric(
        label=f"🟡 Precio Medio ({yield_medio:.2f}%)",
        value=f"{precio_medio:.2f}",
        delta=f"{dist_medio:+.1f}% a media",
        delta_color="normal"
    )
with c4:
    st.metric(
        label=f"🔴 Sobrevaloración ({yield_sobre:.2f}%)",
        value=f"{precio_sobre:.2f}",
        delta=f"{dist_sobre:+.1f}% vs actual",
        delta_color="off"
    )

# Barra de posición en el canal de Weiss
rango_total = precio_sobre - precio_infra
if rango_total > 0:
    posicion_rel = (precio_actual - precio_infra) / rango_total
    posicion_clamped = min(max(posicion_rel, 0.0), 1.0)
    st.markdown(
        f"**Posición en el canal de Weiss ({etiqueta_extremo}):** `{posicion_rel * 100:.1f}%` "
        "*(0% = Infravalorada | 50% ≈ Media | 100% = Sobrevalorada)*"
    )
    st.progress(posicion_clamped)

# ==============================================================================
# SECCIÓN DEDICADA: REGLA DE CHOWDER Y CRECIMIENTO DEL DIVIDENDO (DGR)
# ==============================================================================
st.divider()
st.subheader("📈 Regla de Chowder y Crecimiento del Dividendo")

if chowder_number is not None:
    margen_chowder = chowder_number - objetivo_chowder
    if chowder_number >= objetivo_chowder:
        st.success(
            f"✅ **CUMPLE la Regla de Chowder:** **{chowder_number:.2f}%** "
            f"(objetivo {regla_chowder_texto} | margen: {margen_chowder:+.2f} pp)"
        )
    elif chowder_number >= objetivo_chowder - 2.0:
        st.warning(
            f"⚠️ **CERCA del objetivo de Chowder:** **{chowder_number:.2f}%** "
            f"(objetivo {regla_chowder_texto} | diferencia: {margen_chowder:+.2f} pp)"
        )
    else:
        st.error(
            f"❌ **NO CUMPLE la Regla de Chowder:** **{chowder_number:.2f}%** "
            f"(objetivo {regla_chowder_texto} | diferencia: {margen_chowder:+.2f} pp)"
        )

    ch1, ch2, ch3, ch4 = st.columns(4)
    with ch1:
        st.metric(
            label="Número de Chowder",
            value=f"{chowder_number:.2f}%",
            delta=f"{margen_chowder:+.2f}% vs objetivo",
            delta_color="normal"
        )
    with ch2:
        st.metric(
            label="Dividend Yield Actual",
            value=f"{yield_actual:.2f}%",
            delta="Componente renta",
            delta_color="off"
        )
    with ch3:
        st.metric(
            label=etiqueta_dgr_chowder,
            value=f"{dgr_chowder:+.2f}%",
            delta="Componente crecimiento",
            delta_color="off"
        )
    with ch4:
        st.metric(
            label="Umbral Aplicable",
            value=f"≥ {objetivo_chowder:.0f}%",
            delta=regla_chowder_texto.split("(")[-1].replace(")", ""),
            delta_color="off"
        )

    # Desglose de tasas DGR para evaluar aceleración o desaceleración
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("DGR 1 Año", f"{dgr_1y:+.2f}%" if dgr_1y is not None else "N/D")
    d2.metric("DGR 3 Años", f"{dgr_3y:+.2f}%" if dgr_3y is not None else "N/D")
    d3.metric("DGR 5 Años", f"{dgr_5y:+.2f}%" if dgr_5y is not None else "N/D")
    d4.metric("DGR 10 Años", f"{dgr_10y:+.2f}%" if dgr_10y is not None else "N/D")
else:
    st.info("No hay suficientes años naturales completos de dividendos para calcular la Regla de Chowder.")

# ==============================================================================
# GRÁFICO 1: FRANJAS DE GERALDINE WEISS (SIN PICOS Y SIN SOLAPAMIENTO EN MÓVIL)
# ==============================================================================
st.divider()
st.subheader(f"Franjas de Geraldine Weiss — {ticker_actual} ({years} años)")

# Configuración limpia de barra de herramientas (evita tapar leyenda o título en móvil)
plotly_config = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "hoverClosestCartesian", "hoverCompareCartesian"
    ]
}

fig_precio = go.Figure()

# Banda inferior (Infravaloración)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Infra"],
    mode="lines",
    name=f"Infravaloración ({yield_infra:.2f}%)",
    line=dict(color="#00C853", width=1.8, dash="dot")
))

# Banda media (relleno verde suave entre Infravaloración y Media)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Media"],
    mode="lines",
    name=f"Media ({yield_medio:.2f}%)",
    line=dict(color="#FFAB00", width=1.8, dash="dash"),
    fill="tonexty",
    fillcolor="rgba(0, 200, 83, 0.14)"
))

# Banda superior (relleno rojo suave entre Media y Sobrevaloración)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Sobre"],
    mode="lines",
    name=f"Sobrevaloración ({yield_sobre:.2f}%)",
    line=dict(color="#FF1744", width=1.8, dash="dot"),
    fill="tonexty",
    fillcolor="rgba(255, 23, 68, 0.14)"
))

# Precio de cierre real sin ajustar por dividendos
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Close"],
    mode="lines",
    name="Precio (sin ajustar div.)",
    line=dict(color="#2979FF", width=2.4)
))

fig_precio.update_layout(
    xaxis_title="Fecha",
    yaxis_title=f"Precio ({moneda})",
    yaxis_type="log" if escala_log else "linear",
    hovermode="x unified",
    height=500,
    margin=dict(l=10, r=10, t=20, b=110),
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.20,
        xanchor="center",
        x=0.5,
        font=dict(size=11)
    )
)

st.plotly_chart(fig_precio, use_container_width=True, config=plotly_config)

# ==============================================================================
# GRÁFICO 2: HISTÓRICO DE DIVIDEND YIELD (LIMPIO Y CON LEYENDA INFERIOR)
# ==============================================================================
st.subheader(f"Histórico de Dividend Yield (%) — {ticker_actual}")

fig_yield = go.Figure()

fig_yield.add_trace(go.Scatter(
    x=df.index,
    y=df["Yield"],
    mode="lines",
    name="Yield TTM (%)",
    line=dict(color="#2979FF", width=2.2)
))

# Usar líneas de referencia como trazas evita que los textos se pisen en pantallas pequeñas
x_extremos = [df.index[0], df.index[-1]]

fig_yield.add_trace(go.Scatter(
    x=x_extremos,
    y=[yield_infra, yield_infra],
    mode="lines",
    name=f"Infravaloración ({yield_infra:.2f}%)",
    line=dict(color="#00C853", width=1.6, dash="dot")
))

fig_yield.add_trace(go.Scatter(
    x=x_extremos,
    y=[yield_medio, yield_medio],
    mode="lines",
    name=f"Media ({yield_medio:.2f}%)",
    line=dict(color="#FFAB00", width=1.6, dash="dash")
))

fig_yield.add_trace(go.Scatter(
    x=x_extremos,
    y=[yield_sobre, yield_sobre],
    mode="lines",
    name=f"Sobrevaloración ({yield_sobre:.2f}%)",
    line=dict(color="#FF1744", width=1.6, dash="dot")
))

fig_yield.update_layout(
    xaxis_title="Fecha",
    yaxis_title="Dividend Yield (%)",
    hovermode="x unified",
    height=380,
    margin=dict(l=10, r=10, t=20, b=110),
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.25,
        xanchor="center",
        x=0.5,
        font=dict(size=11)
    )
)

st.plotly_chart(fig_yield, use_container_width=True, config=plotly_config)

# ==============================================================================
# TABLAS RESUMEN Y EXPORTACIÓN
# ==============================================================================
col_tab1, col_tab2 = st.columns(2)

with col_tab1:
    st.subheader("📋 Resumen de Precios Objetivo")
    resumen_df = pd.DataFrame({
        "Zona": [
            "🟢 Infravaloración",
            "🟡 Media Histórica",
            "🔴 Sobrevaloración",
            "🔵 Precio Actual"
        ],
        "Yield (%)": [
            f"{yield_infra:.2f}%",
            f"{yield_medio:.2f}%",
            f"{yield_sobre:.2f}%",
            f"{yield_actual:.2f}%"
        ],
        f"Precio ({moneda})": [
            f"{precio_infra:.2f}",
            f"{precio_medio:.2f}",
            f"{precio_sobre:.2f}",
            f"{precio_actual:.2f}"
        ],
        "Distancia": [
            f"{dist_infra:+.2f}%",
            f"{dist_medio:+.2f}%",
            f"{dist_sobre:+.2f}%",
            "0.00%"
        ]
    })
    st.dataframe(resumen_df, use_container_width=True, hide_index=True)

with col_tab2:
    st.subheader("📅 Historial de Dividendos Anuales")
    div_mostrar = div_por_anio.tail(years + 1)

    tabla_div = pd.DataFrame({
        "Año": div_mostrar.index.astype(str),
        f"Dividendo ({moneda})": div_mostrar.values
    })
    tabla_div["Crecimiento YoY (%)"] = tabla_div[f"Dividendo ({moneda})"].pct_change() * 100.0
    tabla_div.loc[tabla_div["Año"] == str(anio_actual), "Año"] = f"{anio_actual} (YTD)"

    st.dataframe(
        tabla_div.iloc[::-1].style.format({
            f"Dividendo ({moneda})": "{:.4f}",
            "Crecimiento YoY (%)": "{:+.2f}%"
        }, na_rep="—"),
        use_container_width=True,
        hide_index=True
    )

with st.expander("📥 Exportar serie histórica calculada (CSV)"):
    csv_export = df[
        ["Close", "Dividends", "TTM_Div", "Yield", "Banda_Infra", "Banda_Media", "Banda_Sobre"]
    ].to_csv()
    st.download_button(
        label="Descargar CSV con bandas de Weiss",
        data=csv_export,
        file_name=f"weiss_chowder_{ticker_actual}_{years}y.csv",
        mime="text/csv"
    )
