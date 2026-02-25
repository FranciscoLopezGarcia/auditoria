import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# -----------------------------------------------------
# DATA MODEL
# -----------------------------------------------------

@dataclass
class PeriodBundle:
    periodo: str
    f931: Optional[str] = None
    borrador: Optional[str] = None
    asiento: Optional[str] = None
    status: str = "PENDING"
    diagnostics: Dict = field(default_factory=dict)


# -----------------------------------------------------
# ORCHESTRATOR A
# -----------------------------------------------------

class OrchestratorA:

    def __init__(
        self,
        project_root: str,
        temp_input_dir: str = "temp_inputs",
        output_dir: str = "output"
    ):
        self.project_root = Path(project_root)
        self.temp_input_dir = self.project_root / temp_input_dir
        self.output_dir = self.project_root / output_dir

        self.temp_input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    # -----------------------------------------------------
    # PUBLIC ENTRYPOINT
    # -----------------------------------------------------

    def run(self, pdf_paths: List[str]) -> Dict[str, PeriodBundle]:

        bundles = self._group_by_period(pdf_paths)

        for periodo, bundle in bundles.items():

            self._validate_bundle(bundle)

            if bundle.status == "BLOCKED":
                continue

            try:
                self._execute_pipeline(bundle)
                bundle.status = "OK"

            except Exception as e:
                bundle.status = "BLOCKED"
                bundle.diagnostics["pipeline_error"] = str(e)

        return bundles

    # -----------------------------------------------------
    # GROUPING
    # -----------------------------------------------------

    def _group_by_period(self, pdf_paths: List[str]) -> Dict[str, PeriodBundle]:

        bundles: Dict[str, PeriodBundle] = {}

        for path in pdf_paths:

            filename = os.path.basename(path).upper()
            periodo = self._extract_period(filename)

            if not periodo:
                continue

            if periodo not in bundles:
                bundles[periodo] = PeriodBundle(periodo=periodo)

            bundle = bundles[periodo]

            if "F931" in filename:
                bundle.f931 = path
            elif "BORRADOR" in filename:
                bundle.borrador = path
            elif "ASIENTO" in filename:
                bundle.asiento = path

        return bundles

    def _extract_period(self, filename: str) -> Optional[str]:
        # YYYY-MM o YYYYMM
        match = re.search(r"(20\d{2})[-_]?(\d{2})", filename)
        if match:
            year, month = match.groups()
            return f"{year}-{month}"

        # MM-YY
        match_alt = re.search(r"(\d{2})[-_](\d{2})", filename)
        if match_alt:
            month, year_short = match_alt.groups()
            year = f"20{year_short}"
            return f"{year}-{month}"

        # MMYYYY (ej: 052025)
        match_compact = re.search(r"(\d{2})(20\d{2})", filename)
        if match_compact:
            month, year = match_compact.groups()
            return f"{year}-{month}"

        return None
    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    def _validate_bundle(self, bundle: PeriodBundle):

        missing = []

        if not bundle.f931:
            missing.append("F931")
        if not bundle.borrador:
            missing.append("BORRADOR")
        if not bundle.asiento:
            missing.append("ASIENTO")

        if missing:
            bundle.status = "BLOCKED"
            bundle.diagnostics["missing_documents"] = missing

    # -----------------------------------------------------
    # PIPELINE
    # -----------------------------------------------------

    def _execute_pipeline(self, bundle: PeriodBundle):

        periodo = bundle.periodo

        # 1️⃣ limpiar output antes de procesar
        self._clean_output_jsons()

        # 2️⃣ crear carpeta temporal para este periodo
        periodo_input_dir = self.temp_input_dir / periodo
        if periodo_input_dir.exists():
            shutil.rmtree(periodo_input_dir)
        periodo_input_dir.mkdir(parents=True)

        # 3️⃣ copiar PDFs
        shutil.copy(bundle.f931, periodo_input_dir)
        shutil.copy(bundle.borrador, periodo_input_dir)
        shutil.copy(bundle.asiento, periodo_input_dir)

        # 4️⃣ ejecutar pipeline
        self._run_parser(periodo_input_dir)
        self._run_normalizer()
        self._run_consolidator()

        # 5️⃣ validar consolidated
        consolidated_path = self.output_dir / f"consolidated_{periodo}.json"

        if not consolidated_path.exists():
            raise Exception(f"No se generó consolidated_{periodo}.json")

        # 6️⃣ manifest
        manifest = {
            "periodo": periodo,
            "sources": {
                "f931": bundle.f931,
                "borrador": bundle.borrador,
                "asiento": bundle.asiento,
            }
        }

        manifest_path = self.output_dir / f"sources_manifest_{periodo}.json"

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # 7️⃣ limpiar temp
        shutil.rmtree(periodo_input_dir)

    # -----------------------------------------------------
    # SCRIPT RUNNERS
    # -----------------------------------------------------

    def _run_parser(self, input_dir: Path):

        subprocess.run(
            [
                "python",
                "run_parser.py",
                "--input",
                str(input_dir),
                "--output",
                str(self.output_dir)
            ],
            check=True
        )

    def _run_normalizer(self):

        subprocess.run(
            [
                "python",
                "run_normalizer.py"
            ],
            check=True
        )

    def _run_consolidator(self):

        subprocess.run(
            [
                "python",
                "run_consolidator.py"
            ],
            check=True
        )

    # -----------------------------------------------------
    # HELPERS
    # -----------------------------------------------------

    def _clean_output_jsons(self):

        for file in self.output_dir.glob("*.json"):
            file.unlink()