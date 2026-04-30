import glob
import os

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Negociacoes XP", layout="wide")
st.title("Negociacoes de Acoes")

files = sorted(glob.glob(os.path.join("reports", "negociacoes_*.csv")))
if not files:
    st.info("Nenhum relatorio de negociacoes encontrado ainda.")
    st.stop()

selected_file = st.selectbox("Arquivo", options=files, index=len(files) - 1)
df = pd.read_csv(selected_file)

if df.empty:
    st.info("Relatorio encontrado, mas sem registros.")
    st.stop()

required_columns = [
    "especificacao_titulo",
    "quantidade",
    "preco_ajuste",
    "valor_operacao_ajuste",
    "dc",
]
missing = [col for col in required_columns if col not in df.columns]
if missing:
    st.error(f"Colunas ausentes no relatorio: {', '.join(missing)}")
    st.stop()

numeric_value = (
    df["valor_operacao_ajuste"]
    .astype(str)
    .str.replace(r"[^0-9,.-]", "", regex=True)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
df["valor_num"] = pd.to_numeric(numeric_value, errors="coerce").fillna(0.0)

st.caption(f"Fonte: {os.path.basename(selected_file)}")

c1, c2, c3 = st.columns(3)
c1.metric("Operacoes", f"{len(df)}")
c2.metric("Total Debitos", f"R$ {df.loc[df['dc'] == 'D', 'valor_num'].sum():,.2f}")
c3.metric("Total Creditos", f"R$ {df.loc[df['dc'] == 'C', 'valor_num'].sum():,.2f}")

by_title = (
    df.groupby("especificacao_titulo", as_index=False)["valor_num"]
    .sum()
    .sort_values("valor_num", ascending=False)
    .head(12)
    .set_index("especificacao_titulo")
)
st.subheader("Top titulos por volume")
st.bar_chart(by_title)

st.subheader("Detalhamento")
st.dataframe(
    df[
        [
            "data",
            "especificacao_titulo",
            "quantidade",
            "preco_ajuste",
            "valor_operacao_ajuste",
            "dc",
            "origem email",
            "arquivo pdf",
        ]
    ],
    width="stretch",
)
