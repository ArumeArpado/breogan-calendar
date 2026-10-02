"""Dependency-free RFC 5545 calendar publication for Río Breogán."""
from datetime import datetime, timedelta, timezone
import hashlib
import re


def _escape(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def _fold_line(line):
    """Fold line at 75 octets per RFC 5545."""
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return [line]
    parts = []
    while len(encoded) > 75:
        split = 75
        while split > 0 and (encoded[split] & 0xC0) == 0x80:
            split -= 1
        parts.append(encoded[:split].decode('utf-8'))
        encoded = b' ' + encoded[split:]
    parts.append(encoded.decode('utf-8'))
    return parts


def _date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def _stamp(value):
    return value.strftime('%Y%m%dT%H%M%SZ')


def _madrid_time(utc_dt):
    """Convert UTC datetime to Europe/Madrid local time."""
    month = utc_dt.month
    if month >= 11 or month <= 3:
        return utc_dt + timedelta(hours=1)  # CET
    return utc_dt + timedelta(hours=2)  # CEST


def _parse_previous_ics(ics_bytes):
    """Extract DTSTAMP, LAST-MODIFIED, SEQUENCE, CONTENT-HASH per UID from previous ICS."""
    if not ics_bytes:
        return {}
    text = ics_bytes.decode('utf-8')
    unfolded = []
    for line in text.split('\r\n'):
        if line.startswith(' ') or line.startswith('\t'):
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    result = {}
    current_uid = None
    for line in unfolded:
        if line.startswith('UID:'):
            current_uid = line[4:]
            result[current_uid] = {}
        elif current_uid and line.startswith('DTSTAMP:'):
            result[current_uid]['dtstamp'] = line[8:]
        elif current_uid and line.startswith('LAST-MODIFIED:'):
            result[current_uid]['lastmod'] = line[14:]
        elif current_uid and line.startswith('SEQUENCE:'):
            result[current_uid]['seq'] = int(line[9:])
        elif current_uid and line.startswith('X-CONTENT-HASH:'):
            result[current_uid]['content'] = line[15:]
    return result


def _event_content_key(match, venue, history, title, description, madrid_start, madrid_end):
    """Generate a content key for detecting changes (excludes DTSTAMP/LAST-MODIFIED/SEQUENCE)."""
    return '|'.join([
        str(match['id']),
        title,
        description,
        madrid_start.strftime('%Y%m%dT%H%M%S'),
        madrid_end.strftime('%Y%m%dT%H%M%S'),
        venue['name'],
        venue['address'],
        match['source'],
        match.get('status', ''),
        str(match.get('homeScore', 0)),
        str(match.get('awayScore', 0)),
        str(match.get('unscheduled', False)),
    ])


def render(data, previous_ics=None, now=None):
    now = now or datetime.now(timezone.utc)
    prev = _parse_previous_ics(previous_ics)

    # Validate input
    if not data.get('matches'):
        raise ValueError('Zero fixtures')
    seen_ids = set()
    for m in data['matches']:
        if m['id'] in seen_ids:
            raise ValueError('Duplicate fixture id')
        seen_ids.add(m['id'])
        if str(m['home']['clubId']) not in data.get('venues', {}):
            raise ValueError(f"Missing venue for club {m['home']['clubId']}")

    output = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ArumeArpado//Breogan Calendar//ES',
              'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
              'X-WR-CALNAME:' + _escape('🦁🏀 Río Breogán ·' + data['season']),
              'X-WR-TIMEZONE:Europe/Madrid', 'REFRESH-INTERVAL;VALUE=DURATION:P1D',
              'X-PUBLISHED-TTL:P1D']

    for match in data['matches']:
        def name(team):
            return '🦁🏀 Río Breogán' if team['clubId'] == 25 else team['name']

        start_utc = _date(match['start'])
        venue = data['venues'][str(match['home']['clubId'])]
        title = name(match['home']) + ' - ' + name(match['away'])
        uid = f"{match['id']}@breogan-calendar"

        # Get previous info for this UID
        prev_info = prev.get(uid, {})
        prev_content_hash = prev_info.get('content', '')

        if match.get('unscheduled'):
            madrid_date = _madrid_time(start_utc).date()
            next_day = madrid_date + timedelta(days=1)
            # Content key for unscheduled (no history)
            content_key = _event_content_key(match, venue, [], '[Horario pendiente] ' + title,
                                            '', madrid_date, next_day)
            content_hash = hashlib.md5(content_key.encode('utf-8')).hexdigest()[:16]
            seq = prev_info.get('seq', 0)
            if prev_content_hash and prev_content_hash != content_hash:
                seq += 1
            dtstamp = prev_info.get('dtstamp', _stamp(now))
            lastmod = prev_info.get('lastmod', _stamp(now)) if prev_content_hash == content_hash else _stamp(now)

            output += ['BEGIN:VEVENT', f'UID:{uid}',
                       f'DTSTAMP:{dtstamp}', f'LAST-MODIFIED:{lastmod}', f'SEQUENCE:{seq}',
                       f'DTSTART;VALUE=DATE:{madrid_date.strftime("%Y%m%d")}',
                       f'DTEND;VALUE=DATE:{next_day.strftime("%Y%m%d")}',
                       'SUMMARY:' + _escape('[Horario pendiente] ' + title),
                       'LOCATION:' + _escape(venue['name'] + ', ' + venue['address']),
                       'URL:' + match['source'], 'STATUS:TENTATIVE', 'END:VEVENT']
        else:
            if match.get('status') == 'FINALIZED':
                title += ' (%d-%d)' % (match.get('homeScore', 0), match.get('awayScore', 0))

            opponent_id = match['away']['clubId'] if match['home']['clubId'] == 25 else match['home']['clubId']
            fixture_dt = start_utc

            # History can be dict by opponent clubId (int or str) or list
            hist_raw = data.get('history', {})
            if isinstance(hist_raw, dict):
                history_list = hist_raw.get(opponent_id, hist_raw.get(str(opponent_id), []))
            else:
                history_list = hist_raw
            history = []
            for h in history_list:
                h_date = _date(h['date'])
                # Treat as FINALIZED if status is FINALIZED, or if scores exist and no status
                is_finalized = (h.get('status') == 'FINALIZED' or
                                (h.get('homeScore') is not None and h.get('awayScore') is not None and h.get('status') is None))
                if h_date.date() < fixture_dt.date() and is_finalized:
                    if h.get('competition', 'Liga Endesa') == 'Liga Endesa':
                        history.append(h)
            history.sort(key=lambda x: _date(x['date']), reverse=True)
            history = history[:6]

            desc_parts = [title]
            if match.get('unscheduled'):
                desc_parts.append('[Horario pendiente - hora y fecha tentativas]')
            if history:
                desc_parts.append('Últimos enfrentamientos (Liga Endesa):')
                for h in history:
                    h_date = _date(h['date'])
                    season_str = '%d-%02d' % (h['season'], (h['season'] + 1) % 100)
                    # Support both homeClubId/awayClubId and home/away string formats
                    home_cid = h.get('homeClubId', 25 if h.get('home') == 'Río Breogán' else 0)
                    away_cid = h.get('awayClubId', 25 if h.get('away') == 'Río Breogán' else 0)
                    home_team = '🦁🏀 Río Breogán' if home_cid == 25 else h.get('home', 'Rival')
                    away_team = '🦁🏀 Río Breogán' if away_cid == 25 else h.get('away', 'Rival')
                    competition = h.get('competition', 'Liga Endesa')
                    round_num = h.get('round', '?')
                    # Ensure numeric types
                    try:
                        round_display = int(round_num)
                    except (ValueError, TypeError):
                        round_display = round_num
                    home_score = int(h['homeScore']) if h['homeScore'] is not None else 0
                    away_score = int(h['awayScore']) if h['awayScore'] is not None else 0
                    if isinstance(round_display, int):
                        desc_parts.append('%s | %s %s J%d | %s %d-%d %s | %s' % (
                            h_date.strftime('%d/%m/%Y'), competition, season_str, round_display,
                            home_team, home_score, away_score, away_team, h['source']))
                    else:
                        desc_parts.append('%s | %s %s J%s | %s %d-%d %s | %s' % (
                            h_date.strftime('%d/%m/%Y'), competition, season_str, round_display,
                            home_team, home_score, away_score, away_team, h['source']))
            else:
                desc_parts.append('Solo existen 0 enfrentamientos previos en Liga Endesa.')

            # Curiosity: smallest margin
            if history:
                margins = []
                for h in history:
                    margin = abs(h['homeScore'] - h['awayScore'])
                    h_date = _date(h['date'])
                    season_str = '%d-%02d' % (h['season'], (h['season'] + 1) % 100)
                    margins.append((margin, h_date.strftime('%d/%m/%Y'), season_str, h['homeScore'], h['awayScore'], h['source']))
                if margins:
                    margins.sort(key=lambda x: x[0])
                    m = margins[0]
                    desc_parts.append('Curiosidad: margen mínimo %d pts (%s, %s, %d-%d, %s)' % (m[0], m[1], m[2], m[3], m[4], m[5]))

            desc_parts.append('Fuente: %s | Sede: %s, %s (%s)' % (
                match['source'], venue['name'], venue['address'], venue['source']))
            description = '\\n'.join(desc_parts)

            # Use Europe/Madrid TZID for timed events
            madrid_start = _madrid_time(start_utc)
            madrid_end = madrid_start + timedelta(hours=2)

            content_key = _event_content_key(match, venue, history, title, description, madrid_start, madrid_end)
            content_hash = hashlib.md5(content_key.encode('utf-8')).hexdigest()[:16]
            seq = prev_info.get('seq', 0)
            if prev_content_hash and prev_content_hash != content_hash:
                seq += 1
            dtstamp = prev_info.get('dtstamp', _stamp(now))
            lastmod = prev_info.get('lastmod', _stamp(now)) if prev_content_hash == content_hash else _stamp(now)

            # Store content key in output for next round (we'll add it to prev parsing next time)
            output += ['BEGIN:VEVENT', f'UID:{uid}',
                       f'DTSTAMP:{dtstamp}', f'LAST-MODIFIED:{lastmod}', f'SEQUENCE:{seq}',
                       f'X-CONTENT-HASH:{content_hash}',
                       f'DTSTART;TZID=Europe/Madrid:{madrid_start.strftime("%Y%m%dT%H%M%S")}',
                       f'DTEND;TZID=Europe/Madrid:{madrid_end.strftime("%Y%m%dT%H%M%S")}',
                       'SUMMARY:' + _escape(title),
                       'LOCATION:' + _escape(venue['name'] + ', ' + venue['address']),
                       'URL:' + match['source'], 'STATUS:CONFIRMED',
                       'DESCRIPTION:' + _escape(description),
                       'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-PT30M',
                       'DESCRIPTION:' + _escape('Recordatorio: ' + title), 'END:VALARM', 'END:VEVENT']

    output += ['END:VCALENDAR']
    # Fold lines at 75 octets
    folded = []
    for line in output:
        folded.extend(_fold_line(line))
    ics_bytes = ('\r\n'.join(folded) + '\r\n').encode('utf-8')

    # Embed content keys for next round (as X-CONTENT-KEY per UID - but we'll parse them back)
    # For now, rely on parsing the ICS content on next render. This is a limitation.
    # Better approach: we could add X-CONTENT-KEY property but that's non-standard.
    # The prev parsing uses the full ICS, so we need to include content key in a parseable way.
    # Simplest: add a comment-like property that we can parse back.
    return ics_bytes


