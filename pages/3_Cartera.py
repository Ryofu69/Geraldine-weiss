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
# PARSER Y LIMPIEZA UNIVERSAL DE NÚMEROS
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
        return df, None
    except Exception as e:
        return None, f"Error al procesar el formato: {e}"

# ==========================================
# GESTIÓN PERSISTENTE DE CARTERA (PLANTILLA NEUTRA)
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
    # Plantilla vacía sin ninguna posición real
    return "Fecha,Ticker,Operacion,Acciones,Precio\n"

def guardar_cartera_persistente(texto):
    try:
        with open(ARCHIVO_CARTERA, "w", encoding="utf-8") as f:
            f.write(texto.strip())
        return True
    except Exception:
        return False

# ==========================================
# TASAS DE CAMBIO A EUROS (FX EN VIVO)
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
# INTERFAZ Y PROCESAMIENTO
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

with st.expander("📁 Importación y Gestión de Operaciones", expanded=True):
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
    st.info("ℹ️ No hay operaciones registradas aún. Pega tus transacciones o sube un archivo para visualizar la cartera.")
else:
    with st.spinner("Conectando con mercados y analizando flujo de dividendos..."):
        tasas_fx = obtener_tasas_fx()
        
        tickers_unicos = df_operaciones['Ticker'].unique()
        cartera_consolidada = []
        
        for t in tickers_unicos:
            df_t = df_operaciones[df_operaciones['Ticker'] == t].sort_values('Fecha')
            titulos = 0.0
            coste_total_orig = 0.0
            
            for _, row in df_t.iterrows():
                if row['Operacion'].lower() == 'compra':
                    titulos += row['Acciones']
                    coste_total_orig += (row['Acciones'] * row['Precio'])
                elif row['Operacion'].lower() == 'venta':
                    if titulos > 0:
                        pmc_anterior = coste_total_orig / titulos
                        titulos -= row['Acciones']
                        coste_total_orig -= (row['Acciones'] * pmc_anterior)
                    titulos = max(0.0, titulos)

            if titulos > 0:
                pmc_orig = coste_total_orig / titulos
                cartera_consolidada.append({
                    'Ticker': t,
                    'Acciones': titulos,
                    'PMC_Orig': pmc_orig,
                    'Coste_Total_Orig': coste_total_orig
                })

        df_pos = pd.DataFrame(cartera_consolidada)

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
            
            df_final['YoC_Bruto'] = np.where(df_final['PMC_EUR'] > 0, (df_final['Div_Anual_EUR'] / df_final['PMC_EUR']) * 100.0, 0.0)
            df_final['YoC_Neto'] = df_final['YoC_Bruto'] * net_mult
            df_final['Yield_Actual_Bruto'] = np.where(df_final['Precio_EUR'] > 0, (df_final['Div_Anual_EUR'] / df_final['Precio_EUR']) * 100.0, 0.0)

            total_valor_cartera = df_final['Valor_Actual_EUR'].sum()
            total_coste_cartera = df_final['Coste_EUR'].sum()
            total_renta_neta_anual = df_final['Renta_Neta_Anual_EUR'].sum()
            total_renta_bruta_anual = df_final['Renta_Bruta_Anual_EUR'].sum()

            df_final['Peso_Capital_Pct'] = (df_final['Valor_Actual_EUR'] / total_valor_cartera) * 100.0 if total_valor_cartera > 0 else 0.0
            df_final['Peso_Renta_Pct'] = (df_final['Renta_Neta_Anual_EUR'] / total_renta_neta_anual) * 100.0 if total_renta_neta_anual > 0 else 0.0

            yoc_medio_ponderado_neto = (total_renta_neta_anual / total_coste_cartera * 100.0) if total_coste_cartera > 0 else 0.0
            plusvalia_global_eur = total_valor_cartera - total_coste_cartera
            plusvalia_global_pct = (plusvalia_global_eur / total_coste_cartera * 100.0) if total_coste_cartera > 0 else 0.0

            st.divider()
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            
            with col_k1:
                st.markdown(f"""
                <div class="card-dgi">
                    <span style="color: #aaa; font-size: 0.85rem;">💰 Valor Total de Cartera</span>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #00d4ff;">{total_valor_cartera:,.2f} €</div>
                    <span style="font-size: 0.85rem; color: #888;">Coste invertido: {total_coste_cartera:,.2f} €</span>
                </div>
                """, unsafe_allow_html=True)
            
            with col_k2:
                b_color_pl = "badge-verde" if plusvalia_global_eur >= 0 else "badge-rojo"
                st.markdown(f"""
                <div class="card-dgi">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="color: #aaa; font-size: 0.85rem;">📈 Plusvalía Latente</span>
                        <span class="{b_color_pl}">{plusvalia_global_pct:+.2f}%</span>
                    </div>
                    <div style="font-size: 1.8rem; font-weight: bold;">{plusvalia_global_eur:+,.2f} €</div>
                    <span style="font-size: 0.85rem; color: #888;">Sin contar dividendos cobrados</span>
                </div>
                """, unsafe_allow_html=True)

            with col_k3:
                renta_mensual = total_renta_neta_anual / 12.0
                st.markdown(f"""
                <div class="card-dgi">
                    <span style="color: #aaa; font-size: 0.85rem;">💵 Renta Pasiva Neta (Anual)</span>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #21c354;">{total_renta_neta_anual:,.2f} €</div>
                    <span class="badge-verde" style="font-size: 0.8rem;">~{renta_mensual:,.2f} € / mes limpios</span>
                </div>
                """, unsafe_allow_html=True)

            with col_k4:
                st.markdown(f"""
                <div class="card-dgi">
                    <span style="color: #aaa; font-size: 0.85rem;">⏳ Yield on Cost (YoC) Neto</span>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #faca2b;">{yoc_medio_ponderado_neto:.2f}%</div>
                    <span style="font-size: 0.85rem; color: #888;">Yield s/ Coste Bruto: {(total_renta_bruta_anual/total_coste_cartera)*100:.2f}%</span>
                </div>
                """, unsafe_allow_html=True)

            max_pos_cap = df_final.loc[df_final['Peso_Capital_Pct'].idxmax()]
            max_pos_div = df_final.loc[df_final['Peso_Renta_Pct'].idxmax()]
            
            avisos_riesgo = []
            if max_pos_cap['Peso_Capital_Pct'] > 5.0:
                avisos_riesgo.append(f"**{max_pos_cap['Ticker']}** supera el límite prudencial con un **{max_pos_cap['Peso_Capital_Pct']:.1f}% del capital**.")
            if max_pos_div['Peso_Renta_Pct'] > 10.0:
                avisos_riesgo.append(f"Alta dependencia: **{max_pos_div['Ticker']}** genera el **{max_pos_div['Peso_Renta_Pct']:.1f}% de tus dividendos netos**.")

            if avisos_riesgo:
                st.warning("⚠️ **Control de Concentración DGI:** " + " | ".join(avisos_riesgo))

            st.divider()
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("#### 🍩 Concentración de Capital vs. Rentas")
                fig_don = go.Figure()
                fig_don.add_trace(go.Pie(
                    labels=df_final['Ticker'], values=df_final['Renta_Neta_Anual_EUR'],
                    name="Flujo Dividendos", hole=0.55, textinfo='label+percent',
                    marker=dict(line=dict(color='#000000', width=1))
                ))
                fig_don.update_layout(
                    template='plotly_dark', margin=dict(l=0, r=0, t=10, b=10), height=320,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    showlegend=False
                )
                st.plotly_chart(fig_don, use_container_width=True)

            with col_g2:
                st.markdown("#### 🚀 Yield on Cost (YoC) vs Yield Actual")
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=df_final['Ticker'], y=df_final['YoC_Neto'],
                    name='YoC Neto (s/ Compra)', marker_color='#faca2b'
                ))
                fig_bar.add_trace(go.Bar(
                    x=df_final['Ticker'], y=df_final['Yield_Actual_Bruto'] * net_mult,
                    name='Yield Actual Neto', marker_color='#00d4ff'
                ))
                fig_bar.update_layout(
                    barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=10, b=10), height=320,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            st.divider()
            st.subheader("📋 Desglose Individual de Posiciones")

            df_tabla = df_final[[
                'Ticker', 'Nombre', 'Acciones', 'PMC_EUR', 'Precio_EUR',
                'Coste_EUR', 'Valor_Actual_EUR', 'Plusvalia_Pct',
                'Renta_Neta_Anual_EUR', 'YoC_Neto', 'Yield_Actual_Bruto',
                'Peso_Capital_Pct', 'Peso_Renta_Pct'
            ]].copy()

            df_tabla = df_tabla.sort_values(by='Valor_Actual_EUR', ascending=False)

            def formato_posiciones(row):
                styles = [''] * len(row)
                for idx, col in enumerate(row.index):
                    if col == 'Plusvalia_Pct':
                        val = row['Plusvalia_Pct']
                        styles[idx] = 'color: #21c354; font-weight: bold;' if val >= 0 else 'color: #ff4b4b; font-weight: bold;'
                    elif col == 'YoC_Neto':
                        styles[idx] = 'color: #faca2b; font-weight: bold;'
                    elif col == 'Renta_Neta_Anual_EUR':
                        styles[idx] = 'color: #21c354;'
                    elif col in ['Peso_Capital_Pct', 'Peso_Renta_Pct']:
                        if (col == 'Peso_Capital_Pct' and row[col] > 5.0) or (col == 'Peso_Renta_Pct' and row[col] > 10.0):
                            styles[idx] = 'color: #ff4b4b; font-weight: bold;'
                return styles

            df_display = df_tabla.copy()
            df_display['Acciones'] = df_display['Acciones'].apply(lambda x: f"{x:,.2f}".rstrip('0').rstrip('.'))
            df_display['PMC_EUR'] = df_display['PMC_EUR'].apply(lambda x: f"{x:.2f} €")
            df_display['Precio_EUR'] = df_display['Precio_EUR'].apply(lambda x: f"{x:.2f} €")
            df_display['Coste_EUR'] = df_display['Coste_EUR'].apply(lambda x: f"{x:,.2f} €")
            df_display['Valor_Actual_EUR'] = df_display['Valor_Actual_EUR'].apply(lambda x: f"{x:,.2f} €")
            df_display['Plusvalia_Pct'] = df_display['Plusvalia_Pct'].apply(lambda x: f"{x:+.2f}%")
            df_display['Renta_Neta_Anual_EUR'] = df_display['Renta_Neta_Anual_EUR'].apply(lambda x: f"{x:,.2f} €")
            df_display['YoC_Neto'] = df_display['YoC_Neto'].apply(lambda x: f"{x:.2f}%")
            df_display['Yield_Actual_Bruto'] = df_display['Yield_Actual_Bruto'].apply(lambda x: f"{x:.2f}%")
            df_display['Peso_Capital_Pct'] = df_display['Peso_Capital_Pct'].apply(lambda x: f"{x:.1f}%")
            df_display['Peso_Renta_Pct'] = df_display['Peso_Renta_Pct'].apply(lambda x: f"{x:.1f}%")

            styled_tabla = df_tabla.style.apply(formato_posiciones, axis=1)
            st.dataframe(
                df_display.set_index('Ticker'),
                use_container_width=True
            )

            csv_export = df_tabla.to_csv(index=False, sep=';', decimal=',').encode('utf-8')
            st.download_button(
                label="💾 Descargar Resumen de Cartera en CSV",
                data=csv_export,
                file_name=f"Cartera_DGI_Consolidada_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No se han encontrado posiciones abiertas activas tras procesar las operaciones.")
