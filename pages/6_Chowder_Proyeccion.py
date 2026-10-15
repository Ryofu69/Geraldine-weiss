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
# FORMATEO A LA ESPAÑOLA (1.234,56)
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
# CACHÉ COMPARTIDA CON RESPALDO
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

# ==========================================
# FUNCIÓN PRINCIPAL PESTAÑA 3: CHOWDER Y YOC 15A
# ==========================================
def render_chowder_proyeccion(ticker_symbol, años_analisis, impuesto_pct, aplicar_merma_origen, capital_simulado, activar_drip):
    info, dividendos_raw, inc_stmt, bs_stmt, cf_stmt, shares_hist, fx_rate, curr_fin = cargar_fundamentales_pesados(ticker_symbol)
    historial_raw, precio_vivo, shares_fast, mcap_fast = cargar_cotizacion_tiempo_real(ticker_symbol)

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
.badge-verde { background: rgba(33, 195, 84, 0.2); color: #21c354; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; white-space: nowrap; }
.badge-rojo { background: rgba(255, 75, 75, 0.2); color: #ff4b4b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; white-space: nowrap; }
.badge-ambar { background: rgba(250, 202, 43, 0.2); color: #faca2b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; white-space: nowrap; }
.badge-azul { background: rgba(0, 212, 255, 0.2); color: #00d4ff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.82rem; white-space: nowrap; }
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

    sector_en = info.get('sector', 'General')
    industry_en = info.get('industry', 'General')
    pais = info.get('country', 'Desconocido')
    nombre_empresa = info.get('shortName', ticker_symbol)
    sector_final = TRADUCCION.get(sector_en, sector_en)

    es_reit_puro = 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
    es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()
    es_telecom = 'telecom' in industry_en.lower()

    merma_origen_pct = MERMA_ORIGEN_PAIS.get(pais, 0.0) if aplicar_merma_origen else 0.0
    net_mult = (1.0 - (impuesto_pct / 100.0)) * (1.0 - (merma_origen_pct / 100.0))

    # ==========================================
    # MOTOR ORIGINAL DE DIVIDENDOS SINCRONIZADO CON PESTAÑA 1 Y 2
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

    forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
    if es_peniques_uk and forward_dividend > (precio_actual * 0.25):
        forward_dividend /= 100.0
    if forward_dividend == 0 and not dividendos.empty:
        ultimo_año_completo = divs_por_año.iloc[-2] if len(divs_por_año) > 1 else 0.0
        forward_dividend = max(float(dividendos.iloc[-1]) * pagos_por_año, float(ultimo_año_completo))

    historial_analisis['Year'] = historial_analisis.index.year
    historial_analisis['Div_Anual'] = historial_analisis['Year'].map(divs_por_año)
    historial_analisis.loc[historial_analisis['Year'] == año_actual, 'Div_Anual'] = forward_dividend
    historial_analisis['Div_Anual'] = historial_analisis['Div_Anual'].bfill().ffill()
    historial_analisis['Yield_Diario'] = (historial_analisis['Div_Anual'] / historial_analisis['Close']) * 100
    historial_analisis.replace([np.inf, -np.inf], np.nan, inplace=True)

    yields_validos = historial_analisis['Yield_Diario'].dropna()
    yields_validos = yields_validos[yields_validos > 0]
    yield_infravalorado = float(yields_validos.quantile(0.95))
    yield_medio = float(yields_validos.mean())
    yield_actual = (forward_dividend / precio_actual) * 100 if precio_actual > 0 else 0.0

    precio_compra_weiss = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0.0
    precio_justo_weiss = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0.0

    dividendos_barras = divs_por_año.copy()
    if año_actual in dividendos_barras.index:
        dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)
    else:
        dividendos_barras.loc[año_actual] = forward_dividend

    dgr_1y, dgr_3y, dgr_5y, dgr_periodo = None, None, None, None
    if len(dividendos_barras) >= 2 and dividendos_barras.iloc[-2] > 0:
        dgr_1y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-2]) - 1) * 100
    if len(dividendos_barras) >= 4 and dividendos_barras.iloc[-4] > 0:
        dgr_3y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-4]) ** (1/3) - 1) * 100
    if len(dividendos_barras) >= 6 and dividendos_barras.iloc[-6] > 0:
        dgr_5y = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-6]) ** (1/5) - 1) * 100
    if len(dividendos_barras) >= (años_analisis + 1) and dividendos_barras.iloc[-(años_analisis + 1)] > 0:
        dgr_periodo = ((dividendos_barras.iloc[-1] / dividendos_barras.iloc[-(años_analisis + 1)]) ** (1/años_analisis) - 1) * 100

    # ==========================================
    # SECCIÓN 1: REGLA DE CHOWDER DUAL (CLÁSICA 5A vs ESTRICTA)
    # ==========================================
    st.header(f"🥣 Regla de Chowder y Proyección a 15 Años — {nombre_empresa} ({ticker_symbol})")
    st.caption(f"Sector: {sector_final} | Cotización: {f_num(precio_actual, 2, sym)} | Dividendo Anual: {f_num(forward_dividend, 2, sym)} ({f_num(yield_actual, 2, '%')} Bruto / {f_num(yield_actual * net_mult, 2, '%')} Neto)")

    if (es_utility_pura or es_telecom or es_reit_puro) and yield_actual > 4.0:
        chowder_target = 8.0
        criterio_txt = "Sector Regulado / REIT / Utility con Yield > 4,0% (Meta oficial ≥ 8,0 pts)"
    elif yield_actual >= 3.0:
        chowder_target = 12.0
        criterio_txt = "Yield Inicial ≥ 3,0% (Meta oficial estándar ≥ 12,0 pts)"
    else:
        chowder_target = 15.0
        criterio_txt = "Yield Inicial Bajo < 3,0% (Meta exigente ≥ 15,0 pts por alto crecimiento)"

    # Tasa conservadora realista
    tasas_disp = [t for t in [dgr_5y, dgr_periodo, dgr_3y] if t is not None]
    dgr_conservador = min(tasas_disp) if tasas_disp else (dgr_1y if dgr_1y is not None else 0.0)
    if dgr_1y is not None and dgr_1y < (dgr_conservador * 0.6):
        dgr_conservador = (dgr_conservador + max(0.0, dgr_1y)) / 2.0

    chowder_5y = (yield_actual + dgr_5y) if dgr_5y is not None else None
    # En Chowder Estricto limitamos el Yield computable al 6,5% para evitar que un Yield del 14% sin crecimiento apruebe solo
    yield_topado_estricto = min(yield_actual, 6.5)
    chowder_cons = (yield_topado_estricto + dgr_conservador) if tasas_disp else None

    precio_obj_chowder_5y, yield_req_5y = None, None
    if dgr_5y is not None:
        yield_req_5y = chowder_target - dgr_5y
        if yield_req_5y > 0:
            precio_obj_chowder_5y = (forward_dividend / yield_req_5y) * 100

    col_ch1, col_ch2, col_ch3 = st.columns(3)

    with col_ch1:
        if chowder_5y is not None:
            pct_prog_5y = min(100.0, max(0.0, (chowder_5y / chowder_target) * 100))
            diff_5y = chowder_5y - chowder_target
            pass_5y = chowder_5y >= chowder_target
            b_cls = "badge-verde" if pass_5y else ("badge-ambar" if diff_5y >= -1.5 else "badge-rojo")
            b_txt = f"🟢 Aprobada ({f_num(diff_5y, 1, ' pts', signo_pos=True)})" if pass_5y else f"🔴 {f_num(diff_5y, 1, ' pts', signo_pos=True)}"
            c_bar = "#21c354" if pass_5y else ("#faca2b" if diff_5y >= -1.5 else "#ff4b4b")

            st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="color: #aaa; font-size: 0.85rem;">🥣 Chowder Clásico (DGR 5A)</span>
