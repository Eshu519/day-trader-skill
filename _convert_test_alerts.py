f = "tests/test_alerts.py"
src = open(f, encoding="utf-8").read()
orig = src

def sub(old, new, count=1):
    global src
    assert old in src, "NOT FOUND: %r" % old[:80]
    src = src.replace(old, new, count)

# header: NSE 2026 holidays (from Groww, read 2026-11-11)
sub('''# NYSE holidays as published at https://www.nyse.com/markets/hours-calendars (read 2026-10-13)
NYSE_2026 = ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
             "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"]
NYSE_2027 = ["2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
             "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"]
EARLY = ["2026-11-27", "2026-12-24", "2027-11-26"]''',
    '''# NSE holidays as published at https://groww.in/p/nse-holidays (read 2026-11-11)
NSE_2026 = ["2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03",
            "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
            "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25"]''')

# calendar tests
sub('''    def test_holidays_match_the_published_list(self):
        self.assertEqual(sorted(alerts.NYSE_HOLIDAYS), NYSE_2026 + NYSE_2027)
        self.assertEqual(sorted(alerts.NYSE_EARLY_CLOSE), EARLY)
        for d in list(alerts.NYSE_HOLIDAYS) + list(alerts.NYSE_EARLY_CLOSE):
            self.assertLess(datetime.date.fromisoformat(d).weekday(), 5, d)

    def test_daylight_saving_switches(self):
        self.assertEqual(alerts.eastern_offset(DT(2026, 3, 8, 6, 59)), -5)
        self.assertEqual(alerts.eastern_offset(DT(2026, 3, 8, 7, 0)), -4)
        self.assertEqual(alerts.eastern_offset(DT(2026, 11, 1, 5, 59)), -4)
        self.assertEqual(alerts.eastern_offset(DT(2026, 11, 1, 6, 0)), -5)
        self.assertEqual(alerts.eastern_offset(DT(2027, 3, 14, 7, 0)), -4)

    def test_parse_now(self):
        self.assertEqual(ny("2026-10-13T09:30"), DT(2026, 10, 13, 13, 30))
        self.assertEqual(ny("2026-10-19 10:15"), DT(2026, 10, 19, 14, 15))
        self.assertEqual(ny("2026-12-01T09:30"), DT(2026, 12, 1, 14, 30))
        self.assertEqual(ny("2026-10-13T20:00:01Z"), DT(2026, 10, 13, 20, 0, 1))
        with self.assertRaises(alerts.AlertError):
            ny("tomorrow")''',
    '''    def test_holidays_match_the_published_list(self):
        self.assertEqual(sorted(alerts.NSE_HOLIDAYS), NSE_2026)
        for d in alerts.NSE_HOLIDAYS:
            self.assertLess(datetime.date.fromisoformat(d).weekday(), 5, d)

    def test_ist_is_a_fixed_offset(self):
        self.assertEqual(alerts.IST_OFFSET, datetime.timedelta(hours=5, minutes=30))
        self.assertEqual(alerts.to_ist(DT(2026, 1, 15, 15, 0)), DT(2026, 1, 15, 20, 30))
        self.assertEqual(alerts.to_ist(DT(2026, 10, 19, 14, 15)), DT(2026, 10, 19, 19, 45))
        self.assertEqual(alerts.ist_to_utc(DT(2026, 10, 19, 10, 15)), DT(2026, 10, 19, 4, 45))

    def test_parse_now(self):
        self.assertEqual(ny("2026-10-13T09:15"), DT(2026, 10, 13, 3, 45))
        self.assertEqual(ny("2026-10-19 10:15"), DT(2026, 10, 19, 4, 45))
        self.assertEqual(ny("2026-12-01T09:15"), DT(2026, 12, 1, 3, 45))
        self.assertEqual(ny("2026-10-13T20:00:01Z"), DT(2026, 10, 13, 20, 0, 1))
        with self.assertRaises(alerts.AlertError):
            ny("tomorrow")''')

