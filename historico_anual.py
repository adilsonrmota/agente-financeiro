import argparse
import json
import os
import re
from datetime import date, datetime

from dotenv import load_dotenv

from gmail_reader import FINANCIAL_KEYWORDS
from pdf_reader import download_pdf_attachments
from reports import generate_monthly_reports

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")


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


def _save_raw_records(records: list[dict], year: int) -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, f"historico_{year}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return path


def build_historical_reports(year: int, max_results: int = 2000) -> None:
    load_dotenv()
    cpf = os.getenv("CPF", "").strip()

    if not cpf:
        raise RuntimeError("CPF não encontrado no .env")

    query = (
        f"({' OR '.join(FINANCIAL_KEYWORDS)}) has:attachment filename:pdf "
        f"after:{year}/01/01 before:{year + 1}/01/01"
    )

    print(f"Buscando e-mails financeiros de {year}...")
    pdf_items = download_pdf_attachments(
        cpf=cpf,
        max_results=max_results,
        output_dir=os.path.join("downloads", "pdfs", str(year)),
        skip_email_ids=set(),
        query=query,
        inbox_only=False,
    )

    if not pdf_items:
        print("Nenhum e-mail com PDF encontrado para o período.")
        return

    records: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    pdf_errors = 0
    parse_warnings = 0

    for item in pdf_items:
        extraction = item.get("extração", {})
        email_id = str(item.get("email_id", ""))
        arquivo = str(item.get("arquivo", ""))
        dedup_key = (email_id, arquivo)

        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        empresa = item.get("empresa", "Não identificada")
        assunto = item.get("assunto", "")

        if extraction.get("error"):
            pdf_errors += 1
            records.append(
                {
                    "empresa": empresa,
                    "valor": "",
                    "vencimento": "",
                    "status": "erro pdf",
                    "origem email": assunto,
                    "arquivo pdf": arquivo,
                }
            )
            continue

        text = extraction.get("text", "")
        valor = _extract_amount(text)
        vencimento = _extract_due_date(text)

        status = "extraido"
        if not valor or not vencimento:
            status = "dados incompletos"
            parse_warnings += 1

        records.append(
            {
                "empresa": empresa,
                "valor": valor or "",
                "vencimento": vencimento or "",
                "status": status,
                "origem email": assunto,
                "arquivo pdf": arquivo,
            }
        )

    raw_path = _save_raw_records(records, year)

    months = set()
    for record in records:
        due = _parse_due_date(record.get("vencimento"))
        if due and due.year == year:
            months.add(due.month)

    generated = []
    for month in sorted(months):
        info = generate_monthly_reports(records, year, month)
        generated.append(info)

    print("Resumo da carga histórica:")
    print(f"Itens lidos: {len(pdf_items)}")
    print(f"Registros consolidados: {len(records)}")
    print(f"Erros de PDF: {pdf_errors}")
    print(f"Avisos de parsing: {parse_warnings}")
    print(f"JSON bruto: {raw_path}")

    if not generated:
        print("Nenhum relatório mensal foi gerado (sem vencimentos válidos).")
        return

    print("Relatórios gerados:")
    for info in generated:
        print(
            f"- {info['year']}-{info['month']:02d} | registros={info['total_records']} | "
            f"csv={info['csv']} | excel={info['excel']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga histórica de e-mails financeiros por ano")
    parser.add_argument("--year", type=int, default=date.today().year, help="Ano da carga histórica")
    parser.add_argument("--max-results", type=int, default=2000, help="Limite de e-mails a buscar")
    args = parser.parse_args()

    build_historical_reports(year=args.year, max_results=args.max_results)
