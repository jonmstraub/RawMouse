# Copyright (c) 2020 burtoogle.
# HIDTest is released under the terms of the AGPLv3 or higher.

import json
import sys
import os

from threading import Thread

#from UM.Controller import Controller
from UM.Extension import Extension
from UM.Logger import Logger
from cura.CuraApplication import CuraApplication

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

if sys.platform == "linux":
    sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "hidapi", "hidapi-0.9.0-py3.5-linux-" + os.uname()[4] + ".egg"))
elif sys.platform == "win32":
    sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "hidapi", "hidapi-0.9.0-py3.5-win-amd64.egg"))
import hid
del sys.path[-1]

class HIDTest(Extension, QObject,):
    def __init__(self, parent = None):
        QObject.__init__(self, parent)
        Extension.__init__(self)

        self._application = CuraApplication.getInstance()
        self._camera_tool = self._application.getController().getCameraTool()

        self.setMenuName(catalog.i18nc("@item:inmenu", "HIDTest"))
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Reload"), self._reload)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Restart"), self._restart)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Stop"), self._stop)

        self._running = False
        self._runner = None
        self._reload()
        self._start()

    def _reload(self):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "hid.json"), "r", encoding = "utf-8") as f:
            self._config = json.load(f)

    def _restart(self):
        self._stop()
        self._start()

    def _start(self):
        self._hid_dev = None
        for hid_dev in hid.enumerate():
            for known_dev in self._config["devices"]:
                if hid_dev["vendor_id"] == int(known_dev[0], base = 16) and hid_dev["product_id"] == int(known_dev[1], base = 16):
                    self._hid_dev = hid_dev
                    self._hid_profile = known_dev[2]
                    break
            if self._hid_dev is not None:
                break

        if self._hid_dev is not None:
            self._runner = Thread(target = self._run, daemon = True, name = "HID Event Reader")
            self._runner.start()
        else:
            Logger.log("w", "No known HID device found")

    def _stop(self):
        self._running = False
        while self._runner is not None:
            self._runner.join(timeout = 2.0)

    def _run(self):
        self._running = True
        try:
            h = hid.device()
            if self._hid_dev["path"]:
                Logger.log("d", "Trying to open %s", self._hid_dev["path"])
                h.open_path(self._hid_dev["path"])
            else:
                Logger.log("d", "Trying to open [%x,%x]", self._hid_dev["vendor_id"], self._hid_dev["product_id"])
                h.open(self._hid_dev["vendor_id"], self._hid_dev["product_id"])

            Logger.log("i", "Manufacturer: %s", h.get_manufacturer_string())
            Logger.log("i", "Product: %s", h.get_product_string())
            #Logger.log("i", "Serial No: %s", h.get_serial_number_string())

            while self._running:
                d = h.read(64, 1000)
                if d:
                    self._decodeHIDEvent(d)

            h.close()
        except Exception as e:
            Logger.log("e", "Exception while reading HID events: %s" % e)
        self._running = False
        self._runner = None

    def _decodeHIDEvent(self, buf):
        if self._hid_profile == "spacemouse":
            self._decodeSpacemouseAxisEvent(buf)
        else:
            Logger.log("d", "Unknown HID event: profile= %s, code = %x, len = %d", self._hid_profile, buf[0], len(buf))

    def _decodeSpacemouseAxisEvent(self, buf):
        if len(buf) == 7 and (buf[0] == 1 or buf[0] == 2):
            for a in range(0, 3):
                val = buf[2 * a + 1] | buf[2 * a + 2] << 8
                if val & 0x8000:
                    val = val - 0x10000
                val = val / 350.0
                if abs(val) > 0.01:
                    self._spacemouseAxisEvent((buf[0] - 1) * 3 + a, val)
        elif len(buf) == 13 and buf[0] == 1:
            for a in range(0, 6):
                val = buf[2 * a + 1] | buf[2 * a + 2] << 8
                if val & 0x8000:
                    val = val - 0x10000
                val = val / 350.0
                if abs(val) > 0.01:
                    self._spacemouseAxisEvent(a, val)
        else:
            Logger.log("d", "Unknown spacemouse event: code = %x, len = %d", buf[0], len(buf))

    def _spacemouseAxisEvent(self, axis, val):
        Logger.log("d", "axis[%d] = %f", axis, val)