# market_status test
sub('''    def test_market_status(self):
        st = alerts.market_status(ny("2026-10-13T10:00"))
        self.assertTrue(st["open"])
        self.assertFalse(alerts.market_status(ny("2026-10-13T09:29"))["open"])
        self.assertEqual(alerts.market_status(ny("2026-10-13T09:29"))["next_open"], "2026-10-13 09:30")
        after = alerts.market_status(ny("2026-10-13T16:00"))
        self.assertFalse(after["open"])
        self.assertEqual(after["next_open"], "2026-10-14 09:30")
        july = alerts.market_status(ny("2026-07-03T11:00"))
        self.assertFalse(july["open"])
        self.assertIn("Independence Day", july["reason"])
        self.assertEqual(july["next_open"], "2026-07-06 09:30")
        self.assertTrue(alerts.market_status(ny("2026-11-27T12:59"))["open"])
        self.assertFalse(alerts.market_status(ny("2026-11-27T13:00"))["open"])
        xmas = alerts.market_status(ny("2027-12-24T10:00"))
        self.assertFalse(xmas["open"])
        self.assertEqual(xmas["next_open"], "2027-12-27 09:30")
        self.assertTrue(alerts.market_status(ny("2027-12-31T10:00"))["open"])
        self.assertEqual(alerts.market_status(ny("2026-10-17T10:00"))["reason"], "weekend")
        self.assertFalse(alerts.market_status(ny("2028-03-01T10:00"))["calendar_known"])''',
    '''    def test_market_status(self):
        st = alerts.market_status(ny("2026-10-13T10:00"))
        self.assertTrue(st["open"])
        self.assertFalse(alerts.market_status(ny("2026-10-13T09:14"))["open"])
        self.assertEqual(alerts.market_status(ny("2026-10-13T09:14"))["next_open"], "2026-10-13 09:15")
        after = alerts.market_status(ny("2026-10-13T15:30"))
        self.assertFalse(after["open"])
        self.assertEqual(after["next_open"], "2026-10-14 09:15")
        diwali = alerts.market_status(ny("2026-11-10T11:00"))
        self.assertFalse(diwali["open"])
        self.assertIn("Diwali", diwali["reason"])
        self.assertEqual(diwali["next_open"], "2026-11-11 09:15")
        xmas = alerts.market_status(ny("2026-12-25T10:00"))
        self.assertFalse(xmas["open"])
        self.assertEqual(xmas["next_open"], "2026-12-28 09:15")
        self.assertTrue(alerts.market_status(ny("2026-12-24T10:00"))["open"])
        self.assertEqual(alerts.market_status(ny("2026-10-17T10:00"))["reason"], "weekend")
        self.assertFalse(alerts.market_status(ny("2028-03-01T10:00"))["calendar_known"])''')

# plan rules: flat_by now 15:25, no before_close
sub('        self.assertEqual((rules[2]["at"], rules[2]["label"], rules[2]["before_close"]), ("15:55", "flat by close", True))',
    '        self.assertEqual((rules[2]["at"], rules[2]["label"]), ("15:25", "flat by close"))')

# flat_by_close test
sub('''    def test_flat_by_close_rings_once_per_trading_day(self):
        rules = plan_rules()[2:]
        self.assertEqual(self.at("2026-10-19 15:54", rules)[0], [])
        rings, st = self.at("2026-10-19 15:55", rules)
        self.assertEqual(len(rings), 1)
        self.assertIn("Flat by close: it is 15:55 New York (set for 15:55), the market closes at 16:00", rings[0]["message"])
        self.assertIn("trader-broker flatten --symbol TSLA", rings[0]["message"])
        self.assertEqual(self.at("2026-10-19 15:59", rules, st)[0], [])
        rings, _ = self.at("2026-10-19 16:10", rules)
        self.assertIn("the market has closed", rings[0]["message"])
        self.assertEqual(self.at("2026-10-20 15:56", rules, st)[0], [])     # plan rules: their day only''',
    '''    def test_flat_by_close_rings_once_per_trading_day(self):
        rules = plan_rules()[2:]
        self.assertEqual(self.at("2026-10-19 15:24", rules)[0], [])
        rings, st = self.at("2026-10-19 15:25", rules)
        self.assertEqual(len(rings), 1)
        self.assertIn("Flat by close: it is 15:25 IST (set for 15:25), the market closes at 15:30", rings[0]["message"])
        self.assertIn("trader-broker flatten --symbol TSLA", rings[0]["message"])
        self.assertEqual(self.at("2026-10-19 15:29", rules, st)[0], [])
        rings, _ = self.at("2026-10-19 15:40", rules)
        self.assertIn("the market has closed", rings[0]["message"])
        self.assertEqual(self.at("2026-10-20 15:26", rules, st)[0], [])     # plan rules: their day only''')

