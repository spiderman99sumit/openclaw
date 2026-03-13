#!/usr/bin/env python3
"""Handle preview approval decisions."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

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


def approve(job_id: str, approved_files: List[str], notes: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') != 'preview_review':
        raise ValueError(
            f'Job {job_id} is in status "{job.get("status")}", expected "preview_review"'
        )

    preview = job.get('preview', {})
    available = preview.get('assets', [])

    if not approved_files:
        approved_files = available

    invalid = [f for f in approved_files if f not in available]
    if invalid:
        raise ValueError(f'Files not in preview assets: {invalid}')

    approval_record = {
        'decision': 'approved',
        'approved_files': approved_files,
        'rejected_files': [f for f in available if f not in approved_files],
        'notes': notes,
        'decided_at': now_iso(),
        'decided_by': 'manual'
    }

    approval_dir = JOBS_DIR / job_id / 'approvals'
    approval_dir.mkdir(parents=True, exist_ok=True)
    approval_path = approval_dir / 'approval-record.json'
    save_json(approval_path, approval_record)

    preview['review_status'] = 'approved'
    preview['approved_files'] = approved_files
    job['preview'] = preview
    job['status'] = 'approved_for_training'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'approval': approval_record}


def reject(job_id: str, notes: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    preview = job.get('preview', {})

    approval_record = {
        'decision': 'rejected',
        'approved_files': [],
        'rejected_files': preview.get('assets', []),
        'notes': notes,
        'decided_at': now_iso(),
        'decided_by': 'manual'
    }

    approval_dir = JOBS_DIR / job_id / 'approvals'
    approval_dir.mkdir(parents=True, exist_ok=True)
    save_json(approval_dir / 'approval-record.json', approval_record)

    preview['review_status'] = 'rejected'
    job['preview'] = preview
    job['status'] = 'preview_running'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'approval': approval_record}


def main() -> int:
    parser = argparse.ArgumentParser(description='Handle preview approvals')
    sub = parser.add_subparsers(dest='cmd', required=True)

    a = sub.add_parser('approve')
    a.add_argument('--job-id', required=True)
    a.add_argument('--files', nargs='*', default=[], help='Specific files to approve. If empty, approves all.')
    a.add_argument('--notes', default='')

    r = sub.add_parser('reject')
    r.add_argument('--job-id', required=True)
    r.add_argument('--notes', default='')

    s = sub.add_parser('status')
    s.add_argument('--job-id', required=True)

    args = parser.parse_args()

    if args.cmd == 'approve':
        result = approve(args.job_id, args.files, args.notes)
    elif args.cmd == 'reject':
        result = reject(args.job_id, args.notes)
    else:
        path = job_json_path(args.job_id)
        job = load_json(path)
        approval_path = JOBS_DIR / args.job_id / 'approvals' / 'approval-record.json'
        result = {
            'job_id': args.job_id,
            'job_status': job.get('status'),
            'review_status': job.get('preview', {}).get('review_status'),
            'approval_record': load_json(approval_path) if approval_path.exists() else None
        }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
