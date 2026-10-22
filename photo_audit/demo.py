"""Small synthetic PNG/ZIP fixtures; never copies personal photos."""

from pathlib import Path
import struct
import zipfile
import zlib


def png(rgb):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + bytes(rgb) * 2) * 2)) + chunk(b"IEND", b""))


def make_demo(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    source, target = root / "来源导出", root / "搬家后"
    source.mkdir()
    target.mkdir()
    green, blue, orange, extra = [png(color) for color in ((30, 150, 120), (60, 100, 210), (220, 140, 40), (130, 70, 150))]
    with zipfile.ZipFile(source / "takeout-001.zip", "w") as archive:
        archive.writestr("Takeout/旅行/海边.png", green)
        archive.writestr("Takeout/家庭/生日.png", blue)
        archive.writestr("Takeout/收藏/海边副本.png", green)
        archive.writestr("Takeout/旅行/未搬走.png", orange)
        archive.writestr("Takeout/旅行/海边.png.json", '{"title":"海边.png"}')
    (target / "改过名字.png").write_bytes(green)
    (target / "生日.png").write_bytes(blue)
    (target / "生日副本.png").write_bytes(blue)
    (target / "另外拍的.png").write_bytes(extra)
    (target / "损坏示例.jpg").write_bytes(b"this is not a JPEG")
    return str(source), str(target)
