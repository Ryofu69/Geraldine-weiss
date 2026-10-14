import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
# FORMATEO A LA ESPAÑOLA (PUNTOS Y COMAS)
# ==========================================
def f_num(val, dec=2, sufijo="", signo_pos=False):
    if pd.isna(val) or val is None:
        return "N/D"
    try:
        val_f = float(val)
        pref = "+" if (signo_pos and val_f > 0) else ""
        formatted = f"{val_f:,.{dec}f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{pref}{formatted}{sufijo}"
    except Exception:
        return str(val)

# ==========================================
# CACHÉ INTELIGENTE CON RESPALDO CONTABLE
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def cargar_fundamentales_pesados(ticker_symbol):
    t = yf.Ticker(ticker_symbol)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

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
        shares_hist = t.get_shares_full(start="2008-01-01")
    except Exception: pass

    # Respaldo de divisa desde fast_info si info falló
    curr_cot = info.get('currency')
    if not curr_cot:
        try:
            curr_cot = t.fast_info.currency or 'USD'
        except Exception:
            curr_cot = 'USD'
        info['currency'] = curr_cot

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
    shares_fast = None
    mcap_fast = None
    try:
        precio_vivo = float(t.fast_info.last_price)
    except Exception: pass
    try:
        shares_fast = float(t.fast_info.shares)
    except Exception: pass
    try:
        mcap_fast = float(t.fast_info.market_cap)
    except Exception: pass
    return hist, precio_vivo, shares_fast, mcap_fast

def interpolar_puntos(valor, umbral_max, umbral_med, pts_max, pts_med, inverso=False):
    if valor is None or pd.isna(valor):
        return 0.0
    if not inverso:
        if valor >= umbral_max: return pts_max
        if valor < umbral_med: return 0.0
        if umbral_max == umbral_med: return pts_max
        ratio = (valor - umbral_med) / (umbral_max - umbral_med)
        return round(pts_med + ratio * (pts_max - pts_med), 2)
    else:
        if valor < 0: return 0.0
        if valor <= umbral_max: return pts_max
        if valor > umbral_med: return 0.0
        if umbral_med == umbral_max: return pts_max
        ratio = (umbral_med - valor) / (umbral_med - umbral_max)
        return round(pts_med + ratio * (pts_max - pts_med), 2)

def ultimo_valor_tabla(df, claves):
    """Extrae el último dato anual disponible en inc_stmt, bs_stmt o cf_stmt si ticker.info falla."""
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    return float(s.iloc[-1])
    return 0.0

