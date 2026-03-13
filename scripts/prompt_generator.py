#!/usr/bin/env python3
"""
Standalone prompt generator for AI Influencer Factory.

THIS TOOL IS MANUAL ONLY.
No agent, no automation, no orchestrator calls this.
Only the human operator runs it directly.

Uses OpenRouter API with dolphin-mistral-24b-venice-edition.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

# Try to load from Kaggle secrets if env var not set
if not os.environ.get('OPENROUTER_API_KEY'):
 try:
  from kaggle_secrets import UserSecretsClient
  _secrets = UserSecretsClient()
  os.environ['OPENROUTER_API_KEY'] = _secrets.get_secret('OPENROUTER_API_KEY')
 except Exception:
  pass

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODEL = 'cognitivecomputations/dolphin-mistral-24b-venice-edition:free'


def now_iso() -> str:
 return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def job_json_path(job_id: str) -> Path:
 return JOBS_DIR / job_id / 'metadata' / 'job.json'


def load_json(path: Path) -> Dict[str, Any]:
 return json.loads(path.read_text())


def save_json(path: Path, data: Dict[str, Any]) -> None:
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(data, indent=2))


def call_openrouter(
 system_prompt: str,
 user_prompt: str,
 api_key: str = '',
 model: str = MODEL,
 max_tokens: int = 4000,
 temperature: float = 0.85,
) -> str:
 """Call OpenRouter API with retry logic."""
 import time
 import urllib.error

 key = api_key or OPENROUTER_API_KEY
 if not key:
  raise ValueError(
   'No OpenRouter API key. '
   'Set OPENROUTER_API_KEY env var or pass --api-key'
  )

 models_to_try = [
  model,
  'cognitivecomputations/dolphin-mistral-24b-venice-edition:free',
  'nvidia/nemotron-3-super-120b-a12b:free',
  'nvidia/nemotron-3-nano-30b-a3b:free',
  'nvidia/nemotron-nano-9b-v2:free',
 ]
 seen = set()
 unique_models = []
 for m in models_to_try:
  if m not in seen:
   seen.add(m)
   unique_models.append(m)

 last_error = None

 for current_model in unique_models:
  for attempt in range(3):
   payload = {
    'model': current_model,
    'messages': [
     {'role': 'system', 'content': system_prompt},
     {'role': 'user', 'content': user_prompt},
    ],
    'max_tokens': max_tokens,
    'temperature': temperature,
   }

   req = urllib.request.Request(
    OPENROUTER_URL,
    data=json.dumps(payload).encode('utf-8'),
    headers={
     'Content-Type': 'application/json',
     'Authorization': f'Bearer {key}',
     'HTTP-Referer': 'https://openclaw.factory',
     'X-Title': 'AI Influencer Factory',
    },
    method='POST',
   )

   try:
    with urllib.request.urlopen(req, timeout=120) as resp:
     result = json.loads(resp.read().decode('utf-8'))
    content = result['choices'][0]['message']['content']
    if current_model != model:
     print(f' (Used fallback model: {current_model})')
    return content

   except urllib.error.HTTPError as e:
    last_error = e
    if e.code == 429:
     wait = (attempt + 1) * 10
     print(f' Rate limited on {current_model}, waiting {wait}s (attempt {attempt + 1}/3)...')
     time.sleep(wait)
    else:
     print(f' HTTP {e.code} on {current_model}: {e.reason}')
     break

   except Exception as e:
    last_error = e
    print(f' Error on {current_model}: {e}')
    break

 raise RuntimeError(f'All models failed. Last error: {last_error}')


SYSTEM_PROMPT = """You are an expert prompt engineer for AI image generation.

You write prompts for a Z-Image / Stable Diffusion model that generates ultra-realistic photos of AI influencer personas.

RULES:
1. Every prompt MUST start with: RAW photo of {trigger_word}
2. Every prompt MUST include: ultra-realistic, 8k resolution, highly detailed
3. Every prompt must describe: setting, lighting, outfit/styling, pose/mood
4. Prompts must be varied — different settings, outfits, lighting, moods
5. Prompts must match the specified niche and style direction
6. Do NOT include negative prompts — those are handled separately
7. Output ONLY the prompts, one per line, numbered
8. No explanations, no commentary, just the numbered prompts
9. Each prompt should be 1-3 sentences maximum
10. Make them feel like real Instagram/social media photo descriptions"""


def build_user_prompt(
 trigger_word: str,
 niche: str,
 style: str,
 count: int,
 notes: str = '',
) -> str:
 prompt = f"""Generate exactly {count} image generation prompts for an AI influencer.

Trigger word (MUST appear at start of every prompt): {trigger_word}
Niche: {niche}
Style direction: {style}
"""
 if notes:
  prompt += f"\nAdditional notes from client: {notes}\n"

 prompt += f"""
