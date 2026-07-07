import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import warnings
import plotly.graph_objects as go

# Ignorar advertencias menores de Pandas
warnings.filterwarnings('ignore')

# Configuración principal de la página
st.set_page_config(page_title="Screener Geraldine Weiss", page_icon="📊", layout="wide")

def screener_weiss_definitivo(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None: return default
        try: return float(val)
        except (ValueError, TypeError): return default

    currency = info.get('currency', 'USD')
    divisor_uk = 1.0 
    
    if currency == 'EUR': sym = '€'
    elif currency == 'GBP': sym = '£'
    elif currency == 'GBp':
        sym = '£'
        divisor_uk = 100.0 
    else: sym = '$' 

    # --- HISTORIAL Y BANDAS YIELD ---
    historial_completo = ticker.history(period="10y")
    dividendos = ticker.dividends
    
    if dividendos.empty or len(historial_completo) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    dividendos.index = dividendos.index.tz_localize(None).normalize()
    dividendos = dividendos.sort_index()

    historial_completo['Div'] = dividendos
    historial_completo.fillna({'Div': 0}, inplace=True)
    
    historial_completo['Div_TTM'] = historial_completo['Div'].rolling(window=252).sum()
    historial_completo['Yield_Diario'] = (historial_completo['Div_TTM'] / historial_completo['Close']) * 100

    fecha_corte_5y = historial_completo.index[-1] - pd.DateOffset(years=5)
    historial_5y = historial_completo[historial_completo.index >= fecha_corte_5y]
    
    yields_validos = historial_5y['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]
    
    if yields_validos.empty:
        st.error("❌ Error: No se pudo calcular el histórico de Yield.")
        return

    yield_infravalorado = yields_validos.quantile(0.95) 
    yield_sobrevalorado = yields_validos.quantile(0.05) 
    yield_medio = yields_validos.mean()

    # --- DATOS ACTUALES ---
    precio_actual = historial_5y['Close'].dropna().iloc[-1]
    ultimo_pago = dividendos.iloc[-1]
    
    año_actual = datetime.now().year
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_cerrado = conteo_por_año[conteo_por_año.index < año_actual]
    
    if not conteo_cerrado.empty:
        pagos_por_año = int(conteo_cerrado.max())
    else:
        pagos_por_año = int(conteo_por_año.max()) if not conteo_por_año.empty else 4 
        
    if pagos_por_año not in [1, 2, 4, 12]:
        if pagos_por_año == 3: pagos_por_año = 4
        elif pagos_por_año > 10: pagos_por_año = 12
        else: pagos_por_año = 4

    forward_dividend = get_safe('dividendRate')
    if forward_dividend == 0: 
        forward_dividend = get_safe('trailingAnnualDividendRate')
    if forward_dividend == 0: 
        forward_dividend = ultimo_pago * pagos_por_año 
        
    if currency == 'GBp' and forward_dividend > 0:
        if forward_dividend < (precio_actual / 10): 
            forward_dividend = forward_dividend * 100
            
    yield_actual = (forward_dividend / precio_actual) * 100
    
    payout_ratio = get_safe('payoutRatio') * 100
    per = get_safe('trailingPE', get_safe('forwardPE'))
    deuda_equity = get_safe('debtToEquity') 
    market_cap = get_safe('marketCap')
    current_ratio = get_safe('currentRatio') 

    bpa_trailing = get_safe('trailingEps')
    bpa_forward = get_safe('forwardEps')
    per_forward = get_safe('forwardPE')
    
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
    except Exception:
        pass
    
    fcf = get_safe('freeCashflow')
    shares = get_safe('sharesOutstanding')
    payout_fcf = None
    p_fcf = None
    fcf_yield = None
    
    if fcf != 0 and shares > 0:
        fcf_per_share = fcf / shares
        if currency == 'GBp': fcf_per_share *= 100 
        
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100
        else:
            payout_fcf = -1 
            p_fcf = -1 

    dgr_5y = None
    if len(dividendos) >= (pagos_por_año * 5): 
        bloque_actual = dividendos.tail(pagos_por_año).sum()
        fecha_hace_5_años_div = dividendos.index[-1] - pd.DateOffset(years=5)
        dividendos_antiguos = dividendos[dividendos.index <= fecha_hace_5_años_div]
        
        if len(dividendos_antiguos) >= pagos_por_año:
            bloque_hace_5_años = dividendos_antiguos.tail(pagos_por_año).sum()
            if bloque_hace_5_años > 0:
                dgr_5y = (((bloque_actual / bloque_hace_5_años) ** (1 / 5)) - 1) * 100

    dividendos_anuales = dividendos.groupby(dividendos.index.year).sum()
    años_pagando = año_actual - dividendos_anuales.index[0]
    
    racha_sin_recortes = 0
    historial_ttm = historial_completo['Div_TTM'].dropna()
    
    if len(historial_ttm) > 252:
        ttm_evaluado = historial_ttm.iloc[-1]
        for i in range(1, 10):
            dias_atras = i * 252
            if dias_atras >= len(historial_ttm): break
            ttm_previo = historial_ttm.iloc[-(dias_atras + 1)]
            if ttm_evaluado >= ttm_previo * 0.99:
                racha_sin_recortes += 1
                ttm_evaluado = ttm_previo 
            else:
                break 

    # --- CÁLCULO DE VARIACIÓN DE ACCIONES EN CIRCULACIÓN POR AÑO ---
    variacion_acciones = None
    shares_yearly = pd.Series(dtype=float)
    
    try:
        shares_hist = ticker.get_shares_full(start=fecha_corte_5y.strftime('%Y-%m-%d'), end=None)
        if shares_hist is not None and len(shares_hist) > 1:
            shares_yearly = shares_hist.groupby(shares_hist.index.year).last()
            acc_ini = shares_yearly.iloc[0]
            acc_fin = shares_yearly.iloc[-1]
            if acc_ini > 0:
                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
    except Exception:
        pass
        
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
                            if acc_ini > 0:
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                            break
        except Exception:
            pass

    if yield_infravalorado > 0: precio_compra = (forward_dividend / yield_infravalorado) * 100
    else: precio_compra = 0
    if yield_medio > 0: precio_justo = (forward_dividend / yield_medio) * 100
    else: precio_justo = 0
    if yield_sobrevalorado > 0: precio_venta = (forward_dividend / yield_sobrevalorado) * 100
    else: precio_venta = 0

    # ==========================================
    # INTERFAZ VISUAL STREAMLIT
    # ==========================================
    st.header(f"Análisis de {ticker_symbol} ({currency})")
    
    # 1. VALORACIÓN ACTUAL (DISEÑO COLOREADO A MEDIDA)
    st.subheader("🎯 Precios Objetivo y Valoración Actual")
    
    if precio_actual <= precio_compra: color_actual = "#21c354" 
    elif precio_actual >= precio_venta: color_actual = "#ff4b4b" 
    else: color_actual = "#faca2b" 

    def metric_color(label, value, yield_txt, color):
        st.markdown(f"""
            <div style="display: flex; flex-direction: column; margin-bottom: 1rem;">
                <span style="font-size: 1rem; color: #c4c4cc;">{label}</span>
                <span style="font-size: 2.2rem; font-weight: 700; color: {color}; margin-top: 0.2rem; margin-bottom: 0.2rem;">{value}</span>
                <span style="font-size: 0.95rem; font-weight: 600; color: {color};">↑ {yield_txt}</span>
            </div>
        """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1: metric_color("Cotización Actual", f"{precio_actual / divisor_uk:.2f}{sym}", f"Yield: {yield_actual:.2f}%", color_actual)
    with col2: metric_color("Franja Infravalorada", f"{precio_compra / divisor_uk:.2f}{sym}", f"Yield {yield_infravalorado:.2f}%", "#21c354") 
    with col3: metric_color("Precio Justo (Media)", f"{precio_justo / divisor_uk:.2f}{sym}", f"Yield {yield_medio:.2f}%", "#faca2b") 
    with col4: metric_color("Franja Sobrevalorada", f"{precio_venta / divisor_uk:.2f}{sym}", f"Yield {yield_sobrevalorado:.2f}%", "#ff4b4b") 

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

    # --- GRÁFICO INTERACTIVO ---
    st.markdown("### 📈 Evolución Histórica de Valoración (5 Años)")
    
    df_grafico = historial_5y[['Close']].copy()
    
    if not df_grafico.empty:
        divs_rodantes = dividendos.rolling(window=pagos_por_año).sum()
        df_grafico['Div_Grafico'] = divs_rodantes
        df_grafico['Div_Grafico'] = df_grafico['Div_Grafico'].ffill().bfill()
        
        if not dividendos.empty:
            df_grafico.loc[df_grafico.index >= dividendos.index[-1], 'Div_Grafico'] = forward_dividend
            
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

    # 2. BENEFICIOS Y PROYECCIONES CON COLOR EN RECOMPRAS
    st.subheader("📊 Beneficios, Proyecciones y Acciones")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("BPA Actual", f"{bpa_trailing / divisor_uk:.2f}{sym}" if bpa_trailing != 0 else "N/D")
    c2.metric("BPA Esperado", f"{bpa_forward / divisor_uk:.2f}{sym}" if bpa_forward != 0 else "N/D")
    c3.metric("PER Futuro", f"{per_forward:.2f}" if per_forward != 0 else "N/D")
    c4.metric("Crecimiento BPA (3Y)", f"{crecimiento_bpa_3y:.2f}%" if crecimiento_bpa_3y is not None else "N/D")
    
    if variacion_acciones is not None:
        signo = "+" if variacion_acciones > 0 else ""
        if variacion_acciones < -0.5:
            estado_acc, color_acc = "- Recomprando", "inverse"
        elif variacion_acciones <= 1.0:
            estado_acc, color_acc = "Estable", "off"
        else:
            estado_acc, color_acc = "+ Diluyendo", "inverse"
        c5.metric("Acciones (5Y)", f"{signo}{variacion_acciones:.2f}%", delta=estado_acc, delta_color=color_acc)
    else:
        c5.metric("Acciones (5Y)", "N/D")

    # --- HISTORIAL ANUAL DE RECOMPRAS ---
    if not shares_yearly.empty and len(shares_yearly) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🔄 Historial Anual de Recompras / Dilución")
        
        yoy_shares = shares_yearly.pct_change().dropna() * 100
        text_labels = [f"+{val:.2f}%" if val > 0 else f"{val:.2f}%" for val in yoy_shares.values]
        colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares.values]

        fig_shares = go.Figure()
        fig_shares.add_trace(go.Bar(
            x=yoy_shares.index.astype(str), 
            y=yoy_shares.values,
            marker_color=colores_barras,
            text=text_labels,
            textposition='auto'
        ))
        
        fig_shares.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=230,
            yaxis_title="Variación Anual (%)", xaxis_title="",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_shares, use_container_width=True)

    # --- NUEVO GRÁFICO COMBINADO: HISTORIAL DE DIVIDENDOS (BARRAS) + CRECIMIENTO YOY (LÍNEA) ---
    if not dividendos_anuales.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 💰 Historial de Dividendos Anuales y Crecimiento YoY")
        
        # Filtramos los dividendos para los últimos 5 años coincidiendo con el contexto global
        divs_5y = dividendos_anuales[dividendos_anuales.index >= fecha_corte_5y.year]
        if len(divs_5y) > 0:
            crecimiento_yoy = divs_5y.pct_change() * 100
            
            fig_divs = go.Figure()
            
            # 1. Añadimos las Barras para el dividendo bruto cobrado (Eje Y principal)
            fig_divs.add_trace(go.Bar(
                x=divs_5y.index.astype(str),
                y=divs_5y.values,
                name=f"Dividendo ({sym})",
                marker_color='#00d4ff',
                yaxis='y1',
                text=[f"{val:.2f}{sym}" for val in divs_5y.values],
                textposition='auto'
            ))
            
            # 2. Añadimos la Línea con puntos para el crecimiento porcentual (Eje Y secundario)
            text_crecimiento = ["" if pd.isna(val) else (f"+{val:.1f}%" if val > 0 else f"{val:.1f}%") for val in crecimiento_yoy.values]
            fig_divs.add_trace(go.Scatter(
                x=crecimiento_yoy.index.astype(str),
                y=crecimiento_yoy.values,
                name="Crecimiento YoY",
                mode='lines+markers',
                line=dict(color='#21c354', width=3),
                marker=dict(size=8),
                yaxis='y2',
                text=text_crecimiento,
                textposition='top center'
            ))
            
            # Layout con doble configuración de eje Y unificado
            fig_divs.update_layout(
                template='plotly_dark',
                margin=dict(l=0, r=0, t=30, b=0),
                height=280,
                hovermode="x unified",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(
                    title=f"Dividendo ({sym})",
                    titlefont=dict(color="#00d4ff"),
                    tickfont=dict(color="#00d4ff")
                ),
                yaxis2=dict(
                    title="Crecimiento (%)",
                    titlefont=dict(color="#21c354"),
                    tickfont=dict(color="#21c354"),
                    overlaying='y',
                    side='right',
                    showgrid=False
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_divs, use_container_width=True)

    st.divider()

    # 3. DECÁLOGO DE CALIDAD
    st.subheader("📋 Decálogo de Calidad del Blue Chip")
    
    if yield_actual >= yield_infravalorado: st.success(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Excelente, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: st.warning(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Aceptable, superior a media de {yield_medio:.2f}%)")
    else: st.error(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Pobre, inferior a media de {yield_medio:.2f}%)")

    if 0 < payout_ratio <= 50: st.success(f"Payout (BPA): {payout_ratio:.2f}% (Seguro, exige < 50%)")
    elif 50 < payout_ratio <= 65: st.warning(f"Payout (BPA): {payout_ratio:.2f}% (Alto, exige < 50%)")
    else: st.error(f"Payout (BPA): {payout_ratio:.2f}% (Peligro, exige < 50%)")
    
    if payout_fcf is not None:
        if payout_fcf == -1: st.error(f"Payout (FCF): NEGATIVO (Quema de caja)")
        elif payout_fcf <= 60: st.success(f"Payout (FCF): {payout_fcf:.2f}% (Caja fuerte)")
        elif payout_fcf <= 85: st.warning(f"Payout (FCF): {payout_fcf:.2f}% (Aceptable)")
        else: st.error(f"Payout (FCF): {payout_fcf:.2f}% (Peligro, reparte más de lo que entra)")
    else: st.warning("Payout (FCF): Sin datos disponibles")

    if 0 < per <= 20: st.success(f"PER (Beneficio Contable): {per:.2f} (Barato)")
    else: st.error(f"PER (Beneficio Contable): {per:.2f} (Caro)")

    if p_fcf is not None:
        if p_fcf == -1: st.error("P/FCF (Efectivo Real): NEGATIVO")
        elif 0 < p_fcf <= 20: st.success(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Barato. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Caro. FCF Yield: {fcf_yield:.2f}%)")
    else: st.warning("P/FCF (Efectivo Real): Sin datos")

    if variacion_acciones is not None:
        if variacion_acciones < 0:
            st.success(f"Acciones en circulación: {variacion_acciones:.2f}% en 5 años (Excelente, la empresa recompra fuertemente)")
        elif variacion_acciones <= 5:
            st.warning(f"Acciones en circulación: +{variacion_acciones:.2f}% en 5 años (Estable / Ligera dilución)")
        else:
            st.error(f"Acciones en circulación: +{variacion_acciones:.2f}% en 5 años (Peligro, la empresa diluye al accionista)")
    else:
        st.warning("Acciones en circulación: Sin datos históricos suficientes.")

    if años_pagando >= 25 and racha_sin_recortes >= 12: st.success(f"Historial: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Aristócrata)")
    elif años_pagando >= 25: st.warning(f"Historial: {años_pagando} años pagando | Racha: {racha_sin_recortes} años sin recortes")
    else: st.warning(f"Historial: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Falta para > 25 años)")

    if dgr_5y is no
