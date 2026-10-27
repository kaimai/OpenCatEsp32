from __future__ import annotations

import re
import warnings
from typing import List, Optional, Tuple

from serial.tools import list_ports

from petoi.errors import ConnectionFailed, PetoiError
from petoi.robot import Robot

SSP_MARK = "_SSP"  # src/bluetoothManager.h:73
MIN_FIRMWARE_DATE = "260820"  # firmware in this repo (src/OpenCat.h:80); the version hardware tests run against
_USB_HINTS = ("usb", "wch", "ch340", "ch910", "cp210", "uart", "acm")
_IGNORE = ("bluetooth-incoming-port", "debug-console")
_LOCAL = re.compile(r"^[^/:]+\.local(:\d+)?$")
_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$")


def classify(target: Optional[str]) -> Tuple[str, Optional[str]]:
    if target is None:
        return ("serial", None)
    low = target.lower()
    if low in ("bluetooth", "ble", "mock"):
        return (low, None)
    if low.startswith("ble:"):
        return ("ble", target[4:])
    if low.startswith("ws://") or _IP.match(target) or _LOCAL.match(low):
        return ("wifi", target)
    return ("serial", target)


def pick_serial_port(ports, bluetooth: bool) -> str:
    candidates = [p for p in ports if not any(i in p.device.lower() for i in _IGNORE)]
    if bluetooth:
        matches = [p for p in candidates if SSP_MARK in p.device or SSP_MARK in (p.description or "")]
    else:
        matches = [p for p in candidates
                   if SSP_MARK not in p.device
                   and any(h in f"{p.device} {p.description}".lower() for h in _USB_HINTS)]
    if len(matches) == 1:
        return matches[0].device
    if not matches:
        what = "paired Bluetooth (_SSP)" if bluetooth else "USB"
        hint = (" On Windows or Linux the Bluetooth port has no _SSP in its name; pass the Bluetooth COM port "
                "or /dev/rfcomm* port explicitly.") if bluetooth else ""
        raise ConnectionFailed(f"No robot {what} port found. Ports seen: {[p.device for p in ports] or 'none'}.{hint}")
    raise ConnectionFailed(f"Several possible ports, pass one: {', '.join(p.device for p in matches)}")


def list_ports_info() -> List[str]:
    """List serial ports as "device<TAB>description" lines, to find your robot."""
    return [f"{p.device}\t{p.description}" for p in list_ports.comports()]


def _open(kind: str, value: Optional[str], timeout: float):
    if kind == "mock":
        from petoi.transports.mock import MockTransport
        return MockTransport()
    if kind == "wifi":
        from petoi.transports.websocket import WebSocketTransport
        return WebSocketTransport(value, timeout=timeout)
    if kind == "ble":
        from petoi.transports.ble import BleTransport
        return BleTransport(value, scan_timeout=timeout)
    from petoi.transports.serial import SerialTransport
    if value is None:
        value = pick_serial_port(list_ports.comports(), bluetooth=(kind == "bluetooth"))
    if kind == "bluetooth" or SSP_MARK in value:
        return SerialTransport(value, boot_timeout=0)  # SPP doesn't reset the board
    return SerialTransport(value)  # USB: the transport's default boot wait


def _check_firmware(robot: Robot) -> None:
    try:
        info = robot.info()
    except PetoiError:
        warnings.warn("robot did not answer '?'; its firmware may be too old for this API", RuntimeWarning, stacklevel=3)
        return
    robot.model, robot.firmware = info["model"], info["version"]
    date = info["version"].rsplit("_", 1)[-1]  # BOARD_YYMMDD, src/OpenCat.h:666
    if len(date) == 6 and date.isdigit() and date < MIN_FIRMWARE_DATE:
        warnings.warn(f"firmware {info['version']} is older than {MIN_FIRMWARE_DATE}; some commands may not work. "
                      "Update it with the Petoi Desktop App.", RuntimeWarning, stacklevel=3)


def connect(target: Optional[str] = None, timeout: float = 5.0, check_firmware: bool = True) -> Robot:
    """Connect to a robot. target: None (USB), a port name, "bluetooth", "ble",
    "ble:<address>", a Wi-Fi address, or "mock". timeout is also the BLE scan time."""
    kind, value = classify(target)
    transport = _open(kind, value, timeout)
    try:
        robot = Robot(transport, timeout=timeout)
        if check_firmware:
            _check_firmware(robot)
    except BaseException:
        transport.close()
        raise
    return robot
