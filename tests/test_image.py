"""The Docker image opens the web UI over the seeded plant-kg demo; built with
`--build-arg SEED=none` it runs a stetiq server, with auth on, over an empty tracking database.

Black box: the test starts the image and talks only to its published port (and, for the
no-seed image, runs `stetiq token create` in the container as an administrator would). It
runs the images named by $STETIQ_TEST_IMAGE and $STETIQ_TEST_IMAGE_NO_SEED (CI passes the
ones it just built), else builds them from the repo, which needs the built frontend.
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
NO_SEED_IMAGE_ENV = "STETIQ_TEST_IMAGE_NO_SEED"
KG = "plant-maintenance"


def _unavailable(reason: str):
    if os.environ.get("CI"):
        pytest.fail(f"{reason}: CI must run the image test")
    pytest.skip(reason)


def _docker():
    try:
        import docker
    except ImportError:
        _unavailable("the docker package is not installed")
    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no Docker here"
        _unavailable(f"Docker is unavailable: {exc}")
    return client


def _image(env: str, tag: str, buildargs: dict[str, str] | None = None) -> str:
    client = _docker()
    if name := os.environ.get(env):
        return name
    if not BUILT_SHELL.is_file():
        _unavailable("frontend not built; run `npm run build` in frontend/")
    client.images.build(path=str(REPO_ROOT), tag=tag, rm=True, buildargs=buildargs)
    return tag


def _wait_for(http: httpx.Client, path: str) -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            http.get(path)
            return
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@pytest.fixture(scope="module")
def image() -> str:
    return _image(IMAGE_ENV, "stetiq:test")


@pytest.fixture(scope="module")
def no_seed_image() -> str:
    return _image(NO_SEED_IMAGE_ENV, "stetiq:test-no-seed", {"SEED": "none"})


@pytest.fixture(scope="module")
def ui(image) -> httpx.Client:
    from testcontainers.core.container import DockerContainer

    with DockerContainer(image).with_exposed_ports(5000) as container:
        base = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(5000)}"
        with httpx.Client(base_url=base) as http:
            _wait_for(http, "/ui")
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


def test_the_no_seed_image_serves_an_empty_tracking_database_behind_api_tokens(no_seed_image):
    from testcontainers.core.container import DockerContainer

    with DockerContainer(no_seed_image).with_exposed_ports(5000) as container:
        base = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(5000)}"
        with httpx.Client(base_url=base) as http:
            _wait_for(http, "/api/v1/knowledge-graphs")
            exit_code, output = container.exec(
                ["stetiq", "token", "create", "showcase", "--grant", "*=edit"]
            )
            assert exit_code == 0, output.decode()
            token = output.decode().strip().splitlines()[-1]

            anonymous = http.get("/api/v1/knowledge-graphs")
            signed_in = http.get(
                "/api/v1/knowledge-graphs", headers={"Authorization": f"Bearer {token}"}
            )

    assert anonymous.status_code == 401
    assert signed_in.status_code == 200
    assert signed_in.json() == []
