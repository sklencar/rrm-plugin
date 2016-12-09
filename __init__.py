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

from config_dialog import ConfigDialog

this_dir = os.path.dirname(__file__)

def classFactory(iface):
    return PostGIS_SamplingToolPlugin(iface)

class PostGIS_SamplingToolPlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction(QIcon(os.path.join(this_dir, 'icon.svg')), u'Configure PostGIS Sampling Tool', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def run(self):
        dlg = ConfigDialog()
        dlg.exec_()

