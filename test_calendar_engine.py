"""Stdlib regression tests for the calendar's publication contract."""
import importlib
import re
import unittest
from datetime import datetime, timezone

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def fixture():
    return {
        'season': '2026-27', 'fetchedAt': '2026-10-02T12:00:00Z',
        'matches': [{'id': 123, 'competition': 'Liga Endesa', 'round': 1,
                     'home': {'clubId': 25, 'name': 'Río Breogán'},
                     'away': {'clubId': 9, 'name': 'Rival'},
                     'start': '2026-10-04T17:00:00Z', 'unscheduled': False,
                     'status': 'SCHEDULED', 'homeScore': 0, 'awayScore': 0,
                     'source': 'https://acb.example/match/123'}],
        'history': [],
        'venues': {'25': {'name': 'Pazo dos Deportes', 'address': 'Lugo, España',
                          'source': 'https://acb.example/club/25'},
                   '9': {'name': 'Arena', 'address': 'Ciudad',
                         'source': 'https://acb.example/club/9'}}}


def lines(raw):
    return raw.decode('utf-8').replace('\r\n ', '').replace('\r\n\t', '').split('\r\n')


class CalendarTests(unittest.TestCase):
    def engine(self):
        return importlib.import_module('calendar_engine')

    def test_timed_event_publication(self):
        raw = self.engine().render(fixture(), now=NOW)
        text = '\n'.join(lines(raw))
        for field in ('BEGIN:VCALENDAR', 'VERSION:2.0', 'METHOD:PUBLISH',
                      'CALSCALE:GREGORIAN', 'X-WR-CALNAME:🦁🏀 Río Breogán ·2026-27',
                      'X-WR-TIMEZONE:Europe/Madrid', 'REFRESH-INTERVAL;VALUE=DURATION:P1D',
                      'X-PUBLISHED-TTL:P1D', 'SUMMARY:🦁🏀 Río Breogán - Rival',
                      'DTSTART;TZID=Europe/Madrid:20261004T190000',
                      'DTEND;TZID=Europe/Madrid:20261004T210000',
                      'DTSTAMP:20261002T120000Z', 'LAST-MODIFIED:20261002T120000Z',
                      'SEQUENCE:0', 'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-PT30M',
                      'LOCATION:Pazo dos Deportes\\, Lugo\\, España',
                      'URL:https://acb.example/match/123'):
            self.assertIn(field, text)
        self.assertIn('PRODID:', text)
        self.assertTrue(raw.endswith(b'END:VCALENDAR\r\n'))

    def test_unscheduled_all_day_event(self):
        data = fixture()
        data['matches'][0]['unscheduled'] = True
        data['matches'][0]['start'] = '2026-10-05T00:00:00Z'
        raw = self.engine().render(data, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('DTSTART;VALUE=DATE:20261005', text)
        self.assertIn('SUMMARY:[Horario pendiente] 🦁🏀 Río Breogán - Rival', text)
        self.assertIn('STATUS:TENTATIVE', text)
        self.assertNotIn('BEGIN:VALARM', text)
        self.assertNotIn('DTEND:', text)

    def test_finalized_score_in_summary(self):
        data = fixture()
        data['matches'][0]['status'] = 'FINALIZED'
        data['matches'][0]['homeScore'] = 82
        data['matches'][0]['awayScore'] = 78
        raw = self.engine().render(data, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('SUMMARY:🦁🏀 Río Breogán - Rival (82-78)', text)

    def test_scheduled_no_score_in_summary(self):
        data = fixture()
        data['matches'][0]['status'] = 'SCHEDULED'
        data['matches'][0]['homeScore'] = 0
        data['matches'][0]['awayScore'] = 0
        raw = self.engine().render(data, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('SUMMARY:🦁🏀 Río Breogán - Rival', text)
        self.assertNotIn('SUMMARY:🦁🏀 Río Breogán - Rival (0-0)', text)

    def test_validator_structural_checks(self):
        data = fixture()
        ics = self.engine().render(data, now=NOW)
        summary = self.engine().validate(data, ics)
        self.assertEqual(summary['matches_total'], 1)
        self.assertEqual(summary['events_total'], 1)
        self.assertEqual(summary['uids_unique'], True)
        self.assertEqual(summary['lines_max75'], True)
        self.assertEqual(summary['dates_ok'], True)
        self.assertEqual(summary['duration_ok'], True)
        self.assertEqual(summary['alarm_30m'], True)
        self.assertEqual(summary['emojis_present'], True)
        self.assertEqual(summary['venues_ok'], True)
        self.assertEqual(summary['history_count_ok'], True)

    def test_description_history_readable_format(self):
        """New readable format: line breaks, no J?, compact sources."""
        data = fixture()
        data['history'] = [
            {'id': 1, 'date': '2026-01-10T17:00:00Z', 'home': 'Río Breogán', 'away': 'Rival',
             'homeClubId': 25, 'awayClubId': 9, 'homeScore': 80, 'awayScore': 75,
             'season': 2025, 'source': 'https://acb.example/history/1'},
            {'id': 2, 'date': '2025-03-15T17:00:00Z', 'home': 'Rival', 'away': 'Río Breogán',
             'homeClubId': 9, 'awayClubId': 25, 'homeScore': 70, 'awayScore': 85,
             'season': 2024, 'source': 'https://acb.example/history/2'},
        ]
        raw = self.engine().render(data, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('DESCRIPTION:', text)
        self.assertIn('10/01/2026', text)  # DD/MM/YYYY format
        self.assertIn('15/03/2025', text)
        self.assertIn('80–75', text)  # en dash
        self.assertIn('70–85', text)
        self.assertIn('2025-26', text)
        self.assertIn('2024-25', text)
        self.assertNotIn('J?', text)
        self.assertIn('ENFRENTAMIENTOS ANTERIORES', text)
        self.assertIn('PARTIDO PARA RECORDAR', text)
        self.assertIn('FUENTES', text)
        # Each season URL cited once
        self.assertEqual(text.count('https://acb.example/history/1'), 1)
        self.assertEqual(text.count('https://acb.example/history/2'), 1)

    def test_uid_stable_based_on_match_id(self):
        raw = self.engine().render(fixture(), previous_ics=None, now=NOW)
        self.assertIn('UID:123@breogan-calendar', '\n'.join(lines(raw)))

    def test_away_title_with_emoji(self):
        data = fixture()
        data['matches'][0]['home'], data['matches'][0]['away'] = (
            data['matches'][0]['away'], data['matches'][0]['home'])
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        self.assertIn('SUMMARY:Rival - 🦁🏀 Río Breogán', '\n'.join(lines(raw)))

    def test_timed_event_europe_madrid_tzid(self):
        data = fixture()
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('DTSTART;TZID=Europe/Madrid:20261004T190000', text)
        self.assertIn('DTEND;TZID=Europe/Madrid:20261004T210000', text)

    def test_unscheduled_all_day_local_madrid(self):
        data = fixture()
        data['matches'][0]['unscheduled'] = True
        data['matches'][0]['start'] = '2026-10-05T00:00:00Z'
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('DTSTART;VALUE=DATE:20261005', text)
        self.assertIn('DTEND;VALUE=DATE:20261006', text)
        self.assertIn('[Horario pendiente]', text)

    def test_30min_display_alarm_timed_only(self):
        raw = self.engine().render(fixture(), previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('BEGIN:VALARM\nACTION:DISPLAY\nTRIGGER:-PT30M', text)
        self.assertIn('DESCRIPTION:Recordatorio: 🦁🏀 Río Breogán - Rival', text)

    def test_no_alarm_for_unscheduled(self):
        data = fixture()
        data['matches'][0]['unscheduled'] = True
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        self.assertNotIn('BEGIN:VALARM', '\n'.join(lines(raw)))

    def test_description_contains_history_and_source(self):
        data = fixture()
        data['history'] = {9: [{'id': 104706, 'date': '2026-04-26T10:00:00Z',
                                'home': 'Río Breogán', 'away': 'Rival',
                                'homeClubId': 25, 'awayClubId': 9,
                                'homeScore': 93, 'awayScore': 86,
                                'season': 2025, 'status': 'FINALIZED',
                                'source': 'https://acb.com/temporada=90'}]}
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('DESCRIPTION:', text)
        self.assertIn('26/04/2026', text)
        self.assertIn('2025-26', text)
        self.assertIn('93–86', text)  # en dash
        self.assertIn('temporada=90', text)
        self.assertIn('ENFRENTAMIENTOS ANTERIORES', text)
        self.assertIn('PARTIDO PARA RECORDAR', text)
        self.assertIn('FUENTES', text)

    def test_history_scarcity_honest(self):
        data = fixture()
        data['history'] = {9: []}
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('ENFRENTAMIENTOS ANTERIORES (0)', text)
        self.assertIn('Solo hay 0 encuentros anteriores verificados', text)

    def test_curiosity_from_real_history(self):
        data = fixture()
        data['history'] = {9: [{'id': 104706, 'date': '2026-04-26T10:00:00Z',
                                'home': 'Río Breogán', 'away': 'Rival',
                                'homeClubId': 25, 'awayClubId': 9,
                                'homeScore': 93, 'awayScore': 86,
                                'season': 2025, 'status': 'FINALIZED',
                                'source': 'https://acb.com/temporada=90'}]}
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('PARTIDO PARA RECORDAR', text)
        self.assertIn('26/04/2026', text)
        self.assertIn('7 puntos de diferencia', text)

    def test_cutoff_strictly_before_fixture(self):
        data = fixture()
        data['history'] = {9: [
            {'id': 999999, 'date': '2026-10-04T09:00:00Z', 'home': 'A', 'away': 'B',
             'homeClubId': 25, 'awayClubId': 9, 'homeScore': 1, 'awayScore': 1,
             'season': 2025, 'status': 'FINALIZED', 'source': 'x'},
            {'id': 999998, 'date': '2026-10-03T10:00:00Z', 'home': 'C', 'away': 'D',
             'homeClubId': 25, 'awayClubId': 9, 'homeScore': 2, 'awayScore': 2,
             'season': 2025, 'status': 'FINALIZED', 'source': 'x'},
        ]}
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertNotIn('04/10/2026', text)  # same day excluded
        self.assertIn('03/10/2026', text)      # day before included

    def test_utf8_crlf_folding_75_octets(self):
        long_venue = {'name': 'X' * 80, 'address': 'Y' * 80, 'source': 'z'}
        data = fixture()
        data['venues']['25'] = long_venue
        raw = self.engine().render(data, previous_ics=None, now=NOW)
        folded = raw.decode('utf-8')
        for line in folded.split('\r\n'):
            if line.startswith(' ') or line.startswith('\t'):
                self.assertLessEqual(len(line.encode('utf-8')), 75)

    def test_no_op_stable_uid_on_reschedule(self):
        engine = self.engine()
        ics1 = engine.render(fixture(), previous_ics=None, now=NOW)
        ics2 = engine.render(fixture(), previous_ics=ics1, now=NOW)
        self.assertEqual(ics1, ics2)

    def test_sequence_increments_on_change(self):
        engine = self.engine()
        ics1 = engine.render(fixture(), previous_ics=None, now=NOW)
        changed = fixture()
        changed['matches'][0]['homeScore'] = 111
        ics2 = engine.render(changed, previous_ics=ics1, now=NOW)
        seq1 = int(re.search(r'SEQUENCE:(\d+)', ics1.decode()).group(1))
        seq2 = int(re.search(r'SEQUENCE:(\d+)', ics2.decode()).group(1))
        self.assertEqual(seq2, seq1 + 1)

    def test_validator_counts_and_no_duplicates(self):
        engine = self.engine()
        ics = engine.render(fixture(), previous_ics=None, now=NOW)
        text = '\n'.join(lines(ics))
        summary = engine.validate(fixture(), ics)
        self.assertEqual(summary['events'], 1)
        self.assertEqual(summary['duplicate_uids'], 0)
        self.assertEqual(summary['lines_over_75'], 0)
        self.assertTrue(summary['emoji_present'])
        self.assertTrue(summary['venues_present'])
        # New format uses "ENFRENTAMIENTOS ANTERIORES" instead of "Últimos enfrentamientos"
        self.assertTrue(any('ENFRENTAMIENTOS' in l for l in lines(ics)))

    def test_validator_rejects_missing_venues(self):
        engine = self.engine()
        bad_data = fixture()
        bad_data['venues'] = {}
        with self.assertRaises(ValueError):
            engine.render(bad_data, previous_ics=None, now=NOW)

    def test_validator_rejects_zero_fixtures(self):
        engine = self.engine()
        empty = fixture()
        empty['matches'] = []
        with self.assertRaises(ValueError):
            engine.render(empty, previous_ics=None, now=NOW)

    def test_validator_rejects_duplicate_fixtures(self):
        engine = self.engine()
        dup = fixture()
        dup['matches'] = [dup['matches'][0], dup['matches'][0]]
        with self.assertRaises(ValueError):
            engine.render(dup, previous_ics=None, now=NOW)

    def test_external_parse_independent(self):
        engine = self.engine()
        ics = engine.render(fixture(), previous_ics=None, now=NOW)
        events = re.findall(rb'BEGIN:VEVENT(.*?)END:VEVENT', ics, re.DOTALL)
        self.assertEqual(len(events), 1)

    def test_metadata_headers(self):
        raw = self.engine().render(fixture(), previous_ics=None, now=NOW)
        text = '\n'.join(lines(raw))
        self.assertIn('METHOD:PUBLISH', text)
        self.assertIn('VERSION:2.0', text)
        self.assertIn('PRODID:-//ArumeArpado//Breogan Calendar//ES', text)
        self.assertIn('CALSCALE:GREGORIAN', text)
        self.assertIn('X-WR-CALNAME:🦁🏀 Río Breogán ·2026-27', text)
        self.assertIn('X-WR-TIMEZONE:Europe/Madrid', text)
        self.assertIn('REFRESH-INTERVAL;VALUE=DURATION:P1D', text)
        self.assertIn('X-PUBLISHED-TTL:P1D', text)


if __name__ == '__main__':
    unittest.main()