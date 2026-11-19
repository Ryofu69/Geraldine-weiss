import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS (MÓVIL + ESCRITORIO)
# ==============================================================================
st.set_page_config(
    page_title="Analizador Geraldine Weiss",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2.5rem;
        max-width: 1120px;
    }
    .weiss-header-title {
        font-size: 1.55rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
        line-height: 1.25;
    }
    .weiss-header-meta {
        font-size: 0.86rem;
        color: #9CA3AF;
        margin-bottom: 0.65rem;
        line-height: 1.45;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.38rem 0.9rem;
        border-radius: 999px;
        font-size: 0.88rem;
        font-weight: 600;
        margin-bottom: 0.9rem;
        border: 1px solid;
    }
    .tax-warning {
        background: rgba(245, 158, 11, 0.10);
        border: 1px solid rgba(245, 158, 11, 0.42);
        border-radius: 12px;
        padding: 0.8rem 1rem;
        font-size: 0.84rem;
        color: #FDE68A;
        line-height: 1.45;
        margin-bottom: 0.85rem;
    }
    .data-warning {
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.50);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        font-size: 0.84rem;
        color: #FECACA;
        line-height: 1.45;
        margin-bottom: 0.95rem;
    }
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
        margin-bottom: 0.95rem;
    }
    @media (max-width: 768px) {
        .kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.6rem;
        }
    }
    .kpi-card {
        background: #16191F;
        border: 1px solid #2A2F3A;
        border-top: 3px solid var(--accent, #2979FF);
        border-radius: 12px;
        padding: 0.82rem 0.9rem;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #9CA3AF;
        margin-bottom: 0.35rem;
        line-height: 1.25;
    }
    .kpi-value {
        font-size: 1.42rem;
        font-weight: 800;
        line-height: 1.15;
        margin-bottom: 0.32rem;
        color: var(--val-color, #F9FAFB);
        word-break: break-word;
    }
    @media (max-width: 480px) {
        .kpi-value {
            font-size: 1.24rem;
        }
    }
    .kpi-mid {
        font-size: 0.78rem;
        color: #D1D5DB;
        margin-bottom: 0.2rem;
        line-height: 1.3;
    }
    .kpi-sub {
        font-size: 0.76rem;
        color: var(--sub-color, #9CA3AF);
        line-height: 1.25;
    }
    .channel-box {
        background: #16191F;
        border: 1px solid #2A2F3A;
        border-radius: 12px;
        padding: 0.9rem 1rem;
        margin-bottom: 1.15rem;
    }
    .channel-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        margin-bottom: 0.65rem;
        gap: 0.5rem;
    }
    .channel-track {
        position: relative;
        height: 11px;
        border-radius: 999px;
        background: linear-gradient(90deg, #00C853 0%, #8BC34A 28%, #FFAB00 50%, #FF6D00 76%, #FF1744 100%);
        margin: 0.5rem 0 0.6rem 0;
    }
    .channel-mid-tick {
        position: absolute;
        left: 50%;
        top: -4px;
        width: 2px;
        height: 19px;
        background: rgba(255, 255, 255, 0.85);
        transform: translateX(-50%);
        border-radius: 2px;
    }
    .channel-dot {
        position: absolute;
        top: 50%;
        width: 19px;
        height: 19px;
        border-radius: 50%;
        background: var(--dot-color, #00E676);
        border: 3px solid #FFFFFF;
        box-shadow: 0 0 8px rgba(0, 0, 0, 0.65);
        transform: translate(-50%, -50%);
        z-index: 2;
    }
    .channel-labels {
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        margin-top: 0.25rem;
    }
    .info-note {
        background: rgba(59, 130, 246, 0.10);
        border: 1px solid rgba(59, 130, 246, 0.35);
        border-radius: 10px;
        padding: 0.68rem 0.9rem;
        font-size: 0.82rem;
        color: #BFDBFE;
        margin-bottom: 0.9rem;
    }
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.84rem;
        margin-bottom: 1rem;
        background: #16191F;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #2A2F3A;
    }
    .styled-table th {
        text-align: left;
        padding: 0.62rem 0.75rem;
        background: #1E222B;
        color: #9CA3AF;
        font-weight: 600;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        border-bottom: 1px solid #2A2F3A;
    }
    .styled-table td {
        padding: 0.58rem 0.75rem;
        border-bottom: 1px solid #232832;
        color: #E5E7EB;
    }
    .styled-table tr:last-child td {
        border-bottom: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# FISCALIDAD POR PAÍS (CONVENIOS DE DOBLE IMPOSICIÓN CON ESPAÑA)
# ==============================================================================
FISCALIDAD_PAISES = {
    "Spain":          ("España",        0.0,    0.0),
    "United Kingdom": ("Reino Unido",   0.0,    0.0),
    "United States":  ("EE. UU.",      15.0,   15.0),
    "Ireland":        ("Irlanda",      25.0,    0.0),
    "Germany":        ("Alemania",     26.375, 15.0),
    "France":         ("Francia",      25.0,   15.0),
    "Switzerland":    ("Suiza",        35.0,   15.0),
    "Netherlands":    ("Países Bajos", 15.0,   15.0),
    "Italy":          ("Italia",       26.0,   15.0),
    "Canada":         ("Canadá",       15.0,   15.0),
    "Belgium":        ("Bélgica",      30.0,   15.0),
    "Portugal":       ("Portugal",     25.0,   15.0),
    "Sweden":         ("Suecia",       30.0,   15.0),
    "Denmark":        ("Dinamarca",    27.0,   15.0),
    "Finland":        ("Finlandia",    35.0,   15.0),
    "Norway":         ("Noruega",      25.0,   15.0),
    "Austria":        ("Austria",      27.5,   15.0),
    "Japan":          ("Japón",        15.315, 10.0),
    "Australia":      ("Australia",    15.0,   15.0),
}

SUFIJO_PAIS = {
    ".MC": "Spain",
    ".L":  "United Kingdom",
    ".DE": "Germany",
    ".PA": "France",
    ".SW": "Switzerland",
    ".AS": "Netherlands",
    ".MI": "Italy",
    ".TO": "Canada",
    ".BR": "Belgium",
    ".LS": "Portugal",
    ".ST": "Sweden",
    ".CO": "Denmark",
    ".HE": "Finland",
    ".OL": "Norway",
    ".VI": "Austria",
    ".T":  "Japan",
    ".AX": "Australia",
}

EJEMPLOS_DGI = [
    "— Elegir ejemplo rápido —",
    "JNJ (Johnson & Johnson)",
    "KO (Coca-Cola)",
    "PG (Procter & Gamble)",
    "MKC (McCormick)",
    "ACN (Accenture)",
    "ABBV (AbbVie)",
    "PEP (PepsiCo)",
    "O (Realty Income)",
    "VIS.MC (Viscofan)",
    "IBE.MC (Iberdrola)",
    "ITX.MC (Inditex)",
    "ULVR.L (Unilever)",
]


def detectar_fiscalidad(ticker: str, info: dict):
    """Devuelve (nombre_pais, retencion_origen_%, limite_cdi_%)."""
    pais_info = (info.get("country") or "").strip()
    if pais_info in FISCALIDAD_PAISES:
        return FISCALIDAD_PAISES[pais_info]

    for sufijo, pais_key in SUFIJO_PAIS.items():
        if ticker.endswith(sufijo):
            return FISCALIDAD_PAISES[pais_key]

    if "." not in ticker:
        return FISCALIDAD_PAISES["United States"]

    return (pais_info or "Desconocido", 15.0, 15.0)


def calcular_carga_fiscal(ret_origen: float, limite_cdi: float, irpf: float, modo_neto: str):
    """Calcula la carga fiscal efectiva tras Renta (CDI) y en cobro en cascada."""
    deducible_cdi = min(ret_origen, limite_cdi, irpf)
    exceso_no_deducible = max(0.0, ret_origen - deducible_cdi)
    carga_renta = min(100.0, irpf + exceso_no_deducible)
    carga_cascada = (1.0 - (1.0 - ret_origen / 100.0) * (1.0 - irpf / 100.0)) * 100.0

    if modo_neto.startswith("Neto final"):
        efectivo = carga_renta
        etiqueta_corta = "tras Renta"
    else:
        efectivo = carga_cascada
        etiqueta_corta = "en cascada"

    return {
        "deducible_cdi": deducible_cdi,
        "exceso_no_deducible": exceso_no_deducible,
        "carga_renta": carga_renta,
        "carga_cascada": carga_cascada,
        "efectivo": efectivo,
        "etiqueta_corta": etiqueta_corta,
    }


# ==============================================================================
# LIMPIEZA DE DATOS, DIVISAS, FRECUENCIA DINÁMICA Y OVERRIDE MANUAL
# ==============================================================================
def normalizar_divisa_subunidad(df: pd.DataFrame, info: dict, ticker: str):
    """
    Corrige desajustes 100x típicos de la Bolsa de Londres (.L) entre peniques (GBp/GBX)
    y libras esterlinas (GBP) en precios, dividendos históricos y tasas anuales.
    """
    moneda = info.get("currency") or ""
    forward_rate = info.get("dividendRate")
    trailing_rate = info.get("trailingAnnualDividendRate")
    es_londres_sub = moneda in ("GBp", "GBX") or (ticker.endswith(".L") and moneda == "")

    if not es_londres_sub:
        return df, moneda or "USD", forward_rate, trailing_rate

    df = df.copy()
    df["Close"] = df["Close"] / 100.0
    med_price_gbp = float(df["Close"].median()) if not df["Close"].empty else 0.0

    divs_pos = df["Dividends"][df["Dividends"] > 0]
    if not divs_pos.empty and med_price_gbp > 0:
        recientes = divs_pos[divs_pos.index >= (divs_pos.index[-1] - pd.Timedelta(days=1095))]
        if not recientes.empty:
            span_anios = max(1.0, (recientes.index[-1] - recientes.index[0]).days / 365.25)
            anual_est = float(recientes.sum()) / span_anios
            if (anual_est / med_price_gbp) > 0.50:
                df["Dividends"] = df["Dividends"] / 100.0

    last_close_gbp = float(df["Close"].iloc[-1]) if not df["Close"].empty else 0.0
    if forward_rate and forward_rate > 0 and last_close_gbp > 0:
        if (float(forward_rate) / last_close_gbp) > 0.50:
            forward_rate = float(forward_rate) / 100.0
    if trailing_rate and trailing_rate > 0 and last_close_gbp > 0:
        if (float(trailing_rate) / last_close_gbp) > 0.50:
            trailing_rate = float(trailing_rate) / 100.0

    return df, "GBP", forward_rate, trailing_rate


def parsear_dividendos_manuales(texto: str) -> dict:
    """
    Parsea líneas con formato 'Año, Dividendo' (acepta ',', ';', ':' o espacios y
    decimales con punto o coma, p. ej. '2024; 2,33' o '2024, 2.33').
    """
    resultado = {}
    if not texto or not texto.strip():
        return resultado

    for linea in texto.strip().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        m = re.match(r"^(\d{4})\s*[,;:\t\s]+\s*([0-9]+(?:[.,][0-9]+)?)$", linea)
        if m:
            anio = int(m.group(1))
            val = float(m.group(2).replace(",", "."))
            if 1980 <= anio <= 2100 and val > 0:
                resultado[anio] = val
    return dict(sorted(resultado.items()))


def consolidar_eventos_dividendo(div_series: pd.Series) -> pd.Series:
    """
    Extrae dividendos > 0 y elimina duplicados idénticos en un margen de 1–5 días
    (error ocasional de Yahoo Finance) en lugar de sumarlos.
    """
    s = div_series[div_series > 0].sort_index()
    if s.empty:
        return s

    fechas_out = []
    valores_out = []

    for fecha, val in s.items():
        val = float(val)
        if not fechas_out:
            fechas_out.append(fecha)
            valores_out.append(val)
            continue

        delta_dias = (fecha - fechas_out[-1]).total_seconds() / 86400.0
        if delta_dias <= 5.0:
            prev_val = valores_out[-1]
            diff_rel = abs(val - prev_val) / max(val, prev_val)
            if diff_rel <= 0.05:
                continue
            else:
                valores_out[-1] = prev_val + val
        else:
            fechas_out.append(fecha)
            valores_out.append(val)

    return pd.Series(valores_out, index=pd.DatetimeIndex(fechas_out), name="Dividends")


def filtrar_extraordinarios_intercalados(eventos: pd.Series) -> pd.Series:
    """
    Filtra pequeños dividendos extraordinarios que caen entre dos pagos regulares
    (ej. VIS.MC en marzo de 2018) para no hundir las bandas.
    """
    if len(eventos) < 5:
        return eventos.copy()

    dias = np.array([(f - eventos.index[0]).total_seconds() / 86400.0 for f in eventos.index], dtype=float)
    vals = eventos.values.astype(float)
    n = len(eventos)
    mantener = np.ones(n, dtype=bool)
    gaps_all = np.diff(dias)

    for i in range(1, n - 1):
        lo_g = max(0, i - 3)
        hi_g = min(len(gaps_all), i + 3)
        local_gap = float(np.median(gaps_all[lo_g:hi_g]))

        lo_v = max(0, i - 2)
        hi_v = min(n, i + 3)
        vecinos = [vals[j] for j in range(lo_v, hi_v) if j != i]
        local_amt = float(np.median(vecinos)) if vecinos else vals[i]

        gap_prev = dias[i] - dias[i - 1]
        gap_next = dias[i + 1] - dias[i]

        if (
            local_gap > 0
            and gap_prev < 0.65 * local_gap
            and gap_next < 0.65 * local_gap
            and vals[i] < 0.45 * local_amt
        ):
            mantener[i] = False

    return eventos[mantener].copy()


def _mapear_gap_a_frecuencia(gap_dias: float) -> int:
    if gap_dias <= 0:
        return 4
    if gap_dias < 45:
        return 12
    if gap_dias < 110:
        return 4
    if gap_dias < 150:
        return 3
    if gap_dias < 260:
        return 2
    return 1


def _frecuencia_mas_cercana(ratio: float) -> int:
    candidatos = [1, 2, 3, 4, 12]
    return min(candidatos, key=lambda c: abs(c - ratio))


def detectar_frecuencia_dinamica(eventos: pd.Series, forward_rate=None, freq_forzada=None) -> pd.Series:
    """
    Detecta la frecuencia anual de pago por tramos usando días reales y valida cada
    transición mediante continuidad del importe y contraste con dividendRate.
    """
    n = len(eventos)
    if n == 0:
        return pd.Series(dtype=int)

    if freq_forzada is not None:
        return pd.Series([int(freq_forzada)] * n, index=eventos.index, dtype=int)

    if n == 1:
        f = 4
        if forward_rate and forward_rate > 0 and eventos.iloc[0] > 0:
            est = float(forward_rate) / float(eventos.iloc[0])
            cand = _frecuencia_mas_cercana(est)
            if abs(est - cand) / cand <= 0.25:
                f = cand
        return pd.Series([f], index=eventos.index, dtype=int)

    dias = np.array([(f - eventos.index[0]).total_seconds() / 86400.0 for f in eventos.index], dtype=float)
    vals = eventos.values.astype(float)
    gaps = np.diff(dias)

    raw_freqs = np.zeros(n, dtype=int)
    for i in range(n):
        g_list = []
        if i > 0:
            g_list.append(gaps[i - 1])
        if i < n - 1:
            g_list.append(gaps[i])
        if i > 1:
            g_list.append(gaps[i - 2])
        if i < n - 2:
            g_list.append(gaps[i + 1])
        med_g = float(np.median(g_list)) if g_list else 91.25
        raw_freqs[i] = _mapear_gap_a_frecuencia(med_g)

    for i in range(1, n - 1):
        if raw_freqs[i - 1] == raw_freqs[i + 1] and raw_freqs[i] != raw_freqs[i - 1]:
            raw_freqs[i] = raw_freqs[i - 1]

    segmentos = []
    start = 0
    for i in range(1, n):
        if raw_freqs[i] != raw_freqs[start]:
            segmentos.append([start, i - 1, int(raw_freqs[start])])
            start = i
    segmentos.append([start, n - 1, int(raw_freqs[start])])

    ancla_actual = None
    if forward_rate and forward_rate > 0 and vals[-1] > 0:
        est = float(forward_rate) / vals[-1]
        cand = _frecuencia_mas_cercana(est)
        if abs(est - cand) / cand <= 0.18:
            ancla_actual = cand
            segmentos[-1][2] = cand

    for k in range(1, len(segmentos)):
        a_ini, a_fin, f_a = segmentos[k - 1]
        b_ini, b_fin, f_b = segmentos[k]
        if f_a == f_b:
            continue

        amt_a = float(np.median(vals[max(a_ini, a_fin - 1): a_fin + 1]))
        amt_b = float(np.median(vals[b_ini: min(b_fin + 1, b_ini + 2)]))
        if amt_a <= 0 or amt_b <= 0:
            continue

        actual_ratio = amt_b / amt_a
        expected_ratio = f_a / f_b

        if abs(np.log(actual_ratio)) < abs(np.log(actual_ratio / expected_ratio)):
            if k == len(segmentos) - 1 and ancla_actual is not None:
                segmentos[k][2] = ancla_actual
            else:
                segmentos[k][2] = f_a

    if ancla_actual is not None and len(segmentos) >= 2:
        for k in range(len(segmentos) - 1, 0, -1):
            a_ini, a_fin, f_a = segmentos[k - 1]
            b_ini, b_fin, f_b = segmentos[k]
            if f_a == f_b:
                continue
            amt_a = float(np.median(vals[max(a_ini, a_fin - 1): a_fin + 1]))
            amt_b = float(np.median(vals[b_ini: min(b_fin + 1, b_ini + 2)]))
            if amt_a <= 0 or amt_b <= 0:
                continue
            actual_ratio = amt_b / amt_a
            expected_ratio = f_a / f_b
            if abs(np.log(actual_ratio)) < abs(np.log(actual_ratio / expected_ratio)):
                segmentos[k - 1][2] = f_b

    freqs_final = np.zeros(n, dtype=int)
    for ini, fin, f in segmentos:
        freqs_final[ini: fin + 1] = f

    return pd.Series(freqs_final, index=eventos.index, dtype=int)


def es_patron_pagos_uniforme(eventos: pd.Series, freqs: pd.Series) -> bool:
    """
    Determina si la empresa paga importes regulares iguales cada periodo (modo Weiss clásico)
    o pagos alternantes desiguales a cuenta/complementario (modo TTM móvil).
    """
    if len(eventos) < 4:
        return True

    freq_actual = int(freqs.iloc[-1])
    if freq_actual == 1:
        return True

    recientes = eventos[freqs == freq_actual].tail(8)
    if len(recientes) < 3:
        return True

    ratios = recientes.values[1:] / recientes.values[:-1]
    saltos_bruscos = np.sum((ratios < 0.80) | (ratios > 1.28))
    return (saltos_bruscos / len(ratios)) < 0.30


def construir_series_dividendo_diarias(
    df_index: pd.DatetimeIndex,
    eventos: pd.Series,
    freqs: pd.Series,
    metodo_efectivo: str,
) -> pd.Series:
    """Construye la serie diaria de dividendo anualizado ('weiss' o 'ttm')."""
    if eventos.empty:
        return pd.Series(np.nan, index=df_index)

    if metodo_efectivo == "weiss":
        div_ev = eventos * freqs
    else:
        vals = eventos.values.astype(float)
        f_arr = freqs.values.astype(int)
        ttm_vals = []
        for i in range(len(vals)):
            n_pagos = max(1, int(f_arr[i]))
            if i + 1 < n_pagos:
                ttm_vals.append(float(np.mean(vals[: i + 1])) * n_pagos)
            else:
                ttm_vals.append(float(np.sum(vals[i - n_pagos + 1: i + 1])))
        div_ev = pd.Series(ttm_vals, index=eventos.index)

    serie_diaria = div_ev.reindex(df_index.union(div_ev.index)).sort_index().ffill()
    return serie_diaria.reindex(df_index)


def calcular_dividendos_anuales_normalizados(
    eventos: pd.Series,
    freqs: pd.Series,
    div_indicado_diario: pd.Series,
    es_uniforme: bool,
):
    """
    Construye la serie de dividendos por año natural completo normalizando años con
    cambio de calendario, pagos omitidos por Yahoo o exceso de pagos.
    """
    if eventos.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), []

    anio_actual = datetime.today().year
    anios = sorted(set(eventos.index.year))
    brutos_dict = {}
    norm_dict = {}
    anios_normalizados = []

    for y in anios:
        ev_y = eventos[eventos.index.year == y]
        fr_y = freqs[freqs.index.year == y]
        suma_bruta = float(ev_y.sum())
        brutos_dict[y] = suma_bruta

        if y >= anio_actual:
            norm_dict[y] = suma_bruta
            continue

        frecuencias_unicas = sorted(set(fr_y.values))
        cambio_cal = len(frecuencias_unicas) > 1
        freq_esp = int(fr_y.mode().iloc[0]) if not fr_y.empty else 4
        n_pagos = len(ev_y)

        necesita_norm = cambio_cal or (n_pagos != freq_esp)

        if necesita_norm and (es_uniforme or cambio_cal or n_pagos < freq_esp):
            ind_y = div_indicado_diario[div_indicado_diario.index.year == y].dropna()
            if not ind_y.empty:
                val_norm = float(ind_y.mean())
            else:
                val_norm = float((ev_y * fr_y).mean())
            norm_dict[y] = val_norm
            anios_normalizados.append(y)
        else:
            norm_dict[y] = suma_bruta

    return pd.Series(brutos_dict, dtype=float), pd.Series(norm_dict, dtype=float), anios_normalizados


def calcular_cagr(serie: pd.Series, anios_atras: int):
    """Calcula el CAGR entre el último año completo y (último - anios_atras)."""
    if len(serie) < 2:
        return None, None, None
    anio_fin = int(serie.index[-1])
    anio_ini = anio_fin - anios_atras
    if anio_ini not in serie.index:
        return None, None, None
    v_ini = float(serie.loc[anio_ini])
    v_fin = float(serie.loc[anio_fin])
    if v_ini <= 0 or v_fin <= 0:
        return None, None, None
    cagr = ((v_fin / v_ini) ** (1.0 / anios_atras) - 1.0) * 100.0
    return cagr, anio_ini, anio_fin


def auditar_integridad_yahoo(
    df_div_anual: pd.Series,
    div_serie_actual: float,
    forward_yahoo,
    trailing_yahoo,
    moneda: str,
):
    """
    Detecta signos claros de datos incompletos en Yahoo Finance:
      1. Diferencia > 20% entre el dividendo calculado del histórico y dividendRate/trailingRate.
      2. Desplomes bruscos > 35% en un único salto de la serie de dividendo anualizado.
    """
    alertas = []

    ref_yahoo = None
    ref_etiq = ""
    if forward_yahoo and forward_yahoo > 0:
        ref_yahoo = float(forward_yahoo)
        ref_etiq = "Forward (dividendRate)"
    elif trailing_yahoo and trailing_yahoo > 0:
        ref_yahoo = float(trailing_yahoo)
        ref_etiq = "Trailing anual"

    if ref_yahoo and div_serie_actual > 0:
        diff_pct = abs(ref_yahoo - div_serie_actual) / ref_yahoo * 100.0
        if diff_pct >= 20.0:
            alertas.append(
                f"El histórico de pagos de Yahoo arroja <b>{div_serie_actual:.3f} {moneda}/año</b>, "
                f"pero el dato {ref_etiq} de Yahoo marca <b>{ref_yahoo:.3f} {moneda}/año</b> "
                f"(desviación del <b>{diff_pct:.0f}%</b>). Es habitual en bolsas europeas cuando Yahoo omite "
                f"dividendos a cuenta o complementarios."
            )

    # Detectar escalones con caídas > 35% en un solo paso
    cambios = df_div_anual[df_div_anual.ne(df_div_anual.shift())]
    if len(cambios) >= 2:
        caidas = []
        vals_c = cambios.values
        fechas_c = cambios.index
        for i in range(1, len(vals_c)):
            if vals_c[i - 1] > 0:
                pct = (vals_c[i] - vals_c[i - 1]) / vals_c[i - 1] * 100.0
                if pct <= -35.0:
                    caidas.append(f"{fechas_c[i].year} ({pct:.0f}%)")
        if caidas:
            alertas.append(
                f"Se detectan caídas bruscas en la serie de dividendo de Yahoo en: "
                f"<b>{', '.join(caidas)}</b>. Comprueba en <i>Tablas y CSV → Pagos crudos de Yahoo</i> "
                f"si fue un recorte real o falta de pagos en Yahoo."
            )

    return alertas


# ==============================================================================
# DESCARGA CACHEADA DE YAHOO FINANCE
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def cargar_datos_yahoo(ticker: str, years: int):
    """Descarga histórico SIN ajustar por dividendos (auto_adjust=False)."""
    end_date = datetime.today()
    descarga_anios = max(years + 2, 13)
    start_date = end_date - timedelta(days=descarga_anios * 365 + 45)

    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date, auto_adjust=False)

    if df.empty or "Close" not in df.columns:
        return None, {}, "", None, None

    if "Dividends" not in df.columns:
        df["Dividends"] = 0.0

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    df, moneda, forward_rate, trailing_rate = normalizar_divisa_subunidad(df, info, ticker)
    return df, info, moneda, forward_rate, trailing_rate


# ==============================================================================
# INTERFAZ SUPERIOR
# ==============================================================================
st.markdown("## 📊 Analizador DGI · Geraldine Weiss & Chowder")

if "ticker_activo" not in st.session_state:
    st.session_state["ticker_activo"] = "ACN"
if "selector_ejemplo" not in st.session_state:
    st.session_state["selector_ejemplo"] = EJEMPLOS_DGI[0]


def _on_ejemplo_change():
    sel = st.session_state["selector_ejemplo"]
    if sel != EJEMPLOS_DGI[0]:
        st.session_state["ticker_activo"] = sel.split(" ")[0].strip().upper()
        st.session_state["selector_ejemplo"] = EJEMPLOS_DGI[0]


col_sel1, col_sel2, col_sel3 = st.columns([2.2, 1.5, 1.1])

with col_sel1:
    with st.form("form_ticker", border=False):
        c_in, c_btn = st.columns([3, 1.2])
        with c_in:
            ticker_text = st.text_input(
                "Ticker (Yahoo Finance)",
                value=st.session_state["ticker_activo"],
                placeholder="Ej: JNJ, MKC, ACN, VIS.MC, ULVR.L",
                label_visibility="collapsed",
            )
        with c_btn:
            submitted = st.form_submit_button("Analizar", type="primary", use_container_width=True)
        if submitted and ticker_text.strip():
            st.session_state["ticker_activo"] = ticker_text.strip().upper()

with col_sel2:
    st.selectbox(
        "Ejemplos DGI",
        options=EJEMPLOS_DGI,
        key="selector_ejemplo",
        on_change=_on_ejemplo_change,
        label_visibility="collapsed",
    )

with col_sel3:
    years = st.selectbox(
        "Periodo",
        options=[5, 7, 10, 12, 15, 20],
        index=3,  # Predeterminado: 12 años
        format_func=lambda x: f"{x} años",
        label_visibility="collapsed",
    )

ticker_input = st.session_state["ticker_activo"]

with st.spinner(f"Descargando datos históricos de {ticker_input}..."):
    df_raw, info, moneda, forward_yahoo, trailing_yahoo = cargar_datos_yahoo(ticker_input, years)

if df_raw is None or df_raw.empty:
    st.error(
        f"No se encontraron datos para **{ticker_input}** en Yahoo Finance. "
        "Verifica el símbolo (ej. `JNJ`, `MKC`, `ACN`, `VIS.MC`, `IBE.MC`, `ULVR.L`)."
    )
    st.stop()

pais_nombre, ret_origen_auto, cdi_auto = detectar_fiscalidad(ticker_input, info)
sector = info.get("sector") or "N/D"
es_defensiva_auto = any(
    k in sector.lower() for k in ("utilit", "real estate", "communication")
)

# ==============================================================================
# PANEL DE AJUSTES
# ==============================================================================
with st.expander("⚙️ Ajustes de cálculo (método Weiss, franjas, YoC, impuestos y corrección manual)", expanded=False):
    a1, a2 = st.columns(2)

    with a1:
        modo_franjas = st.selectbox(
            "Construcción de franjas",
            options=[
                "Automático (Weiss clásico / TTM)",
                "Escalón clásico Weiss (Dividendo indicado)",
                "TTM móvil (Últimos N pagos)",
            ],
            index=0,
        )

        metodo_extremos = st.radio(
            "Extremos de Yield",
            options=["Percentiles (filtra atípicos)", "Mínimo / Máximo absoluto"],
            index=0,
        )

        if metodo_extremos.startswith("Percentiles"):
            percentil = st.slider("Recorte en extremos (%)", min_value=1, max_value=15, value=5)
        else:
            percentil = 0

        tipo_media = st.radio(
            "Referencia central",
            options=["Media aritmética", "Mediana"],
            index=0,
        )

        fuente_dividendo = st.radio(
            "Dividendo anual actual",
            options=["Según franja (Indicado / TTM)", "Forward (Yahoo)", "Manual"],
            index=0,
        )
        div_manual = None
        if fuente_dividendo == "Manual":
            div_manual = st.number_input(
                f"Dividendo anual manual ({moneda})",
                min_value=0.0001,
                value=1.0,
                step=0.05,
                format="%.4f",
            )

    with a2:
        freq_opcion = st.selectbox(
            "Frecuencia de pagos",
            options=["Automática", "1 pago/año", "2 pagos/año", "3 pagos/año", "4 pagos/año", "12 pagos/año"],
            index=0,
        )
        freq_forzada = None if freq_opcion == "Automática" else int(freq_opcion.split(" ")[0])

        modo_yoc = st.radio(
            "Curva YoC en gráfico de Yield",
            options=[
                "YoC histórico a hoy (Div. actual / Precio)",
                "YoC acumulado desde compra (escalones)",
            ],
            index=0,
        )
        precio_compra_yoc = st.number_input(
            f"Precio medio de compra para 'Mi YoC' ({moneda}, 0 = desactivado)",
            min_value=0.0,
            value=0.0,
            step=1.0,
            format="%.2f",
        )

        st.markdown("**Fiscalidad y doble retención**")
        modo_neto = st.radio(
            "Cálculo del Yield neto",
            options=[
                "Neto final tras Renta (deducción CDI)",
                "Neto al cobro en cascada",
            ],
            index=0,
        )
        irpf_espana = st.number_input(
            "IRPF ahorro España (%)",
            min_value=0.0,
            max_value=50.0,
            value=19.0,
            step=1.0,
            format="%.1f",
        )
        personalizar_origen = st.checkbox(
            f"Personalizar retención de origen (auto {pais_nombre}: {ret_origen_auto:g}% / CDI {cdi_auto:g}%)",
            value=False,
        )
        if personalizar_origen:
            c_t1, c_t2 = st.columns(2)
            with c_t1:
                ret_origen = st.number_input(
                    "Ret. origen (%)",
                    min_value=0.0,
                    max_value=60.0,
                    value=float(ret_origen_auto),
                    step=0.5,
                    format="%.2f",
                )
            with c_t2:
                limite_cdi = st.number_input(
                    "Límite CDI (%)",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(cdi_auto),
                    step=1.0,
                    format="%.1f",
                )
        else:
            ret_origen = float(ret_origen_auto)
            limite_cdi = float(cdi_auto)

        escala_log = st.checkbox("Escala logarítmica en precio", value=False)
        forzar_chowder_def = st.checkbox("Umbral Chowder defensivo (≥ 8%)", value=es_defensiva_auto)

    st.divider()
    st.markdown("**🛠️ Corrección manual de histórico de dividendos (si Yahoo omite pagos)**")
    usar_hist_manual = st.checkbox(
        "Sustituir el histórico de dividendos de Yahoo por mi tabla anual",
        value=False,
    )
    texto_hist_manual = ""
    if usar_hist_manual:
        texto_hist_manual = st.text_area(
            "Pega un año y su dividendo total anual por línea (ej: 2024, 2.33):",
            height=170,
            placeholder="2015, 0.75\n2016, 0.79\n2017, 0.85\n...\n2025, 2.33\n2026, 2.52",
        )


# ==============================================================================
# CÁLCULOS PRINCIPALES
# ==============================================================================
eventos_brutos = consolidar_eventos_dividendo(df_raw["Dividends"])
manual_dict = parsear_dividendos_manuales(texto_hist_manual) if usar_hist_manual else {}
manual_hist_activo = usar_hist_manual and len(manual_dict) >= 2

if manual_hist_activo:
    # Serie diaria mapeada directamente desde la tabla manual anual
    anios_serie = pd.Series(df_raw.index.year, index=df_raw.index)
    div_activo_full = anios_serie.map(manual_dict).ffill()
    metodo_efectivo = "manual_anual"
    es_uniforme = True
    freqs_din = pd.Series([1], index=pd.DatetimeIndex([df_raw.index[-1]]), dtype=int)
    eventos_reg = eventos_brutos
    div_anual_bruto = pd.Series(manual_dict, dtype=float).sort_index()
    div_anual_norm = div_anual_bruto.copy()
    anios_norm = []
else:
    if eventos_brutos.empty:
        st.error(
            f"**{ticker_input}** no registra dividendos en Yahoo Finance en este periodo. "
            "Puedes introducirlos manualmente en ⚙️ Ajustes."
        )
        st.stop()

    eventos_reg = filtrar_extraordinarios_intercalados(eventos_brutos)
    freqs_din = detectar_frecuencia_dinamica(eventos_reg, forward_rate=forward_yahoo, freq_forzada=freq_forzada)
    es_uniforme = es_patron_pagos_uniforme(eventos_reg, freqs_din)

    if modo_franjas.startswith("Automático"):
        metodo_efectivo = "weiss" if es_uniforme else "ttm"
    elif modo_franjas.startswith("Escalón"):
        metodo_efectivo = "weiss"
    else:
        metodo_efectivo = "ttm"

    div_indicado_full = construir_series_dividendo_diarias(df_raw.index, eventos_reg, freqs_din, "weiss")
    div_activo_full = construir_series_dividendo_diarias(df_raw.index, eventos_reg, freqs_din, metodo_efectivo)

    div_anual_bruto, div_anual_norm, anios_norm = calcular_dividendos_anuales_normalizados(
        eventos_reg, freqs_din, div_indicado_full, es_uniforme
    )

df = df_raw[["Close", "Dividends"]].copy()
df["Div_Anual"] = div_activo_full

cutoff_date = datetime.today() - timedelta(days=years * 365)
df = df[df.index >= cutoff_date].copy()
df = df[(df["Close"] > 0) & (df["Div_Anual"] > 0)].copy()

if df.empty or len(df) < 20:
    st.error(f"No hay suficientes datos válidos de precio y dividendo para **{ticker_input}** en {years} años.")
    st.stop()

df["Yield"] = (df["Div_Anual"] / df["Close"]) * 100.0

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
div_serie_actual = float(df["Div_Anual"].iloc[-1])

if fuente_dividendo == "Manual" and div_manual is not None:
    div_actual = float(div_manual)
    etiqueta_div = "Dividendo Manual"
elif fuente_dividendo == "Forward (Yahoo)" and forward_yahoo and forward_yahoo > 0:
    div_actual = float(forward_yahoo)
    etiqueta_div = "Dividendo Forward"
else:
    div_actual = div_serie_actual
    if manual_hist_activo:
        etiqueta_div = "Dividendo Tabla Manual"
    elif metodo_efectivo == "weiss":
        etiqueta_div = "Dividendo Indicado"
    else:
        etiqueta_div = "Dividendo TTM"

# Auditoría de integridad de datos de Yahoo (solo cuando no hay override manual)
alertas_yahoo = (
    []
    if manual_hist_activo
    else auditar_integridad_yahoo(df["Div_Anual"], div_serie_actual, forward_yahoo, trailing_yahoo, moneda)
)

fiscal = calcular_carga_fiscal(ret_origen, limite_cdi, irpf_espana, modo_neto)
factor_neto = 1.0 - fiscal["efectivo"] / 100.0

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

# Posición por tramos en la barra (Media = 50% exacto)
if precio_actual <= precio_medio:
    denom = precio_medio - precio_infra
    pos_pct = 50.0 * (precio_actual - precio_infra) / denom if denom > 0 else 0.0
else:
    denom = precio_sobre - precio_medio
    pos_pct = 50.0 + 50.0 * (precio_actual - precio_medio) / denom if denom > 0 else 100.0

pos_clamped = min(max(pos_pct, 0.0), 100.0)

if precio_actual <= precio_infra:
    estado_txt = "Infravalorada · Zona de Compra"
    franja_corta = "INFRAVALORADA"
    color_actual = "#00E676"
    bg_pill = "rgba(0, 230, 118, 0.12)"
    bd_pill = "rgba(0, 230, 118, 0.45)"
elif precio_actual <= precio_medio:
    estado_txt = "Franja Atractiva · Bajo la Media"
    franja_corta = "BAJO LA MEDIA"
    color_actual = "#26C6DA"
    bg_pill = "rgba(38, 198, 218, 0.12)"
    bd_pill = "rgba(38, 198, 218, 0.45)"
elif precio_actual < precio_sobre:
    estado_txt = "Franja Cara · Sobre la Media"
    franja_corta = "SOBRE LA MEDIA"
    color_actual = "#FFAB00"
    bg_pill = "rgba(255, 171, 0, 0.12)"
    bd_pill = "rgba(255, 171, 0, 0.45)"
else:
    estado_txt = "Sobrevalorada · Zona de Precaución"
    franja_corta = "SOBREVALORADA"
    color_actual = "#FF5252"
    bg_pill = "rgba(255, 82, 82, 0.12)"
    bd_pill = "rgba(255, 82, 82, 0.45)"

# Cálculo de YoC
precio_inicio = float(df["Close"].iloc[0])
fecha_inicio_str = df.index[0].strftime("%d/%m/%Y")

if modo_yoc.startswith("YoC histórico"):
    df["YoC"] = (div_actual / df["Close"]) * 100.0
    yoc_inicio_hoy = (div_actual / precio_inicio) * 100.0
    yoc_medio_periodo = float(df["YoC"].mean())
    subtitulo_yoc = (
        f"Si compraste hace {years} años ({precio_inicio:.2f} {moneda} el {fecha_inicio_str}), "
        f"tu YoC hoy es **{yoc_inicio_hoy:.2f}%** · YoC medio del periodo: **{yoc_medio_periodo:.2f}%**."
    )
    yoc_shape = "linear"
else:
    base_yoc = precio_compra_yoc if precio_compra_yoc > 0 else precio_inicio
    df["YoC"] = (df["Div_Anual"] / base_yoc) * 100.0
    yoc_actual_esc = (div_actual / base_yoc) * 100.0
    origen_txt = (
        f"tu compra ({base_yoc:.2f} {moneda})"
        if precio_compra_yoc > 0
        else f"inicio periodo ({base_yoc:.2f} {moneda} el {fecha_inicio_str})"
    )
    subtitulo_yoc = f"YoC actual: **{yoc_actual_esc:.2f}%** · Base: {origen_txt}."
    yoc_shape = "hv" if metodo_efectivo in ("weiss", "manual_anual") else "linear"

anio_actual_cal = datetime.today().year
anios_completos = div_anual_norm[div_anual_norm.index < anio_actual_cal]
anios_completos = anios_completos[anios_completos > 0]

# ==============================================================================
# CABECERA Y ALERTAS
# ==============================================================================
nombre_empresa = info.get("longName") or info.get("shortName") or ticker_input
if manual_hist_activo:
    texto_freq = "Histórico anual manual"
else:
    freq_actual_n = int(freqs_din.iloc[-1])
    freqs_previas = [int(f) for f in pd.unique(freqs_din.values) if int(f) != freq_actual_n]
    texto_freq = f"{freq_actual_n} pagos/año"
    if freqs_previas:
        texto_freq += f" (antes {', '.join(str(x) for x in freqs_previas)}/año)"

st.markdown(f"<div class='weiss-header-title'>{nombre_empresa} ({ticker_input})</div>", unsafe_allow_html=True)
st.markdown(
    f"<div class='weiss-header-meta'>"
    f"{sector} · {etiqueta_div}: <b>{div_actual:.3f} {moneda}</b> · {texto_freq} · Cierre: {fecha_ultimo}<br>"
    f"Origen ({pais_nombre}): <b>{ret_origen:g}%</b> (CDI {limite_cdi:g}%) · "
    f"IRPF: <b>{irpf_espana:g}%</b> → <b>{fiscal['efectivo']:.2f}%</b> ({fiscal['etiqueta_corta']})"
    f"</div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='status-pill' style='background:{bg_pill}; border-color:{bd_pill}; color:{color_actual};'>"
    f"<span>●</span><span>{estado_txt}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

if alertas_yahoo:
    detalle_alertas = "<br>".join(f"• {a}" for a in alertas_yahoo)
    st.markdown(
        f"<div class='data-warning'>"
        f"🚨 <b>Posible histórico incompleto en Yahoo Finance ({ticker_input}):</b><br>"
        f"{detalle_alertas}<br>"
        f"<i>Solución: abre ⚙️ Ajustes → activa «Sustituir el histórico de dividendos de Yahoo» y pega los dividendos anuales reales.</i>"
        f"</div>",
        unsafe_allow_html=True,
    )

if fiscal["exceso_no_deducible"] > 0.01:
    st.markdown(
        f"<div class='tax-warning'>"
        f"⚠️ <b>Doble retención en origen ({pais_nombre}):</b> se retiene un <b>{ret_origen:g}%</b> en origen y "
        f"solo es deducible un <b>{fiscal['deducible_cdi']:g}%</b> en la Renta "
        f"(exceso no recuperado: <b>{fiscal['exceso_no_deducible']:g}%</b>). "
        f"Carga final tras Renta: <b>{fiscal['carga_renta']:.2f}%</b> "
        f"(en cobro en cascada: <b>{fiscal['carga_cascada']:.2f}%</b>)."
        f"</div>",
        unsafe_allow_html=True,
    )

# ==============================================================================
# PESTAÑAS PRINCIPALES
# ==============================================================================
tab_weiss, tab_chowder, tab_tablas = st.tabs(["📈 Valoración Weiss", "🧮 Regla de Chowder", "📋 Tablas y CSV"])

# ------------------------------------------------------------------------------
# TAB 1: VALORACIÓN GERALDINE WEISS
# ------------------------------------------------------------------------------
with tab_weiss:
    color_pot_media = "#00E676" if dist_medio >= 0 else "#FF5252"
    color_dist_infra = "#00E676" if dist_infra >= 0 else "#9CA3AF"

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card" style="--accent:{color_actual}; --val-color:{color_actual}; --sub-color:{color_actual};">
                <div class="kpi-label">Precio Actual ({franja_corta})</div>
                <div class="kpi-value">{precio_actual:.2f} {moneda}</div>
                <div class="kpi-mid">Bruto: {yield_actual:.2f}% · Neto: {yield_actual_neto:.2f}%</div>
                <div class="kpi-sub">Efectivo ({fiscal['etiqueta_corta']}): {fiscal['efectivo']:.2f}%</div>
            </div>
            <div class="kpi-card" style="--accent:#00E676; --val-color:#00E676; --sub-color:{color_dist_infra};">
                <div class="kpi-label">Infravaloración</div>
                <div class="kpi-value">{precio_infra:.2f} {moneda}</div>
                <div class="kpi-mid">Bruto: {yield_infra:.2f}% · Neto: {yield_infra_neto:.2f}%</div>
                <div class="kpi-sub">{dist_infra:+.1f}% vs actual</div>
            </div>
            <div class="kpi-card" style="--accent:#FFAB00; --val-color:#FFAB00; --sub-color:{color_pot_media};">
                <div class="kpi-label">Valoración Media</div>
                <div class="kpi-value">{precio_medio:.2f} {moneda}</div>
                <div class="kpi-mid">Bruto: {yield_medio:.2f}% · Neto: {yield_medio_neto:.2f}%</div>
                <div class="kpi-sub">{dist_medio:+.1f}% potencial</div>
            </div>
            <div class="kpi-card" style="--accent:#FF5252; --val-color:#FF5252; --sub-color:#9CA3AF;">
                <div class="kpi-label">Sobrevaloración</div>
                <div class="kpi-value">{precio_sobre:.2f} {moneda}</div>
                <div class="kpi-mid">Bruto: {yield_sobre:.2f}% · Neto: {yield_sobre_neto:.2f}%</div>
                <div class="kpi-sub">{dist_sobre:+.1f}% vs actual</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="channel-box">
            <div class="channel-top">
                <span><b>Posición en el canal de Weiss</b> <span style="color:#9CA3AF;">({etiqueta_extremo} · Media = 50%)</span></span>
                <span style="font-weight:700; color:{color_actual};">{pos_pct:.1f}%</span>
            </div>
            <div class="channel-track">
                <div class="channel-mid-tick"></div>
                <div class="channel-dot" style="left:{pos_clamped:.2f}%; --dot-color:{color_actual};"></div>
            </div>
            <div class="channel-labels">
                <span style="color:#00E676;">Infravalorada ({precio_infra:.2f})</span>
                <span style="color:#FFAB00;">Media ({precio_medio:.2f})</span>
                <span style="color:#FF5252;">Sobrevalorada ({precio_sobre:.2f})</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if manual_hist_activo:
        metodo_label = "Tabla manual de dividendos anuales"
    elif metodo_efectivo == "weiss":
        metodo_label = "Escalón clásico Weiss (Dividendo indicado)"
    else:
        metodo_label = f"TTM móvil (últimos {int(freqs_din.iloc[-1])} pagos)"

    st.markdown(f"### Franjas de Geraldine Weiss ({years} años)")
    st.caption(f"Método activo: {metodo_label} · Precio de cierre sin ajustar por dividendos.")

    fig_precio = go.Figure()

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Infra"],
        mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#00C853", width=1.8, shape="hv"),
        hovertemplate="Infra: %{y:.2f}<extra></extra>",
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Media"],
        mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#FFAB00", width=1.6, dash="dash", shape="hv"),
        fill="tonexty",
        fillcolor="rgba(0, 200, 83, 0.14)",
        hovertemplate="Media: %{y:.2f}<extra></extra>",
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Banda_Sobre"],
        mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#FF1744", width=1.8, shape="hv"),
        fill="tonexty",
        fillcolor="rgba(255, 23, 68, 0.14)",
        hovertemplate="Sobre: %{y:.2f}<extra></extra>",
    ))

    fig_precio.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        name="Precio (sin ajustar)",
        line=dict(color="#29B6F6", width=2.2),
        hovertemplate="Precio: %{y:.2f}<extra></extra>",
    ))

    fig_precio.update_layout(
        yaxis_title=f"Precio ({moneda})",
        yaxis_type="log" if escala_log else "linear",
        hovermode="x unified",
        height=440,
        margin=dict(l=52, r=14, t=12, b=76),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", zeroline=False),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.14,
            xanchor="center",
            x=0.5,
            font=dict(size=11),
        ),
    )

    st.plotly_chart(fig_precio, use_container_width=True, config={"displayModeBar": False})

    # --- GRÁFICO 2: DIVIDEND YIELD Y YoC ---
    st.markdown("### Histórico de Dividend Yield y YoC (%)")
    st.caption(subtitulo_yoc)

    fig_yield = go.Figure()

    fig_yield.add_trace(go.Scatter(
        x=df.index,
        y=df["Yield"],
        mode="lines",
        name=f"Dividend Yield ({yield_actual:.2f}%)",
        line=dict(color="#29B6F6", width=2.0),
        fill="tozeroy",
        fillcolor="rgba(41, 182, 246, 0.08)",
        hovertemplate="Yield: %{y:.2f}%<extra></extra>",
    ))

    yoc_label_val = float(df["YoC"].iloc[0]) if modo_yoc.startswith("YoC histórico") else float(df["YoC"].iloc[-1])
    fig_yield.add_trace(go.Scatter(
        x=df.index,
        y=df["YoC"],
        mode="lines",
        name=f"YoC ({yoc_label_val:.2f}%)",
        line=dict(color="#AB47BC", width=2.0, shape=yoc_shape),
        hovertemplate="YoC: %{y:.2f}%<extra></extra>",
    ))

    fig_yield.add_trace(go.Scatter(
        x=[df.index[0], df.index[-1]],
        y=[yield_infra, yield_infra],
        mode="lines",
        name=f"Infravaloración ({yield_infra:.2f}%)",
        line=dict(color="#00C853", width=1.4, dash="dot"),
        hoverinfo="skip",
    ))
    fig_yield.add_trace(go.Scatter(
        x=[df.index[0], df.index[-1]],
        y=[yield_medio, yield_medio],
        mode="lines",
        name=f"Media ({yield_medio:.2f}%)",
        line=dict(color="#FFAB00", width=1.4, dash="dash"),
        hoverinfo="skip",
    ))
    fig_yield.add_trace(go.Scatter(
        x=[df.index[0], df.index[-1]],
        y=[yield_sobre, yield_sobre],
        mode="lines",
        name=f"Sobrevaloración ({yield_sobre:.2f}%)",
        line=dict(color="#FF1744", width=1.4, dash="dot"),
        hoverinfo="skip",
    ))

    if precio_compra_yoc > 0:
        mi_yoc = (div_actual / precio_compra_yoc) * 100.0
        fig_yield.add_trace(go.Scatter(
            x=[df.index[0], df.index[-1]],
            y=[mi_yoc, mi_yoc],
            mode="lines",
            name=f"Mi YoC ({mi_yoc:.2f}%)",
            line=dict(color="#F50057", width=1.8, dash="dashdot"),
            hoverinfo="skip",
        ))

    fig_yield.update_layout(
        yaxis_title="Yield / YoC (%)",
        hovermode="x unified",
        height=390,
        margin=dict(l=52, r=14, t=12, b=84),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", zeroline=False),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="center",
            x=0.5,
            font=dict(size=11),
        ),
    )

    st.plotly_chart(fig_yield, use_container_width=True, config={"displayModeBar": False})


