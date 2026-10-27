import threading
import time

import pytest

from conftest import FakeStream
from petoi._timing import skill_seconds
from petoi.constants import Joint, Skill
from petoi.errors import RobotError, RobotTimeout, WifiSetupFailed
from petoi.protocol import encode
from petoi.robot import Robot
from petoi.transports.base import STALE_SECONDS, Transport


def robot(replies=None, **kw):
    return Robot(FakeStream(replies or {}, **kw), timeout=0.2)


def test_raw_send_appends_newline():
    assert robot().send("ksit").completed


def test_raw_send_accepts_space_after_token():
    r = robot({b"k sit\n": ["k"]})
    assert r.send("k sit").completed


@pytest.mark.parametrize(
    "call, sent",
    [
        (lambda r: r.sit(), b"ksit\n"),
        (lambda r: r.stand(), b"kup\n"),
        (lambda r: r.rest(), b"d\n"),
        (lambda r: r.stop(), b"kup\n"),
        (lambda r: r.walk(), b"kwkF\n"),
        (lambda r: r.walk("left"), b"kwkL\n"),
        (lambda r: r.trot("right"), b"ktrR\n"),
        (lambda r: r.crawl(), b"kcrF\n"),
        (lambda r: r.back(), b"kbk\n"),
        (lambda r: r.skill("hi"), b"khi\n"),
        (lambda r: r.skill(Skill.HIGH_FIVE), b"kfiv\n"),
        (lambda r: r.joint(8, 30), b"i8 30\n"),
        (lambda r: r.joint(Joint.HEAD_PAN, -20), b"i0 -20\n"),
        (lambda r: r.move_joints({8: 30, 9: -20}), b"i8 30 9 -20\n"),
        (lambda r: r.move_joints({0: 45}, sequential=True), b"m0 45\n"),
        (lambda r: r.beep(12, 8), b"b12 8\n"),
        (lambda r: r.back("left"), b"kbkL\n"),
        (lambda r: r.back("right"), b"kbkR\n"),
        (lambda r: r.joint(0, 30.7), b"i0 31\n"),
        (lambda r: r.move_joints({8: 29.6, 9: -20.4}), b"i8 30 9 -20\n"),
        (lambda r: r.melody([(12, 8), (0, 4), (14, 8)]), b"b12 8 0 4 14 8\n"),
    ],
)
def test_high_level_commands(call, sent):
    r = robot()
    call(r)
    assert r.transport.written[-1] == sent


def test_unknown_direction_is_a_clear_error():
    with pytest.raises(ValueError, match="forward, left, right"):
        robot().walk("up")


def test_high_level_raises_when_robot_never_confirms():
    r = robot(auto_echo=False)
    with pytest.raises(RobotTimeout, match="did not confirm"):
        r.sit()


def test_raw_send_returns_incomplete_instead_of_raising():
    assert robot(auto_echo=False).send("ksit").completed is False


def test_wait_false_neither_waits_nor_raises():
    robot(auto_echo=False).skill("hi", wait=False)


def test_joints_parses_angle_line():
    r = robot({b"j\n": ["=", "0\t1\t2\t", "0,\t-3,\t45,\t", "j"]})
    assert r.joints() == [0, -3, 45]


def test_info_returns_model_and_version():
    r = robot({b"?\n": ["Bittle X", "B10_260820", "?"]})
    assert r.info() == {"model": "Bittle X", "version": "B10_260820"}


def test_context_manager_closes():
    r = robot()
    with r:
        pass
    assert r.transport.closed


def test_exception_inside_with_stops_robot_then_closes():
    r = robot()
    with pytest.raises(KeyboardInterrupt):
        with r:
            r.walk()
            raise KeyboardInterrupt
    assert r.transport.written[-1] == b"kup\n"
    assert r.transport.closed


