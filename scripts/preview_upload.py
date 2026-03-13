#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'
DEFAULT_WEBHOOK = os.environ.get('N8N_PREVIEW_UPLOAD_WEBHOOK', 'http://127.0.0.1:5678/webhook/factory-preview-upload-v2')
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
N8N_ALLOWED_FILES_DIR = Path('/root/.n8n-files')


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_json_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / 'metadata' / 'job.json'


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def collect_preview_files(job_id: str) -> List[Path]:
    previews_dir = JOBS_DIR / job_id / 'previews'
    files = [p for p in sorted(previews_dir.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return files


def infer_folder_id(job: Dict[str, Any]) -> str:
    folder_id = job.get('drive', {}).get('subfolders', {}).get('previews', '')
    if folder_id:
        return folder_id
    # backward compatibility with earlier metadata shape
    preview_link = job.get('preview_folder', '') or job.get('drive', {}).get('root_folder_link', '')
    if '/folders/' in preview_link:
        return preview_link.rstrip('/').split('/folders/')[-1].split('?')[0]
    return ''


def mime_for(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or 'application/octet-stream'


def to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode('ascii')


def build_batch_payload(job_id: str, job: Dict[str, Any], files: List[Path]) -> Dict[str, Any]:
    return {
        'job_id': job_id,
        'folder_id': infer_folder_id(job),
        'files': [
            {
                'filename': p.name,
                'mime_type': mime_for(p),
                'base64_data': to_base64(p)
            }
            for p in files
        ]
    }


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode('utf-8')
    return json.loads(text) if text.strip() else {}


def stage_for_n8n(job_id: str, path: Path) -> Path:
    staged_dir = N8N_ALLOWED_FILES_DIR / job_id
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_path = staged_dir / path.name
    shutil.copy2(path, staged_path)
    return staged_path


def fallback_single_uploads(job_id: str, job: Dict[str, Any], files: List[Path], webhook_url: str) -> List[str]:
    """Upload files one at a time using the same batch contract."""
    drive_links: List[str] = []
    folder_id = infer_folder_id(job)
    for path in files:
        payload = {
            'job_id': job_id,
            'folder_id': folder_id,
            'files': [
                {
                    'filename': path.name,
                    'mime_type': mime_for(path),
                    'base64_data': to_base64(path)
                }
            ]
        }
        try:
            result = post_json(webhook_url, payload)
            links = result.get('drive_links', [])
            drive_links.extend(links)
        except Exception as e:
            print(f'Warning: failed to upload {path.name}: {e}')
    return drive_links


def update_sheet_row(job_id: str) -> None:
    try:
        subprocess.run(
            [
                'python',
                str(WORKSPACE / 'scripts' / 'factory_drive_sync.py'),
                'update-job-status',
                job_id,
                'preview_review'
            ],
            cwd=str(WORKSPACE),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f'Warning: Sheets sync failed: {e.stderr}')
    except FileNotFoundError:
        print('Warning: factory_drive_sync.py not found, skipping Sheets update')


def main() -> int:
    parser = argparse.ArgumentParser(description='Upload preview files through n8n and update job state')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--webhook-url', default=DEFAULT_WEBHOOK)
    args = parser.parse_args()

    job_id = args.job_id
    path = job_json_path(job_id)
    job = load_json(path)
    files = collect_preview_files(job_id)
    if not files:
        raise SystemExit(f'No preview files found in {JOBS_DIR / job_id / "previews"}')

    batch_payload = build_batch_payload(job_id, job, files)
    batch_payload_path = JOBS_DIR / job_id / 'metadata' / 'preview-upload-payload.json'
    save_json(batch_payload_path, batch_payload)

    drive_links: List[str] = []
    batch_error = None
    try:
        result = post_json(args.webhook_url, batch_payload)
        if isinstance(result, dict):
            if isinstance(result.get('drive_links'), list):
                drive_links = [x for x in result['drive_links'] if isinstance(x, str)]
            elif result.get('drive_link'):
                drive_links = [result['drive_link']]
    except Exception as e:
        batch_error = str(e)

    if not drive_links:
        drive_links = fallback_single_uploads(job_id, job, files, args.webhook_url)

    preview = job.setdefault('preview', {
        'assets': [], 'drive_links': [], 'uploaded': False, 'uploaded_at': '', 'review_status': 'pending'
    })
    preview['assets'] = [p.name for p in files]
    preview['drive_links'] = drive_links
    preview['uploaded'] = bool(drive_links)
    preview['uploaded_at'] = now_iso() if drive_links else ''
    preview['review_status'] = 'ready' if drive_links else 'pending'
    job['status'] = 'preview_review' if drive_links else job.get('status', 'preview_running')
    job['updated_at'] = now_iso()
    job.setdefault('drive', {}).setdefault('subfolders', {})
    save_json(path, job)

    update_sheet_row(job_id)

    print(json.dumps({
        'job_id': job_id,
        'webhook_url': args.webhook_url,
        'batch_payload_path': str(batch_payload_path),
        'batch_error': batch_error,
        'uploaded_files': [p.name for p in files],
        'drive_links': drive_links,
        'status': job['status']
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
