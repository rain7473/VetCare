"""Consultas de solo lectura para el dashboard por rol."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import oracledb

from models.dashboard import DashboardItem
from config.constants import APPOINTMENT_STATUS_DISPLAY


def begin_snapshot(conn):
    """Lectura consistente y fechas locales de Panamá; no modifica el esquema."""
    conn.call_timeout = 15000
    with conn.cursor() as cur:
        cur.execute("ALTER SESSION SET TIME_ZONE = '-05:00'")
        cur.execute("SET TRANSACTION READ ONLY")


def _scalar(conn: oracledb.Connection, sql: str, params: dict | None = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        row = cur.fetchone()
    return row[0] if row else 0


def count_active_pets(conn: oracledb.Connection) -> int:
    return int(_scalar(conn, "SELECT COUNT(*) FROM pets WHERE status = 'ACTIVE'"))


def count_appointments_today(conn: oracledb.Connection, day: date) -> int:
    return int(_scalar(conn, """
        SELECT COUNT(*) FROM appointments
        WHERE appointment_at >= :day AND appointment_at < :day + 1
          AND status NOT IN ('CANCELLED', 'NO_SHOW')
    """, {"day": day}))


def count_active_hospitalizations(
    conn: oracledb.Connection, veterinarian_id: int | None = None
) -> int:
    sql = """
        SELECT COUNT(*) FROM hospitalizations
        WHERE status IN ('ADMITTED', 'OBSERVATION', 'CRITICAL')
    """
    params: dict = {}
    if veterinarian_id is not None:
        sql += " AND veterinarian_id = :veterinarian_id"
        params["veterinarian_id"] = veterinarian_id
    return int(_scalar(conn, sql, params))


def count_open_alerts(
    conn: oracledb.Connection, veterinarian_id: int | None = None
) -> int:
    sql = """
        SELECT COUNT(DISTINCT a.id)
        FROM clinical_alerts a
        LEFT JOIN hospitalizations h ON h.id = a.hospitalization_id
        WHERE a.status IN ('OPEN', 'ACKNOWLEDGED')
    """
    params: dict = {}
    if veterinarian_id is not None:
        sql += " AND h.veterinarian_id = :veterinarian_id"
        params["veterinarian_id"] = veterinarian_id
    return int(_scalar(conn, sql, params))


def count_low_stock_products(conn: oracledb.Connection) -> int:
    return int(_scalar(conn, """
        SELECT COUNT(*)
        FROM products p
        WHERE p.is_active = 1
          AND NVL((
              SELECT SUM(l.quantity_available)
              FROM inventory_lots l
              WHERE l.product_id = p.id
          ), 0) <= p.minimum_stock
    """))


def count_expiring_lots(
    conn: oracledb.Connection, start_day: date, end_day: date
) -> int:
    return int(_scalar(conn, """
        SELECT COUNT(*)
        FROM inventory_lots
        WHERE quantity_available > 0
          AND expiry_date >= :start_day AND expiry_date < :end_day
    """, {"start_day": start_day, "end_day": end_day + timedelta(days=1)}))


def count_active_products(conn: oracledb.Connection) -> int:
    return int(_scalar(conn, "SELECT COUNT(*) FROM products WHERE is_active = 1"))


def count_active_users(conn: oracledb.Connection) -> int:
    return int(_scalar(conn, "SELECT COUNT(*) FROM users WHERE is_active = 1"))


def count_waiting_patients(conn: oracledb.Connection, day: date) -> int:
    return int(_scalar(conn, """
        SELECT COUNT(*) FROM appointments
        WHERE appointment_at >= :day AND appointment_at < :day + 1 AND status = 'IN_ATTENTION'
    """, {"day": day}))


def count_triages_today(conn: oracledb.Connection, day: date) -> int:
    return int(_scalar(
        conn,
        "SELECT COUNT(*) FROM triages WHERE created_at >= :day AND created_at < :day + 1",
        {"day": day},
    ))


def count_upcoming_appointments(
    conn: oracledb.Connection,
    start_at: datetime,
    end_at: datetime,
    veterinarian_id: int | None = None,
) -> int:
    sql = """
        SELECT COUNT(*) FROM appointments
        WHERE appointment_at >= :start_at AND appointment_at < :end_at
          AND status IN ('SCHEDULED', 'CONFIRMED', 'IN_ATTENTION')
    """
    params: dict = {"start_at": start_at, "end_at": end_at}
    if veterinarian_id is not None:
        sql += " AND veterinarian_id = :veterinarian_id"
        params["veterinarian_id"] = veterinarian_id
    return int(_scalar(conn, sql, params))


def list_alerts_and_triage(
    conn: oracledb.Connection,
    day: date,
    veterinarian_id: int | None = None,
    limit: int = 6,
    *, clinical: bool = True, triage: bool = True,
) -> list[DashboardItem]:
    params: dict = {"day": day, "limit": limit}
    vet_alert = "" if clinical else "AND 1 = 0"
    vet_triage = "" if triage else "AND 1 = 0"
    if veterinarian_id is not None:
        vet_alert += " AND h.veterinarian_id = :veterinarian_id"
        vet_triage += " AND ap.veterinarian_id = :veterinarian_id"
        params["veterinarian_id"] = veterinarian_id
    sql = f"""
        SELECT title, detail, occurred_at, severity, module
        FROM (
            SELECT 'Alerta · ' || p.name AS title,
                   DBMS_LOB.SUBSTR(a.message, 500, 1) AS detail,
                   a.created_at AS occurred_at,
                   a.severity AS severity, 'hospitalization' AS module
            FROM clinical_alerts a
            JOIN pets p ON p.id = a.pet_id
            LEFT JOIN hospitalizations h ON h.id = a.hospitalization_id
            WHERE a.status IN ('OPEN', 'ACKNOWLEDGED')
              {vet_alert}
            UNION ALL
            SELECT 'Triaje P' || t.priority_level || ' · ' || p.name AS title,
                   DBMS_LOB.SUBSTR(t.reason, 500, 1) AS detail,
                   t.created_at AS occurred_at,
                   CASE t.priority_level
                       WHEN 1 THEN 'CRITICAL'
                       WHEN 2 THEN 'HIGH'
                       WHEN 3 THEN 'MEDIUM'
                       ELSE 'LOW'
                   END AS severity, 'triage' AS module
            FROM triages t
            JOIN pets p ON p.id = t.pet_id
            LEFT JOIN appointments ap ON ap.id = t.appointment_id
            WHERE t.created_at >= :day AND t.created_at < :day + 1
              AND t.priority_level <= 2
              AND NOT EXISTS (SELECT 1 FROM consultations c WHERE c.triage_id = t.id)
              AND (ap.id IS NULL OR ap.status IN ('SCHEDULED','CONFIRMED','IN_ATTENTION'))
              {vet_triage}
        )
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                 WHEN 'MEDIUM' THEN 3 ELSE 4 END, occurred_at DESC
        FETCH FIRST :limit ROWS ONLY
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [DashboardItem(*r) for r in cur.fetchall()]


