import json
import unittest
from pathlib import Path
from event_notes import build_notes

class LayoutTests(unittest.TestCase):
    def test_numbered_games_with_visible_separators(self):
        data = json.loads(Path('data.json').read_text())
        match = next(m for m in data['matches'] if m['id'] == 105386)
        notes = build_notes(data, match, data['venues'][str(match['home']['clubId'])])
        self.assertIn('1. 28/03/2026 · 2025-26\nBreogán 91–78 Manresa', notes)
        self.assertIn('\n\n────────────\n\n2. ', notes)
        # Verify format: numbered games, clear separators, no literal \n
        self.assertNotIn('\\n', notes)
        self.assertIn('PARTIDO PARA RECORDAR', notes)
        self.assertIn('FUENTES', notes)

if __name__ == '__main__':
    unittest.main()