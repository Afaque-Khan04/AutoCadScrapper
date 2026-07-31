import fitz
doc = fitz.open(r'd:\Workspace\ACS\AutoCadScrapper\reference\benchmarkpdf.pdf')
page = doc[0]

# Find ALL horizontal/vertical lines with length > 50 in the right-side panel area
# The General Notes box is somewhere around x=950-1170, y=60-420
print('=== LONG LINES IN RIGHT PANEL (x>940, len>50) ===')
for drawing in page.get_drawings():
    for item in drawing['items']:
        if item[0] == 'l':
            p1, p2 = item[1], item[2]
            dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
            length = (dx**2 + dy**2)**0.5
            if length < 50:
                continue
            x_min = min(p1.x, p2.x)
            if x_min < 940:
                continue
            if dy < 2:
                print(f'  H: y={p1.y:.1f}  x=[{min(p1.x,p2.x):.1f}, {max(p1.x,p2.x):.1f}]  len={length:.1f}')
            elif dx < 2:
                print(f'  V: x={p1.x:.1f}  y=[{min(p1.y,p2.y):.1f}, {max(p1.y,p2.y):.1f}]  len={length:.1f}')

print()
print('=== RECTANGLES IN RIGHT PANEL (x>940, w>50 or h>50) ===')
for drawing in page.get_drawings():
    for item in drawing['items']:
        if item[0] == 're':
            r = item[1]
            if r.x0 < 940:
                continue
            w, h = r.x1 - r.x0, r.y1 - r.y0
            if w > 50 or h > 50:
                print(f'  RECT: x=[{r.x0:.1f},{r.x1:.1f}] y=[{r.y0:.1f},{r.y1:.1f}] w={w:.1f} h={h:.1f}')

print()
# Also get the title block borders (the big framing lines)
print('=== LONGEST LINES ON PAGE (len>200) ===')
for drawing in page.get_drawings():
    for item in drawing['items']:
        if item[0] == 'l':
            p1, p2 = item[1], item[2]
            dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
            length = (dx**2 + dy**2)**0.5
            if length < 200:
                continue
            if dy < 2:
                print(f'  H: y={p1.y:.1f}  x=[{min(p1.x,p2.x):.1f}, {max(p1.x,p2.x):.1f}]  len={length:.1f}')
            elif dx < 2:
                print(f'  V: x={p1.x:.1f}  y=[{min(p1.y,p2.y):.1f}, {max(p1.y,p2.y):.1f}]  len={length:.1f}')
