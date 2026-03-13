#!/usr/bin/env python3
"""Generate final delivery batch via Modal ComfyUI endpoint."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))
from generate_previews import (
 generate_single_image,
 load_json,
 save_json,
 now_iso,
 MODAL_ENDPOINT,
 DEFAULT_NEGATIVE,
 PREVIEW_PROMPTS,
)

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'


def job_json_path(job_id: str) -> Path:
 return JOBS_DIR / job_id / 'metadata' / 'job.json'


def generate_final_batch(
 job_id: str,
 prompts: List[str] | None = None,
 negative_prompt: str = DEFAULT_NEGATIVE,
 count: int = 20,
 width: int = 864,
 height: int = 1536,
 base_seed: int = -1,
 endpoint: str = MODAL_ENDPOINT,
) -> List[Path]:
 path = job_json_path(job_id)
 job = load_json(path)

 if job.get('status') not in ('training_done', 'final_generation_running'):
  raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "training_done"')

 finals_dir = JOBS_DIR / job_id / 'final_batches'
 finals_dir.mkdir(parents=True, exist_ok=True)

 if prompts is None:
  prompts_file = JOBS_DIR / job_id / 'intake' / 'generated-prompts.json'
  if prompts_file.exists():
   prompt_data = load_json(prompts_file)
   all_prompts = prompt_data.get('prompts', [])
   if all_prompts:
    prompts = []
    for i in range(count):
     prompts.append(all_prompts[i % len(all_prompts)])
    print(f'Using prompts from {prompts_file}')

 if prompts is None:
  prompts = []
  for i in range(count):
   prompts.append(PREVIEW_PROMPTS[i % len(PREVIEW_PROMPTS)])

 if base_seed == -1:
  base_seed = random.randint(0, 2**32 - 1)

 job['status'] = 'final_generation_running'
 job['updated_at'] = now_iso()
 save_json(path, job)

 generated_files: List[Path] = []
 errors: List[str] = []

 for i, prompt in enumerate(prompts):
  seed = base_seed + i
  try:
   print(f'\n[{i+1}/{len(prompts)}] Generating final image {i+1}')
   img_bytes, ext = generate_single_image(prompt=prompt, negative_prompt=negative_prompt, seed=seed, width=width, height=height, endpoint=endpoint)
   filename = f'final-{i+1:03d}-seed{seed}{ext}'
   out_path = finals_dir / filename
   out_path.write_bytes(img_bytes)
   generated_files.append(out_path)
   print(f' Saved: {out_path}')
  except Exception as e:
   error_msg = f'Failed to generate final-{i+1:03d}: {e}'
   print(f' ERROR: {error_msg}')
   errors.append(error_msg)

 gen_record = {'job_id': job_id, 'stage': 'final_batch', 'generated_at': now_iso(), 'endpoint': endpoint, 'base_seed': base_seed, 'files_generated': [p.name for p in generated_files], 'errors': errors}
 logs_dir = JOBS_DIR / job_id / 'logs'
 logs_dir.mkdir(parents=True, exist_ok=True)
 save_json(logs_dir / 'final-generation.json', gen_record)

 job = load_json(path)
 final_batch = job.get('final_batch', {})
 final_batch['assets'] = [p.name for p in generated_files]
 job['final_batch'] = final_batch
 job['status'] = 'training_done'
 job['updated_at'] = now_iso()
 save_json(path, job)

 return generated_files


def main() -> int:
 parser = argparse.ArgumentParser(description='Generate final delivery images')
 parser.add_argument('--job-id', required=True)
 parser.add_argument('--count', type=int, default=20)
 parser.add_argument('--seed', type=int, default=-1)
 parser.add_argument('--width', type=int, default=864)
 parser.add_argument('--height', type=int, default=1536)
 parser.add_argument('--endpoint', default=MODAL_ENDPOINT)
 parser.add_argument('--prompt', action='append', default=None)
 args = parser.parse_args()
 files = generate_final_batch(job_id=args.job_id, prompts=args.prompt, count=args.count, base_seed=args.seed, width=args.width, height=args.height, endpoint=args.endpoint)
 print(f'\n=== Generated {len(files)} final images ===')
 for f in files:
  print(f' {f}')
 print(f'\nNext steps:')
 print(f' python scripts/final_batch_handler.py upload --job-id {args.job_id}')
 return 0


if __name__ == '__main__':
 raise SystemExit(main())
