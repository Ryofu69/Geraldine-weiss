
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES (ADAPTATIVOS MÓVIL / ESCRITORIO)
# ==============================================================================
st.set_page_config(
    page_title="Geraldine Weiss & Chowder",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CUSTOM_CSS = """
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
    max-width: 1120px;
}
.weiss-header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.75rem;
}
.weiss-title {
    font-size: 1.45rem;
    font-weight: 700;
    margin: 0;
    line-height: 1.2;
}
.weiss-meta {
    font-size: 0.82rem;
    opacity: 0.74;
    margin-top: 4px;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 13px;
    border-radius: 999px;
    font-size: 0.83rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.pill-green { background: rgba(16, 185, 129, 0.15); color: #10B981; border-color: rgba(16, 185, 129, 0.35); }
.pill-blue  { background: rgba(56, 189, 248, 0.15); color: #38BDF8; border-color: rgba(56, 189, 248, 0.35); }
.pill-amber { background: rgba(245, 158, 11, 0.15); color: #F59E0B; border-color: rgba(245, 158, 11, 0.35); }
.pill-red   { background: rgba(239, 68, 68, 0.15);  color: #EF4444; border-color: rgba(239, 68, 68, 0.35); }

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin: 0.6rem 0 1rem 0;
}
@media (min-width: 768px) {
    .kpi-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
    }
}
.kpi-card {
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-top: 3px solid rgba(148, 163, 184, 0.45);
    border-radius: 12px;
    padding: 12px 13px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.kpi-card.accent-blue  { border-top-color: #38BDF8; }
.kpi-card.accent-green { border-top-color: #10B981; }
.kpi-card.accent-amber { border-top-color: #F59E0B; }
.kpi-card.accent-red   { border-top-color: #EF4444; }
.kpi-card.accent-slate { border-top-color: #94A3B8; }

.kpi-label {
    font-size: 0.75rem;
    font-weight: 600;
    opacity: 0.72;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 1.42rem;
    font-weight: 700;
    line-height: 1.15;
    margin-bottom: 4px;
}
.kpi-sub {
    font-size: 0.78rem;
    opacity: 0.78;
}
.kpi-sub.pos { color: #10B981; opacity: 1; font-weight: 600; }
.kpi-sub.neg { color: #EF4444; opacity: 1; font-weight: 600; }

.gauge-box {
    background: rgba(148, 163, 184, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 12px;
    padding: 13px 15px;
    margin: 0.4rem 0 1.2rem 0;
}
.gauge-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.82rem;
    margin-bottom: 10px;
}
.gauge-track {
    position: relative;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(90deg, #10B981 0%, #F59E0B 50%, #EF4444 100%);
}
.gauge-marker {
    position: absolute;
    top: 50%;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #FFFFFF;
    border: 3px solid #0F172A;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85), 0 2px 6px rgba(0, 0, 0, 0.45);
    transform: translate(-50%, -50%);
}
.gauge-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.73rem;
    opacity: 0.72;
    margin-top: 8px;
}
.section-caption {
    font-size: 0.82rem;
    opacity: 0.72;
    margin-top: -8px;
    margin-bottom: 10px;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Empresas de ejemplo para selección rápida
EJEMPLOS_DGI = {
    "McCormick (MKC)": "MKC",
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
    "Viscofan (VIS.MC)": "VIS.MC",
}

if "ticker_activo" not in st.session_state:
    st.session_state.ticker_activo = "MKC"


def actualizar_desde_ejemplo():
    seleccion = st.session_state.selector_ejemplo
    if seleccion in EJEMPLOS_DGI:
        st.session_state.ticker_activo = EJEMPLOS_DGI[seleccion]
        st.session_state.input_ticker = EJEMPLOS_DGI[seleccion]


# ==============================================================================
# FUNCIONES DE DESCARGA Y CÁLCULO FINANCIERO
# ==============================================================================
def consolidar_eventos_dividendo(div_series: pd.Series, ventana_dias: int = 7) -> pd.Series:
    """Agrupa registros duplicados o contiguos en menos de 7 días."""
    eventos = div_series[div_series > 0].sort_index()
    if eventos.empty:
        return eventos

    fechas, montos = [], []
    f_act = eventos.index[0]
    m_act = float(eventos.iloc[0])

    for fecha, monto in list(eventos.items())[1:]:
        if (fecha - f_act).days <= ventana_dias:
            m_act += float(monto)
            f_act = fecha
        else:
            fechas.append(f_act)
            montos.append(m_act)
            f_act = fecha
            m_act = float(monto)

    fechas.append(f_act)
    montos.append(m_act)
    return pd.Series(montos, index=pd.DatetimeIndex(fechas), name="Dividends")


def detectar_frecuencia_pagos(div_events: pd.Series) -> int:
    """Detecta cuántos pagos regulares realiza la empresa al año (1, 2, 3, 4, 6 o 12)."""
    if div_events.empty:
        return 4

    anio_actual = datetime.today().year
    primer_anio = div_events.index.year.min()
    pagos_por_anio = div_events.groupby(div_events.index.year).count()
    completos = pagos_por_anio[
        (pagos_por_anio.index > primer_anio) & (pagos_por_anio.index < anio_actual)
    ]

    if len(completos) >= 2:
        mediana = int(round(float(completos.median())))
        if mediana in (1, 2, 3, 4, 6, 12):
            return mediana
        if mediana > 0:
            return mediana

    gaps = div_events.index.to_series().diff().dt.days.dropna()
    gaps = gaps[(gaps > 15) & (gaps < 450)]
    if not gaps.empty:
        d = float(gaps.median())
        if d <= 45:
            return 12
        if d <= 108:
            return 4
        if d <= 145:
            return 3
        if d <= 250:
            return 2
        return 1
    return 4


def detectar_pagos_uniformes(div_events: pd.Series, freq: int) -> bool:
    """
    Determina si la empresa paga importes iguales en cada periodo hasta su subida anual
    (ej. EE. UU.: MKC, JNJ, KO) o pagos desiguales alternantes (ej. Europa: a cuenta y
    complementario como IBE.MC o ITX.MC).
    """
    if freq <= 1 or len(div_events) < freq * 2:
        return True

    recientes = div_events.tail(min(len(div_events), freq * 5))
    cambios = recientes.pct_change().dropna()
    if cambios.empty:
        return True

    # Contar alternancias claras de subida/bajada fuertes (> 12% en sentido contrario)
    caidas_fuertes = (cambios < -0.12).sum()
    subidas_fuertes = (cambios > 0.12).sum()
    if caidas_fuertes >= 2 and subidas_fuertes >= 2 and (caidas_fuertes / len(cambios)) >= 0.20:
        return False

    return True


def filtrar_dividendos_extraordinarios(div_events: pd.Series) -> pd.Series:
    """
    Evita que un dividendo extraordinario aislado (pago puntual muy superior seguido de
    vuelta al importe regular) genere un pico falso al multiplicar por la frecuencia.
    """
    if len(div_events) < 3:
        return div_events.copy()

    limpios = div_events.copy()
    valores = div_events.values

    for i in range(1, len(valores) - 1):
        prev_v = valores[i - 1]
        curr_v = valores[i]
        next_v = valores[i + 1]
        # Si el pago actual es >55% mayor que el anterior y el siguiente vuelve cerca del anterior
        if prev_v > 0 and curr_v > prev_v * 1.55 and next_v < curr_v * 0.75:
            limpios.iloc[i] = prev_v

    return limpios


def calcular_dividendo_weiss(
    df_precios: pd.DataFrame,
    modo_calculo: str = "auto",
    freq_override: int = 0
) -> tuple[pd.Series, int, str]:
    """
    Calcula la serie diaria de dividendo anualizado:
    - 'weiss_clasico': Dividendo Anual Indicado (último pago regular * frecuencia).
      Produce franjas horizontales exactas desde un aumento de dividendo hasta el siguiente.
    - 'ttm': Suma móvil de los últimos N pagos (recomendado en pagos desiguales).
    - 'auto': Usa Weiss clásico en pagos uniformes y TTM en pagos desiguales.
    """
    div_events = consolidar_eventos_dividendo(df_precios["Dividends"])
    if div_events.empty:
        return pd.Series(np.nan, index=df_precios.index), 0, "N/D"

    freq = freq_override if freq_override > 0 else detectar_frecuencia_pagos(div_events)
    uniforme = detectar_pagos_uniformes(div_events, freq)

    if modo_calculo == "auto":
        modo_efectivo = "weiss_clasico" if uniforme else "ttm"
    else:
        modo_efectivo = modo_calculo

    if modo_efectivo == "weiss_clasico":
        eventos_reg = filtrar_dividendos_extraordinarios(div_events)
        div_anual_evento = eventos_reg * freq
        etiqueta_modo = "Escalón clásico Weiss (Dividendo indicado)"
    else:
        div_anual_evento = div_events.rolling(window=freq, min_periods=freq).sum()
        etiqueta_modo = f"TTM móvil (últimos {freq} pagos)"

    serie_diaria = div_anual_evento.reindex(df_precios.index, method="ffill")

    # Anular si la empresa lleva > 420 días sin pagar dividendo
    fechas_ev = pd.Series(div_events.index, index=div_events.index)
    ultima_fecha = fechas_ev.reindex(df_precios.index, method="ffill")
    dias_sin_pago = (df_precios.index.to_series() - ultima_fecha).dt.days
    serie_diaria = serie_diaria.where(dias_sin_pago <= 420, np.nan)

    return serie_diaria, freq, etiqueta_modo


def calcular_cagr(valor_final: float, valor_inicial: float, anios: int):
    if valor_inicial is None or valor_final is None:
        return None
    if valor_inicial <= 0 or valor_final <= 0 or anios <= 0:
        return None
    return ((valor_final / valor_inicial) ** (1.0 / anios) - 1.0) * 100.0


def render_kpi_grid(cards: list[dict]):
    """Renderiza una cuadrícula limpia 2x2 en móvil y 4x1 en escritorio."""
    html_cards = []
    for c in cards:
        accent = c.get("accent", "slate")
        sub_cls = c.get("sub_class", "")
        html_cards.append(
            f'<div class="kpi-card accent-{accent}">'
            f'<div class="kpi-label">{c["label"]}</div>'
            f'<div class="kpi-value">{c["value"]}</div>'
            f'<div class="kpi-sub {sub_cls}">{c.get("sub", "")}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(html_cards)}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_datos_yahoo(ticker: str, years: int):
    """Descarga precios de cierre SIN ajustar por dividendos (auto_adjust=False)."""
    try:
        hoy = datetime.today()
        anios_necesarios = max(years, 11) + 2
        start_date = datetime(hoy.year - anios_necesarios, 1, 1)

        stock = yf.Ticker(ticker)
        df_full = stock.history(start=start_date, end=hoy + timedelta(days=1), auto_adjust=False)

        if df_full is None or df_full.empty:
            return None, {}

        if df_full.index.tz is not None:
            df_full.index = df_full.index.tz_localize(None)

        df_full = df_full[df_full["Close"].notna() & (df_full["Close"] > 0)].copy()

        try:
            info = stock.info or {}
        except Exception:
            info = {}

        return df_full, info
    except Exception as exc:
        return None, {"_error": str(exc)}


# ==============================================================================
# BARRA SUPERIOR DE SELECCIÓN DE EMPRESA (COMPACTA Y ACCESIBLE EN MÓVIL)
# ==============================================================================
st.markdown("### 📊 Analizador Geraldine Weiss & Regla de Chowder")

with st.container(border=True):
    col_busq, col_ej, col_per = st.columns([2.2, 2.0, 1.0])

    with col_busq:
        with st.form(key="form_ticker", border=False):
            c_in, c_btn = st.columns([3, 1.3])
            with c_in:
                ticker_escrito = st.text_input(
                    "Ticker (Yahoo Finance)",
                    value=st.session_state.ticker_activo,
                    key="input_ticker",
                    placeholder="MKC, JNJ, KO, IBE.MC..."
                )
            with c_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                enviar = st.form_submit_button("Analizar", type="primary", use_container_width=True)

            if enviar and ticker_escrito.strip():
                st.session_state.ticker_activo = ticker_escrito.strip().upper()

    with col_ej:
        st.selectbox(
            "Acceso rápido DGI",
            options=["— Elegir empresa —"] + list(EJEMPLOS_DGI.keys()),
            key="selector_ejemplo",
            on_change=actualizar_desde_ejemplo
        )

    with col_per:
        years = st.selectbox("Periodo", options=[5, 7, 10, 15, 20], index=2, format_func=lambda x: f"{x} años")

    with st.expander("⚙️ Ajustes de cálculo (método Weiss, franjas y dividendo)", expanded=False):
        a1, a2, a3 = st.columns(3)
        with a1:
            opciones_modo = {
                "Automático (Weiss clásico / TTM)": "auto",
                "Escalón clásico Weiss (Pago × Frec.)": "weiss_clasico",
                "TTM móvil (Últimos N pagos)": "ttm",
            }
            modo_sel = st.selectbox("Construcción de franjas", list(opciones_modo.keys()), index=0)
            modo_calculo = opciones_modo[modo_sel]

            metodo_franjas = st.radio(
                "Extremos de Yield",
                options=["Percentiles (filtra atípicos)", "Mínimo / Máximo absoluto"],
                index=0
            )
            percentil = st.slider("Recorte en extremos (%)", 1, 15, 5) if metodo_franjas.startswith("Percentiles") else 0

        with a2:
            tipo_media = st.radio("Referencia central", ["Media aritmética", "Mediana"], index=0)

            fuente_dividendo = st.radio(
                "Dividendo anual actual",
                options=["Según franja (Indicado / TTM)", "Forward (Yahoo)", "Manual"],
                index=0
            )
            div_manual = None
            if fuente_dividendo == "Manual":
                div_manual = st.number_input("Dividendo anual manual", min_value=0.0001, value=1.0, step=0.05, format="%.4f")

        with a3:
            freq_opciones = {
                "Automática": 0,
                "Anual (1/año)": 1,
                "Semestral (2/año)": 2,
                "Cuatrimestral (3/año)": 3,
                "Trimestral (4/año)": 4,
                "Mensual (12/año)": 12,
            }
            freq_override = freq_opciones[st.selectbox("Frecuencia de pagos", list(freq_opciones.keys()), index=0)]
            escala_log = st.checkbox("Escala logarítmica en precio", value=False)
            forzar_defensiva = st.checkbox("Umbral Chowder defensivo (≥ 8%)", value=False)

ticker_actual = st.session_state.ticker_activo

# ==============================================================================
# CARGA Y CÁLCULOS PRINCIPALES
# ==============================================================================
with st.spinner(f"Analizando {ticker_actual}..."):
    df_full, info = cargar_datos_yahoo(ticker_actual, years)

if df_full is None or df_full.empty:
    st.error(f"No se encontraron datos para **{ticker_actual}** en Yahoo Finance.")
    if info.get("_error"):
        st.caption(f"Detalle: {info['_error']}")
    st.stop()

df_full["Div_Anual"], freq_usada, etiqueta_modo = calcular_dividendo_weiss(
    df_full, modo_calculo=modo_calculo, freq_override=freq_override
)

if freq_usada == 0 or df_full["Div_Anual"].dropna().empty:
    st.error(f"**{ticker_actual}** no cuenta con suficiente historial de dividendos para aplicar Geraldine Weiss.")
    st.stop()

cutoff_date = datetime.today() - timedelta(days=years * 365)
df = df_full[df_full.index >= cutoff_date].copy()
df = df[(df["Close"] > 0) & (df["Div_Anual"].notna()) & (df["Div_Anual"] > 0)].copy()

if df.empty:
    st.error(f"No hay datos válidos de dividendo para **{ticker_actual}** en los últimos {years} años.")
    st.stop()

# Dividend Yield histórico real sobre cierre SIN ajustar por dividendos
df["Yield"] = (df["Div_Anual"] / df["Close"]) * 100.0

nombre_empresa = info.get("longName") or info.get("shortName") or ticker_actual
moneda = info.get("currency", "")
sector = info.get("sector", "N/D")

# Bandas de Yield de Geraldine Weiss
if percentil == 0:
    yield_infra = float(df["Yield"].max())
    yield_sobre = float(df["Yield"].min())
    etiqueta_extremo = "Mín/Máx absoluto"
else:
    yield_infra = float(df["Yield"].quantile(1.0 - percentil / 100.0))
    yield_sobre = float(df["Yield"].quantile(percentil / 100.0))
    etiqueta_extremo = f"P{percentil}–P{100 - percentil}"

yield_medio = float(df["Yield"].mean()) if tipo_media == "Media aritmética" else float(df["Yield"].median())

if yield_sobre <= 0 or yield_medio <= 0 or yield_infra <= 0:
    st.error("Los valores de Dividend Yield no permiten generar bandas válidas.")
    st.stop()

# Franjas históricas sobre el precio (escalones limpios de dividendo a dividendo)
df["Banda_Infra"] = df["Div_Anual"] / (yield_infra / 100.0)
df["Banda_Media"] = df["Div_Anual"] / (yield_medio / 100.0)
df["Banda_Sobre"] = df["Div_Anual"] / (yield_sobre / 100.0)

precio_actual = float(df["Close"].iloc[-1])
fecha_ultimo = df.index[-1].strftime("%d/%m/%Y")
div_serie_actual = float(df["Div_Anual"].iloc[-1])
forward_yahoo = info.get("dividendRate")

if fuente_dividendo == "Manual" and div_manual is not None:
    div_actual = float(div_manual)
    etiqueta_div = "Manual"
elif fuente_dividendo == "Forward (Yahoo)" and forward_yahoo and float(forward_yahoo) > 0:
    div_actual = float(forward_yahoo)
    etiqueta_div = "Forward Yahoo"
else:
    div_actual = div_serie_actual
    etiqueta_div = "Indicado" if "Escalón" in etiqueta_modo else f"TTM ({freq_usada}p)"

yield_actual = (div_actual / precio_actual) * 100.0

precio_infra = div_actual / (yield_infra / 100.0)
precio_medio = div_actual / (yield_medio / 100.0)
precio_sobre = div_actual / (yield_sobre / 100.0)

dist_infra = ((precio_infra - precio_actual) / precio_actual) * 100.0
dist_medio = ((precio_medio - precio_actual) / precio_actual) * 100.0
dist_sobre = ((precio_sobre - precio_actual) / precio_actual) * 100.0

# Diagnóstico de estado Weiss
if precio_actual <= precio_infra:
    badge_weiss = ("🟢 Infravalorada · Zona de Compra", "pill-green")
elif precio_actual <= precio_medio:
    badge_weiss = ("🔵 Por debajo de la Media · Atractiva", "pill-blue")
elif precio_actual < precio_sobre:
    badge_weiss = ("🟠 Por encima de la Media · Esperar", "pill-amber")
else:
    badge_weiss = ("🔴 Sobrevalorada · Precaución", "pill-red")

# ==============================================================================
# CÁLCULO DE DGR Y REGLA DE CHOWDER
# ==============================================================================
anio_actual = datetime.today().year
div_por_anio = df_full["Dividends"].groupby(df_full.index.year).sum()
div_por_anio = div_por_anio[div_por_anio > 0]
anios_completos = div_por_anio[div_por_anio.index < anio_actual]

dgr_1y = dgr_3y = dgr_5y = dgr_10y = None
ultimo_anio = None

if not anios_completos.empty:
    ultimo_anio = int(anios_completos.index.max())
    div_ult = float(anios_completos.loc[ultimo_anio])
    if (ultimo_anio - 1) in anios_completos.index:
        dgr_1y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 1]), 1)
    if (ultimo_anio - 3) in anios_completos.index:
        dgr_3y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 3]), 3)
    if (ultimo_anio - 5) in anios_completos.index:
        dgr_5y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 5]), 5)
    if (ultimo_anio - 10) in anios_completos.index:
        dgr_10y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 10]), 10)

if dgr_5y is not None:
    dgr_chowder = dgr_5y
    etiqueta_dgr = f"DGR 5Y ({ultimo_anio - 5}–{ultimo_anio})"
elif dgr_3y is not None:
    dgr_chowder = dgr_3y
    etiqueta_dgr = f"DGR 3Y ({ultimo_anio - 3}–{ultimo_anio})"
elif dgr_1y is not None:
    dgr_chowder = dgr_1y
    etiqueta_dgr = f"DGR 1Y ({ultimo_anio - 1}–{ultimo_anio})"
else:
    dgr_chowder = None
    etiqueta_dgr = "Sin historial"

chowder_val = (yield_actual + dgr_chowder) if dgr_chowder is not None else None

sectores_defensivos = {"Utilities", "Real Estate", "Communication Services"}
es_defensiva = forzar_defensiva or (sector in sectores_defensivos)
if es_defensiva:
    objetivo_chowder = 8.0
    regla_texto = "Utility / REIT / Telecom"
elif yield_actual >= 3.0:
    objetivo_chowder = 12.0
    regla_texto = "Yield ≥ 3%"
else:
    objetivo_chowder = 15.0
    regla_texto = "Yield < 3%"

# ==============================================================================
# CABECERA DE LA EMPRESA ANALIZADA
# ==============================================================================
sufijo_moneda = f" {moneda}" if moneda else ""

header_html = (
    '<div class="weiss-header">'
    '<div>'
    f'<div class="weiss-title">{nombre_empresa} <span style="opacity:0.65;font-weight:500;">({ticker_actual})</span></div>'
    f'<div class="weiss-meta">{sector} · Dividendo {etiqueta_div}: <b>{div_actual:.3f}{sufijo_moneda}</b> · '
    f'{freq_usada} pagos/año · Cierre: {fecha_ultimo}</div>'
    '</div>'
    f'<span class="status-pill {badge_weiss[1]}">{badge_weiss[0]}</span>'
    '</div>'
)
st.markdown(header_html, unsafe_allow_html=True)

# ==============================================================================
# PESTAÑAS ORGANIZADAS (CERO SCROLL INFINITO EN MÓVIL)
# ==============================================================================
tab_weiss, tab_chowder, tab_datos = st.tabs([
    "📈 Valoración Weiss",
    "🧮 Regla de Chowder",
    "📋 Tablas y CSV"
])

plotly_config = {
    "displaylogo": False,
    "displayModeBar": False,
    "responsive": True
}

# ------------------------------------------------------------------------------
# PESTAÑA 1: VALORACIÓN GERALDINE WEISS
# ------------------------------------------------------------------------------
with tab_weiss:
    render_kpi_grid([
        {
            "label": "Precio Actual",
            "value": f"{precio_actual:.2f}{sufijo_moneda}",
            "sub": f"Yield actual: {yield_actual:.2f}%",
            "accent": "blue"
        },
        {
            "label": f"Infravaloración ({yield_infra:.2f}%)",
            "value": f"{precio_infra:.2f}{sufijo_moneda}",
            "sub": f"{dist_infra:+.1f}% vs actual",
            "sub_class": "pos" if dist_infra >= 0 else "",
            "accent": "green"
        },
        {
            "label": f"Valoración Media ({yield_medio:.2f}%)",
            "value": f"{precio_medio:.2f}{sufijo_moneda}",
            "sub": f"{dist_medio:+.1f}% potencial",
            "sub_class": "pos" if dist_medio >= 0 else "neg",
            "accent": "amber"
        },
        {
            "label": f"Sobrevaloración ({yield_sobre:.2f}%)",
            "value": f"{precio_sobre:.2f}{sufijo_moneda}",
            "sub": f"{dist_sobre:+.1f}% vs actual",
            "accent": "red"
        },
    ])

    # Barra visual de posición en el canal de Weiss
    rango_total = precio_sobre - precio_infra
    if rango_total > 0:
        pos_rel = (precio_actual - precio_infra) / rango_total
        pos_pct = min(max(pos_rel * 100.0, 0.0), 100.0)
        gauge_html = (
            '<div class="gauge-box">'
            '<div class="gauge-top">'
            f'<span><b>Posición en el canal de Weiss</b> <span style="opacity:0.68;">({etiqueta_extremo})</span></span>'
            f'<span><b>{pos_rel * 100:.1f}%</b></span>'
            '</div>'
            '<div class="gauge-track">'
            f'<div class="gauge-marker" style="left:{pos_pct:.1f}%;"></div>'
            '</div>'
            '<div class="gauge-labels">'
            f'<span>Infravalorada ({precio_infra:.2f})</span>'
            f'<span>Media ({precio_medio:.2f})</span>'
            f'<span>Sobrevalorada ({precio_sobre:.2f})</span>'
            '</div>'
            '</div>'
        )
        st.markdown(gauge_html, unsafe_allow_html=True)

    # GRÁFICO 1: FRANJAS DE GERALDINE WEISS (ESCALONES HORIZONTALES LIMPIOS)
    st.markdown(f"#### Franjas de Geraldine Weiss ({years} años)")
    st.markdown(
        f'<div class="section-caption">Método activo: <b>{etiqueta_modo}</b> · Precio de cierre sin ajustar por dividendos.</div>',
        unsafe_allow_html=True
    )

    fig_precio = go.Figure()

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Infra"],
        mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#10B981", width=1.8, shape="hv"),
        hovertemplate="%{y:.2f}"
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Media"],
        mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#F59E0B", width=1.7, dash="dash", shape="hv"),
        fill="tonexty",
        fillcolor="rgba(16, 185, 129, 0.14)",
        hovertemplate="%{y:.2f}"
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Sobre"],
        mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#EF4444", width=1.8, shape="hv"),
        fill="tonexty",
        fillcolor="rgba(239, 68, 68, 0.13)",
        hovertemplate="%{y:.2f}"
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        name="Precio (sin ajustar)",
        line=dict(color="#38BDF8", width=2.2),
        hovertemplate="%{y:.2f}"
    ))

    fig_precio.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title=f"Precio ({moneda})" if moneda else "Precio",
        yaxis_type="log" if escala_log else "linear",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.14)",
            zeroline=False,
            automargin=True
        ),
        hovermode="x unified",
        height=440,
        margin=dict(l=8, r=10, t=12, b=78),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        )
    )

    st.plotly_chart(fig_precio, use_container_width=True, config=plotly_config)

    # GRÁFICO 2: HISTÓRICO DE DIVIDEND YIELD
    st.markdown(f"#### Histórico de Dividend Yield (%)")

    fig_yield = go.Figure()
    x_ext = [df.index[0], df.index[-1]]

    fig_yield.add_trace(go.Scatter(
        x=df.index,
        y=df["Yield"],
        mode="lines",
        name="Dividend Yield (%)",
        line=dict(color="#38BDF8", width=2.1),
        fill="tozeroy",
        fillcolor="rgba(56, 189, 248, 0.08)",
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_infra, yield_infra], mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#10B981", width=1.6, dash="dot"),
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_medio, yield_medio], mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#F59E0B", width=1.6, dash="dash"),
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_sobre, yield_sobre], mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#EF4444", width=1.6, dash="dot"),
        hovertemplate="%{y:.2f}%"
    ))

    y_min = max(0.0, float(df["Yield"].min()) * 0.85)
    y_max = float(df["Yield"].max()) * 1.10

    fig_yield.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Yield (%)",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(
            range=[y_min, y_max],
            gridcolor="rgba(148, 163, 184, 0.14)",
            zeroline=False,
            automargin=True
        ),
        hovermode="x unified",
        height=330,
        margin=dict(l=8, r=10, t=12, b=78),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        )
    )

    st.plotly_chart(fig_yield, use_container_width=True, config=plotly_config)

# ------------------------------------------------------------------------------
# PESTAÑA 2: REGLA DE CHOWDER Y CRECIMIENTO DEL DIVIDENDO (DGR)
# ------------------------------------------------------------------------------
with tab_chowder:
    if chowder_val is not None:
        margen_ch = chowder_val - objetivo_chowder
        if chowder_val >= objetivo_chowder:
            pill_ch = (f"✅ Cumple Regla de Chowder · {chowder_val:.2f}% (margen {margen_ch:+.2f} pp)", "pill-green")
            accent_ch = "green"
        elif chowder_val >= objetivo_chowder - 2.0:
            pill_ch = (f"⚠️ Cerca del objetivo Chowder · {chowder_val:.2f}% ({margen_ch:+.2f} pp)", "pill-amber")
            accent_ch = "amber"
        else:
            pill_ch = (f"❌ No cumple Regla de Chowder · {chowder_val:.2f}% ({margen_ch:+.2f} pp)", "pill-red")
            accent_ch = "red"

        st.markdown(
            f'<div style="margin: 0.3rem 0 0.8rem 0;"><span class="status-pill {pill_ch[1]}">{pill_ch[0]}</span></div>',
            unsafe_allow_html=True
        )

        render_kpi_grid([
            {
                "label": "Número de Chowder",
                "value": f"{chowder_val:.2f}%",
                "sub": f"{margen_ch:+.2f} pp vs objetivo",
                "sub_class": "pos" if margen_ch >= 0 else "neg",
                "accent": accent_ch
            },
            {
                "label": "Dividend Yield Actual",
                "value": f"{yield_actual:.2f}%",
                "sub": "Componente renta",
                "accent": "blue"
            },
            {
                "label": etiqueta_dgr,
                "value": f"{dgr_chowder:+.2f}%",
                "sub": "Componente crecimiento",
                "sub_class": "pos" if dgr_chowder >= 0 else "neg",
                "accent": "green" if dgr_chowder >= 5 else "amber"
            },
            {
                "label": "Umbral Aplicable",
                "value": f"≥ {objetivo_chowder:.0f}%",
                "sub": regla_texto,
                "accent": "slate"
            },
        ])

        st.markdown("#### Ritmo histórico de crecimiento del dividendo (DGR)")
        render_kpi_grid([
            {
                "label": "DGR 1 Año",
                "value": f"{dgr_1y:+.2f}%" if dgr_1y is not None else "N/D",
                "sub": f"{ultimo_anio - 1}–{ultimo_anio}" if dgr_1y is not None else "Sin datos",
                "sub_class": "pos" if (dgr_1y or 0) > 0 else ("neg" if (dgr_1y or 0) < 0 else ""),
                "accent": "slate"
            },
            {
                "label": "DGR 3 Años",
                "value": f"{dgr_3y:+.2f}%" if dgr_3y is not None else "N/D",
                "sub": f"{ultimo_anio - 3}–{ultimo_anio}" if dgr_3y is not None else "Sin datos",
                "sub_class": "pos" if (dgr_3y or 0) > 0 else ("neg" if (dgr_3y or 0) < 0 else ""),
                "accent": "slate"
            },
            {
                "label": "DGR 5 Años",
                "value": f"{dgr_5y:+.2f}%" if dgr_5y is not None else "N/D",
                "sub": f"{ultimo_anio - 5}–{ultimo_anio}" if dgr_5y is not None else "Sin datos",
                "sub_class": "pos" if (dgr_5y or 0) > 0 else ("neg" if (dgr_5y or 0) < 0 else ""),
                "accent": "blue"
            },
            {
                "label": "DGR 10 Años",
                "value": f"{dgr_10y:+.2f}%" if dgr_10y is not None else "N/D",
                "sub": f"{ultimo_anio - 10}–{ultimo_anio}" if dgr_10y is not None else "Sin datos",
                "sub_class": "pos" if (dgr_10y or 0) > 0 else ("neg" if (dgr_10y or 0) < 0 else ""),
                "accent": "slate"
            },
        ])

        # Gráfico de barras de dividendos anuales completos
        div_hist_bar = anios_completos.tail(min(len(anios_completos), 12))
        if not div_hist_bar.empty:
            st.markdown("#### Evolución del dividendo anual (años completos)")
            fig_div = go.Figure(data=[
                go.Bar(
                    x=div_hist_bar.index.astype(str),
                    y=div_hist_bar.values,
                    marker_color="#10B981",
                    marker_line_width=0,
                    text=[f"{v:.2f}" for v in div_hist_bar.values],
                    textposition="outside",
                    hovertemplate="Año %{x}: %{y:.4f}" + sufijo_moneda + "<extra></extra>"
                )
            ])
            fig_div.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title=f"Dividendo ({moneda})" if moneda else "Dividendo",
                xaxis=dict(showgrid=False, type="category"),
                yaxis=dict(
                    range=[0, float(div_hist_bar.max()) * 1.18],
                    gridcolor="rgba(148, 163, 184, 0.14)",
                    automargin=True
                ),
                height=310,
                margin=dict(l=8, r=10, t=14, b=35),
                showlegend=False
            )
            st.plotly_chart(fig_div, use_container_width=True, config=plotly_config)
    else:
        st.info("No hay suficientes años naturales completos de dividendos para calcular la Regla de Chowder.")

# ------------------------------------------------------------------------------
# PESTAÑA 3: TABLAS RESUMEN Y EXPORTACIÓN CSV
# ------------------------------------------------------------------------------
with tab_datos:
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("#### 🎯 Resumen de Precios Objetivo")
        resumen_df = pd.DataFrame({
            "Zona": [
                "🟢 Infravaloración",
                "🟡 Valoración Media",
                "🔴 Sobrevaloración",
                "🔵 Cotización Actual"
            ],
            "Yield": [
                f"{yield_infra:.2f}%",
                f"{yield_medio:.2f}%",
                f"{yield_sobre:.2f}%",
                f"{yield_actual:.2f}%"
            ],
            f"Precio{sufijo_moneda}": [
                f"{precio_infra:.2f}",
                f"{precio_medio:.2f}",
                f"{precio_sobre:.2f}",
                f"{precio_actual:.2f}"
            ],
            "Distancia": [
                f"{dist_infra:+.1f}%",
                f"{dist_medio:+.1f}%",
                f"{dist_sobre:+.1f}%",
                "0.0%"
            ]
        })
        st.dataframe(resumen_df, use_container_width=True, hide_index=True)

    with col_t2:
        st.markdown("#### 📅 Historial de Dividendos Anuales")
        div_mostrar = div_por_anio.tail(years + 1)
        tabla_div = pd.DataFrame({
            "Año": div_mostrar.index.astype(str),
            f"Dividendo{sufijo_moneda}": div_mostrar.values
        })
        tabla_div["YoY (%)"] = tabla_div[f"Dividendo{sufijo_moneda}"].pct_change() * 100.0
        tabla_div.loc[tabla_div["Año"] == str(anio_actual), "Año"] = f"{anio_actual} (YTD)"

        st.dataframe(
            tabla_div.iloc[::-1].style.format({
                f"Dividendo{sufijo_moneda}": "{:.4f}",
                "YoY (%)": "{:+.2f}%"
            }, na_rep="—"),
            use_container_width=True,
            hide_index=True
        )

    csv_export = df[
        ["Close", "Dividends", "Div_Anual", "Yield", "Banda_Infra", "Banda_Media", "Banda_Sobre"]
    ].to_csv()
    st.download_button(
        label="📥 Descargar serie histórica en CSV",
        data=csv_export,
        file_name=f"weiss_chowder_{ticker_actual}_{years}y.csv",
        mime="text/csv",
        use_container_width=True
    )
