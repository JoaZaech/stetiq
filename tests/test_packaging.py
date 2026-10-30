"""The wheel ships the built web UI, so an installed stetiq serves `/ui` without Node."""

import os
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILT_SHELL = REPO_ROOT / "src" / "stetiq" / "_frontend" / "index.html"


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> zipfile.ZipFile:
    if not BUILT_SHELL.is_file():
        if os.environ.get("CI"):
            pytest.fail(f"{BUILT_SHELL} is missing: CI must build the frontend first")
        pytest.skip("frontend not built; run `npm run build` in frontend/")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), str(REPO_ROOT)],
        check=True,
        capture_output=True,
    )
    [built] = out.glob("stetiq-*.whl")
    return zipfile.ZipFile(built)


def test_the_wheel_contains_the_built_frontend(wheel):
    names = wheel.namelist()

    assert "stetiq/_frontend/index.html" in names
    assert "stetiq/_frontend/favicon.svg" in names
    assert any(n.startswith("stetiq/_frontend/assets/") and n.endswith(".js") for n in names)
    assert any(n.startswith("stetiq/_frontend/assets/") and n.endswith(".css") for n in names)
    shell = wheel.read("stetiq/_frontend/index.html").decode()
    assert 'src="/ui/assets/' in shell
