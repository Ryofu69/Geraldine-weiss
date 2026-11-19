import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuración de la página
st.set_page_config(
    page_title="Analizador Geraldine Weiss",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Valoración por Teoría del Dividendo (Geraldine Weiss)")
st.caption("Cálculo basado en precios de cierre históricos **sin ajustar por dividendos** (`auto_adjust=False`).")


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_datos_yahoo(ticker: str, years: int):
    """
    Descarga histórico de precios sin ajustar por dividendos y calcula el dividendo
    anualizado móvil (TTM - últimos 365 días).
    """
    end_date = datetime.today()
    # Descargamos 1 año extra para llenar la ventana móvil de 365 días desde el inicio del periodo
    start_date = end_date - timedelta(days=(years + 1) * 365 + 20)

    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date, auto_adjust=False)

    if df.empty:
        return None, None, {}

    # Eliminar zona horaria del índice para evitar conflictos en cálculos y gráficos
    df.index = df.index.tz_localize(None)

    # Guardar copia de dividendos brutos para el resumen anual
    div_brutos = df["Dividends"].copy()

    # Calcular Dividendo TTM (suma móvil de los últimos 365 días naturales)
    df["TTM_Div"] = df["Dividends"].rolling("365D").sum()

    # Recortar al periodo exacto solicitado por el usuario
    cutoff_date = end_date - timedelta(days=years * 365)
    df = df[df.index >= cutoff_date].copy()

    # Filtrar días sin precio o sin dividendo TTM válido
    df = df[(df["Close"] > 0) & (df["TTM_Div"] > 0)].copy()

    if df.empty:
        return None, div_brutos, {}

    # Dividend Yield histórico real (%) = (Dividendo TTM / Precio Cierre sin ajustar) * 100
    df["Yield"] = (df["TTM_Div"] / df["Close"]) * 100.0

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    return df, div_brutos, info


# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Parámetros de Análisis")

    ticker_input = st.text_input(
        "Ticker (Yahoo Finance)",
        value="JNJ",
        help="Ejemplos: JNJ, KO, PG, PEP, ABBV, IBE.MC, ITX.MC, ENAG.MC"
    ).strip().upper()

    years = st.selectbox(
        "Periodo histórico (años)",
        options=[5, 7, 10, 15, 20],
        index=2
    )

    st.divider()
    st.subheader("Cálculo de Franjas Weiss")

    metodo_franjas = st.radio(
        "Método para extremos de Yield",
        options=["Percentiles (filtra picos atípicos)", "Extremos absolutos (Mín / Máx)"],
        index=0,
        help=(
            "Los percentiles evitan que caídas extremas de un solo día (ej. crash puntual) "
            "o solapamientos de fechas de pago distorsionen las bandas."
        )
    )

    if metodo_franjas.startswith("Percentiles"):
        percentil = st.slider(
            "Recorte en extremos (%)",
            min_value=1,
            max_value=15,
            value=5,
            help="Un 5% usa el Percentil 95 para Infravaloración y el Percentil 5 para Sobrevaloración."
        )
    else:
        percentil = 0

    tipo_media = st.radio(
        "Referencia central",
        options=["Media aritmética", "Mediana"],
        index=0
    )

    st.divider()
    st.subheader("Dividendo para Precios Objetivo")
    fuente_dividendo = st.radio(
        "Dividendo anual actual",
        options=["TTM (últimos 12 meses)", "Forward (estimado Yahoo)", "Manual"],
        index=0
    )
    div_manual = None
    if fuente_dividendo == "Manual":
        div_manual = st.number_input(
            "Introduce el dividendo anual por acción",
            min_value=0.0001,
            value=1.0,
            step=0.05,
            format="%.4f"
        )

    escala_log = st.checkbox("Escala logarítmica en gráfico de precio", value=False)


# --- EJECUCIÓN PRINCIPAL ---
if not ticker_input:
    st.info("Introduce un ticker en la barra lateral para comenzar.")
    st.stop()

with st.spinner(f"Descargando datos históricos de {ticker_input}..."):
    df, div_brutos, info = cargar_datos_yahoo(ticker_input, years)

if df is None or df.empty:
    st.error(
        f"No se encontraron suficientes datos de precio y dividendos para **{ticker_input}** "
        f"en los últimos {years} años. Comprueba que el ticker sea correcto en Yahoo Finance "
        "y que la empresa reparta dividendos."
    )
    st.stop()

# Datos generales de la empresa
nombre_empresa = info.get("longName") or info.get("shortName") or ticker_input
moneda = info.get("currency", "")
sector = info.get("sector", "N/D")

# Cálculo de Yields históricos de referencia
if percentil == 0:
    yield_infra = float(df["Yield"].max())
    yield_sobre = float(df["Yield"].min())
    etiqueta_extremo = "Mín/Máx absoluto"
else:
    yield_infra = float(df["Yield"].quantile(1 - percentil / 100.0))
    yield_sobre = float(df["Yield"].quantile(percentil / 100.0))
    etiqueta_extremo = f"P{percentil} / P{100 - percentil}"

if tipo_media == "Media aritmética":
    yield_medio = float(df["Yield"].mean())
