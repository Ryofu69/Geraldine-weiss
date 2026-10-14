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

# Retención en origen no recuperable fácilmente desde España (exceso sobre el 15% del convenio)
MERMA_ORIGEN_PAIS = {
    'Switzerland': 20.0,  # 35% origen - 15% deducible
    'Denmark': 12.0,      # 27% origen - 15% deducible
    'Germany': 11.375,    # 26.375% origen - 15% deducible
    'France': 10.0,       # 25% estándar (salvo trámite previo 12.8%) - 15% deducible
    'Ireland': 10.0       # 25% origen - 15% deducible
}

# ==========================================
# CACHÉ DE DOBLE VELOCIDAD (MERCADO ABIERTO)
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def cargar_fundamentales_pesados(ticker_symbol):
    """Cachea balances, cuenta de resultados, dividendos y acciones durante 15 min."""
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

    # Detección de desajuste de divisas (ej. ADRs como NVO, TSM, ASML o UK en USD)
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
    """Cache ultra-corta (15s) para precios en mercado abierto."""
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="max", auto_adjust=False)
    precio_vivo = None
    try:
        precio_vivo = float(t.fast_info.last_price)
    except Exception:
        pass
    return hist, precio_vivo

def interpolar_puntos(valor, umbral_max, umbral_med, pts_max, pts_med, inverso=False):
    """Evita el efecto acantilado interpolando linealmente entre el rango medio y el óptimo."""
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
# 1. FUNCIÓN DE ANÁLISIS INDIVIDUAL
# ==========================================
def screener_weiss_definitivo(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
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

    # --- LÓGICA DE DIVISAS Y NORMALIZACIÓN DESDE EL ORIGEN (PENIQUES UK Y FX) ---
    currency_raw = info.get('currency', 'USD')
    es_peniques_uk = (currency_raw == 'GBp')
    currency = 'GBP' if es_peniques_uk else currency_raw

    if currency == 'EUR': sym = '€'
    elif currency == 'GBP': sym = '£'
    else: sym = '$'

    historial_completo = historial_raw.copy()
    dividendos = dividendos_raw.copy()

    historial_completo.index = historial_completo.index.tz_localize(None).normalize()
    dividendos.index = dividendos.index.tz_localize(None).normalize()

    # Si tenemos tick en vivo de mercado abierto, actualizamos la última vela
    if precio_vivo is not None and precio_vivo > 0 and not historial_completo.empty:
        historial_completo.iloc[-1, historial_completo.columns.get_loc('Close')] = precio_vivo
        if precio_vivo > historial_completo['High'].iloc[-1]:
            historial_completo.iloc[-1, historial_completo.columns.get_loc('High')] = precio_vivo
        if precio_vivo < historial_completo['Low'].iloc[-1]:
            historial_completo.iloc[-1, historial_completo.columns.get_loc('Low')] = precio_vivo

    # Normalizar precios UK de peniques (GBp) a Libras (GBP) desde el inicio
    if es_peniques_uk:
        for col in ['Open', 'High', 'Low', 'Close']:
            if col in historial_completo.columns:
                historial_completo[col] = historial_completo[col] / 100.0
        # Si los dividendos históricos venían en peniques, pasarlos a Libras
        if dividendos.median() > (historial_completo['Close'].median() * 0.25):
            dividendos = dividendos / 100.0

    fecha_corte_analisis = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
    historial_analisis = historial_completo[historial_completo.index >= fecha_corte_analisis].copy()

    if historial_analisis.empty:
        st.error(f"❌ Error: No se encontraron datos de cotización en los últimos {años_analisis} años.")
        return

    precio_actual = float(historial_analisis['Close'].dropna().iloc[-1])
    año_actual = datetime.now().year

    # --- DETECCIÓN SECTORIAL AVanzada (REITs, QUASI-REITs, FINANCIERAS) ---
    sector_en = info.get('sector', 'Desconocido')
    industry_en = info.get('industry', 'Desconocido')
    pais = info.get('country', 'Desconocido')
    
    sector_final = TRADUCCION.get(sector_en, sector_en)
    industry_final = industry_en

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_tecnologica = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
    es_industrial = 'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()

    # Merma fiscal efectiva
    merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
    net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

    # --- DIVIDENDOS Y FILTRO DE EXTRAORDINARIOS ANTES DE BANDAS DE WEISS ---
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4
    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    # Limpieza de pagos extraordinarios a nivel de pago individual para no deformar las bandas
    ventana_med = max(4, pagos_por_año * 2)
    mediana_pagos = dividendos.rolling(window=ventana_med, min_periods=1).median()
    umbral_extra = mediana_pagos * 1.75
    aviso_extraordinario = bool((dividendos.tail(pagos_por_año * 2) > umbral_extra.tail(pagos_por_año * 2)).any())
    dividendos_regulares = dividendos.where(dividendos <= umbral_extra, mediana_pagos)

    divs_por_año = dividendos.groupby(dividendos.index.year).sum()
    divs_reg_por_año = dividendos_regulares.groupby(dividendos_regulares.index.year).sum()

    forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    if es_peniques_uk and forward_dividend > (precio_actual * 0.25):
        forward_dividend /= 100.0

    if forward_dividend == 0 and not dividendos_regulares.empty:
        ultimo_año_completo = divs_reg_por_año.iloc[-2] if len(divs_reg_por_año) > 1 else 0
        forward_dividend = max(dividendos_regulares.iloc[-1] * pagos_por_año, ultimo_año_completo)

    # Serie continua TTM (Rolling 365D) para eliminar escalones artificiales de año natural
    divs_diarios_reg = dividendos_regulares.groupby(dividendos_regulares.index).sum()
    idx_completo = pd.date_range(start=historial_completo.index.min(), end=historial_completo.index.max(), freq='D')
    divs_calendario = divs_diarios_reg.reindex(idx_completo, fill_value=0.0)
    div_ttm_serie = divs_calendario.rolling('365D').sum()

    historial_analisis['Year'] = historial_analisis.index.year
    historial_analisis['Div_TTM'] = div_ttm_serie.reindex(historial_analisis.index).bfill().ffill()
    
    # Si al principio de la serie el TTM está incompleto, respaldar con el anual regular
    div_anual_map = historial_analisis['Year'].map(divs_reg_por_año)
    historial_analisis['Div_Anual'] = np.where(
        historial_analisis['Div_TTM'] > (div_anual_map * 0.7),
        historial_analisis['Div_TTM'],
        div_anual_map
    )
    # Anclar los últimos meses al forward_dividend vigente
    fecha_ult_div = dividendos.index[-1]
    historial_analisis.loc[historial_analisis.index >= fecha_ult_div, 'Div_Anual'] = forward_dividend
    historial_analisis['Div_Anual'] = pd.Series(historial_analisis['Div_Anual'], index=historial_analisis.index).bfill().ffill()

    historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
    historial_analisis.replace([np.inf, -np.inf], np.nan, inplace=True)

    yields_validos = historial_analisis['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]

    yield_infravalorado = float(yields_validos.quantile(0.95))
    yield_sobrevalorado = float(yields_validos.quantile(0.05))
    yield_medio = float(yields_validos.mean())
    yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0

    # --- FUNDAMENTALES CON CONVERSIÓN DE DIVISA CONTABLE (fx_rate) ---
    payout_ratio = get_safe('payoutRatio') * 100
    per_actual = get_safe('trailingPE')
    per_forward = get_safe('forwardPE')
    per = per_actual if per_actual > 0 else per_forward
    deuda_equity = get_safe('debtToEquity')
    market_cap = get_safe('marketCap')
    current_ratio = get_safe('currentRatio')
    bpa_trailing = get_safe('trailingEps')
    bpa_forward = get_safe('forwardEps')
    price_to_book = get_safe('priceToBook', -1)
    roe = get_safe('returnOnEquity', 0.0) * 100
    operating_margins = get_safe('operatingMargins', 0.0) * 100

    # Magnitudes absolutas convertidas si la empresa reporta en otra divisa (ej. NVO, SHEL.L, TSM)
    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    total_cash = get_safe('totalCash', 0.0) * fx_rate
    ebitda = get_safe('ebitda', 0.0) * fx_rate
    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    shares = get_safe('sharesOutstanding', 0.0)

    # En REITs puros, el Operating Cash Flow (FFO proxy) es mucho más fiel que el FCF contable
    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw
    etiqueta_fcf = "FFO (Flujo Operativo)" if (es_reit_puro and ocf_raw > fcf_raw) else "FCF (Flujo Caja Libre)"

    # Detección de Quasi-REITs / Franquicias con recompras intensivas y patrimonio contable negativo/bajo (ej. MCD, YUM, SBUX, HD)
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

    payout_limite_bpa = 85.0 if es_regulada_o_reit else 60.0
    payout_amarillo_bpa = 92.0 if es_regulada_o_reit else 75.0
    payout_limite_fcf = 85.0 if es_regulada_o_reit else 75.0
    payout_amarillo_fcf = 92.0 if es_regulada_o_reit else 85.0

    payout_forward = (forward_dividend / bpa_forward) * 100 if bpa_forward > 0 else -1

    deuda_neta = max(0.0, total_debt - total_cash)
    if ebitda > 0:
        deuda_ebitda = deuda_neta / ebitda
    else:
        deuda_ebitda = 999.0 if (total_debt > 0 and not es_financiera) else 0.0

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

    # 1. RETORNO SOBRE EL CAPITAL INVERTIDO (ROIC BLINDADO ANTE EQUITY NEGATIVO)
    roic = None
    try:
        ebit_val = get_safe('operatingIncome') * fx_rate
        if ebit_val == 0 and not inc_stmt.empty:
            for k in ['Operating Income', 'EBIT']:
                if k in inc_stmt.index:
                    ebit_val = float(inc_stmt.loc[k].dropna().iloc[-1]) * fx_rate
                    break
        # Si el patrimonio neto es negativo por recompras masivas (ej. MCD, SBUX), usamos max(0, equity)
        inv_cap = (total_debt + max(0.0, total_equity_raw)) - total_cash
        if inv_cap <= 0 and not bs_stmt.empty:
            for k_ass in ['Total Assets']:
                if k_ass in bs_stmt.index:
                    tot_assets = float(bs_stmt.loc[k_ass].dropna().iloc[-1]) * fx_rate
                    curr_liab = float(bs_stmt.loc['Current Liabilities'].dropna().iloc[-1]) * fx_rate if 'Current Liabilities' in bs_stmt.index else 0.0
                    inv_cap = tot_assets - curr_liab - total_cash
                    break
        if inv_cap > 0 and ebit_val > 0:
            nopat = ebit_val * 0.79
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

    # 3. COBERTURA DE INTERESES
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

    # FCF / FFO por acción
    payout_fcf = -1
    p_fcf = -1
    fcf_yield = 0.0
    deuda_fcf = -1

    if flujo_caja_referencia != 0 and shares > 0:
        fcf_per_share = flujo_caja_referencia / shares
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100

    if flujo_caja_referencia > 0:
        deuda_fcf = total_debt / flujo_caja_referencia

    # 4. COLCHÓN DE CAJA LÍQUIDA PARA DIVIDENDOS
    meses_caja_div = None
    gasto_anual_div = forward_dividend * shares
    if gasto_anual_div > 0 and total_cash > 0:
        meses_caja_div = (total_cash / gasto_anual_div) * 12

    # Dividendos anuales para gráficos de barras, DGR e Inercia
    dividendos_barras = divs_reg_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    divs_recientes = dividendos_barras.tail(años_analisis + 1)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

    dgr_5y, dgr_periodo, dgr_1y = None, None, None
    if len(dividendos_barras) >= 2:
        div_act = dividendos_barras.iloc[-1]
        div_ant = dividendos_barras.iloc[-2]
        if div_ant > 0: dgr_1y = ((div_act / div_ant) - 1) * 100

    if len(dividendos_barras) >= 6:
        div_actual = dividendos_barras.iloc[-1]
        div_5y = dividendos_barras.iloc[-6]
        if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100

    if len(dividendos_barras) >= (años_analisis + 1):
        div_actual = dividendos_barras.iloc[-1]
        div_periodo = dividendos_barras.iloc[-(años_analisis + 1)]
        if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

    # 5. DETECCIÓN DE FATIGA E INERCIA DEL DIVIDENDO
    fatiga_dividendo = False
    inercia_ratio = None
    if dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0:
        inercia_ratio = dgr_1y / dgr_5y
        if inercia_ratio < 0.5:
            fatiga_dividendo = True

    # Racha sin recortes (sobre dividendos regulares para evitar falsos recortes tras dividendo especial)
    racha_sin_recortes = 0
    if len(dividendos_barras) > 1:
        for i in range(1, len(dividendos_barras)):
            if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.98:
                racha_sin_recortes += 1
            else: break

    # Acciones en circulación
    shares_yearly = pd.Series(dtype=float)
    variacion_acciones = None
    try:
        if shares_hist is not None and len(shares_hist) > 1:
            fecha_corte_shares = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis + 3)
            sh_sub = shares_hist[shares_hist.index.tz_localize(None) >= fecha_corte_shares]
            sy = sh_sub.groupby(sh_sub.index.year).last()
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
                            shares_yearly = sh_data.groupby(pd.to_datetime(sh_data.index).year).last()
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
    # CÁLCULO DUAL DGI MODERNO PROGRESIVO (0 a 10 Pts)
    # ==========================================
    score_calidad = 0.0

    # 1. Solvencia adaptada a Sector (Industrial vs REIT/Quasi-REIT vs Financiero)
    lim_deuda_optima = 4.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 3.0
    lim_deuda_aceptable = 5.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0

    if es_financiera:
        pts_deuda = 2.0 if roe >= 12.0 else (1.0 if roe >= 8.0 else 0.0)
        pts_cob = 0.5 if current_ratio >= 1.0 or roe >= 10.0 else 0.0
    else:
        pts_deuda = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable * 1.15, 2.0, 0.75, inverso=True)
        if cobertura_intereses is not None:
            pts_cob = 0.5 if cobertura_intereses >= 4.0 else (0.25 if cobertura_intereses >= 2.5 else 0.0)
        else:
            pts_cob = 0.5 if deuda_neta == 0 else 0.0
    score_calidad += (pts_deuda + pts_cob)

    # 2. Seguridad del Payout (FCF/FFO o BPA en Financieras)
    if es_financiera and payout_fcf == -1:
        pts_fcf = interpolar_puntos(payout_ratio, 50.0, 75.0, 2.0, 0.8, inverso=True) if payout_ratio > 0 else 0.0
    else:
        pts_fcf = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf * 1.05, 2.0, 0.8, inverso=True) if payout_fcf > 0 else 0.0
    score_calidad += pts_fcf

    # 3. Historial
    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: pts_hist = 2.0
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: pts_hist = 1.25
    elif racha_sin_recortes >= 5: pts_hist = 0.75
    else: pts_hist = 0.0
    if fatiga_dividendo and pts_hist > 0.5:
        pts_hist -= 0.5
    score_calidad += pts_hist

    # 4. Foso económico (ROIC o ROE en financieras/quasi-REITs)
    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
    cond_roic = (metrica_rentabilidad is not None and metrica_rentabilidad >= 10.0) or (es_reit_puro and operating_margins >= 25.0)
    cond_rev = (revenue_cagr_3y is not None and revenue_cagr_3y > 0)
    if cond_roic and cond_rev: pts_foso = 1.0
    elif cond_roic or cond_rev: pts_foso = 0.5
    else: pts_foso = 0.0
    score_calidad += pts_foso

    # 5. DGR 5A
    if dgr_5y is not None and dgr_5y >= 5.0: pts_dgr = 1.0
    elif dgr_5y is not None and dgr_5y >= 2.5: pts_dgr = 0.5
    else: pts_dgr = 0.0
    score_calidad += pts_dgr

    # 6. Asignación de Capital
    cond_recompras = variacion_acciones is not None and variacion_acciones < -0.5
    cond_bpa_pos = crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0
    pts_cap = 1.5 if (cond_recompras or cond_bpa_pos) else 0.0
    score_calidad += pts_cap
    score_calidad = min(10.0, round(score_calidad, 1))

    # --- 2. SCORE DE VALORACIÓN DGI PROGRESIVO (10 Pts) ---
    score_val = 0.0

    # Puntos por Yield interpolados sin salto brusco
    if yield_actual >= yield_infravalorado:
        pts_yield = 4.0
    elif yield_actual >= yield_medio:
        pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_medio, 4.0, 2.2, inverso=False)
    elif yield_actual >= yield_sobrevalorado:
        pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 2.2, 0.0, inverso=False)
    else:
        pts_yield = 0.0
    score_val += pts_yield

    # Puntos por P/FCF (o P/FFO en REITs, o P/B en Financieras)
    if es_financiera and p_fcf <= 0:
        pts_pfcf = interpolar_puntos(price_to_book, 1.3, 2.5, 2.5, 1.0, inverso=True) if price_to_book > 0 else 0.0
    else:
        pts_pfcf = interpolar_puntos(p_fcf, 18.0, 26.0, 2.5, 1.0, inverso=True) if p_fcf > 0 else 0.0
    score_val += pts_pfcf

    # Puntos por PER (En REITs puros usamos P/FFO en lugar del PER contable distorsionado por amortizaciones)
    multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
    pts_per = interpolar_puntos(multiplo_per_eval, 18.0, 26.0, 2.0, 0.8, inverso=True) if multiplo_per_eval > 0 else 0.0
    score_val += pts_per

    if (es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0:
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
        pts_chowder = interpolar_puntos(chowder_number, chowder_target, chowder_target - 2.5, 1.5, 0.5, inverso=False)
    else:
        chowder_number = None
        chowder_pass = False
        pts_chowder = 0.0
    score_val += pts_chowder
    score_val = min(10.0, round(score_val, 1))

    # Detección de Trampa de Valor
    posible_trampa_valor = (precio_actual <= precio_compra) and (
        score_calidad < 5.5 or (payout_fcf > 95.0) or (dgr_1y is not None and dgr_1y < -1.0)
    )

    # ==========================================
    # INTERFAZ VISUAL STREAMLIT
    # ==========================================
    if es_reit_puro:
        tipo_empresa_txt = "🏢 REIT / Inmobiliario (Evaluado con FFO y Filtros Flexibles)"
    elif es_quasi_reit_o_recompras:
        tipo_empresa_txt = "🍔 Franquicia / Recompras Intensivas (ROIC y Deuda Ajustados)"
    elif es_financiera:
        tipo_empresa_txt = "🏦 Sector Financiero / Seguros (Evaluado por ROE y P/B)"
    elif es_regulada_o_reit:
        tipo_empresa_txt = "⚡ Sector Regulado / Utility (Filtros de Deuda Flexibles)"
    else:
        tipo_empresa_txt = "🏭 Sector Industrial / General (Filtros Estrictos)"

    hora_actual_str = datetime.now().strftime("%H:%M:%S")
    st.header(f"Análisis de {ticker_symbol} ({currency}) — {tipo_empresa_txt}")
    
    aviso_fx = f"&nbsp;&nbsp;|&nbsp;&nbsp; 💱 <strong>Contabilidad convertida:</strong> {curr_fin} ➔ {currency} (FX: {fx_rate:.4f})" if fx_rate != 1.0 else ""
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 10px; border-radius: 5px; margin-bottom: 20px;">
        <strong>Sector:</strong> <span style="color: #00d4ff;">{sector_final}</span> &nbsp;&nbsp;|&nbsp;&nbsp; 
        <strong>Industry:</strong> <span style="color: #21c354;">{industry_final}</span> &nbsp;&nbsp;|&nbsp;&nbsp;
        <strong>Último tick:</strong> <span style="color: #faca2b;">{hora_actual_str}</span>{aviso_fx}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🌍 Perfil Fiscal y Retención en Origen")
    if pais in ['United States', 'Netherlands', 'Canada']: 
        st.success(f"✅ **{pais}**: Retención en origen del 15%. Al coincidir con el máximo deducible en España por doble imposición internacional, es 100% recuperable automáticamente en tu declaración de la Renta.")
    elif pais == 'United Kingdom': 
        st.success(f"✅ **{pais}**: Retención en origen del 0% (salvo PIDs en REITs). Eficiencia fiscal óptima en origen, solo tributas el impuesto local configurado.")
    elif pais == 'Spain': 
        st.success(f"✅ **{pais}**: Mercado local. Retención directa del {impuesto_pct}%. Sin trámites ni retenciones en el extranjero.")
    elif pais == 'Denmark':
        st.warning(f"⚠️ **{pais}**: Retención en origen del 27%. Recuperas el 15% en la Renta, pero el **12% restante se pierde** salvo reclamación ante *Skat*. {'(Merma descontada del Yield Neto)' if aplicar_merma_origen else ''}")
    elif pais == 'Switzerland':
        st.error(f"❌ **{pais}**: Retención en origen del 35%. Deducible el 15% en España; el **20% sobrante queda retenido en Suiza** (Formulario 81). {'(Merma descontada del Yield Neto)' if aplicar_merma_origen else ''}")
    elif pais == 'Germany':
        st.error(f"❌ **{pais}**: Retención en origen del 26.375%. Recuperas el 15% en España, pero el **11.375% restante se pierde** salvo trámite ante el *BZSt*. {'(Merma descontada del Yield Neto)' if aplicar_merma_origen else ''}")
    elif pais == 'France':
        st.error(f"❌ **{pais}**: Retención estándar del 25% (12.8% si el bróker tramita el formulario 5000). Exceso no recuperable en Renta: **10%**. {'(Merma descontada del Yield Neto)' if aplicar_merma_origen else ''}")
    elif pais == 'Ireland': 
        st.warning(f"⚠️ **{pais}**: Retención en origen del 25%. Puedes deducir el 15% en España; el **10% restante exige trámites** o formulario DWT. {'(Merma descontada del Yield Neto)' if aplicar_merma_origen else ''}")
    else: 
        st.info(f"ℹ️ **{pais}**: Verifica el convenio de doble imposición internacional vigente y las tasas de retención actuales para residentes españoles.")

    if aviso_extraordinario:
        st.warning("⚠️ **Dividendo Extraordinario Filtrado:** Se ha detectado un pago atípico (>75% sobre la mediana). El algoritmo lo ha suavizado automáticamente para no distorsionar las Bandas de Weiss.")

    st.subheader(f"🎯 Precios Objetivo y Valoración Actual (Basado en {años_analisis} Años - TTM Continuo)")
    
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
    with col1: metric_color("Cotización en Vivo", f"{precio_actual:.2f}{sym}", f"Yield: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% neto)", txt_extra_actual, color_actual)
    with col2: metric_color("Franja Infravalorada", f"{precio_compra:.2f}{sym}", f"Yield {yield_infravalorado:.2f}% ({yield_infravalorado * net_mult:.2f}% neto)", txt_extra_infra, "#21c354") 
    with col3: metric_color("Precio Justo (Media)", f"{precio_justo:.2f}{sym}", f"Yield {yield_medio:.2f}% ({yield_medio * net_mult:.2f}% neto)", txt_extra_justo, "#faca2b") 
    with col4: metric_color("Franja Sobrevalorada", f"{precio_venta:.2f}{sym}", f"Yield {yield_sobrevalorado:.2f}% ({yield_sobrevalorado * net_mult:.2f}% neto)", txt_extra_sobre, "#ff4b4b") 

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

    if posible_trampa_valor:
        st.warning("🚨 **ALERTA DE TRAMPA DE VALOR:** La acción cotiza en zona de compra por Yield histórico, pero su Calidad DGI es baja (< 5.5) o el Payout FCF supera el 95%. Riesgo elevado de deterioro fundamental o recorte de dividendo.")
    elif precio_actual <= precio_compra:
        st.success("💡 ESTADO: En zona de COMPRA CLARA (Infravalorada y con fundamentales sanos).")
    elif precio_actual >= precio_venta:
        st.error("💡 ESTADO: En zona de VENTA (Sobrevalorada).")
    else:
        st.info("💡 ESTADO: En zona de MANTENER (Precio Justo / Transición).")

    # --- CALCULADORA RÁPIDA DE EJECUCIÓN EN MERCADO ABIERTO ---
    if precio_actual > 0 and precio_compra > 0:
        acc_hoy = capital_simulado / precio_actual
        div_neto_hoy = acc_hoy * forward_dividend * net_mult
        acc_suelo = capital_simulado / precio_compra
        div_neto_suelo = acc_suelo * forward_dividend * net_mult
        dif_renta = div_neto_suelo - div_neto_hoy

        st.markdown(f"""
        <div style="background: rgba(0, 212, 255, 0.06); border: 1px solid rgba(0, 212, 255, 0.25); border-radius: 8px; padding: 12px 18px; margin-bottom: 20px;">
            <strong>🧮 Simulación de Orden en Mercado Abierto ({capital_simulado:,.0f}{sym}):</strong><br>
            • Comprando <strong>AHORA ({precio_actual:.2f}{sym})</strong>: Obtienes <strong>{acc_hoy:.2f} acciones</strong> ➔ Renta anual neta: <strong style="color:#00d4ff;">{div_neto_hoy:.2f}{sym}/año</strong>.<br>
            • Comprando en <strong>SUELO WEISS ({precio_compra:.2f}{sym})</strong>: Obtendrías <strong>{acc_suelo:.2f} acciones</strong> ➔ Renta anual neta: <strong style="color:#21c354;">{div_neto_suelo:.2f}{sym}/año</strong> 
            ({'+' if dif_renta >= 0 else ''}{dif_renta:.2f}{sym}/año de diferencia).
        </div>
        """, unsafe_allow_html=True)

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
            template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), 
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), 
            hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

        is_compra = df_grafico['Close'] <= df_grafico['Precio_Compra']
        toques_compra = (is_compra & ~is_compra.shift(1, fill_value=False)).sum()
        is_venta = df_grafico['Close'] >= df_grafico['Precio_Venta']
        toques_venta = (is_venta & ~is_venta.shift(1, fill_value=False)).sum()
        
        def format_last_time(is_zone_series, active_color):
            if is_zone_series.sum() == 0: return "Nunca", "#aaa"
            if is_zone_series.iloc[-1]: return "Ahora", active_color
            last_date = is_zone_series[is_zone_series].index[-1]
            days_diff = (pd.Timestamp.now().normalize() - last_date.tz_localize(None).normalize()).days
            if days_diff < 30: return f"hace {days_diff} días", "#ccc"
            elif days_diff < 365: return f"hace {days_diff // 30} meses", "#ccc"
            else: return f"hace {days_diff / 365.25:.1f}a".replace(".", ","), "#ccc"

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
    st.markdown("### 🎯 Lupa de Francotirador: Timing de Entrada (Últimos 2 Meses + RSI + MACD)")
    st.markdown("> **Uso en Mercado Abierto:** Busca picos de volumen rojo extremo (Capitulación), **RSI < 35 (Sobreventa)** y precio tocando la línea verde discontinua (Suelo Weiss). Dispara cuando el histograma MACD pierda inercia bajista o cruce al alza.")

    fecha_calculo_macd = pd.Timestamp.now().normalize() - pd.DateOffset(years=1)
    df_tech_full = historial_analisis[historial_analisis.index >= fecha_calculo_macd].copy()

    if len(df_tech_full) > 30: 
        df_tech_full['Precio_Compra'] = (df_tech_full['Div_Anual'] / yield_infravalorado) * 100
        df_tech_full['Precio_Justo'] = (df_tech_full['Div_Anual'] / yield_medio) * 100
        df_tech_full['Precio_Venta'] = (df_tech_full['Div_Anual'] / yield_sobrevalorado) * 100
        df_tech_full['SMA_200'] = historial_completo['Close'].rolling(200).mean().reindex(df_tech_full.index)

        if yield_req_chowder is not None and yield_req_chowder > 0:
            df_tech_full['Precio_Chowder'] = (df_tech_full['Div_Anual'] / yield_req_chowder) * 100

        # Cálculo de MACD
        ema12 = df_tech_full['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df_tech_full['Close'].ewm(span=26, adjust=False).mean()
        df_tech_full['MACD'] = ema12 - ema26
        df_tech_full['Signal'] = df_tech_full['MACD'].ewm(span=9, adjust=False).mean()
        df_tech_full['Histogram'] = df_tech_full['MACD'] - df_tech_full['Signal']

        # Cálculo de RSI (14 periodos Wilder)
        delta_p = df_tech_full['Close'].diff()
        gain = delta_p.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss = (-delta_p.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        df_tech_full['RSI'] = 100 - (100 / (1 + rs))

        fecha_display = pd.Timestamp.now().normalize() - pd.DateOffset(months=2)
        df_tech = df_tech_full[df_tech_full.index >= fecha_display].copy()

        if not df_tech.empty:
            ult_close_val = precio_actual
            ult_suelo_val = precio_compra
            precio_str = f"{ult_close_val:.2f}{sym}"
            suelo_str = f"{ult_suelo_val:.2f}{sym}"
            dist_suelo = ((ult_close_val - ult_suelo_val) / ult_suelo_val) * 100 if ult_suelo_val > 0 else 999.0

            ult_macd = df_tech['MACD'].iloc[-1]
            ult_signal = df_tech['Signal'].iloc[-1]
            ult_hist = df_tech['Histogram'].iloc[-1]
            penult_hist = df_tech['Histogram'].iloc[-2] if len(df_tech) > 1 else 0
            ult_rsi = df_tech['RSI'].iloc[-1] if pd.notna(df_tech['RSI'].iloc[-1]) else 50.0

            avg_vol = df_tech['Volume'].mean()
            vol_elevado = df_tech['Volume'].tail(5).max() > (avg_vol * 1.5)

            txt_rsi = f"RSI en **{ult_rsi:.1f}** " + ("(Sobreventa extrema 🟢). " if ult_rsi <= 32 else ("(Sobrecompra 🔴). " if ult_rsi >= 70 else "(Zona neutral). "))

            analisis_ia = f"🧠 **Lectura en Vivo ({precio_str}):** {txt_rsi}"
            if dist_suelo <= 0:
                descuento_extra = abs(dist_suelo)
                if descuento_extra > 0.5: analisis_ia += f"🎯 **En Zona de Disparo.** El precio cotiza un **{descuento_extra:.1f}% por debajo** de tu Suelo Fundamental ({suelo_str}). "
                else: analisis_ia += f"🎯 **En Zona de Disparo.** El precio está tocando el Suelo Fundamental ({suelo_str}). "
                if vol_elevado: analisis_ia += "Se detecta pico de volumen reciente (posible capitulación). "
                if ult_macd > ult_signal and ult_hist > 0: analisis_ia += "El MACD confirma giro alcista. **Escenario de COMPRA IDEAL.**"
                elif ult_macd < ult_signal and ult_hist > penult_hist: analisis_ia += "El MACD sigue negativo pero el histograma ya remonta (frenada bajista). Excelente punto para acumular."
                else: analisis_ia += "El MACD sigue cayendo. Puedes fraccionar la entrada si buscas precio o esperar giro de vela."
            elif 0 < dist_suelo <= 5.0:
                analisis_ia += f"🟡 **Alerta Temprana / Rebote.** El precio está a solo un **{dist_suelo:.1f}%** de tu zona de compra ({suelo_str}). "
                if ult_macd > ult_signal: analisis_ia += "El MACD ya es alcista. Si acaba de rebotar cerca de la línea verde, es buena entrada."
                else: analisis_ia += "El MACD es bajista; vigila si corrige ese pequeño tramo restante hasta tocar la línea verde."
            else:
                analisis_ia += f"🔴 **Fuera de Zona.** Cotiza un **{dist_suelo:.1f}%** por encima del suelo exigido ({suelo_str}). "
                analisis_ia += "Sin margen de seguridad por Weiss. Mantén orden limitada o alerta cerca del suelo."
            st.info(analisis_ia)

            colors_vol = ['#21c354' if row['Close'] >= row['Open'] else '#ff4b4b' for index, row in df_tech.iterrows()]
            colors_hist = ['#21c354' if val >= 0 else '#ff4b4b' for val in df_tech['Histogram']]

            fig_tech = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=[0.44, 0.16, 0.20, 0.20])
            fig_tech.add_trace(go.Ohlc(x=df_tech.index, open=df_tech['Open'], high=df_tech['High'], low=df_tech['Low'], close=df_tech['Close'], name='Precio', increasing_line_color='#21c354', decreasing_line_color='#ff4b4b', showlegend=False), row=1, col=1)

            ex_div_ts = info.get('exDividendDate')
            if pd.notna(ex_div_ts) and ex_div_ts is not None:
                try:
                    ex_div_date_future = pd.to_datetime(ex_div_ts, unit='s').tz_localize(None).normalize()
                    if ex_div_date_future >= fecha_display:
                        fig_tech.add_vline(x=ex_div_date_future, line_width=1.5, line_dash="dot", line_color="#e040fb", 
                                           annotation_text=" Ⓓ Ex-Div", annotation_position="bottom right", 
                                           annotation_font=dict(color="#e040fb", size=11, family="Arial", weight="bold"), row=1, col=1)
                except Exception: pass

            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Venta'], name='Techo (Sobrevalorada)', line=dict(color='#ff4b4b', width=1.5, dash='dash'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Justo'], name='Precio Justo', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), showlegend=True, visible='legendonly'), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Compra'], name='Suelo (Infravalorada)', line=dict(color='#21c354', width=1.5, dash='dash'), showlegend=True), row=1, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA_200'], name='SMA 200', line=dict(color='#faca2b', width=1.2, dash='dot'), showlegend=True), row=1, col=1)

            if 'Precio_Chowder' in df_tech.columns:
                fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Precio_Chowder'], name='Precio Obj. Chowder', line=dict(color='#e040fb', width=1.5, dash='dashdot'), showlegend=True, visible='legendonly'), row=1, col=1)

            # Fila 2: Volumen
            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Volume'], name='Volumen', marker_color=colors_vol, showlegend=False), row=2, col=1)
            
            # Fila 3: RSI (14)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['RSI'], name='RSI (14)', line=dict(color='#b388ff', width=1.8), showlegend=False), row=3, col=1)
            fig_tech.add_hline(y=70, line_dash="dot", line_color="#ff4b4b", row=3, col=1)
            fig_tech.add_hline(y=30, line_dash="dot", line_color="#21c354", row=3, col=1)

            # Fila 4: MACD
            fig_tech.add_trace(go.Bar(x=df_tech.index, y=df_tech['Histogram'], name='Histograma', marker_color=colors_hist, showlegend=False), row=4, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['MACD'], name='MACD', line=dict(color='#00d4ff', width=1.5), showlegend=False), row=4, col=1)
            fig_tech.add_trace(go.Scatter(x=df_tech.index, y=df_tech['Signal'], name='Señal', line=dict(color='#ff9900', width=1.5), showlegend=False), row=4, col=1)

            fig_tech.update_yaxes(title_text="Precio", row=1, col=1)
            fig_tech.update_yaxes(title_text="Vol", row=2, col=1)
            fig_tech.update_yaxes(title_text="RSI", range=[15, 85], row=3, col=1)
            fig_tech.update_yaxes(title_text="MACD", row=4, col=1)

            fig_tech.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=880, showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.04, xanchor="center", x=0.5), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_rangeslider_visible=False)
            fig_tech.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_tech, use_container_width=True)

    # ==========================================
    # RADIOGRAFÍA FINANCIERA DGI MODERNA
    # ==========================================
    st.divider()
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
            st.metric("BPA Actual", f"{bpa_trailing:.2f}{sym}" if bpa_trailing != 0 else "N/D")

    with col_bpa2:
        if es_reit_puro and p_fcf > 0:
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏢 Múltiplo Inmobiliario (Precio / FFO)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{p_fcf:.1f}x</span>
                    <span class="{'badge-verde' if p_fcf <= 18 else ('badge-ambar' if p_fcf <= 24 else 'badge-rojo')}">FFO Yield: {fcf_yield:.2f}%</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Múltiplo real REIT sin distorsión por depreciación de inmuebles</span>
            </div>
            """, unsafe_allow_html=True)
        elif per_actual > 0 and per_forward > 0:
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
            st.metric("PER Actual", f"{per_actual:.1f}x" if per_actual > 0 else "N/D")

    col_foso1, col_foso2 = st.columns(2)
    with col_foso1:
        lbl_rent = "🏰 Retorno s/ Capital (ROE)" if es_financiera else "🏰 Retorno s/ Capital Invertido (ROIC)"
        if metrica_rentabilidad is not None:
            if metrica_rentabilidad >= 12.0: r_badge, r_txt = "badge-verde", "Foso Amplio (≥ 12%)"
            elif metrica_rentabilidad >= 8.0: r_badge, r_txt = "badge-ambar", "Foso Medio (≥ 8%)"
            else: r_badge, r_txt = "badge-rojo", "Foso Débil (< 8%)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">{lbl_rent}</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{metrica_rentabilidad:.2f}%</span>
                    <span class="{r_badge}">{r_txt}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Mide la rentabilidad real de reinversión del negocio</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">{lbl_rent}</span>
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

    col_sol1, col_sol2 = st.columns(2)
    with col_sol1:
        if es_financiera:
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏦 Precio / Valor Contable (P/B)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{price_to_book:.2f}x</span>
                    <span class="{'badge-verde' if 0 < price_to_book <= 1.5 else 'badge-ambar'}">Banca/Seguros</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">En entidades financieras no aplica Deuda/EBITDA</span>
            </div>
            """, unsafe_allow_html=True)
        elif deuda_ebitda < 900:
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
            elif inercia_ratio is not None and inercia_ratio >= 1.0:
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
        st.markdown(f"#### 💰 Historial de Dividendos Anuales Regulares y Crecimiento YoY ({años_analisis} Años)")
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
            fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=40), height=300, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color="#00d4ff")), tickfont=dict(color="#00d4ff")), yaxis2=dict(title=dict(text="Crecimiento (%)", font=dict(color="#21c354")), tickfont=dict(color="#21c354"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
            st.plotly_chart(fig_divs, use_container_width=True)

    # ==========================================
    # SECCIÓN CHOWDER REDISEÑADA
    # ==========================================
    st.divider()
    st.subheader("🥣 La Regla de Chowder (Retorno Total Compuesto)")

    if (es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0:
        criterio_txt = "Sector Regulado/REIT/Utility con Yield > 4.0% (Meta ≥ 8.0)"
    elif yield_actual >= 3.0:
        criterio_txt = "Yield Inicial Alto ≥ 3.0% (Meta estándar ≥ 12.0)"
    else:
        criterio_txt = "Yield Inicial Bajo < 3.0% (Meta estricta ≥ 15.0 por alto crecimiento)"

    col_chow1, col_chow2 = st.columns(2)

    with col_chow1:
        if chowder_number is not None:
            pct_progreso = min(100.0, max(0.0, (chowder_number / chowder_target) * 100))
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
                p_obj_val = precio_obj_chowder
                p_act_val = precio_actual
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
    # DECÁLOGO DETALLADO DGI COMPLETO
    # ==========================================
    st.divider()
    st.subheader(f"📋 Decálogo Detallado DGI — Geraldine Weiss Moderno ({años_analisis} Años)")
    
    t_yield = f"[🏷️ Val: +{pts_yield:.2f} / 4.0 pts]"
    t_pfcf = f"[🏷️ Val: +{pts_pfcf:.2f} / 2.5 pts]"
    t_per_t = f"[🏷️ Val: +{pts_per:.2f} / 2.0 pts]"
    t_chowder_t = f"[🏷️ Val: +{pts_chowder:.2f} / 1.5 pts]"
    
    t_fcf = f"[🛡️ Cal: +{pts_fcf:.2f} / 2.0 pts]"
    t_deuda = f"[🛡️ Cal: +{pts_deuda:.2f} / 2.0 pts]"
    t_cob_t = f"[🛡️ Cal: +{pts_cob:.2f} / 0.5 pts]"
    t_hist = f"[🛡️ Cal: +{pts_hist:.2f} / 2.0 pts]"
    t_foso_t = f"[🛡️ Cal: +{pts_foso:.1f} / 1.0 pts]"
    t_dgr_t = f"[🛡️ Cal: +{pts_dgr:.2f} / 1.0 pts]"
    t_cap_t = f"[🛡️ Cal: +{pts_cap:.1f} / 1.5 pts]"
    t_info = "[ℹ️ Info]"

    st.markdown("#### 🏷️ 1. Múltiplos y Oportunidad de Entrada (Score Valoración: 10 Pts)")
    if yield_actual >= yield_infravalorado: 
        st.success(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (En Suelo Histórico de Compra, supera el {yield_infravalorado:.2f}%)")
    elif yield_actual >= yield_medio: 
        st.warning(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Por encima de la media histórica de {yield_medio:.2f}%)")
    else: 
        st.error(f"{t_yield} Rentabilidad Bruta: {yield_actual:.2f}% ({yield_actual * net_mult:.2f}% Neto) | (Por debajo de su media histórica de {yield_medio:.2f}%)")

    if p_fcf != -1:
        if 0 < p_fcf <= 20.0: st.success(f"{t_pfcf} Precio/{etiqueta_fcf}: {p_fcf:.2f}x (Muy atractivo ≤ 20x. Yield de Caja: {fcf_yield:.2f}%)")
        elif 0 < p_fcf <= 26.0: st.warning(f"{t_pfcf} Precio/{etiqueta_fcf}: {p_fcf:.2f}x (Moderado ≤ 26x. Yield de Caja: {fcf_yield:.2f}%)")
        else: st.error(f"{t_pfcf} Precio/{etiqueta_fcf}: {p_fcf:.2f}x (Múltiplo exigente > 26x. Yield de Caja: {fcf_yield:.2f}%)")
    elif es_financiera:
        st.info(f"{t_pfcf} Sector Financiero: Puntuado mediante Precio/Valor en Libros ({price_to_book:.2f}x)")
    else:
        st.error(f"{t_pfcf} P/FCF: NEGATIVO (La empresa no genera flujo de caja libre positivo)")

    if es_reit_puro and p_fcf > 0:
        st.info(f"{t_per_t} REIT Puro: Múltiplo evaluado mediante P/FFO ({p_fcf:.1f}x) para evitar la distorsión del PER contable ({per:.1f}x)")
    elif 0 < per <= 20.0:
        st.success(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Valoración razonable ≤ 20x)")
    elif 0 < per <= 26.0:
        st.warning(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo justo ≤ 26x)")
    else:
        st.error(f"{t_per_t} PER (Beneficio Contable): {per:.2f}x (Múltiplo exigente > 26x)")

    if chowder_number is not None and chowder_pass:
        st.success(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Aprobada ≥ {chowder_target:.0f}. Retorno total compuesto atractivo)")
    elif chowder_number is not None:
        st.error(f"{t_chowder_t} Regla de Chowder: {chowder_number:.1f} (Inferior a la meta de {chowder_target:.0f})")
    else:
        st.info(f"{t_chowder_t} Regla de Chowder: N/D")

    st.markdown("#### 🛡️ 2. Seguridad del Dividendo en Efectivo (Score Calidad: 10 Pts)")
    if payout_fcf != -1:
        if 0 <= payout_fcf <= payout_limite_fcf: 
            st.success(f"{t_fcf} Payout sobre {etiqueta_fcf}: {payout_fcf:.2f}% (Excelente: cubre con holgura el dividendo ≤ {payout_limite_fcf:.0f}%)")
        elif payout_fcf <= payout_amarillo_fcf: 
            st.warning(f"{t_fcf} Payout sobre {etiqueta_fcf}: {payout_fcf:.2f}% (Aceptable ≤ {payout_amarillo_fcf:.0f}%)")
        else: 
            st.error(f"{t_fcf} Payout sobre {etiqueta_fcf}: {payout_fcf:.2f}% (Precaución: el dividendo presiona la caja > {payout_amarillo_fcf:.0f}%)")
    else: 
        st.error(f"{t_fcf} Payout sobre FCF: N/D o Negativo")

    if 0 < payout_ratio <= payout_limite_bpa: 
        st.success(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Sano para su sector, referencia < {payout_limite_bpa:.0f}%)")
    elif payout_limite_bpa < payout_ratio <= payout_amarillo_bpa: 
        st.warning(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (En el límite sectorial de {payout_amarillo_bpa:.0f}%)")
    else: 
        st.info(f"{t_info} Payout contable (BPA): {payout_ratio:.2f}% (Elevado contablemente)")

    st.markdown("#### 🏗️ 3. Solvencia Operativa y Asignación de Capital")
    if es_financiera:
        st.info(f"{t_deuda} Solvencia Financiera evaluada por ROE ({roe:.1f}%) y Liquidez")
    elif deuda_ebitda <= lim_deuda_optima: 
        st.success(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Óptimo ≤ {lim_deuda_optima:.1f}x)")
    elif deuda_ebitda <= lim_deuda_aceptable: 
        st.warning(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Aceptable ≤ {lim_deuda_aceptable:.1f}x)")
    else: 
        st.error(f"{t_deuda} Solvencia Operativa (Deuda Neta / EBITDA): {deuda_ebitda:.2f}x (Elevada > {lim_deuda_aceptable:.1f}x)")

    if cobertura_intereses is not None and cobertura_intereses >= 4.0:
        st.success(f"{t_cob_t} Cobertura de Intereses: {cobertura_intereses:.2f}x (Holgada ≥ 4.0x)")
    elif cobertura_intereses is not None and cobertura_intereses >= 2.5:
        st.warning(f"{t_cob_t} Cobertura de Intereses: {cobertura_intereses:.2f}x (Aceptable)")
    else:
        st.info(f"{t_cob_t} Cobertura de Intereses: Balance sin deuda neta o gasto financiero no desglosado")

    if cond_recompras or cond_bpa_pos:
        txt_mot = f"Recompras netas ({variacion_acciones:+.2f}%)" if cond_recompras else f"Crecimiento BPA 3Y ({crecimiento_bpa_3y:+.2f}%)"
        st.success(f"{t_cap_t} Asignación de Capital: Cumplido vía {txt_mot}")
    else:
        st.error(f"{t_cap_t} Asignación de Capital: Sin recompras netas y con BPA estancado a 3 años")

    st.markdown("#### 🛡️ 4. Resiliencia, Historial y Foso Económico")
    if cond_roic and cond_rev:
        st.success(f"{t_foso_t} Foso Económico: Rentabilidad s/ Capital y Ventas 3A ({revenue_cagr_3y:+.1f}%) positivas y robustas")
    elif cond_roic or cond_rev:
        st.warning(f"{t_foso_t} Foso Económico Parcial: Uno de los dos filtros (ROIC/ROE o Ventas) requiere seguimiento")
    else:
        st.error(f"{t_foso_t} Foso Económico Débil: Retorno sobre capital bajo y ventas estancadas")

    if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15: 
        txt_fatiga_hist = " (Alerta: se detecta fatiga en la última subida)" if fatiga_dividendo else ""
        st.success(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes{txt_fatiga_hist}")
    elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: 
        st.warning(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | {racha_sin_recortes} años sin recortes")
    elif racha_sin_recortes >= 5: 
        st.warning(f"{t_hist} Historial y Resiliencia: {racha_sin_recortes} años consecutivos sin recortes")
    else: 
        st.error(f"{t_hist} Historial y Resiliencia: {años_pagando} años pagando | Racha sin recortes: {racha_sin_recortes} años")

    if dgr_5y is not None and dgr_5y >= 5.0: 
        st.success(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Bate la inflación histórica con holgura ≥ 5.0%)")
    elif dgr_5y is not None and dgr_5y >= 2.5: 
        st.warning(f"{t_dgr_t} Crecimiento Real (DGR 5A): {dgr_5y:.2f}% (Crecimiento moderado ≥ 2.5%)")
    else: 
        st.error(f"{t_dgr_t} Crecimiento Real (DGR 5A): {f'{dgr_5y:.2f}%' if dgr_5y is not None else 'N/D'} (Inferior a 2.5%)")

    # ==========================================
    # PANEL: LOS 8 GRÁFICOS FINANCIEROS COMPLETOS (USANDO CACHÉ Y FX_RATE)
    # ==========================================
    st.divider()
    st.markdown("### 📉 Análisis Fundamental Visual")
    
    try:
        def get_annual_series(df, col_names, mult=1.0):
            if df is not None and not df.empty:
                for col in col_names:
                    if col in df.index:
                        s = df.loc[col].dropna()
                        if not s.empty:
                            s.index = pd.to_datetime(s.index).year
                            return (s.sort_index() * mult)
            return pd.Series(dtype=float)

        fcf_s = get_annual_series(cf_stmt, ['Operating Cash Flow', 'Free Cash Flow'] if es_reit_puro else ['Free Cash Flow'], fx_rate)
        div_s = abs(get_annual_series(cf_stmt, ['Cash Dividends Paid', 'Dividends Paid', 'Common Stock Dividend Paid'], fx_rate))
        rev_s = get_annual_series(inc_stmt, ['Total Revenue', 'Operating Revenue'], fx_rate)
        net_s = get_annual_series(inc_stmt, ['Net Income', 'Net Income Common Stockholders'], fx_rate)
        debt_s = get_annual_series(bs_stmt, ['Total Debt'], fx_rate)
        cash_s = get_annual_series(bs_stmt, ['Cash And Cash Equivalents', 'Cash'], fx_rate)
        shares_s = get_annual_series(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'], 1.0)
        ebitda_s = get_annual_series(inc_stmt, ['EBITDA', 'Normalized EBITDA'], fx_rate)
        
        yearly_closes = historial_completo['Close'].resample('YE').last()
        yearly_closes.index = yearly_closes.index.year

        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.markdown("#### 📈 Evolución del Yield Histórico")
            df_yield_chart = yields_validos.copy()
            fig_yield = go.Figure()
            fig_yield.add_trace(go.Scatter(x=df_yield_chart.index, y=df_yield_chart.values, mode='lines', line=dict(color='#00d4ff', width=2), name='Histórico', showlegend=False))
            fig_yield.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b")
            fig_yield.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354")
            fig_yield.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b")
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Techo: {yield_sobrevalorado:.2f}%"))
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {yield_medio:.2f}%"))
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Suelo: {yield_infravalorado:.2f}%"))
            fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[-1]], y=[yield_actual], mode='markers', marker=dict(color='#00d4ff', size=10, symbol='diamond'), name=f"Actual: {yield_actual:.2f}%"))
            fig_yield.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Rentabilidad (Yield %)", tickformat=".2f"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            fig_yield.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_yield, use_container_width=True)

        with col_graf2:
            st.markdown("#### 📉 Drawdown Histórico")
            df_dd = historial_analisis[['Close']].copy()
            df_dd['Max'] = df_dd['Close'].cummax()
            df_dd['Drawdown'] = (df_dd['Close'] - df_dd['Max']) / df_dd['Max'] * 100
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(x=df_dd.index, y=df_dd['Drawdown'], fill='tozeroy', mode='lines', line=dict(color='#ff4b4b', width=1.5), fillcolor='rgba(255, 75, 75, 0.2)', name='Drawdown %'))
            fig_dd.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Caída desde Máximos (%)", tickformat=".1f", ticksuffix="%"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_dd, use_container_width=True)

        st.markdown("---")
        st.markdown("#### ⏳ Yield on Cost Histórico")
        if not historial_analisis.empty and forward_dividend > 0:
            df_yoc_hist = historial_analisis[['Close', 'Yield_Diario']].dropna().copy()
            df_yoc_hist['YoC_Hist'] = (forward_dividend / df_yoc_hist['Close']) * 100
            df_yoc_hist.replace([np.inf, -np.inf], np.nan, inplace=True)
            df_yoc_hist = df_yoc_hist.dropna(subset=['YoC_Hist'])
            
            fig_yoc_hist = go.Figure()
            fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['Yield_Diario'], mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1.5), name='Yield Histórico (En su día)'))
            fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['YoC_Hist'], mode='lines', line=dict(color='#faca2b', width=2), name='Yield on Cost (Hoy)'))
            fig_yoc_hist.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b", opacity=0.6)
            fig_yoc_hist.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354", opacity=0.6)
            fig_yoc_hist.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b", opacity=0.6)
            fig_yoc_hist.add_hline(y=yield_actual, line_dash="dash", line_color="#00d4ff")
            fig_yoc_hist.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=50), height=380, yaxis=dict(title="Rentabilidad (%)", tickformat=".2f"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
            fig_yoc_hist.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig_yoc_hist, use_container_width=True)

        st.markdown("---")
        col_graf3, col_graf4 = st.columns(2)
        with col_graf3:
            st.markdown(f"#### 💵 Sostenibilidad: {etiqueta_fcf} vs Dividendos")
            years_sost = sorted(list(set(fcf_s.index) & set(div_s.index)))
            if years_sost:
                x_years = [str(y) for y in years_sost]
                fcf_vals = [fcf_s[y] for y in years_sost]
                div_vals = [div_s[y] for y in years_sost]
                payout_vals = [(div/fcf)*100 if fcf > 0 else 0 for fcf, div in zip(fcf_vals, div_vals)]
                fig_sost = make_subplots(specs=[[{"secondary_y": True}]])
                fig_sost.add_trace(go.Bar(x=x_years, y=fcf_vals, name=etiqueta_fcf, marker_color='#00d4ff'), secondary_y=False)
                fig_sost.add_trace(go.Bar(x=x_years, y=div_vals, name='Dividendos', marker_color='#ff9800'), secondary_y=False)
                fig_sost.add_trace(go.Scatter(x=x_years, y=payout_vals, name='Payout %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in payout_vals], textposition="top center", line=dict(color='#ff4b4b', width=2)), secondary_y=True)
                fig_sost.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
                st.plotly_chart(fig_sost, use_container_width=True)
            else: st.info("Datos anuales insuficientes para el gráfico de Sostenibilidad.")

        with col_graf4:
            st.markdown("#### 📊 Ingresos vs Beneficio Neto")
            years_rev = sorted(list(set(rev_s.index) & set(net_s.index)))
            if years_rev:
                x_years_rev = [str(y) for y in years_rev]
                rev_vals = [rev_s[y] for y in years_rev]
                net_vals = [net_s[y] for y in years_rev]
                margin_vals = [(n/r)*100 if r > 0 else 0 for r, n in zip(rev_vals, net_vals)]
                fig_ing = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=rev_vals, name='Ingresos', marker_color='#21c354'), secondary_y=False)
                fig_ing.add_trace(go.Bar(x=x_years_rev, y=net_vals, name='B. Neto', marker_color='#faca2b'), secondary_y=False)
                fig_ing.add_trace(go.Scatter(x=x_years_rev, y=margin_vals, name='Margen Neto %', mode='lines+markers+text', text=[f"{val:.1f}%" for val in margin_vals], textposition="top center", line=dict(color='#00d4ff', width=2)), secondary_y=True)
                fig_ing.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
                st.plotly_chart(fig_ing, use_container_width=True)
            else: st.info("Datos anuales insuficientes para el gráfico de Ingresos.")

        col_graf5, col_graf6 = st.columns(2)
        with col_graf5:
            st.markdown(f"#### ⚖️ Valoración Múltiplo: EV / {etiqueta_fcf.split()[0]}")
            years_ev = sorted(list(set(fcf_s.index) & set(shares_s.index) & set(yearly_closes.index)))
            if years_ev:
                x_years_ev = [str(y) for y in years_ev]
                fcf_ev_vals = [fcf_s[y] for y in years_ev]
                ev_vals = [yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0) for y in years_ev]
                ratio_vals = [(ev/fcf) if fcf > 0 else 0 for ev, fcf in zip(ev_vals, fcf_ev_vals)]
                fig_ev = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=ev_vals, name='EV', marker_color='#9c27b0'), secondary_y=False)
                fig_ev.add_trace(go.Bar(x=x_years_ev, y=fcf_ev_vals, name='Flujo Caja', marker_color='#00d4ff'), secondary_y=False)
                fig_ev.add_trace(go.Scatter(x=x_years_ev, y=ratio_vals, name='Ratio EV/Caja', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_vals], textposition="top center", line=dict(color='#21c354', width=2)), secondary_y=True)
                fig_ev.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_ev, use_container_width=True)
            else: st.info("Datos insuficientes para el gráfico EV/FCF.")

        with col_graf6:
            st.markdown("#### 🏢 Múltiplo Operativo: EV / EBITDA")
            years_ebitda = sorted(list(set(ebitda_s.index) & set(shares_s.index) & set(yearly_closes.index)))
            if years_ebitda:
                x_years_eb = [str(y) for y in years_ebitda]
                ebitda_vals = [ebitda_s[y] for y in years_ebitda]
                ev_eb_vals = [yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0) for y in years_ebitda]
                ratio_eb_vals = [(ev/eb) if eb > 0 else 0 for ev, eb in zip(ev_eb_vals, ebitda_vals)]
                fig_ebitda = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ebitda_vals, name='EBITDA', marker_color='#0288d1'), secondary_y=False)
                fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ev_eb_vals, name='EV', marker_color='#ff9800'), secondary_y=False)
                fig_ebitda.add_trace(go.Scatter(x=x_years_eb, y=ratio_eb_vals, name='Ratio EV/EBITDA', mode='lines+markers+text', text=[f"{val:.1f}x" for val in ratio_eb_vals], textposition="top center", line=dict(color='#ff1744', width=2)), secondary_y=True)
                fig_ebitda.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=300, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_ebitda, use_container_width=True)
            else: st.info("Datos insuficientes para el gráfico EV/EBITDA.")

    except Exception as e:
        st.warning(f"No se han podido cargar todos los gráficos anuales: {e}")

    # ==========================================
    # PROYECCIÓN YIELD ON COST A 15 AÑOS
    # ==========================================
    st.divider()
    st.markdown("#### 🔮 Proyección de Rentabilidad sobre Coste (Yield on Cost a 15 Años)")
    
    val_5y = dgr_5y if dgr_5y is not None else None
    val_periodo = dgr_periodo if dgr_periodo is not None else None

    if val_5y is not None and val_periodo is not None:
        dgr_proyeccion = min(val_5y, val_periodo)
        txt_ritmo = "Ritmo Conservador (5A)" if dgr_proyeccion == val_5y else f"Ritmo Conservador ({años_analisis}A)"
    elif val_5y is not None:
        dgr_proyeccion = val_5y
        txt_ritmo = "Ritmo Disponible (5A)"
    elif val_periodo is not None:
        dgr_proyeccion = val_periodo
        txt_ritmo = f"Ritmo Disponible ({años_analisis}A)"
    else:
        dgr_proyeccion = 0.0
        txt_ritmo = "Crecimiento Nulo / Estancado"
    
    dgr_proyeccion = min(dgr_proyeccion, 15.0)
    años_proyeccion = list(range(1, 16))
    
    div_bruto_proyectado = [forward_dividend * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_bruto_lista = [yield_actual * ((1 + dgr_proyeccion/100) ** año) for año in años_proyeccion]
    yoc_neto_lista = [bruto * net_mult for bruto in yoc_bruto_lista]
    
    x_labels_yoc = [f"{año_actual + año}<br><span style='color:#faca2b; font-size:12px'>{yoc_n:.1f}%</span>" for año, yoc_n in zip(años_proyeccion, yoc_neto_lista)]

    color_barras = '#00d4ff' if dgr_proyeccion >= 0 else '#ff4b4b'
    color_linea = '#21c354' if dgr_proyeccion >= 0 else '#ff4b4b'
    signo_dgr = "+" if dgr_proyeccion > 0 else ""

    st.markdown(f"> **Cálculo de la proyección:** Basado en {txt_ritmo} con un <span style='color:{color_linea};'>**{signo_dgr}{dgr_proyeccion:.1f}% anual constante**</span>.", unsafe_allow_html=True)

    fig_yoc_p = go.Figure()
    fig_yoc_p.add_trace(go.Bar(x=x_labels_yoc, y=div_bruto_proyectado, name=f'Div. Esperado ({sym})', marker_color=color_barras, yaxis='y1', text=[f"{val:.2f}{sym}" for val in div_bruto_proyectado], textposition='auto'))
    fig_yoc_p.add_trace(go.Scatter(x=x_labels_yoc, y=yoc_neto_lista, name="YoC Neto (%)", mode='lines+markers', line=dict(color=color_linea, width=3), marker=dict(size=8), yaxis='y2'))
    fig_yoc_p.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=40), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=dict(text=f"Dividendo ({sym})", font=dict(color=color_barras)), tickfont=dict(color=color_barras)), yaxis2=dict(title=dict(text="YoC Neto (%)", font=dict(color="#faca2b")), tickfont=dict(color="#faca2b"), overlaying='y', side='right', showgrid=False), legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
    st.plotly_chart(fig_yoc_p, use_container_width=True)


