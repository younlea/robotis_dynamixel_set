#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamixel ID Setter — Lightweight GUI tool for changing Dynamixel XC330 motor IDs.

Cross-platform (Windows / Ubuntu / macOS) PyQt5 application using dynamixel_sdk Protocol 2.0.
"""

import sys
import time
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
ADDR_ID = 7                  # 1 Byte
ADDR_OPERATING_MODE = 11     # 1 Byte, EEPROM
ADDR_HOMING_OFFSET = 20      # 4 Bytes, EEPROM (signed int32)
ADDR_TORQUE_ENABLE = 64      # 1 Byte
ADDR_PRESENT_POSITION = 132  # 4 Bytes, RAM (signed int32)
TORQUE_DISABLE = 0
TORQUE_ENABLE = 1
DXL_ID_MIN = 0
DXL_ID_MAX = 252
HOMING_OFFSET_JOINT_LIMIT = 1024  # Position Control Mode limits offset to ±1024
OP_MODE_EXTENDED_POSITION = 4     # Extended Position Control Mode (no offset limit)

DEFAULT_BAUDRATE = 57600
BAUDRATE_OPTIONS = [9600, 57600, 115200, 1000000, 2000000, 3000000, 4000000]

# Model mapping (Internal Model Number -> Friendly Name)
DXL_MODELS = {
    # XC330 series (Micro)
    1210: "XC330-T181-T (11.1V)",
    1220: "XC330-T288-T (11.1V)",
    1230: "XC330-M181-T (5.0V)",
    1240: "XC330-M288-T (5.0V)",
    
    # XL330 series
    1100: "XL330-M288 (5.0V)",
    1110: "XL330-M066 (5.0V)",
    
    # X430 series
    1060: "XL430-W250-T",
    1020: "XM430-W350-T",
    1120: "XM430-W210-T",
    1010: "XH430-W350-T",
    1130: "XH430-W210-T",
    311: "XC430-W150-T",
}

def get_model_name(model_number):
    return DXL_MODELS.get(model_number, f"Unknown ({model_number})")


def to_signed32(value):
    """Convert an unsigned 32-bit value from the SDK to a signed int32."""
    if value >= 0x80000000:
        return value - 0x100000000
    return value


def to_unsigned32(value):
    """Convert a signed int32 to an unsigned 32-bit value for the SDK."""
    if value < 0:
        return value + 0x100000000
    return value


# ──────────────────────────────────────────────
# Worker thread for scanning (avoids UI freeze)
# ──────────────────────────────────────────────
class ScanWorker(QThread):
    """Background thread that pings IDs 0–252."""
    found_id = pyqtSignal(int, int, int)  # (dxl_id, model_number, present_position)
    progress = pyqtSignal(int)            # emitted with current scan ID
    finished = pyqtSignal(list)           # emitted when scan completes

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
                    # Read Present Position (Address 132, 4 Bytes)
                    position = 0
                    try:
                        pos_raw, pos_result, pos_error = self.packet_handler.read4ByteTxRx(
                            self.port_handler, dxl_id, ADDR_PRESENT_POSITION
                        )
                        if pos_result == COMM_SUCCESS:
                            position = to_signed32(pos_raw)
                    except Exception:
                        pass  # position remains 0 on read failure
                    self.found_id.emit(dxl_id, model_number, position)
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

    # ── Set Zero (Homing) ─────────────────────
    def set_zero_homing(self, dxl_id: int, log_callback=None):
        """
        Set the current physical position as zero (homing).
        Returns (success: bool, message: str, verified_position: int).
        """
        if not self.is_open:
            return False, "Port is not open.", 0

        ph = self.port_handler
        pk = self.packet_handler

        def _log(msg):
            if log_callback:
                log_callback(msg)

        # Step a. Torque Off (EEPROM write requires torque disabled)
        try:
            comm_result, dxl_error = pk.write1ByteTxRx(ph, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_DISABLE)
            if comm_result != COMM_SUCCESS:
                return False, f"Torque Off failed: {pk.getTxRxResult(comm_result)}", 0
            if dxl_error != 0:
                _log(f"[Warning] Torque Off status: {pk.getRxPacketError(dxl_error)}")
            _log(f"[Homing] Step 1/6: Torque disabled for ID {dxl_id}")
        except Exception as e:
            return False, f"Torque Off exception: {e}", 0

        # Read current Operating Mode (to restore later and check offset limit)
        original_op_mode = None
        try:
            raw_mode, comm_result, dxl_error = pk.read1ByteTxRx(ph, dxl_id, ADDR_OPERATING_MODE)
            if comm_result == COMM_SUCCESS:
                original_op_mode = raw_mode
                _log(f"[Homing] Current Operating Mode = {original_op_mode}")
        except Exception:
            _log("[Warning] Could not read Operating Mode")

        # Step b. Read current Homing Offset and Present Position
        try:
            raw_offset, comm_result, dxl_error = pk.read4ByteTxRx(ph, dxl_id, ADDR_HOMING_OFFSET)
            if comm_result != COMM_SUCCESS:
                return False, f"Read Homing Offset failed: {pk.getTxRxResult(comm_result)}", 0
            if dxl_error != 0:
                _log(f"[Warning] Read Homing Offset status: {pk.getRxPacketError(dxl_error)}")
            current_offset = to_signed32(raw_offset)
            _log(f"[Homing] Step 2/6: Current Homing Offset = {current_offset}")
        except Exception as e:
            return False, f"Read Homing Offset exception: {e}", 0

        try:
            raw_pos, comm_result, dxl_error = pk.read4ByteTxRx(ph, dxl_id, ADDR_PRESENT_POSITION)
            if comm_result != COMM_SUCCESS:
                return False, f"Read Present Position failed: {pk.getTxRxResult(comm_result)}", 0
            if dxl_error != 0:
                _log(f"[Warning] Read Present Position status: {pk.getRxPacketError(dxl_error)}")
            current_position = to_signed32(raw_pos)
            _log(f"[Homing] Step 2/6: Current Present Position = {current_position}")
        except Exception as e:
            return False, f"Read Present Position exception: {e}", 0

        # Step c. Calculate new offset
        new_offset = current_offset - current_position
        _log(f"[Homing] Step 3/6: New Homing Offset = {current_offset} - {current_position} = {new_offset}")

        # Check if offset exceeds Position Control Mode limit (±1024)
        # If so, temporarily switch to Extended Position Control Mode (mode 4)
        mode_switched = False
        if original_op_mode is not None and abs(new_offset) > HOMING_OFFSET_JOINT_LIMIT:
            if original_op_mode != OP_MODE_EXTENDED_POSITION:
                _log(f"[Homing] Offset {new_offset} exceeds ±{HOMING_OFFSET_JOINT_LIMIT} limit for mode {original_op_mode}")
                _log(f"[Homing] Temporarily switching to Extended Position Control Mode (mode 4)")
                try:
                    comm_result, dxl_error = pk.write1ByteTxRx(
                        ph, dxl_id, ADDR_OPERATING_MODE, OP_MODE_EXTENDED_POSITION
                    )
                    if comm_result == COMM_SUCCESS:
                        mode_switched = True
                    else:
                        _log(f"[Warning] Failed to switch Operating Mode: {pk.getTxRxResult(comm_result)}")
                except Exception as e:
                    _log(f"[Warning] Operating Mode switch exception: {e}")

        # Step d. Write new Homing Offset
        try:
            write_value = to_unsigned32(new_offset)
            comm_result, dxl_error = pk.write4ByteTxRx(ph, dxl_id, ADDR_HOMING_OFFSET, write_value)
            if comm_result != COMM_SUCCESS:
                return False, f"Write Homing Offset failed: {pk.getTxRxResult(comm_result)}", 0
            if dxl_error != 0:
                _log(f"[Warning] Write Homing Offset status: {pk.getRxPacketError(dxl_error)}")
            _log(f"[Homing] Step 4/6: Homing Offset written = {new_offset}")
        except Exception as e:
            return False, f"Write Homing Offset exception: {e}", 0

        # Wait for EEPROM write, then read back to verify
        time.sleep(0.2)
        try:
            raw_readback, comm_result, dxl_error = pk.read4ByteTxRx(ph, dxl_id, ADDR_HOMING_OFFSET)
            if comm_result == COMM_SUCCESS:
                readback_offset = to_signed32(raw_readback)
                _log(f"[Homing] Step 4/6: Homing Offset read-back = {readback_offset}")
                if readback_offset != new_offset:
                    return False, f"EEPROM write verification failed: wrote {new_offset}, read back {readback_offset}", 0
        except Exception:
            _log("[Warning] Could not read back Homing Offset for verification")

        # Restore original Operating Mode if we switched it
        if mode_switched and original_op_mode is not None:
            _log(f"[Homing] Restoring Operating Mode to {original_op_mode}")
            try:
                pk.write1ByteTxRx(ph, dxl_id, ADDR_OPERATING_MODE, original_op_mode)
            except Exception:
                _log("[Warning] Could not restore Operating Mode")

        # Step e. Reboot motor to apply changes cleanly
        try:
            comm_result, dxl_error = pk.reboot(ph, dxl_id)
            if comm_result != COMM_SUCCESS:
                _log(f"[Warning] Reboot failed: {pk.getTxRxResult(comm_result)}, enabling torque directly")
                pk.write1ByteTxRx(ph, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ENABLE)
            else:
                _log(f"[Homing] Step 5/6: Reboot sent to ID {dxl_id}, waiting for restart…")
        except Exception:
            _log("[Warning] Reboot not supported, enabling torque directly")
            pk.write1ByteTxRx(ph, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ENABLE)

        # Wait for motor to reboot and come back online
        time.sleep(1.0)
        for retry in range(10):
            try:
                _, comm_result, _ = pk.ping(ph, dxl_id)
                if comm_result == COMM_SUCCESS:
                    _log(f"[Homing] Step 5/6: Motor ID {dxl_id} is back online")
                    break
            except Exception:
                pass
            time.sleep(0.3)
        else:
            return False, f"Motor ID {dxl_id} did not respond after reboot", 0

        # Enable torque after reboot
        try:
            pk.write1ByteTxRx(ph, dxl_id, ADDR_TORQUE_ENABLE, TORQUE_ENABLE)
        except Exception:
            pass

        # Step f. Verify — read Present Position with retries
        verified_position = None
        for attempt in range(5):
            try:
                time.sleep(0.3)
                raw_verify, comm_result, dxl_error = pk.read4ByteTxRx(ph, dxl_id, ADDR_PRESENT_POSITION)
                if comm_result == COMM_SUCCESS:
                    verified_position = to_signed32(raw_verify)
                    _log(f"[Homing] Step 6/6: Verified Position = {verified_position} (attempt {attempt + 1})")
                    if verified_position == 0:
                        break
            except Exception:
                pass

        if verified_position is None:
            return False, f"Verification read failed for ID {dxl_id}", 0
        elif verified_position == 0:
            return True, "Homing 설정 완료", 0
        else:
            return False, f"검증 실패: 위치가 0으로 초기화되지 않았습니다 (현재값: {verified_position})", verified_position



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
        self.list_ids.setMaximumHeight(140)
        self.list_ids.setSelectionMode(QListWidget.ExtendedSelection)
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

        # ── Section 4: Set Zero (Homing) ──────
        grp_zero = QGroupBox("Set Zero (Homing)")
        lay_zero = QVBoxLayout()

        _zero_btn_style = """
            QPushButton {
                background: #c67c00;
                color: #fff;
                border: none;
                border-radius: 4px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background: #e09100; }
            QPushButton:pressed { background: #a06500; }
            QPushButton:disabled { background: #555; color: #888; }
        """

        row_zero_btns = QHBoxLayout()

        self.btn_set_zero_selected = QPushButton("Set Zero (Selected)")
        self.btn_set_zero_selected.setEnabled(False)
        self.btn_set_zero_selected.setStyleSheet(_zero_btn_style)
        self.btn_set_zero_selected.clicked.connect(self._set_zero_selected)
        row_zero_btns.addWidget(self.btn_set_zero_selected)

        self.btn_set_zero_all = QPushButton("Set Zero (All Motors)")
        self.btn_set_zero_all.setEnabled(False)
        self.btn_set_zero_all.setStyleSheet(_zero_btn_style)
        self.btn_set_zero_all.clicked.connect(self._set_zero_all)
        row_zero_btns.addWidget(self.btn_set_zero_all)

        lay_zero.addLayout(row_zero_btns)

        lbl_zero_desc = QLabel(
            "⚠  선택된 모터의 현재 물리적 위치를 0점으로 영구 설정합니다.\n"
            "    (Sets the current physical position as the permanent zero point)"
        )
        lbl_zero_desc.setStyleSheet("color: #e67e22; font-size: 11px;")
        lbl_zero_desc.setWordWrap(True)
        lay_zero.addWidget(lbl_zero_desc)

        grp_zero.setLayout(lay_zero)
        root_layout.addWidget(grp_zero)

        # ── Section 5: Log Viewer ─────────────
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
        self.btn_set_zero_selected.setEnabled(False)
        self.btn_set_zero_all.setEnabled(False)
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

    def _on_scan_found(self, dxl_id, model_num, position):
        model_name = get_model_name(model_num)
        self.list_ids.addItem(f"Motor ID: {dxl_id} [{model_name}] (Position: {position})")
        self._log(f"[Scan] Found motor at ID {dxl_id} ({model_name}) — Position: {position}")

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
            self.btn_set_zero_selected.setEnabled(True)
            self.btn_set_zero_all.setEnabled(True)
        elif len(found_list) > 1:
            self._log("[Warning] Multiple motors detected! Connect only ONE motor for safe ID change.")
            self.btn_set_zero_all.setEnabled(True)

    def _on_id_selected(self, item):
        text = item.text()  # "Motor ID: X [Model] (Position: Y)"
        try:
            # Extract only ID
            id_part = text.split(":")[1].split("[")[0].strip()
            dxl_id = int(id_part)
            self.lbl_current_id.setText(str(dxl_id))
            self.btn_set_id.setEnabled(True)
            self.btn_set_zero_selected.setEnabled(True)
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

    # ── Set Zero (Homing) ────────────────────
    def _set_zero_selected(self):
        """Home only the selected motor(s) in the list."""
        selected_items = self.list_ids.selectedItems()
        if not selected_items:
            self._log("[Error] No motor selected. Click on motor(s) in the list first.")
            QMessageBox.warning(self, "No Selection", "리스트에서 모터를 선택해 주세요.\nPlease select motor(s) from the list.")
            return

        # Extract IDs from selected items
        target_ids = []
        for item in selected_items:
            try:
                id_part = item.text().split(":")[1].split("[")[0].strip()
                target_ids.append(int(id_part))
            except (IndexError, ValueError):
                pass

        if not target_ids:
            self._log("[Error] Could not parse motor IDs from selection.")
            return

        id_list_str = ", ".join(str(i) for i in target_ids)
        reply = QMessageBox.question(
            self,
            "Confirm Homing (Selected)",
            f"선택된 {len(target_ids)}개 모터의 현재 위치를 0점으로 설정합니다.\n"
            f"Set zero for motor ID(s): {id_list_str}?\n\n"
            "이 작업은 Homing Offset(EEPROM)을 변경합니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._log("[Info] Homing cancelled by user.")
            return

        self._perform_homing_batch(target_ids)

    def _set_zero_all(self):
        """Home all scanned motors."""
        if not self.found_ids:
            self._log("[Error] No motors found. Run a scan first.")
            return

        id_list_str = ", ".join(str(i) for i in self.found_ids)
        reply = QMessageBox.question(
            self,
            "Confirm Homing (All Motors)",
            f"스캔된 모든 모터({len(self.found_ids)}개)의 현재 위치를 0점으로 설정합니다.\n"
            f"Set zero for ALL motor ID(s): {id_list_str}?\n\n"
            "이 작업은 Homing Offset(EEPROM)을 변경합니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._log("[Info] Homing cancelled by user.")
            return

        self._perform_homing_batch(list(self.found_ids))

    def _perform_homing_batch(self, target_ids):
        """Execute homing sequence for a list of motor IDs."""
        total = len(target_ids)
        success_ids = []
        fail_ids = []

        self._log(f"[Homing] Starting homing for {total} motor(s): {target_ids}")

        for idx, dxl_id in enumerate(target_ids, 1):
            self._log(f"[Homing] ── Motor {idx}/{total} (ID: {dxl_id}) ──")
            success, msg, verified_pos = self.dxl.set_zero_homing(dxl_id, log_callback=self._log)

            if success:
                self._log(f"[Homing] ✔ ID {dxl_id}: {msg}")
                success_ids.append(dxl_id)
                self._update_list_position(dxl_id, 0)
            else:
                self._log(f"[Homing] ✘ ID {dxl_id}: {msg}")
                self._log(f"[Homing] Verified position after attempt: {verified_pos}")
                fail_ids.append((dxl_id, msg))

        # Summary
        self._log(f"[Homing] ════ Result: {len(success_ids)} succeeded, {len(fail_ids)} failed ════")

        if fail_ids:
            fail_detail = "\n".join(f"  ID {fid}: {fmsg}" for fid, fmsg in fail_ids)
            QMessageBox.warning(
                self, "Homing Partial/Failure",
                f"성공: {len(success_ids)}개, 실패: {len(fail_ids)}개\n\n"
                f"실패 목록:\n{fail_detail}"
            )
        else:
            QMessageBox.information(
                self, "Homing Complete",
                f"모든 모터({len(success_ids)}개) Homing 설정 완료!\n"
                f"All {len(success_ids)} motor(s) homed successfully."
            )

    def _update_list_position(self, dxl_id, position):
        """Update the position text for a given motor ID in the list widget."""
        for i in range(self.list_ids.count()):
            item = self.list_ids.item(i)
            text = item.text()
            try:
                id_part = text.split(":")[1].split("[")[0].strip()
                if int(id_part) == dxl_id:
                    model_part = text.split("[")[1].split("]")[0] if "[" in text else ""
                    item.setText(f"Motor ID: {dxl_id} [{model_part}] (Position: {position})")
                    break
            except (IndexError, ValueError):
                pass

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