else:
    yield_medio = float(df["Yield"].median())

# Validar que los yields sean mayores que cero
if yield_sobre <= 0 or yield_medio <= 0 or yield_infra <= 0:
    st.error("Los valores de Dividend Yield calculados no son válidos para construir las bandas.")
    st.stop()

# Bandas históricas dinámicas sobre el precio (sin ajustar por dividendos)
df["Banda_Infra"] = df["TTM_Div"] / (yield_infra / 100.0)
df["Banda_Media"] = df["TTM_Div"] / (yield_medio / 100.0)
df["Banda_Sobre"] = df["TTM_Div"] / (yield_sobre / 100.0)

# Precio actual y dividendo anual de referencia
precio_actual = float(df["Close"].iloc[-1])
fecha_ultimo_dato = df.index[-1].strftime("%Y-%m-%d")
ttm_actual = float(df["TTM_Div"].iloc[-1])
forward_yahoo = info.get("dividendRate")

if fuente_dividendo == "Manual" and div_manual is not None:
    div_actual = float(div_manual)
    etiqueta_div = "Manual"
elif fuente_dividendo == "Forward (estimado Yahoo)" and forward_yahoo and forward_yahoo > 0:
    div_actual = float(forward_yahoo)
    etiqueta_div = "Forward Yahoo"
else:
    div_actual = ttm_actual
    etiqueta_div = "TTM 12M"
    if fuente_dividendo == "Forward (estimado Yahoo)":
        st.sidebar.warning("Yahoo no dispone de dividendo Forward para este ticker; se usa TTM.")

yield_actual = (div_actual / precio_actual) * 100.0

# Precios objetivo actuales según Geraldine Weiss
precio_infra = div_actual / (yield_infra / 100.0)
precio_medio = div_actual / (yield_medio / 100.0)
precio_sobre = div_actual / (yield_sobre / 100.0)

# Distancias porcentuales desde el precio actual
dist_infra = ((precio_infra - precio_actual) / precio_actual) * 100.0
dist_medio = ((precio_medio - precio_actual) / precio_actual) * 100.0
dist_sobre = ((precio_sobre - precio_actual) / precio_actual) * 100.0

# Diagnóstico de valoración
if precio_actual <= precio_infra:
    estado = "🟢 INFRAVALORADA (Zona de Compra)"
    color_estado = "success"
elif precio_actual <= precio_medio:
    estado = "🟡 POR DEBAJO DE LA MEDIA (Atractiva)"
    color_estado = "info"
elif precio_actual < precio_sobre:
    estado = "🟠 POR ENCIMA DE LA MEDIA (Esperar / Mantener)"
    color_estado = "warning"
else:
    estado = "🔴 SOBREVALORADA (Zona de Precaución / Venta)"
    color_estado = "error"

# --- CABECERA Y DIAGNÓSTICO ---
col_head1, col_head2 = st.columns([2, 1])
with col_head1:
    st.subheader(f"{nombre_empresa} ({ticker_input})")
    st.caption(
        f"Sector: **{sector}** | Divisa: **{moneda}** | "
        f"Dividendo base ({etiqueta_div}): **{div_actual:.4f} {moneda}** | "
        f"Último cierre: **{fecha_ultimo_dato}**"
    )
with col_head2:
    getattr(st, color_estado)(estado)

# --- TARJETAS DE MÉTRICAS PRINCIPALES ---
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        label=f"Precio Actual ({moneda})",
        value=f"{precio_actual:.2f}",
        delta=f"Yield actual: {yield_actual:.2f}%",
        delta_color="off"
    )

with c2:
    st.metric(
        label=f"🟢 Infravaloración (Yield {yield_infra:.2f}%)",
        value=f"{precio_infra:.2f}",
        delta=f"{dist_infra:+.1f}% vs actual",
        delta_color="off"
    )

with c3:
    st.metric(
        label=f"🟡 Precio Medio (Yield {yield_medio:.2f}%)",
        value=f"{precio_medio:.2f}",
        delta=f"{dist_medio:+.1f}% potencial a media",
        delta_color="normal"
    )

with c4:
    st.metric(
        label=f"🔴 Sobrevaloración (Yield {yield_sobre:.2f}%)",
        value=f"{precio_sobre:.2f}",
        delta=f"{dist_sobre:+.1f}% vs actual",
        delta_color="off"
    )

# Barra visual de posición dentro del canal de valoración
rango_total = precio_sobre - precio_infra
if rango_total > 0:
    posicion_rel = (precio_actual - precio_infra) / rango_total
    posicion_clamped = min(max(posicion_rel, 0.0), 1.0)
    st.markdown(
        f"**Posición en el canal de Weiss ({etiqueta_extremo}):** "
        f"`{posicion_rel * 100:.1f}%` *(0% = Infravalorada | 100% = Sobrevalorada)*"
    )
    st.progress(posicion_clamped)

st.divider()

# --- GRÁFICO 1: PRECIO Y FRANJAS DE GERALDINE WEISS ---
fig_precio = go.Figure()

