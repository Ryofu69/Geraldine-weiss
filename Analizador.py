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

    # --- HISTORIAL Y BANDAS YIELD (EXTRACCIÓN PERFECTA 10 AÑOS) ---
    historial_completo = ticker.history(period="10y")
    
    if historial_completo.empty or 'Dividends' not in historial_completo.columns:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    
    # Extraemos los dividendos de la MISMA tabla del histórico para evitar el bug de alineación
    dividendos_limpios = historial_completo['Dividends'][historial_completo['Dividends'] > 0]
    
    if dividendos_limpios.empty or len(historial_completo) < 252:
        st.error("❌ Error: No se detectan pagos de dividendos en la tabla histórica.")
        return

    # Determinar pagos por año
    año_actual = datetime.now().year
    años = dividendos_limpios.index.year
    conteo_por_año = años.value_counts()
    conteo_cerrado = conteo_por_año[conteo_por_año.index < año_actual]
    
    if not conteo_cerrado.empty:
        pagos_por_año = int(conteo_cerrado.mode().iloc[0])
    else:
        pagos_por_año = int(conteo_por_año.mode().iloc[0]) if not conteo_por_año.empty else 4 
        
    if pagos_por_año not in [1, 2, 4, 12]:
        if pagos_por_año == 3: pagos_por_año = 4
        elif pagos_por_año > 10: pagos_por_año = 12
        else: pagos_por_año = 4

    # --- CÁLCULO DEL TTM ESCALONADO PERFECTO ---
    divs_rodantes = dividendos_limpios.rolling(window=pagos_por_año).sum()
    historial_completo['Div_TTM'] = divs_rodantes
    historial_completo['Div_TTM'] = historial_completo['Div_TTM'].ffill().bfill()
    
    # Filtro de dividendos especiales
    median_div = (dividendos_limpios.groupby(dividendos_limpios.index.year).mean() * pagos_por_año).median()
    if median_div > 0:
        historial_completo['Div_TTM'] = historial_completo['Div_TTM'].apply(lambda x: min(x, median_div * 2.5))

    historial_completo['Yield_Diario'] = (historial_completo['Div_TTM'] / historial_completo['Close']) * 100

    yields_validos = historial_completo['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]
    
    if yields_validos.empty:
        st.error("❌ Error: No se pudo calcular el histórico de Yield.")
        return

    yield_infravalorado = yields_validos.quantile(0.95) 
    yield_sobrevalorado = yields_validos.quantile(0.05) 
    yield_medio = yields_validos.mean()

    # --- DATOS ACTUALES ---
    precio_actual = historial_completo['Close'].dropna().iloc[-1]
    ultimo_pago = dividendos_limpios.iloc[-1]
    
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
    
    # --- CONSISTENCIA DE BENEFICIOS AÑO A AÑO ---
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
    except Exception:
        pass
        
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

    # --- MAGIA DEL CALENDARIO Y CORRECCIÓN DE ASIMETRÍA ---
    dividendos_anuales = dividendos_limpios.groupby(dividendos_limpios.index.year).mean() * pagos_por_año
    
    # CORRECCIÓN: Si el año actual está a medias y tiene pagos asimétricos, 
    # sobrescribimos la proyección irreal con el TTM actual (los últimos 12 meses exactos).
    if año_actual in dividendos_anuales.index:
        dividendos_anuales[año_actual] = historial_completo['Div_TTM'].iloc[-1]

    años_pagando = año_actual - dividendos_anuales.index[0]
    
    divs_recientes = dividendos_anuales.tail(11)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

    # --- CÁLCULO DGR 5Y Y 10Y BASADO EN LA SERIE LIMPIA ---
    dgr_5y = None
    dgr_10y = None
    try:
        if len(dividendos_anuales) >= 6:
            div_actual = dividendos_anuales.iloc[-1]
            div_5y = dividendos_anuales.iloc[-6]
            if div_5y > 0:
                dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100
        if len(dividendos_anuales) >= 11:
            div_10y = dividendos_anuales.iloc[-11]
            if div_10y > 0:
                dgr_10y = ((div_actual / div_10y) ** (1/10) - 1) * 100
    except Exception:
        pass

    racha_sin_recortes = 0
    if len(dividendos_anuales) > 1:
        for i in range(1, len(dividendos_anuales)):
            if dividendos_anuales.iloc[-(i)] >= dividendos_anuales.iloc[-(i+1)] * 0.99:
                racha_sin_recortes += 1
            else:
                break

    # --- VARIACIÓN DE ACCIONES ---
    fecha_corte_10y = historial_completo.index[-1] - pd.DateOffset(years=10)
    variacion_acciones = None
    shares_yearly = pd.Series(dtype=float)
    
    try:
        shares_hist = ticker.get_shares_full(start=fecha_corte_10y.strftime('%Y-%m-%d'), end=None)
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
    tipo_empresa_txt = "🏢 Sector Inmobiliario/Regulado (Filtros Flexibles)" if es_regulada_o_reit else "🏭 Sector Industrial/General (Filtros Estrictos)"
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")
    
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

    # --- GRÁFICO INTERACTIVO (10 AÑOS) ---
    st.markdown("### 📈 Evolución Histórica de Valoración (10 Años)")
    df_grafico = historial_completo[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_completo['Div_TTM']
        if not dividendos_limpios.empty:
            df_grafico.loc[df_grafico.index >= dividendos_limpios.index[-1], 'Div_Grafico'] = forward_dividend
            
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
    c2.metric("BPA Esperado", f"{bpa_forward / divisor_uk:.2f}{sym}" if bpa_forward != 0 else "N/D")
    c3.metric("PER Futuro", f"{per_forward:.2f}" if per_forward != 0 else "N/D")
    c4.metric("Crecimiento BPA (3Y)", f"{crecimiento_bpa_3y:.2f}%" if crecimiento_bpa_3y is not None else "N/D")
    
    if variacion_acciones is not None:
        signo = "+" if variacion_acciones > 0 else ""
        if variacion_acciones < -0.5: estado_acc, color_acc = "- Recomprando", "inverse"
        elif variacion_acciones <= 1.0: estado_acc, color_acc = "Estable", "off"
        else: estado_acc, color_acc = "+ Diluyendo", "inverse"
        c5.metric("Acciones (10Y)", f"{signo}{variacion_acciones:.2f}%", delta=estado_acc, delta_color=color_acc)
    else:
        c5.metric("Acciones (10Y)", "N/D")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📈 Crecimiento Anual Compuesto del Dividendo (CAGR / DGR)")
    cd1, cd2 = st.columns(2)
    cd1.metric("DGR 5 Años (Medio Plazo)", f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D")
    cd2.metric("DGR 10 Años (Largo Plazo)", f"{dgr_10y:.2f}%" if dgr_10y is not None else "N/D")

    # --- HISTORIAL ANUAL DE RECOMPRAS ---
    if not shares_yearly.empty and len(shares_yearly) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🔄 Historial Anual de Recompras / Dilución")
        yoy_shares = shares_yearly.pct_change().dropna() * 100
        text_labels = [f"+{val:.2f}%" if val > 0 else f"{val:.2f}%" for val in yoy_shares.values]
        colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares.values]
        fig_shares = go.Figure()
        fig_shares.add_trace(go.Bar(x=yoy_shares.index.astype(str), y=yoy_shares.values, marker_color=colores_barras, text=text_labels, textposition='auto'))
        fig_shares.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=230,
            yaxis_title="Variación Anual (%)", xaxis_title="", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_shares, use_container_width=True)

    # --- GRÁFICO COMBINADO DE DIVIDENDOS (AHORA CON EJE X ENRIQUECIDO) ---
    if not dividendos_anuales.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 💰 Historial de Dividendos Anuales y Crecimiento YoY (10 Años)")
        fecha_corte_10y_divs = datetime.now() - pd.DateOffset(years=10)
        divs_10y = dividendos_anuales[dividendos_anuales.index >= fecha_corte_10y_divs.year]
        
        if len(divs_10y) > 0:
            crecimiento_yoy = divs_10y.pct_change() * 100
            
            x_labels_enriquecidos = []
            for year, val in zip(divs_10y.index, crecimiento_yoy.values):
                if pd.isna(val):
                    x_labels_enriquecidos.append(str(year))
                else:
                    color_pct = '#21c354' if val > 0 else '#ff4b4b'
                    signo_pct = '+' if val > 0 else ''
                    x_labels_enriquecidos.append(f"{year}<br><span style='color:{color_pct}; font-size:12px'>{signo_pct}{val:.1f}%</span>")
            
            fig_divs = go.Figure()
            
            fig_divs.add_trace(go.Bar(
                x=x_labels_enriquecidos, y=divs_10y.values, name=f"Dividendo ({sym})", marker_color='#00d4ff', yaxis='y1',
                text=[f"{val:.2f}{sym}" for val in divs_10y.values], textposition='auto'
            ))
            
            fig_divs.add_trace(go.Scatter(
                x=x_labels_enriquecidos, y=crecimiento_yoy.values, name="Crecimiento YoY", 
                mode='lines+markers', 
                line=dict(color='#21c354', width=3), marker=dict(size=8), yaxis='y2'
            ))
            
            fig_divs.update_layout(
                template='plotly_dark', 
                margin=dict(l=0, r=0, t=30, b=40), 
                height=300, 
                hovermode="x unified", 
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")),
                yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_divs, use_container_width=True)

    st.divider()

    # 3. DECÁLOGO DE CALIDAD
    st.subheader("📋 Decálogo de Calidad del Blue Chip")
    
    if yield_actual >= yield_infravalorado: st.success(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Excelente, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: st.warning(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Aceptable, superior a media de {yield_medio:.2f}%)")
    else: st.error(f"Rentabilidad Bruta (Real): {yield_actual:.2f}% (Pobre, inferior a media de {yield_medio:.2f}%)")

    if 0 < payout_ratio <= payout_limite_bpa: st.success(f"Payout (BPA): {payout_ratio:.2f}% (Seguro para su sector, exige < {payout_limite_bpa:.0f}%)")
    else: st.error(f"Payout (BPA): {payout_ratio:.2f}% (Elevado, el límite de su sector exige < {payout_limite_bpa:.0f}%)")
    
    if payout_fcf is not None:
        if payout_fcf == -1: st.error(f"Payout (FCF): NEGATIVO (Quema de caja)")
        elif payout_fcf <= payout_limite_fcf: st.success(f"Payout (FCF): {payout_fcf:.2f}% (Caja fuerte para su sector, exige < {payout_limite_fcf:.0f}%)")
        else: st.error(f"Payout (FCF): {payout_fcf:.2f}% (Peligro, supera el límite sectorial de {payout_limite_fcf:.0f}%)")

    if 0 < per <= 20: st.success(f"PER (Beneficio Contable): {per:.2f} (Valoración atractiva)")
    else: st.error(f"PER (Beneficio Contable): {per:.2f} (Múltiplo caro)")

    if p_fcf is not None:
        if p_fcf == -1: st.error("P/FCF (Efectivo Real): NEGATIVO")
        elif 0 < p_fcf <= 20: st.success(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Barato. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"P/FCF (Efectivo Real): {p_fcf:.2f} (Caro. FCF Yield: {fcf_yield:.2f}%)")

    if variacion_acciones is not None:
        if variacion_acciones < 0: st.success(f"Acciones en circulación: {variacion_acciones:.2f}% en 10 años (Excelente, la empresa destruye acciones)")
        elif variacion_acciones <= 5: st.warning(f"Acciones en circulación: +{variacion_acciones:.2f}% en 10 años (Estable / Ligera dilución)")
        else: st.error(f"Acciones en circulación: +{variacion_acciones:.2f}% en 10 años (Peligro, la empresa diluye al accionista)")

    if años_pagando >= 25 and racha_sin_recortes >= 12: st.success(f"Historial: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes (Aristócrata consagrada)")
    else: st.warning(f"Historial: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años")

    if incrementos_dividendo >= 5:
        st.success(f"Frecuencia de Aumentos (Filtro Weiss): El dividendo ha subido {incrementos_dividendo} veces en la última década (Cumple exigencia de > 5 aumentos)")
    else:
        st.error(f"Frecuencia de Aumentos (Filtro Weiss): Solo {incrementos_dividendo} aumentos detectados (Falta de crecimiento activo)")

    if total_años_bpa_datos > 0:
        ratio_bpa = años_crecimiento_bpa / total_años_bpa_datos
        if ratio_bpa >= 0.65:
            st.success(f"Consistencia BPA (Filtro Weiss): Crecimiento neto positivo en {años_crecimiento_bpa} de {total_años_bpa_datos} años analizados (Empresa altamente consistente)")
        else:
            st.error(f"Consistencia BPA (Filtro Weiss): Solo {años_crecimiento_bpa} años de crecimiento de {total_años_bpa_datos} evaluados (Excesiva ciclicidad)")

    if dgr_5y is not None:
        if dgr_5y >= 10: st.success(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Excelente)")
        elif dgr_5y > 0: st.warning(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Positivo)")
        else: st.error(f"Crecimiento DGR 5A (Medio Plazo): {dgr_5y:.2f}% (Estancado)")

    if dgr_10y is not None:
        if dgr_10y >= 10: st.success(f"Crecimiento DGR 10A (Largo Plazo): {dgr_10y:.2f}% (Excelente ritmo continuo)")
        elif dgr_10y > 0: st.warning(f"Crecimiento DGR 10A (Largo Plazo): {dgr_10y:.2f}% (Sostenido)")
        else: st.error(f"Crecimiento DGR 10A (Largo Plazo): {dgr_10y:.2f}% (Estancado)")

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
st.title("Screener Fundamental - Método Geraldine Weiss")
st.markdown("Introduce el ticker de una empresa para extraer sus datos financieros, rentabilidad real (FCF) y calcular sus bandas de valoración históricas.")

col_input, col_btn = st.columns([4, 1])
with col_input:
    ticker_input = st.text_input("Ticker de la empresa (Ej: ACN, WPC, AAPL):", placeholder="Escribe aquí...").upper()
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    analizar = st.button("Analizar Empresa", use_container_width=True)

if analizar and ticker_input:
    with st.spinner(f"Analizando {ticker_input}..."):
        try: screener_weiss_definitivo(ticker_input)
        except Exception as e: st.error(f"Se ha producido un error al descargar los datos: {e}")
