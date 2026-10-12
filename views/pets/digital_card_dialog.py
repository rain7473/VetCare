"""Diálogo del carné digital de la mascota."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from config.constants import PET_SEX_DISPLAY, APP_NAME
from database.connection import DatabaseConnectionError
from services import digital_card_service, permission_service
from services.permission_service import PermissionDeniedError
from utils.images import resolve_photo
from utils.icons import pixmap as icon_pixmap, set_button_icon
from utils.qr import make_qr_pixmap
from utils.validators import ValidationError
from widgets.managed_dialog import ManagedDialog


class DigitalCardDialog(ManagedDialog):
    """Muestra el carné con foto, datos básicos, vacunas y QR."""

    def __init__(self, pet_id: int, parent=None) -> None:
        super().__init__(parent)
        self._pet_id = pet_id
        self.setWindowTitle(f"{APP_NAME} — Carné digital")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        top = QHBoxLayout()
        self.photo_label = QLabel()
        self.photo_label.setPixmap(icon_pixmap("pets", 38, "#79B6C5"))
        self.photo_label.setObjectName("photoPreview")
        self.photo_label.setFixedSize(96, 96)
        self.photo_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self.photo_label)

        info = QVBoxLayout()
        self.name_label = QLabel("")
        self.name_label.setObjectName("profileName")
        info.addWidget(self.name_label)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("screenSubtitle")
        self.meta_label.setWordWrap(True)
        info.addWidget(self.meta_label)
        info.addStretch()
        top.addLayout(info, stretch=1)

        self.qr_label = QLabel()
        self.qr_label.setFixedSize(160, 160)
        self.qr_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self.qr_label)
        layout.addLayout(top)

        form = QFormLayout()
        self.detail_labels: dict[str, QLabel] = {}
        for key, title in [
            ("owner", "Propietario"),
            ("sex", "Sexo"),
            ("birth", "Nacimiento / edad"),
            ("microchip", "Microchip"),
            ("token", "Token público"),
            ("vaccines", "Vacunas"),
        ]:
            value = QLabel("—")
            value.setWordWrap(True)
            self.detail_labels[key] = value
            form.addRow(f"{title}:", value)
        layout.addLayout(form)

        note = QLabel(
            "El QR solo contiene el token público. No incluye información clínica."
        )
        note.setObjectName("versionLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        if permission_service.has_permission("PETS_WRITE"):
            reissue = QPushButton("Reemitir carné")
            set_button_icon(reissue, "card", color="#008FA3")
            reissue.setProperty("variant", "secondary")
            reissue.clicked.connect(self._on_reissue)
            buttons.addWidget(reissue)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _load(self) -> None:
        try:
            view = digital_card_service.get_or_issue_card(self._pet_id)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Carné digital", str(exc))
            self.reject()
            return

        pet = view.pet
        self.name_label.setText(pet.name)
        breed = pet.breed_name or "Sin raza"
        self.meta_label.setText(f"{pet.species_name} · {breed}")

        photo = resolve_photo(pet.photo_url)
        if photo:
            pixmap = QPixmap(str(photo)).scaled(
                96, 96, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.photo_label.setPixmap(pixmap)
        else:
            self.photo_label.setPixmap(icon_pixmap("pets", 38, "#79B6C5"))

        self.detail_labels["owner"].setText(pet.owner_name or "—")
        self.detail_labels["sex"].setText(PET_SEX_DISPLAY.get(pet.sex, pet.sex))
        birth = (
            pet.birth_date.strftime("%d/%m/%Y")
            if pet.birth_date
            else pet.age_text()
        )
        self.detail_labels["birth"].setText(birth)
        self.detail_labels["microchip"].setText(pet.microchip_number or "—")
        self.detail_labels["token"].setText(view.card.public_token_hex)

        if view.vaccines:
            lines = [
                f"{v.vaccine_name} ({v.applied_at.strftime('%d/%m/%Y')})"
                for v in view.vaccines
            ]
            self.detail_labels["vaccines"].setText("\n".join(lines))
        else:
            self.detail_labels["vaccines"].setText("Sin vacunas registradas")

        self.qr_label.setPixmap(make_qr_pixmap(view.qr_payload))

    def _on_reissue(self) -> None:
        if QMessageBox.question(
            self,
            "Carné digital",
            "¿Reemitir el carné? El QR anterior dejará de ser el activo.",
        ) != QMessageBox.Yes:
            return
        try:
            digital_card_service.reissue_card(self._pet_id)
        except (ValidationError, PermissionDeniedError, DatabaseConnectionError) as exc:
            QMessageBox.warning(self, "Carné digital", str(exc))
            return
        self._load()
