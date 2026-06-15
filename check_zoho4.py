import re
html = open('zoho_dump.html', encoding='utf-8').read()
m = re.search(r"(<div[^>]*role=[\'\"]option[\'\"][^>]*>.*?)(<div[^>]*role=[\'\"]option[\'\"]|</div)", html, flags=re.DOTALL)
if m:
    with open("zoho_option_dump.html", "w", encoding="utf-8") as f:
        f.write(m.group(1))
