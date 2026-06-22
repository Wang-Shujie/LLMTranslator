import pytest
from llm_translator.storage import paths


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """把数据目录重定向到临时目录，避免污染真实用户目录。"""
    monkeypatch.setattr(paths, "_data_dir", tmp_path)
    return tmp_path
