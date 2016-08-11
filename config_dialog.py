# encoding: utf-8
#-----------------------------------------------------------
# Copyright (C) 2016 Martin Dobias
#-----------------------------------------------------------
# Licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#---------------------------------------------------------------------

import os
import psycopg2

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from PyQt4 import uic

from qgis.core import QgsApplication

from trigger_dialog import TriggerDialog
from sql_generator import SqlGenerator, list_triggers
from pg_connection import connection_from_name

this_dir = os.path.dirname(__file__)

WIDGET, BASE = uic.loadUiType(os.path.join(this_dir, 'config_dialog.ui'))


class ConfigDialog(BASE, WIDGET):
    def __init__(self, parent=None):
        BASE.__init__(self, parent)
        self.setupUi(self)

        settings = QSettings()
        self.restoreGeometry(settings.value("/Plugins/RRM_Plugin/config_geometry", "", "QByteArray"))

        self.btnAdd.setIcon(QgsApplication.getThemeIcon("/symbologyAdd.svg"))
        self.btnEdit.setIcon(QgsApplication.getThemeIcon("/mActionToggleEditing.svg"))
        self.btnRemove.setIcon(QgsApplication.getThemeIcon("/symbologyRemove.svg"))

        settings.beginGroup('/PostgreSQL/connections')
        pg_connections = settings.childGroups()
        settings.endGroup()

        # populate connections
        self.cboConnection.addItem("[select a PostGIS connection]")
        for name in pg_connections:
            self.cboConnection.addItem(name)
        last_conn_name = settings.value("/Plugins/RRM_Plugin/last_conn_name", "")
        if last_conn_name in pg_connections:
            self.cboConnection.setCurrentIndex(pg_connections.index(last_conn_name)+1)

        self.model = QStandardItemModel()
        self.treeTriggers.setModel(self.model)

        self.cboConnection.currentIndexChanged.connect(self.populate_triggers)
        self.btnAdd.clicked.connect(self.add_trigger)
        self.btnEdit.clicked.connect(self.edit_trigger)
        self.btnRemove.clicked.connect(self.remove_trigger)

        self.populate_triggers()

    def hideEvent(self, e):
        # using hideEvent() because closeEvent() was not called when "Close" button was clicked!
        settings = QSettings()
        settings.setValue("/Plugins/RRM_Plugin/config_geometry", self.saveGeometry())
        settings.setValue("/Plugins/RRM_Plugin/last_conn_name", self.cboConnection.currentText())
        BASE.hideEvent(self, e)

    def get_connection(self):

        name = self.cboConnection.currentText()
        return connection_from_name(name)

    def enable_controls(self, enabled):
        for w in [self.btnAdd, self.btnEdit, self.btnRemove]:
            w.setEnabled(enabled)

    def populate_triggers(self):

        self.triggers = []
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["ID", "Source Table", "Target Table"])

        try:
            conn = self.get_connection()
        except Exception:
            if self.cboConnection.currentIndex() > 0:
                QMessageBox.warning(self, "RRM", "Cannot connect to the selected database connection!")
            self.enable_controls(False)
            return

        self.enable_controls(True)

        self.triggers = list_triggers(conn)

        for trigger_id, source_table, target_table in self.triggers:
            item_0 = QStandardItem(str(trigger_id))
            item_1 = QStandardItem(source_table)
            item_2 = QStandardItem(target_table)
            for i in [item_0, item_1, item_2]:
                i.setEditable(False)
            self.model.appendRow([item_0, item_1, item_2])

        self.treeTriggers.resizeColumnToContents(1)

    def add_trigger(self):
        conn = self.get_connection()
        dlg = TriggerDialog(conn)
        if not dlg.exec_():
            return

        sql_gen = SqlGenerator()
        sql_gen.source_table = dlg.cboSource.currentText()
        sql_gen.target_table = dlg.cboTarget.currentText()
        # mapping
        sql_gen.attr_map = {}
        for row in xrange(dlg.model.rowCount()):
            if dlg.model.item(row, 0).checkState() == Qt.Checked:
                source_attr = dlg.model.item(row, 0).text()
                target_attr = dlg.model.item(row, 1).text()
                sql_gen.attr_map[source_attr] = target_attr
        # find new trigger ID
        if len(self.triggers) != 0:
            sql_gen.trg_fcn_id = max(trigger[0] for trigger in self.triggers) + 1
        else:
            sql_gen.trg_fcn_id = 1
        sql = sql_gen.create_sql()

        cur = conn.cursor()
        cur.execute("BEGIN;"+sql+"COMMIT;")

        self.populate_triggers()

    def edit_trigger(self):
        # TODO
        QMessageBox.information(self, "RRM", "Not implemented yet.")

    def remove_trigger(self):

        index = self.treeTriggers.selectionModel().currentIndex()
        if not index.isValid():
            return

        trigger = self.triggers[index.row()]
        sql_gen = SqlGenerator()
        sql_gen.trg_fcn_id = trigger[0]
        sql_gen.source_table = trigger[1]
        sql_gen.target_table = trigger[2]
        sql = sql_gen.drop_sql()

        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("BEGIN;"+sql+"COMMIT;")

        self.populate_triggers()
