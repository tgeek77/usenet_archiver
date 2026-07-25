"""Application entry: GUI by default, ``-c`` for CLI-only."""

from __future__ import annotations

import sys

# Top-level flags that should never launch the GUI.
_HELP_FLAGS = frozenset({"-h", "--help"})
_VERSION_FLAGS = frozenset({"-V", "--version"})


def run() -> None:
    """Zipapp / console_scripts / ``python -m usenet_archiver`` entry point.

    Default launches the Tk GUI. Pass ``-c`` as the first argument to run the
    CLI instead (remaining argv are forwarded to the CLI parser).

    ``--help`` / ``-h`` and ``--version`` / ``-V`` work without ``-c``.
    """
    argv = sys.argv[1:]

    if argv and argv[0] == "-c":
        sys.argv = [sys.argv[0], *argv[1:]]
        from .cli import run as cli_run

        cli_run()
        return

    # Help / version at the top level (no -c required).
    if argv and argv[0] in _HELP_FLAGS:
        from .cli import build_parser

        build_parser().print_help()
        raise SystemExit(0)

    if argv and argv[0] in _VERSION_FLAGS:
        from . import __version__

        sys.stdout.write(f"usenet-archiver {__version__}\n")
        raise SystemExit(0)

    try:
        from .gui import main as gui_main
    except ImportError as e:
        sys.stderr.write(
            "error: Tkinter GUI is unavailable ({0}).\n"
            "Install python3-tk (or your OS Tk package), or run the CLI with:\n"
            "  {1} -c pull --help\n"
            "Top-level help (no GUI): {1} --help\n".format(e, sys.argv[0])
        )
        raise SystemExit(1) from e
    gui_main()


if __name__ == "__main__":
    run()
