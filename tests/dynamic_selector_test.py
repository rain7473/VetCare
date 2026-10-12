"""Pruebas offscreen del selector dinámico reutilizable."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from widgets.dynamic_selector import DynamicEntitySelector, SelectorItem

    _app = QApplication.instance() or QApplication([])
    selector = DynamicEntitySelector(
        placeholder="Buscar propietario…", add_tooltip="Crear propietario"
    )
    selector.set_items(
        [
            SelectorItem(10, "María González", "8-123-456 6000-1111"),
            SelectorItem(20, "Carlos Ramírez", "PE-90 6000-2222"),
        ]
    )

    results: dict[str, bool] = {}
    results["Botón + siempre visible"] = not selector.add_button.isHidden()
    results["Selección guarda ID"] = selector.select_id(20) and selector.current_id() == 20

    selector.combo.lineEdit().setText("6000-1111")
    selector.combo.lineEdit().textEdited.emit("6000-1111")
    results["Filtra por atributo secundario"] = selector._proxy.rowCount() == 1
    results["Botón + sigue visible con coincidencias"] = not selector.add_button.isHidden()

    selector.combo.lineEdit().setText("no-existe")
    selector.combo.lineEdit().textEdited.emit("no-existe")
    results["Texto libre invalida selección"] = selector.current_id() is None
    results["Muestra mensaje sin coincidencias"] = not selector.message_label.isHidden()
    results["Botón + visible sin coincidencias"] = not selector.add_button.isHidden()

    emitted: list[bool] = []
    selector.add_requested.connect(lambda: emitted.append(True))
    selector.add_button.click()
    results["Botón + emite creación"] = emitted == [True]

    selector.set_items(
        [
            SelectorItem(10, "María González"),
            SelectorItem(20, "Carlos Ramírez"),
            SelectorItem(30, "Nuevo Propietario"),
        ],
        selected_id=30,
    )
    results["Registro creado queda seleccionado"] = selector.current_id() == 30

    failures = [name for name, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"  [{'OK' if ok else 'FALLO'}] {name}")
    if failures:
        print(f"\nPrueba FALLIDA: {len(failures)} comprobación(es).")
        return 1
    print("\nPrueba superada: selector dinámico correcto.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
