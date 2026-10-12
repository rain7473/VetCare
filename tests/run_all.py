"""Runner aislado de la suite completa de VetCare.

Uso:
    python -m tests.run_all
    python -m tests.run_all --fail-fast
"""

import argparse
import os
import subprocess
import sys
import time


TEST_MODULES = (
    "tests.icons_test",
    "tests.architecture_test",
    "tests.db_health_test",
    "tests.bootstrap_test",
    "tests.auth_test",
    "tests.permissions_test",
    "tests.owners_test",
    "tests.pets_test",
    "tests.pet_profile_test",
    "tests.appointments_test",
    "tests.triage_test",
    "tests.consultations_test",
    "tests.pharmacology_test",
    "tests.surgery_test",
    "tests.vaccines_test",
    "tests.hospitalization_test",
    "tests.monitoring_test",
    "tests.integrity_test",
    "tests.digital_card_test",
    "tests.inventory_test",
    "tests.barcode_test",
    "tests.dynamic_selector_test",
    "tests.sales_test",
    "tests.dashboard_test",
    "tests.audit_test",
    "tests.general_test",
    "tests.smoke_test",
)


def run(*, fail_fast: bool = False) -> int:
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    outcomes: list[tuple[str, bool, float]] = []

    for module in TEST_MODULES:
        print(f"\n=== {module} ===", flush=True)
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-m", module],
            env=env,
            check=False,
        )
        elapsed = time.monotonic() - started
        passed = completed.returncode == 0
        outcomes.append((module, passed, elapsed))
        if fail_fast and not passed:
            break

    print("\n=== RESUMEN GENERAL ===")
    for module, passed, elapsed in outcomes:
        print(f"  [{'OK' if passed else 'FALLO'}] {module} ({elapsed:.1f}s)")
    failures = [module for module, passed, _elapsed in outcomes if not passed]
    if failures:
        print(f"\nSuite FALLIDA: {len(failures)} módulo(s) con errores.")
        return 1
    print(f"\nSuite superada: {len(outcomes)} módulos sin errores.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()
    return run(fail_fast=args.fail_fast)


if __name__ == "__main__":
    sys.exit(main())

