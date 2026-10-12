"""Selector reutilizable de entidades relacionadas.

Combina un ``QComboBox`` editable, autocompletado ``contains`` y un botón
``+`` siempre visible.  El texto escrito nunca se considera un valor válido:
solo una fila seleccionada aporta el ID que consumen los formularios.
"""

from __future__ import annotations

from dataclasses import dataclass
from utils.icons import set_button_icon

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


ID_ROLE = Qt.UserRole
SEARCH_ROLE = Qt.UserRole + 1


@dataclass(frozen=True)
class SelectorItem:
    id: object
    label: str
    search_text: str = ""


class DynamicEntitySelector(QWidget):
    """Selector buscable que conserva un ID válido y permite crear registros."""

    add_requested = Signal()
    selection_changed = Signal(object)

    def __init__(
        self,
        *,
        placeholder: str = "Buscar…",
        add_tooltip: str = "Crear nuevo registro",
        allow_empty: bool = False,
        empty_label: str = "— Sin seleccionar —",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._allow_empty = allow_empty
        self._empty_label = empty_label
        self._items: list[SelectorItem] = []
        self._selected_id = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.lineEdit().setPlaceholderText(placeholder)
        self.combo.lineEdit().textEdited.connect(self._on_text_edited)
        self.combo.activated.connect(self._on_activated)
        row.addWidget(self.combo, stretch=1)

        self.add_button = QPushButton()
        set_button_icon(self.add_button, "add", size=16)
        self.add_button.setObjectName("selectorAddButton")
        self.add_button.setFixedWidth(36)
        self.add_button.setToolTip(add_tooltip)
        self.add_button.setAccessibleName(add_tooltip)
        self.add_button.clicked.connect(self.add_requested)
        row.addWidget(self.add_button)
        outer.addLayout(row)

        self.message_label = QLabel("No se encontraron coincidencias")
        self.message_label.setObjectName("selectorMessage")
        self.message_label.setVisible(False)
        outer.addWidget(self.message_label)

        self._model = QStandardItemModel(self)
        self.combo.setModel(self._model)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterRole(SEARCH_ROLE)
        self._proxy.setFilterKeyColumn(0)

        self._completer = QCompleter(self._proxy, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setCompletionRole(Qt.DisplayRole)
        self.combo.setCompleter(self._completer)
        self._completer.activated.connect(self._on_completion)

    def set_add_enabled(self, enabled: bool, tooltip: str | None = None) -> None:
        self.add_button.setEnabled(enabled)
        if tooltip:
            self.add_button.setToolTip(tooltip)

    def set_items(
        self,
        items: list[SelectorItem],
        *,
        selected_id=None,
        preserve_text: bool = False,
    ) -> None:
        typed = self.combo.currentText() if preserve_text else ""
        self._items = list(items)
        self._model.clear()
        self.combo.blockSignals(True)
        self.combo.clear()

        if self._allow_empty:
            self._append_item(SelectorItem(None, self._empty_label, self._empty_label))
        for item in self._items:
            self._append_item(item)
        self.combo.blockSignals(False)

        if selected_id is not None or (self._allow_empty and selected_id is None):
            self.select_id(selected_id)
        else:
            self.clear_selection(text=typed)

    def _append_item(self, item: SelectorItem) -> None:
        model_item = QStandardItem(item.label)
        model_item.setData(item.id, ID_ROLE)
        searchable = f"{item.label} {item.search_text}".strip()
        model_item.setData(searchable, SEARCH_ROLE)
        self._model.appendRow(model_item)

    def current_id(self):
        return self._selected_id

    def has_valid_selection(self) -> bool:
        return self._selected_id is not None or (
            self._allow_empty and self.combo.currentText() == self._empty_label
        )

    def select_id(self, record_id) -> bool:
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            if self._model.data(index, ID_ROLE) == record_id:
                self.combo.setCurrentIndex(row)
                self._selected_id = record_id
                self.message_label.setVisible(False)
                self.selection_changed.emit(record_id)
                return True
        return False

    def clear_selection(self, text: str = "") -> None:
        self.combo.setCurrentIndex(-1)
        self.combo.setEditText(text)
        self._selected_id = None

    def focus_search(self) -> None:
        self.combo.setFocus()
        self.combo.lineEdit().selectAll()

    def _on_text_edited(self, text: str) -> None:
        self._selected_id = None
        self._proxy.setFilterFixedString(text.strip())
        has_matches = self._proxy.rowCount() > 0
        self.message_label.setVisible(bool(text.strip()) and not has_matches)
        if text.strip() and has_matches:
            self._completer.complete()

    def _on_activated(self, index: int) -> None:
        if index < 0:
            return
        self._selected_id = self.combo.itemData(index, ID_ROLE)
        self.message_label.setVisible(False)
        self.selection_changed.emit(self._selected_id)

    def _on_completion(self, value) -> None:
        label = value if isinstance(value, str) else value.data(Qt.DisplayRole)
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            if self._model.data(index, Qt.DisplayRole) == label:
                self.combo.setCurrentIndex(row)
                self._selected_id = self._model.data(index, ID_ROLE)
                self.message_label.setVisible(False)
                self.selection_changed.emit(self._selected_id)
                return
