"""Modelos de dados: um lead individual e a coleção com deduplicação/persistência."""

from __future__ import annotations

import datetime
import os
from dataclasses import asdict, dataclass, field

import pandas as pd

from atlasleads.constants import DATA_DIR


@dataclass
class Business:
    """Representa os dados de um lead coletado do Google Maps."""

    name: str | None = None
    address: str | None = None
    domain: str | None = None
    website: str | None = None
    phone_number: str | None = None
    category: str | None = None
    location: str | None = None
    reviews_count: int | None = None
    reviews_average: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    emails: str | None = None
    scraped_phones: str | None = None

    def __hash__(self) -> int:
        """Gera hash com base em nome + campos de contato não-vazios."""
        key_parts = [self.name]
        if self.domain:
            key_parts.append(f"domain:{self.domain}")
        if self.website:
            key_parts.append(f"website:{self.website}")
        if self.phone_number:
            key_parts.append(f"phone:{self.phone_number}")
        return hash(tuple(key_parts))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Business) and hash(self) == hash(other)


@dataclass
class BusinessCollection:
    """Coleção de leads com deduplicação automática e persistência em CSV/XLSX."""

    _items: list[Business] = field(default_factory=list, init=False)
    _seen: set[int] = field(default_factory=set, init=False)
    _output_dir: str = field(init=False)

    def __post_init__(self) -> None:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self._output_dir = os.path.join(DATA_DIR, today)
        os.makedirs(self._output_dir, exist_ok=True)

    def add(self, business: Business) -> None:
        """Adiciona um lead ao conjunto se ainda não existir."""
        key = hash(business)
        if key not in self._seen:
            self._items.append(business)
            self._seen.add(key)

    def to_dataframe(self) -> pd.DataFrame:
        """Converte a coleção em um DataFrame pandas."""
        return pd.json_normalize((asdict(b) for b in self._items), sep="_")

    def save(self, filename: str) -> None:
        """Persiste a coleção em CSV e XLSX no diretório de saída."""
        safe_name = filename.replace(" ", "_")
        df = self.to_dataframe()
        df.to_csv(os.path.join(self._output_dir, f"{safe_name}.csv"), index=False)
        df.to_excel(os.path.join(self._output_dir, f"{safe_name}.xlsx"), index=False)

    @property
    def output_dir(self) -> str:
        return self._output_dir

    def __len__(self) -> int:
        return len(self._items)
