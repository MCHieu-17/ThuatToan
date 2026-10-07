from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_demo_run_and_seek(monkeypatch):
    root = Path(__file__).parents[1]
    monkeypatch.chdir(root)
    app = AppTest.from_file(str(root / "app.py"), default_timeout=60).run()
    assert not app.exception
    app.checkbox[0].set_value(True).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert len(app.metric) == 12
    assert len(app.get("plotly_chart")) >= 9
    assert len(app.get("download_button")) == 3
    app.slider(key="replay_slider").set_value(3.0).run()
    assert not app.exception
    assert app.session_state["replay_clock"] == 3.0
