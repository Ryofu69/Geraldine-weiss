import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Ignorar advertencias menores
warnings.filterwarnings('ignore')

TRADUCCION = {
    'Technology': 'Tecnología', 'Healthcare': 'Salud', 'Financial Services': 'Servicios Financieros',
    'Consumer Cyclical': 'Consumo Cíclico', 'Industrials': 'Industrial', 'Consumer Defensive': 'Consumo Defensivo',
    'Energy': 'Energía', 'Real Estate': 'Inmobiliario', 'Utilities': 'Servicios Públicos',
    'Basic Materials': 'Materiales Básicos', 'Communication Services': 'Servicios de Comunicación'
}

MERMA_ORIGEN_PAIS = {
    'Switzerland': 20.0, 'Denmark': 12.0, 'Germany': 11.375, 'France': 10.0, 'Ireland': 10.0
}

# ==========================================
# CACHÉ DE DOBLE VELOCIDAD (MERCADO ABIERTO)
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def cargar_fundamentales_pesados(ticker_symbol):
    t = yf.Ticker(ticker_symbol)
    info = t.info or {}
    divs = t.dividends
    
    inc_stmt, bs_stmt, cf_stmt = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        if t.income_stmt is not None and not t.income_stmt.empty:
            inc_stmt = t.income_stmt.T.sort_index().T
    except Exception: pass
    try:
        if t.balance_sheet is not None and not t.balance_sheet.empty:
            bs_stmt = t.balance_sheet.T.sort_index().T
    except Exception: pass
    try:
        if t.cashflow is not None and not t.cashflow.empty:
            cf_stmt = t.cashflow.T.sort_index().T
    except Exception: pass

    shares_hist = None
    try:
        shares_hist = t.get_shares_full(start="2004-01-01")
    except Exception: pass

    curr_cot = info.get('currency', 'USD')
    curr_Base = 'GBP' if curr_cot == 'GBp' else curr_cot
    curr_fin = info.get('financialCurrency', curr_Base) or curr_Base
    if curr_fin == 'GBp': curr_fin = 'GBP'

    fx_rate = 1.0
    if curr_fin != curr_Base:
        try:
            fx_pair = f"{curr_fin}{curr_Base}=X"
            fx_data = yf.Ticker(fx_pair).history(period="5d")
            if not fx_data.empty:
                fx_rate = float(fx_data['Close'].dropna().iloc[-1])
        except Exception:
            fx_rate = 1.0

    return info, divs, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin

@st.cache_data(ttl=15, show_spinner=False)
def cargar_cotizacion_tiempo_real(ticker_symbol):
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="max", auto_adjust=False)
    precio_vivo = None
    try:
        precio_vivo = float(t.fast_info.last_price)
    except Exception:
        pass
    return hist, precio_vivo

def interpolar_puntos(valor, umbral_max, umbral_med, pts_max, pts_med, inverso=False):
    if not inverso:
        if valor >= umbral_max: return pts_max
        if valor < umbral_med: return 0.0
        if umbral_max == umbral_med: return pts_max
        ratio = (valor - umbral_med) / (umbral_max - umbral_med)
        return round(pts_med + ratio * (pts_max - pts_med), 2)
    else:
        if valor <= 0: return 0.0
        if valor <= umbral_max: return pts_max
        if valor > umbral_med: return 0.0
        if umbral_med == umbral_max: return pts_max
        ratio = (umbral_med - valor) / (umbral_med - umbral_max)
        return round(pts_med + ratio * (pts_max - pts_med), 2)

