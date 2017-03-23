#!/usr/bin/env python3
# -*- coding: ascii -*-

import _thread
import asyncore
import base64
import datetime
import email
import glob
import html
import logging
import mailbox
import operator
import os
import pprint
import queue
import re
import socket
import subprocess
import sys
import threading
import traceback
from email.header import decode_header, Header
from email.utils import parsedate_tz, mktime_tz
from functools import wraps
from time import sleep
from time import time

import smtpd

import lxml as lxml
from PyQt5 import QtCore, QtGui, QtWidgets, QtPrintSupport
from lxml.html.clean import Cleaner
import cutesmtp_icons
from valid_encodings import VALID_ENCODINGS
import pickle as pickle

__all__ = ['cutesmtp_icons',
           'SmtpMailsinkServer',
           'EmailParser']

DEBUG_SMTP = True
DEBUG_APP = False
DEFAULT_PORT = 1025
DISABLE_APPSTATE = False
APPNAME = 'Cute Pie SMTP Daemon'
VERSION = '0.17.3.2221 (pyqt5)'
DEFAULT_MBOX_PATH = 'mailbox.mbox'
POLLING_TIME_MILLISECS = 1000
PICKLE_FILE_NAME = "app_cache.appstate"
PICKLE_IS_LOADED = False
PICKLE_STATE_DIRTY = False
INDEX_HIDDEN_METADATA = 3  # hidden row for message storage
LOG_FILE_NAME = 'app.log'

LOG = None  # type: logging.Logger

tableview_data = []  # type: list


