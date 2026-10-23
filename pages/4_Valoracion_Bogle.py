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
    'Technology': 'Tecnología', 'Information Technology': 'Tecnología',
    'Healthcare': 'Salud', 'Financial Services': 'Servicios Financieros', 'Financials': 'Servicios Financieros',
    'Consumer Cyclical': 'Consumo Cíclico', 'Consumer Discretionary': 'Consumo Cíclico',
    'Industrials': 'Industrial', 'Consumer Defensive': 'Consumo Defensivo', 'Consumer Staples': 'Consumo Defensivo',
    'Energy': 'Energía', 'Real Estate': 'Inmobiliario', 'Utilities': 'Servicios Públicos',
    'Basic Materials': 'Materiales Básicos', 'Materials': 'Materiales Básicos',
    'Communication Services': 'Servicios de Comunicación'
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

    if not info.get('sector') or not info.get('shortName'):
        try:
            busq = yf.Search(ticker_symbol, max_results=1).quotes
            if busq and len(busq) > 0:
                q0 = busq[0]
                if not info.get('shortName'):
                    info['shortName'] = q0.get('shortname') or q0.get('longname') or ticker_symbol
                if not info.get('sector') and q0.get('sector'):
                    info['sector'] = q0.get('sector')
                if not info.get('industry') and q0.get('industry'):
                    info['industry'] = q0.get('industry')
        except Exception:
            pass

    divs = t.dividends

    inc_stmt, bs_stmt, cf_stmt = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        if t.income_stmt is not None and not t.income_stmt.empty:
            inc_stmt = t.income_stmt.T.sort_index().T
    except Exception:
        pass
    try:
        if t.balance_sheet is not None and not t.balance_sheet.empty:
            bs_stmt = t.balance_sheet.T.sort_index().T
    except Exception:
        pass
    try:
        if t.cashflow is not None and not t.cashflow.empty:
            cf_stmt = t.cashflow.T.sort_index().T
    except Exception:
        pass

    shares_hist = None
    try:
        shares_hist = t.get_shares_full(start="2008-01-01")
    except Exception:
        pass

    curr_cot = info.get('currency')
    if not curr_cot:
        try:
            curr_cot = t.fast_info.currency or 'USD'
        except Exception:
            curr_cot = 'USD'
        info['currency'] = curr_cot

    curr_Base = 'GBP' if curr_cot == 'GBp' else curr_cot
    curr_fin = info.get('financialCurrency', curr_Base) or curr_Base
    if curr_fin == 'GBp':
        curr_fin = 'GBP'

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
    except Exception:
        pass
    try:
        shares_fast = float(t.fast_info.shares)
    except Exception:
        pass
    try:
        mcap_fast = float(t.fast_info.market_cap)
    except Exception:
        pass
    return hist, precio_vivo, shares_fast, mcap_fast

def interpolar_puntos(valor, umbral_max, umbral_med, pts_max, pts_med, inverso=False):
    if valor is None or pd.isna(valor):
        return 0.0
    if not inverso:
        if valor >= umbral_max:
            return float(pts_max)
        if valor < umbral_med:
            return 0.0
        if umbral_max == umbral_med:
            return float(pts_max)
        ratio = (valor - umbral_med) / (umbral_max - umbral_med)
        return round(float(pts_med + ratio * (pts_max - pts_med)), 2)
    else:
        if valor < 0:
            return 0.0
        if valor <= umbral_max:
            return float(pts_max)
        if valor > umbral_med:
            return 0.0
        if umbral_med == umbral_max:
            return float(pts_max)
        ratio = (umbral_med - valor) / (umbral_med - umbral_max)
        return round(float(pts_med + ratio * (pts_max - pts_med)), 2)

def serie_historica_tabla(df, claves, fx_rate=1.0):
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    s_yearly = s.groupby(pd.to_datetime(s.index).year).last().sort_index()
                    return s_yearly.astype(float) * fx_rate
    return pd.Series(dtype=float)

def ultimo_valor_tabla(df, claves):
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    return float(s.iloc[-1])
    return 0.0

def procesar_dividendos_robusto(dividendos, ticker_symbol, año_actual, precio_actual, es_peniques_uk, fd_info):
    es_europea = any(ticker_symbol.endswith(suf) for suf in ['.MC', '.PA', '.DE', '.AS', '.MI', '.LS', '.SW', '.BR', '.HE'])
    divs_clean = dividendos.copy()

    if es_europea and len(divs_clean) > 2:
        fechas = divs_clean.index
        valores = divs_clean.values
        keep_idx = []
        i = 0
        while i < len(valores):
            if i < len(valores) - 1 and (fechas[i + 1] - fechas[i]).days <= 12:
                if valores[i + 1] >= valores[i]:
                    keep_idx.append(i + 1)
                else:
                    keep_idx.append(i)
                i += 2
            else:
                keep_idx.append(i)
                i += 1
        divs_clean = divs_clean.iloc[keep_idx]

    divs_por_año = divs_clean.groupby(divs_clean.index.year).sum()

    años_div = divs_clean.index.year
    conteo_por_año = años_div.value_counts()
    conteo_closed = conteo_por_año[(conteo_por_año.index < año_actual) & (conteo_por_año.index >= año_actual - 5)]
    if conteo_closed.empty:
        conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    mediana_pagos_año = float(conteo_closed.median()) if not conteo_closed.empty else 4.0

    if mediana_pagos_año >= 10:
        pagos_por_año = 12
    elif mediana_pagos_año >= 3:
        pagos_por_año = 4
    elif mediana_pagos_año >= 1.5:
        pagos_por_año = 2
    else:
        pagos_por_año = 1

    divs_para_bandas = divs_por_año.copy()
    años_cerrados = divs_para_bandas[divs_para_bandas.index < año_actual]
    if es_europea and len(años_cerrados) >= 5:
        mediana_5a = float(años_cerrados.tail(6).median())
        for y in años_cerrados.index:
            if divs_para_bandas.loc[y] > mediana_5a * 1.45:
                vecinos = [divs_para_bandas.loc[v] for v in [y - 1, y - 2, y + 1] if v in años_cerrados.index and divs_para_bandas.loc[v] <= mediana_5a * 1.45]
                if vecinos:
                    divs_para_bandas.loc[y] = float(np.max(vecinos)) * 1.05

    if es_peniques_uk and fd_info > (precio_actual * 0.25):
        fd_info /= 100.0

    ultimo_año_cerrado = float(años_cerrados.iloc[-1]) if not años_cerrados.empty else 0.0
    ultimo_año_bandas = float(divs_para_bandas[divs_para_bandas.index < año_actual].iloc[-1]) if not años_cerrados.empty else 0.0

    ult_fecha_div = divs_clean.index[-1]
    div_ttm_real = float(divs_clean[divs_clean.index > (ult_fecha_div - pd.DateOffset(days=370))].sum())

    if es_europea or pagos_por_año in [1, 2]:
        ref_anual_real = max(div_ttm_real, ultimo_año_bandas)
        if fd_info <= 0 or fd_info < (ref_anual_real * 0.65):
            forward_dividend = ref_anual_real
        elif fd_info > (ultimo_año_bandas * 1.45):
            forward_dividend = ultimo_año_bandas
        else:
            forward_dividend = fd_info
    else:
        ult_cupon_anualizado = float(divs_clean.iloc[-1]) * pagos_por_año
        if fd_info <= 0 or abs(ult_cupon_anualizado - fd_info) / max(1.0, ult_cupon_anualizado) > 0.25:
            forward_dividend = max(ult_cupon_anualizado, ultimo_año_cerrado)
        else:
            forward_dividend = fd_info

    return divs_por_año, divs_para_bandas, forward_dividend, pagos_por_año

