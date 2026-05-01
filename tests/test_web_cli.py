from pathlib import Path


def test_streamlit_app_file_exists() -> None:
    path = Path("src/nextinai/web/streamlit_app.py")
    assert path.exists()
