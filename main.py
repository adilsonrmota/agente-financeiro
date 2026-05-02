import json
import os
import re
import traceback
from datetime import date, datetime

from dotenv import load_dotenv

from agenda import criar_evento_vencimento
from gmail_reader import FINANCIAL_SENDERS, get_financial_body_emails
from pdf_reader import download_pdf_attachments

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_FILE = os.path.join(BASE_DIR, "processados.json")
LOG_FILE = os.path.join(BASE_DIR, "log.txt")


def _append_log(level: str, message: str, **context: object) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context_str = " | ".join(f"{key}={value}" for key, value in context.items())
    line = f"[{timestamp}] {level} | {message}"
    if context_str:
        line += f" | {context_str}"

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{line}\n")


def _load_processed_ids() -> set[str]:
    if not os.path.exists(PROCESSED_FILE):
        return set()

    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return set()

    if isinstance(data, list):
        return set(str(item) for item in data)

    if isinstance(data, dict):
        return set(str(item) for item in data.get("emails", []))

    return set()


def _save_processed_ids(processed_ids: set[str]) -> None:
    with open(PROCESSED_FILE, "w", encoding="utf-8") as file:
        json.dump({"emails": sorted(processed_ids)}, file, ensure_ascii=False, indent=2)


def _extract_amount(text: str) -> str | None:
    normalized_text = re.sub(r"\s+", " ", text)
    patterns = [
        r"(?:valor\s+total\s+a\s+pagar|total\s+a\s+pagar|valor\s+da\s+fatura|valor\s+do\s+documento|valor\s+total|valor\s+final|valor)\s*[:\-]?\s*R\$\s*([0-9\.,]+)",
        r"(?:pagamento|total|fatura|boleto)\s*[:\-]?\s*R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})",
        r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            return f"R$ {match.group(1)}"

    return None


def _extract_due_date(text: str) -> str | None:
    normalized_text = re.sub(r"\s+", " ", text)
    patterns = [
        r"(?:data\s+de\s+vencimento|vencimento|vence\s+em|vcto\.?|vencto\.?)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        r"(?:pagar\s+ate|pagamento\s+ate|validade)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        r"(\d{2}[/-]\d{2}[/-]\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).replace("-", "/")

    return None


def _parse_due_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _print_item(empresa: str, valor: str | None, vencimento: str | None) -> None:
    print(f"Empresa: {empresa}")
    print(f"Valor: {valor or 'Não identificado'}")
    print(f"Vencimento: {vencimento or 'Não identificado'}")
    print()


def main() -> None:
    load_dotenv()
    cpf = os.getenv("CPF", "").strip()
    max_results_raw = os.getenv("EMAIL_MAX_RESULTS", "200").strip()

    try:
        max_results = max(1, int(max_results_raw))
    except ValueError:
        max_results = 200

    if not cpf:
        message = "CPF não encontrado no arquivo .env"
        print(message)
        _append_log("ERROR", message)
        return

    processed_ids = _load_processed_ids()

    print("Lendo Gmail, filtrando contas e processando PDFs...\n")
    _append_log("INFO", "Execução diária iniciada")

    try:
        pdf_items = download_pdf_attachments(
            cpf=cpf,
            max_results=max_results,
            skip_email_ids=processed_ids,
        )
        body_query = " OR ".join(f"from:{sender}" for sender in FINANCIAL_SENDERS.values())
        body_items = get_financial_body_emails(
            max_results=max_results,
            query=body_query,
            skip_email_ids=processed_ids,
        )
    except Exception as exc:
        print(f"Erro ao consultar Gmail/PDFs: {exc}")
        _append_log("ERROR", "Falha ao consultar Gmail/PDFs", erro=str(exc), traceback=traceback.format_exc().strip())
        return

    if not pdf_items and not body_items:
        print("Nenhum novo e-mail financeiro para processar.")
        _append_log("INFO", "Nenhum novo e-mail financeiro para processar")
        return

    total_items = len(pdf_items)
    processed_now = 0
    pdf_errors = 0
    parse_warnings = 0
    calendar_created = 0
    calendar_duplicates = 0
    calendar_errors = 0
    seen_event_keys: set[tuple[str, str, str]] = set()

    for item in pdf_items:
        email_id = item.get("email_id", "desconhecido")
        empresa = item.get("empresa", "Não identificada")

        try:
            extraction = item["extração"]

            if extraction.get("error"):
                pdf_errors += 1
                _print_item(empresa, None, None)
                _append_log("ERROR", "Falha ao extrair PDF", email_id=email_id, empresa=empresa, erro=extraction["error"], arquivo=item.get("arquivo", ""))
                processed_ids.add(email_id)
                processed_now += 1
                continue

            text = extraction.get("text", "")
            valor = _extract_amount(text)
            vencimento = _extract_due_date(text)
            vencimento_data = _parse_due_date(vencimento)

            event_link = None
            event_error = None
            event_exists = False

            if valor and vencimento_data:
                event_key = (empresa, valor, vencimento_data.isoformat())
                if event_key in seen_event_keys:
                    event_exists = True
                else:
                    try:
                        event = criar_evento_vencimento(
                            empresa=empresa,
                            valor=valor,
                            vencimento=vencimento_data,
                        )
                        event_link = event.get("htmlLink")
                        event_exists = bool(event.get("already_exists"))
                        seen_event_keys.add(event_key)
                    except Exception as exc:
                        event_error = str(exc)

            _print_item(empresa, valor, vencimento)

            if event_link and event_exists:
                calendar_duplicates += 1
                print(f"Evento existente: {event_link}")
                print()
            elif event_link:
                calendar_created += 1
                print(f"Evento: {event_link}")
                print()
            elif event_error:
                calendar_errors += 1
                print(f"Erro Calendario: {event_error}")
                print()
            elif valor is None or vencimento is None:
                parse_warnings += 1

            should_mark_processed = event_error is None

            if event_link and event_exists:
                _append_log("INFO", "Evento já existente no calendário", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", evento=event_link)
            elif event_link:
                _append_log("INFO", "Evento criado no calendário", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", evento=event_link)
            elif event_error:
                _append_log("ERROR", "Falha ao criar evento no calendário", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", erro=event_error)
            else:
                _append_log("WARN", "Dados incompletos para criar evento", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", arquivo=item.get("arquivo", ""))

            if should_mark_processed:
                processed_ids.add(email_id)
            processed_now += 1
        except Exception as exc:
            _append_log("ERROR", "Falha inesperada ao processar item", email_id=email_id, empresa=empresa, erro=str(exc), traceback=traceback.format_exc().strip())
            print(f"Erro inesperado ao processar {empresa}: {exc}")
            print()

    pdf_email_ids = {str(item.get("email_id", "")) for item in pdf_items}
    for item in body_items:
        email_id = str(item.get("id", "desconhecido"))
        if email_id in pdf_email_ids and item.get("has_pdf"):
            continue

        empresa = item.get("company", "Não identificada")
        assunto = item.get("subject", "")

        try:
            content = f"{item.get('subject', '')} {item.get('snippet', '')} {item.get('body_text', '')}"
            valor = _extract_amount(content)
            vencimento = _extract_due_date(content)
            vencimento_data = _parse_due_date(vencimento)

            event_link = None
            event_error = None
            event_exists = False

            if valor and vencimento_data:
                event_key = (empresa, valor, vencimento_data.isoformat())
                if event_key in seen_event_keys:
                    event_exists = True
                else:
                    try:
                        event = criar_evento_vencimento(
                            empresa=empresa,
                            valor=valor,
                            vencimento=vencimento_data,
                        )
                        event_link = event.get("htmlLink")
                        event_exists = bool(event.get("already_exists"))
                        seen_event_keys.add(event_key)
                    except Exception as exc:
                        event_error = str(exc)

            _print_item(empresa, valor, vencimento)

            if event_link and event_exists:
                calendar_duplicates += 1
                print(f"Evento existente: {event_link}")
                print()
            elif event_link:
                calendar_created += 1
                print(f"Evento: {event_link}")
                print()
            elif event_error:
                calendar_errors += 1
                print(f"Erro Calendario: {event_error}")
                print()
            elif valor is None or vencimento is None:
                parse_warnings += 1

            should_mark_processed = event_error is None

            if event_link and event_exists:
                _append_log("INFO", "Evento já existente no calendário (corpo e-mail)", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", origem=assunto, evento=event_link)
            elif event_link:
                _append_log("INFO", "Evento criado no calendário (corpo e-mail)", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", origem=assunto, evento=event_link)
            elif event_error:
                _append_log("ERROR", "Falha ao criar evento no calendário (corpo e-mail)", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", origem=assunto, erro=event_error)
            else:
                _append_log("WARN", "Dados incompletos para criar evento (corpo e-mail)", email_id=email_id, empresa=empresa, valor=valor or "nao-identificado", vencimento=vencimento or "nao-identificado", origem=assunto)

            if should_mark_processed:
                processed_ids.add(email_id)
            processed_now += 1
            total_items += 1
        except Exception as exc:
            _append_log("ERROR", "Falha inesperada ao processar corpo do e-mail", email_id=email_id, empresa=empresa, erro=str(exc), traceback=traceback.format_exc().strip())
            print(f"Erro inesperado ao processar corpo de e-mail ({empresa}): {exc}")
            print()

    _save_processed_ids(processed_ids)

    print("Resumo final:")
    print(f"Itens encontrados: {total_items}")
    print(f"Itens processados: {processed_now}")
    print(f"Erros de PDF: {pdf_errors}")
    print(f"Avisos de parsing: {parse_warnings}")
    print(f"Eventos criados: {calendar_created}")
    print(f"Eventos duplicados: {calendar_duplicates}")
    print(f"Erros de calendário: {calendar_errors}")

    _append_log(
        "INFO",
        "Execução diária finalizada",
        itens_encontrados=total_items,
        itens_processados=processed_now,
        erros_pdf=pdf_errors,
        avisos_parsing=parse_warnings,
        eventos_criados=calendar_created,
        eventos_duplicados=calendar_duplicates,
        erros_calendario=calendar_errors,
    )


if __name__ == "__main__":
    main()