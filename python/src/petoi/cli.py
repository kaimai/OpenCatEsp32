from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from petoi.connect import connect, list_ports_info
from petoi.errors import PetoiError


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="petoi", description="Talk to a Petoi robot.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports", help="list serial ports")
    send = sub.add_parser("send", help="send a command, e.g. petoi send ksit")
    send.add_argument("command")
    send.add_argument("--to", default=None, help="port, 'bluetooth', 'ble', a Wi-Fi address, or 'mock'")
    args = parser.parse_args(argv)

    if args.cmd == "ports":
        for line in list_ports_info():
            print(line)
        return 0
    try:
        with connect(args.to) as robot:
            reply = robot.send(args.command)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except PetoiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not reply.completed:
        if reply.text:
            print(reply.text)
        print("no reply", file=sys.stderr)
        return 1
    print(reply.text or "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
