"""Deep diagnostic: find ALL horizontals near table area spanning full page width."""
import fitz

doc = fitz.open("reference/benchmarkpdf.pdf")
page = doc[0]

# Search the entire table area (y=700-800) across full page width
region = fitz.Rect(0, 700, 612, 800)
print("=== ALL lines in y=[700,800] across full page ===")
l_count = 0
re_count = 0
all_horizontals = []
all_verticals = []
all_rects = []

for drawing in page.get_drawings():
    drect = fitz.Rect(drawing["rect"])
    if not region.intersects(drect):
        continue
    for item in drawing["items"]:
        if item[0] == "l":
            p1, p2 = item[1], item[2]
            dx, dy = abs(p2.x-p1.x), abs(p2.y-p1.y)
            length = (dx**2 + dy**2)**0.5
            if length < 5:
                continue
            l_count += 1
            if dy < 2:
                all_horizontals.append((p1.y, p1.x, p2.x, length))
            elif dx < 2:
                all_verticals.append((p1.x, p1.y, p2.y, length))
        elif item[0] == "re":
            r = item[1]
            w, h = abs(r.x1-r.x0), abs(r.y1-r.y0)
            if min(w, h) > 2:
                re_count += 1
                all_rects.append((r, w, h))

print(f"Line items: {l_count}")
print(f"Rectangle items: {re_count}")
print()

print(f"All horizontals ({len(all_horizontals)}):")
for y, x0, x1, length in sorted(all_horizontals, key=lambda x: x[0]):
    print(f"  y={y:.1f}  x=[{x0:.1f}, {x1:.1f}]  len={length:.1f}")

print(f"\nAll verticals ({len(all_verticals)}):")
for x, y0, y1, length in sorted(all_verticals, key=lambda x: x[0]):
    print(f"  x={x:.1f}  y=[{y0:.1f}, {y1:.1f}]  len={length:.1f}")

print(f"\nAll rectangles ({len(all_rects)}):")
for r, w, h in sorted(all_rects, key=lambda x: x[0].y0):
    orient = "H-band" if h < w/5 else ("V-band" if w < h/5 else "block")
    print(f"  ({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f}) w={w:.1f} h={h:.1f} {orient}")
