import re
import bs4

html = open('debug_no_attach_289a11eb344005092143b9ddfd2cc769.html', encoding='utf-8').read()
soup = bs4.BeautifulSoup(html, 'html.parser')

print("Looking for download elements...")
for el in soup.find_all(lambda tag: 'Download' in str(tag.get('title', ''))):
    print(f"Found element with title: {el.name} {el.attrs}")
for el in soup.find_all(lambda tag: 'download' in str(tag.get('title', '')).lower()):
    print(f"Found element with title (case-insensitive): {el.name} {el.attrs}")
