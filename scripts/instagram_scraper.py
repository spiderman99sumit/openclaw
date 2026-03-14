#!/usr/bin/env python3
"""
Instagram Public Profile Scraper — AI Influencer Factory

Scrapes best posts from any public Instagram profile.
Downloads images and metadata for LoRA training dataset prep.

MANUAL TOOL ONLY — not for automated/agent use.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

WORKSPACE = Path('/kaggle/working/.openclaw/workspace')
JOBS_DIR = WORKSPACE / 'jobs'


def now_iso() -> str:
 return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def save_json(path: Path, data: Any) -> None:
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(data, indent=2))


def load_json(path: Path) -> Dict[str, Any]:
 return json.loads(path.read_text())


def sanitize_filename(name: str) -> str:
 return re.sub(r'[^\w\-.]', '_', name)


def scrape_profile(
 username: str,
 output_dir: Path,
 max_posts: int = 300,
 sort_by: str = 'likes',
 images_only: bool = True,
 min_likes: int = 0,
 login_user: str = '',
 login_pass: str = '',
) -> Dict[str, Any]:
 """
 Scrape public Instagram profile and download best posts.
 
 Returns metadata about the scrape.
 """
 import instaloader

 L = build_loader(quiet=False, login_user=login_user, login_pass=login_pass)

 print(f'\nScraping @{username} (max {max_posts} posts)...\n')

 try:
  profile = instaloader.Profile.from_username(L.context, username)
 except instaloader.exceptions.ProfileNotExistsException:
  raise ValueError(f'Profile @{username} does not exist')
 except instaloader.exceptions.ConnectionException as e:
  raise ConnectionError(f'Could not connect to Instagram: {e}')

 profile_info = {
  'username': profile.username,
  'full_name': profile.full_name,
  'biography': profile.biography,
  'followers': profile.followers,
  'following': profile.followees,
  'post_count': profile.mediacount,
  'is_private': profile.is_private,
  'profile_pic_url': profile.profile_pic_url,
 }

 print(f' Profile: @{profile.username}')
 print(f' Name: {profile.full_name}')
 print(f' Followers: {profile.followers:,}')
 print(f' Posts: {profile.mediacount:,}')

 if profile.is_private:
  raise ValueError(f'Profile @{username} is private. Cannot scrape.')

 # Collect posts
 print(f'\n Collecting posts...')
 all_posts = []
 post_count = 0

 try:
  for post in profile.get_posts():
   if post_count >= max_posts:
    break

   # Skip videos if images_only
   if images_only and post.is_video:
    continue

   # Skip carousel/sidecar — collect individual images
   post_data = {
    'shortcode': post.shortcode,
    'url': f'https://www.instagram.com/p/{post.shortcode}/',
    'timestamp': post.date_utc.isoformat() + 'Z',
    'likes': post.likes,
    'comments': post.comments,
    'caption': post.caption or '',
    'is_video': post.is_video,
    'is_sidecar': post.typename == 'GraphSidecar',
    'image_url': post.url if not post.is_video else '',
    'engagement': post.likes + (post.comments * 3),
   }

   if min_likes > 0 and post.likes < min_likes:
    continue

   all_posts.append(post_data)
   post_count += 1

   if post_count % 25 == 0:
    print(f' Collected {post_count} posts...')

   # Small delay to avoid rate limiting
   if post_count % 50 == 0:
    print(f' Pausing to avoid rate limit...')
    time.sleep(3)

 except instaloader.exceptions.ConnectionException as e:
  print(f'\n Connection interrupted after {len(all_posts)} posts: {e}')
  print(f' Continuing with what we have...')
 except KeyboardInterrupt:
  print(f'\n Interrupted. Continuing with {len(all_posts)} posts...')

 if not all_posts:
  raise ValueError(f'No posts found for @{username}')

 print(f'\n Total posts collected: {len(all_posts)}')

 # Sort posts
 if sort_by == 'likes':
  all_posts.sort(key=lambda p: p['likes'], reverse=True)
 elif sort_by == 'engagement':
  all_posts.sort(key=lambda p: p['engagement'], reverse=True)
 elif sort_by == 'recent':
  all_posts.sort(key=lambda p: p['timestamp'], reverse=True)
 elif sort_by == 'oldest':
  all_posts.sort(key=lambda p: p['timestamp'])

 print(f' Sorted by: {sort_by}')
 print(f' Top post: {all_posts[0]["likes"]:,} likes')
 print(f' Lowest post: {all_posts[-1]["likes"]:,} likes')

 # Download images
 output_dir.mkdir(parents=True, exist_ok=True)
 images_dir = output_dir / 'images'
 images_dir.mkdir(parents=True, exist_ok=True)

 print(f'\n Downloading images to: {images_dir}')

 downloaded = []
 download_errors = []

 for i, post in enumerate(all_posts):
  if post['is_video']:
   continue

  image_url = post.get('image_url', '')
  if not image_url:
   continue

  filename = f'{i+1:04d}_likes{post["likes"]}_{post["shortcode"]}.jpg'
  filepath = images_dir / filename

  try:
   import urllib.request
   urllib.request.urlretrieve(image_url, str(filepath))
   post['local_file'] = str(filepath)
   post['local_filename'] = filename
   downloaded.append(post)

   if (i + 1) % 25 == 0:
    print(f' Downloaded {i+1}/{len(all_posts)} images...')

   # Rate limiting
   if (i + 1) % 50 == 0:
    time.sleep(2)

  except Exception as e:
   error = f'Failed to download {post["shortcode"]}: {e}'
   download_errors.append(error)
   if len(download_errors) <= 5:
    print(f' WARNING: {error}')

 print(f'\n Downloaded: {len(downloaded)} images')
 if download_errors:
  print(f' Errors: {len(download_errors)}')

 # Save metadata
 scrape_result = {
  'username': username,
  'scraped_at': now_iso(),
  'profile': profile_info,
  'settings': {
   'max_posts': max_posts,
   'sort_by': sort_by,
   'images_only': images_only,
   'min_likes': min_likes,
  },
  'stats': {
   'total_collected': len(all_posts),
   'total_downloaded': len(downloaded),
   'download_errors': len(download_errors),
   'avg_likes': sum(p['likes'] for p in all_posts) // max(len(all_posts), 1),
   'max_likes': all_posts[0]['likes'] if all_posts else 0,
   'min_likes': all_posts[-1]['likes'] if all_posts else 0,
  },
  'posts': all_posts,
  'errors': download_errors[:20],
 }

 metadata_path = output_dir / 'scrape-metadata.json'
 save_json(metadata_path, scrape_result)
 print(f'\n Metadata saved: {metadata_path}')

 # Save top posts summary
 top_posts = all_posts[:50]
 summary_path = output_dir / 'top-posts-summary.json'
 save_json(summary_path, {
  'username': username,
  'top_50_posts': [
   {
    'rank': i + 1,
    'likes': p['likes'],
    'comments': p['comments'],
    'url': p['url'],
    'caption': (p['caption'] or '')[:200],
    'filename': p.get('local_filename', ''),
   }
   for i, p in enumerate(top_posts)
  ]
 })

 return scrape_result


def build_loader(quiet: bool = False, login_user: str = '', login_pass: str = ''):
 try:
  import instaloader
 except ImportError:
  import subprocess
  subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'instaloader', '-q'])
  import instaloader

 L = instaloader.Instaloader(quiet=quiet)

 # Try to load saved session file
 session_file = WORKSPACE / '.instagram_session'
 if session_file.exists() and not login_user:
  try:
   L.load_session_from_file(
    username=L.context.username or 'session_user',
    filename=str(session_file)
   )
   print(f' Loaded saved session from {session_file}')
  except Exception:
   pass

 if login_user and login_pass:
  try:
   L.login(login_user, login_pass)
   print(f' Logged in as: {login_user}')
   try:
    session_save = WORKSPACE / '.instagram_session'
    L.save_session_to_file(filename=str(session_save))
   except Exception:
    pass
   return L
  except Exception as e:
   print(f' Login failed: {e}')
   print(f' Continuing without login (may hit rate limits faster)')

 if not login_user:
  session_loaded = False
  try:
   from kaggle_secrets import UserSecretsClient
   secrets = UserSecretsClient()
   try:
    session_id = secrets.get_secret('INSTAGRAM_SESSION_ID')
    if session_id:
     ig_user = secrets.get_secret('INSTAGRAM_USER')
     L.context._session.cookies.set('sessionid', session_id, domain='.instagram.com', path='/')
     if '%3A' in session_id:
      user_id = session_id.split('%3A')[0]
      L.context._session.cookies.set('ds_user_id', user_id, domain='.instagram.com', path='/')
     L.context.username = ig_user or 'session_user'
     print(' Loaded Instagram session cookie')
     session_loaded = True
   except Exception as e:
    print(f' Session cookie method failed: {e}')

   if not session_loaded:
    try:
     ig_user = secrets.get_secret('INSTAGRAM_USER')
     ig_pass = secrets.get_secret('INSTAGRAM_PASS')
     if ig_user and ig_pass:
      L.login(ig_user, ig_pass)
      print(f' Logged in via Kaggle secrets as: {ig_user}')
      session_loaded = True
      try:
       session_save = WORKSPACE / '.instagram_session'
       L.save_session_to_file(filename=str(session_save))
      except Exception:
       pass
    except Exception as e:
     print(f' Password login failed: {e}')
  except Exception:
   pass

  if not session_loaded:
   print(' WARNING: No Instagram session. Scraping without login (may fail).')

 return L


def scrape_for_job(
 job_id: str,
 username: str,
 max_posts: int = 300,
 sort_by: str = 'likes',
 min_likes: int = 0,
) -> Dict[str, Any]:
 """Scrape Instagram profile and save to a job's references folder."""
 job_dir = JOBS_DIR / job_id
 if not job_dir.exists():
  raise FileNotFoundError(f'Job {job_id} not found')

 output_dir = job_dir / 'references' / f'instagram_{sanitize_filename(username)}'

 result = scrape_profile(
  username=username,
  output_dir=output_dir,
  max_posts=max_posts,
  sort_by=sort_by,
  min_likes=min_likes,
 )

 # Update job.json
 job_json_path = job_dir / 'metadata' / 'job.json'
 if job_json_path.exists():
  job = load_json(job_json_path)
  if 'references' not in job:
   job['references'] = {}
  job['references']['instagram'] = {
   'username': username,
   'scraped_at': now_iso(),
   'post_count': result['stats']['total_downloaded'],
   'folder': str(output_dir),
  }
  job['updated_at'] = now_iso()
  save_json(job_json_path, job)

 return result


