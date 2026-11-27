"""Correct the Vela 0.2.2 shutdown probe on the pinned dependency only."""

from pathlib import Path

from vela.cli import selftest


def main() -> None:
    path = Path(selftest.__file__)
    source = path.read_text(encoding="utf-8")
    old = '    checks["shutdown"] = ApiServer.is_port_available("127.0.0.1", port)'
    new = """    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            checks["shutdown"] = False
    except ConnectionRefusedError:
        checks["shutdown"] = True"""
    if new in source:
        return
    previous = new.replace("timeout=5", "timeout=1")
    if previous in source:
        path.write_text(source.replace(previous, new, 1), encoding="utf-8")
        return
    if source.count(old) != 1:
        raise RuntimeError("Vela revision does not match the expected shutdown probe.")
    source = source.replace("import platform\n", "import platform\nimport socket\n", 1)
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
