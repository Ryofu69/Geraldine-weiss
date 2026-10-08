import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import plotly.graph_objects as go
import io
import os

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Control de Cartera DGI", page_icon="💼", layout="wide")

ARCHIVO_CARTERA = "cartera.csv"

# ==========================================
# UTILIDADES DE LIMPIEZA Y PERSISTENCIA
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

def cargar_cartera_guardada():
    if os.path.exists(ARCHIVO_CARTERA):
        try:
            with open(ARCHIVO_CARTERA, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    return c
        except Exception:
            pass
    return "Fecha,Ticker,Operacion,Acciones,Precio\n"

def guardar_cartera_archivo(texto):
    try:
        with open(ARCHIVO_CARTERA, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# ==========================================
# INTERFAZ DE ENTRADA Y CONTROL
# ==========================================
st.title("💼 Control de Rentabilidad y Añadas en Tiempo Real")
st.markdown("> *Privacidad garantizada: Tus transacciones se procesan localmente sin exponerse en GitHub.*")

col_c1, col_c2 = st.columns(2)
with col_c1:
    metodo_carga = st.radio("¿Cómo quieres cargar tu cartera?", ["📝 Pegar / Editar Texto", "📂 Subir Archivo"], horizontal=True)
with col_c2:
    impuesto_cart = st.number_input("Retención media de dividendos (%)", value=19.0, step=0.5, key="imp_cart_p3")

df_ops = None
texto_guardado = cargar_cartera_guardada()

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
    st.info("Pega directamente tu historial. Encabezados: Fecha, Ticker, Operacion, Acciones, Precio.")
    texto_csv = st.text_area("Pega aquí tus transacciones:", value=texto_guardado, height=140)
    col_btn_cart, _ = st.columns([1, 4])
    with col_btn_cart:
        if st.button("💾 Guardar Cartera en Archivo"):
            if guardar_cartera_archivo(texto_csv):
                st.success("Cartera guardada correctamente en `cartera.csv`.")
            else:
                st.error("Error al guardar el archivo.")
    if texto_csv and texto_csv.strip():
        try:
            df_ops = pd.read_csv(io.StringIO(texto_csv.strip()), sep=None, engine='python', dtype=str)
        except Exception as e:
            st.error(f"Error al leer el texto pegado: {e}")

# ==========================================
# PROCESAMIENTO Y MOTOR DE CÁLCULO
# ==========================================
if df_ops is not None and not df_ops.empty:
    try:
        # Mapeo universal de cabeceras
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
            # Limpieza universal de números
            df_ops['Acciones'] = df_ops['Acciones'].apply(limpiar_numero_europeo)
            df_ops['Precio'] = df_ops['Precio'].apply(limpiar_numero_europeo)
            df_ops['Fecha'] = pd.to_datetime(df_ops['Fecha'], errors='coerce', dayfirst=True)
            df_ops['Ticker'] = df_ops['Ticker'].astype(str).str.strip().str.upper()
            df_ops['Operacion'] = df_ops['Operacion'].astype(str).str.strip().str.capitalize()

            df_ops = df_ops.dropna(subset=['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio'])
            df_ops = df_ops[df_ops['Acciones'] > 0]
            df_ops = df_ops.sort_values('Fecha')

            if df_ops.empty:
                st.warning("No hay transacciones válidas que procesar.")
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

                # Aplicación de filtros
                if año_filtro != "Todo el Historial":
                    df_ops = df_ops[(df_ops['Fecha'].dt.year == int(año_filtro)) & (df_ops['Operacion'] == 'Compra')]
                if ticker_filtro != "Todas las Empresas":
                    df_ops = df_ops[df_ops['Ticker'] == ticker_filtro]

                if df_ops.empty:
                    st.warning("No hay operaciones válidas con los filtros seleccionados.")
                else:
                    min_date = df_ops_global['Fecha'].min()
                    tickers_unicos = df_ops['Ticker'].unique().tolist()

                    dict_historicos = {}
                    dict_dividendos = {}
                    dict_forward_div = {}

                    with st.spinner("Descargando precios de mercado, dividendos e historial FX..."):
                        for t in tickers_global:
                            try:
                                tk = yf.Ticker(t)
                                hist = tk.history(start=min_date, auto_adjust=False)
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
                                            divs_finales = divs_reales[divs_reales.index >= min_date]
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
                            except Exception:
                                pass

                    if dict_historicos:
                        datos_historicos = pd.DataFrame(dict_historicos)
                        datos_dividendos = pd.DataFrame(dict_dividendos)
                        rango_fechas = pd.date_range(start=min_date.normalize(), end=pd.Timestamp.today().normalize())
                        datos_historicos = datos_historicos.reindex(rango_fechas).ffill().fillna(0)
                        datos_dividendos = datos_dividendos.reindex(rango_fechas).fillna(0)

                        # ==========================================
                        # 1. LÓGICA LOCAL (MODO AÑADA / FILTRADA)
                        # ==========================================
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
                        daily_net_divs = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=1) * (1 - (impuesto_cart / 100.0))
                        accumulated_divs = daily_net_divs.cumsum()
                        total_patrimonio = daily_value + accumulated_divs

                        st.markdown("#### 📈 Evolución de tu Patrimonio")
                        fig_cartera = go.Figure()
                        fig_cartera.add_trace(go.Scatter(x=daily_invested.index, y=daily_invested.values, mode='lines', line=dict(color='#faca2b', width=2, dash='dash'), name='Capital Aportado'))
                        fig_cartera.add_trace(go.Scatter(x=daily_value.index, y=daily_value.values, mode='lines', line=dict(color='#21c354', width=2), name='Valor Mercado'))
                        fig_cartera.add_trace(go.Scatter(x=accumulated_divs.index, y=accumulated_divs.values, fill='tozeroy', mode='lines', line=dict(color='#00d4ff', width=2), fillcolor='rgba(0, 212, 255, 0.15)', name='Divs Netos Acumulados'))
                        fig_cartera.add_trace(go.Scatter(x=total_patrimonio.index, y=total_patrimonio.values, mode='lines', line=dict(color='#e040fb', width=2.5), name='Patrimonio Total'))
                        fig_cartera.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=20, b=0), height=420, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5))
                        st.plotly_chart(fig_cartera, use_container_width=True)

                        posiciones_activas = {t: current_shares[t] for t in tickers_unicos if current_shares[t] > 0.001}
                        if posiciones_activas:
                            fx_rates_hoy = {'EUR': 1.0, 'USD': 1.0, 'GBP': 1.0, 'GBp': 1.0}
                            historico_fx = {}
                            try:
                                fx_usd = yf.Ticker("EURUSD=X").history(start=min_date)['Close']
                                fx_usd.index = fx_usd.index.tz_localize(None).normalize()
                                historico_fx['USD'] = fx_usd
                                fx_rates_hoy['USD'] = float(fx_usd.iloc[-1]) if not fx_usd.empty else 1.0

                                fx_gbp = yf.Ticker("EURGBP=X").history(start=min_date)['Close']
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

                            divs_per_ticker = (daily_shares_shifted * datos_dividendos[tickers_unicos]).sum(axis=0) * (1 - (impuesto_cart / 100.0))
                            resultados_tabla, global_inversion_eur, global_mercado_eur, global_divs_eur = [], 0.0, 0.0, 0.0
                            total_div_anual_eur = 0.0

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

                                v_mercado_orig, divs_orig = acc * p_actual, divs_per_ticker[t]
                                b_abs_orig = v_mercado_orig - current_cost[t]
                                b_total_orig = b_abs_orig + divs_orig

                                rent_precio_orig = (b_abs_orig / current_cost[t]) * 100 if current_cost[t] > 0 else 0
                                rent_total_orig = (b_total_orig / current_cost[t]) * 100 if current_cost[t] > 0 else 0

                                v_mercado_eur, divs_eur = v_mercado_orig / fx_hoy, divs_orig / fx_hoy
                                b_abs_eur = v_mercado_eur - coste_eur_total
                                b_total_eur = b_abs_eur + divs_eur

                                rent_precio_eur = (b_abs_eur / coste_eur_total) * 100 if coste_eur_total > 0 else 0
                                rent_total_eur = (b_total_eur / coste_eur_total) * 100 if coste_eur_total > 0 else 0

                                global_inversion_eur += coste_eur_total
                                global_mercado_eur += v_mercado_eur
                                global_divs_eur += divs_eur
                                sym_divisa = "€" if curr == "EUR" else ("£" if curr in ["GBP", "GBp"] else "$")

                                div_anual_unitario = dict_forward_div.get(t, 0.0)
                                yoc_bruto = (div_anual_unitario / p_medio * 100) if p_medio > 0 else 0.0
                                yoc_neto = yoc_bruto * (1 - (impuesto_cart / 100.0))
                                yield_act_bruto = (div_anual_unitario / p_actual * 100) if p_actual > 0 else 0.0
                                yield_act_neto = yield_act_bruto * (1 - (impuesto_cart / 100.0))

                                total_div_anual_eur += (acc * div_anual_unitario) / fx_hoy

                                resultados_tabla.append({
                                    "Ticker": t, "Acciones": round(acc, 4),
                                    "Precio Medio": f"{p_medio:.2f} {sym_divisa}", "Precio Actual": f"{p_actual:.2f} {sym_divisa}",
                                    "Valor Mercado": v_mercado_orig, "P/L Latente": b_abs_orig, "Divs. Cobrados": divs_orig, "Bº Total (Abs)": b_total_orig,
                                    "Rent. Precio (€)": rent_precio_eur, "Rent. Total (€)": rent_total_eur,
                                    "YoC Bruto": yoc_bruto, "YoC Neto": yoc_neto,
                                    "Yield Act. Bruto": yield_act_bruto, "Yield Act. Neto": yield_act_neto
                                })

                            b_l_mercado_eur = global_mercado_eur - global_inversion_eur
                            b_total_global_eur = b_l_mercado_eur + global_divs_eur

                            yoc_global_bruto = (total_div_anual_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0.0
                            yoc_global_neto = yoc_global_bruto * (1 - (impuesto_cart / 100.0))
                            yield_global_bruto = (total_div_anual_eur / global_mercado_eur * 100) if global_mercado_eur > 0 else 0.0
                            yield_global_neto = yield_global_bruto * (1 - (impuesto_cart / 100.0))

                            st.markdown("#### 🌐 Resumen Global Hoy (Convertido a Euros €)")
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("Capital Invertido", f"{global_inversion_eur:,.2f} €")
                            c2.metric("Valor Mercado", f"{global_mercado_eur:,.2f} €", f"{(b_l_mercado_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0:+.2f}%")
                            c3.metric("Dividendos Cobrados", f"{global_divs_eur:,.2f} €", f"{(global_divs_eur / global_inversion_eur * 100) if global_inversion_eur > 0 else 0:+.2f}% del Cap")
                            c4.metric("YoC (s/ Coste)", f"{yoc_global_neto:.2f}% Neto", f"Bruto: {yoc_global_bruto:.2f}%")
                            c5.metric("Yield Actual", f"{yield_global_neto:.2f}% Neto", f"Bruto: {yield_global_bruto:.2f}%")

                            st.markdown("#### 📋 Posiciones Abiertas (Con Rendimientos Brutos y Netos)")
                            resultados_tabla_ordenados = sorted(resultados_tabla, key=lambda k: k['Rent. Total (€)'], reverse=True)
                            df_mostrar = pd.DataFrame(resultados_tabla_ordenados)
                            styled_df = df_mostrar.style.format({
                                "Valor Mercado": "{:,.2f}", "P/L Latente": "{:+.2f}", "Divs. Cobrados": "{:,.2f}", "Bº Total (Abs)": "{:+.2f}",
                                "Rent. Precio (€)": "{:+.2f}%", "Rent. Total (€)": "{:+.2f}%",
                                "YoC Bruto": "{:.2f}%", "YoC Neto": "{:.2f}%",
                                "Yield Act. Bruto": "{:.2f}%", "Yield Act. Neto": "{:.2f}%"
                            }).map(lambda val: f"color: {'#21c354' if val > 0 else '#ff4b4b'}; font-weight: bold;", subset=['P/L Latente', 'Bº Total (Abs)', 'Rent. Precio (€)', 'Rent. Total (€)']).map(lambda val: f"color: {'#00d4ff' if val > 0 else '#aaaaaa'};", subset=['Divs. Cobrados']).map(lambda val: "color: #faca2b; font-weight: bold;", subset=['YoC Neto'])
                            st.dataframe(styled_df, use_container_width=True, hide_index=True)

                            st.markdown("#### 📊 YoC vs Yield Actual por Empresa (Selección Actual)")
                            fig_yocs = go.Figure()
                            tickers_bars = [r['Ticker'] for r in resultados_tabla_ordenados]
                            fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['YoC_Bruto'] for r in resultados_tabla_ordenados], name='YoC Bruto', marker_color='#faca2b'))
                            fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['YoC_Neto'] for r in resultados_tabla_ordenados], name='YoC Neto', marker_color='#ff9800'))
                            fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['Yield_Act. Bruto'] for r in resultados_tabla_ordenados], name='Yield Act. Bruto', marker_color='#00d4ff'))
                            fig_yocs.add_trace(go.Bar(x=tickers_bars, y=[r['Yield_Act. Neto'] for r in resultados_tabla_ordenados], name='Yield Act. Neto', marker_color='#0088cc'))
                            fig_yocs.update_layout(barmode='group', template='plotly_dark', height=350, margin=dict(l=0, r=0, t=20, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
                            st.plotly_chart(fig_yocs, use_container_width=True)

                            df_divs_hist = pd.DataFrame({'Fecha': daily_net_divs.index, 'Dividendo': daily_net_divs.values})
                            df_divs_hist = df_divs_hist[df_divs_hist['Dividendo'] > 0]
                            if not df_divs_hist.empty:
                                st.divider()
                                st.markdown("#### 🗓️ Calendario Histórico de Dividendos Netos")
                                df_divs_hist['Año'], df_divs_hist['Mes'] = df_divs_hist['Fecha'].dt.year, df_divs_hist['Fecha'].dt.month
                                agrup_meses = df_divs_hist.groupby(['Año', 'Mes'])['Dividendo'].sum().reset_index()
                                anual_divs = df_divs_hist.groupby('Año')['Dividendo'].sum().reset_index()
                                anual_divs['Crec. YoY (%)'] = anual_divs['Dividendo'].pct_change() * 100

                                col_m1, col_m2 = st.columns([2.5, 1])
                                with col_m1:
                                    st.markdown("##### 📊 Ingresos Mensuales (Comparativa Anual)")
                                    fig_meses = go.Figure()
                                    meses_str = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                                    for año in sorted(agrup_meses['Año'].unique()):
                                        d_a = agrup_meses[agrup_meses['Año'] == año]
                                        fig_meses.add_trace(go.Bar(x=list(meses_str.values()), y=[d_a[d_a['Mes'] == m]['Dividendo'].values[0] if not d_a[d_a['Mes'] == m].empty else 0.0 for m in range(1, 13)], name=str(año)))
                                    fig_meses.update_layout(barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
                                    st.plotly_chart(fig_meses, use_container_width=True)
                                with col_m2:
                                    st.markdown("##### 📝 Resumen YoY")
                                    st.dataframe(anual_divs.style.format({'Dividendo': '{:,.2f} €', 'Crec. YoY (%)': '{:+.2f}%'}).map(lambda v: f"color: {'#21c354' if v>0 else ('#ff4b4b' if v<0 else '#aaaaaa')}; font-weight: bold;" if pd.notna(v) else "", subset=['Crec. YoY (%)']), use_container_width=True, hide_index=True)

                                st.markdown("<br>", unsafe_allow_html=True)
                                st.markdown("##### 📈 Evolución Anual (Efecto Bola de Nieve)")
                                fig_anual = go.Figure(go.Bar(x=anual_divs['Año'].astype(str), y=anual_divs['Dividendo'], name='Total Cobrado', marker_color='#00d4ff', text=[f"{val:,.2f} €" for val in anual_divs['Dividendo']], textposition='auto'))
                                fig_anual.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=350, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title="Dividendos Netos Totales (€)"))
                                st.plotly_chart(fig_anual, use_container_width=True)

                            st.divider()
                            st.markdown("#### 📊 Rentabilidad por Empresa en Euros (Precio vs Total con Divs)")
                            fig_comp = go.Figure()
                            x_t = [r['Ticker'] for r in resultados_tabla_ordenados]
                            y_rp = [r['Rent. Precio (€)'] for r in resultados_tabla_ordenados]
                            y_rt = [r['Rent. Total (€)'] for r in resultados_tabla_ordenados]
                            fig_comp.add_trace(go.Bar(x=x_t, y=y_rp, name='Solo Cotización (€)', marker_color=['#21c354' if r >= 0 else '#ff4b4b' for r in y_rp], text=[f"{v:+.1f}%" for v in y_rp], textposition='auto'))
                            fig_comp.add_trace(go.Bar(x=x_t, y=y_rt, name='Total (Cotización + Divs €)', marker_color='#00d4ff', text=[f"{v:+.1f}%" for v in y_rt], textposition='auto'))
                            fig_comp.update_layout(barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=400, hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
                            st.plotly_chart(fig_comp, use_container_width=True)

                        # ==========================================
                        # 2. RADIOGRAFÍA ANUAL (FOTO FIJA GLOBAL)
                        # ==========================================
                        st.divider()
                        st.markdown("### 📸 Radiografía del Año Natural (Toda la Cartera)")
                        st.markdown("> *Esta vista ignora los filtros de 'Modo Añada' de arriba. Muestra cómo se comportó **toda tu cartera real** desde el 1 de enero hasta el 31 de diciembre del año que selecciones.*")

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
                            daily_net_divs_g = (daily_shares_g.shift(1).fillna(0) * datos_dividendos[tickers_global]).sum(axis=1) * (1 - (impuesto_cart / 100.0))

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

                                def fmt_es(num, signo=False):
                                    if pd.isna(num): return "0,00"
                                    s = f"{num:+,.2f}" if signo else f"{num:,.2f}"
                                    return s.replace(",", "X").replace(".", ",").replace("X", ".")

                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric(f"Valor Base ({año_radio})", f"{fmt_es(base_pct)} €", f"Aportación nueva: {fmt_es(aportaciones, True)} €")
                                c2.metric("P/L de Mercado (Anual)", f"{fmt_es(b_mercado, True)} €", f"{(b_mercado/base_pct)*100:+.2f}%")
                                c3.metric("Dividendos Netos (Anual)", f"{fmt_es(div_tot)} €", f"{(div_tot/base_pct)*100:+.2f}% del Capital Base")
                                c4.metric("Beneficio Total (Anual)", f"{fmt_es(b_total, True)} €", f"{(b_total/base_pct)*100:+.2f}%")

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
                                    text_vals = [f"{fmt_es(v)} €" if v > 0 else "" for v in y_vals]

                                    fig_d = go.Figure(go.Bar(x=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'], y=y_vals, marker_color='#00d4ff', text=text_vals, textposition='auto'))
                                    fig_d.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0), height=300, yaxis_title="Dividendos Netos (€)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                                    st.plotly_chart(fig_d, use_container_width=True)
                                else:
                                    st.info(f"No se cobraron dividendos en {año_radio}.")
    except Exception as e:
        st.error(f"No se pudo procesar la cartera. Detalle: {e}")
