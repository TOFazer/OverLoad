from overload.settings.store import SettingsStore
from overload.ui.theme import (
    ACCENTS,
    DEFAULT_ACCENT,
    FOREST_BRAND,
    FOREST_CHARCOAL,
    FOREST_CREAM,
    FOREST_MOSS,
    FOREST_PINE,
    FOREST_SAGE,
    build_stylesheet,
    palette,
)


def test_appearance_defaults_and_persistence(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    prefs = store.get()
    assert prefs.accent == "forest"
    assert DEFAULT_ACCENT == "forest"
    assert prefs.ui_scale == "normal"

    store.update(accent="blue", ui_scale="large")
    reloaded = SettingsStore(tmp_path / "settings.json").get()
    assert reloaded.accent == "blue"
    assert reloaded.ui_scale == "large"


def test_invalid_appearance_values_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"accent": "neon", "ui_scale": "geante"}', encoding="utf-8")
    prefs = SettingsStore(path).get()
    assert prefs.accent == "forest"
    assert prefs.ui_scale == "normal"


def test_old_default_violet_migrates_once_to_forest(tmp_path):
    path = tmp_path / "settings.json"
    # Ancien fichier (schéma 2) : le violet était l'accent par défaut.
    path.write_text('{"schema_version": 2, "accent": "violet"}', encoding="utf-8")
    assert SettingsStore(path).get().accent == "forest"

    # Après migration, un violet explicitement choisi est conservé.
    store = SettingsStore(path)
    store.update(accent="violet")
    assert SettingsStore(path).get().accent == "violet"


def test_forest_palette_matches_overx_forest_tokens():
    dark = palette("dark", "forest")
    assert dark.canvas == FOREST_PINE == "#14251B"
    assert dark.surface == FOREST_CHARCOAL == "#202722"
    assert dark.text == FOREST_CREAM == "#E8EDE5"
    assert dark.text_secondary == FOREST_SAGE == "#A8BFA5"
    assert dark.accent == FOREST_MOSS == "#52765B"
    assert ACCENTS["forest"].light == FOREST_BRAND == "#244A35"

    light = palette("light", "forest")
    assert light.theme == "light"
    assert light.text == FOREST_PINE
    assert light.accent == FOREST_BRAND


def test_palette_uses_requested_accent_and_theme():
    dark = palette("dark", "violet")
    assert dark.canvas == "#14251B"  # socle forêt commun, accent personnalisable
    assert dark.accent == ACCENTS["violet"].dark
    light = palette("light", "blue")
    assert light.theme == "light"
    assert light.accent == ACCENTS["blue"].light


def test_stylesheet_scales_with_ui_size():
    normal = build_stylesheet("dark", "forest", "normal")
    large = build_stylesheet("dark", "forest", "large")
    assert "#14251B" in normal
    assert normal != large
    assert "font-size: 15px" in large
