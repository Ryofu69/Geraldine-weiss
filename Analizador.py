import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io 

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
            st.success(f"🥣 **REGLA DE CHOWDER: APROBADA ({chowder_number:.1f})** — Supera el objetivo exigido de {chowder_target:.0f}.")
        else:
            txt_precio_c = f" Cotiza a {precio_actual / divisor_uk:.2f}{sym} y debería cotizar a {precio_obj_chowder / divisor_uk:.2f}{sym} para cumplir." if (precio_obj_chowder is not None and yield_req_chowder > 0) else ""
            st.error(f"🥣 **REGLA DE CHOWDER: SUSPENSA ({chowder_number:.1f})** — No alcanza el objetivo exigido de {chowder_target:.0f}.{txt_precio_c}")
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

        # --- ESTADÍSTICAS DE TOQUES ZONAS ---
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
        historial = ticker.history(period="15y", auto_adjust=False)
        
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

        # --- CÁLCULO DE SCORE ---
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
            "Chowder": f"{chowder_number:.1f} (Obj: {chowder_target:.0f})" if chowder_number != -999.0 else "N/D",
            "Cotización Actual": f"{precio_actual / divisor_uk:.2f}{sym_m} ({dist_real_suelo:+.2f}%)",
            "Suelo (Infra)": f"{precio_compra / divisor_uk:.2f}{sym_m} ({pct_infra_vs_media:+.2f}%)" if precio_compra > 0 else "N/D",
            "Precio Justo": f"{precio_justo / divisor_uk:.2f}{sym_m}",
            "Techo (Sobre)": f"{precio_venta / divisor_uk:.2f}{sym_m} ({pct_sobre_vs_media:+.2f}%)" if precio_venta > 0 else "N/D",
            "Div. Neto": f"{div_neto_absoluto / divisor_uk:.2f}{sym_m}",
            "Yield Bruto": f"{yield_actual:.2f}% {pts_yield}",
            "Yield Neto": f"{yield_neto:.2f}%",
            "PER": f"{per:.2f} {pts_per}" if per > 0 else f"N/D {pts_per}",
            "P/FCF": f"{p_fcf:.2f} {pts_pfcf}" if p_fcf != -1 else f"N/D {pts_pfcf}",
            "P/B": f"{pb:.2f}x" if pb > 0 else "N/D",
            "Payout BPA": f"{payout_bpa:.2f}% {pts_bpa}",
            "Payout FCF": f"{payout_fcf:.2f}% {pts_fcf}" if payout_fcf != -1 else f"N/D {pts_fcf}",
            "Deuda/FCF": f"{deuda_fcf:.2f}A {pts_deuda}" if deuda_fcf != -1 else (f"Quema Caja {pts_deuda}" if total_debt > 0 else f"0.00A {pts_deuda}"),
            "Acciones": f"{variacion_acciones:+.2f}% {pts_acc}" if variacion_acciones is not None else f"N/D {pts_acc}",
            "Crec. BPA 3Y": f"{crecimiento_bpa_3y:+.2f}%" if crecimiento_bpa_3y is not None else "N/D",
            "Consist. BPA": f"{años_crecimiento_bpa}/{total_años_bpa_datos}A {pts_cons}",
            "DGR 5A": f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D",
            f"DGR {años_analisis}A": f"{dgr_periodo:.2f}%" if dgr_periodo is not None else "N/D",
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

tab_individual, tab_masiva, tab_cartera = st.tabs(["🔍 Análisis de Francotirador", "📑 Screener Múltiple (Radar)", "💼 Mi Cartera Privada"])

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

