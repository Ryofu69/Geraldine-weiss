import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Radar Watchlist - Weiss DGI", page_icon="📡", layout="wide")

ARCHIVO_WATCHLIST = "watchlist.txt"

MERMA_ORIGEN_PAIS = {
    'Switzerland': 20.0, 'Denmark': 12.0, 'Germany': 11.375, 'France': 10.0, 'Ireland': 10.0
}

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
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    return float(s.iloc[-1])
    return 0.0

@st.cache_data(ttl=3600, show_spinner=False)
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

    if mediana_pagos_año >= 10: pagos_por_año = 12
    elif mediana_pagos_año >= 3: pagos_por_año = 4
    elif mediana_pagos_año >= 1.5: pagos_por_año = 2
    else: pagos_por_año = 1

    divs_para_bandas = divs_por_año.copy()
    años_cerrados = divs_para_bandas[divs_para_bandas.index < año_actual]
    if es_europea and len(años_cerrados) >= 5:
        mediana_5a = float(años_cerrados.tail(6).median())
        for y in años_cerrados.index:
            if divs_para_bandas.loc[y] > mediana_5a * 1.45:
                vecinos = [divs_para_bandas.loc[v] for v in [y - 1, y - 2, y + 1] if v in años_cerrados.index and divs_para_bandas.loc[v] <= mediana_5a * 1.45]
                if vecinos:
                    divs_para_bandas.loc[y] = float(np.max(vecinos)) * 1.05

    # Filtrar posibles apuntes de spin-offs (>1.5x la mediana reciente) para leer los cupones ordinarios reales
    med_cupon = divs_clean.rolling(window=max(4, pagos_por_año * 2), min_periods=1).median()
    cupones_reg = divs_clean[divs_clean <= med_cupon * 1.50]
    if cupones_reg.empty:
        cupones_reg = divs_clean

    # Detección exacta de dividendo congelado:
    #En trimestrales (pagos_por_año=4), el pago de hace 12 meses exactos es iloc[-4] (o iloc[-5] si hubo 5 apuntes).
    dividendo_congelado = False
    if not es_europea and pagos_por_año == 4 and len(cupones_reg) >= 4:
        ult_c = float(cupones_reg.iloc[-1])
        c_hace_1a = float(cupones_reg.iloc[-4])
        # Si el cupón actual es igual al de hace 4 trimestres (ej. CMCSA lleva 4 pagos seguidos en $0.33)
        if c_hace_1a > 0 and ult_c <= c_hace_1a * 1.005:
            dividendo_congelado = True

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
        ult_cupon_anualizado = float(cupones_reg.iloc[-1]) * pagos_por_año
        if fd_info <= 0 or abs(ult_cupon_anualizado - fd_info) / max(1.0, ult_cupon_anualizado) > 0.25:
            forward_dividend = max(ult_cupon_anualizado, ultimo_año_cerrado)
        else:
            forward_dividend = fd_info

    return divs_por_año, divs_para_bandas, forward_dividend, pagos_por_año, dividendo_congelado

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

