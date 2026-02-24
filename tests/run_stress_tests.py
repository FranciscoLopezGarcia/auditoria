import os
import shutil
import random
import subprocess
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEST_RUNTIME = PROJECT_ROOT / "test_runtime"
TEST_INPUT = TEST_RUNTIME / "temp_inputs"
TEST_OUTPUT = TEST_RUNTIME / "output"

BASE_TEST_PDFS = PROJECT_ROOT / "base_test_pdfs"


def reset_test_environment():
    if TEST_RUNTIME.exists():
        shutil.rmtree(TEST_RUNTIME)

    TEST_INPUT.mkdir(parents=True)
    TEST_OUTPUT.mkdir(parents=True)


def copy_base_pdfs():
    for file in BASE_TEST_PDFS.glob("*.pdf"):
        shutil.copy(file, TEST_INPUT / file.name)


def simulate_missing_pdf():
    files = list(TEST_INPUT.glob("*.pdf"))
    if files:
        os.remove(random.choice(files))
        print("⚠ Simulado: faltante de PDF")


def simulate_wrong_name():
    files = list(TEST_INPUT.glob("*.pdf"))
    if files:
        file = random.choice(files)
        file.rename(TEST_INPUT / ("WRONG_" + file.name))
        print("⚠ Simulado: nombre incorrecto")


def simulate_duplicate():
    files = list(TEST_INPUT.glob("*.pdf"))
    if files:
        file = random.choice(files)
        shutil.copy(file, TEST_INPUT / ("DUP_" + file.name))
        print("⚠ Simulado: duplicado")


def run_pipeline():
    print("\n🚀 Ejecutando Orchestrator_A")

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "run_orchestrator_a.py"),
            "--input", str(TEST_INPUT),
            "--output", str(TEST_OUTPUT),
        ],
        check=False
    )

    print("\n🚀 Ejecutando Orchestrator_B")

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "run_orchestrator_b.py"),
            "--output", str(TEST_OUTPUT),
        ],
        check=False
    )


def main():

    print("\n========== TEST STRESS ==========")

    reset_test_environment()
    copy_base_pdfs()

    simulate_missing_pdf()
    simulate_wrong_name()
    simulate_duplicate()

    run_pipeline()

    print("\n========== FIN TEST ==========")


if __name__ == "__main__":
    main()