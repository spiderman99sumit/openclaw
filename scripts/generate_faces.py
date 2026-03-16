#!/usr/bin/env python3
"""
Stage 2 — Step 1: Face candidate generation
Generates 5 face images using Z-Image endpoint with no client LoRA (strength=0).
Images saved to jobs/JOB_ID/references/face_candidates/

Usage:
  python scripts/generate_faces.py --job-id CLIENT-001
  python scripts/generate_faces.py --job-id CLIENT-001 --feedback "more ethnic, darker skin, longer hair"
  python scripts/generate_faces.py --job-id CLIENT-001 --select 3
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE   = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR    = WORKSPACE / 'jobs'
SCRIPTS_DIR = WORKSPACE / 'scripts'

ZIMAGE_URL  = os.environ.get(
    'MODAL_ZIMAGE_URL',
    'https://lastgamer612--comfyui-zimage-generate.modal.run'
)
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')

COUNT = 5


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def job_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / 'metadata' / 'job.json'


def build_face_prompt(niche: str, style: str, feedback: str = '') -> str:
    """
    Build a face generation prompt from job metadata + optional feedback.
    No trigger word needed here — this is a candidate face, no LoRA.
    """
    base = (
        "masterpiece, best quality, ultra photorealistic, RAW 8k photo, "
        "close-up portrait shot, sharp focus on face, "
        "beautiful young woman, "
        "flawless smooth skin with visible realistic pores, "
        "natural subsurface scattering, "
        "professional studio lighting with soft catchlights in eyes, "
        "neutral background, "
        "shot on Canon EOS R5 85mm f/1.4 lens"
    )

    niche_prompts = {
        'fitness':     'athletic build, strong jawline, bright confident eyes, sporty vibe',
        'glamour':     'full glossy lips, dramatic eye makeup, high cheekbones, luxury editorial look',
        'onlyfans':    'seductive expression, sultry eyes, natural makeup, intimate vibe',
        'lifestyle':   'girl-next-door look, warm smile, approachable natural beauty',
        'cosplay':     'expressive face, striking features, bold eye contact',
        'mature':      'elegant mature woman, sophisticated look, refined features',
    }

    style_prompts = {
        'asian':       'east asian features, almond-shaped eyes, straight black hair',
        'latina':      'latina features, warm olive skin, dark expressive eyes, dark hair',
        'european':    'european features, light skin, blue or green eyes',
        'african':     'african features, rich dark skin, full lips, natural hair',
        'mixed':       'mixed ethnicity, exotic features, unique striking look',
        'blonde':      'blonde hair, light eyes, fair skin',
        'brunette':    'brunette hair, brown eyes, warm skin tone',
        'redhead':     'red hair, freckles, pale skin, green eyes',
    }

    parts = [base]

    niche_lower = niche.lower() if niche else ''
    for key, val in niche_prompts.items():
        if key in niche_lower:
            parts.append(val)
            break

    style_lower = style.lower() if style else ''
    for key, val in style_prompts.items():
        if key in style_lower:
            parts.append(val)
            break

    if niche and niche.lower() not in [k for k in niche_prompts]:
        parts.append(niche)
    if style and style.lower() not in [k for k in style_prompts]:
        parts.append(style)

    if feedback and feedback.strip():
        parts.append(feedback.strip())

    return ', '.join(parts)


def call_zimage(prompt: str, seed: int, out_path: Path) -> bool:
    """Call Z-Image endpoint with lora_strength=0 (no client LoRA), 1024x1024."""
    payload = json.dumps({
        'prompt':        prompt,
        'seed':          seed,
        'width':         1024,
        'height':        1024,
        'lora_name':     'bg4m_000000700.safetensors',
        'lora_strength': 0.0,   # bypass client LoRA entirely
    }).encode('utf-8')

    req = urllib.request.Request(
        ZIMAGE_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(resp.read())
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  HTTP {e.code}: {body[:200]}')
        return False
    except Exception as e:
        print(f'  Error: {e}')
        return False


def generate_faces(job_id: str, feedback: str = '', round_num: int = 1) -> list:
    """Generate COUNT face candidates. Returns list of saved paths."""
    path = job_path(job_id)
    if not path.exists():
        print(f'ERROR: Job {job_id} not found at {path}')
        sys.exit(1)

    job = load_json(path)
    niche = job.get('niche', '')
    style = job.get('style', '')

    prompt = build_face_prompt(niche, style, feedback)
    print(f'\nPrompt: {prompt[:120]}...\n')

    candidates_dir = JOBS_DIR / job_id / 'references' / 'face_candidates'
    candidates_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    import random
    base_seed = random.randint(10000, 999999)

    for i in range(1, COUNT + 1):
        seed = base_seed + i
        fname = f'face_{round_num:02d}_{i:02d}.png'
        out_path = candidates_dir / fname
        print(f'  Generating {fname} (seed={seed})...', end=' ', flush=True)

        ok = call_zimage(prompt, seed, out_path)
        if ok:
            print(f'saved ({out_path.stat().st_size // 1024} KB)')
            saved.append(str(out_path))
        else:
            print('FAILED')

    # Update job.json
    job.setdefault('stage2', {})
    job['stage2']['face_candidates'] = saved
    job['stage2']['face_prompt'] = prompt
    job['stage2']['face_feedback'] = feedback
    job['stage2']['face_round'] = round_num
    job['stage2']['face_generated_at'] = now_iso()
    job['status'] = 'face_selection'
    job['updated_at'] = now_iso()
    save_json(path, job)

    print(f'\n  {len(saved)}/{COUNT} images saved to: {candidates_dir}')
    print(f'\nChoose a face and run:')
    print(f'  python scripts/generate_faces.py --job-id {job_id} --select N  (1-{COUNT})')
    print(f'Or regenerate with feedback:')
    print(f'  python scripts/generate_faces.py --job-id {job_id} --feedback "your feedback here"')

    return saved


def select_face(job_id: str, choice: int) -> str:
    """Mark a candidate as the selected face for this job."""
    path = job_path(job_id)
    job = load_json(path)

    candidates = job.get('stage2', {}).get('face_candidates', [])
    if not candidates:
        print('ERROR: No face candidates found. Run generate_faces first.')
        sys.exit(1)

    if choice < 1 or choice > len(candidates):
        print(f'ERROR: Choice must be 1-{len(candidates)}')
        sys.exit(1)

    selected_src = Path(candidates[choice - 1])
    if not selected_src.exists():
        print(f'ERROR: File not found: {selected_src}')
        sys.exit(1)

    selected_dst = JOBS_DIR / job_id / 'references' / 'selected_face.png'
    import shutil
    shutil.copy2(selected_src, selected_dst)

    job['stage2']['selected_face'] = str(selected_dst)
    job['stage2']['selected_face_index'] = choice
    job['stage2']['selected_at'] = now_iso()
    job['status'] = 'face_selected'
    job['updated_at'] = now_iso()
    save_json(path, job)

    print(f'\n  Selected: face {choice} → {selected_dst}')
    print(f'  Status: face_selected')
    print(f'\nNext: upload body images to:')
    print(f'  {JOBS_DIR / job_id / "references" / "bodies"}/')
    print(f'Then run:')
    print(f'  python scripts/generate_dataset.py --job-id {job_id}')

    return str(selected_dst)


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate face candidates for a job')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--feedback', default='', help='Feedback to refine next generation')
    parser.add_argument('--select', type=int, default=0, help='Select face number (1-5)')
    parser.add_argument('--zimage-url', default='', help='Override Z-Image endpoint URL')
    args = parser.parse_args()

    if args.zimage_url:
        global ZIMAGE_URL
        ZIMAGE_URL = args.zimage_url

    if args.select > 0:
        select_face(args.job_id, args.select)
    else:
        path = job_path(args.job_id)
        job = load_json(path)
        current_round = job.get('stage2', {}).get('face_round', 0) + 1
        generate_faces(args.job_id, args.feedback, current_round)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