# 1. Banda de Infravaloración (límite inferior verde)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Infra"],
    mode="lines",
    name=f"Infravaloración ({yield_infra:.2f}%)",
    line=dict(color="#00C853", width=1.8, dash="dot")
))

# 2. Banda Media (relleno verde suave entre Infravaloración y Media)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Media"],
    mode="lines",
    name=f"Valoración Media ({yield_medio:.2f}%)",
    line=dict(color="#FFAB00", width=1.8, dash="dash"),
    fill="tonexty",
    fillcolor="rgba(0, 200, 83, 0.12)"
))

# 3. Banda de Sobrevaloración (relleno rojo suave entre Media y Sobrevaloración)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Banda_Sobre"],
    mode="lines",
    name=f"Sobrevaloración ({yield_sobre:.2f}%)",
    line=dict(color="#FF1744", width=1.8, dash="dot"),
    fill="tonexty",
    fillcolor="rgba(255, 23, 68, 0.12)"
))

# 4. Precio de cierre real (sin ajustar por dividendos)
fig_precio.add_trace(go.Scatter(
    x=df.index,
    y=df["Close"],
    mode="lines",
    name="Precio Cierre (sin ajustar div.)",
    line=dict(color="#2979FF", width=2.4)
))

fig_precio.update_layout(
    title=f"Franjas de Geraldine Weiss — {ticker_input} ({years} años)",
    xaxis_title="Fecha",
    yaxis_title=f"Precio ({moneda})",
    yaxis_type="log" if escala_log else "linear",
    hovermode="x unified",
    height=540,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig_precio, use_container_width=True)

# --- GRÁFICO 2: HISTÓRICO DE DIVIDEND YIELD ---
fig_yield = go.Figure()

fig_yield.add_trace(go.Scatter(
    x=df.index,
    y=df["Yield"],
    mode="lines",
    name="Dividend Yield TTM (%)",
    line=dict(color="#2979FF", width=2)
))

fig_yield.add_hline(
    y=yield_infra,
    line_dash="dot",
    line_color="#00C853",
    annotation_text=f"Infravaloración: {yield_infra:.2f}%",
    annotation_position="top left"
)
fig_yield.add_hline(
    y=yield_medio,
    line_dash="dash",
    line_color="#FFAB00",
    annotation_text=f"Media: {yield_medio:.2f}%",
    annotation_position="top left"
)
fig_yield.add_hline(
    y=yield_sobre,
    line_dash="dot",
    line_color="#FF1744",
    annotation_text=f"Sobrevaloración: {yield_sobre:.2f}%",
    annotation_position="bottom left"
)

fig_yield.update_layout(
    title=f"Histórico de Dividend Yield (%) — {ticker_input}",
    xaxis_title="Fecha",
    yaxis_title="Dividend Yield (%)",
    hovermode="x unified",
    height=380,
    showlegend=False
)

st.plotly_chart(fig_yield, use_container_width=True)

# --- TABLAS RESUMEN ---
col_tab1, col_tab2 = st.columns(2)

with col_tab1:
    st.subheader("📋 Resumen de Bandas Actuales")
    resumen_df = pd.DataFrame({
        "Zona de Valoración": [
            "🟢 Infravaloración (Compra)",
            "🟡 Valoración Media (Justo)",
            "🔴 Sobrevaloración (Venta)",
            "🔵 Cotización Actual"
        ],
        "Dividend Yield (%)": [
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
        "Distancia vs Actual": [
            f"{dist_infra:+.2f}%",
            f"{dist_medio:+.2f}%",
            f"{dist_sobre:+.2f}%",
            "0.00%"
        ]
    })
    st.dataframe(resumen_df, use_container_width=True, hide_index=True)

with col_tab2:
    st.subheader("📅 Historial de Dividendos Anuales")
    div_anual = div_brutos.groupby(div_brutos.index.year).sum()
    div_anual = div_anual[div_anual > 0].tail(years + 1)

    tabla_div = pd.DataFrame({
        "Año": div_anual.index.astype(str),
        f"Dividendo ({moneda})": div_anual.values
    })
    tabla_div["Crecimiento YoY (%)"] = tabla_div[f"Dividendo ({moneda})"].pct_change() * 100

    # Marcar el año en curso como YTD
    anio_actual = str(datetime.today().year)
    tabla_div.loc[tabla_div["Año"] == anio_actual, "Año"] = f"{anio_actual} (YTD)"

    st.dataframe(
        tabla_div.iloc[::-1].style.format({
            f"Dividendo ({moneda})": "{:.4f}",
            "Crecimiento YoY (%)": "{:+.2f}%"
        }, na_rep="—"),
        use_container_width=True,
        hide_index=True
    )

# --- DESCARGA DE DATOS ---
with st.expander("📥 Exportar serie histórica calculada (CSV)"):
    csv_export = df[["Close", "Dividends", "TTM_Div", "Yield", "Banda_Infra", "Banda_Media", "Banda_Sobre"]].to_csv()
    st.download_button(
        label="Descargar CSV con bandas históricas",
        data=csv_export,
        file_name=f"weiss_{ticker_input}_{years}y.csv",
        mime="text/csv"
    )
