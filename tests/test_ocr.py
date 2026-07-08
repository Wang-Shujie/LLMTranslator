from llm_translator.core.ocr import OcrBlock, _polygon_to_bbox


def test_polygon_to_bbox_simple():
    poly = [[10, 20], [110, 20], [110, 50], [10, 50]]
    assert _polygon_to_bbox(poly) == (10, 20, 100, 30)


def test_polygon_to_bbox_rotated():
    poly = [[5, 5], [15, 8], [13, 18], [3, 15]]
    x, y, w, h = _polygon_to_bbox(poly)
    assert x == 3 and y == 5 and w == 12 and h == 13


def test_ocr_block_dataclass():
    b = OcrBlock(text="hello", bbox=(0, 0, 100, 20))
    assert b.text == "hello"
    assert b.bbox == (0, 0, 100, 20)
