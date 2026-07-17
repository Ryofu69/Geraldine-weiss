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

# Diccionario de respaldo
TRADUCCION = {
    'Technology': 'Tecnología', 'Healthcare': 'Salud', 'Financial Services': 'Servicios Financieros',
    'Consumer Cyclical': 'Consumo Cíclico', 'Industrials': 'Industrial', 'Consumer Defensive': 'Consumo Defensivo',
    'Energy': 'Energía', 'Real Estate': 'Inmobiliario', 'Utilities': 'Servicios Públicos',
    'Basic Materials': 'Materiales Básicos', 'Communication Services': 'Servicios de Comunicación'
}

# ==========================================
# 1. FUNCIÓN DE ANÁLISIS INDIVIDUAL (Intacta)
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

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

    # ==========================================
    # 1. GRÁFICO EVOLUCIÓN HISTÓRICA (Largo Plazo)
    # ==========================================
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

    # ==========================================
    # 2. PANEL TÉCNICO MACD, VOLUMEN Y BANDAS WEISS (Vista Lupa 2 Meses)
    # ==========================================
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
            
            # --- MÓDULO DE ANÁLISIS AUTOMÁTICO SINCRONIZADO CON COTIZACIÓN ACTUAL ---
            ult_close_val = precio_actual / divisor_uk
            ult_suelo_val = precio_compra / divisor_uk
            
            precio_str = f"{ult_close_val:.2f}{sym}"
            suelo_str = f"{ult_suelo_val:.2f}{sym}"

            if ult_suelo_val > 0:
                dist_suelo = ((ult_close_val - ult_suelo_val) / ult_suelo_val) * 100
            else:
                dist_suelo = 999.0

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
                if descuento_extra > 0.5:
                    analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) cotiza un **{descuento_extra:.1f}% por debajo** de tu Suelo Fundamental ({suelo_str}). "
                else:
                    analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) está tocando el Suelo Fundamental ({suelo_str}). "
                
                if vol_elevado: analisis_ia += "Se detecta volumen extremo reciente (posible capitulación). "
                if ult_macd > ult_signal and ult_hist > 0:
                    analisis_ia += "El MACD confirma giro alcista. **Escenario de COMPRA IDEAL.**"
                elif ult_macd < ult_signal and ult_hist > penult_hist:
                    analisis_ia += "El MACD sigue bajista pero pierde fuerza. Atento al inminente cruce al alza."
                else:
                    analisis_ia += "El MACD sigue cayendo con fuerza. Compra si eres un fundamental estricto, o espera si prefieres confirmación técnica."
            
            elif 0 < dist_suelo <= 5.0:
                analisis_ia += f"🟡 **Alerta Temprana / Rebote.** El precio ({precio_str}) está a un **{dist_suelo:.1f}%** de tu zona de compra ({suelo_str}). "
                if ult_macd > ult_signal:
                    analisis_ia += "El MACD es alcista. Si la acción acaba de rebotar desde la línea verde, es buena entrada aunque llegues algo tarde."
                else:
                    analisis_ia += "El MACD es bajista. Lo ideal es esperar a que siga corrigiendo hasta tocar la línea verde discontinua para maximizar el margen de seguridad."
            
            else:
                analisis_ia += f"🔴 **Fuera de Zona.** El precio ({precio_str}) cotiza un **{dist_suelo:.1f}%** por encima del suelo exigido ({suelo_str}). "
                analisis_ia += "No hay margen de seguridad suficiente. Observa desde la barrera y pon alertas por si la acción sufre una corrección severa."

            st.info(analisis_ia)
            # ----------------------------------------

            colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for index, row in df_tech.iterrows()]
            colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']]

            fig_tech = make_subplots(rows=3, cols=1, shared_xaxes=True, 
            vertical_spacing=0.03, 
            row_heights=[0.5, 0.2, 0.3])

            fig_tech.add_trace(go.Ohlc(
                x=df_tech.index, open=df_tech['Open'], high=df_tech['High'],
                low=df_tech['Low'], close=df_tech['Close'], name='Precio',
                increasing_line_color='#21c354', decreasing_line_color='#ff4b4b',
                showlegend=False
            ), row=1, col=1)

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)

            fig_tech.add_trace(go.Bar(
                x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False
            ), row=2, col=1)

            fig_tech.add_trace(go.Bar(
                x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False
            ), row=3, col=1)
            fig_tech.add_trace(go.Scatter(
                x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False
            ), row=3, col=1)
            fig_tech.add_trace(go.Scatter(
                x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False
            ), row=3, col=1)

            fig_tech.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=800,
                showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis_rangeslider_visible=False 
            )
            
            fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            
            st.plotly_chart(fig_tech, use_container_width=True)
        else:
            st.info("No hay suficientes datos recientes en Yahoo Finance para dibujar el panel de 2 meses.")
    else:
        st.info("No hay suficientes datos históricos en Yahoo Finance para calcular el panel técnico (MACD/Volumen).")

    st.divider()

    # ==========================================
    # FILA DE BENEFICIOS CON DELTAS DINÁMICOS
    # ==========================================
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
    else: 
        c6.metric(f"Acciones ({años_analisis}Y)", "N/D")

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
            fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_divs, use_container_width=True)


