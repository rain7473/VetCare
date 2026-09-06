"""Inspector de esquema Oracle (SOLO LECTURA).

Herramienta de desarrollo para consultar el diccionario de datos antes
de implementar cada módulo, como exige la metodología del proyecto.
No ejecuta DML ni DDL: únicamente SELECT sobre vistas del diccionario
y, opcionalmente, sobre la tabla indicada para ver filas de ejemplo.

Uso:
    python -m database.schema_inspector TABLA [TABLA...] [--rows N]
"""

import argparse

from database.connection import connection_scope

_VALID_TABLE_SQL = "SELECT COUNT(*) FROM user_tables WHERE table_name = :name"


def _print_section(title: str) -> None:
    print(f"\n--- {title} ---")


def inspect_table(cur, table: str, rows: int) -> None:
    table = table.upper()
    cur.execute(_VALID_TABLE_SQL, {"name": table})
    if cur.fetchone()[0] == 0:
        print(f"\n=== {table}: NO EXISTE ===")
        return

    print(f"\n=== {table} ===")

    _print_section("Columnas")
    cur.execute(
        """
        SELECT column_name, data_type, data_length, nullable, identity_column
        FROM user_tab_columns WHERE table_name = :t ORDER BY column_id
        """,
        {"t": table},
    )
    for name, dtype, length, nullable, identity in cur.fetchall():
        extra = " IDENTITY" if identity == "YES" else ""
        null = "NULL" if nullable == "Y" else "NOT NULL"
        print(f"  {name}  {dtype}({length})  {null}{extra}")

    _print_section("Constraints")
    cur.execute(
        """
        SELECT c.constraint_name, c.constraint_type,
               LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position),
               c.search_condition_vc
        FROM user_constraints c
        LEFT JOIN user_cons_columns cc ON cc.constraint_name = c.constraint_name
        WHERE c.table_name = :t
        GROUP BY c.constraint_name, c.constraint_type, c.search_condition_vc
        ORDER BY c.constraint_type, c.constraint_name
        """,
        {"t": table},
    )
    for name, ctype, cols, cond in cur.fetchall():
        detail = cond if cond else cols
        print(f"  [{ctype}] {name}: {detail}")

    _print_section("Triggers")
    cur.execute(
        """
        SELECT trigger_name, trigger_type, triggering_event, status
        FROM user_triggers WHERE table_name = :t
        """,
        {"t": table},
    )
    triggers = cur.fetchall()
    if not triggers:
        print("  (ninguno)")
    for name, ttype, event, status in triggers:
        print(f"  {name}: {ttype} {event} [{status}]")

    if rows > 0:
        _print_section(f"Primeras {rows} filas")
        cur.execute(f"SELECT * FROM {table} FETCH FIRST {rows} ROWS ONLY")  # noqa: S608
        cols = [d[0] for d in cur.description]
        print("  " + " | ".join(cols))
        fetched = cur.fetchall()
        if not fetched:
            print("  (sin datos)")
        for row in fetched:
            print("  " + " | ".join(str(v)[:48] for v in row))

    _print_section("Total de filas")
    cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    print(f"  {cur.fetchone()[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", nargs="+", help="Tablas a inspeccionar")
    parser.add_argument("--rows", type=int, default=10, help="Filas de ejemplo")
    args = parser.parse_args()

    with connection_scope() as conn:
        with conn.cursor() as cur:
            for table in args.tables:
                inspect_table(cur, table, args.rows)


if __name__ == "__main__":
    main()
