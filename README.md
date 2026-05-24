# x-tools

X/Twitter scraping tools — fetch tweets, profiles, and extract video frames via ffmpeg.

Uses the FxTwitter API (no auth required for read access).

## Usage

```bash
python3 x_tools.py tweets <handle>
python3 x_tools.py tweets <tweet_id_or_url>
python3 x_tools.py video <tweet_id_or_url>
python3 x_tools.py profile <handle>
```

## Requirements
- Python 3.8+
- ffmpeg (for video frame extraction)