<span class="{b_cls}">{b_txt}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
<span style="font-size: 1.05rem; color: #ccc;">
<strong style="color:#00d4ff;">{f_num(yield_actual, 2, '%')}</strong> + 
<strong style="color:#faca2b;">{f_num(dgr_5y, 2, '%')}</strong> = 
<strong style="font-size: 1.5rem; color: white;"> {f_num(chowder_5y, 1)}</strong>
</span>
<span style="font-size: 0.85rem; color: #888;">Meta: <strong>≥ {f_num(chowder_target, 0)}</strong></span>
</div>
<div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 6px;">
<div style="background: {c_bar}; width: {pct_prog_5y:.1f}%; height: 100%;"></div>
</div>
<span style="font-size: 0.75rem; color: #888;">{criterio_txt}</span>
</div>
""", unsafe_allow_html=True)
        else:
            st.info("Sin historial de 5 años completo para Chowder Clásico.")

    with col_ch2:
        if chowder_cons is not None:
            pct_prog_c = min(100.0, max(0.0, (chowder_cons / chowder_target) * 100))
            diff_c = chowder_cons - chowder_target
            pass_c = (chowder_cons >= chowder_target) and (dgr_conservador >= 2.0)
            b_cls_c = "badge-verde" if pass_c else ("badge-ambar" if diff_c >= -1.5 and dgr_conservador >= 1.5 else "badge-rojo")
            b_txt_c = f"🟢 Aprobada ({f_num(diff_c, 1, ' pts', signo_pos=True)})" if pass_c else f"🔴 {f_num(diff_c, 1, ' pts', signo_pos=True)}"
            c_bar_c = "#21c354" if pass_c else ("#faca2b" if diff_c >= -1.5 else "#ff4b4b")

            nota_tope_y = f" (Yield topado al 6,5%)" if yield_actual > 6.5 else ""
            st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="color: #aaa; font-size: 0.85rem;">🛡️ Chowder Estricto (Conservador)</span>
<span class="{b_cls_c}">{b_txt_c}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
<span style="font-size: 1.05rem; color: #ccc;">
<strong style="color:#00d4ff;">{f_num(yield_topado_estricto, 2, '%')}</strong> + 
<strong style="color:#b388ff;">{f_num(dgr_conservador, 2, '%')}</strong> = 
<strong style="font-size: 1.5rem; color: white;"> {f_num(chowder_cons, 1)}</strong>
</span>
<span style="font-size: 0.85rem; color: #888;">Meta: <strong>≥ {f_num(chowder_target, 0)}</strong></span>
</div>
<div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-bottom: 6px;">
<div style="background: {c_bar_c}; width: {pct_prog_c:.1f}%; height: 100%;"></div>
</div>
<span style="font-size: 0.75rem; color: #888;">Usa el menor DGR entre 5A ({f_num(dgr_5y, 1, '%')}), {años_analisis}A ({f_num(dgr_periodo, 1, '%')}) e inercia{nota_tope_y}.</span>
</div>
""", unsafe_allow_html=True)

    with col_ch3:
        if chowder_5y is not None:
            if chowder_5y >= chowder_target or (yield_req_5y is not None and yield_req_5y <= 0):
                st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<span style="color: #aaa; font-size: 0.85rem;">🎯 Precio Máximo de Entrada por Chowder</span>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px; margin-bottom: 8px;">
