"""Dashboard de solo lectura, con autorización y agregados por período."""

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from database.connection import connection_scope
from models.dashboard import DashboardMetric, DashboardPeriod, DashboardSeries, DashboardSnapshot
from models.user import User
from repositories import dashboard_repository as repo
from services import permission_service, session

PANAMA = timezone(timedelta(hours=-5))
ROLE_MODULES = {
    "ADMIN": frozenset(permission_service.MODULE_PERMISSIONS),
    "RECEPTION": frozenset({"pets", "appointments", "triage"}),
    "VETERINARIAN": frozenset({"pets", "appointments", "consultations", "hospitalization", "vaccines", "triage"}),
    "SALES": frozenset({"sales", "inventory"}),
}
MONTHS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def resolve_period(key: str, today: date | None = None, start=None, end=None):
    today = today or datetime.now(PANAMA).date()
    if key == "custom":
        if start is None or end is None:
            raise ValueError("Seleccione ambas fechas.")
        if end > today:
            raise ValueError("El período estadístico no puede terminar en el futuro.")
        return DashboardPeriod(start, end, "Rango personalizado")
    first, label = {
        "today": (today, "Hoy"),
        "7d": (today - timedelta(days=6), "Últimos 7 días"),
        "30d": (today - timedelta(days=29), "Últimos 30 días"),
        "month": (today.replace(day=1), "Este mes"),
    }[key]
    return DashboardPeriod(first, today, label)


