"""Notes must remain readable after an independent iCalendar TEXT decode."""
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
import calendar_engine


def decode_text(value):
    result = []
    i = 0
    while i < len(value):
        if value[i] == '\\' and i + 1 < len(value):
            i += 1
            result.append('\n' if value[i] in 'nN' else value[i])
        else:
            result.append(value[i])
        i += 1
    return ''.join(result)


def descriptions(raw):
    unfolded = raw.decode().replace('\r\n ', '').replace('\r\n\t', '')
    events = []
    current = None
    alarm = False
    for line in unfolded.split('\r\n'):
        if line == 'BEGIN:VEVENT':
            current = {}
        elif line == 'BEGIN:VALARM':
            alarm = True
        elif line == 'END:VALARM':
            alarm = False
        elif line == 'END:VEVENT':
            events.append(current)
            current = None
        elif current is not None and not alarm and ':' in line:
            key, value = line.split(':', 1)
            current[key] = decode_text(value)
    return events


class ReadabilityTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path('data.json').read_text())
        self.now = datetime(2026, 10, 2, 18, tzinfo=timezone.utc)

    def test_real_line_breaks_and_compact_history(self):
        events = descriptions(calendar_engine.render(self.data, now=self.now))
        event = next(e for e in events if e['UID'] == '105386@breogan-calendar')
        notes = event['DESCRIPTION']
        self.assertNotIn('\\n', notes)
        self.assertNotIn('J?', notes)
        self.assertIn('\n\nÚLTIMOS 6 ENFRENTAMIENTOS\n', notes)
        self.assertIn('28/03/2026 · 2025-26\nBreogán 91–78 Manresa', notes)
        self.assertIn('\n\nPARTIDO PARA RECORDAR\n', notes)
        self.assertIn('\n\nFUENTES\n', notes)
        self.assertEqual(notes.count('https://acb.com/es/liga/calendario?temporada=90'), 1)
        self.assertNotIn('Jornada ?', notes)
        self.assertNotIn('Sede:', notes)

    def test_every_event_has_readable_notes_even_when_unscheduled(self):
        events = descriptions(calendar_engine.render(self.data, now=self.now))
        for event in events:
            notes = event.get('DESCRIPTION', '')
            self.assertIn('FUENTES\n', notes, event['UID'])
            self.assertIn('\n\n', notes, event['UID'])
            self.assertNotIn('\\n', notes, event['UID'])
            self.assertNotIn('J?', notes, event['UID'])
            self.assertIn('PARTIDO PARA RECORDAR', notes, event['UID'])

    def test_updates_preserve_identity_and_are_idempotent(self):
        old = Path('calendario.ics').read_bytes()
        new = calendar_engine.render(self.data, previous_ics=old, now=self.now)
        before = {e['UID']: e for e in descriptions(old)}
        after = {e['UID']: e for e in descriptions(new)}
        self.assertEqual(set(before), set(after))
        for uid in before:
            for key in ('SUMMARY', 'LOCATION'):
                self.assertEqual(before[uid][key], after[uid][key])
            for key in before[uid]:
                if key.startswith('DTSTART') or key.startswith('DTEND'):
                    self.assertEqual(before[uid][key], after[uid][key])
        self.assertEqual(new, calendar_engine.render(self.data, previous_ics=new, now=self.now))


if __name__ == '__main__':
    unittest.main()
