# 生成 OSD 用 8x16 ASCII 点阵字库（32..127，共 96 字），渲染 Windows 自带 Consolas
# 输出：rtl/font8x16.mem，地址 = (字符-32)*16 + 行，数据 8 位（bit7 为最左像素）
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = r"C:\Windows\Fonts\consola.ttf"


def main():
    f = ImageFont.truetype(FONT, 15)
    rows_out, preview = [], Image.new("L", (8 * 32, 16 * 3), 0)
    for code in range(32, 128):
        im = Image.new("L", (8, 16), 0)
        ch = chr(code) if code < 127 else " "
        d = ImageDraw.Draw(im)
        # 以字形包围盒水平居中，基线固定
        l, t, r, b = d.textbbox((0, 0), ch, font=f)
        x = (8 - (r - l)) // 2 - l
        d.text((x, 0), ch, font=f, fill=255)
        for y in range(16):
            v = 0
            for xx in range(8):
                if im.getpixel((xx, y)) >= 110:
                    v |= 0x80 >> xx
            rows_out.append(v)
        i = code - 32
        preview.paste(im.point(lambda p: 255 if p >= 110 else 0), ((i % 32) * 8, (i // 32) * 16))
    out = os.path.join(ROOT, "rtl", "font8x16.mem")
    with open(out, "w") as fo:
        for v in rows_out:
            fo.write(f"{v:02x}\n")
    preview.resize((8 * 32 * 3, 16 * 3 * 3), Image.NEAREST).save(os.path.join(ROOT, "docs", "font_preview.png"))
    print(out, len(rows_out))


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    sys.exit(main())
