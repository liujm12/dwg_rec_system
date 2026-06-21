from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ParserAdapter(Protocol):
    adapter_name: str
    parser_name: str
    parser_version: str
    source_type: str

    def parse_file(self, path: str | Path) -> dict:
        ...

    def parse_data(self, payload: dict, source_uri: str | None = None) -> dict:
        ...


def available_adapters() -> list[dict]:
    from .sample_json import SampleJsonParserAdapter

    adapter = SampleJsonParserAdapter()
    return [
        {
            "adapter_name": adapter.adapter_name,
            "parser_name": adapter.parser_name,
            "parser_version": adapter.parser_version,
            "source_type": adapter.source_type,
        }
    ]


def get_adapter(name: str) -> ParserAdapter:
    from .sample_json import SampleJsonParserAdapter

    adapters = {
        SampleJsonParserAdapter.adapter_name: SampleJsonParserAdapter,
    }
    adapter_class = adapters.get(name)
    if not adapter_class:
        raise ValueError(f"unsupported parser adapter: {name}")
    return adapter_class()
