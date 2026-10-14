import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import warnings
import plotly.graph_objects as go

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
# FORMATEO ESPAÑOL (1.234,56)
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

def f_millones(val, sym=""):
    if pd.isna(val) or val is None:
        return "N/D"
    try:
        v = float(val)
        abs_v = abs(v)
        if abs_v >= 1e9:
            return f"{f_num(v / 1e9, 2)} MM{sym}"
        elif abs_v >= 1e6:
            return f"{f_num(v / 1e6, 1)} M{sym}"
        else:
            return f"{f_num(v, 0)} {sym}"
    except Exception:
        return str(val)

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
# CACHÉ COMPARTIDA DE DATOS
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

# ==========================================
# FUNCIÓN PRINCIPAL PESTAÑA 4: DECÁLOGO DGI (20 PTS)
# ==========================================
def render_decalogo_weiss(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen):
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

    st.markdown("""
<style>
.card-audit {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 10px;
    padding: 12px 15px;
    margin-bottom: 11px;
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
.badge-pts-verde { background: rgba(33, 195, 84, 0.22); color: #21c354; padding: 3px 9px; border-radius: 5px; font-weight: 700; font-size: 0.82rem; white-space: nowrap; }
.badge-pts-ambar { background: rgba(250, 202, 43, 0.22); color: #faca2b; padding: 3px 9px; border-radius: 5px; font-weight: 700; font-size: 0.82rem; white-space: nowrap; }
.badge-pts-rojo { background: rgba(255, 75, 75, 0.22); color: #ff4b4b; padding: 3px 9px; border-radius: 5px; font-weight: 700; font-size: 0.82rem; white-space: nowrap; }
.badge-pts-info { background: rgba(0, 212, 255, 0.18); color: #00d4ff; padding: 3px 9px; border-radius: 5px; font-weight: 700; font-size: 0.82rem; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)

    def render_item_auditoria(titulo, valor_txt, pts_ganados, pts_max, diagnostico_txt, meta_txt):
        """Dibuja una tarjeta de auditoría sin sangrías HTML para evitar bloques de código en Markdown."""
        if pts_max > 0:
            pct = min(100.0, max(0.0, (pts_ganados / pts_max) * 100))
            if pct >= 75:
                color = "#21c354"
                cls_b = "badge-pts-verde"
            elif pct >= 35:
                color = "#faca2b"
                cls_b = "badge-pts-ambar"
            else:
                color = "#ff4b4b"
                cls_b = "badge-pts-rojo"
            badge_html = f'<span class="{cls_b}">+{f_num(pts_ganados, 2)} / {f_num(pts_max, 1)} pts</span>'
            barra_html = f'<div style="background: rgba(255,255,255,0.08); border-radius: 4px; height: 6px; width: 100%; overflow: hidden; margin: 8px 0;"><div style="background: {color}; width: {pct:.1f}%; height: 100%;"></div></div>'
        else:
            badge_html = '<span class="badge-pts-info">ℹ️ Auxiliar</span>'
            barra_html = '<div style="height: 6px;"></div>'

        html_card = (
            f'<div class="card-audit">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">'
            f'<span style="font-size: 0.92rem; font-weight: 600; color: #eee;">{titulo}: <strong style="color:#00d4ff;">{valor_txt}</strong></span>'
            f'{badge_html}'
            f'</div>'
            f'{barra_html}'
            f'<div style="font-size: 0.83rem; color: #ccc; margin-bottom: 4px;">{diagnostico_txt}</div>'
            f'<div style="font-size: 0.77rem; color: #999;">🎯 <em>{meta_txt}</em></div>'
            f'</div>'
        )
        st.markdown(html_card, unsafe_allow_html=True)

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
    precio_actual = float(historial_analisis['Close'].dropna().iloc[-1])

    sector_en = info.get('sector', 'Desconocido')
    industry_en = info.get('industry', 'Desconocido')
    pais = info.get('country', 'Desconocido')
    nombre_empresa = info.get('shortName', ticker_symbol)
    sector_final = TRADUCCION.get(sector_en, sector_en)

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_tecnologica = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
    es_industrial = 'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()

    merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
    net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

    # --- DIVIDENDOS ANUALES ---
    años = dividendos.index.year
    conteo_por_año = años.value_counts()
    conteo_closed = conteo_por_año[conteo_por_año.index < año_actual]
    pagos_por_año = int(conteo_closed.mode().iloc[0]) if not conteo_closed.empty else 4
    if pagos_por_año not in [1, 2, 4, 12]:
        pagos_por_año = 4 if pagos_por_año == 3 else (12 if pagos_por_año > 10 else 4)

    ventana_med = max(4, pagos_por_año * 2)
    mediana_pagos = dividendos.rolling(window=ventana_med, min_periods=1).median()
    dividendos_regulares = dividendos.where(dividendos <= mediana_pagos * 1.75, mediana_pagos)

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

    precio_compra_weiss = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0.0

    # --- FUNDAMENTALES ---
    payout_ratio = get_safe('payoutRatio') * 100
    per_actual = get_safe('trailingPE')
    per_forward = get_safe('forwardPE')
    per = per_actual if per_actual > 0 else per_forward
    bpa_forward = get_safe('forwardEps')
    deuda_equity = get_safe('debtToEquity')
    market_cap = get_safe('marketCap') * fx_rate
    current_ratio = get_safe('currentRatio')
    price_to_book = get_safe('priceToBook', -1)
    roe = get_safe('returnOnEquity', 0.0) * 100
    operating_margins = get_safe('operatingMargins', 0.0) * 100
    respaldo_institucional = get_safe('heldPercentInstitutions') * 100

    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    total_cash = get_safe('totalCash', 0.0) * fx_rate
    ebitda = get_safe('ebitda', 0.0) * fx_rate
    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    shares = get_safe('sharesOutstanding', 0.0)

    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw
    etiqueta_fcf = "FFO" if (es_reit_puro and ocf_raw > fcf_raw) else "FCF"

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

    payout_limite_fcf = 75.0 if es_regulada_o_reit else 65.0
    payout_amarillo_fcf = 90.0 if es_regulada_o_reit else 85.0
    payout_forward = (forward_dividend / bpa_forward) * 100 if bpa_forward > 0 else -1

    deuda_neta = max(0.0, total_debt - total_cash)
    deuda_ebitda = (deuda_neta / ebitda) if ebitda > 0 else (999.0 if (total_debt > 0 and not es_financiera) else 0.0)

    años_crecimiento_bpa, total_años_bpa_datos, crecimiento_bpa_3y = 0, 0, None
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

    payout_fcf, p_fcf, fcf_yield, deuda_fcf = -1, -1, 0.0, -1
    if flujo_caja_referencia != 0 and shares > 0:
        fcf_per_share = flujo_caja_referencia / shares
        if fcf_per_share > 0:
            payout_fcf = (forward_dividend / fcf_per_share) * 100
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100
    if flujo_caja_referencia > 0:
        deuda_fcf = total_debt / flujo_caja_referencia

    dividendos_barras = divs_reg_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
    divs_recientes = dividendos_barras.tail(años_analisis + 1)
    incrementos_dividendo = int((divs_recientes.diff().dropna() > 0).sum())

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
    variacion_acciones = None
    try:
        if shares_hist is not None and len(shares_hist) > 1:
            fecha_corte_shares = hoy_ts - pd.DateOffset(years=años_analisis + 3)
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
                            acc_ini, acc_fin = shares_yearly.iloc[0], shares_yearly.iloc[-1]
                            if acc_ini > 0:
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                break
        except Exception: pass

    # ==========================================
    # CÁLCULO RIGUROSO DE PUNTOS
    # ==========================================
    lim_deuda_optima = 3.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 2.5
    lim_deuda_aceptable = 5.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0

    if es_financiera:
        pts_deuda = 2.0 if roe >= 14.0 else (1.0 if roe >= 9.0 else 0.0)
        pts_cob = 0.5 if current_ratio >= 1.1 else 0.0
    else:
        pts_deuda = interpolar_puntos(deuda_ebitda, lim_deuda_optima, lim_deuda_aceptable, 2.0, 0.5, inverso=True)
        pts_cob = (0.5 if cobertura_intereses >= 5.0 else (0.25 if cobertura_intereses >= 3.0 else 0.0)) if cobertura_intereses is not None else (0.5 if deuda_neta == 0 else 0.0)

    if es_financiera and payout_fcf == -1:
        pts_fcf = interpolar_puntos(payout_ratio, 45.0, 70.0, 2.0, 0.5, inverso=True) if payout_ratio > 0 else 0.0
    else:
        pts_fcf = interpolar_puntos(payout_fcf, payout_limite_fcf, payout_amarillo_fcf, 2.0, 0.5, inverso=True) if payout_fcf > 0 else 0.0

    if (años_pagando >= 25 and racha_sin_recortes >= 12) or racha_sin_recortes >= 20: pts_hist = 2.0
    elif (años_pagando >= 12 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10: pts_hist = 1.2
    elif racha_sin_recortes >= 5: pts_hist = 0.6
    else: pts_hist = 0.0
    if fatiga_dividendo and pts_hist > 0.5: pts_hist -= 0.6
    pts_hist = max(0.0, pts_hist)

    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic
    cond_roic = (metrica_rentabilidad is not None and metrica_rentabilidad >= 12.0) or (es_reit_puro and operating_margins >= 28.0)
    cond_rev = (revenue_cagr_3y is not None and revenue_cagr_3y > 1.0)
    pts_foso = 1.5 if (cond_roic and cond_rev) else (0.75 if (cond_roic or cond_rev) else 0.0)

    pts_dgr = 1.0 if (dgr_5y is not None and dgr_5y >= 6.0) else (0.5 if (dgr_5y is not None and dgr_5y >= 3.0) else 0.0)
    pts_cap = 1.0 if (variacion_acciones is not None and variacion_acciones < -1.0) else (0.5 if (crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 2.0) else 0.0)

    score_calidad = min(10.0, round(pts_deuda + pts_cob + pts_fcf + pts_hist + pts_foso + pts_dgr + pts_cap, 1))

    if yield_actual >= yield_infravalorado: pts_yield = 4.0
    elif yield_actual >= yield_medio: pts_yield = interpolar_puntos(yield_actual, yield_infravalorado, yield_medio, 4.0, 2.0, inverso=False)
    elif yield_actual >= yield_sobrevalorado: pts_yield = interpolar_puntos(yield_actual, yield_medio, yield_sobrevalorado, 2.0, 0.0, inverso=False)
    else: pts_yield = 0.0

    if es_financiera and p_fcf <= 0:
        pts_pfcf = interpolar_puntos(price_to_book, 1.1, 2.0, 2.5, 0.8, inverso=True) if price_to_book > 0 else 0.0
    else:
        pts_pfcf = interpolar_puntos(p_fcf, 15.0, 22.0, 2.5, 0.8, inverso=True) if p_fcf > 0 else 0.0

    multiplo_per_eval = p_fcf if (es_reit_puro and p_fcf > 0) else per
    pts_per = interpolar_puntos(multiplo_per_eval, 16.0, 24.0, 2.0, 0.6, inverso=True) if multiplo_per_eval > 0 else 0.0

    chowder_target = 9.0 if ((es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0) else (13.0 if yield_actual >= 3.0 else 16.0)
    if dgr_5y is not None:
        chowder_number = yield_actual + dgr_5y
        pts_chowder = interpolar_puntos(chowder_number, chowder_target, chowder_target - 3.0, 1.5, 0.3, inverso=False)
    else:
        chowder_number, pts_chowder = None, 0.0

    score_val = min(10.0, round(pts_yield + pts_pfcf + pts_per + pts_chowder, 1))
    score_total_20 = round(score_calidad + score_val, 1)

    # ==========================================
    # SECCIÓN 1: HUELLA PENTAGONAL FIJA (SIN ROTACIÓN ACCIDENTAL EN MÓVIL)
    # ==========================================
    st.header(f"📋 Auditoría y Decálogo DGI (20 Puntos) — {nombre_empresa} ({ticker_symbol})")
    st.caption(f"Nota Global Combinada: {f_num(score_total_20, 1)} / 20,0 pts  |  Calidad: {f_num(score_calidad, 1)}/10  |  Valoración: {f_num(score_val, 1)}/10")

    pilar_yield_pct = (pts_yield / 4.0) * 100
    pilar_mult_pct = ((pts_pfcf + pts_per + pts_chowder) / 6.0) * 100
    pilar_caja_pct = (pts_fcf / 2.0) * 100
    pilar_solv_pct = ((pts_deuda + pts_cob + pts_cap) / 3.5) * 100
    pilar_foso_pct = ((pts_hist + pts_foso + pts_dgr) / 4.5) * 100

    categorias_radar = [
        "1. Yield Weiss (4p)",
        "2. Múltiplos y Chowder (6p)",
        "3. Seguridad Caja (2p)",
        "4. Solvencia y Capital (3,5p)",
        "5. Foso e Historial (4,5p)"
    ]
    valores_radar = [pilar_yield_pct, pilar_mult_pct, pilar_caja_pct, pilar_solv_pct, pilar_foso_pct]

    # Configuración para evitar que al hacer scroll en el móvil se deforme o gire el gráfico
    config_fijo_movil = {
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d'],
        'scrollZoom': False
    }

    col_rad1, col_rad2 = st.columns(2)
    with col_rad1:
        st.markdown("#### 🕸️ Huella Pentagonal DGI (% de Perfección por Pilar)")
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=valores_radar + [valores_radar[0]],
            theta=categorias_radar + [categorias_radar[0]],
            fill='toself',
            fillcolor='rgba(0, 212, 255, 0.22)',
            line=dict(color='#00d4ff', width=2.5),
            name=ticker_symbol
        ))
        fig_radar.update_layout(
            template='plotly_dark',
            dragmode=False,
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%", fixedrange=True, gridcolor="rgba(255,255,255,0.1)"),
                angularaxis=dict(fixedrange=True, rotation=90, direction="clockwise"),
                bgcolor='rgba(0,0,0,0)'
            ),
            margin=dict(l=40, r=40, t=25, b=25),
            height=330,
            paper_bgcolor='rgba(0,0,0,0)',
            showlegend=False
        )
        st.plotly_chart(fig_radar, use_container_width=True, config=config_fijo_movil)

    with col_rad2:
        st.markdown("#### 📊 Puntos Obtenidos vs. Máximo Posible por Bloque")
        bloques_nombres = [
            "Yield Histórico Weiss",
            "Múltiplos (P/FCF, PER, Chowder)",
            "Payout Efectivo (FCF)",
            "Solvencia y Recompras",
            "Foso, Historial y DGR"
        ]
        pts_obt = [pts_yield, round(pts_pfcf + pts_per + pts_chowder, 2), pts_fcf, round(pts_deuda + pts_cob + pts_cap, 2), round(pts_hist + pts_foso + pts_dgr, 2)]
        pts_max_b = [4.0, 6.0, 2.0, 3.5, 4.5]
        pts_falta = [max(0.0, m - o) for o, m in zip(pts_obt, pts_max_b)]

        fig_bar_pts = go.Figure()
        fig_bar_pts.add_trace(go.Bar(
            y=bloques_nombres, x=pts_obt, name='Puntos Ganados', orientation='h',
            marker_color='#21c354', text=[f"{f_num(v, 2)} pts" for v in pts_obt], textposition='inside'
        ))
        fig_bar_pts.add_trace(go.Bar(
            y=bloques_nombres, x=pts_falta, name='Margen Restante', orientation='h',
            marker_color='rgba(255, 255, 255, 0.12)', text=[f"Máx: {f_num(m, 1)}" for m in pts_max_b], textposition='inside'
        ))
        fig_bar_pts.update_layout(
            barmode='stack', template='plotly_dark', dragmode=False,
            margin=dict(l=0, r=10, t=20, b=20), height=330,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
            xaxis=dict(title="Puntos", fixedrange=True),
            yaxis=dict(fixedrange=True)
        )
        st.plotly_chart(fig_bar_pts, use_container_width=True, config=config_fijo_movil)

    idx_mejor = int(np.argmax(valores_radar))
    idx_peor = int(np.argmin(valores_radar))
    st.markdown(
        f'<div class="explicacion-graf">'
        f'💡 <strong>Diagnóstico Global en {ticker_symbol}:</strong> Suma <strong>{f_num(score_total_20, 1)} de 20 puntos posibles</strong>. '
        f'Su mayor fortaleza actual es <strong>{categorias_radar[idx_mejor]}</strong> (al <strong>{f_num(valores_radar[idx_mejor], 0, "%")}</strong> de su capacidad máxima), '
        f'mientras que su punto más exigente hoy es <strong>{categorias_radar[idx_peor]}</strong> (al <strong>{f_num(valores_radar[idx_peor], 0, "%")}</strong>).'
        f'</div>',
        unsafe_allow_html=True
    )

    # ==========================================
    # SECCIÓN 2: AUDITORÍA PUNTO POR PUNTO (2 COLUMNAS)
    # ==========================================
    st.divider()
    col_aud_val, col_aud_cal = st.columns(2)

    with col_aud_val:
        st.subheader(f"🏷️ 1. Auditoría de Valoración ({f_num(score_val, 1)} / 10,0 Pts)")

        diag_y = f"Percentil {f_num(percentil_yield_actual, 1)}% de los últimos {años_analisis} años (Media: {f_num(yield_medio, 2, '%')} | Suelo P95: {f_num(yield_infravalorado, 2, '%')})."
        meta_y = f"Logra los 4,0 pts si el precio baja a ≤ {f_num(precio_compra_weiss, 2, sym)} (Yield ≥ {f_num(yield_infravalorado, 2, '%')})." if pts_yield < 4.0 else "¡Máxima puntuación conseguida! Cotiza en suelo histórico de compra."
        render_item_auditoria(
            "Canal de Rendimiento Weiss",
            f"{f_num(yield_actual, 2, '%')} ({f_num(yield_actual * net_mult, 2, '%')} Neto)",
            pts_yield, 4.0, diag_y, meta_y
        )

        if es_financiera and p_fcf <= 0:
            diag_pf = f"Entidad financiera evaluada mediante Precio / Valor Contable ({f_num(price_to_book, 2, 'x')})."
            meta_pf = "Logra los 2,5 pts con un P/B ≤ 1,10x."
            val_pf_txt = f"{f_num(price_to_book, 2, 'x')} P/B"
        elif p_fcf > 0:
            precio_meta_pfcf = (flujo_caja_referencia / shares) * 15.0 if shares > 0 else 0.0
            diag_pf = f"Yield de Caja Libre ({etiqueta_fcf} Yield) del {f_num(fcf_yield, 2, '%')}. Óptimo ≤ 15x, aceptable ≤ 22x."
            meta_pf = f"Logra los 2,5 pts a un precio ≤ {f_num(precio_meta_pfcf, 2, sym)} (múltiplo ≤ 15,0x)." if pts_pfcf < 2.5 else "¡Máxima puntuación conseguida! Múltiplo de caja ≤ 15,0x."
            val_pf_txt = f"{f_num(p_fcf, 1, 'x')} P/{etiqueta_fcf}"
        else:
            diag_pf = "Flujo de caja libre negativo o no disponible en el último ejercicio."
            meta_pf = "Requiere generación de caja libre positiva y múltiplo ≤ 22,0x."
            val_pf_txt = "Negativo / N/D"
        render_item_auditoria(f"Múltiplo de Caja (Precio / {etiqueta_fcf})", val_pf_txt, pts_pfcf, 2.5, diag_pf, meta_pf)

        if es_reit_puro and p_fcf > 0:
            diag_per = f"En REITs se evalúa P/FFO ({f_num(p_fcf, 1, 'x')}) en lugar del PER contable ({f_num(per, 1, 'x')}) distorsionado por amortizaciones."
            meta_per = "Logra los 2,0 pts con P/FFO ≤ 16,0x."
            val_per_txt = f"{f_num(p_fcf, 1, 'x')} P/FFO"
        elif multiplo_per_eval > 0:
            diag_per = "Múltiplo sobre beneficio contable. Óptimo ≤ 16,0x, aceptable ≤ 24,0x."
            meta_per = "Logra los 2,0 pts cuando el PER baja a ≤ 16,0x." if pts_per < 2.0 else "¡Máxima puntuación conseguida! PER ≤ 16,0x."
            val_per_txt = f"{f_num(per, 1, 'x')}"
        else:
            diag_per = "Beneficio contable negativo en los últimos 12 meses."
            meta_per = "Requiere BPA positivo y PER ≤ 24,0x."
            val_per_txt = "N/D"
        render_item_auditoria("Múltiplo Beneficio (PER)", val_per_txt, pts_per, 2.0, diag_per, meta_per)

        if chowder_number is not None:
            diag_ch = f"Suma de Yield ({f_num(yield_actual, 2, '%')}) + DGR 5A ({f_num(dgr_5y, 2, '%')}). Meta exigida para su perfil: ≥ {f_num(chowder_target, 0)} pts."
            meta_ch = f"Logra los 1,5 pts alcanzando un número Chowder ≥ {f_num(chowder_target, 0)}." if pts_chowder < 1.5 else "¡Máxima puntuación conseguida! Supera el umbral exigido de Chowder."
            val_ch_txt = f"{f_num(chowder_number, 1)} pts"
        else:
            diag_ch = "Sin historial completo de 5 años para calcular DGR 5A."
            meta_ch = "Requiere al menos 5 años de historial de dividendos."
            val_ch_txt = "N/D"
        render_item_auditoria("Regla de Chowder (Retorno Compuesto)", val_ch_txt, pts_chowder, 1.5, diag_ch, meta_ch)

        if price_to_book > 0:
            ctx_pb = "Financiero/Industrial" if (es_financiera or es_industrial) else ("Tecnología" if es_tecnologica else "General")
            render_item_auditoria(
                f"Precio / Valor Contable ({ctx_pb})",
                f"{f_num(price_to_book, 2, 'x')}",
                0.0, 0.0,
                "Compara la cotización frente al patrimonio contable en balance.",
                "En empresas con fuertes recompras (MCD, HD, SBUX) el P/B se dispara sin implicar riesgo."
            )

    with col_aud_cal:
        st.subheader(f"🛡️ 2. Auditoría de Calidad del Negocio ({f_num(score_calidad, 1)} / 10,0 Pts)")

        if payout_fcf > 0:
            diag_pfcf = f"Porcentaje del {etiqueta_fcf} real consumido por el dividendo. Límite sano: ≤ {f_num(payout_limite_fcf, 0, '%')}, alerta: > {f_num(payout_amarillo_fcf, 0, '%')}."
            meta_pfcf = f"Logra los 2,0 pts manteniendo el Payout {etiqueta_fcf} ≤ {f_num(payout_limite_fcf, 0, '%')}." if pts_fcf < 2.0 else f"¡Máxima puntuación! El dividendo está holgadamente cubierto por el {etiqueta_fcf}."
            val_pay_txt = f"{f_num(payout_fcf, 1, '%')}"
        else:
            diag_pfcf = f"Payout Contable BPA: {f_num(payout_ratio, 1, '%')}. (Sin FCF positivo reportado)."
            meta_pfcf = f"Logra los 2,0 pts con Payout sobre caja ≤ {f_num(payout_limite_fcf, 0, '%')}."
            val_pay_txt = f"{f_num(payout_ratio, 1, '%')} (BPA)"
        render_item_auditoria(f"Seguridad del Dividendo (Payout {etiqueta_fcf})", val_pay_txt, pts_fcf, 2.0, diag_pfcf, meta_pfcf)

        if es_financiera:
            diag_deb = f"En banca y seguros se evalúa mediante la rentabilidad sobre recursos propios (ROE: {f_num(roe, 1, '%')})."
            meta_deb = "Logra los 2,0 pts con un ROE ≥ 14,0%."
            val_deb_txt = f"ROE {f_num(roe, 1, '%')}"
        else:
            diag_deb = f"Años de EBITDA para pagar la Deuda Neta. Límite óptimo sectorial: ≤ {f_num(lim_deuda_optima, 1, 'x')} (máx. {f_num(lim_deuda_aceptable, 1, 'x')})."
            meta_deb = f"Logra los 2,0 pts con Deuda Neta / EBITDA ≤ {f_num(lim_deuda_optima, 1, 'x')}." if pts_deuda < 2.0 else "¡Máxima puntuación! Balance con endeudamiento muy bajo."
            val_deb_txt = f"{f_num(deuda_ebitda, 2, 'x')}" if deuda_ebitda < 900 else "Elevada"
        render_item_auditoria("Solvencia Operativa (Deuda Neta / EBITDA)", val_deb_txt, pts_deuda, 2.0, diag_deb, meta_deb)

        val_cob_txt = f"{f_num(cobertura_intereses, 1, 'x')}" if cobertura_intereses is not None else ("Sin Deuda Neta" if deuda_neta == 0 else "N/D")
        diag_cob = "Veces que el beneficio operativo (EBIT) cubre la factura anual de intereses bancarios."
        meta_cob = "Logra los 0,5 pts con un ratio EBIT / Intereses ≥ 5,0x (o deuda neta cero)."
        render_item_auditoria("Cobertura de Intereses (EBIT / Intereses)", val_cob_txt, pts_cob, 0.5, diag_cob, meta_cob)

        aviso_fat = " ⚠️ Penalizado en -0,6 pts por fatiga en la última subida anual." if fatiga_dividendo else ""
        diag_hist = f"Lleva {años_pagando} años repartiendo dividendos y encadena {racha_sin_recortes} años sin recortes.{aviso_fat}"
        meta_hist = "Logra los 2,0 pts con ≥ 20 años sin recortes (o 25 años pagando y 12 sin recortes) sin fatiga reciente."
        render_item_auditoria("Resiliencia e Historial de Pagos", f"{años_pagando}A pagando | {racha_sin_recortes}A sin recorte", pts_hist, 2.0, diag_hist, meta_hist)

        lbl_foso_m = "ROE" if es_financiera else "ROIC"
        val_foso_txt = f"{lbl_foso_m}: {f_num(metrica_rentabilidad, 1, '%')} | Ventas 3A: {f_num(revenue_cagr_3y, 1, '%', signo_pos=True)}"
        diag_foso = "Combina la rentabilidad sobre el capital invertido con la expansión real de facturación a 3 años."
        meta_foso = f"Logra los 1,5 pts con {lbl_foso_m} ≥ 12,0% y crecimiento de ventas > +1,0% anual."
        render_item_auditoria("Foso Económico (Rentabilidad + Ventas)", val_foso_txt, pts_foso, 1.5, diag_foso, meta_foso)

        val_dgr_txt = f_num(dgr_5y, 2, '%') if dgr_5y is not None else "N/D"
        diag_dgr = "Crecimiento anual compuesto del dividendo en los últimos 5 años frente a la inflación."
        meta_dgr = "Logra 1,0 pt completo con DGR 5A ≥ 6,0% anual (0,5 pts si está entre 3,0% y 6,0%)."
        render_item_auditoria("Crecimiento Real del Dividendo (DGR 5A)", val_dgr_txt, pts_dgr, 1.0, diag_dgr, meta_dgr)

        val_cap_txt = f"Acciones: {f_num(variacion_acciones, 1, '%', signo_pos=True)} | BPA 3A: {f_num(crecimiento_bpa_3y, 1, '%', signo_pos=True)}"
        diag_cap = "Evalúa si la directiva crea valor recomprando acciones netas o expandiendo el beneficio por acción."
        meta_cap = "Logra 1,0 pt reduciendo acciones en circulación (> 1%) o 0,5 pts con BPA 3A creciendo > 2%/año."
        render_item_auditoria("Asignación de Capital (Recompras / BPA)", val_cap_txt, pts_cap, 1.0, diag_cap, meta_cap)

    # ==========================================
    # SECCIÓN 3: FORTALEZA INSTITUCIONAL Y MÉTRICAS COMPLEMENTARIAS
    # ==========================================
    st.divider()
    st.subheader("🏛️ 3. Fortaleza Institucional y Métricas Auxiliares (Criterios Clásicos de Weiss)")

    col_inst1, col_inst2, col_inst3 = st.columns(3)
    with col_inst1:
        es_blue_chip = market_cap >= 10e9
        render_item_auditoria(
            "Capitalización Bursátil (Tamaño)",
            f_millones(market_cap, sym),
            0.0, 0.0,
            "🟢 Gran Capitalización (Blue Chip ≥ 10.000 M)." if es_blue_chip else "🟡 Capitalización Media/Pequeña (< 10.000 M).",
            "Geraldine Weiss exigía empresas líderes consolidadas para asegurar liquidez y resiliencia."
        )
    with col_inst2:
        es_inst_fuerte = respaldo_institucional >= 50.0
        render_item_auditoria(
            "Respaldo Institucional (Fondos)",
            f_num(respaldo_institucional, 1, '%'),
            0.0, 0.0,
            "🟢 Alto respaldo de grandes fondos y gestoras (≥ 50%)." if es_inst_fuerte else "🟡 Presencia institucional moderada o alta propiedad familiar.",
            "Geraldine Weiss buscaba que al menos el 50% del capital estuviera en manos institucionales."
        )
    with col_inst3:
        tend_fw_txt = f"Forward Payout BPA: {f_num(payout_forward, 1, '%')}" if payout_forward > 0 else f"Current Ratio (Liquidez): {f_num(current_ratio, 2, 'x')}"
        diag_aux = f"El dividendo ha subido {incrementos_dividendo} veces en los últimos {años_analisis} años."
        if total_años_bpa_datos > 0:
            diag_aux += f" BPA creció en {años_crecimiento_bpa} de los últimos {total_años_bpa_datos} cierres."
        render_item_auditoria(
            "Consistencia de Subidas y Cobertura",
            tend_fw_txt,
            0.0, 0.0,
            diag_aux,
            f"Deuda Total / {etiqueta_fcf}: {f_num(deuda_fcf, 1)} años" if deuda_fcf > 0 else "Revisa que el Forward Payout se mantenga por debajo del límite sectorial."
        )


# ==========================================
# INTERFAZ CONECTADA A MEMORIA GLOBAL
# ==========================================
st.title("📋 4. Decálogo Detallado DGI (20 Puntos)")

st.session_state.setdefault("ticker_activo", "MKC")
st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("merma_activa", True)

lista_años = [5, 10, 12, 15, 20]
idx_años = lista_años.index(st.session_state.años_activo) if st.session_state.años_activo in lista_años else 2

col_d1, col_d2, col_d3 = st.columns([1.3, 1, 1])
with col_d1:
    ticker_input = st.text_input("Ticker activo:", value=st.session_state.ticker_activo).upper().strip()
with col_d2:
    años_analisis = st.selectbox("Periodo Histórico:", lista_años, index=idx_años)
with col_d3:
    impuesto = st.number_input("Retención IRPF (%)", value=float(st.session_state.impuesto_activo), step=1.0)

aplicar_merma = st.checkbox(
    "Aplicar merma fiscal en origen no recuperable (>15% Suiza, Alemania, Francia, Dinamarca, Irlanda)",
    value=st.session_state.merma_activa
)

st.session_state.ticker_activo = ticker_input
st.session_state.años_activo = años_analisis
st.session_state.impuesto_activo = impuesto
st.session_state.merma_activa = aplicar_merma

if ticker_input:
    with st.spinner(f"Auditando los 20 puntos del Decálogo DGI en {ticker_input}..."):
        try:
            render_decalogo_weiss(ticker_input, años_analisis, impuesto, aplicar_merma)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