# ==========================================
# 2. FUNCIÓN LIGERA PARA SCREENER MASIVO
# ==========================================
def analizar_empresa_rapido(ticker_symbol, años_analisis):
    try:
        ticker = yf.Ticker(ticker_symbol.strip().upper())
        info = ticker.info
        
        if 'dividendRate' not in info and 'trailingAnnualDividendRate' not in info:
            return None
            
        dividendos = ticker.dividends
        historial = ticker.history(period="15y")
        
        if dividendos.empty or len(historial) < 252: return None

        historial.index = historial.index.tz_localize(None).normalize()
        dividendos.index = dividendos.index.tz_localize(None).normalize()

        fecha_corte = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
        historial_analisis = historial[historial.index >= fecha_corte].copy()
        if historial_analisis.empty: return None

        precio_actual = historial_analisis['Close'].dropna().iloc[-1]
        divs_por_año = dividendos.groupby(dividendos.index.year).sum()
        forward_dividend = info.get('dividendRate', info.get('trailingAnnualDividendRate', 0))
        if forward_dividend == 0: return None

        historial_analisis['Year'] = historial_analisis.index.year
        historial_analisis['Div_Anual'] = historial_analisis['Year'].map(divs_por_año)
        historial_analisis.loc[historial_analisis['Year'] == datetime.now().year, 'Div_Anual'] = forward_dividend
        historial_analisis['Div_Anual'] = historial_analisis['Div_Anual'].bfill().ffill()

        historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
        yields_validos = historial_analisis['Yield_Diario'].dropna()
        yields_validos = yields_validos[yields_validos > 0]

        yield_infravalorado = yields_validos.quantile(0.95)
        precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
        dist_suelo = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 999
        yield_actual = (forward_dividend / precio_actual) * 100
        
        dgr_5y = 0
        if len(divs_por_año) >= 6:
            div_actual = divs_por_año.iloc[-1]
            div_5y = divs_por_año.iloc[-6]
            if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100

        payout = info.get('payoutRatio', 1) * 100
        fcf = info.get('freeCashflow', 0)
        debt_fcf = info.get('totalDebt', 0) / fcf if fcf > 0 else 999
        per = info.get('trailingPE', 99)
        
        score = 0
        if 0 < payout <= 60: score += 2
        if 0 < debt_fcf <= 5: score += 2
        if 0 < per <= 20: score += 2
        if yield_actual >= yields_validos.mean(): score += 2
        if dgr_5y > 5: score += 2

        estado = "🎯 COMPRA" if dist_suelo <= 1.0 else ("🟡 Cerca" if dist_suelo <= 10.0 else "🔴 Lejos")

        return {
            "Ticker": ticker_symbol.strip().upper(),
            "Precio": round(precio_actual, 2),
            "Suelo Weiss": round(precio_compra, 2),
            "Distancia %": round(dist_suelo, 2),
            "Estado": estado,
            "Score": score,
            "Yield %": round(yield_actual, 2),
            "DGR 5A %": round(dgr_5y, 2),
            "Deuda/FCF": round(debt_fcf, 2)
        }
    except:
        return None

# ==========================================
# ESTRUCTURA PRINCIPAL DE PESTAÑAS (UI)
# ==========================================
st.title("Sistema Fundamental - Método Geraldine Weiss")

tab_individual, tab_masiva = st.tabs(["🔍 Análisis de Francotirador", "📑 Screener Masivo (Lotes)"])

# ----------------- PESTAÑA 1: INDIVIDUAL -----------------
with tab_individual:
    col_input1, col_input2, col_input3 = st.columns(3)
    with col_input1: ticker_input = st.text_input("Ticker individual:", "NVO").upper()
    with col_input2: años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)
    with col_input3: impuesto = st.number_input("Retención (%)", value=19.0)

    if st.button("Analizar Empresa"):
        with st.spinner(f"Analizando {ticker_input} en profundidad..."):
            try: 
                screener_weiss_definitivo(ticker_input, años_analisis, impuesto)
            except Exception as e: 
                st.error(f"Se ha producido un error: {e}")

# ----------------- PESTAÑA 2: MASIVA -----------------
with tab_masiva:
    st.markdown("### 📡 Radar de Oportunidades Múltiples")
    st.markdown("Pega aquí tu lista de seguimiento (*Watchlist*). El sistema buscará cuáles han caído a tu **Suelo Fundamental**.")
    
    tickers_masivos = st.text_area("Tickers (separados por comas):", "NVO, LOW, ACN, MSFT, JNJ, PG, PEP, HD")
    años_masivos = st.selectbox("Periodo para el Suelo Masivo:", [5, 10, 12, 15, 20], index=2, key="años_masivos")

    if st.button("🚀 Escanear Lista Completa"):
        lista_tickers = [t for t in tickers_masivos.split(",") if t.strip()]
        
        if len(lista_tickers) > 0:
            barra_progreso = st.progress(0)
            texto_estado = st.empty()
            resultados = []
            
            for idx, ticker in enumerate(lista_tickers):
                texto_estado.text(f"Descargando y analizando {ticker} ({idx+1}/{len(lista_tickers)})...")
                datos = analizar_empresa_rapido(ticker, años_masivos)
                if datos: resultados.append(datos)
                barra_progreso.progress((idx + 1) / len(lista_tickers))
            
            texto_estado.text("¡Escaneo finalizado!")
            
            if resultados:
                df_res = pd.DataFrame(resultados)
                df_res = df_res.sort_values(by="Distancia %")
                
                # CORRECCIÓN PARA PANDAS ACTUALIZADO: Usamos map en lugar de applymap
                def color_estado(val):
                    if val == "🎯 COMPRA": return 'background-color: #004d00'
                    elif val == "🟡 Cerca": return 'background-color: #4d4d00'
                    return ''
                
                st.dataframe(df_res.style.map(color_estado, subset=['Estado']), use_container_width=True)
                
                csv = df_res.to_csv(index=False, sep=';', decimal=',').encode('utf-8')
                st.download_button(
                    label="💾 Descargar CSV para Google Sheets",
                    data=csv,
                    file_name=f"Screener_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No se encontraron datos de dividendos para ninguna de las empresas introducidas.")
