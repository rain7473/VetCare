"""Diálogo modal que libera su ventana nativa al terminar.

En Qt, cerrar un ``QDialog`` que tiene padre solo lo oculta: el objeto y su
ventana nativa continúan vivos hasta destruir el padre. En una aplicación de
escritorio de larga duración eso acumula superficies ocultas y, en Windows,
puede producir miniaturas o ventanas fantasma al abrir nuevos formularios.
"""

from PySide6.QtWidgets import QDialog


class ManagedDialog(QDialog):
    """QDialog síncrono que programa su destrucción después de ``exec``.

    ``deleteLater`` conserva el objeto durante la pila actual, por lo que el
    código llamador todavía puede leer atributos como ``created_id`` justo
    después de ``exec()``. La destrucción ocurre al volver al bucle principal
    de eventos.
    """

    def exec(self) -> int:
        result = super().exec()
        self.hide()
        self.deleteLater()
        return result
