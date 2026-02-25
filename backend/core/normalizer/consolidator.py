from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import CanonicalSourceModel, CanonicalConceptValue


# ---------------------------------------------------------------------
# V1 (se deja tal cual existe hoy)
# ---------------------------------------------------------------------

SOURCE_PRIORITY: list[str] = ["f931", "borrador", "asiento"]


@dataclass(frozen=True)
class ConsolidatedModel:
    periodo: str
    conceptos: dict[str, float]
    origen_por_concepto: dict[str, str]
    faltantes: list[str]


class Consolidator:
    def __init__(
        self,
        sources: list[CanonicalSourceModel],
        concept_keys: list[str],
        priority: list[str] = SOURCE_PRIORITY,
    ) -> None:
        self._sources: dict[str, CanonicalSourceModel] = {
            model.source: model for model in sources
        }
        self._concept_keys = concept_keys
        self._priority = priority

    def consolidate(self) -> ConsolidatedModel:
        periodo = self._resolve_period()
        conceptos: dict[str, float] = {}
        origen_por_concepto: dict[str, str] = {}
        faltantes: list[str] = []

        for key in self._concept_keys:
            value, origin = self._resolve_concept(key)
            if value is not None and origin is not None:
                conceptos[key] = value
                origen_por_concepto[key] = origin
            else:
                faltantes.append(key)

        return ConsolidatedModel(
            periodo=periodo,
            conceptos=conceptos,
            origen_por_concepto=origen_por_concepto,
            faltantes=faltantes,
        )

    def _resolve_concept(self, key: str) -> tuple[Optional[float], Optional[str]]:
        for source_name in self._priority:
            model = self._sources.get(source_name)
            if model is None:
                continue
            concept: Optional[CanonicalConceptValue] = model.conceptos.get(key)
            if concept is not None:
                try:
                    return float(concept.valor), source_name
                except (TypeError, ValueError):
                    continue
        return None, None

    def _resolve_period(self) -> str:
        for source_name in self._priority:
            model = self._sources.get(source_name)
            if model is not None and model.periodo:
                return model.periodo
        return ""


# ---------------------------------------------------------------------
# V2 (nuevo): Consolidado técnico completo para alimentar Excel
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class ConsolidatedCanonicalBlock:
    """
    Bloque canónico (lo que ya resuelve el normalizer + dictionary).
    Sirve para controles / diagnóstico / métricas.
    """
    periodo: str
    conceptos: dict[str, float]
    origen_por_concepto: dict[str, str]
    faltantes: list[str]


@dataclass(frozen=True)
class ConsolidatedDiagnostics:
    """
    Diagnóstico puramente técnico: warnings agregados, fuentes presentes, etc.
    """
    sources_present: list[str] = field(default_factory=list)
    warnings_by_source: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsolidatedTechnicalModel:
    """
    Consolidado técnico completo:
    - sources_raw: JSON parseado de cada fuente (metadata + extracted + raw, etc)
    - canonical: bloque canónico v1 (opcional pero recomendado)
    - diagnostics: warnings + trazas
    """
    schema_version: str
    periodo_iso: str

    sources_raw: dict[str, dict[str, Any]]
    canonical: ConsolidatedCanonicalBlock
    diagnostics: ConsolidatedDiagnostics


class ConsolidatorV2:
    """
    Consolida TODO lo relevante, sin interpretar:
    - adjunta los 3 parseados (raw) para que el ExcelMapper no tenga que reparsear
    - genera el bloque canónico (mismo comportamiento del Consolidator v1)
    - agrega diagnostics
    """

    def __init__(
        self,
        sources_canonical: list[CanonicalSourceModel],
        sources_raw: dict[str, dict[str, Any]],
        concept_keys: list[str],
        priority: list[str] = SOURCE_PRIORITY,
        schema_version: str = "2.0.0",
    ) -> None:
        self._canon_by_name: dict[str, CanonicalSourceModel] = {
            s.source: s for s in sources_canonical
        }
        self._raw_by_name = sources_raw
        self._concept_keys = concept_keys
        self._priority = priority
        self._schema_version = schema_version

    def consolidate(self) -> ConsolidatedTechnicalModel:
        periodo_iso = self._resolve_period_iso()

        canonical_block = self._build_canonical_block(periodo_iso)
        diagnostics = self._build_diagnostics()

        return ConsolidatedTechnicalModel(
            schema_version=self._schema_version,
            periodo_iso=periodo_iso,
            sources_raw=self._raw_by_name,
            canonical=canonical_block,
            diagnostics=diagnostics,
        )

    # -------------------------
    # Periodo ISO: 2025-05
    # -------------------------
    def _resolve_period_iso(self) -> str:
        # 1) Intentar desde RAW (más confiable para Excel)
        for source_name in self._priority:
            raw = self._raw_by_name.get(source_name) or {}
            md = raw.get("metadata") or {}

            # F931 / Borrador típicamente traen periodo_iso
            p = md.get("periodo_iso")
            if isinstance(p, str) and p.strip():
                return p.strip()

            # Asiento trae "periodo_detectado" tipo "05/2025"
            pd = md.get("periodo_detectado")
            if isinstance(pd, str) and "/" in pd:
                mm, yyyy = pd.split("/", 1)
                mm = mm.zfill(2)
                yyyy = yyyy.strip()
                return f"{yyyy}-{mm}"

        # 2) Fallback desde canonical models (lo que tenías en v1)
        for source_name in self._priority:
            c = self._canon_by_name.get(source_name)
            if c and c.periodo:
                return c.periodo

        return ""

    # -------------------------
    # Canonical block (v1)
    # -------------------------
    def _build_canonical_block(self, periodo_iso: str) -> ConsolidatedCanonicalBlock:
        conceptos: dict[str, float] = {}
        origen_por_concepto: dict[str, str] = {}
        faltantes: list[str] = []

        for key in self._concept_keys:
            value, origin = self._resolve_concept(key)
            if value is not None and origin is not None:
                conceptos[key] = value
                origen_por_concepto[key] = origin
            else:
                faltantes.append(key)

        return ConsolidatedCanonicalBlock(
            periodo=periodo_iso,
            conceptos=conceptos,
            origen_por_concepto=origen_por_concepto,
            faltantes=faltantes,
        )

    def _resolve_concept(self, key: str) -> tuple[Optional[float], Optional[str]]:
        for source_name in self._priority:
            model = self._canon_by_name.get(source_name)
            if model is None:
                continue
            concept: Optional[CanonicalConceptValue] = model.conceptos.get(key)
            if concept is not None:
                try:
                    return float(concept.valor), source_name
                except (TypeError, ValueError):
                    continue
        return None, None

    # -------------------------
    # Diagnostics
    # -------------------------
    def _build_diagnostics(self) -> ConsolidatedDiagnostics:
        present = sorted(set(self._raw_by_name.keys()) | set(self._canon_by_name.keys()))
        warnings_by_source: dict[str, list[dict[str, Any]]] = {}

        for name in present:
            c = self._canon_by_name.get(name)
            if c and c.warnings:
                warnings_by_source[name] = list(c.warnings)
            else:
                warnings_by_source[name] = []

        return ConsolidatedDiagnostics(
            sources_present=present,
            warnings_by_source=warnings_by_source,
        )