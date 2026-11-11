```python
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import time
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Radar Watchlist - Weiss DGI & Chowder", page_icon="📡", layout="wide")

ARCHIVO_WATCHLIST = "watchlist.txt"

MERMA_ORIGEN_PAIS = {
    'Switzerland': 20.0, 'Denmark': 12.0, 'Germany': 11.375, 'France': 10.0, 'Ireland': 10.0
}

ARISTOCRATAS_Y_KINGS = {
    'JNJ', 'PG', 'KO', 'PEP', 'MMM', 'LOW', 'CL', 'WMT', 'EMR', 'GPC', 'SYY', 'APD',
    'BDX', 'HRL', 'ITW', 'SWK', 'FRT', 'O', 'ABBV', 'ABT', 'MCD', 'ADP', 'TGT',
    'MKC', 'GD', 'CAT', 'CVX', 'XOM', 'IBM', 'ED', 'AWR', 'CINF', 'DOV', 'PH',
    'PPG', 'LEG', 'SJW', 'ADM', 'CB', 'AFL', 'ROP', 'SHW', 'SPGI', 'ECL', 'CTAS',
    'WPC', 'NNN', 'ESS', 'MAA', 'KMB', 'GIS', 'NDSN', 'CSL', 'BRO', 'GWW', 'NUE'
}

# ==========================================
# PALETA DE COLORES UNIFICADA POR ESTADO
# ==========================================
MAPA_COLORES_ESTADO = {
    "💎 COMPRA FUERTE": "#7cfc00",       # Verde Lima Brillante (Compra Fuerte P95 + Calidad Élite)
    "🎯 COMPRA (P95)": "#21c354",        # Verde Compra P95
    "🔵 ACUMULAR (P90)": "#00d4ff",      # Azul P90 (Acumulación)
    "🟡 MANTENER": "#faca2b",            # Amarillo Mantener
    "⚠️ TRAMPA VALOR": "#ff9800",        # Naranja Alerta (Trampa de Valor)
    "⚪ RIESGO / BAJA CALIDAD": "#9e9e9e",# Gris Baja Calidad
    "🔴 SOBREVALORADA": "#ff4b4b"        # Rojo Sobrevaloración (P05)
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
    """Interpolación lineal suave entre umbrales óptimos y medios."""
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

def ultimo_valor_tabla(df, claves):
    """Obtiene el último valor no nulo de una fila contable."""
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = df.loc[k].dropna()
                if not s.empty:
                    return float(s.iloc[-1])
    return 0.0

def serie_valores_tabla(df, claves, n=4):
    """Extrae los últimos N valores anuales válidos (orden cronológico) para normalizar ciclos."""
    if df is not None and not df.empty:
        for k in claves:
            if k in df.index:
                s = pd.to_numeric(df.loc[k], errors='coerce').dropna()
                if not s.empty:
                    return [float(x) for x in s.iloc[-n:].values]
    return []

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
    return "REP.MC, KHC, ENG.MC, DGE.L, PFE, BATS.L, RKT.L, TGT, WPC, HRL, BMY, O, RED.MC, CMCSA, EBRO.MC, LOG.MC, VZ, ACN, WKL.AS, VOW3.DE, PEP, KO, VICI, IIPR, HSY, MDLZ, UPS, GOOGL, UNH, GIS, ADP, LOW, MCD, VIS.MC, MC.PA, NKE, MKC, JNJ, PG, CL, WMT, MDT, ABT, ABBV, BDX, EMR, GPC, SYY, APD, STAG, MRK, MO, ABF.L, PBR, OHI, CSCO, PM, CVX, XOM, TAP, IBE.MC, GAW.L, AD.AS, ITX.MC, ELE.MC, VID.MC, UNA.AS, PH, NDSN, CSL"

def guardar_watchlist(texto):
    try:
        with open(ARCHIVO_WATCHLIST, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# ==========================================
# MOTOR DE DESCARGA CON CACHÉ EN DISCO PERSISTENTE
# ==========================================
@st.cache_data(persist="disk", ttl=604800, show_spinner=False)
def descargar_fundamentales_persistentes_disco(t_clean):
    """
    Descarga estados contables e info pesada y los guarda en DISCO duro por 7 días.
    Evita bloqueos (rate-limit) de Yahoo Finance.
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
    """Cotización rápida y ligera (renovada cada 60s)."""
    try:
        t = yf.Ticker(t_clean)
        fast = t.fast_info
        if fast is not None and fast.last_price is not None:
            return float(fast.last_price), getattr(fast, 'currency', None), getattr(fast, 'shares', None)
    except Exception:
        pass
    return None, None, None

# ==========================================
# MOTOR DE AUDITORÍA DE CALIDAD Y VALORACIÓN DGI
# ==========================================
def analizar_empresa_rapido(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado):
    try:
        t_clean = ticker_symbol.strip().upper()
        info, dividendos_raw, historial_raw, inc_stmt, bs_stmt, cf_stmt = descargar_fundamentales_persistentes_disco(t_clean)

        if dividendos_raw.empty or len(historial_raw) < 200:
            return None

        precio_vivo, curr_vivo, shares_vivo = obtener_cotizacion_viva_radar(t_clean)

        def get_safe(key, default=0.0):
            val = info.get(key)
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        currency_raw = curr_vivo or info.get('currency', 'USD')
        es_peniques_uk = (currency_raw == 'GBp')
        currency = 'GBP' if es_peniques_uk else currency_raw
        curr_fin = info.get('financialCurrency', currency) or currency
        if curr_fin == 'GBp':
            curr_fin = 'GBP'
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

        # Clasificación sectorial inteligente
        sector_en = info.get('sector', '') or ''
        industry_en = info.get('industry', '') or ''
        nombre_empresa = info.get('shortName') or info.get('longName') or t_clean
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
        # MOTOR DE DIVIDENDOS BLINDADO
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
        # EXTRACCIÓN Y NORMALIZACIÓN MULTIANUAL DE BALANCES
        # ==========================================
        shares = get_safe('sharesOutstanding', 0.0)
        if shares <= 0 and shares_vivo:
            shares = shares_vivo
        if shares <= 0:
            shares = ultimo_valor_tabla(inc_stmt, ['Diluted Average Shares', 'Basic Average Shares'])

        # BPA y PER normalizados
        bpa_serie = serie_valores_tabla(inc_stmt, ['Diluted EPS', 'Basic EPS'], n=4)
        bpa_trailing = get_safe('trailingEps', 0.0)
        if bpa_trailing == 0 and bpa_serie:
            bpa_trailing = bpa_serie[-1] * fx_rate
        bpa_mediano_3y = (float(np.median(bpa_serie[-3:])) * fx_rate) if len(bpa_serie) >= 2 else bpa_trailing

        per = get_safe('trailingPE', 0.0)
        if per <= 0 and bpa_trailing > 0 and precio_actual > 0:
            per = precio_actual / bpa_trailing
        if per <= 0:
            per = get_safe('forwardPE', 0.0)

        # Payout BPA (usando BPA actual, pero suavizado con mediana 3Y si hay un bache contable puntual)
        bpa_ref_payout = max(bpa_trailing, bpa_mediano_3y * 0.85) if (bpa_trailing > 0 and bpa_mediano_3y > 0) else (bpa_trailing if bpa_trailing > 0 else bpa_mediano_3y)
        payout_bpa = get_safe('payoutRatio', 0.0) * 100
        if (payout_bpa <= 0 or payout_bpa > 250) and bpa_ref_payout > 0:
            payout_bpa = (forward_dividend / bpa_ref_payout) * 100

        # Deuda y Caja
        total_debt = get_safe('totalDebt', 0.0) * fx_rate
        if total_debt <= 0:
            total_debt = ultimo_valor_tabla(bs_stmt, ['Total Debt', 'Long Term Debt And Capital Lease Obligation', 'Long Term Debt']) * fx_rate

        total_cash = get_safe('totalCash', 0.0) * fx_rate
        if total_cash <= 0:
            total_cash = ultimo_valor_tabla(bs_stmt, ['Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents', 'Cash']) * fx_rate

        # EBITDA y EBIT (con respaldo de serie histórica)
        ebitda = get_safe('ebitda', 0.0) * fx_rate
        if ebitda <= 0:
            ebitda = ultimo_valor_tabla(inc_stmt, ['EBITDA', 'Normalized EBITDA', 'Operating Income']) * fx_rate

        ebit_serie = [x * fx_rate for x in serie_valores_tabla(inc_stmt, ['Operating Income', 'EBIT'], n=4)]
        ebit_val = get_safe('operatingIncome', 0.0) * fx_rate
        if ebit_val <= 0 and ebit_serie:
            ebit_val = ebit_serie[-1]
        if ebitda <= 0 and ebit_val > 0:
            ebitda = ebit_val * 1.18

        # Flujo de Caja Libre (FCF) y Operativo (OCF) Normalizados (TTM + Mediana 3Y)
        fcf_serie = [x * fx_rate for x in serie_valores_tabla(cf_stmt, ['Free Cash Flow'], n=4)]
        ocf_serie = [x * fx_rate for x in serie_valores_tabla(cf_stmt, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'], n=4)]
        capex_serie = [abs(x) * fx_rate for x in serie_valores_tabla(cf_stmt, ['Capital Expenditure', 'Capital Expenditures'], n=4)]

        if not fcf_serie and ocf_serie and len(ocf_serie) == len(capex_serie):
            fcf_serie = [o - c for o, c in zip(ocf_serie, capex_serie)]

        fcf_ttm = get_safe('freeCashflow', 0.0) * fx_rate
        if fcf_ttm == 0 and fcf_serie:
            fcf_ttm = fcf_serie[-1]

        ocf_ttm = get_safe('operatingCashflow', 0.0) * fx_rate
        if ocf_ttm == 0 and ocf_serie:
            ocf_ttm = ocf_serie[-1]

        if fcf_ttm == 0 and ocf_ttm != 0:
            capex_ult = capex_serie[-1] if capex_serie else 0.0
            fcf_ttm = ocf_ttm - capex_ult

        # Normalización anticíclica: 65% flujo actual + 35% mediana últimos 3 años
        fcf_med_3y = float(np.median(fcf_serie[-3:])) if len(fcf_serie) >= 2 else fcf_ttm
        ocf_med_3y = float(np.median(ocf_serie[-3:])) if len(ocf_serie) >= 2 else ocf_ttm

        fcf_norm = (0.65 * fcf_ttm + 0.35 * fcf_med_3y) if (fcf_ttm != 0 and fcf_med_3y != 0) else (fcf_ttm if fcf_ttm != 0 else fcf_med_3y)
        ocf_norm = (0.65 * ocf_ttm + 0.35 * ocf_med_3y) if (ocf_ttm != 0 and ocf_med_3y != 0) else (ocf_ttm if ocf_ttm != 0 else ocf_med_3y)

        flujo_caja_referencia = ocf_norm if es_reit_puro else fcf_norm

        # Fondos Propios, Activos y ROE/ROIC/CROIC
        total_equity_raw = get_safe('totalStockholderEquity', 0.0) * fx_rate
        if total_equity_raw == 0:
            total_equity_raw = ultimo_valor_tabla(bs_stmt, ['Stockholders Equity', 'Total Stockholder Equity', 'Common Stock Equity']) * fx_rate

        net_inc_serie = [x * fx_rate for x in serie_valores_tabla(inc_stmt, ['Net Income', 'Net Income Common Stockholders'], n=4)]
        net_inc_val = net_inc_serie[-1] if net_inc_serie else 0.0

        roe = get_safe('returnOnEquity', 0.0) * 100
        if roe == 0 and total_equity_raw > 0 and net_inc_val > 0:
            roe = (net_inc_val / total_equity_raw) * 100

        # Ventas y Márgenes Operativos (Nivel + Estabilidad 3A)
        rev_serie = [x * fx_rate for x in serie_valores_tabla(inc_stmt, ['Total Revenue', 'Operating Revenue'], n=4)]
        rev_tabla = rev_serie[-1] if rev_serie else (get_safe('totalRevenue', 0.0) * fx_rate)

        operating_margins = get_safe('operatingMargins', 0.0) * 100
        if operating_margins == 0 and rev_tabla > 0 and ebit_val > 0:
            operating_margins = (ebit_val / rev_tabla) * 100

        # Estabilidad de margen operativo en los últimos 3-4 años
        margen_estable_o_creciente = True
        if len(ebit_serie) >= 3 and len(rev_serie) == len(ebit_serie):
            margenes_hist = [(e / r) * 100 for e, r in zip(ebit_serie, rev_serie) if r > 0]
            if len(margenes_hist) >= 3:
                margen_estable_o_creciente = margenes_hist[-1] >= (np.mean(margenes_hist[:-1]) - 2.0)

        # Conversión de Caja (OCF / Beneficio Neto) y Margen FCF
        fcf_margin = (flujo_caja_referencia / rev_tabla) * 100 if (rev_tabla > 0 and flujo_caja_referencia > 0) else 0.0
        conversion_caja = (ocf_norm / net_inc_val) if (net_inc_val > 0 and ocf_norm > 0) else 1.0

        pb = get_safe('priceToBook', -1.0)
        current_ratio = get_safe('currentRatio', 0.0)
        if current_ratio <= 0 and not bs_stmt.empty:
            ca_v = ultimo_valor_tabla(bs_stmt, ['Current Assets', 'Total Current Assets'])
            cl_v = ultimo_valor_tabla(bs_stmt, ['Current Liabilities', 'Total Current Liabilities'])
            if cl_v > 0:
                current_ratio = ca_v / cl_v

        # Detección de "Cannibal Compounders" (empresas con patrimonio neto negativo o mínimo por recompras masivas: MCD, LOW, PM, ADP, CL...)
        es_canibal_recompras = (not es_reit_puro) and (not es_financiera) and (operating_margins >= 16.0 or fcf_margin >= 12.0) and (total_equity_raw <= 0 or pb < 0 or pb > 18.0)
        es_regulada_o_reit = es_reit_puro or es_utility_pura

        payout_lim_bpa = 85.0 if es_regulada_o_reit else 62.0
        payout_ama_bpa = 95.0 if es_regulada_o_reit else 78.0
        payout_limite_fcf = 80.0 if es_reit_puro else (75.0 if es_utility_pura else 62.0)
        payout_amarillo_fcf = 92.0 if es_regulada_o_reit else 82.0

        # Deuda Neta / EBITDA
        tiene_caja_neta = (total_cash >= total_debt) and (ebitda > 0 or total_cash > 0)
        deuda_neta = max(0.0, total_debt - total_cash)
        if es_financiera:
            deuda_ebitda = -1.0
        elif tiene_caja_neta:
            deuda_ebitda = 0.0
        elif ebitda > 0:
            deuda_ebitda = deuda_neta / ebitda
        elif total_debt > 0:
            deuda_ebitda = 999.0
        else:
            deuda_ebitda = 0.0

        # Payout FCF y P/FCF
        payout_fcf, p_fcf = -1.0, -1.0
        if flujo_caja_referencia != 0 and shares > 0 and forward_dividend > 0:
            fcf_per_share = flujo_caja_referencia / shares
            if fcf_per_share > 0:
                payout_fcf = (forward_dividend / fcf_per_share) * 100
                p_fcf = precio_actual / fcf_per_share
            elif fcf_per_share < 0:
                payout_fcf = 999.0

        # ROIC y CROIC (Cash Return on Invested Capital)
        roic, croic = None, None
        try:
            tot_assets = ultimo_valor_tabla(bs_stmt, ['Total Assets']) * fx_rate
            curr_liab = ultimo_valor_tabla(bs_stmt, ['Current Liabilities', 'Total Current Liabilities']) * fx_rate
            inv_cap_contable = (total_debt + max(0.0, total_equity_raw)) - total_cash
            inv_cap_activos = (tot_assets - curr_liab - total_cash) if tot_assets > curr_liab else 0.0
            inv_cap = max(inv_cap_contable, inv_cap_activos * 0.75) if inv_cap_contable > 0 else inv_cap_activos

            if inv_cap > 0:
                if ebit_val > 0:
                    roic = ((ebit_val * 0.78) / inv_cap) * 100
                if flujo_caja_referencia > 0:
                    croic = (flujo_caja_referencia / inv_cap) * 100
        except Exception:
            pass

        # Selección inteligente de métrica de rentabilidad según estructura de capital
        if es_financiera:
            metrica_rentabilidad = roe if roe > 0 else None
        elif es_reit_puro:
            metrica_rentabilidad = operating_margins if operating_margins > 0 else roic
        else:
            candidatos_rent = [x for x in [roic, croic] if x is not None and 0 < x < 150]
            if es_canibal_recompras and operating_margins > 0:
                candidatos_rent.append(operating_margins * 0.90)
            if not candidatos_rent and 0 < roe < 150:
                candidatos_rent.append(roe)
            metrica_rentabilidad = max(candidatos_rent) if candidatos_rent else None

        # Crecimientos a 3 Años (BPA y Ventas)
        crecimiento_bpa_3y = None
        if len(bpa_serie) >= 4 and bpa_serie[0] > 0 and bpa_serie[-1] > 0:
            crecimiento_bpa_3y = (((bpa_serie[-1] / bpa_serie[0]) ** (1 / (len(bpa_serie) - 1))) - 1) * 100
        elif len(bpa_serie) >= 3 and bpa_serie[0] > 0 and bpa_serie[-1] > 0:
            crecimiento_bpa_3y = (((bpa_serie[-1] / bpa_serie[0]) ** (1 / 2)) - 1) * 100
        if crecimiento_bpa_3y is None and info.get('earningsGrowth') is not None:
            crecimiento_bpa_3y = float(info.get('earningsGrowth')) * 100

        revenue_cagr_3y = None
        if len(rev_serie) >= 4 and rev_serie[0] > 0 and rev_serie[-1] > 0:
            revenue_cagr_3y = (((rev_serie[-1] / rev_serie[0]) ** (1 / (len(rev_serie) - 1))) - 1) * 100
        elif len(rev_serie) >= 3 and rev_serie[0] > 0 and rev_serie[-1] > 0:
            revenue_cagr_3y = (((rev_serie[-1] / rev_serie[0]) ** (1 / 2)) - 1) * 100
        if revenue_cagr_3y is None and info.get('revenueGrowth') is not None:
            revenue_cagr_3y = float(info.get('revenueGrowth')) * 100

        # Cobertura de Intereses
        cobertura_intereses = None
        if tiene_caja_neta:
            cobertura_intereses = 30.0
        elif not inc_stmt.empty:
            try:
                claves_op = ['EBITDA', 'Normalized EBITDA', 'Operating Income'] if es_reit_puro else ['Operating Income', 'EBIT']
                ebit_cov = ultimo_valor_tabla(inc_stmt, claves_op)
                int_exp = abs(ultimo_valor_tabla(inc_stmt, ['Interest Expense', 'Interest Expense Non Operating']))
                if ebit_cov > 0 and int_exp > 0:
                    cobertura_intereses = ebit_cov / int_exp
            except Exception:
                pass
        if cobertura_intereses is None and ebit_val > 0 and total_debt > 0:
            cobertura_intereses = ebit_val / (total_debt * 0.045)

        # ==========================================
        # HISTORIAL DE DIVIDENDOS, RACHA Y DGR 5A
        # ==========================================
        dividendos_barras = divs_por_año.copy()
        if año_actual in dividendos_barras.index:
            dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)
        else:
            dividendos_barras.loc[año_actual] = forward_dividend

        años_pagando = int(año_actual - dividendos_barras.index[0]) if not dividendos_barras.empty else 0
        if es_aristocrata_reconocida:
            años_pagando = max(años_pagando, 25)

        dgr_5y, dgr_periodo, dgr_1y = None, None, None
        if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
            dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
        if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
            dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1 / 5) - 1) * 100
        if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
            dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1 / años_analisis) - 1) * 100

        fatiga_dividendo = bool(dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.5 and (dgr_1y / dgr_5y) < 0.40)

        # Detector de racha sin recortes (con tolerancia a desfase de fecha ex-dividendo en pagos semestrales europeos)
        racha_sin_recortes = 0
        tolerancia_racha = 0.94 if pagos_por_año <= 2 else 0.975
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                actual_d = dividendos_barras.iloc[-i]
                prev_d = dividendos_barras.iloc[-(i + 1)]
                if actual_d >= prev_d * tolerancia_racha:
                    racha_sin_recortes += 1
                elif i + 2 <= len(dividendos_barras) and actual_d >= dividendos_barras.iloc[-(i + 2)] * 0.98:
                    # Si el año anterior tuvo un dividendo extraordinario puntual pero la tendencia base sigue intacta
                    racha_sin_recortes += 1
                else:
                    break
        if es_aristocrata_reconocida and (dgr_1y is None or dgr_1y >= -1.0):
            racha_sin_recortes = max(racha_sin_recortes, 25)

        # Variación de acciones (Recompras netas vs Dilución)
        variacion_acciones, recompras_anualizadas = None, 0.0
        try:
            if not inc_stmt.empty:
                for key in ['Diluted Average Shares', 'Basic Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = pd.to_numeric(inc_stmt.loc[key], errors='coerce').dropna()
                        sh_data = sh_data[sh_data > 0]
                        if len(sh_data) >= 2:
                            sy = sh_data.groupby(pd.to_datetime(sh_data.index).year).last().sort_index()
                            acc_ini, acc_fin = float(sy.iloc[0]), float(sy.iloc[-1])
                            n_anios_sh = max(1, int(sy.index[-1] - sy.index[0]))
                            if acc_ini > 0 and (acc_fin / acc_ini) > 0.10:
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                recompras_anualizadas = -(((acc_fin / acc_ini) ** (1 / n_anios_sh)) - 1) * 100
                                break
        except Exception:
            pass
        recompras_anualizadas = max(-6.0, min(8.0, recompras_anualizadas))

        # ==============================================================================
        # 1. MOTOR DE CALIDAD FORENSE DGI MEJORADO (0 A 10.0 PUNTOS - 5 PILARES)
        # ==============================================================================
        if es_reit_puro:
            lim_deuda_optima, lim_deuda_aceptable = 5.5, 7.2
        elif es_utility_pura:
            lim_deuda_optima, lim_deuda_aceptable = 3.8, 5.2
        elif es_defensivo or es_telecom or es_canibal_recompras:
            lim_deuda_optima, lim_deuda_aceptable = 2.7, 4.0
        else:
            lim_deuda_optima, lim_deuda_aceptable = 2.0, 3.4

        # --- PILAR 1: SOLVENCIA Y FORTALEZA DE BALANCE (Máx 2.0 pts) ---
        if tiene_caja_neta and not es_financiera:
            pilar1 = 2.0
        elif es_financiera:
            pts_deuda = interpolar_puntos(roe, 13.5, 7.0, 1.5, 0.4, inverso=False)
            pts_cob = 0.5 if (roe >= 10.0 or pb <= 1.5) else 0.2
            pilar1 = round(min(2.0, pts_deuda + pts_cob), 2)
        else:
            deuda_eval = deuda_ebitda if deuda_ebitda >= 0 else 2.4
            pts_deuda = interpolar_puntos(deuda_eval, lim_deuda_optima, lim_deuda_aceptable, 1.35, 0.25, inverso=True)
            u_cob_max = 3.2 if es_reit_puro else (4.2 if es_utility_pura else 7.5)
            u_cob_min = 1.7 if es_reit_puro else (2.2 if es_utility_pura else 2.8)
            pts_cob = interpolar_puntos(cobertura_intereses, u_cob_max, u_cob_min, 0.65, 0.15, inverso=False) if cobertura_intereses is not None else 0.30
            pilar1 = round(min(2.0, pts_deuda + pts_cob), 2)

        # --- PILAR 2: SOSTENIBILIDAD DEL DIVIDENDO Y CALIDAD DE CAJA (Máx 2.5 pts) ---
        if es_financiera:
            pts_pay_fin = interpolar_puntos(payout_bpa, 48.0, 75.0, 2.0, 0.5, inverso=True) if payout_bpa > 0 else 1.2
            pts_conv_fin = 0.5 if bpa_trailing > 0 else 0.1
            pilar2 = round(min(2.5, pts_pay_fin + pts_conv_fin), 2)
        elif es_reit_puro:
            pts_ffo = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 2.1, 0.5, inverso=True) if 0 < payout_fcf < 200 else 1.1
            pts_margen_reit = 0.4 if fcf_margin >= 25.0 else (0.2 if fcf_margin >= 12.0 else 0.1)
            pilar2 = round(min(2.5, pts_ffo + pts_margen_reit), 2)
        else:
            pts_fcf_sub = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 1.45, 0.30, inverso=True) if 0 < payout_fcf < 200 else 0.20
            pts_bpa_sub = interpolar_puntos(payout_bpa, payout_lim_bpa, payout_ama_bpa, 0.60, 0.15, inverso=True) if payout_bpa > 0 else 0.20
            # Calidad de conversión de beneficio contable en flujo de caja real
            pts_conv = interpolar_puntos( max(conversion_caja, fcf_margin / 12.0), 0.90, 0.55, 0.45, 0.10, inverso=False)
            pilar2 = round(min(2.5, pts_fcf_sub + pts_bpa_sub + pts_conv), 2)

        # --- PILAR 3: FOSO ECONÓMICO (MOAT), ROIC/CROIC Y ESTABILIDAD DE MÁRGENES (Máx 2.2 pts) ---
        if es_reit_puro:
            pts_rent_sub = interpolar_puntos(operating_margins, 38.0, 20.0, 1.30, 0.35, inverso=False)
        elif es_utility_pura or es_telecom:
            pts_rent_sub = interpolar_puntos(metrica_rentabilidad, 10.5, 5.5, 1.30, 0.35, inverso=False) if metrica_rentabilidad is not None else 0.60
        else:
            pts_rent_sub = interpolar_puntos(metrica_rentabilidad, 15.0, 7.5, 1.30, 0.30, inverso=False) if metrica_rentabilidad is not None else 0.55

        pts_margen_est = (0.45 if margen_estable_o_creciente else 0.15) if operating_margins >= 12.0 else (0.25 if margen_estable_o_creciente else 0.05)
        pts_rev_sub = interpolar_puntos(revenue_cagr_3y, 4.0, 0.3, 0.45, 0.10, inverso=False) if revenue_cagr_3y is not None else 0.20
        pilar3 = round(min(2.2, pts_rent_sub + pts_margen_est + pts_rev_sub), 2)

        # --- PILAR 4: HISTORIAL WEISS, CONSISTENCIA Y POTENCIA DGI (Máx 1.8 pts) ---
        bono_longevidad = 6 if años_pagando >= 25 else (3 if años_pagando >= 15 else (1 if años_pagando >= 10 else 0))
        racha_efectiva = racha_sin_recortes + bono_longevidad
        pts_racha = interpolar_puntos(racha_efectiva, 20.0, 5.0, 1.05, 0.25, inverso=False)

        dgr_opt_p4 = 4.5 if (es_utility_pura or es_reit_puro) else 6.5
        pts_dgr_sub = interpolar_puntos(dgr_5y, dgr_opt_p4, 2.0, 0.75, 0.15, inverso=False) if dgr_5y is not None else 0.20
        if fatiga_dividendo:
            pts_dgr_sub = max(0.05, pts_dgr_sub - 0.25)
        pilar4 = round(min(1.8, pts_racha + pts_dgr_sub), 2)

        # --- PILAR 5: ASIGNACIÓN DE CAPITAL, RECOMPRAS Y CRECIMIENTO POR ACCIÓN (Máx 1.5 pts) ---
        if es_reit_puro:
            # Los REITs emiten capital para comprar inmuebles; se evalúa si ese capital crea crecimiento de dividendo/FFO por acción
            crec_reit_eval = max(dgr_5y or 0.0, crecimiento_bpa_3y or 0.0)
            pilar5 = round(interpolar_puntos(crec_reit_eval, 4.5, 1.0, 1.5, 0.35, inverso=False), 2)
        else:
            pts_rec_sub = interpolar_puntos(recompras_anualizadas, 1.5, -0.3, 0.65, 0.20, inverso=False)
            crec_ppa_eval = crecimiento_bpa_3y if crecimiento_bpa_3y is not None else dgr_5y
            pts_crec_sub = interpolar_puntos(crec_ppa_eval, 6.0, 1.0, 0.85, 0.20, inverso=False) if crec_ppa_eval is not None else 0.30
            pilar5 = round(min(1.5, pts_rec_sub + pts_crec_sub), 2)

        # Penalizaciones forenses estrictas ante banderas rojas
        penalizacion = 0.0
        if dgr_1y is not None and dgr_1y < -4.0 and racha_sin_recortes == 0:
            penalizacion += 1.4  # Recorte real reciente del dividendo
        if not es_reit_puro and not es_financiera and payout_fcf > 105.0:
            penalizacion += 0.9  # El flujo de caja libre normalizado no cubre el dividendo
        if not es_financiera and deuda_ebitda > (lim_deuda_aceptable * 1.35) and (cobertura_intereses is not None and cobertura_intereses < 2.2):
            penalizacion += 0.7  # Alerta de estrés financiero en balance
        if (revenue_cagr_3y is not None and revenue_cagr_3y < -2.5) and (crecimiento_bpa_3y is not None and crecimiento_bpa_3y < -5.0):
            penalizacion += 0.5  # Contracción simultánea de ingresos y beneficios

        score_calidad = max(1.0, min(10.0, round((pilar1 + pilar2 + pilar3 + pilar4 + pilar5) - penalizacion, 1)))
        desglose_calidad_str = (
            f"Balance: {f_num(pilar1, 2)}/2,0 | Caja/Payout: {f_num(pilar2, 2)}/2,5 | "
            f"Moat/ROIC: {f_num(pilar3, 2)}/2,2 | Historial: {f_num(pilar4, 2)}/1,8 | "
            f"Cap.Alloc: {f_num(pilar5, 2)}/1,5" + (f" | Penaliz.: -{f_num(penalizacion, 1)}" if penalizacion > 0 else "")
        )

        # ==============================================================================
        # 2. REGLA DE CHOWDER OFICIAL (SEGÚN EL LISTÓN DEL AUTOR DEL GRÁFICO)
        # ==============================================================================
        # Listón oficial del gráfico:
        # - Si Rentabilidad (Yield) >= 3.0%: se exigen 12 puntos (o 8 en Utilities/REITs puros de alto yield)
        # - Si Rentabilidad (Yield) < 3.0%: el autor exige 15 puntos
        chowder_target_autor = 12.0 if yield_actual >= 3.0 else 15.0
        chowder_target_sectorial = 8.0 if ((es_utility_pura or es_reit_puro) and yield_actual >= 4.0) else chowder_target_autor
        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0

        pasa_liston_autor = bool(chowder_number != -999.0 and dgr_5y is not None and dgr_5y > 0 and chowder_number >= chowder_target_autor)
        pasa_12_no_15 = bool(chowder_number != -999.0 and yield_actual < 3.0 and 12.0 <= chowder_number < 15.0)
        pasa_chowder_ajustado = bool(chowder_number != -999.0 and dgr_5y is not None and dgr_5y >= 1.5 and chowder_number >= chowder_target_sectorial)

        # ==============================================================================
        # 3. SCORE DE VALORACIÓN AJUSTADO POR CRECIMIENTO (0 A 10.0 PUNTOS)
        # ==============================================================================
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
            crec_negocio_val = min(crec_negocio_val, 2.0)

        # Prima de múltiplo para empresas de calidad sobresaliente (Moat >= 8.0)
        prima_calidad_mult = 1.5 if score_calidad >= 8.0 else 0.0
        mult_optimo = float(np.clip(8.5 + max(0.0, crec_negocio_val) * 0.9 + prima_calidad_mult, 8.5, 19.0))
        mult_aceptable = mult_optimo + 7.0

        if es_financiera and p_fcf <= 0:
            pts_pfcf = interpolar_puntos(pb, 1.15, 2.1, 2.5, 0.4, inverso=True) if pb > 0 else 0.0
        else:
            pts_pfcf = interpolar_puntos(p_fcf, 15.0 if es_reit_puro else mult_optimo, 22.0 if es_reit_puro else mult_aceptable, 2.5, 0.4, inverso=True) if p_fcf > 0 else 0.0

        multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
        pts_per = interpolar_puntos(multiplo_per_eval, mult_optimo + 0.5, mult_aceptable + 1.0, 2.0, 0.3, inverso=True) if multiplo_per_eval > 0 else 0.0

        if dgr_5y is not None:
            if dgr_5y < 1.0 or (dgr_1y is not None and dgr_1y < -2.0):
                pts_chowder = 0.0
            else:
                chowder_efectivo = min(yield_actual, 7.0) + dgr_5y
                pts_chowder = interpolar_puntos(chowder_efectivo, chowder_target_sectorial, chowder_target_sectorial - 3.0, 1.5, 0.3, inverso=False)
        else:
            pts_chowder = 0.0

        score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
        score_total = round(score_calidad + score_val, 1)

        # ==============================================================================
        # 4. VEREDICTO Y ESTADO DE LA LISTA (COLORES UNIFICADOS CON EL GRÁFICO)
        # ==============================================================================
        deterioro_grave = (
            (score_calidad < 5.4) or
            (not es_reit_puro and not es_financiera and payout_fcf > 105.0) or
            (dgr_1y is not None and dgr_1y < -4.0 and racha_sin_recortes == 0)
        )

        if es_aristocrata_reconocida and score_calidad >= 6.0 and (dgr_1y is None or dgr_1y >= 0.0) and (cobertura_intereses is None or cobertura_intereses >= 3.5):
            deterioro_grave = False

        es_trampa_valor = (precio_actual <= precio_acumulacion) and deterioro_grave

        if es_trampa_valor:
            estado = "⚠️ TRAMPA VALOR"
            orden_estado = 5
        elif score_calidad >= 7.6 and precio_actual <= precio_compra:
            estado = "💎 COMPRA FUERTE"
            orden_estado = 1
        elif score_calidad >= 6.2 and precio_actual <= precio_compra:
            estado = "🎯 COMPRA (P95)"
            orden_estado = 2
        elif score_calidad >= 6.4 and precio_actual <= precio_acumulacion:
            estado = "🔵 ACUMULAR (P90)"
            orden_estado = 3
        elif precio_actual >= precio_venta:
            estado = "🔴 SOBREVALORADA"
            orden_estado = 7
        elif score_calidad < 5.5:
            estado = "⚪ RIESGO / BAJA CALIDAD"
            orden_estado = 6
        else:
            estado = "🟡 MANTENER"
            orden_estado = 4

        # ==============================================================================
        # 5. PROYECCIÓN BOGLE-WEISS 5A Y SIMULACIÓN DE RENTA
        # ==============================================================================
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
        divs_netos_5a = sum([renta_neta_orden_anual * ((1 + max(0.0, crec_bogle) / 100.0) ** a) for a in range(1, 6)])
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
            "Chowder": f"{f_num(chowder_number, 1)} (Obj: {f_num(chowder_target_autor, 0)})" if chowder_number != -999.0 else "N/D",
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
            "Deuda/EBITDA": ("N/A (Banca)" if es_financiera else ("Caja Neta" if tiene_caja_neta else (f_num(deuda_ebitda, 2, "x") if 0 <= deuda_ebitda < 900 else "N/D"))),
            "Payout FCF": (f"{f_num(payout_fcf, 1, '%')} (FFO)" if (es_reit_puro and 0 < payout_fcf < 500) else (f_num(payout_fcf, 1, "%") if 0 < payout_fcf < 500 else ("Déficit" if payout_fcf >= 500 else "N/D"))),
            "Payout BPA": ("N/A (REIT)" if es_reit_puro else (f_num(payout_bpa, 1, "%") if payout_bpa > 0 else "N/D")),
            "ROIC/ROE": f_num(metrica_rentabilidad, 1, "%") if metrica_rentabilidad is not None else "N/D",
            "Ventas 3A": f_num(revenue_cagr_3y, 1, "%", signo_pos=True) if revenue_cagr_3y is not None else "N/D",
            "Acciones": f_num(variacion_acciones, 1, "%", signo_pos=True) if variacion_acciones is not None else "N/D",
            "Crec. BPA 3Y": f_num(crecimiento_bpa_3y, 1, "%", signo_pos=True) if crecimiento_bpa_3y is not None else "N/D",
            "DGR 5A": f_num(dgr_5y, 2, "%") if dgr_5y is not None else "N/D",
            f"DGR {años_analisis}A": f_num(dgr_periodo, 2, "%") if dgr_periodo is not None else "N/D",
            "Años Pag.": f"{años_pagando}A (R: {racha_sin_recortes}A)",
            "Desglose Calidad": desglose_calidad_str,

            # Metadatos internos para ordenación, estilos y Gráfico Zona Chowder
            "_nombre": nombre_empresa,
            "_orden_estado": orden_estado,
            "_score_total": score_total,
            "_score_calidad": score_calidad,
            "_score_val": score_val,
            "_pilar1": pilar1, "_pilar2": pilar2, "_pilar3": pilar3, "_pilar4": pilar4, "_pilar5": pilar5, "_penaliz": penalizacion,
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
            "_chowder_target": chowder_target_autor,
            "_chowder_target_sec": chowder_target_sectorial,
            "_pasa_liston_autor": pasa_liston_autor,
            "_pasa_12_no_15": pasa_12_no_15,
            "_pasa_chowder_sec": pasa_chowder_ajustado,
            "_col_renta": col_renta_nombre
        }
    except Exception:
        return None


# ==============================================================================
# GENERADOR DEL GRÁFICO INTERACTIVO "ZONA CHOWDER" + PUNTOS COLOREADOS POR ESTADO
# ==============================================================================
def construir_grafico_zona_chowder(df_source, mostrar_etiquetas="Zona Chowder y Compras", acotar_extremos=True):
    """
    Construye el gráfico de la Zona Chowder fiel al diseño de referencia:
    - Eje X: Crecimiento anual del dividendo, últimos 5 años (%)
    - Eje Y: Rentabilidad por dividendo (%)
    - Zona sombreada dorada: >= 12 puntos (si Yield >= 3%) y >= 15 puntos (si Yield < 3%)
    - Línea discontinua entre 12 y 15 puntos para Yield < 3% ("Pasa los 12, no los 15")
    - Puntos coloreados según el Estado en la Watchlist (Verde P95, Azul P90, Rojo Sobrevalorada, Amarillo Mantener, Naranja Trampa...)
    """
    df_plot = df_source[df_source["_dgr"] != -999].copy()
    if df_plot.empty:
        return None

    # Límites dinámicos o acotados al marco visual clásico [0% - 18%+ en X, 0% - 10%+ en Y]
    max_x_data = float(df_plot["_dgr"].max()) if not df_plot.empty else 18.0
    max_y_data = float(df_plot["_y_act"].max()) if not df_plot.empty else 10.0

    x_max_axis = max(18.5, min(26.0, max_x_data + 1.5)) if acotar_extremos else max(18.5, max_x_data + 1.5)
    y_max_axis = max(10.2, min(14.0, max_y_data + 0.8)) if acotar_extremos else max(10.2, max_y_data + 1.0)
    x_min_axis = 0.0 if acotar_extremos else min(0.0, float(df_plot["_dgr"].min()) - 1.0)

    # Coordenadas del área sombreada "Zona Chowder" (Listón del autor: 12 pts si Y >= 3%, 15 pts si Y < 3%)
    x_top_left = max(0.0, 12.0 - y_max_axis)
    poly_x = [x_top_left, 9.0, 12.0, 15.0, x_max_axis, x_max_axis, x_top_left]
    poly_y = [y_max_axis, 3.0, 3.0, 0.0, 0.0, y_max_axis, y_max_axis]

    fig = go.Figure()

    # 1. Polígono sombreado de la "Zona Chowder"
    fig.add_trace(go.Scatter(
        x=poly_x,
        y=poly_y,
        fill="toself",
        fillcolor="rgba(218, 165, 32, 0.22)",
        line=dict(color="rgba(0,0,0,0)"),
        hoverinfo="skip",
        showlegend=False,
        name="Zona Chowder"
    ))

    # 2. Línea discontinua amarilla de los 12 puntos totales (desde Y=10% hasta Y=0%, X=12%)
    fig.add_trace(go.Scatter(
        x=[x_top_left, 9.0, 12.0],
        y=[y_max_axis, 3.0, 0.0],
        mode="lines",
        line=dict(color="#f5b700", width=2.2, dash="dash"),
        hoverinfo="skip",
        name="Línea 12 puntos (Yield + DGR = 12)"
    ))

    # 3. Escalón sólido del autor para Yield < 3% (exige 15 puntos: de (9,3) -> (12,3) -> (15,0))
    fig.add_trace(go.Scatter(
        x=[9.0, 12.0, 15.0],
        y=[3.0, 3.0, 0.0],
        mode="lines",
        line=dict(color="#f5b700", width=3.4),
        hoverinfo="skip",
        name="Listón estricto (<3% yield exige 15 pts)"
    ))

    # 4. Trazado de las empresas agrupadas por su ESTADO en la lista (con sus colores exactos)
    orden_estados_leyenda = [
        "💎 COMPRA FUERTE",
        "🎯 COMPRA (P95)",
        "🔵 ACUMULAR (P90)",
        "🟡 MANTENER",
        "⚠️ TRAMPA VALOR",
        "⚪ RIESGO / BAJA CALIDAD",
        "🔴 SOBREVALORADA"
    ]

    for est in orden_estados_leyenda:
        sub = df_plot[df_plot["Estado"] == est].copy()
        if sub.empty:
            continue

        color_punto = MAPA_COLORES_ESTADO.get(est, "#ffffff")

        # Coordenadas X e Y (acotadas al borde si tienen DGR negativo para que siempre sean visibles en el gráfico)
        x_vals = np.clip(sub["_dgr"].values, x_min_axis + 0.15, x_max_axis - 0.25) if acotar_extremos else sub["_dgr"].values
        y_vals = np.clip(sub["_y_act"].values, 0.1, y_max_axis - 0.2) if acotar_extremos else sub["_y_act"].values

        # Borde dorado grueso si supera el listón del autor, aro ámbar si está entre 12 y 15 (<3% yield), borde fino oscuro para el resto
        colores_borde = []
        anchos_borde = []
        tamanos_punto = []
        textos_etiqueta = []
        hover_texts = []

        for idx_t, row in sub.iterrows():
            pasa_autor = bool(row["_pasa_liston_autor"])
            pasa_12_15 = bool(row["_pasa_12_no_15"])

            if pasa_autor:
                colores_borde.append("#ffd700")
                anchos_borde.append(2.8)
                tamanos_punto.append(14)
                veredicto_chowder_txt = "✅ SÍ pasa el listón del autor"
            elif pasa_12_15:
                colores_borde.append("#ffae00")
                anchos_borde.append(2.4)
                tamanos_punto.append(13)
                veredicto_chowder_txt = "🟡 Pasa los 12, no los 15 (Yield < 3%)"
            else:
                colores_borde.append("#0b1520")
                anchos_borde.append(1.4)
                tamanos_punto.append(11)
                veredicto_chowder_txt = "❌ No alcanza el listón (12 / 15 pts)"

            # Control de etiquetas de texto sobre los puntos
            es_compra_o_acum = ("COMPRA" in est or "ACUMULAR" in est)
            if mostrar_etiquetas == "Todas las empresas":
                textos_etiqueta.append(idx_t)
            elif mostrar_etiquetas == "Zona Chowder y Compras":
                textos_etiqueta.append(idx_t if (pasa_autor or pasa_12_15 or es_compra_o_acum) else "")
            elif mostrar_etiquetas == "Solo en Zona Chowder":
                textos_etiqueta.append(idx_t if (pasa_autor or pasa_12_15) else "")
            else:
                textos_etiqueta.append("")

            hover_texts.append(
                f"<b>{idx_t} — {row['_nombre']}</b><br>"
                f"Estado Radar: <b>{est}</b><br>"
                f"Calidad Forense: <b>{row['Calidad']}</b> | Valoración: <b>{row['Valoración']}</b><br>"
                f"──────────────────────────<br>"
                f"Rentabilidad (Yield): <b>{f_num(row['_y_act'], 2, '%')}</b><br>"
                f"Crecimiento Div. 5A: <b>{f_num(row['_dgr'], 2, '%')}</b><br>"
                f"Número Chowder: <b>{f_num(row['_chowder'], 1)} pts</b> (Listón: {f_num(row['_chowder_target'], 0)})<br>"
                f"Listón Chowder: <b>{veredicto_chowder_txt}</b><br>"
                f"──────────────────────────<br>"
                f"Cotización: {row['Cotización Actual']} | Suelo P95: {row['Suelo P95']}<br>"
                f"<i>{row['Desglose Calidad']}</i>"
            )

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers+text",
            name=est,
            text=textos_etiqueta,
            textposition="top center",
            textfont=dict(color="#e8eef5", size=11, family="Arial Black, sans-serif"),
            marker=dict(
                color=color_punto,
                size=tamanos_punto,
                line=dict(color=colores_borde, width=anchos_borde),
                opacity=0.94
            ),
            hovertext=hover_texts,
            hoverinfo="text"
        ))

    # Anotaciones idénticas al gráfico original de Zona Chowder
    fig.add_annotation(
        x=x_max_axis - 0.6,
        y=y_max_axis - 0.6,
        text="<b>Zona Chowder</b><br><span style='font-size:12px;'>12 puntos o más</span>",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        align="right",
        font=dict(color="#f5b700", size=18)
    )

    fig.add_annotation(
        x=14.2,
        y=4.4,
        text="<b>Con rentabilidad bajo el 3 %,<br>el autor pedía 15</b>",
        showarrow=False,
        xanchor="center",
        align="center",
        font=dict(color="#f5b700", size=12)
    )

    fig.update_layout(
        title=dict(
            text="Número Chowder = <span style='color:#f5b700;'>rentabilidad</span> + <span style='color:#f5b700;'>crecimiento anual del dividendo</span> a 5 años",
            font=dict(color="#ffffff", size=18),
            x=0.01,
            y=0.96
        ),
        paper_bgcolor="#0b1520",
        plot_bgcolor="#101f30",
        height=600,
        margin=dict(l=55, r=30, t=65, b=65),
        xaxis=dict(
            title=dict(text="<b>Crecimiento anual del dividendo, últimos 5 años</b>", font=dict(color="#ffffff", size=14)),
            range=[x_min_axis, x_max_axis],
            dtick=3,
            ticksuffix=" %",
            gridcolor="rgba(255, 255, 255, 0.08)",
            zerolinecolor="rgba(255, 255, 255, 0.18)",
            tickfont=dict(color="#b0c4de", size=12)
        ),
        yaxis=dict(
            title=dict(text="<b>Rentabilidad por dividendo</b>", font=dict(color="#ffffff", size=14)),
            range=[0.0, y_max_axis],
            dtick=2,
            ticksuffix=" %",
            gridcolor="rgba(255, 255, 255, 0.08)",
            zerolinecolor="rgba(255, 255, 255, 0.18)",
            tickfont=dict(color="#b0c4de", size=12)
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.22,
            xanchor="center",
            x=0.5,
            font=dict(color="#e0e6ed", size=12),
            bgcolor="rgba(11, 21, 32, 0.85)",
            bordercolor="rgba(255, 255, 255, 0.15)",
            borderwidth=1
        ),
        hoverlabel=dict(
            bgcolor="#0e1b29",
            font_size=12,
            font_family="sans-serif",
            bordercolor="#f5b700"
        )
    )

    return fig


# ==========================================
# INTERFAZ PRINCIPAL DE LA PÁGINA (RADAR)
# ==========================================
st.title("📡 Radar Watchlist DGI — Geraldine Weiss + Zona Chowder")

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
            texto_estado.text(f"Auditando calidad y valoración de {ticker} ({idx+1}/{len(lista_tickers)})...")
            datos = analizar_empresa_rapido(ticker, años_masivos, impuesto_masivo, aplicar_merma_masivo, capital_masivo)
            if datos:
                resultados.append(datos)

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

    # ==========================================
    # MÉTRICAS RESUMEN RÁPIDAS DEL RADAR
    # ==========================================
    total_emp = len(df_res)
    n_compra_p95 = int(df_res["Estado"].isin(["💎 COMPRA FUERTE", "🎯 COMPRA (P95)"]).sum())
    n_acum_p90 = int((df_res["Estado"] == "🔵 ACUMULAR (P90)").sum())
    n_chowder_ok = int(df_res["_pasa_liston_autor"].sum())
    n_calidad_alta = int((df_res["_score_calidad"] >= 7.5).sum())

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Empresas Auditadas", f"{total_emp}")
    k2.metric("🟢 En Compra (P95)", f"{n_compra_p95}")
    k3.metric("🔵 En Acumulación (P90)", f"{n_acum_p90}")
    k4.metric("🏆 Superan Listón Chowder", f"{n_chowder_ok}")
    k5.metric("⭐ Calidad Élite (≥ 7,5/10)", f"{n_calidad_alta}")

    # ==========================================
    # SECCIÓN 1: GRÁFICO INTERACTIVO ZONA CHOWDER
    # ==========================================
    st.markdown("### 📊 Mapa Visual: Zona Chowder y Estado de Valoración")
    col_f1, col_f2, col_f3 = st.columns([2, 1.5, 1.5])
    with col_f1:
        estados_disponibles = list(MAPA_COLORES_ESTADO.keys())
        filtro_estados_graf = st.multiselect(
            "Filtrar estados en el gráfico:",
            options=estados_disponibles,
            default=estados_disponibles
        )
    with col_f2:
        modo_etiquetas = st.selectbox(
            "Mostrar nombres (Tickers) en el gráfico:",
            options=["Zona Chowder y Compras", "Todas las empresas", "Solo en Zona Chowder", "Ninguna (solo al pasar ratón)"],
            index=0
        )
    with col_f3:
        acotar_ejes = st.checkbox(
            "Mantener escala clásica Chowder (0% a 18%+)",
            value=True,
            help="Mantiene los ejes limpios como en el gráfico clásico de Chowder, situando valores con DGR negativo en el borde izquierdo (0%) y mostrando su dato exacto al pasar el cursor."
        )

    df_graf_filtrado = df_res[df_res["Estado"].isin(filtro_estados_graf)] if filtro_estados_graf else df_res
    fig_chowder = construir_grafico_zona_chowder(df_graf_filtrado, mostrar_etiquetas=modo_etiquetas, acotar_extremos=acotar_ejes)

    if fig_chowder is not None:
        st.plotly_chart(fig_chowder, use_container_width=True)
        st.caption(
            "💡 **Leyenda rápida del gráfico:** El **color interior de cada punto** corresponde exactamente a su **Estado en la lista** "
            "(🟢 Verde = Compra P95 / Compra Fuerte, 🔵 Azul = Acumular P90, 🟡 Amarillo = Mantener, 🟠 Naranja = Trampa de Valor, 🔴 Rojo = Sobrevalorada). "
            "El **borde dorado brillante** destaca las empresas que cumplen el **Listón oficial de Chowder** (≥ 12 pts con yield ≥ 3%, o ≥ 15 pts con yield < 3%)."
        )

    # Tabla resumen del Listón de Chowder (igual a la parte inferior de la imagen) + Auditor de Calidad
    with st.expander("🏅 Ver Tabla del Listón de Chowder y Desglose Forense de los 5 Pilares de Calidad", expanded=False):
        tab_c1, tab_c2 = st.tabs(["📋 Listón del Autor (Zona Chowder)", "🔬 Auditoría de Calidad Forense (5 Pilares)"])

        with tab_c1:
            df_ch_tabla = df_res[df_res["_chowder"] != -999].sort_values(by="_chowder", ascending=False).copy()
            filas_chowder = []
            for tk, r in df_ch_tabla.iterrows():
                if r["_pasa_liston_autor"]:
                    liston_str = "Sí"
                elif r["_pasa_12_no_15"]:
                    liston_str = "No (12-15)"
                else:
                    liston_str = "No"
                filas_chowder.append({
                    "Ticker": tk,
                    "Estado": r["Estado"],
                    "Calidad": r["Calidad"],
                    "Rentabilidad": f_num(r["_y_act"], 2, " %"),
                    "Crecimiento 5 años": f_num(r["_dgr"], 1, " %"),
                    "Listón del autor": liston_str,
                    "Número": f_num(r["_chowder"], 1),
                    "_pasa": r["_pasa_liston_autor"],
                    "_pasa12": r["_pasa_12_no_15"]
                })
            df_ch_view = pd.DataFrame(filas_chowder).set_index("Ticker")

            def estilo_tabla_chowder(row):
                estilos = [''] * len(row)
                est_c = MAPA_COLORES_ESTADO.get(row["Estado"], "#ffffff")
                for i, col in enumerate(row.index):
                    if col == "Estado":
                        estilos[i] = f"color: {est_c}; font-weight: bold;"
                    elif col == "Listón del autor":
                        if row["_pasa"]:
                            estilos[i] = "color: #21c354; font-weight: bold;"
                        elif row["_pasa12"]:
                            estilos[i] = "color: #faca2b; font-weight: bold;"
                        else:
                            estilos[i] = "color: #8b9bb4;"
                    elif col == "Número":
                        estilos[i] = "color: #f5b700; font-weight: bold;"
                return estilos

            cols_ch_vis = ["Estado", "Calidad", "Rentabilidad", "Crecimiento 5 años", "Listón del autor", "Número"]
            st.dataframe(
                df_ch_view.style.apply(estilo_tabla_chowder, axis=1),
                column_order=cols_ch_vis,
                use_container_width=True,
                height=360
            )

        with tab_c2:
            st.markdown(
                "**Arquitectura de los 5 Pilares de Calidad Forense (Máx. 10,0 puntos):**\n"
                "- **Pilar 1 — Balance y Solvencia (2,0 pts):** Deuda Neta/EBITDA ajustada por sector, premio por Caja Neta y Cobertura de Intereses.\n"
                "- **Pilar 2 — Sostenibilidad de Caja (2,5 pts):** Payout FCF normalizado (media ponderada TTM + Mediana 3A para evitar distorsiones de CapEx), Payout BPA y Conversión de Caja.\n"
                "- **Pilar 3 — Foso Económico / Moat (2,2 pts):** ROIC / CROIC (reconociendo recompras caníbales como MCD, LOW o ADP), nivel y estabilidad del margen operativo y crecimiento de ventas.\n"
                "- **Pilar 4 — Historial DGI Weiss (1,8 pts):** Años pagando, racha sin recortes y crecimiento del dividendo (DGR 5A) con detector de fatiga.\n"
                "- **Pilar 5 — Asignación de Capital (1,5 pts):** Recompras netas de acciones y crecimiento del BPA/FFO por acción a 3 años."
            )
            df_cal_view = pd.DataFrame({
                "Estado": df_res["Estado"],
                "Calidad Total": df_res["Calidad"],
                "1. Balance (2,0)": df_res["_pilar1"].apply(lambda x: f_num(x, 2)),
                "2. Caja y Payout (2,5)": df_res["_pilar2"].apply(lambda x: f_num(x, 2)),
                "3. Moat y ROIC (2,2)": df_res["_pilar3"].apply(lambda x: f_num(x, 2)),
                "4. Historial DGI (1,8)": df_res["_pilar4"].apply(lambda x: f_num(x, 2)),
                "5. Cap. Alloc (1,5)": df_res["_pilar5"].apply(lambda x: f_num(x, 2)),
                "Penalización": df_res["_penaliz"].apply(lambda x: f"-{f_num(x, 1)}" if x > 0 else "0,0")
            }, index=df_res.index)
            st.dataframe(df_cal_view, use_container_width=True, height=360)

    # ==========================================
    # SECCIÓN 2: TABLA PRINCIPAL DEL RADAR DGI
    # ==========================================
    st.markdown("### 📋 Tabla Completa del Radar Watchlist")

    def color_row(row):
        styles = [''] * len(row)
        est = str(row['Estado'])
        for idx, col_name in enumerate(row.index):
            if col_name == 'Calidad':
                if row['_score_calidad'] >= 7.8: styles[idx] = 'color: #21c354; font-weight: bold;'
                elif row['_score_calidad'] >= 6.2: styles[idx] = 'color: #faca2b; font-weight: bold;'
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
                if row['_chowder'] != -999.0:
                    if row['_pasa_liston_autor']:
                        styles[idx] = 'color: #21c354; font-weight: bold;'
                    elif row['_pasa_12_no_15'] or row['_pasa_chowder_sec']:
                        styles[idx] = 'color: #faca2b; font-weight: bold;'
                    else:
                        styles[idx] = 'color: #ff4b4b;'
                else:
                    styles[idx] = 'color: #888;'
            elif col_name == 'Estado':
                if "COMPRA FUERTE" in est: styles[idx] = 'background-color: #004d00; color: #7cfc00; font-weight: bold;'
                elif "ACUMULAR" in est: styles[idx] = 'background-color: #003344; color: #00d4ff; font-weight: bold;'
                elif "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: #21c354; font-weight: bold;'
                elif "TRAMPA" in est: styles[idx] = 'background-color: #663300; color: #ff9800; font-weight: bold;'
                elif "RIESGO" in est: styles[idx] = 'background-color: #333333; color: #cccccc;'
                elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: #ff4b4b; font-weight: bold;'
                else: styles[idx] = 'background-color: #3d3d00; color: #faca2b; font-weight: bold;'
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
```
