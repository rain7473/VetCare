"""Repository de la tabla OWNERS."""

import oracledb

from models.owner import Owner

_OWNER_SELECT = """
    SELECT id, identification, first_name, last_name, phone, secondary_phone,
           email, address, notes, is_active, created_at, updated_at
    FROM owners
"""


def _row_to_owner(row: tuple) -> Owner:
    return Owner(
        id=row[0],
        identification=row[1],
        first_name=row[2],
        last_name=row[3],
        phone=row[4],
        secondary_phone=row[5],
        email=row[6],
        address=row[7],
        notes=row[8],
        is_active=bool(row[9]),
        created_at=row[10],
        updated_at=row[11],
    )


def list_owners(conn: oracledb.Connection) -> list[Owner]:
    """Todos los propietarios ordenados por apellido y nombre."""
    with conn.cursor() as cur:
        cur.execute(_OWNER_SELECT + " ORDER BY last_name, first_name")
        return [_row_to_owner(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, owner_id: int) -> Owner | None:
    with conn.cursor() as cur:
        cur.execute(_OWNER_SELECT + " WHERE id = :id", {"id": owner_id})
        row = cur.fetchone()
    return _row_to_owner(row) if row else None


def identification_exists(
    conn: oracledb.Connection, identification: str,
    exclude_owner_id: int | None = None,
) -> bool:
    sql = "SELECT COUNT(*) FROM owners WHERE LOWER(identification) = :ident"
    params: dict = {"ident": identification.lower()}
    if exclude_owner_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_owner_id
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0] > 0


def insert_owner(
    conn: oracledb.Connection,
    *,
    identification: str | None,
    first_name: str,
    last_name: str,
    phone: str,
    secondary_phone: str | None,
    email: str | None,
    address: str | None,
    notes: str | None,
) -> int:
    """Inserta un propietario y devuelve su ID. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO owners (
                identification, first_name, last_name, phone, secondary_phone,
                email, address, notes, is_active, created_at, updated_at
            ) VALUES (
                :identification, :first_name, :last_name, :phone,
                :secondary_phone, :email, :address, :notes, 1,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "identification": identification,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "secondary_phone": secondary_phone,
                "email": email,
                "address": address,
                "notes": notes,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def update_owner(
    conn: oracledb.Connection,
    owner_id: int,
    *,
    identification: str | None,
    first_name: str,
    last_name: str,
    phone: str,
    secondary_phone: str | None,
    email: str | None,
    address: str | None,
    notes: str | None,
    is_active: bool,
) -> None:
    """Actualiza un propietario. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE owners
            SET identification = :identification,
                first_name = :first_name,
                last_name = :last_name,
                phone = :phone,
                secondary_phone = :secondary_phone,
                email = :email,
                address = :address,
                notes = :notes,
                is_active = :is_active
            WHERE id = :id
            """,
            {
                "identification": identification,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "secondary_phone": secondary_phone,
                "email": email,
                "address": address,
                "notes": notes,
                "is_active": 1 if is_active else 0,
                "id": owner_id,
            },
        )


def set_active(conn: oracledb.Connection, owner_id: int, active: bool) -> None:
    """Activa o desactiva un propietario. No hace COMMIT."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE owners SET is_active = :active WHERE id = :id",
            {"active": 1 if active else 0, "id": owner_id},
        )
