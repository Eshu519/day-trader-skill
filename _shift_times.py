"""Shift all IST wall-clock times in test files by -15 minutes.

NYSE 9:30 open -> NSE 9:15 open, so every IST time in the tests moves back 15 min.
UTC stamps (with 'T' and 'Z') are left alone. Config values already updated are
left alone (they don't match the session-time patterns we shift).
"""
import re
import sys

def shift_time(h, m, s=None):
    total = h * 60 + m - 15
    if total < 0:
        total += 24 * 60
    nh, nm = divmod(total, 60)
    if s is not None:
        return "%02d:%02d:%s" % (nh, nm, s)
    return "%02d:%02d" % (nh, nm)

def shift_ampm(h, m, ampm):
    # convert to 24h, shift, convert back
    h24 = h % 12 + (12 if ampm.upper() == "PM" else 0)
    total = h24 * 60 + m - 15
    if total < 0:
        total += 24 * 60
    nh24, nm = divmod(total, 60)
    if nh24 == 0:
        nh, ap = 12, "AM"
    elif nh24 < 12:
        nh, ap = nh24, "AM"
    elif nh24 == 12:
        nh, ap = 12, "PM"
    else:
        nh, ap = nh24 - 12, "PM"
    return "%d:%02d %s" % (nh, nm, ap)

def process(path):
    src = open(path, encoding="utf-8").read()
    orig = src

    # 1. "YYYY-MM-DD HH:MM" and "YYYY-MM-DD HH:MM:SS" (space separator, not T)
    def repl_dt(m):
        date, h, mi, s = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        return "%s %s" % (date, shift_time(h, mi, s))
    src = re.sub(r'(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})(?::(\d{2}))?', repl_dt, src)

    # 2. "HH:MM AM/PM" display strings (not preceded by T or digit)
    def repl_ampm(m):
        return shift_ampm(int(m.group(1)), int(m.group(2)), m.group(3))
    src = re.sub(r'(?<![T\d])(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b', repl_ampm, src)

    # 3. bare "HH:MM" and "HH:MM:SS" (not preceded by T, digit, or date)
    def repl_bare(m):
        return shift_time(int(m.group(1)), int(m.group(2)), m.group(3))
    src = re.sub(r'(?<![T\d-])(\d{2}):(\d{2})(?::(\d{2}))?(?![\dZ])', repl_bare, src)

    if src != orig:
        open(path, "w", encoding="utf-8", newline="\n").write(src)
        print("shifted", path)
    else:
        print("no change", path)

for f in sys.argv[1:]:
    process(f)