# ==========================================
# INTERFAZ DIRECTA CON REFRESCO EN TIEMPO REAL
# ==========================================
st.title("🔍 Análisis Individual — Geraldine Weiss DGI")

if "analizar_activo" not in st.session_state:
    st.session_state.analizar_activo = False

col_input1, col_input2, col_input3, col_input4 = st.columns([1.2, 1, 1, 1.3])
with col_input1: 
    ticker_input = st.text_input("Ticker individual:", "MKC").upper().strip()
with col_input2: 
    años_analisis = st.selectbox("Periodo Histórico:", [5, 10, 12, 15, 20], index=2)
with col_input3: 
    impuesto = st.number_input("Retención IRPF (%)", value=19.0, step=1.0, key="imp_ind")
with col_input4:
    capital_simulado = st.number_input("Capital Simulado Orden:", value=2000.0, step=250.0)

aplicar_merma = st.checkbox("Aplicar merma fiscal en origen no recuperable (>15% en Suiza, Alemania, Francia, Dinamarca, Irlanda)", value=True)

if st.button("🚀 Analizar / Actualizar Cotización en Vivo", use_container_width=True):
    # Limpia la caché de precio para forzar lectura en tiempo real en mercado abierto
    cargar_cotizacion_tiempo_real.clear()
    st.session_state.analizar_activo = True

if st.session_state.analizar_activo:
    with st.spinner(f"Actualizando cotización en vivo y métricas de {ticker_input}..."):
        try:
            screener_weiss_definitivo(ticker_input, años_analisis, impuesto, aplicar_merma, capital_simulado)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
