"""Compile the Ocre setup wizard from the official Vela bundle and Inno script."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from vela.cli.install import read_manifest
from vela.cli.standalone_installer import find_iscc, installer_name, windows_script


def setup_script(bundle: Path, stage: Path, meta: dict, name: str) -> str:
    """Add Ocre welcome, terms and an optional desktop shortcut to Vela's wizard."""
    legal = bundle / "assets/legal"
    terms = legal / "TERMOS-DE-USO.txt"
    intro = legal / "LEIA-ANTES-DE-INSTALAR.txt"
    for source in (terms, intro):
        if not source.is_file():
            raise FileNotFoundError(source)
    icon = bundle / meta["icon"] if meta.get("icon") else None
    script = windows_script(bundle, meta, stage, name, icon=icon)
    script = script.replace(
        "[Setup]\n",
        "[Setup]\nDisableWelcomePage=no\nDisableDirPage=no\n"
        f'LicenseFile="{terms}"\nInfoBeforeFile="{intro}"\n',
        1,
    )
    script = script.replace(
        "[Files]\n",
        '[Languages]\nName: "ptbr"; MessagesFile: "compiler:Languages\\BrazilianPortuguese.isl"\n\n'
        '[Tasks]\nName: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; '
        "Flags: unchecked\n\n[Files]\n",
        1,
    )
    exe = meta["executable"]
    return script.replace(
        "[Run]\n",
        f'Name: "{{autodesktop}}\\Ocre Studio"; Filename: "{{app}}\\{exe}"; '
        'WorkingDir: "{app}"; Tasks: desktopicon\n\n[Run]\n',
        1,
    )


def main() -> None:
    """Build the Windows installer only on the native Windows runner."""
    if platform.system() != "Windows":
        raise SystemExit("Compile o instalador no Windows.")
    dist = Path("dist").resolve()
    bundle = dist / "Ocre-Studio"
    meta = read_manifest(bundle)
    name = installer_name(meta)
    compiler = find_iscc()
    with TemporaryDirectory(prefix="ocre-inno-", dir=dist) as folder:
        stage = Path(folder)
        script = stage / "setup.iss"
        script.write_text(setup_script(bundle, stage, meta, name), encoding="utf-8-sig")
        subprocess.run([str(compiler), str(script)], check=True)
        compiled = stage / (name + ".exe")
        compiled.replace(dist / compiled.name)


if __name__ == "__main__":
    main()
