"""BigQuery CLI smoke test for Manual Receiving ATC.

Purpose:
- Prove bq CLI can execute a query from *this* machine/user
- Print stdout/stderr + which account is active

Run:
  atc_env\Scripts\python.exe bq_smoke_test.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _resolve_bq_argv(bq_path: str) -> list[str]:
    """Return argv to invoke bq reliably.

    If bq_path is a Cloud SDK .cmd launcher, call the underlying
    `bin/bootstrapping/bq.py` directly.
    """

    p = Path(bq_path)
    if p.suffix.lower() in {".cmd", ".bat"}:
        cloudsdk_root = p.parent.parent
        bq_py = cloudsdk_root / "bin" / "bootstrapping" / "bq.py"
        bundled_python = cloudsdk_root / "platform" / "bundledpython" / "python.exe"
        python_exe = str(bundled_python) if bundled_python.exists() else sys.executable

        if not bq_py.exists():
            raise FileNotFoundError(f"Cloud SDK bq.py not found: {bq_py}")

        return [python_exe, str(bq_py)]

    return [bq_path]


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "atc_config.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def main() -> None:
    cfg = load_config()
    bq_path = cfg.get("bigquery", {}).get("bq_path")
    billing_project = cfg.get("bigquery", {}).get("billing_project")
    job_project = cfg.get("bigquery", {}).get("job_project")
    project_id = job_project or billing_project

    print(f"bq_path: {bq_path}")
    print(f"billing_project: {billing_project}")
    print(f"job_project: {job_project}")
    print(f"project_id used for jobs: {project_id}")

    # 1) show gcloud account(s)
    print("\n=== gcloud auth list (best-effort) ===")
    try:
        p = subprocess.run(["gcloud", "auth", "list"], capture_output=True, text=True)
        print(p.stdout.strip() or p.stderr.strip())
    except FileNotFoundError:
        print("gcloud not found on PATH (ok). Skipping.")

    # 2) run a trivial query
    sql = "SELECT 1 AS ok"
    base_args = [
        "query",
        "--quiet",
        "--use_legacy_sql=false",
        "--format=csv",
    ]
    if project_id:
        base_args.append(f"--project_id={project_id}")

    print("\n=== running bq query (SELECT 1) ===")

    full_cmd = _resolve_bq_argv(str(bq_path)) + base_args

    print("CMD:")
    print(" ".join(full_cmd))

    proc = subprocess.run(full_cmd, input=sql, capture_output=True, text=True, timeout=60)

    print("\nSTDOUT:")
    print(proc.stdout)

    print("\nSTDERR:")
    print(proc.stderr)

    print(f"\nexit_code: {proc.returncode}")


if __name__ == "__main__":
    main()
