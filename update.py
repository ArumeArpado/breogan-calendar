"""Public ACB calendar ingestion. No authentication or third-party dependencies."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request

BASE = Path(__file__).resolve().parent
CALENDAR = 'https://acb.com/es/liga/calendario'
BREOGAN = 25
SEASON = 2026
EDITION = 91

def parse_calendar(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    stream = ''.join(json.loads(chunk) for chunk in chunks)
    for line in stream.splitlines():
        if '"rounds":' not in line or '"teams":' not in line:
            continue
        try:
            value = json.loads(line.split(':', 1)[1])
            data = value[3]['data']
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if isinstance(data, dict) and all(k in data for k in ['rounds', 'teams', 'selectedFilters']):
            return data
    raise ValueError('ACB calendar payload missing; published calendar will not be changed')

def extract_matches(data, source, year, regular_only=False):
    teams = data['teams']
    def resolve(ref):
        team = ref if isinstance(ref, dict) else teams[int(ref.rsplit(':', 1)[1])]
        return {'clubId': team['clubId'], 'name': team['fullName']}
    competition = {1:'Liga Endesa', 2:'Copa del Rey', 3:'Supercopa Endesa'}[data['selectedFilters']['competition']]
    matches = []
    for rd in data['rounds']:
        if regular_only and rd.get('subphase') is not None:
            continue
        for match in rd['matches']:
            home, away = resolve(match['homeTeam']), resolve(match['awayTeam'])
            if BREOGAN not in (home['clubId'], away['clubId']):
                continue
            if match['seasonStartYear'] != year:
                raise ValueError('Wrong season in official payload')
            matches.append({'id':match['id'], 'competition':competition, 'round':rd['roundNumber'],
                            'home':home, 'away':away, 'start':match['startDateTime'],
                            'unscheduled':match['matchStatus'] == 'UNSCHEDULED',
                            'status':match['matchStatus'], 'homeScore':match['homeTeamScore'],
                            'awayScore':match['awayTeamScore'], 'source':source})
    return matches

def load_history(json_path):
    import json
    return json.loads(Path(json_path).read_text())

def filter_history_for_opponent(history, opponent_id, before_date):
    """Return up to 6 most recent FINALIZED regular ACB matches vs opponent strictly before before_date."""
    opp = history.get(str(opponent_id), [])
    filtered = [h for h in opp if h['status'] == 'FINALIZED' and h['date'] < before_date]
    filtered.sort(key=lambda x: x['date'], reverse=True)
    return filtered[:6]

def best_curiosity(history, opponent_id):
    """Pick the narrowest-margin FINALIZED match vs opponent as a curiosity."""
    opp = history.get(str(opponent_id), [])
    finals = [h for h in opp if h['status'] == 'FINALIZED']
    if not finals:
        return None
    best = min(finals, key=lambda h: abs(h['homeScore'] - h['awayScore']))
    return best

if __name__ == '__main__':
    raise SystemExit('Updater orchestration is not implemented yet')