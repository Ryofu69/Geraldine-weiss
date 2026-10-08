import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io 
import os

# Ignorar advertencias menores
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Screener Geraldine Weiss", page_icon="📊", layout="wide")

ARCHIVO_WATCHLIST = "watchlist.txt"
ARCHIVO_CARTERA = "cartera.csv"

# ==========================================
# UTILIDADES DE LIMPIEZA Y PERSISTENCIA
# ==========================================
def limpiar_numero_europeo(val):
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).strip().replace('€', '').replace('$', '').replace('£', '').replace(' ', '')
    if '.' in val_str and ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def cargar_archivo_texto(ruta, predeterminado=""):
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c: return c
        except Exception: pass
    return predeterminado

def guardar_archivo_texto(ruta, texto):
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# Diccionario de respaldo
TRADUCCION = {
    'Technology': 'Tecnología', 'Healthcare': 'Salud', 'Financial Services': 'Servicios Financieros',
    'Consumer Cyclical': 'Consumo Cíclico', 'Industrials': 'Industrial', 'Consumer Defensive': 'Consumo Defensivo',
    'Energy': 'Energía', 'Real Estate': 'Inmobiliario', 'Utilities': 'Servicios Públicos',
    'Basic Materials': 'Materiales Básicos', 'Communication Services': 'Servicios de Comunicación'
}

