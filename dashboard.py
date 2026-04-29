import glob
import os

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Agente Financeiro", layout="wide")
st.title("Painel Financeiro")


def _latest_report_path() -> str | None:
    report_paths = glob.glob(os.path.join("reports", "relatorio_*.csv"))
    if not report_paths:
        return None
    return max(report_paths, key=os.path.getmtime)


report_path = _latest_report_path()

if report_path is None:
    st.warning("Nenhum relatorio CSV encontrado em reports/.")
    st.stop()

st.caption(f"Relatorio carregado: {os.path.basename(report_path)}")

df = pd.read_csv(report_path)

required_cols = ["empresa", "valor", "vencimento", "status"]
missing_cols = [c for c in required_cols if c not in df.columns]
if missing_cols:
    st.error(f"Colunas ausentes no relatorio: {', '.join(missing_cols)}")
    st.stop()

if df.empty:
    st.info("Relatorio encontrado, mas sem registros neste mes.")
    st.dataframe(df, use_container_width=True)
    st.stop()

st.subheader("Contas do mes")
st.dataframe(df, use_container_width=True)

values = (
    df["valor"]
    .astype(str)
    .str.replace(r"[^0-9,.-]", "", regex=True)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
df["valor_num"] = pd.to_numeric(values, errors="coerce").fillna(0.0)

st.metric("Total a pagar", f"R$ {df['valor_num'].sum():,.2f}")

st.subheader("Proximos vencimentos")
next_due = df.sort_values("vencimento").head(5)
st.write(next_due)
