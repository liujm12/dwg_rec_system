from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..parsers import available_adapters, get_adapter
from .recognition import RecognitionImportService


class ParserImportService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def import_file(
        self,
        path: str | Path,
        adapter_name: str = "sample-json",
    ) -> dict[str, Any]:
        adapter = get_adapter(adapter_name)
        recognition_payload = adapter.parse_file(path)
        summary = RecognitionImportService(self.connection).import_data(recognition_payload)
        return {
            "adapter_name": adapter.adapter_name,
            "parser_name": adapter.parser_name,
            "parser_version": adapter.parser_version,
            "source_type": adapter.source_type,
            "recognition": summary,
        }


def list_parser_adapters() -> list[dict]:
    return available_adapters()
