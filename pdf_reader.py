import os
import base64
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from gmail_reader import FINANCIAL_KEYWORDS, _detect_company, _get_service, _parse_headers


def _cpf_password_candidates(cpf: str) -> list[str]:
    """
    Gera senhas candidatas a partir dos dígitos do CPF.
    Formato esperado: apenas dígitos, ex: '18394401805'
    """
    digits = cpf.replace(".", "").replace("-", "").replace(" ", "").strip()

    if len(digits) != 11:
        return [digits]

    formatted = f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"

    candidates = [
        digits,                         # 18394401805
        formatted,                      # 183.944.018-05
        digits[:3],                     # 3 primeiros: 183
        digits[:5],                     # 5 primeiros (comum em faturas Claro): 18394
        digits[-2:],                    # 2 últimos (dígitos verificadores): 05
        digits[:6],                     # 6 primeiros: 183944
        digits[-4:],                    # 4 últimos: 1805
        digits[:9],                     # 9 primeiros (sem dígitos verificadores): 183944018
        digits[9:],                     # dígitos verificadores: 05
        digits[:3] + digits[-2:],       # primeiros 3 + últimos 2: 18305
        digits[-6:],                    # 6 últimos: 401805
    ]

    # remove duplicatas mantendo ordem
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def extract_text(pdf_path: str, cpf: str | None = None) -> dict:
    """
    Extrai o texto completo de um PDF.

    - Se o PDF não for protegido, extrai diretamente.
    - Se for protegido por senha, tenta automaticamente combinações
      baseadas nos dígitos do CPF informado.

    Parâmetros:
        pdf_path  : caminho absoluto ou relativo ao arquivo PDF
        cpf       : CPF do titular (apenas dígitos ou formatado)

    Retorno (dict):
        {
            "path":       str,   caminho do arquivo
            "pages":      int,   número de páginas
            "protected":  bool,  True se o PDF era protegido por senha
            "password":   str | None,  senha que funcionou (se protegido)
            "text":       str,   texto completo extraído
            "error":      str | None,  mensagem de erro, se houver
        }
    """
    result = {
        "path":      pdf_path,
        "pages":     0,
        "protected": False,
        "password":  None,
        "text":      "",
        "error":     None,
    }

    if not os.path.isfile(pdf_path):
        result["error"] = f"Arquivo não encontrado: {pdf_path}"
        return result

    try:
        reader = PdfReader(pdf_path)

        if reader.is_encrypted:
            result["protected"] = True
            unlocked = False

            # tenta senha vazia primeiro
            candidates = [""]
            if cpf:
                candidates += _cpf_password_candidates(cpf)

            for pwd in candidates:
                try:
                    if reader.decrypt(pwd):
                        result["password"] = pwd if pwd else "(vazia)"
                        unlocked = True
                        break
                except Exception:
                    continue

            if not unlocked:
                result["error"] = (
                    "PDF protegido por senha. Nenhuma combinação do CPF funcionou."
                )
                return result

        result["pages"] = len(reader.pages)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

        result["text"] = "\n".join(pages_text).strip()

    except PdfReadError as e:
        result["error"] = f"Erro ao ler o PDF: {e}"

    return result


def _collect_pdf_parts(parts: list) -> list[dict]:
    pdf_parts = []

    for part in parts or []:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})

        if mime_type == "application/pdf" and filename and body.get("attachmentId"):
            pdf_parts.append({
                "filename": filename,
                "attachment_id": body["attachmentId"],
            })

        # multipart/* pode conter anexos em níveis mais profundos
        nested_parts = part.get("parts", [])
        if nested_parts:
            pdf_parts.extend(_collect_pdf_parts(nested_parts))

    return pdf_parts


def download_pdf_attachments(
    cpf: str,
    max_results: int = 20,
    output_dir: str = "downloads/pdfs",
    skip_email_ids: set[str] | None = None,
    query: str | None = None,
    inbox_only: bool = True,
) -> list[dict]:
    """
    Procura anexos PDF em e-mails financeiros filtrados e baixa para disco.

    Retorna uma lista de dicts contendo metadados do e-mail, caminho do PDF
    e o texto extraído via extract_text().
    """
    service = _get_service()
    query_text = query or f"({' OR '.join(FINANCIAL_KEYWORDS)}) has:attachment filename:pdf"

    messages: list[dict] = []
    page_token = None

    while len(messages) < max_results:
        request_size = min(500, max_results - len(messages))
        request_kwargs = {
            "userId": "me",
            "q": query_text,
            "maxResults": request_size,
        }
        if inbox_only:
            request_kwargs["labelIds"] = ["INBOX"]
        if page_token:
            request_kwargs["pageToken"] = page_token

        response = service.users().messages().list(**request_kwargs).execute()
        batch = response.get("messages", [])
        if not batch:
            break

        messages.extend(batch)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    os.makedirs(output_dir, exist_ok=True)

    results = []
    skip_ids = skip_email_ids or set()

    for msg in messages:
        message_id = msg.get("id")
        if message_id in skip_ids:
            continue

        meta = service.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()

        headers = _parse_headers(meta.get("payload", {}).get("headers", []))
        subject = headers.get("Subject", "(sem assunto)")
        sender = headers.get("From", "(desconhecido)")
        raw_date = headers.get("Date", "")
        snippet = meta.get("snippet", "")

        combined = (subject + " " + snippet).lower()
        matched = [kw for kw in FINANCIAL_KEYWORDS if kw in combined]
        if not matched:
            continue

        company = _detect_company(sender, subject, snippet, matched)

        message = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

        payload = message.get("payload", {})
        pdf_parts = _collect_pdf_parts(payload.get("parts", []))

        if not pdf_parts:
            continue

        for idx, part in enumerate(pdf_parts, start=1):
            attachment = service.users().messages().attachments().get(
                userId="me",
                messageId=message_id,
                id=part["attachment_id"],
            ).execute()

            data = attachment.get("data", "")
            if not data:
                continue

            raw_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))

            safe_filename = part["filename"].replace("/", "_").replace("\\", "_")
            if len(pdf_parts) > 1:
                name, ext = os.path.splitext(safe_filename)
                safe_filename = f"{name}_{idx}{ext}"

            pdf_path = os.path.join(output_dir, safe_filename)

            with open(pdf_path, "wb") as f:
                f.write(raw_bytes)

            extraction = extract_text(pdf_path, cpf=cpf)

            results.append({
                "email_id": message_id,
                "empresa": company,
                "assunto": subject,
                "data": raw_date,
                "arquivo": pdf_path,
                "extração": extraction,
            })

    return results
