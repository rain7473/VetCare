"""Service de historial inmutable: verificación SHA-256 y enmiendas.

Las consultas SEALED no se modifican. Las correcciones van a
CLINICAL_AMENDMENTS (append-only). El hash de cada enmienda se calcula
con DBMS_CRYPTO en Oracle, igual que el sellado clínico.
"""

import logging
from dataclasses import dataclass

import oracledb

from database.connection import connection_scope
from models.amendment import ClinicalAmendment
from repositories import amendment_repository, consultation_repository
from services import permission_service, session
from utils import validators
from utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AmendmentFormData:
    consultation_id: int
    reason: str
    amendment_text: str


@dataclass(frozen=True)
class IntegrityReport:
    consultation_id: int
    status: str
    sealed_hash: str | None
    sealed_at: object | None
    seal_ok: bool | None
    amendments: list[tuple[ClinicalAmendment, bool | None]]


def verify_consultation_integrity(consultation_id: int) -> IntegrityReport:
    """Verifica el sello Oracle y los hashes de enmiendas."""
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return _verify(conn, consultation_id)


def list_amendments(consultation_id: int) -> list[ClinicalAmendment]:
    permission_service.require_permission("CONSULTATIONS_READ")
    with connection_scope() as conn:
        return amendment_repository.list_by_consultation(conn, consultation_id)


def add_amendment(data: AmendmentFormData) -> int:
    """Agrega una corrección a una consulta sellada (append-only)."""
    permission_service.require_permission("CONSULTATIONS_WRITE")
    with connection_scope(commit=True) as conn:
        return _add_amendment(conn, data)


def _verify(conn: oracledb.Connection, consultation_id: int) -> IntegrityReport:
    consultation = consultation_repository.get_by_id(conn, consultation_id)
    if consultation is None:
        raise ValidationError("La consulta no existe.")

    seal_ok = None
    if consultation.status == "SEALED":
        seal_ok = consultation_repository.verify_hash(conn, consultation_id)

    amendments = amendment_repository.list_by_consultation(conn, consultation_id)
    checked: list[tuple[ClinicalAmendment, bool | None]] = []
    for item in amendments:
        if not item.amendment_hash:
            checked.append((item, None))
            continue
        expected = _payload_hash(
            conn,
            consultation_id=item.consultation_id,
            created_by=item.created_by,
            reason=item.reason,
            amendment_text=item.amendment_text,
        )
        checked.append((item, expected == item.amendment_hash))

    return IntegrityReport(
        consultation_id=consultation.id,
        status=consultation.status,
        sealed_hash=consultation.sealed_hash,
        sealed_at=consultation.sealed_at,
        seal_ok=seal_ok,
        amendments=checked,
    )


def _add_amendment(conn: oracledb.Connection, data: AmendmentFormData) -> int:
    current = session.get_current_user()
    if current is None:
        raise ValidationError("No hay una sesión activa.")

    consultation = consultation_repository.get_by_id(conn, data.consultation_id)
    if consultation is None:
        raise ValidationError("La consulta no existe.")
    if consultation.status != "SEALED":
        raise ValidationError(
            "Las enmiendas solo aplican a consultas selladas. "
            "Si aún está en borrador, edítela directamente."
        )

    reason = validators.validate_required_text(data.reason, "El motivo", 4000)
    text = validators.validate_required_text(
        data.amendment_text, "El texto de la corrección", 4000
    )
    amendment_hash = _payload_hash(
        conn,
        consultation_id=consultation.id,
        created_by=current.id,
        reason=reason,
        amendment_text=text,
    )
    amendment_id = amendment_repository.insert_amendment(
        conn,
        consultation_id=consultation.id,
        created_by=current.id,
        reason=reason,
        amendment_text=text,
        amendment_hash=amendment_hash,
    )
    logger.info(
        "Enmienda %s agregada a consulta sellada %s",
        amendment_id,
        consultation.id,
    )
    return amendment_id


def _payload_hash(
    conn: oracledb.Connection,
    *,
    consultation_id: int,
    created_by: int,
    reason: str,
    amendment_text: str,
) -> str:
    payload = (
        f"{consultation_id}|{created_by}|{reason.strip()}|{amendment_text.strip()}"
    )
    return amendment_repository.oracle_sha256(conn, payload)
