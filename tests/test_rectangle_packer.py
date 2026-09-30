from core.rectangle_packer import RectItem, pack_rectangles, validate_no_overlap


def test_three_l_pieces_use_99_percent_of_width():
    items = [RectItem(f"L-BK-{i}", "3238OW", "L", "BK", 23.87, 31.37) for i in range(3)]
    result = pack_rectangles(items, fabric_width=72.0, max_length=100.0, random_iterations=4)
    assert validate_no_overlap(result)
    assert result.used_length <= 31.37 + 1e-6
    row_width = sum(p.width for p in result.placements if abs(p.y) < 1e-6)
    assert abs(row_width - 71.61) < 1e-6
    assert abs(row_width / 72.0 - 0.9945833333) < 1e-6


def test_reuses_space_under_short_piece():
    items = [
        RectItem("ft-xl", "M1", "XL", "FT", 40, 20),
        RectItem("bk-xl", "M1", "XL", "BK", 40, 20),
        RectItem("sl-xs", "M1", "XS", "SL", 12, 10),
        RectItem("ft-xs", "M1", "XS", "FT", 28, 20),
        RectItem("small", "M1", "XS", "SM", 12, 10),
    ]
    result = pack_rectangles(items, fabric_width=40, max_length=100, random_iterations=8)
    assert validate_no_overlap(result)
    assert result.used_length <= 60
    assert result.efficiency > 0.80


def test_all_placements_respect_fabric_width():
    items = [RectItem(str(i), "M", "S", "P", 17, 11 + i % 3) for i in range(12)]
    result = pack_rectangles(items, fabric_width=72, max_length=200)
    assert validate_no_overlap(result)
    assert all(p.right <= 72 + 1e-9 for p in result.placements)