<span style="font-size: 1.45rem; font-weight: bold; color: #21c354;">Ya Cumple en {f_num(precio_actual, 2, sym)}</span>
<span class="badge-verde">En Zona</span>
</div>
<span style="font-size: 0.75rem; color: #888;">Su crecimiento ya compensa el Yield actual. Suelo Weiss: <strong>{f_num(precio_compra_weiss, 2, sym)}</strong>.</span>
</div>
""", unsafe_allow_html=True)
            else:
                dist_chow = ((precio_actual - precio_obj_chowder_5y) / precio_obj_chowder_5y) * 100
                st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="color: #aaa; font-size: 0.85rem;">🎯 Precio Objetivo Chowder</span>
<span class="badge-rojo">{f_num(dist_chow, 1, '%', signo_pos=True)} sobre meta</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
<span style="font-size: 1.5rem; font-weight: bold; color: #e040fb;">{f_num(precio_obj_chowder_5y, 2, sym)}</span>
<span style="font-size: 0.85rem; color: #888;">Exige Yield de {f_num(yield_req_5y, 2, '%')}</span>
</div>
<span style="font-size: 0.75rem; color: #888;">Precio necesario para que el Yield inicial sume {f_num(chowder_target, 0)} pts junto al DGR 5A.</span>
</div>
""", unsafe_allow_html=True)

    # --- GRÁFICO 1 DE LA PÁGINA 3: COMPARATIVA DE NIVELES DE ENTRADA (WEISS VS CHOWDER) ---
    st.markdown("#### ⚖️ Mapa de Precios de Entrada: Cotización vs. Suelo Weiss vs. Precio Chowder")
    niveles_nombres = ["Cotización en Vivo", "Suelo Compra Weiss (P95)", "Precio Justo Weiss (Media)"]
    niveles_valores = [precio_actual, precio_compra_weiss, precio_justo_weiss]
    niveles_colores = ["#00d4ff", "#21c354", "#faca2b"]

    if precio_obj_chowder_5y is not None and 0 < precio_obj_chowder_5y < (precio_justo_weiss * 2.2):
        niveles_nombres.insert(2, "Precio Objetivo Chowder")
        niveles_valores.insert(2, precio_obj_chowder_5y)
        niveles_colores.insert(2, "#e040fb")

    fig_niv = go.Figure()
    fig_niv.add_trace(go.Bar(
        y=niveles_nombres, x=niveles_valores, orientation='h',
        marker_color=niveles_colores,
        text=[f_num(v, 2, sym) for v in niveles_valores],
        textposition='auto'
    ))
    fig_niv.update_layout(
        template='plotly_dark', margin=dict(l=0, r=20, t=10, b=10), height=230,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(title=f"Precio por Acción ({sym})")
    )
    st.plotly_chart(fig_niv, use_container_width=True)

    suelo_maestro = min(precio_compra_weiss, precio_obj_chowder_5y) if (precio_obj_chowder_5y is not None and precio_obj_chowder_5y > 0) else precio_compra_weiss
    criterio_mas_estricto = "la Regla de Chowder" if (precio_obj_chowder_5y is not None and 0 < precio_obj_chowder_5y < precio_compra_weiss) else "el Suelo Histórico de Geraldine Weiss"
    st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
