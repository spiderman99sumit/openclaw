#!/usr/bin/env python3
"""One-time migration for old flat-format jobs."""
import json
from pathlib import Path

JOBS_DIR = Path('/kaggle/working/.openclaw/workspace/jobs')


def migrate_job(job_id: str):
    path = JOBS_DIR / job_id / 'metadata' / 'job.json'
    if not path.exists():
        print(f'No job.json for {job_id}')
        return

    job = json.loads(path.read_text())

    if 'drive' in job and 'subfolders' in job.get('drive', {}):
        print(f'{job_id} already in new format')
        return

    drive_job_folder = job.get('drive_job_folder', '')
    preview_folder = job.get('preview_folder', '')
    final_folder = job.get('final_folder', '')
    delivery_folder = job.get('delivery_folder', '')

    def extract_id(link):
        if '/folders/' in str(link):
            return link.rstrip('/').split('/folders/')[-1].split('?')[0]
        return ''

    job['drive'] = {
        'root_folder_id': extract_id(drive_job_folder),
        'root_folder_link': drive_job_folder,
        'subfolders': {
            'intake': '',
            'references': '',
            'dataset': '',
            'previews': extract_id(preview_folder),
            'approvals': '',
            'lora': '',
            'final_batches': extract_id(final_folder),
            'delivery': extract_id(delivery_folder),
            'logs': '',
            'metadata': ''
        }
    }

    job['preview'] = job.get('preview', {
        'assets': [],
        'drive_links': [],
        'uploaded': False,
        'uploaded_at': '',
        'review_status': 'pending'
    })
    job['training'] = job.get('training', {
        'model_type': '',
        'platform': '',
        'run_id': '',
        'checkpoint_path': '',
        'status': 'not_started'
    })
    job['final_batch'] = job.get('final_batch', {
        'assets': [],
        'drive_links': [],
        'qa_status': 'pending'
    })
    job['delivery'] = job.get('delivery', {
        'package_link': '',
        'delivered': False,
        'delivered_at': ''
    })

    if not job.get('client_name'):
        job['client_name'] = ''
    if not job.get('persona_name'):
        job['persona_name'] = ''
    if not job.get('created_at'):
        job['created_at'] = job.get('last_updated', '')
    if not job.get('updated_at'):
        job['updated_at'] = job.get('last_updated', '')

    path.write_text(json.dumps(job, indent=2))
    print(f'Migrated {job_id} to new format')


if __name__ == '__main__':
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if job_dir.is_dir():
            migrate_job(job_dir.name)
