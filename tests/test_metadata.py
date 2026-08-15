"""Release metadata consistency tests."""

import json
import tomllib
from pathlib import Path

import yaml

from ncsim import __version__
from ncsim.main import main
from viz.server.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_match() -> None:
    """Package, citation, CLI API, and visualization versions stay aligned."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    with (ROOT / "CITATION.cff").open(encoding="utf-8") as handle:
        citation_version = str(yaml.safe_load(handle)["version"])

    with (ROOT / "viz" / "package.json").open(encoding="utf-8") as handle:
        visualization_version = json.load(handle)["version"]

    with (ROOT / "viz" / "package-lock.json").open(encoding="utf-8") as handle:
        visualization_lock = json.load(handle)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert __version__ == project_version
    assert citation_version == project_version
    assert visualization_version == project_version
    assert visualization_lock["version"] == project_version
    assert visualization_lock["packages"][""]["version"] == project_version
    assert app.version == project_version
    assert f"version   = {{{project_version}}}" in readme


def test_cli_version_uses_package_metadata(capsys) -> None:
    """The CLI version flag reports the installed distribution version."""
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("--version did not exit")

    assert capsys.readouterr().out.strip() == f"ncsim {__version__}"