💡 <strong>Lectura de Niveles en {ticker_symbol}:</strong> Compara de un vistazo cuánto te pide cada estrategia para entrar. Actualmente el filtro más exigente es <strong>{criterio_mas_estricto}</strong>, situando el suelo maestro de máxima exigencia en <strong>{f_num(suelo_maestro, 2, sym)}</strong> frente a los <strong>{f_num(precio_actual, 2, sym)}</strong> a los que cotiza hoy.
</div>
""", unsafe_allow_html=True)

    # ==========================================
    # SECCIÓN 2: SIMULADOR DE PROYECCIÓN A 15 AÑOS (CON Y SIN DRIP)
    # ==========================================
    st.divider()
    st.subheader(f"🔮 Proyección de Rentabilidad sobre Coste (YoC) y Renta a 15 Años (Orden de {f_num(capital_simulado, 0, sym)})")

    dgr_proyeccion = max(0.0, min(14.0, dgr_conservador))
    años_proyeccion = list(range(1, 16))
    acciones_iniciales = (capital_simulado / precio_actual) if precio_actual > 0 else 0.0

    div_por_accion_bruto = []
    renta_anual_neta_sin_drip = []
    renta_anual_neta_con_drip = []
    yoc_neto_sin_drip = []
    yoc_neto_con_drip = []
    acciones_acum_drip = []
    poder_adquisitivo_real_hoy = []

    acc_drip = acciones_iniciales
    inflacion_anual = 0.025  # 2,5% inflación media descontada

    for año in años_proyeccion:
        factor_crec = (1.0 + (dgr_proyeccion / 100.0)) ** año
        div_acc_año = forward_dividend * factor_crec
        precio_acc_est_año = precio_actual * factor_crec

        cobro_neto_sin = acciones_iniciales * div_acc_año * net_mult
        yoc_n_sin = (cobro_neto_sin / capital_simulado) * 100 if capital_simulado > 0 else 0.0

        cobro_neto_con = acc_drip * div_acc_año * net_mult
        yoc_n_con = (cobro_neto_con / capital_simulado) * 100 if capital_simulado > 0 else 0.0
        if precio_acc_est_año > 0:
            acc_drip += (cobro_neto_con / precio_acc_est_año)

        renta_elegida = cobro_neto_con if activar_drip else cobro_neto_sin
        renta_real_hoy = renta_elegida / ((1.0 + inflacion_anual) ** año)

        div_por_accion_bruto.append(div_acc_año)
        renta_anual_neta_sin_drip.append(cobro_neto_sin)
        renta_anual_neta_con_drip.append(cobro_neto_con)
        yoc_neto_sin_drip.append(yoc_n_sin)
        yoc_neto_con_drip.append(yoc_n_con)
        acciones_acum_drip.append(acc_drip)
        poder_adquisitivo_real_hoy.append(renta_real_hoy)

    serie_renta_activa = renta_anual_neta_con_drip if activar_drip else renta_anual_neta_sin_drip
    serie_yoc_activa = yoc_neto_con_drip if activar_drip else yoc_neto_sin_drip

    total_dividendos_15a = float(np.sum(serie_renta_activa))
    pct_payback_15a = (total_dividendos_15a / capital_simulado) * 100 if capital_simulado > 0 else 0.0

    año_cruce_7pct = "Más de 15 años"
    for a, yoc_v in zip(años_proyeccion, serie_yoc_activa):
        if yoc_v >= 7.0:
            año_cruce_7pct = f"Año {a} ({año_actual + a})"
            break

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<span style="color: #aaa; font-size: 0.85rem;">💵 Renta Neta Año 1 vs. Año 15</span>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
<span style="font-size: 1.45rem; font-weight: bold;">{f_num(serie_renta_activa[0], 2, sym)} <span style="font-size: 1rem; color: #888;">➔</span> <span style="color:#21c354;">{f_num(serie_renta_activa[-1], 2, sym)}/año</span></span>
</div>
<span style="font-size: 0.75rem; color: #888;">Equivalente a <strong>{f_num(poder_adquisitivo_real_hoy[-1], 2, sym)} de hoy</strong> descontando un 2,5% de inflación anual</span>
</div>
""", unsafe_allow_html=True)

    with col_h2:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<span style="color: #aaa; font-size: 0.85rem;">💰 Capital Recuperado en Dividendos (15A)</span>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
