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
from wizard_dialog import WizardDialog

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

        self.triggers = []
        self.model = QStandardItemModel()
        self.treeTriggers.setModel(self.model)

        self.cboConnection.currentIndexChanged.connect(self.populate_triggers)
        self.cboSchema.currentIndexChanged.connect(self._update_triggers_model)
        self.btnAdd.clicked.connect(self.add_trigger)
        self.btnEdit.clicked.connect(self.edit_trigger)
        self.btnRemove.clicked.connect(self.remove_trigger)
        self.btnWizard.clicked.connect(self.open_wizard)

        self.populate_triggers()

    def showEvent(self, event):
        self.delete_not_valid_triggers()


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
        for w in [self.btnAdd, self.btnEdit, self.btnRemove, self.cboSchema, self.btnWizard]:
            w.setEnabled(enabled)

    def populate_triggers(self):

        self.triggers = []

        try:
            conn = self.get_connection()
        except Exception:
            if self.cboConnection.currentIndex() > 0:
                QMessageBox.warning(self, "PostGIS Sampling Tool", "Cannot connect to the selected database connection!")
            self.enable_controls(False)
            return

        self.enable_controls(True)

        # populate list of schemas (for filtering)
        old_schema_filter = self.cboSchema.currentText()
        self.cboSchema.blockSignals(True)
        self.cboSchema.clear()
        self.cboSchema.addItem("[all]")
        c = conn.cursor()
        c.execute("SELECT oid, nspname FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname != 'information_schema'")
        for row in c.fetchall():
            self.cboSchema.addItem(row[1])
        if self.cboSchema.findText(old_schema_filter) != -1:  # select previously used filter
            self.cboSchema.setCurrentIndex(self.cboSchema.findText(old_schema_filter))
        self.cboSchema.blockSignals(False)

        self.triggers = list_triggers(conn)

        self._update_triggers_model()

    def delete_not_valid_triggers(self):
        if not self.triggers: return

        invalid = []
        for trigger_id, src, trg in self.triggers:
            if not src or not trg:
                invalid.append((trigger_id, src, trg))

        if not invalid: return

        msgBox = QMessageBox()
        msgBox.setWindowTitle("Invalid triggers found")
        msgBox.setText("Do you want to delete all invalid triggers?")
        msgBox.setStandardButtons(QMessageBox.Yes)
        msgBox.addButton(QMessageBox.No)
        msgBox.setDefaultButton(QMessageBox.No)
        if msgBox.exec_() == QMessageBox.Yes:
            for trigger_id, src, trg in invalid:
                    sql_gen = SqlGenerator()
                    sql_gen.trg_fcn_id = trigger_id
                    sql_gen.source_table = src
                    sql_gen.target_table = trg
                    sql = sql_gen.drop_sql()

                    conn = self.get_connection()
                    cur = conn.cursor()
                    cur.execute("BEGIN;" + sql + "COMMIT;")

            self.populate_triggers()

    def _update_triggers_model(self):
        schema_filter = self.cboSchema.currentText() if self.cboSchema.currentIndex() > 0 else None
        def _filter_accepts(table_name):
            return schema_filter is None or table_name.startswith(schema_filter+".")

        self.model.clear()
        self.model.setHorizontalHeaderLabels(["ID", "Source Table", "Target Table"])
        index = -1
        for trigger_id, source_table, target_table in self.triggers:
            index += 1
            if not _filter_accepts(source_table) and not _filter_accepts(target_table):
                continue
            item_0 = QStandardItem(str(trigger_id))
            item_0.setData(index)  # store index of the item in self.triggers (used in _current_item_to_generator)
            item_1 = QStandardItem(source_table)
            item_2 = QStandardItem(target_table)
            for i in [item_0, item_1, item_2]:
                i.setEditable(False)
                if not source_table or not target_table:
                    i.setData(QColor("pink"), Qt.BackgroundRole)
                    i.setToolTip("Not valid, the trigger is missing source or target table.")
            self.model.appendRow([item_0, item_1, item_2])

        self.treeTriggers.resizeColumnToContents(1)

    def open_wizard(self):
        conn = self.get_connection()
        dlg = WizardDialog(conn)
        if not dlg.exec_():
            return
        generators = dlg.to_sql_generator()

        final_sql = ""
        offset = 0
        for sql_gen in generators:
            sql_gen.trg_fcn_id = self._new_trigger_id() + offset
            sql = sql_gen.create_sql()
            final_sql += sql + ";"
            offset +=1

        cur = conn.cursor()
        cur.execute("BEGIN;" + final_sql + "COMMIT;")
        self.populate_triggers()


    def add_trigger(self):
        conn = self.get_connection()
        dlg = TriggerDialog(conn)
        if not dlg.exec_():
            return

        sql_gen = dlg.to_sql_generator()
        sql_gen.trg_fcn_id = self._new_trigger_id()
        sql = sql_gen.create_sql()

        cur = conn.cursor()
        cur.execute("BEGIN;" + sql + "COMMIT;")

        self.populate_triggers()

    def _new_trigger_id(self):
        # find new trigger ID
        if len(self.triggers) == 0:
            return 1

        return max(trigger[0] for trigger in self.triggers) + 1

    def _current_item_to_sql_generator(self):
        index = self.treeTriggers.selectionModel().currentIndex()
        if not index.isValid():
            return

        # because of the filtering by schema, index of the item may not be same as index in self.triggers
        trigger_index = self.model.data(self.model.index(index.row(),0), Qt.UserRole+1)

        trigger = self.triggers[trigger_index]
        sql_gen = SqlGenerator()
        sql_gen.trg_fcn_id = trigger[0]
        sql_gen.source_table = trigger[1]
        sql_gen.target_table = trigger[2]
        return sql_gen

    def edit_trigger(self):
        sql_gen = self._current_item_to_sql_generator()
        if not sql_gen:
            return

        sql = sql_gen.load_trigger_sql()

        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        trigger_json_str = cur.fetchone()[0]
        if trigger_json_str is None:
            QMessageBox.critical(self, "Error", "Cannot fetch trigger's details.\n\nRemoving the trigger and adding it again will fix the problem.")
            return

        try:
            sql_gen.parse_json(trigger_json_str)
        except ValueError:
            QMessageBox.critical(self, "Error", "Trigger's details are malformed.\n\nRemoving the trigger and adding it again will fix the problem.")
            return

        dlg = TriggerDialog(conn, sql_gen)
        if not dlg.exec_():
            return

        cur = conn.cursor()

        # remove the existing pair of triggers
        sql_drop_old = sql_gen.drop_sql()
        cur.execute("BEGIN;" + sql_drop_old + "COMMIT;")

        # create new pair of triggers
        sql_gen_new = dlg.to_sql_generator()
        sql_gen_new.trg_fcn_id = self._new_trigger_id()
        sql = sql_gen_new.create_sql()
        cur.execute("BEGIN;" + sql + "COMMIT;")

        self.populate_triggers()

    def remove_trigger(self):

        sql_gen = self._current_item_to_sql_generator()
        if not sql_gen:
            return

        sql = sql_gen.drop_sql()

        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("BEGIN;"+sql+"COMMIT;")

        self.populate_triggers()
