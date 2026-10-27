import os
import warnings

import pytest

import petoi

PORT = os.environ.get("PETOI_PORT")
SSID = os.environ.get("PETOI_WIFI_SSID")
PASSWORD = os.environ.get("PETOI_WIFI_PASSWORD", "")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not (PORT and SSID), reason="set PETOI_PORT, PETOI_WIFI_SSID and PETOI_WIFI_PASSWORD"),
]


def test_wrong_password_fails_without_leaking_it():  # runs first: once joined, the robot ignores new details
    bad = "petoi-wrong-password"
    with petoi.connect(PORT) as robot:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                robot.setup_wifi(SSID, bad)
            except petoi.WifiSetupFailed as e:
                assert bad not in str(e) and bad[-4:] not in str(e)
                return
    pytest.skip("robot is already on Wi-Fi; hold its BOOT button to clear it to run this test")


def test_setup_wifi_then_connect_over_wifi():
    with petoi.connect(PORT) as robot:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # already on Wi-Fi from an earlier run is fine
            ip = robot.setup_wifi(SSID, PASSWORD)
        print(f"\nrobot joined {SSID!r} at {ip}")
        assert robot.info()["model"]  # same USB connection still works after the reboot (open question 1)
    with petoi.connect(ip) as wifi:
        assert wifi.info()["model"]
