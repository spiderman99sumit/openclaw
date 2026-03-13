#!/usr/bin/env python3
"""Sync critical factory state to Google Drive for persistence."""
from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def collect_state() -> dict:
    """Collect all job states into one JSON for Drive backup."""
    state = {
        'exported_at': now_iso(),
        'jobs': {}
    }
    if not JOBS_DIR.exists():
        return state

    for job_json in sorted(JOBS_DIR.glob('*/metadata/job.json')):
        try:
            job = json.loads(job_json.read_text())
            job_id = job.get('job_id', job_json.parent.parent.name)
            state['jobs'][job_id] = job
        except Exception:
            continue

    return state


def save_state_locally() -> Path:
    """Save combined state to a local file."""
    state = collect_state()
    out = Path('/kaggle/working/.openclaw/backups/factory-state-latest.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2))
    print(f'State saved: {out}')
    print(f'Jobs: {len(state["jobs"])}')
    return out


if __name__ == '__main__':
    save_state_locally()