<span style="font-size: 1.45rem; font-weight: bold; color: #00d4ff;">{f_num(total_dividendos_15a, 2, sym)}</span>
<span class="{'badge-verde' if pct_payback_15a >= 50 else 'badge-ambar'}">{f_num(pct_payback_15a, 1, '%')} de tu orden</span>
</div>
<span style="font-size: 0.75rem; color: #888;">Efectivo neto total cobrado en 15 años sobre tus {f_num(capital_simulado, 0, sym)} iniciales</span>
</div>
""", unsafe_allow_html=True)

    with col_h3:
        st.markdown(f"""
<div class="card-dgi notranslate" translate="no">
<span style="color: #aaa; font-size: 0.85rem;">🚀 Meta YoC Neto ≥ 7,0%</span>
<div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
<span style="font-size: 1.45rem; font-weight: bold; color: #faca2b;">{año_cruce_7pct}</span>
<span class="badge-azul">YoC 15A: {f_num(serie_yoc_activa[-1], 2, '%')}</span>
</div>
<span style="font-size: 0.75rem; color: #888;">{'Con reinversión DRIP activa' if activar_drip else 'Sin reinvertir dividendos'} a un ritmo del {f_num(dgr_proyeccion, 2, '%')}/año</span>
</div>
""", unsafe_allow_html=True)

    # --- GRÁFICO 2 DE LA PÁGINA 3: PROYECCIÓN A 15 AÑOS ---
    x_labels_yoc = [f"{año_actual + a}<br><span style='color:#faca2b; font-size:11px'>{f_num(yoc_n, 1, '%')}</span>" for a, yoc_n in zip(años_proyeccion, serie_yoc_activa)]

    fig_yoc_p = make_subplots(specs=[[{"secondary_y": True}]])
    fig_yoc_p.add_trace(
        go.Bar(
            x=x_labels_yoc, y=serie_renta_activa,
            name=f"Renta Neta Anual ({sym})",
            marker_color='#00d4ff',
            text=[f_num(val, 1, sym) for val in serie_renta_activa],
            textposition='auto'
        ),
        secondary_y=False
    )
    fig_yoc_p.add_trace(
        go.Scatter(
            x=x_labels_yoc, y=yoc_neto_sin_drip,
            name="YoC Neto Sin DRIP (%)",
            mode='lines+markers',
            line=dict(color='#21c354', width=2.5, dash='dot' if activar_drip else 'solid'),
            marker=dict(size=7)
        ),
        secondary_y=True
    )
    if activar_drip:
        fig_yoc_p.add_trace(
            go.Scatter(
                x=x_labels_yoc, y=yoc_neto_con_drip,
                name="YoC Neto Con DRIP (%)",
                mode='lines+markers',
                line=dict(color='#faca2b', width=3),
                marker=dict(size=8)
            ),
            secondary_y=True
        )

    fig_yoc_p.update_layout(
        template='plotly_dark', margin=dict(l=0, r=0, t=20, b=40), height=390,
        hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    )
    fig_yoc_p.update_yaxes(title_text=f"Renta Neta Cobrada ({sym})", secondary_y=False)
    fig_yoc_p.update_yaxes(title_text="Yield on Cost Neto (%)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig_yoc_p, use_container_width=True)

    modo_txt = f"reinvertidos automáticamente (pasando de <strong>{f_num(acciones_iniciales, 2)}</strong> a <strong>{f_num(acciones_acum_drip[-1], 2)} títulos</strong>)" if activar_drip else f"cobrados en cuenta sin reinvertir (manteniendo tus <strong>{f_num(acciones_iniciales, 2)} títulos</strong> iniciales)"
    st.markdown(f"""