def analizar_empresa_rapido(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    try:
        t_clean = ticker_symbol.strip().upper()
        ticker = yf.Ticker(t_clean)
        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            info = {}

        if not info.get('sector'):
            try:
                busq = yf.Search(t_clean, max_results=1).quotes
                if busq and len(busq) > 0:
                    q0 = busq[0]
                    if q0.get('sector'): info['sector'] = q0.get('sector')
                    if q0.get('industry'): info['industry'] = q0.get('industry')
            except Exception:
                pass

        def get_safe(key, default=0.0):
            val = info.get(key)
            if val is None: return default
            try: return float(val)
            except (ValueError, TypeError): return default

        dividendos_raw = ticker.dividends
        historial_raw = ticker.history(period="22y", auto_adjust=False)

        if dividendos_raw.empty or len(historial_raw) < 252:
            return None

        inc_stmt, bs_stmt, cf_stmt = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        try:
            if ticker.income_stmt is not None and not ticker.income_stmt.empty:
                inc_stmt = ticker.income_stmt.T.sort_index().T
        except Exception: pass
        try:
            if ticker.balance_sheet is not None and not ticker.balance_sheet.empty:
                bs_stmt = ticker.balance_sheet.T.sort_index().T
        except Exception: pass
        try:
            if ticker.cashflow is not None and not ticker.cashflow.empty:
                cf_stmt = ticker.cashflow.T.sort_index().T
        except Exception: pass

        currency_raw = info.get('currency')
        if not currency_raw:
            try: currency_raw = ticker.fast_info.currency or 'USD'
            except Exception: currency_raw = 'USD'
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

        try:
            p_vivo = float(ticker.fast_info.last_price)
            if p_vivo > 0 and not historial.empty:
                historial.iloc[-1, historial.columns.get_loc('Close')] = p_vivo
        except Exception:
            pass

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

        sector_en = info.get('sector', 'General')
        industry_en = info.get('industry', 'General')
        pais = info.get('country', 'Desconocido')
        if pais == 'Desconocido' and t_clean.endswith('.MC'):
            pais = 'Spain'

        es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
        es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
        es_telecom = 'telecom' in industry_en.lower()
        es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
        es_defensivo = 'consumer defensive' in sector_en.lower() or 'consumer staples' in sector_en.lower() or 'healthcare' in sector_en.lower()

        merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
        net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

        fd_info = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
        divs_por_año, divs_para_bandas, forward_dividend, pagos_por_año, dividendo_congelado = procesar_dividendos_robusto(
            dividendos, t_clean, año_actual, precio_actual, es_peniques_uk, fd_info
        )

        ha['Year'] = ha.index.year
        ha['Div_Anual'] = ha['Year'].map(divs_para_bandas)
        ha.loc[ha['Year'] == año_actual, 'Div_Anual'] = forward_dividend
        ha['Div_Anual'] = ha['Div_Anual'].bfill().ffill()

        ha['Yield_Diario'] = (ha['Div_Anual'] / ha['Close']) * 100
        ha.replace([np.inf, -np.inf], np.nan, inplace=True)
        yields_validos = ha['Yield_Diario'].dropna()
        yields_validos = yields_validos[yields_validos > 0]

        yield_infravalorado = float(yields_validos.quantile(0.95))
        yield_sobrevalorado = float(yields_validos.quantile(0.05))
        yield_medio = float(yields_validos.mean())

        precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0.0
        precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0.0
        precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0.0

        yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0
        yield_neto = yield_actual * net_mult
        div_neto_absoluto = forward_dividend * net_mult

        shares = get_safe('sharesOutstanding', 0.0)
        if shares <= 0:
            try: shares = float(ticker.fast_info.shares)
            except Exception: pass
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

        payout_bpa = get_safe('payoutRatio', 0.0) * 100
        if payout_bpa <= 0 and bpa_trailing > 0:
            payout_bpa = (forward_dividend / bpa_trailing) * 100

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

        pb = get_safe('priceToBook', -1.0)
        if pb <= 0 and total_equity_raw > 0 and shares > 0:
            pb = precio_actual / (total_equity_raw / shares)

        current_ratio = get_safe('currentRatio', 0.0)

        es_quasi_reit_o_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 24.0) and (total_equity_raw <= 0 or pb < 0)
        es_regulada_o_reit = es_reit_puro or es_utility_pura or es_quasi_reit_o_recompras

        payout_lim_bpa = 85.0 if es_regulada_o_reit else 60.0
        payout_ama_bpa = 92.0 if es_regulada_o_reit else 75.0
        payout_limite_fcf = 75.0 if es_regulada_o_reit else 55.0
        payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 80.0

        deuda_neta = max(0.0, total_debt - total_cash)
        deuda_ebitda = (deuda_neta / ebitda) if ebitda > 0 else (999.0 if (total_debt > 0 and not es_financiera) else 0.0)

        payout_fcf, p_fcf = -1.0, -1.0
        if flujo_caja_referencia > 0 and shares > 0 and forward_dividend > 0:
            fcf_per_share = flujo_caja_referencia / shares
            if fcf_per_share > 0:
                payout_fcf = (forward_dividend / fcf_per_share) * 100
                p_fcf = precio_actual / fcf_per_share

        crecimiento_bpa_3y = None
        if not inc_stmt.empty:
            for key in ['Diluted EPS', 'Basic EPS']:
                if key in inc_stmt.index:
                    eps_series = inc_stmt.loc[key].dropna()
                    if len(eps_series) >= 4 and eps_series.iloc[-4] > 0 and eps_series.iloc[-1] > 0:
                        crecimiento_bpa_3y = (((eps_series.iloc[-1] / eps_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                    break

        crecimiento_ffo_sh_3y = None
        if es_reit_puro and not cf_stmt.empty and not inc_stmt.empty:
            try:
                ocf_s = cf_stmt.loc['Operating Cash Flow'].dropna() if 'Operating Cash Flow' in cf_stmt.index else pd.Series(dtype=float)
                sh_s = inc_stmt.loc['Diluted Average Shares'].dropna() if 'Diluted Average Shares' in inc_stmt.index else pd.Series(dtype=float)
                common_idx = ocf_s.index.intersection(sh_s.index)
                if len(common_idx) >= 4:
                    ffo_sh = (ocf_s.loc[common_idx] / sh_s.loc[common_idx]).sort_index()
                    if ffo_sh.iloc[-4] > 0 and ffo_sh.iloc[-1] > 0:
                        crecimiento_ffo_sh_3y = (((ffo_sh.iloc[-1] / ffo_sh.iloc[-4]) ** (1 / 3)) - 1) * 100
            except Exception: pass

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

        dividendos_barras = divs_para_bandas.copy()
        if año_actual in dividendos_barras.index:
            dividendos_barras[año_actual] = forward_dividend
        else:
            dividendos_barras.loc[año_actual] = forward_dividend

        años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
        dgr_5y, dgr_periodo, dgr_1y = None, None, None
        if dividendo_congelado:
            dgr_1y = 0.0
        elif len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
            dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100

        if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
            dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1/5) - 1) * 100
        if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
            dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1/años_analisis) - 1) * 100

        fatiga_dividendo = bool(dividendo_congelado or (dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0 and (dgr_1y / dgr_5y) < 0.5))

        racha_sin_recortes = 0
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.98:
                    racha_sin_recortes += 1
                else: break

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
        # 1. SCORE DE CALIDAD DGI
        # ==========================================
        if es_reit_puro:
            lim_deuda_optima, lim_deuda_aceptable = 5.2, 6.8
        elif es_utility_pura or es_quasi_reit_o_recompras:
            lim_deuda_optima, lim_deuda_aceptable = 3.5, 5.0
        elif es_defensivo or es_telecom:
            lim_deuda_optima, lim_deuda_aceptable = 2.5, 3.8
        else:
            lim_deuda_optima, lim_deuda_aceptable = 1.8, 3.2

        if es_financiera:
            pts_deuda = interpolar_puntos(roe, 15.0, 8.0, 2.0, 0.4, inverso=False)
            pts_cob = 0.5 if (current_ratio >= 1.0 or roe >= 11.0) else 0.0
        else:
            pts_deuda = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable, 2.0, 0.3, inverso=True)
            umbral_cob_max = 3.2 if es_reit_puro else 7.0
            umbral_cob_min = 1.8 if es_reit_puro else 3.0
            pts_cob = interpolar_puntos(cobertura_intereses, umbral_cob_max, umbral_cob_min, 0.5, 0.1, inverso=False) if cobertura_intereses is not None else (0.5 if deuda_neta == 0 else 0.0)

        if es_financiera and payout_fcf == -1:
            pts_fcf = interpolar_puntos(payout_bpa, 45.0, 75.0, 2.0, 0.4, inverso=True) if payout_bpa > 0 else 0.0
        else:
            pts_fcf = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 2.0, 0.4, inverso=True) if payout_fcf > 0 else 0.0

        racha_efectiva = racha_sin_recortes + (3 if años_pagando >= 25 else 0)
        pts_hist = interpolar_puntos(racha_efectiva, 20.0, 6.0, 2.0, 0.5, inverso=False)
        if dividendo_congelado:
            pts_hist = max(0.0, round(pts_hist - 0.8, 2))
        elif fatiga_dividendo:
            pts_hist = max(0.0, round(pts_hist - 0.5, 2))

        metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
        if es_reit_puro:
            pts_roic_sub = interpolar_puntos(operating_margins, 35.0, 20.0, 0.9, 0.3, inverso=False)
        else:
            pts_roic_sub = interpolar_puntos(metrica_rentabilidad, 16.0, 7.0, 0.9, 0.2, inverso=False) if metrica_rentabilidad is not None else 0.0
        pts_rev_sub = interpolar_puntos(revenue_cagr_3y, 5.0, 1.0, 0.6, 0.1, inverso=False) if revenue_cagr_3y is not None else 0.0
        pts_foso = round(pts_roic_sub + pts_rev_sub, 2)

        pts_dgr = interpolar_puntos(dgr_5y, 7.5, 2.5, 1.0, 0.25, inverso=False) if dgr_5y is not None else 0.0
        if dividendo_congelado:
            pts_dgr = round(pts_dgr * 0.25, 2)

        if es_reit_puro:
            crec_reit_ref = crecimiento_ffo_sh_3y if crecimiento_ffo_sh_3y is not None else (dgr_5y or 0.0)
            pts_cap = interpolar_puntos(crec_reit_ref, 4.5, 1.0, 1.0, 0.3, inverso=False)
        else:
            pts_recompra_sub = interpolar_puntos(recompras_anualizadas, 2.5, 0.4, 0.6, 0.2, inverso=False)
            pts_bpa_sub = interpolar_puntos(crecimiento_bpa_3y, 7.0, 2.0, 0.6, 0.2, inverso=False) if crecimiento_bpa_3y is not None else 0.0
            pts_cap = min(1.0, round(pts_recompra_sub + pts_bpa_sub, 2))

        score_calidad = min(10.0, round(pts_deuda + pts_cob + pts_fcf + pts_hist + pts_foso + pts_dgr + pts_cap, 1))

        # ==========================================
        # 2. SCORE DE VALORACIÓN DGI
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
        if dividendo_congelado or (revenue_cagr_3y is not None and revenue_cagr_3y < 1.5):
            crec_negocio_val = min(crec_negocio_val, 1.2)

        mult_optimo = float(np.clip(8.5 + max(0.0, crec_negocio_val) * 0.9, 8.5, 17.0))
        mult_aceptable = mult_optimo + 7.0

        if es_financiera and p_fcf <= 0:
            pts_pfcf = interpolar_puntos(pb, 1.1, 2.0, 2.5, 0.4, inverso=True) if pb > 0 else 0.0
        else:
            pts_pfcf = interpolar_puntos(p_fcf, 15.0 if es_reit_puro else mult_optimo, 22.0 if es_reit_puro else mult_aceptable, 2.5, 0.4, inverso=True) if p_fcf > 0 else 0.0

        multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
        pts_per = interpolar_puntos(multiplo_per_eval, mult_optimo + 0.5, mult_aceptable + 1.0, 2.0, 0.3, inverso=True) if multiplo_per_eval > 0 else 0.0

        if dividendo_congelado or (revenue_cagr_3y is not None and revenue_cagr_3y < 1.0):
            pts_pfcf = round(pts_pfcf * 0.65, 2)
            pts_per = round(pts_per * 0.65, 2)

        chowder_target = 8.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (12.0 if yield_actual >= 3.0 else 15.0)
        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0
        if dgr_5y is not None:
            if dividendo_congelado or dgr_5y < 2.0 or (dgr_1y is not None and dgr_1y <= 0):
                pts_chowder = 0.0
            else:
                chowder_efectivo = min(yield_actual, 6.5) + dgr_5y
                pts_chowder = interpolar_puntos(chowder_efectivo, chowder_target, chowder_target - 3.0, 1.5, 0.3, inverso=False)
        else:
            pts_chowder = 0.0

        score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
        score_total = round(score_calidad + score_val, 1)

        # ==========================================
        # 3. FÓRMULA BOGLE-WEISS 5A Y RENTA ANUAL POR 500 €/$
        # ==========================================
        horizonte_bogle = 5
        candidatos_crec = [x for x in [dgr_5y, dgr_periodo, crecimiento_bpa_3y] if x is not None]
        crec_bogle = float(np.median(candidatos_crec)) if candidatos_crec else 3.0
        if dividendo_congelado:
            crec_bogle = min(crec_bogle, 3.0)
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
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0

        # Detector de Trampa de Valor:
        # En empresas con Calidad >= 6.0 (ej. PEP), un pico de CapEx en FCF solo es trampa si también el Payout BPA > 88%
        payout_critico = (payout_fcf > 92.0 and (score_calidad < 6.0 or payout_bpa > 88.0))
        posible_trampa = (precio_actual <= precio_compra) and (
            score_calidad < 5.5 or payout_critico or (dgr_1y is not None and dgr_1y < -5.0)
        )

        if posible_trampa:
            estado = "⚠️ TRAMPA VALOR"
            orden_estado = 2
        elif precio_actual <= precio_compra:
            estado = "🎯 COMPRA"
            orden_estado = 1
        elif precio_actual >= precio_venta:
            estado = "🔴 SOBREVALORADA"
            orden_estado = 4
        else:
            estado = "🟡 MANTENER"
            orden_estado = 3

        col_renta_nombre = f"Renta {int(capital_simulado)} (/Año)"
        txt_chowder = f"{f_num(chowder_number, 1)} ❄️" if (chowder_number != -999.0 and dividendo_congelado) else (f"{f_num(chowder_number, 1)} (Obj: {f_num(chowder_target, 0)})" if chowder_number != -999.0 else "N/D")

        return {
            "Ticker": t_clean,
            "Estado": estado,
            "Calidad": f"{f_num(score_calidad, 1)}/10",
            "Valoración": f"{f_num(score_val, 1)}/10",
            "Score Total": f"{f_num(score_total, 1)}/20",
            "Chowder": txt_chowder,
            "Bogle-Weiss 5A": f"{f_num(retorno_bogle_neto, 1, '%', signo_pos=True)}/año (➔ {f_num(valor_total_5a_weiss, 0, sym_m)})",
            col_renta_nombre: f"{f_num(renta_neta_orden_anual, 2, sym_m)}/año ({f_num(acc_compradas, 1)} tít.)",
            "Cotización Actual": f"{f_num(precio_actual, 2, sym_m)} ({f_num(dist_real_suelo, 1, '%', signo_pos=True)})",
            "Suelo (Infra)": f"{f_num(precio_compra, 2, sym_m)} ({f_num(pct_infra_vs_media, 1, '%', signo_pos=True)})" if precio_compra > 0 else "N/D",
            "Precio Justo": f_num(precio_justo, 2, sym_m),
            "Techo (Sobre)": f"{f_num(precio_venta, 2, sym_m)} ({f_num(pct_sobre_vs_media, 1, '%', signo_pos=True)})" if precio_venta > 0 else "N/D",
            "Div. Neto": f_num(div_neto_absoluto, 2, sym_m),
            "Yield Bruto": f_num(yield_actual, 2, "%"),
            "Yield Neto": f_num(yield_neto, 2, "%"),
            "PER": f_num(per, 1, "x") if per > 0 else "N/D",
            "P/FCF": f_num(p_fcf, 1, "x") if p_fcf != -1 else "N/D",
            "Deuda/EBITDA": f_num(deuda_ebitda, 2, "x") if deuda_ebitda < 900 else "N/D",
            "Payout FCF": f_num(payout_fcf, 1, "%") if payout_fcf != -1 else "N/D",
            "Payout BPA": f_num(payout_bpa, 1, "%"),
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
            "_congelado": dividendo_congelado,
            "_col_renta": col_renta_nombre
        }
    except Exception:
        return None