def list_weekly_appointments(
    conn: oracledb.Connection,
    start_at: datetime,
    end_at: datetime,
    veterinarian_id: int | None = None,
    limit: int = 7,
) -> list[DashboardItem]:
    sql = """
        SELECT p.name, a.appointment_at AT TIME ZONE '-05:00', a.status, u.full_name,
               o.first_name || ' ' || o.last_name
        FROM appointments a
        JOIN pets p ON p.id = a.pet_id
        JOIN owners o ON o.id = p.owner_id
        LEFT JOIN users u ON u.id = a.veterinarian_id
        WHERE a.appointment_at >= :start_at AND a.appointment_at < :end_at
          AND a.status IN ('SCHEDULED', 'CONFIRMED', 'IN_ATTENTION')
    """
    params: dict = {"start_at": start_at, "end_at": end_at, "limit": limit}
    if veterinarian_id is not None:
        sql += " AND a.veterinarian_id = :veterinarian_id"
        params["veterinarian_id"] = veterinarian_id
    sql += " ORDER BY a.appointment_at FETCH FIRST :limit ROWS ONLY"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [DashboardItem(
            title=f"{row[0]} · {APPOINTMENT_STATUS_DISPLAY.get(row[2], row[2])}",
            detail=f"Propietario: {row[4]} · Veterinario: {row[3] or 'Sin asignar'}",
            occurred_at=row[1],
            module="appointments",
        ) for row in cur.fetchall()]


def period_summary(conn, kind, period, user_id=None):
    """Solo identificadores definidos aquí; valores externos siempre enlazados."""
    table, stamp, aggregate, predicate, owner = {
        "consultations": ("consultations", "started_at", "COUNT(*)", "1=1", "veterinarian_id"),
        "sales": ("sales", "sold_at", "NVL(SUM(total),0)", "status='COMPLETED'", "sold_by"),
    }[kind]
    sql = f"SELECT {aggregate} FROM {table} WHERE {predicate} AND {stamp} >= :start_at AND {stamp} < :end_at"
    params = {"start_at": period.start, "end_at": period.end + timedelta(days=1)}
    if user_id is not None:
        sql += f" AND {owner} = :user_id"
        params["user_id"] = user_id
    return Decimal(str(_scalar(conn, sql, params)))


def monthly_totals(conn, kind, start, end, user_id=None):
    table, stamp, aggregate, predicate, owner = {
        "consultations": ("consultations", "started_at", "COUNT(*)", "1=1", "veterinarian_id"),
        "sales": ("sales", "sold_at", "SUM(total)", "status='COMPLETED'", "sold_by"),
    }[kind]
    month = f"TO_CHAR({stamp} AT TIME ZONE '-05:00', 'YYYY-MM')"
    sql = f"SELECT {month}, {aggregate} FROM {table} WHERE {predicate} AND {stamp} >= :start_at AND {stamp} < :end_at"
    params = {"start_at": start, "end_at": end + timedelta(days=1)}
    if user_id is not None:
        sql += f" AND {owner} = :user_id"
        params["user_id"] = user_id
    sql += f" GROUP BY {month} ORDER BY 1"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return {r[0]: float(r[1]) for r in cur.fetchall()}