def timed(f):
    """
    Metrics for method execution
    :param f: function
    """

    @wraps(f)
    def wrapper(*args, **kwds):
        start = time()
        result = f(*args, **kwds)
        elapsed = time() - start
        LOG.debug("method %s() took %.6f seconds to complete" % (f.__name__, elapsed))
        return result

    return wrapper


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.actionLogToFileEnabled = None

        self.appdata_dir = None
        self.attachments_dir = None
        self.last_saved_sort_column = None
        self.last_saved_sort_order = None
        self.last_used_fileopen_folder = None
        self.actionLogToFileEnabled = None

        self.iconSwitch = QtGui.QIcon(':/icons/switch.png')
        self.setWindowIcon(self.iconSwitch)

        # window size and position
        self.setGeometry(100, 150, 500, 660)
        self.read_settings()

        init_logging(log_file_dir=self.appdata_dir, log_to_file=self.is_log_file_enabled)
        self.init_folders()

        self.textEdit = QtWidgets.QTextEdit()
        self.textEdit.setReadOnly(True)

        self.setCentralWidget(self.textEdit)

        self.createActions()
        self.createMenus()
        self.createToolBars()
        self.createStatusBar()
        self.createDockWindows()
        self.createAttachmentsMenuItems()
        self.setWindowTitle("%s - %s" % (APPNAME, self.mbox_path))

        self.topDock.setWindowTitle(" SMTP status: localhost:%s OFF" % self.port)

        self.setUnifiedTitleAndToolBarOnMac(True)
        self.mailsync = None
        self.attachment_buttons = None
        self.attachment_icon = QtGui.QIcon(':/icons/attached.png')

        if self.isSmtpAutostartEnabled:
            self.toggle_smtp_server_state(start=True)

        if self.is_toolbar_hidden:
            self.actionToggleToolbar.setChecked(True)
            self.on_toggle_toolbar()

        if self.isHtmlCleaningEnabled:
            self.actionCleanHtmlToggle.setChecked(True)

        EmailParser.cleaning_is_enabled = self.isHtmlCleaningEnabled

        self.pickle_storage_path = os.path.join(self.appdata_dir, PICKLE_FILE_NAME)
        self.initialize_data()  # here data init is happening
        self.restore_column_sort_mode()

    def restart_as_root(self):
        euid = os.geteuid()
        if euid != 0:
            reply = QtWidgets.QMessageBox.question(self, APPNAME,
                                                   "Script not running as root. Restart with root permissions?",
                                                   QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                executable = getattr(sys, 'frozen', False) and sys.argv[0] or sys.executable

                args = ['sudo', executable] + sys.argv + [os.environ]
                # the next line replaces the currently-running process with the sudo
                if sys.platform.startswith('darwin'):
                    executable = os.path.abspath(executable)
                    print(executable, type(executable))

                    os.execlpe('osascript',
                               'osascript',
                               '-e',
                               "do shell script \"python /Users/vio/projects/cutesmtpdaemon/cutepiesmtpdaemon.py\" with administrator privileges",
                               os.environ)
                else:
                    os.execlpe('sudo', *args)

    def init_folders(self):
        userhome = os.path.expanduser("~")

        self.appdata_dir = os.path.join(userhome, APPNAME)
        self.attachments_dir = os.path.join(self.appdata_dir, "attachments")

        create_folder_if_not_exists(self.appdata_dir)
        create_folder_if_not_exists(self.attachments_dir)

        if not self.mbox_path or not os.path.exists(self.mbox_path):

            default_mbox_path = os.path.join(self.appdata_dir, DEFAULT_MBOX_PATH)

            if not os.path.exists(default_mbox_path):
                with (open(default_mbox_path, 'w')) as f:
                    pass
                self.mbox_path = default_mbox_path

    def print_(self):

        selected_indexes = self.tableView.selectionModel().selectedRows()

        if not len(selected_indexes):
            QtWidgets.QMessageBox.warning(self, APPNAME,
                                          "Please select a message first")
            return

        document = self.textEdit.document()
        printer = QtPrintSupport.QPrinter()

        dlg = QtPrintSupport.QPrintDialog(printer, self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        document.print_(printer)

        self.statusBar().showMessage("Ready", 2000)

    @timed
    def on_open_raw_message(self, row_index=None, extension='txt'):
        """ open raw message body in default text editor """

        if not row_index:
            selected_indexes = self.tableView.selectionModel().selectedRows()

            if len(selected_indexes):
                row_index = selected_indexes[0].row()
            else:
                show_gui_error("No message selected", "Please select a message first!")
                return

        meta_data = tableview_data[row_index][INDEX_HIDDEN_METADATA]
        raw_body = meta_data.message

        raw_message_path = os.path.join(self.appdata_dir, "message.tmp.%s.%s" % (time(), extension))

        try:
            with open(raw_message_path, 'wb') as attachmentFile:
                attachmentFile.write(bytes(raw_body))
                sleep(0.2)
        except IOError as e:
            show_gui_error(e, 'Cannot create file: %s' % raw_message_path)
            return
        self.start_file(raw_message_path)

    def save_binary_file(self, caption=None, fname=None, bytes=None):
        filename, __ = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             caption, os.path.join(self.attachments_dir, fname), '*.*')

        if not filename:
            return

        qFile = QtCore.QFile(filename)

        if not qFile.open(QtCore.QFile.WriteOnly | QtCore.QFile.ReadWrite):
            QtWidgets.QMessageBox.warning(self, APPNAME,
                                          "Cannot create file: %s\n%s." % (filename, qFile.errorString()))
            return

        with open(filename, 'wb') as file_handle:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            file_handle.write(bytes)
            QtWidgets.QApplication.restoreOverrideCursor()

        self.statusBar().showMessage("Saved '%s'" % filename, 2000)

    def save_generated_html(self):

        selected_indices = self.tableView.selectionModel().selectedRows()

        if not len(selected_indices):
            QtWidgets.QMessageBox.warning(self, APPNAME,
                                          "Please select a message first")
            return

        filename, __ = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             "Saving current message in HTML format...", '.',
                                                             "HTML (*.html *.htm)")
        if not filename:
            return

        file_name = QtCore.QFile(filename)

        if not file_name.open(QtCore.QFile.WriteOnly | QtCore.QFile.Text):
            QtWidgets.QMessageBox.warning(self, APPNAME,
                                          "Cannot write file_name %s:\n%s." % (filename, file_name.errorString()))
            return

        out = QtCore.QTextStream(file_name)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        out << self.textEdit.toHtml()
        QtWidgets.QApplication.restoreOverrideCursor()

        self.statusBar().showMessage("Saved '%s'" % filename, 2000)

    def on_about(self):
        QtWidgets.QMessageBox.about(self, "About",
                                    "X-Mailer: %s<br/><br/>"
                                    "X-Version: %s<br/><br/>"
                                    "From: <a href='mailto:booleanbaby@gmail.com?Subject=CutePieSmtpDaemon'>booleanbaby@gmail.com</a><br/><br/>"
                                    "Subject: For a moment, nothing happened.&nbsp;Then, after a second or so, nothing continued to happen...<br/><br/>"
                                    "Cute SMPT Daemon is a fake SMTP server created for debugging and development purposes.<br/>"
                                    "The app listens on localhost, intercepts email messages, and writes them to a standard Unix mailbox file.<br/>"
                                    "The app can also open an existing Unix mailbox file "
                                    "or raw email messages in EML/MSG format.<br/>"
                                    "To strip styles and scripts from the HTML messages use Config &gt; 'Enable HTML cleaning'<br/>"
                                    "%s is capable of extracting and saving attachments from mailboxes or from EML/MSG files.<br/>"
                                    "Running the SMTP server on port 25 requires root priveleges. To run as a regular user, set a port "
                                    "higher than 1024, and configure your email clients to use that port.<br/><br/> "
                                    "X-Dedicated-To: Douglas Adams" % (APPNAME, VERSION, APPNAME))

    def createActions(self):
        """
        # ICONS http://standards.freedesktop.org/icon-naming-spec/icon-naming-spec-latest.html

        SHORTCUTS MAPPING: http://pyqt.sourceforge.net/Docs/PyQt4/qkeysequence.html
        """
        self.actionNewMboxFile = QtWidgets.QAction(QtGui.QIcon(':/icons/new.png'),
                                                   "Create &New mailbox", self,
                                                   shortcut=QtGui.QKeySequence.New,
                                                   statusTip="Create new mailbox file",
                                                   triggered=self.create_new_mbox)
        self.actionNewMboxFile.setIconText("New")

        self.actionSmtpToggle = QtWidgets.QAction(self.iconSwitch,
                                                  "Start/Stop SMTP", self,
                                                  shortcut=QtGui.QKeySequence.MoveToStartOfDocument,
                                                  statusTip="Start/Stop SMTP server",
                                                  triggered=self.toggle_smtp_server_state,
                                                  checkable=True)
        self.actionSmtpToggle.setIconText("SMTP")

        self.actionSmtpAutostartToggle = QtWidgets.QAction(self.iconSwitch,
                                                           "&Autostart SMTP server", self,
                                                           statusTip="Autostart SMTP server",
                                                           triggered=self.update_smtp_autostart_setting,
                                                           checkable=True)
        self.actionSmtpAutostartToggle.setChecked(self.isSmtpAutostartEnabled)
        self.actionSmtpAutostartToggle.setIconText("SMTP autostart")

        self.actionSaveHtml = QtWidgets.QAction(QtGui.QIcon(':/icons/device.png'),
                                                "&Save HTML for selected message", self,
                                                shortcut=QtGui.QKeySequence.Save,
                                                statusTip="Save rendered HTML for the selected message",
                                                triggered=self.save_generated_html)
        self.actionSaveHtml.setIconText("Save")

        self.actionShowRowMessage = QtWidgets.QAction(
            "Open &raw message as text...", self,
            shortcut=QtGui.QKeySequence.Forward,
            statusTip="Open raw email message as text",
            triggered=lambda: self.on_open_raw_message(extension='txt'))

        self.actionToggleToolbar = QtWidgets.QAction(
            "Hide toolbar...", self,
            shortcut=QtGui.QKeySequence.Bold,
            statusTip="Show or hide toolbar",
            triggered=self.on_toggle_toolbar,
            checkable=True)

        self.actionLogToFileEnabled = QtWidgets.QAction(
            "Enable logging to file", self,
            statusTip="Enable logging to file",
            triggered=self.on_logging_enabled,
            checkable=True)
        self.actionLogToFileEnabled.setChecked(self.is_log_file_enabled)

        self.actionOpenMessage = QtWidgets.QAction("Open message with default &email app", self,
                                                   shortcut=QtGui.QKeySequence.InsertParagraphSeparator,
                                                   statusTip="Open message with default email app",
                                                   triggered=lambda: self.on_open_raw_message(extension='eml'))

        self.actionPrint = QtWidgets.QAction(QtGui.QIcon(':/icons/printer.png'),
                                             "&Print selected message...", self,
                                             shortcut=QtGui.QKeySequence.Print,
                                             statusTip="Print the selected message",
                                             triggered=self.print_)
        self.actionPrint.setIconText("Print")

        self.quitAct = QtWidgets.QAction("&Quit", self,
                                         statusTip="Quit the application", triggered=self.close)

        self.actionAbout = QtWidgets.QAction("X-About", self,
                                             statusTip="Show the About box",
                                             triggered=self.on_about)

        # self.aboutAct = QtWidgets.QAction("About this app", self,
        #         statusTip="Show the application's About box",
        #         triggered=self.on_about)

        self.actionSetPort = QtWidgets.QAction("SMTP port", self,
                                               statusTip="Set SMTP port",
                                               triggered=self.set_port)

        self.actionCleanHtmlToggle = QtWidgets.QAction("Enable HTML cleaning", self,
                                                       statusTip="Enabling will remove all styling from the markup",
                                                       checkable=True,
                                                       triggered=self.update_html_clean_setting)
        self.actionCleanHtmlToggle.setChecked(self.isHtmlCleaningEnabled)

        # ACTIONS FOR ATTACHMENT CONTEXT MENU
        self.actionAttachmentSave = QtWidgets.QAction("Save &attachment", self,
                                                      statusTip="Save attachment to file",
                                                      triggered=self.on_attachment_context_menu_selection)

        self.actionAttachmentOpen = QtWidgets.QAction("Open attachment with associated program", self,
                                                      statusTip="Open attachment with system default application",
                                                      triggered=self.on_attachment_context_menu_selection)

        self.actionAttachmentOpenAsText = QtWidgets.QAction("Open attachment as text", self,
                                                            statusTip="Open attachment as plain text",
                                                            triggered=self.on_attachment_context_menu_selection)

        self.actionOpenMboxFile = QtWidgets.QAction(QtGui.QIcon(':/icons/open.png'),
                                                    "Open Mailbox", self,
                                                    shortcut=QtGui.QKeySequence.Open,
                                                    statusTip="Open mailbox file",
                                                    triggered=self.on_open_file)
        self.actionOpenMboxFile.setIconText("Open")

    def set_port(self):
        int_value, ok = QtWidgets.QInputDialog.getInt(self,
                                                          "SMTP port", "Enter SMTP port:", self.port)
        if ok:
            self.port = int_value
            self.statusBar().showMessage('Set SMTP port to %s' % self.port)
            self.topDock.setWindowTitle(" SMTP status: localhost:%s OFF" % self.port)

    def on_logging_enabled(self):
        if self.actionLogToFileEnabled.isChecked():
            QtWidgets.QMessageBox.information(self, APPNAME, "Enabled logging to {}".format(
                os.path.join(self.appdata_dir, LOG_FILE_NAME)))

    def on_open_file(self, filePath=None):

        global PICKLE_STATE_DIRTY

        if not filePath:
            filePath, __ = QtWidgets.QFileDialog.getOpenFileName(self,
                                                                 "Select a Mailbox/EML/MSG file...",
                                                                 self.last_used_fileopen_folder or os.path.dirname(
                                                                     self.mbox_path),
                                                                 "All Files (*)")
        if filePath:
            self.last_used_fileopen_folder = os.path.dirname(filePath)

            if filePath.lower().endswith('.eml') or filePath.lower().endswith('.msg'):
                with open(filePath, 'r') as fh:
                    msg = email.message_from_file(fh)
                    self.add_single_email_item(msg, True)
                    fh.seek(0)
                    QtWidgets.QMessageBox.information(self, APPNAME, "Single email message selected."
                                                                     "It will be appended to the current mailbox.")
                    mbox_write_item(self.mbox_path, msg['From'], fh.read())
                    PICKLE_STATE_DIRTY = True
                return

            self.textEdit.setHtml("")
            self.mbox_path = filePath
            self.write_settings()
            self.statusBar().showMessage('Mailbox: %s' % self.mbox_path)

            del tableview_data[:]
            self.parse_email_items()
            PICKLE_STATE_DIRTY = True
            self.setWindowTitle("%s - %s" % (APPNAME, self.mbox_path))

    def update_html_clean_setting(self):
        self.isHtmlCleaningEnabled = self.actionCleanHtmlToggle.isChecked()
        EmailParser.cleaning_is_enabled = self.isHtmlCleaningEnabled
        self.write_settings()

    def on_toggle_toolbar(self):
        self.is_toolbar_hidden = self.actionToggleToolbar.isChecked()
        self.toolBar.setVisible(not self.is_toolbar_hidden)

    def update_smtp_autostart_setting(self):
        self.isSmtpAutostartEnabled = self.actionSmtpAutostartToggle.isChecked()
        self.write_settings()

    def toggle_smtp_server_state(self, start=False):

        if self.port < 1024 and os.name != 'nt' and os.geteuid() != 0:
            QtWidgets.QMessageBox.warning(self, "Not running as root",
                                          "You must be root in order to run the SMTP server on port %s (current UID=%s).\n"
                                          "To run as regular user set a port higher than 1024 in the Config menu" % (
                                          self.port, os.geteuid()))
            self.statusBar().showMessage('Failed starting SMTP server')
            return

        if start:
            self.queueSmtpResult = queue.Queue()

            try:
                self.mailsync = SmtpMailsink(host="0.0.0.0", port=self.port, mailboxFilePath=self.mbox_path,
                                             mailQueue=self.queueSmtpResult)
            except PortAlreadyInUseException as e:
                QtWidgets.QMessageBox.warning(None, APPNAME,
                                              "SMTP port %d is already in use\n\n%s" % (self.port, str(e)))
                return

            self.mailsync.start()
            self.topDock.setWindowTitle(" smtp@0.0.0.0:%s ON" % self.port)

            #     set polling for new messages every 1 sec
            self.poller = EmailPoller()
            self.poller.set_queue(self.queueSmtpResult)
            self.poller.set_handler(self.add_single_email_item)
            self.poller.start()

            self.actionSmtpToggle.setChecked(True)

        elif self.mailsync and self.mailsync.isAlive():
            self.mailsync.stop()
            self.topDock.setWindowTitle(" smtp@0.0.0.0:%s OFF" % self.port)
            self.poller.stop()
            # self.actionSmtpToggle.setIconText("&Start SMTP")

    def createMenus(self):

        self.setMenuBar(QtWidgets.QMenuBar())
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.actionNewMboxFile)
        self.fileMenu.addAction(self.actionOpenMboxFile)
        # self.fileMenu.addAction(self.actionSmtpToggle)
        self.fileMenu.addAction(self.actionPrint)
        self.fileMenu.addAction(self.quitAct)

        self.editMenu = self.menuBar().addMenu("&Edit")
        self.editMenu.addAction(self.actionSaveHtml)
        self.editMenu.addAction(self.actionOpenMessage)
        self.editMenu.addAction(self.actionShowRowMessage)

        self.viewMenu = self.menuBar().addMenu("&View")
        self.viewMenu.addAction(self.actionToggleToolbar)

        self.smtpMenu = self.menuBar().addMenu("&SMTP")
        self.smtpMenu.addAction(self.actionSmtpToggle)

        self.configMenu = self.menuBar().addMenu("&Config")
        self.configMenu.addAction(self.actionSetPort)
        self.configMenu.addAction(self.actionSmtpAutostartToggle)
        self.configMenu.addAction(self.actionCleanHtmlToggle)
        self.configMenu.addAction(self.actionLogToFileEnabled)

        self.helpMenu = self.menuBar().addMenu("&Help")
        self.helpMenu.addAction(self.actionAbout)

    def createAttachmentsMenuItems(self):
        # ATTACHMENT RIGHT-CLICK CONTEXT MENU
        self.attachmentContextMenu = QtWidgets.QMenu(self)
        self.attachmentContextMenu.addAction(self.actionAttachmentOpen)
        self.attachmentContextMenu.addAction(self.actionAttachmentOpenAsText)
        self.attachmentContextMenu.addAction(self.actionAttachmentSave)

    def createToolBars(self):
        self.toolBar = self.addToolBar("&File")
        self.toolBar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)

        self.toolBar.addAction(self.actionNewMboxFile)
        self.toolBar.addAction(self.actionOpenMboxFile)
        self.toolBar.addAction(self.actionSmtpToggle)
        self.toolBar.addAction(self.actionSaveHtml)
        self.toolBar.addAction(self.actionPrint)

    def createStatusBar(self):
        self.statusBar().showMessage("Ready")

    def createDockWindows(self):
        self.topDock = QtWidgets.QDockWidget(self)
        self.topDock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable)
        self.topDock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea
                                     | QtCore.Qt.RightDockWidgetArea
                                     | QtCore.Qt.TopDockWidgetArea
                                     | QtCore.Qt.BottomDockWidgetArea)

        self.tableView = EmailTableView()
        self.tableView.addAction(self.actionSaveHtml)
        self.tableView.addAction(self.actionShowRowMessage)
        self.tableView.addAction(self.actionOpenMessage)
        self.tableView.setAppWindowHandle(self)

        self.tableView.setSelectionMode(QtWidgets.QTableView.SingleSelection)
        self.topDock.setWindowTitle(" %s" % self.mbox_path)

        self.topDock.setWidget(self.tableView)
        self.tableView.selectionModel().selectionChanged.connect(self.onListItemSelect)
        self.tableView.doubleClicked.connect(self.onListItemDoubleClick)

        # self.tableView.connect(self.tableView, QtCore.SIGNAL("doubleClicked(QtCore.QModelIndex)"),
        #                        self.tableView, QtCore.SLOT("self.onListItemDoubleClick(QtCore.QModelIndex)"))
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.topDock)

        self.bottomDock = QtWidgets.QDockWidget("", self)
        self.bottomDock.setFeatures(QtWidgets.QDockWidget.DockWidgetVerticalTitleBar)
        self.bottomDock.setTitleBarWidget(QtWidgets.QWidget(self.bottomDock))
        # self.bottomDock.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable)
        self.bottomDock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea | QtCore.Qt.RightDockWidgetArea)

        ## hide initially
        self.bottomDock.hide()
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.bottomDock)

    @timed
    def initialize_data(self):
        global tableview_data, PICKLE_IS_LOADED

        if not DISABLE_APPSTATE and os.path.exists(self.pickle_storage_path):
            LOG.debug('Appstate file found at %s, loading...' % self.pickle_storage_path)

            try:
                self.tableView.tableModel.sendSignalLayoutAboutToBeChanged()
                listview_table_data_ = restore_state(open(self.pickle_storage_path, 'rb'))
                tableview_data[:] = listview_table_data_[
                                    :]  # don't assign directly, need to keep the existing reference!
                self.tableView.tableModel.sendSignalLayoutChanged()
                PICKLE_IS_LOADED = True
            except Exception as e:
                LOG.error("Error initializing data", exc_info=e)

        if not PICKLE_IS_LOADED:
            LOG.info('Appstate not found or invalid, parsing data...')
            try:
                self.parse_email_items()
            except Exception as e:
                show_gui_error(e, 'Failed parsing mailbox!')

                # self.tableView.resizeColumnsToContents()

    def restore_column_sort_mode(self):
        if len(tableview_data):
            if self.last_saved_sort_column and self.last_saved_sort_order:
                self.tableView.tableModel.sort(self.last_saved_sort_column, self.last_saved_sort_order)

    def create_new_mbox(self):
        suggested_filename = os.path.join(self.appdata_dir, 'mymailbox.mbox')
        filename, __ = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             "Create a new mailbox file", suggested_filename,
                                                             "Mailbox (*.mbox)")
        if not filename:
            return

        with open(filename, 'wb') as new_file:
            pass

        if os.path.exists(filename):
            self.on_open_file(filePath=filename)

    def clearLayout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
            elif child.layout() is not None:
                self.clearLayout(child.layout())

    def onListItemDoubleClick(self, qModelIndex):

        self.on_open_raw_message(row_index=qModelIndex.row(), extension='eml')
        # print 'double-clicked', qModelIndex.row()

    def onListItemSelect(self, selected):
        """an item in the listbox has been clicked/selected
        :param selected bool
        """
        self.bottomDock.hide()
        self.attachment_buttons = []

        rowIndex = selected.first().top()

        #  TODO: clear layout
        # self.clearLayout(self.bottomDock)
        meta_data = tableview_data[rowIndex][INDEX_HIDDEN_METADATA]
        email_message = meta_data.message
        headers = meta_data.headers
        email_body, attachments = EmailParser.parse_email_body(email_message)

        if not email_body:
            email_body = '<pre>[invalid message body]</pre><hr/>\n' + email_message.as_string()

        html_headers = []

        for header in list(headers.keys()):

            header_value = headers[header]

            if isinstance(header_value, str):

                if header in ("From", "To"):
                    header_value = html.escape(header_value)

                html_headers.append('<b>%s</b>: %s' % (header, header_value))

        htmlheaders_div = '''<div style="font-size:10pt; color:#888;">
{0}</div><hr/>'''.format("<br/>\n".join(html_headers))

        self.textEdit.setHtml(htmlheaders_div + email_body)

        if attachments and len(attachments):

            self.bottomDockWidgetContents = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(self.bottomDockWidgetContents)  # :type layout: QtWidgets.QVBoxLayout
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.setAlignment(QtCore.Qt.AlignTop)

            self.bottomDockLayout = QtWidgets.QHBoxLayout()

            for attachIdx, attachmnt in enumerate(attachments):
                button = QtWidgets.QPushButton(attachmnt.filename, None)
                self.attachment_buttons.append(button)
                button.setMenu(self.attachmentContextMenu)
                button.setIcon(self.attachment_icon)
                button.setIconSize(QtCore.QSize(16, 16))
                button.attachment = attachmnt

                sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
                sizePolicy.setHorizontalStretch(0)
                sizePolicy.setVerticalStretch(0)
                button.setSizePolicy(sizePolicy)

                layout.addWidget(button)

            scrollarea = QtWidgets.QScrollArea()
            scrollarea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
            scrollarea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scrollarea.setWidgetResizable(True)
            scrollarea.setWidget(self.bottomDockWidgetContents)

            self.bottomDock.setWidget(scrollarea)
            self.bottomDock.show()
            self.bottomDock.setMinimumHeight(32)

    def on_attachment_context_menu_selection(self):
        """
        Triggered when an item is selected in the rich-click context menu on an attachment button
        """

        action = self.sender()

        widgets = self.bottomDockWidgetContents.children()

        selected_button = None

        # TODO: Find a cleaner way to get the target without looping
        #  SEARCH FOR THE PRESSED BUTTON
        for widget in widgets:

            if isinstance(widget, QtWidgets.QPushButton):
                if widget.isDown():
                    selected_button = widget
                    break

        if selected_button:
            if action == self.actionAttachmentOpen:
                self.attachment_button_click_handler(selected_button)
            if action == self.actionAttachmentOpenAsText:
                self.attachment_button_click_handler(selected_button, ".txt")

            if action == self.actionAttachmentSave:
                attachment = selected_button.attachment

                if attachment:
                    self.save_binary_file(caption='Saved attached file',
                                          fname=attachment.filename,
                                          bytes=attachment.binary_data)

    def attachment_button_click_handler(self, widget=None, appendExtension=""):
        """
        #:type attachments: Attachment
        # :type attachIdx: int
        """
        # PySide: Connecting Multiple Widgets to the Same Slot - The Mouse Vs. The Python
        # http://www.blog.pythonlibrary.org/2013/04/10/pyside-connecting-multiple-widgets-to-the-same-slot/

        target = self.sender()

        if isinstance(target, QtWidgets.QPushButton):
            button = target
        else:
            button = widget

        if not button:
            raise ValueError('Ouch! Expecting a button!')

        attachment = button.attachment
        attachment_file_path = os.path.join(self.appdata_dir, attachment.filename) + appendExtension

        try:
            with open(attachment_file_path, 'wb') as attachmentFile:
                attachmentFile.write(attachment.binary_data)
                self.start_file(attachment_file_path)
        except Exception as e:
            show_gui_error(e, error_text="Failed writing file " + attachment_file_path)

    def start_file(self, filepath):
        """
        Launches a file in platform-independent way
        """
        if sys.platform.startswith('darwin'):
            subprocess.call(('open', filepath))
        elif os.name == 'nt':
            os.startfile(filepath)  ## only available on windowses
        elif os.name == 'posix':
            subprocess.call(('xdg-open', filepath))

    def read_settings(self):
        self.settings = QtCore.QSettings(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, "xh", APPNAME)
        pos = self.settings.value("pos", QtCore.QPoint(200, 200))
        size = self.settings.value("size", QtCore.QSize(600, 400))
        self.resize(size)
        self.move(pos)
        self.port = self.settings.contains('port') and self.settings.value("port", type=int) or DEFAULT_PORT
        self.mbox_path = self.settings.contains('mbox_path') and self.settings.value("mbox_path")
        self.isSmtpAutostartEnabled = self.settings.contains('smtp_autostart') and self.settings.value(
            "smtp_autostart", type=bool) or False
        self.isHtmlCleaningEnabled = self.settings.contains('clean_html') and self.settings.value(
            "clean_html", type=bool) or False
        self.last_saved_sort_column = self.settings.contains('last_saved_sort_column') and self.settings.value(
            "last_saved_sort_column", type=int) or None
        self.last_saved_sort_order = self.settings.contains('last_saved_sort_order') and self.settings.value(
            "last_saved_sort_order", type=int) or None
        self.is_toolbar_hidden = self.settings.contains('is_toolbar_hidden') and self.settings.value(
            "is_toolbar_hidden", type=bool) or False
        self.is_log_file_enabled = self.settings.contains('is_log_file_enabled') and self.settings.value(
            "is_log_file_enabled", type=bool) or False

    def write_settings(self):
        settings = QtCore.QSettings(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, "xh", APPNAME)
        settings.setValue("pos", self.pos())
        settings.setValue("size", self.size())
        settings.setValue("port", self.port)
        settings.setValue("mbox_path", str(self.mbox_path))
        settings.setValue("smtp_autostart", self.isSmtpAutostartEnabled)
        settings.setValue("clean_html", self.isHtmlCleaningEnabled)
        settings.setValue("last_saved_sort_column", self.last_saved_sort_column)
        settings.setValue("last_saved_sort_order", self.last_saved_sort_order)
        settings.setValue("is_toolbar_hidden", self.is_toolbar_hidden)
        settings.setValue("is_log_file_enabled", self.actionLogToFileEnabled.isChecked())

        settings.sync()

    def closeEvent(self, event):

        if self.mailsync and self.mailsync.isAlive():
            self.mailsync.stop()

        if self.tableView.tableModel.last_saved_sort_column and self.tableView.tableModel.last_saved_sort_order:
            self.last_saved_sort_column = self.tableView.tableModel.last_saved_sort_column
            self.last_saved_sort_order = self.tableView.tableModel.last_saved_sort_order

        LOG.info('closeEvent: Saving settings...')
        self.write_settings()
        LOG.info('Cleanup...')
        delete_temp_files(self.appdata_dir, '*.tmp.*')

        if not DISABLE_APPSTATE:
            self.save_appstate()

        return
        quit_msg = "Are you sure you want to exit the program?"
        reply = QtWidgets.QMessageBox.question(self, 'Message',
                                               quit_msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            self.write_settings()
            event.accept()
            QtWidgets.QApplication.instance().quit()
        else:
            event.ignore()

    @timed
    def save_appstate(self):

        if PICKLE_IS_LOADED and not PICKLE_STATE_DIRTY:
            # avoid resaving appstate if it did not change
            LOG.info('App state data unchanged. Skipping saving appstate!')
            return

        LOG.info('Serializing appstate to file %s', self.pickle_storage_path)
        fhandle = open(self.pickle_storage_path, 'wb')
        save_state(tableview_data, fhandle)

    def add_single_email_item(self, email_message, isSendUpdateModelSignal=True):
        """
        This method is called both from bulk parsing, and single message parsing which required
        the update signals to be sent
        """

        headers = EmailParser.parse_email_headers(email_message)

        if isSendUpdateModelSignal:
            self.tableView.tableModel.sendSignalLayoutAboutToBeChanged()

        # special treatment for the date column, since it needs to be sortable
        # therefore using a QTableWidgetItem for it
        timestamp = headers.get('timestamp', 0)

        if isinstance(timestamp, float):
            timestamp = int(timestamp)
        qDate = QtCore.QDateTime.fromTime_t(timestamp)

        tableview_data.append((headers.get('From', '[empty]'),
                               qDate,
                               headers.get('Subject', '[empty]'),
                               ItemMetaData(email_message, headers)
                               )
                              )

        if isSendUpdateModelSignal:
            self.tableView.tableModel.sendSignalLayoutChanged()

    def parse_email_items(self):
        """
        start parser thread in a separate thread
        """
        _thread.start_new_thread(self.parse_email_items_task, ())

    @timed
    def parse_email_items_task(self):

        mbox = mailbox.mbox(self.mbox_path)
        num_total = 0

        # table model update start
        self.tableView.tableModel.sendSignalLayoutAboutToBeChanged()

        for count, email_message in enumerate(mbox):

            try:
                self.add_single_email_item(email_message)
            except Exception as e:
                LOG.error('Error parsing message %s. Skipping..', pprint.pformat(email_message), exc_info=e)

            if count % 100 == 0:
                LOG.info('%d', count)
            self.topDock.setWindowTitle("Loading messages: %s..." % count)
            num_total = count

        #####  magic model update end
        self.tableView.tableModel.sendSignalLayoutChanged()
        LOG.info('Total messages parsed: %d', num_total)
        self.topDock.setWindowTitle("Total messages: %s" % num_total)


class EmailPoller:
    """
    :type queue: Queue.Queue
    """

    def __init__(self):
        self.timer = QtCore.QTimer()
        self.timer.setInterval(POLLING_TIME_MILLISECS)
        self.timer.timeout.connect(self.check_for_new_items)
        self.queue = None
        self.handler = None

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def set_queue(self, queue=None):
        self.queue = queue

    def set_handler(self, handler):
        self.handler = handler

    # @QtCore.pyqtSlot()
    def check_for_new_items(self):

        global PICKLE_STATE_DIRTY

        if not self.queue:
            raise Exception("You forgot to set a Queue object")

        if not self.handler:
            raise Exception("You forgot to set a handler")

        if not self.queue.empty():
            raw_email = self.queue.get()

            if raw_email:
                raw_email = re.sub("""<style.*?</style>""", '', raw_email)
                emailMessage = email.message_from_string(raw_email)
                self.handler(emailMessage, isSendUpdateModelSignal=True)
                PICKLE_STATE_DIRTY = True


class EmailParser:
    cleaning_is_enabled = False

    @staticmethod
    def parse_email_body(email_message):

        if not email_message:
            return None, None

        attachments = []

        body_plain = ''
        body_html = ''
        body_image = ''
        body_attacments_info = ''
        mainbodydata = ''

        already_have_html = False

        if email_message.is_multipart():
            for part in email_message.walk():
                # print part.get_content_type(), part.is_multipart(), len(part.get_payload())

                charset = part.get_content_charset()

                if charset and charset.lower() in VALID_ENCODINGS:
                    charset = None

                content_type = part.get_content_type()

                if 'text/html' in content_type:
                    body_html = EmailParser.decode_part(part, charset, content_type)
                    already_have_html = True

                elif ('text/plain' in content_type and not already_have_html) \
                        or 'text/calendar' in content_type:
                    body_plain = '<pre style="white-space:pre-wrap; word-wrap:break-word;">' \
                                 + EmailParser.decode_part(part, charset) + "</pre>"

                elif 'image/png' in content_type \
                        or 'image/jpeg' in content_type \
                        or 'image/jpg' in content_type \
                        or 'image/gif' in content_type:
                    body_image += EmailParser.decode_image_part(part, content_type)

                else:
                    filename = part.get_filename()

                    if filename:
                        body_attacments_info += "<b>Attachment</b>: {0}<br/>\n".format(filename)
                        attachment = Attachment(filename, part.get_payload(decode=True))
                        attachments.append(attachment)

                    else:
                        dec_payload = EmailParser.decode_part(part, charset)
                        if dec_payload:
                            body_attacments_info += '''<br/><p><small>Content-Type: %s</small></p>%s''' % (
                                content_type, dec_payload)

        else:
            content_type = email_message.get_content_type()
            msg_charset = email_message.get_content_charset()

            if content_type and 'text/plain' in content_type.lower():
                mainbodydata = '<pre style="white-space:pre-wrap; word-wrap:break-word;">' \
                               + EmailParser.decode_part(email_message, msg_charset) + "</pre>"
            else:
                if msg_charset and msg_charset.lower() in VALID_ENCODINGS:
                    mainbodydata = EmailParser.decode_part(email_message, msg_charset)
                else:
                    mainbodydata = EmailParser.decode_part(email_message)

        assembled_body = body_html or body_plain + body_image + body_attacments_info + mainbodydata

        return assembled_body, attachments
        # email_bodies.append((htmlhead + mainbodydata, attachments, email_message))

    @staticmethod
    def parse_email_headers(email_message, allowed_headers=None):

        """
        :param allowed_headers:
        """
        if not allowed_headers:
            allowed_headers = ['subject',
                               'from',
                               'to',
                               'date',
                               'reply-to',
                               'x-mailer']

        headers = {}

        for key in email_message.keys():
            if key.lower() in allowed_headers:

                current_header = email_message[key]
                decoded_chunks = decode_header(current_header)
                current_header = EmailParser.assemble_header_chunks(decoded_chunks)

                if key.lower() in ['from', 'to', 'reply-to']:
                    current_header = EmailParser.clean_header(current_header, "'\r\n\t")

                if key.lower() == 'date':
                    parsed_date = parsedate_tz(current_header)

                    if parsed_date:
                        timestamp = mktime_tz(parsed_date)
                        headers['timestamp'] = timestamp

                        if timestamp:
                            formatted_time = datetime.datetime.fromtimestamp(
                                timestamp).strftime('%d-%b-%Y %H:%M')
                            current_header = formatted_time

                headers[key] = current_header

        return headers

    @staticmethod
    def assemble_header_chunks(chunks):

        header_chunks = []

        for val, enc in chunks:
            decoded_header_fragment = val
            header_fragment_encoding = None

            if enc and enc.lower() in VALID_ENCODINGS:
                header_fragment_encoding = enc

            if isinstance(val, bytes):

                if header_fragment_encoding:
                    decoded_header_fragment = val.decode(encoding=header_fragment_encoding)
                else:
                    try:
                        decoded_header_fragment = val.decode()
                    except UnicodeDecodeError as ue:
                        LOG.error('Error decoding header: %s. Suppressing conversion error.',
                                  pprint.pformat(chunks), exc_info=ue)
                        decoded_header_fragment = val.decode(errors='replace')
            header_chunks.append(decoded_header_fragment)

        return ''.join(header_chunks)

    @staticmethod
    def clean_header(header, chars=None):

        if isinstance(header, Header):
            return 'Header_error'

        return header.translate({ord(c): None for c in chars})

    @staticmethod
    def decode_image_part(part, content_type):
        image_bytes = part.get_payload(decode=True)
        image_base64 = base64.b64encode(image_bytes)
        return '<img src="data:{0};base64,{1}">'.format(content_type, image_base64)

    @staticmethod
    def decode_part(part, charset=None, content_type=None):

        payload = None
        can_decode = False

        try:
            payload = part.get_payload(decode=True)

            if isinstance(payload, bytes) and len(payload):
                if charset and charset in VALID_ENCODINGS:
                    try:
                        payload = str(payload, encoding=charset, errors="ignore")  # .encode('utf8', 'replace')
                        can_decode = True
                    except Exception as e:
                        LOG.debug('\t\terror decoding payload with charset: %s\n%s. Trying to guess encoding...',
                                  charset, pprint.pformat(payload), exc_info=e)
                if not can_decode:
                    payload = str(payload, encoding='utf-8', errors='ignore')

            elif isinstance(payload, list) and len(payload):
                payload = "".join([str(pl, encoding='latin1', errors='ignore') for pl in payload])

        except Exception as e:
            LOG.error("error decoding payload for part: {}\n{}".format(pprint.pformat(part), str(e)))

        if not payload:
            return ""

        if content_type and content_type == 'text/html' and EmailParser.cleaning_is_enabled and len(payload.strip()):

            try:
                if Cleaner and payload:

                    cleaner = Cleaner(page_structure=False, links=False, style=True, scripts=True, frames=True)
                    if isinstance(payload, str):
                        payload = payload.encode("utf-8")
                    payload = cleaner.clean_html(payload)
            except (lxml.etree.ParserError, UnicodeDecodeError, ValueError) as e:
                LOG.error("Html cleaning error:", exc_info=e)

        if isinstance(payload, bytes):
            try:
                payload = str(payload, 'utf-8', errors='ignore')
            except Exception as e:
                LOG.error('Error decoding email part', e)

        return payload


class EmailTableView(QtWidgets.QTableView):
    def __init__(self, *args):
        QtWidgets.QTableView.__init__(self, *args)
        self.tableModel = EmailTableModel(tableview_data, self)
        self.setModel(self.tableModel)
        self.configureTableView()
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

    def setAppWindowHandle(self, mainWindowHandle):
        self.mainWindow = mainWindowHandle

    def configureTableView(self):
        self.setShowGrid(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setTabKeyNavigation(False)

        # disable row editing
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # disable bold column headers
        horizontalHeader = self.horizontalHeader()
        horizontalHeader.setHighlightSections(False)

        self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
        self.resizeColumnsToContents()
        self.setWordWrap(True)
        self.setSortingEnabled(True)


# http://www.saltycrane.com/blog/2007/06/pyqt-42-qabstracttablemodelqtableview/
class EmailTableModel(QtCore.QAbstractTableModel):
    header_labels = ['            From            ', '            Date            ', 'Subject']

    def __init__(self, datain, parent=None, *args):
        QtCore.QAbstractTableModel.__init__(self, parent, *args)
        self.arraydata = datain
        self.last_saved_sort_column = None
        self.last_saved_sort_order = None

    def rowCount(self, parent):
        return len(self.arraydata)

    def columnCount(self, parent):
        return len(self.header_labels)

    def data(self, qModelIndex, role):
        # index is a QModelIndex type
        if not qModelIndex.isValid():
            return QtCore.QVariant()
        elif role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft
        elif qModelIndex.isValid() and role == QtCore.Qt.DecorationRole:
            row = qModelIndex.row()
            column = qModelIndex.column()
            value = None
            try:
                value = self.arraydata[row][column]
            except IndexError:
                return
        elif qModelIndex.isValid() and role == QtCore.Qt.DisplayRole:
            row = qModelIndex.row()
            column = qModelIndex.column()
            try:
                value = self.arraydata[row][column]
            except IndexError:
                return
            return value

        return QtCore.QVariant(self.arraydata[qModelIndex.row()][qModelIndex.column()])

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == QtCore.Qt.EditRole:
            self.arraydata[index.row()] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def sendSignalLayoutAboutToBeChanged(self):
        self.layoutAboutToBeChanged.emit()
        self.beginResetModel()

    def sendSignalLayoutChanged(self):
        self.endResetModel()
        self.layoutChanged.emit()

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.header_labels[section]
        return QtCore.QAbstractTableModel.headerData(self, section, orientation, role)

    def insertRows(self, position, item, parent=QtCore.QModelIndex()):

        self.beginInsertRows(QtCore.QModelIndex(), len(self.arraydata), len(self.arraydata) + 1)
        self.arraydata.append(item)  # Item must be an array
        self.endInsertRows()
        return True

    def sort(self, ncol, order):
        """
        Sort table by given column number.
        """
        self.sendSignalLayoutAboutToBeChanged()

        sorted_data = sorted(self.arraydata, key=operator.itemgetter(ncol), reverse=order)
        self.arraydata[:] = sorted_data[:]
        self.sendSignalLayoutChanged()
        self.last_saved_sort_column = ncol
        self.last_saved_sort_order = order

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable

class SmtpMailsinkServer(smtpd.SMTPServer):
    __version__ = 'Python SMTP Mail Sink version 0.2'

    def __init__(self, *args, **kwargs):
        if DEBUG_SMTP:
            smtpd.DEBUGSTREAM = sys.stdout
            smtpd.SMTPServer.debug = True
        smtpd.SMTPServer.__init__(self, *args, **kwargs)
        self.mailboxFilePath = None
        self.queue = None

    def setQueue(self, mailQueue):
        self.queue = mailQueue

    def set_mbox_file_path(self, mailboxFilePath):
        self.mailboxFilePath = mailboxFilePath

    def process_message(self, peer, mailfrom, rcpttos, data):

        LOG.info("processing new message from %s", mailfrom)

        if self.mailboxFilePath is not None:
            mbox_write_item(mbox_path=self.mailboxFilePath, from_text=mailfrom, data=data)

        # print "Adding data to queue %s" % str(self.queue)
        self.queue.put(data)
        # print "Finish adding data to queue"


class PortAlreadyInUseException(Exception):
    pass


class SmtpMailsink(threading.Thread):
    TIME_TO_WAIT_BETWEEN_CHECKS_TO_STOP_SERVING = 0.001

    def __init__(self, host="localhost", port=DEFAULT_PORT, mailboxFilePath=None, threadName=None, mailQueue=None):
        self.queue = mailQueue
        self.throwExceptionIfAddressIsInUse(host, port)
        self.initializeThread(threadName)
        self.initializeSmtpMailsinkServer(host, port, mailboxFilePath)

    def throwExceptionIfAddressIsInUse(self, host, port):
        testSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        testSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                              testSocket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) | 1)
        try:
            testSocket.bind((host, port))
        except Exception as e:
            raise PortAlreadyInUseException(e)
        finally:
            testSocket.close()

    def initializeThread(self, threadName):
        self._stopevent = threading.Event()
        self.threadName = threadName
        if self.threadName is None:
            self.threadName = SmtpMailsink.__class__
        threading.Thread.__init__(self, name=self.threadName)

    def initializeSmtpMailsinkServer(self, host, port, mailboxFilePath):
        self.smtpMailsinkServer = SmtpMailsinkServer((host, port), None)
        self.smtpMailsinkServer.setQueue(self.queue)
        self.init_mailbox(mailboxFilePath)
        smtpd.__version__ = SmtpMailsinkServer.__version__

    def init_mailbox(self, mailboxFilePath=None):
        self.mailboxFilePath = mailboxFilePath
        #        if self.mailboxFilePath is None:
        #            self.mailboxFilePath = StringIO.StringIO()
        self.smtpMailsinkServer.set_mbox_file_path(self.mailboxFilePath)
        if not os.path.exists(self.mailboxFilePath):
            with open(self.mailboxFilePath, 'ab') as mbox:
                mbox.write('Started on %s' % QtCore.QDateTime.currentDateTime().toString())

    def getMailboxContents(self):
        return self.mailboxFilePath.getvalue()

    def getMailboxFile(self):
        return self.mailboxFilePath

    def run(self):
        while not self._stopevent.isSet():
            asyncore.loop(timeout=SmtpMailsink.TIME_TO_WAIT_BETWEEN_CHECKS_TO_STOP_SERVING, count=1)

    def stop(self, timeout=None):
        LOG.info("Stopping SMTP server...")
        self._stopevent.set()
        threading.Thread.join(self, timeout)
        self.smtpMailsinkServer.close()
        LOG.info("Stopped.")


