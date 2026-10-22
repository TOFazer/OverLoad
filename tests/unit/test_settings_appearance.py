from overload.settings.store import SettingsStore
from overload.ui.theme import (
    ACCENTS,
    DEFAULT_ACCENT,
    FOREST_BRAND,
    FOREST_CREAM,
    FOREST_NIGHT,
    FOREST_PANEL,
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


def test_forest_palette_matches_v2_identity_tokens():
    # Identité v2.0 demandée : fond #101713, panneaux #1A261F,
    # vert forêt #315E43 (actions), vert sauge #A9C7AE (détails).
    dark = palette("dark", "forest")
    assert dark.canvas == FOREST_NIGHT == "#101713"
    assert dark.surface == FOREST_PANEL == "#1A261F"
    assert dark.text == FOREST_CREAM == "#EAF1E8"
    assert dark.text_secondary == FOREST_SAGE == "#A9C7AE"
    assert dark.accent == FOREST_BRAND == "#315E43"
    # Le texte d'accent passe par la sauge pour rester lisible sur le fond nuit.
    assert dark.accent_text == FOREST_SAGE
    assert ACCENTS["forest"].dark == FOREST_BRAND
    assert ACCENTS["forest"].light == FOREST_BRAND
    # Couleurs d'état distinctes de l'accent et entre elles.
    states = {dark.accent, dark.success, dark.warning, dark.danger, dark.info}
    assert len(states) == 5

    light = palette("light", "forest")
    assert light.theme == "light"
    assert light.text == FOREST_NIGHT
    assert light.accent == FOREST_BRAND
    assert light.accent_text == FOREST_BRAND


def test_palette_uses_requested_accent_and_theme():
    dark = palette("dark", "violet")
    assert dark.canvas == "#101713"  # socle vert-noir commun, accent personnalisable
    assert dark.accent_text == dark.accent
    assert dark.accent == ACCENTS["violet"].dark
    light = palette("light", "blue")
    assert light.theme == "light"
    assert light.accent == ACCENTS["blue"].light


def test_stylesheet_scales_with_ui_size():
    normal = build_stylesheet("dark", "forest", "normal")
    large = build_stylesheet("dark", "forest", "large")
    assert "#101713" in normal
    assert "#315E43" in normal
    assert "#A9C7AE" in normal
    assert normal != large
    assert "font-size: 15px" in large