class SlowStream(FakeStream):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    def command(self, *args, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        try:
            return super().command(*args, **kwargs)
        finally:
            self.active -= 1


def test_commands_from_threads_never_overlap():
    s = SlowStream()
    r = Robot(s)
    threads = [threading.Thread(target=r.sit) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.max_active == 1


def test_send_timeout_zero_does_not_wait():
    r = robot(auto_echo=False)
    seen = []
    real = r.transport.command
    r.transport.command = lambda token, payload, timeout: (seen.append(timeout), real(token, payload, timeout))[1]
    r.send("ksit", timeout=0)
    assert seen == [0]


def test_send_rejects_embedded_newline():
    with pytest.raises(ValueError, match="newline"):
        robot().send("ksit\nkup")


def test_send_keeps_working_with_trailing_line_ending():
    r = robot()
    assert r.send("ksit\r\n").completed
    assert r.transport.written == [b"ksit\r\n"]


def test_send_rejects_uppercase_token():
    with pytest.raises(ValueError, match="send_binary"):
        robot().send("I8 30")


class FailingStop(FakeStream):
    def write(self, data):
        if data == b"kup\n":
            raise OSError("port gone")
        super().write(data)


def test_failed_safe_stop_does_not_mask_the_users_exception():
    r = Robot(FailingStop())
    with pytest.raises(KeyboardInterrupt):
        with r:
            raise KeyboardInterrupt
    assert r.transport.closed


def test_send_rejects_bare_carriage_return():
    with pytest.raises(ValueError, match="carriage return"):
        robot().send("ksit\rkup")


@pytest.mark.parametrize("on, sent", [(True, b"gB\n"), (False, b"gb\n")])
def test_gyro_sets_balancing_explicitly(on, sent):
    r = robot()
    assert r.gyro(on).completed
    assert r.transport.written[-1] == sent


def test_gyro_off_double_echo_does_not_leak_into_next_reply():
    # gb prints 'g' before its echo (src/reaction.h:579, :1557)
    r = robot({b"gb\n": ["g", "g"], b"?\n": ["Bittle X", "B10_260820", "?"]})
    r.gyro(False)
    assert r.info() == {"model": "Bittle X", "version": "B10_260820"}


def test_back_only_turns_left_or_right():
    with pytest.raises(ValueError, match="left, right"):
        robot().back("forward")


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.sit(wait=False),
        lambda r: r.stand(wait=False),
        lambda r: r.stop(wait=False),
        lambda r: r.rest(wait=False),
        lambda r: r.walk("left", wait=False),
        lambda r: r.trot(wait=False),
        lambda r: r.crawl(wait=False),
        lambda r: r.back(wait=False),
        lambda r: r.joint(8, 30, wait=False),
        lambda r: r.move_joints({8: 30}, wait=False),
        lambda r: r.melody([(12, 8)], wait=False),
    ],
)
def test_wait_false_on_moves_neither_waits_nor_raises(call):
    call(robot(auto_echo=False))


@pytest.mark.parametrize("notes", [[], [(12, 0)], [(12,)], [(12, 8, 1)]])
def test_melody_rejects_what_the_firmware_would_misread(notes):
    # bare 'b' toggles all sound (src/reaction.h:967); duration 0 is skipped (:1003)
    with pytest.raises(ValueError):
        robot().melody(notes)


def test_melody_waits_for_its_own_length():
    r = robot()
    seen = []
    command = r.transport.command
    r.transport.command = lambda token, payload, timeout: seen.append(timeout) or command(token, payload, timeout)
    r.melody([(12, 1), (14, 4)])  # 1000/1 + 1000/4 ms (src/reaction.h:1004)
    assert seen == [pytest.approx(0.2 + 1.25)]


def test_every_public_method_has_a_docstring():
    public = [n for n in dir(Robot) if not n.startswith("_")]
    assert [n for n in public if callable(getattr(Robot, n)) and not getattr(Robot, n).__doc__] == []


def test_gyro_state_parses_the_state_line():
    # src/reaction.h:608-612 prints one line on USB; other output may come first
    r = robot({b"g?\n": ["ypr 1 2 3", "Gyro state: Update-1 Balance-0 Print-0 Frequency-1", "g"]})
    assert r.gyro_state() == {"update": True, "balance": False, "print": False, "fine": True}
    assert r.transport.written[-1] == b"g?\n"


def test_gyro_state_without_state_line_is_an_error():
    r = robot({b"g?\n": ["g"]})  # e.g. over BLE: the line is USB-only (src/tools.h:6)
    with pytest.raises(RobotError, match="gyro state"):
        r.gyro_state()


def test_calibrate_gyro_waits_for_calibration_done():
    r = robot({b"gc\n": [
        "Setting updateGyroQ to false...", "Calibrating...", "Calibration done.",
        "Calibration completed, allowing IMU to stabilize...", "Creating IMU task...", "g",
    ]})
    seen = []
    command = r.transport.command
    r.transport.command = lambda token, payload, timeout: seen.append(timeout) or command(token, payload, timeout)
    assert r.calibrate_gyro().completed
    assert r.transport.written[-1] == b"gc\n"
    assert seen == [pytest.approx(0.2 + 20)]