class Attachment:
    def __init__(self, filename, binary_data, content_type=None, content_disposition=None):
        self.filename = filename
        self.content_type = content_type
        self.binary_data = binary_data
        self.content_disposition = content_disposition


class ItemMetaData:
    def __init__(self, message, headers):
        self.message = message
        self.headers = headers


def mbox_write_item(mbox_path, from_text, data):
    try:
        with open(mbox_path, 'a') as mbox_file:
            mbox_file.write("From %s\n" % from_text)
            mbox_file.write(data)
            mbox_file.write("\n\n")
            LOG.debug('From: %s', from_text)

            if DEBUG_APP:
                LOG.debug(data)
    except Exception as e:
        LOG.error('Error processing mail item!', exc_info=e)
        show_gui_error(e, error_text='Cannot write to mailbox %s! Please, check if file is writable.' % mbox_path)


def create_folder_if_not_exists(folder_path=None, error_message="CANNOT CREATE FOLDER: %s!"):
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path)
            LOG.info('Created folder [%s]', folder_path)
        except Exception as e:
            show_gui_error(e, error_message % folder_path)


def delete_temp_files(indir=None, mask=None):
    for file_name in glob.glob(os.path.join(indir, mask)):
        try:
            os.remove(file_name)
        except Exception as e:
            LOG.error("Error removing file", exc_info=e)  # don't show annoying gui errors
        finally:
            LOG.info('Removed %s', file_name)


