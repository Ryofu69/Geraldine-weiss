import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings

# Ignorar advertencias menores
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Radar Watchlist - Weiss DGI", page_icon="📡", layout="wide")

# ==========================================
# FUNCIÓN DE ANÁLISIS RÁPIDO PARA RADAR
# ==========================================
def analizar_empresa_rapido(ticker_symbol, años_analisis, impuesto_pct):
    try:
        ticker = yf.Ticker(ticker_symbol.strip().upper())
        info = ticker.info
        
        def get_safe(key, default=0.0):
            val = info.get(key)
            if val is None: return default
            try: return float(val)
            except (ValueError, TypeError): return default
            
        dividendos = ticker.dividends
        historial = ticker.history(period="15y", auto_adjust=False)
        
        if dividendos.empty or len(historial) < 252: 
            return None

        historial.index = historial.index.tz_localize(None).normalize()
        dividendos.index = dividendos.index.tz_localize(None).normalize()

        fecha_corte = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis)
        ha = historial[historial.index >= fecha_corte].copy()
        if ha.empty: 
            return None

        # Parámetros sectoriales
        sector_en = info.get('sector', '')
        industry_en = info.get('industry', '')
        es_regulada = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower() or 'reit' in industry_en.lower() or 'real estate' in sector_en.lower()
        es_tech = 'technology' in sector_en.lower() or 'software' in industry_en.lower()
        es_fin_ind = ('financial' in sector_en.lower() or 'bank' in industry_en.lower() or 
                      'industrial' in sector_en.lower() or 'basic materials' in sector_en.lower())
        es_defensivo = 'consumer defensive' in sector_en.lower() or 'healthcare' in sector_en.lower()
        
        es_telecom = 'communication' in sector_en.lower() or 'telecom' in industry_en.lower()
        es_utility_pura = 'utility' in sector_en.lower() or 'utilities' in sector_en.lower()

        payout_lim_bpa = 80.0 if es_regulada else 60.0
        payout_ama_bpa = 85.0 if es_regulada else 75.0
        payout_lim_fcf = 85.0 if es_regulada else 75.0
        payout_ama_fcf = 92.0 if es_regulada else 85.0

        precio_actual = ha['Close'].dropna().iloc[-1]
        divs_por_año = dividendos.groupby(dividendos.index.year).sum()
        año_actual = datetime.now().year
        
        forward_dividend = get_safe('dividendRate', get_safe('trailingAnnualDividendRate'))
        if forward_dividend == 0 and not dividendos.empty:
            ultimo_año_completo = divs_por_año.iloc[-2] if len(divs_por_año) > 1 else 0
            forward_dividend = max(dividendos.iloc[-1] * 4, ultimo_año_completo)

        currency = info.get('currency', 'USD')
        divisor_uk = 1.0
        if currency == 'GBp': divisor_uk = 100.0

        if currency == 'GBp' and forward_dividend > 0:
            if forward_dividend < (precio_actual / 10): forward_dividend *= 100

        dividendos_barras = divs_por_año.copy()
        if año_actual in dividendos_barras.index:
            dividendos_barras[año_actual] = max(dividendos_barras[año_actual], forward_dividend)

        ha['Year'] = ha.index.year
        ha['Div_Anual'] = ha['Year'].map(divs_por_año)
        ha.loc[ha['Year'] == año_actual, 'Div_Anual'] = forward_dividend
        ha['Div_Anual'] = ha['Div_Anual'].bfill().ffill()

        ha['Yield_Diario'] = (ha['Div_Anual'] / ha['Close']) * 100
        yields_validos = ha['Yield_Diario'].dropna()
        yields_validos = yields_validos[yields_validos > 0]

        yield_infravalorado = yields_validos.quantile(0.95)
        yield_sobrevalorado = yields_validos.quantile(0.05)
        yield_medio = yields_validos.mean()

        precio_compra = (forward_dividend / yield_infravalorado) * 100 if yield_infravalorado > 0 else 0
        precio_justo = (forward_dividend / yield_medio) * 100 if yield_medio > 0 else 0
        precio_venta = (forward_dividend / yield_sobrevalorado) * 100 if yield_sobrevalorado > 0 else 0

        yield_actual = (forward_dividend / precio_actual) * 100
        yield_neto = yield_actual * (1 - (impuesto_pct / 100))
        div_neto_absoluto = forward_dividend * (1 - (impuesto_pct / 100))

        # Extracción de métricas fundamentales
        payout_bpa = get_safe('payoutRatio') * 100
        fcf = get_safe('freeCashflow')
        shares = get_safe('sharesOutstanding')
        total_debt = get_safe('totalDebt', 0.0)
        total_cash = get_safe('totalCash', 0.0)
        ebitda = get_safe('ebitda', 0.0)
        per = get_safe('trailingPE', get_safe('forwardPE'))
        pb = get_safe('priceToBook', -1.0)

        # Deuda Neta / EBITDA Operativa
        deuda_neta = max(0.0, total_debt - total_cash)
        if ebitda > 0:
            deuda_ebitda = deuda_neta / ebitda
        else:
            deuda_ebitda = 999.0 if total_debt > 0 else 0.0

        payout_fcf = -1.0
        p_fcf = -1.0
        if fcf > 0 and shares > 0 and forward_dividend > 0:
            fcf_per_share = fcf / shares
            if currency == 'GBp': fcf_per_share *= 100
            if fcf_per_share > 0:
                payout_fcf = (forward_dividend / fcf_per_share) * 100
                p_fcf = precio_actual / fcf_per_share

        # Cálculo de recompras/dilución (Doble motor)
        shares_yearly = pd.Series(dtype=float)
        variacion_acciones = None

        try:
            inc_stmt = ticker.income_stmt
            if not inc_stmt.empty:
                for key in ['Basic Average Shares', 'Diluted Average Shares']:
                    if key in inc_stmt.index:
                        sh_data = inc_stmt.loc[key].dropna().sort_index()
                        sh_data = sh_data[sh_data > 0]
                        if len(sh_data) >= 2:
                            shares_yearly = sh_data.groupby(sh_data.index.year).last()
                            acc_ini = shares_yearly.iloc[0]
                            acc_fin = shares_yearly.iloc[-1]
                            if acc_ini > 0 and (acc_fin / acc_ini) > 0.10: 
                                variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
                                break
        except Exception: pass

        if variacion_acciones is None or shares_yearly.empty:
            try:
                fecha_corte_shares = pd.Timestamp.now().normalize() - pd.DateOffset(years=años_analisis + 3)
                shares_hist = ticker.get_shares_full(start=fecha_corte_shares.strftime('%Y-%m-%d'), end=None)
                if shares_hist is not None and len(shares_hist) > 1:
                    sy = shares_hist.groupby(shares_hist.index.year).last()
                    sy = sy[sy > 0]
                    if len(sy) >= 2:
                        shares_yearly = sy
                        acc_ini = shares_yearly.iloc[-(años_analisis + 1)] if len(shares_yearly) >= (años_analisis + 1) else shares_yearly.iloc[0]
                        acc_fin = shares_yearly.iloc[-1]
                        if acc_ini > 0 and (acc_fin / acc_ini) > 0.10:
                            variacion_acciones = ((acc_fin / acc_ini) - 1) * 100
            except Exception: pass

        # Crecimiento histórico de dividendos (DGR)
        dgr_5y = None
        if len(dividendos_barras) >= 6:
            div_actual = dividendos_barras.iloc[-1]
            div_5y = dividendos_barras.iloc[-6]
            if div_5y > 0: dgr_5y = ((div_actual / div_5y) ** (1/5) - 1) * 100

        dgr_periodo = None
        if len(dividendos_barras) >= (años_analisis + 1):
            div_actual = dividendos_barras.iloc[-1]
            div_periodo = dividendos_barras.iloc[-(años_analisis + 1)]
            if div_periodo > 0: dgr_periodo = ((div_actual / div_periodo) ** (1/años_analisis) - 1) * 100

        años_pagando = año_actual - dividendos_barras.index[0] if not dividendos_barras.empty else 0
        racha_sin_recortes = 0
        if len(dividendos_barras) > 1:
            for i in range(1, len(dividendos_barras)):
                if dividendos_barras.iloc[-(i)] >= dividendos_barras.iloc[-(i+1)] * 0.99:
                    racha_sin_recortes += 1
                else: break

        crecimiento_bpa_3y = None
        try:
            inc_stmt = ticker.income_stmt
            if not inc_stmt.empty:
                eps_data = inc_stmt.loc['Diluted EPS'].dropna() if 'Diluted EPS' in inc_stmt.index else inc_stmt.loc['Basic EPS'].dropna()
                if len(eps_data) >= 4 and eps_data.iloc[3] > 0 and eps_data.iloc[0] > 0:
                    crecimiento_bpa_3y = (((eps_data.iloc[0] / eps_data.iloc[3]) ** (1 / 3)) - 1) * 100
        except Exception: pass

        # ==========================================
        # 1. SCORE DE CALIDAD DGI MODERNA (0 a 10 Pts)
        # ==========================================
        score_calidad = 0.0

        # Solvencia Operativa Real (2.5 pts)
        lim_deuda_optima = 4.0 if (es_regulada or es_defensivo or es_telecom) else 3.0
        lim_deuda_aceptable = 5.0 if (es_regulada or es_defensivo or es_telecom) else 4.0
        if deuda_ebitda <= lim_deuda_optima:
            score_calidad += 2.5
        elif deuda_ebitda <= lim_deuda_aceptable:
            score_calidad += 1.5

        # Seguridad del Dividendo en Efectivo - FCF (2.5 pts)
        if 0 <= payout_fcf <= payout_lim_fcf:
            score_calidad += 2.5
        elif payout_fcf <= payout_ama_fcf:
            score_calidad += 1.25

        # Resiliencia y Compromiso Histórico (2.0 pts)
        if (años_pagando >= 20 and racha_sin_recortes >= 10) or racha_sin_recortes >= 15:
            score_calidad += 2.0
        elif (años_pagando >= 10 and racha_sin_recortes >= 8) or racha_sin_recortes >= 10:
            score_calidad += 1.25
        elif racha_sin_recortes >= 5:
            score_calidad += 0.75

        # Crecimiento Real por encima de inflación DGR 5A (1.5 pts)
        if dgr_5y is not None and dgr_5y >= 5.0:
            score_calidad += 1.5
        elif dgr_5y is not None and dgr_5y >= 2.5:
            score_calidad += 0.75

        # Asignación de Capital: Recompras o Crecimiento de BPA (1.5 pts)
        cond_recompras = variacion_acciones is not None and variacion_acciones < -0.5
        cond_bpa_pos = crecimiento_bpa_3y is not None and crecimiento_bpa_3y > 0
        if cond_recompras or cond_bpa_pos:
            score_calidad += 1.5

        # ==========================================
        # 2. SCORE DE VALORACIÓN DGI (0 a 10 Pts)
        # ==========================================
        score_val = 0.0

        # Canal de Rendimiento Histórico Weiss (4.0 pts máx)
        if yield_actual >= yield_infravalorado:
            score_val += 4.0
        elif yield_actual >= yield_medio:
            score_val += 2.5

        # Múltiplo de Flujo de Caja Libre (2.5 pts)
        if 0 < p_fcf <= 20.0:
            score_val += 2.5
        elif 0 < p_fcf <= 25.0:
            score_val += 1.25

        # Múltiplo de Beneficio PER (2.0 pts)
        if 0 < per <= 20.0:
            score_val += 2.0
        elif 0 < per <= 25.0:
            score_val += 1.0

        # Regla de Chowder (1.5 pts)
        if (es_utility_pura or es_telecom) and yield_actual > 4.0:
            chowder_target = 8.0
        elif yield_actual >= 3.0:
            chowder_target = 12.0
        else:
            chowder_target = 15.0

        chowder_number = (yield_actual + dgr_5y) if dgr_5y is not None else -999.0
        if chowder_number != -999.0 and chowder_number >= chowder_target:
            score_val += 1.5

        dist_real_suelo = ((precio_actual - precio_compra) / precio_compra) * 100 if precio_compra > 0 else 999.0
        pct_infra_vs_media = ((precio_compra - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0
        pct_sobre_vs_media = ((precio_venta - precio_justo) / precio_justo) * 100 if precio_justo > 0 else 0.0

        if precio_actual <= precio_compra: estado = "🎯 COMPRA"
        elif precio_actual >= precio_venta: estado = "🔴 SOBREVALORADA"
        else: estado = "🟡 MANTENER"

        sym_m = "€" if currency == "EUR" else ("£" if currency in ["GBP", "GBp"] else "$")

        return {
            "Estado": estado,
            "Ticker": ticker_symbol.strip().upper(),
            "Calidad": f"{score_calidad:.1f}/10",
            "Valoración": f"{score_val:.1f}/10",
            "Chowder": f"{chowder_number:.1f} (Obj: {chowder_target:.0f})" if chowder_number != -999.0 else "N/D",
            "Cotización Actual": f"{precio_actual / divisor_uk:.2f}{sym_m} ({dist_real_suelo:+.2f}%)",
            "Suelo (Infra)": f"{precio_compra / divisor_uk:.2f}{sym_m} ({pct_infra_vs_media:+.2f}%)" if precio_compra > 0 else "N/D",
            "Precio Justo": f"{precio_justo / divisor_uk:.2f}{sym_m}",
            "Techo (Sobre)": f"{precio_venta / divisor_uk:.2f}{sym_m} ({pct_sobre_vs_media:+.2f}%)" if precio_venta > 0 else "N/D",
            "Div. Neto": f"{div_neto_absoluto / divisor_uk:.2f}{sym_m}",
            "Yield Bruto": f"{yield_actual:.2f}%",
            "Yield Neto": f"{yield_neto:.2f}%",
            "PER": f"{per:.2f}" if per > 0 else "N/D",
            "P/FCF": f"{p_fcf:.2f}" if p_fcf != -1 else "N/D",
            "Deuda/EBITDA": f"{deuda_ebitda:.2f}x" if deuda_ebitda < 900 else "N/D",
            "Payout FCF": f"{payout_fcf:.2f}%" if payout_fcf != -1 else "N/D",
            "Payout BPA": f"{payout_bpa:.2f}%",
            "P/B": f"{pb:.2f}x" if pb > 0 else "N/D",
            "Acciones": f"{variacion_acciones:+.2f}%" if variacion_acciones is not None else "N/D",
            "Crec. BPA 3Y": f"{crecimiento_bpa_3y:+.2f}%" if crecimiento_bpa_3y is not None else "N/D",
            "DGR 5A": f"{dgr_5y:.2f}%" if dgr_5y is not None else "N/D",
            f"DGR {años_analisis}A": f"{dgr_periodo:.2f}%" if dgr_periodo is not None else "N/D",
            "Años Pag.": f"{años_pagando}A (R: {racha_sin_recortes}A)",
            
            "_Dist_Suelo": dist_real_suelo,
            "_y_act": yield_actual, "_y_inf": yield_infravalorado, "_y_med": yield_medio,
            "_per": per, "_p_fcf": p_fcf, "_pb": pb, 
            "_pay_bpa": payout_bpa, "_l_bpa": payout_lim_bpa, "_a_bpa": payout_ama_bpa,
            "_pay_fcf": payout_fcf, "_l_fcf": payout_lim_fcf, "_a_fcf": payout_ama_fcf,
            "_deuda_ebitda": deuda_ebitda, "_lim_deuda_opt": lim_deuda_optima, "_lim_deuda_acep": lim_deuda_aceptable,
            "_acc": variacion_acciones if variacion_acciones is not None else 999,
            "_dgr": dgr_5y if dgr_5y is not None else -999,
            "_dgr_per": dgr_periodo if dgr_periodo is not None else -999,
            "_cbpa3": crecimiento_bpa_3y if crecimiento_bpa_3y is not None else -999,
            "_score_calidad": score_calidad,
            "_score_val": score_val,
            "_chowder": chowder_number,
            "_chowder_target": chowder_target
        }
    except Exception:
        return None

# ==========================================
# INTERFAZ DIRECTA DE LA PÁGINA (RADAR)
# ==========================================
st.title("📡 Radar Watchlist DGI — Geraldine Weiss Moderno")
st.markdown("La tabla prioriza oportunidades ordenando primero las empresas con mayor descuento respecto a su **Suelo Fundamental**.")
st.markdown("> *Puntuaciones: **Calidad (0-10)** evalúa la solvencia por caja, resiliencia y retribución. **Valoración (0-10)** mide el margen de seguridad vía Canal Weiss, múltiplos P/FCF y Chowder. P/B queda como dato informativo secundario.*")

tickers_masivos = st.text_area("Lista de Tickers (separados por comas):", "MKC, VIS.MC, MCD, GIS, WKL.AS, PEP, JNJ, HD")

col_m1, col_m2 = st.columns(2)
with col_m1: años_masivos = st.selectbox("Periodo para canal histórico:", [5, 10, 12, 15, 20], index=2, key="años_mas")
with col_m2: impuesto_masivo = st.number_input("Retención (%)", value=19.0, key="imp_mas")

if st.button("🚀 Escanear Watchlist", use_container_width=True):
    lista_tickers = [t.strip() for t in tickers_masivos.split(",") if t.strip()]
    
    if len(lista_tickers) > 0:
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        resultados = []
        
        for idx, ticker in enumerate(lista_tickers):
            texto_estado.text(f"Escaneando {ticker} ({idx+1}/{len(lista_tickers)})...")
            datos = analizar_empresa_rapido(ticker, años_masivos, impuesto_masivo)
            if datos: resultados.append(datos)
            barra_progreso.progress((idx + 1) / len(lista_tickers))
        
        texto_estado.text("¡Escaneo masivo completado!")
        
        if resultados:
            df_res = pd.DataFrame(resultados).sort_values(by="_Dist_Suelo")
            
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
                    elif col_name == 'Cotización Actual':
                        if "COMPRA" in est: styles[idx] = 'color: #21c354; font-weight: bold;'
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
                        if 0 < row['_per'] <= 20: styles[idx] = 'color: #21c354;'
                        elif 0 < row['_per'] <= 25: styles[idx] = 'color: #faca2b;'
                        else: styles[idx] = 'color: #ff4b4b;'
                    elif col_name == 'P/FCF':
                        if 0 < row['_p_fcf'] <= 20: styles[idx] = 'color: #21c354;'
                        elif 0 < row['_p_fcf'] <= 25: styles[idx] = 'color: #faca2b;'
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
                        if val_col >= 10.0: styles[idx] = 'color: #21c354;'
                        elif val_col >= 5.0: styles[idx] = 'color: #faca2b;'
                        elif val_col >= 2.5: styles[idx] = 'color: #ff9800;'
                        else: styles[idx] = 'color: #ff4b4b;'
                    elif col_name == 'Chowder':
                        c_num = row['_chowder']
                        c_tar = row['_chowder_target']
                        if c_num != -999.0:
                            if c_num >= c_tar: styles[idx] = 'color: #21c354; font-weight: bold;'
                            else: styles[idx] = 'color: #ff4b4b;'
                    elif col_name == 'Estado':
                        if "COMPRA" in est: styles[idx] = 'background-color: #004d00; color: white;'
                        elif "SOBREVALORADA" in est: styles[idx] = 'background-color: #4d0000; color: white;'
                        else: styles[idx] = 'background-color: #4d4d00; color: white;'
                return styles
            
            columnas_visibles = [c for c in df_res.columns if not c.startswith('_')]
            styled_df = df_res.style.apply(color_row, axis=1)
            st.dataframe(styled_df, column_order=columnas_visibles, use_container_width=True)
            
            df_export = df_res[columnas_visibles]
            csv = df_export.to_csv(index=False, sep=';', decimal=',').encode('utf-8')
            st.download_button(
                label="💾 Descargar CSV para Google Sheets",
                data=csv,
                file_name=f"Screener_DGI_Weiss_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.warning("No se pudieron recopilar canales históricos válidos para los tickers introducidos.")