def shift_month(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def comparison_text(value, previous):
    if previous == 0:
        return "Sin actividad previa" if value == 0 else "Sin base previa para calcular %"
    return f"{(value - previous) / previous * 100:+.1f}% vs. período anterior"


def _series(conn, kind, period, scoped_id=None):
    # Seis meses de contexto; un rango más amplio conserva todos sus meses.
    start = min(shift_month(period.end.replace(day=1), -5), period.start.replace(day=1))
    months = []
    cursor = start
    while cursor <= period.end:
        months.append(cursor)
        cursor = shift_month(cursor, 1)
    history = repo.monthly_totals(conn, kind, start, period.end, scoped_id)
    selected = repo.monthly_totals(conn, kind, period.start, period.end, scoped_id)
    previous = repo.monthly_totals(conn, kind, shift_month(start, -12), shift_month(period.end, -12), scoped_id) if kind == "sales" else {}
    return DashboardSeries(
        tuple(f"{MONTHS[m.month-1]} {m.year % 100:02d}" for m in months),
        tuple(history.get(f"{m:%Y-%m}", 0) for m in months),
        tuple(selected.get(f"{m:%Y-%m}", 0) for m in months),
        tuple(previous.get(f"{shift_month(m, -12):%Y-%m}", 0) for m in months) if kind == "sales" else (),
    )


def load_dashboard(user: User, now: datetime | None = None, *, period: DashboardPeriod | None = None) -> DashboardSnapshot:
    current_user = session.get_current_user()
    if current_user != user or not user.is_active or user.role_name not in ROLE_MODULES:
        raise permission_service.PermissionDeniedError("DASHBOARD_SESSION")
    permissions = session.get_permissions()
    allowed = {module for module in ROLE_MODULES[user.role_name]
               if any(code in permissions for code in permission_service.MODULE_PERMISSIONS[module])}
    current = now or datetime.now(PANAMA)
    if current.tzinfo:
        current = current.astimezone(PANAMA).replace(tzinfo=None)
    today = current.date()
    period = period or resolve_period("month", today)
    vet_id = user.id if user.role_name == "VETERINARIAN" else None
    sale_id = user.id if user.role_name == "SALES" else None
    metrics = []

    def metric(key, title, value, icon, module, detail="Estado actual"):
        metrics.append(DashboardMetric(key, title, str(value), icon, detail, module))

    with connection_scope() as conn:
        repo.begin_snapshot(conn)
        if "pets" in allowed and vet_id is None:
            metric("pets", "Mascotas activas", repo.count_active_pets(conn), "pets", "pets")
        if "appointments" in allowed:
            count = repo.count_appointments_today(conn, today) if vet_id is None else repo.count_upcoming_appointments(conn, today, today + timedelta(days=1), vet_id)
            metric("appointments", "Mis citas de hoy" if vet_id else "Citas de hoy", count, "appointments", "appointments", "Hoy · excluye canceladas y ausencias" if vet_id is None else "Hoy · pendientes asignadas")
        if "hospitalization" in allowed:
            metric("hospitalized", "Mis hospitalizados" if vet_id else "Hospitalizados", repo.count_active_hospitalizations(conn, vet_id), "hospitalization", "hospitalization")
            metric("alerts", "Alertas asignadas" if vet_id else "Alertas abiertas", repo.count_open_alerts(conn, vet_id), "warning", "hospitalization", "Abiertas o reconocidas")
        if "inventory" in allowed:
            metric("low_stock", "Productos con stock bajo", repo.count_low_stock_products(conn), "inventory", "inventory", "Disponible ≤ stock mínimo")
            metric("expiring", "Próximos vencimientos", repo.count_expiring_lots(conn, today, today + timedelta(days=30)), "expiring", "inventory", "Lotes con stock · próximos 30 días")
            if user.role_name == "SALES":
                metric("products", "Productos activos", repo.count_active_products(conn), "products", "inventory")
        if "sales" in allowed:
            total = repo.period_summary(conn, "sales", DashboardPeriod(today, today), sale_id)
            metric("sales", "Mis ventas de hoy" if sale_id else "Ventas de hoy", f"${total:,.2f}", "sales", "sales", "Ventas completadas · USD")
        if "users" in allowed:
            metric("users", "Usuarios activos", repo.count_active_users(conn), "users", "users")
        if user.role_name == "RECEPTION":
            if "appointments" in allowed:
                metric("waiting", "Pacientes esperando", repo.count_waiting_patients(conn, today), "waiting", "appointments", "Citas de hoy en atención")
                metric("upcoming", "Próximas citas", repo.count_upcoming_appointments(conn, current, today + timedelta(days=7)), "followup", "appointments", "Desde ahora · próximos 7 días")
            if "triage" in allowed:
                metric("triages", "Triajes de hoy", repo.count_triages_today(conn, today), "triage", "triage", "Registrados hoy")
        consultations = revenue = species = states = None
        for module, kind, key, title, scoped_id in (
            ("consultations", "consultations", "period_consultations", "Consultas", vet_id),
            ("sales", "sales", "period_revenue", "Ingresos", sale_id),
        ):
            if module not in allowed:
                continue
            value = repo.period_summary(conn, kind, period, scoped_id)
            previous = repo.period_summary(conn, kind, period.previous, scoped_id)
            caption = f"{title} del mes" if period.label == "Este mes" else f"{title} del período"
            metric(key, caption, f"${value:,.2f}" if kind == "sales" else int(value), module, module, comparison_text(value, previous))
            chart = _series(conn, kind, period, scoped_id)
            if kind == "sales":
                revenue = chart
            else:
                consultations = chart
        if "vaccines" in allowed:
            metric("vaccines", "Vacunas pendientes", repo.pending_vaccines(conn, today + timedelta(days=30), vet_id), "vaccines", "vaccines", "Vencidas y a 30 días" + (" · propias" if vet_id else ""))
        if "pets" in allowed:
            rows = repo.species_distribution(conn, vet_id)
            species = DashboardSeries(tuple(r[0] for r in rows), tuple(float(r[1]) for r in rows))
        if "appointments" in allowed:
            rows = repo.appointment_states(conn, period, vet_id)
            states = DashboardSeries(tuple(r[0] for r in rows), tuple(float(r[1]) for r in rows))
        alerts = []
        if allowed & {"hospitalization", "triage"}:
            alerts = repo.list_alerts_and_triage(conn, today, vet_id, clinical="hospitalization" in allowed, triage="triage" in allowed)
        if "inventory" in allowed:
            alerts += repo.inventory_alerts(conn, today, today + timedelta(days=30))
        priorities = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        alerts.sort(key=lambda item: priorities.get(item.severity, 4))
        upcoming = repo.list_weekly_appointments(conn, current, today + timedelta(days=7), vet_id, limit=5) if "appointments" in allowed else []
        activity = repo.recent_activity(conn, period, audit="audit" in allowed, user_id=user.id)
    return DashboardSnapshot(
        role_name=user.role_name, metrics=tuple(metrics), alerts_and_triage=tuple(alerts[:6]),
        weekly_appointments=tuple(upcoming), recent_activity=tuple(activity), period=period,
        consultations=consultations, revenue=revenue, species=species, appointment_states=states,
        loaded_at=current,
    )
