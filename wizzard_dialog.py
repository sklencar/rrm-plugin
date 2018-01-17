# encoding: utf-8
# -----------------------------------------------------------
# Copyright (C) 2017 Viktor Sklencar
# -----------------------------------------------------------
# Licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# ---------------------------------------------------------------------

import os

from PyQt4 import uic
from PyQt4.QtCore import *

from PyQt4.QtGui import QStandardItemModel, QStandardItem

import trigger_dialog

this_dir = os.path.dirname(__file__)

WIDGET, BASE = uic.loadUiType(os.path.join(this_dir, 'wizzard_dialog.ui'))


class WizzardDialog(BASE, WIDGET):
    def __init__(self, conn, parent=None):
        BASE.__init__(self, parent)
        self.setupUi(self)

        self.conn = conn

        self.table_model = QStandardItemModel()
        self.tableView.setModel(self.table_model)

        self.field_model = QStandardItemModel()
        self.fieldView.setModel(self.field_model)

        self.delegate = trigger_dialog.MyDelegate()
        self.fieldView.setItemDelegateForColumn(1, self.delegate)

        for schema_oid, schema_name in trigger_dialog.get_schemas(conn):
            self.cboSourceSchema.addItem(schema_name)
            self.cboTargetSchema.addItem(schema_name)

        self.cboSourceSchema.currentIndexChanged.connect(self.populate_tables)
        self.cboTargetSchema.currentIndexChanged.connect(self.populate_tables)
        self.prefixSourceFld.textChanged.connect(self.populate_tables)
        self.suffixSourceFld.textChanged.connect(self.populate_tables)
        self.prefixTargetFld.textChanged.connect(self.populate_tables)
        self.suffixTargetFld.textChanged.connect(self.populate_tables)

        self.layers = trigger_dialog.get_spatial_tables(conn)
        self.populate_tables()

    # TODO support for regex??
    def filter_prefix_suffix(self, list, prefix, suffix):
        result = []
        ix = 0
        for item in list:
            if prefix and item.startswith(prefix):
                item = item.replace(prefix, "", 1)
            if suffix and item.endswith(suffix):
                item = "".join(item.rsplit(suffix, 1))

            result.append((item, ix))
            ix += 1
        return result

    def update_table_model(self):
        self.table_model.clear()
        self.table_model.setHorizontalHeaderLabels(["ID", "Tables", "Origin"])
        index = -1
        for table, origin in self.tables:
            index += 1
            # if not _filter_accepts(source_table) and not _filter_accepts(target_table):
            #     continue
            # TODO get rid of ID
            item_0 = QStandardItem(str(index))
            item_0.setData(index)  # store index of the item in self.triggers (used in _current_item_to_generator)
            item_1 = QStandardItem(table)
            item_1.setCheckable(True)
            item_2 = QStandardItem(origin)
            for i in [item_0, item_1, item_2]:
                i.setEditable(False)
            self.table_model.appendRow([item_0, item_1, item_2])

        self.tableView.resizeColumnToContents(1)

    def populate_tables(self):
        tabs1 = self.get_tables(self.cboSourceSchema.currentText())
        tabs2 = self.get_tables(self.cboTargetSchema.currentText())

        tab11, tab22 = self.get_similar(tabs1, tabs2, self.prefixSourceFld.text(), self.suffixSourceFld.text(), self.prefixTargetFld.text(), self.suffixTargetFld.text())
        self.tables = tab11 + tab22
        self.update_table_model()

        source = [elem for (elem, schema) in tab11]
        target = [elem for (elem, schema) in tab22]

        self.populate_attr(source, target)

    def populate_attr(self, source_tabs, target_tabs):
        fields1 = self.get_attr(self.cboSourceSchema.currentText(), source_tabs)
        fields2 = self.get_attr(self.cboTargetSchema.currentText(), target_tabs)

        tab11, tab22 = self.get_similar(fields1, fields2, self.prefixSourceAttr.text(), self.suffixSourceAttr.text(),
                                        self.prefixTargetAttr.text(), self.suffixTargetAttr.text())
        self.update_field_model(tab11, tab22)

    def get_attr(self, schema, tables):
        all_fields = []
        for table in tables:
            fields = trigger_dialog.get_table_fields(self.conn, schema, table)
            fields_name = [elem[1] for elem in fields]
            all_fields.append(fields_name)


        filtered_fields = self.get_elems_occured_in_all(all_fields)
        return list(filtered_fields)

    def get_elems_occured_in_all(self, lists):
        sets = list(map(set, lists))
        if not sets: return []

        result = sets[0]
        for s in sets:
            result = result.intersection(s)
        return result

    def get_similar(self, tabs1, tabs2, prefix1, suffix1, prefix2, suffix2):
        fil_tab1 = self.filter_prefix_suffix(tabs1, prefix1, suffix1)
        fil_tab2 = self.filter_prefix_suffix(tabs2, prefix2, suffix2)
        tab11 = [(tabs1[ix], self.cboSourceSchema.currentText()) for (item, ix) in fil_tab1 if
                 item in [i for (i, ixx) in fil_tab2]]
        tab22 = [(tabs2[ix], self.cboTargetSchema.currentText()) for (item, ix) in fil_tab2 if
                 item in [i for (i, ixx) in fil_tab1]]
        return tab11, tab22

    def get_tables(self, current_schema):
        tables = []
        for schema, table, geom in self.layers:
            if schema == current_schema:
                tables.append(table)
        return tables

    def get_selected_tables(self):
        selection = []
        table_name_id = 1
        for row in xrange(self.table_model.rowCount()):
            if self.table_model.item(row, table_name_id).checkState() == Qt.Checked:
                selection.append(self.model.item(row, table_name_id).text())

        return selection

    # TODO refactor with trigger dialog
    # todo run when selection has changed
    def update_field_model(self, source_fields, target_fields):

        self.field_model.clear()
        self.field_model.setHorizontalHeaderLabels(["Source field", "Target field"])

        # TODO handle if not same length
        if len(source_fields) != len(target_fields): return

        for ix, field in enumerate(source_fields):
            item = QStandardItem(field[0])
            item.setCheckable(True)
            item.setEditable(False)

            item1 = QStandardItem(target_fields[ix][0])
            item1.setEditable(False)
            self.field_model.appendRow([item, item1])

        self.fieldView.resizeColumnToContents(0)

    def filter_function2(self, list, prefix, suffix, com_list):
        result = []
        for item in list:
            i = item
            if prefix and i.startswith(prefix):
                i = i.replace(prefix, "", 1)
            if suffix and item.endswith(suffix):
                i = "".join(i.rsplit(suffix, 1))
            if i in com_list:
                result.append(item)
        return result
