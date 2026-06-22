import pytest
from llm_translator.storage import paths


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """把数据目录重定向到临时目录，避免污染真实用户目录。

    autouse=True：所有测试自动获得隔离，无需逐个声明 data_dir 参数。
    防止 CredentialStore/HistoryStore 测试把数据写到真实用户目录并相互污染。
    """
    monkeypatch.setattr(paths, "_data_dir", tmp_path)
    return tmp_path
