"""
ncsim-viz backend server.

Provides API endpoints to run ncsim experiments and browse saved results.

Usage:
    cd ncsim-viz/server
    python run.py
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ncsim-viz API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sequential execution lock - only one ncsim run at a time
_run_lock = asyncio.Lock()

# Path to sample-runs directory (relative to ncsim-viz root)
NCSIM_VIZ_ROOT = Path(__file__).parent.parent
SAMPLE_RUNS_DIR = NCSIM_VIZ_ROOT / "public" / "sample-runs"
NCSIM_ROOT = NCSIM_VIZ_ROOT.parent  # Repo root IS the ncsim project


class RunRequest(BaseModel):
    name: str
    scenario_yaml: str


class RunResponse(BaseModel):
    status: str
    scenario_yaml: str
    trace_jsonl: str
    metrics_json: str
    error: str | None = None


class ExperimentSummary(BaseModel):
    name: str
    scenario_name: str
    makespan: float | None = None
    total_tasks: int | None = None
    total_transfers: int | None = None
    scheduler: str | None = None
    status: str | None = None
    seed: int | None = None


@app.get("/api/experiments")
async def list_experiments() -> list[ExperimentSummary]:
    """Scan sample-runs/ directories and return summaries."""
    experiments: list[ExperimentSummary] = []

    if not SAMPLE_RUNS_DIR.exists():
        return experiments

    for run_dir in sorted(SAMPLE_RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue

        metrics_path = run_dir / "metrics.json"
        scenario_path = run_dir / "scenario.yaml"

        summary = ExperimentSummary(
            name=run_dir.name,
            scenario_name=run_dir.name,
        )

        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                summary.scenario_name = metrics.get("scenario", run_dir.name)
                summary.makespan = metrics.get("makespan")
                summary.total_tasks = metrics.get("total_tasks")
                summary.total_transfers = metrics.get("total_transfers")
                summary.status = metrics.get("status")
                summary.seed = metrics.get("seed")
            except (json.JSONDecodeError, OSError):
                pass

        # Try to extract scheduler from scenario YAML
        if scenario_path.exists():
            try:
                import yaml
                scenario_data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
                config = scenario_data.get("scenario", {}).get("config", {})
                summary.scheduler = config.get("scheduler")
            except Exception:
                pass

        experiments.append(summary)

    return experiments


@app.get("/api/experiments/{name}")
async def get_experiment(name: str) -> dict:
    """Load all files for a specific experiment."""
    run_dir = SAMPLE_RUNS_DIR / name
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Experiment '{name}' not found")

    result: dict = {"name": name}

    scenario_path = run_dir / "scenario.yaml"
    trace_path = run_dir / "trace.jsonl"
    metrics_path = run_dir / "metrics.json"

    if scenario_path.exists():
        result["scenario_yaml"] = scenario_path.read_text(encoding="utf-8")
    if trace_path.exists():
        result["trace_jsonl"] = trace_path.read_text(encoding="utf-8")
    if metrics_path.exists():
        result["metrics_json"] = metrics_path.read_text(encoding="utf-8")

    return result


@app.post("/api/run")
async def run_experiment(req: RunRequest) -> RunResponse:
    """Run ncsim with the given scenario YAML and return results."""
    async with _run_lock:
        return await _run_ncsim(req)


async def _run_ncsim(req: RunRequest) -> RunResponse:
    """Execute ncsim in a subprocess and collect output."""
    import re

    # Slugify the name for directory
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-") or "experiment"
    timestamp = int(time.time())
    run_name = f"{slug}-{timestamp}"

    output_dir = SAMPLE_RUNS_DIR / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write scenario YAML to a temp directory OUTSIDE the output dir.
    # ncsim's main.py copies scenario into output_dir via shutil.copy2,
    # so the source must be a different file. Use mkdtemp + manual write
    # to avoid Windows NamedTemporaryFile lock issues.
    tmp_dir = Path(tempfile.mkdtemp(prefix="ncsim_"))
    scenario_path = tmp_dir / "scenario.yaml"
    scenario_path.write_text(req.scenario_yaml, encoding="utf-8")

    try:
        # Run ncsim as subprocess
        import sys
        import subprocess
        python = sys.executable
        ncsim_main = NCSIM_ROOT / "ncsim" / "main.py"

        cmd = [
            python, str(ncsim_main),
            "--scenario", str(scenario_path),
            "--output", str(output_dir),
            "--verbose",
        ]

        # Use synchronous subprocess.run wrapped in asyncio.to_thread
        # (async subprocess has issues on Windows with uvicorn reload)
        def _run_sync():
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(NCSIM_ROOT),
                timeout=60,
            )

        result = await asyncio.to_thread(_run_sync)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or f"ncsim exited with code {result.returncode}"
            return _build_response(output_dir, req.scenario_yaml, "error", error_msg)

        # Check if output files were actually produced
        trace_path = output_dir / "trace.jsonl"
        if not trace_path.exists():
            error_msg = result.stderr.strip() or result.stdout.strip() or "ncsim produced no output files"
            return _build_response(output_dir, req.scenario_yaml, "error", error_msg)

        return _build_response(output_dir, req.scenario_yaml, "completed")

    except asyncio.TimeoutError:
        return RunResponse(
            status="error",
            scenario_yaml=req.scenario_yaml,
            trace_jsonl="",
            metrics_json="",
            error="Simulation timed out after 60 seconds",
        )
    except Exception as e:
        return RunResponse(
            status="error",
            scenario_yaml=req.scenario_yaml,
            trace_jsonl="",
            metrics_json="",
            error=str(e),
        )
    finally:
        # Clean up temp scenario dir
        import shutil as _shutil
        try:
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def _build_response(
    output_dir: Path,
    scenario_yaml: str,
    status: str,
    error: str | None = None,
) -> RunResponse:
    """Read output files and build response."""
    trace_path = output_dir / "trace.jsonl"
    metrics_path = output_dir / "metrics.json"

    trace_jsonl = ""
    metrics_json = ""

    if trace_path.exists():
        trace_jsonl = trace_path.read_text(encoding="utf-8")
    if metrics_path.exists():
        metrics_json = metrics_path.read_text(encoding="utf-8")

    return RunResponse(
        status=status,
        scenario_yaml=scenario_yaml,
        trace_jsonl=trace_jsonl,
        metrics_json=metrics_json,
        error=error,
    )
