#!/usr/bin/env python3
"""Handle training lifecycle."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_json_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / 'metadata' / 'job.json'


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def start_training(job_id: str, model_type: str, platform: str, run_id: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') != 'approved_for_training':
        raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "approved_for_training"')

    training = job.get('training', {})
    training['model_type'] = model_type
    training['platform'] = platform
    training['run_id'] = run_id or f'{job_id}-run-001'
    training['status'] = 'training_running'
    training['started_at'] = now_iso()
    training['checkpoint_path'] = ''

    job['training'] = training
    job['status'] = 'training_running'
    job['updated_at'] = now_iso()
    save_json(path, job)

    log_entry = {
        'event': 'training_started',
        'timestamp': now_iso(),
        'model_type': model_type,
        'platform': platform,
        'run_id': training['run_id']
    }
    log_dir = JOBS_DIR / job_id / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    save_json(log_dir / 'training-start.json', log_entry)

    return {'job_id': job_id, 'status': job['status'], 'training': training}


def complete_training(job_id: str, checkpoint_path: str) -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') != 'training_running':
        raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "training_running"')

    training = job.get('training', {})
    training['status'] = 'training_done'
    training['checkpoint_path'] = checkpoint_path
    training['completed_at'] = now_iso()

    job['training'] = training
    job['status'] = 'training_done'
    job['updated_at'] = now_iso()
    save_json(path, job)

    lora_dir = JOBS_DIR / job_id / 'lora'
    lora_dir.mkdir(parents=True, exist_ok=True)
    save_json(lora_dir / 'checkpoint-info.json', {
        'checkpoint_path': checkpoint_path,
        'completed_at': now_iso(),
        'run_id': training.get('run_id', '')
    })

    return {'job_id': job_id, 'status': job['status'], 'training': training}


def fail_training(job_id: str, reason: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    training = job.get('training', {})
    training['status'] = 'training_failed'
    training['failed_at'] = now_iso()
    training['failure_reason'] = reason

    job['training'] = training
    job['status'] = 'training_failed'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'training': training}


def main() -> int:
    parser = argparse.ArgumentParser(description='Training lifecycle handler')
    sub = parser.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('start')
    s.add_argument('--job-id', required=True)
    s.add_argument('--model-type', required=True)
    s.add_argument('--platform', required=True)
    s.add_argument('--run-id', default='')

    c = sub.add_parser('complete')
    c.add_argument('--job-id', required=True)
    c.add_argument('--checkpoint-path', required=True)

    f = sub.add_parser('fail')
    f.add_argument('--job-id', required=True)
    f.add_argument('--reason', default='')

    st = sub.add_parser('status')
    st.add_argument('--job-id', required=True)

    args = parser.parse_args()

    if args.cmd == 'start':
        result = start_training(args.job_id, args.model_type, args.platform, args.run_id)
    elif args.cmd == 'complete':
        result = complete_training(args.job_id, args.checkpoint_path)
    elif args.cmd == 'fail':
        result = fail_training(args.job_id, args.reason)
    else:
        job = load_json(job_json_path(args.job_id))
        result = {'job_id': args.job_id, 'job_status': job.get('status'), 'training': job.get('training', {})}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