<div class="explicacion-graf notranslate" translate="no">
💡 <strong>Qué vemos en esta proyección de {ticker_symbol}:</strong> Invirtiendo hoy <strong>{f_num(capital_simulado, 0, sym)}</strong> con los dividendos {modo_txt} y creciendo al <strong>{f_num(dgr_proyeccion, 2, '%')} anual</strong>, tu rentabilidad neta sobre el dinero que pusiste de tu bolsillo pasará del <strong>{f_num(yield_actual * net_mult, 2, '%')}</strong> actual al <strong>{f_num(serie_yoc_activa[-1], 2, '%')} neto anual</strong> en {año_actual + 15}. En total habrás cobrado <strong>{f_num(total_dividendos_15a, 2, sym)} limpios</strong> de impuestos (recuperando el <strong>{f_num(pct_payback_15a, 1, '%')}</strong> de tu inversión inicial solo en dividendos).
</div>
""", unsafe_allow_html=True)

    # --- TABLA RESUMEN DE HITOS (AÑOS 1, 5, 10 Y 15) ---
    st.markdown("#### 📅 Tabla de Hitos de tu Orden (Años 1, 5, 10 y 15)")
    hitos_idx = [0, 4, 9, 14]
    filas_tabla = []
    for idx in hitos_idx:
        a_num = años_proyeccion[idx]
        acum_hasta_fecha = float(np.sum(serie_renta_activa[:idx + 1]))
        filas_tabla.append({
            "Horizonte": f"Año {a_num} ({año_actual + a_num})",
            f"Div./Acción Bruto ({sym})": f_num(div_por_accion_bruto[idx], 2, sym),
            "Títulos Totales": f_num(acciones_acum_drip[idx] if activar_drip else acciones_iniciales, 2),
            f"Renta Neta Anual ({sym})": f_num(serie_renta_activa[idx], 2, sym),
            f"Poder Adquisitivo Hoy ({sym})": f_num(poder_adquisitivo_real_hoy[idx], 2, sym),
            "YoC Neto (%)": f_num(serie_yoc_activa[idx], 2, "%"),
            f"Dividendos Acumulados ({sym})": f"{f_num(acum_hasta_fecha, 2, sym)} ({f_num((acum_hasta_fecha/capital_simulado)*100, 1, '%')})"
        })
    st.dataframe(pd.DataFrame(filas_tabla), use_container_width=True, hide_index=True)


# ==========================================
# INTERFAZ CONECTADA A MEMORIA GLOBAL
# ==========================================
st.title("🥣 3. Regla de Chowder y Proyección YoC 15A")

st.session_state.setdefault("ticker_activo", "MKC")
st.session_state.setdefault("años_activo", 12)
st.session_state.setdefault("impuesto_activo", 19.0)
st.session_state.setdefault("capital_activo", 500.0)
st.session_state.setdefault("merma_activa", True)

lista_años = [5, 10, 12, 15, 20]
idx_años = lista_años.index(st.session_state.años_activo) if st.session_state.años_activo in lista_años else 2

col_c1, col_c2, col_c3, col_c4 = st.columns([1.2, 1, 1, 1.3])
with col_c1:
    ticker_input = st.text_input("Ticker activo:", value=st.session_state.ticker_activo).upper().strip()
with col_c2:
    años_analisis = st.selectbox("Periodo Histórico:", lista_años, index=idx_años)
with col_c3:
    impuesto = st.number_input("Retención IRPF (%)", value=float(st.session_state.impuesto_activo), step=1.0)
with col_c4:
    capital_simulado = st.number_input("Capital Simulado Orden:", value=float(st.session_state.capital_activo), step=50.0)

col_chk1, col_chk2 = st.columns(2)
with col_chk1:
    aplicar_merma = st.checkbox(
        "Aplicar merma fiscal en origen no recuperable (>15% Suiza, Alemania, Francia, Dinamarca, Irlanda)",
        value=st.session_state.merma_activa
    )
with col_chk2:
    activar_drip = st.checkbox(
        "❄️ Simular Reinversión Automática de Dividendos Netos (Efecto Bola de Nieve / DRIP)",
        value=True
    )

st.session_state.ticker_activo = ticker_input
st.session_state.años_activo = años_analisis
st.session_state.impuesto_activo = impuesto
st.session_state.capital_activo = capital_simulado
st.session_state.merma_activa = aplicar_merma

if ticker_input:
    with st.spinner(f"Calculando Regla de Chowder y proyección a 15 años de {ticker_input}..."):
        try:
            render_chowder_proyeccion(ticker_input, años_analisis, impuesto, aplicar_merma, capital_simulado, activar_drip)
        except Exception as e:
            st.error(f"Se ha producido un error al procesar los datos: {e}")
