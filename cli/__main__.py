"""CLI entry: ``python -m cli <command>``.

Examples::

    python -m cli screen
    python -m cli save
    python -m cli scene
    python -m cli help
    python -m cli go
    python -m cli bot
    python -m cli bot hermes
    python -m cli client
"""

from __future__ import annotations

import sys

from cli.commands import dispatch
from cli.mode import parse_bot_argv
from utility.telegram_cli import run_cli_bot


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        ok, msg = dispatch("help")
        print(msg)
        print("\npython -m cli bot           听筒（人 / Hermes 当操作员）")
        print("python -m cli bot hermes    同上（别名）")
        print("python -m cli client        Hermes 流水线 client（本机跑完全程）")
        return 0 if ok else 2
    if args[0] in ("client", "hermes-client"):
        from cli.telegram_bot_client import main as client_main

        return client_main(args[1:])
    if args[0] == "bot":
        try:
            mode = parse_bot_argv(args[1:])
        except ValueError as exc:
            print(f"ERROR: {exc}", flush=True)
            return 2
        return run_cli_bot(mode=mode)
    ok, msg = dispatch(" ".join(args))
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
