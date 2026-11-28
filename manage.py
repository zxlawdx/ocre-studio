#!/usr/bin/env python
"""Delegate project commands and exit codes to the official Vela CLI."""

import sys

from vela.cli.commands import CommandRunner

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "buildapp":
        from vela.plugins import register_build_hook

        from tools.build_hooks import exclude_unused_qt, include_native_models

        register_build_hook(exclude_unused_qt)
        register_build_hook(include_native_models)
        if "--plugins" not in sys.argv[2:]:
            sys.argv.append("--plugins")
    result = CommandRunner().execute(sys.argv[1:])
    sys.exit(result if isinstance(result, int) else 0)
