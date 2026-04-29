import csv
import os
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font

REPORT_COLUMNS = [
    "empresa",
    "valor",
    "vencimento",
    "status",
    "origem email",
    "arquivo pdf",
]


def _normalize_due_date(value) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

    return None


def _normalize_record(record: dict) -> dict:
    due_date = _normalize_due_date(record.get("vencimento"))

    return {
        "empresa": str(record.get("empresa", "")).strip(),
        "valor": str(record.get("valor", "")).strip(),
        "vencimento": due_date.strftime("%d/%m/%Y") if due_date else str(record.get("vencimento", "")).strip(),
        "status": str(record.get("status", "")).strip(),
        "origem email": str(record.get("origem email", record.get("origem_email", ""))).strip(),
        "arquivo pdf": str(record.get("arquivo pdf", record.get("arquivo_pdf", ""))).strip(),
        "_due_date": due_date,
    }


def _filter_month(records: list[dict], year: int, month: int) -> list[dict]:
    filtered = []

    for record in records:
        normalized = _normalize_record(record)
        due_date = normalized["_due_date"]

        if due_date and due_date.year == year and due_date.month == month:
            filtered.append(normalized)

    filtered.sort(key=lambda item: (item["_due_date"], item["empresa"], item["valor"]))
    return filtered


def _report_paths(output_dir: str, year: int, month: int) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    base_name = f"relatorio_{year}_{month:02d}"
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    xlsx_path = os.path.join(output_dir, f"{base_name}.xlsx")
    return csv_path, xlsx_path


def generate_monthly_csv(records: list[dict], year: int, month: int, output_dir: str = "reports") -> str:
    monthly_records = _filter_month(records, year, month)
    csv_path, _ = _report_paths(output_dir, year, month)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()

        for record in monthly_records:
            writer.writerow({column: record[column] for column in REPORT_COLUMNS})

    return csv_path


def generate_monthly_excel(records: list[dict], year: int, month: int, output_dir: str = "reports") -> str:
    monthly_records = _filter_month(records, year, month)
    _, xlsx_path = _report_paths(output_dir, year, month)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"{year}-{month:02d}"

    sheet.append(REPORT_COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for record in monthly_records:
        sheet.append([record[column] for column in REPORT_COLUMNS])

    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 60)

    workbook.save(xlsx_path)
    return xlsx_path


def generate_monthly_reports(records: list[dict], year: int, month: int, output_dir: str = "reports") -> dict:
    csv_path = generate_monthly_csv(records, year, month, output_dir=output_dir)
    xlsx_path = generate_monthly_excel(records, year, month, output_dir=output_dir)

    return {
        "csv": csv_path,
        "excel": xlsx_path,
        "year": year,
        "month": month,
        "total_records": len(_filter_month(records, year, month)),
    }


if __name__ == "__main__":
    example_records = [
        {
            "empresa": "Claro",
            "valor": "R$ 225,32",
            "vencimento": "05/05/2026",
            "status": "evento criado",
            "origem email": "Sua Fatura Digital Claro chegou",
            "arquivo pdf": "downloads/pdfs/Fatura Claro.pdf",
        },
        {
            "empresa": "CPFL",
            "valor": "R$ 189,90",
            "vencimento": "10/05/2026",
            "status": "aguardando revisão",
            "origem email": "Conta por e-mail CPFL",
            "arquivo pdf": "downloads/pdfs/Conta_CPFL.pdf",
        },
    ]

    today = date.today()
    report_files = generate_monthly_reports(example_records, today.year, today.month)
    print(f"CSV: {report_files['csv']}")
    print(f"Excel: {report_files['excel']}")
    print(f"Registros: {report_files['total_records']}")