#!/usr/bin/env python3
"""Generate preview images via Modal ComfyUI endpoint."""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.request
import urllib.parse
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'

MODAL_ENDPOINT = os.environ.get(
 'MODAL_COMFYUI_URL',
 'https://sumit-pbh999--comfyui-zimage-generate.modal.run'
)

DEFAULT_NEGATIVE = (
 'low resolution, cartoon, anime, CGI, 3D render, '
 'plastic skin, distorted face, blurry, deformed'
)

PREVIEW_PROMPTS = [
 'RAW photo of p3r5on young woman, professional headshot, studio lighting, '
 'neutral background, ultra-realistic, 8k resolution, highly detailed',

 'RAW photo of p3r5on young woman, casual lifestyle photo, natural lighting, '
 'coffee shop setting, ultra-realistic, 8k resolution, highly detailed',

 'RAW photo of p3r5on young woman, outdoor portrait, golden hour lighting, '
 'urban background, ultra-realistic, 8k resolution, highly detailed',

 'RAW photo of p3r5on young woman, fitness lifestyle, activewear, '
 'gym setting, ultra-realistic, 8k resolution, highly detailed',

 'RAW photo of p3r5on young woman, elegant evening look, '
 'soft studio lighting, ultra-realistic, 8k resolution, highly detailed',
]


def now_iso() -> str:
 return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_json_path(job_id: str) -> Path:
 return JOBS_DIR / job_id / 'metadata' / 'job.json'


def load_json(path: Path) -> Dict[str, Any]:
 return json.loads(path.read_text())


def save_json(path: Path, data: Dict[str, Any]) -> None:
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(data, indent=2))


def generate_single_image(
 prompt: str,
 negative_prompt: str = DEFAULT_NEGATIVE,
 seed: int = -1,
 width: int = 864,
 height: int = 1536,
 endpoint: str = MODAL_ENDPOINT,
 timeout: int = 300,
) -> bytes:
 """Call Modal ComfyUI endpoint and return JPEG bytes."""
 if seed == -1:
  seed = random.randint(0, 2**32 - 1)

 params = urllib.parse.urlencode({
  'prompt': prompt,
  'negative_prompt': negative_prompt,
  'seed': seed,
  'width': width,
  'height': height,
 })

 url = f'{endpoint}?{params}'
 req = urllib.request.Request(url, method='POST')

 print(f' Generating: seed={seed}, {width}x{height}')
 print(f' Prompt: {prompt[:80]}...')

 start = time.time()
 with urllib.request.urlopen(req, timeout=timeout) as resp:
  data = resp.read()
 elapsed = time.time() - start

 print(f' Done: {len(data)} bytes in {elapsed:.1f}s')
 return data


def generate_preview_batch(
 job_id: str,
 prompts: List[str] | None = None,
 negative_prompt: str = DEFAULT_NEGATIVE,
 count: int = 5,
 width: int = 864,
 height: int = 1536,
 base_seed: int = -1,
 endpoint: str = MODAL_ENDPOINT,
) -> List[Path]:
 """Generate a batch of preview images for a job."""
 path = job_json_path(job_id)
 job = load_json(path)

 previews_dir = JOBS_DIR / job_id / 'previews'
 previews_dir.mkdir(parents=True, exist_ok=True)

 if prompts is None:
  prompts = PREVIEW_PROMPTS[:count]

 if base_seed == -1:
  base_seed = random.randint(0, 2**32 - 1)

 job['status'] = 'preview_running'
 job['updated_at'] = now_iso()
 save_json(path, job)

 generated_files: List[Path] = []
 errors: List[str] = []

 for i, prompt in enumerate(prompts):
  seed = base_seed + i
  filename = f'preview-{i+1:03d}-seed{seed}.jpg'
  out_path = previews_dir / filename

  try:
   print(f'\n[{i+1}/{len(prompts)}] Generating {filename}')
   img_bytes = generate_single_image(
    prompt=prompt,
    negative_prompt=negative_prompt,
    seed=seed,
    width=width,
    height=height,
    endpoint=endpoint,
   )
   out_path.write_bytes(img_bytes)
   generated_files.append(out_path)
   print(f' Saved: {out_path}')

  except Exception as e:
   error_msg = f'Failed to generate {filename}: {e}'
   print(f' ERROR: {error_msg}')
   errors.append(error_msg)

 gen_record = {
  'job_id': job_id,
  'generated_at': now_iso(),
  'endpoint': endpoint,
  'base_seed': base_seed,
  'width': width,
  'height': height,
  'prompts_used': prompts,
  'negative_prompt': negative_prompt,
  'files_generated': [p.name for p in generated_files],
  'errors': errors,
 }

 logs_dir = JOBS_DIR / job_id / 'logs'
 logs_dir.mkdir(parents=True, exist_ok=True)
 save_json(logs_dir / 'preview-generation.json', gen_record)

 job = load_json(path)
 preview = job.get('preview', {})
 preview['assets'] = [p.name for p in generated_files]
 preview['generation_record'] = {
  'base_seed': base_seed,
  'endpoint': endpoint,
  'generated_at': now_iso(),
  'count': len(generated_files),
 }
 job['preview'] = preview
 job['updated_at'] = now_iso()
 save_json(path, job)

 return generated_files