# ==========================================
# FUNCIÓN PESTAÑA 1: VALORACIÓN, BOGLE Y TIMING
# ==========================================
def render_valoracion_bogle(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    info, dividendos_raw, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin = cargar_fundamentales_pesados(ticker_symbol)
    historial_raw, precio_vivo, shares_fast, mcap_fast = cargar_cotizacion_tiempo_real(ticker_symbol)

    # Si info se quedó vacío en caché por un microcorte de Yahoo, reintentar una vez en vivo
    if not info.get('sector') and not info.get('shortName'):
        cargar_fundamentales_pesados.clear()
        info, dividendos_raw, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin = cargar_fundamentales_pesados(ticker_symbol)

    if dividendos_raw.empty or len(historial_raw) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None: return default
        try: return float(val)
        except (ValueError, TypeError): return default

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

    # --- DIVIDENDOS CORREGIDOS (FRECUENCIA DE LOS ÚLTIMOS 3 AÑOS CERRADOS) ---
    años_div = dividendos.index.year
    conteo_por_año = años_div.value_counts()
    # Mirar solo los últimos 3 años cerrados para detectar cambios de semestral a trimestral (ej. ACN)
    conteo_reciente = conteo_por_año[(conteo_por_año.index < año_actual) & (conteo_por_año.index >= año_actual - 3)]
    if not conteo_reciente.empty:
        pagos_por_año = int(conteo_reciente.mode().iloc[0])
    else:
        conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
        pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4

    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    # Filtro suave de pagos especiales (>2.2x la mediana de su propio año/entorno)
    mediana_pagos = dividendos.rolling(window=max(4, pagos_por_año), min_periods=1).median()
    umbral_extra = mediana_pagos * 2.2
    aviso_extraordinario = bool((dividendos.tail(pagos_por_año) > umbral_extra.tail(pagos_por_año)).any())
    dividendos_regulares = dividendos.where(dividendos <= umbral_extra, mediana_pagos)

    divs_reg_por_año = dividendos_regulares.groupby(dividendos_regulares.index.year).sum()

    # Forward dividend: prioriza el último pago regular * pagos_por_año si supera al dato estático de Yahoo
    ult_pago_anualizado = float(dividendos_regulares.iloc[-1]) * pagos_por_año if not dividendos_regulares.empty else 0.0
    ultimo_año_completo = float(divs_reg_por_año.loc[divs_reg_por_año.index < año_actual].iloc[-1]) if any(divs_reg_por_año.index < año_actual) else 0.0
    
    fd_info = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    if es_peniques_uk and fd_info > (precio_actual * 0.25):
        fd_info /= 100.0

    # Si fd_info es 0 (fallo de info) o menor al último pago anualizado (ej. subida reciente de dividendo), usamos el real
    if fd_info <= 0 or abs(ult_pago_anualizado - fd_info) / max(1.0, ult_pago_anualizado) > 0.20:
        forward_dividend = max(ult_pago_anualizado, ultimo_año_completo)
    else:
        forward_dividend = max(fd_info, ult_pago_anualizado)

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

    # --- FUNDAMENTALES CON RESPALDO AUTOMÁTICO DESDE TABLAS CONTABLES ---
    shares = get_safe('sharesOutstanding', 0.0)
    if shares <= 0 and shares_fast:
        shares = shares_fast
    if shares <= 0:
        shares = ultimo_valor_tabla(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'])

    bpa_trailing = get_safe('trailingEps', 0.0)
    if bpa_trailing == 0:
        bpa_trailing = ultimo_valor_tabla(inc_stmt, ['Diluted EPS', 'Basic EPS']) * fx_rate

    per_actual = get_safe('trailingPE', 0.0)
    if per_actual <= 0 and bpa_trailing > 0:
        per_actual = precio_actual / bpa_trailing
    per_forward = get_safe('forwardPE', 0.0)
    per = per_actual if per_actual > 0 else per_forward

    payout_ratio = get_safe('payoutRatio', 0.0) * 100
    if payout_ratio <= 0 and bpa_trailing > 0:
        payout_ratio = (forward_dividend / bpa_trailing) * 100

    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    if total_debt <= 0:
        total_debt = ultimo_valor_tabla(bs_stmt, ['Total Debt', 'Long Term Debt And Capital Lease Obligation', 'Long Term Debt']) * fx_rate

    total_cash = get_safe('totalCash', 0.0) * fx_rate
    if total_cash <= 0:
        total_cash = ultimo_valor_tabla(bs_stmt, ['Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents', 'Cash']) * fx_rate

    ebitda = get_safe('ebitda', 0.0) * fx_rate
    if ebitda <= 0:
        ebitda = ultimo_valor_tabla(inc_stmt, ['EBITDA', 'Normalized EBITDA', 'Operating Income']) * fx_rate

    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    if fcf_raw == 0:
        fcf_raw = ultimo_valor_tabla(cf_stmt, ['Free Cash Flow']) * fx_rate

    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    if ocf_raw == 0:
        ocf_raw = ultimo_valor_tabla(cf_stmt, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities']) * fx_rate

    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw

    total_equity_raw = get_safe('totalStockholderEquity', 0.0) * fx_rate
    if total_equity_raw == 0:
        total_equity_raw = ultimo_valor_tabla(bs_stmt, ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity']) * fx_rate

    net_inc_val = ultimo_valor_tabla(inc_stmt, ['Net Income', 'Net Income Common Stockholders']) * fx_rate
    roe = get_safe('returnOnEquity', 0.0) * 100
    if roe == 0 and total_equity_raw > 0 and net_inc_val > 0:
        roe = (net_inc_val / total_equity_raw) * 100

    ebit_tabla = ultimo_valor_tabla(inc_stmt, ['Operating Income', 'EBIT']) * fx_rate
    rev_tabla = ultimo_valor_tabla(inc_stmt, ['Total Revenue', 'Operating Revenue']) * fx_rate
    operating_margins = get_safe('operatingMargins', 0.0) * 100
    if operating_margins == 0 and rev_tabla > 0 and ebit_tabla > 0:
        operating_margins = (ebit_tabla / rev_tabla) * 100

    price_to_book = get_safe('priceToBook', -1)
    if price_to_book <= 0 and total_equity_raw > 0 and shares > 0:
        price_to_book = precio_actual / (total_equity_raw / shares)

    deuda_equity = get_safe('debtToEquity', 0.0)
    current_ratio = get_safe('currentRatio', 0.0)

    es_quasi_reit_o_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 22.0) and (total_equity_raw <= 0 or price_to_book < 0 or deuda_equity == 0.0)
    es_regulada_o_reit = es_reit_puro or es_utility_pura or es_quasi_reit_o_recompras

    payout_limite_fcf = 75.0 if es_regulada_o_reit else 65.0
    payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 85.0

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
        if ebit_val == 0: ebit_val = ebit_tabla
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
    else:
        dividendos_barras.loc[año_actual] = forward_dividend

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

    # Acciones en circulación: priorizar Diluted Average Shares auditadas de inc_stmt para evitar ruido de clases en ACN
    shares_yearly = pd.Series(dtype=float)
    variacion_acciones, recompras_anualizadas = None, 0.0
    try:
        if not inc_stmt.empty:
            for key in ['Diluted Average Shares', 'Basic Average Shares']:
                if key in inc_stmt.index:
                    sh_data = inc_stmt.loc[key].dropna()
                    sh_data = sh_data[sh_data > 0]
                    if len(sh_data) >= 2:
                        shares_yearly = sh_data.groupby(pd.to_datetime(sh_data.index).year).last().sort_index()
                        acc_ini, acc_fin = float(shares_yearly.iloc[0]), float(shares_yearly.iloc[-1])
                        n_anios_sh = max(1, int(shares_yearly.index[-1] - shares_yearly.index[0]))
                        if acc_ini > 0:
                            variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                            recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100
                            break
    except Exception: pass

    if variacion_acciones is None and shares_hist is not None and len(shares_hist) > 1:
        try:
            fecha_corte_shares = hoy_ts - pd.DateOffset(years=años_analisis)
            sh_sub = shares_hist[shares_hist.index.tz_localize(None) >= fecha_corte_shares]
            sy = sh_sub.groupby(sh_sub.index.year).median()
            sy = sy[sy > 0]
            if len(sy) >= 2:
                shares_yearly = sy
                n_anios_sh = max(1, int(sy.index[-1] - sy.index[0]))
                acc_ini, acc_fin = float(sy.iloc[0]), float(sy.iloc[-1])
                if acc_ini > 0:
                    variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                    recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100
        except Exception: pass

    recompras_anualizadas = max(-5.0, min(8.0, recompras_anualizadas))
    shareholder_yield = yield_actual + recompras_anualizadas

    precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
    precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
    precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

    pct_actual_vs_media = ((precio_actual - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    dist_suelo_pct = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 0

    # ==========================================
    # SISTEMA DE PUNTUACIONES CALIBRADO Y CORREGIDO (0 A 10 PTS)
    # ==========================================
    lim_deuda_optima = 3.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 2.5
    lim_deuda_aceptable = 5.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0

    if es_financiera:
        pts_deuda = interpolar_puntos(roe, 14.0, 7.0, 2.0, 0.5, inverso=False)
        pts_cob = 0.5 if (current_ratio >= 1.0 or roe >= 10.0) else 0.0
    else:
        pts_deuda = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable, 2.0, 0.5, inverso=True)
        pts_cob = interpolar_puntos(cobertura_intereses, 5.0, 2.5, 0.5, 0.15, inverso=False) if cobertura_intereses is not None else (0.5 if deuda_neta == 0 else 0.0)

    if es_financiera and payout_fcf == -1:
        pts_fcf = interpolar_puntos(payout_ratio, 50.0, 75.0, 2.0, 0.5, inverso=True) if payout_ratio > 0 else 0.0
    else:
        pts_fcf = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 2.0, 0.5, inverso=True) if payout_fcf > 0 else 0.0

    racha_efectiva = racha_sin_recortes + (3 if años_pagando >= 20 else 0)
    pts_hist = interpolar_puntos(racha_efectiva, 18.0, 5.0, 2.0, 0.6, inverso=False)
    if fatiga_dividendo and pts_hist > 0.5:
        pts_hist = max(0.0, round(pts_hist - 0.5, 2))

    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
    pts_roic_sub = interpolar_puntos(metrica_rentabilidad, 12.0, 6.0, 0.9, 0.3, inverso=False) if metrica_rentabilidad is not None else (0.8 if (es_reit_puro and operating_margins >= 25.0) else 0.0)
    pts_rev_sub = interpolar_puntos(revenue_cagr_3y, 4.0, 0.0, 0.6, 0.2, inverso=False) if revenue_cagr_3y is not None else 0.0
    pts_foso = round(pts_roic_sub + pts_rev_sub, 2)

    pts_dgr = interpolar_puntos(dgr_5y, 6.0, 2.5, 1.0, 0.3, inverso=False) if dgr_5y is not None else 0.0

    pts_recompra_sub = interpolar_puntos(-(variacion_acciones or 0.0), 2.0, 0.2, 1.0, 0.4, inverso=False) if (variacion_acciones is not None and variacion_acciones < -0.2) else 0.0
    pts_bpa_sub = interpolar_puntos(crecimiento_bpa_3y, 6.0, 1.5, 1.0, 0.4, inverso=False) if (crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 1.5) else 0.0
    pts_cap = round(max(pts_recompra_sub, pts_bpa_sub, min(1.0, (pts_recompra_sub + pts_bpa_sub) * 0.75)), 2)

    score_calidad = min(10.0, round(pts_deuda + pts_cob + pts_fcf + pts_hist + pts_foso + pts_dgr + pts_cap, 1))

    # --- SCORE DE VALORACIÓN (0 A 10 PTS) ---
    if yield_actual >= yield_infravalorado:
        pts_yield = 4.0
    elif yield_actual >= yield_medio:
        pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_medio, 4.0, 2.0, inverso=False)
    elif yield_actual >= yield_sobrevalorado:
        pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 2.0, 0.0, inverso=False)
    else:
        pts_yield = 0.0

    if es_financiera and p_fcf <= 0:
        pts_pfcf = interpolar_puntos(price_to_book, 1.2, 2.2, 2.5, 0.5, inverso=True) if price_to_book > 0 else 0.0
    else:
        pts_pfcf = interpolar_puntos(p_fcf, 16.0, 25.0, 2.5, 0.4, inverso=True) if p_fcf > 0 else 0.0

    multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
    pts_per = interpolar_puntos(multiplo_per_eval, 16.0, 25.0, 2.0, 0.4, inverso=True) if multiplo_per_eval > 0 else 0.0

    chowder_target = 8.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (12.0 if yield_actual >= 3.0 else 15.0)
    yield_req_chowder = None
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        yield_req_chowder = chowder_target - dgr_5y
        pts_chowder = interpolar_puntos(chowder_number, chowder_target, chowder_target - 3.0, 1.5, 0.3, inverso=False)
    else:
        pts_chowder = 0.0

    score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
    posible_trampa_valor = (precio_actual <= precio_compra) and (score_calidad < 5.5 or (payout_fcf > 92.0) or (dgr_1y is not None and dgr_1y < -2.0))

    # ==========================================
    # MOTOR BOGLE + REVERSIÓN A LA MEDIA (5 AÑOS)
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
    # RENDERIZADO VISUAL (CON PROTECCIÓN NOTRANSLATE PARA CHROME MÓVIL)
    # ==========================================
    if es_reit_puro: tipo_empresa_txt = "🏢 REIT / Inmobiliario (FFO)"
    elif es_quasi_reit_o_recompras: tipo_empresa_txt = "🍔 Franquicia / Recompras"
    elif es_financiera: tipo_empresa_txt = "🏦 Financiero / Seguros (ROE)"
    elif es_regulada_o_reit: tipo_empresa_txt = "⚡ Sector Regulado / Utility"
    else: tipo_empresa_txt = "🏭 Industrial / General"

    hora_actual_str = ahora_madrid.strftime("%H:%M:%S")
    st.header(f"{nombre_empresa} ({ticker_symbol} · {currency}) — {tipo_empresa_txt}")

    txt_exdiv = "Último Ex-Div: " + dividendos.index[-1].strftime('%d/%m/%Y') if not dividendos.empty else "Sin fecha Ex-Div"
    ex_div_ts = info.get('exDividendDate')
    if pd.notna(ex_div_ts) and ex_div_ts is not None:
        try:
            ex_dt = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()
            dias_ex = (ex_dt - hoy_ts).days
            if dias_ex > 0: txt_exdiv = f"📅 Ex-Div en {dias_ex} días ({ex_dt.strftime('%d/%m/%Y')})"
            elif dias_ex == 0: txt_exdiv = f"🚨 ¡HOY es Ex-Dividend! ({ex_dt.strftime('%d/%m/%Y')})"
            else: txt_exdiv = f"Último Ex-Div: {ex_dt.strftime('%d/%m/%Y')} (hace {abs(dias_ex)}d)"
        except Exception: pass

    aviso_fx = f" | 💱 <strong>FX:</strong> {curr_fin}➔{currency} ({f_num(fx_rate, 3)})" if fx_rate != 1.0 else ""
    st.markdown(f"""
<div class="notranslate" translate="no" style="background-color: rgba(255, 255, 255, 0.05); padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 0.9rem;">
<strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;|&nbsp; 
<strong>Último tick:</strong> <span style="color: #faca2b;">{hora_actual_str}</span> &nbsp;|&nbsp; 
<span style="color: #e040fb; font-weight:600;">{txt_exdiv}</span> &nbsp;|&nbsp;
<strong>Shareholder Yield:</strong> <span style="color: #21c354;">{f_num(shareholder_yield, 2, '%')}</span>{aviso_fx}
</div>
""", unsafe_allow_html=True)

    if pais in ['United States', 'Netherlands', 'Canada']: 
        st.success(f"✅ **Fiscalidad ({pais})**: Retención en origen del 15% (100% recuperable en la Renta en España).")
    elif pais == 'United Kingdom': 
        st.success(f"✅ **Fiscalidad ({pais})**: Retención en origen del 0% (salvo PIDs en REITs).")
    elif pais == 'Spain': 
        st.success(f"✅ **Fiscalidad ({pais})**: Mercado local. Retención directa del {f_num(impuesto_pct, 1, '%')}.")
    elif pais in MERMA_ORIGEN_PAIS:
        st.warning(f"⚠️ **Fiscalidad ({pais})**: Exceso de retención en origen del **{f_num(MERMA_ORIGEN_PAIS[pais], 2, '%')}** sobre el 15% del convenio.")

    if aviso_extraordinario:
        st.warning("⚠️ **Dividendo Extraordinario Filtrado:** Pago atípico suavizado automáticamente.")

    # 1. PUNTUACIONES Y VEREDICTO
    col_sc1, col_sc2 = st.columns(2)
    with col_sc1:
        if score_calidad >= 8.0: 
            st.success(f"🛡️ **CALIDAD DGI: {f_num(score_calidad, 1)}/10** — Negocio Sobresaliente y Balance Blindado.")
        elif score_calidad >= 6.0: 
            st.warning(f"⚖️ **CALIDAD DGI: {f_num(score_calidad, 1)}/10** — Negocio Sólido. Apto vigilando deuda.")
        else: 
            st.error(f"🚨 **CALIDAD DGI: {f_num(score_calidad, 1)}/10** — Calidad Insuficiente / Riesgo de Apalancamiento.")

    with col_sc2:
        if score_val >= 7.0: 
            st.success(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Oportunidad Clara (Percentil {f_num(percentil_yield_actual, 0)}% de Yield).")
        elif score_val >= 4.0: 
            st.warning(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Neutral / Cerca de su media histórica.")
        else: 
            st.error(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Cotización Cara o Exigente.")

    if posible_trampa_valor:
        st.warning("🚨 **VEREDICTO: POSIBLE TRAMPA DE VALOR** — Cotiza en Suelo de Weiss, pero su Calidad DGI es baja (< 5,5) o el Payout FCF supera el 92%.")
    elif precio_actual <= precio_compra and score_calidad >= 7.0:
        st.success(f"💎 **VEREDICTO: COMPRA FUERTE DGI** — Alta calidad ({f_num(score_calidad, 1)}/10) por debajo del Suelo Weiss ({f_num(precio_compra, 2)}{sym}).")
    elif precio_actual <= precio_compra:
        st.success(f"🟢 **VEREDICTO: EN ZONA DE COMPRA WEISS** — Cotiza un {f_num(abs(dist_suelo_pct), 1)}% por debajo de su Suelo ({f_num(precio_compra, 2)}{sym}).")
    elif precio_actual <= precio_justo and score_calidad >= 7.0:
        st.info(f"🟢 **VEREDICTO: ACUMULAR / VIGILAR** — Gran negocio con un {f_num(abs(pct_actual_vs_media), 1)}% de descuento sobre su Precio Justo.")
    elif precio_actual >= precio_venta:
        st.error(f"🔴 **VEREDICTO: ZONA DE VENTA** — Supera el techo histórico de Weiss ({f_num(precio_venta, 2)}{sym}).")
    else:
        st.info(f"⏳ **VEREDICTO: MANTENER / EN ESPERA** — Cotiza un +{f_num(pct_actual_vs_media, 1)}% sobre su Precio Justo.")

    # 2. CUADRÍCULA 2x2 RESPONSIVA CON PROTECCIÓN CONTRA TRADUCTOR DE CHROME
    color_actual = "#21c354" if precio_actual <= precio_compra else ("#ff4b4b" if precio_actual >= precio_venta else "#faca2b")
    txt_extra_actual = f"Descuento: {f_num(abs(pct_actual_vs_media), 1)}% vs Media" if pct_actual_vs_media <= 0 else f"Sobreprecio: +{f_num(pct_actual_vs_media, 1)}% vs Media"

    st.markdown(f"""
<div class="grid-precios-weiss notranslate" translate="no">
<div class="card-precio" style="border-top: 3px solid {color_actual};">
<span style="font-size: 0.85rem; color: #aaa;">Cotización en Vivo</span>
<span style="font-size: 1.75rem; font-weight: 800; color: {color_actual};">{f_num(precio_actual, 2)}{sym}</span>
<span style="font-size: 0.85rem; font-weight: 600; color: {color_actual};">Yield: {f_num(yield_actual, 2, '%')} ({f_num(yield_actual * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.78rem; color: #999; margin-top: 2px;">{txt_extra_actual} · Perc. {f_num(percentil_yield_actual, 0)}%</span>
</div>
<div class="card-precio" style="border-top: 3px solid #21c354;">
<span style="font-size: 0.85rem; color: #aaa;">Suelo Compra (Weiss)</span>
<span style="font-size: 1.75rem; font-weight: 800; color: #21c354;">{f_num(precio_compra, 2)}{sym}</span>
<span style="font-size: 0.85rem; font-weight: 600; color: #21c354;">Yield: {f_num(yield_infravalorado, 2, '%')} ({f_num(yield_infravalorado * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Suelo: {f_num(pct_infra_vs_media, 1)}% vs Media</span>
</div>
<div class="card-precio" style="border-top: 3px solid #faca2b;">
<span style="font-size: 0.85rem; color: #aaa;">Precio Justo ({años_analisis}A)</span>
<span style="font-size: 1.75rem; font-weight: 800; color: #faca2b;">{f_num(precio_justo, 2)}{sym}</span>
<span style="font-size: 0.85rem; font-weight: 600; color: #faca2b;">Yield: {f_num(yield_medio, 2, '%')} ({f_num(yield_medio * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Imán Reversión a la Media</span>
</div>
<div class="card-precio" style="border-top: 3px solid #ff4b4b;">
<span style="font-size: 0.85rem; color: #aaa;">Techo Venta (Weiss)</span>
<span style="font-size: 1.75rem; font-weight: 800; color: #ff4b4b;">{f_num(precio_venta, 2)}{sym}</span>
<span style="font-size: 0.85rem; font-weight: 600; color: #ff4b4b;">Yield: {f_num(yield_sobrevalorado, 2, '%')} ({f_num(yield_sobrevalorado * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.78rem; color: #999; margin-top: 2px;">Techo: +{f_num(pct_sobre_vs_media, 1)}% vs Media</span>
</div>
</div>
""", unsafe_allow_html=True)

    # 3. TERMÓMETRO VISUAL
    if precio_venta > precio_compra:
        pos_canal = ((precio_actual - precio_compra) / (precio_venta - precio_compra)) * 100
        pos_canal_clamp = max(2.0, min(98.0, pos_canal))
        if pos_canal > 100:
            etiqueta_pos = f"📍 <strong style='color:#ff4b4b;'>Posición: {f_num(pos_canal, 0)}% (Sobre Techo Venta)</strong>"
            borde_bola = "#ff4b4b"
        elif pos_canal < 0:
            etiqueta_pos = f"📍 <strong style='color:#21c354;'>Posición: {f_num(pos_canal, 0)}% (Bajo Suelo Compra)</strong>"
            borde_bola = "#21c354"
        else:
            etiqueta_pos = f"📍 <strong>Posición en Canal: {f_num(pos_canal, 0)}%</strong>"
            borde_bola = "#00d4ff"

        st.markdown(f"""
<div class="notranslate" translate="no" style="background: rgba(255,255,255,0.04); padding: 10px 14px; border-radius: 8px; margin-bottom: 16px;">
<div style="display:flex; justify-content:space-between; font-size:0.8rem; color:#bbb; margin-bottom:6px;">
<span>🟢 Suelo Compra ({f_num(precio_compra, 2)}{sym})</span>
<span>{etiqueta_pos}</span>
<span>🔴 Techo Venta ({f_num(precio_venta, 2)}{sym})</span>
</div>
<div style="position: relative; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #21c354 0%, #faca2b 50%, #ff4b4b 100%);">
<div style="position: absolute; left: {pos_canal_clamp:.1f}%; top: -5px; width: 20px; height: 20px; background: white; border: 4px solid {borde_bola}; border-radius: 50%; transform: translateX(-50%); box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>
</div>
</div>
""", unsafe_allow_html=True)

    # 4. BOGLE + REVERSIÓN WEISS
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
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="color: #aaa; font-size: 0.85rem;">Ecuación Bogle: Yield + Crecimiento ± Reversión Weiss</span>
<span class="{b_tot_cls}">CAGR Bruto: {f_num(retorno_bogle_bruto_anual, 1, '%', signo_pos=True)}/año</span>
</div>
<div style="font-size: 1.15rem; margin: 8px 0;">
<span style="color:#00d4ff; font-weight:bold;">{f_num(yield_actual, 2, '%')}</span> <span style="font-size:0.8rem; color:#888;">(Yield)</span> + 
<span style="color:#faca2b; font-weight:bold;">{f_num(crec_bogle, 1, '%', signo_pos=True)}</span> <span style="font-size:0.8rem; color:#888;">(Crec.)</span> 
<span style="color:{'#21c354' if reversion_weiss_anual_acotada >= 0 else '#ff4b4b'}; font-weight:bold;"> {signo_rev}{f_num(reversion_weiss_anual_acotada, 1, '%')}</span> <span style="font-size:0.8rem; color:#888;">(Reversión)</span> = 
<strong style="font-size: 1.45rem; color: white;">{f_num(retorno_bogle_neto_anual, 1, '%', signo_pos=True)} neto/año</strong>
</div>
<span style="font-size: 0.78rem; color: #999;">
Si en 5 años vuelve a su Yield Medio ({f_num(yield_medio, 2, '%')}), su cotización rondaría los <strong>{f_num(precio_estimado_5a, 2)}{sym}</strong> ({signo_rev}{f_num(reversion_weiss_anual_acotada, 1)}% anual por múltiplo).
</span>
</div>
""", unsafe_allow_html=True)

    with col_bog2:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="color: #aaa; font-size: 0.85rem;">🧮 Simulación de tu Orden de {f_num(capital_simulado, 0)}{sym}</span>
<span class="{b_rev_cls}">A 5 Años: {f_num(capital_final_5a, 0)}{sym} ({f_num(ganancia_neta_5a, 0, sym, signo_pos=True)})</span>
</div>
<div style="font-size: 0.9rem; color: #ddd; line-height: 1.5; margin-top: 4px;">
• <strong>Comprando HOY ({f_num(precio_actual, 2)}{sym}):</strong> {f_num(acc_hoy, 2)} títulos ➔ Renta neta: <strong style="color:#00d4ff;">{f_num(div_neto_hoy, 2)}{sym}/año</strong>.<br>
• <strong>Esperando al SUELO ({f_num(precio_compra, 2)}{sym}):</strong> {f_num(acc_suelo, 2)} títulos ➔ Renta neta: <strong style="color:#21c354;">{f_num(div_neto_suelo, 2)}{sym}/año</strong>.
</div>
</div>
""", unsafe_allow_html=True)

    # 5. GRÁFICO 1: WEISS
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

        estado_canal_txt = f"un <strong>{f_num(abs(pct_actual_vs_media), 1)}% por debajo</strong> de su Precio Justo ({f_num(precio_justo, 2)}{sym})" if pct_actual_vs_media <= 0 else f"un <strong>+{f_num(pct_actual_vs_media, 1)}% por encima</strong> de su Precio Justo ({f_num(precio_justo, 2)}{sym})"
        dist_compra_txt = f"ya cotiza un <strong>{f_num(abs(dist_suelo_pct), 1)}% por debajo de la línea verde</strong>" if dist_suelo_pct <= 0 else f"necesita caer un <strong>{f_num(dist_suelo_pct, 1)}% adicional</strong> para tocar la línea verde ({f_num(precio_compra, 2)}{sym})"

        st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
💡 <strong>Lectura en {ticker_symbol}:</strong> Hoy cotiza a <strong>{f_num(precio_actual, 2)}{sym}</strong> ({estado_canal_txt}) y {dist_compra_txt}. En los últimos {años_analisis} años ha tocado la zona de compra <strong>{toques_compra} veces</strong> y la de venta <strong>{toques_venta} veces</strong>. Su Yield actual (<strong>{f_num(yield_actual, 2, '%')}</strong>) supera al <strong>{f_num(percentil_yield_actual, 1)}%</strong> de las sesiones históricas.
</div>
""", unsafe_allow_html=True)

    # 6. GRÁFICO 2: LUPA DE FRANCOTIRADOR
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

            txt_s200 = f"a un <strong>{f_num(((precio_actual - ult_sma200)/ult_sma200)*100, 1, signo_pos=True)}%</strong> de su SMA 200 ({f_num(ult_sma200, 2)}{sym})" if ult_sma200 else ""
            txt_s1000 = f"y a un <strong>{f_num(((precio_actual - ult_sma1000)/ult_sma1000)*100, 1, signo_pos=True)}%</strong> de su SMA 1000 ({f_num(ult_sma1000, 2)}{sym})" if ult_sma1000 else ""
            estado_macd = "alcista" if ult_macd > ult_signal else ("bajista perdiendo fuerza" if ult_hist > penult_hist else "bajista")
            estado_rsi = "en sobreventa (<32)" if ult_rsi <= 32 else ("en sobrecompra (>70)" if ult_rsi >= 70 else "en zona neutral")

            st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
💡 <strong>Lectura Técnica:</strong> Cotiza {txt_s200} {txt_s1000}. RSI en <strong>{f_num(ult_rsi, 1)}</strong> ({estado_rsi}) y MACD <strong>{estado_macd}</strong>. Volumen reciente de <strong>{f_num(ratio_vol, 2)}x</strong> sobre la media.
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

st.session_state.ticker_activo = ticker_input
st.session_state.años_activo = años_analisis
st.session_state.impuesto_activo = impuesto
st.session_state.capital_activo = capital_simulado
st.session_state.merma_activa = aplicar_merma

if st.button("🚀 Analizar / Actualizar Cotización en Vivo", use_container_width=True):
    cargar_cotizacion_tiempo_real.clear()
    cargar_fundamentales_pesados.clear()
    st.session_state.analizar_activo = True

if st.session_state.analizar_activo:
    with st.spinner(f"Actualizando cotización en vivo y métricas de {ticker_input}..."):
        try:
            render_valoracion_bogle(ticker_input, años_analisis, impuesto, aplicar_merma, capital_simulado)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
