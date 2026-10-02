#!/usr/bin/env python3
"""Daily updater for Río Breogán calendar. Fetches ACB data, merges history, publishes .ics."""
import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = REPO_ROOT.parent
OUT_ICS = REPO_ROOT / 'calendario.ics'
DATA_JSON = REPO_ROOT / 'data.json'
HISTORY_JSON = PROJECT_ROOT / 'history-all.json'
VENUES_JSON = PROJECT_ROOT / 'venues.json'
ACB_HTML = PROJECT_ROOT / 'acb-calendar.html'

# Import local modules
sys.path.insert(0, str(REPO_ROOT))
import update
import calendar_engine as cal


def fetch_acb_html():
    """Fetch and cache the ACB calendar page."""
    url = 'https://acb.com/es/liga/calendario?temporada=91'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
    ACB_HTML.write_text(html)
    return html


def load_venues():
    return json.loads(VENUES_JSON.read_text())


def load_history():
    return json.loads(HISTORY_JSON.read_text())


def build_data(html):
    """Parse ACB HTML and build data dict for calendar engine."""
    data = update.parse_calendar(html)
    matches = update.extract_matches(data, 'https://acb.com/es/liga/calendario?temporada=91', 2026)
    venues = load_venues()
    history = load_history()
    return {
        'season': '2026-27',
        'fetchedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'matches': matches,
        'venues': venues,
        'history': history,
    }


def main():
    parser = argparse.ArgumentParser(description='Update Breogan calendar')
    parser.add_argument('--fetch-only', action='store_true', help='Only fetch ACB HTML, do not generate .ics')
    parser.add_argument('--validate', action='store_true', help='Validate existing .ics without regenerating')
    args = parser.parse_args()

    # Fetch latest ACB data
    html = fetch_acb_html()
    data = build_data(html)

    if args.fetch_only:
        DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f'Fetched {len(data["matches"])} matches, wrote {DATA_JSON}')
        return 0

    # Read previous ICS for stable UIDs/sequence
    previous_ics = OUT_ICS.read_bytes() if OUT_ICS.exists() else None

    # Render calendar
    now = datetime.now(timezone.utc)
    ics_bytes = cal.render(data, previous_ics=previous_ics, now=now)

    # Validate
    summary = cal.validate(data, ics_bytes)
    if summary['duplicate_uids'] > 0:
        print(f'ERROR: {summary["duplicate_uids"]} duplicate UIDs', file=sys.stderr)
        return 1
    if summary['lines_over_75'] > 0:
        print(f'ERROR: {summary["lines_over_75"]} lines exceed 75 octets', file=sys.stderr)
        return 1

    # Atomic write
    tmp = OUT_ICS.with_suffix('.ics.tmp')
    tmp.write_bytes(ics_bytes)
    tmp.replace(OUT_ICS)

    # Save data.json for reference
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    print(f'Updated {OUT_ICS} ({summary["events"]} events, seq stable)')
    print(f'Validation: {summary}')
    return 0


if __name__ == '__main__':
    sys.exit(main())