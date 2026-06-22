from llm_translator.storage.history import Entry, HistoryStore


def test_add_and_list(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="你好", target_text="Hello", provider="deepseek-api"))
    rows = store.list(limit=10)
    assert len(rows) == 1
    assert rows[0].source_text == "你好"
    assert rows[0].target_text == "Hello"


def test_list_orders_newest_first(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="第一", target_text="first", provider="p"))
    store.add(Entry(src="auto", tgt="en", source_text="第二", target_text="second", provider="p"))
    rows = store.list(limit=10)
    assert rows[0].source_text == "第二"
    assert rows[1].source_text == "第一"


def test_search(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="你好世界", target_text="Hello world", provider="p"))
    store.add(Entry(src="auto", tgt="en", source_text="再见", target_text="Goodbye", provider="p"))
    hits = store.search("world")
    assert len(hits) == 1
    assert hits[0].target_text == "Hello world"


def test_clear(data_dir):
    store = HistoryStore()
    store.add(Entry(src="auto", tgt="en", source_text="x", target_text="y", provider="p"))
    store.clear()
    assert store.list(limit=10) == []
