"""Repository de HOSPITAL_AREAS, HOSPITAL_SPACES y HOSPITALIZATIONS."""

import oracledb

from models.hospitalization import HospitalArea, HospitalSpace, Hospitalization

_HOSP_SELECT = """
    SELECT h.id, h.pet_id, h.consultation_id, h.veterinarian_id, h.space_id,
           h.admitted_at, h.discharged_at, h.reason, h.treatment_plan,
           h.status, h.discharge_notes, h.created_at, h.updated_at,
           p.name AS pet_name,
           o.first_name || ' ' || o.last_name AS owner_name,
           v.full_name AS veterinarian_name,
           s.code AS space_code,
           a.name AS area_name
    FROM hospitalizations h
    JOIN pets p ON p.id = h.pet_id
    JOIN owners o ON o.id = p.owner_id
    JOIN users v ON v.id = h.veterinarian_id
    LEFT JOIN hospital_spaces s ON s.id = h.space_id
    LEFT JOIN hospital_areas a ON a.id = s.area_id
"""


def list_areas(conn: oracledb.Connection, only_active: bool = True) -> list[HospitalArea]:
    sql = "SELECT id, name, description, is_active FROM hospital_areas"
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            HospitalArea(id=r[0], name=r[1], description=r[2], is_active=bool(r[3]))
            for r in cur.fetchall()
        ]


def insert_area(
    conn: oracledb.Connection, *, name: str, description: str | None
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO hospital_areas (name, description, is_active)
            VALUES (:name, :description, 1)
            RETURNING id INTO :new_id
            """,
            {"name": name, "description": description, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def list_spaces(
    conn: oracledb.Connection,
    *,
    only_available: bool = False,
    only_active: bool = True,
) -> list[HospitalSpace]:
    sql = """
        SELECT s.id, s.area_id, s.code, s.description, s.status, s.is_active,
               a.name AS area_name
        FROM hospital_spaces s
        JOIN hospital_areas a ON a.id = s.area_id
        WHERE 1 = 1
    """
    if only_active:
        sql += " AND s.is_active = 1 AND a.is_active = 1"
    if only_available:
        sql += " AND s.status = 'AVAILABLE'"
    sql += " ORDER BY a.name, s.code"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [_row_to_space(row) for row in cur.fetchall()]


def get_space(conn: oracledb.Connection, space_id: int) -> HospitalSpace | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.area_id, s.code, s.description, s.status, s.is_active,
                   a.name AS area_name
            FROM hospital_spaces s
            JOIN hospital_areas a ON a.id = s.area_id
            WHERE s.id = :id
            """,
            {"id": space_id},
        )
        row = cur.fetchone()
    return _row_to_space(row) if row else None


def insert_space(
    conn: oracledb.Connection,
    *,
    area_id: int,
    code: str,
    description: str | None,
) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO hospital_spaces (
                area_id, code, description, status, is_active
            ) VALUES (
                :area_id, :code, :description, 'AVAILABLE', 1
            )
            RETURNING id INTO :new_id
            """,
            {
                "area_id": area_id,
                "code": code,
                "description": description,
                "new_id": new_id,
            },
        )
        return int(new_id.getvalue()[0])


def set_space_status(
    conn: oracledb.Connection, space_id: int, status: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE hospital_spaces SET status = :status WHERE id = :id",
            {"status": status, "id": space_id},
        )


def list_hospitalizations(
    conn: oracledb.Connection, *, active_only: bool = False
) -> list[Hospitalization]:
    sql = _HOSP_SELECT
    if active_only:
        sql += " WHERE h.status IN ('ADMITTED', 'OBSERVATION', 'CRITICAL')"
    sql += " ORDER BY h.admitted_at DESC"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [_row_to_hospitalization(row) for row in cur.fetchall()]


def get_by_id(conn: oracledb.Connection, hosp_id: int) -> Hospitalization | None:
    with conn.cursor() as cur:
        cur.execute(_HOSP_SELECT + " WHERE h.id = :id", {"id": hosp_id})
        row = cur.fetchone()
    return _row_to_hospitalization(row) if row else None


def count_active_for_pet(conn: oracledb.Connection, pet_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM hospitalizations
            WHERE pet_id = :pet_id
              AND status IN ('ADMITTED', 'OBSERVATION', 'CRITICAL')
            """,
            {"pet_id": pet_id},
        )
        return cur.fetchone()[0]


def insert_hospitalization(conn: oracledb.Connection, **fields) -> int:
    with conn.cursor() as cur:
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            """
            INSERT INTO hospitalizations (
                pet_id, consultation_id, veterinarian_id, space_id,
                admitted_at, reason, treatment_plan, status,
                created_at, updated_at
            ) VALUES (
                :pet_id, :consultation_id, :veterinarian_id, :space_id,
                :admitted_at, :reason, :treatment_plan, :status,
                SYSTIMESTAMP, SYSTIMESTAMP
            )
            RETURNING id INTO :new_id
            """,
            {**fields, "new_id": new_id},
        )
        return int(new_id.getvalue()[0])


def update_hospitalization(
    conn: oracledb.Connection,
    hosp_id: int,
    *,
    space_id: int | None,
    veterinarian_id: int,
    reason: str,
    treatment_plan: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE hospitalizations
            SET space_id = :space_id,
                veterinarian_id = :veterinarian_id,
                reason = :reason,
                treatment_plan = :treatment_plan
            WHERE id = :id
            """,
            {
                "space_id": space_id,
                "veterinarian_id": veterinarian_id,
                "reason": reason,
                "treatment_plan": treatment_plan,
                "id": hosp_id,
            },
        )


def set_status(
    conn: oracledb.Connection,
    hosp_id: int,
    *,
    status: str,
    discharge_notes: str | None = None,
    mark_discharged: bool = False,
) -> None:
    if mark_discharged:
        sql = """
            UPDATE hospitalizations
            SET status = :status,
                discharge_notes = :discharge_notes,
                discharged_at = SYSTIMESTAMP
            WHERE id = :id
        """
    else:
        sql = """
            UPDATE hospitalizations
            SET status = :status,
                discharge_notes = NVL(:discharge_notes, discharge_notes)
            WHERE id = :id
        """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "status": status,
                "discharge_notes": discharge_notes,
                "id": hosp_id,
            },
        )


def _row_to_space(row: tuple) -> HospitalSpace:
    return HospitalSpace(
        id=row[0],
        area_id=row[1],
        code=row[2],
        description=row[3],
        status=row[4],
        is_active=bool(row[5]),
        area_name=row[6],
    )


def _row_to_hospitalization(row: tuple) -> Hospitalization:
    return Hospitalization(
        id=row[0],
        pet_id=row[1],
        consultation_id=row[2],
        veterinarian_id=row[3],
        space_id=row[4],
        admitted_at=row[5],
        discharged_at=row[6],
        reason=row[7],
        treatment_plan=row[8],
        status=row[9],
        discharge_notes=row[10],
        created_at=row[11],
        updated_at=row[12],
        pet_name=row[13],
        owner_name=row[14],
        veterinarian_name=row[15],
        space_code=row[16],
        area_name=row[17],
    )
