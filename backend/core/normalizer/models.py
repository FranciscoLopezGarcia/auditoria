from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IndexedItem:
    json_path: str
    label: Optional[str]
    value: float
    raw: str
    codigo: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexedSource:
    source: str
    periodo: Optional[str]
    items: List[IndexedItem]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalConceptEvidence:
    label_original: Optional[str]
    codigo: Optional[str]
    json_path: str
    raw: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalConceptValue:
    valor: float
    evidencia: CanonicalConceptEvidence


@dataclass
class CanonicalSourceModel:
    source: str
    periodo: Optional[str]
    conceptos: Dict[str, CanonicalConceptValue]
    variables_contables: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]