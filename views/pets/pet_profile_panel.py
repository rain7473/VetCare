"""Ficha compacta de la mascota seleccionada; solo presentación y eventos."""

from datetime import date, datetime

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import CONSULTATION_STATUS_DISPLAY, PET_SEX_DISPLAY, PET_STATUS_DISPLAY
from models.pet import Pet
from services.pet_profile_service import PetProfileData
from utils.images import resolve_photo
from utils.icons import icon, icon_label, pixmap, set_button_icon

_FIELD_ICONS = {
    "Propietario": "owners", "Sexo": "sex", "Edad": "age", "Color": "color",
    "Microchip": "microchip", "Estado": "success", "Tipo de sangre": "blood",
    "Alergias": "allergies", "Cond. crónicas": "chronic", "Características": "features",
    "Última consulta": "consultations", "Próxima vacuna": "vaccines", "Último peso": "weight",
    "Registrada": "appointments", "Actualizada": "refresh",
}

_CARD_ICONS = {
    "Información general": "info", "Estado y características": "chronic",
    "Seguimiento": "followup", "Notas adicionales": "notes", "Fotografía de perfil": "camera",
    "Información de registro": "history",
}


def _display(value: object) -> str:
    return str(value).strip() if value is not None and str(value).strip() else "—"


def _date(value: date | datetime | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _rounded_photo(path: str, size: int = 112) -> QPixmap:
    source = QPixmap.fromImage(QImage(path))
    if source.isNull():
        return QPixmap()
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, 13, 13)
    painter.setClipPath(clip)
    scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    source_rect = QRect((scaled.width() - size) // 2, (scaled.height() - size) // 2, size, size)
    painter.drawPixmap(QRect(0, 0, size, size), scaled, source_rect)
    painter.end()
    return canvas


class PetProfilePanel(QFrame):
    """Cabecera y acciones fijas; cada pestaña desplaza su contenido interno."""

    edit_requested = Signal()
    photo_requested = Signal()
    consultation_requested = Signal()
    history_requested = Signal()
    vaccination_requested = Signal()
    card_requested = Signal()

    def __init__(
        self, *, can_write: bool, can_consult: bool, can_history: bool,
        can_vaccinate: bool, parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("petProfilePanel")
        self._can_write = can_write
        self._can_consult = can_consult
        self._can_history = can_history
        self._can_vaccinate = can_vaccinate
        self._pet: Pet | None = None
        self._columns = 0
        self._action_columns = 0
        self._build_ui()
        self.set_pet(None, None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("petProfileHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 18, 16, 16)
        header_layout.setSpacing(14)

        photo_box = QWidget()
        photo_box.setFixedSize(120, 120)
        photo_grid = QGridLayout(photo_box)
        photo_grid.setContentsMargins(0, 0, 0, 0)
        self.photo_label = QLabel()
        self.photo_label.setObjectName("petProfilePhoto")
        self.photo_label.setFixedSize(112, 112)
        self.photo_label.setAlignment(Qt.AlignCenter)
        photo_grid.addWidget(self.photo_label, 0, 0, Qt.AlignTop | Qt.AlignLeft)
        self.photo_button = QPushButton()
        set_button_icon(self.photo_button, "camera", size=14)
        self.photo_button.setObjectName("petPhotoButton")
        self.photo_button.setFixedSize(30, 30)
        self.photo_button.setToolTip("Cambiar fotografía")
        self.photo_button.setAccessibleName("Cambiar fotografía")
        self.photo_button.clicked.connect(self.photo_requested.emit)
        photo_grid.addWidget(self.photo_button, 0, 0, Qt.AlignBottom | Qt.AlignRight)
        header_layout.addWidget(photo_box, 0, Qt.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(7)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.name_label = QLabel()
        self.name_label.setObjectName("petProfileName")
        self.name_label.setWordWrap(True)
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_row.addWidget(self.name_label, 1)
        self.header_edit_button = QPushButton()
        self.header_edit_button.setObjectName("petHeaderEdit")
        self.header_edit_button.setFixedSize(27, 27)
        self.header_edit_button.setToolTip("Editar mascota")
        self.header_edit_button.setAccessibleName("Editar mascota")
        set_button_icon(self.header_edit_button, "edit", size=13, color="#008FA3")
        self.header_edit_button.clicked.connect(self.edit_requested.emit)
        name_row.addWidget(self.header_edit_button, 0, Qt.AlignTop)
        identity.addLayout(name_row)
        self.species_label = QLabel()
        self.breed_label = QLabel()
        for label, name in ((self.species_label, "pets"), (self.breed_label, "breed")):
            label.setObjectName("petProfileSubtle")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            row = QHBoxLayout()
            row.setSpacing(7)
            row.addWidget(icon_label(name, 14), 0, Qt.AlignTop)
            row.addWidget(label, 1)
            identity.addLayout(row)
        status_row = QHBoxLayout()
        self.status_icon = icon_label("success", 13, "#14946F")
        status_row.addWidget(self.status_icon)
        self.status_label = QLabel()
        self.status_label.setObjectName("petStatusBadge")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        identity.addLayout(status_row)
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.sex_label = QLabel()
        self.age_label = QLabel()
        for label, name in ((self.sex_label, "sex"), (self.age_label, "age")):
            label.setObjectName("petHeaderMetric")
            metrics.addWidget(icon_label(name, 13))
            label.setWordWrap(True)
            metrics.addWidget(label, 1)
        identity.addLayout(metrics)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("petProfileSubtle")
        self.meta_label.setWordWrap(True)
        identity.addWidget(self.meta_label)
        identity.addStretch()
        header_layout.addLayout(identity, 1)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("petProfileTabs")
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabs.setDocumentMode(True)
        tab_bar = self.tabs.tabBar()
        tab_bar.setObjectName("petProfileTabBar")
        tab_bar.setExpanding(True)
        tab_bar.setDrawBase(False)
        tab_bar.setElideMode(Qt.ElideRight)
        tab_bar.setUsesScrollButtons(False)
        self.tabs.setIconSize(QSize(14, 14))
        # Fijar también la paleta evita que el área libre use el fondo oscuro
        # del tema nativo de Windows, fuera de los rectángulos de cada pestaña.
        for widget in (self.tabs, tab_bar):
            palette = widget.palette()
            palette.setColor(QPalette.Window, QColor("#F8FCFD"))
            palette.setColor(QPalette.Base, QColor("#F8FCFD"))
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
        self.info_layout = self._add_scroll_tab("Información")
        self._build_information()
        self.history_layout = self._add_scroll_tab("Historial")
        self.vaccine_layout = self._add_scroll_tab("Vacunas")
        self.consult_layout = self._add_scroll_tab("Consultas")
        self.files_layout = self._add_scroll_tab("Archivos")
        for index, name in enumerate(("info", "history", "vaccines", "consultations", "files")):
            self.tabs.setTabIcon(index, icon(name, "#718B9D", active="#008FA3"))
            self.tabs.setTabToolTip(index, self.tabs.tabText(index))
        root.addWidget(self.tabs, 1)

        footer = QFrame()
        footer.setObjectName("petProfileFooter")
        self.actions_grid = QGridLayout(footer)
        self.actions_grid.setContentsMargins(10, 9, 10, 9)
        self.actions_grid.setHorizontalSpacing(6)
        self.actions_grid.setVerticalSpacing(6)
        self.quick_buttons = [
            self._quick_button("Nueva consulta", "consultations", self.consultation_requested.emit),
            self._quick_button("Ver historial", "history", self.history_requested.emit),
            self._quick_button("Vacunar", "vaccines", self.vaccination_requested.emit),
            self._quick_button("Carné digital", "card", self.card_requested.emit),
        ]
        for button, tooltip in zip(self.quick_buttons, (
            "Abrir una consulta para la mascota seleccionada",
            "Ver el historial de la mascota seleccionada",
            "Registrar una vacuna para la mascota seleccionada",
            "Ver el carné digital con QR",
        )):
            button.setToolTip(tooltip)
        root.addWidget(footer)
        self._arrange(width=0)

    def _add_scroll_tab(self, title: str) -> QVBoxLayout:
        scroll = QScrollArea()
        scroll.setObjectName("petProfileScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("petProfileContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, title)
        return layout

    def _build_information(self) -> None:
        self.info_grid = QGridLayout()
        self.info_grid.setSpacing(10)
        self.info_grid.setColumnStretch(0, 1)
        self.info_grid.setColumnStretch(1, 1)
        self.info_grid.setAlignment(Qt.AlignTop)
        self.info_layout.addLayout(self.info_grid)
        self.info_layout.addStretch()

        general, general_body = self._card("Información general", edit=True)
        self.general_values = self._field_rows(
            general_body, ("Propietario", "Sexo", "Edad", "Color", "Microchip")
        )
        status, status_body = self._card("Estado y características")
        self.status_values = self._field_rows(
            status_body, ("Estado", "Tipo de sangre", "Alergias", "Cond. crónicas", "Características")
        )
        follow, follow_body = self._card("Seguimiento")
        self.follow_values = self._field_rows(
            follow_body, ("Última consulta", "Próxima vacuna", "Último peso")
        )
        links = QVBoxLayout()
        links.setSpacing(4)
        history_link = self._link("Abrir historial", self.history_requested.emit, "history")
        history_link.setEnabled(self._can_history)
        links.addWidget(history_link)
        vaccine_link = self._link("Abrir vacunas", self.vaccination_requested.emit, "vaccines")
        vaccine_link.setEnabled(self._can_vaccinate)
        links.addWidget(vaccine_link)
        follow_body.addLayout(links)
        notes, notes_body = self._card("Notas adicionales")
        self.notes_empty_icon = icon_label("notes", 26, "#9EB9C7")
        notes_body.addWidget(self.notes_empty_icon, 0, Qt.AlignLeft)
        self.notes_label = QLabel()
        self.notes_label.setObjectName("petProfileNote")
        self.notes_label.setWordWrap(True)
        notes_body.addWidget(self.notes_label)
        registration, registration_body = self._card("Información de registro")
        self.registration_values = self._field_rows(
            registration_body, ("Registrada", "Actualizada")
        )
        notes_column = QWidget()
        notes_column.setObjectName("petNotesColumn")
        notes_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        notes_column_layout = QVBoxLayout(notes_column)
        notes_column_layout.setContentsMargins(0, 0, 0, 0)
        notes_column_layout.setSpacing(10)
        notes_column_layout.addWidget(notes)
        notes_column_layout.addWidget(registration)
        self.info_cards = [general, status, follow, notes_column]

    def _card(self, title: str, *, edit: bool = False) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("petInfoCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(7)
        heading.addWidget(icon_label(_CARD_ICONS.get(title, "history"), 15), 0, Qt.AlignTop)
        label = QLabel(title)
        label.setObjectName("petCardHeading")
        label.setWordWrap(True)
        heading.addWidget(label, 1)
        if edit:
            button = self._link("", self.edit_requested.emit, "edit")
            button.setToolTip("Editar información general")
            button.setAccessibleName("Editar información general")
            button.setEnabled(self._can_write)
            heading.addWidget(button)
        layout.addLayout(heading)
        return card, layout

    def _field_rows(self, layout: QVBoxLayout, names: tuple[str, ...]) -> dict[str, QLabel]:
        values = {}
        for index, name in enumerate(names):
            row = QGridLayout()
            row.setHorizontalSpacing(7)
            row.setVerticalSpacing(2)
            row.addWidget(icon_label(_FIELD_ICONS[name], 13, "#7C9DAE"), 0, 0)
            caption = QLabel(name)
            caption.setObjectName("petFieldCaption")
            caption.setWordWrap(True)
            row.addWidget(caption, 0, 1)
            value = QLabel("—")
            value.setObjectName("petFieldValue")
            value.setWordWrap(True)
            value.setTextFormat(Qt.PlainText)
            value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            row.addWidget(value, 1, 1)
            row.setColumnStretch(1, 1)
            layout.addLayout(row)
            if index < len(names) - 1:
                line = QFrame()
                line.setObjectName("petFieldSeparator")
                line.setFixedHeight(1)
                layout.addWidget(line)
            values[name] = value
        return values

    def _link(self, text: str, callback, name: str = "view") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("petProfileLink")
        set_button_icon(button, name, size=13, color="#008FA3")
        button.clicked.connect(callback)
        return button

    def _quick_button(self, text: str, name: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("petQuickAction")
        set_button_icon(button, name, size=15)
        button.clicked.connect(callback)
        return button

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._arrange(self.width())

    def _arrange(self, width: int) -> None:
        columns = 2 if width >= 440 else 1
        if columns != self._columns:
            self._columns = columns
            for card in self.info_cards:
                self.info_grid.removeWidget(card)
            self.info_grid.setColumnStretch(1, 1 if columns == 2 else 0)
            for index, card in enumerate(self.info_cards):
                self.info_grid.addWidget(card, index // columns, index % columns, Qt.AlignTop)
        action_columns = 4 if width >= 620 else 2
        if action_columns != self._action_columns:
            self._action_columns = action_columns
            for button in self.quick_buttons:
                self.actions_grid.removeWidget(button)
            for index, button in enumerate(self.quick_buttons):
                self.actions_grid.addWidget(button, index // action_columns, index % action_columns)

    def set_pet(self, pet: Pet | None, data: PetProfileData | None) -> None:
        self._pet = pet
        selected = pet is not None
        self.name_label.setText(pet.name if pet else "Seleccione una mascota")
        self.species_label.setText(_display(pet.species_name) if pet else "Elija una fila para ver su perfil")
        self.breed_label.setText(
            pet.breed_name or "Sin raza definida" if pet else "—"
        )
        self.status_label.setText(PET_STATUS_DISPLAY.get(pet.status, pet.status) if pet else "")
        self.status_label.setProperty("petStatus", pet.status if pet else "")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        status_icon, status_color = {
            "ACTIVE": ("success", "#14946F"), "INACTIVE": ("inactive", "#B48022"),
            "DECEASED": ("deceased", "#C05F69"),
        }.get(pet.status if pet else "", ("pets", "#8AA4B2"))
        self.status_icon.setPixmap(pixmap(status_icon, 13, status_color))
        self.status_icon.setVisible(selected)
        self.status_label.setVisible(selected)
        self.sex_label.setText(PET_SEX_DISPLAY.get(pet.sex, pet.sex) if pet else "—")
        self.age_label.setText(pet.age_text() if pet else "—")
        meta = ""
        if data and data.latest_weight_kg is not None:
            meta = f"Último peso registrado: {data.latest_weight_kg:g} kg"
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))
        photo = resolve_photo(pet.photo_url) if pet else None
        photo_pixmap = _rounded_photo(str(photo)) if photo else QPixmap()
        self.photo_label.setPixmap(
            photo_pixmap if not photo_pixmap.isNull() else pixmap("pets", 48, "#79B6C5")
        )
        self.photo_button.setEnabled(selected and self._can_write)
        self.header_edit_button.setEnabled(selected and self._can_write)
        for button, allowed in zip(
            self.quick_buttons,
            (self._can_consult, self._can_history, self._can_vaccinate, True),
        ):
            button.setEnabled(selected and allowed)

        self._fill_information(pet, data)
        self._fill_history(pet, data)
        self._fill_vaccines(pet, data)
        self._fill_consultations(pet, data)
        self._fill_files(pet, photo)
        for index in range(self.tabs.count()):
            self.tabs.widget(index).verticalScrollBar().setValue(0)

    def _fill_information(self, pet: Pet | None, data: PetProfileData | None) -> None:
        general = self.general_values
        status = self.status_values
        follow = self.follow_values
        for name, value in (
            ("Registrada", pet.created_at if pet else None),
            ("Actualizada", pet.updated_at if pet else None),
        ):
            self.registration_values[name].setText(
                value.strftime("%d/%m/%Y · %H:%M") if value else "—"
            )
        fields = {
            "Propietario": pet.owner_name if pet else None,
            "Sexo": PET_SEX_DISPLAY.get(pet.sex, pet.sex) if pet else None,
            "Edad": pet.age_text() if pet else None,
            "Color": pet.color if pet else None,
            "Microchip": pet.microchip_number if pet else None,
        }
        for name, value in fields.items():
            general[name].setText(_display(value))
        for name, value in {
            "Estado": PET_STATUS_DISPLAY.get(pet.status, pet.status) if pet else None,
            "Tipo de sangre": pet.blood_type if pet else None,
            "Alergias": pet.allergies if pet else None,
            "Cond. crónicas": pet.chronic_conditions if pet else None,
            "Características": pet.distinctive_features if pet else None,
        }.items():
            status[name].setText(_display(value))
        clinical = data.consultations if data else ()
        follow["Última consulta"].setText(
            _date(clinical[0].started_at) if clinical else
            "Sin permiso" if pet and data and not data.clinical_allowed else "—"
        )
        next_vaccine = data.next_vaccination if data else None
        due_text = (
            f"Pendiente desde {_date(next_vaccine.next_due_date)}"
            if next_vaccine and next_vaccine.next_due_date < date.today()
            else _date(next_vaccine.next_due_date) if next_vaccine else ""
        )
        follow["Próxima vacuna"].setText(
            f"{_display(next_vaccine.vaccine_name)} · {due_text}"
            if next_vaccine else
            "Sin permiso" if pet and data and not data.vaccines_allowed else "—"
        )
        follow["Último peso"].setText(
            f"{data.latest_weight_kg:g} kg" if data and data.latest_weight_kg is not None else "—"
        )
        observation = next((c for c in clinical if c.observations and str(c.observations).strip()), None)
        self.notes_empty_icon.setVisible(observation is None)
        self.notes_label.setText(
            f"Observación clínica del {_date(observation.started_at)}: {observation.observations}"
            if observation else
            "Sin permiso para ver notas clínicas." if pet and data and not data.clinical_allowed
            else "No hay observaciones clínicas registradas."
        )

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _empty(self, layout: QVBoxLayout, message: str) -> None:
        label = QLabel(message)
        label.setObjectName("petProfileEmpty")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()

    def _entry(self, layout: QVBoxLayout, title: str, subtitle: str, body: str = "") -> None:
        card, content = self._card(title)
        caption = QLabel(subtitle)
        caption.setObjectName("petProfileSubtle")
        caption.setWordWrap(True)
        content.addWidget(caption)
        if body:
            detail = QLabel(body)
            detail.setWordWrap(True)
            content.addWidget(detail)
        layout.addWidget(card)

    def _fill_history(self, pet: Pet | None, data: PetProfileData | None) -> None:
        layout = self.history_layout
        self._clear(layout)
        if not pet:
            return self._empty(layout, "Seleccione una mascota para ver su historial.")
        if data is None or not data.clinical_allowed:
            return self._empty(layout, "Sin permiso para consultar el historial clínico.")
        events = []
        for consultation in data.consultations:
            events.append((consultation.started_at,
                           f"Consulta · {consultation.started_at:%d/%m/%Y %H:%M}",
                           consultation.reason,
                           CONSULTATION_STATUS_DISPLAY.get(consultation.status, consultation.status)))
        if data.vaccines_allowed:
            for vaccine in data.vaccinations:
                events.append((vaccine.applied_at,
                               f"Vacuna · {vaccine.applied_at:%d/%m/%Y %H:%M}",
                               _display(vaccine.vaccine_name),
                               f"Próxima aplicación: {_date(vaccine.next_due_date)}"))
        if not events:
            return self._empty(layout, "No hay eventos clínicos registrados.")
        for _when, title, subtitle, body in sorted(
            events, key=lambda item: item[0].timestamp(), reverse=True
        ):
            self._entry(layout, title, subtitle, body)
        layout.addStretch()

    def _fill_vaccines(self, pet: Pet | None, data: PetProfileData | None) -> None:
        layout = self.vaccine_layout
        self._clear(layout)
        if not pet:
            return self._empty(layout, "Seleccione una mascota para ver sus vacunas.")
        if data is None or not data.vaccines_allowed:
            return self._empty(layout, "Sin permiso para consultar vacunas.")
        if not data.vaccinations:
            return self._empty(layout, "No hay vacunas registradas para esta mascota.")
        for vaccination in data.vaccinations:
            self._entry(
                layout, _display(vaccination.vaccine_name),
                f"Aplicada: {_date(vaccination.applied_at)} · Por: {_display(vaccination.applied_by_name)}",
                f"Próxima aplicación: {_date(vaccination.next_due_date)}"
                + (f" · Lote: {vaccination.lot_number}" if vaccination.lot_number else ""),
            )
        layout.addStretch()

    def _fill_consultations(self, pet: Pet | None, data: PetProfileData | None) -> None:
        layout = self.consult_layout
        self._clear(layout)
        if not pet:
            return self._empty(layout, "Seleccione una mascota para ver sus consultas.")
        if data is None or not data.clinical_allowed:
            return self._empty(layout, "Sin permiso para consultar el historial clínico.")
        if not data.consultations:
            return self._empty(layout, "No hay consultas registradas para esta mascota.")
        for consultation in data.consultations:
            self._entry(
                layout, f"Consulta · {_date(consultation.started_at)}",
                f"{_display(consultation.veterinarian_name)} · "
                f"{CONSULTATION_STATUS_DISPLAY.get(consultation.status, consultation.status)}",
                _display(consultation.reason),
            )
        layout.addStretch()

    def _fill_files(self, pet: Pet | None, photo) -> None:
        layout = self.files_layout
        self._clear(layout)
        if not pet:
            return self._empty(layout, "Seleccione una mascota para ver sus archivos.")
        if photo:
            card, content = self._card("Fotografía de perfil")
            preview = QLabel()
            preview.setPixmap(_rounded_photo(str(photo), 140))
            preview.setAlignment(Qt.AlignLeft)
            content.addWidget(preview)
            layout.addWidget(card)
        self._empty(layout, "No hay documentos adjuntos registrados.")