def test_calibrate_gyro_raises_when_firmware_gives_up():
    r = robot({b"gc\n": [
        "Timeout waiting for calibration to complete. Forcing continuation.",
        "Calibration completed, allowing IMU to stabilize...", "g",
    ]})
    with pytest.raises(RobotError, match="calibration did not finish"):
        r.calibrate_gyro()


def recorded_timeouts(r):
    seen = []
    command = r.transport.command
    r.transport.command = lambda token, payload, timeout: seen.append(timeout) or command(token, payload, timeout)
    return seen


def test_skill_waits_skill_timeout_because_it_confirms_when_finished():
    r = robot()
    seen = recorded_timeouts(r)
    r.skill(Skill.CLAP)
    r.skill("anything")
    assert seen == [r.skill_timeout, r.skill_timeout]


def test_skill_timeout_can_be_overridden_per_call():
    r = robot()
    seen = recorded_timeouts(r)
    r.skill("myLongSkill", timeout=60)
    assert seen == [60]


@pytest.mark.parametrize(
    "call",
    [lambda r: r.sit(), lambda r: r.stand(), lambda r: r.stop(), lambda r: r.walk(),
     lambda r: r.trot("left"), lambda r: r.crawl(), lambda r: r.back("right")],
)
def test_gaits_and_postures_keep_the_short_timeout(call):
    r = robot()  # gaits echo when they start (src/reaction.h:1555-1565)
    seen = recorded_timeouts(r)
    call(r)
    assert seen == [0.2]


def test_skill_timeout_error_names_the_skill_limit():
    r = Robot(FakeStream({}, auto_echo=False), timeout=0.2, skill_timeout=0.3)
    with pytest.raises(RobotTimeout, match=r"within 0\.3s"):
        r.skill("hi")


def test_default_skill_timeout_fits_between_stale_window_and_wifi_abort():
    # at least the 15 s stale window, below the Wi-Fi server's 45 s task abort (src/webServer.h:53)
    assert STALE_SECONDS <= Robot(FakeStream()).skill_timeout < 45


UP = [0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30]  # Bittle "up" (src/InstinctBittleESP.h:1898-1900)
POSTURE = [1, 0, 0, 1] + UP
STILL = UP + [8, 0, 0, 0]  # speed 8/8 = 1 degree a step, no pause, no gyro trigger
HEAD = [30] + UP[1:] + [8, 0, 0, 0]


def behavior(*frames, loop=(0, 0, 0)):
    return [-len(frames), 0, 0, 1, *loop] + [v for f in frames for v in f]


def test_skill_data_is_sent_as_one_binary_command():
    r = robot()
    assert r.run_skill_data(POSTURE).completed
    assert r.transport.written == [b"K\x01\x00\x00\x01" + bytes(UP) + b"~"]


@pytest.mark.parametrize("width", [8, 12])
def test_gait_frames_may_be_8_or_12_wide(width):
    r = robot()
    r.run_skill_data([2, 0, 0, 1] + [10] * (2 * width))
    assert r.transport.written[-1] == encode("K", 2, 0, 0, 1, *([10] * (2 * width)))


def test_bittle_gait_must_be_8_wide():
    r = robot()
    r.model = "Bittle X"
    with pytest.raises(ValueError, match="needs 20 values"):
        r.run_skill_data([2, 0, 0, 1] + [10] * 24)


def test_behavior_waits_for_its_second_echo():
    data = behavior(STILL, HEAD, STILL)
    r = robot({encode("K", *data): ["K", "note", "K"]})
    reply = r.run_skill_data(data)
    assert reply.completed and reply.lines == ["note"]


def test_behavior_without_end_echo_raises():
    data = behavior(STILL, HEAD)
    r = robot({encode("K", *data): ["K"]})  # started, never finished
    with pytest.raises(RobotTimeout, match="uploaded skill"):
        r.run_skill_data(data)


def test_behavior_wait_false_owes_both_echoes():
    r = robot(auto_echo=False)
    r.run_skill_data(behavior(STILL, HEAD), wait=False)
    r.transport.replies[b"ksit\n"] = ["K", "K", "k"]  # both late K echoes arrive during the next command
    assert r.sit().lines == []


