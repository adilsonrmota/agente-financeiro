import glob
import os
import re
from datetime import date

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Agente Financeiro", layout="wide")


MONTH_NAMES = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

        :root {
            --bg-soft: #f4f7fb;
            --card: #ffffff;
            --ink: #12223a;
            --muted: #5e6f8a;
            --brand: #0f766e;
            --brand-2: #1d4ed8;
            --line: #e4ebf5;
        }

        html, body, [class*="css"] {
            font-family: 'Manrope', sans-serif;
            color: var(--ink);
        }

        .stApp {
            background:
                radial-gradient(circle at 10% 0%, #dbeafe 0%, rgba(219, 234, 254, 0) 35%),
                radial-gradient(circle at 100% 20%, #ccfbf1 0%, rgba(204, 251, 241, 0) 35%),
                var(--bg-soft);
        }

        .top-hero {
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 22px 24px;
            background: linear-gradient(110deg, #ffffff 0%, #eef5ff 100%);
            box-shadow: 0 10px 24px rgba(18, 34, 58, 0.08);
            margin-bottom: 12px;
        }

        .top-hero h1 {
            margin: 0;
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .top-hero p {
            margin: 6px 0 0;
            color: var(--muted);
            font-size: 14px;
        }

        .kpi-card {
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 16px;
            background: var(--card);
            box-shadow: 0 6px 18px rgba(18, 34, 58, 0.05);
            min-height: 115px;
        }

        .kpi-label {
            color: var(--muted);
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .kpi-value {
            color: var(--ink);
            font-size: 30px;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.1;
        }

        .kpi-sub {
            color: var(--brand-2);
            font-size: 12px;
            font-weight: 700;
            margin-top: 8px;
        }

        .section-title {
            font-size: 18px;
            font-weight: 800;
            margin: 6px 0 10px;
            color: var(--ink);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _kpi_card(label: str, value: str, sub: str) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _parse_period_from_name(path: str) -> tuple[int, int] | None:
    name = os.path.basename(path)
    match = re.match(r"relatorio_(\d{4})_(\d{2})\.csv$", name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _load_history_dataframe() -> pd.DataFrame:
    report_paths = sorted(glob.glob(os.path.join("reports", "relatorio_*.csv")))
    frames: list[pd.DataFrame] = []

    for path in report_paths:
        period = _parse_period_from_name(path)
        if not period:
            continue
        year, month = period

        frame = pd.read_csv(path)
        frame["ano"] = year
        frame["mes"] = month
        frame["origem_relatorio"] = os.path.basename(path)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


df = _load_history_dataframe()
if df.empty:
    st.warning("Nenhum relatorio CSV encontrado em reports/.")
    st.stop()

_inject_theme()

required_cols = ["empresa", "valor", "vencimento", "status"]
missing_cols = [c for c in required_cols if c not in df.columns]
if missing_cols:
    st.error(f"Colunas ausentes no relatorio: {', '.join(missing_cols)}")
    st.stop()

df["vencimento_data"] = pd.to_datetime(df["vencimento"], format="%d/%m/%Y", errors="coerce")

values = (
    df["valor"]
    .astype(str)
    .str.replace(r"[^0-9,.-]", "", regex=True)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
df["valor_num"] = pd.to_numeric(values, errors="coerce").fillna(0.0)

available_years = sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
default_year = date.today().year if date.today().year in available_years else available_years[0]

st.sidebar.header("Filtros")
selected_year = st.sidebar.selectbox("Ano", options=available_years, index=available_years.index(default_year))

months_in_year = sorted(df.loc[df["ano"] == selected_year, "mes"].dropna().astype(int).unique().tolist())
month_options = [0] + months_in_year
month_labels = {0: "Todos"}
month_labels.update({month: f"{month:02d}" for month in months_in_year})

selected_month = st.sidebar.selectbox(
    "Mês",
    options=month_options,
    index=0,
    format_func=lambda value: month_labels[value] if value == 0 else f"{value:02d} - {MONTH_NAMES.get(value, '')}",
)

filtered = df[df["ano"] == selected_year].copy()
if selected_month != 0:
    filtered = filtered[filtered["mes"] == selected_month].copy()

if filtered.empty:
    st.info("Nenhum registro encontrado para o período selecionado.")
    st.stop()

title_period = f"{selected_year}" if selected_month == 0 else f"{selected_year}-{selected_month:02d}"
st.markdown(
    f"""
    <div class="top-hero">
        <h1>Painel Financeiro</h1>
        <p>Visao consolidada das contas extraidas do Gmail. Periodo ativo: <strong>{title_period}</strong>.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

total_value = filtered["valor_num"].sum()
total_items = len(filtered)
valid_due = filtered["vencimento_data"].notna().sum()
avg_ticket = total_value / total_items if total_items else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    _kpi_card("Total a pagar", f"R$ {total_value:,.2f}", "Consolidado no periodo")
with k2:
    _kpi_card("Contas", f"{total_items}", "Itens encontrados")
with k3:
    _kpi_card("Com vencimento valido", f"{valid_due}", "Base para previsao")
with k4:
    _kpi_card("Ticket medio", f"R$ {avg_ticket:,.2f}", "Media por conta")

st.markdown('<div class="section-title">Analises do periodo</div>', unsafe_allow_html=True)

left, right = st.columns(2)

with left:
    by_company = (
        filtered.groupby("empresa", dropna=False, as_index=False)["valor_num"]
        .sum()
        .sort_values("valor_num", ascending=False)
        .head(8)
        .set_index("empresa")
    )
    st.caption("Top empresas por valor")
    st.bar_chart(by_company)

with right:
    monthly_series = (
        filtered.dropna(subset=["vencimento_data"])
        .assign(competencia=lambda x: x["vencimento_data"].dt.strftime("%Y-%m"))
        .groupby("competencia", as_index=True)["valor_num"]
        .sum()
        .sort_index()
    )
    st.caption("Tendencia por competencia")
    if monthly_series.empty:
        st.info("Sem vencimentos validos para tendencia.")
    else:
        st.line_chart(monthly_series)

st.markdown('<div class="section-title">Proximos vencimentos</div>', unsafe_allow_html=True)
next_due = filtered.dropna(subset=["vencimento_data"]).sort_values("vencimento_data", ascending=True).head(8)

if next_due.empty:
    st.info("Nenhum vencimento valido no periodo selecionado.")
else:
    st.dataframe(
        next_due[["empresa", "valor", "vencimento", "status", "origem email"]],
        width="stretch",
    )

st.markdown('<div class="section-title">Detalhamento de contas</div>', unsafe_allow_html=True)
display_columns = [
    "empresa",
    "valor",
    "vencimento",
    "status",
    "origem email",
    "arquivo pdf",
    "ano",
    "mes",
]
available_display_columns = [col for col in display_columns if col in filtered.columns]
st.dataframe(filtered[available_display_columns], width="stretch")
