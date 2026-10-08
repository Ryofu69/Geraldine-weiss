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

# Diccionario de respaldo de sectores
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

    # --- FUNDAMENTALES Y MÉTRICAS BASE ---
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

    # --- EXTRACCIÓN DE INFORMES FINANCIEROS (ORDEN CRONOLÓGICO) ---
    inc_stmt = pd.DataFrame()
    bs_stmt = pd.DataFrame()
    try:
        if ticker.income_stmt is not None and not ticker.income_stmt.empty:
            inc_stmt = ticker.income_stmt.T.sort_index().T
        if ticker.balance_sheet is not None and not ticker.balance_sheet.empty:
            bs_stmt = ticker.balance_sheet.T.sort_index().T
    except Exception: pass

    # BPA y Crecimiento BPA 3Y
    años_crecimiento_bpa = 0
    total_años_bpa_datos = 0
    crecimiento_bpa_3y = None
    if not inc_stmt.empty:
        for key in ['Diluted EPS', 'Basic EPS']:
            if key in inc_stmt.index:
                eps_series = inc_stmt.loc[key].dropna()
                if len(eps_series) >= 2:
                    diffs = eps_series.diff().dropna()
                    años_crecimiento_bpa = int((diffs > 0).sum())
                    total_años_bpa_datos = len(diffs)
                if len(eps_series) >= 4 and eps_series.iloc[-4] > 0 and eps_series.iloc[-1] > 0:
                    crecimiento_bpa_3y = (((eps_series.iloc[-1] / eps_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                break

    # 1. RETORNO SOBRE EL CAPITAL INVERTIDO (ROIC)
    roic = None
    try:
        ebit_val = get_safe('operatingIncome')
        if ebit_val == 0 and not inc_stmt.empty:
            for k in ['Operating Income', 'EBIT']:
                if k in inc_stmt.index:
                    ebit_val = inc_stmt.loc[k].dropna().iloc[-1]
                    break
        total_equity = get_safe('totalStockholderEquity')
        if total_equity == 0 and not bs_stmt.empty:
            for eq_k in ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity']:
                if eq_k in bs_stmt.index:
                    total_equity = bs_stmt.loc[eq_k].dropna().iloc[-1]
                    break
        inv_cap = (total_debt + total_equity) - total_cash
        if inv_cap > 0 and ebit_val > 0:
            nopat = ebit_val * 0.79  # Tasa fiscal estándar corporativa (21%)
            roic = (nopat / inv_cap) * 100
    except Exception: pass

    # 2. CRECIMIENTO DE INGRESOS (REVENUE CAGR 3Y)
    revenue_cagr_3y = None
    if not inc_stmt.empty:
        for k in ['Total Revenue', 'Operating Revenue']:
            if k in inc_stmt.index:
                rev_series = inc_stmt.loc[k].dropna()
                if len(rev_series) >= 4 and rev_series.iloc[-4] > 0 and rev_series.iloc[-1] > 0:
                    revenue_cagr_3y = (((rev_series.iloc[-1] / rev_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                break

    # 3. COBERTURA DE INTERESES (EBIT / GASTO POR INTERESES)
    cobertura_intereses = None
    if not inc_stmt.empty:
        try:
            ebit_cov = None
            int_exp = None
            for k in ['Operating Income', 'EBIT']:
                if k in inc_stmt.index:
                    ebit_cov = inc_stmt.loc[k].dropna().iloc[-1]
                    break
            for k in ['Interest Expense', 'Interest Expense Non Operating']:
                if k in inc_stmt.index:
                    int_exp = abs(inc_stmt.loc[k].dropna().iloc[-1])
                    break
            if ebit_cov is not None and int_exp is not None and int_exp > 0:
                cobertura_intereses = ebit_cov / int_exp
        except Exception: pass

    # FCF y Payout sobre Caja
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

    # 4. COLCHÓN DE CAJA LÍQUIDA PARA DIVIDENDOS (MESES CUBIERTOS)
    meses_caja_div = None
    gasto_anual_div = forward_dividend * shares
    if currency == 'GBp': gasto_anual_div /= 100.0
    if gasto_anual_div > 0 and total_cash > 0:
        meses_caja_div = (total_cash / gasto_anual_div) * 12

    # Dividendos, DGR e Inercia
    dividendos_barras = divs_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    divs_recientes = dividendos_barras.tail(años_analisis + 1)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

    dgr_5y = None
    dgr_periodo = None
    dgr_1y = None
    if len(dividendos_barras) >= 2:
        div_act = dividendos_barras.iloc[-1]
        div_ant = dividendos_barras.iloc[-2]
        if div_ant > 0: dgr_1y = ((div_act / div_ant) - 1) * 100

    if len(dividendos_barras) >= 6:
        div_actual = dividendos_barras.iloc[-1]
        div_5y = dividendos_barras.iloc[-6]
        if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100
    
    if len(dividendos_barras) >= (años_analisis + 1):
        div_periodo = dividendos_barras.iloc[-(años_analisis + 1)]
        if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

    # 5. DETECCIÓN DE FATIGA E INERCIA DEL DIVIDENDO
    fatiga_dividendo = False
    inercia_ratio = None
    if dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0:
        inercia_ratio = dgr_1y / dgr_5y
        if inercia_ratio < 0.5:
            fatiga_dividendo = True

    # 6. AISLADOR DE DIVIDENDOS EXTRAORDINARIOS
    aviso_extraordinario = False
    if len(dividendos_barras) >= 4:
        mediana_reciente = dividendos_barras.iloc[-4:-1].median()
        ultimo_div = dividendos_barras.iloc[-1]
        if mediana_reciente > 0 and (ultimo_div / mediana_reciente) > 1.35:
            aviso_extraordinario = True

    racha_sin_recortes = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99:
                racha_sin_recortes += 1
            else: break

    # Acciones en circulación
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
            if not inc_stmt.empty:
                for key in ['Basic Average Shares', 'Diluted Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna()
                        sh_data = sh_data[sh_data > 0]
                        sh_data = sh_data[sh_data.pct_change().fillna(0) > -0.50]
                        if len(sh_data) >= 2:
                            shares_yearly = sh_data.groupby(sh_data.index.year).last()
                            acc_ini = shares_yearly.iloc[0]
                            acc_fin = shares_yearly.iloc[-1]
                            if acc_ini > 0: 
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                break
        except Exception: pass

    # Canales de Precio Weiss
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

    # ==========================================
    # CÁLCULO DUAL DGI MODERNO (0 a 10 Pts)
    # ==========================================
    
    # 1. SCORE DE CALIDAD DGI (10 Pts)
    score_calidad = 0.0

    # Solvencia Operativa (2.0 pts)
    lim_deuda_optima = 4.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 3.0
    lim_deuda_aceptable = 5.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0
    if deuda_ebitda <= lim_deuda_optima: pts_deuda = 2.0
    elif deuda_ebitda <= lim_deuda_aceptable: pts_deuda = 1.0
    else: pts_deuda = 0.0
    score_calidad += pts_deuda

    # Cobertura de Intereses (0.5 pts)
    if cobertura_intereses is not None:
        pts_cob = 0.5 if cobertura_intereses >= 4.0 else (0.25 if cobertura_intereses >= 2.5 else 0.0)
    else:
        pts_cob = 0.5 if deuda_neta == 0 else 0.0
    score_calidad += pts_cob

    # Seguridad del Dividendo - Payout FCF (2.0 pts)
    if 0 <= payout_fcf <= payout_limite_fcf: pts_fcf = 2.0
    elif payout_fcf <= payout_amarillo_fcf: pts_fcf = 1.0
    else: pts_fcf = 0.0
    score_calidad += pts_fcf

    # Resiliencia y Compromiso sin Fatiga (2.0 pts)
    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: pts_hist = 2.0
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: pts_hist = 1.25
    elif racha_sin_recortes >= 5: pts_hist = 0.75
    else: pts_hist = 0.0
    if fatiga_dividendo and pts_hist > 0.5:
        pts_hist -= 0.5
    score_calidad += pts_hist

    # Foso Económico - ROIC y Ventas (1.0 pt)
    cond_roic = (roic is not None and roic >= 10.0)
    cond_rev = (revenue_cagr_3y is not None and revenue_cagr_3y > 0)
    if cond_roic and cond_rev: pts_foso = 1.0
    elif cond_roic or cond_rev: pts_foso = 0.5
    else: pts_foso = 0.0
    score_calidad += pts_foso

    # Crecimiento Real DGR 5A (1.0 pt)
    if dgr_5y is not None and dgr_5y >= 5.0: pts_dgr = 1.0
    elif dgr_5y is not None and dgr_5y >= 2.5: pts_dgr = 0.5
    else: pts_dgr = 0.0
    score_calidad += pts_dgr

    # Asignación de Capital: Recompras o Crecimiento de BPA (1.5 pts)
    cond_recompras = variacion_acciones is not None and variacion_acciones < -0.5
    cond_bpa_pos = crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0
    pts_cap = 1.5 if (cond_recompras or cond_bpa_pos) else 0.0
    score_calidad += pts_cap

    # 2. SCORE DE VALORACIÓN DGI (10 Pts)
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
    tipo_empresa_txt = "🏢 Sector Inmobiliario/Regulado (Filtros Flexibles)" if es_regulada_o_reit else "🏭 Sector Industrial/General (Filtros Estrictos)[span_6](start_span)"[span_6](end_span)
    
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")[span_7](start_span)[span_7](end_span)
    
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 10px; border-radius: 5px; margin-bottom: 20px;">
        <strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <strong>Industry:</strong> <span style="color: #21c354;">{industry_final}</span>
    </div>
    """, unsafe_allow_html=True)[span_8](start_span)[span_8](end_span)
    
    # Módulo Fiscal[span_9](start_span)[span_9](end_span)
    st.markdown("### 🌍 Perfil Fiscal y Retención en Origen")[span_10](start_span)[span_10](end_span)
    if pais in ['United States', 'Netherlands', 'Canada']: 
        st.success(f"✅ **{pais}**: Retención en origen del 15%. Al coincidir con el máximo deducible en España por doble imposición internacional, es 100% recuperable automáticamente en tu declaración de la Renta.")[span_11](start_span)[span_11](end_span)
    elif pais == 'United Kingdom': 
        st.success(f"✅ **{pais}**: Retención en origen del 0% (salvo algunos REITs). Eficiencia fiscal óptima en origen, solo tributas el impuesto local configurado.")[span_12](start_span)[span_12](end_span)
    elif pais == 'Spain': 
        st.success(f"✅ **{pais}**: Mercado local. Retención directa del {impuesto_pct}%. Sin trámites ni retenciones en el extranjero.")[span_13](start_span)[span_13](end_span)
    elif pais == 'Denmark':
        st.warning(f"⚠️ **{pais} (Novo Nordisk, etc.)**: Retención estándar en origen muy elevada del 27%. El convenio con España limita la retención final al 15% (que recuperas en tu Renta). El **12% restante se queda retenido en Dinamarca** y exige un trámite de reclamación directa ante su hacienda (*Skat*).")[span_14](start_span)[span_14](end_span)
    elif pais == 'Switzerland':
        st.error(f"❌ **{pais}**: Retención en origen extrema del 35%. El convenio te permite deducir el 15% en España, pero el **20% sobrante queda bloqueado en Suiza** a menos que inicies el complejo proceso burocrático de devolución internacional (Formulario 81).")[span_15](start_span)[span_15](end_span)
    elif pais == 'Germany':
        st.error(f"❌ **{pais}**: Retención en origen del 26.375% (incluye el impuesto de solidaridad). Recuperas el 15% en España de forma automática, pero el **11.375% restante se pierde** si no reclamas su devolución rellenando los formularios de la hacienda federal alemana (*BZSt*).")[span_16](start_span)[span_16](end_span)
    elif pais == 'France':
        st.error(f"❌ **{pais}**: Retención estándar en origen del 25% (puede reducirse al 12.8% si tu bróker tramita los formularios de residencia previos). De lo contrario, tendrás que reclamar el exceso por encima del 15% a la hacienda francesa.")[span_17](start_span)[span_17](end_span)
    elif pais == 'Ireland': 
        st.warning(f"⚠️ **{pais}**: Retención en origen del 25%. Puedes deducir el 15% en España, pero el **10% restante exige trámites complejos** de devolución en origen según las capacidades de tu bróker.")[span_18](start_span)[span_18](end_span)
    else: 
        st.info(f"ℹ️ **{pais}**: Verifica el convenio de doble imposición internacional vigente y las tasas de retención actuales para residentes españoles.")[span_19](start_span)[span_19](end_span)

    # Alerta condicional de dividendo extraordinario
    if aviso_extraordinario:
        st.warning("⚠️ **Aviso de Dividendo Extraordinario:** Yahoo Finance registra un reparto un 35% superior a la mediana reciente. Comprueba si incluye un pago especial no recurrente antes de proyectar la rentabilidad futura.")

    st.subheader(f"🎯 Precios Objetivo y Valoración Actual (Basado en {años_analisis} Años)")[span_20](start_span)[span_20](end_span)
    
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
        """, unsafe_allow_html=True)[span_21](start_span)[span_21](end_span)

    col1, col2, col3, col4 = st.columns(4)[span_22](start_span)[span_22](end_span)
    with col1: metric_color("Cotización Actual", f"{precio_actual / divisor_uk:.2f}{sym}", f"Yield: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% neto)", txt_extra_actual, color_actual)[span_23](start_span)[span_23](end_span)
    with col2: metric_color("Franja Infravalorada", f"{precio_compra / divisor_uk:.2f}{sym}", f"Yield {yield_infravalorado:.2f}% ({yield_infravalorado * net_mult:.2f}% neto)", txt_extra_infra, "#21c354")[span_24](start_span)[span_24](end_span)
    with col3: metric_color("Precio Justo (Media)", f"{precio_justo / divisor_uk:.2f}{sym}", f"Yield {yield_medio:.2f}% ({yield_medio * net_mult:.2f}% neto)", txt_extra_justo, "#faca2b")[span_25](start_span)[span_25](end_span)
    with col4: metric_color("Franja Sobrevalorada", f"{precio_venta / divisor_uk:.2f}{sym}", f"Yield {yield_sobrevalorado:.2f}% ({yield_sobrevalorado * net_mult:.2f}% neto)", txt_extra_sobre, "#ff4b4b")[span_26](start_span)[span_26](end_span)

    st.markdown("<br>", unsafe_allow_html=True)[span_27](start_span)[span_27](end_span)
    
    # Doble Ranking DGI Independiente
    col_sc1, col_sc2 = st.columns(2)
    with col_sc1:
        if score_calidad >= 8.0: 
            st.success(f"🛡️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Sobresaliente. Fuerte generación de caja, balance blindado y foso claro.")
        elif score_calidad >= 6.0: 
            st.warning(f"⚖️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Aceptable. Negocio sólido con algún reto de apalancamiento o ciclo inversor.")
        else: 
            st.error(f"🚨 **CALIDAD DGI: {score_calidad:.1f}/10** — Calidad Insuficiente. Alerta en cobertura, solvencia o contracción estructural.")

    with col_sc2:
        if score_val >= 7.0: 
            st.success(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Oportunidad Clara. Cotiza en suelo de compra por canal histórico de Yield.")
        elif score_val >= 4.0: 
            st.warning(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Valoración Neutral. Cotiza cerca de su media histórica.")
        else: 
            st.error(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Sobrevalorada o Exigente. Margen de seguridad reducido.")

    if precio_actual <= precio_compra: st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada).")[span_28](start_span)[span_28](end_span)
    elif precio_actual >= precio_venta: st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")[span_29](start_span)[span_29](end_span)
    else: st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")[span_30](start_span)[span_30](end_span)

    # Gráfico del Canal Histórico Weiss[span_31](start_span)[span_31](end_span)
    st.markdown(f"### 📈 Evolución Histórica de Valoración ({años_analisis} Años)")[span_32](start_span)[span_32](end_span)
    df_grafico = historial_analisis[['Close']].copy()[span_33](start_span)[span_33](end_span)
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_analisis['Div_Anual'][span_34](start_span)[span_34](end_span)
        df_grafico['Precio_Compra'] = (df_grafico['Div_Grafico'] / yield_infravalorado) * 100[span_35](start_span)[span_35](end_span)
        df_grafico['Precio_Justo'] = (df_grafico['Div_Grafico'] / yield_medio) * 100[span_36](start_span)[span_36](end_span)
        df_grafico['Precio_Venta'] = (df_grafico['Div_Grafico'] / yield_sobrevalorado) * 100[span_37](start_span)[span_37](end_span)
        
        if currency == 'GBp':
            df_grafico['Close'] = df_grafico['Close'] / divisor_uk[span_38](start_span)[span_38](end_span)
            df_grafico['Precio_Compra'] = df_grafico['Precio_Compra'] / divisor_uk[span_39](start_span)[span_39](end_span)
            df_grafico['Precio_Justo'] = df_grafico['Precio_Justo'] / divisor_uk[span_40](start_span)[span_40](end_span)
            df_grafico['Precio_Venta'] = df_grafico['Precio_Venta'] / divisor_uk[span_41](start_span)[span_41](end_span)

        fig = go.Figure()[span_42](start_span)[span_42](end_span)
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Venta'], name='Franja Sobrevalorada (Venta)', line=dict(color='#ff4b4b', width=2)))[span_43](start_span)[span_43](end_span)
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dash')))[span_44](start_span)[span_44](end_span)
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Compra'], name='Franja Infravalorada (Compra)', line=dict(color='#21c354', width=2)))[span_45](start_span)[span_45](end_span)
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Close'], name='Cotización Real', line=dict(color='#00d4ff', width=3)))[span_46](start_span)[span_46](end_span)
        
        fig.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), 
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), 
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )[span_47](start_span)[span_47](end_span)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])[span_48](start_span)[span_48](end_span)
        st.plotly_chart(fig, use_container_width=True)[span_49](start_span)[span_49](end_span)

        is_compra = df_grafico['Close'] <= df_grafico['Precio_Compra'][span_50](start_span)[span_50](end_span)
        toques_compra = (is_compra & ~is_compra.shift(1, fill_value=False)).sum()[span_51](start_span)[span_51](end_span)
        is_venta = df_grafico['Close'] >= df_grafico['Precio_Venta'][span_52](start_span)[span_52](end_span)
        toques_venta = (is_venta & ~is_venta.shift(1, fill_value=False)).sum()[span_53](start_span)[span_53](end_span)
        
        def format_last_time(is_zone_series, active_color):
            if is_zone_series.sum() == 0: return "Nunca", "#aaa[span_54](start_span)"[span_54](end_span)
            if is_zone_series.iloc[-1]: return "Ahora", active_color[span_55](start_span)[span_55](end_span)
            last_date = is_zone_series[is_zone_series].index[-1][span_56](start_span)[span_56](end_span)
            days_diff = (pd.Timestamp.now().normalize() - last_date.tz_localize(None).normalize()).days[span_57](start_span)[span_57](end_span)
            if days_diff < 30: return f"hace {days_diff} días", "#ccc[span_58](start_span)"[span_58](end_span)
            elif days_diff < 365: return f"hace {days_diff // 30} meses", "#ccc[span_59](start_span)"[span_59](end_span)
            else: return f"hace {days_diff / 365.25:.1f}a".replace(".", ","), "#ccc[span_60](start_span)"[span_60](end_span)

        str_ultima_compra, color_ult_compra = format_last_time(is_compra, "#21c354")[span_61](start_span)[span_61](end_span)
        str_ultima_venta, color_ult_venta = format_last_time(is_venta, "#ff4b4b")[span_62](start_span)[span_62](end_span)

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
        ""[span_63](start_span)"[span_63](end_span)
        st.markdown(html_stats, unsafe_allow_html=True)[span_64](start_span)[span_64](end_span)

    # Lupa de Francotirador MACD[span_65](start_span)[span_65](end_span)
    st.divider()[span_66](start_span)[span_66](end_span)
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses)")[span_67](start_span)[span_67](end_span)
    st.markdown("> **Uso según el Método Weiss:** Busca picos de volumen rojo extremo (Capitulación) cuando las barras toquen la línea verde discontinua (Suelo Fundamental). Dispara cuando el MACD cruce al alza perdiendo inercia bajista.")[span_68](start_span)[span_68](end_span)

    fecha_calculo_macd = pd.Timestamp.now().normalize() - pd.DateOffset(years=1)[span_69](start_span)[span_69](end_span)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()[span_70](start_span)[span_70](end_span)

    if len(df_tech_full) > 30: 
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100[span_71](start_span)[span_71](end_span)
        df_tech_full['Precio_Justo'] = (df_tech_full['Div_Anual'] / yield_medio) * 100[span_72](start_span)[span_72](end_span)
        df_tech_full['Precio_Venta'] = (df_tech_full['Div_Anual'] / yield_sobrevalorado) * 100[span_73](start_span)[span_73](end_span)

        if yield_req_chowder is not None and yield_req_chowder > 0:
            df_tech_full['Precio_Chowder'] = (df_tech_full['Div_Anual'] / yield_req_chowder) * 100[span_74](start_span)[span_74](end_span)

        if currency == 'GBp':
            for col in ['Open', 'High', 'Low', 'Close', 'Precio_Compra', 'Precio_Justo', 'Precio_Venta']: 
                df_tech_full[col] = df_tech_full[col] / divisor_uk[span_75](start_span)[span_75](end_span)
            if 'Precio_Chowder' in df_tech_full.columns:
                df_tech_full['Precio_Chowder'] = df_tech_full['Precio_Chowder'] / divisor_uk[span_76](start_span)[span_76](end_span)

        ema12 = df_tech_full['Close'].ewm(span=12, adjust=False).mean()[span_77](start_span)[span_77](end_span)
        ema26 = df_tech_full['Close'].ewm(span=26, adjust=False).mean()[span_78](start_span)[span_78](end_span)
        df_tech_full['MACD'] = ema12 - ema26[span_79](start_span)[span_79](end_span)
        df_tech_full['Signal'] = df_tech_full['MACD'].ewm(span=9, adjust=False).mean()[span_80](start_span)[span_80](end_span)
        df_tech_full['Histogram'] = df_tech_full['MACD'] - df_tech_full['Signal'][span_81](start_span)[span_81](end_span)

        fecha_display = pd.Timestamp.now().normalize() - pd.DateOffset(months=2)[span_82](start_span)[span_82](end_span)
        df_tech = df_tech_full[df_tech_full.index >= fecha_display].copy()[span_83](start_span)[span_83](end_span)

        if not df_tech.empty:
            ult_close_val = precio_actual / divisor_uk[span_84](start_span)[span_84](end_span)
            ult_suelo_val = precio_compra / divisor_uk[span_85](start_span)[span_85](end_span)
            precio_str = f"{ult_close_val:.2f}{sym}[span_86](start_span)"[span_86](end_span)
            suelo_str = f"{ult_suelo_val:.2f}{sym}[span_87](start_span)"[span_87](end_span)
            dist_suelo = ((ult_close_val - ult_suelo_val) / ult_suelo_val) * 100 if ult_suelo_val > 0 else 999.0[span_88](start_span)[span_88](end_span)

            ult_macd = df_tech['MACD'].iloc[-1][span_89](start_span)[span_89](end_span)
            ult_signal = df_tech['Signal'].iloc[-1][span_90](start_span)[span_90](end_span)
            ult_hist = df_tech['Histogram'].iloc[-1][span_91](start_span)[span_91](end_span)
            penult_hist = df_tech['Histogram'].iloc[-2] if len(df_tech) > 1 else 0[span_92](start_span)[span_92](end_span)

            avg_vol = df_tech['Volume'].mean()[span_93](start_span)[span_93](end_span)
            max_vol_reciente = df_tech['Volume'].tail(5).max()[span_94](start_span)[span_94](end_span)
            vol_elevado = max_vol_reciente > (avg_vol * 1.5)[span_95](start_span)[span_95](end_span)

            analisis_ia = f"🧠 **Análisis de la IA (Leyendo cotización actual: {precio_str}):** [span_96](start_span)"[span_96](end_span)
            if dist_suelo <= 0:
                descuento_extra = abs(dist_suelo)[span_97](start_span)[span_97](end_span)
                if descuento_extra > 0.5: analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) cotiza un **{descuento_extra:.1f}% por debajo** de tu Suelo Fundamental ({suelo_str}). [span_98](start_span)"[span_98](end_span)
                else: analisis_ia += f"🎯 **En Zona de Disparo.** El precio ({precio_str}) está tocando el Suelo Fundamental ({suelo_str}). [span_99](start_span)"[span_99](end_span)
                if vol_elevado: analisis_ia += "Se detecta volumen extremo reciente (posible capitulación). [span_100](start_span)"[span_100](end_span)
                if ult_macd > ult_signal and ult_hist > 0: analisis_ia += "El MACD confirma giro alcista. **Escenario de COMPRA IDEAL.**[span_101](start_span)"[span_101](end_span)
                elif ult_macd < ult_signal and ult_hist > penult_hist: analisis_ia += "El MACD sigue bajista pero pierde fuerza. Atento al inminente cruce al alza.[span_102](start_span)"[span_102](end_span)
                else: analisis_ia += "El MACD sigue cayendo con fuerza. Compra si eres un fundamental estricto, o espera si prefieres confirmación técnica.[span_103](start_span)"[span_103](end_span)
            elif 0 < dist_suelo <= 5.0:
                analisis_ia += f"🟡 **Alerta Temprana / Rebote.** El precio ({precio_str}) está a un **{dist_suelo:.1f}%** de tu zona de compra ({suelo_str}). [span_104](start_span)"[span_104](end_span)
                if ult_macd > ult_signal: analisis_ia += "El MACD es alcista. Si la acción acaba de rebotar desde la línea verde, es buena entrada aunque llegues algo tarde.[span_105](start_span)"[span_105](end_span)
                else: analisis_ia += "El MACD es bajista. Lo ideal es esperar a que siga corrigiendo hasta tocar la línea verde discontinua para maximizar el margen de seguridad.[span_106](start_span)"[span_106](end_span)
            else:
                analisis_ia += f"🔴 **Fuera de Zona.** El precio ({precio_str}) cotiza un **{dist_suelo:.1f}%** por encima del suelo exigido ({suelo_str}). [span_107](start_span)"[span_107](end_span)
                analisis_ia += "No hay margen de seguridad suficiente. Observa desde la barrera y pon alertas por si la acción sufre una corrección severa.[span_108](start_span)"[span_108](end_span)
            st.info(analisis_ia)[span_109](start_span)[span_109](end_span)

            colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for index, row in df_tech.iterrows()][span_110](start_span)[span_110](end_span)
            colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']][span_111](start_span)[span_111](end_span)

            fig_tech = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3])[span_112](start_span)[span_112](end_span)
            fig_tech.add_trace(go.Ohlc(x=df_tech.index, open=df_tech['Open'], high=df_tech['High'], low=df_tech['Low'], close=df_tech['Close'], name='Precio', increasing_line_color='#21c354', decreasing_line_color='#ff4b4b', showlegend=False), row=1, col=1)[span_113](start_span)[span_113](end_span)

            ex_div_ts = info.get('exDividendDate')[span_114](start_span)[span_114](end_span)
            if pd.notna(ex_div_ts) and ex_div_ts is not None:
                try:
                    ex_div_date_future = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()[span_115](start_span)[span_115](end_span)
                    if ex_div_date_future >= pd.Timestamp.now().normalize():
                        fig_tech.add_vline(x=ex_div_date_future, line_width=1.5, line_dash="dot", line_color="#e040fb", 
                                           annotation_text=" Ⓓ Ex-Div", annotation_position="bottom right", 
                                           annotation_font=dict(color="#e040fb", size=11, family="Arial", weight="bold"), row=1, col=1)[span_116](start_span)[span_116](end_span)
                except: pass[span_117](start_span)[span_117](end_span)

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)[span_118](start_span)[span_118](end_span)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)[span_119](start_span)[span_119](end_span)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)[span_120](start_span)[span_120](end_span)

            if 'Precio_Chowder' in df_tech.columns:
                fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Chowder'], name='Precio Obj. Chowder', line=dict(color='#e040fb', width=1.5, dash='dashdot'), showlegend=True, visible='legendonly'), row=1, col=1)[span_121](start_span)[span_121](end_span)

            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False), row=2, col=1)[span_122](start_span)[span_122](end_span)
            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False), row=3, col=1)[span_123](start_span)[span_123](end_span)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False), row=3, col=1)[span_124](start_span)[span_124](end_span)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False), row=3, col=1)[span_125](start_span)[span_125](end_span)

            fig_tech.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=800, showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_rangeslider_visible=False)[span_126](start_span)[span_126](end_span)
            fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])[span_127](start_span)[span_127](end_span)
            st.plotly_chart(fig_tech, use_container_width=True)[span_128](start_span)[span_128](end_span)
        else: st.info("No hay suficientes datos recientes en Yahoo Finance para dibujar el panel de 2 meses.")[span_129](start_span)[span_129](end_span)
    else: st.info("No hay suficientes datos históricos en Yahoo Finance para calcular el panel técnico (MACD/Volumen).")[span_130](start_span)[span_130](end_span)

    # ==========================================
    # RADIOGRAFÍA FINANCIERA DGI MODERNA
    # ==========================================
    st.divider()[span_131](start_span)[span_131](end_span)
    st.subheader("📊 Radiografía Financiera y Métricas DGI Modernas")

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

    # 1. BENEFICIOS Y MÚLTIPLOS (PRESENTE VS FUTURO)
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
            st.metric("BPA Actual", f"{bpa_trailing:.2f}{sym}" if bpa_trailing != 0 else "N/D")[span_132](start_span)[span_132](end_span)

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
            st.metric("PER Actual", f"{per_actual:.1f}x" if per_actual > 0 else "N/D")[span_133](start_span)[span_133](end_span)

    # 2. VALIDACIÓN DE FOSO ECONÓMICO (ROIC Y VENTAS)
    col_foso1, col_foso2 = st.columns(2)
    with col_foso1:
        if roic is not None:
            if roic >= 12.0: r_badge, r_txt = "badge-verde", "Foso Amplio (≥ 12%)"
            elif roic >= 8.0: r_badge, r_txt = "badge-ambar", "Foso Medio (≥ 8%)"
            else: r_badge, r_txt = "badge-rojo", "Foso Débil (< 8%)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏰 Retorno s/ Capital Invertido (ROIC)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{roic:.2f}%</span>
                    <span class="{r_badge}">{r_txt}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Mide la rentabilidad real de reinversión del negocio</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏰 Retorno s/ Capital Invertido (ROIC)</span>
                <div style="font-size: 1.3rem; font-weight: bold; margin-top: 4px;">N/D</div>
                <span style="font-size: 0.75rem; color: #888;">Datos de balance insuficientes</span>
            </div>
            """, unsafe_allow_html=True)

    with col_foso2:
        if revenue_cagr_3y is not None:
            v_badge = "badge-verde" if revenue_cagr_3y > 0 else "badge-rojo"
            v_txt = "Expandiendo" if revenue_cagr_3y > 0 else "Contrayendo"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">📊 Crecimiento de Ventas (Top-Line 3A)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{revenue_cagr_3y:+.2f}%</span>
                    <span class="{v_badge}">{v_txt}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">CAGR de ingresos netos (filtro anti trampa de valor)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">📊 Crecimiento de Ventas (Top-Line 3A)</span>
                <div style="font-size: 1.3rem; font-weight: bold; margin-top: 4px;">N/D</div>
                <span style="font-size: 0.75rem; color: #888;">Historial de facturación insuficiente</span>
            </div>
            """, unsafe_allow_html=True)

    # 3. SOLVENCIA OPERATIVA Y COBERTURA DE INTERESES
    col_sol1, col_sol2 = st.columns(2)
    with col_sol1:
        if deuda_ebitda < 900:
            if deuda_ebitda <= lim_deuda_optima: b_deb, t_deb = "badge-verde", f"Óptimo (≤ {lim_deuda_optima:.1f}x)"
            elif deuda_ebitda <= lim_deuda_aceptable: b_deb, t_deb = "badge-ambar", f"Aceptable (≤ {lim_deuda_aceptable:.1f}x)"
            else: b_deb, t_deb = "badge-rojo", "Apalancada"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🛡️ Deuda Neta / EBITDA</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{deuda_ebitda:.2f}x</span>
                    <span class="{b_deb}">{t_deb}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Años de EBITDA para extinguir la deuda neta</span>
            </div>
            """, unsafe_allow_html=True)

    with col_sol2:
        if cobertura_intereses is not None:
            if cobertura_intereses >= 4.0: b_cob, t_cob = "badge-verde", "Holgada (≥ 4.0x)"
            elif cobertura_intereses >= 2.5: b_cob, t_cob = "badge-ambar", "Aceptable (≥ 2.5x)"
            else: b_cob, t_cob = "badge-rojo", "Riesgo (< 2.5x)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⚡ Cobertura de Intereses (EBIT / Intereses)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{cobertura_intereses:.2f}x</span>
                    <span class="{b_cob}">{t_cob}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Capacidad de pago de intereses con beneficio operativo</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            txt_caja_neta = "Caja Neta (Sin Deuda)" if deuda_neta == 0 else "N/D"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⚡ Cobertura de Intereses</span>
                <div style="font-size: 1.3rem; font-weight: bold; margin-top: 4px;">{txt_caja_neta}</div>
                <span style="font-size: 0.75rem; color: #888;">No registra cargos por intereses bancarios</span>
            </div>
            """, unsafe_allow_html=True)

    # 4. COLCHÓN DE CAJA Y RETORNO DE CAPITAL
    col_caj1, col_caj2 = st.columns(2)
    with col_caj1:
        if meses_caja_div is not None:
            b_caj = "badge-verde" if meses_caja_div >= 12.0 else ("badge-ambar" if meses_caja_div >= 6.0 else "badge-rojo")
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">💰 Colchón de Caja para Dividendos</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{meses_caja_div:.1f} Meses</span>
                    <span class="{b_caj}">{meses_caja_div / 12:.1f} Años</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Meses de dividendo cubiertos solo con la tesorería actual</span>
            </div>
            """, unsafe_allow_html=True)

    with col_caj2:
        if variacion_acciones is not None:
            if variacion_acciones < -0.5: t_acc, c_acc_b, sub_acc = "🟢 Recomprando", "badge-verde", "Destruye acciones (Genera valor)"
            elif variacion_acciones <= 2.0: t_acc, c_acc_b, sub_acc = "🟡 Estable", "badge-ambar", "Capital social constante"
            else: t_acc, c_acc_b, sub_acc = "🔴 Diluyendo", "badge-rojo", "Ampliaciones o compensaciones en títulos"
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

    # 5. VELOCÍMETRO DEL DIVIDENDO E INERCIA (DETECCIÓN DE FATIGA)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🚀 Crecimiento del Dividendo e Inercia (DGR)")
    
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
                <span style="font-size: 0.75rem; color: #888;">Poder adquisitivo anual ganado s/ inflación de referencia (2.5%)</span>
            </div>
            """, unsafe_allow_html=True)

    with col_dgr2:
        if dgr_1y is not None and dgr_5y is not None:
            if fatiga_dividendo:
                t_iner, b_iner = "⚠️ Fatiga (Frenando)", "badge-rojo"
            elif inercia_ratio >= 1.0:
                t_iner, b_iner = "⚡ Acelerando", "badge-verde"
            else:
                t_iner, b_iner = "➡️ Ritmo Estable", "badge-ambar"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">Inercia del Dividendo (Último Año vs Media 5A)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.6rem; font-weight: bold; color: #00d4ff;">{dgr_1y:+.2f}%</span>
                    <span class="{b_iner}">{t_iner}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Última subida anual vs tasa quinquenal ({dgr_5y:.2f}%)</span>
            </div>
            """, unsafe_allow_html=True)

    # Historial de Recompras y Dividendos Gráficos[span_134](start_span)[span_134](end_span)
    if not shares_yearly.empty and len(shares_yearly) > 1:
        st.markdown("<br>", unsafe_allow_html=True)[span_135](start_span)[span_135](end_span)
        st.markdown(f"#### 🔄 Historial Anual de Recompras / Dilución ({años_analisis} Años)")[span_136](start_span)[span_136](end_span)
        yoy_shares_total = shares_yearly.pct_change().dropna() * 100[span_137](start_span)[span_137](end_span)
        yoy_shares_analisis = yoy_shares_total.tail(años_analisis)[span_138](start_span)[span_138](end_span)
        text_labels = [f"+{val:.2f}%" if val > 0 else f"{val:.2f}%" for val in yoy_shares_analisis.values][span_139](start_span)[span_139](end_span)
        colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares_analisis.values][span_140](start_span)[span_140](end_span)
        fig_shares = go.Figure()[span_141](start_span)[span_141](end_span)
        fig_shares.add_trace(go.Bar(x=yoy_shares_analisis.index.astype(str), y=yoy_shares_analisis.values, marker_color=colores_barras, text=text_labels, textposition='auto'))[span_142](start_span)[span_142](end_span)
        fig_shares.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=230, yaxis_title="Variación Anual (%)", xaxis_title="", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')[span_143](start_span)[span_143](end_span)
        st.plotly_chart(fig_shares, use_container_width=True)[span_144](start_span)[span_144](end_span)

    if not dividendos_barras.empty:
        st.markdown("<br>", unsafe_allow_html=True)[span_145](start_span)[span_145](end_span)
        st.markdown(f"#### 💰 Historial de Dividendos Anuales y Crecimiento YoY ({años_analisis} Años)")[span_146](start_span)[span_146](end_span)
        crecimiento_yoy_total = dividendos_barras.pct_change() * 100[span_147](start_span)[span_147](end_span)
        divs_analisis = dividendos_barras.tail(años_analisis)[span_148](start_span)[span_148](end_span)
        crecimiento_yoy_analisis = crecimiento_yoy_total.tail(años_analisis)[span_149](start_span)[span_149](end_span)
        if len(divs_analisis) > 0:
            x_labels_enriquecidos = [][span_150](start_span)[span_150](end_span)
            for year, val in zip(divs_analisis.index, crecimiento_yoy_analisis.values):
                if pd.isna(val): x_labels_enriquecidos.append(str(year))[span_151](start_span)[span_151](end_span)
                else:
                    color_pct = '#21c354' if val > 0 else '#ff4b4b[span_152](start_span)'[span_152](end_span)
                    signo_pct = '+' if val > 0 else '[span_153](start_span)'[span_153](end_span)
                    x_labels_enriquecidos.append(f"{year}<br><span style='color:{color_pct}; font-size:12px'>{signo_pct}{val:.1f}%</span>")[span_154](start_span)[span_154](end_span)
            fig_divs = go.Figure()[span_155](start_span)[span_155](end_span)
            fig_divs.add_trace(go.Bar(x=x_labels_enriquecidos, y=divs_analisis.values, name=f"Dividendo ({sym})", marker_color='#00d4ff', yaxis='y1', text=[f"{val:.2f}{sym}" for val in divs_analisis.values], textposition='auto'))[span_156](start_span)[span_156](end_span)
            fig_divs.add_trace(go.Scatter(x=x_labels_enriquecidos, y=crecimiento_yoy_analisis.values, name="Crecimiento YoY", mode='lines+markers', line=dict(color='#21c354', width=3), marker=dict(size=8), yaxis='y2'))[span_157](start_span)[span_157](end_span)
            fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))[span_158](start_span)[span_158](end_span)
            st.plotly_chart(fig_divs, use_container_width=True)[span_159](start_span)[span_159](end_span)

    # ==========================================
    # SECCIÓN CHOWDER REDISEÑADA
    # ==========================================
    st.divider()[span_160](start_span)[span_160](end_span)
    st.subheader("🥣 La Regla de Chowder (Retorno Total Compuesto)")

    if (es_utility_pura or es_telecom) and yield_actual > 4.0:
        criterio_txt = "Sector Regulado/Utility con Yield > 4.0% (Meta ≥ 8.0)"
    elif yield_actual >= 3.0:
        criterio_txt = "Yield Inicial Alto ≥ 3.0% (Meta estándar ≥ 12.0)"
    else:
        criterio_txt = "Yield Inicial Bajo < 3.0% (Meta estricta ≥ 15.0 por alto crecimiento)"

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
                <div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 6px;">
                    <div style="background: {color_barra}; width: {pct_progreso:.1f}%; height: 100%;"></div>
                </div>
                <span style="font-size: 0.75rem; color: #888;">{criterio_txt}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("🥣 Datos de crecimiento a 5 años insuficientes para calcular la Regla de Chowder.")

    with col_chow2:
        if chowder_number is not None:
            if chowder_pass or yield_req_chowder <= 0:
                st.markdown(f"""
                <div class="card-dgi">
                    <span style="color: #aaa; font-size: 0.85rem;">🎯 Precio Objetivo por Chowder</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px; margin-bottom: 8px;">
                        <span style="font-size: 1.5rem; font-weight: bold; color: #21c354;">Ya Cumple la Regla</span>
                        <span class="badge-verde">En Precio</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #888;">El rendimiento actual y su ritmo de subida ya baten la meta sin exigir mayor descuento.</span>
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

    # ==========================================
    # DECÁLOGO DETALLADO DGI COMPLETO[span_161](start_span)[span_161](end_span)
    # ==========================================
    st.divider()[span_162](start_span)[span_162](end_span)
    st.subheader(f"📋 Decálogo Detallado DGI — Geraldine Weiss Moderno ({años_analisis} Años)")[span_163](start_span)[span_163](end_span)
    
    t_yield = f"[🏷️ Val: +{pts_yield:.1f} / 4.0 pts]"
    t_pfcf = f"[🏷️ Val: +{pts_pfcf:.2f} / 2.5 pts]"
    t_per_t = f"[🏷️ Val: +{pts_per:.1f} / 2.0 pts]"
    t_chowder_t = f"[🏷️ Val: +{pts_chowder:.1f} / 1.5 pts]"
    
    t_fcf = f"[🛡️ Cal: +{pts_fcf:.2f} / 2.0 pts]"
    t_deuda = f"[🛡️ Cal: +{pts_deuda:.1f} / 2.0 pts]"
    t_cob_t = f"[🛡️ Cal: +{pts_cob:.2f} / 0.5 pts]"
    t_hist = f"[🛡️ Cal: +{pts_hist:.2f} / 2.0 pts]"
    t_foso_t = f"[🛡️ Cal: +{pts_foso:.1f} / 1.0 pts]"
    t_dgr_t = f"[🛡️ Cal: +{pts_dgr:.2f} / 1.0 pts]"
    t_cap_t = f"[🛡️ Cal: +{pts_cap:.1f} / 1.5 pts]"
    t_info = "[ℹ️ Info][span_164](start_span)"[span_164](end_span)

    st.markdown("#### 🏷️ 1. Múltiplos y Oportunidad de Entrada (Score Valoración: 10 Pts)")
    if yield_actual >= yield_infravalorado: 
        st.success(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (En Suelo Histórico de Compra, supera el {yield_infravalorado:.2f}%)")[span_165](start_span)[span_165](end_span)
    elif yield_actual >= yield_medio: 
        st.warning(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Aceptable: por encima de la media histórica de {yield_medio:.2f}%)")[span_166](start_span)[span_166](end_span)
    else: 
        st.error(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Pobre: por debajo de su media histórica de {yield_medio:.2f}%)")[span_167](start_span)[span_167](end_span)

    if p_fcf != -1:
        if 0 < p_fcf <= 20.0: st.success(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Muy atractivo ≤ 20x. FCF Yield: {fcf_yield:.2f}%)")[span_168](start_span)[span_168](end_span)
        elif 0 < p_fcf <= 25.0: st.warning(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Moderado ≤ 25x. FCF Yield: {fcf_yield:.2f}%)")
        else: st.error(f"{t_pfcf} P/FCF (Múltiplo Flujo de Caja): {p_fcf:.2f}x (Múltiplo exigente > 25x. FCF Yield: {fcf_yield:.2f}%)")[span_169](start_span)[span_169](end_span)
    else: st.error(f"{t_pfcf} P/FCF: NEGATIVO (La empresa no genera flujo de caja libre)")[span_170](start_span)[span_170](end_span)

    if 0 < per <= 20.0: st.success(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Valoración razonable ≤ 20x)")[span_171](start_span)[span_171](end_span)
    elif 0 < per <= 25.0: st.warning(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo justo ≤ 25x)")
    else: st.error(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo exigente > 25x)")[span_172](start_span)[span_172](end_span)

    if chowder_number is not None and chowder_pass:
        st.success(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Aprobada ≥ {chowder_target:.0f}. Retorno total compuesto atractivo)")
    elif chowder_number is not None:
        st.error(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Suspensa < {chowder_target:.0f}. Retorno combinado insuficiente)")
    else:
        st.info(f"{t_chowder_t} Regla de Chowder: N/D")

    if price_to_book > 0:
        if es_financiera or es_industrial: l_verde, l_amarillo = 1.5, 2.5; ctx = "Financiero/Industrial[span_173](start_span)"[span_173](end_span)
        elif es_tecnologica: l_verde, l_amarillo = 5.0, 10.0; ctx = "Tecnología/Software[span_174](start_span)"[span_174](end_span)
        else: l_verde, l_amarillo = 2.5, 5.0; ctx = "General[span_175](start_span)"[span_175](end_span)
        if price_to_book <= l_verde: st.success(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: Atractivo)")[span_176](start_span)[span_176](end_span)
        elif price_to_book <= l_amarillo: st.warning(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: En rango)")[span_177](start_span)[span_177](end_span)
        else: st.info(f"{t_info} Precio/Libros (P/B): {price_to_book:.2f}x ({ctx}: Elevado por intangibles o recompras)")[span_178](start_span)[span_178](end_span)

    st.markdown("#### 🛡️ 2. Seguridad del Dividendo en Efectivo (Score Calidad: 10 Pts)")
    if payout_fcf != -1:
        if 0 <= payout_fcf <= payout_limite_fcf: 
            st.success(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Excelente: holgura de caja ≤ {payout_limite_fcf:.0f}%)")[span_179](start_span)[span_179](end_span)
        elif payout_fcf <= payout_amarillo_fcf: 
            st.warning(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Aceptable: consume parte del colchón de caja ≤ {payout_amarillo_fcf:.0f}%)")[span_180](start_span)[span_180](end_span)
        else: 
            st.error(f"{t_fcf} Payout sobre FCF (Efectivo Real): {payout_fcf:.2f}% (Precaución: el dividendo presiona el flujo libre > {payout_amarillo_fcf:.0f}%)")[span_181](start_span)[span_181](end_span)
    else: 
        st.error(f"{t_fcf} Payout sobre FCF: NEGATIVO (La empresa está quemando caja)")[span_182](start_span)[span_182](end_span)

    if 0 < payout_ratio <= payout_limite_bpa: 
        st.success(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Sano para su sector, referencia < {payout_limite_bpa:.0f}%)")[span_183](start_span)[span_183](end_span)
    elif payout_limite_bpa < payout_ratio <= payout_amarillo_bpa: 
        st.warning(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (En el límite sectorial de {payout_amarillo_bpa:.0f}%)")[span_184](start_span)[span_184](end_span)
    else: 
        st.info(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Elevado contablemente)")[span_185](start_span)[span_185](end_span)
    
    if payout_forward != -1:
        tendencia_fw = "mejorará" if payout_forward < payout_ratio else "empeorará[span_186](start_span)"[span_186](end_span)
        st.info(f"{t_info} Forward Payout BPA (Estimado): {payout_forward:.2f}% (La cobertura contable prevista {tendencia_fw})")[span_187](start_span)[span_187](end_span)

    st.markdown("#### 🏗️ 3. Solvencia Operativa y Asignación de Capital")
    if deuda_ebitda <= lim_deuda_optima: 
        st.success(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Óptimo ≤ {lim_deuda_optima:.1f}x. Capacidad de pago excelente)")
    elif deuda_ebitda <= lim_deuda_aceptable: 
        st.warning(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Aceptable ≤ {lim_deuda_aceptable:.1f}x. Apalancamiento controlado)")
    else: 
        st.error(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Peligro: deuda operativa elevada > {lim_deuda_aceptable:.1f}x)")

    if cobertura_intereses is not None and cobertura_intereses >= 4.0:
        st.success(f"{t_cob_t} Cobertura de Intereses: {cobertura_intereses:.2f}x (Holgada ≥ 4.0x)")
    elif cobertura_intereses is not None and cobertura_intereses >= 2.5:
        st.warning(f"{t_cob_t} Cobertura de Intereses: {cobertura_intereses:.2f}x (Aceptable)")
    else:
        st.info(f"{t_cob_t} Cobertura de Intereses: Balance sin deuda neta o gasto por intereses nulo")

    if deuda_fcf != -1:
        st.info(f"{t_info} Deuda Total / FCF: {deuda_fcf:.2f} años de flujo libre para extinguir la deuda íntegra")[span_188](start_span)[span_188](end_span)
    if deuda_equity == 0.0: 
        st.warning(f"{t_info} Deuda/Capital: 0.00% (Posible Patrimonio Negativo por recompras masivas)")[span_189](start_span)[span_189](end_span)
    elif 0 < deuda_equity <= 50: 
        st.success(f"{t_info} Deuda/Capital: {deuda_equity:.2f}% (Balance sano)")[span_190](start_span)[span_190](end_span)
    else: 
        st.error(f"{t_info} Deuda/Capital: {deuda_equity:.2f}% (Apalancamiento elevado)")[span_191](start_span)[span_191](end_span)

    if current_ratio > 0:
        if current_ratio >= 1.5: st.success(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Caja solvente)")[span_192](start_span)[span_192](end_span)
        elif current_ratio >= 1.0: st.warning(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Justa)")[span_193](start_span)[span_193](end_span)
        else: st.error(f"{t_info} Liquidez (Current Ratio): {current_ratio:.2f} (Falta de liquidez a corto plazo)")[span_194](start_span)[span_194](end_span)

    if cond_recompras or cond_bpa_pos:
        txt_mot = f"Recompras netas ({variacion_acciones:+.2f}%)" if cond_recompras else f"Crecimiento BPA 3Y ({crecimiento_bpa_3y:+.2f}%)"
        st.success(f"{t_cap_t} Asignación de Capital: Cumplido vía {txt_mot}")
    else:
        st.error(f"{t_cap_t} Asignación de Capital: Sin recompras netas y con BPA estancado a 3 años")

    st.markdown("#### 🛡️ 4. Resiliencia, Historial y Foso Económico")
    if cond_roic and cond_rev:
        st.success(f"{t_foso_t} Foso Económico: ROIC ({roic:.1f}%) y Ventas 3A ({revenue_cagr_3y:+.1f}%) positivos y robustos")
    elif cond_roic or cond_rev:
        st.warning(f"{t_foso_t} Foso Económico Parcial: Uno de los dos filtros (ROIC o Ventas) requiere seguimiento")
    else:
        st.error(f"{t_foso_t} Foso Económico Débil: ROIC bajo y ventas estancadas")

    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: 
        txt_fatiga_hist = " (Alerta: se detecta fatiga en la última subida)" if fatiga_dividendo else ""
        st.success(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes{txt_fatiga_hist}")
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: 
        st.warning(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes")
    elif racha_sin_recortes >= 5: 
        st.warning(f"{t_hist} Historial y Resiliencia: {racha_sin_recortes} años consecutivos sin recortes")
    else: 
        st.error(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años (Insuficiente)")[span_195](start_span)[span_195](end_span)

    if dgr_5y is not None and dgr_5y >= 5.0: 
        st.success(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Bate la inflación histórica con holgura ≥ 5.0%)")
    elif dgr_5y is not None and dgr_5y >= 2.5: 
        st.warning(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Crecimiento moderado ≥ 2.5%)")
    else: 
        st.error(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y if dgr_5y is not None else 'N/D'}% (Estancado o inferior a 2.5%)")

    if incrementos_dividendo >= min(5, años_analisis): 
        st.info(f"{t_info} Frecuencia de Subidas: El dividendo ha aumentado {incrementos_dividendo} veces en {años_analisis} años")[span_196](start_span)[span_196](end_span)
    if total_años_bpa_datos > 0:
        ratio_bpa = años_crecimiento_bpa / total_años_bpa_datos[span_197](start_span)[span_197](end_span)
        if ratio_bpa >= 0.65: st.success(f"{t_info} Consistencia BPA (Proxy Yahoo): Crecimiento neto positivo en {años_crecimiento_bpa} de {total_años_bpa_datos} años analizados")[span_198](start_span)[span_198](end_span)
        else: st.warning(f"{t_info} Consistencia BPA (Proxy Yahoo): Crecimiento en {años_crecimiento_bpa} de {total_años_bpa_datos} años evaluados")[span_199](start_span)[span_199](end_span)

    if dgr_periodo is not None:
        st.info(f"{t_info} Crecimiento DGR {años_analisis}A (Largo Plazo): {dgr_periodo:.2f}% anual compuesto")[span_200](start_span)[span_200](end_span)

    st.markdown("#### 🏢 5. Fortaleza Institucional")[span_201](start_span)[span_201](end_span)
    if market_cap > 10_000_000_000: st.success(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Gran capitalización institucional)")[span_202](start_span)[span_202](end_span)
    else: st.error(f"{t_info} Tamaño: {market_cap / 1e9:.2f} mil millones de {sym} (Capitalización pequeña)")[span_203](start_span)[span_203](end_span)

    # ==========================================
    # PANEL: LOS 8 GRÁFICOS FINANCIEROS COMPLETOS[span_204](start_span)[span_204](end_span)
    # ==========================================
    st.divider()[span_205](start_span)[span_205](end_span)
    st.markdown("### 📉 Análisis Fundamental Visual")[span_206](start_span)[span_206](end_span)
    
    try:
        df_cashflow = ticker.cashflow[span_207](start_span)[span_207](end_span)
        df_financials = ticker.financials[span_208](start_span)[span_208](end_span)
        df_balance = ticker.balance_sheet[span_209](start_span)[span_209](end_span)
        
        def get_annual_series(df, col_names):
            if df is not None and not df.empty:
                for col in col_names:
                    if col in df.index:
                        s = df.loc[col].dropna()
                        if not s.empty:
                            s.index = pd.to_datetime(s.index).year
                            return s.sort_index()
            return pd.Series(dtype=float)[span_210](start_span)[span_210](end_span)

        fcf_s = get_annual_series(df_cashflow, ['Free Cash Flow'])[span_211](start_span)[span_211](end_span)
        div_s = abs(get_annual_series(df_cashflow, ['Cash Dividends Paid', 'Dividends Paid']))[span_212](start_span)[span_212](end_span)
        rev_s = get_annual_series(df_financials, ['Total Revenue', 'Operating Revenue'])[span_213](start_span)[span_213](end_span)
        net_s = get_annual_series(df_financials, ['Net Income', 'Net Income Common Stockholders'])[span_214](start_span)[span_214](end_span)
        debt_s = get_annual_series(df_balance, ['Total Debt'])[span_215](start_span)[span_215](end_span)
        cash_s = get_annual_series(df_balance, ['Cash And Cash Equivalents', 'Cash'])[span_216](start_span)[span_216](end_span)
        shares_s = get_annual_series(df_financials, ['Diluted Average Shares', 'Basic Average Shares'])[span_217](start_span)[span_217](end_span)
        ebitda_s = get_annual_series(df_financials, ['EBITDA', 'Normalized EBITDA'])[span_218](start_span)[span_218](end_span)
        
        yearly_closes = historial_completo['Close'].resample('YE').last()[span_219](start_span)[span_219](end_span)
        yearly_closes.index = yearly_closes.index.year[span_220](start_span)[span_220](end_span)

        col_graf1, col_graf2 = st.columns(2)[span_221](start_span)[span_221](end_span)

        # 1. Gráfico de Yield Limpio[span_222](start_span)[span_222](end_span)
        with col_graf1:
            st.markdown("#### 📈 Evolución del Yield Histórico")[span_223](start_span)[span_223](end_span)
            df_yield_chart = yields_validos.copy()[span_224](start_span)[span_224](end_span)
            fig_yield = go.Figure()[span_225](start_span)[span_225](end_span)
            fig_yield.add_trace(go.Scatter(x=df_yield_chart.index, y=df_yield_chart.values, mode='lines', line=dict(color='#00d4ff', width=2), name='Histórico', showlegend=False))[span_226](start_span)[span_226](end_span)
            fig_yield.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b")[span_227](start_span)[span_227](end_span)
            fig_yield.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354")[span_228](start_span)[span_228](end_span)
            fig_yield.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b")[span_229](start_span)[span_229](end_span)
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Techo: {yield_sobrevalorado:.2f}%"))[span_230](start_span)[span_230](end_span)
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {yield_medio:.2f}%"))[span_231](start_span)[span_231](end_span)
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Suelo: {yield_infravalorado:.2f}%"))[span_232](start_span)[span_232](end_span)
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[-1]], y=[df_yield_chart.iloc[-1]], mode='markers', marker=dict(color='#00d4ff', size=10, symbol='diamond'), name=f"Actual: {yield_actual:.2f}%"))[span_233](start_span)[span_233](end_span)
            fig_yield.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Rentabilidad (Yield %)", tickformat=".2f"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_234](start_span)[span_234](end_span)
            fig_yield.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])[span_235](start_span)[span_235](end_span)
            st.plotly_chart(fig_yield, use_container_width=True)[span_236](start_span)[span_236](end_span)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Muestra la rentabilidad por dividendo a lo largo del tiempo. Las caídas bruscas del precio provocan picos en el Yield (tocando la línea verde inferior), señalando las mejores oportunidades históricas de compra.</p>", unsafe_allow_html=True)[span_237](start_span)[span_237](end_span)

        # 2. Drawdown Histórico[span_238](start_span)[span_238](end_span)
        with col_graf2:
            st.markdown("#### 📉 Drawdown Histórico")[span_239](start_span)[span_239](end_span)
            df_dd = historial_analisis[['Close']].copy()[span_240](start_span)[span_240](end_span)
            df_dd['Max'] = df_dd['Close'].cummax()[span_241](start_span)[span_241](end_span)
            df_dd['Drawdown'] = (df_dd['Close'] - df_dd['Max']) / df_dd['Max'] * 100[span_242](start_span)[span_242](end_span)
            fig_dd = go.Figure()[span_243](start_span)[span_243](end_span)
            fig_dd.add_trace(go.Scatter(x=df_dd.index, y=df_dd['Drawdown'], fill='tozeroy', mode='lines', line=dict(color='#ff4b4b', width=1.5), fillcolor='rgba(255, 75, 75, 0.2)', name='Drawdown %'))[span_244](start_span)[span_244](end_span)
            fig_dd.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Caída desde Máximos (%)", tickformat=".1f", ticksuffix="%"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')[span_245](start_span)[span_245](end_span)
            st.plotly_chart(fig_dd, use_container_width=True)[span_246](start_span)[span_246](end_span)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Mide la caída porcentual de la acción desde su último máximo histórico. Es la mejor forma de evaluar la volatilidad real de la empresa y detectar correcciones de mercado severas.</p>", unsafe_allow_html=True)[span_247](start_span)[span_247](end_span)

        # 1.5. YIELD ON COST HISTÓRICO CON SUPERPOSICIÓN[span_248](start_span)[span_248](end_span)
        st.markdown("---")[span_249](start_span)[span_249](end_span)
        st.markdown("#### ⏳ Yield on Cost Histórico")[span_250](start_span)[span_250](end_span)
        st.markdown(f"> **Yield on Cost (YoC):** Muestra el Yield Actual ({yield_actual:.2f}%) que tendrías hoy si hubieras comprado la acción en cualquier fecha del pasado. Calculado dividiendo el dividendo actual ({forward_dividend / divisor_uk:.2f}{sym}) entre el precio histórico de cada día.")[span_251](start_span)[span_251](end_span)
        
        if not historial_analisis.empty and forward_dividend > 0:
            df_yoc_hist = historial_analisis[['Close', 'Yield_Diario']].copy()[span_252](start_span)[span_252](end_span)
            df_yoc_hist = df_yoc_hist.dropna(subset=['Close', 'Yield_Diario'])[span_253](start_span)[span_253](end_span)
            df_yoc_hist['Close_Div'] = df_yoc_hist['Close'] / divisor_uk if currency == 'GBp' else df_yoc_hist['Close'][span_254](start_span)[span_254](end_span)
            df_yoc_hist['YoC_Hist'] = (forward_dividend / df_yoc_hist['Close_Div']) * 100[span_255](start_span)[span_255](end_span)
            df_yoc_hist.replace([np.inf, -np.inf], np.nan, inplace=True)[span_256](start_span)[span_256](end_span)
            df_yoc_hist = df_yoc_hist.dropna(subset=['YoC_Hist'])[span_257](start_span)[span_257](end_span)
            
            fig_yoc_hist = go.Figure()[span_258](start_span)[span_258](end_span)
            fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['Yield_Diario'], mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1.5), name='Yield Histórico (En su día)'))[span_259](start_span)[span_259](end_span)
            fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['YoC_Hist'], mode='lines', line=dict(color='#faca2b', width=2), name='Yield on Cost (Hoy)'))[span_260](start_span)[span_260](end_span)
            fig_yoc_hist.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b", opacity=0.6)[span_261](start_span)[span_261](end_span)
            fig_yoc_hist.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354", opacity=0.6)[span_262](start_span)[span_262](end_span)
            fig_yoc_hist.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b", opacity=0.6)[span_263](start_span)[span_263](end_span)

            primera_fecha = df_yoc_hist.index[0][span_264](start_span)[span_264](end_span)
            fig_yoc_hist.add_trace(go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Techo: {yield_sobrevalorado:.2f}%"))[span_265](start_span)[span_265](end_span)
            fig_yoc_hist.add_trace(go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {yield_medio:.2f}%"))[span_266](start_span)[span_266](end_span)
            fig_yoc_hist.add_trace(go.Scatter(x=[primera_fecha], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Suelo: {yield_infravalorado:.2f}%"))[span_267](start_span)[span_267](end_span)
            fig_yoc_hist.add_hline(y=yield_actual, line_dash="dash", line_color="#00d4ff")[span_268](start_span)[span_268](end_span)
            fig_yoc_hist.add_annotation(x=df_yoc_hist.index[-1], y=yield_actual, text=f"Yield Hoy: {yield_actual:.2f}%", showarrow=False, yshift=15, font=dict(color="#00d4ff", size=11, weight="bold"), xanchor="right")[span_269](start_span)[span_269](end_span)

            fig_yoc_hist.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=50), height=400, yaxis=dict(title="Rentabilidad (%)", tickformat=".2f"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))[span_270](start_span)[span_270](end_span)
            fig_yoc_hist.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])[span_271](start_span)[span_271](end_span)
            st.plotly_chart(fig_yoc_hist, use_container_width=True)[span_272](start_span)[span_272](end_span)
        else:
            st.info("Datos insuficientes para calcular el Yield on Cost histórico.")[span_273](start_span)[span_273](end_span)

        # 3. Sostenibilidad FCF vs Dividendos[span_274](start_span)[span_274](end_span)
        st.markdown("---")[span_275](start_span)[span_275](end_span)
        col_graf3, col_graf4 = st.columns(2)[span_276](start_span)[span_276](end_span)
        with col_graf3:
            st.markdown("#### 💵 Sostenibilidad: FCF vs Dividendos")[span_277](start_span)[span_277](end_span)
            years_sost = sorted(list(set(fcf_s.index) & set(div_s.index)))[span_278](start_span)[span_278](end_span)
            if years_sost:
                x_years = [str(y) for y in years_sost][span_279](start_span)[span_279](end_span)
                fcf_vals = [fcf_s[y] for y in years_sost][span_280](start_span)[span_280](end_span)
                div_vals = [div_s[y] for y in years_sost][span_281](start_span)[span_281](end_span)
                payout_vals = [(div/fcf)*100 if fcf > 0 else 0 for fcf, div in zip(fcf_vals, div_vals)][span_282](start_span)[span_282](end_span)
                fig_sost = make_subplots(specs=[[{"secondary_y": True}]])[span_283](start_span)[span_283](end_span)
                fig_sost.add_trace(go.Bar(x=x_years, y=fcf_vals, name='FCF', marker_color='#00d4ff'), secondary_y=False)[span_284](start_span)[span_284](end_span)
                fig_sost.add_trace(go.Bar(x=x_years, y=div_vals, name='Dividendos', marker_color='#ff9800'), secondary_y=False)[span_285](start_span)[span_285](end_span)
                fig_sost.add_trace(go.Scatter(x=x_years, y=payout_vals, name='Payout FCF %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in payout_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff4b4b', width=2), marker=dict(size=8)), secondary_y=True)[span_286](start_span)[span_286](end_span)
                fig_sost.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_287](start_span)[span_287](end_span)
                fig_sost.update_yaxes(title_text="Absoluto", secondary_y=False)[span_288](start_span)[span_288](end_span)
                fig_sost.update_yaxes(title_text="Payout %", secondary_y=True, showgrid=False, range=[0, max(payout_vals)*1.2 if payout_vals else 100])[span_289](start_span)[span_289](end_span)
                st.plotly_chart(fig_sost, use_container_width=True)[span_290](start_span)[span_290](end_span)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Compara el dinero real contante y sonante que entra en la caja (FCF, azul) frente al dinero que sale para pagar los dividendos (Naranja). La línea roja debe mantenerse por debajo del 60-70% para garantizar que el dividendo es seguro a futuro.</p>", unsafe_allow_html=True)[span_291](start_span)[span_291](end_span)
            else: st.info("Datos anuales insuficientes para el gráfico de Sostenibilidad.")[span_292](start_span)[span_292](end_span)

        # 4. Ingresos vs Beneficio Neto[span_293](start_span)[span_293](end_span)
        with col_graf4:
            st.markdown("#### 📊 Ingresos vs Beneficio Neto")[span_294](start_span)[span_294](end_span)
            years_rev = sorted(list(set(rev_s.index) & set(net_s.index)))[span_295](start_span)[span_295](end_span)
            if years_rev:
                x_years_rev = [str(y) for y in years_rev][span_296](start_span)[span_296](end_span)
                rev_vals = [rev_s[y] for y in years_rev][span_297](start_span)[span_297](end_span)
                net_vals = [net_s[y] for y in years_rev][span_298](start_span)[span_298](end_span)
                margin_vals = [(n/r)*100 if r > 0 else 0 for r, n in zip(rev_vals, net_vals)][span_299](start_span)[span_299](end_span)
                fig_ing = make_subplots(specs=[[{"secondary_y": True}]])[span_300](start_span)[span_300](end_span)
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=rev_vals, name='Ingresos', marker_color='#21c354'), secondary_y=False)[span_301](start_span)[span_301](end_span)
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=net_vals, name='B. Neto', marker_color='#faca2b'), secondary_y=False)[span_302](start_span)[span_302](end_span)
                fig_ing.add_trace(go.Scatter(x=x_years_rev, y=margin_vals, name='Margen Neto %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in margin_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#00d4ff', width=2), marker=dict(size=8)), secondary_y=True)[span_303](start_span)[span_303](end_span)
                fig_ing.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_304](start_span)[span_304](end_span)
                fig_ing.update_yaxes(title_text="Absoluto", secondary_y=False)[span_305](start_span)[span_305](end_span)
                fig_ing.update_yaxes(title_text="Margen %", secondary_y=True, showgrid=False, range=[0, max(margin_vals)*1.2 if margin_vals else 100])[span_306](start_span)[span_306](end_span)
                st.plotly_chart(fig_ing, use_container_width=True)[span_307](start_span)[span_307](end_span)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Evalúa el crecimiento del negocio. Barras verdes indican que la empresa vende más. La línea azul mide el Margen Neto: qué porcentaje de esas ventas se convierte en ganancias puras. Crecimiento de ingresos con márgenes estables o al alza indica una ventaja competitiva fuerte.</p>", unsafe_allow_html=True)[span_308](start_span)[span_308](end_span)
            else: st.info("Datos anuales insuficientes para el gráfico de Ingresos.")[span_309](start_span)[span_309](end_span)

        # 5. EV/FCF y EV/EBITDA[span_310](start_span)[span_310](end_span)
        col_graf5, col_graf6 = st.columns(2)[span_311](start_span)[span_311](end_span)
        with col_graf5:
            st.markdown("#### ⚖️ Valoración Múltiplo: EV / FCF")[span_312](start_span)[span_312](end_span)
            years_ev = sorted(list(set(fcf_s.index) & set(shares_s.index) & set(yearly_closes.index)))[span_313](start_span)[span_313](end_span)
            if years_ev:
                x_years_ev = [str(y) for y in years_ev][span_314](start_span)[span_314](end_span)
                fcf_ev_vals = [fcf_s[y] for y in years_ev][span_315](start_span)[span_315](end_span)
                ev_vals = [yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0) for y in years_ev][span_316](start_span)[span_316](end_span)
                ratio_vals = [(ev/fcf) if fcf > 0 else 0 for ev, fcf in zip(ev_vals, fcf_ev_vals)][span_317](start_span)[span_317](end_span)
                fig_ev = make_subplots(specs=[[{"secondary_y": True}]])[span_318](start_span)[span_318](end_span)
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=ev_vals, name='Enterprise Value (EV)', marker_color='#9c27b0'), secondary_y=False)[span_319](start_span)[span_319](end_span)
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=fcf_ev_vals, name='FCF', marker_color='#00d4ff'), secondary_y=False)[span_320](start_span)[span_320](end_span)
                fig_ev.add_trace(go.Scatter(x=x_years_ev, y=ratio_vals, name='Ratio EV/FCF', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#21c354', width=2), marker=dict(size=8)), secondary_y=True)[span_321](start_span)[span_321](end_span)
                fig_ev.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_322](start_span)[span_322](end_span)
                fig_ev.update_yaxes(title_text="Absoluto", secondary_y=False)[span_323](start_span)[span_323](end_span)
                fig_ev.update_yaxes(title_text="Ratio (Múltiplo)", secondary_y=True, showgrid=False, range=[0, max(ratio_vals)*1.2 if ratio_vals else 30])[span_324](start_span)[span_324](end_span)
                st.plotly_chart(fig_ev, use_container_width=True)[span_325](start_span)[span_325](end_span)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Calcula cuántas veces está valorada la empresa (sumando su deuda y restando su liquidez) respecto a su Flujo de Caja. Es mucho más preciso que el PER porque incluye la deuda real. Un ratio por debajo de 15x-20x suele indicar infravaloración.</p>", unsafe_allow_html=True)[span_326](start_span)[span_326](end_span)
            else: st.info("Datos insuficientes para el gráfico EV/FCF.")[span_327](start_span)[span_327](end_span)

        with col_graf6:
            st.markdown("#### 🏢 Múltiplo Operativo: EV / EBITDA")[span_328](start_span)[span_328](end_span)
            years_ebitda = sorted(list(set(ebitda_s.index) & set(shares_s.index) & set(yearly_closes.index)))[span_329](start_span)[span_329](end_span)
            if years_ebitda:
                x_years_eb = [str(y) for y in years_ebitda][span_330](start_span)[span_330](end_span)
                ebitda_vals = [ebitda_s[y] for y in years_ebitda][span_331](start_span)[span_331](end_span)
                ev_eb_vals = [yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0) for y in years_ebitda][span_332](start_span)[span_332](end_span)
                ratio_eb_vals = [(ev/eb) if eb > 0 else 0 for ev, eb in zip(ev_eb_vals, ebitda_vals)][span_333](start_span)[span_333](end_span)
                fig_ebitda = make_subplots(specs=[[{"secondary_y": True}]])[span_334](start_span)[span_334](end_span)
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ebitda_vals, name='EBITDA', marker_color='#0288d1'), secondary_y=False)[span_335](start_span)[span_335](end_span)
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ev_eb_vals, name='Enterprise Value (EV)', marker_color='#ff9800'), secondary_y=False)[span_336](start_span)[span_336](end_span)
                fig_ebitda.add_trace(go.Scatter(x=x_years_eb, y=ratio_eb_vals, name='Ratio EV/EBITDA', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_eb_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff1744', width=2), marker=dict(size=8)), secondary_y=True)[span_337](start_span)[span_337](end_span)
                fig_ebitda.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_338](start_span)[span_338](end_span)
                fig_ebitda.update_yaxes(title_text="Absoluto", secondary_y=False)[span_339](start_span)[span_339](end_span)
                fig_ebitda.update_yaxes(title_text="Ratio (Múltiplo)", secondary_y=True, showgrid=False, range=[0, max(ratio_eb_vals)*1.2 if ratio_eb_vals else 30])[span_340](start_span)[span_340](end_span)
                st.plotly_chart(fig_ebitda, use_container_width=True)[span_341](start_span)[span_341](end_span)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>El múltiplo clásico de las adquisiciones corporativas. Compara el Valor de la Empresa con sus beneficios antes de intereses, impuestos, depreciaciones y amortizaciones. Permite medir si la empresa cotiza cara o barata ignorando temporalmente su estructura fiscal y contable.</p>", unsafe_allow_html=True)[span_342](start_span)[span_342](end_span)
            else: st.info("Datos insuficientes para el gráfico EV/EBITDA.")[span_343](start_span)[span_343](end_span)

        # 7. DEUDA NETA / FCF[span_344](start_span)[span_344](end_span)
        st.markdown("#### 🛡️ Solvencia: Deuda Neta vs FCF")[span_345](start_span)[span_345](end_span)
        years_debt = sorted(list(set(fcf_s.index) & set(debt_s.index)))[span_346](start_span)[span_346](end_span)
        if years_debt:
            x_years_d = [str(y) for y in years_debt][span_347](start_span)[span_347](end_span)
            fcf_d_vals = [fcf_s[y] for y in years_debt][span_348](start_span)[span_348](end_span)
            net_debt_vals = [max(0, debt_s.get(y, 0) - cash_s.get(y, 0)) for y in years_debt][span_349](start_span)[span_349](end_span)
            ratio_d_vals = [(nd/fcf) if fcf > 0 else 0 for nd, fcf in zip(net_debt_vals, fcf_d_vals)][span_350](start_span)[span_350](end_span)
            fig_deuda = make_subplots(specs=[[{"secondary_y": True}]])[span_351](start_span)[span_351](end_span)
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=fcf_d_vals, name='Flujo Caja Libre (FCF)', marker_color='#0288d1'), secondary_y=False)[span_352](start_span)[span_352](end_span)
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=net_debt_vals, name='Deuda Neta', marker_color='#ff9800'), secondary_y=False)[span_353](start_span)[span_353](end_span)
            fig_deuda.add_trace(go.Scatter(x=x_years_d, y=ratio_d_vals, name='Deuda Neta / FCF', mode='lines+markers+text', text=[f"{val:.2f}x" for val in ratio_d_vals], textposition="top center", textfont=dict(color="white", size=11, weight="bold"), line=dict(color='#ff1744', width=2), marker=dict(size=8)), secondary_y=True)[span_354](start_span)[span_354](end_span)
            fig_deuda.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))[span_355](start_span)[span_355](end_span)
            fig_deuda.update_yaxes(title_text="Absoluto", secondary_y=False)[span_356](start_span)[span_356](end_span)
            fig_deuda.update_yaxes(title_text="Años para Pagar", secondary_y=True, showgrid=False, range=[0, max(ratio_d_vals)*1.2 if ratio_d_vals else 5])[span_357](start_span)[span_357](end_span)
            st.plotly_chart(fig_deuda, use_container_width=True)[span_358](start_span)[span_358](end_span)
            st.markdown("<p style='font-size:0.85rem; color:#aaa;'>La métrica definitiva de tranquilidad. Muestra cuántos años completos necesitaría la empresa, usando todo el efectivo libre anual que genera, para dejar su Deuda Neta a cero. Un valor inferior a 3.0 años demuestra un balance blindado frente a crisis económicas.</p>", unsafe_allow_html=True)[span_359](start_span)[span_359](end_span)
        else: st.info("Datos insuficientes para el gráfico de Deuda.")[span_360](start_span)[span_360](end_span)

        # 8. PERFIL DE DEUDA Y LIQUIDEZ (CORTO VS LARGO)[span_361](start_span)[span_361](end_span)
        st.markdown("#### ⏳ Estructura de Deuda Actual (Corto vs Largo Plazo)")[span_362](start_span)[span_362](end_span)
        if df_balance is not None and not df_balance.empty:
            bs_cols = df_balance.index.tolist()[span_363](start_span)[span_363](end_span)
            def get_latest_bs_val(keys):
                for k in keys:
                    if k in bs_cols:
                        s = df_balance.loc[k].dropna()[span_364](start_span)[span_364](end_span)
                        if not s.empty: return s.iloc[0][span_365](start_span)[span_365](end_span)
                return 0.0[span_366](start_span)[span_366](end_span)

            st_debt = get_latest_bs_val(['Current Debt', 'Short Long Term Debt', 'Short Term Debt'])[span_367](start_span)[span_367](end_span)
            lt_debt = get_latest_bs_val(['Long Term Debt'])[span_368](start_span)[span_368](end_span)
            caja_actual = get_latest_bs_val(['Cash And Cash Equivalents', 'Cash', 'Total Cash'])[span_369](start_span)[span_369](end_span)
            
            if st_debt > 0 or lt_debt > 0 or caja_actual > 0:
                fig_venc = go.Figure()[span_370](start_span)[span_370](end_span)
                fig_venc.add_trace(go.Bar(y=['Estructura Actual'], x=[caja_actual], name='Liquidez (Caja y Equivalentes)', orientation='h', marker_color='#21c354', text=f"{caja_actual/1e9:.2f}B {sym}", textposition='inside'))[span_371](start_span)[span_371](end_span)
                fig_venc.add_trace(go.Bar(y=['Estructura Actual'], x=[st_debt], name='Deuda Corto Plazo (< 1 Año)', orientation='h', marker_color='#ff9800', text=f"{st_debt/1e9:.2f}B {sym}", textposition='inside'))[span_372](start_span)[span_372](end_span)
                fig_venc.add_trace(go.Bar(y=['Estructura Actual'], x=[lt_debt], name='Deuda Largo Plazo (> 1 Año)', orientation='h', marker_color='#ff4b4b', text=f"{lt_debt/1e9:.2f}B {sym}", textposition='inside'))[span_373](start_span)[span_373](end_span)
                fig_venc.update_layout(barmode='stack', template='plotly_dark', margin=dict(l=0, r=0, t=30, b=80), height=250, hovermode="y unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.5, xanchor="center", x=0.5), xaxis=dict(showticklabels=False, title=""))[span_374](start_span)[span_374](end_span)
                st.plotly_chart(fig_venc, use_container_width=True)[span_375](start_span)[span_375](end_span)
                st.markdown("<p style='font-size:0.85rem; color:#aaa;'>Muestra la liquidez inmediata frente a los vencimientos de deuda. La deuda a corto plazo (naranja) es la que vence en menos de 12 meses. Lo ideal es que la barra verde (Caja) sea superior a la barra naranja, indicando que la empresa no necesita emitir nueva deuda cara para pagar la que vence este año.</p>", unsafe_allow_html=True)[span_376](start_span)[span_376](end_span)
            else:
                st.info("No hay desglose de deuda a corto/largo plazo en Yahoo Finance para esta empresa.")[span_377](start_span)[span_377](end_span)

    except Exception as e:
        st.warning(f"No se han podido cargar los gráficos financieros anuales completos de Yahoo Finance. Error: {e}")[span_378](start_span)[span_378](end_span)

    # ==========================================
    # PROYECCIÓN YIELD ON COST A 15 AÑOS[span_379](start_span)[span_379](end_span)
    # ==========================================
    st.divider()[span_380](start_span)[span_380](end_span)
    st.markdown("#### 🔮 Proyección de Rentabilidad sobre Coste (Yield on Cost a 15 Años)")[span_381](start_span)[span_381](end_span)
    
    val_5y = dgr_5y if dgr_5y is not None else None[span_382](start_span)[span_382](end_span)
    val_periodo = dgr_periodo if dgr_periodo is not None else None[span_383](start_span)[span_383](end_span)

    if val_5y is not None and val_periodo is not None:
        dgr_proyeccion = min(val_5y, val_periodo)[span_384](start_span)[span_384](end_span)
        txt_ritmo = "Ritmo Conservador (5A)" if dgr_proyeccion == val_5y else f"Ritmo Conservador ({años_analisis}A)[span_385](start_span)"[span_385](end_span)
    elif val_5y is not None:
        dgr_proyeccion = val_5y[span_386](start_span)[span_386](end_span)
        txt_ritmo = "Ritmo Disponible (5A)[span_387](start_span)"[span_387](end_span)
    elif val_periodo is not None:
        dgr_proyeccion = val_periodo[span_388](start_span)[span_388](end_span)
        txt_ritmo = f"Ritmo Disponible ({años_analisis}A)[span_389](start_span)"[span_389](end_span)
    else:
        dgr_proyeccion = 0.0[span_390](start_span)[span_390](end_span)
        txt_ritmo = "Crecimiento Nulo / Estancado[span_391](start_span)"[span_391](end_span)
    
    dgr_proyeccion = min(dgr_proyeccion, 15.0)[span_392](start_span)[span_392](end_span)
    años_proyeccion = list(range(1, 16))[span_393](start_span)[span_393](end_span)
    
    div_bruto_proyectado = [forward_dividend * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion][span_394](start_span)[span_394](end_span)
    yoc_bruto_lista = [yield_actual * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion][span_395](start_span)[span_395](end_span)
    yoc_neto_lista = [bruto * net_mult for bruto in yoc_bruto_lista][span_396](start_span)[span_396](end_span)
    
    x_labels_yoc = [][span_397](start_span)[span_397](end_span)
    for año, yoc_n in zip(años_proyeccion, yoc_neto_lista):
        año_futuro = año_actual + año[span_398](start_span)[span_398](end_span)
        x_labels_yoc.append(f"{año_futuro}<br><span style='color:#faca2b; font-size:12px'>{yoc_n:.1f}%</span>")[span_399](start_span)[span_399](end_span)

    color_barras = '#00d4ff' if dgr_proyeccion >= 0 else '#ff4b4b[span_400](start_span)'[span_400](end_span)
    color_linea = '#21c354' if dgr_proyeccion >= 0 else '#ff4b4b[span_401](start_span)'[span_401](end_span)
    signo_dgr = "+" if dgr_proyeccion > 0 else "[span_402](start_span)"[span_402](end_span)

    st.markdown(f"> **Cálculo de la proyección:** Basado en {txt_ritmo} con un <span style='color:{color_linea};'>**{signo_dgr}{dgr_proyeccion:.1f}% anual constante**</span>.", unsafe_allow_html=True)[span_403](start_span)[span_403](end_span)

    fig_yoc_p = go.Figure()[span_404](start_span)[span_404](end_span)
    fig_yoc_p.add_trace(go.Bar(x=x_labels_yoc, y=div_bruto_proyectado, name=f'Div. Esperado ({sym})', marker_color=color_barras, yaxis='y1', text=[f"{val:.2f}{sym}" for val in div_bruto_proyectado], textposition='auto'))[span_405](start_span)[span_405](end_span)
    fig_yoc_p.add_trace(go.Scatter(x=x_labels_yoc, y=yoc_neto_lista, name="YoC Neto (%)", mode='lines+markers', line=dict(color=color_linea, width=3), marker=dict(size=8), yaxis='y2'))[span_406](start_span)[span_406](end_span)
    fig_yoc_p.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=40), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color=color_barras)), tickfont=dict(color=color_barras)), yaxis2=dict(title=dict(text="YoC Neto (%)", font=dict(color="#faca2b")), tickfont=dict(color="#faca2b"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))[span_407](start_span)[span_407](end_span)
    st.plotly_chart(fig_yoc_p, use_container_width=True)[span_408](start_span)[span_408](end_span)

# ==========================================
# INTERFAZ DIRECTA DE LA PÁGINA
# ==========================================
st.title("🔍 Análisis Individual — Geraldine Weiss DGI")[span_409](start_span)[span_409](end_span)

col_input1, col_input2, col_input3 = st.columns(3)[span_410](start_span)[span_410](end_span)
with col_input1: 
    ticker_input = st.text_input("Ticker individual:", "MKC").upper()[span_411](start_span)[span_411](end_span)
with col_input2: 
    años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)[span_412](start_span)[span_412](end_span)
with col_input3: 
    impuesto = st.number_input("Retención (%)", value=19.0, key="imp_ind")[span_413](start_span)[span_413](end_span)

if st.button("🚀 Analizar Empresa", use_container_width=True):[span_414](start_span)[span_414](end_span)
    with st.spinner(f"Analizando {ticker_input} en profundidad..."):[span_415](start_span)[span_415](end_span)
        try:
            screener_weiss_definitivo(ticker_input, años_analisis, impuesto)[span_416](start_span)[span_416](end_span)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")[span_417](start_span)[span_417](end_span)
