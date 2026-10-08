import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import plotly.graph_objects as go
import io

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Control de Cartera DGI", page_icon="💼", layout="wide")

# ==========================================
# UTILIDADES DE LIMPIEZA Y FORMATEO ESPAÑOL
# ==========================================
def limpiar_numero_europeo(val):
    if pd.isna(val) or val is None:
        return 0.0
    val_str = str(val).strip().replace('€', '').replace('$', '').replace('£', '').replace(' ', '')
    if '.' in val_str and ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def fmt_es(val, dec=2, signo=False, sufijo=""):
    """Convierte números a formato español: 1.234,56 € o +5,20%"""
    if pd.isna(val) or val is None:
        return f"0,{dec * '0'}{sufijo}"
    try:
        val = float(val)
    except (ValueError, TypeError):
        return str(val)
    s = f"{val:{'+' if signo else ''},.{dec}f}"
    s_es = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s_es}{sufijo}"

def fmt_acciones(acc):
    try:
        acc_fl = float(acc)
        if acc_fl.is_integer():
            return f"{int(acc_fl)}"
        return fmt_es(acc_fl, 4).rstrip('0').rstrip(',')
    except Exception:
        return str(acc)

# ==========================================
# INYECCIÓN CSS PARA DISEÑO VISUAL
# ==========================================
st.markdown("""
<style>
.metric-box {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 12px;
}
.metric-title {
    color: #9e9e9e;
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.metric-val {
    font-size: 1.65rem;
    font-weight: 700;
    margin-top: 4px;
    margin-bottom: 2px;
}
.metric-sub {
    font-size: 0.85rem;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# ENTRADA DE DATOS (100% PRIVADA Y EN MEMORIA)
# ==========================================
st.title("💼 Panel de Rendimiento y Análisis DGI")
st.markdown("> *Privacidad garantizada: Procesamiento 100% en memoria temporal de sesión. No se guarda ningún dato en servidor ni en GitHub.*")

col_c1, col_c2 = st.columns(2)
with col_c1:
    metodo_carga = st.radio("¿Cómo quieres cargar tu cartera?", ["📝 Pegar Texto", "📂 Subir Archivo"], horizontal=True)
with col_c2:
    impuesto_cart = st.number_input("Retención media de dividendos (%)", value=19.0, step=0.5, key="imp_cart_p3")

net_factor = 1.0 - (impuesto_cart / 100.0)
df_ops = None

if metodo_carga == "📂 Subir Archivo":
    archivo_subido = st.file_uploader("Sube tu historial de operaciones (CSV o Excel)", type=["csv", "xlsx"])
    if archivo_subido is not None:
        try:
            if archivo_subido.name.endswith('.xlsx'):
                df_ops = pd.read_excel(archivo_subido, dtype=str)
            else:
                df_ops = pd.read_csv(archivo_subido, sep=None, engine='python', dtype=str)
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")
else:
    st.info("Pega directamente tu historial. Encabezados: Fecha, Ticker, Operacion, Acciones, Precio (admite comas europeas y tabuladores de Excel).")
    texto_csv = st.text_area(
        "Pega aquí tus transacciones:",
        value="",
        height=140,
        placeholder="Fecha,Ticker,Operacion,Acciones,Precio\n01/01/2024,TICKER,Compra,10,25.50"
    )
    if texto_csv and texto_csv.strip():
        try:
            df_ops = pd.read_csv(io.StringIO(texto_csv.strip()), sep=None, engine='python', dtype=str)
        except Exception as e:
            st.error(f"Error al leer el texto pegado: {e}")

# ==========================================
# MOTOR DE PROCESAMIENTO
# ==========================================
if df_ops is not None and not df_ops.empty:
    try:
        col_map = {}
        for col in df_ops.columns:
            c_clean = col.strip().lower()
            if 'fech' in c_clean: col_map[col] = 'Fecha'
            elif 'tick' in c_clean or 'empresa' in c_clean: col_map[col] = 'Ticker'
            elif 'oper' in c_clean or 'tipo' in c_clean: col_map[col] = 'Operacion'
            elif 'acc' in c_clean or 'cant' in c_clean or 'titul' in c_clean: col_map[col] = 'Acciones'
            elif 'prec' in c_clean or 'cost' in c_clean: col_map[col] = 'Precio'
        df_ops = df_ops.rename(columns=col_map)

        columnas_requeridas = ['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio']
        if not all(col in df_ops.columns for col in columnas_requeridas):
            st.error(f"❌ Error de formato. Faltan columnas: {', '.join(columnas_requeridas)}")
        else:
            df_ops['Acciones'] = df_ops['Acciones'].apply(limpiar_numero_europeo)
            df_ops['Precio'] = df_ops['Precio'].apply(limpiar_numero_europeo)
            df_ops['Fecha'] = pd.to_datetime(df_ops['Fecha'], errors='coerce', dayfirst=True)
            df_ops['Ticker'] = df_ops['Ticker'].astype(str).str.strip().str.upper()
            df_ops['Operacion'] = df_ops['Operacion'].astype(str).str.strip().str.capitalize()

            df_ops = df_ops.dropna(subset=['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio'])
            df_ops = df_ops[df_ops['Acciones'] > 0]
            df_ops = df_ops.sort_values('Fecha')

            if df_ops.empty:
                st.warning("No hay transacciones válidas registradas.")
            else:
                df_ops_global = df_ops.copy()
                tickers_global = sorted(df_ops_global['Ticker'].unique().tolist())

                años_unicos = sorted(df_ops['Fecha'].dt.year.dropna().unique())
                opciones_año = ["Todo el Historial"] + [str(int(a)) for a in años_unicos]
                opciones_ticker = ["Todas las Empresas"] + tickers_global

                st.divider()
                st.markdown("#### 🎯 Filtros Analíticos de Cartera")
                col_f1, col_f2 = st.columns(2)
                with col_f1: año_filtro = st.selectbox("📅 Selecciona Año de Compra (Modo Añada):", opciones_año)
                with col_f2: ticker_filtro = st.selectbox("🏢 Selecciona Empresa a Inspeccionar:", opciones_ticker)

                if año_filtro != "Todo el Historial":
                    df_ops = df_ops[(df_ops['Fecha'].dt.year == int(año_filtro)) & (df_ops['Operacion'] == 'Compra')]
                if ticker_filtro != "Todas las Empresas":
                    df_ops = df_ops[df_ops['Ticker'] == ticker_filtro]

                if df_ops.empty:
                    st.warning("No hay operaciones válidas con los filtros seleccionados.")
                else:
                    min_date_global = df_ops_global['Fecha'].min()
                    tickers_unicos = df_ops['Ticker'].unique().tolist()

                    dict_historicos = {}
                    dict_dividendos = {}
                    dict_forward_div = {}
                    dict_dgr5 = {}

                    with st.spinner("Descargando fundamentales, dividendos y tipos de cambio..."):
                        for t in tickers_global:
                            try:
                                tk = yf.Ticker(t)
                                hist = tk.history(start=min_date_global, auto_adjust=False)
                                if not hist.empty:
                                    hist.index = hist.index.tz_localize(None).normalize()
                                    hist = hist[~hist.index.duplicated(keep='last')]

                                    if 'Dividends' in hist.columns and hist['Dividends'].sum() > 0:
                                        divs_finales = hist['Dividends']
                                    else:
                                        divs_reales = tk.dividends
                                        if not divs_reales.empty:
                                            divs_reales.index = divs_reales.index.tz_localize(None).normalize()
                                            divs_reales = divs_reales[~divs_reales.index.duplicated(keep='last')]
                                            divs_finales = divs_reales[divs_reales.index >= min_date_global]
                                        else:
                                            divs_finales = pd.Series(dtype=float)

                                    es_uk = tk.info.get('currency') == 'GBp'
                                    if es_uk:
                                        hist['Close'] = hist['Close'] / 100.0
                                        if not divs_finales.empty:
                                            divs_finales = divs_finales / 100.0

                                    dict_historicos[t] = hist['Close']
                                    dict_dividendos[t] = divs_finales

                                    f_div = tk.info.get('dividendRate', tk.info.get('trailingAnnualDividendRate', 0.0))
                                    if f_div is None or f_div == 0.0:
                                        f_div = divs_finales.tail(4).sum() if len(divs_finales) >= 4 else (divs_finales.iloc[-1] * 4 if not divs_finales.empty else 0.0)
                                    if es_uk and f_div > 0:
                                        f_div = f_div / 100.0
                                    dict_forward_div[t] = f_div

                                    # Estimación de crecimiento DGR a 5 años
                                    div_hist_full = tk.dividends
                                    if not div_hist_full.empty and len(div_hist_full) >= 8:
                                        divs_anuales = div_hist_full.groupby(div_hist_full.index.year).sum()
                                        if len(divs_anuales) >= 6 and divs_anuales.iloc[-6] > 0:
                                            dgr = ((divs_anuales.iloc[-1] / divs_anuales.iloc[-6]) ** (1/5) - 1) * 100
                                            dict_dgr5[t] = max(0.0, min(dgr, 15.0))
                                        else:
                                            dict_dgr5[t] = 5.0
                                    else:
                                        dict_dgr5[t] = 5.0
                            except Exception:
                                pass

                    if dict_historicos:
                        datos_historicos = pd.DataFrame(dict_historicos)
                        datos_dividendos = pd.DataFrame(dict_dividendos)
                        rango_fechas = pd.date_range(start=min_date_global.normalize(), end=pd.Timestamp.today().normalize())
                        datos_historicos = datos_historicos.reindex(rango_fechas).ffill().fillna(0)
                        datos_dividendos = datos_dividendos.reindex(rango_fechas).fillna(0)

                        daily_shares = pd.DataFrame(0.0, index=datos_historicos.index, columns=tickers_unicos)
                        daily_invested = pd.Series(0.0, index=datos_historicos.index)

                        current_shares = {t: 0.0 for t in tickers_unicos}
                        current_cost = {t: 0.0 for t in tickers_unicos}
                        total_invested = 0.0

                        for date in datos_historicos.index:
                            ops_today = df_ops[df_ops['Fecha'].dt.date == date.date()]
                            for _, row in ops_today.iterrows():
                                t, op, acc, precio = row['Ticker'], row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                if op == 'Compra':
                                    current_shares[t] += acc
                                    coste = acc * precio
                                    current_cost[t] += coste
                                    total_invested += coste
                                elif op == 'Venta' and current_shares.get(t, 0) > 0:
                                    pmp = current_cost[t] / current_shares[t]
                                    current_shares[t] -= acc
                                    coste_red = acc * pmp
                                    current_cost[t] -= coste_red
                                    total_invested -= coste_red
                            for t in tickers_unicos:
                                daily_shares.at[date, t] = current_shares.get(t, 0.0)
                            daily_invested.at[date] = total_invested

                        daily_value = (daily_shares * datos_historicos[tickers_unicos]).sum(axis=1)
                        daily_shares_shifted = daily_shares.shift(1).fillna(0)
                        
                        daily_gross_divs = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=1)
                        daily_net_divs = daily_gross_divs * net_factor
                        accumulated_divs_net = daily_net_divs.cumsum()
                        total_patrimonio = daily_value + accumulated_divs_net

                        posiciones_activas = {t: current_shares[t] for t in tickers_unicos if current_shares[t] > 0.001}
                        if posiciones_activas:
                            fx_rates_hoy = {'EUR': 1.0, 'USD': 1.0, 'GBP': 1.0, 'GBp': 1.0}
                            historico_fx = {}
                            try:
                                fx_usd = yf.Ticker("EURUSD=X").history(start=min_date_global)['Close']
                                fx_usd.index = fx_usd.index.tz_localize(None).normalize()
                                historico_fx['USD'] = fx_usd
                                fx_rates_hoy['USD'] = float(fx_usd.iloc[-1]) if not fx_usd.empty else 1.0

                                fx_gbp = yf.Ticker("EURGBP=X").history(start=min_date_global)['Close']
                                fx_gbp.index = fx_gbp.index.tz_localize(None).normalize()
                                historico_fx['GBP'] = fx_gbp
                                historico_fx['GBp'] = fx_gbp
                                fx_rates_hoy['GBP'] = float(fx_gbp.iloc[-1]) if not fx_gbp.empty else 1.0
                                fx_rates_hoy['GBp'] = fx_rates_hoy['GBP']
                            except Exception:
                                pass

                            def get_fx_hist(divisa, fecha):
                                if divisa == 'EUR': return 1.0
                                serie = historico_fx.get(divisa)
                                if serie is not None and not serie.empty:
                                    fecha_norm = pd.Timestamp(fecha).normalize()
                                    if fecha_norm in serie.index: return float(serie.loc[fecha_norm])
                                    idx = serie.index.get_indexer([fecha_norm], method='pad')[0]
                                    if idx != -1: return float(serie.iloc[idx])
                                return fx_rates_hoy.get(divisa, 1.0)

                            divs_gross_per_ticker = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=0)
                            divs_net_per_ticker = divs_gross_per_ticker * net_factor
                            
                            resultados_tabla = []
                            global_inversion_eur = 0.0
                            global_mercado_eur = 0.0
                            global_divs_gross_eur = 0.0
                            global_divs_net_eur = 0.0
                            total_forward_div_bruto_eur = 0.0

                            for t, acc in posiciones_activas.items():
                                try: curr = yf.Ticker(t).info.get('currency', 'USD')
                                except Exception: curr = 'USD'
                                fx_hoy = fx_rates_hoy.get(curr, 1.0)
                                p_actual = datos_historicos[t].iloc[-1]
                                p_medio = current_cost[t] / acc if acc > 0 else 0

                                coste_eur_total, acc_acumuladas = 0.0, 0.0
                                ops_t = df_ops[df_ops['Ticker'] == t].sort_values('Fecha')
                                for _, row in ops_t.iterrows():
                                    op, a, p = row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                    if curr == 'GBp': p = p / 100.0
                                    fx_d = get_fx_hist(curr, row['Fecha'])
                                    if op == 'Compra':
                                        acc_acumuladas += a
                                        coste_eur_total += (a * p) / fx_d
                                    elif op == 'Venta' and acc_acumuladas > 0:
                                        pmp_eur = coste_eur_total / acc_acumuladas
                                        acc_acumuladas -= a
                                        coste_eur_total -= (a * pmp_eur)

                                if coste_eur_total <= 0:
                                    coste_eur_total = (current_cost[t] / fx_hoy) if fx_hoy > 0 else current_cost[t]

                                v_mercado_eur = (acc * p_actual) / fx_hoy
                                divs_g_eur = divs_gross_per_ticker[t] / fx_hoy
                                divs_n_eur = divs_net_per_ticker[t] / fx_hoy
                                plusvalia_eur = v_mercado_eur - coste_eur_total
                                
                                ret_bruto_eur = plusvalia_eur + divs_g_eur
                                ret_neto_eur = plusvalia_eur + divs_n_eur

                                rent_plusvalia_pct = (plusvalia_eur / coste_eur_total * 100) if coste_eur_total > 0 else 0.0
                                rent_divs_gross_pct = (divs_g_eur / coste_eur_total * 100) if coste_eur_total > 0 else 0.0
                                rent_divs_net_pct = (divs_n_eur / coste_eur_total * 100) if coste_eur_total > 0 else 0.0
                                rent_tot_bruto_pct = (ret_bruto_eur / coste_eur_total * 100) if coste_eur_total > 0 else 0.0
                                rent_tot_neto_pct = (ret_neto_eur / coste_eur_total * 100) if coste_eur_total > 0 else 0.0

                                global_inversion_eur += coste_eur_total
                                global_mercado_eur += v_mercado_eur
                                global_divs_gross_eur += divs_g_eur
                                global_divs_net_eur += divs_n_eur
                                sym_divisa = "€" if curr == "EUR" else ("£" if curr in ["GBP", "GBp"] else "$")

                                div_anual_unitario = dict_forward_div.get(t, 0.0)
                                forward_div_anual_pos_bruto = (acc * div_anual_unitario) / fx_hoy
                                forward_div_anual_pos_neto = forward_div_anual_pos_bruto * net_factor
                                total_forward_div_bruto_eur += forward_div_anual_pos_bruto

                                yoc_bruto = (div_anual_unitario / p_medio * 100) if p_medio > 0 else 0.0
                                yoc_neto = yoc_bruto * net_factor
                                yield_act_bruto = (div_anual_unitario / p_actual * 100) if p_actual > 0 else 0.0
                                yield_act_neto = yield_act_bruto * net_factor

                                resultados_tabla.append({
                                    "Ticker": t,
                                    "Acciones": acc,
                                    "PMC": p_medio,
                                    "Precio": p_actual,
                                    "Moneda": sym_divisa,
                                    "Coste EUR": coste_eur_total,
                                    "Valor EUR": v_mercado_eur,
                                    "Plusvalia EUR": plusvalia_eur,
                                    "Rent Plusvalia Pct": rent_plusvalia_pct,
                                    "Divs Gross EUR": divs_g_eur,
                                    "Divs Net EUR": divs_n_eur,
                                    "Rent Divs Gross Pct": rent_divs_gross_pct,
                                    "Rent Divs Net Pct": rent_divs_net_pct,
                                    "Total Bruto EUR": ret_bruto_eur,
                                    "Total Neto EUR": ret_neto_eur,
                                    "Rent Tot Bruto Pct": rent_tot_bruto_pct,
                                    "Rent Tot Neto Pct": rent_tot_neto_pct,
                                    "Renta Anual Proyectada Neto": forward_div_anual_pos_neto,
                                    "YoC Bruto": yoc_bruto,
                                    "YoC Neto": yoc_neto,
                                    "Yield Act Bruto": yield_act_bruto,
                                    "Yield Act Neto": yield_act_neto,
                                    "DGR5": dict_dgr5.get(t, 5.0)
                                })

                            plusvalia_global_eur = global_mercado_eur - global_inversion_eur
                            ret_tot_global_bruto_eur = plusvalia_global_eur + global_divs_gross_eur
                            ret_tot_global_neto_eur = plusvalia_global_eur + global_divs_net_eur
                            
                            pct_plusvalia_global = (plusvalia_global_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            pct_divs_gross_global = (global_divs_gross_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            pct_divs_net_global = (global_divs_net_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            pct_ret_bruto_global = (ret_tot_global_bruto_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            pct_ret_neto_global = (ret_tot_global_neto_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0

                            total_forward_div_neto_eur = total_forward_div_bruto_eur * net_factor
                            sueldo_pasivo_mes_neto = total_forward_div_neto_eur / 12.0

                            yoc_global_bruto = (total_forward_div_bruto_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            yoc_global_neto = yoc_global_bruto * net_factor
                            yield_global_bruto = (total_forward_div_bruto_eur / global_mercado_eur * 100) if global_mercado_eur > 0 else 0.0
                            yield_global_neto = yield_global_bruto * net_factor

                            # Asignar Pesos de Capital vs Pesos de Dividendo
                            for r in resultados_tabla:
                                r['Peso Capital Pct'] = (r['Valor EUR'] / global_mercado_eur * 100) if global_mercado_eur > 0 else 0.0
                                r['Peso Renta Pct'] = (r['Renta Anual Proyectada Neto'] / total_forward_div_neto_eur * 100) if total_forward_div_neto_eur > 0 else 0.0

                            # ==========================================
                            # 1. TARJETAS KPIS ESTRATÉGICAS DGI
                            # ==========================================
                            st.markdown(f"#### 🌐 Resumen de Rendimiento ({año_filtro})")
                            
                            k1, k2, k3, k4, k5 = st.columns(5)
                            
                            with k1:
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-title">💰 Valor Cartera vs Coste</div>
                                    <div class="metric-val" style="color: #00d4ff;">{fmt_es(global_mercado_eur, 2, sufijo=" €")}</div>
                                    <div class="metric-sub" style="color: #aaa;">Coste: {fmt_es(global_inversion_eur, 2, sufijo=" €")}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            with k2:
                                col_p = "#21c354" if plusvalia_global_eur >= 0 else "#ff4b4b"
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-title">📈 Plusvalía Latente</div>
                                    <div class="metric-val" style="color: {col_p};">{fmt_es(plusvalia_global_eur, 2, signo=True, sufijo=" €")}</div>
                                    <div class="metric-sub" style="color: {col_p};">{fmt_es(pct_plusvalia_global, 2, signo=True, sufijo="% s/ Coste")}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            with k3:
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-title">💵 Dividendos Cobrados</div>
                                    <div class="metric-val" style="color: #00d4ff;">{fmt_es(global_divs_net_eur, 2, sufijo=" €")} <span style="font-size: 0.85rem; color: #aaa;">Neto</span></div>
                                    <div class="metric-sub" style="color: #aaa;">Bruto: {fmt_es(global_divs_gross_eur, 2, sufijo=" €")} ({fmt_es(pct_divs_net_global, 2, sufijo="% recup.")})</div>
                                </div>
                                """, unsafe_allow_html=True)

                            with k4:
                                col_tot = "#21c354" if ret_tot_global_neto_eur >= 0 else "#ff4b4b"
                                st.markdown(f"""
                                <div class="metric-box" style="border-color: rgba(33, 195, 84, 0.35); background: rgba(33, 195, 84, 0.05);">
                                    <div class="metric-title" style="color: #21c354;">🚀 Retorno Total Real</div>
                                    <div class="metric-val" style="color: {col_tot};">{fmt_es(ret_tot_global_neto_eur, 2, signo=True, sufijo=" €")} <span style="font-size: 0.85rem;">Neto</span></div>
                                    <div class="metric-sub" style="color: {col_tot};"><b>{fmt_es(pct_ret_neto_global, 2, signo=True, sufijo="%")}</b> | Bruto: {fmt_es(pct_ret_bruto_global, 2, signo=True, sufijo="%")}</div>
                                </div>
                                """, unsafe_allow_html=True)

                            with k5:
                                st.markdown(f"""
                                <div class="metric-box">
                                    <div class="metric-title">⏳ Renta Futura Proyectada</div>
                                    <div class="metric-val" style="color: #faca2b;">{fmt_es(total_forward_div_neto_eur, 2, sufijo=" €/año")}</div>
                                    <div class="metric-sub" style="color: #21c354;"><b>~{fmt_es(sueldo_pasivo_mes_neto, 2, sufijo=" €/mes limpios")}</b> | YoC: {fmt_es(yoc_global_neto, 2, sufijo="%")}</div>
                                </div>
                                """, unsafe_allow_html=True)

                            # ==========================================
                            # 2. HERRAMIENTAS GRÁFICAS DE ESTRATEGIA DGI
                            # ==========================================
                            st.divider()
                            col_g1, col_g2 = st.columns(2)
                            
                            df_analytics = pd.DataFrame(resultados_tabla).sort_values(by="Total Neto EUR", ascending=True)

                            with col_g1:
                                st.markdown("#### 🎯 Retorno Total: Plusvalía vs Dividendos (€)")
                                fig_comp_eur = go.Figure()
                                fig_comp_eur.add_trace(go.Bar(
                                    y=df_analytics['Ticker'],
                                    x=df_analytics['Plusvalia EUR'],
                                    name='Plusvalía Latente (€)',
                                    orientation='h',
                                    marker_color=['#21c354' if x >= 0 else '#ff4b4b' for x in df_analytics['Plusvalia EUR']],
                                    text=[fmt_es(x, 0, signo=True, sufijo=" €") for x in df_analytics['Plusvalia EUR']],
                                    textposition='auto'
                                ))
                                fig_comp_eur.add_trace(go.Bar(
                                    y=df_analytics['Ticker'],
                                    x=df_analytics['Divs Net EUR'],
                                    name='Dividendos Cobrados Netos (€)',
                                    orientation='h',
                                    marker_color='#00d4ff',
                                    text=[fmt_es(x, 0, sufijo=" €") for x in df_analytics['Divs Net EUR']],
                                    textposition='auto'
                                ))
                                fig_comp_eur.update_layout(
                                    template='plotly_dark',
                                    barmode='relative',
                                    height=340,
                                    margin=dict(l=0, r=20, t=10, b=10),
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                                    xaxis=dict(title="Beneficio Total (€)")
                                )
                                st.plotly_chart(fig_comp_eur, use_container_width=True)

                            with col_g2:
                                st.markdown("#### 🛡️ Radar de Concentración: Capital vs Flujo de Renta (%)")
                                fig_conc = go.Figure()
                                fig_conc.add_trace(go.Bar(
                                    x=df_analytics['Ticker'],
                                    y=df_analytics['Peso Capital Pct'],
                                    name='% de tu Patrimonio (Capital)',
                                    marker_color='#9c27b0',
                                    text=[fmt_es(x, 1, sufijo="%") for x in df_analytics['Peso Capital Pct']],
                                    textposition='auto'
                                ))
                                fig_conc.add_trace(go.Bar(
                                    x=df_analytics['Ticker'],
                                    y=df_analytics['Peso Renta Pct'],
                                    name='% de tu Renta Total (Dividendos)',
                                    marker_color='#00d4ff',
                                    text=[fmt_es(x, 1, sufijo="%") for x in df_analytics['Peso Renta Pct']],
                                    textposition='auto'
                                ))
                                fig_conc.update_layout(
                                    barmode='group',
                                    template='plotly_dark',
                                    height=340,
                                    margin=dict(l=0, r=10, t=10, b=10),
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                                    yaxis=dict(title="Porcentaje (%)")
                                )
                                st.plotly_chart(fig_conc, use_container_width=True)

                            # Proyección Compuesta Bola de Nieve a 10 Años
                            st.divider()
                            st.markdown("#### 🔮 Proyección a 10 Años: Efecto Bola de Nieve (Sin Aportar Más Capital)")
                            dgr_medio_cartera = float(np.average(
                                [r['DGR5'] for r in resultados_tabla],
                                weights=[r['Renta Anual Proyectada Neto'] for r in resultados_tabla]
                            )) if total_forward_div_neto_eur > 0 else 6.0

                            años_futuros = list(range(1, 11))
                            año_base = datetime.now().year
                            labels_futuros = [str(año_base + y) for y in años_futuros]

                            renta_proy_conservadora = [total_forward_div_neto_eur * ((1 + 0.04) ** y) for y in años_futuros]
                            renta_proy_cartera = [total_forward_div_neto_eur * ((1 + (dgr_medio_cartera/100)) ** y) for y in años_futuros]
                            renta_proy_fuerte = [total_forward_div_neto_eur * ((1 + 0.09) ** y) for y in años_futuros]

                            fig_snow = go.Figure()
                            fig_snow.add_trace(go.Bar(
                                x=labels_futuros,
                                y=renta_proy_cartera,
                                name=f'Ritmo de tu Cartera (DGR: {dgr_medio_cartera:.1f}%)',
                                marker_color='#21c354',
                                text=[fmt_es(val, 0, sufijo=" €") for val in renta_proy_cartera],
                                textposition='auto'
                            ))
                            fig_snow.add_trace(go.Scatter(
                                x=labels_futuros,
                                y=renta_proy_conservadora,
                                mode='lines+markers',
                                name='Escenario Conservador (+4%)',
                                line=dict(color='#ff9800', width=2, dash='dot')
                            ))
                            fig_snow.add_trace(go.Scatter(
                                x=labels_futuros,
                                y=renta_proy_fuerte,
                                mode='lines+markers',
                                name='Escenario Alto (+9%)',
                                line=dict(color='#00d4ff', width=2, dash='dash')
                            ))
                            fig_snow.update_layout(
                                template='plotly_dark',
                                height=350,
                                margin=dict(l=0, r=0, t=10, b=10),
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
                                yaxis=dict(title="Renta Pasiva Neta / Año (€)")
                            )
                            st.plotly_chart(fig_snow, use_container_width=True)

                            # ==========================================
                            # 3. EVOLUCIÓN PATRIMONIAL ADAPTADA A LA AÑADA
                            # ==========================================
                            st.divider()
                            st.markdown(f"#### 📈 Evolución Patrimonial ({'Desde ' + año_filtro if año_filtro != 'Todo el Historial' else 'Histórico Completo'})")
                            
                            if año_filtro != "Todo el Historial":
                                fecha_corte_inicio = pd.Timestamp(f"{int(año_filtro)}-01-01")
                            else:
                                fecha_corte_inicio = min_date_global

                            mask_chart = daily_invested.index >= fecha_corte_inicio
                            di_plot = daily_invested[mask_chart]
                            dv_plot = daily_value[mask_chart]
                            ad_plot = accumulated_divs_net[mask_chart]
                            tp_plot = total_patrimonio[mask_chart]

                            fig_cartera = go.Figure()
                            fig_cartera.add_trace(go.Scatter(
                                x=di_plot.index, y=di_plot.values, mode='lines',
                                line=dict(color='#faca2b', width=2, dash='dash'), name='Capital Aportado'
                            ))
                            fig_cartera.add_trace(go.Scatter(
                                x=dv_plot.index, y=dv_plot.values, mode='lines',
                                line=dict(color='#21c354', width=2), name='Valor de Mercado'
                            ))
                            fig_cartera.add_trace(go.Scatter(
                                x=ad_plot.index, y=ad_plot.values, fill='tozeroy', mode='lines',
                                line=dict(color='#00d4ff', width=2), fillcolor='rgba(0, 212, 255, 0.15)', name='Divs Netos Acumulados'
                            ))
                            fig_cartera.add_trace(go.Scatter(
                                x=tp_plot.index, y=tp_plot.values, mode='lines',
                                line=dict(color='#e040fb', width=2.5), name='Patrimonio Total (Mercado + Divs)'
                            ))
                            fig_cartera.update_layout(
                                template='plotly_dark', margin=dict(l=0, r=0, t=10, b=10), height=400,
                                hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
                            )
                            st.plotly_chart(fig_cartera, use_container_width=True)

                            # ==========================================
                            # 4. TABLA DETALLADA DE POSICIONES
                            # ==========================================
                            st.divider()
                            st.markdown("#### 📋 Desglose Detallado de Posiciones")
                            
                            df_pos_sorted = pd.DataFrame(resultados_tabla).sort_values(by="Total Neto EUR", ascending=False)

                            rows_display = []
                            for _, r in df_pos_sorted.iterrows():
                                sym = r['Moneda']
                                rows_display.append({
                                    "Ticker": r['Ticker'],
                                    "Acciones": fmt_acciones(r['Acciones']),
                                    "PMC": f"{fmt_es(r['PMC'], 2)} {sym}",
                                    "Precio": f"{fmt_es(r['Precio'], 2)} {sym}",
                                    "Coste (€)": fmt_es(r['Coste EUR'], 2, sufijo=" €"),
                                    "Valor (€)": fmt_es(r['Valor EUR'], 2, sufijo=" €"),
                                    "Plusvalía (€)": fmt_es(r['Plusvalia EUR'], 2, signo=True, sufijo=" €"),
                                    "Plusvalía (%)": fmt_es(r['Rent Plusvalia Pct'], 2, signo=True, sufijo="%"),
                                    "Divs Cobrados (€)": fmt_es(r['Divs Net EUR'], 2, sufijo=" €"),
                                    "Ret. Total Neto (€)": fmt_es(r['Total Neto EUR'], 2, signo=True, sufijo=" €"),
                                    "Ret. Total Neto (%)": fmt_es(r['Rent Tot Neto Pct'], 2, signo=True, sufijo="%"),
                                    "YoC Neto (%)": fmt_es(r['YoC Neto'], 2, sufijo="%"),
                                    "Yield Act. Neto (%)": fmt_es(r['Yield Act Neto'], 2, sufijo="%"),
                                    "Peso Cap. (%)": fmt_es(r['Peso Capital Pct'], 1, sufijo="%"),
                                    "Peso Renta (%)": fmt_es(r['Peso Renta Pct'], 1, sufijo="%")
                                })

                            df_disp = pd.DataFrame(rows_display)

                            def estilo_positivo_negativo(val):
                                if isinstance(val, str) and (val.startswith('+') or val.startswith(' +')):
                                    return 'color: #21c354; font-weight: bold;'
                                elif isinstance(val, str) and (val.startswith('-') or val.startswith(' -')):
                                    return 'color: #ff4b4b; font-weight: bold;'
                                return ''

                            styler = df_disp.style
                            cols_target = ['Plusvalía (€)', 'Plusvalía (%)', 'Ret. Total Neto (€)', 'Ret. Total Neto (%)']
                            if hasattr(styler, 'map'):
                                styler = styler.map(estilo_positivo_negativo, subset=cols_target)
                            else:
                                styler = styler.applymap(estilo_positivo_negativo, subset=cols_target)

                            st.dataframe(styler, use_container_width=True, hide_index=True)

                            # ==========================================
                            # 5. CALENDARIO DE DIVIDENDOS NETOS
                            # ==========================================
                            df_divs_hist = pd.DataFrame({'Fecha': daily_net_divs.index, 'Dividendo': daily_net_divs.values})
                            df_divs_hist = df_divs_hist[df_divs_hist['Dividendo'] > 0]
                            if not df_divs_hist.empty:
                                st.divider()
                                st.markdown("#### 🗓️ Calendario Histórico de Cobros y Crecimiento")
                                df_divs_hist['Año'], df_divs_hist['Mes'] = df_divs_hist['Fecha'].dt.year, df_divs_hist['Fecha'].dt.month
                                agrup_meses = df_divs_hist.groupby(['Año', 'Mes'])['Dividendo'].sum().reset_index()
                                anual_divs = df_divs_hist.groupby('Año')['Dividendo'].sum().reset_index()
                                anual_divs['Crec. YoY (%)'] = anual_divs['Dividendo'].pct_change() * 100

                                col_m1, col_m2 = st.columns([2.5, 1])
                                with col_m1:
                                    st.markdown("##### 📊 Ingresos Mensuales por Año")
                                    fig_meses = go.Figure()
                                    meses_str = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                                    for año in sorted(agrup_meses['Año'].unique()):
                                        d_a = agrup_meses[agrup_meses['Año'] == año]
                                        fig_meses.add_trace(go.Bar(x=list(meses_str.values()), y=[d_a[d_a['Mes'] == m]['Dividendo'].values[0] if not d_a[d_a['Mes'] == m].empty else 0.0 for m in range(1, 13)], name=str(año)))
                                    fig_meses.update_layout(barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=340, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
                                    st.plotly_chart(fig_meses, use_container_width=True)
                                with col_m2:
                                    st.markdown("##### 📝 Crecimiento Anual (YoY)")
                                    df_anual_disp = anual_divs.copy()
                                    df_anual_disp['Dividendo'] = df_anual_disp['Dividendo'].apply(lambda v: fmt_es(v, 2, sufijo=" €"))
                                    df_anual_disp['Crec. YoY (%)'] = df_anual_disp['Crec. YoY (%)'].apply(lambda v: fmt_es(v, 2, signo=True, sufijo="%") if pd.notna(v) else "-")
                                    st.dataframe(df_anual_disp, use_container_width=True, hide_index=True)

                                st.markdown("<br>", unsafe_allow_html=True)
                                st.markdown("##### 📈 Efecto Bola de Nieve (Dividendos Anuales Totales)")
                                text_bolanieve = [fmt_es(val, 2, sufijo=" €") for val in anual_divs['Dividendo']]
                                fig_anual = go.Figure(go.Bar(x=anual_divs['Año'].astype(str), y=anual_divs['Dividendo'], name='Total Cobrado', marker_color='#00d4ff', text=text_bolanieve, textposition='auto'))
                                fig_anual.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=320, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title="Dividendos Netos (€)"))
                                st.plotly_chart(fig_anual, use_container_width=True)

                        # ==========================================
                        # 6. RADIOGRAFÍA ANUAL FIJA
                        # ==========================================
                        st.divider()
                        st.markdown("### 📸 Radiografía del Año Natural (Toda la Cartera)")
                        st.markdown("> *Muestra el comportamiento del 1 de enero al 31 de diciembre del año elegido para el conjunto total de tu cartera.*")

                        año_minimo = int(df_ops_global['Fecha'].dt.year.min())
                        año_actual_num = int(pd.Timestamp.today().year)
                        opciones_radio = [str(a) for a in range(año_minimo, año_actual_num + 1)]

                        año_radio = st.selectbox("Selecciona Año a Inspeccionar:", opciones_radio, index=len(opciones_radio)-1, key="año_rad_ind")

                        if año_radio:
                            año_int = int(año_radio)

                            daily_shares_g = pd.DataFrame(0.0, index=datos_historicos.index, columns=tickers_global)
                            daily_invested_g = pd.Series(0.0, index=datos_historicos.index)

                            curr_sh_g = {t: 0.0 for t in tickers_global}
                            curr_c_g = {t: 0.0 for t in tickers_global}
                            tot_inv_g = 0.0

                            for date in datos_historicos.index:
                                ops_today = df_ops_global[df_ops_global['Fecha'].dt.date == date.date()]
                                for _, row in ops_today.iterrows():
                                    t, op, acc, precio = row['Ticker'], row['Operacion'], float(row['Acciones']), float(row['Precio'])
                                    if op == 'Compra':
                                        curr_sh_g[t] += acc
                                        curr_c_g[t] += (acc * precio)
                                        tot_inv_g += (acc * precio)
                                    elif op == 'Venta' and curr_sh_g.get(t, 0) > 0:
                                        pmp = curr_c_g[t] / curr_sh_g[t]
                                        curr_sh_g[t] -= acc
                                        curr_c_g[t] -= (acc * pmp)
                                        tot_inv_g -= (acc * pmp)
                                for t in tickers_global:
                                    daily_shares_g.at[date, t] = curr_sh_g.get(t, 0.0)
                                daily_invested_g.at[date] = tot_inv_g

                            daily_value_g = (daily_shares_g * datos_historicos[tickers_global]).sum(axis=1)
                            daily_net_divs_g = (daily_shares_g.shift(1).fillna(0) * datos_dividendos[tickers_global]).sum(axis=1) * net_factor

                            mask_y = daily_invested_g.index.year == año_int
                            di_y = daily_invested_g[mask_y]
                            dv_y = daily_value_g[mask_y]
                            dd_y = daily_net_divs_g[mask_y]

                            if not di_y.empty:
                                acc_divs_y = dd_y.cumsum()
                                tot_pat_y = dv_y + acc_divs_y

                                inv_ini, inv_fin = di_y.iloc[0], di_y.iloc[-1]
                                val_ini, val_fin = dv_y.iloc[0], dv_y.iloc[-1]
                                div_tot = acc_divs_y.iloc[-1]

                                aportaciones = inv_fin - inv_ini
                                b_mercado = (val_fin - val_ini) - aportaciones
                                b_total = b_mercado + div_tot

                                base_pct = val_ini + aportaciones if (val_ini + aportaciones) > 0 else 1.0

                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric(f"Valor Base ({año_radio})", fmt_es(base_pct, 2, sufijo=" €"), f"Aportación nueva: {fmt_es(aportaciones, 2, signo=True, sufijo=' €')}")
                                c2.metric("P/L Mercado (Anual)", fmt_es(b_mercado, 2, signo=True, sufijo=" €"), fmt_es((b_mercado/base_pct)*100, 2, signo=True, sufijo="%"))
                                c3.metric("Dividendos Netos (Anual)", fmt_es(div_tot, 2, sufijo=" €"), f"{fmt_es((div_tot/base_pct)*100, 2, signo=True, sufijo='%')} s/ Base")
                                c4.metric("Beneficio Total (Anual)", fmt_es(b_total, 2, signo=True, sufijo=" €"), fmt_es((b_total/base_pct)*100, 2, signo=True, sufijo="%"))

                                fig_y = go.Figure()
                                fig_y.add_trace(go.Scatter(x=di_y.index, y=di_y.values, mode='lines', line=dict(color='#faca2b', width=2, dash='dash'), name='Capital Global Invertido'))
                                fig_y.add_trace(go.Scatter(x=dv_y.index, y=dv_y.values, mode='lines', line=dict(color='#21c354', width=2), name='Valor Mercado'))
                                fig_y.add_trace(go.Scatter(x=acc_divs_y.index, y=acc_divs_y.values, fill='tozeroy', mode='lines', line=dict(color='#00d4ff', width=2), fillcolor='rgba(0, 212, 255, 0.15)', name=f'Divs Acumulados ({año_radio})'))
                                fig_y.add_trace(go.Scatter(x=tot_pat_y.index, y=tot_pat_y.values, mode='lines', line=dict(color='#e040fb', width=2.5), name='Patrimonio Total'))
                                fig_y.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=380, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
                                st.plotly_chart(fig_y, use_container_width=True)

                                st.markdown(f"#### 📊 Cobros Mensuales en {año_radio}")
                                df_d_y = pd.DataFrame({'Fecha': dd_y.index, 'Dividendo': dd_y.values})
                                df_d_y = df_d_y[df_d_y['Dividendo'] > 0]
                                if not df_d_y.empty:
                                    df_d_y['Mes'] = df_d_y['Fecha'].dt.month
                                    agrup_m = df_d_y.groupby('Mes')['Dividendo'].sum()
                                    y_vals = [agrup_m.get(m, 0.0) for m in range(1, 13)]
                                    text_vals = [fmt_es(v, 2, sufijo=" €") if v > 0 else "" for v in y_vals]

                                    fig_d = go.Figure(go.Bar(x=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'], y=y_vals, marker_color='#00d4ff', text=text_vals, textposition='auto'))
                                    fig_d.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=300, yaxis_title="Dividendos Netos (€)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                                    st.plotly_chart(fig_d, use_container_width=True)
                                else:
                                    st.info(f"No se cobraron dividendos en {año_radio}.")
    except Exception as e:
        st.error(f"No se pudo procesar la cartera. Detalle: {e}")
