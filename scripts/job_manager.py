#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'
JOB_SUBFOLDERS = [
    'intake', 'references', 'dataset', 'previews', 'approvals',
    'lora', 'final_batches', 'delivery', 'logs', 'metadata'
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def job_json_path(job_id: str) -> Path:
    return job_dir(job_id) / 'metadata' / 'job.json'


def default_job(job_id: str, client_name: str = '', persona_name: str = '') -> Dict[str, Any]:
    return {
        'job_id': job_id,
        'client_name': client_name,
        'persona_name': persona_name,
        'status': 'new',
        'created_at': now_iso(),
        'updated_at': now_iso(),
        'drive': {
            'root_folder_id': '',
            'root_folder_link': '',
            'subfolders': {
                'intake': '',
                'references': '',
                'dataset': '',
                'previews': '',
                'approvals': '',
                'lora': '',
                'final_batches': '',
                'delivery': '',
                'logs': '',
                'metadata': ''
            }
        },
        'preview': {
            'assets': [],
            'drive_links': [],
            'uploaded': False,
            'uploaded_at': '',
            'review_status': 'pending'
        },
        'training': {
            'model_type': '',
            'platform': '',
            'run_id': '',
            'checkpoint_path': '',
            'status': 'not_started'
        },
        'final_batch': {
            'assets': [],
            'drive_links': [],
            'qa_status': 'pending'
        },
        'delivery': {
            'package_link': '',
            'delivered': False,
            'delivered_at': ''
        }
    }


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def create_job(job_id: str, client_name: str, persona_name: str) -> Dict[str, Any]:
    base = job_dir(job_id)
    base.mkdir(parents=True, exist_ok=True)
    for sub in JOB_SUBFOLDERS:
        (base / sub).mkdir(parents=True, exist_ok=True)
    job = default_job(job_id, client_name, persona_name)
    save_json(job_json_path(job_id), job)
    return job


def update_status(job_id: str, new_status: str) -> Dict[str, Any]:
    job = get_job(job_id)
    job['status'] = new_status
    job['updated_at'] = now_iso()
    save_json(job_json_path(job_id), job)
    return job


def get_job(job_id: str) -> Dict[str, Any]:
    path = job_json_path(job_id)
    if not path.exists():
        raise FileNotFoundError(path)
    return load_json(path)


def list_jobs() -> List[Dict[str, Any]]:
    rows = []
    if not JOBS_DIR.exists():
        return rows
    for path in sorted(JOBS_DIR.glob('*/metadata/job.json')):
        try:
            job = load_json(path)
            rows.append({
                'job_id': job.get('job_id', path.parent.parent.name),
                'client_name': job.get('client_name', ''),
                'persona_name': job.get('persona_name', ''),
                'status': job.get('status', 'unknown'),
                'updated_at': job.get('updated_at', '')
            })
        except Exception:
            continue
    return rows


def cmd_create(args: argparse.Namespace) -> int:
    job = create_job(args.job_id, args.client, args.persona)
    print(json.dumps(job, indent=2))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    job = update_status(args.job_id, args.status)
    print(json.dumps(job, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(get_job(args.job_id), indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    print(json.dumps(list_jobs(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Job manager for AI Influencer Factory')
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('create')
    c.add_argument('--job-id', required=True)
    c.add_argument('--client', required=True)
    c.add_argument('--persona', required=True)
    c.set_defaults(func=cmd_create)

    u = sub.add_parser('update-status')
    u.add_argument('--job-id', required=True)
    u.add_argument('--status', required=True)
    u.set_defaults(func=cmd_update)

    s = sub.add_parser('status')
    s.add_argument('--job-id', required=True)
    s.set_defaults(func=cmd_status)

    l = sub.add_parser('list')
    l.set_defaults(func=cmd_list)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
