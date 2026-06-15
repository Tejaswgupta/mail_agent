import re
html = open('zoho_dump.html', encoding='utf-8').read()
m = re.search(r"<[^>]*aria-label=[\'\"]Email listing[\'\"][^>]*>", html)
print("Tag:", m.group(0) if m else "Not found")
