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

st.set_page_config(page_title="Screener Geraldine Weiss", page_icon="📊", layout="wide")

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

    historial_completo = ticker.history(period="max")
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
    total_debt = get_safe('totalDebt', 0)
    respaldo_institucional = get_safe('heldPercentInstitutions') * 100
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

    fecha_corte_shares = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis + 3)
    variacion_acciones = None
    shares_yearly = pd.Series(dtype=float)
    try:
        shares_hist = ticker.get_shares_full(start=fecha_corte_shares.strftime('%Y-%m-%d'), end=None)
        if shares_hist is not None and len(shares_hist) > 1:
            shares_yearly = shares_hist.groupby(shares_hist.index.year).last()
            if len(shares_yearly) >= (años_analisis + 1):
                acc_ini = shares_yearly.iloc[-(años_analisis + 1)]
            else:
                acc_ini = shares_yearly.iloc[0]
            acc_fin = shares_yearly.iloc[-1]
            if acc_ini > 0: variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
    except Exception: pass
    
    if variacion_acciones is None or shares_yearly.empty:
        try:
            inc_stmt = ticker.income_stmt
            if not inc_stmt.empty:
                for key in ['Basic Average Shares', 'Diluted Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna().sort_index()
                        if len(sh_data) >= 2:
                            shares_yearly = sh_data.groupby(sh_data.index.year).last()
                            acc_ini = shares_yearly.iloc[0]
                            acc_fin = shares_yearly.iloc[-1]
                            if acc_ini > 0: variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                            break
        except Exception: pass

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

    # --- CÁLCULO DEL SCORE WEISS ---
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

    # --- CÁLCULO DE LA REGLA DE CHOWDER Y PRECIO OBJETIVO CHOWDER ---
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
    else:
        chowder_number = None
        chowder_pass = False

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
    if score >= 8.0: st.success(f"🏆 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Sobresaliente. Fuerte generación de caja y altísima seguridad.")
    elif score >= 5.0: st.warning(f"⚖️ **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Aceptable. Tiene solidez pero presenta debilidades en su flujo de efectivo o valoración.")
    else: st.error(f"🚨 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Calidad Insuficiente. No supera los filtros de caja real y seguridad.")

    # --- AVISO CHOWDER ---
    if chowder_number is not None:
        if chowder_pass:
            st.success(f"🥣 **REGLA DE CHOWDER: APROBADA ({chowder_number:.1f})** — Supera el objetivo exigido de {chowder_target:.0f}[span_0](start_span)[span_0](end_span).")
        else:
            txt_precio_c = f" Cotiza a {precio_actual / divisor_uk:.2f}{sym} y debería cotizar a {precio_obj_chowder / divisor_uk:.2f}{sym} para cumplir." if (precio_obj_chowder is not None and yield_req_chowder > 0) else ""
            st.error(f"🥣 **REGLA DE CHOWDER: SUSPENSA ({chowder_number:.1f})** — No alcanza el objetivo exigido de {chowder_target:.0f}[span_1](start_span)[span_1](end_span).{txt_precio_c}")
    else:
        st.info("🥣 **REGLA DE CHOWDER: N/D** — No hay datos de crecimiento a 5 años suficientes para su cálculo.")

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
        
        # --- CÁLCULO DE CHOWDER HISTÓRICO PARA EL GRÁFICO PRINCIPAL ---
        rolling_5y_dgr = (dividendos_barras / dividendos_barras.shift(5)) ** (1/5) - 1
        rolling_5y_dgr_pct = rolling_5y_dgr * 100
        df_grafico['Year'] = df_grafico.index.year
        df_grafico['DGR_5Y'] = df_grafico['Year'].map(rolling_5y_dgr_pct)
        df_grafico['Yield_Diario'] = (df_grafico['Div_Grafico'] / df_grafico['Close']) * 100
        
        df_grafico['Chowder_Target_Hist'] = 15.0
        df_grafico.loc[df_grafico['Yield_Diario'] >= 3.0, 'Chowder_Target_Hist'] = 12.0
        if es_utility_pura or es_telecom:
            df_grafico.loc[df_grafico['Yield_Diario'] > 4.0, 'Chowder_Target_Hist'] = 8.0
            
        df_grafico['Req_Yield_Hist'] = df_grafico['Chowder_Target_Hist'] - df_grafico['DGR_5Y']
        
        # Evitar picos infinitos en el gráfico si el Req_Yield es 0 o negativo
        df_grafico['Precio_Chowder_Hist'] = np.where(
            df_grafico['Req_Yield_Hist'] > 0.1, 
            (df_grafico['Div_Grafico'] / df_grafico['Req_Yield_Hist']) * 100, 
            np.nan
        )
        
        if currency == 'GBp':
            df_grafico['Close'] = df_grafico['Close'] / divisor_uk
            df_grafico['Precio_Compra'] = df_grafico['Precio_Compra'] / divisor_uk
            df_grafico['Precio_Justo'] = df_grafico['Precio_Justo'] / divisor_uk
            df_grafico['Precio_Venta'] = df_grafico['Precio_Venta'] / divisor_uk
            df_grafico['Precio_Chowder_Hist'] = df_grafico['Precio_Chowder_Hist'] / divisor_uk
            
        # Recortar picos absurdos visuales para no deformar el eje Y
        max_price_chart = df_grafico['Close'].max() * 3
        df_grafico['Precio_Chowder_Hist'] = df_grafico['Precio_Chowder_Hist'].clip(upper=max_price_chart)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Venta'], name='Franja Sobrevalorada (Venta)', line=dict(color='#ff4b4b', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Compra'], name='Franja Infravalorada (Compra)', line=dict(color='#21c354', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Close'], name='Cotización Real', line=dict(color='#00d4ff', width=3)))
        
        # LÍNEA HISTÓRICA DE CHOWDER OCULTA POR DEFECTO
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Chowder_Hist'], name='Precio Obj. Chowder', line=dict(color='#e040fb', width=2, dash='dashdot'), showlegend=True, visible='legendonly'))

        fig.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), 
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), 
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Muestra la evolución del precio real frente a las franjas de valoración de Weiss. <b>💡 CONSEJO CHOWDER:</b> En la leyenda puedes hacer clic para activar la línea oculta 'Precio Obj. Chowder' y ver a qué precio debías haber comprado en el pasado para superar la regla basándote en el crecimiento de los 5 años anteriores de cada época.</p>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses)")
    st.markdown("> **Uso según el Método Weiss:** Busca picos de volumen rojo extremo (Capitulación) cuando las barras toquen la línea verde discontinua (Suelo Fundamental). Dispara cuando el MACD cruce al alza perdiendo inercia bajista.")

    fecha_calculo_macd = pd.Timestamp.now().normalize() - pd.DateOffset(years=1)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()

    if len(df_tech_full) > 30: 
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100
        df_tech_full['Precio_Justo'] = (df_tech_full['Div_Anual'] / yield_medio) * 100
        df_tech_full['Precio_Venta'] = (df_tech_full['Div_Anual'] / yield_sobrevalorado) * 100

        if currency == 'GBp':
            for col in ['Open', 'High', 'Low', 'Close', 'Precio_Compra', 'Precio_Justo', 'Precio_Venta']: 
                df_tech_full[col] = df_tech_full[col] / divisor_uk

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
                x=df_tech.index, open=df_tech['Open'], high=df_tech['High'],
                low=df_tech['Low'], close=df_tech['Close'], name='Precio',
                increasing_line_color='#21c354', decreasing_line_color='#ff4b4b',
                showlegend=False
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

    st.divider()
    st.subheader("📊 Beneficios, Proyecciones y Acciones")
    
    delta_bpa = None
    if bpa_trailing != 0 and bpa_forward != 0:
        var_bpa = ((bpa_forward - bpa_trailing) / abs(bpa_trailing)) * 100
        delta_bpa = f"{var_bpa:.2f}%"

    delta_per = None
    if per_actual > 0 and per_forward > 0:
        var_per = ((per_forward - per_actual) / per_actual) * 100
        signo_per = "+" if var_per > 0 else ""
        delta_per = f"{signo_per}{var_per:.2f}%"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("BPA Actual", f"{bpa_trailing / divisor_uk:.2f}{sym}" if bpa_trailing != 0 else "N/D")
    c2.metric("BPA Esperado", f"{bpa_forward / divisor_uk:.2f}{sym}" if bpa_forward != 0 else "N/D", delta=delta_bpa)
    c3.metric("PER Actual", f"{per_actual:.2f}" if per_actual > 0 else "N/D")
    c4.metric("PER Futuro", f"{per_forward:.2f}" if per_forward > 0 else "N/D", delta=delta_per, delta_color="inverse")
    c5.metric("Crecimiento BPA (3Y)", f"{crecimiento_bpa_3y:.2f}%" if crecimiento_bpa_3y is not None else "N/D")
    
    if variacion_acciones is not None:
        signo = "+" if variacion_acciones > 0 else ""
        if variacion_acciones < -0.5: estado_acc, color_acc = "- Recomprando", "inverse"
        elif variacion_acciones <= 1.0: estado_acc, color_acc = "Estable", "off"
        else: estado_acc, color_acc = "+ Diluyendo", "inverse"
        c6.metric(f"Acciones ({años_analisis}Y)", f"{signo}{variacion_acciones:.2f}%", delta=estado_acc, delta_color=color_acc)
    else: c6.metric(f"Acciones ({años_analisis}Y)", "N/D")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### ⚖️ Valoración Contable y Solvencia Real")
    cv1, cv2, cv3 = st.columns(3)
    
    if price_to_book > 0:
        if es_financiera or es_industrial: pb_optimo, pb_max = 1.5, 2.5; txt_opt = "Óptimo < 1.5x (Fin/Ind)"
        elif es_tecnologica: pb_optimo, pb_max = 5.0, 10.0; txt_opt = "Óptimo < 5.0x (Tech/Soft)"
        else: pb_optimo, pb_max = 2.5, 5.0; txt_opt = "Óptimo < 2.5x (General)"
        pb_color = "off" if price_to_book <= pb_optimo else "inverse"
        cv1.metric("Precio / Valor en Libros (P/B)", f"{price_to_book:.2f}x", txt_opt, delta_color=pb_color)
    else: cv1.metric("Precio / Valor en Libros (P/B)", "N/D")
        
    if fcf_yield > 0:
        fcf_color = "normal" if fcf_yield > yield_actual else "inverse"
        cv2.metric("FCF Yield (Rentabilidad de Caja)", f"{fcf_yield:.2f}%", f"Óptimo > {yield_actual:.2f}% (Div. Bruto)", delta_color=fcf_color)
    else: cv2.metric("FCF Yield (Rentabilidad de Caja)", "N/D")
        
    if deuda_fcf > 0:
        if deuda_fcf < 3: d_estado, d_color = "Óptimo < 3.0 Años", "normal"
        elif deuda_fcf < 5: d_estado, d_color = "Aceptable < 5.0 Años", "off"
        else: d_estado, d_color = "Peligro > 5.0 Años", "inverse"
        cv3.metric("Deuda Total / FCF", f"{deuda_fcf:.2f} Años", delta=d_estado, delta_color=d_color)
    else: cv3.metric("Deuda Total / FCF", "N/D" if total_debt == 0 else "FCF Negativo")

    if variacion_acciones is not None and variacion_acciones < -1.0:
        if price_to_book > 5.0 or deuda_fcf > 4.0:
            mensajes_alerta = []
            if price_to_book > 5.0: mensajes_alerta.append("un **P/B muy elevado** (distorsión del patrimonio contable)")
            if deuda_fcf > 4.0: mensajes_alerta.append("una **Deuda/FCF en zona de aviso** (apalancamiento mantenido)")
            motivos = " y ".join(mensajes_alerta)
            st.info(f"🕵️‍♂️ **Aviso Analítico Avanzado:** La empresa presenta {motivos}. Al tener un historial agresivo de destrucción de acciones ({variacion_acciones:.2f}%), **revisa si estos datos son fruto de la ingeniería financiera (recompras masivas)** más que de un deterioro real del negocio.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📈 Crecimiento Anual Compuesto del Dividendo (CAGR / DGR)")
    cd1, cd2 = st.columns(2)
    cd1.metric("DGR 5 Años (Medio Plazo)", f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D")
    cd2.metric(f"DGR {años_analisis} Años (Periodo Actual)", f"{dgr_periodo:.2f}%" if dgr_periodo is not None else "N/D")

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
    st.subheader(f"📋 Decálogo de Calidad del Blue Chip ({años_analisis} Años)")
    
    t_fcf = "[🎯 +1.5 / 1.5 pts]" if cond_fcf else "[❌ 0.0 / 1.5 pts]"
    t_pfcf = "[🎯 +1.5 / 1.5 pts]" if cond_pfcf else "[❌ 0.0 / 1.5 pts]"
    t_deuda = "[🎯 +1.5 / 1.5 pts]" if cond_deuda else "[❌ 0.0 / 1.5 pts]"
    t_hist = "[🎯 +1.5 / 1.5 pts]" if cond_historial else "[❌ 0.0 / 1.5 pts]"
    t_aum = "[🎯 +1.0 / 1.0 pts]" if cond_aumentos else "[❌ 0.0 / 1.0 pts]"
    t_acc = "[🎯 +1.0 / 1.0 pts]" if cond_acciones else "[❌ 0.0 / 1.0 pts]"
    t_yield = "[🎯 +0.5 / 0.5 pts]" if cond_yield else "[❌ 0.0 / 0.5 pts]"
    t_bpa = "[🎯 +0.5 / 0.5 pts]" if cond_bpa else "[❌ 0.0 / 0.5 pts]"
    t_per_t = "[🎯 +0.5 / 0.5 pts]" if cond_per else "[❌ 0.0 / 0.5 pts]"
    t_cons = "[🎯 +0.5 / 0.5 pts]" if cond_consistencia else "[❌ 0.0 / 0.5 pts]"
    t_info = "[ℹ️ Info]"

    st.markdown("#### 💰 1. Valoración y Rentabilidad")
    if yield_actual >= yield_infravalorado: st.success(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Excelente, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: st.warning(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Aceptable, superior a media de {yield_medio:.2f}%)")
    else: st.error(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Pobre, inferior a media de {yield_medio:.2f}%)")

    if 0 < per <= 20: st.success(f"{t_per_t} PER (Beneficio Contable): {per:.2f} (Valoración atractiva)")
    else: st.error(f"{t_per_t} PER (Beneficio Contable): {per:.2f} (Múltiplo caro)")

    if p_fcf != -1:
        if 0 < p_fcf <= 20: st.success(f"{t_pfcf} P/FCF (Efectivo Real): {p_fcf:.2f} (Barato. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"{t_pfcf} P/FCF (Efectivo Real): {p_fcf:.2f} (Caro. FCF Yield: {fcf_yield:.2f}%)")
    else: st.error(f"{t_pfcf} P/FCF (Efectivo Real): NEGATIVO")

    if price_to_book > 0:
        if es_financiera or es_industrial: l_verde, l_amarillo = 1.5, 2.5; ctx = "Sector Fin/Ind (Exige P/B estricto)"
        elif es_tecnologica: l_verde, l_amarillo = 5.0, 10.0; ctx = "Sector Tech/Software (P/B alto por intangibles)"
        else: l_verde, l_amarillo = 2.5, 5.0; ctx = "Sector General"
        if price_to_book <= l_verde: st.success(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x | {ctx} (Atractivo)")
        elif price_to_book <= l_amarillo: st.warning(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x | {ctx} (Exigente, pero en el límite)")
        else: st.error(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x | {ctx} (Sobrevaloración contable extrema o recompras masivas)")

    st.markdown("#### 🛡️ 2. Seguridad del Dividendo (Cobertura)")
    if 0 < payout_ratio <= payout_limite_bpa: st.success(f"{t_bpa} Payout (BPA Histórico): {payout_ratio:.2f}% (Seguro para su sector, exige < {payout_limite_bpa:.0f}%)")
    elif payout_limite_bpa < payout_ratio <= payout_amarillo_bpa: st.warning(f"{t_bpa} Payout (BPA Histórico): {payout_ratio:.2f}% (Atención: Excede el límite óptimo de {payout_limite_bpa:.0f}%, pero se mantiene cubierto bajo el {payout_amarillo_bpa:.0f}%)")
    else: st.error(f"{t_bpa} Payout (BPA Histórico): {payout_ratio:.2f}% (Elevado y peligroso: supera el límite sectorial de {payout_amarillo_bpa:.0f}%)")
    
    if payout_forward != -1:
        if payout_forward < (payout_ratio - 1): tendencia_fw = "mejorará"
        elif payout_forward > (payout_ratio + 1): tendencia_fw = "empeorará"
        else: tendencia_fw = "se mantendrá estable"
        if 0 < payout_forward <= payout_limite_bpa: st.success(f"{t_info} Forward Payout (Proyección Año Próximo): {payout_forward:.2f}% (Sano: la cobertura {tendencia_fw})")
        elif payout_limite_bpa < payout_forward <= payout_amarillo_bpa: st.warning(f"{t_info} Forward Payout (Proyección Año Próximo): {payout_forward:.2f}% (Justo: la cobertura {tendencia_fw})")
        else: st.error(f"{t_info} Forward Payout (Proyección Año Próximo): {payout_forward:.2f}% (Peligro: la cobertura {tendencia_fw})")
    else: st.error(f"{t_info} Forward Payout: No disponible por BPA futuro negativo")

    if payout_fcf != -1:
        if payout_fcf <= payout_limite_fcf: st.success(f"{t_fcf} Payout (FCF / Caja Real): {payout_fcf:.2f}% (Caja fuerte para su sector, exige < {payout_limite_fcf:.0f}%)")
        elif payout_limite_fcf < payout_fcf <= payout_amarillo_fcf: st.warning(f"{t_fcf} Payout (FCF / Caja Real): {payout_fcf:.2f}% (Precaución: El dividendo consume más caja de lo ideal, rozando el límite sectorial de {payout_amarillo_fcf:.0f}%)")
        else: st.error(f"{t_fcf} Payout (FCF / Caja Real): {payout_fcf:.2f}% (Peligro crítico: la empresa destina demasiada caja al dividendo, supera el {payout_amarillo_fcf:.0f}%)")
    else: st.error(f"{t_fcf} Payout (FCF): NEGATIVO (La empresa está quemando caja real)")

    st.markdown("#### 🏗️ 3. Solvencia y Gestión del Capital")
    if deuda_fcf != -1:
        if deuda_fcf <= 3.0: st.success(f"{t_deuda} Solvencia (Deuda/FCF): {deuda_fcf:.2f} años (Excelente: Puede liquidar su deuda con la caja íntegra de {deuda_fcf:.1f} años)")
        elif deuda_fcf <= 5.0: st.warning(f"{t_deuda} Solvencia (Deuda/FCF): {deuda_fcf:.2f} años (Aceptable: Nivel de apalancamiento controlable)")
        else: st.error(f"{t_deuda} Solvencia (Deuda/FCF): {deuda_fcf:.2f} años (Peligro: Alta carga de deuda respecto a su capacidad de generar caja)")
    elif total_debt > 0 and fcf <= 0: st.error(f"{t_deuda} Solvencia (Deuda/FCF): PELIGRO (Tiene deuda estructural y quema caja libre)")

    if deuda_equity == 0.0: st.warning(f"{t_info} Deuda/Capital: 0.00% (Posible Patrimonio Negativo por recompras masivas)")
    elif 0 < deuda_equity <= 50: st.success(f"{t_info} Deuda/Capital: {deuda_equity:.2f}% (Balance sano)")
    else: st.error(f"{t_info} Deuda/Capital: {deuda_equity:.2f}% (Apalancamiento elevado)")

    if current_ratio > 0:
        if current_ratio >= 1.5: st.success(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Caja solvente)")
        elif current_ratio >= 1.0: st.warning(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Justa)")
        else: st.error(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Falta de liquidez a corto plazo)")

    if variacion_acciones is not None:
        if variacion_acciones < 0: st.success(f"{t_acc} Acciones en circulación: {variacion_acciones:.2f}% en {años_analisis} años (Excelente, la empresa destruye acciones)")
        elif variacion_acciones <= 5: st.warning(f"{t_acc} Acciones en circulación: +{variacion_acciones:.2f}% en {años_analisis} años (Estable / Ligera dilución)")
        else: st.error(f"{t_acc} Acciones en circulación: +{variacion_acciones:.2f}% en {años_analisis} años (Peligro, la empresa diluye al accionista)")

    st.markdown("#### 🛡️ 4. Historial y Crecimiento")
    if años_pagando >= 25 and racha_sin_recortes >= 12: st.success(f"{t_hist} Historial: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Aristócrata consagrada)")
    else: st.warning(f"{t_hist} Historial: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años")

    if incrementos_dividendo >= min(5, años_analisis): st.success(f"{t_aum} Frecuencia de Aumentos (Filtro Weiss): El dividendo ha subido {incrementos_dividendo} veces en los últimos {años_analisis} años (Cumple exigencia de crecimiento)")
    else: st.error(f"{t_aum} Frecuencia de Aumentos (Filtro Weiss): Solo {incrementos_dividendo} aumentos detectados en {años_analisis} años (Falta de crecimiento activo)")

    if total_años_bpa_datos > 0:
        ratio_bpa = años_crecimiento_bpa / total_años_bpa_datos
        if ratio_bpa >= 0.65: st.success(f"{t_cons} Consistencia BPA (Proxy Yahoo): Crecimiento neto positivo en {años_crecimiento_bpa} de {total_años_bpa_datos} años analizados (Consistente a corto plazo)")
        else: st.error(f"{t_cons} Consistencia BPA (Proxy Yahoo): Solo {años_crecimiento_bpa} años de crecimiento de {total_años_bpa_datos} evaluados (Excesiva ciclicidad reciente)")

    if dgr_5y is not None:
        if dgr_5y >= 10: st.success(f"{t_info} Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Excelente)")
        elif dgr_5y > 0: st.warning(f"{t_info} Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Positivo)")
        else: st.error(f"{t_info} Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Estancado / Recortes)")

    if dgr_periodo is not None:
        if dgr_periodo >= 10: st.success(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Excelente ritmo continuo)")
        elif dgr_periodo > 0: st.warning(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Sostenido)")
        else: st.error(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Estancado / Recortes)")

    st.markdown("#### 🏢 5. Fortaleza Institucional")
    if market_cap > 10_000_000_000: st.success(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Gran capitalización institucional)")
    else: st.error(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Capitalización pequeña)")

    if respaldo_institucional > 0:
        if respaldo_institucional >= 50.0: st.success(f"{t_info} Respaldo Institucional: {respaldo_institucional:.1f}% en manos de Fondos/Bancos (Cumple criterio de respaldo institucional)")
        else: st.warning(f"{t_info} Respaldo Institucional: {respaldo_institucional:.1f}% (Interés institucional bajo o fragmentado)")
    else: st.warning(f"{t_info} Respaldo Institucional: Datos no disponibles en Yahoo")

    st.divider()
    st.subheader("🥣 La Regla de Chowder")
    st.markdown("> **Filtro de Rentabilidad Total:** Diseñado por 'Chowder' en Seeking Alpha, busca unificar el dilema entre rentabilidad inicial y crecimiento del dividendo[span_2](start_span)[span_2](end_span). La premisa establece que si una empresa paga poco dividendo hoy, debe compensarlo subiéndolo a un ritmo vertiginoso para asegurar un retorno que bata al mercado a largo plazo[span_3](start_span)[span_3](end_span).")
    
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    col_c1.metric("Yield Actual", f"{yield_actual:.2f}%")
    col_c2.metric("Crecimiento (DGR 5A)", f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D")
    
    if dgr_5y is not None:
        c_color = "normal" if chowder_pass else "inverse"
        col_c3.metric("Número Chowder", f"{chowder_number:.2f}", delta=f"Objetivo mínimo: {chowder_target:.0f}", delta_color=c_color)
        
        if yield_req_chowder <= 0:
            col_c4.metric("Precio Obj. Chowder", "Ya lo cumple", help="El crecimiento del dividendo a 5 años ya supera por sí solo el objetivo de Chowder.")
        else:
            dist_chowder = ((precio_actual - precio_obj_chowder) / precio_obj_chowder) * 100
            col_c4.metric("Precio Obj. Chowder", f"{precio_obj_chowder / divisor_uk:.2f}{sym}", delta=f"{dist_chowder:+.1f}% vs Actual", delta_color="inverse")
    else:
        col_c3.metric("Número Chowder", "N/D")
        col_c4.metric("Precio Obj. Chowder", "N/D")
    
    st.markdown("#### 📐 Criterios de Aprobación de esta empresa")
    if (es_utility_pura or es_telecom) and yield_actual > 4.0:
        st.info("Al pertenecer a un sector hiper-estable regulado (Utilities/Telecom) y tener un Yield inicial > 4%, se le aplica la **excepción de Chowder**, bajando el objetivo de puntuación a **≥ 8**[span_4](start_span)[span_4](end_span).")
    elif yield_actual >= 3.0:
        st.info("Al ofrecer un Yield inicial atractivo (≥ 3.0%), se le exige un objetivo Chowder estándar de **≥ 12**[span_5](start_span)[span_5](end_span).")
    else:
        st.info("Al ofrecer un Yield inicial bajo (< 3.0%), se le exige mayor crecimiento para compensar, con un objetivo Chowder estricto de **≥ 15**[span_6](start_span)[span_6](end_span).")
    
    st.markdown("*Nota: Los números mágicos de 12 y 15 buscan emular o superar la media histórica del S&P 500 (8%), permitiendo que la rentabilidad sobre coste (YoC) de tu cartera se duplique cíclicamente[span_7](start_span)[span_7](end_span).*")

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
                line=dict(color='#00d4ff', width=2), name='Yield %'
            ))
            
            fig_yield.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b", name="Media")
            fig_yield.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354", name="Suelo (Compra)")
            fig_yield.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b", name="Techo (Venta)")

            fig_yield.add_trace(go.Scatter(
                x=[df_yield_chart.index[-1]], y=[df_yield_chart.iloc[-1]], mode='markers+text',
                marker=dict(color='#00d4ff', size=10, symbol='diamond'),
                text=[f"Actual: {yield_actual:.2f}%"], textposition="top center",
                textfont=dict(color="#00d4ff", size=13, weight="bold"), name="Yield Actual"
            ))
            fig_yield.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                height=300, yaxis=dict(title="Rentabilidad (Yield %)", tickformat=".2f"), hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
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
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                height=300, yaxis=dict(title="Caída desde Máximos (%)", tickformat=".1f", ticksuffix="%"), hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_dd, use_container_width=True)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Mide la caída porcentual de la acción desde su último máximo histórico. Es la mejor forma de evaluar la volatilidad real de la empresa y detectar correcciones de mercado severas.</p>", unsafe_allow_html=True)

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
                fig_sost.add_trace(go.Scatter(x=x_years, y=payout_vals, name='Payout FCF %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in payout_vals], textposition="top center", textfont=dict(color="#ff4b4b", size=11, weight="bold"), line=dict(color='#ff4b4b', width=2), marker=dict(size=8)), secondary_y=True)
                fig_sost.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
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
                fig_ing.add_trace(go.Scatter(x=x_years_rev, y=margin_vals, name='Margen Neto %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in margin_vals], textposition="top center", textfont=dict(color="#00d4ff", size=11, weight="bold"), line=dict(color='#00d4ff', width=2), marker=dict(size=8)), secondary_y=True)
                fig_ing.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
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
                fig_ev.add_trace(go.Scatter(x=x_years_ev, y=ratio_vals, name='Ratio EV/FCF', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_vals], textposition="top center", textfont=dict(color="#21c354", size=11, weight="bold"), line=dict(color='#21c354', width=2), marker=dict(size=8)), secondary_y=True)
                fig_ev.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
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
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                    height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
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
                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0),
                height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
            )
            fig_deuda.update_yaxes(title_text="Absoluto", secondary_y=False)
            fig_deuda.update_yaxes(title_text="Años para Pagar", secondary_y=True, showgrid=False, range=[0, max(ratio_d_vals)*1.2 if ratio_d_vals else 5])
            st.plotly_chart(fig_deuda, use_container_width=True)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>La métrica definitiva de tranquilidad. Muestra cuántos años completos necesitaría la empresa, usando todo el efectivo libre anual que genera, para dejar su Deuda Neta a cero. Un valor inferior a 3.0 años demuestra un balance blindado frente a crisis económicas.</p>", unsafe_allow_html=True)
        else: st.info("Datos insuficientes para el gráfico de Deuda.")

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

    fig_yoc = go.Figure()
    fig_yoc.add_trace(go.Bar(
        x=x_labels_yoc, y=div_bruto_proyectado, name=f'Div. Esperado ({sym})', marker_color=color_barras, yaxis='y1', 
        text=[f"{val:.2f}{sym}" for val in div_bruto_proyectado], textposition='auto'
    ))
    fig_yoc.add_trace(go.Scatter(
        x=x_labels_yoc, y=yoc_neto_lista, name="YoC Neto (%)", mode='lines+markers', 
        line=dict(color=color_linea, width=3), marker=dict(size=8), yaxis='y2'
    ))
    
    fig_yoc.update_layout(
        template='plotly_dark', margin=dict(l=0, r=0, t=10, b=40), height=350, hovermode="x unified", 
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
        yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color=color_barras)), tickfont=dict(color=color_barras)), 
        yaxis2=dict(title=dict(text="YoC Neto (%)", font=dict(color="#faca2b")), tickfont=dict(color="#faca2b"), overlaying='y', side='right', showgrid=False), 
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig_yoc, use_container_width=True)



# ==========================================
# 2. FUNCIÓN PARA EL RADAR MÚLTIPLE
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
        historial = ticker.history(period="15y")
        
        if dividendos.empty or len(historial) < 252: 
            return None

        historial.index = historial.index.tz_localize(None).normalize()
        dividendos.index = dividendos.index.tz_localize(None).normalize()

        fecha_corte = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
        ha = historial[historial.index >= fecha_corte].copy()
        if ha.empty: 
            return None

        # Parametros sectoriales para límites
        sector_en = info.get('sector', '')
        industry_en = info.get('industry', '')
        es_regulada = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower() or 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
        es_tech = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
        es_fin_ind = ('financial' in sector_en.lower() or 'bank' in industry_en.lower() or 
                      'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower())
        
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
        divisor_uk = 1.0
        if currency == 'GBp': divisor_uk = 100.0

        if currency == 'GBp' and forward_dividend > 0:
            if forward_dividend < (precio_actual / 10): forward_dividend *= 100

        # FIX AÑADIDO: REEMPLAZAR EL AÑO ACTUAL INCOMPLETO POR EL FORWARD DIVIDEND
        dividendos_barras = divs_por_año.copy()
        if año_actual in dividendos_barras.index:
            dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

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

        # Extracción de métricas de calidad
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
                        if len(sh_data) >= 2:
                            acc_ini = sh_data.iloc[0]
                            acc_fin = sh_data.iloc[-1]
                            if acc_ini > 0: variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                            break
        except: pass

        dgr_5y = None
        if len(dividendos_barras) >= 6:
            div_actual = dividendos_barras.iloc[-1]
            div_5y = dividendos_barras.iloc[-6]
            if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100

        dgr_periodo = None
        if len(dividendos_barras) >= (años_analisis + 1):
            div_actual = dividendos_barras.iloc[-1]
            div_periodo = dividendos_barras.iloc[-(años_analisis + 1)]
            if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

        años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
        racha_sin_recortes = 0
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99:
                    racha_sin_recortes += 1
                else: break

        divs_recientes = dividendos_barras.tail(años_analisis + 1)
        incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

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
        except: pass
        
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
        except: pass

        # --- CÁLCULO DE SCORE CON ETIQUETAS DE PUNTUACIÓN DE CARA AL USUARIO ---
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

        # LÓGICA DE CHOWDER
        if (es_utility_pura or es_telecom) and yield_actual > 4.0: chowder_target = 8.0
        elif yield_actual >= 3.0: chowder_target = 12.0
        else: chowder_target = 15.0

        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0

        pts_fcf = "(+1.5p)" if cond_fcf else "(0p)"
        pts_pfcf = "(+1.5p)" if cond_pfcf else "(0p)"
        pts_deuda = "(+1.5p)" if cond_deuda else "(0p)"
        pts_hist = "(+1.5p)" if cond_historial else "(0p)"
        pts_aum = "(+1.0p)" if cond_aumentos else "(0p)"
        pts_acc = "(+1.0p)" if cond_acciones else "(0p)"
        pts_yield = "(+0.5p)" if cond_yield else "(0p)"
        pts_bpa = "(+0.5p)" if cond_bpa else "(0p)"
        pts_per = "(+0.5p)" if cond_per else "(0p)"
        pts_cons = "(+0.5p)" if cond_consistencia else "(0p)"

        dist_real_suelo = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 999.0
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0

        if precio_actual <= precio_compra: estado = "🎯 COMPRA"
        elif precio_actual >= precio_venta: estado = "🔴 SOBREVALORADA"
        else: estado = "🟡 MANTENER"

        sym_m = "€" if currency == "EUR" else ("£" if currency in ["GBP", "GBp"] else "$")

        return {
            "Estado": estado,
            "Ticker": ticker_symbol.strip().upper(),
            "Score Weiss": f"{score:.1f}/10",
            "Cotización Actual": f"{precio_actual / divisor_uk:.2f}{sym_m} ({dist_real_suelo:+.2f}%)",
            "Suelo (Infra)": f"{precio_compra / divisor_uk:.2f}{sym_m} ({pct_infra_vs_media:+.2f}%)" if precio_compra > 0 else "N/D",
            "Precio Justo": f"{precio_justo / divisor_uk:.2f}{sym_m}",
            "Techo (Sobre)": f"{precio_venta / divisor_uk:.2f}{sym_m} ({pct_sobre_vs_media:+.2f}%)" if precio_venta > 0 else "N/D",
            "Div. Neto": f"{div_neto_absoluto / divisor_uk:.2f}{sym_m}",
            "Yield Bruto": f"{yield_actual:.2f}% {pts_yield}",
            "Yield Neto": f"{yield_neto:.2f}%",
            "PER": f"{per:.2f} {pts_per}" if per > 0 else f"N/D {pts_per}",
            "P/FCF": f"{p_fcf:.2f} {pts_pfcf}" if p_fcf != -1 else f"N/D {pts_pfcf}",
            "Payout BPA": f"{payout_bpa:.2f}% {pts_bpa}",
            "Payout FCF": f"{payout_fcf:.2f}% {pts_fcf}" if payout_fcf != -1 else f"N/D {pts_fcf}",
            "Deuda/FCF": f"{deuda_fcf:.2f}A {pts_deuda}" if deuda_fcf != -1 else (f"Quema Caja {pts_deuda}" if total_debt > 0 else f"0.00A {pts_deuda}"),
            "Acciones": f"{variacion_acciones:+.2f}% {pts_acc}" if variacion_acciones is not None else f"N/D {pts_acc}",
            "Crec. BPA 3Y": f"{crecimiento_bpa_3y:+.2f}%" if crecimiento_bpa_3y is not None else "N/D",
            "Consist. BPA": f"{años_crecimiento_bpa}/{total_años_bpa_datos}A {pts_cons}",
            "DGR 5A": f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D",
            f"DGR {años_analisis}A": f"{dgr_periodo:.2f}%" if dgr_periodo is not None else "N/D",
            "Chowder": f"{chowder_number:.1f} (Obj: {chowder_target:.0f})" if chowder_number != -999.0 else "N/D",
            "Aumentos": f"{incrementos_dividendo} {pts_aum}",
            "Años Pag.": f"{años_pagando}A (R: {racha_sin_recortes}A) {pts_hist}",
            
            "_Dist_Suelo": dist_real_suelo,
            "_y_act": yield_actual, "_y_inf": yield_infravalorado, "_y_med": yield_medio,
            "_per": per, "_p_fcf": p_fcf, "_pb": pb, 
            "_sec": 1 if es_fin_ind else (2 if es_tech else 3),
            "_pay_bpa": payout_bpa, "_l_bpa": payout_lim_bpa, "_a_bpa": payout_ama_bpa,
            "_pay_fcf": payout_fcf, "_l_fcf": payout_lim_fcf, "_a_fcf": payout_ama_fcf,
            "_deuda": deuda_fcf,
            "_acc": variacion_acciones if variacion_acciones is not None else 999,
            "_dgr": dgr_5y if dgr_5y is not None else -999,
            "_dgr_per": dgr_periodo if dgr_periodo is not None else -999,
            "_hist": 1 if (años_pagando >= 25 and racha_sin_recortes >= 12) else 0,
            "_aum": incrementos_dividendo,
            "_cbpa3": crecimiento_bpa_3y if crecimiento_bpa_3y is not None else -999,
            "_cons": 1 if cond_consistencia else 0,
            "_score": score,
            "_chowder": chowder_number,
            "_chowder_target": chowder_target
        }
    except:
        return None

# ==========================================
# 3. MAQUETACIÓN EN PESTAÑAS (UI)
# ==========================================
st.title("Sistema Fundamental - Método Geraldine Weiss")

tab_individual, tab_masiva = st.tabs(["🔍 Análisis de Francotirador", "📑 Screener Múltiple (Radar)"])

with tab_individual:
    col_input1, col_input2, col_input3 = st.columns(3)
    with col_input1: ticker_input = st.text_input("Ticker individual:", "NVO").upper()
    with col_input2: años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)
    with col_input3: impuesto = st.number_input("Retención (%)", value=19.0, key="imp_ind")

    if st.button("Analizar Empresa"):
        with st.spinner(f"Analizando {ticker_input} en profundidad..."):
            try: screener_weiss_definitivo(ticker_input, años_analisis, impuesto)
            except Exception as e: st.error(f"Se ha producido un error: {e}")

with tab_masiva:
    st.markdown("### 📡 Radar Fundamental Completo por Lotes")
    st.markdown("La tabla está ordenada matemáticamente enseñando primero las mayores **gangas** respecto al Suelo Fundamental.")
    st.markdown("> *Nota: El porcentaje de la 'Cotización Actual' indica a qué distancia exacta se encuentra de su **Suelo de Compra**. Las métricas de puntuación indican explícitamente cuánto aportan al Score global.*")
    
    tickers_masivos = st.text_area("Lista de Tickers (separados por comas):", "NVO, LOW, ACN, MSFT, JNJ, PG, PEP, HD")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1: años_masivos = st.selectbox("Periodo para canal histórico:", [5, 10, 12, 15, 20], index=2, key="años_mas")
    with col_m2: impuesto_masivo = st.number_input("Retención (%)", value=19.0, key="imp_mas")

    if st.button("🚀 Escanear Watchlist"):
        lista_tickers = [t.strip() for t in tickers_masivos.split(",") if t.strip()]
        
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
                df_res = pd.DataFrame(resultados).sort_values(by="_Dist_Suelo")
                
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
                        elif col_name == 'P/B':
                            pb = row['_pb']
                            sec = row['_sec']
                            if pb <= 0: styles[idx] = 'color: #ff4b4b;'
                            else:
                                lv, la = (1.5, 2.5) if sec == 1 else ((5.0, 10.0) if sec == 2 else (2.5, 5.0))
                                if pb <= lv: styles[idx] = 'color: #21c354;'
                                elif pb <= la: styles[idx] = 'color: #faca2b;'
                                else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Payout BPA':
                            p = row['_pay_bpa']
                            if 0 < p <= row['_l_bpa']: styles[idx] = 'color: #21c354;'
                            elif p <= row['_a_bpa']: styles[idx] = 'color: #faca2b;'
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
                        elif col_name == 'Acciones':
                            a = row['_acc']
                            if a < -0.5: styles[idx] = 'color: #21c354;'
                            elif a <= 1.0: styles[idx] = 'color: #faca2b;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Crec. BPA 3Y':
                            c = row['_cbpa3']
                            if c != -999 and c > 0: styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Consist. BPA':
                            if row['_cons'] == 1: styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'DGR 5A':
                            d = row['_dgr']
                            if d >= 10.0: styles[idx] = 'color: #21c354;'
                            elif d >= 7.5: styles[idx] = 'color: #faca2b;'
                            elif d >= 5.0: styles[idx] = 'color: #ff9800;'
                            elif d >= 2.5: styles[idx] = 'color: #ff7043;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == f'DGR {años_masivos}A':
                            d = row['_dgr_per']
                            if d >= 10.0: styles[idx] = 'color: #21c354;'
                            elif d >= 7.5: styles[idx] = 'color: #faca2b;'
                            elif d >= 5.0: styles[idx] = 'color: #ff9800;'
                            elif d >= 2.5: styles[idx] = 'color: #ff7043;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Chowder':
                            c_num = row['_chowder']
                            c_tar = row['_chowder_target']
                            if c_num != -999.0:
                                if c_num >= c_tar: styles[idx] = 'color: #21c354; font-weight: bold;'
                                else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Aumentos':
                            if row['_aum'] >= min(5, años_masivos): styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #ff4b4b;'
                        elif col_name == 'Años Pag.':
                            if row['_hist'] == 1: styles[idx] = 'color: #21c354;'
                            else: styles[idx] = 'color: #faca2b;'
                        elif col_name == 'Estado':
                            if "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: white;'
                            elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: white;'
                            else: styles[idx] = 'background-color: #4d4d00; color: white;'
                    return styles
                
                columnas_visibles = [c for c in df_res.columns if not c.startswith('_')]
                styled_df = df_res.style.apply(color_row, axis=1)
                st.dataframe(styled_df, column_order=columnas_visibles, use_container_width=True)
                
                df_export = df_res[columnas_visibles]
                csv = df_export.to_csv(index=False, sep=';', decimal=',').encode('utf-8')
                st.download_button(
                    label="💾 Descargar CSV para Google Sheets",
                    data=csv,
                    file_name=f"Screener_Multi_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No se pudieron recopilar canales históricos válidos para los tickers introducidos.")
