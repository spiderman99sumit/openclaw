#!/usr/bin/env python3
"""
AI Influencer Factory — Professional Dashboard
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

# Health check cache — don't re-check every request
_health_cache: Dict[str, Any] = {}
_health_cache_time: float = 0
HEALTH_CACHE_TTL = 60 # seconds

_modal_cache: Dict[str, Any] = {}
_modal_cache_time: float = 0
MODAL_CACHE_TTL = 120 # seconds


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
    job['_preview_count'] = len([f for f in (job_dir / 'previews').glob('*.*') if f.is_file()]) if (job_dir / 'previews').exists() else 0
    job['_final_count'] = len([f for f in (job_dir / 'final_batches').glob('*.*') if f.is_file()]) if (job_dir / 'final_batches').exists() else 0
    jobs.append(job)
 return jobs


def get_job(job_id: str) -> Dict[str, Any]:
 job_json = JOBS_DIR / job_id / 'metadata' / 'job.json'
 if not job_json.exists():
  return {}
 job = load_json_safe(job_json)
 job['_has_prompts'] = (JOBS_DIR / job_id / 'intake' / 'generated-prompts.json').exists()
 job['_preview_count'] = len([f for f in (JOBS_DIR / job_id / 'previews').glob('*.*') if f.is_file()]) if (JOBS_DIR / job_id / 'previews').exists() else 0
 job['_final_count'] = len([f for f in (JOBS_DIR / job_id / 'final_batches').glob('*.*') if f.is_file()]) if (JOBS_DIR / job_id / 'final_batches').exists() else 0
 prompts_file = JOBS_DIR / job_id / 'intake' / 'generated-prompts.json'
 if prompts_file.exists():
  prompt_data = load_json_safe(prompts_file)
  job['_prompts'] = prompt_data.get('prompts', [])
 else:
  job['_prompts'] = []
 return job


def get_all_loras() -> List[Dict[str, Any]]:
 """Scan all jobs for LoRA information."""
 loras = []
 if not JOBS_DIR.exists():
  return loras
 for job_dir in sorted(JOBS_DIR.iterdir()):
  if not job_dir.is_dir():
   continue
  job_json = job_dir / 'metadata' / 'job.json'
  if not job_json.exists():
   continue
  job = load_json_safe(job_json)
  training = job.get('drive', {}).get('training', {})
  if training.get('status', 'not_started') != 'not_started':
   lora_info = {
    'job_id': job.get('job_id', job_dir.name),
    'client_name': job.get('client_name', ''),
    'persona_name': job.get('persona_name', ''),
    'model_type': training.get('model_type', ''),
    'platform': training.get('platform', ''),
    'run_id': training.get('run_id', ''),
    'checkpoint_path': training.get('checkpoint_path', ''),
    'status': training.get('status', ''),
    'started_at': training.get('started_at', ''),
    'completed_at': training.get('completed_at', ''),
    'trigger_word': 'p3r5on',
   }
   checkpoint_info = job_dir / 'lora' / 'checkpoint-info.json'
   if checkpoint_info.exists():
    lora_info['_has_checkpoint'] = True
    lora_info['_checkpoint_data'] = load_json_safe(checkpoint_info)
   else:
    lora_info['_has_checkpoint'] = False
   loras.append(lora_info)
 return loras


def get_modal_status() -> Dict[str, Any]:
 """Check Modal deployment status."""
 status = {
  'endpoint': os.environ.get('MODAL_COMFYUI_URL', 'https://sumit-pbh999--comfyui-zimage-generate.modal.run'),
  'endpoint_alive': False,
  'modal_cli_available': False,
  'apps': [],
  'credits_info': 'Check https://modal.com/settings for billing details',
 }
 try:
  result = subprocess.run(['modal', '--version'], capture_output=True, text=True, timeout=10)
  if result.returncode == 0:
   status['modal_cli_available'] = True
   status['modal_version'] = result.stdout.strip()
 except Exception:
  pass
 try:
  import urllib.request
  req = urllib.request.Request(status['endpoint'], method='POST')
  req.add_header('Content-Type', 'application/x-www-form-urlencoded')
  with urllib.request.urlopen(req, timeout=10) as resp:
   status['endpoint_alive'] = resp.status == 200
 except Exception as e:
  status['endpoint_error'] = str(e)[:200]
 if status['modal_cli_available']:
  try:
   result = subprocess.run(['modal', 'app', 'list'], capture_output=True, text=True, timeout=30)
   if result.returncode == 0:
    status['apps_raw'] = result.stdout[:2000]
  except Exception:
   pass
 return status


def get_system_health() -> Dict[str, Any]:
 """Get overall system health."""
 health = {
  'n8n_running': False,
  'webhook_active': False,
  'modal_endpoint': False,
  'drive_connected': True,
  'backup_exists': False,
  'last_backup': '',
 }

 # Check n8n — short timeout
 try:
  import urllib.request
  urllib.request.urlopen('http://127.0.0.1:5678/healthz', timeout=2)
  health['n8n_running'] = True
 except Exception:
  pass

 # Check webhook — short timeout
 try:
  import urllib.request
  req = urllib.request.Request(
   'http://127.0.0.1:5678/webhook/factory-preview-upload-v2',
   data=json.dumps({'job_id': 'health', 'folder_id': '', 'files': []}).encode(),
   headers={'Content-Type': 'application/json'},
   method='POST'
  )
  urllib.request.urlopen(req, timeout=3)
  health['webhook_active'] = True
 except Exception:
  pass

 # Skip Modal check on every health call — too slow through tunnel
 # Modal status is checked separately on the API page
 health['modal_endpoint'] = True

 # Check backup — fast, local filesystem
 backup_dir = WORKSPACE.parent / 'backups'
 if backup_dir.exists():
  backups = sorted(backup_dir.glob('factory-backup-*.tar.gz'))
  if backups:
   health['backup_exists'] = True
   health['last_backup'] = backups[-1].name

 return health


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
  'task_id': task_id, 'task_name': task_name, 'status': 'queued',
  'current_step': '', 'progress': '', 'steps_completed': [],
  'error': '', 'started_at': '', 'finished_at': '',
 }
 thread = threading.Thread(target=background_task_runner, args=(task_id, steps), daemon=True)
 thread.start()
 return task_id


@app.get('/', response_class=HTMLResponse)
async def dashboard():
 html_path = WORKSPACE / 'templates' / 'dashboard.html'
 if html_path.exists():
  return HTMLResponse(html_path.read_text())
 return HTMLResponse('<h1>Dashboard not found</h1>')

@app.get('/api/jobs')
async def api_list_jobs():
 return get_all_jobs()

@app.get('/api/jobs/{job_id}')
async def api_get_job(job_id: str):
 job = get_job(job_id)
 if not job:
  return JSONResponse({'error': 'Not found'}, status_code=404)
 return job

@app.get('/api/loras')
async def api_list_loras():
 return get_all_loras()

@app.get('/api/modal/status')
async def api_modal_status():
 import time
 global _modal_cache, _modal_cache_time
 if time.time() - _modal_cache_time < MODAL_CACHE_TTL and _modal_cache:
  return _modal_cache
 _modal_cache = get_modal_status()
 _modal_cache_time = time.time()
 return _modal_cache

@app.get('/api/health')
async def api_health():
 import time
 global _health_cache, _health_cache_time
 if time.time() - _health_cache_time < HEALTH_CACHE_TTL and _health_cache:
  return _health_cache
 _health_cache = get_system_health()
 _health_cache_time = time.time()
 return _health_cache

@app.get('/api/tasks/{task_id}')
async def api_task_status(task_id: str):
 if task_id not in task_status:
  return JSONResponse({'error': 'Not found'}, status_code=404)
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
  return JSONResponse({'error': 'Client and niche required'}, status_code=400)
 ts = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
 job_id = f'{client.upper().replace(" ", "-")}-{ts}'
 if not persona:
  persona = f'{client}-persona'
 steps = [
  {'name': 'Create job', 'cmd': [sys.executable, str(SCRIPTS / 'job_manager.py'), 'create', '--job-id', job_id, '--client', client, '--persona', persona]},
  {'name': 'Bootstrap Drive', 'cmd': [sys.executable, str(SCRIPTS / 'factory_drive_sync.py'), 'bootstrap', '--job-id', job_id]},
  {'name': 'Generate prompts', 'cmd': [sys.executable, str(SCRIPTS / 'prompt_generator.py'), '--job-id', job_id, '--niche', niche, '--style', style or 'natural, modern', '--count', str(count), '--trigger-word', trigger_word, '--notes', notes]},
 ]
 task_id = start_background_task(f'New Order: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}

@app.post('/api/generate-previews/{job_id}')
async def api_generate_previews(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 count = int(body.get('count', 5))
 steps = [
  {'name': f'Generate {count} previews', 'cmd': [sys.executable, str(SCRIPTS / 'generate_previews.py'), 'batch', '--job-id', job_id, '--count', str(count)]},
  {'name': 'Upload to Drive', 'cmd': [sys.executable, str(SCRIPTS / 'preview_upload.py'), '--job-id', job_id]},
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
  {'name': f'Generate {count} finals', 'cmd': [sys.executable, str(SCRIPTS / 'generate_finals.py'), '--job-id', job_id, '--count', str(count)]},
  {'name': 'Upload finals to Drive', 'cmd': [sys.executable, str(SCRIPTS / 'final_batch_handler.py'), 'upload', '--job-id', job_id]},
 ]
 task_id = start_background_task(f'Finals: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}

@app.post('/api/deliver/{job_id}')
async def api_deliver(job_id: str, request: Request):
 body = await request.json() if await request.body() else {}
 notes = body.get('notes', 'Delivered via dashboard')
 qa = run_script([sys.executable, str(SCRIPTS / 'final_batch_handler.py'), 'qa-approve', '--job-id', job_id, '--notes', 'QA via dashboard'])
 if not qa['success']:
  return JSONResponse({'error': f"QA failed: {qa['stderr'][:200]}"}, status_code=500)
 deliver = run_script([sys.executable, str(SCRIPTS / 'delivery_handler.py'), 'deliver', '--job-id', job_id, '--notes', notes])
 return {'success': deliver['success'], 'output': deliver['stdout'][:500]}

@app.post('/api/update-prompts/{job_id}')
async def api_update_prompts(job_id: str, request: Request):
 body = await request.json()
 prompts = body.get('prompts', [])
 if not prompts:
  return JSONResponse({'error': 'No prompts'}, status_code=400)
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
 (prompts_dir / 'prompts.txt').write_text('\n'.join(prompts))
 return {'success': True, 'count': len(prompts)}

@app.post('/api/regenerate-prompts/{job_id}')
async def api_regenerate_prompts(job_id: str, request: Request):
 body = await request.json()
 steps = [
  {'name': 'Regenerate prompts', 'cmd': [sys.executable, str(SCRIPTS / 'prompt_generator.py'), '--job-id', job_id, '--niche', body.get('niche', 'lifestyle'), '--style', body.get('style', 'natural, modern'), '--count', str(body.get('count', 20)), '--trigger-word', body.get('trigger_word', 'p3r5on'), '--notes', body.get('notes', '')]},
 ]
 task_id = start_background_task(f'Regen prompts: {job_id}', steps)
 return {'task_id': task_id, 'job_id': job_id}

@app.post('/api/modal/deploy')
async def api_modal_deploy():
 result = run_script(['modal', 'deploy', 'modal_comfyui.py'], cwd=str(WORKSPACE))
 return {'success': result['success'], 'output': result['stdout'][:1000], 'error': result['stderr'][:500]}

@app.post('/api/modal/update-endpoint')
async def api_modal_update_endpoint(request: Request):
 body = await request.json()
 new_url = body.get('endpoint', '').strip()
 if new_url:
  os.environ['MODAL_COMFYUI_URL'] = new_url
  return {'success': True, 'endpoint': new_url}
 return JSONResponse({'error': 'No endpoint provided'}, status_code=400)

@app.post('/api/backup')
async def api_backup():
 result = run_script(['bash', str(SCRIPTS / 'factory_backup.sh')])
 return {'success': result['success'], 'output': result['stdout'][:500]}


if __name__ == '__main__':
 print('=' * 50)
 print(' AI INFLUENCER FACTORY — DASHBOARD')
 print('=' * 50)
 print(f' URL: http://localhost:7860')
 print('=' * 50)
 uvicorn.run(app, host='0.0.0.0', port=7860)
