"""Exercise every final artifact with clean user data and offline inference."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.model_library.native import BUNDLED_MODELS, V7_PAYLOAD, NativeModelRegistry
from tools.release_artifacts import artifacts, digest


def run(command, env=None, cwd=None) -> None:
    subprocess.run(command, env=env, cwd=cwd, check=True, timeout=300)


def check_executable(executable: Path, env: dict[str, str], work: Path) -> None:
    report = work / "inference.json"
    command = [executable, "--self-test", f"--self-test-report={report}"]
    if os.name == "nt":
        rule = f"Ocre-offline-{work.name}"
        firewall = ["netsh", "advfirewall", "firewall"]
        run(
            [
                *firewall,
                "add",
                "rule",
                f"name={rule}",
                "dir=out",
                "action=block",
                "profile=any",
                f"program={executable}",
            ]
        )
        try:
            run(command, env, work)
        finally:
            run([*firewall, "delete", "rule", f"name={rule}"])
    else:
        run(command, env, work)
    expected = {
        preset: {"device": "cpu", "checkpoints": V7_PAYLOAD}
        for preset in ("adaptativo", "cromatico", "combinado")
    }
    if json.loads(report.read_text(encoding="utf-8")) != expected:
        raise ValueError(f"Invalid packaged inference report from {executable}.")


def check_artifact(artifact: Path, platform: str, work: Path) -> None:
    env = os.environ.copy()
    env.pop("OCRE_MODEL_DIR", None)
    for variable in (
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "LOCALAPPDATA",
        "APPDATA",
    ):
        directory = work / variable
        directory.mkdir()
        env[variable] = str(directory)
    if platform == "linux":
        home = work / "home"
        home.mkdir()
        env["HOME"] = str(home)

    target = work / "installed"
    executable = "Ocre-Studio.exe" if platform == "windows" else "Ocre-Studio"
    match artifact.suffix:
        case ".zip":
            if platform == "linux":
                run(["unzip", "-q", artifact, "-d", target])
            else:
                shutil.unpack_archive(artifact, target)
            target /= "Ocre-Studio"
        case ".exe":
            run(
                [
                    artifact,
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    "/TASKS=desktopicon",
                    f"/DIR={target}",
                ],
                env,
                work,
            )
            if not (target / "assets/legal/TERMOS-DE-USO.txt").is_file():
                raise FileNotFoundError("Termos ausentes na instalação Windows.")
        case ".run":
            run(["sh", artifact], env, work)
            target = Path(env["XDG_DATA_HOME"]) / "vela-apps/Ocre-Studio"
        case ".deb":
            (target / "var/lib/dpkg").mkdir(parents=True)
            run(["sudo", "-n", "dpkg", f"--root={target}", "--force-depends", "-i", artifact])
            target /= "opt/Ocre-Studio"
        case ".rpm":
            target.mkdir()
            run(["sudo", "-n", "rpm", "--root", target, "--nodeps", "-i", artifact])
            target /= "opt/Ocre-Studio"
        case ".AppImage":
            env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
            check_executable(artifact, env, work)
            return
        case _:
            raise ValueError(f"Unknown distribution format: {artifact.name}")
    registry = NativeModelRegistry(target / BUNDLED_MODELS)
    if not registry.available():
        raise FileNotFoundError(f"Incomplete Kokentau payload in {artifact.name}.")
    for name, expected in V7_PAYLOAD.items():
        if digest(registry.directory / "v7" / name) != expected:
            raise ValueError(f"Invalid SHA-256 for {name} in {artifact.name}.")
    check_executable(target / executable, env, work)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("platform", choices=("windows", "linux"))
    args = parser.parse_args()
    for artifact in artifacts(args.dist.resolve(), args.platform):
        if artifact.suffix == ".json":
            continue
        print(f"Validating installed Kokentau runtime: {artifact.name}", flush=True)
        with TemporaryDirectory(prefix="ocre-offline-") as directory:
            work = Path(directory)
            try:
                check_artifact(artifact, args.platform, work)
            finally:
                if artifact.suffix in {".deb", ".rpm"}:
                    run(["sudo", "-n", "rm", "-rf", "--", work / "installed"])


if __name__ == "__main__":
    main()
