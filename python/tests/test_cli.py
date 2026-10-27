from conftest import FakeStream
from petoi import Robot, cli


def test_ports_lists_devices(monkeypatch, capsys):
    monkeypatch.setattr(cli, "list_ports_info", lambda: ["/dev/cu.usbserial-1\tUSB Serial"])
    assert cli.main(["ports"]) == 0
    assert "usbserial-1" in capsys.readouterr().out


def test_send_to_mock_prints_reply(capsys):
    assert cli.main(["send", "?", "--to", "mock"]) == 0
    assert "Mock Bittle" in capsys.readouterr().out


def test_connection_error_exits_1(capsys):
    assert cli.main(["send", "ksit", "--to", "/dev/does-not-exist-petoi"]) == 1
    assert "error:" in capsys.readouterr().err


def test_no_reply_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(cli, "connect", lambda to: Robot(FakeStream(auto_echo=False), timeout=0.05))
    assert cli.main(["send", "ksit"]) == 1
    assert "no reply" in capsys.readouterr().err


def test_bad_command_exits_2(capsys):
    assert cli.main(["send", "I8 30", "--to", "mock"]) == 2
    assert "error:" in capsys.readouterr().err
