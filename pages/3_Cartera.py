import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import io
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Control de Cartera DGI", page_icon="💼", layout="wide")

ARCHIVO_CARTERA = "cartera.csv"

# ==========================================
# PARSER UNIVERSAL (COMAS, PUNTOS Y EXCEL)
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

def procesar_texto_o_archivo(contenido):
    try:
        if not contenido or not str(contenido).strip():
            return None, None

        if isinstance(contenido, str):
            stream = io.StringIO(contenido.strip())
        else:
            stream = io.BytesIO(contenido.read())

        df_raw = pd.read_csv(stream, sep=None, engine='python', dtype=str)
        if df_raw.empty:
            return None, None

        column_map = {}
        for col in df_raw.columns:
            c_norm = col.strip().lower()
            if 'fech' in c_norm: column_map[col] = 'Fecha'
            elif 'tick' in c_norm or 'empresa' in c_norm: column_map[col] = 'Ticker'
            elif 'oper' in c_norm or 'tipo' in c_norm: column_map[col] = 'Operacion'
            elif 'acc' in c_norm or 'cant' in c_norm or 'titul' in c_norm: column_map[col] = 'Acciones'
            elif 'prec' in c_norm or 'cost' in c_norm: column_map[col] = 'Precio'

        df = df_raw.rename(columns=column_map)
        cols_necesarias = ['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio']
        
        for c in cols_necesarias:
            if c not in df.columns:
                return None, f"Falta la columna obligatoria '{c}' en los datos pegados o subidos."

        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
        df['Operacion'] = df['Operacion'].astype(str).str.strip().str.capitalize()
        
        df['Acciones'] = df['Acciones'].apply(limpiar_numero_europeo)
        df['Precio'] = df['Precio'].apply(limpiar_numero_europeo)
        df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')
        
        df = df.dropna(subset=['Fecha', 'Ticker'])
        df = df[df['Acciones'] > 0]
        if not df.empty:
            df['Año'] = df['Fecha'].dt.year.astype(int)
        return df, None
    except Exception as e:
        return None, f"Error al procesar el formato: {e}"

