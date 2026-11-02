"""The Docker image opens the web UI over the seeded plant-kg demo.

Black box: the test starts the image and talks only to its published port. It runs the
image named by $STETIQ_TEST_IMAGE (CI passes the one it just built), else builds one from
the repo, which needs the built frontend.
"""

import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.image

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILT_SHELL = REPO_ROOT / "src" / "stetiq" / "_frontend" / "index.html"
IMAGE_ENV = "STETIQ_TEST_IMAGE"
KG = "plant-maintenance"


def _unavailable(reason: str):
    if os.environ.get("CI"):
        pytest.fail(f"{reason}: CI must run the image test")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def image() -> str:
    try:
        import docker
    except ImportError:
        _unavailable("the docker package is not installed")
    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no Docker here"
        _unavailable(f"Docker is unavailable: {exc}")
    if name := os.environ.get(IMAGE_ENV):
        return name
    if not BUILT_SHELL.is_file():
        _unavailable("frontend not built; run `npm run build` in frontend/")
    client.images.build(path=str(REPO_ROOT), tag="stetiq:test", rm=True)
    return "stetiq:test"


@pytest.fixture(scope="module")
def ui(image) -> httpx.Client:
    from testcontainers.core.container import DockerContainer

    with DockerContainer(image).with_exposed_ports(5000) as container:
        base = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(5000)}"
        with httpx.Client(base_url=base) as http:
            deadline = time.monotonic() + 30
            while True:
                try:
                    http.get("/ui")
                    break
                except httpx.TransportError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.5)
            yield http


def test_the_image_serves_the_built_web_ui(ui):
    response = ui.get("/ui")

    assert response.status_code == 200
    assert 'src="/ui/assets/' in response.text


def test_the_image_opens_on_the_seeded_plant_kg_demo(ui):
    kgs = ui.get("/api/v1/knowledge-graphs").json()
    versions = ui.get(f"/api/v1/knowledge-graphs/{KG}/ontology-versions").json()
    runs = ui.get(f"/api/v1/knowledge-graphs/{KG}/runs").json()

    assert [kg["name"] for kg in kgs] == [KG]
    # The three recorded rounds: v1, prompt v2's Candidate, the fix.
    assert [v["number"] for v in versions] == [1, 2, 3]
    assert len(runs) == 3
