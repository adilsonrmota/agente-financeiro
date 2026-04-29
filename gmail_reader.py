import os
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

FINANCIAL_KEYWORDS = [
    "claro",
    "cpfl",
    "edp",
    "boleto",
    "fatura",
    "vencimento",
    "conta",
    "energia",
    "internet",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def _get_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _parse_headers(headers: list) -> dict:
    keys = {"Subject", "From", "Date"}
    return {h["name"]: h["value"] for h in headers if h["name"] in keys}


def _detect_company(sender: str, subject: str, snippet: str, matched_keywords: list[str]) -> str:
    sender_lower = sender.lower()
    content = f"{subject} {snippet}".lower()

    if "claro" in matched_keywords or "claro" in sender_lower or "claro" in content:
        return "Claro"
    if "cpfl" in matched_keywords or "cpfl" in sender_lower or "cpfl" in content:
        return "CPFL"
    if "edp" in matched_keywords or "edp" in sender_lower or "edp" in content:
        return "EDP"

    if sender:
        return sender.split("<", 1)[0].strip().strip('"') or sender

    return "Não identificada"


def get_inbox_emails(max_results: int = 20) -> list[dict]:
    """
    Retorna os últimos `max_results` e-mails da caixa de entrada.

    Cada item do retorno contém:
        - subject  (str): assunto do e-mail
        - sender   (str): remetente
        - date     (str): data/hora no formato ISO 8601
        - snippet  (str): prévia do corpo do e-mail
    """
    service = _get_service()

    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", [])
    emails = []

    for msg in messages:
        detail = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()

        headers = _parse_headers(detail.get("payload", {}).get("headers", []))

        raw_date = headers.get("Date", "")
        try:
            iso_date = parsedate_to_datetime(raw_date).isoformat()
        except Exception:
            iso_date = raw_date

        emails.append({
            "subject": headers.get("Subject", "(sem assunto)"),
            "sender":  headers.get("From", "(desconhecido)"),
            "date":    iso_date,
            "snippet": detail.get("snippet", ""),
        })

    return emails


def get_financial_emails(max_results: int = 100) -> list[dict]:
    """
    Retorna e-mails da caixa de entrada cujo assunto ou prévia
    contenha pelo menos uma das palavras em FINANCIAL_KEYWORDS.

    `max_results` define quantos e-mails buscar antes de filtrar.
    """
    service = _get_service()

    query = " OR ".join(FINANCIAL_KEYWORDS)

    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        q=query,
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", [])
    emails = []

    for msg in messages:
        detail = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()

        headers = _parse_headers(detail.get("payload", {}).get("headers", []))

        raw_date = headers.get("Date", "")
        try:
            iso_date = parsedate_to_datetime(raw_date).isoformat()
        except Exception:
            iso_date = raw_date

        subject = headers.get("Subject", "(sem assunto)")
        sender = headers.get("From", "(desconhecido)")
        snippet = detail.get("snippet", "")

        combined = (subject + " " + snippet).lower()
        matched = [kw for kw in FINANCIAL_KEYWORDS if kw in combined]
        if not matched:
            continue

        company = _detect_company(sender, subject, snippet, matched)

        emails.append({
            "id":       msg["id"],
            "company":  company,
            "subject":  subject,
            "sender":   sender,
            "date":     iso_date,
            "snippet":  snippet,
            "keywords": matched,
        })

    return emails


if __name__ == "__main__":
    print("Autenticando com Gmail API...")
    print("(Na primeira execução o navegador abrirá para autorização)\n")

    emails = get_inbox_emails(max_results=20)

    if not emails:
        print("Nenhum e-mail encontrado.")
    else:
        print(f"{len(emails)} e-mail(s) encontrado(s):\n")
        for i, email in enumerate(emails, start=1):
            print(f"[{i:02d}] {email['date']}")
            print(f"     De:      {email['sender']}")
            print(f"     Assunto: {email['subject']}")
            print()

    print("token.json criado com sucesso. Próximas execuções não precisam de navegador.")
