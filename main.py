#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamixel ID Setter — Lightweight GUI tool for changing Dynamixel XC330 motor IDs.

Cross-platform (Windows / Ubuntu / macOS) PyQt5 application using dynamixel_sdk Protocol 2.0.
"""

import sys
import platform

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QSpinBox,
    QPlainTextEdit, QListWidget, QMessageBox, QSizePolicy, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

import serial.tools.list_ports

try:
    from dynamixel_sdk import (
        PortHandler, PacketHandler,
        COMM_SUCCESS, COMM_TX_FAIL
    )
except ImportError:
    print("ERROR: dynamixel_sdk is not installed. Run: pip install dynamixel-sdk")
    sys.exit(1)

# ──────────────────────────────────────────────
# Constants — XC330 / Protocol 2.0
# ──────────────────────────────────────────────
PROTOCOL_VERSION = 2.0
ADDR_TORQUE_ENABLE = 64      # 1 Byte
ADDR_ID = 7                  # 1 Byte
TORQUE_DISABLE = 0
TORQUE_ENABLE = 1
DXL_ID_MIN = 0
DXL_ID_MAX = 252

DEFAULT_BAUDRATE = 57600
BAUDRATE_OPTIONS = [9600, 57600, 115200, 1000000, 2000000, 3000000, 4000000]


# ──────────────────────────────────────────────
# Worker thread for scanning (avoids UI freeze)
# ──────────────────────────────────────────────
class ScanWorker(QThread):
    """Background thread that pings IDs 0–252."""
    found_id = pyqtSignal(int)       # emitted per found ID
    progress = pyqtSignal(int)       # emitted with current scan ID
    finished = pyqtSignal(list)      # emitted when scan completes

    def __init__(self, port_handler, packet_handler, stop_on_first=False, parent=None):
        super().__init__(parent)
        self.port_handler = port_handler
        self.packet_handler = packet_handler
        self.stop_on_first = stop_on_first
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        found = []
        for dxl_id in range(DXL_ID_MIN, DXL_ID_MAX + 1):
            if self._abort:
                break
            self.progress.emit(dxl_id)
            try:
                model_number, comm_result, dxl_error = self.packet_handler.ping(
                    self.port_handler, dxl_id
                )
                if comm_result == COMM_SUCCESS:
                    found.append(dxl_id)
                    self.found_id.emit(dxl_id)
                    if self.stop_on_first:
                        self._abort = True
            except Exception:
                pass
        self.finished.emit(found)


# ──────────────────────────────────────────────
# Dynamixel Manager — SDK wrapper
# ──────────────────────────────────────────────
class DynamixelManager:
    """Thin wrapper around dynamixel_sdk for port management and ID operations."""

    def __init__(self):
        self.port_handler = None
        self.packet_handler = PacketHandler(PROTOCOL_VERSION)
        self.is_open = False

    # ── Port ──────────────────────────────────
    def open_port(self, port_name: str, baudrate: int) -> str:
        """Open serial port. Returns empty string on success, error message on failure."""
        try:
            self.port_handler = PortHandler(port_name)
            if not self.port_handler.openPort():
                return f"Failed to open port: {port_name}"
            if not self.port_handler.setBaudRate(baudrate):
                self.port_handler.closePort()
                return f"Failed to set baudrate: {baudrate}"
            self.is_open = True
            return ""
        except Exception as e:
            return str(e)

    def close_port(self):
        try:
            if self.port_handler and self.is_open:
                self.port_handler.closePort()
        except Exception:
            pass
        self.is_open = False

    # ── ID change ─────────────────────────────
    def set_id(self, current_id: int, new_id: int, log_callback=None):
        """
        Change motor ID.
        Returns (success: bool, message: str).
        """
        if not self.is_open:
            return False, "Port is not open."

        ph = self.port_handler
        pk = self.packet_handler
        warnings = []

        # 1. Torque Off
        try:
            comm_result, dxl_error = pk.write1ByteTxRx(ph, current_id, ADDR_TORQUE_ENABLE, TORQUE_DISABLE)
            if comm_result != COMM_SUCCESS:
                return False, f"Torque Off failed: {pk.getTxRxResult(comm_result)}"
            if dxl_error != 0:
                err_msg = pk.getRxPacketError(dxl_error)
                warnings.append(f"Torque Off status: {err_msg}")
                if log_callback:
                    log_callback(f"[Warning] {err_msg}")
        except Exception as e:
            return False, f"Torque Off exception: {e}"

        # 2. Write new ID
        try:
            comm_result, dxl_error = pk.write1ByteTxRx(ph, current_id, ADDR_ID, new_id)
            if comm_result != COMM_SUCCESS:
                return False, f"ID Write failed: {pk.getTxRxResult(comm_result)}"
            if dxl_error != 0:
                err_msg = pk.getRxPacketError(dxl_error)
                warnings.append(f"ID Write status: {err_msg}")
                if log_callback:
                    log_callback(f"[Warning] {err_msg}")
        except Exception as e:
            return False, f"ID Write exception: {e}"

        # 3. Verify — ping new ID
        try:
            _, comm_result, dxl_error = pk.ping(ph, new_id)
            if comm_result != COMM_SUCCESS:
                return False, f"Verification ping failed: {pk.getTxRxResult(comm_result)}"
            
            success_msg = f"ID changed successfully: {current_id} → {new_id}"
            if warnings:
                success_msg += f" (Note: {len(warnings)} warnings occurred)"
            return True, success_msg
        except Exception as e:
            return False, f"Verification exception: {e}"


# ──────────────────────────────────────────────
# Utility — cross-platform port listing
# ──────────────────────────────────────────────
def list_serial_ports():
    """Return list of available serial port names, filtered by OS."""
    os_name = platform.system()
    ports = serial.tools.list_ports.comports()

    if os_name == "Windows":
        return sorted([p.device for p in ports if "COM" in p.device])
    elif os_name == "Darwin":
        return sorted([
            p.device for p in ports
            if "usbserial" in p.device or "usbmodem" in p.device
        ])
    else:  # Linux
        return sorted([
            p.device for p in ports
            if "ttyUSB" in p.device or "ttyACM" in p.device
        ])


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.dxl = DynamixelManager()
        self.scan_worker = None
        self.found_ids = []

        self._init_ui()
        self._refresh_ports()

    # ── UI Construction ───────────────────────
    def _init_ui(self):
        self.setWindowTitle("Dynamixel ID Setter  —  XC330 (Protocol 2.0)")
        self.setMinimumSize(520, 620)
        self.resize(540, 660)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(8)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # ── Section 1: Connection ─────────────
        grp_conn = QGroupBox("Connection")
        lay_conn = QVBoxLayout()

        row_port = QHBoxLayout()
        row_port.addWidget(QLabel("Port:"))
        self.combo_port = QComboBox()
        self.combo_port.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_port.addWidget(self.combo_port)
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setFixedWidth(90)
        self.btn_refresh.clicked.connect(self._refresh_ports)
        row_port.addWidget(self.btn_refresh)
        lay_conn.addLayout(row_port)

        row_baud = QHBoxLayout()
        row_baud.addWidget(QLabel("Baudrate:"))
        self.combo_baud = QComboBox()
        for b in BAUDRATE_OPTIONS:
            self.combo_baud.addItem(str(b), b)
        self.combo_baud.setCurrentText(str(DEFAULT_BAUDRATE))
        row_baud.addWidget(self.combo_baud)

        self.btn_open = QPushButton("Open")
        self.btn_open.setCheckable(True)
        self.btn_open.setFixedWidth(100)
        self.btn_open.clicked.connect(self._toggle_port)
        row_baud.addWidget(self.btn_open)
        lay_conn.addLayout(row_baud)

        grp_conn.setLayout(lay_conn)
        root_layout.addWidget(grp_conn)

        # ── Section 2: Scan & Status ──────────
        grp_scan = QGroupBox("Scan && Status")
        lay_scan = QVBoxLayout()

        warn = QLabel("⚠  ID 설정 시 모터를 1대만 연결하세요  (Connect only ONE motor at a time)")
        warn.setStyleSheet("color: #e67e22; font-weight: bold;")
        warn.setWordWrap(True)
        lay_scan.addWidget(warn)

        row_scan_btn = QHBoxLayout()
        self.btn_scan = QPushButton("Scan (ID 0–252)")
        self.btn_scan.setEnabled(False)
        self.btn_scan.clicked.connect(self._start_scan)
        row_scan_btn.addWidget(self.btn_scan)

        self.cb_stop_fast = QCheckBox("Quick Scan (Stop at first ID)")
        self.cb_stop_fast.setStyleSheet("color: #00e676;")
        self.cb_stop_fast.setChecked(True)
        row_scan_btn.addWidget(self.cb_stop_fast)

        self.lbl_scan_status = QLabel("")
        row_scan_btn.addWidget(self.lbl_scan_status)
        lay_scan.addLayout(row_scan_btn)

        self.list_ids = QListWidget()
        self.list_ids.setMaximumHeight(80)
        self.list_ids.itemClicked.connect(self._on_id_selected)
        lay_scan.addWidget(self.list_ids)

        grp_scan.setLayout(lay_scan)
        root_layout.addWidget(grp_scan)

        # ── Section 3: Setup ID ───────────────
        grp_setup = QGroupBox("Setup ID")
        lay_setup = QVBoxLayout()

        row_cur = QHBoxLayout()
        row_cur.addWidget(QLabel("Current ID:"))
        self.lbl_current_id = QLabel("—")
        self.lbl_current_id.setStyleSheet("font-size: 16px; font-weight: bold;")
        row_cur.addWidget(self.lbl_current_id)
        row_cur.addStretch()
        lay_setup.addLayout(row_cur)

        row_new = QHBoxLayout()
        row_new.addWidget(QLabel("New ID:"))
        self.spin_new_id = QSpinBox()
        self.spin_new_id.setRange(DXL_ID_MIN, DXL_ID_MAX)
        self.spin_new_id.setValue(1)
        row_new.addWidget(self.spin_new_id)

        self.btn_set_id = QPushButton("Set Target ID")
        self.btn_set_id.setEnabled(False)
        self.btn_set_id.clicked.connect(self._set_id)
        row_new.addWidget(self.btn_set_id)
        lay_setup.addLayout(row_new)

        grp_setup.setLayout(lay_setup)
        root_layout.addWidget(grp_setup)

        # ── Section 4: Log Viewer ─────────────
        grp_log = QGroupBox("Log")
        lay_log = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        lay_log.addWidget(self.log_view)
        grp_log.setLayout(lay_log)
        root_layout.addWidget(grp_log)

        # ── Styling ──────────────────────────
        self.setStyleSheet("""
            QMainWindow { background: #2b2b2b; }
            QGroupBox {
                color: #dcdcdc;
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QLabel { color: #dcdcdc; }
            QComboBox, QSpinBox {
                background: #3c3f41;
                color: #dcdcdc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QPushButton {
                background: #3c6e3c;
                color: #fff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #4a8a4a; }
            QPushButton:pressed { background: #2e5a2e; }
            QPushButton:disabled { background: #555; color: #888; }
            QPushButton:checked { background: #8b3a3a; }
            QPushButton:checked:hover { background: #a04545; }
            QListWidget {
                background: #1e1e1e;
                color: #00e676;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 13px;
            }
            QPlainTextEdit {
                background: #1e1e1e;
                color: #b0bec5;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)

    # ── Helpers ────────────────────────────────
    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def _refresh_ports(self):
        self.combo_port.clear()
        ports = list_serial_ports()
        if ports:
            self.combo_port.addItems(ports)
            self._log(f"[Port] Found {len(ports)} port(s): {', '.join(ports)}")
        else:
            self._log("[Port] No serial ports detected.")

    # ── Connection ────────────────────────────
    def _toggle_port(self):
        if self.btn_open.isChecked():
            port = self.combo_port.currentText()
            baud = self.combo_baud.currentData()
            if not port:
                self._log("[Error] No port selected.")
                self.btn_open.setChecked(False)
                return
            err = self.dxl.open_port(port, baud)
            if err:
                self._log(f"[Error] {err}")
                self.btn_open.setChecked(False)
                return
            self.btn_open.setText("Close")
            self.btn_scan.setEnabled(True)
            self.combo_port.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            self._log(f"[Port] Opened {port} @ {baud} bps")
        else:
            self._close_port()

    def _close_port(self):
        self.dxl.close_port()
        self.btn_open.setText("Open")
        self.btn_open.setChecked(False)
        self.btn_scan.setEnabled(False)
        self.btn_set_id.setEnabled(False)
        self.combo_port.setEnabled(True)
        self.combo_baud.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.list_ids.clear()
        self.found_ids.clear()
        self.lbl_current_id.setText("—")
        self._log("[Port] Closed.")

    # ── Scanning ──────────────────────────────
    def _start_scan(self):
        if not self.dxl.is_open:
            self._log("[Error] Port is not open.")
            return

        self.list_ids.clear()
        self.found_ids.clear()
        self.lbl_current_id.setText("—")
        self.btn_set_id.setEnabled(False)
        self.btn_scan.setEnabled(False)

        stop_on_first = self.cb_stop_fast.isChecked()
        self._log(f"[Scan] Scanning IDs 0–252 … {'(Fast Mode)' if stop_on_first else ''}")

        self.scan_worker = ScanWorker(
            self.dxl.port_handler, 
            self.dxl.packet_handler, 
            stop_on_first=stop_on_first
        )
        self.scan_worker.found_id.connect(self._on_scan_found)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.start()

    def _on_scan_found(self, dxl_id):
        self.list_ids.addItem(f"Motor ID: {dxl_id}")
        self._log(f"[Scan] Found motor at ID {dxl_id}")

    def _on_scan_progress(self, current_id):
        self.lbl_scan_status.setText(f"Scanning ID {current_id}/252")

    def _on_scan_finished(self, found_list):
        self.found_ids = found_list
        self.btn_scan.setEnabled(True)
        self.lbl_scan_status.setText(f"Done — {len(found_list)} motor(s)")
        self._log(f"[Scan] Complete. Found {len(found_list)} motor(s).")

        if len(found_list) == 1:
            self.lbl_current_id.setText(str(found_list[0]))
            self.btn_set_id.setEnabled(True)
        elif len(found_list) > 1:
            self._log("[Warning] Multiple motors detected! Connect only ONE motor for safe ID change.")

    def _on_id_selected(self, item):
        text = item.text()  # "Motor ID: X"
        try:
            dxl_id = int(text.split(":")[1].strip())
            self.lbl_current_id.setText(str(dxl_id))
            self.btn_set_id.setEnabled(True)
        except (IndexError, ValueError):
            pass

    # ── ID Setting ────────────────────────────
    def _set_id(self):
        try:
            current_id = int(self.lbl_current_id.text())
        except ValueError:
            self._log("[Error] No current ID selected.")
            return

        new_id = self.spin_new_id.value()

        if current_id == new_id:
            self._log(f"[Info] New ID is the same as current ID ({current_id}). Nothing to do.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm ID Change",
            f"Change motor ID from {current_id} to {new_id}?\n\n"
            "Make sure only ONE motor is connected.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._log("[Info] ID change cancelled by user.")
            return

        self._log(f"[ID] Changing ID: {current_id} → {new_id} …")
        success, msg = self.dxl.set_id(current_id, new_id, log_callback=self._log)
        if success:
            self._log(f"[ID] ✔ {msg}")
            self.lbl_current_id.setText(str(new_id))
            # Update list
            self.list_ids.clear()
            self.list_ids.addItem(f"Motor ID: {new_id}")
            self.found_ids = [new_id]
        else:
            self._log(f"[ID] ✘ {msg}")

    # ── Window close ──────────────────────────
    def closeEvent(self, event):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.abort()
            self.scan_worker.wait(2000)
        self.dxl.close_port()
        event.accept()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dynamixel ID Setter")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
