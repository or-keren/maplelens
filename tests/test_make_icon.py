import importlib.util
import struct
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("make_icon", ROOT / "scripts" / "make_icon.py")
make_icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_icon)

PNG = b"\x89PNG\r\n\x1a\n"


def test_ico_entries_point_at_their_pngs():
    pngs = {16: PNG + b"a", 256: PNG + b"bbbb"}
    data = make_icon.ico_bytes(pngs)
    assert struct.unpack_from("<HHH", data) == (0, 1, 2)
    for i, size in enumerate(sorted(pngs)):
        w, h, *_, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        assert (w, h) == (size % 256, size % 256)  # 0 means 256
        assert data[offset : offset + length] == pngs[size]


def test_icns_blocks_add_up():
    data = make_icon.icns_bytes([(b"icp4", PNG + b"a"), (b"ic10", PNG + b"bb")])
    assert data[:4] == b"icns" and struct.unpack_from(">I", data, 4)[0] == len(data)
    pos, seen = 8, []
    while pos < len(data):
        seen.append(data[pos : pos + 4])
        assert data[pos + 8 : pos + 16] == PNG
        pos += struct.unpack_from(">I", data, pos + 4)[0]
    assert pos == len(data) and seen == [b"icp4", b"ic10"]
