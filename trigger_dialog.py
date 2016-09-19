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

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from PyQt4 import uic

from sql_generator import SqlGenerator

this_dir = os.path.dirname(__file__)

WIDGET, BASE = uic.loadUiType(os.path.join(this_dir, 'trigger_dialog.ui'))


def get_table_fields(conn, schema, table):
    sql = u"""SELECT a.attnum AS ordinal_position,
                            a.attname AS column_name,
                            t.typname AS data_type,
                            a.attlen AS char_max_len,
                            a.atttypmod AS modifier,
                            a.attnotnull AS notnull,
                            a.atthasdef AS hasdefault,
                            adef.adsrc AS default_value,
                            pg_catalog.format_type(a.atttypid,a.atttypmod) AS formatted_type
                    FROM pg_class c
                    JOIN pg_attribute a ON a.attrelid = c.oid
                    JOIN pg_type t ON a.atttypid = t.oid
                    JOIN pg_namespace nsp ON c.relnamespace = nsp.oid
                    LEFT JOIN pg_attrdef adef ON adef.adrelid = a.attrelid AND adef.adnum = a.attnum
                    WHERE
                      a.attnum > 0 AND c.relname='%s' AND nspname='%s'
                    ORDER BY a.attnum""" % (table, schema)

    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def get_spatial_tables(conn):
    sql = "SELECT f_table_schema, f_table_name, f_geometry_column FROM geometry_columns"

    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


class MyDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        QStyledItemDelegate.__init__(self, parent)
        self.fields = []

    def createEditor(self, parent, option, index):
        cbo = QComboBox(parent)
        cbo.addItem("[none]")
        for field in self.fields:
            cbo.addItem(field)
        cbo.setCurrentIndex(0)
        return cbo

    def setEditorData(self, cbo, index):
        target_attr_name = index.model().data(index, Qt.DisplayRole)
        if target_attr_name in self.fields:
            cbo.setCurrentIndex(self.fields.index(target_attr_name)+1)

    def setModelData(self, cbo, model, index):
        field_name = self.fields[cbo.currentIndex()-1]
        model.setData(index, field_name, Qt.DisplayRole)


class TriggerDialog(BASE, WIDGET):
    def __init__(self, conn, sql_gen=None, parent=None):
        BASE.__init__(self, parent)
        self.setupUi(self)
        self.conn = conn    # psycopg2 connection to the DB

        self.buttonBox.accepted.connect(self.on_ok)

        self.model = QStandardItemModel()
        self.treeMapping.setModel(self.model)
        self.delegate = MyDelegate()
        self.treeMapping.setItemDelegateForColumn(1, self.delegate)

        # populate source/target layers
        self.layers = get_spatial_tables(conn)
        for schema, table, geom in self.layers:
            self.cboSource.addItem(schema + "." + table)
            self.cboTarget.addItem(schema + "." + table)

        if sql_gen is not None:
            source_schema, source_table = sql_gen.source_table.split('.')
            src_index = self.cboSource.findText(source_schema + "." + source_table)
            self.cboSource.setCurrentIndex(src_index)

            target_schema, target_table = sql_gen.target_table.split('.')
            target_index = self.cboTarget.findText(target_schema + "." + target_table)
            self.cboTarget.setCurrentIndex(target_index)

        self.cboSource.currentIndexChanged.connect(self.populate_source_attrs)
        self.cboTarget.currentIndexChanged.connect(self.populate_target_attrs)

        self.populate_source_attrs()
        self.populate_target_attrs()

        if sql_gen is not None:
            source_schema, source_table = sql_gen.source_table.split('.')
            source_field_names = [ field[1] for field in get_table_fields(self.conn, source_schema, source_table) ]
            for source_attr, target_attr in sql_gen.attr_map.iteritems():
                try:
                    source_field_index = source_field_names.index(source_attr)
                except ValueError:
                    continue  # source field not found - strange but can happen...
                item = self.treeMapping.model().item(source_field_index, 0)
                item.setCheckState(Qt.Checked)
                item2 = self.treeMapping.model().item(source_field_index, 1)
                item2.setText(target_attr)

    def populate_source_attrs(self):

        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Source field", "Target field"])

        index = self.cboSource.currentIndex()
        if index < 0:
            return

        fields = get_table_fields(self.conn, self.layers[index][0], self.layers[index][1])
        for field in fields:
            item = QStandardItem(field[1])
            item.setCheckable(True)
            item.setEditable(False)
            self.model.appendRow([item, QStandardItem("[none]")])

        self.treeMapping.resizeColumnToContents(0)

    def populate_target_attrs(self):

        index = self.cboTarget.currentIndex()
        if index < 0:
            self.delegate.fields = []
            return

        fields = get_table_fields(self.conn, self.layers[index][0], self.layers[index][1])
        self.delegate.fields = [ field[1] for field in fields ]

    def to_sql_generator(self):
        """Populate and return SqlGenerator instance from trigger dialog"""
        sql_gen = SqlGenerator()
        sql_gen.source_table = self.cboSource.currentText()
        sql_gen.target_table = self.cboTarget.currentText()
        # mapping
        sql_gen.attr_map = {}
        for row in xrange(self.model.rowCount()):
            if self.model.item(row, 0).checkState() == Qt.Checked:
                source_attr = self.model.item(row, 0).text()
                target_attr = self.model.item(row, 1).text()
                sql_gen.attr_map[source_attr] = target_attr
        return sql_gen

    def on_ok(self):
        """ Do some sanity checks before accepting the dialog """

        if self.cboSource.currentText() == self.cboTarget.currentText():
            QMessageBox.warning(self, "Warning", "Source and target tables must be different.")
            return

        # at least one attribute must be checked
        has_checked_item = False
        has_chosen_target_attrs = True
        for row in xrange(self.model.rowCount()):
            if self.model.item(row, 0).checkState() == Qt.Checked:
                has_checked_item = True

                if self.model.item(row, 1).text() == "[none]":
                    has_chosen_target_attrs = False

        if not has_checked_item:
            QMessageBox.warning(self, "Warning", "At least one attribute must be checked.")
            return

        if not has_chosen_target_attrs:
            QMessageBox.warning(self, "Warning", "All checked attributes must have a target attribute.")
            return

        self.accept()