# early-close test -> NSE holiday test
sub('''    def test_a_time_alert_moves_with_an_early_close(self):
        rule = [{"id": "flat", "type": "time", "at": "15:55", "label": "flat by close", "before_close": True}]
        self.assertEqual(self.at("2026-11-27 12:54", rule)[0], [])
        rings, _ = self.at("2026-11-27 12:55", rule)
        self.assertIn("set for 12:55), the market closes at 13:00", rings[0]["message"])
        plain = [{"id": "t", "type": "time", "at": "15:55", "label": "check"}]
        self.assertEqual(self.at("2026-11-27 12:55", plain)[0], [])
        self.assertEqual(self.at("2026-10-17 15:56", rule)[0], [])         # Saturday: no session
        self.assertEqual(self.at("2026-11-26 15:56", rule)[0], [])         # Thanksgiving
        rings, st = self.at("2026-12-01 15:55", rule)                      # standard time
        self.assertEqual(len(rings), 1)
        self.assertEqual(st["rung"]["flat"], "2026-12-01T20:55:00Z")''',
    '''    def test_a_time_alert_rings_on_a_trading_day_only(self):
        rule = [{"id": "flat", "type": "time", "at": "15:25", "label": "flat by close"}]
        self.assertEqual(self.at("2026-10-17 15:26", rule)[0], [])         # Saturday: no session
        self.assertEqual(self.at("2026-11-10 15:26", rule)[0], [])         # Diwali-Balipratipada
        rings, st = self.at("2026-12-01 15:25", rule)
        self.assertEqual(len(rings), 1)
        self.assertEqual(st["rung"]["flat"], "2026-12-01T09:55:00Z")''')

# CLI: reel trade
sub('''        code, text, _ = self.check("2026-10-19 15:55")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Flat by close", text)
        self.assertIn("not an order", text)
        self.assertEqual(self.check("2026-10-19 15:57")[0], 1)''',
    '''        code, text, _ = self.check("2026-10-19 15:25")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Flat by close", text)
        self.assertIn("not an order", text)
        self.assertEqual(self.check("2026-10-19 15:27")[0], 1)''')

# CLI: add --at with before-close
sub('''        code, text, _ = run(["add", "--rules", self.rules, "--at", "15:55", "--label", "flat by close",
                             "--before-close", "--symbol", "tsla"])
        self.assertEqual(code, 0)''',
    '''        code, text, _ = run(["add", "--rules", self.rules, "--at", "15:25", "--label", "flat by close",
                             "--symbol", "tsla"])
        self.assertEqual(code, 0)''')
sub('''        self.assertEqual(rules[0], {"id": "time-1555", "type": "time", "at": "15:55", "label": "flat by close",
                                    "symbol": "TSLA", "before_close": True})''',
    '''        self.assertEqual(rules[0], {"id": "time-1525", "type": "time", "at": "15:25", "label": "flat by close",
                                    "symbol": "TSLA"})''')

# clock exit codes: Christmas 2026 is a Friday NSE holiday
sub('''        code, text, _ = run(["clock", "--now", "2026-12-25T10:00"])
        self.assertEqual(code, 1)
        self.assertIn("Christmas Day", text)''',
    '''        code, text, _ = run(["clock", "--now", "2026-12-25T10:00"])
        self.assertEqual(code, 1)
        self.assertIn("Christmas", text)''')

# catch-all renames
src = src.replace("NYSE_HOLIDAYS", "NSE_HOLIDAYS")
src = src.replace("NYSE_2026", "NSE_2026")
src = src.replace("NYSE_2027", "NSE_2027")
src = src.replace("to_eastern", "to_ist")
src = src.replace("eastern_offset", "ist_offset")
src = src.replace("eastern_to_utc", "ist_to_utc")
src = src.replace("NYSE", "NSE")
src = src.replace("New York", "IST")
src = src.replace("nyse.com", "nseindia.com")

assert src != orig
open(f, "w", encoding="utf-8", newline="\n").write(src)
print("test_alerts.py done")
