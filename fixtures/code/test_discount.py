from discount import total_after_discount


def test_percentage_discount():
    assert total_after_discount([100, 50], 0.10) == 135


def test_empty_cart():
    assert total_after_discount([], 0.10) == 0
