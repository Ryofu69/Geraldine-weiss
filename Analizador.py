
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES (ADAPTATIVOS MÓVIL / ESCRITORIO)
# ==============================================================================
st.set_page_config(
    page_title="Geraldine Weiss & Chowder",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CUSTOM_CSS = """
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
    max-width: 1120px;
}
.weiss-header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.75rem;
}
.weiss-title {
    font-size: 1.45rem;
    font-weight: 700;
    margin: 0;
    line-height: 1.2;
}
.weiss-meta {
    font-size: 0.82rem;
    opacity: 0.76;
    margin-top: 4px;
    line-height: 1.4;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 13px;
    border-radius: 999px;
    font-size: 0.83rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.pill-green { background: rgba(16, 185, 129, 0.15); color: #10B981; border-color: rgba(16, 185, 129, 0.38); }
.pill-teal  { background: rgba(20, 184, 166, 0.15); color: #2DD4BF; border-color: rgba(20, 184, 166, 0.38); }
.pill-blue  { background: rgba(56, 189, 248, 0.15); color: #38BDF8; border-color: rgba(56, 189, 248, 0.38); }
.pill-amber { background: rgba(245, 158, 11, 0.15); color: #F59E0B; border-color: rgba(245, 158, 11, 0.38); }
.pill-red   { background: rgba(239, 68, 68, 0.15);  color: #EF4444; border-color: rgba(239, 68, 68, 0.38); }

.tax-banner {
    background: rgba(245, 158, 11, 0.10);
    border: 1px solid rgba(245, 158, 11, 0.32);
    border-left: 3px solid #F59E0B;
    border-radius: 10px;
    padding: 9px 12px;
    font-size: 0.80rem;
    margin: 0.35rem 0 0.8rem 0;
    line-height: 1.4;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin: 0.6rem 0 1rem 0;
}
@media (min-width: 768px) {
    .kpi-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
    }
}
.kpi-card {
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-top: 3px solid rgba(148, 163, 184, 0.45);
    border-radius: 12px;
    padding: 12px 13px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.kpi-card.accent-blue   { border-top-color: #38BDF8; }
.kpi-card.accent-green  { border-top-color: #10B981; }
.kpi-card.accent-teal   { border-top-color: #2DD4BF; }
.kpi-card.accent-amber  { border-top-color: #F59E0B; }
.kpi-card.accent-red    { border-top-color: #EF4444; }
.kpi-card.accent-purple { border-top-color: #A855F7; }
.kpi-card.accent-slate  { border-top-color: #94A3B8; }

.kpi-label {
    font-size: 0.75rem;
    font-weight: 600;
    opacity: 0.74;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 1.44rem;
    font-weight: 800;
    line-height: 1.15;
    margin-bottom: 4px;
}
.val-green  { color: #10B981; }
.val-teal   { color: #2DD4BF; }
.val-blue   { color: #38BDF8; }
.val-amber  { color: #F59E0B; }
.val-red    { color: #EF4444; }
.val-purple { color: #A855F7; }
.val-slate  { color: inherit; }

.kpi-yields {
    font-size: 0.74rem;
    opacity: 0.88;
    margin-bottom: 4px;
    line-height: 1.3;
}
.kpi-sub {
    font-size: 0.76rem;
    opacity: 0.80;
}
.kpi-sub.pos  { color: #10B981; opacity: 1; font-weight: 600; }
.kpi-sub.teal { color: #2DD4BF; opacity: 1; font-weight: 600; }
.kpi-sub.warn { color: #F59E0B; opacity: 1; font-weight: 600; }
.kpi-sub.neg  { color: #EF4444; opacity: 1; font-weight: 600; }

.gauge-box {
    background: rgba(148, 163, 184, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 12px;
    padding: 13px 15px;
    margin: 0.4rem 0 1.2rem 0;
}
.gauge-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.82rem;
    margin-bottom: 10px;
}
.gauge-track {
    position: relative;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(90deg, #10B981 0%, #F59E0B 50%, #EF4444 100%);
}
.gauge-mid-tick {
    position: absolute;
    left: 50%;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: rgba(255, 255, 255, 0.82);
    border-radius: 2px;
    transform: translateX(-50%);
}
.gauge-marker {
    position: absolute;
    top: 50%;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #FFFFFF;
    border: 3px solid #0F172A;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85), 0 2px 6px rgba(0, 0, 0, 0.45);
    transform: translate(-50%, -50%);
}
.gauge-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.74rem;
    font-weight: 600;
    margin-top: 8px;
}
.section-caption {
    font-size: 0.82rem;
    opacity: 0.78;
    margin-top: -8px;
    margin-bottom: 10px;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

EJEMPLOS_DGI = {
    "McCormick (MKC)": "MKC",
    "Accenture (ACN)": "ACN",
    "Johnson & Johnson (JNJ)": "JNJ",
    "Coca-Cola (KO)": "KO",
    "Procter & Gamble (PG)": "PG",
    "PepsiCo (PEP)": "PEP",
    "AbbVie (ABBV)": "ABBV",
    "Realty Income (O)": "O",
    "Microsoft (MSFT)": "MSFT",
    "Iberdrola (IBE.MC)": "IBE.MC",
    "Inditex (ITX.MC)": "ITX.MC",
    "Enagás (ENG.MC)": "ENG.MC",
    "Viscofan (VIS.MC)": "VIS.MC",
    "Allianz (ALV.DE)": "ALV.DE",
    "Nestlé (NESN.SW)": "NESN.SW",
    "Unilever (ULVR.L)": "ULVR.L",
}

FISCALIDAD_PAISES = {
    "Spain": ("España", 0.0, 0.0, "Sin retención extranjera; tributa únicamente en IRPF destino."),
    "United States": ("EE. UU.", 15.0, 15.0, "15% en origen con W-8BEN (30% sin W-8BEN). Deducible hasta 15% en Renta."),
    "Ireland": ("Irlanda", 25.0, 0.0, "Irlanda retiene 25% DWT, pero el convenio con España fija 0% (no deducible en Casilla 0588; requiere exención V2A o reclamación a Irlanda)."),
    "United Kingdom": ("Reino Unido", 0.0, 0.0, "0% en origen en acciones ordinarias (20% en REITs PID)."),
    "Germany": ("Alemania", 26.375, 15.0, "26,375% en origen; solo 15% deducible en Renta (11,375% reclamable a Alemania)."),
    "France": ("Francia", 25.0, 15.0, "25% estándar en origen (12,8% si tu bróker aplica tarifa persona física). Máximo 15% deducible en Renta."),
    "Switzerland": ("Suiza", 35.0, 15.0, "35% en origen; solo 15% deducible en Renta (20% reclamable a Suiza)."),
    "Netherlands": ("Países Bajos", 15.0, 15.0, "15% en origen, íntegramente deducible en Renta (CDI 15%)."),
    "Italy": ("Italia", 26.0, 15.0, "26% en origen; solo 15% deducible en Renta (11% reclamable a Italia)."),
    "Canada": ("Canadá", 15.0, 15.0, "15% con formulario NR301 (25% sin él). Máximo 15% deducible en Renta."),
    "Belgium": ("Bélgica", 30.0, 15.0, "30% en origen; solo 15% deducible en Renta (15% reclamable a Bélgica)."),
    "Portugal": ("Portugal", 25.0, 15.0, "25% estándar en origen (puede ser 35% en cuentas ómnibus). Máximo 15% deducible en Renta."),
    "Japan": ("Japón", 15.315, 15.0, "15,315% en origen; deducible hasta 15% en Renta."),
    "Sweden": ("Suecia", 30.0, 15.0, "30% en origen; solo 15% deducible en Renta."),
    "Norway": ("Noruega", 25.0, 15.0, "25% en origen; solo 15% deducible en Renta."),
    "Finland": ("Finlandia", 35.0, 15.0, "35% en origen; solo 15% deducible en Renta."),
    "Denmark": ("Dinamarca", 27.0, 19.0, "27% en origen (sin convenio vigente con España; deducción sujeta al art. 80 LIRPF)."),
    "Australia": ("Australia", 15.0, 15.0, "0% en dividendos franked / 15% en unfranked (CDI 15%)."),
    "Hong Kong": ("Hong Kong", 0.0, 0.0, "0% en origen."),
    "Singapore": ("Singapur", 0.0, 0.0, "0% en origen."),
}

SUFIJO_A_PAIS = {
    ".MC": "Spain",
    ".L": "United Kingdom",
    ".DE": "Germany",
    ".F": "Germany",
    ".PA": "France",
    ".SW": "Switzerland",
    ".AS": "Netherlands",
    ".MI": "Italy",
    ".TO": "Canada",
    ".V": "Canada",
    ".BR": "Belgium",
    ".LS": "Portugal",
    ".T": "Japan",
    ".ST": "Sweden",
    ".OL": "Norway",
    ".HE": "Finland",
    ".CO": "Denmark",
    ".IR": "Ireland",
    ".AX": "Australia",
    ".HK": "Hong Kong",
    ".SI": "Singapore",
}

if "ticker_activo" not in st.session_state:
    st.session_state.ticker_activo = "ACN"


def actualizar_desde_ejemplo():
    seleccion = st.session_state.selector_ejemplo
    if seleccion in EJEMPLOS_DGI:
        st.session_state.ticker_activo = EJEMPLOS_DGI[seleccion]
        st.session_state.input_ticker = EJEMPLOS_DGI[seleccion]


def detectar_fiscalidad_pais(ticker: str, info: dict):
    pais_en = str(info.get("country") or "").strip()
    if not pais_en:
        for suf, p_fallback in SUFIJO_A_PAIS.items():
            if ticker.upper().endswith(suf):
                pais_en = p_fallback
                break

    if pais_en in FISCALIDAD_PAISES:
        p_es, r_orig, l_cdi, nota = FISCALIDAD_PAISES[pais_en]
        return pais_en, p_es, r_orig, l_cdi, nota

    if pais_en:
        return pais_en, pais_en, 15.0, 15.0, f"País detectado ({pais_en}): retención estimada 15% / CDI 15% (editable en Ajustes)."
    return "", "No detectado", 0.0, 0.0, "No se detectó el país fiscal; revisa la retención en origen en Ajustes."


def calcular_fiscalidad_efectiva(ret_origen: float, limite_cdi: float, imp_destino: float, modo_neto: str) -> dict:
    r_orig = max(0.0, min(100.0, float(ret_origen)))
    l_cdi = max(0.0, min(100.0, float(limite_cdi)))
    t_dest = max(0.0, min(100.0, float(imp_destino)))

    deducible_renta = min(r_orig, l_cdi, t_dest)
    exceso_no_deducible = max(0.0, r_orig - deducible_renta)
    efectivo_renta = min(100.0, t_dest + exceso_no_deducible)

    factor_cascada = (1.0 - r_orig / 100.0) * (1.0 - t_dest / 100.0)
    efectivo_cascada = (1.0 - factor_cascada) * 100.0

    if modo_neto == "cascada":
        tasa_efectiva = efectivo_cascada
        factor_neto = factor_cascada
        etiqueta_corta = f"Cobro cascada: {tasa_efectiva:.2f}%"
    else:
        tasa_efectiva = efectivo_renta
        factor_neto = max(0.0, 1.0 - tasa_efectiva / 100.0)
        etiqueta_corta = f"Efectivo Renta: {tasa_efectiva:.2f}%"

    return {
        "tasa_efectiva": tasa_efectiva,
        "factor_neto": factor_neto,
        "deducible_renta": deducible_renta,
        "exceso_no_deducible": exceso_no_deducible,
        "efectivo_renta": efectivo_renta,
        "efectivo_cascada": efectivo_cascada,
        "etiqueta_corta": etiqueta_corta,
    }


def fmt_pct_limpio(valor: float) -> str:
    if abs(valor - round(valor)) < 1e-6:
        return f"{int(round(valor))}%"
    if abs(valor * 10 - round(valor * 10)) < 1e-5:
        return f"{valor:.1f}%"
    return f"{valor:.2f}%"


def consolidar_eventos_dividendo(div_series: pd.Series, ventana_dias: int = 7) -> pd.Series:
    eventos = div_series[div_series > 0].sort_index()
    if eventos.empty:
        return eventos

    fechas, montos = [], []
    f_act = eventos.index[0]
    m_act = float(eventos.iloc[0])

    for fecha, monto in list(eventos.items())[1:]:
        monto_f = float(monto)
        diff_dias = (fecha - f_act).days
        if diff_dias <= ventana_dias:
            es_duplicado = (
                diff_dias <= 5
                and m_act > 0
                and abs(monto_f - m_act) / m_act < 0.002
            )
            if not es_duplicado:
                m_act += monto_f
                f_act = fecha
        else:
            fechas.append(f_act)
            montos.append(m_act)
            f_act = fecha
            m_act = monto_f

    fechas.append(f_act)
    montos.append(m_act)
    return pd.Series(montos, index=pd.DatetimeIndex(fechas), name="Dividends")


def detectar_frecuencia_dinamica(div_events: pd.Series) -> pd.Series:
    if div_events.empty:
        return pd.Series(dtype=int)

    fechas = div_events.index
    n = len(fechas)
    if n == 1:
        return pd.Series([1], index=fechas, dtype=int)

    dias = (fechas - fechas[0]).total_seconds().to_numpy(dtype=np.float64) / 86400.0
    ventana_dias = 348.0
    ultimo_dia = float(dias[-1])
    primer_dia = float(dias[0])

    raw_freq = np.zeros(n, dtype=int)
    for i in range(n):
        d = float(dias[i])
        if d + ventana_dias <= ultimo_dia:
            j = int(np.searchsorted(dias, d + ventana_dias, side="right"))
            cnt = j - i
        elif d - ventana_dias >= primer_dia:
            j = int(np.searchsorted(dias, d - ventana_dias, side="left"))
            cnt = i - j + 1
        else:
            cnt = n
        raw_freq[i] = max(1, cnt)

    def normalizar_freq(c: int) -> int:
        if c >= 8:
            return 12
        if c in (5, 7):
            return 4
        return max(1, c)

    norm_raw = np.array([normalizar_freq(int(c)) for c in raw_freq], dtype=int)

    runs = []
    start = 0
    for i in range(1, n):
        if norm_raw[i] != norm_raw[start]:
            runs.append((start, i, int(norm_raw[start])))
            start = i
    runs.append((start, n, int(norm_raw[start])))

    estable = np.full(n, np.nan, dtype=float)
    for s, e, val in runs:
        longitud = e - s
        es_tramo_final = (e == n)
        if val <= 4:
            min_req = val if (es_tramo_final and val >= 2) else (val + 1)
        else:
            min_req = max(5, val // 2)
        if longitud >= min_req:
            estable[s:e] = val

    serie_est = pd.Series(estable, index=fechas)
    if serie_est.isna().all():
        fallback = int(round(float(np.median(norm_raw))))
        return pd.Series([max(1, fallback)] * n, index=fechas, dtype=int)

    return serie_est.ffill().bfill().astype(int)


def validar_cambios_frecuencia(div_events: pd.Series, freq_serie: pd.Series, info=None) -> pd.Series:
    if len(div_events) < 2:
        return freq_serie

    vals = div_events.values.astype(float)
    freqs = freq_serie.values.astype(int).copy()
    n = len(freqs)

    segmentos = []
    s = 0
    for i in range(1, n):
        if freqs[i] != freqs[s]:
            segmentos.append([s, i, int(freqs[s])])
            s = i
    segmentos.append([s, n, int(freqs[s])])

    if len(segmentos) > 1:
        for idx in range(1, len(segmentos)):
            prev_s, prev_e, f_prev = segmentos[idx - 1]
            curr_s, curr_e, f_curr = segmentos[idx]
            if f_curr == f_prev:
                continue

            v_before = float(np.median(vals[max(prev_s, prev_e - min(f_prev, 2)) : prev_e]))
            v_after = float(np.median(vals[curr_s : min(curr_e, curr_s + min(f_curr, 2))]))

            if v_before > 0 and v_after > 0:
                anual_prev = v_before * f_prev
                err_mantener = abs(np.log((v_after * f_prev) / anual_prev))
                err_cambiar = abs(np.log((v_after * f_curr) / anual_prev))
                if err_mantener < err_cambiar:
                    segmentos[idx][2] = f_prev
                    freqs[curr_s:curr_e] = f_prev

    forward_rate = (info or {}).get("dividendRate")
    if forward_rate and float(forward_rate) > 0 and vals[-1] > 0:
        ratio = float(forward_rate) / float(vals[-1])
        estandar = [1, 2, 3, 4, 6, 12]
        f_info = min(estandar, key=lambda f: abs(ratio - f))
        if abs(ratio - f_info) / f_info <= 0.12 and freqs[-1] != f_info:
            ultimos = vals[max(0, n - 4) :]
            if len(ultimos) >= 2 and (np.max(ultimos) / max(np.min(ultimos), 1e-9)) <= 1.35:
                last_s = segmentos[-1][0]
                freqs[last_s:n] = f_info
                for k in range(last_s - 1, -1, -1):
                    if vals[k] > 0 and 0.65 <= (vals[k] / vals[k + 1]) <= 1.50:
                        freqs[k] = f_info
                    else:
                        break

    return pd.Series(freqs, index=div_events.index, dtype=int)


def detectar_intercalados_extra(div_events: pd.Series, freq_serie: pd.Series) -> pd.Series:
    n = len(div_events)
    mask = np.zeros(n, dtype=bool)
    if n < 3:
        return pd.Series(mask, index=div_events.index)

    fechas = div_events.index
    valores = div_events.values
    freqs = freq_serie.values

    for i in range(1, n - 1):
        f_i = int(freqs[i])
        if f_i <= 0 or freqs[i - 1] != f_i or freqs[i + 1] != f_i:
            continue

        periodo_esperado = 365.0 / f_i
        gap_prev = (fechas[i] - fechas[i - 1]).days
        gap_next = (fechas[i + 1] - fechas[i]).days
        if (gap_prev + gap_next) <= periodo_esperado * 1.28:
            ref_min = min(valores[i - 1], valores[i + 1])
            if ref_min > 0 and valores[i] < ref_min * 0.45:
                mask[i] = True

    return pd.Series(mask, index=div_events.index)


def detectar_pagos_uniformes(div_events: pd.Series, freq_serie: pd.Series) -> bool:
    if div_events.empty:
        return True

    freq_actual = int(freq_serie.iloc[-1])
    if freq_actual <= 1:
        return True

    ev_regimen = div_events[freq_serie == freq_actual]
    if len(ev_regimen) < freq_actual * 2:
        return True

    recientes = ev_regimen.tail(min(len(ev_regimen), freq_actual * 5))
    cambios = recientes.pct_change().dropna()
    if cambios.empty:
        return True

    caidas_fuertes = (cambios < -0.12).sum()
    subidas_fuertes = (cambios > 0.12).sum()
    if caidas_fuertes >= 2 and subidas_fuertes >= 2 and (caidas_fuertes / len(cambios)) >= 0.20:
        return False
    return True


def filtrar_dividendos_extraordinarios(serie_anual: pd.Series) -> pd.Series:
    if len(serie_anual) < 3:
        return serie_anual.copy()

    limpios = serie_anual.copy()
    valores = serie_anual.values
    for i in range(1, len(valores) - 1):
        prev_v, curr_v, next_v = valores[i - 1], valores[i], valores[i + 1]
        if prev_v > 0 and curr_v > prev_v * 1.55 and next_v < curr_v * 0.75:
            limpios.iloc[i] = prev_v
    return limpios


def calcular_dividendo_weiss(df_precios: pd.DataFrame, modo_calculo: str = "auto", freq_override: int = 0, info=None):
    div_events = consolidar_eventos_dividendo(df_precios["Dividends"])
    if div_events.empty:
        vacio = pd.Series(dtype=float)
        return pd.Series(np.nan, index=df_precios.index), 0, "N/D", "", vacio, vacio

    if freq_override > 0:
        freq_serie = pd.Series(freq_override, index=div_events.index, dtype=int)
    else:
        freq_bruta = detectar_frecuencia_dinamica(div_events)
        freq_serie = validar_cambios_frecuencia(div_events, freq_bruta, info=info)

    freq_actual = int(freq_serie.iloc[-1])
    freqs_unicas = list(dict.fromkeys(int(x) for x in freq_serie.values))
    previas_lista = [x for x in freqs_unicas if x != freq_actual]
    if previas_lista and freq_override == 0:
        previas = "/".join(str(x) for x in previas_lista)
        info_cambio_freq = f"{freq_actual} pagos/año (antes {previas}/año)"
    else:
        info_cambio_freq = f"{freq_actual} pagos/año"

    intercalados = detectar_intercalados_extra(div_events, freq_serie)
    ev_reg = div_events[~intercalados]
    freq_reg = freq_serie[~intercalados]
    if ev_reg.empty:
        ev_reg = div_events
        freq_reg = freq_serie

    uniforme = detectar_pagos_uniformes(ev_reg, freq_reg)
    modo_efectivo = ("weiss_clasico" if uniforme else "ttm") if modo_calculo == "auto" else modo_calculo

    if modo_efectivo == "weiss_clasico":
        anual_bruto = ev_reg * freq_reg
        div_anual_evento = filtrar_dividendos_extraordinarios(anual_bruto)
        etiqueta_modo = "Escalón clásico Weiss (Dividendo indicado)"
    else:
        vals = ev_reg.values
        freqs = freq_reg.values
        ttm_vals = np.full(len(vals), np.nan, dtype=float)
        for i in range(len(vals)):
            f_i = int(freqs[i])
            if i + 1 >= f_i:
                ttm_vals[i] = float(np.sum(vals[i - f_i + 1 : i + 1]))
        div_anual_evento = pd.Series(ttm_vals, index=ev_reg.index)
        etiqueta_modo = f"TTM móvil (últimos {freq_actual} pagos)"

    serie_diaria = div_anual_evento.reindex(df_precios.index, method="ffill")
    fechas_ev = pd.Series(div_events.index, index=div_events.index)
    ultima_fecha = fechas_ev.reindex(df_precios.index, method="ffill")
    dias_sin_pago = (df_precios.index.to_series() - ultima_fecha).dt.days
    serie_diaria = serie_diaria.where(dias_sin_pago <= 420, np.nan)

    return serie_diaria, freq_actual, etiqueta_modo, info_cambio_freq, ev_reg, freq_reg


def calcular_cagr(valor_final: float, valor_inicial: float, anios: int):
    if valor_inicial is None or valor_final is None:
        return None
    if valor_inicial <= 0 or valor_final <= 0 or anios <= 0:
        return None
    return ((valor_final / valor_inicial) ** (1.0 / anios) - 1.0) * 100.0


def color_dgr(valor):
    if valor is None:
        return "slate", ""
    if valor >= 5.0:
        return "green", "pos"
    if valor > 0:
        return "teal", "teal"
    if valor == 0:
        return "amber", "warn"
    return "red", "neg"


def render_kpi_grid(cards: list):
    html_cards = []
    for c in cards:
        accent = c.get("accent", "slate")
        val_cls = c.get("val_class", f"val-{accent}")
        sub_cls = c.get("sub_class", "")
        yields_html = f'<div class="kpi-yields">{c["yields"]}</div>' if c.get("yields") else ""
        html_cards.append(
            f'<div class="kpi-card accent-{accent}">'
            f'<div class="kpi-label">{c["label"]}</div>'
            f'<div class="kpi-value {val_cls}">{c["value"]}</div>'
            f'{yields_html}'
            f'<div class="kpi-sub {sub_cls}">{c.get("sub", "")}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(html_cards)}</div>', unsafe_allow_html=True)


def normalizar_divisa_subunidad(df_full: pd.DataFrame, info: dict):
    moneda = str(info.get("currency") or "")
    if moneda not in {"GBp", "GBX", "ZAc", "ILA"}:
        return df_full, info

    df_norm = df_full.copy()
    info_norm = dict(info)
    close_ult = float(df_norm["Close"].iloc[-1])
    divs_pos = df_norm["Dividends"][df_norm["Dividends"] > 0]
    if close_ult <= 0 or divs_pos.empty:
        return df_norm, info_norm

    fecha_max = df_norm.index.max()
    div_1y = float(divs_pos[divs_pos.index >= fecha_max - timedelta(days=365)].sum())
    if div_1y <= 0:
        div_1y = float(divs_pos.tail(4).sum())

    yield_bruto_est = div_1y / close_ult
    trailing_y = info_norm.get("trailingAnnualDividendYield")

    desajuste_divs = False
    if trailing_y is not None and float(trailing_y) > 0.005 and yield_bruto_est < 0.0025:
        if 40.0 <= (float(trailing_y) / max(yield_bruto_est, 1e-9)) <= 160.0:
            desajuste_divs = True
    elif yield_bruto_est < 0.0015 and (yield_bruto_est * 100.0) <= 0.30:
        desajuste_divs = True

    if desajuste_divs:
        df_norm["Dividends"] = df_norm["Dividends"] * 100.0
        div_1y *= 100.0
        info_norm["_nota_divisa"] = f"Dividendos normalizados ×100 a {moneda}"

    fwd = info_norm.get("dividendRate")
    if fwd is not None and float(fwd) > 0 and div_1y > 0:
        ratio_fwd = div_1y / float(fwd)
        if 45.0 <= ratio_fwd <= 160.0:
            info_norm["dividendRate"] = float(fwd) * 100.0

    return df_norm, info_norm


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_datos_yahoo(ticker: str, years: int):
    try:
        hoy = datetime.today()
        anios_necesarios = max(years, 12) + 2
        start_date = datetime(hoy.year - anios_necesarios, 1, 1)

        stock = yf.Ticker(ticker)
        df_full = stock.history(start=start_date, end=hoy + timedelta(days=1), auto_adjust=False)

        if df_full is None or df_full.empty:
            return None, {}

        if df_full.index.tz is not None:
            df_full.index = df_full.index.tz_localize(None)

        df_full = df_full[df_full["Close"].notna() & (df_full["Close"] > 0)].copy()

        try:
            info = stock.info or {}
        except Exception:
            info = {}

        df_full, info = normalizar_divisa_subunidad(df_full, info)
        return df_full, info
    except Exception as exc:
        return None, {"_error": str(exc)}


# ==============================================================================
# BARRA SUPERIOR DE SELECCIÓN DE EMPRESA Y CARGA DE DATOS
# ==============================================================================
st.markdown("### 📊 Analizador Geraldine Weiss & Regla de Chowder")

with st.container(border=True):
    col_busq, col_ej, col_per = st.columns([2.2, 2.0, 1.0])

    with col_busq:
        with st.form(key="form_ticker", border=False):
            c_in, c_btn = st.columns([3, 1.3])
            with c_in:
                ticker_escrito = st.text_input(
                    "Ticker (Yahoo Finance)",
                    value=st.session_state.ticker_activo,
                    key="input_ticker",
                    placeholder="MKC, ACN, JNJ, IBE.MC..."
                )
            with c_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                enviar = st.form_submit_button("Analizar", type="primary", use_container_width=True)

            if enviar and ticker_escrito.strip():
                st.session_state.ticker_activo = ticker_escrito.strip().upper()

    with col_ej:
        st.selectbox(
            "Acceso rápido DGI",
            options=["— Elegir empresa —"] + list(EJEMPLOS_DGI.keys()),
            key="selector_ejemplo",
            on_change=actualizar_desde_ejemplo
        )

    with col_per:
        years = st.selectbox(
            "Periodo",
            options=[5, 7, 10, 12, 15, 20],
            index=3,
            format_func=lambda x: f"{x} años"
        )

    ticker_actual = st.session_state.ticker_activo

    with st.spinner(f"Cargando datos históricos de {ticker_actual}..."):
        df_full, info = cargar_datos_yahoo(ticker_actual, years)

    pais_en, pais_es, orig_def, cdi_def, nota_pais = detectar_fiscalidad_pais(ticker_actual, info or {})
    clave_fiscal = (ticker_actual, pais_en)
    if st.session_state.get("fiscal_sync_key") != clave_fiscal:
        st.session_state["ret_origen_input"] = float(orig_def)
        st.session_state["limite_cdi_input"] = float(cdi_def)
        st.session_state["fiscal_sync_key"] = clave_fiscal

    with st.expander("⚙️ Ajustes de cálculo (método Weiss, franjas, YoC y doble retención)", expanded=False):
        a1, a2, a3 = st.columns(3)
        with a1:
            opciones_modo = {
                "Automático (Weiss clásico / TTM)": "auto",
                "Escalón clásico Weiss (Pago × Frec.)": "weiss_clasico",
                "TTM móvil (Últimos N pagos)": "ttm",
            }
            modo_sel = st.selectbox("Construcción de franjas", list(opciones_modo.keys()), index=0)
            modo_calculo = opciones_modo[modo_sel]

            metodo_franjas = st.radio(
                "Extremos de Yield",
                options=["Percentiles (filtra atípicos)", "Mínimo / Máximo absoluto"],
                index=0
            )
            percentil = st.slider("Recorte en extremos (%)", 1, 15, 5) if metodo_franjas.startswith("Percentiles") else 0

            tipo_media = st.radio(
                "Referencia central",
                ["Media aritmética", "Mediana"],
                index=0
            )

        with a2:
            st.markdown(f"**Fiscalidad ({pais_es})**")
            modo_neto_sel = st.radio(
                "Cálculo del Yield Neto",
                options=[
                    "Neto final tras Renta (deducción CDI)",
                    "Neto al cobro (cascada bróker español)"
                ],
                index=0
            )
            modo_neto = "cascada" if modo_neto_sel.startswith("Neto al cobro") else "renta"

            f_col1, f_col2 = st.columns(2)
            with f_col1:
                ret_origen = st.number_input(
                    "Ret. origen (%)",
                    min_value=0.0,
                    max_value=60.0,
                    step=0.5,
                    format="%.2f",
                    key="ret_origen_input"
                )
            with f_col2:
                limite_cdi = st.number_input(
                    "Deducible CDI (%)",
                    min_value=0.0,
                    max_value=60.0,
                    step=0.5,
                    format="%.2f",
                    key="limite_cdi_input"
                )

            impuesto_destino = st.number_input(
                "IRPF destino España (%)",
                min_value=0.0,
                max_value=60.0,
                value=19.0,
                step=1.0,
                format="%.1f"
            )
            st.caption(f"ℹ️ {nota_pais}")

        with a3:
            fuente_dividendo = st.radio(
                "Dividendo anual actual",
                options=["Según franja (Indicado / TTM)", "Forward (Yahoo)", "Manual"],
                index=0
            )
            div_manual = None
            if fuente_dividendo == "Manual":
                div_manual = st.number_input("Dividendo anual manual", min_value=0.0001, value=1.0, step=0.05, format="%.4f")

            freq_opciones = {
                "Automática (dinámica por tramos)": 0,
                "Anual (1/año)": 1,
                "Semestral (2/año)": 2,
                "Cuatrimestral (3/año)": 3,
                "Trimestral (4/año)": 4,
                "Mensual (12/año)": 12,
            }
            freq_override = freq_opciones[st.selectbox("Frecuencia de pagos", list(freq_opciones.keys()), index=0)]

            modo_yoc = st.radio(
                "Curva YoC en gráfico",
                options=["YoC hoy según fecha de compra", "Evolución YoC desde precio fijo"],
                index=0
            )
            precio_compra_yoc = st.number_input(
                "Tu precio medio de compra (opcional)",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.2f"
            )
            escala_log = st.checkbox("Escala logarítmica en precio", value=False)
            forzar_defensiva = st.checkbox("Umbral Chowder defensivo (≥ 8%)", value=False)

# ==============================================================================
# VALIDACIÓN Y CÁLCULO DE BANDAS GERALDINE WEISS
# ==============================================================================
if df_full is None or df_full.empty:
    detalle_err = (info or {}).get("_error", "")
    st.error(
        f"No se pudieron obtener datos de **{ticker_actual}** en Yahoo Finance. "
        f"Comprueba el ticker (en Bolsa española añade `.MC`, ej. `IBE.MC`)."
        + (f" ({detalle_err})" if detalle_err else "")
    )
    st.stop()

div_anual_serie, freq_actual, etiqueta_modo, info_cambio_freq, ev_reg, freq_reg = calcular_dividendo_weiss(
    df_full,
    modo_calculo=modo_calculo,
    freq_override=freq_override,
    info=info
)

if freq_actual == 0 or div_anual_serie.isna().all():
    st.warning(f"**{ticker_actual}** no tiene suficiente historial de dividendos en Yahoo Finance para aplicar Geraldine Weiss.")
    st.stop()

df_full = df_full.copy()
df_full["Div_Anual"] = div_anual_serie

fecha_corte = datetime.today() - timedelta(days=years * 365)
df = df_full[df_full.index >= fecha_corte].copy()
df = df[df["Div_Anual"].notna() & (df["Div_Anual"] > 0) & (df["Close"] > 0)].copy()

if df.empty:
    st.warning(f"No hay suficientes registros válidos de precio y dividendo para **{ticker_actual}** en los últimos {years} años.")
    st.stop()

df["Yield"] = (df["Div_Anual"] / df["Close"]) * 100.0

nombre_empresa = info.get("longName") or info.get("shortName") or ticker_actual
moneda = info.get("currency", "")
sufijo_moneda = f" {moneda}" if moneda else ""
sector = info.get("sector", "N/D")

if percentil == 0:
    yield_infra = float(df["Yield"].max())
    yield_sobre = float(df["Yield"].min())
    etiqueta_extremo = "Mín–Máx"
else:
    yield_infra = float(df["Yield"].quantile(1.0 - percentil / 100.0))
    yield_sobre = float(df["Yield"].quantile(percentil / 100.0))
    etiqueta_extremo = f"P{percentil}–P{100 - percentil}"

yield_medio = float(df["Yield"].mean()) if tipo_media == "Media aritmética" else float(df["Yield"].median())

if yield_sobre <= 0 or yield_medio <= 0 or yield_infra <= 0:
    st.error("Los valores de Dividend Yield calculados no permiten construir las bandas.")
    st.stop()

df["Banda_Infra"] = df["Div_Anual"] / (yield_infra / 100.0)
df["Banda_Media"] = df["Div_Anual"] / (yield_medio / 100.0)
df["Banda_Sobre"] = df["Div_Anual"] / (yield_sobre / 100.0)

precio_actual = float(df["Close"].iloc[-1])
fecha_ultimo = df.index[-1].strftime("%d/%m/%Y")
div_actual_franja = float(df["Div_Anual"].iloc[-1])
forward_yahoo = info.get("dividendRate")

if fuente_dividendo == "Manual" and div_manual is not None:
    div_actual = float(div_manual)
    etiqueta_div = "Manual"
elif fuente_dividendo == "Forward (Yahoo)" and forward_yahoo and float(forward_yahoo) > 0:
    div_actual = float(forward_yahoo)
    etiqueta_div = "Forward"
else:
    div_actual = div_actual_franja
    etiqueta_div = "Indicado" if "Escalón" in etiqueta_modo else "TTM"

fisc = calcular_fiscalidad_efectiva(ret_origen, limite_cdi, impuesto_destino, modo_neto)
factor_neto = fisc["factor_neto"]
tasa_efectiva = fisc["tasa_efectiva"]

yield_actual = (div_actual / precio_actual) * 100.0
yield_actual_neto = yield_actual * factor_neto
yield_infra_neto = yield_infra * factor_neto
yield_medio_neto = yield_medio * factor_neto
yield_sobre_neto = yield_sobre * factor_neto

precio_infra = div_actual / (yield_infra / 100.0)
precio_medio = div_actual / (yield_medio / 100.0)
precio_sobre = div_actual / (yield_sobre / 100.0)

dist_infra = ((precio_infra - precio_actual) / precio_actual) * 100.0
dist_medio = ((precio_medio - precio_actual) / precio_actual) * 100.0
dist_sobre = ((precio_sobre - precio_actual) / precio_actual) * 100.0

if precio_actual <= precio_infra:
    badge_weiss = ("🟢 Infravalorada · Zona de Compra", "pill-green")
    color_actual_key = "green"
    color_actual_hex = "#10B981"
    etiqueta_franja_actual = "Infravalorada"
    sub_actual_cls = "pos"
elif precio_actual <= precio_medio:
    badge_weiss = ("🟢 Franja Atractiva · Bajo la Media", "pill-teal")
    color_actual_key = "teal"
    color_actual_hex = "#2DD4BF"
    etiqueta_franja_actual = "Bajo la Media"
    sub_actual_cls = "teal"
elif precio_actual < precio_sobre:
    badge_weiss = ("🟠 Franja Cara · Sobre la Media", "pill-amber")
    color_actual_key = "amber"
    color_actual_hex = "#F59E0B"
    etiqueta_franja_actual = "Sobre la Media"
    sub_actual_cls = "warn"
else:
    badge_weiss = ("🔴 Sobrevalorada · Zona de Venta", "pill-red")
    color_actual_key = "red"
    color_actual_hex = "#EF4444"
    etiqueta_franja_actual = "Sobrevalorada"
    sub_actual_cls = "neg"

mi_yoc_personal = (div_actual / float(precio_compra_yoc)) * 100.0 if precio_compra_yoc > 0 else None
precio_inicio = float(df["Close"].iloc[0])
fecha_inicio = df.index[0].strftime("%d/%m/%Y")

if modo_yoc.startswith("YoC hoy"):
    df["YoC"] = (div_actual / df["Close"]) * 100.0
    shape_yoc = "linear"
    yoc_inicio = float(df["YoC"].iloc[0])
    yoc_medio_hist = float(df["YoC"].mean())
    etiqueta_leyenda_yoc = f"YoC hoy si compraste ahí (inicio: {yoc_inicio:.2f}%)"
    texto_caption_yoc = (
        f"Si compraste hace {years} años ({precio_inicio:.2f}{sufijo_moneda} el {fecha_inicio}), "
        f"tu <b>YoC hoy es {yoc_inicio:.2f}%</b> bruto (<b>{yoc_inicio * factor_neto:.2f}%</b> neto) · "
        f"YoC medio del periodo: <b>{yoc_medio_hist:.2f}%</b>."
    )
    if mi_yoc_personal is not None:
        texto_caption_yoc += (
            f" · <b>Tu YoC ({precio_compra_yoc:.2f}{sufijo_moneda}): "
            f"{mi_yoc_personal:.2f}% bruto / {mi_yoc_personal * factor_neto:.2f}% neto</b>."
        )
else:
    base_yoc_precio = float(precio_compra_yoc) if precio_compra_yoc > 0 else precio_inicio
    etiqueta_base_yoc = (
        f"tu compra ({base_yoc_precio:.2f}{sufijo_moneda})"
        if precio_compra_yoc > 0
        else f"inicio del periodo ({precio_inicio:.2f}{sufijo_moneda} el {fecha_inicio})"
    )
    df["YoC"] = (df["Div_Anual"] / base_yoc_precio) * 100.0
    shape_yoc = "hv"
    yoc_actual_fijo = (div_actual / base_yoc_precio) * 100.0
    etiqueta_leyenda_yoc = f"Evolución YoC ({yoc_actual_fijo:.2f}%)"
    texto_caption_yoc = (
        f"YoC actual: <b>{yoc_actual_fijo:.2f}%</b> bruto (<b>{yoc_actual_fijo * factor_neto:.2f}%</b> neto) · "
        f"Base: {etiqueta_base_yoc}."
    )

# ==============================================================================
# CÁLCULO DE DGR Y REGLA DE CHOWDER
# ==============================================================================
anio_actual = datetime.today().year
div_eventos_limpios = consolidar_eventos_dividendo(df_full["Dividends"])
div_por_anio = div_eventos_limpios.groupby(div_eventos_limpios.index.year).sum()
div_por_anio = div_por_anio[div_por_anio > 0]
anios_completos = div_por_anio[div_por_anio.index < anio_actual].copy()
anios_reparados = []

if "Escalón" in etiqueta_modo and not anios_completos.empty and not freq_reg.empty:
    for anio in list(anios_completos.index):
        ev_anio = ev_reg[ev_reg.index.year == anio]
        f_anio_serie = freq_reg[freq_reg.index.year == anio]
        if ev_anio.empty or f_anio_serie.empty:
            continue

        n_pagos_anio = len(ev_anio)
        f_esperada = int(f_anio_serie.max())
        hubo_cambio_en_anio = f_anio_serie.nunique() > 1

        serie_anio = df_full.loc[df_full.index.year == anio, "Div_Anual"].dropna()
        if serie_anio.empty:
            continue

        est_anio = float(serie_anio.mean())
        val_anio = float(anios_completos.loc[anio])
        deficit_pagos = (n_pagos_anio < f_esperada or hubo_cambio_en_anio) and val_anio < est_anio * 0.85
        exceso_pagos = (n_pagos_anio > f_esperada or hubo_cambio_en_anio) and val_anio > est_anio * 1.15

        if deficit_pagos or exceso_pagos:
            anios_completos.loc[anio] = est_anio
            div_por_anio.loc[anio] = est_anio
            anios_reparados.append(int(anio))

dgr_1y = dgr_3y = dgr_5y = dgr_10y = None
ultimo_anio = None

if not anios_completos.empty:
    ultimo_anio = int(anios_completos.index.max())
    div_ult = float(anios_completos.loc[ultimo_anio])
    if (ultimo_anio - 1) in anios_completos.index:
        dgr_1y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 1]), 1)
    if (ultimo_anio - 3) in anios_completos.index:
        dgr_3y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 3]), 3)
    if (ultimo_anio - 5) in anios_completos.index:
        dgr_5y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 5]), 5)
    if (ultimo_anio - 10) in anios_completos.index:
        dgr_10y = calcular_cagr(div_ult, float(anios_completos.loc[ultimo_anio - 10]), 10)

if dgr_5y is not None:
    dgr_chowder = dgr_5y
    etiqueta_dgr = f"DGR 5Y ({ultimo_anio - 5}–{ultimo_anio})"
elif dgr_3y is not None:
    dgr_chowder = dgr_3y
    etiqueta_dgr = f"DGR 3Y ({ultimo_anio - 3}–{ultimo_anio})"
elif dgr_1y is not None:
    dgr_chowder = dgr_1y
    etiqueta_dgr = f"DGR 1Y ({ultimo_anio - 1}–{ultimo_anio})"
else:
    dgr_chowder = None
    etiqueta_dgr = "Sin historial"

chowder_val = (yield_actual + dgr_chowder) if dgr_chowder is not None else None

sectores_defensivos = {"Utilities", "Real Estate", "Communication Services"}
es_defensiva = forzar_defensiva or (sector in sectores_defensivos)
if es_defensiva:
    objetivo_chowder = 8.0
    regla_texto = "Utility / REIT / Telecom"
elif yield_actual >= 3.0:
    objetivo_chowder = 12.0
    regla_texto = "Yield ≥ 3%"
else:
    objetivo_chowder = 15.0
    regla_texto = "Yield < 3%"

# ==============================================================================
# CABECERA DE LA EMPRESA ANALIZADA Y AVISO FISCAL
# ==============================================================================
nota_divisa = info.get("_nota_divisa")
nota_divisa_html = f" · <i>{nota_divisa}</i>" if nota_divisa else ""
resumen_fiscal_meta = (
    f"Origen ({pais_es}): <b>{fmt_pct_limpio(ret_origen)}</b>"
    + (f" (CDI {fmt_pct_limpio(limite_cdi)})" if ret_origen > 0 else "")
    + f" · IRPF: <b>{fmt_pct_limpio(impuesto_destino)}</b> → "
    + f"<b>{fmt_pct_limpio(tasa_efectiva)}</b> ({'tras Renta' if modo_neto == 'renta' else 'cascada cobro'})"
)

header_html = (
    '<div class="weiss-header">'
    '<div>'
    f'<div class="weiss-title">{nombre_empresa} <span style="opacity:0.65;font-weight:500;">({ticker_actual})</span></div>'
    f'<div class="weiss-meta">{sector} · Dividendo {etiqueta_div}: <b>{div_actual:.3f}{sufijo_moneda}</b> · '
    f'{info_cambio_freq} · Cierre: {fecha_ultimo}{nota_divisa_html}<br/>{resumen_fiscal_meta}</div>'
    '</div>'
    f'<span class="status-pill {badge_weiss[1]}">{badge_weiss[0]}</span>'
    '</div>'
)
st.markdown(header_html, unsafe_allow_html=True)

if fisc["exceso_no_deducible"] > 0.01:
    st.markdown(
        '<div class="tax-banner">'
        f'⚠️ <b>Doble retención en origen ({pais_es}):</b> se retiene un <b>{fmt_pct_limpio(ret_origen)}</b> en origen '
        f'y solo es deducible un <b>{fmt_pct_limpio(fisc["deducible_renta"])}</b> en la Renta (exceso no recuperado: '
        f'<b>{fmt_pct_limpio(fisc["exceso_no_deducible"])}</b>). Carga final tras Renta: '
        f'<b>{fmt_pct_limpio(fisc["efectivo_renta"])}</b> (en cobro en cascada: <b>{fmt_pct_limpio(fisc["efectivo_cascada"])}</b>). '
        'Si tu bróker tramita exención en origen o reclamas la devolución, ajusta la retención en ⚙️ Ajustes.'
        '</div>',
        unsafe_allow_html=True
    )

# ==============================================================================
# PESTAÑAS ORGANIZADAS
# ==============================================================================
tab_weiss, tab_chowder, tab_datos = st.tabs([
    "📈 Valoración Weiss",
    "🧮 Regla de Chowder",
    "📋 Tablas y CSV"
])

plotly_config = {
    "displaylogo": False,
    "displayModeBar": False,
    "responsive": True
}

# ------------------------------------------------------------------------------
# PESTAÑA 1: VALORACIÓN GERALDINE WEISS
# ------------------------------------------------------------------------------
with tab_weiss:
    render_kpi_grid([
        {
            "label": f"Precio Actual ({etiqueta_franja_actual})",
            "value": f"{precio_actual:.2f}{sufijo_moneda}",
            "yields": f"Bruto: <b>{yield_actual:.2f}%</b> · Neto: <b>{yield_actual_neto:.2f}%</b>",
            "sub": fisc["etiqueta_corta"],
            "sub_class": sub_actual_cls,
            "accent": color_actual_key,
            "val_class": f"val-{color_actual_key}"
        },
        {
            "label": "Infravaloración",
            "value": f"{precio_infra:.2f}{sufijo_moneda}",
            "yields": f"Bruto: <b>{yield_infra:.2f}%</b> · Neto: <b>{yield_infra_neto:.2f}%</b>",
            "sub": f"{dist_infra:+.1f}% vs actual",
            "sub_class": "pos" if dist_infra >= 0 else "",
            "accent": "green",
            "val_class": "val-green"
        },
        {
            "label": "Valoración Media",
            "value": f"{precio_medio:.2f}{sufijo_moneda}",
            "yields": f"Bruto: <b>{yield_medio:.2f}%</b> · Neto: <b>{yield_medio_neto:.2f}%</b>",
            "sub": f"{dist_medio:+.1f}% potencial",
            "sub_class": "pos" if dist_medio >= 0 else "neg",
            "accent": "amber",
            "val_class": "val-amber"
        },
        {
            "label": "Sobrevaloración",
            "value": f"{precio_sobre:.2f}{sufijo_moneda}",
            "yields": f"Bruto: <b>{yield_sobre:.2f}%</b> · Neto: <b>{yield_sobre_neto:.2f}%</b>",
            "sub": f"{dist_sobre:+.1f}% vs actual",
            "sub_class": "neg" if dist_sobre <= 0 else "",
            "accent": "red",
            "val_class": "val-red"
        },
    ])

    rango_total = precio_sobre - precio_infra
    if rango_total > 0:
        if precio_infra < precio_medio < precio_sobre:
            if precio_actual <= precio_medio:
                pos_rel = 0.5 * (precio_actual - precio_infra) / (precio_medio - precio_infra)
            else:
                pos_rel = 0.5 + 0.5 * (precio_actual - precio_medio) / (precio_sobre - precio_medio)
        else:
            pos_rel = (precio_actual - precio_infra) / rango_total

        pos_pct = min(max(pos_rel * 100.0, 0.0), 100.0)
        gauge_html = (
            '<div class="gauge-box">'
            '<div class="gauge-top">'
            f'<span><b>Posición en el canal de Weiss</b> <span style="opacity:0.68;">({etiqueta_extremo} · Media = 50%)</span></span>'
            f'<span style="color:{color_actual_hex};font-weight:800;">{pos_rel * 100:.1f}%</span>'
            '</div>'
            '<div class="gauge-track">'
            '<div class="gauge-mid-tick"></div>'
            f'<div class="gauge-marker" style="left:{pos_pct:.1f}%;border-color:{color_actual_hex};"></div>'
            '</div>'
            '<div class="gauge-labels">'
            f'<span style="color:#10B981;">Infravalorada ({precio_infra:.2f})</span>'
            f'<span style="color:#F59E0B;">Media ({precio_medio:.2f})</span>'
            f'<span style="color:#EF4444;">Sobrevalorada ({precio_sobre:.2f})</span>'
            '</div>'
            '</div>'
        )
        st.markdown(gauge_html, unsafe_allow_html=True)

    st.markdown(f"#### Franjas de Geraldine Weiss ({years} años)")
    st.markdown(
        f'<div class="section-caption">Método activo: <b>{etiqueta_modo}</b> · Precio de cierre sin ajustar por dividendos.</div>',
        unsafe_allow_html=True
    )

    fig_precio = go.Figure()
    fig_precio.add_trace(go.Scatter(
        x=df.index, y=df["Banda_Infra"], mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#10B981", width=1.8, shape="hv"),
        hovertemplate="%{y:.2f}"
    ))
    fig_precio.add_trace(go.Scatter(
        x=df.index, y=df["Banda_Media"], mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#F59E0B", width=1.7, dash="dash", shape="hv"),
        fill="tonexty", fillcolor="rgba(16, 185, 129, 0.14)",
        hovertemplate="%{y:.2f}"
    ))
    fig_precio.add_trace(go.Scatter(
        x=df.index, y=df["Banda_Sobre"], mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#EF4444", width=1.8, shape="hv"),
        fill="tonexty", fillcolor="rgba(239, 68, 68, 0.13)",
        hovertemplate="%{y:.2f}"
    ))
    fig_precio.add_trace(go.Scatter(
        x=df.index, y=df["Close"], mode="lines",
        name="Precio (sin ajustar)",
        line=dict(color="#38BDF8", width=2.2),
        hovertemplate="%{y:.2f}"
    ))

    fig_precio.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title=f"Precio ({moneda})" if moneda else "Precio",
        yaxis_type="log" if escala_log else "linear",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(148, 163, 184, 0.14)", zeroline=False, automargin=True),
        hovermode="x unified",
        height=440,
        margin=dict(l=8, r=10, t=12, b=78),
        legend=dict(orientation="h", yanchor="top", y=-0.16, xanchor="center", x=0.5, font=dict(size=11))
    )
    st.plotly_chart(fig_precio, use_container_width=True, config=plotly_config)

    st.markdown("#### Histórico de Dividend Yield y YoC (%)")
    st.markdown(f'<div class="section-caption">{texto_caption_yoc}</div>', unsafe_allow_html=True)

    fig_yield = go.Figure()
    x_ext = [df.index[0], df.index[-1]]

    fig_yield.add_trace(go.Scatter(
        x=df.index, y=df["Yield"], mode="lines",
        name=f"Dividend Yield ({yield_actual:.2f}%)",
        line=dict(color="#38BDF8", width=2.1),
        fill="tozeroy", fillcolor="rgba(56, 189, 248, 0.08)",
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=df.index, y=df["YoC"], mode="lines",
        name=etiqueta_leyenda_yoc,
        line=dict(color="#A855F7", width=2.1, shape=shape_yoc),
        hovertemplate="%{y:.2f}%"
    ))

    if modo_yoc.startswith("YoC hoy") and mi_yoc_personal is not None:
        fig_yield.add_trace(go.Scatter(
            x=x_ext, y=[mi_yoc_personal, mi_yoc_personal], mode="lines",
            name=f"Mi YoC ({mi_yoc_personal:.2f}%)",
            line=dict(color="#EC4899", width=2.0, dash="dashdot"),
            hovertemplate="%{y:.2f}%"
        ))

    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_infra, yield_infra], mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#10B981", width=1.6, dash="dot"),
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_medio, yield_medio], mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#F59E0B", width=1.6, dash="dash"),
        hovertemplate="%{y:.2f}%"
    ))
    fig_yield.add_trace(go.Scatter(
        x=x_ext, y=[yield_sobre, yield_sobre], mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#EF4444", width=1.6, dash="dot"),
        hovertemplate="%{y:.2f}%"
    ))

    y_vals_max = [float(df["Yield"].max()), float(df["YoC"].max()), yield_infra]
    y_vals_min = [float(df["Yield"].min()), float(df["YoC"].min()), yield_sobre]
    if mi_yoc_personal is not None:
        y_vals_max.append(mi_yoc_personal)
        y_vals_min.append(mi_yoc_personal)

    fig_yield.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Yield / YoC (%)",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(
            range=[max(0.0, min(y_vals_min) * 0.85), max(y_vals_max) * 1.12],
            gridcolor="rgba(148, 163, 184, 0.14)",
            zeroline=False,
            automargin=True
        ),
        hovermode="x unified",
        height=370,
        margin=dict(l=8, r=10, t=12, b=98),
        legend=dict(orientation="h", yanchor="top", y=-0.20, xanchor="center", x=0.5, font=dict(size=11))
    )
    st.plotly_chart(fig_yield, use_container_width=True, config=plotly_config)

# ------------------------------------------------------------------------------
# PESTAÑA 2: REGLA DE CHOWDER Y GRÁFICO HORIZONTAL DE DIVIDENDOS + YoY (%)
# ------------------------------------------------------------------------------
with tab_chowder:
    if chowder_val is not None:
        margen_ch = chowder_val - objetivo_chowder
        if chowder_val >= objetivo_chowder:
            pill_ch = (f"✅ Cumple Regla de Chowder · {chowder_val:.2f}% (margen {margen_ch:+.2f} pp)", "pill-green")
            accent_ch = "green"
        elif chowder_val >= objetivo_chowder - 2.0:
            pill_ch = (f"⚠️ Cerca del objetivo Chowder · {chowder_val:.2f}% ({margen_ch:+.2f} pp)", "pill-amber")
            accent_ch = "amber"
        else:
            pill_ch = (f"❌ No cumple Regla de Chowder · {chowder_val:.2f}% ({margen_ch:+.2f} pp)", "pill-red")
            accent_ch = "red"

        st.markdown(
            f'<div style="margin: 0.3rem 0 0.8rem 0;"><span class="status-pill {pill_ch[1]}">{pill_ch[0]}</span></div>',
            unsafe_allow_html=True
        )

        acc_dgr_ch, sub_dgr_ch = color_dgr(dgr_chowder)
        render_kpi_grid([
            {
                "label": "Número de Chowder",
                "value": f"{chowder_val:.2f}%",
                "sub": f"{margen_ch:+.2f} pp vs objetivo",
                "sub_class": "pos" if margen_ch >= 0 else "neg",
                "accent": accent_ch,
                "val_class": f"val-{accent_ch}"
            },
            {
                "label": "Dividend Yield Actual",
                "value": f"{yield_actual:.2f}%",
                "yields": f"Neto: <b>{yield_actual_neto:.2f}%</b> ({fmt_pct_limpio(tasa_efectiva)} ef.)",
                "sub": f"Franja: {etiqueta_franja_actual}",
                "sub_class": sub_actual_cls,
                "accent": color_actual_key,
                "val_class": f"val-{color_actual_key}"
            },
            {
                "label": etiqueta_dgr,
                "value": f"{dgr_chowder:+.2f}%",
                "sub": "Componente crecimiento",
                "sub_class": sub_dgr_ch,
                "accent": acc_dgr_ch,
                "val_class": f"val-{acc_dgr_ch}"
            },
            {
                "label": "Umbral Aplicable",
                "value": f"≥ {objetivo_chowder:.0f}%",
                "sub": regla_texto,
                "accent": "blue",
                "val_class": "val-blue"
            },
        ])

        if anios_reparados:
            lista_rep = ", ".join(str(a) for a in sorted(anios_reparados))
            st.caption(
                f"ℹ️ Se han normalizado los dividendos de **{lista_rep}** usando la tasa anual indicada "
                "(por cambio de calendario, pagos omitidos en Yahoo o desplazamiento de fecha ex-dividendo)."
            )

        st.markdown("#### Ritmo histórico de crecimiento del dividendo (DGR)")
        acc_1y, sub_1y = color_dgr(dgr_1y)
        acc_3y, sub_3y = color_dgr(dgr_3y)
        acc_5y, sub_5y = color_dgr(dgr_5y)
        acc_10y, sub_10y = color_dgr(dgr_10y)

        render_kpi_grid([
            {
                "label": "DGR 1 Año",
                "value": f"{dgr_1y:+.2f}%" if dgr_1y is not None else "N/D",
                "sub": f"{ultimo_anio - 1}–{ultimo_anio}" if dgr_1y is not None else "Sin datos",
                "sub_class": sub_1y,
                "accent": acc_1y,
                "val_class": f"val-{acc_1y}"
            },
            {
                "label": "DGR 3 Años",
                "value": f"{dgr_3y:+.2f}%" if dgr_3y is not None else "N/D",
                "sub": f"{ultimo_anio - 3}–{ultimo_anio}" if dgr_3y is not None else "Sin datos",
                "sub_class": sub_3y,
                "accent": acc_3y,
                "val_class": f"val-{acc_3y}"
            },
            {
                "label": "DGR 5 Años",
                "value": f"{dgr_5y:+.2f}%" if dgr_5y is not None else "N/D",
                "sub": f"{ultimo_anio - 5}–{ultimo_anio}" if dgr_5y is not None else "Sin datos",
                "sub_class": sub_5y,
                "accent": acc_5y,
                "val_class": f"val-{acc_5y}"
            },
            {
                "label": "DGR 10 Años",
                "value": f"{dgr_10y:+.2f}%" if dgr_10y is not None else "N/D",
                "sub": f"{ultimo_anio - 10}–{ultimo_anio}" if dgr_10y is not None else "Sin datos",
                "sub_class": sub_10y,
                "accent": acc_10y,
                "val_class": f"val-{acc_10y}"
            },
        ])

        yoy_completos = anios_completos.pct_change() * 100.0
        n_barras = min(len(anios_completos), 12)
        div_hist_bar = anios_completos.tail(n_barras)
        yoy_hist_bar = yoy_completos.tail(n_barras)

        if not div_hist_bar.empty:
            st.markdown("#### Evolución del dividendo anual y aumento YoY")
            etiquetas_eje = [
                f"{int(a)}*" if int(a) in anios_reparados else str(int(a))
                for a in div_hist_bar.index
            ]
            colores_barras = []
            textos_barras = []
            hover_yoy = []

            for val, yoy in zip(div_hist_bar.values, yoy_hist_bar.values):
                val_txt = f"{val:.2f}" if val >= 1.0 else f"{val:.3f}"
                if pd.isna(yoy):
                    colores_barras.append("#38BDF8")
                    textos_barras.append(f"<b>{val_txt}</b>")
                    hover_yoy.append("Base")
                elif yoy > 0.05:
                    colores_barras.append("#10B981")
                    textos_barras.append(f"<b>{val_txt}</b> <span style='color:#10B981;'>({yoy:+.1f}%)</span>")
                    hover_yoy.append(f"{yoy:+.2f}%")
                elif yoy < -0.05:
                    colores_barras.append("#EF4444")
                    textos_barras.append(f"<b>{val_txt}</b> <span style='color:#EF4444;'>({yoy:+.1f}%)</span>")
                    hover_yoy.append(f"{yoy:+.2f}%")
                else:
                    colores_barras.append("#F59E0B")
                    textos_barras.append(f"<b>{val_txt}</b> <span style='color:#F59E0B;'>(0.0%)</span>")
                    hover_yoy.append("0.00%")

            altura_barras = max(260, n_barras * 32 + 56)
            max_div_bar = float(div_hist_bar.max())

            fig_div = go.Figure(data=[
                go.Bar(
                    x=div_hist_bar.values,
                    y=etiquetas_eje,
                    orientation="h",
                    marker_color=colores_barras,
                    marker_line_width=0,
                    text=textos_barras,
                    textposition="outside",
                    textfont=dict(size=11),
                    constraintext="none",
                    cliponaxis=False,
                    customdata=hover_yoy,
                    hovertemplate="Año %{y}: %{x:.4f}" + sufijo_moneda + " (YoY: %{customdata})<extra></extra>"
                )
            ])
            fig_div.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=f"Dividendo anual ({moneda})" if moneda else "Dividendo anual",
                xaxis=dict(
                    range=[0, max_div_bar * 1.62],
                    gridcolor="rgba(148, 163, 184, 0.14)",
                    zeroline=False,
                    automargin=True
                ),
                yaxis=dict(type="category", showgrid=False, automargin=True),
                height=altura_barras,
                margin=dict(l=8, r=14, t=10, b=36),
                showlegend=False
            )
            st.plotly_chart(fig_div, use_container_width=True, config=plotly_config)
            st.caption("Verde: subida · Ámbar: congelado · Rojo: recorte · * año normalizado por calendario/Yahoo.")
    else:
        st.info("No hay suficientes años naturales completos de dividendos para calcular la Regla de Chowder.")

# ------------------------------------------------------------------------------
# PESTAÑA 3: TABLAS RESUMEN Y EXPORTACIÓN CSV
# ------------------------------------------------------------------------------
with tab_datos:
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown(f"#### 🎯 Precios Objetivo ({fisc['etiqueta_corta']})")
        col_precio_lbl = f"Precio{sufijo_moneda}"
        resumen_df = pd.DataFrame({
            "Zona": [
                "🟢 Infravaloración",
                "🟡 Valoración Media",
                "🔴 Sobrevaloración",
                f"● Actual ({etiqueta_franja_actual})"
            ],
            "Yield Bruto": [
                f"{yield_infra:.2f}%",
                f"{yield_medio:.2f}%",
                f"{yield_sobre:.2f}%",
                f"{yield_actual:.2f}%"
            ],
            "Yield Neto": [
                f"{yield_infra_neto:.2f}%",
                f"{yield_medio_neto:.2f}%",
                f"{yield_sobre_neto:.2f}%",
                f"{yield_actual_neto:.2f}%"
            ],
            col_precio_lbl: [
                f"{precio_infra:.2f}",
                f"{precio_medio:.2f}",
                f"{precio_sobre:.2f}",
                f"{precio_actual:.2f}"
            ],
            "Distancia": [
                f"{dist_infra:+.1f}%",
                f"{dist_medio:+.1f}%",
                f"{dist_sobre:+.1f}%",
                "0.0%"
            ]
        })

        colores_filas = ["#10B981", "#F59E0B", "#EF4444", color_actual_hex]

        def estilizar_resumen(row):
            c = colores_filas[row.name]
            return [
                "",
                f"color: {c}; font-weight: 600;",
                f"color: {c}; font-weight: 600;",
                f"color: {c}; font-weight: 700;",
                ""
            ]

        st.dataframe(
            resumen_df.style.apply(estilizar_resumen, axis=1),
            use_container_width=True,
            hide_index=True
        )

        st.markdown(f"#### 🧾 Desglose Fiscal ({pais_es})")
        fiscal_df = pd.DataFrame({
            "Concepto": [
                "Retención en origen",
                "Deducible en Renta (CDI)",
                "Exceso no deducible",
                "IRPF destino (España)",
                "Carga final tras Renta",
                "Retención al cobro (cascada)"
            ],
            "Porcentaje": [
                fmt_pct_limpio(ret_origen),
                fmt_pct_limpio(fisc["deducible_renta"]),
                fmt_pct_limpio(fisc["exceso_no_deducible"]),
                fmt_pct_limpio(impuesto_destino),
                fmt_pct_limpio(fisc["efectivo_renta"]),
                fmt_pct_limpio(fisc["efectivo_cascada"])
            ]
        })
        st.dataframe(fiscal_df, use_container_width=True, hide_index=True)

    with col_t2:
        st.markdown("#### 📅 Historial de Dividendos Anuales")
        div_mostrar = div_por_anio.tail(years + 1)
        etiquetas_anio = []
        for a in div_mostrar.index:
            if int(a) == anio_actual:
                etiquetas_anio.append(f"{a} (YTD)")
            elif int(a) in anios_reparados:
                etiquetas_anio.append(f"{a}*")
            else:
                etiquetas_anio.append(str(a))

        tabla_div = pd.DataFrame({
            "Año": etiquetas_anio,
            f"Dividendo{sufijo_moneda}": div_mostrar.values
        })
        tabla_div["YoY (%)"] = tabla_div[f"Dividendo{sufijo_moneda}"].pct_change() * 100.0

        def color_yoy(val):
            if pd.isna(val):
                return ""
            if val > 0:
                return "color: #10B981; font-weight: 600;"
            if val < 0:
                return "color: #EF4444; font-weight: 600;"
            return "color: #F59E0B;"

        st.dataframe(
            tabla_div.iloc[::-1].style.format({
                f"Dividendo{sufijo_moneda}": "{:.4f}",
                "YoY (%)": "{:+.2f}%"
            }, na_rep="—").map(color_yoy, subset=["YoY (%)"]),
            use_container_width=True,
            hide_index=True
        )
        if anios_reparados:
            st.caption("*Año normalizado por cambio de calendario, pagos omitidos o desplazamiento de fecha ex-dividendo.")

    csv_export = df[
        ["Close", "Dividends", "Div_Anual", "Yield", "YoC", "Banda_Infra", "Banda_Media", "Banda_Sobre"]
    ].to_csv()
    st.download_button(
        label="📥 Descargar serie histórica en CSV",
        data=csv_export,
        file_name=f"weiss_chowder_{ticker_actual}_{years}y.csv",
        mime="text/csv",
        use_container_width=True
    )
