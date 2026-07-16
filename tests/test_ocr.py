from llm_translator.core.ocr import OcrBlock, _polygon_to_bbox, merge_line_blocks


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


def test_merge_line_blocks_same_line():
    """同行碎片块应合并为一个（文本用空格连接，bbox 取并集）。"""
    blocks = [
        OcrBlock("Open", (10, 50, 40, 20)),
        OcrBlock("Chat", (55, 50, 35, 20)),
        OcrBlock("Window", (95, 50, 50, 20)),
    ]
    merged = merge_line_blocks(blocks)
    assert len(merged) == 1
    assert merged[0].text == "Open Chat Window"
    assert merged[0].bbox == (10, 50, 135, 20)


def test_merge_line_blocks_different_lines():
    """不同行（y 差大）不合并。"""
    blocks = [
        OcrBlock("Line 1", (10, 50, 60, 20)),
        OcrBlock("Line 2", (10, 100, 60, 20)),
    ]
    merged = merge_line_blocks(blocks)
    assert len(merged) == 2


def test_merge_line_blocks_mixed():
    """多行多块：每行内的块合并，行间分开。"""
    blocks = [
        OcrBlock("Hello", (10, 50, 40, 20)),
        OcrBlock("World", (55, 52, 40, 20)),
        OcrBlock("Foo", (10, 100, 30, 20)),
        OcrBlock("Bar", (45, 98, 30, 20)),
    ]
    merged = merge_line_blocks(blocks)
    assert len(merged) == 2
    assert merged[0].text == "Hello World"
    assert merged[1].text == "Foo Bar"


def test_merge_line_blocks_single():
    """单个块不变。"""
    blocks = [OcrBlock("Only", (0, 0, 40, 20))]
    assert merge_line_blocks(blocks) == blocks