@pytest.mark.parametrize(
    "data, message",
    [
        ([1, 0, 0], "header"),
        ([0, 0, 0, 1], "cannot be 0"),
        ([1, 0, 0, 3] + UP, "angle ratio"),
        ([1, 0, 0, 1] + UP[:-1], "needs 20 values"),
        ([2, 0, 0, 1] + [0] * 20, "needs 20 or 28 values"),
        (behavior(STILL, loop=(0, 0, -1)), "forever"),
        (behavior(STILL, STILL, loop=(0, 2, 3)), "loop rows"),
        ([1, 0, 0, 1] + UP[:-1] + [126], "126 at index 19"),
        ([1, 0, 0, 1] + UP[:-1] + [200], "int8"),
        (behavior(*[STILL] * 125), "too long"),
        (["1", 0, 0, 1] + UP, "integers"),
    ],
)
def test_skill_data_rejects_what_the_robot_would_misread(data, message):
    r = robot()
    with pytest.raises(ValueError, match=message):
        r.run_skill_data(data)
    assert r.transport.written == []


def test_behavior_time_from_frame_0_counts_pauses_and_loops():
    pause = UP + [0, 20, 0, 0]  # jump, then 20 x 50 ms = 1 s (src/skill.h:355)
    start = UP  # the robot is already at frame 0 when the behavior starts (src/reaction.h:1414)
    assert 2.0 <= skill_seconds(behavior(pause, pause), start) < 2.1
    assert 6.0 <= skill_seconds(behavior(pause, pause, loop=(0, 1, 3)), start) < 6.1  # rows 0-1 run three times


def test_behavior_waits_robot_timeout_plus_one_and_a_half_estimates():
    data = [-2, 0, 0, 2, 0, 0, 0] + STILL + HEAD  # angle ratio 2: frame 0 is UP doubled
    r = robot({encode("K", *data): ["K", "K"]})
    seen = []
    expect = r.transport.expect
    r.transport.expect = lambda token, timeout: seen.append(timeout) or expect(token, timeout)
    r.run_skill_data(data)
    # command() waits for the start echo through expect() too
    assert seen == [0.2, pytest.approx(0.2 + 1.5 * skill_seconds(data, [2 * a for a in UP]))]
    assert skill_seconds(data, [2 * a for a in UP]) == pytest.approx((1 + 1 + 61) * 0.008)  # 60 degrees doubled


def test_posture_and_gait_uploads_keep_the_short_timeout():
    r = robot()
    seen = recorded_timeouts(r)
    r.run_skill_data(POSTURE)
    r.run_skill_data([2, 0, 0, 1] + [10] * 16)
    r.run_skill_data(POSTURE, timeout=3)
    assert seen == [0.2, 0.2, 3]


PW = "s3cret-pw-9876"
SENT = b"w%Home%" + PW.encode() + b"\n"
INTRO = [  # src/reaction.h:440, :447, :458 (the robot shows the last 4 characters)
    "The wifi info should start with 'w' and followed by ssid and password, separated by %.",
    " e.g. w%WifiName%password",
    "WifiSSID: \tHome",
    "Password: \t**********9876",
]
JOINED = "Successfully connected Wifi to IP Address: 192.168.1.23"  # src/reaction.h:465, src/webServer.h:622


def wifi_robot(lines):
    return robot({SENT: INTRO + lines})


def assert_secret_kept(error):
    assert PW not in str(error) and "9876" not in str(error)


def test_setup_wifi_returns_the_ip_after_the_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.", "ets Jun  8 2016 00:22:57", JOINED, "Ready!"])
    assert r.setup_wifi("Home", PW) == "192.168.1.23"
    assert r.transport.written == [SENT]


def test_setup_wifi_prefers_the_address_from_after_the_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.",
                    "Successfully connected Wifi to IP Address: 192.168.1.40", "Ready!"])
    assert r.setup_wifi("Home", PW) == "192.168.1.40"


def test_setup_wifi_wrong_password_raises_without_the_password():
    r = wifi_robot([f"WiFi connection failed on attempt: \t{n}" for n in (1, 2, 3)]
                   + ["All WiFi connection attempts failed", "Timeout: Fail to connect Wifi!", "w"])
    with pytest.raises(WifiSetupFailed, match="'Home'") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_raises_if_the_robot_cannot_rejoin_after_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.", "Timeout: Fail to connect web server!", "Ready!"])
    with pytest.raises(WifiSetupFailed, match="rejoin") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_returns_the_ip_with_a_warning_if_the_reboot_is_slow():
    r = wifi_robot([JOINED, "Rebooting to use web server."])
    with pytest.warns(RuntimeWarning, match="did not finish rebooting"):
        assert r.setup_wifi("Home", PW, timeout=0.2) == "192.168.1.23"


