import re, json
html = open('zoho_dump.html', encoding='utf-8').read()
m = re.search(r"(<div[^>]*role=['\"]option['\"][^>]*>.*?)(<div[^>]*role=['\"]option['\"]|</div)", html, flags=re.DOTALL)
if m:
    print("Option HTML:", m.group(1)[:1000])
