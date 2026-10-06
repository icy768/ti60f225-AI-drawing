# 生成 raw_bin2 的 sRGB gamma 表：10 位线性值 → 8 位 sRGB（IEC 61966-2-1 编码函数，四舍五入）
# 用法：python tools/gen_gamma.py  → rtl/gamma_srgb.mem（1024 行，每行 2 位十六进制）
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def srgb8(i):
    x = i / 1023.0
    y = 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
    return min(255, int(y * 255 + 0.5))


def table():
    return [srgb8(i) for i in range(1024)]


if __name__ == "__main__":
    path = os.path.join(ROOT, "rtl", "gamma_srgb.mem")
    with open(path, "w") as f:
        f.writelines(f"{v:02x}\n" for v in table())
    print(path)
