import os
import json
from pathlib import Path

# Hardcodeado como venís usando
BASE_CONSOLIDATED = r"C:\Users\franl\Desktop\auditoria\proyecto\px_laboral_automation\output\consolidated_2025-05.json"
OUT_DIR = r"C:\Users\franl\Desktop\auditoria\proyecto\px_laboral_automation\output"


def main():
    base_path = Path(BASE_CONSOLIDATED)
    out_dir = Path(OUT_DIR)

    if not base_path.exists():
        raise FileNotFoundError(f"No existe: {base_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(base_path, "r", encoding="utf-8") as f:
        base = json.load(f)

    year = int(base["periodo_iso"].split("-")[0])

    created = 0
    for m in range(1, 13):
        periodo = f"{year}-{m:02d}"

        cloned = json.loads(json.dumps(base))  # deep copy simple
        cloned["periodo_iso"] = periodo

        out_file = out_dir / f"consolidated_{periodo}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(cloned, f, ensure_ascii=False, indent=2)

        created += 1
        print("✓ creado:", out_file.name)

    print(f"\nListo. Creados {created} consolidados en: {out_dir}")


if __name__ == "__main__":
    main()