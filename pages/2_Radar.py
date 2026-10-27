import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import time
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Radar Watchlist - Weiss DGI", page_icon="📡", layout="wide")

ARCHIVO_WATCHLIST = "watchlist.txt"

MERMA_ORIGEN_PAIS = {
    'Switzerland': 20.0, 'Denmark': 12.0, 'Germany': 11.375, 'France': 10.0, 'Ireland': 10.0
}

ARISTOCRATAS_Y_KINGS = {
    'JNJ', 'PG', 'KO', 'PEP', 'MMM', 'LOW', 'CL', 'WMT', 'EMR', 'GPC', 'SYY', 'APD',
    'BDX', 'HRL', 'ITW', 'SWK', 'FRT', 'O', 'ABBV', 'ABT', 'MCD', 'ADP', 'TGT',
    'MKC', 'GD', 'CAT', 'CVX', 'XOM', 'IBM', 'ED', 'AWR', 'CINF', 'DOV', 'PH',
    'PPG', 'LEG', 'SJW', 'ADM', 'CB', 'AFL', 'ROP', 'SHW', 'SPGI', 'ECL', 'CTAS',
    'WPC', 'NNN', 'ESS', 'MAA', 'KMB', 'GIS'
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

def interpolar_puntos(valor, umbral_max, umbral_med, pts_max, pts_med, inverso=False):
    if valor is None or pd.isna(valor):
        return 0.0
    if not inverso:
        if valor >= umbral_max: return float(pts_max)
        if valor < umbral_med: return 0.0
        if umbral_max == umbral_med: return float(pts_max)
        ratio = (valor - umbral_med) / (umbral_max - umbral_med)
        return round(float(pts_med + ratio * (pts_max - pts_med)), 2)
    else:
        if valor < 0: return 0.0
        if valor <= umbral_max: return float(pts_max)
        if valor > umbral_med: return 0.0
        if umbral_med == umbral_max: return float(pts_max)
        ratio = (umbral_med - valor) / (umbral_med - umbral_max)
        return round(float(pts_med + ratio * (pts_max - pts_med)), 2)

def ultimo_valor_tabla(df, claves):
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    return float(s.iloc[-1])
    return 0.0

@st.cache_data(ttl=86400, show_spinner=False)
def obtener_fx_rate(curr_fin, curr_base):
    if not curr_fin or not curr_base or curr_fin == curr_base:
        return 1.0
    try:
        fx_pair = f"{curr_fin}{curr_base}=X"
        fx_data = yf.Ticker(fx_pair).history(period="5d")
        if not fx_data.empty:
            return float(fx_data['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return 1.0

# ==========================================
# GESTIÓN DEL ARCHIVO PERSISTENTE DE WATCHLIST
# ==========================================
def cargar_watchlist():
    if os.path.exists(ARCHIVO_WATCHLIST):
        try:
            with open(ARCHIVO_WATCHLIST, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return contenido
        except Exception:
            pass
    return "REP.MC, KHC, ENG.MC, DGE.L, PFE, BATS.L, RKT.L, TGT, WPC, HRL, BMY, O, RED.MC, CMCSA, EBRO.MC, LOG.MC, VZ, ACN, WKL.AS, VOW3.DE, PEP, KO, VICI, IIPR, HSY, MDLZ, UPS, GOOGL, UNH, GIS, ADP, LOW, MCD, VIS.MC, MC.PA, NKE, MKC, JNJ, PG, CL, WMT, MDT, ABT, ABBV, BDX, EMR, GPC, SYY, APD, STAG, MRK, MO, ABF.L, PBR, OHI, CSCO, PM, CVX, XOM, TAP, IBE.MC, GAW.L, AD.AS, ITX.MC, ELE.MC, VID.MC, UNA.AS"

def guardar_watchlist(texto):
    try:
        with open(ARCHIVO_WATCHLIST, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# ==========================================
# MOTOR DE DESCARGA CON CACHÉ EN DISCO PERSISTENTE
# Evita baneos de Yahoo al guardar balances en disco durante 7 días
# ==========================================
@st.cache_data(persist="disk", ttl=604800, show_spinner=False)
def descargar_fundamentales_persistentes_disco(t_clean):
    """
    Descarga estados contables e info pesada y los guarda en DISCO duro por 7 días.
    Nunca vuelve a pedir los balances a Yahoo si ya están en disco.
    """
    ticker = yf.Ticker(t_clean)
    info = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    dividendos = pd.Series(dtype=float)
    try:
        dividendos = ticker.dividends
    except Exception:
        pass

    historial = pd.DataFrame()
    try:
        historial = ticker.history(period="20y", auto_adjust=False)
    except Exception:
        pass

    inc_stmt, bs_stmt, cf_stmt = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        if ticker.income_stmt is not None and not ticker.income_stmt.empty:
            inc_stmt = ticker.income_stmt.T.sort_index().T
    except Exception:
        pass
    try:
        if ticker.balance_sheet is not None and not ticker.balance_sheet.empty:
            bs_stmt = ticker.balance_sheet.T.sort_index().T
    except Exception:
        pass
    try:
        if ticker.cashflow is not None and not ticker.cashflow.empty:
            cf_stmt = ticker.cashflow.T.sort_index().T
    except Exception:
        pass

    return info, dividendos, historial, inc_stmt, bs_stmt, cf_stmt

@st.cache_data(ttl=60, show_spinner=False)
def obtener_cotizacion_viva_radar(t_clean):
    """Cotización ultra-rápida y ligera (renovada cada 60s), inmune a rate limits."""
    try:
        t = yf.Ticker(t_clean)
        fast = t.fast_info
        if fast is not None and fast.last_price is not None:
            return float(fast.last_price), getattr(fast, 'currency', None), getattr(fast, 'shares', None)
    except Exception:
        pass
    return None, None, None

def analizar_empresa_rapido(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    try:
        t_clean = ticker_symbol.strip().upper()
        
        # 1. Recuperar balances y dividendos (desde disco duro si ya se consultó)
        info, dividendos_raw, historial_raw, inc_stmt, bs_stmt, cf_stmt = descargar_fundamentales_persistentes_disco(t_clean)

        if dividendos_raw.empty or len(historial_raw) < 200:
            return None

        # 2. Cotización en tiempo real
        precio_vivo, curr_vivo, shares_vivo = obtener_cotizacion_viva_radar(t_clean)

        def get_safe(key, default=0.0):
            val = info.get(key)
            if val is None: return default
            try: return float(val)
            except (ValueError, TypeError): return default

        currency_raw = curr_vivo or info.get('currency', 'USD')
        es_peniques_uk = (currency_raw == 'GBp')
        currency = 'GBP' if es_peniques_uk else currency_raw
        curr_fin = info.get('financialCurrency', currency) or currency
        if curr_fin == 'GBp': curr_fin = 'GBP'
        fx_rate = obtener_fx_rate(curr_fin, currency)

        sym_m = "€" if currency == "EUR" else ("£" if currency == "GBP" else "$")

        historial = historial_raw.copy()
        dividendos = dividendos_raw.copy()
        historial.index = historial.index.tz_localize(None).normalize()
        dividendos.index = dividendos.index.tz_localize(None).normalize()
        dividendos = dividendos.groupby(dividendos.index).sum()

        if precio_vivo is not None and precio_vivo > 0 and not historial.empty:
            historial.iloc[-1, historial.columns.get_loc('Close')] = precio_vivo

        if es_peniques_uk:
            for col in ['Open', 'High', 'Low', 'Close']:
                if col in historial.columns:
                    historial[col] = historial[col] / 100.0
            if dividendos.median() > (historial['Close'].median() * 0.25):
                dividendos = dividendos / 100.0

        ahora_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
        año_actual = ahora_madrid.year
        hoy_ts = pd.Timestamp.now().normalize()

        fecha_corte = hoy_ts - pd.DateOffset(years=años_analisis)
        ha = historial[historial.index >= fecha_corte].copy()
        if ha.empty:
            return None

        precio_actual = float(ha['Close'].dropna().iloc[-1])

        # Parámetros sectoriales y fiscales
        sector_en = info.get('sector', '')
        industry_en = info.get('industry', '')
        pais = info.get('country', 'Desconocido')
        if pais == 'Desconocido':
            if t_clean.endswith('.MC'): pais = 'Spain'
            elif t_clean.endswith('.PA'): pais = 'France'
            elif t_clean.endswith('.DE'): pais = 'Germany'
            elif t_clean.endswith('.AS'): pais = 'Netherlands'
            elif t_clean.endswith('.L'): pais = 'United Kingdom'

        es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
        es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
        es_telecom = 'telecom' in industry_en.lower() or 'communication' in sector_en.lower()
        es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
        es_defensivo = 'consumer defensive' in sector_en.lower() or 'consumer staples' in sector_en.lower() or 'healthcare' in sector_en.lower()
        es_aristocrata_reconocida = t_clean in ARISTOCRATAS_Y_KINGS

        merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
        net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

        # ==========================================
        # MOTOR DE DIVIDENDOS BLINDADO (CALIBRACIÓN ROBUSTA)
        # ==========================================
        divs_por_año = dividendos.groupby(dividendos.index.year).sum()

        años_div = dividendos.index.year
        conteo_por_año = años_div.value_counts()
        conteo_closed = conteo_por_año[(conteo_por_año.index < año_actual) & (conteo_por_año.index >= año_actual - 5)]
        if conteo_closed.empty:
            conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
        mediana_pagos_año = float(conteo_closed.median()) if not conteo_closed.empty else 4.0

        if mediana_pagos_año >= 10: pagos_por_año = 12
        elif mediana_pagos_año >= 3: pagos_por_año = 4
        elif mediana_pagos_año >= 1.5: pagos_por_año = 2
        else: pagos_por_año = 1

        ult_fecha_div = dividendos.index[-1]
        div_ttm = float(dividendos[dividendos.index > (ult_fecha_div - pd.DateOffset(days=370))].sum())
        años_cerrados = divs_por_año[divs_por_año.index < año_actual]
        ultimo_año_completo = float(años_cerrados.iloc[-1]) if not años_cerrados.empty else 0.0

        forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate', 0.0))
        if es_peniques_uk and forward_dividend > (precio_actual * 0.25):
            forward_dividend /= 100.0

        ult_cupon = float(dividendos.iloc[-1])
        candidato_fwd = ult_cupon * pagos_por_año

        # Corrección de frecuencia para STAG u otras que alternen mensual/trimestral
        if div_ttm > 0 and candidato_fwd > (div_ttm * 1.5):
            if abs(ult_cupon * 4 - div_ttm) < abs(candidato_fwd - div_ttm):
                pagos_por_año = 4
                candidato_fwd = ult_cupon * 4
            else:
                candidato_fwd = div_ttm

        if forward_dividend <= 0 or forward_dividend > (max(div_ttm, ultimo_año_completo) * 1.7):
            forward_dividend = candidato_fwd if candidato_fwd > 0 else (div_ttm if div_ttm > 0 else ultimo_año_completo)
        elif pagos_por_año <= 2 and forward_dividend < (div_ttm * 0.65):
            forward_dividend = max(div_ttm, ultimo_año_completo)

        ha['Year'] = ha.index.year
        ha['Div_Anual'] = ha['Year'].map(divs_por_año)
        ha.loc[ha['Year'] == año_actual, 'Div_Anual'] = forward_dividend
        ha['Div_Anual'] = ha['Div_Anual'].bfill().ffill()

        ha['Yield_Diario'] = (ha['Div_Anual'] / ha['Close']) * 100
        ha.replace([np.inf, -np.inf], np.nan, inplace=True)
        yields_validos = ha['Yield_Diario'].dropna()
        yields_validos = yields_validos[yields_validos > 0]

        yield_infravalorado = float(yields_validos.quantile(0.95))
        yield_acumulacion = float(yields_validos.quantile(0.90))
        yield_sobrevalorado = float(yields_validos.quantile(0.05))
        yield_medio = float(yields_validos.mean())

        precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0.0
        precio_acumulacion = (forward_dividend / yield_acumulacion) * 100 if yield_acumulacion > 0 else 0.0
        precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0.0
        precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0.0

        yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0
        yield_neto = yield_actual * net_mult
        div_neto_absoluto = forward_dividend * net_mult

        # ==========================================
        # FUNDAMENTALES CON RESPALDO CONTABLE TOTAL
        # ==========================================
        # 1. Acciones
        shares = get_safe('sharesOutstanding', 0.0)
        if shares <= 0 and shares_vivo: shares = shares_vivo
        if shares <= 0: shares = ultimo_valor_tabla(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'])

        # 2. BPA y PER
        bpa_trailing = get_safe('trailingEps', 0.0)
        if bpa_trailing == 0:
            bpa_trailing = ultimo_valor_tabla(inc_stmt, ['Diluted EPS', 'Basic EPS']) * fx_rate

        per = get_safe('trailingPE', 0.0)
        if per <= 0 and bpa_trailing > 0 and precio_actual > 0:
            per = precio_actual / bpa_trailing
        if per <= 0:
            per = get_safe('forwardPE', 0.0)

        # 3. Payout BPA
        payout_bpa = get_safe('payoutRatio', 0.0) * 100
        if (payout_bpa <= 0 or payout_bpa > 300) and bpa_trailing > 0:
            payout_bpa = (forward_dividend / bpa_trailing) * 100

        # 4. Deuda y Caja
        total_debt = get_safe('totalDebt', 0.0) * fx_rate
        if total_debt <= 0:
            total_debt = ultimo_valor_tabla(bs_stmt, ['Total Debt', 'Long Term Debt And Capital Lease Obligation', 'Long Term Debt']) * fx_rate

        total_cash = get_safe('totalCash', 0.0) * fx_rate
        if total_cash <= 0:
            total_cash = ultimo_valor_tabla(bs_stmt, ['Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents', 'Cash']) * fx_rate

        # 5. EBITDA y EBIT
        ebitda = get_safe('ebitda', 0.0) * fx_rate
        if ebitda <= 0:
            ebitda = ultimo_valor_tabla(inc_stmt, ['EBITDA', 'Normalized EBITDA', 'Operating Income']) * fx_rate

        ebit_val = get_safe('operatingIncome', 0.0) * fx_rate
        if ebit_val <= 0:
            ebit_val = ultimo_valor_tabla(inc_stmt, ['Operating Income', 'EBIT']) * fx_rate
        if ebitda <= 0 and ebit_val > 0:
            ebitda = ebit_val * 1.15

        # 6. Flujo de Caja
        fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
        if fcf_raw == 0:
            fcf_raw = ultimo_valor_tabla(cf_stmt, ['Free Cash Flow']) * fx_rate

        ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
        if ocf_raw == 0:
            ocf_raw = ultimo_valor_tabla(cf_stmt, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities']) * fx_rate

        if fcf_raw == 0 and ocf_raw != 0:
            capex_val = abs(ultimo_valor_tabla(cf_stmt, ['Capital Expenditure', 'Capital Expenditures'])) * fx_rate
            fcf_raw = ocf_raw - capex_val

        # Para REITs el flujo de referencia siempre es OCF/FFO
        flujo_caja_referencia = ocf_raw if es_reit_puro else fcf_raw

        # 7. Fondos Propios y ROE
        total_equity_raw = get_safe('totalStockholderEquity', 0.0) * fx_rate
        if total_equity_raw <= 0:
            total_equity_raw = ultimo_valor_tabla(bs_stmt, ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity']) * fx_rate

        net_inc_val = ultimo_valor_tabla(inc_stmt, ['Net Income', 'Net Income Common Stockholders']) * fx_rate
        roe = get_safe('returnOnEquity', 0.0) * 100
        if roe == 0 and total_equity_raw > 0 and net_inc_val > 0:
            roe = (net_inc_val / total_equity_raw) * 100

        # 8. Márgenes
        operating_margins = get_safe('operatingMargins', 0.0) * 100
        rev_tabla = ultimo_valor_tabla(inc_stmt, ['Total Revenue', 'Operating Revenue']) * fx_rate
        if operating_margins == 0 and rev_tabla > 0 and ebit_val > 0:
            operating_margins = (ebit_val / rev_tabla) * 100

        pb = get_safe('priceToBook', -1.0)
        current_ratio = get_safe('currentRatio', 0.0)
        if current_ratio <= 0 and not bs_stmt.empty:
            ca_v = ultimo_valor_tabla(bs_stmt, ['Current Assets', 'Total Current Assets'])
            cl_v = ultimo_valor_tabla(bs_stmt, ['Current Liabilities', 'Total Current Liabilities'])
            if cl_v > 0: current_ratio = ca_v / cl_v

        es_quasi_reit_o_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 24.0) and (total_equity_raw <= 0 or pb < 0)
        es_regulada_o_reit = es_reit_puro or es_utility_pura or es_quasi_reit_o_recompras

        payout_lim_bpa = 85.0 if es_regulada_o_reit else 60.0
        payout_ama_bpa = 92.0 if es_regulada_o_reit else 75.0
        payout_limite_fcf = 78.0 if es_reit_puro else (72.0 if es_utility_pura else 58.0)
        payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 80.0

        # 9. Deuda Neta / EBITDA
        deuda_neta = max(0.0, total_debt - total_cash)
        if es_financiera:
            deuda_ebitda = -1.0
        elif ebitda > 0:
            deuda_ebitda = deuda_neta / ebitda
        elif total_debt > 0:
            deuda_ebitda = 999.0
        elif not bs_stmt.empty and 'Total Debt' in bs_stmt.index:
            deuda_ebitda = 0.0
        else:
            deuda_ebitda = -1.0

        # 10. Payout FCF y P/FCF
        payout_fcf, p_fcf = -1.0, -1.0
        if flujo_caja_referencia != 0 and shares > 0 and forward_dividend > 0:
            fcf_per_share = flujo_caja_referencia / shares
            if fcf_per_share > 0:
                payout_fcf = (forward_dividend / fcf_per_share) * 100
                p_fcf = precio_actual / fcf_per_share
            elif fcf_per_share < 0:
                payout_fcf = 999.0

        # 11. ROIC
        roic = None
        try:
            inv_cap = (total_debt + max(0.0, total_equity_raw)) - total_cash
            if inv_cap <= 0 and not bs_stmt.empty and 'Total Assets' in bs_stmt.index:
                tot_assets = float(bs_stmt.loc['Total Assets'].dropna().iloc[-1]) * fx_rate
                curr_liab = float(bs_stmt.loc['Current Liabilities'].dropna().iloc[-1]) * fx_rate if 'Current Liabilities' in bs_stmt.index else 0.0
                inv_cap = tot_assets - curr_liab - total_cash
            if inv_cap > 0 and ebit_val > 0:
                roic = ((ebit_val * 0.79) / inv_cap) * 100
        except Exception:
            pass

        metrica_rentabilidad = roe if es_financiera else (roic if roic is not None else (roe if roe > 0 else (operating_margins if es_reit_puro else None)))

        # 12. Crecimientos 3A
        crecimiento_bpa_3y = None
        if not inc_stmt.empty:
            for key in ['Diluted EPS', 'Basic EPS']:
                if key in inc_stmt.index:
                    eps_series = inc_stmt.loc[key].dropna()
                    if len(eps_series) >= 4 and eps_series.iloc[-4] > 0 and eps_series.iloc[-1] > 0:
                        crecimiento_bpa_3y = (((eps_series.iloc[-1] / eps_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                    break
        if crecimiento_bpa_3y is None and info.get('earningsGrowth') is not None:
            crecimiento_bpa_3y = float(info.get('earningsGrowth')) * 100

        revenue_cagr_3y = None
        if not inc_stmt.empty:
            for k in ['Total Revenue', 'Operating Revenue']:
                if k in inc_stmt.index:
                    rev_series = inc_stmt.loc[k].dropna()
                    if len(rev_series) >= 4 and rev_series.iloc[-4] > 0 and rev_series.iloc[-1] > 0:
                        revenue_cagr_3y = (((rev_series.iloc[-1] / rev_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                    break
        if revenue_cagr_3y is None and info.get('revenueGrowth') is not None:
            revenue_cagr_3y = float(info.get('revenueGrowth')) * 100

        # Cobertura de intereses
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
            except Exception: pass
        if cobertura_intereses is None and ebit_val > 0 and total_debt > 0:
            cobertura_intereses = ebit_val / (total_debt * 0.045)
        elif cobertura_intereses is None and deuda_neta == 0:
            cobertura_intereses = 25.0

        dividendos_barras = divs_por_año.copy()
        if año_actual in dividendos_barras.index:
            dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)
        else:
            dividendos_barras.loc[año_actual] = forward_dividend

        años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
        if es_aristocrata_reconocida:
            años_pagando = max(años_pagando, 25)

        dgr_5y, dgr_periodo, dgr_1y = None, None, None
        if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
            dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
        if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
            dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1/5) - 1) * 100
        if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
            dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1/años_analisis) - 1) * 100

        fatiga_dividendo = bool(dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0 and (dgr_1y / dgr_5y) < 0.45)

        racha_sin_recortes = 0
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.98:
                    racha_sin_recortes += 1
                else: break
        if es_aristocrata_reconocida and (dgr_1y is None or dgr_1y >= 0.0):
            racha_sin_recortes = max(racha_sin_recortes, 25)

        variacion_acciones, recompras_anualizadas = None, 0.0
        try:
            if not inc_stmt.empty:
                for key in ['Diluted Average Shares', 'Basic Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna()
                        sh_data = sh_data[sh_data > 0]
                        if len(sh_data) >= 2:
                            sy = sh_data.groupby(pd.to_datetime(sh_data.index).year).last().sort_index()
                            acc_ini, acc_fin = float(sy.iloc[0]), float(sy.iloc[-1])
                            n_anios_sh = max(1, int(sy.index[-1] - sy.index[0]))
                            if acc_ini > 0 and (acc_fin / acc_ini) > 0.10:
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100
                                break
        except Exception: pass
        recompras_anualizadas = max(-5.0, min(8.0, recompras_anualizadas))

        # ==========================================
        # 1. SCORE DE CALIDAD FORENSE (0 a 10 PTS)
        # ==========================================
        if es_reit_puro:
            lim_deuda_optima, lim_deuda_aceptable = 5.5, 7.0
        elif es_utility_pura or es_quasi_reit_o_recompras:
            lim_deuda_optima, lim_deuda_aceptable = 3.8, 5.2
        elif es_defensivo or es_telecom:
            lim_deuda_optima, lim_deuda_aceptable = 2.8, 4.0
        else:
            lim_deuda_optima, lim_deuda_aceptable = 2.0, 3.4

        if es_financiera:
            pts_deuda = interpolar_puntos(roe, 14.0, 7.5, 1.5, 0.3, inverso=False)
            pts_cob = 0.5 if (current_ratio >= 1.0 or roe >= 10.0) else 0.1
        else:
            deuda_eval = deuda_ebitda if deuda_ebitda >= 0 else 2.5
            pts_deuda = interpolar_puntos(deuda_eval, lim_deuda_optima, lim_deuda_aceptable, 1.5, 0.25, inverso=True)
            u_cob_max = 3.0 if es_reit_puro else 6.0
            u_cob_min = 1.7 if es_reit_puro else 2.5
            pts_cob = interpolar_puntos(cobertura_intereses, u_cob_max, u_cob_min, 0.5, 0.1, inverso=False) if cobertura_intereses is not None else (0.5 if deuda_neta == 0 else 0.15)
        pilar1 = min(2.0, pts_deuda + pts_cob)

        # PILAR 2: COBERTURA Y CALIDAD DE CAJA (Máx 2.5 pts)
        if es_financiera:
            pilar2 = interpolar_puntos(payout_bpa, 45.0, 75.0, 2.5, 0.5, inverso=True) if payout_bpa > 0 else 1.2
        elif es_reit_puro:
            pilar2 = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 2.5, 0.5, inverso=True) if 0 < payout_fcf < 200 else 1.0
        else:
            pts_fcf_sub = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 1.8, 0.3, inverso=True) if 0 < payout_fcf < 200 else 0.2
            pts_bpa_sub = interpolar_puntos(payout_bpa, 55.0, 82.0, 0.7, 0.1, inverso=True) if payout_bpa > 0 else 0.2
            pilar2 = min(2.5, pts_fcf_sub + pts_bpa_sub)

        # PILAR 3: FOSO ECONÓMICO (MOAT) Y MÁRGENES (Máx 2.0 pts)
        if es_reit_puro:
            pts_rent_sub = interpolar_puntos(operating_margins, 35.0, 20.0, 1.2, 0.3, inverso=False)
        else:
            pts_rent_sub = interpolar_puntos(metrica_rentabilidad, 15.0, 7.5, 1.2, 0.25, inverso=False) if metrica_rentabilidad is not None else 0.5
        pts_rev_sub = interpolar_puntos(revenue_cagr_3y, 4.0, 0.5, 0.8, 0.15, inverso=False) if revenue_cagr_3y is not None else 0.3
        pilar3 = min(2.0, pts_rent_sub + pts_rev_sub)

        # PILAR 4: HISTORIAL WEISS Y CONSISTENCIA (Máx 2.0 pts)
        racha_efectiva = racha_sin_recortes + (5 if años_pagando >= 25 else (2 if años_pagando >= 15 else 0))
        pts_racha = interpolar_puntos(racha_efectiva, 20.0, 5.0, 1.2, 0.3, inverso=False)
        pts_dgr_sub = interpolar_puntos(dgr_5y, 7.0, 2.5, 0.8, 0.2, inverso=False) if dgr_5y is not None else 0.2
        if fatiga_dividendo:
            pts_dgr_sub = max(0.0, pts_dgr_sub - 0.3)
        pilar4 = min(2.0, pts_racha + pts_dgr_sub)

        # PILAR 5: ASIGNACIÓN DE CAPITAL Y CRECIMIENTO (Máx 1.5 pts)
        if es_reit_puro:
            pilar5 = interpolar_puntos(dgr_5y if dgr_5y is not None else 2.0, 4.5, 1.0, 1.5, 0.3, inverso=False)
        else:
            pts_rec_sub = interpolar_puntos(recompras_anualizadas, 2.0, 0.1, 0.6, 0.15, inverso=False)
            pts_crec_sub = interpolar_puntos(crecimiento_bpa_3y, 6.5, 1.5, 0.9, 0.2, inverso=False) if crecimiento_bpa_3y is not None else 0.3
            pilar5 = min(1.5, pts_rec_sub + pts_crec_sub)

        # Penalizaciones estrictas
        penalizacion = 0.0
        if dgr_1y is not None and dgr_1y < -3.0:
            penalizacion += 1.5
        if not es_reit_puro and not es_financiera and payout_fcf > 105.0:
            penalizacion += 0.8

        score_calidad = max(1.0, min(10.0, round((pilar1 + pilar2 + pilar3 + pilar4 + pilar5) - penalizacion, 1)))

        # ==========================================
        # 2. SCORE DE VALORACIÓN AJUSTADO POR CRECIMIENTO
        # ==========================================
        if yield_actual >= yield_infravalorado:
            pts_yield = 4.0
        elif yield_actual >= yield_acumulacion:
            pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_acumulacion, 4.0, 3.2, inverso=False)
        elif yield_actual >= yield_medio:
            pts_yield = interpolar_puntos(yield_actual, yield_acumulacion, yield_medio, 3.2, 1.8, inverso=False)
        elif yield_actual >= yield_sobrevalorado:
            pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 1.8, 0.0, inverso=False)
        else:
            pts_yield = 0.0

        tasas_crec_negocio = [x for x in [dgr_5y, revenue_cagr_3y, crecimiento_bpa_3y] if x is not None]
        crec_negocio_val = float(np.median(tasas_crec_negocio)) if tasas_crec_negocio else 3.0
        if revenue_cagr_3y is not None and revenue_cagr_3y < 0.5:
            crec_negocio_val = min(crec_negocio_val, 1.5)

        mult_optimo = float(np.clip(8.5 + max(0.0, crec_negocio_val) * 0.9, 8.5, 17.5))
        mult_aceptable = mult_optimo + 7.0

        if es_financiera and p_fcf <= 0:
            pts_pfcf = interpolar_puntos(pb, 1.1, 2.0, 2.5, 0.4, inverso=True) if pb > 0 else 0.0
        else:
            pts_pfcf = interpolar_puntos(p_fcf, 15.0 if es_reit_puro else mult_optimo, 22.0 if es_reit_puro else mult_aceptable, 2.5, 0.4, inverso=True) if p_fcf > 0 else 0.0

        multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
        pts_per = interpolar_puntos(multiplo_per_eval, mult_optimo + 0.5, mult_aceptable + 1.0, 2.0, 0.3, inverso=True) if multiplo_per_eval > 0 else 0.0

        chowder_target = 8.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (12.0 if yield_actual >= 3.0 else 15.0)
        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0
        if dgr_5y is not None:
            if dgr_5y < 1.5 or (dgr_1y is not None and dgr_1y < 0):
                pts_chowder = 0.0
            else:
                chowder_efectivo = min(yield_actual, 6.5) + dgr_5y
                pts_chowder = interpolar_puntos(chowder_efectivo, chowder_target, chowder_target - 3.0, 1.5, 0.3, inverso=False)
        else:
            pts_chowder = 0.0

        score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
        score_total = round(score_calidad + score_val, 1)

        # ==========================================
        # 3. VEREDICTO COHERENTE (FILTRO WEISS + DYT)
        # ==========================================
        deterioro_grave = (
            (score_calidad < 5.2) or
            (not es_reit_puro and not es_financiera and payout_fcf > 105.0) or
            (dgr_1y is not None and dgr_1y < -3.5)
        )

        if es_aristocrata_reconocida and (dgr_1y is None or dgr_1y >= 0.0) and (cobertura_intereses is None or cobertura_intereses >= 3.5):
            deterioro_grave = False

        es_trampa_valor = (precio_actual <= precio_acumulacion) and deterioro_grave

        if es_trampa_valor:
            estado = "⚠️ TRAMPA VALOR"
            orden_estado = 5
        elif score_calidad >= 7.5 and precio_actual <= precio_compra:
            estado = "💎 COMPRA FUERTE"
            orden_estado = 1
        elif score_calidad >= 7.5 and precio_actual <= precio_acumulacion:
            estado = "🟢 ACUMULAR (P90)"
            orden_estado = 2
        elif score_calidad >= 6.3 and precio_actual <= precio_compra:
            estado = "🎯 COMPRA (P95)"
            orden_estado = 3
        elif score_calidad < 6.0 and precio_actual <= precio_compra:
            estado = "⚪ RIESGO / BAJA CALIDAD"
            orden_estado = 6
        elif precio_actual >= precio_venta:
            estado = "🔴 SOBREVALORADA"
            orden_estado = 7
        else:
            estado = "🟡 MANTENER"
            orden_estado = 4

        # ==========================================
        # 4. BOGLE-WEISS 5A Y SIMULACIÓN DE RENTA
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

        retorno_bogle_neto = yield_neto + crec_bogle + reversion_weiss_anual_acotada

        acc_compradas = (capital_simulado / precio_actual) if precio_actual > 0 else 0.0
        renta_neta_orden_anual = acc_compradas * forward_dividend * net_mult
        divs_netos_5a = sum([renta_neta_orden_anual * ((1 + max(0.0, crec_bogle)/100.0) ** a) for a in range(1, 6)])
        precio_est_5a = precio_justo * ((1 + (crec_bogle / 100.0)) ** 5)
        valor_total_5a_weiss = (acc_compradas * precio_est_5a) + divs_netos_5a

        dist_real_suelo = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 999.0
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0
        pct_acum_vs_media = ((precio_acumulacion - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0

        col_renta_nombre = f"Renta {int(capital_simulado)} (/Año)"

        return {
            "Ticker": t_clean,
            "Estado": estado,
            "Calidad": f"{f_num(score_calidad, 1)}/10",
            "Valoración": f"{f_num(score_val, 1)}/10",
            "Score Total": f"{f_num(score_total, 1)}/20",
            "Chowder": f"{f_num(chowder_number, 1)} (Obj: {f_num(chowder_target, 0)})" if chowder_number != -999.0 else "N/D",
            "Bogle-Weiss 5A": f"{f_num(retorno_bogle_neto, 1, '%', signo_pos=True)}/año (➔ {f_num(valor_total_5a_weiss, 0, sym_m)})",
            col_renta_nombre: f"{f_num(renta_neta_orden_anual, 2, sym_m)}/año ({f_num(acc_compradas, 1)} tít.)",
            "Cotización Actual": f"{f_num(precio_actual, 2, sym_m)} ({f_num(dist_real_suelo, 1, '%', signo_pos=True)})",
            "Suelo P95": f"{f_num(precio_compra, 2, sym_m)} ({f_num(pct_infra_vs_media, 1, '%', signo_pos=True)})" if precio_compra > 0 else "N/D",
            "Zona Acum. P90": f"{f_num(precio_acumulacion, 2, sym_m)} ({f_num(pct_acum_vs_media, 1, '%', signo_pos=True)})" if precio_acumulacion > 0 else "N/D",
            "Precio Justo": f_num(precio_justo, 2, sym_m),
            "Techo P05": f"{f_num(precio_venta, 2, sym_m)} ({f_num(pct_sobre_vs_media, 1, '%', signo_pos=True)})" if precio_venta > 0 else "N/D",
            "Div. Neto": f_num(div_neto_absoluto, 2, sym_m),
            "Yield Bruto": f_num(yield_actual, 2, "%"),
            "Yield Neto": f_num(yield_neto, 2, "%"),
            "PER": f_num(per, 1, "x") if per > 0 else "N/D",
            "P/FCF": ("N/A (REIT)" if (es_reit_puro and p_fcf > 0) else (f_num(p_fcf, 1, "x") if p_fcf > 0 else "N/D")),
            "Deuda/EBITDA": ("N/A (Banca)" if es_financiera else (f_num(deuda_ebitda, 2, "x") if 0 <= deuda_ebitda < 900 else "N/D")),
            "Payout FCF": ("N/A (REIT)" if es_reit_puro else (f_num(payout_fcf, 1, "%") if 0 < payout_fcf < 500 else ("Déficit" if payout_fcf >= 500 else "N/D"))),
            "Payout BPA": ("N/A (REIT)" if es_reit_puro else (f_num(payout_bpa, 1, "%") if payout_bpa > 0 else "N/D")),
            "ROIC/ROE": f_num(metrica_rentabilidad, 1, "%") if metrica_rentabilidad is not None else "N/D",
            "Ventas 3A": f_num(revenue_cagr_3y, 1, "%", signo_pos=True) if revenue_cagr_3y is not None else "N/D",
            "Acciones": f_num(variacion_acciones, 1, "%", signo_pos=True) if variacion_acciones is not None else "N/D",
            "Crec. BPA 3Y": f_num(crecimiento_bpa_3y, 1, "%", signo_pos=True) if crecimiento_bpa_3y is not None else "N/D",
            "DGR 5A": f_num(dgr_5y, 2, "%") if dgr_5y is not None else "N/D",
            f"DGR {años_analisis}A": f_num(dgr_periodo, 2, "%") if dgr_periodo is not None else "N/D",
            "Años Pag.": f"{años_pagando}A (R: {racha_sin_recortes}A)",

            "_orden_estado": orden_estado,
            "_score_total": score_total,
            "_score_calidad": score_calidad,
            "_score_val": score_val,
            "_Dist_Suelo": dist_real_suelo,
            "_bogle": retorno_bogle_neto,
            "_y_act": yield_actual, "_y_inf": yield_infravalorado, "_y_med": yield_medio,
            "_per": per, "_p_fcf": p_fcf, "_mult_opt": mult_optimo, "_mult_acep": mult_aceptable,
            "_pay_bpa": payout_bpa, "_l_bpa": payout_lim_bpa, "_a_bpa": payout_ama_bpa,
            "_pay_fcf": payout_fcf, "_l_fcf": payout_limite_fcf, "_a_fcf": payout_amarillo_fcf,
            "_deuda_ebitda": deuda_ebitda, "_lim_deuda_opt": lim_deuda_optima, "_lim_deuda_acep": lim_deuda_aceptable,
            "_roic": metrica_rentabilidad if metrica_rentabilidad is not None else -999,
            "_rev3": revenue_cagr_3y if revenue_cagr_3y is not None else -999,
            "_acc": variacion_acciones if variacion_acciones is not None else 999,
            "_dgr": dgr_5y if dgr_5y is not None else -999,
            "_dgr_per": dgr_periodo if dgr_periodo is not None else -999,
            "_cbpa3": crecimiento_bpa_3y if crecimiento_bpa_3y is not None else -999,
            "_chowder": chowder_number,
            "_chowder_target": chowder_target,
            "_col_renta": col_renta_nombre
        }
    except Exception:
        return None

# ==========================================
# INTERFAZ DIRECTA DE LA PÁGINA (RADAR)
# ==========================================
st.title("📡 Radar Watchlist DGI — Geraldine Weiss + Bogle")

st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("capital_activo", 500.0)
st.session_state.setdefault("merma_activa", True)

with st.expander("📁 Lista Persistente (`watchlist.txt`)", expanded=False):
    lista_almacenada = cargar_watchlist()
    tickers_masivos = st.text_area(
        "Edita o consulta los tickers guardados (separados por comas o saltos de línea):",
        value=lista_almacenada,
        height=90
    )
    col_btn_guardar, col_btn_limpiar = st.columns([1, 2])
    with col_btn_guardar:
        if st.button("💾 Guardar Lista"):
            if guardar_watchlist(tickers_masivos):
                st.success("¡Lista guardada correctamente en `watchlist.txt`!")
            else:
                st.error("Error al escribir el archivo.")
    with col_btn_limpiar:
        if st.button("🧹 Limpiar Caché de Disco (Forzar descarga fresca)"):
            descargar_fundamentales_persistentes_disco.clear()
            obtener_cotizacion_viva_radar.clear()
            st.session_state.pop("resultados_radar_cache", None)
            st.success("¡Caché de disco borrada! El próximo escaneo descargará datos frescos.")

lista_años = [5, 10, 12, 15, 20]
idx_años = lista_años.index(st.session_state.años_activo) if st.session_state.años_activo in lista_años else 2

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    años_masivos = st.selectbox("Periodo para canal histórico:", lista_años, index=idx_años, key="años_mas")
with col_m2:
    impuesto_masivo = st.number_input("Retención IRPF (%)", value=float(st.session_state.impuesto_activo), step=1.0, key="imp_mas")
with col_m3:
    capital_masivo = st.number_input("Capital Simulado Orden (€/$):", value=float(st.session_state.capital_activo), step=50.0, key="cap_mas")

aplicar_merma_masivo = st.checkbox(
    "Aplicar merma fiscal en origen no recuperable (>15% Suiza, Alemania, Francia, Dinamarca, Irlanda)",
    value=st.session_state.merma_activa,
    key="merma_mas"
)

st.session_state.años_activo = años_masivos
st.session_state.impuesto_activo = impuesto_masivo
st.session_state.capital_activo = capital_masivo
st.session_state.merma_activa = aplicar_merma_masivo

if st.button("🚀 Escanear Watchlist", use_container_width=True):
    raw_tickers = tickers_masivos.replace("\n", ",").split(",")
    lista_tickers = [t.strip().upper() for t in raw_tickers if t.strip()]

    if len(lista_tickers) > 0:
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        resultados = []

        for idx, ticker in enumerate(lista_tickers):
            texto_estado.text(f"Auditando {ticker} ({idx+1}/{len(lista_tickers)})...")
            
            datos = analizar_empresa_rapido(ticker, años_masivos, impuesto_masivo, aplicar_merma_masivo, capital_masivo)
            if datos:
                resultados.append(datos)
                
            # Micropausa de cortesía de 0.20s para no saturar los sockets de red
            time.sleep(0.20)
            barra_progreso.progress((idx + 1) / len(lista_tickers))

        texto_estado.text(f"¡Escaneo completado con éxito! ({len(resultados)}/{len(lista_tickers)} empresas procesadas)")
        st.session_state["resultados_radar_cache"] = resultados

if "resultados_radar_cache" in st.session_state and st.session_state["resultados_radar_cache"]:
    resultados = st.session_state["resultados_radar_cache"]
    df_res = pd.DataFrame(resultados)
    col_renta_actual = df_res["_col_renta"].iloc[0]

    df_res = df_res.sort_values(
        by=["_orden_estado", "_score_total", "_score_calidad", "_Dist_Suelo"],
        ascending=[True, False, False, True]
    )

    df_res = df_res.set_index("Ticker")

    def color_row(row):
        styles = [''] * len(row)
        est = str(row['Estado'])
        for idx, col_name in enumerate(row.index):
            if col_name == 'Calidad':
                if row['_score_calidad'] >= 8.0: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_score_calidad'] >= 6.3: styles[idx] = 'color: #faca2b; font-weight: bold;'
                else: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
            elif col_name == 'Valoración':
                if row['_score_val'] >= 7.0: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_score_val'] >= 4.0: styles[idx] = 'color: #faca2b; font-weight: bold;'
                else: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
            elif col_name == 'Score Total':
                if row['_score_total'] >= 15.0: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_score_total'] >= 11.0: styles[idx] = 'color: #faca2b; font-weight: bold;'
                else: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
            elif col_name == 'Bogle-Weiss 5A':
                if row['_bogle'] >= 10.0: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_bogle'] >= 6.0: styles[idx] = 'color: #faca2b; font-weight: bold;'
                else: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
            elif col_name == col_renta_actual:
                if row['_y_act'] >= row['_y_inf']: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_y_act'] >= row['_y_med']: styles[idx] = 'color: #00d4ff; font-weight: bold;'
                else: styles[idx] = 'color: #ccc;'
            elif col_name == 'Cotización Actual':
                if "COMPRA FUERTE" in est: styles[idx] = 'color: #7cfc00; font-weight: bold;'
                elif "ACUMULAR" in est: styles[idx] = 'color: #00d4ff; font-weight: bold;'
                elif "COMPRA" in est: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif "TRAMPA" in est: styles[idx] = 'color: #ff9800; font-weight: bold;'
                elif "SOBREVALORADA" in est: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
                else: styles[idx] = 'color: #faca2b; font-weight: bold;'
            elif col_name in ['Suelo P95', 'Zona Acum. P90']:
                styles[idx] = 'color: #21c354;' if col_name == 'Suelo P95' else 'color: #00d4ff;'
            elif col_name == 'Precio Justo': styles[idx] = 'color: #faca2b;'
            elif col_name == 'Techo P05': styles[idx] = 'color: #ff4b4b;'
            elif col_name in ['Yield Bruto', 'Yield Neto', 'Div. Neto']:
                if row['_y_act'] >= row['_y_inf']: styles[idx] = 'color: #21c354;'
                elif row['_y_act'] >= row['_y_med']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'PER':
                if row['_per'] <= 0: styles[idx] = 'color: #888;'
                elif row['_per'] <= row['_mult_opt'] + 0.5: styles[idx] = 'color: #21c354;'
                elif row['_per'] <= row['_mult_acep'] + 1.0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'P/FCF':
                if row['_p_fcf'] <= 0: styles[idx] = 'color: #888;'
                elif row['_p_fcf'] <= row['_mult_opt']: styles[idx] = 'color: #21c354;'
                elif row['_p_fcf'] <= row['_mult_acep']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Deuda/EBITDA':
                d = row['_deuda_ebitda']
                if d < 0 or d >= 900: styles[idx] = 'color: #888;'
                elif d <= row['_lim_deuda_opt']: styles[idx] = 'color: #21c354;'
                elif d <= row['_lim_deuda_acep']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Payout FCF':
                p = row['_pay_fcf']
                if p <= 0 or p >= 500: styles[idx] = 'color: #ff4b4b;'
                elif p <= row['_l_fcf']: styles[idx] = 'color: #21c354;'
                elif p <= row['_a_fcf']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Payout BPA':
                p = row['_pay_bpa']
                if p <= 0: styles[idx] = 'color: #888;'
                elif p <= row['_l_bpa']: styles[idx] = 'color: #21c354;'
                elif p <= row['_a_bpa']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'ROIC/ROE':
                r = row['_roic']
                if r == -999: styles[idx] = 'color: #888;'
                elif r >= 14.0: styles[idx] = 'color: #21c354;'
                elif r >= 7.5: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Ventas 3A':
                v = row['_rev3']
                if v == -999: styles[idx] = 'color: #888;'
                elif v >= 3.0: styles[idx] = 'color: #21c354;'
                elif v > 0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Acciones':
                a = row['_acc']
                if a == 999: styles[idx] = 'color: #888;'
                elif a < -0.5: styles[idx] = 'color: #21c354;'
                elif a <= 1.0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Crec. BPA 3Y':
                c = row['_cbpa3']
                if c == -999: styles[idx] = 'color: #888;'
                elif c > 0: styles[idx] = 'color: #21c354;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name in ['DGR 5A', f'DGR {años_masivos}A']:
                val_col = row['_dgr'] if col_name == 'DGR 5A' else row['_dgr_per']
                if val_col == -999: styles[idx] = 'color: #888;'
                elif val_col >= 7.0: styles[idx] = 'color: #21c354;'
                elif val_col >= 4.0: styles[idx] = 'color: #faca2b;'
                elif val_col >= 2.0: styles[idx] = 'color: #ff9800;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Chowder':
                c_num = row['_chowder']
                c_tar = row['_chowder_target']
                if c_num != -999.0:
                    if c_num >= c_tar and row['_dgr'] >= 1.5:
                        styles[idx] = 'color: #21c354; font-weight: bold;'
                    else:
                        styles[idx] = 'color: #ff4b4b;'
                else:
                    styles[idx] = 'color: #888;'
            elif col_name == 'Estado':
                if "COMPRA FUERTE" in est: styles[idx] = 'background-color: #004d00; color: #7cfc00; font-weight: bold;'
                elif "ACUMULAR" in est: styles[idx] = 'background-color: #003344; color: #00d4ff; font-weight: bold;'
                elif "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: white;'
                elif "TRAMPA" in est: styles[idx] = 'background-color: #663300; color: #ffcc80;'
                elif "RIESGO" in est: styles[idx] = 'background-color: #333333; color: #cccccc;'
                elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: white;'
                else: styles[idx] = 'background-color: #3d3d00; color: #faca2b;'
        return styles

    columnas_visibles = [c for c in df_res.columns if not c.startswith('_')]
    styled_df = df_res.style.apply(color_row, axis=1)
    st.dataframe(styled_df, column_order=columnas_visibles, use_container_width=True, height=640)

    df_export = df_res[columnas_visibles]
    csv = df_export.to_csv(index=True, sep=';', decimal=',').encode('utf-8')
    st.download_button(
        label="💾 Descargar CSV para Google Sheets",
        data=csv,
        file_name=f"Screener_DGI_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )
