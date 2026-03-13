#!/usr/bin/env python3
"""Generate final delivery batch via Modal ComfyUI endpoint."""
from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import List

from generate_previews import (
    generate_single_image,
    load_json,
    save_json,
    now_iso,
    MODAL_ENDPOINT,
    DEFAULT_NEGATIVE,
)

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'

FINAL_PROMPTS = [
 'RAW photo of p3r5on young woman, professional headshot, studio lighting, neutral background, ultra-realistic, 8k resolution, highly detailed',
 'RAW photo of p3r5on young woman, casual lifestyle, coffee shop, natural window lighting, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, outdoor portrait, golden hour, city skyline background, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, fitness lifestyle, activewear, modern gym, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, elegant evening dress, upscale restaurant, soft lighting, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, beach lifestyle, sunset, tropical setting, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, business casual, modern office, confident pose, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, street style fashion, urban, graffiti wall background, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, cozy home setting, loungewear, warm natural lighting, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, travel lifestyle, European cafe, candid pose, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, poolside, swimwear, luxury resort, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, yoga pose, outdoor deck, morning light, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, night out look, rooftop bar, city lights background, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, autumn fashion, park setting, fall colors, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, mirror selfie style, modern bathroom, casual outfit, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, brunch setting, outdoor patio, stylish outfit, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, shopping lifestyle, luxury store, carrying bags, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, reading in library, intellectual look, warm lighting, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, cooking in modern kitchen, casual home outfit, ultra-realistic, 8k resolution',
 'RAW photo of p3r5on young woman, hiking trail, athletic outfit, mountain scenery, ultra-realistic, 8k resolution',
]


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
    """Generate final delivery images for a job."""
    path = job_json_path(job_id)
    job = load_json(path)

    if job.get('status') not in ('training_done', 'final_generation_running'):
        raise ValueError(f'Job {job_id} is "{job.get("status")}", expected "training_done"')

    finals_dir = JOBS_DIR / job_id / 'final_batches'
    finals_dir.mkdir(parents=True, exist_ok=True)

    if prompts is None:
        if count <= len(FINAL_PROMPTS):
            prompts = FINAL_PROMPTS[:count]
        else:
            prompts = [FINAL_PROMPTS[i % len(FINAL_PROMPTS)] for i in range(count)]

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
            img_bytes, ext = generate_single_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                width=width,
                height=height,
                endpoint=endpoint,
            )
            filename = f'final-{i+1:03d}-seed{seed}{ext}'
            out_path = finals_dir / filename
            out_path.write_bytes(img_bytes)
            generated_files.append(out_path)
            print(f' Saved: {out_path}')
        except Exception as e:
            error_msg = f'Failed to generate final-{i+1:03d}: {e}'
            print(f' ERROR: {error_msg}')
            errors.append(error_msg)

    gen_record = {
        'job_id': job_id,
        'stage': 'final_batch',
        'generated_at': now_iso(),
        'endpoint': endpoint,
        'base_seed': base_seed,
        'width': width,
        'height': height,
        'prompts_used': prompts,
        'files_generated': [p.name for p in generated_files],
        'errors': errors,
    }

    logs_dir = JOBS_DIR / job_id / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    save_json(logs_dir / 'final-generation.json', gen_record)

    job = load_json(path)
    final_batch = job.get('final_batch', {})
    final_batch['assets'] = [p.name for p in generated_files]
    final_batch['generation_record'] = {
        'base_seed': base_seed,
        'endpoint': endpoint,
        'generated_at': now_iso(),
        'count': len(generated_files),
    }
    job['final_batch'] = final_batch
    job['status'] = 'training_done'
    job['updated_at'] = now_iso()
    save_json(path, job)

    return generated_files


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate final delivery images via Modal')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--count', type=int, default=20, help='Number of final images')
    parser.add_argument('--seed', type=int, default=-1)
    parser.add_argument('--width', type=int, default=864)
    parser.add_argument('--height', type=int, default=1536)
    parser.add_argument('--endpoint', default=MODAL_ENDPOINT)
    parser.add_argument('--prompt', action='append', default=None)
    args = parser.parse_args()

    files = generate_final_batch(
        job_id=args.job_id,
        prompts=args.prompt,
        count=args.count,
        base_seed=args.seed,
        width=args.width,
        height=args.height,
        endpoint=args.endpoint,
    )

    print(f'\n=== Generated {len(files)} final images ===')
    for f in files:
        print(f' {f}')
    print(f'\nNext steps:')
    print(f' python scripts/final_batch_handler.py upload --job-id {args.job_id}')
    print(f' python scripts/final_batch_handler.py qa-approve --job-id {args.job_id}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