Generate exactly {count} prompts. Number them 1 to {count}.
Each prompt must start with: RAW photo of {trigger_word}
"""
 return prompt


def parse_prompts(raw_text: str, trigger_word: str) -> List[str]:
 """Parse numbered prompts from LLM output."""
 prompts = []

 # First, try to split merged lines (e.g., "8. prompt one 9. prompt two")
 # by detecting numbered patterns mid-line
 expanded_lines = []
 for line in raw_text.strip().split('\n'):
  parts = re.split(r'(?<=\S)\s+(?=\d+[\.\)\:\-]\s)', line.strip())
  expanded_lines.extend(parts)

 for line in expanded_lines:
  line = line.strip()
  if not line:
   continue

  cleaned = re.sub(r'^\d+[\.\)\:\-]\s*', '', line).strip()

  if not cleaned:
   continue

  if len(cleaned) < 20:
   continue

  if trigger_word.lower() not in cleaned.lower():
   cleaned = f'RAW photo of {trigger_word} {cleaned}'

  if not cleaned.lower().startswith('raw photo'):
   cleaned = f'RAW photo of {trigger_word}, {cleaned}'

  prompts.append(cleaned)

 return prompts


def generate_prompts(
 job_id: str = '',
 trigger_word: str = 'p3r5on',
 niche: str = 'lifestyle',
 style: str = 'natural, casual, modern',
 count: int = 20,
 notes: str = '',
 api_key: str = '',
 save_to_job: bool = True,
) -> List[str]:
 """Generate prompts using OpenRouter and optionally save to job folder."""

 print(f'Generating {count} prompts...')
 print(f' Niche: {niche}')
 print(f' Style: {style}')
 print(f' Trigger word: {trigger_word}')
 print(f' Model: {MODEL}')
 print()

 user_prompt = build_user_prompt(trigger_word, niche, style, count, notes)
 raw_response = call_openrouter(SYSTEM_PROMPT, user_prompt, api_key=api_key)

 print('--- RAW LLM OUTPUT ---')
 print(raw_response)
 print('--- END RAW OUTPUT ---')
 print()

 prompts = parse_prompts(raw_response, trigger_word)

 print(f'Parsed {len(prompts)} prompts:')
 for i, p in enumerate(prompts, 1):
  print(f' {i}. {p[:100]}{"..." if len(p) > 100 else ""}')

 if save_to_job and job_id:
  prompts_dir = JOBS_DIR / job_id / 'intake'
  prompts_dir.mkdir(parents=True, exist_ok=True)

  prompt_file = prompts_dir / 'generated-prompts.json'
  prompt_data = {
   'job_id': job_id,
   'generated_at': now_iso(),
   'model': MODEL,
   'trigger_word': trigger_word,
   'niche': niche,
   'style': style,
   'notes': notes,
   'count_requested': count,
   'count_generated': len(prompts),
   'prompts': prompts,
   'raw_response': raw_response,
  }
  save_json(prompt_file, prompt_data)
  print(f'\nSaved to: {prompt_file}')

  txt_file = prompts_dir / 'prompts.txt'
  txt_file.write_text('\n'.join(prompts))
  print(f'Plain text: {txt_file}')

 return prompts


def main() -> int:
 parser = argparse.ArgumentParser(
  description=(
   'Generate image prompts using AI. '
   'MANUAL TOOL ONLY — not for agent/automation use.'
  )
 )

 parser.add_argument('--job-id', default='', help='Job ID to save prompts to')
 parser.add_argument('--trigger-word', default='p3r5on', help='LoRA trigger word')
 parser.add_argument('--niche', required=True, help='Content niche (fitness, luxury, travel, casual, etc)')
 parser.add_argument('--style', default='natural, casual, modern', help='Style direction')
 parser.add_argument('--count', type=int, default=20, help='Number of prompts to generate')
 parser.add_argument('--notes', default='', help='Additional client notes')
 parser.add_argument('--api-key', default='', help='OpenRouter API key (or set OPENROUTER_API_KEY env)')
 parser.add_argument('--no-save', action='store_true', help='Do not save to job folder')

 args = parser.parse_args()

 prompts = generate_prompts(
  job_id=args.job_id,
  trigger_word=args.trigger_word,
  niche=args.niche,
  style=args.style,
  count=args.count,
  notes=args.notes,
  api_key=args.api_key,
  save_to_job=not args.no_save,
 )

 if not prompts:
  print('ERROR: No prompts generated')
  return 1

 print(f'\n=== {len(prompts)} prompts ready ===')

 if args.job_id:
  print(f'\nTo generate images with these prompts:')
  print(f' python scripts/generate_previews.py batch \\')
  print(f' --job-id {args.job_id} \\')
  print(f' --count {len(prompts)}')
  print(f'\nOr review/edit first:')
  print(f' cat jobs/{args.job_id}/intake/prompts.txt')

 return 0


if __name__ == '__main__':
 raise SystemExit(main())
