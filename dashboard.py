import glob
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
from datetime import date
from datetime import datetime
from email.message import EmailMessage

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")
AUTH_FILE = os.path.join(STATE_DIR, "auth.json")

DEFAULT_USERNAME = "Atom_mota"
DEFAULT_PASSWORD = "@Xxxx1234"


def _get_secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    return os.getenv(name, default)


def _password_hash(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return digest.hex()


def _load_auth() -> dict:
    if not os.path.exists(AUTH_FILE):
        initial_username = _get_secret("DASHBOARD_USERNAME", DEFAULT_USERNAME)
        initial_password = _get_secret("DASHBOARD_PASSWORD", DEFAULT_PASSWORD)
        salt_hex = secrets.token_hex(16)
        auth = {
            "username": initial_username,
            "password_hash": _password_hash(initial_password, salt_hex),
            "salt": salt_hex,
            "password_temporary": True,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        _save_auth(auth)
        return auth

    with open(AUTH_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_auth(auth: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(AUTH_FILE, "w", encoding="utf-8") as file:
        json.dump(auth, file, ensure_ascii=False, indent=2)


def _verify_credentials(username: str, password: str) -> bool:
    auth = _load_auth()
    if username != auth.get("username", ""):
        return False

    expected_hash = auth.get("password_hash", "")
    provided_hash = _password_hash(password, auth.get("salt", ""))
    return hmac.compare_digest(expected_hash, provided_hash)


def _change_password(current_password: str, new_password: str) -> tuple[bool, str]:
    auth = _load_auth()
    if not _verify_credentials(auth.get("username", ""), current_password):
        return False, "Senha atual incorreta."

    if len(new_password) < 8:
        return False, "A nova senha precisa ter ao menos 8 caracteres."

    new_salt = secrets.token_hex(16)
    auth["password_hash"] = _password_hash(new_password, new_salt)
    auth["salt"] = new_salt
    auth["password_temporary"] = False
    auth["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_auth(auth)

    return True, "Senha alterada com sucesso."


def _send_password_change_email() -> tuple[bool, str]:
    smtp_host = _get_secret("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(_get_secret("SMTP_PORT", "587"))
    smtp_user = _get_secret("SMTP_USER", "")
    smtp_pass = _get_secret("SMTP_PASS", "")
    recipient = _get_secret("ALERT_EMAIL_TO", smtp_user)

    if not smtp_user or not smtp_pass or not recipient:
        return False, "Email de confirmacao nao enviado. Configure SMTP_USER, SMTP_PASS e ALERT_EMAIL_TO no .env."

    msg = EmailMessage()
    msg["Subject"] = "Confirmacao de troca de senha - Painel Financeiro"
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.set_content(
        "A senha do Painel Financeiro foi alterada com sucesso em "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}."
    )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as exc:
        return False, f"Falha ao enviar email de confirmacao: {exc}"

    return True, f"Email de confirmacao enviado para {recipient}."


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

        .login-wrap {
            max-width: 520px;
            margin: 2rem auto 0;
            border: 1px solid var(--line);
            border-radius: 18px;
            background: #ffffff;
            padding: 18px;
            box-shadow: 0 10px 24px rgba(18, 34, 58, 0.08);
        }

        .login-wrap h2 {
            margin: 0 0 8px;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .login-wrap p {
            margin: 0 0 14px;
            color: var(--muted);
            font-size: 14px;
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


def _calendar_button(url: str = "https://calendar.google.com/calendar/u/0/r") -> None:
    st.markdown(
        f"""
        <div style="display:flex; justify-content:flex-end; margin: 6px 0 12px;">
            <a href="{url}" target="_blank" rel="noopener noreferrer"
               style="text-decoration:none; background:#1d4ed8; color:#ffffff; padding:10px 14px;
                      border-radius:10px; font-weight:700; font-size:13px; box-shadow:0 6px 14px rgba(29,78,216,0.25);">
                Abrir Google Calendar
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_login() -> None:
    st.markdown(
        """
        <div class="login-wrap">
            <h2>Acesso restrito</h2>
            <p>Entre com seu usuario e senha para acessar o painel.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, form_col, _ = st.columns([3, 2, 3])
    with form_col:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", type="primary")

    if submit:
        if _verify_credentials(username, password):
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")


def _require_login() -> None:
    _load_auth()

    if not st.session_state.get("authenticated", False):
        _render_login()
        st.stop()

    auth = _load_auth()
    st.sidebar.success(f"Logado como: {auth.get('username', DEFAULT_USERNAME)}")
    if st.sidebar.button("Sair"):
        st.session_state["authenticated"] = False
        st.session_state["username"] = ""
        st.rerun()

    with st.sidebar.expander("Trocar senha", expanded=False):
        with st.form("change_password_form", clear_on_submit=True):
            current_password = st.text_input("Senha atual", type="password")
            new_password = st.text_input("Nova senha", type="password")
            confirm_password = st.text_input("Confirmar nova senha", type="password")
            change_submit = st.form_submit_button("Atualizar senha")

        if change_submit:
            if not new_password:
                st.error("Informe a nova senha.")
            elif new_password != confirm_password:
                st.error("A confirmacao nao confere.")
            else:
                changed, message = _change_password(current_password, new_password)
                if changed:
                    st.success(message)
                    sent, mail_message = _send_password_change_email()
                    if sent:
                        st.success(mail_message)
                    else:
                        st.warning(mail_message)
                else:
                    st.error(message)

    if auth.get("password_temporary", False):
        st.warning("Voce esta usando a senha provisoria. Recomendado trocar agora no menu lateral.")


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


_inject_theme()
_require_login()

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
_calendar_button()

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
