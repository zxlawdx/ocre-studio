#!/usr/bin/env python
"""Delegate project commands and exit codes to the official Vela CLI."""

import sys

from vela.cli.commands import CommandRunner

if __name__ == "__main__":
    result = CommandRunner().execute(sys.argv[1:])
    sys.exit(result if isinstance(result, int) else 0)