st.title("📡 Radar Watchlist DGI — Geraldine Weiss + Bogle")

st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("capital_activo", 500.0)
st.session_state.setdefault("merma_activa", True)

with st.expander("📁 Lista Persistente (`watchlist.txt`)", expanded=True):
    lista_almacenada = cargar_watchlist()
    tickers_masivos = st.text_area(
        "Edita o consulta los tickers guardados (separados por comas o saltos de línea):",
        value=lista_almacenada,
        height=90
    )
    col_btn_guardar, _ = st.columns([1, 4])
    with col_btn_guardar:
        if st.button("💾 Guardar Lista en Archivo"):
            if guardar_watchlist(tickers_masivos):
                st.success("¡Lista guardada correctamente en `watchlist.txt`!")
            else:
                st.error("Error al escribir el archivo.")

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
            texto_estado.text(f"Escaneando {ticker} ({idx+1}/{len(lista_tickers)})...")
            datos = analizar_empresa_rapido(ticker, años_masivos, impuesto_masivo, aplicar_merma_masivo, capital_masivo)
            if datos:
                resultados.append(datos)
            barra_progreso.progress((idx + 1) / len(lista_tickers))
        
        texto_estado.text("¡Escaneo completado!")
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
        est = row['Estado']
        for idx, col_name in enumerate(row.index):
            if col_name == 'Calidad':
                if row['_score_calidad'] >= 8.0: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_score_calidad'] >= 6.0: styles[idx] = 'color: #faca2b; font-weight: bold;'
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
                if "COMPRA" in est: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif "TRAMPA" in est: styles[idx] = 'color: #ff9800; font-weight: bold;'
                elif "SOBREVALORADA" in est: styles[idx] = 'color: #ff4b4b; font-weight: bold;'
                else: styles[idx] = 'color: #faca2b; font-weight: bold;'
            elif col_name == 'Suelo (Infra)': styles[idx] = 'color: #21c354;'
            elif col_name == 'Precio Justo': styles[idx] = 'color: #faca2b;'
            elif col_name == 'Techo (Sobre)': styles[idx] = 'color: #ff4b4b;'
            elif col_name in ['Yield Bruto', 'Yield Neto', 'Div. Neto']:
                if row['_y_act'] >= row['_y_inf']: styles[idx] = 'color: #21c354;'
                elif row['_y_act'] >= row['_y_med']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'PER':
                if 0 < row['_per'] <= row['_mult_opt'] + 0.5: styles[idx] = 'color: #21c354;'
                elif 0 < row['_per'] <= row['_mult_acep'] + 1.0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'P/FCF':
                if 0 < row['_p_fcf'] <= row['_mult_opt']: styles[idx] = 'color: #21c354;'
                elif 0 < row['_p_fcf'] <= row['_mult_acep']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Deuda/EBITDA':
                d = row['_deuda_ebitda']
                if d <= row['_lim_deuda_opt']: styles[idx] = 'color: #21c354;'
                elif d <= row['_lim_deuda_acep']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Payout FCF':
                p = row['_pay_fcf']
                if 0 <= p <= row['_l_fcf']: styles[idx] = 'color: #21c354;'
                elif p <= row['_a_fcf']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Payout BPA':
                p = row['_pay_bpa']
                if 0 < p <= row['_l_bpa']: styles[idx] = 'color: #21c354;'
                elif p <= row['_a_bpa']: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'ROIC/ROE':
                r = row['_roic']
                if r >= 15.0: styles[idx] = 'color: #21c354;'
                elif r >= 8.0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Ventas 3A':
                v = row['_rev3']
                if v >= 3.0: styles[idx] = 'color: #21c354;'
                elif v > 0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Acciones':
                a = row['_acc']
                if a < -0.5: styles[idx] = 'color: #21c354;'
                elif a <= 1.0: styles[idx] = 'color: #faca2b;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Crec. BPA 3Y':
                c = row['_cbpa3']
                if c != -999 and c > 0: styles[idx] = 'color: #21c354;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name in ['DGR 5A', f'DGR {años_masivos}A']:
                val_col = row['_dgr'] if col_name == 'DGR 5A' else row['_dgr_per']
                if val_col >= 8.0: styles[idx] = 'color: #21c354;'
                elif val_col >= 4.5: styles[idx] = 'color: #faca2b;'
                elif val_col >= 2.5: styles[idx] = 'color: #ff9800;'
                else: styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Chowder':
                c_num = row['_chowder']
                c_tar = row['_chowder_target']
                if c_num != -999.0:
                    if not row['_congelado'] and c_num >= c_tar and row['_dgr'] >= 2.0:
                        styles[idx] = 'color: #21c354; font-weight: bold;'
                    else:
                        styles[idx] = 'color: #ff4b4b;'
            elif col_name == 'Estado':
                if "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: white;'
                elif "TRAMPA" in est: styles[idx] = 'background-color: #663300; color: #ffcc80;'
                elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: white;'
                else: styles[idx] = 'background-color: #4d4d00; color: white;'
        return styles

    columnas_visibles = [c for c in df_res.columns if not c.startswith('_')]
    styled_df = df_res.style.apply(color_row, axis=1)
    st.dataframe(styled_df, column_order=columnas_visibles, use_container_width=True, height=620)

    df_export = df_res[columnas_visibles]
    csv = df_export.to_csv(index=True, sep=';', decimal=',').encode('utf-8')
    st.download_button(
        label="💾 Descargar CSV para Google Sheets",
        data=csv,
        file_name=f"Screener_DGI_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )
