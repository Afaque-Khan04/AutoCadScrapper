import fitz
doc = fitz.open(r'd:\Workspace\AutoCadScrapper\reference\benchmarkpdf.pdf')
page = doc[0]

# Check ALL drawing types in the Insert Schedule TABLE area
# Table grid was at: x=[177.4, 364.4] y=[711.5, 795.9]
region = fitz.Rect(170, 705, 370, 800)
print('=== ALL DRAWINGS in Insert Schedule TABLE area ===')
for drawing in page.get_drawings():
    drect = fitz.Rect(drawing['rect'])
    if not region.intersects(drect):
        continue
    fill = drawing.get('fill')
    color = drawing.get('color')
    print(f'  Drawing rect=({drect.x0:.0f},{drect.y0:.0f},{drect.x1:.0f},{drect.y1:.0f}) fill={fill} color={color}')
    for item in drawing['items']:
        t = item[0]
        if t == 'l':
            p1, p2 = item[1], item[2]
            dx, dy = abs(p2.x-p1.x), abs(p2.y-p1.y)
            length = (dx**2 + dy**2)**0.5
            if length > 3:
                print(f'    line: ({p1.x:.1f},{p1.y:.1f})->({p2.x:.1f},{p2.y:.1f}) len={length:.1f}')
        elif t == 're':
            r = item[1]
            print(f'    rect: ({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f})')
        else:
            print(f'    {t}')