# ==========================================
# FUNCIÓN PESTAÑA 1: VALORACIÓN, BOGLE Y TIMING
# ==========================================
def render_valoracion_bogle(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    info, dividendos_raw, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin = cargar_fundamentales_pesados(ticker_symbol)
    historial_raw, precio_vivo = cargar_cotizacion_tiempo_real(ticker_symbol)

    if dividendos_raw.empty or len(historial_raw) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None: return default
        try: return float(val)
        except (ValueError, TypeError): return default

    # --- ESTILOS CSS (CUADRÍCULA 2x2 EN MÓVIL + TERMÓMETRO + EXPLICACIONES) ---
    st.markdown("""
    <style>
    .grid-precios-weiss {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 16px;
    }
    @media (max-width: 768px) {
        .grid-precios-weiss {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    .card-precio {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 12px 14px;
        display: flex;
        flex-direction: column;
    }
    .card-dgi {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }
    .explicacion-graf {
        background: rgba(0, 212, 255, 0.05);
        border-left: 3px solid #00d4ff;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        font-size: 0.88rem;
        color: #d0d0d8;
        margin-top: -8px;
        margin-bottom: 18px;
        line-height: 1.45;
    }
    .badge-verde { background: rgba(33, 195, 84, 0.2); color: #21c354; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; }
    .badge-rojo { background: rgba(255, 75, 75, 0.2); color: #ff4b4b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; }
    .badge-ambar { background: rgba(250, 202, 43, 0.2); color: #faca2b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; }
    </style>
    """, unsafe_allow_html=True)

    # --- DIVISAS Y NORMALIZACIÓN ---
    currency_raw = info.get('currency', 'USD')
    es_peniques_uk = (currency_raw == 'GBp')
    currency = 'GBP' if es_peniques_uk else currency_raw
    sym = '€' if currency == 'EUR' else ('£' if currency == 'GBP' else '$')

    historial_completo = historial_raw.copy()
    dividendos = dividendos_raw.copy()

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    dividendos.index = dividendos.index.tz_localize(None).normalize()
    dividendos = dividendos.groupby(dividendos.index).sum()

    if precio_vivo is not None and precio_vivo > 0 and not historial_completo.empty:
        historial_completo.iloc[-1, historial_completo.columns.get_loc('Close')] = precio_vivo
        if precio_vivo > historial_completo['High'].iloc[-1]:
            historial_completo.iloc[-1, historial_completo.columns.get_loc('High')] = precio_vivo
        if precio_vivo < historial_completo['Low'].iloc[-1]:
            historial_completo.iloc[-1, historial_completo.columns.get_loc('Low')] = precio_vivo

    if es_peniques_uk:
        for col in ['Open', 'High', 'Low', 'Close']:
            if col in historial_completo.columns:
                historial_completo[col] = historial_completo[col] / 100.0
        if dividendos.median() > (historial_completo['Close'].median() * 0.25):
            dividendos = dividendos / 100.0

    ahora_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
    año_actual = ahora_madrid.year
    hoy_ts = pd.Timestamp.now().normalize()

    fecha_corte_analisis = hoy_ts - pd.DateOffset(years=años_analisis)
    historial_analisis = historial_completo[historial_completo.index >= fecha_corte_analisis].copy()

    if historial_analisis.empty:
        st.error(f"❌ Error: No se encontraron datos de cotización en los últimos {años_analisis} años.")
        return

    precio_actual = float(historial_analisis['Close'].dropna().iloc[-1])

    # --- DETECCIÓN SECTORIAL ---
    sector_en = info.get('sector', 'Desconocido')
    industry_en = info.get('industry', 'Desconocido')
    pais = info.get('country', 'Desconocido')
    nombre_empresa = info.get('shortName', ticker_symbol)
    
    sector_final = TRADUCCION.get(sector_en, sector_en)

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()

    merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
    net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

    # --- DIVIDENDOS ANUALES (1 ESCALÓN POR AÑO NATURAL) ---
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4
    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    ventana_med = max(4, pagos_por_año * 2)
    mediana_pagos = dividendos.rolling(window=ventana_med, min_periods=1).median()
    umbral_extra = mediana_pagos * 1.75
    aviso_extraordinario = bool((dividendos.tail(pagos_por_año * 2) > umbral_extra.tail(pagos_por_año * 2)).any())
    dividendos_regulares = dividendos.where(dividendos <= umbral_extra, mediana_pagos)

    suma_anual_reg = dividendos_regulares.groupby(dividendos_regulares.index.year).sum()
    conteo_anual_reg = dividendos_regulares.groupby(dividendos_regulares.index.year).count()
    divs_reg_por_año = suma_anual_reg.copy()

    for y in divs_reg_por_año.index:
        if y < año_actual and pagos_por_año in [2, 4, 12]:
            c = conteo_anual_reg.loc[y]
            if c > 0 and c != pagos_por_año and abs(c - pagos_por_año) == 1:
                divs_reg_por_año.loc[y] = (suma_anual_reg.loc[y] / c) * pagos_por_año

    forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    if es_peniques_uk and forward_dividend > (precio_actual * 0.25):
        forward_dividend /= 100.0

    if forward_dividend == 0 and not dividendos_regulares.empty:
        ultimo_año_completo = divs_reg_por_año.iloc[-2] if len(divs_reg_por_año) > 1 else 0
        forward_dividend = max(dividendos_regulares.iloc[-1] * pagos_por_año, ultimo_año_completo)

    historial_analisis['Year'] = historial_analisis.index.year
    historial_analisis['Div_Anual'] = historial_analisis['Year'].map(divs_reg_por_año)
    historial_analisis.loc[historial_analisis['Year'] == año_actual, 'Div_Anual'] = forward_dividend
    historial_analisis['Div_Anual'] = historial_analisis['Div_Anual'].bfill().ffill()

    historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
    historial_analisis.replace([np.inf, -np.inf], np.nan, inplace=True)

    yields_validos = historial_analisis['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]

    yield_infravalorado = float(yields_validos.quantile(0.95))
    yield_sobrevalorado = float(yields_validos.quantile(0.05))
    yield_medio = float(yields_validos.mean())
    yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0
    percentil_yield_actual = float((yields_validos < yield_actual).mean() * 100)

    # --- FUNDAMENTALES CON CONVERSIÓN FX ---
    payout_ratio = get_safe('payoutRatio') * 100
    per_actual = get_safe('trailingPE')
    per_forward = get_safe('forwardPE')
    per = per_actual if per_actual > 0 else per_forward
    deuda_equity = get_safe('debtToEquity')
    current_ratio = get_safe('currentRatio')
    price_to_book = get_safe('priceToBook', -1)
    roe = get_safe('returnOnEquity', 0.0) * 100
    operating_margins = get_safe('operatingMargins', 0.0) * 100

    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    total_cash = get_safe('totalCash', 0.0) * fx_rate
    ebitda = get_safe('ebitda', 0.0) * fx_rate
    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    shares = get_safe('sharesOutstanding', 0.0)

    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw

    total_equity_raw = get_safe('totalStockholderEquity', 0.0) * fx_rate
    if total_equity_raw == 0 and not bs_stmt.empty:
        for eq_k in ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity']:
            if eq_k in bs_stmt.index:
                s_eq = bs_stmt.loc[eq_k].dropna()
                if not s_eq.empty:
                    total_equity_raw = float(s_eq.iloc[-1]) * fx_rate
                    break

    es_quasi_reit_o_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 22.0) and (total_equity_raw <= 0 or price_to_book < 0 or deuda_equity == 0.0)
    es_regulada_o_reit = es_reit_puro or es_utility_pura or es_quasi_reit_o_recompras

    payout_limite_fcf = 85.0 if es_regulada_o_reit else 75.0
    payout_amarillo_fcf = 92.0 if es_regulada_o_reit else 85.0

    deuda_neta = max(0.0, total_debt - total_cash)
    deuda_ebitda = (deuda_neta / ebitda) if ebitda > 0 else (999.0 if (total_debt > 0 and not es_financiera) else 0.0)

    crecimiento_bpa_3y = None
    if not inc_stmt.empty:
        for key in ['Diluted EPS', 'Basic EPS']:
            if key in inc_stmt.index:
                eps_series = inc_stmt.loc[key].dropna()
                if len(eps_series) >= 4 and eps_series.iloc[-4] > 0 and eps_series.iloc[-1] > 0:
                    crecimiento_bpa_3y = (((eps_series.iloc[-1] / eps_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                break

    roic = None
    try:
        ebit_val = get_safe('operatingIncome') * fx_rate
        if ebit_val == 0 and not inc_stmt.empty:
            for k in ['Operating Income', 'EBIT']:
                if k in inc_stmt.index:
                    ebit_val = float(inc_stmt.loc[k].dropna().iloc[-1]) * fx_rate
                    break
        inv_cap = (total_debt + max(0.0, total_equity_raw)) - total_cash
        if inv_cap <= 0 and not bs_stmt.empty and 'Total Assets' in bs_stmt.index:
            tot_assets = float(bs_stmt.loc['Total Assets'].dropna().iloc[-1]) * fx_rate
            curr_liab = float(bs_stmt.loc['Current Liabilities'].dropna().iloc[-1]) * fx_rate if 'Current Liabilities' in bs_stmt.index else 0.0
            inv_cap = tot_assets - curr_liab - total_cash
        if inv_cap > 0 and ebit_val > 0:
            roic = ((ebit_val * 0.79) / inv_cap) * 100
    except Exception: pass

    revenue_cagr_3y = None
    if not inc_stmt.empty:
        for k in ['Total Revenue', 'Operating Revenue']:
            if k in inc_stmt.index:
                rev_series = inc_stmt.loc[k].dropna()
                if len(rev_series) >= 4 and rev_series.iloc[-4] > 0 and rev_series.iloc[-1] > 0:
                    revenue_cagr_3y = (((rev_series.iloc[-1] / rev_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                break

    cobertura_intereses = None
    if not inc_stmt.empty:
        try:
            ebit_cov, int_exp = None, None
            for k in ['Operating Income', 'EBIT']:
                if k in inc_stmt.index:
                    ebit_cov = float(inc_stmt.loc[k].dropna().iloc[-1])
                    break
            for k in ['Interest Expense', 'Interest Expense Non Operating']:
                if k in inc_stmt.index:
                    int_exp = abs(float(inc_stmt.loc[k].dropna().iloc[-1]))
                    break
            if ebit_cov is not None and int_exp is not None and int_exp > 0:
                cobertura_intereses = ebit_cov / int_exp
        except Exception: pass

    payout_fcf, p_fcf = -1, -1
    if flujo_caja_referencia != 0 and shares > 0:
        fcf_per_share = flujo_caja_referencia / shares
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share

    dividendos_barras = divs_reg_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    dgr_5y, dgr_periodo, dgr_1y = None, None, None
    if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
        dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
    if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
        dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1/5) - 1) * 100
    if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
        dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1/años_analisis) - 1) * 100

    fatiga_dividendo = bool(dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0 and (dgr_1y / dgr_5y) < 0.5)

    racha_sin_recortes = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.98:
                racha_sin_recortes += 1
            else: break

    shares_yearly = pd.Series(dtype=float)
    variacion_acciones, recompras_anualizadas = None, 0.0
    try:
        if shares_hist is not None and len(shares_hist) > 1:
            fecha_corte_shares = hoy_ts - pd.DateOffset(years=años_analisis + 3)
            sh_sub = shares_hist[shares_hist.index.tz_localize(None) >= fecha_corte_shares]
            sy = sh_sub.groupby(sh_sub.index.year).last()
            sy = sy[sy > 0]
            sy = sy[sy.pct_change().fillna(0) > -0.50]
            if len(sy) >= 2:
                shares_yearly = sy
                n_anios_sh = min(años_analisis, len(shares_yearly) - 1)
                acc_ini = shares_yearly.iloc[-(n_anios_sh + 1)]
                acc_fin = shares_yearly.iloc[-1]
                if acc_ini > 0:
                    variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                    recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / max(1, n_anios_sh))) - 1) * 100
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
                            shares_yearly = sh_data.groupby(pd.to_datetime(sh_data.index).year).last()
                            acc_ini, acc_fin = shares_yearly.iloc[0], shares_yearly.iloc[-1]
                            n_anios_sh = max(1, len(shares_yearly) - 1)
                            if acc_ini > 0:
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100
                                break
        except Exception: pass

    shareholder_yield = yield_actual + recompras_anualizadas

    # Canales de Precio Weiss
    precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
    precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
    precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

    pct_actual_vs_media = ((precio_actual - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    dist_suelo_pct = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 0

    # ==========================================
    # SCORES DGI (CALIDAD Y VALORACIÓN)
    # ==========================================
    score_calidad = 0.0
    lim_deuda_optima = 4.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 3.0
    lim_deuda_aceptable = 5.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0

    if es_financiera:
        pts_deuda = 2.0 if roe >= 12.0 else (1.0 if roe >= 8.0 else 0.0)
        pts_cob = 0.5 if current_ratio >= 1.0 or roe >= 10.0 else 0.0
    else:
        pts_deuda = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable * 1.15, 2.0, 0.75, inverso=True)
        pts_cob = (0.5 if cobertura_intereses >= 4.0 else (0.25 if cobertura_intereses >= 2.5 else 0.0)) if cobertura_intereses is not None else (0.5 if deuda_neta == 0 else 0.0)
    score_calidad += (pts_deuda + pts_cob)

    if es_financiera and payout_fcf == -1:
        pts_fcf = interpolar_puntos(payout_ratio, 50.0, 75.0, 2.0, 0.8, inverso=True) if payout_ratio > 0 else 0.0
    else:
        pts_fcf = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf * 1.05, 2.0, 0.8, inverso=True) if payout_fcf > 0 else 0.0
    score_calidad += pts_fcf

    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: pts_hist = 2.0
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: pts_hist = 1.25
    elif racha_sin_recortes >= 5: pts_hist = 0.75
    else: pts_hist = 0.0
    if fatiga_dividendo and pts_hist > 0.5: pts_hist -= 0.5
    score_calidad += pts_hist

    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
    cond_roic = (metrica_rentabilidad is not None and metrica_rentabilidad >= 10.0) or (es_reit_puro and operating_margins >= 25.0)
    cond_rev = (revenue_cagr_3y is not None and revenue_cagr_3y > 0)
    pts_foso = 1.0 if (cond_roic and cond_rev) else (0.5 if (cond_roic or cond_rev) else 0.0)
    score_calidad += pts_foso

    pts_dgr = 1.0 if (dgr_5y is not None and dgr_5y >= 5.0) else (0.5 if (dgr_5y is not None and dgr_5y >= 2.5) else 0.0)
    score_calidad += pts_dgr

    cond_recompras = variacion_acciones is not None and variacion_acciones < -0.5
    cond_bpa_pos = crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0
    pts_cap = 1.5 if (cond_recompras or cond_bpa_pos) else 0.0
    score_calidad = min(10.0, round(score_calidad + pts_cap, 1))

    score_val = 0.0
    if yield_actual >= yield_infravalorado: pts_yield = 4.0
    elif yield_actual >= yield_medio: pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_medio, 4.0, 2.2, inverso=False)
    elif yield_actual >= yield_sobrevalorado: pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 2.2, 0.0, inverso=False)
    else: pts_yield = 0.0
    score_val += pts_yield

    if es_financiera and p_fcf <= 0:
        pts_pfcf = interpolar_puntos(price_to_book, 1.3, 2.5, 2.5, 1.0, inverso=True) if price_to_book > 0 else 0.0
    else:
        pts_pfcf = interpolar_puntos(p_fcf, 18.0, 26.0, 2.5, 1.0, inverso=True) if p_fcf > 0 else 0.0
    score_val += pts_pfcf

    multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
    pts_per = interpolar_puntos(multiplo_per_eval, 18.0, 26.0, 2.0, 0.8, inverso=True) if multiplo_per_eval > 0 else 0.0
    score_val += pts_per

    chowder_target = 8.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (12.0 if yield_actual >= 3.0 else 15.0)
    yield_req_chowder = None
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        yield_req_chowder = chowder_target - dgr_5y
        pts_chowder = interpolar_puntos(chowder_number, chowder_target, chowder_target - 2.5, 1.5, 0.5, inverso=False)
    else:
        pts_chowder = 0.0
    score_val = min(10.0, round(score_val + pts_chowder, 1))

    posible_trampa_valor = (precio_actual <= precio_compra) and (score_calidad < 5.5 or (payout_fcf > 95.0) or (dgr_1y is not None and dgr_1y < -1.0))

    # ==========================================
    # MOTOR BOGLE + REVERSIÓN A LA MEDIA DE WEISS (5 AÑOS)
    # ==========================================
    horizonte_bogle = 5
    candidatos_crec = [x for x in [dgr_5y, dgr_periodo, crecimiento_bpa_3y] if x is not None]
    crec_bogle = float(np.median(candidatos_crec)) if candidatos_crec else 3.0
    crec_bogle = max(-5.0, min(14.0, crec_bogle))

    if precio_actual > 0 and precio_justo > 0:
        reversion_weiss_anual = (((precio_justo / precio_actual) ** (1 / horizonte_bogle)) - 1) * 100
    else:
        reversion_weiss_anual = 0.0
    reversion_weiss_anual_acotada = max(-15.0, min(20.0, reversion_weiss_anual))

    retorno_bogle_bruto_anual = yield_actual + crec_bogle + reversion_weiss_anual_acotada
    retorno_bogle_neto_anual = (yield_actual * net_mult) + crec_bogle + reversion_weiss_anual_acotada

    capital_final_5a = capital_simulado * ((1 + (retorno_bogle_neto_anual / 100.0)) ** horizonte_bogle)
    ganancia_neta_5a = capital_final_5a - capital_simulado
    precio_estimado_5a = precio_justo * ((1 + (crec_bogle / 100.0)) ** horizonte_bogle)

    # ==========================================
    # RENDERIZADO VISUAL DE LA PÁGINA 1
    # ==========================================
    if es_reit_puro: tipo_empresa_txt = "🏢 REIT / Inmobiliario (FFO)"
    elif es_quasi_reit_o_recompras: tipo_empresa_txt = "🍔 Franquicia / Recompras"
    elif es_financiera: tipo_empresa_txt = "🏦 Financiero / Seguros (ROE)"
    elif es_regulada_o_reit: tipo_empresa_txt = "⚡ Sector Regulado / Utility"
    else: tipo_empresa_txt = "🏭 Industrial / General"

    hora_actual_str = ahora_madrid.strftime("%H:%M:%S")
    st.header(f"{nombre_empresa} ({ticker_symbol} · {currency}) — {tipo_empresa_txt}")

    txt_exdiv = "Sin fecha Ex-Div próxima"
    ex_div_ts = info.get('exDividendDate')
    if pd.notna(ex_div_ts) and ex_div_ts is not None:
        try:
            ex_dt = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()
            dias_ex = (ex_dt - hoy_ts).days
            if dias_ex > 0: txt_exdiv = f"📅 Ex-Div en {dias_ex} días ({ex_dt.strftime('%d/%m/%Y')})"
            elif dias_ex == 0: txt_exdiv = f"🚨 ¡HOY es Ex-Dividend! ({ex_dt.strftime('%d/%m/%Y')})"
            else: txt_exdiv = f"Último Ex-Div: {ex_dt.strftime('%d/%m/%Y')} (hace {abs(dias_ex)}d)"
        except Exception: pass

    aviso_fx = f" | 💱 <strong>FX:</strong> {curr_fin}➔{currency} ({fx_rate:.3f})" if fx_rate != 1.0 else ""
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 0.9rem;">
        <strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;|&nbsp; 
        <strong>Último tick:</strong> <span style="color: #faca2b;">{hora_actual_str}</span> &nbsp;|&nbsp; 
        <span style="color: #e040fb; font-weight:600;">{txt_exdiv}</span> &nbsp;|&nbsp;
        <strong>Shareholder Yield:</strong> <span style="color: #21c354;">{shareholder_yield:.2f}%</span>{aviso_fx}
    </div>
    """, unsafe_allow_html=True)

    # Perfil Fiscal compacto
    if pais in ['United States', 'Netherlands', 'Canada']: 
        st.success(f"✅ **Fiscalidad ({pais})**: Retención en origen del 15% (100% recuperable en la Renta en España).")
    elif pais == 'United Kingdom': 
        st.success(f"✅ **Fiscalidad ({pais})**: Retención en origen del 0% (salvo PIDs en REITs).")
    elif pais == 'Spain': 
        st.success(f"✅ **Fiscalidad ({pais})**: Mercado local. Retención directa del {impuesto_pct}%.")
    elif pais in MERMA_ORIGEN_PAIS:
        st.warning(f"⚠️ **Fiscalidad ({pais})**: Exceso de retención en origen del **{MERMA_ORIGEN_PAIS[pais]}%** sobre el 15% del convenio. {'(Ya descontado de tu Yield Neto)' if aplicar_merma_origen else '(No descontado)'}")

    if aviso_extraordinario:
        st.warning("⚠️ **Dividendo Extraordinario Filtrado:** Pago atípico (>75% sobre la mediana) suavizado automáticamente para no deformar los canales.")

    # 1. PUNTUACIONES Y VEREDICTO EJECUTIVO
    col_sc1, col_sc2 = st.columns(2)
    with col_sc1:
        if score_calidad >= 8.0: 
            st.success(f"🛡️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Sobresaliente. Caja blindada y foso competitivo claro.")
        elif score_calidad >= 6.0: 
            st.warning(f"⚖️ **CALIDAD DGI: {score_calidad:.1f}/10** — Negocio Sólido. Apto para cartera vigilando deuda o ciclo.")
        else: 
            st.error(f"🚨 **CALIDAD DGI: {score_calidad:.1f}/10** — Calidad Baja. Alerta en solvencia, payout o ventas.")

    with col_sc2:
        if score_val >= 7.0: 
            st.success(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Oportunidad Clara. Percentil {percentil_yield_actual:.0f}% de Yield histórico.")
        elif score_val >= 4.0: 
            st.warning(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Valoración Neutral. Cotiza cerca de su media histórica.")
        else: 
            st.error(f"🏷️ **VALORACIÓN DGI: {score_val:.1f}/10** — Exigente / Cara. Margen de seguridad reducido.")

    if posible_trampa_valor:
        st.warning("🚨 **VEREDICTO: POSIBLE TRAMPA DE VALOR** — Cotiza en Suelo de Weiss, pero su Calidad DGI es baja (< 5.5) o el Payout FCF supera el 95%. Riesgo de recorte.")
    elif precio_actual <= precio_compra and score_calidad >= 7.0:
        st.success(f"💎 **VEREDICTO: COMPRA FUERTE DGI** — Empresa de alta calidad ({score_calidad:.1f}/10) cotizando por debajo de su Suelo de Weiss ({precio_compra:.2f}{sym}).")
    elif precio_actual <= precio_compra:
        st.success(f"🟢 **VEREDICTO: EN ZONA DE COMPRA WEISS** — Cotiza un {abs(dist_suelo_pct):.1f}% por debajo de su Suelo de Compra ({precio_compra:.2f}{sym}).")
    elif precio_actual <= precio_justo and score_calidad >= 7.0:
        st.info(f"🟢 **VEREDICTO: ACUMULAR / VIGILAR** — Gran negocio cotizando con un {abs(pct_actual_vs_media):.1f}% de descuento sobre su Precio Justo ({precio_justo:.2f}{sym}).")
    elif precio_actual >= precio_venta:
        st.error(f"🔴 **VEREDICTO: ZONA DE SOBREVALORACIÓN (VENTA / NO COMPRAR)** — Supera el techo histórico de Weiss ({precio_venta:.2f}{sym}).")
    else:
        st.info(f"⏳ **VEREDICTO: MANTENER / EN ESPERA** — Cotiza un +{pct_actual_vs_media:.1f}% sobre su Precio Justo. Espera corrección hacia {precio_compra:.2f}{sym}.")

    # 2. CUADRÍCULA 2x2 RESPONSIVA DE PRECIOS OBJETIVO WEISS
    color_actual = "#21c354" if precio_actual <= precio_compra else ("#ff4b4b" if precio_actual >= precio_venta else "#faca2b")
    txt_extra_actual = f"Descuento: {abs(pct_actual_vs_media):.1f}% vs Media" if pct_actual_vs_media <= 0 else f"Sobreprecio: +{pct_actual_vs_media:.1f}% vs Media"

    st.markdown(f"""
    <div class="grid-precios-weiss">
        <div class="card-precio" style="border-top: 3px solid {color_actual};">
            <span style="font-size: 0.85rem; color: #aaa;">Cotización en Vivo</span>
            <span style="font-size: 1.75rem; font-weight: 800; color: {color_actual};">{precio_actual:.2f}{sym}</span>
            <span style="font-size: 0.85rem; font-weight: 600; color: {color_actual};">Yield: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% neto)</span>
            <span style="font-size: 0.78rem; color: #999; margin-top: 2px;">{txt_extra_actual} · Perc. {percentil_yield_actual:.0f}%</span>
        </div>
        <div class="card-precio" style="border-top: 3px solid #21c354;">
            <span style="font-size: 0.85rem; color: #aaa;">Suelo Compra (Weiss)</span>
            <span style="font-size: 1.75rem; font-weight: 800; color: #21c354;">{precio_compra:.2f}{sym}</span>
            <span style="font-size: 0.85rem; font-weight: 600; color: #21c354;">Yield: {yield_infravalorado:.2f}% ({yield_infravalorado * net_mult:.2f}% neto)</span>
            <span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Suelo: {pct_infra_vs_media:.1f}% vs Media</span>
        </div>
        <div class="card-precio" style="border-top: 3px solid #faca2b;">
            <span style="font-size: 0.85rem; color: #aaa;">Precio Justo ({años_analisis}A)</span>
            <span style="font-size: 1.75rem; font-weight: 800; color: #faca2b;">{precio_justo:.2f}{sym}</span>
            <span style="font-size: 0.85rem; font-weight: 600; color: #faca2b;">Yield: {yield_medio:.2f}% ({yield_medio * net_mult:.2f}% neto)</span>
            <span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Imán Reversión a la Media</span>
        </div>
        <div class="card-precio" style="border-top: 3px solid #ff4b4b;">
            <span style="font-size: 0.85rem; color: #aaa;">Techo Venta (Weiss)</span>
            <span style="font-size: 1.75rem; font-weight: 800; color: #ff4b4b;">{precio_venta:.2f}{sym}</span>
            <span style="font-size: 0.85rem; font-weight: 600; color: #ff4b4b;">Yield: {yield_sobrevalorado:.2f}% ({yield_sobrevalorado * net_mult:.2f}% neto)</span>
            <span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Techo: +{pct_sobre_vs_media:.1f}% vs Media</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 3. TERMÓMETRO VISUAL DEL CANAL DE WEISS
    if precio_venta > precio_compra:
        pos_canal = ((precio_actual - precio_compra) / (precio_venta - precio_compra)) * 100
        pos_canal_clamp = max(2.0, min(98.0, pos_canal))
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.04); padding: 10px 14px; border-radius: 8px; margin-bottom: 16px;">
            <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:#bbb; margin-bottom:4px;">
                <span>🟢 Suelo Compra ({precio_compra:.2f}{sym})</span>
                <span>📍 <strong>Posición en Canal: {pos_canal:.0f}%</strong></span>
                <span>🔴 Techo Venta ({precio_venta:.2f}{sym})</span>
            </div>
            <div style="position: relative; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #21c354 0%, #faca2b 50%, #ff4b4b 100%);">
                <div style="position: absolute; left: {pos_canal_clamp:.1f}%; top: -4px; width: 18px; height: 18px; background: white; border: 3px solid #00d4ff; border-radius: 50%; transform: translateX(-50%);"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 4. REGLA DE BOGLE + REVERSIÓN A LA MEDIA DE WEISS (CON SIMULADOR 500€/$)
    st.markdown("#### 🔮 Retorno Total Esperado: Regla de Bogle + Reversión a la Media de Weiss (5 Años)")
    
    b_rev_cls = "badge-verde" if reversion_weiss_anual_acotada >= 0 else "badge-rojo"
    b_tot_cls = "badge-verde" if retorno_bogle_bruto_anual >= 10.0 else ("badge-ambar" if retorno_bogle_bruto_anual >= 6.0 else "badge-rojo")
    signo_rev = "+" if reversion_weiss_anual_acotada >= 0 else ""

    acc_hoy = capital_simulado / precio_actual if precio_actual > 0 else 0
    div_neto_hoy = acc_hoy * forward_dividend * net_mult
    acc_suelo = capital_simulado / precio_compra if precio_compra > 0 else 0
    div_neto_suelo = acc_suelo * forward_dividend * net_mult

    col_bog1, col_bog2 = st.columns(2)
    with col_bog1:
        st.markdown(f"""
        <div class="card-dgi">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="color: #aaa; font-size: 0.85rem;">Ecuación Bogle: Yield + Crecimiento ± Reversión Weiss</span>
                <span class="{b_tot_cls}">CAGR Bruto: {retorno_bogle_bruto_anual:+.1f}%/año</span>
            </div>
            <div style="font-size: 1.15rem; margin: 8px 0;">
                <span style="color:#00d4ff; font-weight:bold;">{yield_actual:.2f}%</span> <span style="font-size:0.8rem; color:#888;">(Yield)</span> + 
                <span style="color:#faca2b; font-weight:bold;">{crec_bogle:+.1f}%</span> <span style="font-size:0.8rem; color:#888;">(Crec.)</span> 
                <span style="color:{'#21c354' if reversion_weiss_anual_acotada >= 0 else '#ff4b4b'}; font-weight:bold;"> {signo_rev}{reversion_weiss_anual_acotada:.1f}%</span> <span style="font-size:0.8rem; color:#888;">(Reversión)</span> = 
                <strong style="font-size: 1.45rem; color: white;">{retorno_bogle_neto_anual:+.1f}% neto/año</strong>
            </div>
            <span style="font-size: 0.78rem; color: #999;">
                Si en 5 años la acción vuelve a su Yield Medio ({yield_medio:.2f}%), su cotización rondaría los <strong>{precio_estimado_5a:.2f}{sym}</strong>, aportando un <strong>{signo_rev}{reversion_weiss_anual_acotada:.1f}% anual extra</strong> por expansión/contracción de múltiplo.
            </span>
        </div>
        """, unsafe_allow_html=True)

    with col_bog2:
        st.markdown(f"""
        <div class="card-dgi">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="color: #aaa; font-size: 0.85rem;">🧮 Simulación de tu Orden de {capital_simulado:,.0f}{sym}</span>
                <span class="{b_rev_cls}">A 5 Años: {capital_final_5a:,.0f}{sym} ({ganancia_neta_5a:+,.0f}{sym})</span>
            </div>
            <div style="font-size: 0.9rem; color: #ddd; line-height: 1.5; margin-top: 4px;">
                • <strong>Comprando HOY ({precio_actual:.2f}{sym}):</strong> {acc_hoy:.2f} acc. ➔ Renta inicial: <strong style="color:#00d4ff;">{div_neto_hoy:.2f}{sym}/año netos</strong>.<br>
                • <strong>Esperando al SUELO ({precio_compra:.2f}{sym}):</strong> {acc_suelo:.2f} acc. ➔ Renta inicial: <strong style="color:#21c354;">{div_neto_suelo:.2f}{sym}/año netos</strong>.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 5. GRÁFICO 1: CANALES HISTÓRICOS DE WEISS + EXPLICACIÓN DINÁMICA
    st.markdown(f"### 📈 Evolución Histórica de Valoración ({años_analisis} Años)")
    df_grafico = historial_analisis[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_analisis['Div_Anual']
        df_grafico['Precio_Compra'] = (df_grafico['Div_Grafico'] / yield_infravalorado) * 100
        df_grafico['Precio_Justo'] = (df_grafico['Div_Grafico'] / yield_medio) * 100
        df_grafico['Precio_Venta'] = (df_grafico['Div_Grafico'] / yield_sobrevalorado) * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Venta'], name='Franja Sobrevalorada (Venta)', line=dict(color='#ff4b4b', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Compra'], name='Franja Infravalorada (Compra)', line=dict(color='#21c354', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Close'], name='Cotización Real', line=dict(color='#00d4ff', width=3)))
        
        fig.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=420,
            legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5), 
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

        is_compra = df_grafico['Close'] <= df_grafico['Precio_Compra']
        toques_compra = int((is_compra & ~is_compra.shift(1, fill_value=False)).sum())
        is_venta = df_grafico['Close'] >= df_grafico['Precio_Venta']
        toques_venta = int((is_venta & ~is_venta.shift(1, fill_value=False)).sum())

        estado_canal_txt = f"un <strong>{abs(pct_actual_vs_media):.1f}% por debajo</strong> de su Precio Justo ({precio_justo:.2f}{sym})" if pct_actual_vs_media <= 0 else f"un <strong>+{pct_actual_vs_media:.1f}% por encima</strong> de su Precio Justo ({precio_justo:.2f}{sym})"
        dist_compra_txt = f"ya cotiza un <strong>{abs(dist_suelo_pct):.1f}% por debajo de la línea verde</strong>" if dist_suelo_pct <= 0 else f"necesita caer un <strong>{dist_suelo_pct:.1f}% adicional</strong> para tocar la línea verde ({precio_compra:.2f}{sym})"

        st.markdown(f"""
        <div class="explicacion-graf">
            💡 <strong>Lectura de este gráfico en {ticker_symbol}:</strong> Los escalones muestran cómo cada subida anual del dividendo eleva el suelo y el techo de valoración de la empresa. Hoy cotiza a <strong>{precio_actual:.2f}{sym}</strong> ({estado_canal_txt}) y {dist_compra_txt}. En los últimos {años_analisis} años ha tocado la zona de compra <strong>{toques_compra} veces</strong> (y {toques_venta} veces la zona de venta). Su Yield actual (<strong>{yield_actual:.2f}%</strong>) supera al <strong>{percentil_yield_actual:.1f}%</strong> de todas las sesiones de los últimos {años_analisis} años.
        </div>
        """, unsafe_allow_html=True)

    # 6. GRÁFICO 2: LUPA DE FRANCOTIRADOR (TIMING + SMA 200/1000 + RSI + MACD)
    st.divider()
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses + SMA 200/1000 + RSI + MACD)")

    sma_200_full = historial_completo['Close'].rolling(200).mean()
    sma_1000_full = historial_completo['Close'].rolling(1000).mean()

    fecha_calculo_macd = hoy_ts - pd.DateOffset(years=1)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()

    if len(df_tech_full) > 30: 
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100
        df_tech_full['Precio_Justo'] = (df_tech_full['Div_Anual'] / yield_medio) * 100
        df_tech_full['Precio_Venta'] = (df_tech_full['Div_Anual'] / yield_sobrevalorado) * 100
        df_tech_full['SMA_200'] = sma_200_full.reindex(df_tech_full.index)
        df_tech_full['SMA_1000'] = sma_1000_full.reindex(df_tech_full.index)

        if yield_req_chowder is not None and yield_req_chowder > 0:
            df_tech_full['Precio_Chowder'] = (df_tech_full['Div_Anual'] / yield_req_chowder) * 100

        ema12 = df_tech_full['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df_tech_full['Close'].ewm(span=26, adjust=False).mean()
        df_tech_full['MACD'] = ema12 - ema26
        df_tech_full['Signal'] = df_tech_full['MACD'].ewm(span=9, adjust=False).mean()
        df_tech_full['Histogram'] = df_tech_full['MACD'] - df_tech_full['Signal']

        delta_p = df_tech_full['Close'].diff()
        gain = delta_p.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss = (-delta_p.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        df_tech_full['RSI'] = 100 - (100 / (1 + rs))

        fecha_display = hoy_ts - pd.DateOffset(months=2)
        df_tech = df_tech_full[df_tech_full.index >= fecha_display].copy()

        if not df_tech.empty:
            ult_macd = df_tech['MACD'].iloc[-1]
            ult_signal = df_tech['Signal'].iloc[-1]
            ult_hist = df_tech['Histogram'].iloc[-1]
            penult_hist = df_tech['Histogram'].iloc[-2] if len(df_tech) > 1 else 0
            ult_rsi = df_tech['RSI'].iloc[-1] if pd.notna(df_tech['RSI'].iloc[-1]) else 50.0
            ult_sma200 = df_tech['SMA_200'].iloc[-1] if pd.notna(df_tech['SMA_200'].iloc[-1]) else None
            ult_sma1000 = df_tech['SMA_1000'].iloc[-1] if pd.notna(df_tech['SMA_1000'].iloc[-1]) else None

            avg_vol = df_tech['Volume'].mean()
            max_vol_5d = df_tech['Volume'].tail(5).max()
            ratio_vol = (max_vol_5d / avg_vol) if avg_vol > 0 else 1.0

            colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for _, row in df_tech.iterrows()]
            colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']]

            fig_tech = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=[0.44, 0.16, 0.20, 0.20])
            fig_tech.add_trace(go.Ohlc(x=df_tech.index, open=df_tech['Open'], high=df_tech['High'], low=df_tech['Low'], close=df_tech['Close'], name='Precio', increasing_line_color='#21c354', decreasing_line_color='#ff4b4b', showlegend=False), row=1, col=1)

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA_200'], name='SMA 200', line=dict(color='#faca2b', width=1.4, dash='dot'), showlegend=True), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA_1000'], name='SMA 1000', line=dict(color='#ff9100', width=2.0), showlegend=True), row=1, col=1)

            if 'Precio_Chowder' in df_tech.columns:
                fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Chowder'], name='Precio Obj. Chowder', line=dict(color='#e040fb', width=1.5, dash='dashdot'), showlegend=True, visible='legendonly'), row=1, col=1)

            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False), row=2, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['RSI'], name='RSI (14)', line=dict(color='#b388ff', width=1.8), showlegend=False), row=3, col=1)
            fig_tech.add_hline(y=70, line_dash="dot", line_color="#ff4b4b", row=3, col=1)
            fig_tech.add_hline(y=30, line_dash="dot", line_color="#21c354", row=3, col=1)

            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False), row=4, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False), row=4, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False), row=4, col=1)

            fig_tech.update_yaxes(title_text="Precio", row=1, col=1)
            fig_tech.update_yaxes(title_text="Vol", row=2, col=1)
            fig_tech.update_yaxes(title_text="RSI", range=[15, 85], row=3, col=1)
            fig_tech.update_yaxes(title_text="MACD", row=4, col=1)

            fig_tech.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=820, showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.04, xanchor="center", x=0.5), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_rangeslider_visible=False)
            fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_tech, use_container_width=True)

            txt_s200 = f"a un <strong>{((precio_actual - ult_sma200)/ult_sma200)*100:+.1f}%</strong> de su SMA 200 ({ult_sma200:.2f}{sym})" if ult_sma200 else "sin SMA 200"
            txt_s1000 = f"y a un <strong>{((precio_actual - ult_sma1000)/ult_sma1000)*100:+.1f}%</strong> de su SMA 1000 ({ult_sma1000:.2f}{sym})" if ult_sma1000 else ""
            estado_macd = "alcista (MACD sobre Señal)" if ult_macd > ult_signal else ("bajista pero perdiendo fuerza (posible giro)" if ult_hist > penult_hist else "bajista en caída")
            estado_rsi = "en sobreventa (<32, agotamiento vendedor)" if ult_rsi <= 32 else ("en sobrecompra (>70)" if ult_rsi >= 70 else "en zona neutral")

            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Lectura Técnica en Vivo ({precio_actual:.2f}{sym}):</strong> El precio se sitúa {txt_s200} {txt_s1000}. El <strong>RSI (14) marca {ult_rsi:.1f}</strong> ({estado_rsi}) y el <strong>MACD está {estado_macd}</strong>. El pico de volumen reciente equivale a <strong>{ratio_vol:.2f}x veces</strong> la media de 2 meses ({'señal de capitulación/volumen institucional' if ratio_vol >= 1.5 else 'volumen normal de sesión'}).
            </div>
            """, unsafe_allow_html=True)