# ==========================================
# 1. FUNCIÓN DE ANÁLISIS INDIVIDUAL
# ==========================================
def screener_weiss_definitivo(ticker_symbol, años_analisis, impuesto_pct):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    net_mult = 1 - (impuesto_pct / 100)
    
    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None: return default
        try: return float(val)
        except (ValueError, TypeError): return default

    sector_en = info.get('sector', 'Desconocido')
    industry_en = info.get('industry', 'Desconocido')
    pais = info.get('country', 'Desconocido')
    
    sector_final = TRADUCCION.get(sector_en, sector_en)
    industry_final = industry_en 

    es_regulada_o_reit = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower() or 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_tecnologica = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower()
    es_industrial = 'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower()
    
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()

    payout_limite_bpa = 80.0 if es_regulada_o_reit else 50.0
    payout_limite_fcf = 85.0 if es_regulada_o_reit else 60.0
    payout_amarillo_bpa = 85.0 if es_regulada_o_reit else 60.0
    payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 70.0

    currency = info.get('currency', 'USD')
    divisor_uk = 1.0 
    if currency == 'EUR': sym = '€'
    elif currency == 'GBP': sym = '£'
    elif currency == 'GBp': sym = '£'; divisor_uk = 100.0 
    else: sym = '$' 

    historial_completo = ticker.history(period="max", auto_adjust=False)
    dividendos = ticker.dividends
    
    if dividendos.empty or len(historial_completo) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    dividendos.index = dividendos.index.tz_localize(None).normalize()

    fecha_corte_analisis = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
    historial_analisis = historial_completo[historial_completo.index >= fecha_corte_analisis].copy()

    if historial_analisis.empty:
        st.error(f"❌ Error: No se encontraron datos de cotización en los últimos {años_analisis} años.")
        return

    divs_por_año = dividendos.groupby(dividendos.index.year).sum()
    precio_actual = historial_analisis['Close'].dropna().iloc[-1]
    año_actual = datetime.now().year
    
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4
    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    if forward_dividend == 0 and not dividendos.empty:
        ultimo_año_completo = divs_por_año.iloc[-2] if len(divs_por_año) > 1 else 0
        forward_dividend = max(dividendos.iloc[-1] * pagos_por_año, ultimo_año_completo)
    
    if currency == 'GBp' and forward_dividend > 0:
        if forward_dividend < (precio_actual / 10): forward_dividend *= 100

    historial_analisis['Year'] = historial_analisis.index.year
    historial_analisis['Div_Anual'] = historial_analisis['Year'].map(divs_por_año)
    historial_analisis.loc[historial_analisis['Year'] == año_actual, 'Div_Anual'] = forward_dividend
    historial_analisis['Div_Anual'] = historial_analisis['Div_Anual'].bfill().ffill()

    historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
    historial_analisis.replace([np.inf, -np.inf], np.nan, inplace=True)

    yields_validos = historial_analisis['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]

    yield_infravalorado = yields_validos.quantile(0.95) 
    yield_sobrevalorado = yields_validos.quantile(0.05) 
    yield_medio = yields_validos.mean()

    yield_actual = (forward_dividend / precio_actual) * 100

    payout_ratio = get_safe('payoutRatio') * 100
    per = get_safe('trailingPE', get_safe('forwardPE'))
    per_actual = get_safe('trailingPE')
    deuda_equity = get_safe('debtToEquity') 
    market_cap = get_safe('marketCap')
    current_ratio = get_safe('currentRatio') 
    bpa_trailing = get_safe('trailingEps')
    bpa_forward = get_safe('forwardEps')
    per_forward = get_safe('forwardPE')
    price_to_book = get_safe('priceToBook', -1)
    total_debt = get_safe('totalDebt', 0)
    payout_forward = (forward_dividend / bpa_forward) * 100 if bpa_forward > 0 else -1

    años_crecimiento_bpa = 0
    total_años_bpa_datos = 0
    try:
        inc_stmt = ticker.income_stmt
        if not inc_stmt.empty:
            for key in ['Diluted EPS', 'Basic EPS']:
                if key in inc_stmt.index:
                    eps_series = inc_stmt.loc[key].dropna().sort_index()
                    if len(eps_series) >= 2:
                        diffs = eps_series.diff().dropna()
                        años_crecimiento_bpa = int((diffs > 0).sum())
                        total_años_bpa_datos = len(diffs)
                        break
    except Exception: pass
    
    crecimiento_bpa_3y = None
    try:
        inc_stmt = ticker.income_stmt
        if not inc_stmt.empty:
            if 'Diluted EPS' in inc_stmt.index: eps_data = inc_stmt.loc['Diluted EPS'].dropna()
            elif 'Basic EPS' in inc_stmt.index: eps_data = inc_stmt.loc['Basic EPS'].dropna()
            else: eps_data = []

            if len(eps_data) >= 4:
                eps_actual = eps_data.iloc[0] 
                eps_pasado = eps_data.iloc[3] 
                if eps_pasado > 0 and eps_actual > 0:
                    crecimiento_bpa_3y = (((eps_actual / eps_pasado) ** (1 / 3)) - 1) * 100
    except Exception: pass
    
    fcf = get_safe('freeCashflow')
    shares = get_safe('sharesOutstanding')
    payout_fcf = -1
    p_fcf = -1
    fcf_yield = 0
    deuda_fcf = -1 

    if fcf != 0 and shares > 0:
        fcf_per_share = fcf / shares
        if currency == 'GBp': fcf_per_share *= 100 
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100
    
    if fcf > 0:
        deuda_fcf = total_debt / fcf

    dividendos_barras = divs_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    divs_recientes = dividendos_barras.tail(años_analisis + 1)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

    dgr_5y = None
    dgr_periodo = None
    if len(dividendos_barras) >= 6:
        div_actual = dividendos_barras.iloc[-1]
        div_5y = dividendos_barras.iloc[-6]
        if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100
    
    if len(dividendos_barras) >= (años_analisis + 1):
        div_periodo = dividendos_barras.iloc[-(años_analisis + 1)]
        if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

    racha_sin_recortes = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99:
                racha_sin_recortes += 1
            else: break

    shares_yearly = pd.Series(dtype=float)
    variacion_acciones = None

    try:
        fecha_corte_shares = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis + 3)
        shares_hist = ticker.get_shares_full(start=fecha_corte_shares.strftime('%Y-%m-%d'), end=None)
        if shares_hist is not None and len(shares_hist) > 1:
            sy = shares_hist.groupby(shares_hist.index.year).last()
            sy = sy[sy > 0]
            sy = sy[sy.pct_change().fillna(0) > -0.50]
            if len(sy) >= 2:
                shares_yearly = sy
                acc_ini = shares_yearly.iloc[-(años_analisis + 1)] if len(shares_yearly) >= (años_analisis + 1) else shares_yearly.iloc[0]
                acc_fin = shares_yearly.iloc[-1]
                if acc_ini > 0: variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
    except Exception: pass

    if variacion_acciones is None or shares_yearly.empty:
        try:
            inc_stmt = ticker.income_stmt
            if not inc_stmt.empty:
                for key in ['Basic Average Shares', 'Diluted Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna()
                        sh_data = sh_data[sh_data > 0].sort_index()
                        sh_data = sh_data[sh_data.pct_change().fillna(0) > -0.50]
                        if len(sh_data) >= 2:
                            shares_yearly = sh_data.groupby(sh_data.index.year).last()
                            acc_ini = shares_yearly.iloc[0]
                            acc_fin = shares_yearly.iloc[-1]
                            if acc_ini > 0: 
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                break
        except Exception: pass

    precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
    precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
    precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

    if precio_justo > 0:
        pct_actual_vs_media = ((precio_actual - precio_justo) / precio_justo) * 100
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100
    else:
        pct_actual_vs_media = pct_infra_vs_media = pct_sobre_vs_media = 0

    txt_extra_actual = f"Descuento: {abs(pct_actual_vs_media):.1f}% vs Media" if pct_actual_vs_media <= 0 else f"Sobreprecio: +{pct_actual_vs_media:.1f}% vs Media"
    txt_extra_infra = f"Suelo: {pct_infra_vs_media:.1f}% vs Media"
    txt_extra_justo = f"Ancla ({años_analisis}A)"
    txt_extra_sobre = f"Techo: +{pct_sobre_vs_media:.1f}% vs Media"

    score = 0.0
    cond_fcf = payout_fcf != -1 and payout_fcf <= payout_amarillo_fcf
    cond_pfcf = p_fcf != -1 and 0 < p_fcf <= 20
    cond_deuda = deuda_fcf != -1 and 0 < deuda_fcf <= 5.0
    cond_historial = años_pagando >= 25 and racha_sin_recortes >= 12
    cond_aumentos = incrementos_dividendo >= min(5, años_analisis)
    cond_acciones = variacion_acciones is not None and variacion_acciones < 0
    cond_yield = yield_actual >= yield_medio
    cond_bpa = 0 < payout_ratio <= payout_amarillo_bpa
    cond_per = 0 < per <= 20
    ratio_bpa_val = (años_crecimiento_bpa / total_años_bpa_datos) if total_años_bpa_datos > 0 else 0
    cond_consistencia = total_años_bpa_datos > 0 and ratio_bpa_val >= 0.65

    if cond_fcf: score += 1.5
    if cond_pfcf: score += 1.5
    if cond_deuda: score += 1.5
    if cond_historial: score += 1.5
    if cond_aumentos: score += 1.0
    if cond_acciones: score += 1.0
    if cond_yield: score += 0.5
    if cond_bpa: score += 0.5
    if cond_per: score += 0.5
    if cond_consistencia: score += 0.5

    if (es_utility_pura or es_telecom) and yield_actual > 4.0: chowder_target = 8.0
    elif yield_actual >= 3.0: chowder_target = 12.0
    else: chowder_target = 15.0

    precio_obj_chowder = None
    yield_req_chowder = None
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        chowder_pass = chowder_number >= chowder_target
        yield_req_chowder = chowder_target - dgr_5y
        if yield_req_chowder > 0:
            precio_obj_chowder = (forward_dividend / yield_req_chowder) * 100
    else:
        chowder_number = None
        chowder_pass = False

    tipo_empresa_txt = "🏢 Sector Inmobiliario/Regulado (Filtros Flexibles)" if es_regulada_o_reit else "🏭 Sector Industrial/General (Filtros Estrictos)"
    
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")
    
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 10px; border-radius: 5px; margin-bottom: 20px;">
        <strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <strong>Industry:</strong> <span style="color: #21c354;">{industry_final}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🌍 Perfil Fiscal y Retención en Origen")
    if pais in ['United States', 'Netherlands', 'Canada']: 
        st.success(f"✅ **{pais}**: Retención en origen del 15%. Deducción del 100% en el IRPF español por doble imposición internacional.")
    elif pais == 'United Kingdom': 
        st.success(f"✅ **{pais}**: Retención en origen del 0% (salvo algunos REITs).")
    elif pais == 'Spain': 
        st.success(f"✅ **{pais}**: Mercado local. Retención directa del {impuesto_pct}%. Sin trámites en el extranjero.")
    elif pais == 'France':
        st.error(f"❌ **{pais}**: Retención en origen del 25% (exceso reclamable si no hay trámite previo).")
    else: 
        st.info(f"ℹ️ **{pais}**: Revisa el convenio de doble imposición aplicable.")

    st.subheader(f"🎯 Precios Objetivo y Valoración Actual ({años_analisis} Años)")
    
    color_actual = "#21c354" if precio_actual <= precio_compra else ("#ff4b4b" if precio_actual >= precio_venta else "#faca2b")

    def metric_color(label, value, yield_txt, extra_txt, color):
        st.markdown(f"""
        <div style="display: flex; flex-direction: column; margin-bottom: 1rem;">
        <span style="font-size: 1rem; color: #c4c4cc;">{label}</span>
        <span style="font-size: 2.2rem; font-weight: 700; color: {color}; margin-top: 0.2rem; margin-bottom: 0.1rem;">{value}</span>
        <span style="font-size: 0.95rem; font-weight: 600; color: {color}; margin-bottom: 0.2rem;">↑ {yield_txt}</span>
        <span style="font-size: 0.85rem; font-weight: 500; color: #aaa;">{extra_txt}</span>
        </div>
        """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1: metric_color("Cotización Actual", f"{precio_actual / divisor_uk:.2f}{sym}", f"Yield: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% neto)", txt_extra_actual, color_actual)
    with col2: metric_color("Franja Infravalorada", f"{precio_compra / divisor_uk:.2f}{sym}", f"Yield {yield_infravalorado:.2f}% ({yield_infravalorado * net_mult:.2f}% neto)", txt_extra_infra, "#21c354") 
    with col3: metric_color("Precio Justo (Media)", f"{precio_justo / divisor_uk:.2f}{sym}", f"Yield {yield_medio:.2f}% ({yield_medio * net_mult:.2f}% neto)", txt_extra_justo, "#faca2b") 
    with col4: metric_color("Franja Sobrevalorada", f"{precio_venta / divisor_uk:.2f}{sym}", f"Yield {yield_sobrevalorado:.2f}% ({yield_sobrevalorado * net_mult:.2f}% neto)", txt_extra_sobre, "#ff4b4b") 

    st.markdown("<br>", unsafe_allow_html=True)
    if score >= 8.0: st.success(f"🏆 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Sobresaliente.")
    elif score >= 5.0: st.warning(f"⚖️ **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Aceptable.")
    else: st.error(f"🚨 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Calidad Insuficiente.")

    if chowder_number is not None:
        if chowder_pass: st.success(f"🥣 **REGLA DE CHOWDER: APROBADA ({chowder_number:.1f})** — Supera el objetivo de {chowder_target:.0f}.")
        else: st.error(f"🥣 **REGLA DE CHOWDER: SUSPENSA ({chowder_number:.1f})** — Objetivo exigido: {chowder_target:.0f}.")

    st.markdown(f"### 📈 Evolución Histórica de Valoración ({años_analisis} Años)")
    df_grafico = historial_analisis[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_analisis['Div_Anual']
        df_grafico['Precio_Compra'] = (df_grafico['Div_Grafico'] / yield_infravalorado) * 100
        df_grafico['Precio_Justo'] = (df_grafico['Div_Grafico'] / yield_medio) * 100
        df_grafico['Precio_Venta'] = (df_grafico['Div_Grafico'] / yield_sobrevalorado) * 100
        
        if currency == 'GBp':
            for c in ['Close', 'Precio_Compra', 'Precio_Justo', 'Precio_Venta']:
                df_grafico[c] = df_grafico[c] / divisor_uk

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Venta'], name='Franja Sobrevalorada (Venta)', line=dict(color='#ff4b4b', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Compra'], name='Franja Infravalorada (Compra)', line=dict(color='#21c354', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Close'], name='Cotización Real', line=dict(color='#00d4ff', width=3)))
        
        fig.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), 
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), 
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 2. FUNCIÓN RADAR MÚLTIPLE
# ==========================================
def analizar_empresa_rapido(ticker_symbol, años_analisis, impuesto_pct):
    try:
        ticker = yf.Ticker(ticker_symbol.strip().upper())
        info = ticker.info
        
        def get_safe(key, default=0.0):
            val = info.get(key)
            if val is None: return default
            try: return float(val)
            except: return default
            
        dividendos = ticker.dividends
        historial = ticker.history(period="15y", auto_adjust=False)
        
        if dividendos.empty or len(historial) < 252: return None

        historial.index = historial.index.tz_localize(None).normalize()
        dividendos.index = dividendos.index.tz_localize(None).normalize()

        fecha_corte = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
        ha = historial[historial.index >= fecha_corte].copy()
        if ha.empty: return None

        sector_en = info.get('sector', '')
        industry_en = info.get('industry', '')
        es_regulada = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower() or 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
        es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
        es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()

        payout_lim_bpa = 80.0 if es_regulada else 50.0
        payout_ama_bpa = 85.0 if es_regulada else 60.0
        payout_lim_fcf = 85.0 if es_regulada else 60.0
        payout_ama_fcf = 90.0 if es_regulada else 70.0

        precio_actual = ha['Close'].dropna().iloc[-1]
        divs_por_año = dividendos.groupby(dividendos.index.year).sum()
        año_actual = datetime.now().year
        
        forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
        if forward_dividend == 0 and not dividendos.empty:
            ultimo_año_completo = divs_por_año.iloc[-2] if len(divs_por_año) > 1 else 0
            forward_dividend = max(dividendos.iloc[-1] * 4, ultimo_año_completo)

        currency = info.get('currency', 'USD')
        divisor_uk = 100.0 if currency == 'GBp' else 1.0

        if currency == 'GBp' and forward_dividend > 0:
            if forward_dividend < (precio_actual / 10): forward_dividend *= 100

        ha['Year'] = ha.index.year
        ha['Div_Anual'] = ha['Year'].map(divs_por_año)
        ha.loc[ha['Year'] == año_actual, 'Div_Anual'] = forward_dividend
        ha['Div_Anual'] = ha['Div_Anual'].bfill().ffill()

        ha['Yield_Diario'] = (ha['Div_Anual'] / ha['Close']) * 100
        yields_validos = ha['Yield_Diario'].dropna()
        yields_validos = yields_validos[yields_validos > 0]

        yield_infravalorado = yields_validos.quantile(0.95)
        yield_sobrevalorado = yields_validos.quantile(0.05)
        yield_medio = yields_validos.mean()

        precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
        precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
        precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

        yield_actual = (forward_dividend / precio_actual) * 100
        yield_neto = yield_actual * (1 - (impuesto_pct / 100))
        div_neto_absoluto = forward_dividend * (1 - (impuesto_pct / 100))

        payout_bpa = get_safe('payoutRatio') * 100
        fcf = get_safe('freeCashflow')
        shares = get_safe('sharesOutstanding')
        total_debt = get_safe('totalDebt')
        per = get_safe('trailingPE', get_safe('forwardPE'))
        pb = get_safe('priceToBook', -1.0)

        payout_fcf = -1.0
        p_fcf = -1.0
        if fcf > 0 and shares > 0 and forward_dividend > 0:
            fcf_per_share = fcf / shares
            if currency == 'GBp': fcf_per_share *= 100
            if fcf_per_share > 0:
                payout_fcf = (forward_dividend / fcf_per_share) * 100
                p_fcf = precio_actual / fcf_per_share

        deuda_fcf = total_debt / fcf if fcf > 0 else -1.0

        variacion_acciones = None
        try:
            inc_stmt = ticker.income_stmt
            if not inc_stmt.empty:
                for key in ['Basic Average Shares', 'Diluted Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna().sort_index()
                        sh_data = sh_data[sh_data > 0]
                        if len(sh_data) >= 2:
                            sy = sh_data.groupby(sh_data.index.year).last()
                            acc_ini, acc_fin = sy.iloc[0], sy.iloc[-1]
                            if acc_ini > 0 and (acc_fin / acc_ini) > 0.10: 
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                break
        except: pass

        dividendos_barras = divs_por_año.copy()
        if año_actual in dividendos_barras.index: dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

        dgr_5y = None
        if len(dividendos_barras) >= 6:
            div_actual, div_5y = dividendos_barras.iloc[-1], dividendos_barras.iloc[-6]
            if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100

        dgr_periodo = None
        if len(dividendos_barras) >= (años_analisis + 1):
            div_actual, div_periodo = dividendos_barras.iloc[-1], dividendos_barras.iloc[-(años_analisis + 1)]
            if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

        años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
        racha_sin_recortes = 0
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99: racha_sin_recortes += 1
                else: break

        incrementos_dividendo = int((dividendos_barras.tail(años_analisis + 1).diff().dropna() > 0).sum())

        score = 0.0
        cond_fcf = payout_fcf != -1 and payout_fcf <= payout_ama_fcf
        cond_pfcf = p_fcf != -1 and 0 < p_fcf <= 20
        cond_deuda = deuda_fcf != -1 and 0 < deuda_fcf <= 5.0
        cond_historial = años_pagando >= 25 and racha_sin_recortes >= 12
        cond_aumentos = incrementos_dividendo >= min(5, años_analisis)
        cond_acciones = variacion_acciones is not None and variacion_acciones < 0
        cond_yield = yield_actual >= yield_medio
        cond_bpa = 0 < payout_bpa <= payout_ama_bpa
        cond_per = 0 < per <= 20

        if cond_fcf: score += 1.5
        if cond_pfcf: score += 1.5
        if cond_deuda: score += 1.5
        if cond_historial: score += 1.5
        if cond_aumentos: score += 1.0
        if cond_acciones: score += 1.0
        if cond_yield: score += 0.5
        if cond_bpa: score += 0.5
        if cond_per: score += 0.5

        if (es_utility_pura or es_telecom) and yield_actual > 4.0: chowder_target = 8.0
        elif yield_actual >= 3.0: chowder_target = 12.0
        else: chowder_target = 15.0

        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0

        dist_real_suelo = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 999.0
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0

        if precio_actual <= precio_compra:
            estado = "🎯 COMPRA"
            orden_est = 1
        elif precio_actual >= precio_venta:
            estado = "🔴 SOBREVALORADA"
            orden_est = 3
        else:
            estado = "🟡 MANTENER"
            orden_est = 2

        sym_m = "€" if currency == "EUR" else ("£" if currency in ["GBP", "GBp"] else "$")

        return {
            "Estado": estado,
            "Ticker": ticker_symbol.strip().upper(),
            "Score Weiss": f"{score:.1f}/10",
            "Chowder": f"{chowder_number:.1f} (Obj: {chowder_target:.0f})" if chowder_number != -999.0 else "N/D",
            "Cotización Actual": f"{precio_actual / divisor_uk:.2f}{sym_m} ({dist_real_suelo:+.2f}%)",
            "Suelo (Infra)": f"{precio_compra / divisor_uk:.2f}{sym_m} ({pct_infra_vs_media:+.2f}%)" if precio_compra > 0 else "N/D",
            "Precio Justo": f"{precio_justo / divisor_uk:.2f}{sym_m}",
            "Techo (Sobre)": f"{precio_venta / divisor_uk:.2f}{sym_m} ({pct_sobre_vs_media:+.2f}%)" if precio_venta > 0 else "N/D",
            "Div. Neto": f"{div_neto_absoluto / divisor_uk:.2f}{sym_m}",
            "Yield Bruto": f"{yield_actual:.2f}%",
            "Yield Neto": f"{yield_neto:.2f}%",
            "PER": f"{per:.2f}" if per > 0 else "N/D",
            "P/FCF": f"{p_fcf:.2f}" if p_fcf != -1 else "N/D",
            "Payout FCF": f"{payout_fcf:.2f}%" if payout_fcf != -1 else "N/D",
            "Deuda/FCF": f"{deuda_fcf:.2f}A" if deuda_fcf != -1 else "N/D",
            "DGR 5A": f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D",
            "Años Pag.": f"{años_pagando}A (R: {racha_sin_recortes}A)",
            
            "_orden_estado": orden_est,
            "_Dist_Suelo": dist_real_suelo,
            "_score": score,
            "_y_act": yield_actual, "_y_inf": yield_infravalorado, "_y_med": yield_medio,
            "_per": per, "_p_fcf": p_fcf, "_pb": pb, 
            "_pay_bpa": payout_bpa, "_l_bpa": payout_lim_bpa, "_a_bpa": payout_ama_bpa,
            "_pay_fcf": payout_fcf, "_l_fcf": payout_lim_fcf, "_a_fcf": payout_ama_fcf,
            "_deuda": deuda_fcf,
            "_dgr": dgr_5y if dgr_5y is not None else -999,
            "_chowder": chowder_number, "_chowder_target": chowder_target
        }
    except:
        return None

# ==========================================
# 3. INTERFAZ EN PESTAÑAS (TABS PRINCIPALES)
# ==========================================
st.title("Sistema Fundamental — Método Geraldine Weiss")

tab_individual, tab_masiva, tab_cartera = st.tabs(["🔍 Análisis de Francotirador", "📑 Screener Múltiple (Radar)", "💼 Mi Cartera Privada"])

# --- PESTAÑA 1: ANÁLISIS INDIVIDUAL ---
with tab_individual:
    col_input1, col_input2, col_input3 = st.columns(3)
    with col_input1: ticker_input = st.text_input("Ticker individual:", "NVO").upper()
    with col_input2: años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)
    with col_input3: impuesto = st.number_input("Retención (%)", value=19.0, key="imp_ind")

    if st.button("Analizar Empresa"):
        with st.spinner(f"Analizando {ticker_input} en profundidad..."):
            try: screener_weiss_definitivo(ticker_input, años_analisis, impuesto)
            except Exception as e: st.error(f"Se ha producido un error: {e}")

# --- PESTAÑA 2: RADAR WATCHLIST ---
with tab_masiva:
    st.markdown("### 📡 Radar Fundamental por Lotes")
    st.markdown("Clasifica por **Estado de Compra** y prioriza internamente por **Calidad y Descuento al Suelo**.")
    
    watchlist_guardada = cargar_archivo_texto(ARCHIVO_WATCHLIST, "REP.MC, KHC, ENG.MC, DGE.L, PFE, BATS.L, RKT.L, TGT, WPC, HRL, BMY, O, RED.MC, CMCSA, EBRO.MC, LOG.MC, VZ, ACN, WKL.AS, VOW3.DE, PEP, KO, VICI, IIPR, HSY, MDLZ, UPS, GOOGL, UNH, GIS, ADP, LOW, MCD, VIS.MC, MC.PA, NKE, MKC, JNJ, PG")
    
    tickers_masivos = st.text_area("Lista de Tickers (editables y persistentes):", watchlist_guardada, height=100)
    
    col_w_btn, _ = st.columns([1, 4])
    with col_w_btn:
        if st.button("💾 Guardar Lista en Archivo"):
            if guardar_archivo_texto(ARCHIVO_WATCHLIST, tickers_masivos):
                st.success("Watchlist guardada en `watchlist.txt`.")
            else: st.error("Error al guardar.")

    col_m1, col_m2 = st.columns(2)
    with col_m1: años_masivos = st.selectbox("Periodo para canal histórico:", [5, 10, 12, 15, 20], index=2, key="años_mas")
    with col_m2: impuesto_masivo = st.number_input("Retención (%)", value=19.0, key="imp_mas")

    if st.button("🚀 Escanear Watchlist"):
        raw_list = tickers_masivos.replace("\n", ",").split(",")
        lista_tickers = [t.strip().upper() for t in raw_list if t.strip()]
        
        if len(lista_tickers) > 0:
            barra_progreso = st.progress(0)
            texto_estado = st.empty()
            resultados = []
            
            for idx, ticker in enumerate(lista_tickers):
                texto_estado.text(f"Escaneando {ticker} ({idx+1}/{len(lista_tickers)})...")
                datos = analizar_empresa_rapido(ticker, años_masivos, impuesto_masivo)
                if datos: resultados.append(datos)
                barra_progreso.progress((idx + 1) / len(lista_tickers))
            
            texto_estado.text("¡Escaneo masivo completado!")
            
            if resultados:
                df_res = pd.DataFrame(resultados)
                # Ordenación multinivel: Compra -> Mantener -> Sobrevalorada; y dentro por Score y Descuento
                df_res = df_res.sort_values(by=["_orden_estado", "_score", "_Dist_Suelo"], ascending=[True, False, True])
                
                def color_row(row):
                    styles = [''] * len(row)
                    est = row['Estado']
                    for idx, col_name in enumerate(row.index):
                        if col_name == 'Score Weiss':
                            if row['_score'] >= 8: styles[idx] = 'color: #21c354; font-weight: bold;'
                            elif row['_score'] >= 5: styles[idx] = 'color: #faca2b; font-weight: bold;'
                            else: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
                        elif col_name == 'Cotización Actual':
                            if "COMPRA" in est: styles[idx] = 'color: #21c354; font-weight: bold;'
                            elif "SOBREVALORADA" in est: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
                            else: styles[idx] = 'color: #faca2b; font-weight: bold;'
                        elif col_name == 'Suelo (Infra)': styles[idx] = 'color: #21c354;'
                        elif col_name == 'Precio Justo': styles[idx] = 'color: #faca2b;'
                        elif col_name == 'Techo (Sobre)': styles[idx] = 'color: #ff4b4b;'
                        elif col_name in ['Yield Bruto', 'Yield Neto', 'Div. Neto']:
                            if row['_y_act'] >= row['_y_inf']: styles[idx] = 'color: #21c354;'
                            elif row['_y_act'] >= row['_y_med']: styles[idx] = 'color: #faca2b;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'PER':
                            if 0 < row['_per'] <= 20: styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'P/FCF':
                            if 0 < row['_p_fcf'] <= 20: styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Payout FCF':
                            p = row['_pay_fcf']
                            if 0 <= p <= row['_l_fcf']: styles[idx] = 'color: #21c354;'
                            elif p <= row['_a_fcf']: styles[idx] = 'color: #faca2b;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Deuda/FCF':
                            d = row['_deuda']
                            if 0 <= d <= 3.0: styles[idx] = 'color: #21c354;'
                            elif d <= 5.0: styles[idx] = 'color: #faca2b;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Estado':
                            if "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: white;'
                            elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: white;'
                            else: styles[idx] = 'background-color: #4d4d00; color: white;'
                    return styles
                
                columnas_visibles = [c for c in df_res.columns if not c.startswith('_')]
                styled_df = df_res.style.apply(color_row, axis=1)
                st.dataframe(styled_df, column_order=columnas_visibles, use_container_width=True)
                
                csv = df_res[columnas_visibles].to_csv(index=False, sep=';', decimal=',').encode('utf-8')
                st.download_button(
                    label="💾 Descargar CSV para Google Sheets",
                    data=csv,
                    file_name=f"Screener_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No se pudieron recopilar canales históricos válidos para los tickers introducidos.")

# --- PESTAÑA 3: TU CARTERA PRIVADA ---
with tab_cartera:
    st.markdown("### 💼 Control de Rentabilidad y Añadas en Tiempo Real")
    st.markdown("> *Privacidad garantizada: Procesamiento seguro en tu navegador y servidor local.*")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        metodo_carga = st.radio("¿Cómo quieres cargar tu cartera?", ["📝 Pegar / Editar Texto", "📂 Subir Archivo"])
    with col_c2:
        impuesto_cart = st.number_input("Retención media de dividendos (%)", value=19.0, key="imp_cart_3")
    
    df_ops = None
    texto_guardado = cargar_archivo_texto(ARCHIVO_CARTERA, "Fecha,Ticker,Operacion,Acciones,Precio\n")
    
    if metodo_carga == "📂 Subir Archivo":
        archivo_subido = st.file_uploader("Sube tu historial de operaciones (CSV o Excel)", type=["csv", "xlsx"])
        if archivo_subido is not None:
            try:
                if archivo_subido.name.endswith('.xlsx'):
                    df_ops = pd.read_excel(archivo_subido, dtype=str)
                else:
                    df_ops = pd.read_csv(archivo_subido, sep=None, engine='python', dtype=str)
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")
    else:
        st.info("Pega tu historial. Encabezados necesarios: Fecha, Ticker, Operacion, Acciones, Precio (admite comas, puntos y tabuladores de Excel).")
        texto_csv = st.text_area("Pega aquí tus transacciones:", value=texto_guardado, height=140)
        col_btn_cart, _ = st.columns([1, 4])
        with col_btn_cart:
            if st.button("💾 Guardar Cartera Localmente"):
                if guardar_archivo_texto(ARCHIVO_CARTERA, texto_csv):
                    st.success("Cartera guardada en `cartera.csv`.")
                else: st.error("Error al guardar.")
        if texto_csv and texto_csv.strip():
            try:
                df_ops = pd.read_csv(io.StringIO(texto_csv.strip()), sep=None, engine='python', dtype=str)
            except Exception as e:
                st.error(f"Error al leer el texto: {e}")

    if df_ops is not None and not df_ops.empty:
        try:
            # Mapeo universal de nombres de columnas
            col_map = {}
            for col in df_ops.columns:
                c_clean = col.strip().lower()
                if 'fech' in c_clean: col_map[col] = 'Fecha'
                elif 'tick' in c_clean or 'empresa' in c_clean: col_map[col] = 'Ticker'
                elif 'oper' in c_clean or 'tipo' in c_clean: col_map[col] = 'Operacion'
                elif 'acc' in c_clean or 'cant' in c_clean or 'titul' in c_clean: col_map[col] = 'Acciones'
                elif 'prec' in c_clean or 'cost' in c_clean: col_map[col] = 'Precio'
            df_ops = df_ops.rename(columns=col_map)

            columnas_requeridas = ['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio']
            if not all(col in df_ops.columns for col in columnas_requeridas):
                st.error(f"❌ Error de formato. Faltan encabezados obligatorios: {', '.join(columnas_requeridas)}")
            else:
                # Limpieza universal de comas decimales europeas
                df_ops['Acciones'] = df_ops['Acciones'].apply(limpiar_numero_europeo)
                df_ops['Precio'] = df_ops['Precio'].apply(limpiar_numero_europeo)
                df_ops['Fecha'] = pd.to_datetime(df_ops['Fecha'], errors='coerce', dayfirst=True)
                df_ops['Ticker'] = df_ops['Ticker'].astype(str).str.strip().str.upper()
                df_ops['Operacion'] = df_ops['Operacion'].astype(str).str.strip().str.capitalize()
                
                df_ops = df_ops.dropna(subset=['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio'])
                df_ops = df_ops[df_ops['Acciones'] > 0]
                df_ops = df_ops.sort_values('Fecha')
                
                if df_ops.empty:
                    st.warning("No hay filas con acciones mayores que 0 registradas.")
                else:
                    df_ops_global = df_ops.copy()
                    tickers_global = sorted(df_ops_global['Ticker'].unique().tolist())
                    
                    años_unicos = sorted(df_ops['Fecha'].dt.year.dropna().unique())
                    opciones_año = ["Todo el Historial"] + [str(int(a)) for a in años_unicos]
                    opciones_ticker = ["Todas las Empresas"] + tickers_global
                    
                    st.markdown("---")
                    st.markdown("#### 🎯 Filtros Analíticos de Cartera")
                    col_f1, col_f2 = st.columns(2)
                    with col_f1: año_filtro = st.selectbox("📅 Selecciona Año de Compra (Modo Añada):", opciones_año)
                    with col_f2: ticker_filtro = st.selectbox("🏢 Selecciona Empresa a Inspeccionar:", opciones_ticker)
                    
                    if año_filtro != "Todo el Historial": 
                        df_ops = df_ops[(df_ops['Fecha'].dt.year == int(año_filtro)) & (df_ops['Operacion'] == 'Compra')]
                    if ticker_filtro != "Todas las Empresas": 
                        df_ops = df_ops[df_ops['Ticker'] == ticker_filtro]
                    
                    if df_ops.empty:
                        st.warning("No hay operaciones válidas con los filtros seleccionados.")
                    else:
                        min_date = df_ops_global['Fecha'].min()
                        tickers_unicos = df_ops['Ticker'].unique().tolist()
                        
                        dict_historicos = {}
                        dict_dividendos = {}
                        dict_forward_div = {}
                        
                        with st.spinner("Descargando precios reales, dividendos y tipos de cambio..."):
                            for t in tickers_global:
                                try:
                                    tk = yf.Ticker(t)
                                    hist = tk.history(start=min_date, auto_adjust=False)
                                    if not hist.empty:
                                        hist.index = hist.index.tz_localize(None).normalize()
                                        hist = hist[~hist.index.duplicated(keep='last')]
                                        
                                        if 'Dividends' in hist.columns and hist['Dividends'].sum() > 0:
                                            divs_finales = hist['Dividends']
                                        else:
                                            divs_reales = tk.dividends
                                            if not divs_reales.empty:
                                                divs_reales.index = divs_reales.index.tz_localize(None).normalize()
                                                divs_reales = divs_reales[~divs_reales.index.duplicated(keep='last')]
                                                divs_finales = divs_reales[divs_reales.index >= min_date]
                                            else:
                                                divs_finales = pd.Series(dtype=float)
                                                
                                        es_uk = tk.info.get('currency') == 'GBp'
                                        if es_uk: 
                                            hist['Close'] = hist['Close'] / 100.0
                                            if not divs_finales.empty: divs_finales = divs_finales / 100.0
                                            
                                        dict_historicos[t] = hist['Close']
                                        dict_dividendos[t] = divs_finales
                                        
                                        # Forward dividend para YoC y Yield Actual
                                        f_div = tk.info.get('dividendRate', tk.info.get('trailingAnnualDividendRate', 0.0))
                                        if f_div is None or f_div == 0.0:
                                            f_div = divs_finales.tail(4).sum() if len(divs_finales) >= 4 else (divs_finales.iloc[-1] * 4 if not divs_finales.empty else 0.0)
                                        if es_uk and f_div > 0: f_div = f_div / 100.0
                                        dict_forward_div[t] = f_div
                                except: pass
                                    
                        if dict_historicos:
                            datos_historicos = pd.DataFrame(dict_historicos)
                            datos_dividendos = pd.DataFrame(dict_dividendos)
                            rango_fechas = pd.date_range(start=min_date.normalize(), end=pd.Timestamp.today().normalize())
                            datos_historicos = datos_historicos.reindex(rango_fechas).ffill().fillna(0)
                            datos_dividendos = datos_dividendos.reindex(rango_fechas).fillna(0)
                            
                            # ==========================================
                            # 1. LÓGICA LOCAL (FILTRADA POR MODO AÑADA)
                            # ==========================================
                            daily_shares = pd.DataFrame(0.0, index=datos_historicos.index, columns=tickers_unicos)
                            daily_invested = pd.Series(0.0, index=datos_historicos.index)
                            
                            current_shares = {t: 0.0 for t in tickers_unicos}
                            current_cost = {t: 0.0 for t in tickers_unicos}
                            total_invested = 0.0
                            
                            for date in datos_historicos.index:
                                ops_today = df_ops[df_ops['Fecha'].dt.date == date.date()]
                                for _, row in ops_today.iterrows():
                                    t, op, acc, precio = row['Ticker'], row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                    if op == 'Compra':
                                        current_shares[t] += acc; coste = acc * precio; current_cost[t] += coste; total_invested += coste
                                    elif op == 'Venta' and current_shares.get(t, 0) > 0:
                                        pmp = current_cost[t] / current_shares[t]
                                        current_shares[t] -= acc; coste_red = acc * pmp; current_cost[t] -= coste_red; total_invested -= coste_red
                                for t in tickers_unicos: daily_shares.at[date, t] = current_shares.get(t, 0.0)
                                daily_invested.at[date] = total_invested
                                
                            daily_value = (daily_shares * datos_historicos[tickers_unicos]).sum(axis=1)
                            daily_shares_shifted = daily_shares.shift(1).fillna(0)
                            daily_net_divs = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=1) * (1 - (impuesto_cart / 100.0))
                            accumulated_divs = daily_net_divs.cumsum()
                            total_patrimonio = daily_value + accumulated_divs
                            
                            st.markdown("#### 📈 Evolución de tu Patrimonio")
                            fig_cartera = go.Figure()
                            fig_cartera.add_trace(go.Scatter(x=daily_invested.index, y=daily_invested.values, mode='lines', line=dict(color='#faca2b', width=2, dash='dash'), name='Capital Aportado'))
                            fig_cartera.add_trace(go.Scatter(x=daily_value.index, y=daily_value.values, mode='lines', line=dict(color='#21c354', width=2), name='Valor Mercado'))
                            fig_cartera.add_trace(go.Scatter(x=accumulated_divs.index, y=accumulated_divs.values, fill='tozeroy', mode='lines', line=dict(color='#00d4ff', width=2), fillcolor='rgba(0, 212, 255, 0.15)', name='Divs Netos Acumulados'))
                            fig_cartera.add_trace(go.Scatter(x=total_patrimonio.index, y=total_patrimonio.values, mode='lines', line=dict(color='#e040fb', width=2.5), name='Patrimonio Total'))
                            fig_cartera.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=420, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
                            st.plotly_chart(fig_cartera, use_container_width=True)

                            posiciones_activas = {t: current_shares[t] for t in tickers_unicos if current_shares[t] > 0.001}
                            if posiciones_activas:
                                fx_rates_hoy = {'EUR': 1.0, 'USD': 1.0, 'GBP': 1.0, 'GBp': 1.0}
                                historico_fx = {}
                                try:
                                    fx_usd = yf.Ticker("EURUSD=X").history(start=min_date)['Close']; fx_usd.index = fx_usd.index.tz_localize(None).normalize(); historico_fx['USD'] = fx_usd; fx_rates_hoy['USD'] = float(fx_usd.iloc[-1]) if not fx_usd.empty else 1.0
                                    fx_gbp = yf.Ticker("EURGBP=X").history(start=min_date)['Close']; fx_gbp.index = fx_gbp.index.tz_localize(None).normalize(); historico_fx['GBP'] = fx_gbp; historico_fx['GBp'] = fx_gbp; fx_rates_hoy['GBP'] = float(fx_gbp.iloc[-1]) if not fx_gbp.empty else 1.0; fx_rates_hoy['GBp'] = fx_rates_hoy['GBP']
                                except: pass

                                def get_fx_hist(divisa, fecha):
                                    if divisa == 'EUR': return 1.0
                                    serie = historico_fx.get(divisa)
                                    if serie is not None and not serie.empty:
                                        fecha_norm = pd.Timestamp(fecha).normalize()
                                        if fecha_norm in serie.index: return float(serie.loc[fecha_norm])
                                        idx = serie.index.get_indexer([fecha_norm], method='pad')[0]
                                        if idx != -1: return float(serie.iloc[idx])
                                    return fx_rates_hoy.get(divisa, 1.0)
                                    
                                divs_per_ticker = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=0) * (1 - (impuesto_cart / 100.0))
                                resultados_tabla, global_inversion_eur, global_mercado_eur, global_divs_eur = [], 0.0, 0.0, 0.0
                                total_div_anual_eur = 0.0
                                
                                for t, acc in posiciones_activas.items():
                                    try: curr = yf.Ticker(t).info.get('currency', 'USD')
                                    except: curr = 'USD'
                                    fx_hoy = fx_rates_hoy.get(curr, 1.0)
                                    p_actual = datos_historicos[t].iloc[-1]
                                    p_medio = current_cost[t] / acc if acc > 0 else 0
                                    
                                    coste_eur_total, acc_acumuladas = 0.0, 0.0
                                    ops_t = df_ops[df_ops['Ticker'] == t].sort_values('Fecha')
                                    for _, row in ops_t.iterrows():
                                        op, a, p = row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                        if curr == 'GBp': p = p / 100.0
                                        fx_d = get_fx_hist(curr, row['Fecha'])
                                        if op == 'Compra': acc_acumuladas += a; coste_eur_total += (a * p) / fx_d
                                        elif op == 'Venta' and acc_acumuladas > 0: pmp_eur = coste_eur_total / acc_acumuladas; acc_acumuladas -= a; coste_eur_total -= (a * pmp_eur)
                                            
                                    if coste_eur_total <= 0: coste_eur_total = (current_cost[t] / fx_hoy) if fx_hoy > 0 else current_cost[t]
                                    
                                    v_mercado_orig, divs_orig = acc * p_actual, divs_per_ticker[t]
                                    b_abs_orig = v_mercado_orig - current_cost[t]
                                    b_total_orig = b_abs_orig + divs_orig
                                    
                                    rent_precio_orig = (b_abs_orig / current_cost[t]) * 100 if current_cost[t] > 0 else 0
                                    rent_total_orig = (b_total_orig / current_cost[t]) * 100 if current_cost[t] > 0 else 0
                                    
                                    v_mercado_eur, divs_eur = v_mercado_orig / fx_hoy, divs_orig / fx_hoy
                                    b_abs_eur = v_mercado_eur - coste_eur_total
                                    b_total_eur = b_abs_eur + divs_eur
                                    
                                    rent_precio_eur = (b_abs_eur / coste_eur_total) * 100 if coste_eur_total > 0 else 0
                                    rent_total_eur = (b_total_eur / coste_eur_total) * 100 if coste_eur_total > 0 else 0
                                    
                                    global_inversion_eur += coste_eur_total; global_mercado_eur += v_mercado_eur; global_divs_eur += divs_eur
                                    sym_divisa = "€" if curr == "EUR" else ("£" if curr in ["GBP", "GBp"] else "$")
                                    
                                    # Rendimientos DGI (YoC y Yield Actual)
                                    div_anual_unitario = dict_forward_div.get(t, 0.0)
                                    yoc_bruto = (div_anual_unitario / p_medio * 100) if p_medio > 0 else 0.0
                                    yoc_neto = yoc_bruto * (1 - (impuesto_cart / 100.0))
                                    yield_act_bruto = (div_anual_unitario / p_actual * 100) if p_actual > 0 else 0.0
                                    yield_act_neto = yield_act_bruto * (1 - (impuesto_cart / 100.0))
                                    
                                    total_div_anual_eur += (acc * div_anual_unitario) / fx_hoy
                                    
                                    resultados_tabla.append({
                                        "Ticker": t, "Acciones": round(acc, 4), 
                                        "Precio Medio": f"{p_medio:.2f} {sym_divisa}", "Precio Actual": f"{p_actual:.2f} {sym_divisa}", 
                                        "Valor Mercado": v_mercado_orig, "P/L Latente": b_abs_orig, "Divs. Cobrados": divs_orig, "Bº Total (Abs)": b_total_orig, 
                                        "Rent. Precio (€)": rent_precio_eur, "Rent. Total (€)": rent_total_eur, 
                                        "YoC Bruto": yoc_bruto, "YoC Neto": yoc_neto,
                                        "Yield Act. Bruto": yield_act_bruto, "Yield Act. Neto": yield_act_neto
                                    })
                                
                                b_l_mercado_eur = global_mercado_eur - global_inversion_eur
                                b_total_global_eur = b_l_mercado_eur + global_divs_eur
                                
                                yoc_global_bruto = (total_div_anual_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                                yoc_global_neto = yoc_global_bruto * (1 - (impuesto_cart / 100.0))
                                yield_global_bruto = (total_div_anual_eur / global_mercado_eur * 100) if global_mercado_eur > 0 else 0.0
                                yield_global_neto = yield_global_bruto * (1 - (impuesto_cart / 100.0))
                                
                                st.markdown("#### 🌐 Resumen Global Hoy (Convertido a Euros €)")
                                c1, c2, c3, c4, c5 = st.columns(5)
                                c1.metric("Capital Invertido", f"{global_inversion_eur:,.2f} €")
                                c2.metric("Valor Mercado", f"{global_mercado_eur:,.2f} €", f"{(b_l_mercado_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0:+.2f}%")
                                c3.metric("Dividendos Cobrados", f"{global_divs_eur:,.2f} €", f"{(global_divs_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0:+.2f}% del Cap")
                                c4.metric("YoC (s/ Coste)", f"{yoc_global_neto:.2f}% Neto", f"Bruto: {yoc_global_bruto:.2f}%")
                                c5.metric("Yield Actual", f"{yield_global_neto:.2f}% Neto", f"Bruto: {yield_global_bruto:.2f}%")
                                
                                st.markdown("#### 📋 Posiciones Abiertas (Con Rendimientos Brutos y Netos)")
                                resultados_tabla_ordenados = sorted(resultados_tabla, key=lambda k: k['Rent. Total (€)'], reverse=True)
                                df_mostrar = pd.DataFrame(resultados_tabla_ordenados)
                                styled_df = df_mostrar.style.format({
                                    "Valor Mercado": "{:,.2f}", "P/L Latente": "{:+.2f}", "Divs. Cobrados": "{:,.2f}", "Bº Total (Abs)": "{:+.2f}", 
                                    "Rent. Precio (€)": "{:+.2f}%", "Rent. Total (€)": "{:+.2f}%",
                                    "YoC Bruto": "{:.2f}%", "YoC Neto": "{:.2f}%",
                                    "Yield Act. Bruto": "{:.2f}%", "Yield Act. Neto": "{:.2f}%"
                                }).map(lambda val: f"color: {'#21c354' if val > 0 else '#ff4b4b'}; font-weight: bold;", subset=['P/L Latente', 'Bº Total (Abs)', 'Rent. Precio (€)', 'Rent. Total (€)']).map(lambda val: f"color: {'#00d4ff' if val > 0 else '#aaaaaa'};", subset=['Divs. Cobrados']).map(lambda val: "color: #faca2b; font-weight: bold;", subset=['YoC Neto'])
                                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                                
                                # Gráfico comparativo de rendimientos de la selección
                                st.markdown("#### 📊 YoC vs Yield Actual por Empresa (Selección Actual)")
                                fig_yocs = go.Figure()
                                tickers_bars = [r['Ticker'] for r in resultados_tabla_ordenados]
                                fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['YoC_Bruto'] for r in resultados_tabla_ordenados], name='YoC Bruto', marker_color='#faca2b'))
                                fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['YoC_Neto'] for r in resultados_tabla_ordenados], name='YoC Neto', marker_color='#ff9800'))
                                fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['Yield_Act. Bruto'] for r in resultados_tabla_ordenados], name='Yield Act. Bruto', marker_color='#00d4ff'))
                                fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['Yield_Act. Neto'] for r in resultados_tabla_ordenados], name='Yield Act. Neto', marker_color='#0088cc'))
                                fig_yocs.update_layout(barmode='group', template='plotly_dark', height=350, margin=dict(l=0, r=0, t=20, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
                                st.plotly_chart(fig_yocs, use_container_width=True)

                                df_divs_hist = pd.DataFrame({'Fecha': daily_net_divs.index, 'Dividendo': daily_net_divs.values})
                                df_divs_hist = df_divs_hist[df_divs_hist['Dividendo'] > 0]
                                if not df_divs_hist.empty:
                                    st.markdown("---")
                                    st.markdown("#### 🗓️ Calendario Histórico de Dividendos Netos")
                                    df_divs_hist['Año'], df_divs_hist['Mes'] = df_divs_hist['Fecha'].dt.year, df_divs_hist['Fecha'].dt.month
                                    agrup_meses = df_divs_hist.groupby(['Año', 'Mes'])['Dividendo'].sum().reset_index()
                                    anual_divs = df_divs_hist.groupby('Año')['Dividendo'].sum().reset_index()
                                    anual_divs['Crec. YoY (%)'] = anual_divs['Dividendo'].pct_change() * 100
                                    
                                    col_c1, col_c2 = st.columns([2.5, 1])
                                    with col_c1:
                                        st.markdown("##### 📊 Ingresos Mensuales (Comparativa Anual)")
                                        fig_meses = go.Figure()
                                        meses_str = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                                        for año in sorted(agrup_meses['Año'].unique()):
                                            d_a = agrup_meses[agrup_meses['Año'] == año]
                                            fig_meses.add_trace(go.Bar(x=list(meses_str.values()), y=[d_a[d_a['Mes'] == m]['Dividendo'].values[0] if not d_a[d_a['Mes'] == m].empty else 0.0 for m in range(1, 13)], name=str(año)))
                                        fig_meses.update_layout(barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
                                        st.plotly_chart(fig_meses, use_container_width=True)
                                    with col_c2:
                                        st.markdown("##### 📝 Resumen YoY")
                                        st.dataframe(anual_divs.style.format({'Dividendo': '{:,.2f} €', 'Crec. YoY (%)': '{:+.2f}%'}).map(lambda v: f"color: {'#21c354' if v>0 else ('#ff4b4b' if v<0 else '#aaaaaa')}; font-weight: bold;" if pd.notna(v) else "", subset=['Crec. YoY (%)']), use_container_width=True, hide_index=True)
                                    
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    st.markdown("##### 📈 Evolución Anual (Efecto Bola de Nieve)")
                                    fig_anual = go.Figure(go.Bar(x=anual_divs['Año'].astype(str), y=anual_divs['Dividendo'], name='Total Cobrado', marker_color='#00d4ff', text=[f"{val:,.2f} €" for val in anual_divs['Dividendo']], textposition='auto'))
                                    fig_anual.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title="Dividendos Netos Totales (€)"))
                                    st.plotly_chart(fig_anual, use_container_width=True)

                            # ==========================================
                            # 2. RADIOGRAFÍA ANUAL (FOTO FIJA GLOBAL)
                            # ==========================================
                            st.markdown("---")
                            st.markdown("### 📸 Radiografía del Año Natural (Toda la Cartera)")
                            st.markdown("> *Muestra cómo se comportó **toda tu cartera real** desde el 1 de enero hasta el 31 de diciembre del año seleccionado.*")
                            
                            año_minimo = int(df_ops_global['Fecha'].dt.year.min())
                            año_actual_num = int(pd.Timestamp.today().year)
                            opciones_radio = [str(a) for a in range(año_minimo, año_actual_num + 1)]
                            
                            año_radio = st.selectbox("Selecciona Año a Inspeccionar:", opciones_radio, index=len(opciones_radio)-1, key="año_rad")
                            
                            if año_radio:
                                año_int = int(año_radio)
                                
                                daily_shares_g = pd.DataFrame(0.0, index=datos_historicos.index, columns=tickers_global)
                                daily_invested_g = pd.Series(0.0, index=datos_historicos.index)
                                
                                curr_sh_g = {t: 0.0 for t in tickers_global}
                                curr_c_g = {t: 0.0 for t in tickers_global}
                                tot_inv_g = 0.0
                                
                                for date in datos_historicos.index:
                                    ops_today = df_ops_global[df_ops_global['Fecha'].dt.date == date.date()]
                                    for _, row in ops_today.iterrows():
                                        t, op, acc, precio = row['Ticker'], row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                        if op == 'Compra':
                                            curr_sh_g[t] += acc; curr_c_g[t] += (acc * precio); tot_inv_g += (acc * precio)
                                        elif op == 'Venta' and curr_sh_g.get(t, 0) > 0:
                                            pmp = curr_c_g[t] / curr_sh_g[t]; curr_sh_g[t] -= acc; curr_c_g[t] -= (acc * pmp); tot_inv_g -= (acc * pmp)
                                    for t in tickers_global: daily_shares_g.at[date, t] = curr_sh_g.get(t, 0.0)
                                    daily_invested_g.at[date] = tot_inv_g
                                    
                                daily_value_g = (daily_shares_g * datos_historicos[tickers_global]).sum(axis=1)
                                daily_net_divs_g = (daily_shares_g.shift(1).fillna(0) * datos_dividendos[tickers_global]).sum(axis=1) * (1 - (impuesto_cart / 100.0))
                                
                                mask_y = daily_invested_g.index.year == año_int
                                di_y = daily_invested_g[mask_y]
                                dv_y = daily_value_g[mask_y]
                                dd_y = daily_net_divs_g[mask_y]
                                
                                if not di_y.empty:
                                    acc_divs_y = dd_y.cumsum()
                                    tot_pat_y = dv_y + acc_divs_y
                                    
                                    inv_ini, inv_fin = di_y.iloc[0], di_y.iloc[-1]
                                    val_ini, val_fin = dv_y.iloc[0], dv_y.iloc[-1]
                                    div_tot = acc_divs_y.iloc[-1]
                                    
                                    aportaciones = inv_fin - inv_ini
                                    b_mercado = (val_fin - val_ini) - aportaciones
                                    b_total = b_mercado + div_tot
                                    
                                    base_pct = val_ini + aportaciones if (val_ini + aportaciones) > 0 else 1.0
                                    
                                    def fmt_es(num, signo=False):
                                        if pd.isna(num): return "0,00"
                                        s = f"{num:+,.2f}" if signo else f"{num:,.2f}"
                                        return s.replace(",", "X").replace(".", ",").replace("X", ".")
                                    
                                    c1, c2, c3, c4 = st.columns(4)
                                    c1.metric(f"Valor Base ({año_radio})", f"{fmt_es(base_pct)} €", f"Aportación nueva: {fmt_es(aportaciones, True)} €")
                                    c2.metric("P/L de Mercado", f"{fmt_es(b_mercado, True)} €", f"{(b_mercado/base_pct)*100:+.2f}%")
                                    c3.metric("Dividendos Netos", f"{fmt_es(div_tot)} €", f"{(div_tot/base_pct)*100:+.2f}% s/ Base")
                                    c4.metric("Beneficio Total", f"{fmt_es(b_total, True)} €", f"{(b_total/base_pct)*100:+.2f}%")
                                    
                                    fig_y = go.Figure()
                                    fig_y.add_trace(go.Scatter(x=di_y.index, y=di_y.values, mode='lines', line=dict(color='#faca2b', width=2, dash='dash'), name='Capital Global Invertido'))
                                    fig_y.add_trace(go.Scatter(x=dv_y.index, y=dv_y.values, mode='lines', line=dict(color='#21c354', width=2), name='Valor Mercado'))
                                    fig_y.add_trace(go.Scatter(x=acc_divs_y.index, y=acc_divs_y.values, fill='tozeroy', mode='lines', line=dict(color='#00d4ff', width=2), fillcolor='rgba(0, 212, 255, 0.15)', name=f'Divs Acumulados ({año_radio})'))
                                    fig_y.add_trace(go.Scatter(x=tot_pat_y.index, y=tot_pat_y.values, mode='lines', line=dict(color='#e040fb', width=2.5), name='Patrimonio Total'))
                                    fig_y.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=380, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
                                    st.plotly_chart(fig_y, use_container_width=True)
                                    
                                    st.markdown(f"#### 📊 Cobros Mensuales en {año_radio}")
                                    df_d_y = pd.DataFrame({'Fecha': dd_y.index, 'Dividendo': dd_y.values})
                                    df_d_y = df_d_y[df_d_y['Dividendo'] > 0]
                                    if not df_d_y.empty:
                                        df_d_y['Mes'] = df_d_y['Fecha'].dt.month
                                        agrup_m = df_d_y.groupby('Mes')['Dividendo'].sum()
                                        y_vals = [agrup_m.get(m, 0.0) for m in range(1, 13)]
                                        text_vals = [f"{fmt_es(v)} €" if v > 0 else "" for v in y_vals]
                                        
                                        fig_d = go.Figure(go.Bar(x=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'], y=y_vals, marker_color='#00d4ff', text=text_vals, textposition='auto'))
                                        fig_d.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=300, yaxis_title="Dividendos Netos (€)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                                        st.plotly_chart(fig_d, use_container_width=True)
                                    else:
                                        st.info(f"No se cobraron dividendos en {año_radio}.")
        except Exception as e:
            st.error(f"No se pudo procesar la cartera. Detalle: {e}")