def show_gui_error(e, error_text=''):
    full_error = error_text + '\n\n' + str(e) + '\n\n' + (traceback.format_exc() or '')
    LOG.error("GUI error message: %s", full_error)
    QtWidgets.QMessageBox.warning(None, APPNAME, full_error)


@timed
def save_state(data, file_handle):
    pickle.dump(data, file_handle, protocol=pickle.HIGHEST_PROTOCOL)


@timed
def restore_state(file_handle):
    return pickle.load(file_handle)


def init_logging(log_file_dir=None, log_to_stdout=True, log_to_file=False):
    global LOG
    LOG = logging.getLogger("cutepiesmtpdaemon")
    LOG.setLevel(logging.DEBUG)

    if log_to_stdout or log_to_file:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    else:
        return

    if log_to_file:
        if not log_file_dir:
            log_file_dir = '.'

        log_file_path = os.path.join(log_file_dir, LOG_FILE_NAME)
        print('Logging to file', log_file_path)
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        LOG.addHandler(file_handler)

    if log_to_stdout:
        stdout_handler = logging.StreamHandler()
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(formatter)
        LOG.addHandler(stdout_handler)


def main():
    app = QtWidgets.QApplication(sys.argv)
    mainWin = MainWindow()
    mainWin.show()
    mainWin.raise_()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
