#!/usr/bin/env python3
"""
generate_icons.py — генерирует все PNG иконки для PWA из SVG.
Запускать один раз: python generate_icons.py
Требует: pip install cairosvg  или  pip install Pillow
"""

import os
import sys

SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'icons')

# SVG иконка VORTEX — стилизованная буква V в шестиугольнике
SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0f0f1a"/>
      <stop offset="100%" style="stop-color:#1a1a2e"/>
    </linearGradient>
    <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#4ecdc4"/>
      <stop offset="100%" style="stop-color:#44b3e8"/>
    </linearGradient>
  </defs>

  <!-- Фон -->
  <rect width="{size}" height="{size}" rx="{radius}" fill="url(#bg)"/>

  <!-- Шестиугольник -->
  <polygon
    points="{hex_points}"
    fill="none"
    stroke="url(#glow)"
    stroke-width="{stroke}"
    opacity="0.6"
  />

  <!-- Буква V -->
  <polyline
    points="{v_points}"
    fill="none"
    stroke="url(#glow)"
    stroke-width="{v_stroke}"
    stroke-linecap="round"
    stroke-linejoin="round"
  />

  <!-- Точка внизу V -->
  <circle cx="{cx}" cy="{v_bottom}" r="{dot_r}" fill="#4ecdc4"/>
</svg>'''


def make_svg(size: int) -> str:
    s = size
    cx, cy = s / 2, s / 2
    pad = s * 0.12
    r_hex = s / 2 - pad

    import math
    def hex_point(angle_deg):
        a = math.radians(angle_deg)
        return (cx + r_hex * math.cos(a), cy + r_hex * math.sin(a))

    hex_pts = " ".join(f"{hex_point(60*i - 30)[0]:.1f},{hex_point(60*i - 30)[1]:.1f}"
                       for i in range(6))

    # V: две линии от top-left и top-right сходятся внизу по центру
    v_top_y  = s * 0.25
    v_bot_y  = s * 0.72
    v_left_x = s * 0.28
    v_right_x = s * 0.72

    v_pts = f"{v_left_x:.1f},{v_top_y:.1f} {cx:.1f},{v_bot_y:.1f} {v_right_x:.1f},{v_top_y:.1f}"

    return SVG_TEMPLATE.format(
        size=s,
        radius=max(4, int(s * 0.18)),
        hex_points=hex_pts,
        stroke=max(1, s * 0.025),
        v_points=v_pts,
        v_stroke=max(2, s * 0.055),
        cx=cx,
        v_bottom=v_bot_y,
        dot_r=max(2, s * 0.04),
    )


def generate_with_cairosvg():
    import cairosvg
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for size in SIZES:
        svg_data = make_svg(size).encode()
        out_path = os.path.join(OUTPUT_DIR, f'icon-{size}.png')
        cairosvg.svg2png(bytestring=svg_data, write_to=out_path,
                         output_width=size, output_height=size)
        print(f'  ✅ icon-{size}.png')
    # Сохраняем также favicon.ico как 32x32
    svg_data = make_svg(32).encode()
    cairosvg.svg2png(bytestring=svg_data,
                     write_to=os.path.join(OUTPUT_DIR, '..', 'favicon.png'),
                     output_width=32, output_height=32)
    print('  ✅ favicon.png')


def generate_with_pillow():
    from PIL import Image, ImageDraw
    import math
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for size in SIZES:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        s = size
        cx, cy = s / 2, s / 2
        radius = max(4, int(s * 0.18))

        # Фон
        draw.rounded_rectangle([0, 0, s, s], radius=radius, fill=(10, 10, 18, 255))

        # Шестиугольник
        pad = s * 0.12
        r_hex = s / 2 - pad
        hex_pts = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            hex_pts.append((cx + r_hex * math.cos(a), cy + r_hex * math.sin(a)))
        draw.polygon(hex_pts, outline=(78, 205, 196, 100), fill=None)

        # Буква V
        v_top_y  = s * 0.25
        v_bot_y  = s * 0.72
        v_left_x = s * 0.28
        v_right_x = s * 0.72
        lw = max(2, int(s * 0.055))
        draw.line([(v_left_x, v_top_y), (cx, v_bot_y)], fill=(78, 205, 196, 255), width=lw)
        draw.line([(cx, v_bot_y), (v_right_x, v_top_y)], fill=(78, 205, 196, 255), width=lw)

        # Точка
        dot_r = max(2, int(s * 0.04))
        draw.ellipse([(cx - dot_r, v_bot_y - dot_r),
                      (cx + dot_r, v_bot_y + dot_r)], fill=(78, 205, 196, 255))

        out_path = os.path.join(OUTPUT_DIR, f'icon-{size}.png')
        img.save(out_path, 'PNG')
        print(f'  ✅ icon-{size}.png')


def generate_svg_fallback():
    """Сохраняем SVG-версии если ни cairosvg ни Pillow не доступны."""
    svg_dir = os.path.join(OUTPUT_DIR, 'svg')
    os.makedirs(svg_dir, exist_ok=True)
    for size in SIZES:
        path = os.path.join(svg_dir, f'icon-{size}.svg')
        with open(path, 'w') as f:
            f.write(make_svg(size))
        print(f'  📄 icon-{size}.svg (SVG-fallback, сконвертируй в PNG вручную)')
    print('\n  ⚠️  Установи cairosvg или Pillow для PNG: pip install cairosvg')


if __name__ == '__main__':
    print('🎨 Генерация иконок VORTEX...\n')
    try:
        import cairosvg
        print('  Используем cairosvg')
        generate_with_cairosvg()
    except ImportError:
        try:
            from PIL import Image
            print('  Используем Pillow')
            generate_with_pillow()
        except ImportError:
            print('  Ни cairosvg, ни Pillow не найдены — генерируем SVG')
            generate_svg_fallback()
            sys.exit(0)
    print('\n✅ Готово! Иконки в static/icons/')