from streamlit.testing.v1 import AppTest


def _app() -> AppTest:
    app = AppTest.from_file("app.py", default_timeout=60)
    app.run()
    return app


def _markup(app: AppTest) -> str:
    return "\n".join(block.value for block in app.markdown)


def test_light_mode_is_the_default_and_injects_no_filter():
    app = _app()

    assert app.exception == []
    assert app.session_state["theme"] == "light"
    assert "hue-rotate(180deg)" not in _markup(app)


def test_clicking_night_mode_applies_the_dark_filter():
    app = _app()

    dark = next(button for button in app.button if button.key == "theme_dark")
    dark.click().run()

    assert app.exception == []
    assert app.session_state["theme"] == "dark"
    assert "invert(1) hue-rotate(180deg)" in _markup(app)


def test_clicking_light_mode_returns_to_light():
    app = _app()
    next(button for button in app.button if button.key == "theme_dark").click().run()

    light = next(button for button in app.button if button.key == "theme_light")
    light.click().run()

    assert app.exception == []
    assert app.session_state["theme"] == "light"
    assert "hue-rotate(180deg)" not in _markup(app)


def test_theme_survives_page_navigation():
    app = _app()
    next(button for button in app.button if button.key == "theme_dark").click().run()

    inventory = next(button for button in app.button if button.key == "nav_inventory")
    inventory.click().run()

    assert app.exception == []
    assert app.session_state["theme"] == "dark"
    assert app.session_state["page"] == "Inventory"


def test_sidebar_renders_the_fullshelf_logo_artwork():
    app = _app()

    sidebar_markup = "\n".join(block.value for block in app.sidebar.markdown)
    assert "fs-brand-logo" in sidebar_markup
    assert "FULLSHELF" in sidebar_markup
    assert "INVENTORY MANAGEMENT PLATFORM" in sidebar_markup
