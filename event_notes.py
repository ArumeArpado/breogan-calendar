"""Readable plain-text notes; the calendar engine performs TEXT escaping once."""
from datetime import datetime, timezone

NAMES = {25: 'Breogán', 8: 'Joventut', 2: 'Barça', 16: 'Zaragoza',
         591: 'Girona', 658: 'Lleida', 10: 'Manresa', 3: 'Baskonia',
         28: 'Tenerife', 657: 'Coruña', 57: 'Obradoiro', 22: 'Andorra',
         9: 'Real Madrid', 549: 'Burgos', 4: 'Bilbao', 12: 'Murcia',
         14: 'Unicaja', 13: 'Valencia'}


def date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def build_notes(data, match, venue):
    opponent = match['away'] if match['home']['clubId'] == 25 else match['home']
    history = data.get('history', [])
    if isinstance(history, dict):
        history = history.get(opponent['clubId'], history.get(str(opponent['clubId']), []))
    eligible = []
    for item in history:
        home_id = item.get('homeClubId', 25 if item['home'] == 'Río Breogán' else opponent['clubId'])
        away_id = item.get('awayClubId', 25 if item['away'] == 'Río Breogán' else opponent['clubId'])
        if {home_id, away_id} != {25, opponent['clubId']}:
            continue
        if item.get('status', 'FINALIZED') != 'FINALIZED':
            continue
        if item.get('competition', 'Liga Endesa') != 'Liga Endesa' or item.get('subphase') is not None:
            continue
        if date(item['date']).date() < date(match['start']).date():
            eligible.append(item)
    recent = sorted(eligible, key=lambda h: h['date'], reverse=True)[:6]
    source_labels = {}

    def source(label, url):
        if url not in source_labels:
            source_labels[url] = label

    def season(h):
        return '%d-%02d' % (h['season'], (h['season'] + 1) % 100)

    def result(h):
        home_id = h.get('homeClubId', 25 if h['home'] == 'Río Breogán' else opponent['clubId'])
        away_id = h.get('awayClubId', 25 if h['away'] == 'Río Breogán' else opponent['clubId'])
        return '%s %d–%d %s' % (NAMES.get(home_id, h['home']), h['homeScore'],
                                 h['awayScore'], NAMES.get(away_id, h['away']))

    location = 'Partido en casa' if match['home']['clubId'] == 25 else 'Partido fuera de casa'
    sections = ['%s · %s\n%s' % (match['competition'], data['season'], location)]
    if match.get('unscheduled'):
        sections.append('HORARIO PENDIENTE\nLa fecha es provisional. Consulta el calendario oficial antes de organizar el viaje.')
    blocks = []
    for h in recent:
        blocks.append('%s · %s\n%s' % (date(h['date']).strftime('%d/%m/%Y'), season(h), result(h)))
        source('ACB · ' + season(h), h['source'])
    heading = 'ÚLTIMOS 6 ENFRENTAMIENTOS' if len(recent) == 6 else 'ENFRENTAMIENTOS ANTERIORES (%d)' % len(recent)
    intro = 'Solo liga regular ACB.'
    if len(recent) < 6:
        intro += '\nSolo hay %d encuentros anteriores verificados en los datos consultados.' % len(recent)
    sections.append(heading + '\n' + '\n\n'.join(blocks) + '\n\n' + intro)
    if recent:
        memorable = min(recent, key=lambda h: abs(h['homeScore'] - h['awayScore']))
        margin = abs(memorable['homeScore'] - memorable['awayScore'])
        sections.append('PARTIDO PARA RECORDAR\n%s · %s\n%s\nFue el más ajustado de esta lista: %d puntos de diferencia.' %
                        (date(memorable['date']).strftime('%d/%m/%Y'), season(memorable), result(memorable), margin))
    else:
        sections.append('PARTIDO PARA RECORDAR\nNo hay un encuentro anterior verificado que destacar.')
    source('Calendario actual', match['source'])
    source('Información del pabellón', venue['source'])
    sections.append('FUENTES\n' + '\n\n'.join(label + '\n' + url for url, label in source_labels.items()))
    return '\n\n'.join(sections)
