import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Ignorar advertencias menores
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Screener Geraldine Weiss", page_icon="📊", layout="wide")

# Diccionario de respaldo: Solo traduce lo que es seguro, el resto se queda en inglés
TRADUCCION = {
    'Technology': 'Tecnología', 'Healthcare': 'Salud', 'Financial Services': 'Servicios Financieros',
    'Consumer Cyclical': 'Consumo Cíclico', 'Industrials': 'Industrial', 'Consumer Defensive': 'Consumo Defensivo',
    'Energy': 'Energía', 'Real Estate': 'Inmobiliario', 'Utilities': 'Servicios Públicos',
    'Basic Materials': 'Materiales Básicos', 'Communication Services': 'Servicios de Comunicación'
}

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

    payout_ratio = get_safe('payoutRatio') * 100
    per = get_safe('trailingPE', get_safe('forwardPE'))
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

    # ==========================================
    # INTERFAZ VISUAL STREAMLIT
    # ==========================================
    tipo_empresa_txt = "🏢 Sector Inmobiliario/Regulado (Filtros Flexibles)" if es_regulada_o_reit else "🏭 Sector Industrial/General (Filtros Estrictos)"
    
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")
    
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 10px; border-radius: 5px; margin-bottom: 20px;">
        <strong>Sector:</strong> {sector_final} &nbsp;&nbsp;|&nbsp;&nbsp; 
        <strong>Industry:</strong> {industry_final}
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🌍 Perfil Fiscal y Retención en Origen")
    if pais in ['United States', 'Netherlands', 'Canada']: st.success(f"✅ **{pais}**: Retención 15%. Recuperable 100% por doble imposición. Eficiencia fiscal máxima.")
    elif pais == 'United Kingdom': st.success(f"✅ **{pais}**: Retención 0% (salvo REITs). Excelente para la rentabilidad neta.")
    elif pais == 'Spain': st.success(f"✅ **{pais}**: Retención local 19%. Sin fricciones internacionales.")
    elif pais == 'Ireland': st.warning(f"⚠️ **{pais}**: Retención 25% (Irlanda). Peligro de perder un 10% irrecuperable según gestión del bróker.")
    elif pais in ['France', 'Germany', 'Switzerland']: st.error(f"❌ **{pais}**: Retención muy alta (>26%). Trámites burocráticos complejos para recuperar exceso.")
    else: st.info(f"ℹ️ **{pais}**: Verifica el convenio de doble imposición.")

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

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

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

    st.markdown("<br>", unsafe_allow_html=True)
    if score >= 8.0: st.success(f"🏆 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Sobresaliente. Fuerte generación de caja y altísima seguridad.")
    elif score >= 5.0: st.warning(f"⚖️ **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Empresa Aceptable. Tiene solidez pero presenta debilidades en su flujo de efectivo o valoración.")
    else: st.error(f"🚨 **BLUE CHIP SCORE WEISS: {score:.1f}/10** — Calidad Insuficiente. No supera los filtros de caja real y seguridad.")

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
        fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("📊 Beneficios, Proyecciones y Acciones")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("BPA Actual", f"{bpa_trailing / divisor_uk:.2f}{sym}" if bpa_trailing != 0 else "N/D")
    c2.metric("BPA Esperado (Forward)", f"{bpa_forward / divisor_uk:.2f}{sym}" if bpa_forward != 0 else "N/D")
    c3.metric("PER Futuro", f"{per_forward:.2f}" if per_forward != 0 else "N/D")
    c4.metric("Crecimiento BPA (3Y)", f"{crecimiento_bpa_3y:.2f}%" if crecimiento_bpa_3y is not None else "N/D")
    
    if variacion_acciones is not None:
        signo = "+" if variacion_acciones > 0 else ""
        if variacion_acciones < -0.5: estado_acc, color_acc = "- Recomprando", "inverse"
        elif variacion_acciones <= 1.0: estado_acc, color_acc = "Estable", "off"
        else: estado_acc, color_acc = "+ Diluyendo", "inverse"
        c5.metric(f"Acciones ({años_analisis}Y)", f"{signo}{variacion_acciones:.2f}%", delta=estado_acc, delta_color=color_acc)
    else: c5.metric(f"Acciones ({años_analisis}Y)", "N/D")

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

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🔮 Proyección de Rentabilidad sobre Coste (Yield on Cost a 15 Años)")
    
    val_5y = dgr_5y if dgr_5y is not None else -1
    val_periodo = dgr_periodo if dgr_periodo is not None else -1

    if val_5y > 0 and val_periodo > 0:
        if val_5y < val_periodo: dgr_proyeccion = val_5y; txt_ritmo = "Ritmo Conservador (5A)"
        else: dgr_proyeccion = val_periodo; txt_ritmo = f"Ritmo Conservador ({años_analisis}A)"
    elif val_5y > 0: dgr_proyeccion = val_5y; txt_ritmo = "Ritmo Disponible (5A)"
    elif val_periodo > 0: dgr_proyeccion = val_periodo; txt_ritmo = f"Ritmo Disponible ({años_analisis}A)"
    else: dgr_proyeccion = 0.0; txt_ritmo = "Crecimiento Estancado"
    
    dgr_proyeccion = min(dgr_proyeccion, 15.0)
    años_proyeccion = list(range(1, 16))
    div_bruto_proyectado = [forward_dividend * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_bruto_lista = [yield_actual * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_neto_lista = [bruto * net_mult for bruto in yoc_bruto_lista]
    
    x_labels_yoc = []
    for año, yoc_n in zip(años_proyeccion, yoc_neto_lista):
        año_futuro = año_actual + año
        x_labels_yoc.append(f"{año_futuro}<br><span style='color:#faca2b; font-size:12px'>{yoc_n:.1f}%</span>")

    fig_yoc = go.Figure()
    fig_yoc.add_trace(go.Bar(x=x_labels_yoc, y=div_bruto_proyectado, name=f'Div. Esperado ({sym})', marker_color='#00d4ff', yaxis='y1', text=[f"{val:.2f}{sym}" for val in div_bruto_proyectado], textposition='auto'))
    fig_yoc.add_trace(go.Scatter(x=x_labels_yoc, y=yoc_neto_lista, name="YoC Neto (%)", mode='lines+markers', line=dict(color='#21c354', width=3), marker=dict(size=8), yaxis='y2'))
    fig_yoc.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="YoC Neto (%)", font=dict(color="#faca2b")), tickfont=dict(color="#faca2b"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), title=dict(text=f"Basado en {txt_ritmo}: +{dgr_proyeccion:.1f}% anual constante", font=dict(size=14, color="#aaa")))
    st.plotly_chart(fig_yoc, use_container_width=True)

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
            fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_divs, use_container_width=True)

    st.divider()
    st.subheader(f"📋 Decálogo de Calidad del Blue Chip ({años_analisis} Años)")
    
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

    st.markdown("#### 📈 4. Historial y Crecimiento")
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
        else: st.error(f"{t_info} Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Estancado)")

    if dgr_periodo is not None:
        if dgr_periodo >= 10: st.success(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Excelente ritmo continuo)")
        elif dgr_periodo > 0: st.warning(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Sostenido)")
        else: st.error(f"{t_info} Crecimiento DGR {años_analisis}A (Periodo): {dgr_periodo:.2f}% (Estancado)")

    st.markdown("#### 🏢 5. Fortaleza Institucional")
    if market_cap > 10_000_000_000: st.success(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Gran capitalización institucional)")
    else: st.error(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Capitalización pequeña)")

    if respaldo_institucional > 0:
        if respaldo_institucional >= 50.0: st.success(f"{t_info} Respaldo Institucional: {respaldo_institucional:.1f}% en manos de Fondos/Bancos (Cumple criterio de respaldo institucional)")
        else: st.warning(f"{t_info} Respaldo Institucional: {respaldo_institucional:.1f}% (Interés institucional bajo o fragmentado)")
    else: st.warning(f"{t_info} Respaldo Institucional: Datos no disponibles en Yahoo")

    # ==========================================
    # PANEL TÉCNICO MACD, VOLUMEN Y BANDAS WEISS (Corto Plazo)
    # ==========================================
    st.divider()
    st.markdown("### ⏱️ Timing de Entrada: Análisis Técnico a Corto Plazo (1 Año)")
    st.markdown("> **Uso según el Método Weiss:** Busca picos de volumen rojo extremo (Capitulación) cuando las velas crucen o toquen la línea verde discontinua (Suelo Fundamental). Dispara cuando el MACD cruce al alza perdiendo inercia bajista.")

    fecha_tecnico = pd.Timestamp.now().normalize() - pd.DateOffset(years=1)
    
    # Extraemos df_tech de historial_analisis para poder heredar la columna 'Div_Anual'
    df_tech = historial_analisis[historial_analisis.index >= fecha_tecnico].copy()

    if len(df_tech) > 30: 
        # Calculamos los precios objetivo para las bandas en el corto plazo
        df_tech['Precio_Compra'] = (df_tech['Div_Anual'] / yield_infravalorado) * 100
        df_tech['Precio_Justo'] = (df_tech['Div_Anual'] / yield_medio) * 100
        df_tech['Precio_Venta'] = (df_tech['Div_Anual'] / yield_sobrevalorado) * 100

        if currency == 'GBp':
            for col in ['Open', 'High', 'Low', 'Close', 'Precio_Compra', 'Precio_Justo', 'Precio_Venta']: 
                df_tech[col] = df_tech[col] / divisor_uk

        # Cálculo manual de MACD (12, 26, 9)
        ema12 = df_tech['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df_tech['Close'].ewm(span=26, adjust=False).mean()
        df_tech['MACD'] = ema12 - ema26
        df_tech['Signal'] = df_tech['MACD'].ewm(span=9, adjust=False).mean()
        df_tech['Histogram'] = df_tech['MACD'] - df_tech['Signal']

        colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for index, row in df_tech.iterrows()]
        colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']]

        fig_tech = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                 vertical_spacing=0.03, 
                                 row_heights=[0.5, 0.2, 0.3])

        # Fila 1: Velas Japonesas
        fig_tech.add_trace(go.Candlestick(
            x=df_tech.index, open=df_tech['Open'], high=df_tech['High'],
            low=df_tech['Low'], close=df_tech['Close'], name='Precio',
            increasing_line_color='#21c354', decreasing_line_color='#ff4b4b',
            showlegend=False
        ), row=1, col=1)

        # Fila 1: Bandas de Valoración Superpuestas
        fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True), row=1, col=1)
        fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True), row=1, col=1)
        fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)

        # Fila 2: Volumen
        fig_tech.add_trace(go.Bar(
            x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False
        ), row=2, col=1)

        # Fila 3: MACD
        fig_tech.add_trace(go.Bar(
            x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False
        ), row=3, col=1)
        fig_tech.add_trace(go.Scatter(
            x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False
        ), row=3, col=1)
        fig_tech.add_trace(go.Scatter(
            x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False
        ), row=3, col=1)

        # Diseño del gráfico
        fig_tech.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=650,
            showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis_rangeslider_visible=False 
        )
        
        fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        
        st.plotly_chart(fig_tech, use_container_width=True)
    else:
        st.info("No hay suficientes datos recientes en Yahoo Finance para calcular el panel técnico (MACD/Volumen).")

# --- FRONTEND DE LA APLICACIÓN ---
st.title("Screener Fundamental - Método Geraldine Weiss")
ticker_input = st.text_input("Ticker:", "WKL.AS").upper()
años_analisis = st.selectbox("Periodo:", [5, 10, 12, 15, 20], index=2)
impuesto = st.number_input("Retención (%)", value=19.0)

if st.button("Analizar"):
    with st.spinner(f"Analizando {ticker_input} a {años_analisis} años..."):
        try: 
            screener_weiss_definitivo(ticker_input, años_analisis, impuesto)
        except Exception as e: 
            st.error(f"Se ha producido un error al descargar los datos: {e}")