def species_distribution(conn, veterinarian_id=None):
    sql = """SELECT s.name, COUNT(*) FROM pets p
             JOIN species s ON s.id=p.species_id WHERE p.status='ACTIVE'"""
    params = {}
    if veterinarian_id is not None:
        sql += """ AND (EXISTS (SELECT 1 FROM consultations c WHERE c.pet_id=p.id AND c.veterinarian_id=:vet)
                    OR EXISTS (SELECT 1 FROM appointments a WHERE a.pet_id=p.id AND a.veterinarian_id=:vet))"""
        params["vet"] = veterinarian_id
    sql += " GROUP BY s.name ORDER BY COUNT(*) DESC, s.name"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def appointment_states(conn, period, veterinarian_id=None):
    sql = """SELECT status, COUNT(*) FROM appointments
             WHERE appointment_at >= :start_at AND appointment_at < :end_at"""
    params = {"start_at": period.start, "end_at": period.end + timedelta(days=1)}
    if veterinarian_id is not None:
        sql += " AND veterinarian_id=:vet"
        params["vet"] = veterinarian_id
    sql += " GROUP BY status ORDER BY status"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [(APPOINTMENT_STATUS_DISPLAY.get(r[0], r[0]), r[1]) for r in cur.fetchall()]


def pending_vaccines(conn, end, veterinarian_id=None):
    # Solo la aplicación más reciente de cada vacuna por mascota genera pendientes.
    sql = """SELECT COUNT(*) FROM (
        SELECT v.*, ROW_NUMBER() OVER (
            PARTITION BY v.pet_id,v.vaccine_id ORDER BY v.applied_at DESC,v.id DESC) rn
        FROM pet_vaccinations v JOIN pets p ON p.id=v.pet_id WHERE p.status='ACTIVE'
    ) v WHERE rn=1 AND next_due_date < :end_at"""
    params = {"end_at": end + timedelta(days=1)}
    if veterinarian_id is not None:
        sql += " AND v.applied_by=:vet"
        params["vet"] = veterinarian_id
    return int(_scalar(conn, sql, params))


def inventory_alerts(conn, today, end):
    with conn.cursor() as cur:
        cur.execute("""SELECT p.name, l.lot_number, l.expiry_date
            FROM inventory_lots l JOIN products p ON p.id=l.product_id
            WHERE l.quantity_available>0 AND l.expiry_date < :end_at
            AND p.is_active=1 ORDER BY l.expiry_date, l.id FETCH FIRST 5 ROWS ONLY
        """, {"end_at": end + timedelta(days=1)})
        result = [DashboardItem(
            f"{'Vencido' if r[2].date() < today else 'Próximo a vencer'} · {r[0]}",
            f"Lote {r[1] or 'Sin registrar'} · Vence {r[2]:%d/%m/%Y}",
            severity="HIGH" if r[2].date() < today else "MEDIUM", module="inventory",
        ) for r in cur.fetchall()]
        cur.execute("""SELECT p.name, NVL(SUM(l.quantity_available),0), p.minimum_stock
            FROM products p LEFT JOIN inventory_lots l ON l.product_id=p.id
            WHERE p.is_active=1 GROUP BY p.id,p.name,p.minimum_stock
            HAVING NVL(SUM(l.quantity_available),0)<=p.minimum_stock
            ORDER BY 2, p.name FETCH FIRST 5 ROWS ONLY""")
        result.extend(DashboardItem(f"Stock bajo · {r[0]}", f"Disponible: {r[1]} · Mínimo: {r[2]}",
                                   severity="HIGH" if r[1] == 0 else "MEDIUM", module="inventory")
                      for r in cur.fetchall())
    return result


def recent_activity(conn, period, *, audit=False, user_id=None):
    """Cinco eventos auditados; sin acceso a auditoría, solo eventos propios."""
    sql = """SELECT a.entity_type,a.action,a.entity_id,a.created_at AT TIME ZONE '-05:00',u.full_name
        FROM audit_log a LEFT JOIN users u ON u.id=a.user_id
        WHERE a.created_at>=:start_at AND a.created_at<:end_at"""
    params = {"start_at": period.start, "end_at": period.end + timedelta(days=1)}
    if not audit:
        sql += " AND a.user_id=:user_id"
        params["user_id"] = user_id
    sql += " ORDER BY a.created_at DESC,a.id DESC FETCH FIRST 5 ROWS ONLY"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [DashboardItem(f"{r[1]} · {r[0]}",
                              f"{r[4] or 'Sistema'}" + (f" · Registro #{r[2]}" if r[2] is not None else ""),
                              r[3], module="audit" if audit else "") for r in cur.fetchall()]

