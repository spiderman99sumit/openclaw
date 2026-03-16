#!/usr/bin/env python3
"""
Stage 2 — Step 2: Dataset generation
Face swap selected_face.png × all body images in references/bodies/
Captions each result using NVIDIA Nemotron Nano VL via OpenRouter.
Output saved to jobs/JOB_ID/dataset/

Usage:
  python scripts/generate_dataset.py --job-id CLIENT-001
  python scripts/generate_dataset.py --job-id CLIENT-001 --bodies-dir /path/to/bodies
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE      = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR       = WORKSPACE / 'jobs'

FACESWAP_URL   = os.environ.get(
    'MODAL_FACESWAP_URL',
    'https://km485890--comfyui-faceswap-swap.modal.run'
)
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
CAPTION_MODEL  = 'nvidia/llama-3.1-nemotron-nano-vl-8b-v1'

TRIGGER_WORD   = 'p3r5on'
IMAGE_EXTS     = {'.jpg', '.jpeg', '.png', '.webp'}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def job_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / 'metadata' / 'job.json'


def to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode('ascii')


def call_faceswap(face_path: Path, body_path: Path, seed: int = 42) -> bytes | None:
    """Call face swap endpoint, return PNG bytes or None on failure."""
    payload = json.dumps({
        'face_image': to_base64(face_path),
        'body_image': to_base64(body_path),
        'seed':       seed,
    }).encode('utf-8')

    req = urllib.request.Request(
        FACESWAP_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'    Face swap HTTP {e.code}: {body[:200]}')
        return None
    except Exception as e:
        print(f'    Face swap error: {e}')
        return None


def call_caption(image_path: Path, niche: str, style: str) -> str:
    """
    Caption an image using NVIDIA Nemotron Nano VL via OpenRouter.
    Falls back to template caption if API call fails.
    """
    if not OPENROUTER_KEY:
        return build_template_caption(niche, style)

    image_b64 = to_base64(image_path)
    ext = image_path.suffix.lower().lstrip('.')
    mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
    data_url = f'data:{mime};base64,{image_b64}'

    system_prompt = (
        f'You write captions for AI image training datasets. '
        f'Always start captions with "{TRIGGER_WORD}," followed by a comma. '
        f'Be specific about pose, outfit, setting, lighting, and expression. '
        f'One sentence only. No quotes. No preamble.'
    )

    user_prompt = (
        f'Write a training caption for this photo. '
        f'The subject is a {niche} content creator with a {style} look. '
        f'Start with "{TRIGGER_WORD}," then describe what you see: '
        f'pose, clothing, setting, lighting. One sentence only.'
    )

    payload = json.dumps({
        'model': CAPTION_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {
                'role': 'user',
                'content': [
                    {
                        'type':      'image_url',
                        'image_url': {'url': data_url},
                    },
                    {
                        'type': 'text',
                        'text': user_prompt,
                    },
                ],
            },
        ],
        'max_tokens': 120,
        'temperature': 0.4,
    }).encode('utf-8')

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            'Content-Type':  'application/json',
            'Authorization': f'Bearer {OPENROUTER_KEY}',
            'HTTP-Referer':  'https://github.com/spiderman99sumit/openclaw',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            caption = data['choices'][0]['message']['content'].strip()
            # Ensure trigger word is present
            if not caption.lower().startswith(TRIGGER_WORD.lower()):
                caption = f'{TRIGGER_WORD}, {caption}'
            return caption
    except Exception as e:
        print(f'    Caption API error: {e} — using template')
        return build_template_caption(niche, style)


def build_template_caption(niche: str, style: str) -> str:
    """Fallback caption when OpenRouter is unavailable."""
    return (
        f'{TRIGGER_WORD}, realistic photo of a young woman, '
        f'{niche} content, {style} look, natural lighting, confident pose'
    )


def collect_body_images(bodies_dir: Path) -> list[Path]:
    if not bodies_dir.exists():
        return []
    return sorted([
        p for p in bodies_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ])


def generate_dataset(job_id: str, bodies_dir: Path | None = None) -> dict:
    path = job_path(job_id)
    if not path.exists():
        print(f'ERROR: Job {job_id} not found')
        sys.exit(1)

    job = load_json(path)

    # Selected face
    selected_face_str = job.get('stage2', {}).get('selected_face', '')
    if not selected_face_str:
        print('ERROR: No selected face. Run generate_faces.py --select N first.')
        sys.exit(1)

    face_path = Path(selected_face_str)
    if not face_path.exists():
        face_path = JOBS_DIR / job_id / 'references' / 'selected_face.png'
    if not face_path.exists():
        print(f'ERROR: selected_face.png not found at {face_path}')
        sys.exit(1)

    # Body images
    if bodies_dir is None:
        bodies_dir = JOBS_DIR / job_id / 'references' / 'bodies'

    bodies = collect_body_images(bodies_dir)
    if not bodies:
        print(f'ERROR: No body images found in {bodies_dir}')
        print(f'Upload body images (.jpg/.png) to that folder and re-run.')
        sys.exit(1)

    niche = job.get('niche', 'lifestyle')
    style = job.get('style', 'natural')

    dataset_dir = JOBS_DIR / job_id / 'dataset'
    dataset_dir.mkdir(parents=True, exist_ok=True)

    print(f'\nJob:          {job_id}')
    print(f'Face:         {face_path.name}')
    print(f'Body images:  {len(bodies)}')
    print(f'Output:       {dataset_dir}')
    print(f'Caption model: {CAPTION_MODEL}')
    print()

    results = []
    errors  = []

    for idx, body_path in enumerate(bodies, 1):
        print(f'[{idx}/{len(bodies)}] {body_path.name}')

        out_img  = dataset_dir / f'{idx:04d}.png'
        out_txt  = dataset_dir / f'{idx:04d}.txt'

        # Skip if already done
        if out_img.exists() and out_txt.exists():
            print(f'  already exists — skipping')
            results.append({
                'index':   idx,
                'body':    body_path.name,
                'image':   str(out_img),
                'caption': out_txt.read_text().strip(),
            })
            continue

        # Face swap
        print(f'  Swapping face...', end=' ', flush=True)
        import random
        seed = random.randint(1, 99999)
        swapped = call_faceswap(face_path, body_path, seed=seed)

        if swapped is None:
            print('FAILED')
            errors.append({'index': idx, 'body': body_path.name, 'error': 'face swap failed'})
            continue

        out_img.write_bytes(swapped)
        print(f'done ({len(swapped) // 1024} KB)')

        # Caption
        print(f'  Captioning...', end=' ', flush=True)
        caption = call_caption(out_img, niche, style)
        out_txt.write_text(caption)
        print(f'done')
        print(f'  Caption: {caption[:90]}')

        results.append({
            'index':   idx,
            'body':    body_path.name,
            'image':   str(out_img),
            'caption': caption,
        })

        # Small delay to avoid hammering endpoints
        if idx < len(bodies):
            time.sleep(1)

    # Update job.json
    job.setdefault('stage2', {})
    job['stage2']['dataset'] = {
        'total':      len(bodies),
        'completed':  len(results),
        'errors':     len(errors),
        'directory':  str(dataset_dir),
        'items':      results,
        'error_list': errors,
        'generated_at': now_iso(),
    }
    job['status'] = 'dataset_ready' if not errors else 'dataset_partial'
    job['updated_at'] = now_iso()
    save_json(path, job)

    print(f'\n{"="*50}')
    print(f'  Completed: {len(results)}/{len(bodies)}')
    if errors:
        print(f'  Errors:    {len(errors)}')
        for e in errors:
            print(f'    [{e["index"]}] {e["body"]}: {e["error"]}')
    print(f'  Dataset:   {dataset_dir}')
    print(f'  Status:    {job["status"]}')

    if job['status'] == 'dataset_ready':
        print(f'\nDataset ready for LoRA training.')

    return {
        'job_id':    job_id,
        'completed': len(results),
        'errors':    len(errors),
        'directory': str(dataset_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate face-swap dataset with captions')
    parser.add_argument('--job-id',     required=True)
    parser.add_argument('--bodies-dir', default='', help='Override bodies directory')
    parser.add_argument('--faceswap-url', default='', help='Override face swap endpoint')
    args = parser.parse_args()

    if args.faceswap_url:
        global FACESWAP_URL
        FACESWAP_URL = args.faceswap_url

    bodies_dir = Path(args.bodies_dir) if args.bodies_dir else None
    generate_dataset(args.job_id, bodies_dir)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
