"""What the command line and the tools share: output that prints on any system, and a parser that refuses what it
does not know."""
from __future__ import annotations

import argparse
import sys


def print_anywhere():
    """Keep a print from ending the run over a character.

    The engine's text holds ° ² ³ and a few accented letters. Where its output is sent to a file or a pipe on
    Windows, Python writes it in the system's code page, and some code pages lack those characters [DOCUMENTED:
    the documentation of sys.stdout for Python 3.13, Doc/library/sys.rst: "On Windows, UTF-8 is used for the
    console device. Non-character devices such as disk files and pipes use the system locale encoding (i.e. the
    ANSI codepage)."]. A print would then raise UnicodeEncodeError and end the run [INFERRED from that and from
    the code pages: the Japanese one, cp932, has none of ² ³ ö]. This keeps the stream's encoding and writes a
    character that it lacks as its escape (\\xb3 for ³).
    [Tried on Linux by naming such an encoding in the environment variable PYTHONIOENCODING: tests/test_tools.py.
    Not run on Windows.]"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):                 # a stream that cannot be set anew (a test's stand-in) is left as it is
            pass


def tool_parser(doc: str, prog: str) -> argparse.ArgumentParser:
    """The parser of a tool: --help prints the tool's own description and ends with 0; an option that the tool
    does not know ends the run with 2 and a line that names it, and so does a shortened option (so that a misspelt
    one is never taken for another)."""
    return argparse.ArgumentParser(prog=prog, description=doc, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)


def whole_number(low: int, high: int | None = None):
    """For argparse: a whole number of at least `low` (and at most `high`)."""
    def read(text):
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
        if value < low or (high is not None and value > high):
            raise argparse.ArgumentTypeError(f"{value} is outside {low} to {high}" if high is not None else f"{value} is below {low}")
        return value
    return read


def number_between(low: float, high: float, open_low: bool = False):
    """For argparse: a number from `low` to `high` (`low` itself left out if open_low)."""
    def read(text):
        try:
            value = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
        if not (low <= value <= high) or (open_low and value == low) or value != value:
            raise argparse.ArgumentTypeError(f"{text} is outside {'above ' if open_low else ''}{low:g} to {high:g}")
        return value
    return read
