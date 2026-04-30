import glob
import os
import re
from datetime import date

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Agente Financeiro", layout="wide")
st.title("Painel Financeiro")


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

selected_year = st.sidebar.selectbox("Ano", options=available_years, index=available_years.index(default_year))

months_in_year = sorted(df.loc[df["ano"] == selected_year, "mes"].dropna().astype(int).unique().tolist())
month_options = [0] + months_in_year
month_labels = {0: "Todos"}
month_labels.update({month: f"{month:02d}" for month in months_in_year})

selected_month = st.sidebar.selectbox(
    "Mês",
    options=month_options,
    index=0,
    format_func=lambda value: month_labels[value],
)

filtered = df[df["ano"] == selected_year].copy()
if selected_month != 0:
    filtered = filtered[filtered["mes"] == selected_month].copy()

if filtered.empty:
    st.info("Nenhum registro encontrado para o período selecionado.")
    st.stop()

title_period = f"{selected_year}" if selected_month == 0 else f"{selected_year}-{selected_month:02d}"
st.caption(f"Periodo selecionado: {title_period}")

col1, col2 = st.columns(2)
col1.metric("Total a pagar", f"R$ {filtered['valor_num'].sum():,.2f}")
col2.metric("Contas no periodo", f"{len(filtered)}")

st.subheader("Contas")
st.dataframe(filtered.drop(columns=["valor_num", "vencimento_data"]), width="stretch")

st.subheader("Proximos vencimentos")
next_due = filtered.sort_values("vencimento_data", ascending=True).head(5)
st.write(next_due[["empresa", "valor", "vencimento", "status", "origem email"]])
