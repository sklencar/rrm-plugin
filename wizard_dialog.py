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

import sql_generator
import trigger_dialog
from sql_generator import SqlGenerator

this_dir = os.path.dirname(__file__)

WIDGET, BASE = uic.loadUiType(os.path.join(this_dir, 'wizard_dialog.ui'))


class WizardDialog(BASE, WIDGET):
    def __init__(self, conn, parent=None):
        BASE.__init__(self, parent)
        self.setupUi(self)

        self.conn = conn

        self.table_model = QStandardItemModel()
        self.tableView.setModel(self.table_model)

        for schema_oid, schema_name in trigger_dialog.get_schemas(conn):
            self.cboSourceSchema.addItem(schema_name)
            self.cboTargetSchema.addItem(schema_name)

        self.ignore_attr = sql_generator.list_uic_geom_fields(self.conn)

        self.cboSourceSchema.currentIndexChanged.connect(self.populate_tables)
        self.cboTargetSchema.currentIndexChanged.connect(self.populate_tables)

        self.tableFld.textChanged.connect(self.populate_tables)
        self.tableFld.setVisible(self.cboTablesOpt.currentIndex() != 0)
        self.cboTablesOpt.currentIndexChanged.connect(self.table_search_option_changed)

        self.attrFld.textChanged.connect(self.populate_tables)
        self.attrFld.setVisible(self.cboFieldsOpt.currentIndex() != 0)
        self.cboFieldsOpt.currentIndexChanged.connect(self.field_search_option_changed)

        self.layers = trigger_dialog.get_spatial_tables(conn)
        self.doSampleCheck.setCheckState(Qt.Checked)
        self.doSampleCheck.stateChanged.connect(self.populate_tables)

        self.populate_tables()

    def table_search_option_changed(self, index):
        self.tableFld.setVisible(index != 0)
        self.populate_tables()

    def field_search_option_changed(self, index):
        self.attrFld.setVisible(index != 0)
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

            result.append(item)
            ix += 1
        return result

    def update_table_model(self, pairs):
        self.table_model.clear()
        self.table_model.setHorizontalHeaderLabels(["Source", "Target"])
        ix = -1

        for source, target in pairs:
            ix += 1
            item_0 = QStandardItem(source)
            item_0.setCheckable(True)
            item_0.setCheckState(Qt.Checked)
            item_1 = QStandardItem(target)
            for i in [item_0, item_1]:
                i.setEditable(False)
            self.table_model.appendRow([item_0, item_1])

        self.tableView.resizeColumnToContents(0)

    def populate_tables(self):
        tabs1 = self.get_tables(self.cboSourceSchema.currentText())
        tabs2 = self.get_tables(self.cboTargetSchema.currentText())

        prefix_source = self.tableFld.text() if self.cboTablesOpt.currentIndex() == 1 else ""
        suffix_source = self.tableFld.text() if self.cboTablesOpt.currentIndex() == 2 else ""
        prefix_target = self.tableFld.text() if self.cboTablesOpt.currentIndex() == 3 else ""
        suffix_target = self.tableFld.text() if self.cboTablesOpt.currentIndex() == 4 else ""

        tab11, tab22 = self.get_similar(tabs1, tabs2, prefix_source, suffix_source, prefix_target, suffix_target)

        source = [elem for (elem, schema) in tab11]
        target = [elem for (elem, schema) in tab22]

        pairs = [(source[ix], target[ix]) for ix in range(len(source))]
        self.update_table_model(pairs)
        self.populate_attr(pairs)
        self.tableView.resizeColumnToContents(0)

    def populate_attr(self, pairs):

        all_field_pairs = {}
        for source_tab, target_tab in pairs:
            fields1 = self.get_attr(self.cboSourceSchema.currentText(), source_tab)
            fields2 = self.get_attr(self.cboTargetSchema.currentText(), target_tab)

            prefix_source = self.attrFld.text() if self.cboFieldsOpt.currentIndex() == 1 else ""
            suffix_source = self.attrFld.text() if self.cboFieldsOpt.currentIndex() == 2 else ""
            prefix_target = self.attrFld.text() if self.cboFieldsOpt.currentIndex() == 3 else ""
            suffix_target = self.attrFld.text() if self.cboFieldsOpt.currentIndex() == 4 else ""

            tab11, tab22 = self.get_similar(fields1, fields2, prefix_source,suffix_source, prefix_target, suffix_target)

            source = [elem for (elem, schema) in tab11]
            target = [elem for (elem, schema) in tab22]

            field_pairs = [(source[ix], target[ix]) for ix in range(len(source))]
            all_field_pairs[source_tab] = field_pairs

        self.update_field_model(all_field_pairs)

    def get_attr(self, schema, table):
        fields = trigger_dialog.get_table_fields(self.conn, schema, table)
        return [elem[1] for elem in fields if self.is_not_ignored_attr(elem[1], schema, table)]

    def is_not_ignored_attr(self, item, schema, table):
        if self.doSampleCheck.isChecked():
            return schema + '.' + table not in self.ignore_attr.keys() or item not in self.ignore_attr[schema + '.' + table]
        else:
            return True

    def get_similar(self, tabs1, tabs2, prefix1, suffix1, prefix2, suffix2):
        fil_tab1 = self.filter_prefix_suffix(tabs1, prefix1, suffix1)
        fil_tab2 = self.filter_prefix_suffix(tabs2, prefix2, suffix2)
        pairs = []
        for ix in range(len(fil_tab1)):
            item = fil_tab1[ix]
            if item in fil_tab2:
                if not self.have_prefix_suffix(tabs1[ix], tabs2[fil_tab2.index(item)], prefix1, suffix1, prefix2,
                        suffix2): continue
                pairs.append((ix, fil_tab2.index(item)))
        tab11 = [(tabs1[ix], self.cboSourceSchema.currentText()) for ix, ix2 in pairs]
        tab22 = [(tabs2[ix2], self.cboTargetSchema.currentText()) for ix, ix2 in pairs]
        return tab11, tab22

    def have_prefix_suffix(self, src, trg, prefix1, suffix1, prefix2, suffix2):
        return prefix1 in src and suffix1 in src and prefix2 in trg and suffix2 in trg

    def get_tables(self, current_schema):
        tables = []
        for schema, table, geom in self.layers:
            if schema == current_schema:
                tables.append(table)
        return tables

    def update_field_model(self, pairs):
        row = self.table_model.rowCount()
        for ix in range(0, row):
            content = self.table_model.data(self.table_model.index(ix, 0))
            related_table_item = self.table_model.item(ix)
            if content in pairs:
                attrs = pairs[content]
                #if self.is_uic_attr(attrs): continue

                for source, target in attrs:
                    item_0 = QStandardItem(source)
                    item_0.setCheckable(True)
                    item_0.setCheckState(Qt.Checked)
                    item_1 = QStandardItem(target)
                    for i in [item_0, item_1]:
                        i.setEditable(False)
                    related_table_item.appendRow([item_0, item_1])
    # def is_uic_attr(self, attrs):
    #     source = attrs[0]
    #     target = attrs[1]



    def single_sgl_generator(self, source_table, target_table, parent_item):
        sql_gen = SqlGenerator()
        sql_gen.source_table = self.cboSourceSchema.currentText() + "." + source_table
        sql_gen.target_table = self.cboTargetSchema.currentText() + "." + target_table
        # mapping
        sql_gen.attr_map = {}

        for ix in range(0,parent_item.rowCount()):
            if not parent_item.checkState() == Qt.Checked: continue

            if parent_item.child(ix, 0).checkState() == Qt.Checked:
                source_attr = parent_item.child(ix, 0).text()
                target_attr = parent_item.child(ix, 1).text()
                sql_gen.attr_map[source_attr] = target_attr
        if sql_gen.attr_map:
            return sql_gen
        else:
            return None

    def to_sql_generator(self):
        generators = []
        for row in xrange(self.table_model.rowCount()):
            item = self.table_model.item(row)
            source_table = item.text()
            target_table = self.table_model.item(row, 1).text()
            if item.hasChildren():
                gen = self.single_sgl_generator(source_table, target_table, item)
                if gen:
                    generators.append(gen)

        return generators

