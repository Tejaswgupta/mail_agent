import re

html = open('zoho_email_dump.html', encoding='utf-8').read()

# Find the download button
# and then grab 1000 characters before it to see if the filename is there
m = re.search(r'(.{0,1000})title=[\'\"]Download[\'\"]', html)
if m:
    print("Found download button context:")
    print(m.group(1))

