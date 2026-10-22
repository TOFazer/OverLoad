from overload.ui.failure_text import explain_failure


def test_failure_text_explains_http_404():
    info = explain_failure("Fichier introuvable.\nCause probable : le serveur a répondu 404.")
    assert "introuvable" in info.title.lower()
    assert "lien" in info.action.lower()


def test_failure_text_never_returns_empty_strings():
    for raw in ("", "boom", "Téléchargement interrompu.", "HTTP 403 Forbidden"):
        info = explain_failure(raw)
        assert info.title.strip()
        assert info.detail.strip()
        assert info.action.strip()
        assert "Échec" not in info.title


def test_failure_text_detects_access_and_disk_problems():
    access = explain_failure("Accès refusé à ce fichier. HTTP 403.")
    assert "refus" in access.title.lower()
    disk = explain_failure("No space left on device")
    assert "disque" in disk.title.lower()
    permission = explain_failure("PermissionError: Access is denied (WinError 5)")
    assert "écriture" in permission.title.lower()


def test_failure_text_keeps_technical_detail():
    raw = "Connexion impossible ou interrompue.\nCause probable : [Errno 111]"
    info = explain_failure(raw)
    assert raw in info.technical
    assert "Détail technique" in info.dialog_text()
