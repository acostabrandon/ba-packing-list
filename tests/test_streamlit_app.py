from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def test_existing_customer_mode_and_rep_extension_render_without_errors():
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    assert app.radio[0].value == "Customer order"
    assert [tab.label for tab in app.tabs] == ["1 · Import & review", "2 · Packing list", "3 · Client email"]

    app.radio[0].set_value("Demo / rep shipment").run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["1 · Rep & inventory", "2 · Packing list", "3 · Tracking email"]
    assert app.selectbox[0].value == "Garrett Rolfe"
    assert next(field for field in app.text_input if field.label == "Title").value == "Territory Sales Manager"
    assert next(field for field in app.text_input if field.label == "Phone").value == "(318) 676-9697"
    assert next(field for field in app.text_input if field.label == "Email").value == "garrett.rolfe@bostonaesthestics.com"
    assert next(button for button in app.get("download_button") if button.label == "Download branded packing list PDF").disabled


def test_rep_review_gate_enables_both_outputs():
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    app.radio[0].set_value("Demo / rep shipment").run()
    values = {
        "Ship date": "08/21/2026",
        "Estimated delivery": "08/24/2026",
        "Carrier": "UPS",
        "Tracking number": "1Z9999999999999999",
    }
    for label, value in values.items():
        next(field for field in app.text_input if field.label == label).set_value(value)
    for checkbox in app.checkbox:
        checkbox.set_value(True)
    app.run()
    assert not app.exception
    downloads = {button.label: button.disabled for button in app.get("download_button")}
    assert downloads["Download branded packing list PDF"] is False
    assert downloads["Download HTML email"] is False

