"""Repository de CLINICAL_AMENDMENTS (append-only en Oracle)."""

import oracledb

from models.amendment import ClinicalAmendment


def list_by_consultation(
    conn: oracledb.Connection, consultation_id: int
) -> list[ClinicalAmendment]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.consultation_id, a.created_by, a.reason,
                   a.amendment_text, a.amendment_hash, a.created_at,
                   u.full_name
            FROM clinical_amendments a
            JOIN users u ON u.id = a.created_by
            WHERE a.consultation_id = :cid
            ORDER BY a.created_at
            """,
            {"cid": consultation_id},
        )
        return [
            ClinicalAmendment(
                id=row[0],
                consultation_id=row[1],
                created_by=row[2],
                reason=row[3],
                amendment_text=row[4],
                amendment_hash=row[5],
                created_at=row[6],
                created_by_name=row[7],
            )
            for row in cur.fetchall()
        ]


def oracle_sha256(conn: oracledb.Connection, payload: str) -> str:
    """SHA-256 vía DBMS_CRYPTO (misma familia que el sellado de consultas)."""
    with conn.cursor() as cur:
        result = cur.var(oracledb.DB_TYPE_VARCHAR)
        cur.execute(
            """
            DECLARE
                v_raw RAW(32);
            BEGIN
                v_raw := DBMS_CRYPTO.HASH(
                    UTL_I18N.STRING_TO_RAW(:payload, 'AL32UTF8'),
                    DBMS_CRYPTO.HASH_SH256
                );
                :result := LOWER(RAWTOHEX(v_raw));
            END;
            """,
            {"payload": payload, "result": result},
        )
        return result.getvalue()


def insert_amendment(
    conn: oracledb.Connection,
    *,
    consultation_id: int,
    created_by: int,
    reason: str,
    amendment_text: str,
    amendment_hash: str,
) -> int:
    """Inserta una enmienda inmutable. No hace COMMIT."""
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO clinical_amendments (
                consultation_id, created_by, reason, amendment_text,
                amendment_hash, created_at
            ) VALUES (
                :consultation_id, :created_by, :reason, :amendment_text,
                :amendment_hash, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {
                "consultation_id": consultation_id,
                "created_by": created_by,
                "reason": reason,
                "amendment_text": amendment_text,
                "amendment_hash": amendment_hash,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])
