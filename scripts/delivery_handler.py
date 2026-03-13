#!/usr/bin/env python3
"""Handle final delivery packaging."""
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


def deliver(job_id: str, package_link: str = '', notes: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') != 'delivery_ready':
        raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "delivery_ready"')

    delivery_folder_id = job.get('drive', {}).get('subfolders', {}).get('delivery', '')
    if not package_link and delivery_folder_id:
        package_link = f'https://drive.google.com/drive/folders/{delivery_folder_id}'

    delivery = job.get('delivery', {})
    delivery['package_link'] = package_link
    delivery['delivered'] = True
    delivery['delivered_at'] = now_iso()
    delivery['notes'] = notes
    job['delivery'] = delivery
    job['status'] = 'delivered'
    job['updated_at'] = now_iso()
    save_json(path, job)

    delivery_record = {
        'job_id': job_id,
        'client_name': job.get('client_name', ''),
        'persona_name': job.get('persona_name', ''),
        'package_link': package_link,
        'delivered_at': delivery['delivered_at'],
        'final_assets': job.get('final_batch', {}).get('assets', []),
        'final_drive_links': job.get('final_batch', {}).get('drive_links', []),
        'notes': notes
    }

    delivery_dir = JOBS_DIR / job_id / 'delivery'
    delivery_dir.mkdir(parents=True, exist_ok=True)
    save_json(delivery_dir / 'delivery-record.json', delivery_record)

    return delivery_record


def main() -> int:
    parser = argparse.ArgumentParser(description='Delivery handler')
    sub = parser.add_subparsers(dest='cmd', required=True)

    d = sub.add_parser('deliver')
    d.add_argument('--job-id', required=True)
    d.add_argument('--package-link', default='')
    d.add_argument('--notes', default='')

    s = sub.add_parser('status')
    s.add_argument('--job-id', required=True)

    args = parser.parse_args()

    if args.cmd == 'deliver':
        result = deliver(args.job_id, args.package_link, args.notes)
    else:
        job = load_json(job_json_path(args.job_id))
        result = {'job_id': args.job_id, 'job_status': job.get('status'), 'delivery': job.get('delivery', {})}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
