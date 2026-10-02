import unittest
from pathlib import Path

class IngestionTests(unittest.TestCase):
    def test_official_stream_calendar_is_parsed(self):
        import update
        data = update.parse_calendar(Path('../acb-calendar.html').read_text())
        self.assertEqual(data['selectedFilters'], {'competition': 1, 'season': 91})
        self.assertEqual(len(data['rounds']), 34)
        matches = update.extract_matches(data, 'https://acb.com/es/liga/calendario?temporada=91', 2026)
        self.assertEqual(len(matches), 34)
        self.assertEqual(sum(m['home']['clubId'] == 25 for m in matches), 17)
        self.assertEqual(sum(m['unscheduled'] for m in matches), 1)
        self.assertEqual(matches[0]['homeScore'], 110)

if __name__ == '__main__':
    unittest.main()
