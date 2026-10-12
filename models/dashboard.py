"""Modelos de solo lectura para el dashboard de VetCare."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class DashboardPeriod:
    """Fechas locales inclusivas; las consultas usan fin exclusivo."""

    start: date
    end: date
    label: str = "Período seleccionado"

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("La fecha inicial no puede superar la fecha final.")

    @property
    def previous(self):
        days = (self.end - self.start).days + 1
        return DashboardPeriod(self.start - timedelta(days=days), self.start - timedelta(days=1))


@dataclass(frozen=True)
class DashboardSeries:
    labels: tuple[str, ...] = ()
    values: tuple[float, ...] = ()
    selected: tuple[float, ...] = ()
    previous: tuple[float, ...] = ()


@dataclass(frozen=True)
class DashboardMetric:
    key: str
    title: str
    value: str
    icon: str
    detail: str = ""
    module: str = ""


@dataclass(frozen=True)
class DashboardItem:
    title: str
    detail: str
    occurred_at: datetime | None = None
    severity: str | None = None
    module: str = ""


@dataclass(frozen=True)
class DashboardSnapshot:
    role_name: str
    metrics: tuple[DashboardMetric, ...]
    alerts_and_triage: tuple[DashboardItem, ...] = ()
    weekly_appointments: tuple[DashboardItem, ...] = ()
    recent_activity: tuple[DashboardItem, ...] = ()
    period: DashboardPeriod | None = None
    consultations: DashboardSeries | None = None
    revenue: DashboardSeries | None = None
    species: DashboardSeries | None = None
    appointment_states: DashboardSeries | None = None
    loaded_at: datetime | None = None