def main() -> int:
 parser = argparse.ArgumentParser(
  description='Generate preview images via Modal ComfyUI'
 )
 sub = parser.add_subparsers(dest='cmd', required=True)

 g = sub.add_parser('batch', help='Generate a batch of preview images')
 g.add_argument('--job-id', required=True)
 g.add_argument('--count', type=int, default=5,
  help='Number of images to generate')
 g.add_argument('--seed', type=int, default=-1,
  help='Base seed (-1 for random)')
 g.add_argument('--width', type=int, default=864)
 g.add_argument('--height', type=int, default=1536)
 g.add_argument('--endpoint', default=MODAL_ENDPOINT)
 g.add_argument('--prompt', action='append', default=None,
  help='Custom prompt (can specify multiple)')

 s = sub.add_parser('single', help='Generate a single test image')
 s.add_argument('--prompt', required=True)
 s.add_argument('--output', default='test-output.jpg')
 s.add_argument('--seed', type=int, default=-1)
 s.add_argument('--width', type=int, default=864)
 s.add_argument('--height', type=int, default=1536)
 s.add_argument('--endpoint', default=MODAL_ENDPOINT)

 p = sub.add_parser('ping', help='Test if Modal endpoint is reachable')
 p.add_argument('--endpoint', default=MODAL_ENDPOINT)

 args = parser.parse_args()

 if args.cmd == 'batch':
  files = generate_preview_batch(
   job_id=args.job_id,
   prompts=args.prompt,
   count=args.count,
   base_seed=args.seed,
   width=args.width,
   height=args.height,
   endpoint=args.endpoint,
  )
  print(f'\n=== Generated {len(files)} preview images ===')
  for f in files:
   print(f' {f}')
  print(f'\nNext step:')
  print(f' python scripts/preview_upload.py --job-id {args.job_id}')
  return 0

 elif args.cmd == 'single':
  img_bytes = generate_single_image(
   prompt=args.prompt,
   seed=args.seed,
   width=args.width,
   height=args.height,
   endpoint=args.endpoint,
  )
  out = Path(args.output)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_bytes(img_bytes)
  print(f'\nSaved: {out} ({len(img_bytes)} bytes)')
  return 0

 elif args.cmd == 'ping':
  print(f'Testing endpoint: {args.endpoint}')
  try:
   img = generate_single_image(
    prompt='test image, simple gradient background',
    seed=42,
    width=512,
    height=512,
    endpoint=args.endpoint,
    timeout=120,
   )
   print(f'SUCCESS: Got {len(img)} bytes back')
   return 0
  except Exception as e:
   print(f'FAILED: {e}')
   return 1

 return 0


if __name__ == '__main__':
 raise SystemExit(main())
