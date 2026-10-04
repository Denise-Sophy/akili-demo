"""Build build/akili-lambda.zip for the AWS Lambda Python 3.12 runtime (x86_64). No Docker needed.

    python scripts/build_lambda.py
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "lambda"
ZIP = ROOT / "build" / "akili-lambda.zip"
PACKAGES = ["server", "security", "memory"]
DATA = ["fixtures/demo_data.json"]

shutil.rmtree(BUILD, ignore_errors=True)
BUILD.mkdir(parents=True)

# Linux wheels for Lambda, whatever OS this runs on.
subprocess.run([
    sys.executable, "-m", "pip", "install", "--quiet",
    # python3.12 on Lambda runs Amazon Linux 2023 (glibc 2.34), so wheels up to manylinux_2_34 work.
    "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_34_x86_64",
    "--implementation", "cp", "--python-version", "3.12",
    "--only-binary=:all:", "--target", str(BUILD), "-r", str(ROOT / "requirements-server.txt"),
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
