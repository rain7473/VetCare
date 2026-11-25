"""Migración explícita del checkout actual: python -m scripts.apply_barcode_migration."""

from pathlib import Path

from database.connection import connection_scope


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "database/migrations/20261114_barcode_sales.sql"
    block = path.read_text(encoding="utf-8").rstrip().removesuffix("/").rstrip()
    with connection_scope(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(block)
    print("Migración de ventas aplicada; productos, códigos y ventas anteriores conservados.")


if __name__ == "__main__":
    main()
