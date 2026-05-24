#!/usr/bin/env python3
"""X/Twitter tools: fetch tweets, extract videos, grab frames via ffmpeg."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

import requests

API_BASE = "https://api.fxtwitter.com"
FFMPEG = os.path.expanduser("~/.local/bin/ffmpeg")

def api_get(path):
    r = requests.get(f"{API_BASE}{path}", timeout=15)
    r.raise_for_status()
    return r.json()

def get_profile(handle):
    """Get user profile info."""
    return api_get(f"/2/profile/{handle}")

def get_tweets(handle, count=10):
    """Get recent tweets from a user."""
    return api_get(f"/2/profile/{handle}/statuses?count={count}")

def get_tweet(tweet_id):
    """Get a specific tweet by ID."""
    return api_get(f"/2/status/{tweet_id}")

def get_tweet_by_url(url):
    """Get tweet from an x.com or twitter.com URL."""
    parts = url.rstrip("/").split("/")
    if "status" in parts:
        idx = parts.index("status")
        if idx + 1 < len(parts):
            return get_tweet(parts[idx + 1])
    return {"error": "Could not find tweet ID in URL"}

def fetch_tweets(handle_or_url, count=10):
    """Smart fetch: handle or URL."""
    if "x.com/" in handle_or_url or "twitter.com/" in handle_or_url:
        return get_tweet_by_url(handle_or_url)
    if handle_or_url.isdigit():
        return get_tweet(handle_or_url)
    return get_tweets(handle_or_url, count)

def format_tweet(tweet, show_full=False):
    """Format a tweet for display."""
    lines = []
    lines.append(f"━━ {tweet.get('author', {}).get('name', '?')} (@{tweet.get('author', {}).get('screen_name', '?')}) ━━")
    lines.append(f"📝 {tweet.get('text', '')}")
    lines.append(f"❤️ {tweet.get('likes', 0)}  🔁 {tweet.get('reposts', 0)}  💬 {tweet.get('replies', 0)}  👁️ {tweet.get('views', 0)}")
    lines.append(f"🕐 {tweet.get('created_at', '?')}")
    
    media = tweet.get('media', {}) or {}
    if media.get('photos'):
        lines.append(f"📷 {len(media['photos'])} photo(s)")
        for p in media['photos']:
            lines.append(f"   {p.get('url', '')}")
    if media.get('videos'):
        for v in media['videos']:
            lines.append(f"🎬 Video: {v.get('url', '')}")
            if v.get('thumbnail_url'):
                lines.append(f"   Thumb: {v.get('thumbnail_url', '')}")
    if media.get('external', {}).get('type') == 'video':
        lines.append(f"🎬 External: {media['external'].get('url', '')}")
    
    if show_full and tweet.get('quote'):
        lines.append(f"── Quote ──")
        qt = tweet['quote']
        lines.append(f"{qt.get('text', '')[:200]}")
    
    lines.append(f"🔗 {tweet.get('url', '')}")
    return "\n".join(lines)

def get_video_urls(tweet_data):
    """Extract video URLs from tweet data."""
    urls = []
    status = tweet_data.get('status', tweet_data)
    media = status.get('media', {}) or {}
    
    for v in media.get('videos', []):
        if v.get('url'):
            urls.append(v['url'])
    
    ext = media.get('external', {})
    if ext and ext.get('type') == 'video' and ext.get('url'):
        urls.append(ext['url'])
    
    return urls

def extract_frames(video_url, fps=1, output_dir=None, max_frames=50):
    """Download a video and extract frames using ffmpeg."""
    if not os.path.exists(FFMPEG):
        return {"error": f"ffmpeg not found at {FFMPEG}"}
    
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="x_frames_")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Download first (some video CDNs don't like streaming probes)
    video_path = os.path.join(output_dir, "video.mp4")
    headers = {"Referer": "https://x.com/", "User-Agent": "Mozilla/5.0"}
    dl = requests.get(video_url, headers=headers, timeout=60)
    if dl.status_code != 200:
        return {"error": f"Download failed: HTTP {dl.status_code}"}
    with open(video_path, "wb") as f:
        f.write(dl.content)
    
    # Get video info
    probe = subprocess.run(
        [FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True, timeout=30
    )
    
    info = json.loads(probe.stdout) if probe.stdout else {}
    streams = info.get('streams', [])
    duration = 0
    for s in streams:
        if s.get('duration'):
            duration = max(duration, float(s['duration']))
    
    # Extract frames
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")
    
    result = subprocess.run(
        [FFMPEG, "-i", video_path, "-vf", f"fps={fps}", "-vframes", str(max_frames),
         "-q:v", "2", output_pattern, "-y"],
        capture_output=True, text=True, timeout=120
    )
    
    if result.returncode != 0:
        return {"error": f"ffmpeg failed: {result.stderr[:300]}"}
    
    frames = sorted(os.listdir(output_dir))
    
    return {
        "success": True,
        "output_dir": output_dir,
        "frames": len(frames),
        "duration_sec": duration,
        "frame_list": [f for f in frames if f.startswith("frame_")][:10],
        "size_mb": round(len(dl.content) / 1024 / 1024, 1),
        "fps": fps,
    }

def cmd_tweets(args):
    data = fetch_tweets(args.handle, args.count)
    
    if 'status' in data and data['status']:
        print(format_tweet(data['status'], show_full=args.full))
    elif 'results' in data or 'tweets' in data:
        tweets = data.get('results', data.get('tweets', []))
        print(f"📱 {len(tweets)} tweets\n")
        for i, t in enumerate(tweets):
            print(format_tweet(t, show_full=args.full))
            if i < len(tweets) - 1:
                print()
    elif 'user' in data:
        u = data['user']
        print(f"👤 {u.get('name', '?')} (@{u.get('screen_name', '?')})")
        print(f"📝 {u.get('description', '')}")
        print(f"👥 {u.get('followers', 0):,} followers · {u.get('following', 0):,} following")
        print(f"📊 {u.get('tweets', 0):,} tweets")
    else:
        print(json.dumps(data, indent=2))

def cmd_video(args):
    data = None
    if args.tweet_id.isdigit():
        data = get_tweet(args.tweet_id)
    elif "x.com/" in args.tweet_id or "twitter.com/" in args.tweet_id:
        data = get_tweet_by_url(args.tweet_id)
    else:
        print("Need a tweet ID or URL")
        return
    
    if not data or 'status' not in data:
        print("Tweet not found")
        return
    
    urls = get_video_urls(data)
    if not urls:
        print("No video found in tweet")
        print(format_tweet(data['status']))
        return
    
    print(f"Found {len(urls)} video(s):")
    for i, url in enumerate(urls):
        print(f"  [{i+1}] {url}")
    
    if not args.no_download:
        vid_url = urls[args.index - 1] if args.index <= len(urls) else urls[0]
        print(f"\nDownloading: {vid_url}")
        result = extract_frames(vid_url, fps=args.fps, max_frames=args.max_frames)
        
        if result.get('error'):
            print(f"Error: {result['error']}")
        else:
            print(f"✅ {result['frames']} frames extracted to {result['output_dir']}")
            print(f"   Duration: {result['duration_sec']:.1f}s @ {result['fps']} fps")

def main():
    parser = argparse.ArgumentParser(description="X/Twitter tools")
    sub = parser.add_subparsers(dest="command")
    
    # tweets command
    p_tweets = sub.add_parser("tweets", help="Fetch tweets")
    p_tweets.add_argument("handle", help="Twitter handle, URL, or tweet ID")
    p_tweets.add_argument("-c", "--count", type=int, default=10, help="Number of tweets")
    p_tweets.add_argument("--full", action="store_true", help="Show full details")
    
    # video command
    p_vid = sub.add_parser("video", help="Extract video frames from a tweet")
    p_vid.add_argument("tweet_id", help="Tweet ID or URL")
    p_vid.add_argument("-i", "--index", type=int, default=1, help="Video index (if multiple)")
    p_vid.add_argument("--fps", type=float, default=1, help="Frames per second")
    p_vid.add_argument("--max-frames", type=int, default=50, help="Max frames to extract")
    p_vid.add_argument("--no-download", action="store_true", help="Just show URLs, don't download")
    
    # profile command
    p_prof = sub.add_parser("profile", help="Get user profile")
    p_prof.add_argument("handle", help="Twitter handle")
    
    args = parser.parse_args()
    
    if args.command == "tweets":
        cmd_tweets(args)
    elif args.command == "video":
        cmd_video(args)
    elif args.command == "profile":
        data = api_get(f"/2/profile/{args.handle}")
        if 'user' in data:
            u = data['user']
            print(f"👤 {u.get('name', '?')} (@{u.get('screen_name', '?')})")
            print(f"📝 {u.get('description', '')}")
            print(f"👥 {u.get('followers', 0):,} followers · {u.get('following', 0):,} following")
            print(f"📊 {u.get('tweets', 0):,} tweets")
        else:
            print(json.dumps(data, indent=2))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
