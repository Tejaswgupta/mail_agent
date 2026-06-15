import re

html = open('zoho_email_dump.html', encoding='utf-8').read()

# Look for titles with download
downloads = set(re.findall(r'<[^>]*title=[\'\"][^\'\"]*download[^\'\"]*[\'\"][^>]*>', html, re.IGNORECASE))
print("Downloads by title:")
for d in downloads: print(d)

print("\nDownloads by aria-label:")
aria = set(re.findall(r'<[^>]*aria-label=[\'\"][^\'\"]*download[^\'\"]*[\'\"][^>]*>', html, re.IGNORECASE))
for d in aria: print(d)

print("\nDownloads by data-action:")
actions = set(re.findall(r'<[^>]*data-action=[\'\"][^\'\"]*download[^\'\"]*[\'\"][^>]*>', html, re.IGNORECASE))
for d in actions: print(d)

