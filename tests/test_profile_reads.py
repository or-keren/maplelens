import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "profile_reads", Path(__file__).parent.parent / "scripts" / "profile_reads.py"
)
profile_reads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile_reads)

SCREENS = Path(__file__).parent / "fixtures" / "screens"


def test_profile_reads_prints_the_median(capsys):
    frame = SCREENS / "fullscreen_exp_a_3024x1700_100.png"
    assert profile_reads.main([str(frame), "--passes", "1"]) == 0
    out = capsys.readouterr().out
    assert "read_all ms: median" in out
    assert any(line.startswith("  R read_exp") for line in out.splitlines())
