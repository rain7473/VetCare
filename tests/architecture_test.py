"""Controles estáticos de arquitectura y manejo de secretos de VetCare."""

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NON_SQL_LAYERS = ("views", "services", "widgets", "models", "utils", "config")
SQL_CALLS = {"execute", "executemany", "callfunc", "callproc"}


def _sql_calls_outside_repository() -> list[str]:
    violations: list[str] = []
    for folder in NON_SQL_LAYERS:
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in SQL_CALLS
                ):
                    relative = path.relative_to(ROOT)
                    violations.append(f"{relative}:{node.lineno} ({node.func.attr})")
    return violations


def run() -> int:
    from services.permission_service import MODULE_PERMISSIONS
    from widgets.sidebar import NAV_ITEMS

    results: dict[str, bool] = {}
    violations = _sql_calls_outside_repository()
    results["SQL confinado a repositories/database"] = not violations
    if violations:
        print("  SQL fuera de la capa permitida: " + ", ".join(violations))

    nav_keys = {key for key, _icon, _label in NAV_ITEMS}
    results["Sidebar y permisos tienen las mismas claves"] = (
        nav_keys == set(MODULE_PERMISSIONS)
    )

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    results[".env está ignorado"] = ".env" in {line.strip() for line in gitignore}
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    results[".env no está versionado"] = tracked.returncode != 0

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    results[".env.example no contiene contraseña"] = "DB_PASSWORD=" in example and not any(
        line.startswith("DB_PASSWORD=") and line != "DB_PASSWORD="
        for line in example.splitlines()
    )

    production_subprocesses = []
    for folder in NON_SQL_LAYERS:
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names]
                    module = getattr(node, "module", "") or ""
                    if module == "subprocess" or "subprocess" in names:
                        production_subprocesses.append(str(path.relative_to(ROOT)))
    results["La aplicación no lanza procesos de consola"] = not production_subprocesses

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    local_links = [
        target
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        if not target.startswith(("http://", "https://", "#"))
    ]
    results["Enlaces locales del README válidos"] = all(
        (ROOT / target).exists() for target in local_links
    )
    results["Documentación marca objetivo 25 completo"] = (
        "| 25 | Documentación técnica y de usuario ✅ |" in readme
    )

    failures = [name for name, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")
    if failures:
        print(f"\nPruebas FALLIDAS: {len(failures)} de {len(results)}.")
        return 1
    print(f"\nTodas las pruebas superadas ({len(results)}).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