# ==========================================
# GESTIÓN PERSISTENTE (PLANTILLA NEUTRA)
# ==========================================
def cargar_cartera_persistente():
    if os.path.exists(ARCHIVO_CARTERA):
        try:
            with open(ARCHIVO_CARTERA, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return contenido
        except Exception:
            pass
    return "Fecha,Ticker,Operacion,Acciones,Precio\n"

def guardar_cartera_persistente(texto):
    try:
        with open(ARCHIVO_CARTERA, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# ==========================================
# FX EN VIVO
# ==========================================
@st.cache_data(ttl=3600)
def obtener_tasas_fx():
    tasas = {'EUR': 1.0, 'USD': 0.92, 'GBP': 1.17, 'GBp': 0.0117}
    try:
        eur_usd = yf.Ticker('EURUSD=X').history(period='5d')
        if not eur_usd.empty:
            tasas['USD'] = 1.0 / eur_usd['Close'].iloc[-1]
        eur_gbp = yf.Ticker('EURGBP=X').history(period='5d')
        if not eur_gbp.empty:
            tasas['GBP'] = 1.0 / eur_gbp['Close'].iloc[-1]
            tasas['GBp'] = tasas['GBP'] / 100.0
    except Exception: pass
    return tasas

# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================
st.title("💼 Control y Rendimiento de Cartera DGI")

st.markdown("""
<style>
.card-dgi {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 12px;
}
.badge-verde { background: rgba(33, 195, 84, 0.2); color: #21c354; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
.badge-rojo { background: rgba(255, 75, 75, 0.2); color: #ff4b4b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
.badge-ambar { background: rgba(250, 202, 43, 0.2); color: #faca2b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

with st.expander("📁 Importación y Gestión de Operaciones", expanded=False):
    modo_carga = st.radio("Método de entrada:", ["📝 Pegar / Editar Texto", "📂 Subir Archivo CSV o Excel"], horizontal=True)
    contenido_texto = cargar_cartera_persistente()
    
    if modo_carga == "📝 Pegar / Editar Texto":
        raw_input = st.text_area("Pega tus operaciones con comas, puntos o tabuladores:", value=contenido_texto, height=140)
        col_g1, _ = st.columns([1, 4])
        with col_g1:
            if st.button("💾 Guardar Localmente"):
                if guardar_cartera_persistente(raw_input):
                    st.success("Guardado localmente.")
                else:
                    st.error("Error al guardar.")
        df_operaciones, err = procesar_texto_o_archivo(raw_input)
    else:
        uploaded_file = st.file_uploader("Selecciona tu archivo de operaciones", type=['csv', 'xlsx', 'txt'])
        if uploaded_file is not None:
            if uploaded_file.name.endswith('.xlsx'):
                try:
                    df_raw = pd.read_excel(uploaded_file, dtype=str)
                    csv_buf = io.StringIO()
                    df_raw.to_csv(csv_buf, index=False)
                    df_operaciones, err = procesar_texto_o_archivo(csv_buf.getvalue())
                except Exception as e:
                    df_operaciones, err = None, f"Error al leer Excel: {e}."
            else:
                df_operaciones, err = procesar_texto_o_archivo(uploaded_file)
        else:
            df_operaciones, err = procesar_texto_o_archivo(contenido_texto)

retencion_pct = st.number_input("Retención media IRPF / Doble Imposición (%)", value=19.0, step=0.5, key="ret_cart")
net_mult = 1.0 - (retencion_pct / 100.0)

if err:
    st.error(f"⚠️ {err}")
elif df_operaciones is None or df_operaciones.empty:
    st.info("ℹ️ No hay operaciones registradas aún. Pega tus transacciones en el cuadro superior o sube un archivo para visualizar la cartera.")
else:
    # ==========================================
    # FILTROS ANALÍTICOS (AÑADA Y EMPRESA)
    # ==========================================
    st.markdown("### 🎯 Filtros Analíticos de Cartera")
    col_f1, col_f2 = st.columns(2)
    
    años_disponibles = sorted(df_operaciones['Año'].unique().tolist(), reverse=True)
    opciones_años = ["Todo el Historial"] + [str(a) for a in años_disponibles]
    
    with col_f1:
        año_filtro = st.selectbox("📅 Selecciona Año de Compra (Modo Añada):", opciones_años, index=0)
    
    tickers_todos = sorted(df_operaciones['Ticker'].unique().tolist())
    with col_f2:
        empresa_filtro = st.selectbox("🏢 Selecciona Empresa a Inspeccionar:", ["Todas las Empresas"] + tickers_todos, index=0)

    # Filtrar operaciones según selección
    df_filtradas = df_operaciones.copy()
    if año_filtro != "Todo el Historial":
        df_filtradas = df_filtradas[df_filtradas['Año'] == int(año_filtro)]
    if empresa_filtro != "Todas las Empresas":
        df_filtradas = df_filtradas[df_filtradas['Ticker'] == empresa_filtro]

    if df_filtradas.empty:
        st.warning(f"No se encontraron operaciones para el filtro seleccionado ({año_filtro} | {empresa_filtro}).")
    else:
        with st.spinner("Descargando precios actuales y dividendos..."):
            tasas_fx = obtener_tasas_fx()
            
            # Consolidar compras y ventas de la selección
            posiciones = []
            for t in df_filtradas['Ticker'].unique():
                df_t = df_filtradas[df_filtradas['Ticker'] == t].sort_values('Fecha')
                titulos = 0.0
                coste_total_orig = 0.0
                
                for _, row in df_t.iterrows():
                    if row['Operacion'].lower() == 'compra':
                        titulos += row['Acciones']
                        coste_total_orig += (row['Acciones'] * row['Precio'])
                    elif row['Operacion'].lower() == 'venta':
                        if titulos > 0:
                            pmc_ant = coste_total_orig / titulos
                            titulos -= row['Acciones']
                            coste_total_orig -= (row['Acciones'] * pmc_ant)
                        titulos = max(0.0, titulos)

                if titulos > 0:
                    pmc_orig = coste_total_orig / titulos
                    posiciones.append({
                        'Ticker': t,
                        'Acciones': titulos,
                        'PMC_Orig': pmc_orig,
                        'Coste_Total_Orig': coste_total_orig
                    })

            df_pos = pd.DataFrame(posiciones)

            if not df_pos.empty:
                datos_mercado = []
                for t in df_pos['Ticker']:
                    try:
                        info = yf.Ticker(t).info
                        curr = info.get('currency', 'USD')
                        precio_orig = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
                        if precio_orig == 0.0:
                            hist = yf.Ticker(t).history(period='5d')
                            if not hist.empty: precio_orig = hist['Close'].iloc[-1]

                        div_rate_orig = info.get('dividendRate', info.get('trailingAnnualDividendRate', 0.0))
                        if div_rate_orig is None or div_rate_orig == 0.0:
                            divs = yf.Ticker(t).dividends
                            if not divs.empty:
                                div_rate_orig = divs.tail(4).sum() if len(divs) >= 4 else divs.iloc[-1] * 4

                        datos_mercado.append({
                            'Ticker': t,
                            'Moneda': curr,
                            'Precio_Actual_Orig': precio_orig,
                            'Div_Anual_Orig': div_rate_orig if div_rate_orig is not None else 0.0,
                            'Nombre': info.get('shortName', t)
                        })
                    except Exception:
                        datos_mercado.append({
                            'Ticker': t, 'Moneda': 'USD', 'Precio_Actual_Orig': 0.0, 'Div_Anual_Orig': 0.0, 'Nombre': t
                        })

                df_mkt = pd.DataFrame(datos_mercado)
                df_final = pd.merge(df_pos, df_mkt, on='Ticker')

                def fx(moneda): return tasas_fx.get(moneda, 1.0)
                
                df_final['FX_Rate'] = df_final['Moneda'].apply(fx)
                df_final['PMC_EUR'] = df_final['PMC_Orig'] * df_final['FX_Rate']
                df_final['Precio_EUR'] = df_final['Precio_Actual_Orig'] * df_final['FX_Rate']
                df_final['Coste_EUR'] = df_final['Acciones'] * df_final['PMC_EUR']
                df_final['Valor_Actual_EUR'] = df_final['Acciones'] * df_final['Precio_EUR']
                df_final['Plusvalia_EUR'] = df_final['Valor_Actual_EUR'] - df_final['Coste_EUR']
                df_final['Plusvalia_Pct'] = np.where(df_final['Coste_EUR'] > 0, (df_final['Plusvalia_EUR'] / df_final['Coste_EUR']) * 100.0, 0.0)

                df_final['Div_Anual_EUR'] = df_final['Div_Anual_Orig'] * df_final['FX_Rate']
                df_final['Renta_Bruta_Anual_EUR'] = df_final['Acciones'] * df_final['Div_Anual_EUR']
                df_final['Renta_Neta_Anual_EUR'] = df_final['Renta_Bruta_Anual_EUR'] * net_mult
                
                # Rendimientos Brutos y Netos
                df_final['YoC_Bruto'] = np.where(df_final['PMC_EUR'] > 0, (df_final['Div_Anual_EUR'] / df_final['PMC_EUR']) * 100.0, 0.0)
                df_final['YoC_Neto'] = df_final['YoC_Bruto'] * net_mult
                df_final['Yield_Actual_Bruto'] = np.where(df_final['Precio_EUR'] > 0, (df_final['Div_Anual_EUR'] / df_final['Precio_EUR']) * 100.0, 0.0)
                df_final['Yield_Actual_Neto'] = df_final['Yield_Actual_Bruto'] * net_mult

                total_valor = df_final['Valor_Actual_EUR'].sum()
                total_coste = df_final['Coste_EUR'].sum()
                total_renta_neta = df_final['Renta_Neta_Anual_EUR'].sum()
                total_renta_bruta = df_final['Renta_Bruta_Anual_EUR'].sum()

                df_final['Peso_Capital_Pct'] = (df_final['Valor_Actual_EUR'] / total_valor) * 100.0 if total_valor > 0 else 0.0
                df_final['Peso_Renta_Pct'] = (df_final['Renta_Neta_Anual_EUR'] / total_renta_neta) * 100.0 if total_renta_neta > 0 else 0.0

                yoc_medio_bruto = (total_renta_bruta / total_coste * 100.0) if total_coste > 0 else 0.0
                yoc_medio_neto = (total_renta_neta / total_coste * 100.0) if total_coste > 0 else 0.0
                yield_act_medio_bruto = (total_renta_bruta / total_valor * 100.0) if total_valor > 0 else 0.0
                yield_act_medio_neto = (total_renta_neta / total_valor * 100.0) if total_valor > 0 else 0.0

                plusvalia_eur = total_valor - total_coste
                plusvalia_pct = (plusvalia_eur / total_coste * 100.0) if total_coste > 0 else 0.0

                # ==========================================
                # KPIS DINÁMICOS
                # ==========================================
                subtitulo = f"Resultados para Añada: **{año_filtro}**" if año_filtro != "Todo el Historial" else "Resultados de **Todo el Historial**"
                if empresa_filtro != "Todas las Empresas":
                    subtitulo += f" | Empresa: **{empresa_filtro}**"
                st.caption(subtitulo)

                col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
                with col_k1:
                    st.markdown(f"""
                    <div class="card-dgi">
                        <span style="color: #aaa; font-size: 0.85rem;">💰 Valor Seleccionado</span>
                        <div style="font-size: 1.6rem; font-weight: bold; color: #00d4ff;">{total_valor:,.2f} €</div>
                        <span style="font-size: 0.8rem; color: #888;">Coste: {total_coste:,.2f} €</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_k2:
                    b_color_pl = "badge-verde" if plusvalia_eur >= 0 else "badge-rojo"
                    st.markdown(f"""
                    <div class="card-dgi">
                        <div style="display: flex; justify-content: space-between; align-items: baseline;">
                            <span style="color: #aaa; font-size: 0.85rem;">📈 Plusvalía</span>
                            <span class="{b_color_pl}">{plusvalia_pct:+.2f}%</span>
                        </div>
                        <div style="font-size: 1.6rem; font-weight: bold;">{plusvalia_eur:+,.2f} €</div>
                        <span style="font-size: 0.8rem; color: #888;">Revalorización neta</span>
                    </div>
                    """, unsafe_allow_html=True)

                with col_k3:
                    renta_mes = total_renta_neta / 12.0
                    st.markdown(f"""
                    <div class="card-dgi">
                        <span style="color: #aaa; font-size: 0.85rem;">💵 Renta Anual</span>
                        <div style="font-size: 1.6rem; font-weight: bold; color: #21c354;">{total_renta_neta:,.2f} € <span style="font-size:0.8rem; color:#aaa;">Netos</span></div>
                        <span style="font-size: 0.8rem; color: #888;">Bruto: {total_renta_bruta:,.2f} € (~{renta_mes:,.2f}€/m)</span>
                    </div>
                    """, unsafe_allow_html=True)

                with col_k4:
                    st.markdown(f"""
                    <div class="card-dgi">
                        <span style="color: #aaa; font-size: 0.85rem;">⏳ Yield on Cost (YoC)</span>
                        <div style="font-size: 1.6rem; font-weight: bold; color: #faca2b;">{yoc_medio_neto:.2f}% <span style="font-size:0.8rem; color:#aaa;">Neto</span></div>
                        <span style="font-size: 0.8rem; color: #888;">YoC Bruto: <b>{yoc_medio_bruto:.2f}%</b></span>
                    </div>
                    """, unsafe_allow_html=True)

                with col_k5:
                    st.markdown(f"""
                    <div class="card-dgi">
                        <span style="color: #aaa; font-size: 0.85rem;">📊 Yield Mercado Hoy</span>
                        <div style="font-size: 1.6rem; font-weight: bold; color: #00d4ff;">{yield_act_medio_neto:.2f}% <span style="font-size:0.8rem; color:#aaa;">Neto</span></div>
                        <span style="font-size: 0.8rem; color: #888;">Yield Bruto: <b>{yield_act_medio_bruto:.2f}%</b></span>
                    </div>
                    """, unsafe_allow_html=True)

                # ==========================================
                # SECCIÓN 1: GRÁFICOS CUANDO SE ELIGE UN AÑO
                # ==========================================
                if año_filtro != "Todo el Historial":
                    st.divider()
                    st.subheader(f"📊 Análisis Gráfico de la Añada {año_filtro}")
                    col_a1, col_a2 = st.columns(2)

                    with col_a1:
                        st.markdown(f"#### 💰 Coste Invertido vs. Valor Actual Hoy ({año_filtro})")
                        fig_cap = go.Figure()
                        fig_cap.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Coste_EUR'],
                            name=f'Invertido en {año_filtro} (€)', marker_color='#9c27b0'
                        ))
                        fig_cap.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Valor_Actual_EUR'],
                            name='Valor Actual Hoy (€)', marker_color='#00d4ff'
                        ))
                        fig_cap.update_layout(
                            template='plotly_dark', barmode='group', height=360,
                            margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig_cap, use_container_width=True)

                    with col_a2:
                        st.markdown("#### 🚀 Rendimientos DGI: YoC vs. Yield Actual (Bruto y Neto)")
                        fig_y = go.Figure()
                        fig_y.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['YoC_Bruto'],
                            name='YoC Bruto', marker_color='#faca2b'
                        ))
                        fig_y.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['YoC_Neto'],
                            name='YoC Neto', marker_color='#ff9800'
                        ))
                        fig_y.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Yield_Actual_Bruto'],
                            name='Yield Act. Bruto', marker_color='#00d4ff'
                        ))
                        fig_y.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Yield_Actual_Neto'],
                            name='Yield Act. Neto', marker_color='#0088cc'
                        ))
                        fig_y.update_layout(
                            template='plotly_dark', barmode='group', height=360,
                            margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            yaxis=dict(title="Rendimiento (%)"),
                            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig_y, use_container_width=True)

                # ==========================================
                # SECCIÓN 2: GRÁFICOS CUANDO SE VE TODO EL HISTORIAL
                # ==========================================
                elif año_filtro == "Todo el Historial" and empresa_filtro == "Todas las Empresas":
                    if len(años_disponibles) > 1:
                        st.divider()
                        st.subheader("📆 Rendimiento y Yield on Cost por Año de Compra (Añadas)")
                        
                        añadas_data = []
                        for a in sorted(años_disponibles):
                            df_a = df_operaciones[df_operaciones['Año'] == a]
                            c_añada = 0.0
                            v_añada = 0.0
                            r_neta_añada = 0.0
                            r_bruta_añada = 0.0
                            
                            for t in df_a['Ticker'].unique():
                                sub = df_a[df_a['Ticker'] == t]
                                acc_a = sub[sub['Operacion'].str.lower() == 'compra']['Acciones'].sum() - sub[sub['Operacion'].str.lower() == 'venta']['Acciones'].sum()
                                if acc_a > 0:
                                    row_match = df_final[df_final['Ticker'] == t]
                                    fx_t = row_match['FX_Rate'].iloc[0] if not row_match.empty else 1.0
                                    
                                    coste_pos = 0.0
                                    for _, r_op in sub.iterrows():
                                        if r_op['Operacion'].lower() == 'compra':
                                            coste_pos += r_op['Acciones'] * r_op['Precio'] * fx_t
                                            
                                    if not row_match.empty:
                                        pr_e = row_match['Precio_EUR'].iloc[0]
                                        div_e = row_match['Div_Anual_EUR'].iloc[0]
                                        
                                        val_pos = acc_a * pr_e
                                        r_b_pos = acc_a * div_e
                                        r_n_pos = r_b_pos * net_mult
                                        
                                        c_añada += coste_pos
                                        v_añada += val_pos
                                        r_bruta_añada += r_b_pos
                                        r_neta_añada += r_n_pos
                            
                            if c_añada > 0:
                                yoc_b_añada = (r_bruta_añada / c_añada) * 100.0
                                yoc_n_añada = (r_neta_añada / c_añada) * 100.0
                                plusv_añada = ((v_añada - c_añada) / c_añada) * 100.0
                                añadas_data.append({
                                    'Año': str(a),
                                    'Invertido_EUR': c_añada,
                                    'Valor_Hoy_EUR': v_añada,
                                    'YoC_Bruto': yoc_b_añada,
                                    'YoC_Neto': yoc_n_añada,
                                    'Plusvalia_Pct': plusv_añada
                                })

                        if añadas_data:
                            df_añadas = pd.DataFrame(añadas_data)
                            fig_añadas = go.Figure()
                            fig_añadas.add_trace(go.Bar(
                                x=df_añadas['Año'], y=df_añadas['Invertido_EUR'],
                                name='Coste Invertido (€)', marker_color='#9c27b0'
                            ))
                            fig_añadas.add_trace(go.Bar(
                                x=df_añadas['Año'], y=df_añadas['Valor_Hoy_EUR'],
                                name='Valor Actual (€)', marker_color='#00d4ff'
                            ))
                            fig_añadas.add_trace(go.Scatter(
                                x=df_añadas['Año'], y=df_añadas['YoC_Bruto'],
                                name='YoC Bruto (%)', mode='lines+markers',
                                line=dict(color='#faca2b', width=3),
                                yaxis='y2'
                            ))
                            fig_añadas.add_trace(go.Scatter(
                                x=df_añadas['Año'], y=df_añadas['YoC_Neto'],
                                name='YoC Neto (%)', mode='lines+markers+text',
                                text=[f"{v:.1f}%" for v in df_añadas['YoC_Neto']],
                                textposition="top center", line=dict(color='#ff9800', width=3, dash='dot'),
                                yaxis='y2'
                            ))
                            fig_añadas.update_layout(
                                template='plotly_dark', barmode='group', height=360,
                                margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                yaxis=dict(title="Euros (€)"),
                                yaxis2=dict(title="YoC (%)", overlaying='y', side='right', showgrid=False),
                                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                            )
                            st.plotly_chart(fig_añadas, use_container_width=True)

                    st.divider()
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        st.markdown("#### 🍩 Distribución de Renta Neta por Empresa")
                        fig_don = go.Figure()
                        fig_don.add_trace(go.Pie(
                            labels=df_final['Ticker'], values=df_final['Renta_Neta_Anual_EUR'],
                            hole=0.55, textinfo='label+percent'
                        ))
                        fig_don.update_layout(
                            template='plotly_dark', margin=dict(l=0, r=0, t=10, b=10), height=340,
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
                        )
                        st.plotly_chart(fig_don, use_container_width=True)

                    with col_g2:
                        st.markdown("#### 🚀 YoC vs. Yield Actual (Bruto y Neto) Global")
                        fig_y_all = go.Figure()
                        fig_y_all.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['YoC_Bruto'],
                            name='YoC Bruto', marker_color='#faca2b'
                        ))
                        fig_y_all.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['YoC_Neto'],
                            name='YoC Neto', marker_color='#ff9800'
                        ))
                        fig_y_all.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Yield_Actual_Bruto'],
                            name='Yield Act. Bruto', marker_color='#00d4ff'
                        ))
                        fig_y_all.add_trace(go.Bar(
                            x=df_final['Ticker'], y=df_final['Yield_Actual_Neto'],
                            name='Yield Act. Neto', marker_color='#0088cc'
                        ))
                        fig_y_all.update_layout(
                            template='plotly_dark', barmode='group', height=340,
                            margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            yaxis=dict(title="Rendimiento (%)"),
                            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5)
                        )
                        st.plotly_chart(fig_y_all, use_container_width=True)

                # ==========================================
                # HISTORIAL DE OPERACIONES FILTRADAS
                # ==========================================
                if empresa_filtro != "Todas las Empresas" or año_filtro != "Todo el Historial":
                    st.divider()
                    st.subheader("📜 Operaciones Realizadas en esta Selección")
                    df_ops_vista = df_filtradas[['Fecha', 'Ticker', 'Operacion', 'Acciones', 'Precio']].sort_values('Fecha', ascending=False).copy()
                    df_ops_vista['Fecha'] = df_ops_vista['Fecha'].dt.strftime('%d/%m/%Y')
                    st.dataframe(df_ops_vista, use_container_width=True)

                # ==========================================
                # TABLA DETALLADA DE POSICIONES
                # ==========================================
                st.divider()
                st.subheader("📋 Desglose Detallado de Posiciones")

                df_tabla = df_final[[
                    'Ticker', 'Nombre', 'Acciones', 'PMC_EUR', 'Precio_EUR',
                    'Coste_EUR', 'Valor_Actual_EUR', 'Plusvalia_Pct',
                    'Renta_Bruta_Anual_EUR', 'Renta_Neta_Anual_EUR',
                    'YoC_Bruto', 'YoC_Neto',
                    'Yield_Actual_Bruto', 'Yield_Actual_Neto',
                    'Peso_Capital_Pct', 'Peso_Renta_Pct'
                ]].copy()

                df_tabla = df_tabla.sort_values(by='Valor_Actual_EUR', ascending=False)

                df_display = df_tabla.copy()
                df_display['Acciones'] = df_display['Acciones'].apply(lambda x: f"{x:,.2f}".rstrip('0').rstrip('.'))
                df_display['PMC_EUR'] = df_display['PMC_EUR'].apply(lambda x: f"{x:.2f} €")
                df_display['Precio_EUR'] = df_display['Precio_EUR'].apply(lambda x: f"{x:.2f} €")
                df_display['Coste_EUR'] = df_display['Coste_EUR'].apply(lambda x: f"{x:,.2f} €")
                df_display['Valor_Actual_EUR'] = df_display['Valor_Actual_EUR'].apply(lambda x: f"{x:,.2f} €")
                df_display['Plusvalia_Pct'] = df_display['Plusvalia_Pct'].apply(lambda x: f"{x:+.2f}%")
                df_display['Renta_Bruta_Anual_EUR'] = df_display['Renta_Bruta_Anual_EUR'].apply(lambda x: f"{x:,.2f} €")
                df_display['Renta_Neta_Anual_EUR'] = df_display['Renta_Neta_Anual_EUR'].apply(lambda x: f"{x:,.2f} €")
                df_display['YoC_Bruto'] = df_display['YoC_Bruto'].apply(lambda x: f"{x:.2f}%")
                df_display['YoC_Neto'] = df_display['YoC_Neto'].apply(lambda x: f"{x:.2f}%")
                df_display['Yield_Actual_Bruto'] = df_display['Yield_Actual_Bruto'].apply(lambda x: f"{x:.2f}%")
                df_display['Yield_Actual_Neto'] = df_display['Yield_Actual_Neto'].apply(lambda x: f"{x:.2f}%")
                df_display['Peso_Capital_Pct'] = df_display['Peso_Capital_Pct'].apply(lambda x: f"{x:.1f}%")
                df_display['Peso_Renta_Pct'] = df_display['Peso_Renta_Pct'].apply(lambda x: f"{x:.1f}%")

                st.dataframe(
                    df_display.set_index('Ticker'),
                    use_container_width=True
                )

                csv_export = df_tabla.to_csv(index=False, sep=';', decimal=',').encode('utf-8')
                st.download_button(
                    label="💾 Descargar Resumen en CSV",
                    data=csv_export,
                    file_name=f"Cartera_DGI_Seleccion_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("No se han encontrado posiciones abiertas activas tras procesar las operaciones de esta selección.")
