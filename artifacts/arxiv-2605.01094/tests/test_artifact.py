"""Bounded public-artifact checks; no historical/private folders or ns-3 runs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / 'artifacts/arxiv-2605.01094'

def command(root, *args):
    return subprocess.run([sys.executable, '-B',
        str(root / 'artifacts/arxiv-2605.01094/reproduce.py'), *args], cwd=root,
        capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH='', MPLBACKEND='Agg'), timeout=120)

@pytest.fixture(scope='module')
def isolated(tmp_path_factory):
    root = tmp_path_factory.mktemp('standalone-study')
    manifest = json.loads((ART / 'MANIFEST.json').read_text())
    names = list(manifest['repository_files'])
    names += ['artifacts/arxiv-2605.01094/' + n for n in manifest['artifact_files']]
    names += ['artifacts/arxiv-2605.01094/MANIFEST.json']
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    assert not (root / 'experiments').exists() and not (root / 'paper').exists()
    return root

@pytest.mark.parametrize('args, message', [
    (('verify',), 'Verified'),
    (('workflows', '--smoke'), '10 workflow executions match'),
    (('figures',), 'submitted numerical tables match'),
    (('hidden',), 'Fixed-capture benchmark'),
])
def test_bounded_commands(isolated, args, message):
    result = command(isolated, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert message in result.stdout

@pytest.mark.parametrize('folder', ['artifacts/arxiv-2605.01094', 'arxiv-old', 'ncsim'])
def test_rejects_artifact_output(isolated, folder):
    result = command(isolated, 'paper', '--output', str(isolated / folder))
    assert result.returncode != 0 and 'must be separate' in result.stderr

def test_rejects_changed_and_missing_input(isolated):
    path = isolated / 'artifacts/arxiv-2605.01094/inputs/packet_settings.json'
    saved = path.read_bytes()
    try:
        path.write_bytes(saved + b' ')
        result = command(isolated, 'verify')
        assert result.returncode != 0 and 'hash mismatch' in result.stderr
        path.unlink()
        result = command(isolated, 'verify')
        assert result.returncode != 0 and 'Missing or invalid' in result.stderr
    finally:
        path.write_bytes(saved)

def test_recovered_source_hashes():
    record = json.loads((ART / 'provenance/recorded-source.json').read_text())
    with zipfile.ZipFile(ART / 'provenance/recorded-simulator.zip') as z:
        expected = dict(record['source_sha256'], **{'run_minimal_arxiv.py': record['driver_sha256']})
        assert set(z.namelist()) == set(expected)
        for name, digest in expected.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
