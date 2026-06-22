from llm_translator.storage import paths


def test_paths_under_data_dir(data_dir):
    assert paths.data_dir() == data_dir
    assert paths.settings_file() == data_dir / "settings.json"
    assert paths.history_file() == data_dir / "history.db"
    assert paths.secrets_file() == data_dir / "secrets.enc"


def test_ensure_data_dir_creates_directory(data_dir):
    sub = data_dir / "new_sub"
    paths.ensure_dir(sub)
    assert sub.is_dir()
