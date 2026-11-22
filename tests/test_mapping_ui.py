import hashlib

from streamlit.testing.v1 import AppTest

from inventory_engine import inspect_inventory_file

AMBIGUOUS_CSV = (
    "Product,Product Name,Stock,Daily Sales,Unit Cost,Lead Time\n"
    "Lotion,Lotion,8,1.5,72.5,4\n"
).encode()


def _mapping_app() -> AppTest:
    report = inspect_inventory_file(AMBIGUOUS_CSV, "ambiguous.csv")
    app = AppTest.from_file("app.py", default_timeout=60)
    app.run()
    app.session_state["page"] = "Inventory"
    app.session_state["pending_mapping"] = {
        "file_data": AMBIGUOUS_CSV,
        "display_name": "ambiguous.csv",
        "sheet_name": None,
        "report": report,
    }
    app.run()
    return app


def test_ambiguous_headers_open_a_mapping_card_instead_of_an_error():
    app = _mapping_app()

    assert app.exception == []
    markup = "\n".join(block.value for block in app.markdown)
    assert "Check column mapping" in markup
    assert "Product Name" in markup
    labels = [box.label for box in app.selectbox]
    for label in ("Product", "Stock", "Daily sales", "Unit cost", "Lead time"):
        assert label in labels
    assert len(app.dataframe) == 1


def test_gemini_suggestions_require_explicit_consent():
    app = _mapping_app()

    suggest = next(button for button in app.button if button.label == "Suggest with Gemini")
    assert suggest.disabled is True

    app.checkbox[0].check().run()

    assert app.exception == []
    suggest = next(button for button in app.button if button.label == "Suggest with Gemini")
    assert suggest.disabled is False


def test_staged_gemini_suggestions_prefill_the_dropdowns_before_widgets_exist():
    report = inspect_inventory_file(AMBIGUOUS_CSV, "ambiguous.csv")
    fingerprint = hashlib.sha256(AMBIGUOUS_CSV + b"\0").hexdigest()[:12]
    app = AppTest.from_file("app.py", default_timeout=60)
    app.run()
    app.session_state["page"] = "Inventory"
    app.session_state["pending_mapping"] = {
        "file_data": AMBIGUOUS_CSV,
        "display_name": "ambiguous.csv",
        "sheet_name": None,
        "report": report,
    }
    app.session_state[f"mapping_prefill_{fingerprint}"] = {"product": "Product Name"}
    app.run()

    assert app.exception == []
    product = next(box for box in app.selectbox if box.label == "Product")
    assert product.value == "Product Name"
    assert f"mapping_prefill_{fingerprint}" not in app.session_state


def test_confirming_the_mapping_loads_the_inventory():
    app = _mapping_app()

    product = next(box for box in app.selectbox if box.label == "Product")
    product.select("Product Name")
    app.run()

    use = next(button for button in app.button if button.label == "Use this mapping")
    assert use.disabled is False
    use.click().run()

    assert app.exception == []
    assert app.session_state["page"] == "Dashboard"
    assert app.session_state["pending_mapping"] is None
    assert app.session_state["column_mapping"]["product"] == "Product Name"
    assert [product["product"] for product in app.session_state["analysis"]["products"]] == [
        "Lotion"
    ]