# ==========================================
# INTERFAZ CONECTADA A MEMORIA GLOBAL
# ==========================================
st.title("🎯 1. Valoración, Bogle y Timing — Weiss DGI")

st.session_state.setdefault("ticker_activo", "MKC")
st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("capital_activo", 500.0)
st.session_state.setdefault("merma_activa", True)
st.session_state.setdefault("analizar_activo", False)

lista_años = [5, 10, 12, 15, 20]
idx_años = lista_años.index(st.session_state.años_activo) if st.session_state.años_activo in lista_años else 2

col_input1, col_input2, col_input3, col_input4 = st.columns([1.2, 1, 1, 1.3])
with col_input1: 
    ticker_input = st.text_input("Ticker individual:", value=st.session_state.ticker_activo).upper().strip()
with col_input2: 
    años_analisis = st.selectbox("Periodo Histórico:", lista_años, index=idx_años)
with col_input3: 
    impuesto = st.number_input("Retención IRPF (%)", value=float(st.session_state.impuesto_activo), step=1.0)
with col_input4:
    capital_simulado = st.number_input("Capital Simulado Orden:", value=float(st.session_state.capital_activo), step=50.0)

aplicar_merma = st.checkbox(
    "Aplicar merma fiscal en origen no recuperable (>15% en Suiza, Alemania, Francia, Dinamarca, Irlanda)",
    value=st.session_state.merma_activa
)

# Sincronizar cambios en la memoria compartida para el resto de pestañas
st.session_state.ticker_activo = ticker_input
st.session_state.años_activo = años_analisis
st.session_state.impuesto_activo = impuesto
st.session_state.capital_activo = capital_simulado
st.session_state.merma_activa = aplicar_merma

if st.button("🚀 Analizar / Actualizar Cotización en Vivo", use_container_width=True):
    cargar_cotizacion_tiempo_real.clear()
    st.session_state.analizar_activo = True

if st.session_state.analizar_activo:
    with st.spinner(f"Actualizando cotización en vivo y métricas de {ticker_input}..."):
        try:
            render_valoracion_bogle(ticker_input, años_analisis, impuesto, aplicar_merma, capital_simulado)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
