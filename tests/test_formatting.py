from ui.tabs.networth_tab import format_isk_short


def test_format_isk_short_scales_suffixes():
    assert format_isk_short(1_500_000_000) == "1.50b"
    assert format_isk_short(25_000_000) == "25.00m"
    assert format_isk_short(12_345) == "12.35k"
    assert format_isk_short(999) == "999"


def test_format_isk_short_signed_flag():
    assert format_isk_short(1_250, signed=True) == "+1.25k"
    assert format_isk_short(-2_500_000, signed=True) == "-2.50m"
    assert format_isk_short(0, signed=True) == "+0"
