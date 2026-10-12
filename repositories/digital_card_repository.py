"""Repository de PET_DIGITAL_CARDS."""

import oracledb

from models.digital_card import PetDigitalCard


def get_active_for_pet(
    conn: oracledb.Connection, pet_id: int
) -> PetDigitalCard | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.pet_id, RAWTOHEX(c.public_token), c.issued_at,
                   c.expires_at, c.is_active, c.created_by, p.name
            FROM pet_digital_cards c
            JOIN pets p ON p.id = c.pet_id
            WHERE c.pet_id = :pet_id AND c.is_active = 1
            ORDER BY c.issued_at DESC
            FETCH FIRST 1 ROWS ONLY
            """,
            {"pet_id": pet_id},
        )
        row = cur.fetchone()
    return _row_to_card(row) if row else None


def deactivate_for_pet(conn: oracledb.Connection, pet_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pet_digital_cards
            SET is_active = 0
            WHERE pet_id = :pet_id AND is_active = 1
            """,
            {"pet_id": pet_id},
        )


def insert_card(
    conn: oracledb.Connection, *, pet_id: int, created_by: int | None
) -> PetDigitalCard:
    """Emite un carné con token público SYS_GUID(). No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO pet_digital_cards (
                pet_id, public_token, issued_at, is_active, created_by
            ) VALUES (
                :pet_id, SYS_GUID(), SYSTIMESTAMP, 1, :created_by
            )
            RETURNING id INTO :new_id
            """,
            {
                "pet_id": pet_id,
                "created_by": created_by,
                "new_id": new_id,
            },
        )
        value = new_id.getvalue()
        card_id = int(value[0] if isinstance(value, (list, tuple)) else value)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.pet_id, RAWTOHEX(c.public_token), c.issued_at,
                   c.expires_at, c.is_active, c.created_by, p.name
            FROM pet_digital_cards c
            JOIN pets p ON p.id = c.pet_id
            WHERE c.id = :id
            """,
            {"id": card_id},
        )
        row = cur.fetchone()
    return _row_to_card(row)


def _row_to_card(row: tuple) -> PetDigitalCard:
    return PetDigitalCard(
        id=row[0],
        pet_id=row[1],
        public_token_hex=row[2],
        issued_at=row[3],
        expires_at=row[4],
        is_active=bool(row[5]),
        created_by=row[6],
        pet_name=row[7],
    )
