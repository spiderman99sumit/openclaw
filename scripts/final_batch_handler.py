#!/usr/bin/env python3
"""Handle final batch generation, upload, and QA."""
from __future__ import annotations

import argparse
import json
import mimetypes
import base64
import os
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
DEFAULT_WEBHOOK = os.environ.get('N8N_PREVIEW_UPLOAD_WEBHOOK', 'http://127.0.0.1:5678/webhook/factory-preview-upload-v2')


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_json_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / 'metadata' / 'job.json'


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode('utf-8')
        return json.loads(text) if text.strip() else {}


def collect_final_files(job_id: str) -> List[Path]:
    final_dir = JOBS_DIR / job_id / 'final_batches'
    return [p for p in sorted(final_dir.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def upload_final_batch(job_id: str, webhook_url: str) -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') not in ('training_done', 'final_generation_running'):
        raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "training_done" or "final_generation_running"')

    files = collect_final_files(job_id)
    if not files:
        raise FileNotFoundError(f'No final batch files in {JOBS_DIR / job_id / "final_batches"}')

    folder_id = job.get('drive', {}).get('subfolders', {}).get('final_batches', '')
    payload = {
        'job_id': job_id,
        'folder_id': folder_id,
        'files': [
            {
                'filename': p.name,
                'mime_type': mimetypes.guess_type(str(p))[0] or 'application/octet-stream',
                'base64_data': base64.b64encode(p.read_bytes()).decode('ascii')
            }
            for p in files
        ]
    }

    drive_links = []
    try:
        result = post_json(webhook_url, payload)
        drive_links = result.get('drive_links', [])
    except Exception as e:
        print(f'Warning: batch upload failed: {e}')

    final_batch = job.get('final_batch', {})
    final_batch['assets'] = [p.name for p in files]
    final_batch['drive_links'] = drive_links
    final_batch['uploaded_at'] = now_iso()
    final_batch['qa_status'] = 'pending_review'
    job['final_batch'] = final_batch
    job['status'] = 'qa_review'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'uploaded_files': [p.name for p in files], 'drive_links': drive_links}


def qa_approve(job_id: str, notes: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    final_batch = job.get('final_batch', {})
    final_batch['qa_status'] = 'approved'
    final_batch['qa_approved_at'] = now_iso()
    final_batch['qa_notes'] = notes
    job['final_batch'] = final_batch
    job['status'] = 'delivery_ready'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'final_batch': final_batch}


def qa_reject(job_id: str, notes: str = '') -> Dict[str, Any]:
    path = job_json_path(job_id)
    job = load_json(path)

    final_batch = job.get('final_batch', {})
    final_batch['qa_status'] = 'rejected'
    final_batch['qa_rejected_at'] = now_iso()
    final_batch['qa_notes'] = notes
    job['final_batch'] = final_batch
    job['status'] = 'training_done'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return {'job_id': job_id, 'status': job['status'], 'final_batch': final_batch}


def main() -> int:
    parser = argparse.ArgumentParser(description='Final batch and QA handler')
    sub = parser.add_subparsers(dest='cmd', required=True)

    u = sub.add_parser('upload')
    u.add_argument('--job-id', required=True)
    u.add_argument('--webhook-url', default=DEFAULT_WEBHOOK)

    a = sub.add_parser('qa-approve')
    a.add_argument('--job-id', required=True)
    a.add_argument('--notes', default='')

    r = sub.add_parser('qa-reject')
    r.add_argument('--job-id', required=True)
    r.add_argument('--notes', default='')

    s = sub.add_parser('status')
    s.add_argument('--job-id', required=True)

    args = parser.parse_args()

    if args.cmd == 'upload':
        result = upload_final_batch(args.job_id, args.webhook_url)
    elif args.cmd == 'qa-approve':
        result = qa_approve(args.job_id, args.notes)
    elif args.cmd == 'qa-reject':
        result = qa_reject(args.job_id, args.notes)
    else:
        job = load_json(job_json_path(args.job_id))
        result = {'job_id': args.job_id, 'job_status': job.get('status'), 'final_batch': job.get('final_batch', {})}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
