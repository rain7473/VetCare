"""Política visual de calendarios Qt, incluidos los popups de fecha y hora."""
from PySide6.QtCore import QObject, QEvent, QLocale
from PySide6.QtWidgets import QCalendarWidget


class CalendarStyle(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Polish and isinstance(obj, QCalendarWidget):
            obj.setLocale(QLocale(QLocale.Spanish, QLocale.Panama))
            obj.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
            obj.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
            obj.setMinimumSize(350, 280)
        return False