# ------------------------------------------------------------------------------
# TAB 2: REGLA DE CHOWDER Y GRÁFICO HORIZONTAL DE DIVIDENDOS
# ------------------------------------------------------------------------------
with tab_chowder:
    dgr_1, y1_ini, y1_fin = calcular_cagr(anios_completos, 1)
    dgr_3, y3_ini, y3_fin = calcular_cagr(anios_completos, 3)
    dgr_5, y5_ini, y5_fin = calcular_cagr(anios_completos, 5)
    dgr_10, y10_ini, y10_fin = calcular_cagr(anios_completos, 10)

    if forzar_chowder_def:
        umbral_chowder = 8.0
        motivo_umbral = "Defensiva / Utility / REIT"
    elif yield_actual < 3.0:
        umbral_chowder = 15.0
        motivo_umbral = "Yield < 3%"
    else:
        umbral_chowder = 12.0
        motivo_umbral = "Yield ≥ 3%"

    if dgr_5 is not None:
        chowder_num = yield_actual + dgr_5
        margen_chowder = chowder_num - umbral_chowder
        cumple_chowder = chowder_num >= umbral_chowder
        color_chowder = "#00E676" if cumple_chowder else "#FF5252"
        bg_ch = "rgba(0, 230, 118, 0.12)" if cumple_chowder else "rgba(255, 82, 82, 0.12)"
        bd_ch = "rgba(0, 230, 118, 0.45)" if cumple_chowder else "rgba(255, 82, 82, 0.45)"
        pill_ch = (
            f"✅ Cumple Regla de Chowder · {chowder_num:.2f}% (margen {margen_chowder:+.2f} pp)"
            if cumple_chowder
            else f"❌ No cumple Regla de Chowder · {chowder_num:.2f}% ({margen_chowder:+.2f} pp vs objetivo)"
        )
        st.markdown(
            f"<div class='status-pill' style='background:{bg_ch}; border-color:{bd_ch}; color:{color_chowder};'>"
            f"{pill_ch}</div>",
            unsafe_allow_html=True,
        )
        color_dgr5 = "#00E676" if dgr_5 >= 7.0 else ("#FFAB00" if dgr_5 >= 3.0 else "#FF5252")

        st.markdown(
            f"""
            <div class="kpi-grid">
                <div class="kpi-card" style="--accent:{color_chowder}; --val-color:{color_chowder}; --sub-color:{color_chowder};">
                    <div class="kpi-label">Número de Chowder</div>
                    <div class="kpi-value">{chowder_num:.2f}%</div>
                    <div class="kpi-sub">{margen_chowder:+.2f} pp vs objetivo</div>
                </div>
                <div class="kpi-card" style="--accent:{color_actual}; --val-color:{color_actual}; --sub-color:{color_actual};">
                    <div class="kpi-label">Dividend Yield Actual</div>
                    <div class="kpi-value">{yield_actual:.2f}%</div>
                    <div class="kpi-mid">Neto: {yield_actual_neto:.2f}% ({fiscal['efectivo']:.0f}% ef.)</div>
                    <div class="kpi-sub">Franja: {franja_corta.title()}</div>
                </div>
                <div class="kpi-card" style="--accent:{color_dgr5}; --val-color:{color_dgr5}; --sub-color:#9CA3AF;">
                    <div class="kpi-label">DGR 5Y ({y5_ini}–{y5_fin})</div>
                    <div class="kpi-value">{dgr_5:+.2f}%</div>
                    <div class="kpi-sub">Componente crecimiento</div>
                </div>
                <div class="kpi-card" style="--accent:#29B6F6; --val-color:#29B6F6; --sub-color:#9CA3AF;">
                    <div class="kpi-label">Umbral Aplicable</div>
                    <div class="kpi-value">≥ {umbral_chowder:.0f}%</div>
                    <div class="kpi-sub">{motivo_umbral}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("No hay al menos 5 años completos de dividendos para calcular la Regla de Chowder.")

    anios_norm_visibles = [y for y in anios_norm if y in anios_completos.index]
    if anios_norm_visibles:
        lista_str = ", ".join(str(y) for y in anios_norm_visibles)
        st.markdown(
            f"<div class='info-note'>"
            f"ℹ️ Se han normalizado los dividendos de <b>{lista_str}</b> usando la tasa anual indicada "
            f"(por cambio de calendario, pagos omitidos en Yahoo o desplazamiento de fecha ex-dividendo)."
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Ritmo histórico de crecimiento del dividendo (DGR)")

    def _dgr_card(titulo, valor, yi, yf_):
        if valor is None:
            return (
                f"<div class='kpi-card' style='--accent:#4B5563; --val-color:#6B7280;'>"
                f"<div class='kpi-label'>{titulo}</div>"
                f"<div class='kpi-value'>N/D</div>"
                f"<div class='kpi-sub'>Historial insuficiente</div></div>"
            )
        col = "#00E676" if valor >= 7.0 else ("#FFAB00" if valor >= 2.0 else "#FF5252")
        return (
            f"<div class='kpi-card' style='--accent:{col}; --val-color:{col}; --sub-color:#9CA3AF;'>"
            f"<div class='kpi-label'>{titulo}</div>"
            f"<div class='kpi-value'>{valor:+.2f}%</div>"
            f"<div class='kpi-sub'>{yi}–{yf_}</div></div>"
        )

    st.markdown(
        "<div class='kpi-grid'>"
        + _dgr_card("DGR 1 Año", dgr_1, y1_ini, y1_fin)
        + _dgr_card("DGR 3 Años", dgr_3, y3_ini, y3_fin)
        + _dgr_card("DGR 5 Años", dgr_5, y5_ini, y5_fin)
        + _dgr_card("DGR 10 Años", dgr_10, y10_ini, y10_fin)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Evolución del dividendo anual (años completos)")

    if not anios_completos.empty:
        yoy_completo = anios_completos.pct_change() * 100.0
        serie_plot = anios_completos.tail(years)
        yoy_plot = yoy_completo.reindex(serie_plot.index)

        etiquetas_y = []
        textos_barra = []
        colores_barra = []
        hover_textos = []

        for yr, val in serie_plot.items():
            es_norm = yr in anios_norm
            y_label = f"{yr}*" if es_norm else str(yr)
            etiquetas_y.append(y_label)

            yoy_v = yoy_plot.loc[yr]
            if pd.isna(yoy_v):
                txt = f"  {val:.2f}"
                col = "#29B6F6"
                h_yoy = "Inicio de serie"
            else:
                txt = f"  {val:.2f}  ({yoy_v:+.1f}%)"
                h_yoy = f"{yoy_v:+.2f}% YoY"
                if yoy_v > 0.05:
                    col = "#00C853"
                elif yoy_v < -0.05:
                    col = "#FF5252"
                else:
                    col = "#FFAB00"

            textos_barra.append(txt)
            colores_barra.append(col)
            nota_norm = " (normalizado)" if es_norm else ""
            hover_textos.append(f"<b>{yr}{nota_norm}</b><br>Dividendo: {val:.4f} {moneda}<br>Cambio: {h_yoy}")

        max_div = float(serie_plot.max())
        alto_grafico = max(320, len(serie_plot) * 34 + 65)

        fig_div = go.Figure()
        fig_div.add_trace(go.Bar(
            x=serie_plot.values,
            y=etiquetas_y,
            orientation="h",
            marker=dict(color=colores_barra, line=dict(width=0)),
            text=textos_barra,
            textposition="outside",
            textfont=dict(size=12, color="#F3F4F6"),
            cliponaxis=False,
            hovertext=hover_textos,
            hoverinfo="text",
        ))

        fig_div.update_layout(
            xaxis_title=f"Dividendo anual ({moneda})",
            height=alto_grafico,
            margin=dict(l=48, r=16, t=10, b=42),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                range=[0, max_div * 1.65],
                gridcolor="rgba(255,255,255,0.08)",
                zeroline=False,
            ),
            yaxis=dict(
                type="category",
                showgrid=False,
                tickfont=dict(size=12),
            ),
            bargap=0.28,
            showlegend=False,
        )

        st.plotly_chart(fig_div, use_container_width=True, config={"displayModeBar": False})
        st.caption("Verde: subida · Ámbar: congelado · Rojo: recorte · `*` año normalizado por calendario/Yahoo.")


# ------------------------------------------------------------------------------
# TAB 3: TABLAS RESUMEN, DESGLOSE FISCAL, PAGOS CRUDOS Y CSV
# ------------------------------------------------------------------------------
with tab_tablas:
    st.markdown("### 📋 Resumen de Bandas Actuales")
    st.markdown(
        f"""
        <table class="styled-table">
            <thead>
                <tr>
                    <th>Zona de Valoración</th>
                    <th>Yield Bruto</th>
                    <th>Yield Neto</th>
                    <th>Precio ({moneda})</th>
                    <th>vs Actual</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="color:#00E676; font-weight:600;">🟢 Infravaloración</td>
                    <td style="color:#00E676;">{yield_infra:.2f}%</td>
                    <td style="color:#00E676;">{yield_infra_neto:.2f}%</td>
                    <td style="color:#00E676; font-weight:700;">{precio_infra:.2f}</td>
                    <td>{dist_infra:+.2f}%</td>
                </tr>
                <tr>
                    <td style="color:#FFAB00; font-weight:600;">🟡 Valoración Media</td>
                    <td style="color:#FFAB00;">{yield_medio:.2f}%</td>
                    <td style="color:#FFAB00;">{yield_medio_neto:.2f}%</td>
                    <td style="color:#FFAB00; font-weight:700;">{precio_medio:.2f}</td>
                    <td>{dist_medio:+.2f}%</td>
                </tr>
                <tr>
                    <td style="color:#FF5252; font-weight:600;">🔴 Sobrevaloración</td>
                    <td style="color:#FF5252;">{yield_sobre:.2f}%</td>
                    <td style="color:#FF5252;">{yield_sobre_neto:.2f}%</td>
                    <td style="color:#FF5252; font-weight:700;">{precio_sobre:.2f}</td>
                    <td>{dist_sobre:+.2f}%</td>
                </tr>
                <tr>
                    <td style="color:{color_actual}; font-weight:700;">● Cotización Actual</td>
                    <td style="color:{color_actual}; font-weight:700;">{yield_actual:.2f}%</td>
                    <td style="color:{color_actual}; font-weight:700;">{yield_actual_neto:.2f}%</td>
                    <td style="color:{color_actual}; font-weight:700;">{precio_actual:.2f}</td>
                    <td>0.00%</td>
                </tr>
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🧾 Desglose Fiscal Aplicado")
    st.markdown(
        f"""
        <table class="styled-table">
            <thead>
                <tr>
                    <th>Concepto</th>
                    <th>Valor</th>
                </tr>
            </thead>
            <tbody>
                <tr><td>País fiscal detectado</td><td><b>{pais_nombre}</b></td></tr>
                <tr><td>Retención en origen</td><td>{ret_origen:.3g}%</td></tr>
                <tr><td>Máximo deducible en Renta (CDI España)</td><td>{limite_cdi:.3g}%</td></tr>
                <tr><td>Exceso en origen no deducible en Renta</td><td><b>{fiscal['exceso_no_deducible']:.3g}%</b></td></tr>
                <tr><td>IRPF base del ahorro (España)</td><td>{irpf_espana:.3g}%</td></tr>
                <tr><td>Carga efectiva final tras Renta (Casilla 0588)</td><td><b>{fiscal['carga_renta']:.2f}%</b></td></tr>
                <tr><td>Carga efectiva en cobro en cascada</td><td>{fiscal['carga_cascada']:.2f}%</td></tr>
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 📅 Historial de Dividendos Anuales")
    yoy_tabla = div_anual_norm.pct_change() * 100.0
    filas_div = []
    for yr in sorted(div_anual_norm.index, reverse=True):
        etiq_yr = f"{yr} (YTD)" if yr == anio_actual_cal else (f"{yr}*" if yr in anios_norm else str(yr))
        v_bruto = float(div_anual_bruto.loc[yr])
        v_norm = float(div_anual_norm.loc[yr])
        v_yoy = yoy_tabla.loc[yr]
        filas_div.append({
            "Año": etiq_yr,
            f"Bruto ({moneda})": f"{v_bruto:.4f}",
            f"Usado cálculo ({moneda})": f"{v_norm:.4f}",
            "Cambio YoY": "—" if (pd.isna(v_yoy) or yr == anio_actual_cal) else f"{v_yoy:+.2f}%",
        })
    st.dataframe(pd.DataFrame(filas_div), use_container_width=True, hide_index=True)

    with st.expander("🔍 Ver pagos crudos recibidos de Yahoo Finance (auditoría)", expanded=False):
        if not eventos_brutos.empty:
            df_crudos = pd.DataFrame({
                "Fecha ex-div": eventos_brutos.index.strftime("%d/%m/%Y"),
                f"Importe ({moneda})": [f"{v:.4f}" for v in eventos_brutos.values],
            }).iloc[::-1]
            st.dataframe(df_crudos, use_container_width=True, hide_index=True)
        else:
            st.info("Yahoo Finance no devolvió eventos de dividendo para este ticker.")

    st.markdown("### 📥 Exportar datos")
    cols_export = ["Close", "Dividends", "Div_Anual", "Yield", "YoC", "Banda_Infra", "Banda_Media", "Banda_Sobre"]
    csv_export = df[cols_export].to_csv()
    st.download_button(
        label=f"Descargar CSV completo ({ticker_input} · {years} años)",
        data=csv_export,
        file_name=f"weiss_{ticker_input}_{years}y.csv",
        mime="text/csv",
        use_container_width=True,
    )