# --- PESTAÑA 3: TU CARTERA PRIVADA ---
with tab_cartera:
    st.markdown("### 💼 Control de Rentabilidad en Tiempo Real")
    st.markdown("> *Privacidad garantizada: Tus datos solo se procesan en la memoria temporal de tu navegador. Ningún dato se guarda en servidores de terceros ni se sube a GitHub.*")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        metodo_carga = st.radio("¿Cómo quieres cargar tu cartera?", ["📂 Subir Archivo", "📝 Pegar Texto (Recomendado)"])
    with col_c2:
        impuesto_cart = st.number_input("Retención media de dividendos (%)", value=19.0, key="imp_cart_3")
    
    df_ops = None
    
    if metodo_carga == "📂 Subir Archivo":
        archivo_subido = st.file_uploader("Sube tu historial de operaciones (CSV o Excel)", type=["csv", "xlsx"])
        if archivo_subido is not None:
            try:
                if archivo_subido.name.endswith('.csv'):
                    df_ops = pd.read_csv(archivo_subido, sep=None, engine='python')
                else:
                    df_ops = pd.read_excel(archivo_subido)
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")
                
    else:
        st.info("Pega directamente el contenido de tu CSV a continuación. Asegúrate de incluir los encabezados: Fecha, Ticker, Operacion, Acciones, Precio.")
        texto_csv = st.text_area("Pega aquí el contenido de tu CSV:", height=200)
        if texto_csv:
            try:
                df_ops = pd.read_csv(io.StringIO(texto_csv), sep=None, engine='python')
            except Exception as e:
                st.error(f"Error al leer el texto pegado: {e}")

    if df_ops is not None:
        try:
            columnas_requeridas = ['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio']
            if not all(col in df_ops.columns for col in columnas_requeridas):
                st.error(f"❌ Error de formato. El archivo debe contener exactamente estas columnas (respetando mayúsculas): {', '.join(columnas_requeridas)}")
            else:
                df_ops['Fecha'] = pd.to_datetime(df_ops['Fecha'], errors='coerce', dayfirst=True)
                df_ops = df_ops.dropna(subset=['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio'])
                df_ops = df_ops.sort_values('Fecha')
                
                años_unicos = sorted(df_ops['Fecha'].dt.year.dropna().unique())
                opciones_año = ["Todo el Historial"] + [str(int(a)) for a in años_unicos]
                
                tickers_unicos_raw = sorted(df_ops['Ticker'].str.strip().str.upper().unique().tolist())
                opciones_ticker = ["Todas las Empresas"] + tickers_unicos_raw
                
                st.markdown("---")
                st.markdown("#### 🎯 Filtros Analíticos de Cartera")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    año_filtro = st.selectbox("📅 Selecciona Año de Compra (Modo Añada):", opciones_año)
                with col_f2:
                    ticker_filtro = st.selectbox("🏢 Selecciona Empresa a Inspeccionar:", opciones_ticker)
                
                if año_filtro != "Todo el Historial":
                    df_ops = df_ops[(df_ops['Fecha'].dt.year == int(año_filtro)) & (df_ops['Operacion'].str.capitalize() == 'Compra')]
                
                if ticker_filtro != "Todas las Empresas":
                    df_ops = df_ops[df_ops['Ticker'].str.strip().str.upper() == ticker_filtro]
                
                if df_ops.empty:
                    st.warning("No hay operaciones válidas con los filtros seleccionados.")
                else:
                    min_date = df_ops['Fecha'].min()
                    tickers_unicos = df_ops['Ticker'].str.strip().str.upper().unique().tolist()
                    
                    datos_historicos = pd.DataFrame()
                    datos_dividendos = pd.DataFrame()
                    
                    with st.spinner("Descargando precios reales (sin ajustes) y rastreando dividendos desde Yahoo Finance..."):
                        for t in tickers_unicos:
                            try:
                                tk = yf.Ticker(t)
                                hist = tk.history(start=min_date, auto_adjust=False)
                                if not hist.empty:
                                    if tk.info.get('currency') == 'GBp':
                                        hist['Close'] = hist['Close'] / 100.0
                                        if 'Dividends' in hist.columns:
                                            hist['Dividends'] = hist['Dividends'] / 100.0
                                            
                                    datos_historicos[t] = hist['Close']
                                    if 'Dividends' in hist.columns:
                                        datos_dividendos[t] = hist['Dividends']
                                    else:
                                        datos_dividendos[t] = 0.0
                            except Exception:
                                pass
                                
                    if not datos_historicos.empty:
                        datos_historicos.index = datos_historicos.index.tz_localize(None).normalize()
                        datos_dividendos.index = datos_dividendos.index.tz_localize(None).normalize()
                        
                        rango_fechas = pd.date_range(start=min_date.normalize(), end=pd.Timestamp.today().normalize())
                        
                        datos_historicos = datos_historicos.reindex(rango_fechas).ffill().fillna(0)
                        datos_dividendos = datos_dividendos.reindex(rango_fechas).fillna(0)
                        
                        daily_shares = pd.DataFrame(0.0, index=datos_historicos.index, columns=tickers_unicos)
                        daily_invested = pd.Series(0.0, index=datos_historicos.index)
                        
                        current_shares = {t: 0.0 for t in tickers_unicos}
                        current_cost = {t: 0.0 for t in tickers_unicos}
                        total_invested = 0.0
                        
                        for date in datos_historicos.index:
                            ops_today = df_ops[df_ops['Fecha'].dt.date == date.date()]
                            for _, row in ops_today.iterrows():
                                t = row['Ticker'].strip().upper()
                                op = row['Operacion'].strip().capitalize()
                                acc = float(row['Acciones'])
                                precio = float(row['Precio'])
                                
                                if op == 'Compra':
                                    current_shares[t] += acc
                                    coste = acc * precio
                                    current_cost[t] += coste
                                    total_invested += coste
                                elif op == 'Venta':
                                    if current_shares.get(t, 0) > 0:
                                        pmp = current_cost[t] / current_shares[t]
                                        current_shares[t] -= acc
                                        coste_reducido = acc * pmp
                                        current_cost[t] -= coste_reducido
                                        total_invested -= coste_reducido
                                        
                            for t in tickers_unicos:
                                daily_shares.at[date, t] = current_shares.get(t, 0.0)
                            daily_invested.at[date] = total_invested
                            
                        daily_value = (daily_shares * datos_historicos).sum(axis=1)
                        
                        daily_shares_shifted = daily_shares.shift(1).fillna(0)
                        daily_gross_divs = (daily_shares_shifted * datos_dividendos).sum(axis=1)
                        daily_net_divs = daily_gross_divs * (1 - (impuesto_cart / 100.0))
                        
                        accumulated_divs = daily_net_divs.cumsum()
                        total_patrimonio = daily_value + accumulated_divs
                        
                        st.markdown("#### 📈 Evolución de tu Patrimonio")
                        fig_cartera = go.Figure()
                        
                        fig_cartera.add_trace(go.Scatter(
                            x=daily_invested.index, y=daily_invested.values, 
                            mode='lines', line=dict(color='#faca2b', width=2, dash='dash'), 
                            name='Capital Aportado'
                        ))
                        
                        fig_cartera.add_trace(go.Scatter(
                            x=daily_value.index, y=daily_value.values, 
                            mode='lines', line=dict(color='#21c354', width=2), 
                            name='Valor Mercado (Precio Real)'
                        ))
                        
                        fig_cartera.add_trace(go.Scatter(
                            x=accumulated_divs.index, y=accumulated_divs.values, 
                            fill='tozeroy', mode='lines', 
                            line=dict(color='#00d4ff', width=2), 
                            fillcolor='rgba(0, 212, 255, 0.15)', 
                            name='Dividendos Netos Acumulados'
                        ))
                        
                        fig_cartera.add_trace(go.Scatter(
                            x=total_patrimonio.index, y=total_patrimonio.values, 
                            mode='lines', line=dict(color='#e040fb', width=2.5), 
                            name='Patrimonio Total (Mercado + Divs)'
                        ))
                        
                        fig_cartera.update_layout(
                            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=450,
                            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig_cartera, use_container_width=True)

                        posiciones_activas = {t: current_shares[t] for t in tickers_unicos if current_shares[t] > 0.001}
                        if posiciones_activas:
                            inversion_final = daily_invested.iloc[-1]
                            valor_mercado_final = daily_value.iloc[-1]
                            divs_cobrados_totales = accumulated_divs.iloc[-1]
                            patrimonio_final = total_patrimonio.iloc[-1]
                            
                            b_l_mercado = valor_mercado_final - inversion_final
                            b_total_global = b_l_mercado + divs_cobrados_totales
                            
                            rent_precio_global_pct = ((valor_mercado_final - inversion_final) / inversion_final * 100) if inversion_final > 0 else 0
                            pct_divs_sobre_inversion = (divs_cobrados_totales / inversion_final * 100) if inversion_final > 0 else 0
                            rent_total_pct = ((patrimonio_final - inversion_final) / inversion_final * 100) if inversion_final > 0 else 0
                            
                            st.markdown("#### 🌐 Resumen Global Hoy")
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Capital Invertido", f"{inversion_final:,.2f}")
                            c2.metric("Valor Mercado (Sin Divs)", f"{valor_mercado_final:,.2f}", f"{rent_precio_global_pct:+.2f}% ({b_l_mercado:+,.2f} Abs.)")
                            c3.metric("Dividendos Cobrados", f"{divs_cobrados_totales:,.2f}", f"{pct_divs_sobre_inversion:+.2f}% del Capital")
                            c4.metric("Rentab. Total (Con Divs)", f"{rent_total_pct:+.2f}%", f"{b_total_global:+,.2f} Abs. Total")
                            
                            divs_per_ticker = (daily_shares_shifted * datos_dividendos).sum(axis=0) * (1 - (impuesto_cart / 100.0))
                            
                            resultados_tabla = []
                            for t, acc in posiciones_activas.items():
                                p_live = datos_historicos[t].iloc[-1]
                                p_medio = current_cost[t] / acc if acc > 0 else 0
                                v_mercado = acc * p_live
                                divs_cobrados_accion = divs_per_ticker[t]
                                
                                b_abs_mercado = v_mercado - current_cost[t]
                                b_total = b_abs_mercado + divs_cobrados_accion
                                
                                rent_precio_pct = (b_abs_mercado / current_cost[t]) * 100 if current_cost[t] > 0 else 0
                                rent_total_pct = (b_total / current_cost[t]) * 100 if current_cost[t] > 0 else 0
                                
                                resultados_tabla.append({
                                    "Ticker": t,
                                    "Acciones": round(acc, 4),
                                    "Precio Medio": p_medio,
                                    "Precio Live": p_live,
                                    "Valor Mercado": v_mercado,
                                    "P/L Latente": b_abs_mercado,
                                    "Divs. Cobrados": divs_cobrados_accion,
                                    "Bº Total (Abs)": b_total,
                                    "Rentab. Precio (%)": rent_precio_pct,
                                    "Rentab. Total (%)": rent_total_pct
                                })
                            
                            resultados_tabla_ordenados = sorted(resultados_tabla, key=lambda k: k['Rentab. Total (%)'], reverse=True)
                                
                            st.markdown("#### 📋 Posiciones Abiertas (Tabla Detallada)")
                            df_mostrar = pd.DataFrame(resultados_tabla_ordenados)
                            
                            def color_rent(val):
                                color = '#21c354' if val > 0 else '#ff4b4b'
                                return f'color: {color}; font-weight: bold;'
                                
                            def color_divs(val):
                                color = '#00d4ff' if val > 0 else '#aaaaaa'
                                return f'color: {color};'
                            
                            formato_columnas = {
                                "Precio Medio": "{:.2f}",
                                "Precio Live": "{:.2f}",
                                "Valor Mercado": "{:,.2f}",
                                "P/L Latente": "{:+.2f}",
                                "Divs. Cobrados": "{:,.2f}",
                                "Bº Total (Abs)": "{:+.2f}",
                                "Rentab. Precio (%)": "{:+.2f}%",
                                "Rentab. Total (%)": "{:+.2f}%"
                            }
                            
                            styled_df = (df_mostrar.style
                                        .format(formato_columnas)
                                        .map(color_rent, subset=['Rentab. Precio (%)', 'Rentab. Total (%)', 'P/L Latente', 'Bº Total (Abs)'])
                                        .map(color_divs, subset=['Divs. Cobrados']))
                                        
                            st.dataframe(styled_df, use_container_width=True, hide_index=True)
                            
                            if divs_cobrados_totales > 0:
                                st.markdown("---")
                                st.markdown("#### 🗓️ Calendario Histórico de Dividendos Netos")
                                
                                df_divs_hist = pd.DataFrame({'Fecha': daily_net_divs.index, 'Dividendo': daily_net_divs.values})
                                df_divs_hist = df_divs_hist[df_divs_hist['Dividendo'] > 0]
                                
                                if not df_divs_hist.empty:
                                    df_divs_hist['Año'] = df_divs_hist['Fecha'].dt.year
                                    df_divs_hist['Mes'] = df_divs_hist['Fecha'].dt.month
                                    
                                    meses_str = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 
                                                 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                                    
                                    agrupado_meses = df_divs_hist.groupby(['Año', 'Mes'])['Dividendo'].sum().reset_index()
                                    anual_divs = df_divs_hist.groupby('Año')['Dividendo'].sum().reset_index()
                                    anual_divs['Crecimiento YoY (%)'] = anual_divs['Dividendo'].pct_change() * 100
                                    
                                    col_cal1, col_cal2 = st.columns([2.5, 1])
                                    
                                    with col_cal1:
                                        st.markdown("##### 📊 Ingresos Mensuales (Comparativa Anual)")
                                        fig_meses = go.Figure()
                                        años_presentes = sorted(agrupado_meses['Año'].unique())
                                        nombres_meses = [meses_str[i] for i in range(1, 13)]
                                        
                                        for año in años_presentes:
                                            datos_año = agrupado_meses[agrupado_meses['Año'] == año]
                                            y_valores = []
                                            for m in range(1, 13):
                                                fila_mes = datos_año[datos_año['Mes'] == m]
                                                if not fila_mes.empty:
                                                    y_valores.append(fila_mes['Dividendo'].values[0])
                                                else:
                                                    y_valores.append(0.0)
                                            
                                            fig_meses.add_trace(go.Bar(
                                                x=nombres_meses, y=y_valores, name=str(año)
                                            ))
                                            
                                        fig_meses.update_layout(
                                            barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=350,
                                            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), yaxis=dict(title="Dividendos Netos")
                                        )
                                        st.plotly_chart(fig_meses, use_container_width=True)
                                        
                                    with col_cal2:
                                        st.markdown("##### 📈 Resumen por Años (YoY)")
                                        def color_yoy(val):
                                            if pd.isna(val): return ''
                                            color = '#21c354' if val > 0 else ('#ff4b4b' if val < 0 else '#aaaaaa')
                                            return f'color: {color}; font-weight: bold;'
                                            
                                        styled_anual = anual_divs.style.format({
                                            'Dividendo': '{:,.2f}',
                                            'Crecimiento YoY (%)': '{:+.2f}%'
                                        }).map(color_yoy, subset=['Crecimiento YoY (%)'])
                                        st.dataframe(styled_anual, use_container_width=True, hide_index=True)

                            st.markdown("---")
                            st.markdown("#### 📊 Rentabilidad por Empresa (Precio vs Total con Dividendos)")
                            
                            x_tickers = []
                            y_rent_precio = []
                            y_rent_total = []
                            colores_precio = []

                            for res in resultados_tabla_ordenados:
                                x_tickers.append(res['Ticker'])
                                r_precio = res['Rentab. Precio (%)']
                                r_total = res['Rentab. Total (%)']
                                y_rent_precio.append(r_precio)
                                y_rent_total.append(r_total)
                                colores_precio.append('#21c354' if r_precio >= 0 else '#ff4b4b')
                            
                            fig_comp = go.Figure()
                            
                            fig_comp.add_trace(go.Bar(
                                x=x_tickers, y=y_rent_precio, name='Solo Cotización (Mercado)',
                                marker_color=colores_precio, text=[f"{val:+.1f}%" for val in y_rent_precio], textposition='auto'
                            ))
                            
                            fig_comp.add_trace(go.Bar(
                                x=x_tickers, y=y_rent_total, name='Total (Mercado + Dividendos)',
                                marker_color='#00d4ff', text=[f"{val:+.1f}%" for val in y_rent_total], textposition='auto'
                            ))
                            
                            fig_comp.update_layout(
                                barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=400,
                                hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
                            )
                            fig_comp.update_yaxes(title_text="Rentabilidad (%)")
                            st.plotly_chart(fig_comp, use_container_width=True)
                            
                    else:
                        st.error("No se han podido descargar los datos históricos para las empresas de tu archivo.")

        except Exception as e:
            st.error(f"No se pudo procesar el archivo. Verifica que las fechas estén correctas. Detalle: {e}")
