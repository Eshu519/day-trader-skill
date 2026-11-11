f = "tests/test_risk.py"
src = open(f, encoding="utf-8").read()
orig = src

def sub(old, new, count=1):
    global src
    assert old in src, "NOT FOUND: %r" % old[:80]
    src = src.replace(old, new, count)

# QUOTE_TIME comment
sub('QUOTE_TIME = datetime.datetime(2026, 10, 19, 14, 52, 13)   # Yahoo\'s TSLA quote 366.475, 10:52:13 New York',
    'QUOTE_TIME = datetime.datetime(2026, 10, 19, 14, 52, 13)   # Yahoo\'s TSLA quote 366.475, 10:52:13 UTC')

# pass line
sub('            self.assertIn("1 passed, 0 blocked at 2026-10-19 10:15 New York", text)',
    '            self.assertIn("1 passed, 0 blocked at 2026-10-19 10:15 IST", text)')

# entry window test
sub('''    def test_entry_window_new_york_time(self):
        cases = [("2026-10-19 09:44", "no new entries before 09:45 New York (it is 09:44)"),
                 ("2026-10-19 15:31", "no new entries after 15:30 New York (it is 15:31)"),
                 ("2026-10-19 08:00", "the market is closed (Mon 2026-10-19 08:00"),
                 ("2026-10-19 16:05", "the market is closed"),
                 ("2026-10-17 10:15", "the market is closed today (weekend"),
                 ("2026-11-26 10:15", "the market is closed today (NYSE holiday: Thanksgiving Day"),
                 ("2026-11-27 12:31", "no new entries after 12:30 New York"),
                 ("2026-11-27 13:05", "the market is closed"),
                 ("2026-11-02T14:40:00Z", "no new entries before 09:45 New York (it is 09:40)")]
        for now, want in cases:
            res = self.one(tsla(), now=now)
            self.assertIn("window: " + want, reasons(res), now)
        for now in ("2026-10-19 09:45", "2026-10-19 15:30", "2026-11-27 12:30", "2026-11-02T15:15:00Z",
                    "2026-10-30T14:40:00Z", "2026-03-09T13:50:00Z"):
            self.assertEqual(verdicts(self.one(tsla(), now=now)), ["PASS"], now)
        self.assertIn("early close", " ".join(self.one(tsla(), now="2026-11-27 12:30")["warnings"]))
        res = self.one(tsla(), now="2026-10-17 10:15", no_entries_before=None, no_entries_after=None)
        self.assertEqual(verdicts(res), ["PASS"])
        with self.assertRaises(check.RiskError):
            self.one(tsla(), no_entries_before="9.45am")''',
    '''    def test_entry_window_ist(self):
        cases = [("2026-10-19 09:29", "no new entries before 09:30 IST (it is 09:29)"),
                 ("2026-10-19 15:01", "no new entries after 15:00 IST (it is 15:01)"),
                 ("2026-10-19 08:00", "the market is closed (Mon 2026-10-19 08:00"),
                 ("2026-10-19 15:35", "the market is closed"),
                 ("2026-10-17 10:15", "the market is closed today (weekend"),
                 ("2026-11-10 10:15", "the market is closed today (NSE holiday: Diwali-Balipratipada"),
                 ("2026-11-24 10:15", "the market is closed today (NSE holiday: Prakash Gurpurb"),
                 ("2026-12-25 10:15", "the market is closed today (NSE holiday: Christmas"),
                 ("2026-11-02T03:40:00Z", "no new entries before 09:30 IST (it is 09:10)")]
        for now, want in cases:
            res = self.one(tsla(), now=now)
            self.assertIn("window: " + want, reasons(res), now)
        for now in ("2026-10-19 09:30", "2026-10-19 15:00", "2026-11-02T04:00:00Z",
                    "2026-10-30T04:40:00Z", "2026-03-09T04:20:00Z"):
            self.assertEqual(verdicts(self.one(tsla(), now=now)), ["PASS"], now)
        res = self.one(tsla(), now="2026-10-17 10:15", no_entries_before=None, no_entries_after=None)
        self.assertEqual(verdicts(res), ["PASS"])
        with self.assertRaises(check.RiskError):
            self.one(tsla(), no_entries_before="9.30am")''')

# window uses IST not the machine
sub('''    def test_the_window_uses_new_york_time_not_the_machine(self):
        self.assertEqual(check.to_eastern(at("2026-10-19 10:15")), datetime.datetime(2026, 10, 19, 10, 15))
        self.assertEqual(at("2026-10-19 10:15"), datetime.datetime(2026, 10, 19, 14, 15))
        self.assertEqual(at("2026-12-01 10:15"), datetime.datetime(2026, 12, 1, 15, 15))''',
    '''    def test_the_window_uses_ist_not_the_machine(self):
        self.assertEqual(check.to_ist(at("2026-10-19 10:15")), datetime.datetime(2026, 10, 19, 10, 15))
        self.assertEqual(at("2026-10-19 10:15"), datetime.datetime(2026, 10, 19, 4, 45))
        self.assertEqual(at("2026-12-01 10:15"), datetime.datetime(2026, 12, 1, 4, 45))''')

# catch-all renames
src = src.replace("to_eastern", "to_ist")
src = src.replace("eastern_to_utc", "ist_to_utc")
src = src.replace("NYSE", "NSE")
src = src.replace("New York", "IST")
src = src.replace("nyse.com", "nseindia.com")

assert src != orig
open(f, "w", encoding="utf-8", newline="\n").write(src)
print("test_risk.py done")
