"""Excel output helpers."""

from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def create_workbook_with_headers(sheet_title: str, headers: Iterable[str]) -> tuple[Workbook, Worksheet]:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_title
    worksheet.append(list(headers))
    return workbook, worksheet


def save_workbook(workbook: Workbook, output_path: Path) -> None:
    ensure_parent_dir(output_path)
    workbook.save(output_path)
