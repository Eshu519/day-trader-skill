with open(r'tests\test_budget.py', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('"no_entries_before": "09:45", "no_entries_after": "15:30", "flat_by": "15:55"',
     '"no_entries_before": "09:30", "no_entries_after": "15:00", "flat_by": "15:25"'),
    ('"flat_by": "15:55"', '"flat_by": "15:25"'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open(r'tests\test_budget.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print('done')