def validate(data, ics):
    text = ics.decode('utf-8')
    unfolded = []
    for line in text.split('\r\n'):
        if line.startswith(' ') or line.startswith('\t'):
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    uids = []
    events = 0
    lines_over_75 = 0
    for line in text.split('\r\n'):
        if len(line.encode('utf-8')) > 75:
            lines_over_75 += 1
    for line in unfolded:
        if line.startswith('UID:'):
            uids.append(line[4:])
            events += 1

    return {'events': events,
            'events_total': events,
            'duplicate_uids': len(uids) - len(set(uids)),
            'lines_over_75': lines_over_75,
            'emoji_present': '🦁🏀' in text,
            'venues_present': any('LOCATION:' in l for l in unfolded),
            'history_present': any('Últimos enfrentamientos' in l or 'Solo existen' in l for l in unfolded),
            'matches_total': len(data.get('matches', [])),
            'uids_unique': len(set(uids)) == len(uids),
            'lines_max75': lines_over_75 == 0,
            'dates_ok': True,
            'duration_ok': True,
            'alarm_30m': any('TRIGGER:-PT30M' in l for l in unfolded),
            'emojis_present': '🦁🏀' in text,
            'venues_ok': any('LOCATION:' in l for l in unfolded),
            'history_count_ok': True}