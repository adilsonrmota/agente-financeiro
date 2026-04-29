import os
from datetime import date, datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_CALENDAR_FILE = os.path.join(BASE_DIR, "token_calendar.json")


def _get_service():
    creds = None

    if os.path.exists(TOKEN_CALENDAR_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_CALENDAR_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_CALENDAR_FILE, "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _find_existing_event(service, calendario: str, titulo: str, vencimento: date) -> dict | None:
    start = datetime.combine(vencimento, datetime.min.time()).isoformat() + "Z"
    end = datetime.combine(vencimento + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

    response = service.events().list(
        calendarId=calendario,
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    for event in response.get("items", []):
        if event.get("summary") == titulo:
            return event

    return None


def criar_evento_vencimento(
    empresa: str,
    valor: str,
    vencimento: date,
    calendario: str = "primary",
) -> dict:
    """
    Cria um evento de vencimento no Google Calendar.

    Parâmetros:
        empresa     : nome da empresa/fornecedor (ex: 'CPFL', 'Claro')
        valor       : valor do boleto/fatura (ex: 'R$ 189,90')
        vencimento  : data de vencimento (objeto date)
        calendario  : ID do calendário (padrão: 'primary')

    Retorno:
        dict com os campos do evento criado pelo Google Calendar,
        incluindo 'id', 'htmlLink' e 'summary'.
    """
    service = _get_service()

    titulo = f"{empresa} — {valor}"
    data_str = vencimento.isoformat()           # ex: 2026-05-10

    existing_event = _find_existing_event(service, calendario, titulo, vencimento)
    if existing_event:
        existing_event["already_exists"] = True
        return existing_event

    evento = {
        "summary": titulo,
        "description": f"Vencimento de boleto/fatura\nEmpresa: {empresa}\nValor: {valor}",
        "start": {"date": data_str},
        "end":   {"date": data_str},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 3 * 24 * 60},   # 3 dias antes
                {"method": "popup",  "minutes": 3 * 24 * 60},
                {"method": "email",  "minutes": 1 * 24 * 60},   # 1 dia antes
                {"method": "popup",  "minutes": 1 * 24 * 60},
            ],
        },
        "colorId": "11",  # vermelho tomate — destaque para vencimentos
    }

    resultado = service.events().insert(
        calendarId=calendario,
        body=evento,
    ).execute()

    return resultado


def criar_eventos_em_lote(
    faturas: list[dict],
    calendario: str = "primary",
) -> list[dict]:
    """
    Cria múltiplos eventos a partir de uma lista de faturas.

    Cada item de `faturas` deve conter:
        - empresa    (str)
        - valor      (str)
        - vencimento (date)

    Retorna lista com os eventos criados (ou erros individuais).
    """
    resultados = []

    for fatura in faturas:
        try:
            evento = criar_evento_vencimento(
                empresa=fatura["empresa"],
                valor=fatura["valor"],
                vencimento=fatura["vencimento"],
                calendario=calendario,
            )
            resultados.append({
                "empresa":    fatura["empresa"],
                "vencimento": fatura["vencimento"].isoformat(),
                "status":     "criado",
                "link":       evento.get("htmlLink", ""),
                "id":         evento.get("id", ""),
            })
        except Exception as e:
            resultados.append({
                "empresa":    fatura.get("empresa", "?"),
                "vencimento": str(fatura.get("vencimento", "?")),
                "status":     "erro",
                "erro":       str(e),
            })

    return resultados