# ==========================================
# FUNCIÓN PRINCIPAL: WEISS + DGI MODERNO
# ==========================================
def render_valoracion_bogle(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    info, dividendos_raw, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin = cargar_fundamentales_pesados(ticker_symbol)
    historial_raw, precio_vivo, shares_fast, mcap_fast = cargar_cotizacion_tiempo_real(ticker_symbol)

    if dividendos_raw.empty or len(historial_raw) < 252:
        st.error("❌ Error: No hay suficientes datos históricos o de dividendos en Yahoo Finance.")
        return

    def get_safe(key, default=0.0):
        val = info.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    st.markdown("""
<style>
.grid-precios-weiss {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}
@media (max-width: 992px) {
    .grid-precios-weiss {
        grid-template-columns: repeat(2, 1fr);
    }
}
.card-precio {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 11px 13px;
    display: flex;
    flex-direction: column;
}
.card-dgi {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 12px;
}
.pilar-box {
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
}
.barra-fondo {
    width: 100%;
    height: 7px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    overflow: hidden;
    margin: 5px 0;
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
.badge-verde { background: rgba(33, 195, 84, 0.2); color: #21c354; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.80rem; white-space: nowrap; }
.badge-rojo { background: rgba(255, 75, 75, 0.2); color: #ff4b4b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.80rem; white-space: nowrap; }
.badge-ambar { background: rgba(250, 202, 43, 0.2); color: #faca2b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.80rem; white-space: nowrap; }
.badge-azul { background: rgba(0, 212, 255, 0.2); color: #00d4ff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.80rem; white-space: nowrap; }
.badge-morado { background: rgba(224, 64, 251, 0.2); color: #e040fb; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.80rem; white-space: nowrap; }
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

    sector_en = info.get('sector', 'General')
    industry_en = info.get('industry', 'General')
    pais = info.get('country', 'Desconocido')
    if pais == 'Desconocido' and ticker_symbol.endswith('.MC'):
        pais = 'Spain'
    nombre_empresa = info.get('shortName', ticker_symbol)
    sector_final = TRADUCCION.get(sector_en, sector_en)

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'telecom' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'consumer staples' in sector_en.lower() or 'healthcare' in sector_en.lower()

    merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
    net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

    # ==========================================
    # CANALES WEISS CON ZONA DE ACUMULACIÓN P90
    # ==========================================
    fd_info = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    divs_por_año, divs_para_bandas, forward_dividend, pagos_por_año = procesar_dividendos_robusto(
        dividendos, ticker_symbol, año_actual, precio_actual, es_peniques_uk, fd_info
    )

    nombre_frecuencia = {1: "anual", 2: "semestral", 4: "trimestral", 12: "mensual"}.get(pagos_por_año, "periódico")

    historial_analisis['Year'] = historial_analisis.index.year
    historial_analisis['Div_Anual'] = historial_analisis['Year'].map(divs_para_bandas)
    historial_analisis.loc[historial_analisis['Year'] == año_actual, 'Div_Anual'] = forward_dividend
    historial_analisis['Div_Anual'] = historial_analisis['Div_Anual'].bfill().ffill()

    historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
    historial_analisis.replace([np.inf, -np.inf], np.nan, inplace=True)

    yields_validos = historial_analisis['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]

    # Percentiles: Suelo Estricto P95, Acumulación P90 (con margen real), Media, Precaución P20, Techo P05
    yield_infravalorado = float(yields_validos.quantile(0.95))
    yield_acumulacion = float(yields_validos.quantile(0.90))
    yield_medio = float(yields_validos.mean())
    yield_precaucion = float(yields_validos.quantile(0.20))
    yield_sobrevalorado = float(yields_validos.quantile(0.05))

    yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0
    percentil_yield_actual = float((yields_validos < yield_actual).mean() * 100)

    # ==========================================
    # EXTRACCIÓN FORENSE DE ESTADOS FINANCIEROS
    # ==========================================
    shares = get_safe('sharesOutstanding', 0.0)
    if shares <= 0 and shares_fast:
        shares = shares_fast
    if shares <= 0:
        shares = ultimo_valor_tabla(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'])

    s_rev = serie_historica_tabla(inc_stmt, ['Total Revenue', 'Operating Revenue'], fx_rate)
    s_ebit = serie_historica_tabla(inc_stmt, ['Operating Income', 'EBIT'], fx_rate)
    s_ebitda = serie_historica_tabla(inc_stmt, ['EBITDA', 'Normalized EBITDA', 'Operating Income'], fx_rate)
    s_net_inc = serie_historica_tabla(inc_stmt, ['Net Income', 'Net Income Common Stockholders'], fx_rate)
    s_eps = serie_historica_tabla(inc_stmt, ['Diluted EPS', 'Basic EPS'], fx_rate)
    s_shares = serie_historica_tabla(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'], 1.0)
    s_ocf = serie_historica_tabla(cf_stmt, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'], fx_rate)
    s_fcf = serie_historica_tabla(cf_stmt, ['Free Cash Flow'], fx_rate)
    s_capex = serie_historica_tabla(cf_stmt, ['Capital Expenditure', 'Capital Expenditures'], fx_rate)
    s_debt = serie_historica_tabla(bs_stmt, ['Total Debt', 'Long Term Debt And Capital Lease Obligation', 'Long Term Debt'], fx_rate)
    s_cash = serie_historica_tabla(bs_stmt, ['Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents', 'Cash'], fx_rate)
    s_equity = serie_historica_tabla(bs_stmt, ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity'], fx_rate)

    if s_fcf.empty and not s_ocf.empty and not s_capex.empty:
        common_cf = s_ocf.index.intersection(s_capex.index)
        if not common_cf.empty:
            s_fcf = s_ocf.loc[common_cf] - s_capex.loc[common_cf].abs()

    bpa_trailing = get_safe('trailingEps', 0.0)
    if bpa_trailing == 0 and not s_eps.empty:
        bpa_trailing = float(s_eps.iloc[-1])

    per_actual = get_safe('trailingPE', 0.0)
    if per_actual <= 0 and bpa_trailing > 0:
        per_actual = precio_actual / bpa_trailing
    per_forward = get_safe('forwardPE', 0.0)
    per = per_actual if per_actual > 0 else per_forward

    payout_ratio = get_safe('payoutRatio', 0.0) * 100
    if (payout_ratio <= 0 or payout_ratio > 300) and bpa_trailing > 0:
        payout_ratio = (forward_dividend / bpa_trailing) * 100

    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    if total_debt <= 0 and not s_debt.empty:
        total_debt = float(s_debt.iloc[-1])

    total_cash = get_safe('totalCash', 0.0) * fx_rate
    if total_cash <= 0 and not s_cash.empty:
        total_cash = float(s_cash.iloc[-1])

    ebitda = get_safe('ebitda', 0.0) * fx_rate
    if ebitda <= 0 and not s_ebitda.empty:
        ebitda = float(s_ebitda.iloc[-1])

    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    if fcf_raw == 0 and not s_fcf.empty:
        fcf_raw = float(s_fcf.iloc[-1])

    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    if ocf_raw == 0 and not s_ocf.empty:
        ocf_raw = float(s_ocf.iloc[-1])

    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw

    total_equity_raw = get_safe('totalStockholderEquity', 0.0) * fx_rate
    if total_equity_raw == 0 and not s_equity.empty:
        total_equity_raw = float(s_equity.iloc[-1])

    net_inc_val = float(s_net_inc.iloc[-1]) if not s_net_inc.empty else (get_safe('netIncomeToCommon', 0.0) * fx_rate)
    roe = get_safe('returnOnEquity', 0.0) * 100
    if roe == 0 and total_equity_raw > 0 and net_inc_val > 0:
        roe = (net_inc_val / total_equity_raw) * 100

    ebit_tabla = float(s_ebit.iloc[-1]) if not s_ebit.empty else (get_safe('operatingIncome', 0.0) * fx_rate)
    rev_tabla = float(s_rev.iloc[-1]) if not s_rev.empty else (get_safe('totalRevenue', 0.0) * fx_rate)
    operating_margins = get_safe('operatingMargins', 0.0) * 100
    if operating_margins == 0 and rev_tabla > 0 and ebit_tabla > 0:
        operating_margins = (ebit_tabla / rev_tabla) * 100

    fcf_margin_pct = (flujo_caja_referencia / rev_tabla) * 100 if (rev_tabla > 0 and flujo_caja_referencia != 0) else None
    cash_conversion_pct = (ocf_raw / net_inc_val) * 100 if (net_inc_val > 0 and ocf_raw > 0) else None

    price_to_book = get_safe('priceToBook', -1)
    if price_to_book <= 0 and total_equity_raw > 0 and shares > 0:
        price_to_book = precio_actual / (total_equity_raw / shares)

    current_ratio = get_safe('currentRatio', 0.0)
    if current_ratio <= 0 and not bs_stmt.empty:
        ca = ultimo_valor_tabla(bs_stmt, ['Current Assets', 'Total Current Assets'])
        cl = ultimo_valor_tabla(bs_stmt, ['Current Liabilities', 'Total Current Liabilities'])
        if cl > 0:
            current_ratio = ca / cl

    es_quasi_reit_o_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 22.0) and (total_equity_raw <= 0 or price_to_book < 0)
    es_regulada_o_reit = es_reit_puro or es_utility_pura or es_quasi_reit_o_recompras

    payout_limite_fcf = 75.0 if es_regulada_o_reit else 55.0
    payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 80.0

    deuda_neta = max(0.0, total_debt - total_cash)
    deuda_ebitda = (deuda_neta / ebitda) if ebitda > 0 else (999.0 if (total_debt > 0 and not es_financiera) else 0.0)

    crecimiento_bpa_3y = None
    if len(s_eps) >= 4 and s_eps.iloc[-4] > 0 and s_eps.iloc[-1] > 0:
        crecimiento_bpa_3y = (((float(s_eps.iloc[-1]) / float(s_eps.iloc[-4])) ** (1 / 3)) - 1) * 100
    elif len(s_eps) >= 2 and s_eps.iloc[0] > 0 and s_eps.iloc[-1] > 0:
        n_e = max(1, int(s_eps.index[-1] - s_eps.index[0]))
        crecimiento_bpa_3y = (((float(s_eps.iloc[-1]) / float(s_eps.iloc[0])) ** (1 / n_e)) - 1) * 100

    crecimiento_fcf_sh_3y = None
    s_caja_base = s_ocf if es_reit_puro else s_fcf
    if not s_caja_base.empty and not s_shares.empty:
        common_idx = s_caja_base.index.intersection(s_shares.index)
        if len(common_idx) >= 2:
            caja_sh = (s_caja_base.loc[common_idx] / s_shares.loc[common_idx]).sort_index()
            if caja_sh.iloc[0] > 0 and caja_sh.iloc[-1] > 0:
                n_c = max(1, int(caja_sh.index[-1] - caja_sh.index[0]))
                crecimiento_fcf_sh_3y = (((float(caja_sh.iloc[-1]) / float(caja_sh.iloc[0])) ** (1 / n_c)) - 1) * 100

    roic = None
    try:
        ebit_val = ebit_tabla
        inv_cap = (total_debt + max(0.0, total_equity_raw)) - total_cash
        if inv_cap <= 0 and not bs_stmt.empty and 'Total Assets' in bs_stmt.index:
            tot_assets = float(bs_stmt.loc['Total Assets'].dropna().iloc[-1]) * fx_rate
            curr_liab = float(bs_stmt.loc['Current Liabilities'].dropna().iloc[-1]) * fx_rate if 'Current Liabilities' in bs_stmt.index else 0.0
            inv_cap = tot_assets - curr_liab - total_cash
        if inv_cap > 0 and ebit_val > 0:
            roic = ((ebit_val * 0.79) / inv_cap) * 100
    except Exception:
        pass

    estabilidad_margen_ok = True
    caida_margen_bps = 0.0
    if not s_ebit.empty and not s_rev.empty:
        idx_m = s_ebit.index.intersection(s_rev.index)
        if len(idx_m) >= 3:
            s_margenes = (s_ebit.loc[idx_m] / s_rev.loc[idx_m]) * 100
            caida_margen_bps = float(s_margenes.iloc[-1] - s_margenes.iloc[0])
            if caida_margen_bps < -4.0:
                estabilidad_margen_ok = False

    revenue_cagr_3y = None
    if len(s_rev) >= 4 and s_rev.iloc[-4] > 0 and s_rev.iloc[-1] > 0:
        revenue_cagr_3y = (((float(s_rev.iloc[-1]) / float(s_rev.iloc[-4])) ** (1 / 3)) - 1) * 100
    elif len(s_rev) >= 2 and s_rev.iloc[0] > 0 and s_rev.iloc[-1] > 0:
        n_r = max(1, int(s_rev.index[-1] - s_rev.index[0]))
        revenue_cagr_3y = (((float(s_rev.iloc[-1]) / float(s_rev.iloc[0])) ** (1 / n_r)) - 1) * 100

    cobertura_intereses = None
    if not inc_stmt.empty:
        try:
            ebit_cov, int_exp = None, None
            claves_op = ['EBITDA', 'Normalized EBITDA', 'Operating Income'] if es_reit_puro else ['Operating Income', 'EBIT']
            for k in claves_op:
                if k in inc_stmt.index:
                    ebit_cov = float(inc_stmt.loc[k].dropna().iloc[-1])
                    break
            for k in ['Interest Expense', 'Interest Expense Non Operating']:
                if k in inc_stmt.index:
                    int_exp = abs(float(inc_stmt.loc[k].dropna().iloc[-1]))
                    break
            if ebit_cov is not None and int_exp is not None and int_exp > 0:
                cobertura_intereses = ebit_cov / int_exp
        except Exception:
            pass

    payout_fcf, p_fcf, fcf_per_share = -1, -1, 0.0
    if flujo_caja_referencia != 0 and shares > 0:
        fcf_per_share = flujo_caja_referencia / shares
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
        else:
            payout_fcf = 999.0

    # ==========================================
    # MÉTRICAS DE HISTORIAL, CONSISTENCIA Y ACELERACIÓN
    # ==========================================
    dividendos_barras = divs_para_bandas.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = forward_dividend
    else:
        dividendos_barras.loc[año_actual] = forward_dividend

    años_pagando = int(año_actual - dividendos_barras.index[0]) if not dividendos_barras.empty else 0
    dgr_1y, dgr_3y, dgr_5y, dgr_10y, dgr_periodo = None, None, None, None, None

    if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
        dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
    if len(dividendos_barras) >= 4 and dividendos_barras.iloc[-4] > 0:
        dgr_3y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-4]) ** (1 / 3) - 1) * 100
    if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
        dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1 / 5) - 1) * 100
    if len(dividendos_barras) >= 11 and dividendos_barras.iloc[-11] > 0:
        dgr_10y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-11]) ** (1 / 10) - 1) * 100
    if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
        dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1 / años_analisis) - 1) * 100

    regularidad_div_r2 = 0.0
    try:
        div_recientes = dividendos_barras.tail(min(11, len(dividendos_barras)))
        div_pos = div_recientes[div_recientes > 0]
        if len(div_pos) >= 5:
            x_vals = np.arange(len(div_pos))
            y_vals = np.log(div_pos.values.astype(float))
            if np.std(y_vals) > 1e-6:
                corr_m = np.corrcoef(x_vals, y_vals)[0, 1]
                if corr_m > 0:
                    regularidad_div_r2 = float(corr_m ** 2) * 100
    except Exception:
        regularidad_div_r2 = 50.0

    dgr_base_largo = dgr_5y if dgr_5y is not None else dgr_periodo
    ratio_aceleracion_div = (dgr_1y / dgr_base_largo) if (dgr_1y is not None and dgr_base_largo is not None and dgr_base_largo > 1.5) else 1.0
    fatiga_dividendo = bool(dgr_1y is not None and dgr_base_largo is not None and dgr_base_largo > 2.5 and (dgr_1y / dgr_base_largo) < 0.48)

    aviso_extraordinario = False
    if len(divs_por_año) >= 4:
        mediana_reciente = divs_por_año.iloc[-4:-1].median()
        ultimo_div = divs_por_año.iloc[-1]
        if mediana_reciente > 0 and (ultimo_div / mediana_reciente) > 1.35:
            aviso_extraordinario = True

    racha_sin_recortes = 0
    racha_incrementos_puros = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-i] >= dividendos_barras.iloc[-(i + 1)] * 0.98:
                racha_sin_recortes += 1
            else:
                break
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-i] > dividendos_barras.iloc[-(i + 1)] * 1.002:
                racha_incrementos_puros += 1
            else:
                break

    variacion_acciones, recompras_anualizadas = None, 0.0
    if len(s_shares) >= 2:
        acc_ini, acc_fin = float(s_shares.iloc[0]), float(s_shares.iloc[-1])
        n_anios_sh = max(1, int(s_shares.index[-1] - s_shares.index[0]))
        if acc_ini > 0:
            variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
            recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100

    recompras_anualizadas = max(-8.0, min(8.0, recompras_anualizadas))
    shareholder_yield = yield_actual if (es_reit_puro and recompras_anualizadas < 0) else (yield_actual + recompras_anualizadas)

    # Precios de los Canales de Geraldine Weiss
    precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
    precio_acumulacion = (forward_dividend / yield_acumulacion) * 100 if yield_acumulacion > 0 else 0
    precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
    precio_precaucion = (forward_dividend / yield_precaucion) * 100 if yield_precaucion > 0 else 0
    precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

    pct_actual_vs_media = ((precio_actual - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_acum_vs_media = ((precio_acumulacion - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0
    dist_suelo_pct = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 0
    caida_necesaria_suelo_pct = ((precio_actual - precio_compra) / precio_actual) * 100 if precio_actual > 0 else 0

    # ==========================================
    # MOTOR DE CALIDAD BLUE-CHIP (5 PILARES AUDITABLES)
    # ==========================================
    # --- PILAR 1: SOLIDEZ DE BALANCE Y SOLVENCIA (Máx 2.0 pts) ---
    if es_reit_puro:
        lim_deuda_optima, lim_deuda_aceptable = 5.2, 6.8
    elif es_utility_pura or es_quasi_reit_o_recompras:
        lim_deuda_optima, lim_deuda_aceptable = 3.5, 5.0
    elif es_defensivo or es_telecom:
        lim_deuda_optima, lim_deuda_aceptable = 2.5, 3.8
    else:
        lim_deuda_optima, lim_deuda_aceptable = 1.8, 3.2

    if es_financiera:
        pts_deuda_base = interpolar_puntos(roe, 14.5, 8.0, 1.5, 0.3, inverso=False)
        pts_cob_base = 0.5 if (current_ratio >= 1.0 or roe >= 11.0) else 0.1
    else:
        pts_deuda_base = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable, 1.4, 0.25, inverso=True)
        umbral_cob_max = 3.2 if es_reit_puro else 7.5
        umbral_cob_min = 1.8 if es_reit_puro else 3.0
        pts_cob_base = interpolar_puntos(cobertura_intereses, umbral_cob_max, umbral_cob_min, 0.6, 0.1, inverso=False) if cobertura_intereses is not None else (0.6 if deuda_neta == 0 else 0.15)

    pilar1_pts = min(2.0, round(pts_deuda_base + pts_cob_base, 2))

    # --- PILAR 2: COBERTURA DE CAJA Y CALIDAD DEL BENEFICIO (Máx 2.5 pts) ---
    if es_financiera and payout_fcf == -1:
        pts_payout_caja = interpolar_puntos(payout_ratio, 45.0, 75.0, 1.6, 0.3, inverso=True) if payout_ratio > 0 else 0.0
    else:
        pts_payout_caja = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 1.6, 0.3, inverso=True) if 0 < payout_fcf < 500 else 0.0

    pts_calidad_beneficio = 0.0
    if es_reit_puro:
        pts_calidad_beneficio = 0.9 if (0 < payout_fcf <= 82.0) else (0.45 if (0 < payout_fcf <= 92.0) else 0.0)
    else:
        pts_eps_payout = interpolar_puntos(payout_ratio, 55.0 if not es_utility_pura else 72.0, 82.0 if not es_utility_pura else 90.0, 0.5, 0.1, inverso=True) if payout_ratio > 0 else 0.0
        pts_conv = interpolar_puntos(cash_conversion_pct, 105.0, 80.0, 0.4, 0.1, inverso=False) if cash_conversion_pct is not None else 0.2
        pts_calidad_beneficio = pts_eps_payout + pts_conv

    pilar2_pts = min(2.5, round(pts_payout_caja + pts_calidad_beneficio, 2))

    # --- PILAR 3: FOSO ECONÓMICO (MOAT), ROIC Y MÁRGENES (Máx 2.0 pts) ---
    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
    if es_reit_puro:
        pts_roic_sub = interpolar_puntos(operating_margins, 35.0, 20.0, 0.9, 0.25, inverso=False)
        pts_margen_fcf_sub = interpolar_puntos(fcf_margin_pct, 25.0, 12.0, 0.5, 0.15, inverso=False) if fcf_margin_pct is not None else 0.25
    else:
        pts_roic_sub = interpolar_puntos(metrica_rentabilidad, 15.5, 7.5, 0.9, 0.2, inverso=False) if metrica_rentabilidad is not None else 0.0
        pts_margen_fcf_sub = interpolar_puntos(fcf_margin_pct if fcf_margin_pct is not None else operating_margins, 15.0, 6.0, 0.5, 0.1, inverso=False)

    pts_rev_sub = interpolar_puntos(revenue_cagr_3y, 5.0, 1.0, 0.6, 0.1, inverso=False) if revenue_cagr_3y is not None else 0.0
    if not estabilidad_margen_ok:
        pts_rev_sub = max(0.0, pts_rev_sub - 0.25)

    pilar3_pts = min(2.0, round(pts_roic_sub + pts_margen_fcf_sub + pts_rev_sub, 2))

    # --- PILAR 4: HISTORIAL WEISS, REGULARIDAD Y CONSISTENCIA (Máx 2.0 pts) ---
    racha_efectiva = racha_sin_recortes + (4 if años_pagando >= 25 else (2 if años_pagando >= 15 else 0))
    pts_racha = interpolar_puntos(racha_efectiva, 20.0, 6.0, 1.0, 0.25, inverso=False)
    pts_dgr_base = interpolar_puntos(dgr_5y if dgr_5y is not None else dgr_3y, 7.5, 2.5, 0.7, 0.15, inverso=False)
    pts_reg_r2 = interpolar_puntos(regularidad_div_r2, 88.0, 55.0, 0.3, 0.05, inverso=False)

    pilar4_pts = min(2.0, round(pts_racha + pts_dgr_base + pts_reg_r2, 2))
    if fatiga_dividendo:
        pilar4_pts = max(0.0, round(pilar4_pts - 0.35, 2))

    # --- PILAR 5: ASIGNACIÓN DE CAPITAL Y CRECIMIENTO POR ACCIÓN (Máx 1.5 pts) ---
    if es_reit_puro:
        crec_reit_ref = crecimiento_fcf_sh_3y if crecimiento_fcf_sh_3y is not None else (dgr_5y or 0.0)
        pilar5_pts = interpolar_puntos(crec_reit_ref, 4.5, 1.0, 1.5, 0.35, inverso=False)
    else:
        pts_recompra_sub = interpolar_puntos(recompras_anualizadas, 2.2, 0.2, 0.65, 0.15, inverso=False)
        crec_per_share_ref = crecimiento_fcf_sh_3y if (crecimiento_fcf_sh_3y is not None and crecimiento_bpa_3y is None) else crecimiento_bpa_3y
        if crecimiento_bpa_3y is not None and crecimiento_fcf_sh_3y is not None:
            crec_per_share_ref = max(crecimiento_bpa_3y, crecimiento_fcf_sh_3y * 0.85)
        pts_bpa_sub = interpolar_puntos(crec_per_share_ref, 7.0, 2.0, 0.85, 0.2, inverso=False) if crec_per_share_ref is not None else 0.0
        pilar5_pts = min(1.5, round(pts_recompra_sub + pts_bpa_sub, 2))

    # Banderas Rojas y Safety Score
    banderas_rojas = []
    penalizacion_calidad = 0.0

    if not es_financiera and payout_fcf > 100.0:
        banderas_rojas.append(f"🚨 **Dividendo No Cubierto por Caja (Payout FCF: {f_num(payout_fcf, 0)}%):** Paga más en dividendos de lo que genera en FCF, financiándolo con deuda o caja.")
        penalizacion_calidad += 1.0
    elif not es_financiera and payout_fcf > payout_amarillo_fcf:
        banderas_rojas.append(f"⚠️ **Payout FCF Ajustado ({f_num(payout_fcf, 0)}%):** Margen de maniobra estrecho ante una desaceleración económica.")
        penalizacion_calidad += 0.3

    crec_fund_comp = crecimiento_fcf_sh_3y if es_reit_puro else crecimiento_bpa_3y
    if dgr_5y is not None and crec_fund_comp is not None and dgr_5y > 4.0 and (dgr_5y - crec_fund_comp) > 5.5 and payout_fcf > 68.0:
        banderas_rojas.append(f"⚠️ **Crecimiento por Expansión de Payout:** El dividendo sube al {f_num(dgr_5y, 1)}%/año pero el negocio solo al {f_num(crec_fund_comp, 1)}%/año.")
        penalizacion_calidad += 0.4

    if dgr_1y is not None and dgr_1y < 0.0:
        banderas_rojas.append(f"🚨 **Recorte o Merma Reciente del Dividendo ({f_num(dgr_1y, 1)}%):** Ruptura de la regla de oro de Geraldine Weiss.")
        penalizacion_calidad += 1.2
    elif fatiga_dividendo:
        banderas_rojas.append(f"⚠️ **Fatiga del Dividendo:** La última subida ({f_num(dgr_1y, 1)}%) es menos de la mitad de su media quinquenal ({f_num(dgr_5y, 1)}%).")

    if not es_reit_puro and recompras_anualizadas < -1.8:
        banderas_rojas.append(f"⚠️ **Dilución del Accionista ({f_num(-recompras_anualizadas, 1)}%/año más de acciones):** Emisión recurrente diluyendo la participación.")
        penalizacion_calidad += 0.4
    elif es_reit_puro and recompras_anualizadas < -4.0 and (crecimiento_fcf_sh_3y is not None and crecimiento_fcf_sh_3y < 0.5):
        banderas_rojas.append(f"🚨 **Dilución Destructiva en REIT:** Emite acciones al {f_num(-recompras_anualizadas, 1)}%/año sin lograr crecimiento de FFO/acc ({f_num(crecimiento_fcf_sh_3y, 1)}%).")
        penalizacion_calidad += 0.8

    if not es_financiera and cobertura_intereses is not None and cobertura_intereses < (1.6 if es_reit_puro else 2.5):
        banderas_rojas.append(f"🚨 **Presión por Intereses de Deuda (Cobertura {f_num(cobertura_intereses, 1)}x):** Los costes financieros consumen gran parte del beneficio operativo.")
        penalizacion_calidad += 0.7

    score_calidad_bruto = pilar1_pts + pilar2_pts + pilar3_pts + pilar4_pts + pilar5_pts
    score_calidad = max(1.0, min(10.0, round(score_calidad_bruto - penalizacion_calidad, 1)))

    safety_pts = int(round(
        (pilar1_pts / 2.0) * 30.0 +
        (pilar2_pts / 2.5) * 35.0 +
        (pilar4_pts / 2.0) * 20.0 +
        (pilar3_pts / 2.0) * 15.0 -
        (penalizacion_calidad * 12.0)
    ))
    safety_score = max(5, min(99, safety_pts))

    if safety_score >= 81:
        safety_label, safety_color, safety_cls = "MUY SEGURO", "#21c354", "badge-verde"
    elif safety_score >= 61:
        safety_label, safety_color, safety_cls = "SEGURO", "#00d4ff", "badge-azul"
    elif safety_score >= 41:
        safety_label, safety_color, safety_cls = "EN EL LÍMITE (VIGILAR)", "#faca2b", "badge-ambar"
    else:
        safety_label, safety_color, safety_cls = "ALTO RIESGO DE RECORTE", "#ff4b4b", "badge-rojo"

    if racha_sin_recortes >= 45 or años_pagando >= 50:
        estatus_div_txt = "👑 Dividend King / Histórico (>45A)"
    elif racha_sin_recortes >= 25:
        estatus_div_txt = "🛡️ Dividend Aristocrat / Champion (25+ Años)"
    elif racha_sin_recortes >= 10:
        estatus_div_txt = "⚔️ Dividend Contender (10-24 Años)"
    elif racha_sin_recortes >= 5:
        estatus_div_txt = "🌱 Dividend Challenger (5-9 Años)"
    else:
        estatus_div_txt = "🔄 Racha Corta / Cíclica (<5 Años)"

    dgr_ref_arq = dgr_5y if dgr_5y is not None else (dgr_3y or 0.0)
    if yield_actual < 2.4 and dgr_ref_arq >= 8.5 and score_calidad >= 7.0:
        arquetipo_dgi = "🚀 Compounder de Alto Crecimiento"
        arquetipo_desc = "Baja rentabilidad inicial pero alta velocidad de capitalización y reinversión (ROIC elevado)."
    elif 2.2 <= yield_actual <= 4.8 and dgr_ref_arq >= 4.5 and score_calidad >= 6.5:
        arquetipo_dgi = "💎 Core Blue-Chip DGI (Zona Dulce Weiss)"
        arquetipo_desc = "Equilibrio ideal entre renta actual sólida y crecimiento compuesto superior a la inflación."
    elif yield_actual > 4.2 and dgr_ref_arq >= 1.5 and safety_score >= 55:
        arquetipo_dgi = "🐄 Vaca Lechera de Renta Alta (Generadora de Cash)"
        arquetipo_desc = "Prioriza el cobro inmediato de rentas elevadas con crecimiento moderado."
    else:
        arquetipo_dgi = "⚠️ En Observación / Crecimiento Lento o Cíclica"
        arquetipo_desc = "Exige comprar únicamente con gran margen de seguridad en el Suelo de Weiss."

    # ==========================================
    # VALORACIÓN, MÚLTIPLOS Y CHOWDER
    # ==========================================
    if yield_actual >= yield_infravalorado:
        pts_yield = 4.0
    elif yield_actual >= yield_medio:
        pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_medio, 4.0, 1.8, inverso=False)
    elif yield_actual >= yield_sobrevalorado:
        pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 1.8, 0.0, inverso=False)
    else:
        pts_yield = 0.0

    tasas_crec_negocio = [x for x in [dgr_5y, revenue_cagr_3y, crecimiento_bpa_3y] if x is not None]
    crec_negocio_val = float(np.median(tasas_crec_negocio)) if tasas_crec_negocio else 2.0
    if revenue_cagr_3y is not None and revenue_cagr_3y < 0.5:
        crec_negocio_val = min(crec_negocio_val, 1.5)

    prima_calidad_mult = 1.5 if score_calidad >= 8.0 else (0.0 if score_calidad >= 6.5 else -1.5)
    mult_optimo = float(np.clip(8.5 + max(0.0, crec_negocio_val) * 0.9 + prima_calidad_mult, 8.0, 18.5))
    mult_aceptable = mult_optimo + 7.0

    if es_financiera and p_fcf <= 0:
        pts_pfcf = interpolar_puntos(price_to_book, 1.1, 2.0, 2.5, 0.4, inverso=True) if price_to_book > 0 else 0.0
    else:
        pts_pfcf = interpolar_puntos(p_fcf, 15.0 if es_reit_puro else mult_optimo, 22.0 if es_reit_puro else mult_aceptable, 2.5, 0.4, inverso=True) if p_fcf > 0 else 0.0

    multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
    pts_per = interpolar_puntos(multiplo_per_eval, mult_optimo + 0.5, mult_aceptable + 1.0, 2.0, 0.3, inverso=True) if multiplo_per_eval > 0 else 0.0

    chowder_target = 8.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (12.0 if yield_actual >= 3.0 else 15.0)
    yield_req_chowder = None
    chowder_number = None
    chowder_neto = None
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        chowder_neto = (yield_actual * net_mult) + dgr_5y
        yield_req_chowder = chowder_target - dgr_5y
        if dgr_5y < 1.5 or (dgr_1y is not None and dgr_1y <= 0):
            pts_chowder = 0.0
        else:
            chowder_efectivo = min(yield_actual, 6.5) + dgr_5y
            pts_chowder = interpolar_puntos(chowder_efectivo, chowder_target, chowder_target - 3.0, 1.5, 0.3, inverso=False)
    else:
        pts_chowder = 0.0

    score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
    posible_trampa_valor = (precio_actual <= precio_acumulacion) and (score_calidad < 5.5 or safety_score < 45 or (not es_financiera and payout_fcf > 95.0) or (dgr_1y is not None and dgr_1y < -2.0))

    # ==========================================
    # PRECIO MÁXIMO DE ENTRADA SEGÚN DISCIPLINA GERALDINE WEISS
    # Según Geraldine Weiss, JAMÁS se compra a Precio Justo; se exige descuento contrastado
    # Para joyas de calidad élite, el precio máximo de entrada es la Zona de Acumulación (P90)
    # ==========================================
    if score_calidad >= 8.0 and safety_score >= 70:
        precio_objetivo_calidad = precio_acumulacion
        regla_entrada_calidad = "Calidad Élite (≥8,0): Según la disciplina de Geraldine Weiss jamás se compra a Precio Justo; el techo máximo de compra es la Zona de Acumulación (Percentil 90 de Yield) para garantizar descuento real."
    elif score_calidad >= 6.5 and safety_score >= 55:
        precio_objetivo_calidad = round((precio_acumulacion + precio_compra) / 2.0, 2)
        regla_entrada_calidad = "Calidad Sólida (6,5 - 7,9): Exige mayor margen de seguridad. Entrada óptima entre Zona de Acumulación (P90) y Suelo Estricto (P95)."
    else:
        precio_objetivo_calidad = precio_compra
        regla_entrada_calidad = "Calidad Moderada / Cíclica (<6,5): Exige Margen de Seguridad Máximo (Suelo Estricto P95 de Weiss). Prohibido comprar por encima del Suelo."

    # ==========================================
    # MOTOR BOGLE + PROYECCIONES DE RENDIMIENTO
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

    yoc_5a_bruto = yield_actual * ((1 + max(0.0, crec_bogle) / 100.0) ** 5)
    yoc_5a_neto = yoc_5a_bruto * net_mult
    yoc_10a_bruto = yield_actual * ((1 + max(0.0, crec_bogle) / 100.0) ** 10)
    yoc_10a_neto = yoc_10a_bruto * net_mult

    acc_hoy = capital_simulado / precio_actual if precio_actual > 0 else 0.0
    acc_enteras_hoy = int(capital_simulado // precio_actual) if precio_actual > 0 else 0
    sobrante_hoy = capital_simulado - (acc_enteras_hoy * precio_actual)
    div_bruto_hoy = acc_hoy * forward_dividend
    div_neto_hoy = div_bruto_hoy * net_mult
    cobro_por_pago_hoy = div_neto_hoy / pagos_por_año

    acc_suelo = capital_simulado / precio_compra if precio_compra > 0 else 0.0
    acc_enteras_suelo = int(capital_simulado // precio_compra) if precio_compra > 0 else 0
    div_bruto_suelo = acc_suelo * forward_dividend
    div_neto_suelo = div_bruto_suelo * net_mult
    cobro_por_pago_suelo = div_neto_suelo / pagos_por_año

    extra_anual_esperar = div_neto_suelo - div_neto_hoy
    anios_recuperar_1_pago = (cobro_por_pago_hoy / extra_anual_esperar) if extra_anual_esperar > 0.05 else 99.0

    divs_netos_acum_5a = sum([div_neto_hoy * ((1 + max(0.0, crec_bogle) / 100.0) ** a) for a in range(1, 6)])
    valor_acciones_5a_sin_reversion = capital_simulado * ((1 + (crec_bogle / 100.0)) ** 5)
    precio_estimado_5a_weiss = precio_justo * ((1 + (crec_bogle / 100.0)) ** 5)
    valor_acciones_5a_con_reversion = acc_hoy * precio_estimado_5a_weiss

    # ==========================================
    # CABECERA Y RESUMEN GENERAL
    # ==========================================
    if es_reit_puro:
        tipo_empresa_txt = "🏢 REIT / Inmobiliario (FFO)"
    elif es_quasi_reit_o_recompras:
        tipo_empresa_txt = "🍔 Franquicia / Recompras"
    elif es_financiera:
        tipo_empresa_txt = "🏦 Financiero / Seguros (ROE)"
    elif es_regulada_o_reit:
        tipo_empresa_txt = "⚡ Sector Regulado / Utility"
    else:
        tipo_empresa_txt = "🏭 Industrial / General"

    st.header(f"{nombre_empresa} ({ticker_symbol} · {currency}) — {tipo_empresa_txt}")

    txt_exdiv = "Último Ex-Div: " + dividendos.index[-1].strftime('%d/%m/%Y') if not dividendos.empty else "Sin fecha Ex-Div"
    ex_div_ts = info.get('exDividendDate')
    if pd.notna(ex_div_ts) and ex_div_ts is not None:
        try:
            ex_dt = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()
            dias_ex = (ex_dt - hoy_ts).days
            if dias_ex > 0:
                txt_exdiv = f"📅 Ex-Div en {dias_ex} días ({ex_dt.strftime('%d/%m/%Y')})"
            elif dias_ex == 0:
                txt_exdiv = f"🚨 ¡HOY es Ex-Dividend! ({ex_dt.strftime('%d/%m/%Y')})"
            else:
                txt_exdiv = f"Último Ex-Div: {ex_dt.strftime('%d/%m/%Y')} (hace {abs(dias_ex)}d)"
        except Exception:
            pass

    aviso_fx = f" | 💱 <strong>FX:</strong> {curr_fin}➔{currency} ({f_num(fx_rate, 3)})" if fx_rate != 1.0 else ""
    st.markdown(f"""
<div class="notranslate" translate="no" style="background-color: rgba(255, 255, 255, 0.05); padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 0.89rem; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px;">
<div>
<strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;|&nbsp; 
<strong>Estatus:</strong> <span style="color: #faca2b;">{estatus_div_txt}</span> &nbsp;|&nbsp; 
<span style="color: #e040fb; font-weight:600;">{txt_exdiv}</span> &nbsp;|&nbsp;
<strong>Shareholder Yield:</strong> <span style="color: #21c354; font-weight:bold;">{f_num(shareholder_yield, 2, '%')} bruto</span> <span style="font-size:0.80rem; color:#aaa;">({f_num(shareholder_yield * net_mult, 2, '%')} neto)</span>{aviso_fx}
</div>
<div>
<span class="{safety_cls}">🛡️ Seguridad Cupón: {safety_score}/100 ({safety_label})</span>
</div>
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
        st.info("ℹ️ **Dividendo Especial / Scrip Normalizado:** Se han detectado pagos extraordinarios o *scrip dividend* y se han normalizado a la tendencia ordinaria para no deformar los canales de Weiss.")

    # ==========================================
    # 1. PUNTUACIONES Y VEREDICTO GERALDINE WEISS
    # ==========================================
    col_sc1, col_sc2 = st.columns(2)
    with col_sc1:
        if score_calidad >= 8.0:
            st.success(f"🛡️ **CALIDAD BLUE-CHIP WEISS: {f_num(score_calidad, 1)}/10** — Negocio Sobresaliente, Foso Amplio y Caja Blindada.")
        elif score_calidad >= 6.0:
            st.warning(f"⚖️ **CALIDAD BLUE-CHIP WEISS: {f_num(score_calidad, 1)}/10** — Negocio Sólido. Apto exigiendo buen precio de entrada.")
        else:
            st.error(f"🚨 **CALIDAD BLUE-CHIP WEISS: {f_num(score_calidad, 1)}/10** — Calidad Baja / Fragilidad en Balance o Caja.")

    with col_sc2:
        if score_val >= 7.0:
            st.success(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Oportunidad Clara (Percentil {f_num(percentil_yield_actual, 0)}% de Yield Histórico).")
        elif score_val >= 4.2:
            st.warning(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Valoración Razonable / Acorde a su Crecimiento.")
        else:
            st.error(f"🏷️ **VALORACIÓN DGI: {f_num(score_val, 1)}/10** — Cotización Exigente o Sobrevalorada.")

    # Veredicto combinado Calidad + Disciplina Weiss
    if posible_trampa_valor:
        st.error("🚨 **VEREDICTO WEISS: ALERTA DE TRAMPA DE VALOR (VALUE TRAP)** — Aunque cotiza con Yield alto (Zona de Compra), incumple los pilares de calidad Blue-Chip de Geraldine Weiss (Calidad < 5,5 o Payout FCF crítico). El mercado descuenta un posible recorte del cupón.")
    elif precio_actual <= precio_compra and score_calidad >= 7.5:
        st.success(f"💎 **VEREDICTO WEISS: COMPRA FUERTE CONVICCIÓN MÁXIMA** — Empresa Blue-Chip de alta calidad ({f_num(score_calidad, 1)}/10) cotizando un {f_num(abs(dist_suelo_pct), 1)}% por debajo del Suelo Estricto de Weiss ({f_num(precio_compra, 2)}{sym}).")
    elif precio_actual <= precio_acumulacion and score_calidad >= 7.5:
        st.success(f"🟢 **VEREDICTO WEISS: ZONA DE ACUMULACIÓN BLUE-CHIP** — Excelente calidad ({f_num(score_calidad, 1)}/10) dentro del percentil 90 de rentabilidad histórica ({f_num(precio_acumulacion, 2)}{sym}). Margen de seguridad sólido para construir posición por tramos.")
    elif precio_actual <= precio_compra:
        st.warning(f"🟢 **VEREDICTO WEISS: EN SUELO DE COMPRA (CALIDAD MODERADA {f_num(score_calidad, 1)}/10)** — Cotiza por debajo de su Suelo ({f_num(precio_compra, 2)}{sym}), pero vigila las métricas de crecimiento y deuda.")
    elif precio_actual <= precio_justo and score_calidad >= 8.0:
        st.info(f"⏳ **VEREDICTO WEISS: ESPERAR DESCUENTO REAL (DISCIPLINA WEISS)** — Cotiza con leve descuento sobre su Precio Justo ({f_num(precio_justo, 2)}{sym}), pero según Geraldine Weiss jamás se compra a Precio Justo. Tu precio máximo de entrada es **{f_num(precio_objetivo_calidad, 2)}{sym}** (Zona Acumulación P90).")
    elif precio_actual <= precio_justo:
        st.warning(f"⏳ **VEREDICTO WEISS: DESCUENTO INSUFICIENTE — ESPERAR SUELO** — Cotiza por debajo de su Precio Justo ({f_num(precio_justo, 2)}{sym}), pero por su perfil de calidad ({f_num(score_calidad, 1)}/10) exige esperar a su Suelo ({f_num(precio_compra, 2)}{sym}).")
    elif precio_actual >= precio_venta:
        st.error(f"🔴 **VEREDICTO WEISS: ZONA DE SOBREVALORACIÓN EXTREMA** — Supera el Techo Histórico de Weiss ({f_num(precio_venta, 2)}{sym}). Prohibido comprar; valorar rotación si el negocio pierde fuelle.")
    else:
        st.info(f"⏳ **VEREDICTO WEISS: MANTENER EN CARTERA / PACIENCIA PARA COMPRAR** — Cotiza un +{f_num(abs(pct_actual_vs_media), 1)}% sobre su Precio Justo ({f_num(precio_justo, 2)}{sym}). Tu precio objetivo ajustado por calidad es **{f_num(precio_objetivo_calidad, 2)}{sym}**.")

    # ==========================================
    # 2. RADIOGRAFÍA FORENSE DE CALIDAD BLUE-CHIP (COLORES POR CRITERIO)
    # ==========================================
    st.markdown("### 🔬 Radiografía de Calidad Blue-Chip (Los 5 Pilares de Geraldine Weiss + DGI Moderno)")

    if banderas_rojas:
        for rf in banderas_rojas:
            st.warning(rf)

    col_q1, col_q2 = st.columns([1.15, 1])

    with col_q1:
        def render_barra_pilar(titulo, pts, max_pts, detalle_izq, detalle_der):
            pct = max(4.0, min(100.0, (pts / max_pts) * 100.0)) if max_pts > 0 else 0.0
            color_b = "#21c354" if pct >= 75 else ("#faca2b" if pct >= 50 else "#ff4b4b")
            return f"""
<div class="pilar-box notranslate" translate="no">
<div style="display:flex; justify-content:space-between; align-items:center; font-size:0.86rem; font-weight:700;">
<span style="color:#eee;">{titulo}</span>
<span style="color:{color_b};">{f_num(pts, 2)} / {f_num(max_pts, 1)} pts</span>
</div>
<div class="barra-fondo"><div style="width:{pct:.1f}%; height:100%; background:{color_b}; border-radius:4px;"></div></div>
<div style="display:flex; justify-content:space-between; font-size:0.78rem; color:#aaa;">
<span>{detalle_izq}</span>
<span>{detalle_der}</span>
</div>
</div>
"""

        c_deuda = "#21c354" if deuda_ebitda <= lim_deuda_optima else ("#faca2b" if deuda_ebitda <= lim_deuda_aceptable else "#ff4b4b")
        c_cob = "#21c354" if (cobertura_intereses is None and deuda_neta == 0) or ((cobertura_intereses or 0) >= (3.2 if es_reit_puro else 6.0)) else ("#faca2b" if (cobertura_intereses or 0) >= (1.8 if es_reit_puro else 2.8) else "#ff4b4b")
        c_cr = "#21c354" if current_ratio >= 1.3 else ("#faca2b" if current_ratio >= 1.0 else "#ff4b4b")
        c_roe = "#21c354" if roe >= 14.0 else ("#faca2b" if roe >= 8.5 else "#ff4b4b")

        txt_p1_izq = f"Deuda Neta/EBITDA: <strong style='color:{c_deuda};'>{f_num(deuda_ebitda, 2, 'x') if deuda_ebitda < 900 else 'N/D'}</strong> <em>(Lím: {f_num(lim_deuda_optima, 1)}x)</em>" if not es_financiera else f"ROE Financiero: <strong style='color:{c_roe};'>{f_num(roe, 1, '%')}</strong>"
        txt_p1_der = f"Cob. Intereses: <strong style='color:{c_cob};'>{f_num(cobertura_intereses, 1, 'x') if cobertura_intereses else ('Sin Deuda' if deuda_neta == 0 else 'N/D')}</strong> · Liquidez: <strong style='color:{c_cr};'>{f_num(current_ratio, 2, 'x') if current_ratio > 0 else 'N/D'}</strong>"

        c_pfcf_col = "#21c354" if (0 < payout_fcf <= payout_limite_fcf) else ("#faca2b" if (0 < payout_fcf <= payout_amarillo_fcf) else "#ff4b4b")
        c_pbpa = "#21c354" if (0 < payout_ratio <= (55.0 if not es_utility_pura else 72.0)) else ("#faca2b" if (0 < payout_ratio <= (80.0 if not es_utility_pura else 88.0)) else "#ff4b4b")
        c_conv = "#21c354" if (cash_conversion_pct or 0) >= 95.0 else ("#faca2b" if (cash_conversion_pct or 0) >= 80.0 else "#ff4b4b")

        txt_p2_izq = f"Payout FCF/AFFO: <strong style='color:{c_pfcf_col};'>{f_num(payout_fcf, 1, '%') if 0 < payout_fcf < 500 else 'N/D'}</strong> <em>(Óptimo <{f_num(payout_limite_fcf, 0)}%)</em>"
        txt_p2_der = f"Payout BPA: <strong style='color:{c_pbpa};'>{f_num(payout_ratio, 1, '%') if payout_ratio > 0 else 'N/D'}</strong> · Conv. Caja: <strong style='color:{c_conv};'>{f_num(cash_conversion_pct, 0, '%') if cash_conversion_pct else 'N/D'}</strong>"

        c_moat = "#21c354" if (metrica_rentabilidad or 0) >= (30.0 if es_reit_puro else 14.5) else ("#faca2b" if (metrica_rentabilidad or 0) >= (18.0 if es_reit_puro else 8.0) else "#ff4b4b")
        c_mop = "#21c354" if operating_margins >= 18.0 else ("#faca2b" if operating_margins >= 10.0 else "#ff4b4b")
        c_fcfm = "#21c354" if (fcf_margin_pct or 0) >= 14.0 else ("#faca2b" if (fcf_margin_pct or 0) >= 7.0 else "#ff4b4b")
        c_v3a = "#21c354" if (revenue_cagr_3y or 0) >= 4.5 else ("#faca2b" if (revenue_cagr_3y or 0) >= 1.0 else "#ff4b4b")

        txt_p3_izq = f"ROIC/ROE: <strong style='color:{c_moat};'>{f_num(metrica_rentabilidad, 1, '%') if metrica_rentabilidad else 'N/D'}</strong> · Margen EBIT: <strong style='color:{c_mop};'>{f_num(operating_margins, 1, '%')}</strong>"
        txt_p3_der = f"Margen FCF/Vtas: <strong style='color:{c_fcfm};'>{f_num(fcf_margin_pct, 1, '%') if fcf_margin_pct is not None else 'N/D'}</strong> · Ventas 3A: <strong style='color:{c_v3a};'>{f_num(revenue_cagr_3y, 1, '%', True) if revenue_cagr_3y is not None else 'N/D'}</strong>"

        c_racha = "#21c354" if racha_sin_recortes >= 20 else ("#00d4ff" if racha_sin_recortes >= 10 else ("#faca2b" if racha_sin_recortes >= 5 else "#ff4b4b"))
        c_dg5 = "#21c354" if (dgr_5y or 0) >= 6.0 else ("#faca2b" if (dgr_5y or 0) >= 2.5 else "#ff4b4b")
        c_dg1 = "#21c354" if (dgr_1y or 0) >= 5.0 else ("#faca2b" if (dgr_1y or 0) >= 0.0 else "#ff4b4b")
        c_r2 = "#21c354" if regularidad_div_r2 >= 85.0 else ("#faca2b" if regularidad_div_r2 >= 65.0 else "#ff4b4b")

        txt_p4_izq = f"Sin recortes: <strong style='color:{c_racha};'>{racha_sin_recortes} años</strong> <em>(Subidas: {racha_incrementos_puros}A)</em>"
        txt_p4_der = f"DGR 5A: <strong style='color:{c_dg5};'>{f_num(dgr_5y, 1, '%', True) if dgr_5y is not None else 'N/D'}</strong> · DGR 1A: <strong style='color:{c_dg1};'>{f_num(dgr_1y, 1, '%', True) if dgr_1y is not None else 'N/D'}</strong> · R²: <strong style='color:{c_r2};'>{f_num(regularidad_div_r2, 0, '%')}</strong>"

        c_rec = "#21c354" if recompras_anualizadas >= 0.5 else ("#faca2b" if recompras_anualizadas >= -0.5 else "#ff4b4b")
        c_bpa = "#21c354" if (crecimiento_bpa_3y or 0) >= 6.5 else ("#faca2b" if (crecimiento_bpa_3y or 0) >= 2.0 else "#ff4b4b")
        c_cajash = "#21c354" if (crecimiento_fcf_sh_3y or 0) >= 6.0 else ("#faca2b" if (crecimiento_fcf_sh_3y or 0) >= 1.5 else "#ff4b4b")

        txt_p5_izq = f"Recompras Netas: <strong style='color:{c_rec};'>{f_num(recompras_anualizadas, 2, '%/año', True)}</strong>"
        txt_p5_der = f"CAGR BPA 3A: <strong style='color:{c_bpa};'>{f_num(crecimiento_bpa_3y, 1, '%', True) if crecimiento_bpa_3y is not None else 'N/D'}</strong> · FCF/acc 3A: <strong style='color:{c_cajash};'>{f_num(crecimiento_fcf_sh_3y, 1, '%', True) if crecimiento_fcf_sh_3y is not None else 'N/D'}</strong>"

        html_pilares = (
            render_barra_pilar("1️⃣ Pilar Balance y Solvencia de Deuda", pilar1_pts, 2.0, txt_p1_izq, txt_p1_der) +
            render_barra_pilar("2️⃣ Pilar Cobertura por Flujo de Caja y Calidad Contable", pilar2_pts, 2.5, txt_p2_izq, txt_p2_der) +
            render_barra_pilar("3️⃣ Pilar Foso Económico (Moat), ROIC y Márgenes", pilar3_pts, 2.0, txt_p3_izq, txt_p3_der) +
            render_barra_pilar("4️⃣ Pilar Historial Weiss y Consistencia del Dividendo", pilar4_pts, 2.0, txt_p4_izq, txt_p4_der) +
            render_barra_pilar("5️⃣ Pilar Asignación de Capital y Crecimiento por Acción", pilar5_pts, 1.5, txt_p5_izq, txt_p5_der)
        )
        st.markdown(html_pilares, unsafe_allow_html=True)

    with col_q2:
        acel_txt = "🔥 Acelerando" if ratio_aceleracion_div >= 1.05 else ("✅ Ritmo Estable" if ratio_aceleracion_div >= 0.70 else ("⚠️ Desacelerando" if ratio_aceleracion_div >= 0.48 else "🚨 En Fatiga"))
        acel_col = "#21c354" if ratio_aceleracion_div >= 0.75 else ("#faca2b" if ratio_aceleracion_div >= 0.48 else "#ff4b4b")

        chow_ok = (chowder_number is not None and chowder_number >= chowder_target)
        col_chow = "#21c354" if chow_ok else ("#faca2b" if (chowder_number or 0) >= (chowder_target - 3.0) else "#ff4b4b")
        chow_val_txt = f"{f_num(chowder_number, 1)}% bruto" if chowder_number is not None else "N/D"
        chow_neto_txt = f"({f_num(chowder_neto, 1)}% neto)" if chowder_neto is not None else ""

        col_per = "#21c354" if (0 < per <= mult_optimo) else ("#faca2b" if (0 < per <= mult_aceptable) else "#ff4b4b")
        col_pfcf = "#21c354" if (0 < p_fcf <= (15.0 if es_reit_puro else mult_optimo)) else ("#faca2b" if (0 < p_fcf <= (22.0 if es_reit_puro else mult_aceptable)) else "#ff4b4b")

        col_d1 = "#21c354" if (dgr_1y or 0) > 0 else "#ff4b4b"
        col_d5 = "#21c354" if (dgr_5y or 0) > 0 else "#ff4b4b"

        col_obj_calidad = "#21c354" if precio_actual <= precio_objetivo_calidad else ("#faca2b" if precio_actual <= precio_objetivo_calidad * 1.08 else "#ff4b4b")

        st.markdown(f"""
<div class="card-dgi notranslate" translate="no" style="height: 100%;">
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px; margin-bottom:10px;">
<span style="font-weight:700; color:#00d4ff; font-size:0.95rem;">🏛️ Diagnóstico Blue-Chip & Regla de Weiss</span>
<span class="badge-morado">{arquetipo_dgi}</span>
</div>

<div style="font-size:0.84rem; color:#ccc; margin-bottom:10px; line-height:1.45;">
{arquetipo_desc}
</div>

<div style="background:rgba(255,255,255,0.03); border-radius:8px; padding:10px 12px; margin-bottom:10px; font-size:0.85rem; line-height:1.65;">
• <strong>Seguridad del Dividendo (Safety Score):</strong> <strong style="color:{safety_color};">{safety_score}/100 ({safety_label})</strong><br>
• <strong>Momentum del Dividendo (1A vs 5A):</strong> <strong style="color:{acel_col};">{acel_txt}</strong> (<span style="color:{col_d1}; font-weight:bold;">{f_num(dgr_1y, 1, '%', True)}</span> vs <span style="color:{col_d5}; font-weight:bold;">{f_num(dgr_5y, 1, '%', True)}</span>)<br>
• <strong>Número de Chowder (Yield + DGR 5A):</strong> <strong style="color:{col_chow};">{chow_val_txt}</strong> <span style="font-size:0.80rem; color:#aaa;">{chow_neto_txt}</span> <em>(Objetivo: ≥{f_num(chowder_target, 0)}%)</em><br>
• <strong>Múltiplos Actuales:</strong> PER: <strong style="color:{col_per};">{f_num(per, 1, 'x') if per > 0 else 'N/D'}</strong> &nbsp;|&nbsp; Precio/FCF: <strong style="color:{col_pfcf};">{f_num(p_fcf, 1, 'x') if p_fcf > 0 else 'N/D'}</strong> <em>(Techo justo: <span style="color:#21c354;">{f_num(mult_optimo, 1)}x</span> · Aceptable: <span style="color:#faca2b;">{f_num(mult_aceptable, 1)}x</span>)</em><br>
• <strong>Yield on Cost (YoC) comprando hoy:</strong> En 5A: <strong style="color:#00d4ff;">{f_num(yoc_5a_bruto, 2, '%')} bruto</strong> <span style="font-size:0.80rem; color:#aaa;">({f_num(yoc_5a_neto, 2, '%')} neto)</span> &nbsp;|&nbsp; En 10A: <strong style="color:#21c354;">{f_num(yoc_10a_bruto, 2, '%')} bruto</strong> <span style="font-size:0.80rem; color:#aaa;">({f_num(yoc_10a_neto, 2, '%')} neto)</span>
</div>

<div style="background:rgba(33, 195, 84, 0.08); border-left:3px solid {col_obj_calidad}; padding:9px 12px; border-radius:0 6px 6px 0; font-size:0.83rem; color:#ddd;">
🎯 <strong>Precio Máximo de Entrada según Calidad: <span style="color:{col_obj_calidad}; font-size:0.95rem;">{f_num(precio_objetivo_calidad, 2)}{sym}</span></strong><br>
<span style="color:#bbb;">{regla_entrada_calidad}</span>
</div>
</div>
""", unsafe_allow_html=True)

    # ==========================================
    # 3. CUADRÍCULA DE VALORACIÓN HISTÓRICA (BRUTO Y NETO)
    # ==========================================
    st.markdown("#### 📏 Niveles de Valoración por Rentabilidad Histórica (Canales de Geraldine Weiss)")
    color_actual = "#21c354" if precio_actual <= precio_compra else ("#00d4ff" if precio_actual <= precio_acumulacion else ("#ff4b4b" if precio_actual >= precio_venta else "#faca2b"))
    txt_extra_actual = f"Descuento: {f_num(abs(pct_actual_vs_media), 1)}% vs Media" if pct_actual_vs_media <= 0 else f"Sobreprecio: +{f_num(pct_actual_vs_media, 1)}% vs Media"

    st.markdown(f"""
<div class="grid-precios-weiss notranslate" translate="no">
<div class="card-precio" style="border-top: 3px solid {color_actual};">
<span style="font-size: 0.80rem; color: #aaa;">Cotización en Vivo</span>
<span style="font-size: 1.55rem; font-weight: 800; color: {color_actual};">{f_num(precio_actual, 2)}{sym}</span>
<span style="font-size: 0.82rem; font-weight: 600; color: {color_actual};">Yield: {f_num(yield_actual, 2, '%')} bruto</span>
<span style="font-size: 0.77rem; color: #aaa;">({f_num(yield_actual * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.74rem; color: #999; margin-top: 2px;">{txt_extra_actual} · Perc. {f_num(percentil_yield_actual, 0)}%</span>
</div>
<div class="card-precio" style="border-top: 3px solid #21c354;">
<span style="font-size: 0.80rem; color: #aaa;">Suelo Estricto (P95 Weiss)</span>
<span style="font-size: 1.55rem; font-weight: 800; color: #21c354;">{f_num(precio_compra, 2)}{sym}</span>
<span style="font-size: 0.82rem; font-weight: 600; color: #21c354;">Yield: {f_num(yield_infravalorado, 2, '%')} bruto</span>
<span style="font-size: 0.77rem; color: #aaa;">({f_num(yield_infravalorado * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.74rem; color: #999; margin-top: 2px;">Descuento: {f_num(pct_infra_vs_media, 1)}% vs Media</span>
</div>
<div class="card-precio" style="border-top: 3px solid #00d4ff;">
<span style="font-size: 0.80rem; color: #aaa;">Zona Acumulación (P90)</span>
<span style="font-size: 1.55rem; font-weight: 800; color: #00d4ff;">{f_num(precio_acumulacion, 2)}{sym}</span>
<span style="font-size: 0.82rem; font-weight: 600; color: #00d4ff;">Yield: {f_num(yield_acumulacion, 2, '%')} bruto</span>
<span style="font-size: 0.77rem; color: #aaa;">({f_num(yield_acumulacion * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.74rem; color: #999; margin-top: 2px;">Entrada Blue-Chips ({f_num(pct_acum_vs_media, 1)}%)</span>
</div>
<div class="card-precio" style="border-top: 3px solid #faca2b;">
<span style="font-size: 0.80rem; color: #aaa;">Precio Justo ({años_analisis}A)</span>
<span style="font-size: 1.55rem; font-weight: 800; color: #faca2b;">{f_num(precio_justo, 2)}{sym}</span>
<span style="font-size: 0.82rem; font-weight: 600; color: #faca2b;">Yield: {f_num(yield_medio, 2, '%')} bruto</span>
<span style="font-size: 0.77rem; color: #aaa;">({f_num(yield_medio * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.74rem; color: #999; margin-top: 2px;">Imán Reversión a la Media</span>
</div>
<div class="card-precio" style="border-top: 3px solid #ff4b4b;">
<span style="font-size: 0.80rem; color: #aaa;">Techo Venta (P05 Weiss)</span>
<span style="font-size: 1.55rem; font-weight: 800; color: #ff4b4b;">{f_num(precio_venta, 2)}{sym}</span>
<span style="font-size: 0.82rem; font-weight: 600; color: #ff4b4b;">Yield: {f_num(yield_sobrevalorado, 2, '%')} bruto</span>
<span style="font-size: 0.77rem; color: #aaa;">({f_num(yield_sobrevalorado * net_mult, 2, '%')} neto)</span>
<span style="font-size: 0.74rem; color: #999; margin-top: 2px;">Techo: +{f_num(pct_sobre_vs_media, 1)}% vs Media</span>
</div>
</div>
""", unsafe_allow_html=True)

    # 4. TERMÓMETRO VISUAL DEL CANAL DE WEISS
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
<span>🟢 Suelo P95 ({f_num(precio_compra, 2)}{sym})</span>
<span>🔵 Acumulación P90 ({f_num(precio_acumulacion, 2)}{sym})</span>
<span>{etiqueta_pos}</span>
<span>🟡 Justo ({f_num(precio_justo, 2)}{sym})</span>
<span>🔴 Techo P05 ({f_num(precio_venta, 2)}{sym})</span>
</div>
<div style="position: relative; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #21c354 0%, #00d4ff 22%, #faca2b 50%, #ff9100 78%, #ff4b4b 100%);">
<div style="position: absolute; left: {pos_canal_clamp:.1f}%; top: -5px; width: 20px; height: 20px; background: white; border: 4px solid {borde_bola}; border-radius: 50%; transform: translateX(-50%); box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>
</div>
</div>
""", unsafe_allow_html=True)

    # ==========================================
    # 5. SIMULACIÓN TÁCTICA DE ORDEN + PLAN EN 3 TRAMOS
    # ==========================================
    st.markdown(f"#### 🧮 Simulación Táctica de tu Orden de {f_num(capital_simulado, 0)}{sym} y Retorno Bogle-Weiss (5 Años)")

    b_tot_cls = "badge-verde" if retorno_bogle_bruto_anual >= 10.0 else ("badge-ambar" if retorno_bogle_bruto_anual >= 6.0 else "badge-rojo")
    signo_rev = "+" if reversion_weiss_anual_acotada >= 0 else ""

    if dist_suelo_pct <= 0:
        consejo_orden_html = f"🟢 <strong>Disparo Directo:</strong> Ya cotiza en Suelo Estricto de Weiss ({f_num(precio_actual, 2)}{sym} ≤ {f_num(precio_compra, 2)}{sym}). Momento óptimo de ejecución."
    elif caida_necesaria_suelo_pct <= 5.0:
        consejo_orden_html = (
            f"⚡ <strong>Coste de Oportunidad de Esperar:</strong> El Suelo ({f_num(precio_compra, 2)}{sym}) está a solo un <strong>-{f_num(caida_necesaria_suelo_pct, 1)}%</strong> y esperar únicamente te da <strong>+{f_num(extra_anual_esperar, 2)}{sym}/año</strong> extra. "
            f"Si por esperar se te escapa <strong>1 solo cobro {nombre_frecuencia} ({f_num(cobro_por_pago_hoy, 2)}{sym} netos)</strong>, tardarías <strong>{f_num(anios_recuperar_1_pago, 1)} años</strong> en recuperarlo."
        )
    else:
        consejo_orden_html = (
            f"⏳ <strong>Estrategia por Tramos Recomendada:</strong> Necesita corregir un <strong>-{f_num(caida_necesaria_suelo_pct, 1)}%</strong> para tocar el Suelo P95 ({f_num(precio_compra, 2)}{sym}). "
            f"Comprar en suelo te asegura un <strong>+{f_num(((div_neto_suelo / div_neto_hoy) - 1) * 100 if div_neto_hoy > 0 else 0, 1)}% más de renta perpetua</strong> (+{f_num(extra_anual_esperar, 2)}{sym}/año netos)."
        )

    col_bog1, col_bog2 = st.columns(2)
    with col_bog1:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
<span style="color: #00d4ff; font-weight: 700; font-size: 0.9rem;">1️⃣ Comparativa de Ejecución ({f_num(capital_simulado, 0)}{sym})</span>
<span class="badge-azul">Pago {nombre_frecuencia} ({pagos_por_año}/año)</span>
</div>
<div style="font-size: 0.88rem; color: #ddd; line-height: 1.55;">
<div style="background: rgba(255,255,255,0.03); padding: 7px 10px; border-radius: 6px; margin-bottom: 6px;">
• <strong>Comprando HOY ({f_num(precio_actual, 2)}{sym}):</strong> Compras <strong>{f_num(acc_hoy, 2)} títulos</strong> <em>({acc_enteras_hoy} enteras + {f_num(sobrante_hoy, 0)}{sym} sobrantes)</em><br>
&nbsp;&nbsp;➔ Cobras <strong style="color:#00d4ff;">{f_num(div_neto_hoy, 2)}{sym}/año netos</strong> ({f_num(div_bruto_hoy, 2)}{sym} brutos) · <strong>{f_num(cobro_por_pago_hoy, 2)}{sym} netos</strong> cada cobro {nombre_frecuencia}.
</div>
<div style="background: rgba(33, 195, 84, 0.06); padding: 7px 10px; border-radius: 6px; margin-bottom: 8px;">
• <strong>En SUELO WEISS ({f_num(precio_compra, 2)}{sym}):</strong> Comprarías <strong>{f_num(acc_suelo, 2)} títulos</strong> <em>({acc_enteras_suelo} enteras)</em><br>
&nbsp;&nbsp;➔ Cobrarías <strong style="color:#21c354;">{f_num(div_neto_suelo, 2)}{sym}/año netos</strong> ({f_num(div_bruto_suelo, 2)}{sym} brutos · {f_num(extra_anual_esperar, 2, sym, signo_pos=True)}/año netos) · <strong>{f_num(cobro_por_pago_suelo, 2)}{sym} netos</strong> cada cobro.
</div>
<div style="font-size: 0.81rem; color: #ccc; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;">
{consejo_orden_html}
</div>
</div>
</div>
""", unsafe_allow_html=True)

    with col_bog2:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
<span style="color: #faca2b; font-weight: 700; font-size: 0.9rem;">2️⃣ Desglose Real a 5 Años (Fórmula Bogle-Weiss)</span>
<span class="{b_tot_cls}">Retorno Total: {f_num(retorno_bogle_neto_anual, 1, '%', signo_pos=True)}/año</span>
</div>
<div style="font-size: 1.05rem; margin-bottom: 8px; background: rgba(255,255,255,0.03); padding: 6px 10px; border-radius: 6px;">
<span style="color:#00d4ff; font-weight:bold;">{f_num(yield_actual * net_mult, 2, '%')}</span> <span style="font-size:0.75rem; color:#999;">({f_num(yield_actual, 2, '%')} bruto)</span> + 
<span style="color:#faca2b; font-weight:bold;">{f_num(crec_bogle, 1, '%', signo_pos=True)}</span> <span style="font-size:0.75rem; color:#999;">(DGR)</span> 
<span style="color:{'#21c354' if reversion_weiss_anual_acotada >= 0 else '#ff4b4b'}; font-weight:bold;"> {signo_rev}{f_num(reversion_weiss_anual_acotada, 1, '%')}</span> <span style="font-size:0.75rem; color:#999;">(Reversión Media)</span>
</div>
<div style="font-size: 0.85rem; color: #ddd; line-height: 1.55;">
¿En qué se transforman tus <strong>{f_num(capital_simulado, 0)}{sym}</strong> tras 5 años?<br>
1. 💵 <strong>Dividendos Netos cobrados en mano (5A):</strong> <strong style="color:#00d4ff;">+{f_num(divs_netos_acum_5a, 2)}{sym}</strong> limpios en cuenta.<br>
2. 📈 <strong>Valor de tus acciones (Sin cambio de múltiplo):</strong> <strong>{f_num(valor_acciones_5a_sin_reversion, 0)}{sym}</strong> <em>(subiendo solo al {f_num(crec_bogle, 1, '%')}/año)</em>.<br>
3. 🎯 <strong>Valor de tus acciones (Si vuelve al Precio Justo Weiss):</strong> <strong style="color:{'#21c354' if valor_acciones_5a_con_reversion >= capital_simulado else '#ff4b4b'};">{f_num(valor_acciones_5a_con_reversion, 0)}{sym}</strong> <em>(cotización objetivo de {f_num(precio_estimado_5a_weiss, 2)}{sym} al Yield Medio del {f_num(yield_medio, 2, '%')})</em>.
</div>
</div>
""", unsafe_allow_html=True)

    # Plan Táctico de Entrada en 3 Tramos
    p_tramo1 = min(precio_actual, precio_objetivo_calidad)
    p_tramo2 = min(p_tramo1 * 0.95, precio_acumulacion)
    p_tramo3 = min(p_tramo2 * 0.94, precio_compra)
    y_t1 = (forward_dividend / p_tramo1) * 100 if p_tramo1 > 0 else 0
    y_t2 = (forward_dividend / p_tramo2) * 100 if p_tramo2 > 0 else 0
    y_t3 = (forward_dividend / p_tramo3) * 100 if p_tramo3 > 0 else 0

    st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no" style="margin-top: 2px;">
🎯 <strong>Plan de Francotirador en 3 Tramos para tus {f_num(capital_simulado, 0)}{sym} (Estrategia Anti-FOMO):</strong><br>
• <strong>Tramo 1 (35% ➔ {f_num(capital_simulado * 0.35, 0)}{sym}):</strong> Entrada en <strong>{f_num(p_tramo1, 2)}{sym}</strong> (Yield: <strong>{f_num(y_t1, 2, '%')} bruto</strong> · <em>{f_num(y_t1 * net_mult, 2, '%')} neto</em> — {'Ejecutable HOY' if precio_actual <= precio_objetivo_calidad else 'Orden Limitada'}).<br>
• <strong>Tramo 2 (35% ➔ {f_num(capital_simulado * 0.35, 0)}{sym}):</strong> Refuerzo en Zona Acumulación Weiss (P90) a <strong>{f_num(p_tramo2, 2)}{sym}</strong> (Yield: <strong>{f_num(y_t2, 2, '%')} bruto</strong> · <em>{f_num(y_t2 * net_mult, 2, '%')} neto</em>).<br>
• <strong>Tramo 3 (30% ➔ {f_num(capital_simulado * 0.30, 0)}{sym}):</strong> Caza en Suelo Estricto P95 / Capitulación a <strong>{f_num(p_tramo3, 2)}{sym}</strong> (Yield: <strong>{f_num(y_t3, 2, '%')} bruto</strong> · <em>{f_num(y_t3 * net_mult, 2, '%')} neto</em>).
</div>
""", unsafe_allow_html=True)

    # ==========================================
    # 6. GRÁFICO 1: CANALES DE VALORACIÓN GERALDINE WEISS
    # ==========================================
    st.markdown(f"### 📈 Evolución Histórica de Valoración Weiss ({años_analisis} Años)")
    df_grafico = historial_analisis[['Close']].copy()
    if not df_grafico.empty:
        df_grafico['Div_Grafico'] = historial_analisis['Div_Anual']
        df_grafico['Precio_Compra'] = (df_grafico['Div_Grafico'] / yield_infravalorado) * 100
        df_grafico['Precio_Acumulacion'] = (df_grafico['Div_Grafico'] / yield_acumulacion) * 100
        df_grafico['Precio_Justo'] = (df_grafico['Div_Grafico'] / yield_medio) * 100
        df_grafico['Precio_Venta'] = (df_grafico['Div_Grafico'] / yield_sobrevalorado) * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Venta'], name='Techo Venta (P05)', line=dict(color='#ff4b4b', width=2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Justo'], name='Precio Justo (Media)', line=dict(color='rgba(255, 255, 255, 0.45)', width=1.2, dash='dash')))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Acumulacion'], name='Zona Acumulación (P90)', line=dict(color='#00d4ff', width=1.3, dash='dot')))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Precio_Compra'], name='Suelo Estricto (P95)', line=dict(color='#21c354', width=2.2)))
        fig.add_trace(go.Scatter(x=df_grafico.index, y=df_grafico['Close'], name='Cotización Real', line=dict(color='#faca2b', width=2.8)))

        fig.update_layout(
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=430,
            legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

        is_compra = df_grafico['Close'] <= df_grafico['Precio_Compra']
        toques_compra = int((is_compra & ~is_compra.shift(1, fill_value=False)).sum())
        is_venta = df_grafico['Close'] >= df_grafico['Precio_Venta']
        toques_venta = int((is_venta & ~is_venta.shift(1, fill_value=False)).sum())

        def format_last_time(is_zone_series, active_color):
            if is_zone_series.sum() == 0:
                return "Nunca", "#aaa"
            if is_zone_series.iloc[-1]:
                return "Ahora", active_color
            last_date = is_zone_series[is_zone_series].index[-1]
            days_diff = (hoy_ts - last_date.tz_localize(None).normalize()).days
            if days_diff < 30:
                return f"hace {days_diff} días", "#ddd"
            elif days_diff < 365:
                return f"hace {days_diff // 30} meses", "#ddd"
            else:
                return f"hace {f_num(days_diff / 365.25, 1)} años", "#ddd"

        str_ult_compra, col_ult_compra = format_last_time(is_compra, "#21c354")
        str_ult_venta, col_ult_venta = format_last_time(is_venta, "#ff4b4b")

        estado_canal_txt = f"un <strong>{f_num(abs(pct_actual_vs_media), 1)}% por debajo</strong> de su Precio Justo ({f_num(precio_justo, 2)}{sym})" if pct_actual_vs_media <= 0 else f"un <strong>+{f_num(pct_actual_vs_media, 1)}% por encima</strong> de su Precio Justo ({f_num(precio_justo, 2)}{sym})"
        dist_compra_txt = f"ya cotiza un <strong>{f_num(abs(dist_suelo_pct), 1)}% por debajo del Suelo P95</strong>" if dist_suelo_pct <= 0 else f"necesita corregir un <strong>-{f_num(caida_necesaria_suelo_pct, 1)}%</strong> desde el precio actual para tocar el Suelo P95 ({f_num(precio_compra, 2)}{sym})"

        st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
<div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px; margin-bottom:8px;">
<span>🟢 <strong>Toques Suelo Estricto ({años_analisis}A):</strong> <strong style="color:#21c354;">{toques_compra} veces</strong> (Última vez: <strong style="color:{col_ult_compra};">{str_ult_compra}</strong>)</span>
<span>🔴 <strong>Toques Techo Venta ({años_analisis}A):</strong> <strong style="color:#ff4b4b;">{toques_venta} veces</strong> (Última vez: <strong style="color:{col_ult_venta};">{str_ult_venta}</strong>)</span>
</div>
💡 <strong>Lectura de los canales en {ticker_symbol}:</strong> Hoy cotiza a <strong>{f_num(precio_actual, 2)}{sym}</strong> ({estado_canal_txt}) y {dist_compra_txt}. Su Yield actual (<strong>{f_num(yield_actual, 2, '%')} bruto</strong> / <em>{f_num(yield_actual * net_mult, 2, '%')} neto</em>) supera al <strong>{f_num(percentil_yield_actual, 1)}%</strong> de todas las sesiones registradas.
</div>
""", unsafe_allow_html=True)

    # ==========================================
    # 7. GRÁFICO 2: ESCALERA CON % COLOREADOS + RESPALDO FCF/BPA
    # ==========================================
    st.divider()
    st.markdown("### 🛡️ Auditoría Visual de Calidad: Crecimiento del Dividendo vs. Cobertura de Caja y Beneficio")

    col_gcal1, col_gcal2 = st.columns(2)

    with col_gcal1:
        divs_hist_plot = dividendos_barras[dividendos_barras.index >= (año_actual - años_analisis)].copy()
        if not divs_hist_plot.empty:
            c_bars = ['#00d4ff' if y < año_actual else '#21c354' for y in divs_hist_plot.index]

            x_labels = []
            custom_hover_info = []
            años_graf = list(divs_hist_plot.index)

            for idx_y, y in enumerate(años_graf):
                y_str = str(y) + (" (Est.)" if y == año_actual else "")
                val_y = float(divs_hist_plot.loc[y])

                prev_val = dividendos_barras.get(y - 1, None)
                if prev_val is None and idx_y > 0:
                    prev_val = float(divs_hist_plot.iloc[idx_y - 1])

                if prev_val is not None and prev_val > 0:
                    inc_pct = ((val_y / prev_val) - 1.0) * 100.0
                    signo = "+" if inc_pct > 0 else ""
                    txt_pct = f"{signo}{f_num(inc_pct, 1)}%"

                    if inc_pct > 0.05:
                        col_pct = "#21c354"
                    elif inc_pct < -0.05:
                        col_pct = "#ff4b4b"
                    else:
                        col_pct = "#faca2b"

                    x_labels.append(f"{y_str}<br><span style='color:{col_pct}; font-weight:bold;'>({txt_pct})</span>")
                    custom_hover_info.append([y_str, txt_pct, col_pct])
                else:
                    x_labels.append(f"{y_str}<br><span style='color:#aaa;'>Base</span>")
                    custom_hover_info.append([y_str, "Base", "#aaa"])

            hover_template_clean = "<b>Año:</b> %{customdata[0]}<br><b>Dividendo:</b> %{y:.2f}" + sym + "<br><b>Crecimiento:</b> %{customdata[1]}<extra></extra>"

            fig_div = go.Figure()
            fig_div.add_trace(go.Bar(
                x=x_labels,
                y=divs_hist_plot.values,
                name=f'Dividendo Anual ({sym})',
                marker_color=c_bars,
                text=[f_num(v, 2) for v in divs_hist_plot.values],
                textposition='outside',
                customdata=custom_hover_info,
                hovertemplate=hover_template_clean
            ))
            fig_div.update_layout(
                title=dict(text=f"Escalera de Dividendos ({años_analisis} Años · R²={f_num(regularidad_div_r2, 0)}%)", font=dict(size=14)),
                template='plotly_dark', margin=dict(l=0, r=0, t=38, b=60), height=350,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
            )
            st.plotly_chart(fig_div, use_container_width=True)

    with col_gcal2:
        años_contables = sorted(list(set(s_eps.index).union(set(s_caja_base.index))))[-4:]
        if len(años_contables) >= 2 and shares > 0:
            l_anios, l_div, l_fcf_sh, l_eps_sh = [], [], [], []
            for y in años_contables:
                l_anios.append(str(y))
                l_div.append(float(dividendos_barras.get(y, forward_dividend)))
                sh_y = float(s_shares.get(y, shares)) if not s_shares.empty and y in s_shares.index else shares
                caja_y = (float(s_caja_base.get(y, 0.0)) / sh_y) if (not s_caja_base.empty and y in s_caja_base.index and sh_y > 0) else 0.0
                eps_y = float(s_eps.get(y, 0.0)) if (not s_eps.empty and y in s_eps.index) else 0.0
                l_fcf_sh.append(round(caja_y, 2))
                l_eps_sh.append(round(eps_y, 2))

            fig_cov = go.Figure()
            fig_cov.add_trace(go.Bar(x=l_anios, y=l_div, name=f'Dividendo/Acc ({sym})', marker_color='#00d4ff'))
            fig_cov.add_trace(go.Bar(x=l_anios, y=l_fcf_sh, name=f'{"FFO/OCF" if es_reit_puro else "FCF"}/Acc ({sym})', marker_color='#21c354'))
            if not es_reit_puro:
                fig_cov.add_trace(go.Bar(x=l_anios, y=l_eps_sh, name=f'BPA Contable ({sym})', marker_color='#faca2b'))

            fig_cov.update_layout(
                title=dict(text="Respaldo Real del Cupón: Dividendo vs. Caja Libre y BPA", font=dict(size=14)),
                barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=38, b=0), height=330,
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_cov, use_container_width=True)
        else:
            st.info("ℹ️ Yahoo Finance no reporta desglose multianual suficiente por acción para graficar las barras de cobertura contable en este ticker.")

    # ==========================================
    # 8. GRÁFICO 3: LUPA DE FRANCOTIRADOR (TIMING TÉCNICO)
    # ==========================================
    st.divider()
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses + SMA 200/1000 + RSI + MACD)")

    sma_200_full = historial_completo['Close'].rolling(200).mean()
    sma_1000_full = historial_completo['Close'].rolling(1000).mean()

    fecha_calculo_macd = hoy_ts - pd.DateOffset(years=1)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()

    if len(df_tech_full) > 30:
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100
        df_tech_full['Precio_Acumulacion'] = (df_tech_full['Div_Anual'] / yield_acumulacion) * 100
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
        gain = delta_p.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        loss = (-delta_p.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
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

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (P05)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Acumulacion'], name='Zona Acumulación (P90)', line=dict(color='#00d4ff', width=1.4, dash='dot'), showlegend=True), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo Estricto (P95)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)
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

            txt_s200 = f"a un <strong>{f_num(((precio_actual - ult_sma200) / ult_sma200) * 100, 1, signo_pos=True)}%</strong> de su SMA 200 ({f_num(ult_sma200, 2)}{sym})" if ult_sma200 else ""
            txt_s1000 = f"y a un <strong>{f_num(((precio_actual - ult_sma1000) / ult_sma1000) * 100, 1, signo_pos=True)}%</strong> de su SMA 1000 ({f_num(ult_sma1000, 2)}{sym})" if ult_sma1000 else ""

            c_rsi = "#21c354" if ult_rsi <= 35 else ("#ff4b4b" if ult_rsi >= 70 else "#faca2b")
            c_macd = "#21c354" if ult_macd > ult_signal else ("#faca2b" if ult_hist > penult_hist else "#ff4b4b")
            c_vol = "#21c354" if ratio_vol >= 1.25 else "#bbb"

            estado_macd = "en cruce alcista confirmado" if ult_macd > ult_signal else ("bajista pero con divergencia positiva" if ult_hist > penult_hist else "en fase bajista")
            estado_rsi = "en sobreventa técnica (<32)" if ult_rsi <= 32 else ("en sobrecompra (>70)" if ult_rsi >= 70 else "en zona neutral")

            confluencia_compra = (precio_actual <= precio_acumulacion) and (ult_rsi <= 42 or ult_macd > ult_signal or (ult_sma1000 and precio_actual <= ult_sma1000 * 1.03))
            msg_confluencia = "🎯 <strong>¡SEÑAL DE FRANCOTIRADOR ACTIVA!</strong> Confluencia de Infravaloración Fundamental Weiss + Agotamiento Vendedor Técnico." if confluencia_compra else ""

            st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
💡 <strong>Lectura Técnica y Timing:</strong> Cotiza {txt_s200} {txt_s1000}. RSI en <strong style="color:{c_rsi};">{f_num(ult_rsi, 1)}</strong> ({estado_rsi}) y MACD <strong style="color:{c_macd};">{estado_macd}</strong>. Volumen pico reciente de <strong style="color:{c_vol};">{f_num(ratio_vol, 2)}x</strong> sobre la media. {msg_confluencia}
</div>
""", unsafe_allow_html=True)


# ==========================================
# INTERFAZ CONECTADA A MEMORIA GLOBAL
# ==========================================
st.title("🎯 1. Valoración, Bogle y Calidad Blue-Chip — Weiss DGI")

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
    with st.spinner(f"Auditando estados financieros, calidad Blue-Chip y canales Weiss de {ticker_input}..."):
        try:
            render_valoracion_bogle(ticker_input, años_analisis, impuesto, aplicar_merma, capital_simulado)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