def test_setup_wifi_when_already_on_wifi_warns_and_returns_the_ip():
    r = robot({SENT: ["Wifi already connected to IP Address: 10.0.0.7",  # src/reaction.h:485-488
                      "Web server should already be running",
                      "Press the BOOT key to reboot and use Wifi manager.",
                      "Hold the BOOT key and count down 10 if you want to clear the previous Wifi credentials.",
                      "w"]})
    with pytest.warns(RuntimeWarning, match="already on Wi-Fi") as seen:
        assert r.setup_wifi("Home", PW) == "10.0.0.7"
    assert_secret_kept(seen[0].message)


def test_setup_wifi_silence_raises_timeout_without_the_password():
    r = robot(auto_echo=False)
    with pytest.raises(RobotTimeout, match="Wi-Fi") as e:
        r.setup_wifi("Home", PW, timeout=0.2)
    assert_secret_kept(e.value)


def test_setup_wifi_on_firmware_without_wifi_hides_the_echoed_command():
    r = robot({SENT: ["Undefined token!", "%Home%" + PW, "w"]})  # src/reaction.h:1535-1536
    with pytest.raises(RobotError, match="no Wi-Fi support") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)
    assert r.transport.pending == []  # the echoed command (with the password) was read and dropped


def test_setup_wifi_bare_echo_means_not_accepted():
    with pytest.raises(RobotError, match="did not accept"):
        robot({SENT: INTRO[:2] + ["w"]}).setup_wifi("Home", PW)


def test_setup_wifi_forgets_echoes_owed_from_before_the_reboot():
    r = robot()
    r.sit(wait=False)
    assert r.transport._unconfirmed
    r.transport.replies[SENT] = INTRO + [JOINED, JOINED, "Ready!"]
    r.setup_wifi("Home", PW)
    assert r.transport._unconfirmed == []


@pytest.mark.parametrize("password", ["", "a%b c"])  # open network; '%' kept (src/reaction.h:446)
def test_setup_wifi_sends_open_and_percent_passwords_unchanged(password):
    name = "n" * 32
    ip = "Successfully connected Wifi to IP Address: 10.0.0.9"
    r = robot({f"w%{name}%{password}\n".encode(): [ip, ip, "Ready!"]})
    assert r.setup_wifi(name, password) == "10.0.0.9"


@pytest.mark.parametrize(
    "ssid, password, match",
    [
        ("", PW, "1 to 32 bytes"),
        ("x" * 33, PW, "1 to 32 bytes"),
        ("\u00e9" * 17, PW, "1 to 32 bytes"),  # 34 UTF-8 bytes
        ("my%net", PW, "%"),
        ("Home\n", PW, "line break"),
        ("Home", "p" * 65, "64 bytes"),
        ("Home", PW + "\r", "line break"),
        ("Home", PW + "\0", "line break"),
    ],
)
def test_setup_wifi_rejects_what_the_firmware_would_misread(ssid, password, match):
    r = robot()
    with pytest.raises(ValueError, match=match) as e:
        r.setup_wifi(ssid, password)
    assert r.transport.written == []
    assert password not in str(e.value) and PW not in str(e.value)


class NotAStream(Transport):
    def command(self, token, payload, timeout):
        raise AssertionError("must not send")

    def close(self):
        pass


def test_setup_wifi_needs_a_serial_link():
    with pytest.raises(RobotError, match="USB"):
        Robot(NotAStream()).setup_wifi("Home", PW)


def test_behavior_start_timeout_owes_both_echoes():
    data = behavior(STILL, HEAD)
    r = robot({encode("K", *data): []})
    with pytest.raises(RobotTimeout):
        r.run_skill_data(data)  # the robot still sends a start and an end K later
    r.transport.replies[encode("K", *data)] = ["K", "K", "K"]  # two late echoes, then only this upload's start
    with pytest.raises(RobotTimeout):
        r.run_skill_data(data)  # must not take the late echoes for its own


def test_setup_wifi_timeout_starts_after_the_lock_is_free():
    r = wifi_robot([JOINED, JOINED, "Ready!"])
    r._lock.acquire()
    threading.Timer(0.4, r._lock.release).start()  # another command holds the link for a while
    assert r.setup_wifi("Home", PW, timeout=0.3) == "192.168.1.23"


def test_setup_wifi_refuses_ble():
    from petoi.transports.ble import BleTransport

    with pytest.raises(RobotError, match="USB"):
        Robot(object.__new__(BleTransport)).setup_wifi("Home", PW)  # the reboot drops BLE; failures print to USB only
