import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Ignorar advertencias menores
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Analizar Empresa - Weiss DGI", page_icon="🔍", layout="wide")

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

    # --- LÓGICA DE DETECCIÓN Y TRADUCCIÓN SEGURA ---
    sector_en = info.get('sector', 'Desconocido')
    industry_en = info.get('industry', 'Desconocido')
    pais = info.get('country', 'Desconocido')
    
    sector_final = TRADUCCION.get(sector_en, sector_en)
    industry_final = industry_en 

    es_regulada_o_reit = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower() or 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_tecnologica = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower()
    es_industrial = 'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()
    
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()

    payout_limite_bpa = 80.0 if es_regulada_o_reit else 60.0
    payout_amarillo_bpa = 85.0 if es_regulada_o_reit else 75.0
    payout_limite_fcf = 85.0 if es_regulada_o_reit else 75.0
    payout_amarillo_fcf = 92.0 if es_regulada_o_reit else 85.0

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

    # --- FUNDAMENTALES Y MÉTRICAS ---
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
    total_debt = get_safe('totalDebt', 0.0)
    total_cash = get_safe('totalCash', 0.0)
    ebitda = get_safe('ebitda', 0.0)
    respaldo_institucional = get_safe('heldPercentInstitutions') * 100
    payout_forward = (forward_dividend / bpa_forward) * 100 if bpa_forward > 0 else -1

    # Deuda Neta / EBITDA Operativa
    deuda_neta = max(0.0, total_debt - total_cash)
    if ebitda > 0:
        deuda_ebitda = deuda_neta / ebitda
    else:
        deuda_ebitda = 999.0 if total_debt > 0 else 0.0

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
            eps_data = inc_stmt.loc['Diluted EPS'].dropna() if 'Diluted EPS' in inc_stmt.index else inc_stmt.loc['Basic EPS'].dropna()
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

    # === INICIO CÁLCULO DE ACCIONES ===
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
    # === FIN CÁLCULO DE ACCIONES ===

    if yield_infravalorado > 0: precio_compra = (forward_dividend / yield_infravalorado) * 100
    else: precio_compra = 0
    if yield_medio > 0: precio_justo = (forward_dividend / yield_medio) * 100
    else: precio_justo = 0
    if yield_sobrevalorado > 0: precio_venta = (forward_dividend / yield_sobrevalorado) * 100
    else: precio_venta = 0

    if precio_justo > 0:
        pct_actual_vs_media = ((precio_actual - precio_justo) / precio_justo) * 100
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100
    else:
        pct_actual_vs_media = pct_infra_vs_media = pct_sobre_vs_media = 0

    if pct_actual_vs_media <= 0:
        txt_extra_actual = f"Descuento: {abs(pct_actual_vs_media):.1f}% vs Media"
    else:
        txt_extra_actual = f"Sobreprecio: +{pct_actual_vs_media:.1f}% vs Media"
    
    txt_extra_infra = f"Suelo: {pct_infra_vs_media:.1f}% vs Media"
    txt_extra_justo = f"Ancla ({años_analisis}A)"
    txt_extra_sobre = f"Techo: +{pct_sobre_vs_media:.1f}% vs Media"

    # ==========================================
    # CÁLCULO DUAL DGI MODERNO (CALIDAD Y VALORACIÓN)
    # ==========================================
    
    # 1. SCORE DE CALIDAD DGI (0 a 10 Pts)
    score_calidad = 0.0

    lim_deuda_optima = 4.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 3.0
    lim_deuda_aceptable = 5.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0
    if deuda_ebitda <= lim_deuda_optima: pts_deuda = 2.5
    elif deuda_ebitda <= lim_deuda_aceptable: pts_deuda = 1.5
    else: pts_deuda = 0.0
    score_calidad += pts_deuda

    if 0 <= payout_fcf <= payout_limite_fcf: pts_fcf = 2.5
    elif payout_fcf <= payout_amarillo_fcf: pts_fcf = 1.25
    else: pts_fcf = 0.0
    score_calidad += pts_fcf

    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: pts_hist = 2.0
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: pts_hist = 1.25
    elif racha_sin_recortes >= 5: pts_hist = 0.75
    else: pts_hist = 0.0
    score_calidad += pts_hist

    if dgr_5y is not None and dgr_5y >= 5.0: pts_dgr = 1.5
    elif dgr_5y is not None and dgr_5y >= 2.5: pts_dgr = 0.75
    else: pts_dgr = 0.0
    score_calidad += pts_dgr

    cond_recompras = variacion_acciones is not None and variacion_acciones < -0.5
    cond_bpa_pos = crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0
    pts_cap = 1.5 if (cond_recompras or cond_bpa_pos) else 0.0
    score_calidad += pts_cap

    # 2. SCORE DE VALORACIÓN DGI (0 a 10 Pts)
    score_val = 0.0

    if yield_actual >= yield_infravalorado: pts_yield = 4.0
    elif yield_actual >= yield_medio: pts_yield = 2.5
    else: pts_yield = 0.0
    score_val += pts_yield

    if 0 < p_fcf <= 20.0: pts_pfcf = 2.5
    elif 0 < p_fcf <= 25.0: pts_pfcf = 1.25
    else: pts_pfcf = 0.0
    score_val += pts_pfcf

    if 0 < per <= 20.0: pts_per = 2.0
    elif 0 < per <= 25.0: pts_per = 1.0
    else: pts_per = 0.0
    score_val += pts_per

    # Regla de Chowder
    if (es_utility_pura or es_telecom) and yield_actual > 4.0:
        chowder_target = 8.0
    elif yield_actual >= 3.0:
        chowder_target = 12.0
    else:
        chowder_target = 15.0

    precio_obj_chowder = None
    yield_req_chowder = None
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        chowder_pass = chowder_number >= chowder_target
        yield_req_chowder = chowder_target - dgr_5y
        if yield_req_chowder > 0:
            precio_obj_chowder = (forward_dividend / yield_req_chowder) * 100
        pts_chowder = 1.5 if chowder_pass else 0.0
    else:
        chowder_number = None
        chowder_pass = False
        pts_chowder = 0.0
    score_val += pts_chowder

    # ==========================================
    # INTERFAZ VISUAL STREAMLIT
    # ==========================================
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
        st.success(f"✅ **{pais}**: Retención en origen del 15%. Al coincidir con el máximo deducible en España por doble imposición internacional, es 100% recuperable automáticamente en tu declaración de la Renta.")
    elif pais == 'United Kingdom': 
        st.success(f"✅ **{pais}**: Retención en origen del 0% (salvo algunos REITs). Eficiencia fiscal óptima en origen, solo tributas el impuesto local configurado.")
    elif pais == 'Spain': 
        st.success(f"✅ **{pais}**: Mercado local. Retención directa del {impuesto_pct}%. Sin trámites ni retenciones en el extranjero.")
    elif pais == 'Denmark':
        st.warning(f"⚠️ **{pais} (Novo Nordisk, etc.)**: Retención estándar en origen muy elevada del 27%. El convenio con España limita la retención final al 15% (que recuperas en tu Renta). El **12% restante se queda retenido en Dinamarca** y exige un trámite de reclamación directa ante su hacienda (*Skat*).")
    elif pais == 'Switzerland':
        st.error(f"❌ **{pais}**: Retención en origen extrema del 35%. El convenio te permite deducir el 15% en España, pero el **20% sobrante queda bloqueado en Suiza** a menos que inicies el complejo proceso burocrático de devolución internacional (Formulario 81).")
    elif pais == 'Germany':
        st.error(f"❌ **{pais}**: Retención en origen del 26.375% (incluye el impuesto de solidaridad). Recuperas el 15% en España de forma automática, pero el **11.375% restante se pierde** si no reclamas su devolución rellenando los formularios de la hacienda federal alemana (*BZSt*).")
    elif pais == 'France':
        st.error(f"❌ **{pais}**: Retención estándar en origen del 25% (puede reducirse al 12.8% si tu bróker tramita los formularios de residencia previos). De lo contrario, tendrás que reclamar el exceso por encima del 15% a la hacienda francesa.")
    elif pais == 'Ireland': 
        st.warning(f"⚠️ **{pais}**: Retención en origen del 25%. Puedes deducir el 15% en España, pero el **10% restante exige trámites complejos** de devolución en origen según las capacidades de tu bróker.")
    else: 
        st.info(f"ℹ️ **{pais}**: Verifica el convenio de doble imposición internacional vigente y las tasas de retención actuales para residentes españoles.")

    st.subheader(f"🎯 Precios Objetivo y Valoración Actual (Basado en {años_analisis} Años)")
    
    if precio_actual <= precio_compra: color_actual = "#21c354" 
    elif precio_actual >= precio_venta: color_actual = "#ff4b4b" 
    else: color_actual = "#faca2b" 

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
    
    # --- LOS 2 RÁNKINGS DGI INDEPENDIENTES (CALIDAD + VALORACIÓN) ---
    col_sc1, col_sc2 = st.columns(2)
    with col_sc1:
        if score_calidad >= 8.0: 
            st.success(f"🛡️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Sobresaliente. Fuerte generación de caja, balance solvente y resiliencia.")
        elif score_calidad >= 6.0: 
            st.warning(f"⚖️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Aceptable. Solidez con algún reto operativo o ciclo de inversión intensivo.")
        else: 
            st.error(f"🚨 **CALIDAD DGI: {score_calidad:.1f}/10** — Calidad Insuficiente. Riesgo en cobertura de dividendo por caja o endeudamiento.")

    with col_sc2:
        if score_val >= 7.0: 
            st.success(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Oportunidad Clara. Cotiza en zona de ganga histórica por canal de Yield y múltiplos.")
        elif score_val >= 4.0: 
            st.warning(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Valoración Justa. Cotiza cerca de su media histórica o múltiplos intermedios.")
        else: 
            st.error(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Sobrevalorada o Exigente. Poco o nulo margen de seguridad fundamental.")

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

    st.markdown(f"### 📈 Evolución Histórica de Valoración ({años_analisis} Años)")
    df_grafico = historial_analisis[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_analisis['Div_Anual']
        df_grafico['Precio_Compra'] = (df_grafico['Div_Grafico'] / yield_infravalorado) * 100
        df_grafico['Precio_Justo'] = (df_grafico['Div_Grafico'] / yield_medio) * 100
        df_grafico['Precio_Venta'] = (df_grafico['Div_Grafico'] / yield_sobrevalorado) * 100
        
        if currency == 'GBp':
            df_grafico['Close'] = df_grafico['Close'] / divisor_uk
            df_grafico['Precio_Compra'] = df_grafico['Precio_Compra'] / divisor_uk
            df_grafico['Precio_Justo'] = df_grafico['Precio_Justo'] / divisor_uk
            df_grafico['Precio_Venta'] = df_grafico['Precio_Venta'] / divisor_uk

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

        is_compra = df_grafico['Close'] <= df_grafico['Precio_Compra']
        toques_compra = (is_compra & ~is_compra.shift(1, fill_value=False)).sum()
        
        is_venta = df_grafico['Close'] >= df_grafico['Precio_Venta']
        toques_venta = (is_venta & ~is_venta.shift(1, fill_value=False)).sum()
        
        def format_last_time(is_zone_series, active_color):
            if is_zone_series.sum() == 0:
                return "Nunca", "#aaa"
            if is_zone_series.iloc[-1]:
                return "Ahora", active_color
            
            last_date = is_zone_series[is_zone_series].index[-1]
            days_diff = (pd.Timestamp.now().normalize() - last_date.tz_localize(None).normalize()).days
            
            if days_diff < 30:
                return f"hace {days_diff} días", "#ccc"
            elif days_diff < 365:
                meses = days_diff // 30
                return f"hace {meses} meses", "#ccc"
            else:
                anios = days_diff / 365.25
                return f"hace {anios:.1f}a".replace(".", ","), "#ccc"

        str_ultima_compra, color_ult_compra = format_last_time(is_compra, "#21c354")
        str_ultima_venta, color_ult_venta = format_last_time(is_venta, "#ff4b4b")

        html_stats = f"""
        <div style="background-color: rgba(255, 255, 255, 0.05); padding: 15px 20px; border-radius: 5px; margin-top: -15px; margin-bottom: 20px;">
            <div style="font-size: 0.85rem; color: #aaa; margin-bottom: 12px; font-weight: 600; letter-spacing: 1px;">HISTÓRICO {años_analisis}A</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 1rem;"><span style="color: #21c354; font-weight: 900; margin-right: 8px;">—</span>Toques zona compra</span>
                <span style="color: #21c354; font-weight: bold; font-size: 1.1rem;">{toques_compra}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 16px; font-size: 0.9rem; color: #ccc;">
                <span style="padding-left: 24px;">Última vez</span>
                <span style="color: {color_ult_compra}; font-weight: 500;">{str_ultima_compra}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 1rem;"><span style="color: #ff4b4b; font-weight: 900; margin-right: 8px;">—</span>Toques zona venta</span>
                <span style="color: #ff4b4b; font-weight: bold; font-size: 1.1rem;">{toques_venta}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #ccc;">
                <span style="padding-left: 24px;">Última vez</span>
                <span style="color: {color_ult_venta}; font-weight: 500;">{str_ultima_venta}</span>
            </div>
        </div>
        """
        st.markdown(html_stats, unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses)")
    st.markdown("> **Uso según el Método Weiss:** Busca picos de volumen rojo extremo (Capitulación) cuando las barras toquen la línea verde discontinua (Suelo Fundamental). Dispara cuando el MACD cruce al alza perdiendo inercia bajista.")

    fecha_calculo_macd = pd.Timestamp.now().normalize() - pd.DateOffset(years=1)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()

    if len(df_tech_full) > 30: 
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100
        df_tech_full['Precio_Justo'] = (df_tech_full['Div_Anual'] / yield_medio) * 100
        df_tech_full['Precio_Venta'] = (df_tech_full['Div_Anual'] / yield_sobrevalorado) * 100

        if yield_req_chowder is not None and yield_req_chowder > 0:
            df_tech_full['Precio_Chowder'] = (df_tech_full['Div_Anual'] / yield_req_chowder) * 100

        if currency == 'GBp':
            for col in ['Open', 'High', 'Low', 'Close', 'Precio_Compra', 'Precio_Justo', 'Precio_Venta']: 
                df_tech_full[col] = df_tech_full[col] / divisor_uk
            if 'Precio_Chowder' in df_tech_full.columns:
                df_tech_full['Precio_Chowder'] = df_tech_full['Precio_Chowder'] / divisor_uk

        ema12 = df_tech_full['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df_tech_full['Close'].ewm(span=26, adjust=False).mean()
        df_tech_full['MACD'] = ema12 - ema26
        df_tech_full['Signal'] = df_tech_full['MACD'].ewm(span=9, adjust=False).mean()
        df_tech_full['Histogram'] = df_tech_full['MACD'] - df_tech_full['Signal']

        fecha_display = pd.Timestamp.now().normalize() - pd.DateOffset(months=2)
        df_tech = df_tech_full[df_tech_full.index >= fecha_display].copy()

        if not df_tech.empty:
            ult_close_val = precio_actual / divisor_uk
            ult_suelo_val = precio_compra / divisor_uk
            precio_str = f"{ult_close_val:.2f}{sym}"
            suelo_str = f"{ult_suelo_val:.2f}{sym}"
            if ult_suelo_val > 0: dist_suelo = ((ult_close_val - ult_suelo_val) / ult_suelo_val) * 100
            else: dist_suelo = 999.0

            ult_macd = df_tech['MACD'].iloc[-1]
            ult_signal = df_tech['Signal'].iloc[-1]
            ult_hist = df_tech['Histogram'].iloc[-1]
            penult_hist = df_tech['Histogram'].iloc[-2] if len(df_tech) > 1 else 0

            avg_vol = df_tech['Volume'].mean()
            max_vol_reciente = df_tech['Volume'].tail(5).max()
            vol_elevado = max_vol_reciente > (avg_vol * 1.5)

            analisis_ia = f"🧠 **Análisis de la IA (Leyendo cotización actual: {precio_str}):** "
            if dist_suelo <= 0:
                descuento_extra = abs(dist_suelo)
                if descuento_extra > 0.5: analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) cotiza un **{descuento_extra:.1f}% por debajo** de tu Suelo Fundamental ({suelo_str}). "
                else: analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) está tocando el Suelo Fundamental ({suelo_str}). "
                if vol_elevado: analisis_ia += "Se detecta volumen extremo reciente (posible capitulación). "
                if ult_macd > ult_signal and ult_hist > 0: analisis_ia += "El MACD confirma giro alcista. **Escenario de COMPRA IDEAL.**"
                elif ult_macd < ult_signal and ult_hist > penult_hist: analisis_ia += "El MACD sigue bajista pero pierde fuerza. Atento al inminente cruce al alza."
                else: analisis_ia += "El MACD sigue cayendo con fuerza. Compra si eres un fundamental estricto, o espera si prefieres confirmación técnica."
            elif 0 < dist_suelo <= 5.0:
                analisis_ia += f"🟡 **Alerta Temprana / Rebote.** El precio ({precio_str}) está a un **{dist_suelo:.1f}%** de tu zona de compra ({suelo_str}). "
                if ult_macd > ult_signal: analisis_ia += "El MACD es alcista. Si la acción acaba de rebotar desde la línea verde, es buena entrada aunque llegues algo tarde."
                else: analisis_ia += "El MACD es bajista. Lo ideal es esperar a que siga corrigiendo hasta tocar la línea verde discontinua para maximizar el margen de seguridad."
            else:
                analisis_ia += f"🔴 **Fuera de Zona.** El precio ({precio_str}) cotiza un **{dist_suelo:.1f}%** por encima del suelo exigido ({suelo_str}). "
                analisis_ia += "No hay margen de seguridad suficiente. Observa desde la barrera y pon alertas por si la acción sufre una corrección severa."

            st.info(analisis_ia)

            colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for index, row in df_tech.iterrows()]
            colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']]

            fig_tech = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3])

            fig_tech.add_trace(go.Ohlc(
                x=df_tech.index, open=df_tech['Open'], high=df_tech['High'], low=df_tech['Low'], close=df_tech['Close'], 
                name='Precio', increasing_line_color='#21c354', decreasing_line_color='#ff4b4b', showlegend=False
            ), row=1, col=1)

            ex_div_ts = info.get('exDividendDate')
            if pd.notna(ex_div_ts) and ex_div_ts is not None:
                try:
                    ex_div_date_future = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()
                    if ex_div_date_future >= pd.Timestamp.now().normalize():
                        fig_tech.add_vline(x=ex_div_date_future, line_width=1.5, line_dash="dot", line_color="#e040fb", 
                                           annotation_text=" Ⓓ Ex-Div", annotation_position="bottom right", 
                                           annotation_font=dict(color="#e040fb", size=11, family="Arial", weight="bold"), row=1, col=1)
                except: pass

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)

            if 'Precio_Chowder' in df_tech.columns:
                fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Chowder'], name='Precio Obj. Chowder', line=dict(color='#e040fb', width=1.5, dash='dashdot'), showlegend=True, visible='legendonly'), row=1, col=1)

            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False), row=2, col=1)
            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False), row=3, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False), row=3, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False), row=3, col=1)

            fig_tech.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=800, showlegend=True, 
                legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5), 
                hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_rangeslider_visible=False
            )
            fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_tech, use_container_width=True)
        else: st.info("No hay suficientes datos recientes en Yahoo Finance para dibujar el panel de 2 meses.")
    else: st.info("No hay suficientes datos históricos en Yahoo Finance para calcular el panel técnico (MACD/Volumen).")

    # ==========================================
    # BLOQUE VISUAL MEJORADO: BENEFICIOS, PROYECCIONES Y SOLVENCIA
    # ==========================================
    st.divider()
    st.subheader("📊 Radiografía Financiera y Proyecciones")

    # Inyección CSS para tarjetas tipo app fintech
    st.markdown("""
    <style>
    .card-dgi {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }
    .badge-verde { background: rgba(33, 195, 84, 0.2); color: #21c354; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
    .badge-rojo { background: rgba(255, 75, 75, 0.2); color: #ff4b4b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
    .badge-ambar { background: rgba(250, 202, 43, 0.2); color: #faca2b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

    # 1. TARJETAS DE BPA Y PER (PRESENTE VS FUTURO)
    col_bpa1, col_bpa2 = st.columns(2)
    
    with col_bpa1:
        if bpa_trailing != 0 and bpa_forward != 0:
            var_bpa = ((bpa_forward - bpa_trailing) / abs(bpa_trailing)) * 100
            b_class = "badge-verde" if var_bpa >= 0 else "badge-rojo"
            b_sign = "+" if var_bpa > 0 else ""
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">💵 Beneficio por Acción (BPA)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{bpa_trailing:.2f}{sym} <span style="font-size: 1rem; color: #888;">➔</span> {bpa_forward:.2f}{sym}</span>
                    <span class="{b_class}">{b_sign}{var_bpa:.1f}%</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Actual ➔ Estimado a 12 meses</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.metric("BPA Actual", f"{bpa_trailing:.2f}{sym}" if bpa_trailing != 0 else "N/D")

    with col_bpa2:
        if per_actual > 0 and per_forward > 0:
            var_per = ((per_forward - per_actual) / per_actual) * 100
            p_class = "badge-verde" if var_per <= 0 else "badge-rojo"
            p_sign = "+" if var_per > 0 else ""
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏷️ Múltiplo de Valoración (PER)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{per_actual:.1f}x <span style="font-size: 1rem; color: #888;">➔</span> {per_forward:.1f}x</span>
                    <span class="{p_class}">{p_sign}{var_per:.1f}%</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">PER Actual ➔ PER Futuro</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.metric("PER Actual", f"{per_actual:.1f}x" if per_actual > 0 else "N/D")

    # 2. CRECIMIENTO BPA Y GESTIÓN DE ACCIONES
    col_acc1, col_acc2 = st.columns(2)
    with col_acc1:
        c_bpa_val = f"{crecimiento_bpa_3y:+.2f}%" if crecimiento_bpa_3y is not None else "N/D"
        c_badge = "badge-verde" if (crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0) else "badge-rojo"
        st.markdown(f"""
        <div class="card-dgi">
            <span style="color: #aaa; font-size: 0.85rem;">📈 Crecimiento BPA (3 Años)</span>
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                <span style="font-size: 1.5rem; font-weight: bold;">{c_bpa_val}</span>
                <span class="{c_badge}">{'Sólido' if (crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0) else 'Débil'}</span>
            </div>
            <span style="font-size: 0.75rem; color: #888;">Tasa anual compuesta de beneficios</span>
        </div>
        """, unsafe_allow_html=True)

    with col_acc2:
        if variacion_acciones is not None:
            if variacion_acciones < -0.5:
                t_acc, c_acc_b = "🟢 Recomprando", "badge-verde"
                sub_acc = "Destruye acciones (Genera valor)"
            elif variacion_acciones <= 2.0:
                t_acc, c_acc_b = "🟡 Estable", "badge-ambar"
                sub_acc = "Capital social constante"
            else:
                t_acc, c_acc_b = "🔴 Diluyendo", "badge-rojo"
                sub_acc = "Emisión de títulos o fusiones"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🔄 Acciones ({años_analisis} Años)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{variacion_acciones:+.1f}%</span>
                    <span class="{c_acc_b}">{t_acc}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">{sub_acc}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.metric("Acciones", "N/D")

    # 3. SEMÁFORO DE SOLVENCIA Y CAJA REAL
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### ⚖️ Solvencia Operativa y Rentabilidad de Caja")
    col_sol1, col_sol2 = st.columns(2)

    with col_sol1:
        if deuda_ebitda < 900:
            if deuda_ebitda <= lim_deuda_optima:
                badge_d_eb, txt_d_eb = "badge-verde", f"Óptimo (≤ {lim_deuda_optima:.1f}x)"
            elif deuda_ebitda <= lim_deuda_aceptable:
                badge_d_eb, txt_d_eb = "badge-ambar", f"Aceptable (≤ {lim_deuda_aceptable:.1f}x)"
            else:
                badge_d_eb, txt_d_eb = "badge-rojo", "Apalancada"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🛡️ Deuda Neta / EBITDA</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{deuda_ebitda:.2f}x</span>
                    <span class="{badge_d_eb}">{txt_d_eb}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Años de EBITDA para extinguir deuda neta</span>
            </div>
            """, unsafe_allow_html=True)

        if price_to_book > 0:
            pb_badge = "badge-verde" if price_to_book <= 2.5 else "badge-ambar"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">📚 Precio / Valor Contable (P/B)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{price_to_book:.2f}x</span>
                    <span class="{pb_badge}">Múltiplo</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Patrimonio contable sobre cotización</span>
            </div>
            """, unsafe_allow_html=True)

    with col_sol2:
        if deuda_fcf > 0:
            if deuda_fcf <= 3.0: badge_dfcf, txt_dfcf = "badge-verde", "Excelente (≤ 3.0A)"
            elif deuda_fcf <= 5.0: badge_dfcf, txt_dfcf = "badge-ambar", "Normal (≤ 5.0A)"
            else: badge_dfcf, txt_dfcf = "badge-rojo", "Atención (> 5.0A)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⏳ Deuda Total / Flujo de Caja (FCF)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{deuda_fcf:.1f} Años</span>
                    <span class="{badge_dfcf}">{txt_dfcf}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Años de caja libre íntegra para liquidar deuda</span>
            </div>
            """, unsafe_allow_html=True)

        if fcf_yield > 0:
            fcf_b_class = "badge-verde" if fcf_yield >= yield_actual else "badge-ambar"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">💵 FCF Yield (Generación de Efectivo)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{fcf_yield:.2f}%</span>
                    <span class="{fcf_b_class}">Div: {yield_actual:.2f}%</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Debe ser superior a la rentabilidad por dividendo</span>
            </div>
            """, unsafe_allow_html=True)

    # 4. VELOCÍMETRO DEL CRECIMIENTO DEL DIVIDENDO (DGR)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🚀 Crecimiento del Dividendo e Inflación (DGR)")
    
    col_dgr1, col_dgr2 = st.columns(2)
    with col_dgr1:
        if dgr_5y is not None:
            inf_diff = dgr_5y - 2.5
            b_inf = "badge-verde" if inf_diff >= 2.0 else ("badge-ambar" if inf_diff >= 0 else "badge-rojo")
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">DGR 5 Años (Medio Plazo)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.6rem; font-weight: bold; color: #faca2b;">{dgr_5y:.2f}%</span>
                    <span class="{b_inf}">+{inf_diff:.1f}% vs Inflación</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Poder adquisitivo ganado anualmente</span>
            </div>
            """, unsafe_allow_html=True)

    with col_dgr2:
        if dgr_periodo is not None and dgr_5y is not None:
            aceleracion = dgr_5y - dgr_periodo
            if aceleracion >= 0.5: t_inercia, b_iner = "⚡ Acelerando", "badge-verde"
            elif aceleracion <= -0.5: t_inercia, b_iner = "⚠️ Frenando", "badge-ambar"
            else: t_inercia, b_iner = "➡️ Estable", "badge-verde"

            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">DGR {años_analisis} Años (Histórico)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.6rem; font-weight: bold; color: #faca2b;">{dgr_periodo:.2f}%</span>
                    <span class="{b_iner}">{t_inercia}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Tendencia respecto a la media de largo plazo</span>
            </div>
            """, unsafe_allow_html=True)

    if not shares_yearly.empty and len(shares_yearly) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"#### 🔄 Historial Anual de Recompras / Dilución ({años_analisis} Años)")
        yoy_shares_total = shares_yearly.pct_change().dropna() * 100
        yoy_shares_analisis = yoy_shares_total.tail(años_analisis)
        text_labels = [f"+{val:.2f}%" if val > 0 else f"{val:.2f}%" for val in yoy_shares_analisis.values]
        colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares_analisis.values]
        fig_shares = go.Figure()
        fig_shares.add_trace(go.Bar(x=yoy_shares_analisis.index.astype(str), y=yoy_shares_analisis.values, marker_color=colores_barras, text=text_labels, textposition='auto'))
        fig_shares.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=230, yaxis_title="Variación Anual (%)", xaxis_title="", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_shares, use_container_width=True)

    if not dividendos_barras.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"#### 💰 Historial de Dividendos Anuales y Crecimiento YoY ({años_analisis} Años)")
        crecimiento_yoy_total = dividendos_barras.pct_change() * 100
        divs_analisis = dividendos_barras.tail(años_analisis)
        crecimiento_yoy_analisis = crecimiento_yoy_total.tail(años_analisis)
        if len(divs_analisis) > 0:
            x_labels_enriquecidos = []
            for year, val in zip(divs_analisis.index, crecimiento_yoy_analisis.values):
                if pd.isna(val): x_labels_enriquecidos.append(str(year))
                else:
                    color_pct = '#21c354' if val > 0 else '#ff4b4b'
                    signo_pct = '+' if val > 0 else ''
                    x_labels_enriquecidos.append(f"{year}<br><span style='color:{color_pct}; font-size:12px'>{signo_pct}{val:.1f}%</span>")
            fig_divs = go.Figure()
            fig_divs.add_trace(go.Bar(x=x_labels_enriquecidos, y=divs_analisis.values, name=f"Dividendo ({sym})", marker_color='#00d4ff', yaxis='y1', text=[f"{val:.2f}{sym}" for val in divs_analisis.values], textposition='auto'))
            fig_divs.add_trace(go.Scatter(x=x_labels_enriquecidos, y=crecimiento_yoy_analisis.values, name="Crecimiento YoY", mode='lines+markers', line=dict(color='#21c354', width=3), marker=dict(size=8), yaxis='y2'))
            fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
            st.plotly_chart(fig_divs, use_container_width=True)

    st.divider()
    st.subheader(f"📋 Decálogo Detallado DGI — Geraldine Weiss Moderno ({años_analisis} Años)")
    
    t_yield = f"[🏷️ Val: +{pts_yield:.1f} / 4.0 pts]"
    t_pfcf = f"[🏷️ Val: +{pts_pfcf:.2f} / 2.5 pts]"
    t_per_t = f"[🏷️ Val: +{pts_per:.1f} / 2.0 pts]"
    t_chowder_t = f"[🏷️ Val: +{pts_chowder:.1f} / 1.5 pts]"
    
    t_fcf = f"[🛡️ Cal: +{pts_fcf:.2f} / 2.5 pts]"
    t_deuda = f"[🛡️ Cal: +{pts_deuda:.1f} / 2.5 pts]"
    t_hist = f"[🛡️ Cal: +{pts_hist:.2f} / 2.0 pts]"
    t_dgr_t = f"[🛡️ Cal: +{pts_dgr:.2f} / 1.5 pts]"
    t_cap_t = f"[🛡️ Cal: +{pts_cap:.1f} / 1.5 pts]"
    t_info = "[ℹ️ Dato Adicional]"

    st.markdown("#### 🏷️ 1. Múltiplos y Oportunidad de Entrada (Score Valoración: 10 Pts)")
    if yield_actual >= yield_infravalorado: 
        st.success(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (En Suelo Histórico de Compra, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: 
        st.warning(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Aceptable: por encima de la media histórica de {yield_medio:.2f}%)")
    else: 
        st.error(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Pobre: por debajo de su media histórica de {yield_medio:.2f}%)")

    if p_fcf != -1:
        if 0 < p_fcf <= 20.0: st.success(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Muy atractivo ≤ 20x. FCF Yield: {fcf_yield:.2f}%)")
        elif 0 < p_fcf <= 25.0: st.warning(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Moderado ≤ 25x. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Múltiplo exigente > 25x. FCF Yield: {fcf_yield:.2f}%)")
    else: st.error(f"{t_pfcf} P/FCF: NEGATIVO (La empresa no genera flujo de caja libre)")

    if 0 < per <= 20.0: st.success(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Valoración razonable ≤ 20x)")
    elif 0 < per <= 25.0: st.warning(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo justo ≤ 25x)")
    else: st.error(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo exigente > 25x)")

    if chowder_number is not None and chowder_pass:
        st.success(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Aprobada ≥ {chowder_target:.0f}. Retorno total compuesto atractivo)")
    elif chowder_number is not None:
        st.error(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Suspensa < {chowder_target:.0f}. Retorno combinado insuficiente)")
    else:
        st.info(f"{t_chowder_t} Regla de Chowder: N/D")

    if price_to_book > 0:
        if es_financiera or es_industrial: l_verde, l_amarillo = 1.5, 2.5; ctx = "Financiero/Industrial"
        elif es_tecnologica: l_verde, l_amarillo = 5.0, 10.0; ctx = "Tecnología/Software"
        else: l_verde, l_amarillo = 2.5, 5.0; ctx = "General"
        if price_to_book <= l_verde: st.success(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: Atractivo)")
        elif price_to_book <= l_amarillo: st.warning(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: En rango)")
        else: st.info(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: Elevado por intangibles o recompras)")

    st.markdown("#### 🛡️ 2. Seguridad del Dividendo en Efectivo (Score Calidad)")
    if payout_fcf != -1:
        if 0 <= payout_fcf <= payout_limite_fcf: 
            st.success(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Excelente: la caja cubre con holgura el dividendo ≤ {payout_limite_fcf:.0f}%)")
        elif payout_fcf <= payout_amarillo_fcf: 
            st.warning(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Aceptable: consume parte del colchón de caja ≤ {payout_amarillo_fcf:.0f}%)")
        else: 
            st.error(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Precaución: el dividendo presiona el flujo libre > {payout_amarillo_fcf:.0f}%)")
    else: 
        st.error(f"{t_fcf} Payout sobre FCF: NEGATIVO (La empresa está quemando caja)")

    if 0 < payout_ratio <= payout_limite_bpa: 
        st.success(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Sano para su sector, referencia < {payout_limite_bpa:.0f}%)")
    elif payout_limite_bpa < payout_ratio <= payout_amarillo_bpa: 
        st.warning(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (En el límite sectorial de {payout_amarillo_bpa:.0f}%)")
    else: 
        st.info(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Elevado contablemente)")
    
    if payout_forward != -1:
        tendencia_fw = "mejorará" if payout_forward < payout_ratio else "empeorará"
        st.info(f"{t_info} Forward Payout BPA (Estimado): {payout_forward:.2f}% (La cobertura contable prevista {tendencia_fw})")

    st.markdown("#### 🏗️ 3. Solvencia Operativa y Asignación de Capital (Score Calidad)")
    if deuda_ebitda < 900:
        if deuda_ebitda <= lim_deuda_optima: 
            st.success(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Óptimo ≤ {lim_deuda_optima:.1f}x. Capacidad de pago excelente)")
        elif deuda_ebitda <= lim_deuda_aceptable: 
            st.warning(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Aceptable ≤ {lim_deuda_aceptable:.1f}x. Apalancamiento controlado)")
        else: 
            st.error(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Peligro: deuda operativa elevada > {lim_deuda_aceptable:.1f}x)")
    else: 
        st.error(f"{t_deuda} Solvencia Operativa: N/D o EBITDA negativo")

    if cond_recompras or cond_bpa_pos:
        txt_motivo = f"Recompras netas ({variacion_acciones:+.2f}%)" if cond_recompras else f"Crecimiento BPA 3Y ({crecimiento_bpa_3y:+.2f}%)"
        st.success(f"{t_cap_t} Asignación de Capital: Cumplido vía {txt_motivo}")
    else:
        st.error(f"{t_cap_t} Asignación de Capital: Sin recompras netas y con BPA estancado a 3 años")

    if deuda_fcf != -1:
        st.info(f"{t_info} Deuda Total / FCF: {deuda_fcf:.2f} años de flujo libre para extinguir la deuda íntegra")
    if current_ratio > 0:
        st.info(f"{t_info} Liquidez Inmediata (Current Ratio): {current_ratio:.2f}")

    st.markdown("#### 🛡️ 4. Resiliencia, Historial y Crecimiento (Score Calidad)")
    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: 
        st.success(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Aristócrata consagrada / Historial intachable)")
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: 
        st.warning(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Solidez y trayectoria contrastada)")
    elif racha_sin_recortes >= 5: 
        st.warning(f"{t_hist} Historial y Resiliencia: {racha_sin_recortes} años consecutivos sin recortes (Historial reciente)")
    else: 
        st.error(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años (Insuficiente)")

    if dgr_5y is not None and dgr_5y >= 5.0: 
        st.success(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Bate la inflación histórica con holgura ≥ 5.0%)")
    elif dgr_5y is not None and dgr_5y >= 2.5: 
        st.warning(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Crecimiento moderado ≥ 2.5%)")
    else: 
        st.error(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y if dgr_5y is not None else 'N/D'}% (Estancado o inferior a 2.5%)")

    if incrementos_dividendo >= min(5, años_analisis): 
        st.info(f"{t_info} Frecuencia de Subidas: El dividendo ha aumentado {incrementos_dividendo} veces en {años_analisis} años")
    else: 
        st.info(f"{t_info} Frecuencia de Subidas: {incrementos_dividendo} aumentos en {años_analisis} años")

    if dgr_periodo is not None:
        st.info(f"{t_info} Crecimiento DGR {años_analisis}A (Largo Plazo): {dgr_periodo:.2f}% anual compuesto")

    st.markdown("#### 🏢 5. Fortaleza Institucional")
    if market_cap > 10_000_000_000: st.success(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Gran capitalización institucional)")
    else: st.error(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Capitalización pequeña)")

    # ==========================================
    # SECCIÓN CHOWDER REDISEÑADA (VISUAL Y MÓVIL)
    # ==========================================
    st.divider()
    st.subheader("🥣 La Regla de Chowder (Retorno Compuesto)")

    # Determinar texto del criterio sectorial
    if (es_utility_pura or es_telecom) and yield_actual > 4.0:
        criterio_txt = "Sector Regulado/Utility con Yield > 4.0% (Exige ≥ 8.0)"
    elif yield_actual >= 3.0:
        criterio_txt = "Yield Inicial Alto ≥ 3.0% (Exige ≥ 12.0 para batir al mercado)"
    else:
        criterio_txt = "Yield Inicial Bajo < 3.0% (Exige ≥ 15.0 por alto crecimiento)"

    col_chow1, col_chow2 = st.columns(2)

    with col_chow1:
        if chowder_number is not None:
            pct_progreso = min(100.0, (chowder_number / chowder_target) * 100)
            diff_chowder = chowder_number - chowder_target
            
            if chowder_pass:
                ch_badge = "badge-verde"
                ch_estado = f"🟢 Aprobada (+{diff_chowder:.1f} pts)"
                color_barra = "#21c354"
            elif chowder_number >= (chowder_target - 1.5):
                ch_badge = "badge-ambar"
                ch_estado = f"🟡 Cerca ({diff_chowder:.1f} pts)"
                color_barra = "#faca2b"
            else:
                ch_badge = "badge-rojo"
                ch_estado = f"🔴 Suspensa ({diff_chowder:.1f} pts)"
                color_barra = "#ff4b4b"

            st.markdown(f"""
            <div class="card-dgi">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="color: #aaa; font-size: 0.85rem;">Ecuación: Yield + DGR 5A</span>
                    <span class="{ch_badge}">{ch_estado}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
                    <span style="font-size: 1.1rem; color: #ccc;">
                        <span style="color: #00d4ff; font-weight: bold;">{yield_actual:.2f}%</span> + 
                        <span style="color: #faca2b; font-weight: bold;">{dgr_5y:.2f}%</span> = 
                        <span style="font-size: 1.6rem; font-weight: bold; color: white;"> {chowder_number:.1f}</span>
                    </span>
                    <span style="font-size: 0.9rem; color: #888;">Meta: <strong>≥ {chowder_target:.0f}</strong></span>
                </div>
                <!-- Barra de progreso visual -->
                <div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 6px;">
                    <div style="background: {color_barra}; width: {pct_progreso:.1f}%; height: 100%;"></div>
                </div>
                <span style="font-size: 0.75rem; color: #888;">{criterio_txt}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("🥣 Datos insuficientes de crecimiento a 5 años para calcular Chowder.")

    with col_chow2:
        if chowder_number is not None:
            if chowder_pass or yield_req_chowder <= 0:
                st.markdown(f"""
                <div class="card-dgi">
                    <span style="color: #aaa; font-size: 0.85rem;">🎯 Precio Objetivo por Regla de Chowder</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px; margin-bottom: 8px;">
                        <span style="font-size: 1.5rem; font-weight: bold; color: #21c354;">Ya Cumple la Regla</span>
                        <span class="badge-verde">En Precio</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #888;">El dividendo actual y su crecimiento ya baten el objetivo sin requerir mayor descuento.</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                p_obj_val = precio_obj_chowder / divisor_uk
                p_act_val = precio_actual / divisor_uk
                dist_chow = ((p_act_val - p_obj_val) / p_obj_val) * 100
                st.markdown(f"""
                <div class="card-dgi">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="color: #aaa; font-size: 0.85rem;">🎯 Precio Objetivo por Chowder</span>
                        <span class="badge-rojo">+{dist_chow:.1f}% sobre meta</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
                        <span style="font-size: 1.5rem; font-weight: bold;">{p_obj_val:.2f}{sym}</span>
                        <span style="font-size: 0.85rem; color: #888;">Cotiza a {p_act_val:.2f}{sym}</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #888;">Precio necesario para que el Yield ({yield_req_chowder:.2f}%) compense el crecimiento y alcance {chowder_target:.0f}.</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.metric("Precio Obj. Chowder", "N/D")

    st.divider()
    
    # ==========================================
    # PANEL: ANÁLISIS FUNDAMENTAL VISUAL
    # ==========================================
    st.markdown("### 📉 Análisis Fundamental Visual")
    
    try:
        df_cashflow = ticker.cashflow
        df_financials = ticker.financials
        df_balance = ticker.balance_sheet
        
        def get_annual_series(df, col_names):
            if df is not None and not df.empty:
                for col in col_names:
                    if col in df.index:
                        s = df.loc[col].dropna()
                        if not s.empty:
                            s.index = pd.to_datetime(s.index).year
                            return s.sort_index()
            return pd.Series(dtype=float)

        fcf_s = get_annual_series(df_cashflow, ['Free Cash Flow'])
        div_s = abs(get_annual_series(df_cashflow, ['Cash Dividends Paid', 'Dividends Paid']))
        rev_s = get_annual_series(df_financials, ['Total Revenue', 'Operating Revenue'])
        net_s = get_annual_series(df_financials, ['Net Income', 'Net Income Common Stockholders'])
        debt_s = get_annual_series(df_balance, ['Total Debt'])
        cash_s = get_annual_series(df_balance, ['Cash And Cash Equivalents', 'Cash'])
        shares_s = get_annual_series(df_financials, ['Diluted Average Shares', 'Basic Average Shares'])
        ebitda_s = get_annual_series(df_financials, ['EBITDA', 'Normalized EBITDA'])
        
        yearly_closes = historial_completo['Close'].resample('YE').last()
        yearly_closes.index = yearly_closes.index.year

        col_graf1, col_graf2 = st.columns(2)

        # 1. Gráfico de Yield Limpio
        with col_graf1:
            st.markdown("#### 📈 Evolución del Yield Histórico")
            df_yield_chart = yields_validos.copy()
            fig_yield = go.Figure()
            
            fig_yield.add_trace(go.Scatter(
                x=df_yield_chart.index, y=df_yield_chart.values, mode='lines',
                line=dict(color='#00d4ff', width=2), name='Histórico', showlegend=False
            ))
            
            fig_yield.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b")
            fig_yield.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354")
            fig_yield.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b")

            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Techo: {yield_sobrevalorado:.2f}%"))
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {yield_medio:.2f}%"))
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Suelo: {yield_infravalorado:.2f}%"))
            fig_yield.add_trace(go.Scatter(
                x=[df_yield_chart.index[-1]], y=[df_yield_chart.iloc[-1]], mode='markers',
                marker=dict(color='#00d4ff', size=10, symbol='diamond'), name=f"Actual: {yield_actual:.2f}%"
            ))

            fig_yield.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                height=320, yaxis=dict(title="Rentabilidad (Yield %)", tickformat=".2f"), hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
            )
            fig_yield.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_yield, use_container_width=True)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Muestra la rentabilidad por dividendo a lo largo del tiempo. Las caídas bruscas del precio provocan picos en el Yield (tocando la línea verde inferior), señalando las mejores oportunidades históricas de compra.</p>", unsafe_allow_html=True)

        # 2. Drawdown Histórico
        with col_graf2:
            st.markdown("#### 📉 Drawdown Histórico")
            df_dd = historial_analisis[['Close']].copy()
            df_dd['Max'] = df_dd['Close'].cummax()
            df_dd['Drawdown'] = (df_dd['Close'] - df_dd['Max']) / df_dd['Max'] * 100
            
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=df_dd.index, y=df_dd['Drawdown'], fill='tozeroy', mode='lines',
                line=dict(color='#ff4b4b', width=1.5), fillcolor='rgba(255, 75, 75, 0.2)', name='Drawdown %'
            ))
            fig_dd.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                height=320, yaxis=dict(title="Caída desde Máximos (%)", tickformat=".1f", ticksuffix="%"), hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_dd, use_container_width=True)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Mide la caída porcentual de la acción desde su último máximo histórico. Es la mejor forma de evaluar la volatilidad real de la empresa y detectar correcciones de mercado severas.</p>", unsafe_allow_html=True)

        # 1.5. YIELD ON COST HISTÓRICO CON SUPERPOSICIÓN
        st.markdown("---")
        st.markdown("#### ⏳ Yield on Cost Histórico")
        st.markdown(f"> **Yield on Cost (YoC):** Muestra el Yield Actual ({yield_actual:.2f}%) que tendrías hoy si hubieras comprado la acción en cualquier fecha del pasado. Calculado dividiendo el dividendo actual ({forward_dividend / divisor_uk:.2f}{sym}) entre el precio histórico de cada día.")
        
        if not historial_analisis.empty and forward_dividend > 0:
            df_yoc_hist = historial_analisis[['Close', 'Yield_Diario']].copy()
            df_yoc_hist = df_yoc_hist.dropna(subset=['Close', 'Yield_Diario'])
            
            if currency == 'GBp':
                df_yoc_hist['Close_Div'] = df_yoc_hist['Close'] / divisor_uk
            else:
                df_yoc_hist['Close_Div'] = df_yoc_hist['Close']
                
            df_yoc_hist['YoC_Hist'] = (forward_dividend / df_yoc_hist['Close_Div']) * 100
            
            df_yoc_hist.replace([np.inf, -np.inf], np.nan, inplace=True)
            df_yoc_hist = df_yoc_hist.dropna(subset=['YoC_Hist'])
            
            fig_yoc_hist = go.Figure()
            
            fig_yoc_hist.add_trace(go.Scatter(
                x=df_yoc_hist.index, y=df_yoc_hist['Yield_Diario'], mode='lines',
                line=dict(color='rgba(255, 255, 255, 0.4)', width=1.5), name='Yield Histórico (En su día)'
            ))

            fig_yoc_hist.add_trace(go.Scatter(
                x=df_yoc_hist.index, y=df_yoc_hist['YoC_Hist'], mode='lines',
                line=dict(color='#faca2b', width=2), name='Yield on Cost (Hoy)'
            ))
            
            fig_yoc_hist.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b", opacity=0.6)
            fig_yoc_hist.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354", opacity=0.6)
            fig_yoc_hist.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b", opacity=0.6)

            primera_fecha = df_yoc_hist.index[0]
            fig_yoc_hist.add_trace(go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Techo: {yield_sobrevalorado:.2f}%"))
            fig_yoc_hist.add_trace(go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {yield_medio:.2f}%"))
            fig_yoc_trace = go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Suelo: {yield_infravalorado:.2f}%")
            fig_yoc_hist.add_trace(fig_yoc_trace)
            
            fig_yoc_hist.add_hline(y=yield_actual, line_dash="dash", line_color="#00d4ff")
            
            fig_yoc_hist.add_annotation(
                x=df_yoc_hist.index[-1], y=yield_actual, text=f"Yield Hoy: {yield_actual:.2f}%", 
                showarrow=False, yshift=15, font=dict(color="#00d4ff", size=11, weight="bold"), xanchor="right"
            )

            fig_yoc_hist.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=20, b=50),
                height=400, yaxis=dict(title="Rentabilidad (%)", tickformat=".2f"), hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
            )
            fig_yoc_hist.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_yoc_hist, use_container_width=True)
        else:
            st.info("Datos insuficientes para calcular el Yield on Cost histórico.")
            
        st.markdown("---")

        col_graf3, col_graf4 = st.columns(2)

        # 3. Sostenibilidad del Dividendo
        with col_graf3:
            st.markdown("#### 💵 Sostenibilidad: FCF vs Dividendos")
            years_sost = sorted(list(set(fcf_s.index) & set(div_s.index)))
            if years_sost:
                x_years = [str(y) for y in years_sost]
                fcf_vals = [fcf_s[y] for y in years_sost]
                div_vals = [div_s[y] for y in years_sost]
                payout_vals = [(div/fcf)*100 if fcf > 0 else 0 for fcf, div in zip(fcf_vals, div_vals)]
                
                fig_sost = make_subplots(specs=[[{"secondary_y": True}]])
                fig_sost.add_trace(go.Bar(x=x_years, y=fcf_vals, name='FCF', marker_color='#00d4ff'), secondary_y=False)
                fig_sost.add_trace(go.Bar(x=x_years, y=div_vals, name='Dividendos', marker_color='#ff9800'), secondary_y=False)
                fig_sost.add_trace(go.Scatter(x=x_years, y=payout_vals, name='Payout FCF %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in payout_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff4b4b', width=2), marker=dict(size=8)), secondary_y=True)
                fig_sost.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                )
                fig_sost.update_yaxes(title_text="Absoluto", secondary_y=False)
                fig_sost.update_yaxes(title_text="Payout %", secondary_y=True, showgrid=False, range=[0, max(payout_vals)*1.2 if payout_vals else 100])
                st.plotly_chart(fig_sost, use_container_width=True)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Compara el dinero real contante y sonante que entra en la caja (FCF, azul) frente al dinero que sale para pagar los dividendos (Naranja). La línea roja debe mantenerse por debajo del 60-70% para garantizar que el dividendo es seguro a futuro.</p>", unsafe_allow_html=True)
            else: st.info("Datos anuales insuficientes para el gráfico de Sostenibilidad.")

        # 4. Ingresos y Rentabilidad
        with col_graf4:
            st.markdown("#### 📊 Ingresos vs Beneficio Neto")
            years_rev = sorted(list(set(rev_s.index) & set(net_s.index)))
            if years_rev:
                x_years_rev = [str(y) for y in years_rev]
                rev_vals = [rev_s[y] for y in years_rev]
                net_vals = [net_s[y] for y in years_rev]
                margin_vals = [(n/r)*100 if r > 0 else 0 for r, n in zip(rev_vals, net_vals)]
                
                fig_ing = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=rev_vals, name='Ingresos', marker_color='#21c354'), secondary_y=False)
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=net_vals, name='B. Neto', marker_color='#faca2b'), secondary_y=False)
                fig_ing.add_trace(go.Scatter(x=x_years_rev, y=margin_vals, name='Margen Neto %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in margin_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#00d4ff', width=2), marker=dict(size=8)), secondary_y=True)
                fig_ing.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                )
                fig_ing.update_yaxes(title_text="Absoluto", secondary_y=False)
                fig_ing.update_yaxes(title_text="Margen %", secondary_y=True, showgrid=False, range=[0, max(margin_vals)*1.2 if margin_vals else 100])
                st.plotly_chart(fig_ing, use_container_width=True)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Evalúa el crecimiento del negocio. Barras verdes indican que la empresa vende más. La línea azul mide el Margen Neto: qué porcentaje de esas ventas se convierte en ganancias puras. Crecimiento de ingresos con márgenes estables o al alza indica una ventaja competitiva fuerte.</p>", unsafe_allow_html=True)
            else: st.info("Datos anuales insuficientes para el gráfico de Ingresos.")

        col_graf5, col_graf6 = st.columns(2)

        # 5. Evolución EV / FCF
        with col_graf5:
            st.markdown("#### ⚖️ Valoración Múltiplo: EV / FCF")
            years_ev = sorted(list(set(fcf_s.index) & set(shares_s.index) & set(yearly_closes.index)))
            if years_ev:
                x_years_ev = [str(y) for y in years_ev]
                fcf_ev_vals = [fcf_s[y] for y in years_ev]
                ev_vals = []
                for y in years_ev:
                    mcap = yearly_closes[y] * shares_s[y]
                    debt = debt_s.get(y, 0)
                    cash = cash_s.get(y, 0)
                    ev = mcap + debt - cash
                    ev_vals.append(ev)
                
                ratio_vals = [(ev/fcf) if fcf > 0 else 0 for ev, fcf in zip(ev_vals, fcf_ev_vals)]
                
                fig_ev = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=ev_vals, name='Enterprise Value (EV)', marker_color='#9c27b0'), secondary_y=False)
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=fcf_ev_vals, name='FCF', marker_color='#00d4ff'), secondary_y=False)
                fig_ev.add_trace(go.Scatter(x=x_years_ev, y=ratio_vals, name='Ratio EV/FCF', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#21c354', width=2), marker=dict(size=8)), secondary_y=True)
                fig_ev.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                )
                fig_ev.update_yaxes(title_text="Absoluto", secondary_y=False)
                fig_ev.update_yaxes(title_text="Ratio (Múltiplo)", secondary_y=True, showgrid=False, range=[0, max(ratio_vals)*1.2 if ratio_vals else 30])
                st.plotly_chart(fig_ev, use_container_width=True)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Calcula cuántas veces está valorada la empresa (sumando su deuda y restando su liquidez) respecto a su Flujo de Caja. Es mucho más preciso que el PER porque incluye la deuda real. Un ratio por debajo de 15x-20x suele indicar infravaloración.</p>", unsafe_allow_html=True)
            else: st.info("Datos insuficientes para el gráfico EV/FCF.")

        # 6. Evolución EV / EBITDA
        with col_graf6:
            st.markdown("#### 🏢 Múltiplo Operativo: EV / EBITDA")
            years_ebitda = sorted(list(set(ebitda_s.index) & set(shares_s.index) & set(yearly_closes.index)))
            if years_ebitda:
                x_years_eb = [str(y) for y in years_ebitda]
                ebitda_vals = [ebitda_s[y] for y in years_ebitda]
                ev_eb_vals = []
                for y in years_ebitda:
                    mcap = yearly_closes[y] * shares_s[y]
                    debt = debt_s.get(y, 0)
                    cash = cash_s.get(y, 0)
                    ev = mcap + debt - cash
                    ev_eb_vals.append(ev)
                
                ratio_eb_vals = [(ev/eb) if eb > 0 else 0 for ev, eb in zip(ev_eb_vals, ebitda_vals)]
                
                fig_ebitda = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ebitda_vals, name='EBITDA', marker_color='#0288d1'), secondary_y=False)
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ev_eb_vals, name='Enterprise Value (EV)', marker_color='#ff9800'), secondary_y=False)
                fig_ebitda.add_trace(go.Scatter(x=x_years_eb, y=ratio_eb_vals, name='Ratio EV/EBITDA', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_eb_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff1744', width=2), marker=dict(size=8)), secondary_y=True)
                fig_ebitda.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                )
                fig_ebitda.update_yaxes(title_text="Absoluto", secondary_y=False)
                fig_ebitda.update_yaxes(title_text="Ratio (Múltiplo)", secondary_y=True, showgrid=False, range=[0, max(ratio_eb_vals)*1.2 if ratio_eb_vals else 30])
                st.plotly_chart(fig_ebitda, use_container_width=True)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>El múltiplo clásico de las adquisiciones corporativas. Compara el Valor de la Empresa con sus beneficios antes de intereses, impuestos, depreciaciones y amortizaciones. Permite medir si la empresa cotiza cara o barata ignorando temporalmente su estructura fiscal y contable.</p>", unsafe_allow_html=True)
            else: st.info("Datos insuficientes para el gráfico EV/EBITDA.")

        # 7. DEUDA NETA / FCF
        st.markdown("#### 🛡️ Solvencia: Deuda Neta vs FCF")
        years_debt = sorted(list(set(fcf_s.index) & set(debt_s.index)))
        if years_debt:
            x_years_d = [str(y) for y in years_debt]
            fcf_d_vals = [fcf_s[y] for y in years_debt]
            net_debt_vals = []
            for y in years_debt:
                d = debt_s.get(y, 0)
                c = cash_s.get(y, 0)
                nd = max(0, d - c) 
                net_debt_vals.append(nd)
            
            ratio_d_vals = [(nd/fcf) if fcf > 0 else 0 for nd, fcf in zip(net_debt_vals, fcf_d_vals)]
            
            fig_deuda = make_subplots(specs=[[{"secondary_y": True}]])
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=fcf_d_vals, name='Flujo Caja Libre (FCF)', marker_color='#0288d1'), secondary_y=False)
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=net_debt_vals, name='Deuda Neta', marker_color='#ff9800'), secondary_y=False)
            fig_deuda.add_trace(go.Scatter(x=x_years_d, y=ratio_d_vals, name='Deuda Neta / FCF', mode='lines+markers+text', text=[f"{val:.2f}x" for val in ratio_d_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff1744', width=2), marker=dict(size=8)), secondary_y=True)
            fig_deuda.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50),
                height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
            )
            fig_deuda.update_yaxes(title_text="Absoluto", secondary_y=False)
            fig_deuda.update_yaxes(title_text="Años para Pagar", secondary_y=True, showgrid=False, range=[0, max(ratio_d_vals)*1.2 if ratio_d_vals else 5])
            st.plotly_chart(fig_deuda, use_container_width=True)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>La métrica definitiva de tranquilidad. Muestra cuántos años completos necesitaría la empresa, usando todo el efectivo libre anual que genera, para dejar su Deuda Neta a cero. Un valor inferior a 3.0 años demuestra un balance blindado frente a crisis económicas.</p>", unsafe_allow_html=True)
        else: st.info("Datos insuficientes para el gráfico de Deuda.")

        # 8. PERFIL DE DEUDA Y LIQUIDEZ (CORTO VS LARGO)
        st.markdown("#### ⏳ Estructura de Deuda Actual (Corto vs Largo Plazo)")
        if df_balance is not None and not df_balance.empty:
            bs_cols = df_balance.index.tolist()
            def get_latest_bs_val(keys):
                for k in keys:
                    if k in bs_cols:
                        s = df_balance.loc[k].dropna()
                        if not s.empty: return s.iloc[0]
                return 0.0

            st_debt = get_latest_bs_val(['Current Debt', 'Short Long Term Debt', 'Short Term Debt'])
            lt_debt = get_latest_bs_val(['Long Term Debt'])
            caja_actual = get_latest_bs_val(['Cash And Cash Equivalents', 'Cash', 'Total Cash'])
            
            if st_debt > 0 or lt_debt > 0 or caja_actual > 0:
                fig_venc = go.Figure()
                
                fig_venc.add_trace(go.Bar(
                    y=['Estructura Actual'], x=[caja_actual], name='Liquidez (Caja y Equivalentes)',
                    orientation='h', marker_color='#21c354',
                    text=f"{caja_actual/1e9:.2f}B {sym}", textposition='inside'
                ))
                
                fig_venc.add_trace(go.Bar(
                    y=['Estructura Actual'], x=[st_debt], name='Deuda Corto Plazo (< 1 Año)',
                    orientation='h', marker_color='#ff9800',
                    text=f"{st_debt/1e9:.2f}B {sym}", textposition='inside'
                ))
                
                fig_venc.add_trace(go.Bar(
                    y=['Estructura Actual'], x=[lt_debt], name='Deuda Largo Plazo (> 1 Año)',
                    orientation='h', marker_color='#ff4b4b',
                    text=f"{lt_debt/1e9:.2f}B {sym}", textposition='inside'
                ))
                
                fig_venc.update_layout(
                    barmode='stack', template='plotly_dark', margin=dict(l=0, r=0, t=30, b=80), height=250,
                    hovermode="y unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.5, xanchor="center", x=0.5),
                    xaxis=dict(showticklabels=False, title="")
                )
                st.plotly_chart(fig_venc, use_container_width=True)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Muestra la liquidez inmediata frente a los vencimientos de deuda. La deuda a corto plazo (naranja) es la que vence en menos de 12 meses. Lo ideal es que la barra verde (Caja) sea superior a la barra naranja, indicando que la empresa no necesita emitir nueva deuda cara para pagar la que vence este año.</p>", unsafe_allow_html=True)
            else:
                st.info("No hay desglose de deuda a corto/largo plazo en Yahoo Finance para esta empresa.")

    except Exception as e:
        st.warning(f"No se han podido cargar los gráficos financieros anuales completos de Yahoo Finance. Error: {e}")

    st.divider()

    st.markdown("#### 🔮 Proyección de Rentabilidad sobre Coste (Yield on Cost a 15 Años)")
    
    val_5y = dgr_5y if dgr_5y is not None else None
    val_periodo = dgr_periodo if dgr_periodo is not None else None

    if val_5y is not None and val_periodo is not None:
        dgr_proyeccion = min(val_5y, val_periodo)
        txt_ritmo = "Ritmo Conservador (5A)" if dgr_proyeccion == val_5y else f"Ritmo Conservador ({años_analisis}A)"
    elif val_5y is not None:
        dgr_proyeccion = val_5y
        txt_ritmo = "Ritmo Disponible (5A)"
    elif val_periodo is not None:
        dgr_proyeccion = val_periodo
        txt_ritmo = f"Ritmo Disponible ({años_analisis}A)"
    else:
        dgr_proyeccion = 0.0
        txt_ritmo = "Crecimiento Nulo / Estancado"
    
    dgr_proyeccion = min(dgr_proyeccion, 15.0)
    años_proyeccion = list(range(1, 16))
    
    div_bruto_proyectado = [forward_dividend * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_bruto_lista = [yield_actual * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_neto_lista = [bruto * net_mult for bruto in yoc_bruto_lista]
    
    x_labels_yoc = []
    for año, yoc_n in zip(años_proyeccion, yoc_neto_lista):
        año_futuro = año_actual + año
        x_labels_yoc.append(f"{año_futuro}<br><span style='color:#faca2b; font-size:12px'>{yoc_n:.1f}%</span>")

    color_barras = '#00d4ff' if dgr_proyeccion >= 0 else '#ff4b4b'
    color_linea = '#21c354' if dgr_proyeccion >= 0 else '#ff4b4b'
    signo_dgr = "+" if dgr_proyeccion > 0 else ""

    st.markdown(f"> **Cálculo de la proyección:** Basado en {txt_ritmo} con un <span style='color:{color_linea};'>**{signo_dgr}{dgr_proyeccion:.1f}% anual constante**</span>.", unsafe_allow_html=True)

    fig_yoc_p = go.Figure()
    fig_yoc_p.add_trace(go.Bar(
        x=x_labels_yoc, y=div_bruto_proyectado, name=f'Div. Esperado ({sym})', marker_color=color_barras, yaxis='y1', 
        text=[f"{val:.2f}{sym}" for val in div_bruto_proyectado], textposition='auto'
    ))
    fig_yoc_p.add_trace(go.Scatter(
        x=x_labels_yoc, y=yoc_neto_lista, name="YoC Neto (%)", mode='lines+markers', 
        line=dict(color=color_linea, width=3), marker=dict(size=8), yaxis='y2'
    ))
    
    fig_yoc_p.update_layout(
        template='plotly_dark', margin=dict(l=0, r=0, t=10, b=40), height=350, hovermode="x unified", 
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
        yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color=color_barras)), tickfont=dict(color=color_barras)), 
        yaxis2=dict(title=dict(text="YoC Neto (%)", font=dict(color="#faca2b")), tickfont=dict(color="#faca2b"), overlaying='y', side='right', showgrid=False), 
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig_yoc_p, use_container_width=True)

# ==========================================
# INTERFAZ DIRECTA DE LA PÁGINA
# ==========================================
st.title("🔍 Análisis Individual — Geraldine Weiss DGI")

col_input1, col_input2, col_input3 = st.columns(3)
with col_input1: 
    ticker_input = st.text_input("Ticker individual:", "MKC").upper()
with col_input2: 
    años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)
with col_input3: 
    impuesto = st.number_input("Retención (%)", value=19.0, key="imp_ind")

if st.button("🚀 Analizar Empresa", use_container_width=True):
    with st.spinner(f"Analizando {ticker_input} en profundidad..."):
        try:
            screener_weiss_definitivo(ticker_input, años_analisis, impuesto)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