def main() -> int:
 parser = argparse.ArgumentParser(
  description='Scrape best posts from public Instagram profiles'
 )
 sub = parser.add_subparsers(dest='cmd', required=True)

 # Scrape standalone
 s = sub.add_parser('scrape', help='Scrape a profile to a folder')
 s.add_argument('--username', required=True, help='Instagram username (without @)')
 s.add_argument('--output', default='', help='Output directory (default: ./instagram_USERNAME)')
 s.add_argument('--max-posts', type=int, default=300, help='Max posts to collect')
 s.add_argument('--sort', choices=['likes', 'engagement', 'recent', 'oldest'], default='likes')
 s.add_argument('--min-likes', type=int, default=0, help='Minimum likes filter')
 s.add_argument('--login-user', default='', help='Instagram login username')
 s.add_argument('--login-pass', default='', help='Instagram login password')

 # Scrape for a job
 j = sub.add_parser('for-job', help='Scrape a profile and save to job references')
 j.add_argument('--job-id', required=True)
 j.add_argument('--username', required=True, help='Instagram username (without @)')
 j.add_argument('--max-posts', type=int, default=300)
 j.add_argument('--sort', choices=['likes', 'engagement', 'recent', 'oldest'], default='likes')
 j.add_argument('--min-likes', type=int, default=0)

 # Quick info
 i = sub.add_parser('info', help='Get profile info without downloading')
 i.add_argument('--username', required=True)

 args = parser.parse_args()

 if args.cmd == 'scrape':
  output = Path(args.output) if args.output else Path(f'instagram_{sanitize_filename(args.username)}')
  result = scrape_profile(
   username=args.username,
   output_dir=output,
   max_posts=args.max_posts,
   sort_by=args.sort,
   min_likes=args.min_likes,
   login_user=args.login_user,
   login_pass=args.login_pass,
  )
  print(f'\n=== SCRAPE COMPLETE ===')
  print(f' Profile: @{args.username}')
  print(f' Posts collected: {result["stats"]["total_collected"]}')
  print(f' Images downloaded: {result["stats"]["total_downloaded"]}')
  print(f' Avg likes: {result["stats"]["avg_likes"]:,}')
  print(f' Output: {output}')
  return 0

 elif args.cmd == 'for-job':
  result = scrape_for_job(
   job_id=args.job_id,
   username=args.username,
   max_posts=args.max_posts,
   sort_by=args.sort,
   min_likes=args.min_likes,
  )
  print(f'\n=== SCRAPE COMPLETE ===')
  print(f' Job: {args.job_id}')
  print(f' Profile: @{args.username}')
  print(f' Posts collected: {result["stats"]["total_collected"]}')
  print(f' Images downloaded: {result["stats"]["total_downloaded"]}')
  print(f' Saved to: jobs/{args.job_id}/references/')
  return 0

 elif args.cmd == 'info':
  try:
   import instaloader
  except ImportError:
   import subprocess
   subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'instaloader', '-q'])
   import instaloader

  L = instaloader.Instaloader(quiet=True)
  profile = instaloader.Profile.from_username(L.context, args.username)

  info = {
   'username': profile.username,
   'full_name': profile.full_name,
   'biography': profile.biography,
   'followers': profile.followers,
   'following': profile.followees,
   'posts': profile.mediacount,
   'is_private': profile.is_private,
   'is_verified': profile.is_verified,
  }
  print(json.dumps(info, indent=2))
  return 0

 return 0


if __name__ == '__main__':
 raise SystemExit(main())
