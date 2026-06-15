import re
html = open('zoho_dump.html', encoding='utf-8').read()
print("Contains 'Email listing':", 'Email listing' in html)
m = re.search(r"aria-label=['\"]Email listing['\"]", html)
print("Match aria-label:", m)
m2 = re.search(r"role=['\"]listbox['\"]", html)
print("Match role=listbox:", m2)

# Find first option
m3 = re.search(r"role=['\"]option['\"][^>]*>", html)
print("Option:", m3.group(0) if m3 else None)
