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

# based on DB Manager code

import os
import psycopg2

from qgis.core import QgsDataSourceUri, QgsCredentials
from qgis.PyQt.QtCore import QSettings


def connection_from_name(name):
    settings = QSettings()
    settings.beginGroup(u"/PostgreSQL/connections/%s" % name)

    if not settings.contains("database"):  # non-existent entry?
        raise Exception('There is no defined database connection "%s".' % name)

    settingsList = ["service", "host", "port", "database", "username", "password", "authcfg"]
    service, host, port, database, username, password, authcfg = [settings.value(x, "", type=str) for x in settingsList]

    try:
        sslmode = settings.value("sslmode", QgsDataSourceUri.SslPrefer, type=int)
    except TypeError:
        sslmode = QgsDataSourceUri.SslPrefer

    uri = QgsDataSourceUri()

    if service:
        uri.setConnection(service, database, username, password, int(sslmode), authcfg)
    else:
        uri.setConnection(host, port, database, username, password, sslmode, authcfg)

    return connection_from_uri(uri)


def connection_from_uri(uri):
    username = uri.username() or os.environ.get('PGUSER')
    password = uri.password() or os.environ.get('PGPASSWORD')

    # Do not get db and user names from the env if service is used
    if uri.service() is None:
        if username is None:
            username = os.environ.get('USER')
        dbname = uri.database() or os.environ.get('PGDATABASE') or username
        uri.setDatabase(dbname)

    expandedConnInfo = QgsDataSourceUri(uri.uri(False)).connectionInfo(True)
    try:
        connection = psycopg2.connect(expandedConnInfo)
    except Exception as e:
        err = str(e)
        uri = QgsDataSourceUri(uri.uri(False))
        conninfo = uri.connectionInfo(False)
        for i in range(3):
            (ok, username, password) = QgsCredentials.instance().get(conninfo, username, password, err)
            if not ok:
                raise Exception("???")    # why would this happen?

            if username:
                uri.setUsername(username)

            if password:
                uri.setPassword(password)
            newExpandedConnInfo = uri.connectionInfo(True)
            try:
                connection = psycopg2.connect(str(newExpandedConnInfo))
                QgsCredentials.instance().put(conninfo, username, password)
            except Exception as e:
                if i == 2:
                    raise

                err = str(e)
            finally:
                # remove certs (if any) of the expanded connectionInfo
                expandedUri = QgsDataSourceUri(newExpandedConnInfo)

                sslCertFile = expandedUri.param("sslcert")
                if sslCertFile:
                    sslCertFile = sslCertFile.replace("'", "")
                    os.remove(sslCertFile)

                sslKeyFile = expandedUri.param("sslkey")
                if sslKeyFile:
                    sslKeyFile = sslKeyFile.replace("'", "")
                    os.remove(sslKeyFile)

                sslCAFile = expandedUri.param("sslrootcert")
                if sslCAFile:
                    sslCAFile = sslCAFile.replace("'", "")
                    os.remove(sslCAFile)
    finally:
        # remove certs (if any) of the expanded connectionInfo
        expandedUri = QgsDataSourceUri(expandedConnInfo)

        sslCertFile = expandedUri.param("sslcert")
        if sslCertFile:
            sslCertFile = sslCertFile.replace("'", "")
            os.remove(sslCertFile)

        sslKeyFile = expandedUri.param("sslkey")
        if sslKeyFile:
            sslKeyFile = sslKeyFile.replace("'", "")
            os.remove(sslKeyFile)

        sslCAFile = expandedUri.param("sslrootcert")
        if sslCAFile:
            sslCAFile = sslCAFile.replace("'", "")
            os.remove(sslCAFile)

    return connection
