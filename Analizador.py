import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import warnings
import plotly.graph_objects as go

# Ignorar advertencias menores de Pandas
warnings.filterwarnings('ignore')

# Configuración principal de la página
st.set_page_config(page_title="Screener Geraldine Weiss (12 Años)", page_icon="📊", layout="wide")

def screener_weiss_definitivo(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None: return default
        try: return float(val)
        except (ValueError, TypeError): return default

    # --- DETECCIÓN DE SECTOR (MÉTODO WEISS REAL) ---
    sector = info.get('sector', '')
    industry = info.get('industry', '')
    es_regulada_o_reit = 'utility' in sector.lower() or 'utilities' in sector.lower() or 'reit' in industry.lower() or 'real estate' in sector.lower()
    
    payout_limite_bpa = 80.0 if es_regulada_o_reit else 50.0
    payout_limite_fcf = 85.0 if es_regulada_o_reit else 60.0

    currency = info.get('currency', 'USD')
    divisor_uk = 1.0 
    if currency == 'EUR': sym = '€'
    elif currency == 'GBP': sym = '£'
    elif currency == 'GBp':
        sym = '£'
        divisor_uk = 100.0 
    else: sym = '$' 

    # --- HISTORIAL COMPLETO ---
    historial_completo = ticker.history(period="max")
    dividendos = ticker.dividends
    
    if dividendos.empty or len(historial_completo) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    dividendos.index = dividendos.index.tz_localize(None).normalize()

    # Recorte para las bandas a 12 años vista
    fecha_corte_12y = pd.Timestamp.now().normalize() - pd.DateOffset(years=12)
    historial_12y = historial_completo[historial_completo.index >= fecha_corte_12y].copy()

    if historial_12y.empty:
        st.error("❌ Error: No se encontraron datos de cotización en los últimos 12 años.")
        return

    # --- CÁLCULO ESTRICTO DE DIVIDENDOS ANUALES ---
    divs_por_año = dividendos.groupby(dividendos.index.year).sum()

    # --- DETERMINAR FORWARD DIVIDEND ---
    precio_actual = historial_12y['Close'].dropna().iloc[-1]
    año_actual = datetime.now().year
    
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    
    pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4
    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    forward_dividend = get_safe('dividendRate')
    if forward_dividend == 0: forward_dividend = get_safe('trailingAnnualDividendRate')
    if forward_dividend == 0: 
        if not dividendos.empty:
            ultimo_año_completo = divs_por_año.iloc[-2] if len(divs_por_año) > 1 else 0
            forward_dividend = max(dividendos.iloc[-1] * pagos_por_año, ultimo_año_completo)
        else:
            forward_dividend = 0
            
    if currency == 'GBp' and forward_dividend > 0:
        if forward_dividend < (precio_actual / 10): forward_dividend = forward_dividend * 100

    # --- EL MODELO ESCALÓN ANUAL (A 12 AÑOS PARA LAS BANDAS) ---
    historial_12y['Year'] = historial_12y.index.year
    historial_12y['Div_Anual'] = historial_12y['Year'].map(divs_por_año)
    historial_12y.loc[historial_12y['Year'] == año_actual, 'Div_Anual'] = forward_dividend
    historial_12y['Div_Anual'] = historial_12y['Div_Anual'].bfill().ffill()

    historial_12y['Yield_Diario'] = (historial_12y['Div_Anual'] / historial_12y['Close']) * 100

    yields_validos = historial_12y['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]
    
    if yields_validos.empty:
        st.error("❌ Error: No se pudo calcular el histórico de Yield.")
        return

    yield_infravalorado = yields_validos.quantile(0.95) 
    yield_sobrevalorado = yields_validos.quantile(0.05) 
    yield_medio = yields_validos.mean()

    yield_actual = (forward_dividend / precio_actual) * 100

    # --- FUNDAMENTALES ---
    payout_ratio = get_safe('payoutRatio') * 100
    per = get_safe('trailingPE', get_safe('forwardPE'))
    deuda_equity = get_safe('debtToEquity') 
    market_cap = get_safe('marketCap')
    current_ratio = get_safe('currentRatio') 
    bpa_trailing = get_safe('trailingEps')
    bpa_forward = get_safe('forwardEps')
    per_forward = get_safe('forwardPE')
    
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
    
    if fcf != 0 and shares > 0:
        fcf_per_share = fcf / shares
        if currency == 'GBp': fcf_per_share *= 100 
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100

    # --- BARRAS DE DIVIDENDOS Y DGR ---
    dividendos_barras = dividendos.groupby(dividendos.index.year).sum()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    
    divs_recientes = dividendos_barras.tail(13)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

    dgr_5y = None
    dgr_12y = None
    if len(dividendos_barras) >= 6:
        div_actual = dividendos_barras.iloc[-1]
        div_5y = dividendos_barras.iloc[-6]
        if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100
            
    if len(dividendos_barras) >= 13:
        div_12y = dividendos_barras.iloc[-13]
        if div_12y > 0: dgr_12y = ((div_actual / div_12y) ** (1/12) - 1) * 100

    racha_sin_recortes = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99:
                racha_sin_recortes += 1
            else: break

    # --- VARIACIÓN DE ACCIONES (Descargamos 15 años para garantizar el cálculo YoY de 12 años) ---
    fecha_corte_15y = pd.Timestamp.now().normalize() - pd.DateOffset(years=15)
    variacion_acciones = None
    shares_yearly = pd.Series(dtype=float)
    try:
        shares_hist = ticker.get_shares_full(start=fecha_corte_15y.strftime('%Y-%m-%d'), end=None)
        if shares_hist is not None and len(shares_hist) > 1:
            shares_yearly = shares_hist.groupby(shares_hist.index.year).last()
            if len(shares_yearly) >= 13:
                acc_ini = shares_yearly.iloc[-13]
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

    # --- CÁLCULOS MATEMÁTICOS DE DESCUENTO ---
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
    txt_extra_justo = "Ancla de valoración"
    txt_extra_sobre = f"Techo: +{pct_sobre_vs_media:.1f}% vs Media"

    # ==========================================
    # INTERFAZ VISUAL STREAMLIT
    # ==========================================
    tipo_empresa_txt = "🏢 Sector Inmobiliario/Regulado (Filtros Flexibles)" if es_regulada_o_reit else "🏭 Sector Industrial/General (Filtros Estrictos)"
    
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")
    st.subheader("🎯 Precios Objetivo y Valoración Actual")
    
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
    with col1: metric_color("Cotización Actual", f"{precio_actual / divisor_uk:.2f}{sym}", f"Yield: {yield_actual:.2f}%", txt_extra_actual, color_actual)
    with col2: metric_color("Franja Infravalorada", f"{precio_compra / divisor_uk:.2f}{sym}", f"Yield {yield_infravalorado:.2f}%", txt_extra_infra, "#21c354") 
    with col3: metric_color("Precio Justo (Media)", f"{precio_justo / divisor_uk:.2f}{sym}", f"Yield {yield_medio:.2f}%", txt_extra_justo, "#faca2b") 
    with col4: metric_color("Franja Sobrevalorada", f"{precio_venta / divisor_uk:.2f}{sym}", f"Yield {yield_sobrevalorado:.2f}%", txt_extra_sobre, "#ff4b4b") 

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

    # --- ALGORITMO AUTOMÁTICO: BLUE CHIP SCORE (0/10) ---
    score = 0
    if yield_actual >= yield_medio: score += 1
    if 0 < payout_ratio <= payout_limite_bpa: score += 1
    if 0 < payout_fcf <= payout_limite_fcf: score += 1
    if 0 < per <= 20: score += 1
    if 0 < p_fcf <= 20: score += 1
    if variacion_acciones is not None and variacion_acciones < 0: score += 1
    if años_pagando >= 25 and racha_sin_recortes >= 12: score += 1
    if incrementos_dividendo >= 5: score += 1
    if total_años_bpa_datos > 0 and (años_crecimiento_bpa / total_años_bpa_datos) >= 0.65: score += 1
    if market_cap > 10_000_000_000: score += 1

    st.markdown("<br>", unsafe_allow_html=True)
    if score >= 8:
        st.success(f"🏆 **BLUE CHIP SCORE WEISS: {score}/10** — Empresa Sobresaliente. Altísima seguridad y apta para compra si el precio acompaña.")
    elif score >= 5:
        st.warning(f"⚖️ **BLUE CHIP SCORE WEISS: {score}/10** — Empresa Aceptable. Tiene solidez pero presenta algún punto débil que debes vigilar.")
    else:
        st.error(f"🚨 **BLUE CHIP SCORE WEISS: {score}/10** — Calidad Insuficiente. No cumple los exigentes filtros de seguridad de Geraldine Weiss.")

    # --- GRÁFICO INTERACTIVO (12 AÑOS) ---
    st.markdown("### 📈 Evolución Histórica de Valoración (Ciclo Weiss 12 Años)")
    df_grafico = historial_12y[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_12y['Div_Anual']
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
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title=f"Precio ({sym})", xaxis_title="", hovermode="x unified",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 2. BENEFICIOS Y PROYECCIONES
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
        c5.metric("Acciones (12Y)", f"{signo}{variacion_acciones:.2f}%", delta=estado_acc, delta_color=color_acc)
    else:
        c5.metric("Acciones (12Y)", "N/D")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📈 Crecimiento Anual Compuesto del Dividendo (CAGR / DGR)")
    cd1, cd2 = st.columns(2)
    cd1.metric("DGR 5 Años (Medio Plazo)", f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D")
    cd2.metric("DGR 12 Años (Ciclo Completo)", f"{dgr_12y:.2f}%" if dgr_12y is not None else "N/D")

    # --- NUEVO PANEL: SIMULADOR DE YIELD ON COST (YoC) PURO BLUE CHIP ---
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🔮 Proyección de Rentabilidad sobre Coste (Yield on Cost)")
    
    if dgr_12y is not None and dgr_12y > 0:
        dgr_proyeccion = dgr_12y
        txt_ritmo = "Ritmo Histórico (12A)"
    elif dgr_5y is not None and dgr_5y > 0:
        dgr_proyeccion = dgr_5y
        txt_ritmo = "Ritmo Medio (5A)"
    else:
        dgr_proyeccion = 0.0
        txt_ritmo = "Crecimiento Estancado"
    
    dgr_proyeccion = min(dgr_proyeccion, 15.0)
    
    yoc_5 = yield_actual * ((1 + dgr_proyeccion/100) ** 5)
    yoc_10 = yield_actual * ((1 + dgr_proyeccion/100) ** 10)
    yoc_15 = yield_actual * ((1 + dgr_proyeccion/100) ** 15)
    
    cp1, cp2, cp3 = st.columns(3)
    cp1.metric("YoC Esperado a 5 Años", f"{yoc_5:.2f}%", f"{txt_ritmo}: +{dgr_proyeccion:.1f}% anual")
    cp2.metric("YoC Esperado a 10 Años", f"{yoc_10:.2f}%", f"{txt_ritmo}: +{dgr_proyeccion:.1f}% anual")
    cp3.metric("YoC Esperado a 15 Años", f"{yoc_15:.2f}%", f"{txt_ritmo}: +{dgr_proyeccion:.1f}% anual")

    # --- HISTORIAL ANUAL DE RECOMPRAS ---
    if not shares_yearly.empty and len(shares_yearly) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🔄 Historial Anual de Recompras / Dilución (12 Años)")
        
        # Calculamos sobre todo el dataset, borramos nulos, y extraemos exactamente las últimas 12
        yoy_shares_total = shares_yearly.pct_change().dropna() * 100
        yoy_shares_12y = yoy_shares_total.tail(12)
        
        text_labels = [f"+{val:.2f}%" if val > 0 else f"{val:.2f}%" for val in yoy_shares_12y.values]
        colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares_12y.values]
        fig_shares = go.Figure()
        fig_shares.add_trace(go.Bar(x=yoy_shares_12y.index.astype(str), y=yoy_shares_12y.values, marker_color=colores_barras, text=text_labels, textposition='auto'))
        fig_shares.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=230,
            yaxis_title="Variación Anual (%)", xaxis_title="", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_shares, use_container_width=True)

    # --- GRÁFICO COMBINADO DE DIVIDENDOS (12 AÑOS EXACTOS) ---
    if not dividendos_barras.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 💰 Historial de Dividendos Anuales y Crecimiento YoY (12 Años)")
        
        # Calculamos crecimiento sobre TODOS los datos antes de recortar, así la barra 1 no se pierde
        crecimiento_yoy_total = dividendos_barras.pct_change() * 100
        
        # Recorte quirúrgico: Exactamente las últimas 12 barras
        divs_12y = dividendos_barras.tail(12)
        crecimiento_yoy_12y = crecimiento_yoy_total.tail(12)
        
        if len(divs_12y) > 0:
            x_labels_enriquecidos = []
            for year, val in zip(divs_12y.index, crecimiento_yoy_12y.values):
                if pd.isna(val): x_labels_enriquecidos.append(str(year))
                else:
                    color_pct = '#21c354' if val > 0 else '#ff4b4b'
                    signo_pct = '+' if val > 0 else ''
                    x_labels_enriquecidos.append(f"{year}<br><span style='color:{color_pct}; font-size:12px'>{signo_pct}{val:.1f}%</span>")
            
            fig_divs = go.Figure()
            fig_divs.add_trace(go.Bar(
                x=x_labels_enriquecidos, y=divs_12y.values, name=f"Dividendo ({sym})", marker_color='#00d4ff', yaxis='y1',
                text=[f"{val:.2f}{sym}" for val in divs_12y.values], textposition='auto'
            ))
            fig_divs.add_trace(go.Scatter(
                x=x_labels_enriquecidos, y=crecimiento_yoy_12y.values, name="Crecimiento YoY", 
                mode='lines+markers', line=dict(color='#21c354', width=3), marker=dict(size=8), yaxis='y2'
            ))
            fig_divs.update_layout(
                template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")),
                yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_divs, use_container_width=True)

    st.divider()

    # 3. DECÁLOGO DE CALIDAD
    st.subheader("📋 Decálogo de Calidad del Blue Chip (Ciclo Weiss 12 Años)")
    
    if yield_actual >= yield_infravalorado: st.success(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Excelente, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: st.warning(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Aceptable, superior a media de {yield_medio:.2f}%)")
    else: st.error(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Pobre, inferior a media de {yield_medio:.2f}%)")

    if 0 < payout_ratio <= payout_limite_bpa: st.success(f"Payout (BPA Histórico): {payout_ratio:.2f}% (Seguro para su sector, exige < {payout_limite_bpa:.0f}%)")
    else: st.error(f"Payout (BPA Histórico): {payout_ratio:.2f}% (Elevado, el límite de su sector exige < {payout_limite_bpa:.0f}%)")
    
    if payout_forward != -1:
        if 0 < payout_forward <= payout_limite_bpa: st.success(f"Forward Payout (Proyección Año Próximo): {payout_forward:.2f}% (Sano, beneficio futuro cubre el dividendo)")
        else: st.warning(f"Forward Payout (Proyección Año Próximo): {payout_forward:.2f}% (Atención: la cobertura empeorará el año que viene)")
    else: st.error("Forward Payout: No disponible por BPA futuro negativo")

    if payout_fcf != -1:
        if payout_fcf <= payout_limite_fcf: st.success(f"Payout (FCF / Caja Real): {payout_fcf:.2f}% (Caja fuerte para su sector, exige < {payout_limite_fcf:.0f}%)")
        else: st.error(f"Payout (FCF / Caja Real): {payout_fcf:.2f}% (Peligro, supera el límite sectorial de {payout_limite_fcf:.0f}%)")
    else: st.error(f"Payout (FCF): NEGATIVO (Quema de caja)")

    if 0 < per <= 20: st.success(f"PER (Beneficio Contable): {per:.2f} (Valoración atractiva)")
    else: st.error(f"PER (Beneficio Contable): {per:.2f} (Múltiplo caro)")

    if p_fcf != -1:
        if 0 < p_fcf <= 20: st.success(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Barato. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Caro. FCF Yield: {fcf_yield:.2f}%)")
    else: st.error("P/FCF (Efectivo Real): NEGATIVO")

    if variacion_acciones is not None:
        if variacion_acciones < 0: st.success(f"Acciones en circulación: {variacion_acciones:.2f}% en 12 años (Excelente, la empresa destruye acciones)")
        elif variacion_acciones <= 5: st.warning(f"Acciones en circulación: +{variacion_acciones:.2f}% en 12 años (Estable / Ligera dilución)")
        else: st.error(f"Acciones en circulación: +{variacion_acciones:.2f}% en 12 años (Peligro, la empresa diluye al accionista)")

    if años_pagando >= 25 and racha_sin_recortes >= 12: st.success(f"Historial: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Aristócrata consagrada)")
    else: st.warning(f"Historial: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años")

    if incrementos_dividendo >= 5:
        st.success(f"Frecuencia de Aumentos (Filtro Weiss): El dividendo ha subido {incrementos_dividendo} veces en los últimos 12 años (Cumple exigencia de > 5 aumentos)")
    else:
        st.error(f"Frecuencia de Aumentos (Filtro Weiss): Solo {incrementos_dividendo} aumentos detectados en 12 años (Falta de crecimiento activo)")

    if total_años_bpa_datos > 0:
        ratio_bpa = años_crecimiento_bpa / total_años_bpa_datos
        if ratio_bpa >= 0.65:
            st.success(f"Consistencia BPA (Proxy Yahoo): Crecimiento neto positivo en {años_crecimiento_bpa} de {total_años_bpa_datos} años analizados (Consistente a corto plazo)")
        else:
            st.error(f"Consistencia BPA (Proxy Yahoo): Solo {años_crecimiento_bpa} años de crecimiento de {total_años_bpa_datos} evaluados (Excesiva ciclicidad reciente)")

    if respaldo_institucional > 0:
        if respaldo_institucional >= 50.0: st.success(f"Respaldo Institucional: {respaldo_institucional:.1f}% en manos de Fondos/Bancos (Cumple criterio de respaldo institucional)")
        else: st.warning(f"Respaldo Institucional: {respaldo_institucional:.1f}% (Interés institucional bajo o fragmentado)")
    else: st.warning("Respaldo Institucional: Datos no disponibles en Yahoo")

    if dgr_5y is not None:
        if dgr_5y >= 10: st.success(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Excelente)")
        elif dgr_5y > 0: st.warning(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Positivo)")
        else: st.error(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Estancado)")

    if dgr_12y is not None:
        if dgr_12y >= 10: st.success(f"Crecimiento DGR 12A (Ciclo Completo): {dgr_12y:.2f}% (Excelente ritmo continuo)")
        elif dgr_12y > 0: st.warning(f"Crecimiento DGR 12A (Ciclo Completo): {dgr_12y:.2f}% (Sostenido)")
        else: st.error(f"Crecimiento DGR 12A (Ciclo Completo): {dgr_12y:.2f}% (Estancado)")

    if deuda_equity == 0.0: st.warning("Deuda/Capital: 0.00% (Posible Patrimonio Negativo por recompras masivas)")
    elif 0 < deuda_equity <= 50: st.success(f"Deuda/Capital: {deuda_equity:.2f}% (Balance sano)")
    else: st.error(f"Deuda/Capital: {deuda_equity:.2f}% (Apalancamiento elevado)")

    if market_cap > 10_000_000_000: st.success(f"Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Gran capitalización institucional)")
    else: st.error(f"Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Capitalización pequeña)")

    if current_ratio > 0:
        if current_ratio >= 1.5: st.success(f"Liquidez (Current Ratio): {current_ratio:.2f} (Caja solvente)")
        elif current_ratio >= 1.0: st.warning(f"Liquidez (Current Ratio): {current_ratio:.2f} (Justa)")
        else: st.error(f"Liquidez (Current Ratio): {current_ratio:.2f} (Falta de liquidez a corto plazo)")

# --- FRONTEND DE LA APLICACIÓN ---
st.title("Screener Fundamental - Método Geraldine Weiss (12 Años)")
st.markdown("Introduce el ticker de una empresa para extraer sus datos financieros, rentabilidad real (FCF) y calcular sus bandas de valoración históricas.")

col_input, col_btn = st.columns([4, 1])
with col_input:
    ticker_input = st.text_input("Ticker de la empresa (Ej: ACN, WKL, MCD):", placeholder="Escribe aquí...").upper()
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    analizar = st.button("Analizar Empresa", use_container_width=True)

if analizar and ticker_input:
    with st.spinner(f"Analizando {ticker_input}..."):
        try: screener_weiss_definitivo(ticker_input)
        except Exception as e: st.error(f"Se ha producido un error al descargar los datos: {e}")
