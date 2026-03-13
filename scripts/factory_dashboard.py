#!/usr/bin/env python3
"""
AI Influencer Factory — Web Dashboard

Wraps all pipeline scripts into a single web UI.
Run: python scripts/factory_dashboard.py
Open: http://localhost:7860
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

if not os.environ.get('OPENROUTER_API_KEY'):
 try:
  from kaggle_secrets import UserSecretsClient
  os.environ['OPENROUTER_API_KEY'] = UserSecretsClient().get_secret('OPENROUTER_API_KEY')
 except Exception:
  pass

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'
SCRIPTS = WORKSPACE / 'scripts'

app = FastAPI(title='AI Influencer Factory')
task_status: Dict[str, Dict[str, Any]] = {}


def now_iso() -> str:
 return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def run_script(cmd: List[str], cwd: str = None) -> Dict[str, Any]:
 if cwd is None:
  cwd = str(WORKSPACE)
 try:
  result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
  return {
   'success': result.returncode == 0,
   'stdout': result.stdout,
   'stderr': result.stderr,
   'returncode': result.returncode,
  }
 except subprocess.TimeoutExpired:
  return {'success': False, 'stdout': '', 'stderr': 'Timeout after 600s', 'returncode': -1}
 except Exception as e:
  return {'success': False, 'stdout': '', 'stderr': str(e), 'returncode': -1}


def load_json_safe(path: Path) -> Dict[str, Any]:
 try:
  return json.loads(path.read_text())
 except Exception:
  return {}


def get_all_jobs() -> List[Dict[str, Any]]:
 jobs = []
 if not JOBS_DIR.exists():
  return jobs
 for job_dir in sorted(JOBS_DIR.iterdir()):
  if not job_dir.is_dir():
   continue
  job_json = job_dir / 'metadata' / 'job.json'
  if job_json.exists():
   job = load_json_safe(job_json)
   if job:
    job['_has_prompts'] = (job_dir / 'intake' / 'generated-prompts.json').exists()
    job['_preview_count'] = len(list((job_dir / 'previews').glob('*.*'))) if (job_dir / 'previews').exists() else 0
    job['_final_count'] = len(list((job_dir / 'final_batches').glob('*.*'))) if (job_dir / 'final_batches').exists() else 0
    jobs.append(job)
 return jobs


def get_job(job_id: str) -> Dict[str, Any]:
 job_json = JOBS_DIR / job_id / 'metadata' / 'job.json'
 if not job_json.exists():
  return {}
 job = load_json_safe(job_json)
 job['_has_prompts'] = (JOBS_DIR / job_id / 'intake' / 'generated-prompts.json').exists()
 job['_preview_count'] = len(list((JOBS_DIR / job_id / 'previews').glob('*.*'))) if (JOBS_DIR / job_id / 'previews').exists() else 0
 job['_final_count'] = len(list((JOBS_DIR / job_id / 'final_batches').glob('*.*'))) if (JOBS_DIR / job_id / 'final_batches').exists() else 0
 prompts_file = JOBS_DIR / job_id / 'intake' / 'generated-prompts.json'
 if prompts_file.exists():
  prompt_data = load_json_safe(prompts_file)
  job['_prompts'] = prompt_data.get('prompts', [])
 else:
  job['_prompts'] = []
 return job


def background_task_runner(task_id: str, steps: List[Dict[str, Any]]):
 task_status[task_id]['status'] = 'running'
 task_status[task_id]['started_at'] = now_iso()
 for i, step in enumerate(steps):
  task_status[task_id]['current_step'] = step['name']
  task_status[task_id]['progress'] = f'{i + 1}/{len(steps)}'
  result = run_script(step['cmd'])
  task_status[task_id]['steps_completed'].append({
   'name': step['name'],
   'success': result['success'],
   'stdout': result['stdout'][-500:] if result['stdout'] else '',
   'stderr': result['stderr'][-500:] if result['stderr'] else '',
  })
  if not result['success'] and step.get('required', True):
   task_status[task_id]['status'] = 'failed'
   task_status[task_id]['error'] = f"Step '{step['name']}' failed: {result['stderr'][:200]}"
   task_status[task_id]['finished_at'] = now_iso()
   return
 task_status[task_id]['status'] = 'completed'
 task_status[task_id]['finished_at'] = now_iso()


def start_background_task(task_name: str, steps: List[Dict[str, Any]]) -> str:
 task_id = str(uuid.uuid4())[:8]
 task_status[task_id] = {
  'task_id': task_id,
  'task_name': task_name,
  'status': 'queued',
  'current_step': '',
  'progress': '',
  'steps_completed': [],
  'error': '',
  'started_at': '',
  'finished_at': '',
 }
 thread = threading.Thread(target=background_task_runner, args=(task_id, steps), daemon=True)
 thread.start()
 return task_id


@app.get('/', response_class=HTMLResponse)
async def dashboard():
 html_path = WORKSPACE / 'templates' / 'dashboard.html'
 if html_path.exists():
  return HTMLResponse(html_path.read_text())
 return HTMLResponse('<h1>Dashboard HTML not found</h1>')


@app.get('/api/jobs')
async def api_list_jobs():
 return get_all_jobs()


@app.get('/api/jobs/{job_id}')
async def api_get_job(job_id: str):
 job = get_job(job_id)
 if not job:
  return JSONResponse({'error': 'Job not found'}, status_code=404)
 return job


@app.get('/api/tasks/{task_id}')
async def api_task_status(task_id: str):
 if task_id not in task_status:
  return JSONResponse({'error': 'Task not found'}, status_code=404)
 return task_status[task_id]


@app.post('/api/new-order')
async def api_new_order(request: Request):
 body = await request.json()
 client = body.get('client', '').strip()
 persona = body.get('persona', '').strip()
 niche = body.get('niche', '').strip()
 style = body.get('style', '').strip()
 count = int(body.get('prompt_count', 20))
 notes = body.get('notes', '')
 trigger_word = body.get('trigger_word', 'p3r5on')
 if not client or not niche:
  return JSONResponse({'error': 'Client and niche are required'}, status_code=400)
 ts = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
 job_id = f'{client.upper().replace(" ", "-")}-{ts}'
 if not persona:
  persona = f'{client}-persona'
 steps = [
  {'name': 'Create job', 'cmd': [sys.executable, str(SCRIPTS / 'job_manager.py'), 'create', '--job-id', job_id, '--client', client, '--persona', persona]},
  {'name': 'Bootstrap Drive folders', 'cmd': [sys.executable, str(SCRIPTS / 'factory_drive_sync.py'), 'bootstrap', '--job-id', job_id]},
  {'name': 'Generate prompts', 'cmd': [sys.executable, str(SCRIPTS / 'prompt_generator.py'), '--job-id', job_id, '--niche', niche, '--style', style or 'natural, modern', '--count', str(count), '--trigger-word', trigger_word, '--notes', notes]},
 ]
 task_id = start_background_task(f'New Order: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}


@app.post('/api/generate-previews/{job_id}')
async def api_generate_previews(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 count = int(body.get('count', 5))
 steps = [
  {'name': f'Generate {count} preview images', 'cmd': [sys.executable, str(SCRIPTS / 'generate_previews.py'), 'batch', '--job-id', job_id, '--count', str(count)]},
  {'name': 'Upload previews to Drive', 'cmd': [sys.executable, str(SCRIPTS / 'preview_upload.py'), '--job-id', job_id]},
 ]
 task_id = start_background_task(f'Previews: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}


@app.post('/api/approve/{job_id}')
async def api_approve(job_id: str):
 result = run_script([sys.executable, str(SCRIPTS / 'approval_handler.py'), 'approve', '--job-id', job_id])
 return {'success': result['success'], 'output': result['stdout'][:500]}


@app.post('/api/reject/{job_id}')
async def api_reject(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 notes = body.get('notes', 'Rejected')
 result = run_script([sys.executable, str(SCRIPTS / 'approval_handler.py'), 'reject', '--job-id', job_id, '--notes', notes])
 return {'success': result['success'], 'output': result['stdout'][:500]}


@app.post('/api/generate-finals/{job_id}')
async def api_generate_finals(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 count = int(body.get('count', 20))
 steps = [
  {'name': 'Start training', 'cmd': [sys.executable, str(SCRIPTS / 'training_handler.py'), 'start', '--job-id', job_id, '--model-type', 'sdxl-lora', '--platform', 'modal'], 'required': True},
  {'name': 'Complete training', 'cmd': [sys.executable, str(SCRIPTS / 'training_handler.py'), 'complete', '--job-id', job_id, '--checkpoint-path', f'modal-volume/loras/{job_id}.safetensors'], 'required': True},
  {'name': f'Generate {count} final images', 'cmd': [sys.executable, str(SCRIPTS / 'generate_finals.py'), '--job-id', job_id, '--count', str(count)]},
  {'name': 'Upload finals to Drive', 'cmd': [sys.executable, str(SCRIPTS / 'final_batch_handler.py'), 'upload', '--job-id', job_id]},
 ]
 task_id = start_background_task(f'Finals: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}


@app.post('/api/deliver/{job_id}')
async def api_deliver(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 notes = body.get('notes', 'Delivered via dashboard')
 qa_result = run_script([sys.executable, str(SCRIPTS / 'final_batch_handler.py'), 'qa-approve', '--job-id', job_id, '--notes', 'QA approved via dashboard'])
 if not qa_result['success']:
  return JSONResponse({'error': f"QA approve failed: {qa_result['stderr'][:200]}"}, status_code=500)
 deliver_result = run_script([sys.executable, str(SCRIPTS / 'delivery_handler.py'), 'deliver', '--job-id', job_id, '--notes', notes])
 return {'success': deliver_result['success'], 'output': deliver_result['stdout'][:500]}


@app.post('/api/update-prompts/{job_id}')
async def api_update_prompts(job_id: str, request: Request):
 body = await request.json()
 prompts = body.get('prompts', [])
 if not prompts:
  return JSONResponse({'error': 'No prompts provided'}, status_code=400)
 prompts_dir = JOBS_DIR / job_id / 'intake'
 prompts_dir.mkdir(parents=True, exist_ok=True)
 prompts_json = prompts_dir / 'generated-prompts.json'
 if prompts_json.exists():
  data = json.loads(prompts_json.read_text())
 else:
  data = {'job_id': job_id, 'generated_at': now_iso(), 'model': 'manual-edit'}
 data['prompts'] = prompts
 data['count_generated'] = len(prompts)
 data['edited_at'] = now_iso()
 prompts_json.write_text(json.dumps(data, indent=2))
 txt_file = prompts_dir / 'prompts.txt'
 txt_file.write_text('\n'.join(prompts))
 return {'success': True, 'count': len(prompts)}


@app.post('/api/regenerate-prompts/{job_id}')
async def api_regenerate_prompts(job_id: str, request: Request):
 body = await request.json()
 niche = body.get('niche', 'lifestyle')
 style = body.get('style', 'natural, modern')
 count = int(body.get('count', 20))
 trigger_word = body.get('trigger_word', 'p3r5on')
 notes = body.get('notes', '')
 steps = [{
  'name': 'Regenerate prompts',
  'cmd': [sys.executable, str(SCRIPTS / 'prompt_generator.py'), '--job-id', job_id, '--niche', niche, '--style', style, '--count', str(count), '--trigger-word', trigger_word, '--notes', notes],
 }]
 task_id = start_background_task(f'Regenerate prompts: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}


@app.post('/api/backup')
async def api_backup():
 result = run_script(['bash', str(SCRIPTS / 'factory_backup.sh')])
 return {'success': result['success'], 'output': result['stdout'][:500]}


if __name__ == '__main__':
 print('=' * 50)
 print(' AI INFLUENCER FACTORY — DASHBOARD')
 print('=' * 50)
 print(f' Open: http://localhost:7860')
 print('=' * 50)
 uvicorn.run(app, host='0.0.0.0', port=7860)
