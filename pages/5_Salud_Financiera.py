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

# ==========================================
# FUNCIONES DE FORMATEO ESPAÑOL (1.234,56)
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
    """Convierte cifras absolutas a Millones (M) o Miles de Millones (MM) en formato español."""
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
# FUNCIÓN PRINCIPAL PESTAÑA 2: SALUD FINANCIERA
# ==========================================
def render_salud_financiera(ticker_symbol, años_analisis):
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
    nombre_empresa = info.get('shortName', ticker_symbol)
    sector_final = TRADUCCION.get(sector_en, sector_en)

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
    es_financiera = 'financial' in sector_en.lower() or 'bank' in industry_en.lower() or 'insurance' in industry_en.lower()
    es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()

    # Dividendos regulares anuales
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

    # Fundamentales
    bpa_trailing = get_safe('trailingEps')
    bpa_forward = get_safe('forwardEps')
    per_actual = get_safe('trailingPE')
    per_forward = get_safe('forwardPE')
    price_to_book = get_safe('priceToBook', -1)
    deuda_equity = get_safe('debtToEquity')
    roe = get_safe('returnOnEquity', 0.0) * 100
    operating_margins = get_safe('operatingMargins', 0.0) * 100

    total_debt = get_safe('totalDebt', 0.0) * fx_rate
    total_cash = get_safe('totalCash', 0.0) * fx_rate
    ebitda = get_safe('ebitda', 0.0) * fx_rate
    fcf_raw = get_safe('freeCashflow', 0.0) * fx_rate
    ocf_raw = get_safe('operatingCashflow', 0.0) * fx_rate
    shares = get_safe('sharesOutstanding', 0.0)

    flujo_caja_referencia = ocf_raw if (es_reit_puro and ocf_raw > fcf_raw) else fcf_raw
    etiqueta_fcf = "FFO (Flujo Operativo)" if (es_reit_puro and ocf_raw > fcf_raw) else "FCF (Flujo Caja Libre)"

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

    lim_deuda_optima = 3.5 if (es_regulada_o_reit or es_defensivo or es_telecom) else 2.5
    lim_deuda_aceptable = 5.0 if (es_regulada_o_reit or es_defensivo or es_telecom) else 4.0

    deuda_neta = max(0.0, total_debt - total_cash)
    deuda_ebitda = (deuda_neta / ebitda) if ebitda > 0 else (999.0 if (total_debt > 0 and not es_financiera) else 0.0)

    # ROIC
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

    metrica_rentabilidad = roe if (es_financiera or (roic is None and roe > 0)) else roic

    # Crecimiento de Ventas 3A
    revenue_cagr_3y = None
    if not inc_stmt.empty:
        for k in ['Total Revenue', 'Operating Revenue']:
            if k in inc_stmt.index:
                rev_series = inc_stmt.loc[k].dropna()
                if len(rev_series) >= 4 and rev_series.iloc[-4] > 0 and rev_series.iloc[-1] > 0:
                    revenue_cagr_3y = (((rev_series.iloc[-1] / rev_series.iloc[-4]) ** (1 / 3)) - 1) * 100
                break

    # Cobertura de intereses
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

    p_fcf, fcf_yield = -1, 0.0
    if flujo_caja_referencia != 0 and shares > 0:
        fcf_per_share = flujo_caja_referencia / shares
        if fcf_per_share > 0:
            p_fcf = precio_actual / fcf_per_share
            fcf_yield = (fcf_per_share / precio_actual) * 100

    meses_caja_div = None
    gasto_anual_div = forward_dividend * shares
    if gasto_anual_div > 0 and total_cash > 0:
        meses_caja_div = (total_cash / gasto_anual_div) * 12

    # Dividendos y DGR
    dividendos_barras = divs_reg_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

    dgr_5y, dgr_1y = None, None
    if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
        dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
    if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
        dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1/5) - 1) * 100

    fatiga_dividendo = False
    inercia_ratio = None
    if dgr_1y is not None and dgr_5y is not None and dgr_5y > 2.0:
        inercia_ratio = dgr_1y / dgr_5y
        if inercia_ratio < 0.5: fatiga_dividendo = True

    # Acciones en circulación
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
    # CABECERA Y 10 TARJETAS EJECUTIVAS DGI
    # ==========================================
    st.header(f"📊 Radiografía Financiera y Gráficos — {nombre_empresa} ({ticker_symbol})")
    st.caption(f"Sector: {sector_final} | Divisa de análisis: {currency} ({sym}) | Ventana histórica: {años_analisis} Años")

    col_bpa1, col_bpa2 = st.columns(2)
    with col_bpa1:
        if bpa_trailing != 0 and bpa_forward != 0:
            var_bpa = ((bpa_forward - bpa_trailing) / abs(bpa_trailing)) * 100
            b_class = "badge-verde" if var_bpa >= 0 else "badge-rojo"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">💵 Beneficio por Acción (BPA)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(bpa_trailing, 2, sym)} <span style="font-size: 1rem; color: #888;">➔</span> {f_num(bpa_forward, 2, sym)}</span>
                    <span class="{b_class}">{f_num(var_bpa, 1, '%', signo_pos=True)}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Actual ➔ Estimado a 12 meses por consenso</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.metric("BPA Actual", f_num(bpa_trailing, 2, sym) if bpa_trailing != 0 else "N/D")

    with col_bpa2:
        if es_reit_puro and p_fcf > 0:
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏢 Múltiplo Inmobiliario (Precio / FFO)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(p_fcf, 1, 'x')}</span>
                    <span class="{'badge-verde' if p_fcf <= 18 else ('badge-ambar' if p_fcf <= 24 else 'badge-rojo')}">FFO Yield: {f_num(fcf_yield, 2, '%')}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Múltiplo real REIT sin distorsión por depreciación</span>
            </div>
            """, unsafe_allow_html=True)
        elif per_actual > 0 and per_forward > 0:
            var_per = ((per_forward - per_actual) / per_actual) * 100
            p_class = "badge-verde" if var_per <= 0 else "badge-rojo"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🏷️ Múltiplo de Valoración (PER)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(per_actual, 1, 'x')} <span style="font-size: 1rem; color: #888;">➔</span> {f_num(per_forward, 1, 'x')}</span>
                    <span class="{p_class}">{f_num(var_per, 1, '%', signo_pos=True)}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">PER Actual ➔ PER Futuro estimado</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.metric("PER Actual", f_num(per_actual, 1, 'x') if per_actual > 0 else "N/D")

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
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(metrica_rentabilidad, 2, '%')}</span>
                    <span class="{r_badge}">{r_txt}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Rentabilidad real que genera el capital invertido en el negocio</span>
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
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(revenue_cagr_3y, 2, '%', signo_pos=True)}</span>
                    <span class="{v_badge}">{v_txt}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">CAGR anualizado de ingresos netos (filtro anti trampa de valor)</span>
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
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(price_to_book, 2, 'x')}</span>
                    <span class="{'badge-verde' if 0 < price_to_book <= 1.5 else 'badge-ambar'}">Banca/Seguros</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">En entidades financieras no aplica Deuda/EBITDA</span>
            </div>
            """, unsafe_allow_html=True)
        elif deuda_ebitda < 900:
            if deuda_ebitda <= lim_deuda_optima: b_deb, t_deb = "badge-verde", f"Óptimo (≤ {f_num(lim_deuda_optima, 1, 'x')})"
            elif deuda_ebitda <= lim_deuda_aceptable: b_deb, t_deb = "badge-ambar", f"Aceptable (≤ {f_num(lim_deuda_aceptable, 1, 'x')})"
            else: b_deb, t_deb = "badge-rojo", "Apalancada"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🛡️ Deuda Neta / EBITDA</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(deuda_ebitda, 2, 'x')}</span>
                    <span class="{b_deb}">{t_deb}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Años de EBITDA necesarios para extinguir la deuda neta</span>
            </div>
            """, unsafe_allow_html=True)

    with col_sol2:
        if cobertura_intereses is not None:
            if cobertura_intereses >= 5.0: b_cob, t_cob = "badge-verde", "Holgada (≥ 5,0x)"
            elif cobertura_intereses >= 3.0: b_cob, t_cob = "badge-ambar", "Aceptable (≥ 3,0x)"
            else: b_cob, t_cob = "badge-rojo", "Riesgo (< 3,0x)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⚡ Cobertura de Intereses (EBIT / Intereses)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(cobertura_intereses, 2, 'x')}</span>
                    <span class="{b_cob}">{t_cob}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Veces que el beneficio operativo cubre los intereses de la deuda</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            txt_caja_neta = "Caja Neta (Sin Deuda)" if deuda_neta == 0 else "N/D"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⚡ Cobertura de Intereses</span>
                <div style="font-size: 1.3rem; font-weight: bold; margin-top: 4px;">{txt_caja_neta}</div>
                <span style="font-size: 0.75rem; color: #888;">Sin cargos netos por intereses bancarios</span>
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
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(meses_caja_div, 1)} Meses</span>
                    <span class="{b_caj}">{f_num(meses_caja_div / 12, 1)} Años</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Tiempo que podría pagar el dividendo solo con su liquidez actual ({f_millones(total_cash, sym)})</span>
            </div>
            """, unsafe_allow_html=True)

    with col_caj2:
        if variacion_acciones is not None:
            if variacion_acciones < -0.5: t_acc, c_acc_b, sub_acc = "🟢 Recomprando", "badge-verde", "Destruye acciones y aumenta tu participación"
            elif variacion_acciones <= 2.0: t_acc, c_acc_b, sub_acc = "🟡 Estable", "badge-ambar", "Capital social prácticamente constante"
            else: t_acc, c_acc_b, sub_acc = "🔴 Diluyendo", "badge-rojo", "Emite acciones nuevas (diluye al accionista)"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🔄 Variación de Acciones ({años_analisis} Años)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{f_num(variacion_acciones, 1, '%', signo_pos=True)}</span>
                    <span class="{c_acc_b}">{t_acc}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">{sub_acc}</span>
            </div>
            """, unsafe_allow_html=True)

    col_dgr1, col_dgr2 = st.columns(2)
    with col_dgr1:
        if dgr_5y is not None:
            inf_diff = dgr_5y - 2.5
            b_inf = "badge-verde" if inf_diff >= 2.0 else ("badge-ambar" if inf_diff >= 0 else "badge-rojo")
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">🚀 DGR 5 Años (Crecimiento Medio Plazo)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.6rem; font-weight: bold; color: #faca2b;">{f_num(dgr_5y, 2, '%')}</span>
                    <span class="{b_inf}">{f_num(inf_diff, 1, '%', signo_pos=True)} vs Inflación</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Poder adquisitivo ganado anualmente sobre una inflación media del 2,5%</span>
            </div>
            """, unsafe_allow_html=True)

    with col_dgr2:
        if dgr_1y is not None and dgr_5y is not None:
            if fatiga_dividendo: t_iner, b_iner = "⚠️ Fatiga (Frenando)", "badge-rojo"
            elif inercia_ratio is not None and inercia_ratio >= 1.0: t_iner, b_iner = "⚡ Acelerando", "badge-verde"
            else: t_iner, b_iner = "➡️ Ritmo Estable", "badge-ambar"
            st.markdown(f"""
            <div class="card-dgi">
                <span style="color: #aaa; font-size: 0.85rem;">⏱️ Inercia del Dividendo (Último Año vs Media 5A)</span>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.6rem; font-weight: bold; color: #00d4ff;">{f_num(dgr_1y, 2, '%', signo_pos=True)}</span>
                    <span class="{b_iner}">{t_iner}</span>
                </div>
                <span style="font-size: 0.75rem; color: #888;">Última subida anual comparada con su media quinquenal ({f_num(dgr_5y, 2, '%')})</span>
            </div>
            """, unsafe_allow_html=True)

    # ==========================================
    # GRÁFICOS DE ACCIONES Y DIVIDENDOS CON EXPLICACIONES
    # ==========================================
    st.divider()
    col_sh_div1, col_sh_div2 = st.columns(2)

    with col_sh_div1:
        if not shares_yearly.empty and len(shares_yearly) > 1:
            st.markdown(f"#### 🔄 Historial Anual de Recompras / Dilución ({años_analisis} Años)")
            yoy_shares_total = shares_yearly.pct_change().dropna() * 100
            yoy_shares_analisis = yoy_shares_total.tail(años_analisis)
            text_labels = [f_num(val, 2, '%', signo_pos=True) for val in yoy_shares_analisis.values]
            colores_barras = ['#21c354' if val < -0.1 else '#ff4b4b' if val > 1.0 else '#faca2b' for val in yoy_shares_analisis.values]
            
            fig_shares = go.Figure()
            fig_shares.add_trace(go.Bar(x=yoy_shares_analisis.index.astype(str), y=yoy_shares_analisis.values, marker_color=colores_barras, text=text_labels, textposition='auto'))
            fig_shares.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=280, yaxis_title="Variación Anual (%)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_shares, use_container_width=True)

            ult_sh_yoy = float(yoy_shares_analisis.iloc[-1])
            anios_recompra = int((yoy_shares_analisis < -0.1).sum())
            accion_txt = "recomprando y retirando acciones del mercado" if (variacion_acciones or 0) < 0 else "emitiendo nuevas acciones (diluyendo tu porcentaje)"
            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos en {ticker_symbol}:</strong> En el conjunto del periodo el número total de acciones ha variado un <strong>{f_num(variacion_acciones, 1, '%', signo_pos=True)}</strong> ({f_num(ult_sh_yoy, 2, '%', signo_pos=True)} en el último año), {accion_txt}. Ha reducido su capital social en <strong>{anios_recompra} de los {len(yoy_shares_analisis)} años</strong> mostrados (barras verdes): cuantas menos acciones quedan, a más beneficio y dividendo toca cada acción tuya.
            </div>
            """, unsafe_allow_html=True)

    with col_sh_div2:
        if not dividendos_barras.empty:
            st.markdown(f"#### 💰 Dividendos Anuales Regulares y Subida YoY ({años_analisis} Años)")
            crecimiento_yoy_total = dividendos_barras.pct_change() * 100
            divs_analisis = dividendos_barras.tail(años_analisis)
            crecimiento_yoy_analisis = crecimiento_yoy_total.tail(años_analisis)
            if len(divs_analisis) > 0:
                x_labels_enriquecidos = []
                for year, val in zip(divs_analisis.index, crecimiento_yoy_analisis.values):
                    if pd.isna(val): x_labels_enriquecidos.append(str(year))
                    else:
                        color_pct = '#21c354' if val > 0 else '#ff4b4b'
                        x_labels_enriquecidos.append(f"{year}<br><span style='color:{color_pct}; font-size:11px'>{f_num(val, 1, '%', signo_pos=True)}</span>")
                
                fig_divs = go.Figure()
                fig_divs.add_trace(go.Bar(x=x_labels_enriquecidos, y=divs_analisis.values, name=f"Dividendo ({sym})", marker_color='#00d4ff', yaxis='y1', text=[f_num(val, 2, sym) for val in divs_analisis.values], textposition='auto'))
                fig_divs.add_trace(go.Scatter(x=x_labels_enriquecidos, y=crecimiento_yoy_analisis.values, name="Crecimiento YoY", mode='lines+markers', line=dict(color='#21c354', width=3), marker=dict(size=7), yaxis='y2'))
                fig_divs.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=30), height=280, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title=f"Dividendo ({sym})"), yaxis2=dict(title="Subida (%)", overlaying='y', side='right', showgrid=False), showlegend=False)
                st.plotly_chart(fig_divs, use_container_width=True)

                div_ini_per = float(divs_analisis.iloc[0])
                div_fin_per = float(divs_analisis.iloc[-1])
                mult_div = (div_fin_per / div_ini_per) if div_ini_per > 0 else 1.0
                st.markdown(f"""
                <div class="explicacion-graf">
                    💡 <strong>Qué vemos en {ticker_symbol}:</strong> El dividendo anual por acción ha pasado de <strong>{f_num(div_ini_per, 2, sym)}</strong> en {divs_analisis.index[0]} a <strong>{f_num(div_fin_per, 2, sym)}</strong> hoy (se ha multiplicado por <strong>{f_num(mult_div, 2, 'x')}</strong>). La última variación anual ha sido del <strong>{f_num(dgr_1y, 2, '%', signo_pos=True)}</strong> frente a una media de 5 años del <strong>{f_num(dgr_5y, 2, '%')}</strong>.
                </div>
                """, unsafe_allow_html=True)

    # ==========================================
    # LOS 8 GRÁFICOS FUNDAMENTALES Y DE SOLVENCIA CON EXPLICACIONES
    # ==========================================
    st.divider()
    st.markdown("### 📉 Gráficos de Valoración, Caja y Estructura de Deuda")

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

    # 1. YIELD HISTÓRICO Y 2. DRAWDOWN
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.markdown("#### 📈 1. Evolución del Yield Histórico")
        df_yield_chart = yields_validos.copy()
        fig_yield = go.Figure()
        fig_yield.add_trace(go.Scatter(x=df_yield_chart.index, y=df_yield_chart.values, mode='lines', line=dict(color='#00d4ff', width=2), name='Yield %', showlegend=False))
        fig_yield.add_hline(y=yield_medio, line_dash="dash", line_color="#faca2b")
        fig_yield.add_hline(y=yield_infravalorado, line_dash="dot", line_color="#21c354")
        fig_yield.add_hline(y=yield_sobrevalorado, line_dash="dot", line_color="#ff4b4b")
        fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#21c354', dash='dot'), name=f"Compra (P95): {f_num(yield_infravalorado, 2, '%')}"))
        fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#faca2b', dash='dash'), name=f"Media: {f_num(yield_medio, 2, '%')}"))
        fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[0]], y=[None], mode='lines', line=dict(color='#ff4b4b', dash='dot'), name=f"Venta (P05): {f_num(yield_sobrevalorado, 2, '%')}"))
        fig_yield.add_trace(go.Scatter(x=[df_yield_chart.index[-1]], y=[yield_actual], mode='markers', marker=dict(color='#00d4ff', size=10, symbol='diamond'), name=f"Hoy: {f_num(yield_actual, 2, '%')}"))
        fig_yield.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Rentabilidad (Yield %)"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
        fig_yield.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig_yield, use_container_width=True)

        st.markdown(f"""
        <div class="explicacion-graf">
            💡 <strong>Qué vemos hoy:</strong> La rentabilidad actual (<strong>{f_num(yield_actual, 2, '%')}</strong>) se encuentra en el <strong>percentil {f_num(percentil_yield_actual, 1)}%</strong> de los últimos {años_analisis} años. Cuando la línea azul sube hasta tocar o superar el techo verde punteado (<strong>{f_num(yield_infravalorado, 2, '%')}</strong>), indica máxima infravaloración histórica por dividendo.
        </div>
        """, unsafe_allow_html=True)

    with col_graf2:
        st.markdown("#### 📉 2. Drawdown Histórico (Caída desde Máximos)")
        df_dd = historial_analisis[['Close']].copy()
        df_dd['Max'] = df_dd['Close'].cummax()
        df_dd['Drawdown'] = (df_dd['Close'] - df_dd['Max']) / df_dd['Max'] * 100
        
        dd_actual = float(df_dd['Drawdown'].iloc[-1])
        max_dd_hist = float(df_dd['Drawdown'].min())
        fecha_max_dd = df_dd['Drawdown'].idxmin().strftime('%m/%Y')
        max_precio_periodo = float(df_dd['Max'].iloc[-1])

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df_dd.index, y=df_dd['Drawdown'], fill='tozeroy', mode='lines', line=dict(color='#ff4b4b', width=1.5), fillcolor='rgba(255, 75, 75, 0.2)', name='Drawdown %'))
        fig_dd.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=320, yaxis=dict(title="Caída desde Máximos (%)", ticksuffix="%"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_dd, use_container_width=True)

        st.markdown(f"""
        <div class="explicacion-graf">
            💡 <strong>Qué vemos hoy:</strong> {ticker_symbol} acumula actualmente una caída del <strong>{f_num(dd_actual, 1, '%')}</strong> desde su máximo de {años_analisis} años (<strong>{f_num(max_precio_periodo, 2, sym)}</strong>). Su peor caída registrada en todo este periodo (Max Drawdown) fue del <strong>{f_num(max_dd_hist, 1, '%')}</strong> en <strong>{fecha_max_dd}</strong>.
        </div>
        """, unsafe_allow_html=True)

    # 3. YIELD ON COST HISTÓRICO
    st.markdown("---")
    st.markdown("#### ⏳ 3. Yield on Cost (YoC) Histórico: El Efecto Bola de Nieve")
    if not historial_analisis.empty and forward_dividend > 0:
        df_yoc_hist = historial_analisis[['Close', 'Yield_Diario']].dropna().copy()
        df_yoc_hist['YoC_Hist'] = (forward_dividend / df_yoc_hist['Close']) * 100
        df_yoc_hist.replace([np.inf, -np.inf], np.nan, inplace=True)
        df_yoc_hist = df_yoc_hist.dropna(subset=['YoC_Hist'])
        
        yoc_hace_n_anios = float(df_yoc_hist['YoC_Hist'].iloc[0])
        yield_inicial_entonces = float(df_yoc_hist['Yield_Diario'].iloc[0])
        max_yoc_hist = float(df_yoc_hist['YoC_Hist'].max())

        fig_yoc_hist = go.Figure()
        fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['Yield_Diario'], mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1.5), name='Yield en el día de compra'))
        fig_yoc_hist.add_trace(go.Scatter(x=df_yoc_hist.index, y=df_yoc_hist['YoC_Hist'], mode='lines', line=dict(color='#faca2b', width=2.2), name='Yield on Cost (Hoy)'))
        fig_yoc_hist.add_hline(y=yield_actual, line_dash="dash", line_color="#00d4ff")
        fig_yoc_hist.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=350, yaxis=dict(title="Rentabilidad (%)"), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
        fig_yoc_hist.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig_yoc_hist, use_container_width=True)

        st.markdown(f"""
        <div class="explicacion-graf">
            💡 <strong>Qué vemos hoy:</strong> La línea amarilla muestra qué rentabilidad anual sobre tu inversión inicial estarías cobrando hoy con el dividendo actual (<strong>{f_num(forward_dividend, 2, sym)}</strong>) según la fecha en que hubieras comprado. Un inversor que compró al inicio del gráfico hace {años_analisis} años empezó cobrando un <strong>{f_num(yield_inicial_entonces, 2, '%')}</strong> (línea gris), pero hoy recibe un <strong>Yield on Cost del {f_num(yoc_hace_n_anios, 2, '%')}</strong> (con picos de hasta el <strong>{f_num(max_yoc_hist, 2, '%')}</strong> para quien compró en mínimos).
        </div>
        """, unsafe_allow_html=True)

    # 4. SOSTENIBILIDAD FCF VS DIVIDENDOS Y 5. INGRESOS VS BENEFICIO NETO
    st.markdown("---")
    col_graf3, col_graf4 = st.columns(2)
    with col_graf3:
        st.markdown(f"#### 💵 4. Sostenibilidad: {etiqueta_fcf} vs Dividendos")
        years_sost = sorted(list(set(fcf_s.index) & set(div_s.index)))
        if years_sost:
            x_years = [str(y) for y in years_sost]
            fcf_vals = [float(fcf_s[y]) for y in years_sost]
            div_vals = [float(div_s[y]) for y in years_sost]
            payout_vals = [(div/fcf)*100 if fcf > 0 else 100.0 for fcf, div in zip(fcf_vals, div_vals)]
            
            fig_sost = make_subplots(specs=[[{"secondary_y": True}]])
            fig_sost.add_trace(go.Bar(x=x_years, y=fcf_vals, name=etiqueta_fcf, marker_color='#00d4ff'), secondary_y=False)
            fig_sost.add_trace(go.Bar(x=x_years, y=div_vals, name='Dividendos Pagados', marker_color='#ff9800'), secondary_y=False)
            fig_sost.add_trace(go.Scatter(x=x_years, y=payout_vals, name='Payout Caja %', mode='lines+markers+text', text=[f_num(val, 1, '%') for val in payout_vals], textposition="top center", line=dict(color='#ff4b4b', width=2.2)), secondary_y=True)
            fig_sost.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=310, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            fig_sost.update_yaxes(title_text=f"Importe ({sym})", secondary_y=False)
            fig_sost.update_yaxes(title_text="Payout %", secondary_y=True, showgrid=False, range=[0, max(payout_vals)*1.25 if payout_vals else 100])
            st.plotly_chart(fig_sost, use_container_width=True)

            ult_fcf_v = fcf_vals[-1]
            ult_div_v = div_vals[-1]
            ult_pay_v = payout_vals[-1]
            sobrante_caja = ult_fcf_v - ult_div_v
            txt_sobrante = f"le sobran <strong>{f_millones(sobrante_caja, sym)} libres</strong> tras pagar a los accionistas para amortizar deuda o recomprar acciones" if sobrante_caja >= 0 else f"presenta un <strong>déficit de {f_millones(abs(sobrante_caja), sym)}</strong> (el dividendo superó al flujo libre ese ejercicio)"

            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos en el último cierre ({x_years[-1]}):</strong> Generó <strong>{f_millones(ult_fcf_v, sym)}</strong> de {etiqueta_fcf} (barra azul) y desembolsó <strong>{f_millones(ult_div_v, sym)}</strong> en dividendos (barra naranja), lo que supone un <strong>Payout sobre caja del {f_num(ult_pay_v, 1, '%')}</strong>. Con ello, {txt_sobrante}.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Datos anuales insuficientes para el gráfico de Sostenibilidad.")

    with col_graf4:
        st.markdown("#### 📊 5. Ingresos vs Beneficio Neto y Margen")
        years_rev = sorted(list(set(rev_s.index) & set(net_s.index)))
        if years_rev:
            x_years_rev = [str(y) for y in years_rev]
            rev_vals = [float(rev_s[y]) for y in years_rev]
            net_vals = [float(net_s[y]) for y in years_rev]
            margin_vals = [(n/r)*100 if r > 0 else 0.0 for r, n in zip(rev_vals, net_vals)]
            
            fig_ing = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ing.add_trace(go.Bar(x=x_years_rev, y=rev_vals, name='Ingresos (Ventas)', marker_color='#21c354'), secondary_y=False)
            fig_ing.add_trace(go.Bar(x=x_years_rev, y=net_vals, name='Beneficio Neto', marker_color='#faca2b'), secondary_y=False)
            fig_ing.add_trace(go.Scatter(x=x_years_rev, y=margin_vals, name='Margen Neto %', mode='lines+markers+text', text=[f_num(val, 1, '%') for val in margin_vals], textposition="top center", line=dict(color='#00d4ff', width=2.2)), secondary_y=True)
            fig_ing.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=310, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            fig_ing.update_yaxes(title_text=f"Importe ({sym})", secondary_y=False)
            fig_ing.update_yaxes(title_text="Margen %", secondary_y=True, showgrid=False, range=[min(0, min(margin_vals)*1.1), max(margin_vals)*1.25 if margin_vals else 100])
            st.plotly_chart(fig_ing, use_container_width=True)

            ult_rev_v, ult_net_v, ult_mar_v = rev_vals[-1], net_vals[-1], margin_vals[-1]
            ini_mar_v = margin_vals[0]
            tend_margen = "expandiendo márgenes (mayor poder de fijación de precios)" if ult_mar_v >= ini_mar_v else "comprimiendo márgenes respecto a hace unos años"

            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos en el último cierre ({x_years_rev[-1]}):</strong> Facturó <strong>{f_millones(ult_rev_v, sym)}</strong> y obtuvo un beneficio neto limpio de <strong>{f_millones(ult_net_v, sym)}</strong>. Su <strong>Margen Neto es del {f_num(ult_mar_v, 1, '%')}</strong> (en {x_years_rev[0]} era del {f_num(ini_mar_v, 1, '%')}), lo que indica que por cada 100{sym} vendidos gana <strong>{f_num(ult_mar_v, 2, sym)} limpios</strong>, {tend_margen}.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Datos anuales insuficientes para el gráfico de Ingresos.")

    # 6. EV / FCF Y 7. EV / EBITDA
    st.markdown("---")
    col_graf5, col_graf6 = st.columns(2)
    with col_graf5:
        st.markdown(f"#### ⚖️ 6. Valoración Empresarial: EV / {etiqueta_fcf.split()[0]}")
        years_ev = sorted(list(set(fcf_s.index) & set(shares_s.index) & set(yearly_closes.index)))
        if years_ev:
            x_years_ev = [str(y) for y in years_ev]
            fcf_ev_vals = [float(fcf_s[y]) for y in years_ev]
            ev_vals = [float(yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0)) for y in years_ev]
            ratio_vals = [(ev/fcf) if fcf > 0 else 0.0 for ev, fcf in zip(ev_vals, fcf_ev_vals)]
            media_ev_fcf = float(np.mean([r for r in ratio_vals if r > 0])) if any(r > 0 for r in ratio_vals) else 0.0

            fig_ev = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ev.add_trace(go.Bar(x=x_years_ev, y=ev_vals, name='Enterprise Value (EV)', marker_color='#9c27b0'), secondary_y=False)
            fig_ev.add_trace(go.Bar(x=x_years_ev, y=fcf_ev_vals, name=etiqueta_fcf.split()[0], marker_color='#00d4ff'), secondary_y=False)
            fig_ev.add_trace(go.Scatter(x=x_years_ev, y=ratio_vals, name='Ratio EV/Caja', mode='lines+markers+text', text=[f_num(val, 1, 'x') for val in ratio_vals], textposition="top center", line=dict(color='#21c354', width=2.2)), secondary_y=True)
            fig_ev.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=310, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_ev, use_container_width=True)

            ult_ev_fcf = ratio_vals[-1]
            comp_ev_txt = "más barata que su media reciente" if ult_ev_fcf <= media_ev_fcf else "por encima de su media reciente"
            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos hoy:</strong> Incluyendo su capitalización más su deuda neta (Enterprise Value de <strong>{f_millones(ev_vals[-1], sym)}</strong>), cerró en un múltiplo de <strong>{f_num(ult_ev_fcf, 1, 'x')} EV/{etiqueta_fcf.split()[0]}</strong> frente a su media histórica reciente de <strong>{f_num(media_ev_fcf, 1, 'x')}</strong> ({comp_ev_txt}). Un valor ≤ 18x indica un negocio generador de caja a precio muy atractivo.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Datos insuficientes para el gráfico EV/FCF.")

    with col_graf6:
        st.markdown("#### 🏢 7. Múltiplo Operativo: EV / EBITDA")
        years_ebitda = sorted(list(set(ebitda_s.index) & set(shares_s.index) & set(yearly_closes.index)))
        if years_ebitda:
            x_years_eb = [str(y) for y in years_ebitda]
            ebitda_vals = [float(ebitda_s[y]) for y in years_ebitda]
            ev_eb_vals = [float(yearly_closes[y] * shares_s[y] + debt_s.get(y, 0) - cash_s.get(y, 0)) for y in years_ebitda]
            ratio_eb_vals = [(ev/eb) if eb > 0 else 0.0 for ev, eb in zip(ev_eb_vals, ebitda_vals)]
            media_ev_eb = float(np.mean([r for r in ratio_eb_vals if r > 0])) if any(r > 0 for r in ratio_eb_vals) else 0.0

            fig_ebitda = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ebitda_vals, name='EBITDA', marker_color='#0288d1'), secondary_y=False)
            fig_ebitda.add_trace(go.Bar(x=x_years_eb, y=ev_eb_vals, name='Enterprise Value (EV)', marker_color='#ff9800'), secondary_y=False)
            fig_ebitda.add_trace(go.Scatter(x=x_years_eb, y=ratio_eb_vals, name='Ratio EV/EBITDA', mode='lines+markers+text', text=[f_num(val, 1, 'x') for val in ratio_eb_vals], textposition="top center", line=dict(color='#ff1744', width=2.2)), secondary_y=True)
            fig_ebitda.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=310, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_ebitda, use_container_width=True)

            ult_ev_eb = ratio_eb_vals[-1]
            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos hoy:</strong> Con un EBITDA anual de <strong>{f_millones(ebitda_vals[-1], sym)}</strong>, el múltiplo operativo EV/EBITDA se sitúa en <strong>{f_num(ult_ev_eb, 1, 'x')}</strong> (siendo su media de los últimos años de <strong>{f_num(media_ev_eb, 1, 'x')}</strong>). Generalmente, múltiplos EV/EBITDA por debajo de 12x-14x reflejan valoraciones exigentes muy bajas.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Datos insuficientes para el gráfico EV/EBITDA.")

    # 8. DEUDA NETA VS FCF Y 9. VENCIMIENTOS DE DEUDA (CORTO VS LARGO PLAZO)
    st.markdown("---")
    col_graf7, col_graf8 = st.columns(2)
    with col_graf7:
        st.markdown(f"#### 🛡️ 8. Solvencia Real: Deuda Neta vs {etiqueta_fcf.split()[0]}")
        years_debt = sorted(list(set(fcf_s.index) & set(debt_s.index)))
        if years_debt:
            x_years_d = [str(y) for y in years_debt]
            fcf_d_vals = [float(fcf_s[y]) for y in years_debt]
            net_debt_vals = [float(max(0.0, debt_s.get(y, 0) - cash_s.get(y, 0))) for y in years_debt]
            ratio_d_vals = [(nd/fcf) if fcf > 0 else 0.0 for nd, fcf in zip(net_debt_vals, fcf_d_vals)]

            fig_deuda = make_subplots(specs=[[{"secondary_y": True}]])
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=fcf_d_vals, name=etiqueta_fcf.split()[0], marker_color='#0288d1'), secondary_y=False)
            fig_deuda.add_trace(go.Bar(x=x_years_d, y=net_debt_vals, name='Deuda Neta', marker_color='#ff9800'), secondary_y=False)
            fig_deuda.add_trace(go.Scatter(x=x_years_d, y=ratio_d_vals, name='Años para pagar (Deuda/Caja)', mode='lines+markers+text', text=[f_num(val, 2, 'x') for val in ratio_d_vals], textposition="top center", line=dict(color='#ff1744', width=2.2)), secondary_y=True)
            fig_deuda.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=50), height=310, barmode='group', hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            fig_deuda.update_yaxes(title_text=f"Importe ({sym})", secondary_y=False)
            fig_deuda.update_yaxes(title_text="Años de Caja", secondary_y=True, showgrid=False, range=[0, max(ratio_d_vals)*1.25 if ratio_d_vals else 5])
            st.plotly_chart(fig_deuda, use_container_width=True)

            ult_nd_v = net_debt_vals[-1]
            ult_rat_d = ratio_d_vals[-1]
            st.markdown(f"""
            <div class="explicacion-graf">
                💡 <strong>Qué vemos hoy:</strong> La Deuda Neta es de <strong>{f_millones(ult_nd_v, sym)}</strong> frente a <strong>{f_millones(fcf_d_vals[-1], sym)}</strong> de caja anual generada. Esto significa que la empresa tardaría exactamente <strong>{f_num(ult_rat_d, 2)} años</strong> de su flujo libre en dejar su deuda neta a cero (un nivel inferior a 3,5 años indica gran fortaleza financiera).
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Datos insuficientes para el gráfico de Deuda Neta / FCF.")

    with col_graf8:
        st.markdown("#### ⏳ 9. Liquidez vs Vencimientos de Deuda (Corto y Largo Plazo)")
        if not bs_stmt.empty:
            bs_cols = bs_stmt.index.tolist()
            def get_latest_bs_val(keys):
                for k in keys:
                    if k in bs_cols:
                        s = bs_stmt.loc[k].dropna()
                        # Al estar bs_stmt ordenado cronológicamente de menor a mayor fecha, iloc[-1] es el último año actual
                        if not s.empty: return float(s.iloc[-1]) * fx_rate
                return 0.0

            st_debt = get_latest_bs_val(['Current Debt', 'Current Debt And Capital Lease Obligation', 'Short Long Term Debt', 'Short Term Debt'])
            lt_debt = get_latest_bs_val(['Long Term Debt', 'Long Term Debt And Capital Lease Obligation'])
            caja_actual_bs = get_latest_bs_val(['Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments', 'Cash'])
            if caja_actual_bs == 0: caja_actual_bs = total_cash

            if st_debt > 0 or lt_debt > 0 or caja_actual_bs > 0:
                fig_venc = go.Figure()
                fig_venc.add_trace(go.Bar(y=['Balance Actual'], x=[caja_actual_bs], name='Liquidez (Caja)', orientation='h', marker_color='#21c354', text=f_millones(caja_actual_bs, sym), textposition='inside'))
                fig_venc.add_trace(go.Bar(y=['Balance Actual'], x=[st_debt], name='Deuda Corto (< 1 Año)', orientation='h', marker_color='#ff9800', text=f_millones(st_debt, sym), textposition='inside'))
                fig_venc.add_trace(go.Bar(y=['Balance Actual'], x=[lt_debt], name='Deuda Largo (> 1 Año)', orientation='h', marker_color='#ff4b4b', text=f_millones(lt_debt, sym), textposition='inside'))
                fig_venc.update_layout(barmode='stack', template='plotly_dark', margin=dict(l=0, r=0, t=20, b=70), height=310, hovermode="y unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5), xaxis=dict(showticklabels=False, title=""))
                st.plotly_chart(fig_venc, use_container_width=True)

                cobertura_corto_pct = (caja_actual_bs / st_debt * 100) if st_debt > 0 else 999.0
                estado_liquidez = f"cubre el <strong>{f_num(cobertura_corto_pct, 0, '%')}</strong> de los vencimientos a corto plazo sin necesidad de refinanciarse" if st_debt > 0 else "no tiene deuda con vencimiento inferior a 12 meses"

                st.markdown(f"""
                <div class="explicacion-graf">
                    💡 <strong>Qué vemos en el último balance:</strong> Cuenta con <strong>{f_millones(caja_actual_bs, sym)}</strong> en liquidez inmediata (verde) frente a <strong>{f_millones(st_debt, sym)}</strong> de deuda que vence en menos de 12 meses (naranja) y <strong>{f_millones(lt_debt, sym)}</strong> a largo plazo (roja). Su tesorería {estado_liquidez}.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("No hay desglose de deuda a corto/largo plazo en Yahoo Finance para esta empresa.")


# ==========================================
# INTERFAZ CONECTADA A MEMORIA GLOBAL
# ==========================================
st.title("📊 2. Salud Financiera y Gráficos DGI")

st.session_state.setdefault("ticker_activo", "MKC")
st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("analizar_activo", True)

lista_años = [5, 10, 12, 15, 20]
idx_años = lista_años.index(st.session_state.años_activo) if st.session_state.años_activo in lista_años else 2

col_top1, col_top2, col_top3 = st.columns([1.5, 1.2, 1.5])
with col_top1:
    ticker_input = st.text_input("Ticker activo:", value=st.session_state.ticker_activo).upper().strip()
with col_top2:
    años_analisis = st.selectbox("Periodo Histórico:", lista_años, index=idx_años)
with col_top3:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar Datos de Salud Financiera", use_container_width=True):
        cargar_cotizacion_tiempo_real.clear()
        st.session_state.analizar_activo = True

st.session_state.ticker_activo = ticker_input
st.session_state.años_activo = años_analisis

if ticker_input:
    with st.spinner(f"Generando radiografía financiera y gráficos de {ticker_input}..."):
        try:
            render_salud_financiera(ticker_input, años_analisis)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
