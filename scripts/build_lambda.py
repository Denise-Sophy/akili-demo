"""Build build/akili-lambda.zip for the AWS Lambda Python 3.12 runtime (x86_64). No Docker needed.

    python scripts/build_lambda.py

pip evaluates environment markers (e.g. `pywin32; sys_platform == "win32"`) against the
machine it runs on, even with --platform, so it can't resolve Linux deps from Windows.
Instead: walk the dependency tree of the versions installed (and tested) in this venv,
evaluating markers as Linux, then download exactly those versions as Linux wheels.
"""
import re
import shutil
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
except ImportError:  # packaging ships inside pip
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "lambda"
ZIP = ROOT / "build" / "akili-lambda.zip"
PACKAGES = ["server", "security", "memory"]
DATA = ["fixtures/demo_data.json"]

LINUX = {**default_environment(), "sys_platform": "linux", "platform_system": "Linux",
         "os_name": "posix", "platform_machine": "x86_64", "python_version": "3.12",
         "python_full_version": "3.12.0", "implementation_name": "cpython"}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def linux_closure(roots: list[str]) -> dict[str, str]:
    """name -> installed version, for roots and everything they need on Linux."""
    pinned: dict[str, str] = {}
    queue = [(r, set()) for r in roots]
    while queue:
        spec, extras = queue.pop()
        req = Requirement(spec)
        name = norm(req.name)
        extras = extras | set(req.extras)
        if name in pinned and not req.extras:
            continue
        dist = metadata.distribution(req.name)
        pinned[name] = dist.version
        for dep in dist.requires or []:
            d = Requirement(dep)
            if d.marker is None:
                queue.append((dep.split(";")[0], set()))
                continue
            for extra in extras or {""}:
                if d.marker.evaluate({**LINUX, "extra": extra}):
                    queue.append((dep.split(";")[0], set()))
                    break
    return pinned


roots = [Requirement(line.split("#")[0].strip()).name
         for line in (ROOT / "requirements-server.txt").read_text().splitlines()
         if line.split("#")[0].strip()]
pins = linux_closure(roots)
print(f"{len(pins)} packages:", ", ".join(f"{n}=={v}" for n, v in sorted(pins.items())))

shutil.rmtree(BUILD, ignore_errors=True)
BUILD.mkdir(parents=True)
subprocess.run([
    sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
    # python3.12 on Lambda runs Amazon Linux 2023 (glibc 2.34): wheels up to manylinux_2_34 work.
    "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_34_x86_64",
    "--implementation", "cp", "--python-version", "3.12", "--only-binary=:all:",
    "--target", str(BUILD), *[f"{n}=={v}" for n, v in pins.items()],
], check=True)

for pkg in PACKAGES:
    shutil.copytree(ROOT / pkg, BUILD / pkg, ignore=shutil.ignore_patterns("__pycache__"))
for f in DATA:
    (BUILD / f).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / f, BUILD / f)

ZIP.unlink(missing_ok=True)
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted(BUILD.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            z.write(path, path.relative_to(BUILD).as_posix())
print(f"built {ZIP} ({ZIP.stat().st_size / 1_000_000:.1f} MB)")
