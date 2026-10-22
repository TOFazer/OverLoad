"""Traduction des erreurs techniques en explications compréhensibles.

L'objectif : ne jamais afficher un simple « Échec ». Chaque incident possède un
titre lisible, une cause probable en français courant et une action concrète.
Le message technique d'origine reste disponible séparément (dialogue « Détails »).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureInfo:
    title: str
    detail: str
    action: str
    technical: str

    @property
    def summary(self) -> str:
        return f"{self.title} — {self.detail}"

    def dialog_text(self) -> str:
        return (
            f"{self.title}\n\n"
            f"{self.detail}\n\n"
            f"Que faire ?\n{self.action}\n\n"
            f"Détail technique :\n{self.technical.strip() or '—'}"
        )


def _sentence(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return cleaned
    if cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned[0].upper() + cleaned[1:]


def _parse_structured(message: str) -> tuple[str, str, str] | None:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    what = lines[0]
    cause = ""
    action = ""
    for line in lines[1:]:
        if line.startswith("Cause probable :"):
            cause = line.split(":", 1)[1].strip()
        elif line.startswith("Action :"):
            action = line.split(":", 1)[1].strip()
    if not cause and not action:
        return None
    return what, cause, action


def _match(message: str) -> FailureInfo | None:
    text = message.lower()

    def info(title: str, detail: str, action: str) -> FailureInfo:
        return FailureInfo(title, detail, action, message)

    if re.search(r"\b(401|403)\b", text) or "forbidden" in text or "accès refusé" in text:
        if "permission" in text or "access is denied" in text or "winerror 5" in text:
            return info(
                "Écriture impossible",
                "Windows refuse d'écrire dans ce dossier.",
                "Choisissez un autre dossier de destination dans les paramètres.",
            )
        return info(
            "Accès refusé par le serveur",
            "Le site exige une autorisation ou bloque les téléchargements directs.",
            "Ouvrez le lien dans votre navigateur, ou utilisez une adresse directe autorisée.",
        )
    if re.search(r"\b404\b", text) or "not found" in text or "introuvable" in text:
        return info(
            "Fichier introuvable sur le serveur",
            "Le lien a peut-être expiré ou le fichier a été déplacé.",
            "Vérifiez le lien dans votre navigateur, puis relancez avec une adresse à jour.",
        )
    if re.search(r"\b429\b", text) or "too many requests" in text:
        return info(
            "Trop de demandes envoyées",
            "Le serveur limite temporairement les téléchargements depuis votre connexion.",
            "Patientez quelques minutes puis relancez le téléchargement.",
        )
    if re.search(r"\b5\d\d\b", text):
        return info(
            "Le serveur a rencontré un problème",
            "L'erreur vient du site, pas de votre ordinateur ; elle est souvent temporaire.",
            "Relancez dans quelques minutes. La reprise automatique réessaiera si elle est active.",
        )
    if re.search(r"\b(408|409|410|416)\b", text):
        return info(
            "Le serveur n'a pas pu traiter la demande",
            "La ressource a changé ou la connexion a été interrompue côté serveur.",
            "Relancez le téléchargement. S'il échoue encore, vérifiez le lien d'origine.",
        )
    if "getaddrinfo" in text or "name or service not known" in text or "name resolution" in text:
        return info(
            "Adresse introuvable",
            "Le nom de domaine du lien n'a pas pu être résolu par le réseau.",
            "Vérifiez l'orthographe du lien et votre connexion Internet, puis réessayez.",
        )
    if "timed out" in text or "timeout" in text or "délai" in text:
        return info(
            "Le serveur ne répond pas",
            "Le délai d'attente est dépassé : le site est lent ou votre connexion est instable.",
            "Vérifiez votre connexion, puis relancez. La reprise reprendra le fichier partiel.",
        )
    if "ssl" in text or "certificate" in text or "certificat" in text:
        return info(
            "Connexion sécurisée impossible",
            "Le certificat du site n'a pas pu être vérifié.",
            "Vérifiez la date et l'heure de votre PC, puis réessayez avec un lien HTTPS valide.",
        )
    if (
        "connection reset" in text
        or "reset by peer" in text
        or "aborted" in text
        or "coupée" in text
        or "interrompu" in text
        or "remote end closed" in text
    ):
        return info(
            "Connexion interrompue",
            "Le serveur ou le réseau a coupé le transfert en cours de route.",
            "Relancez : la reprise HTTP Range continuera à partir du fichier partiel.",
        )
    if "no space" in text or "disk full" in text or "espace disque" in text:
        return info(
            "Disque plein",
            "Il n'y a plus assez d'espace libre pour terminer ce téléchargement.",
            "Libérez de l'espace sur le disque, puis relancez le téléchargement.",
        )
    if "permission" in text or "access is denied" in text or "winerror 5" in text:
        return info(
            "Écriture impossible",
            "Windows refuse d'écrire dans le dossier de destination.",
            "Choisissez un autre dossier dans les paramètres ou lancez OverLoad "
            "en tant qu'administrateur.",
        )
    if "pas accessible publiquement" in text or "accessible publiquement" in text:
        return info(
            "Fichier non public",
            "Le serveur refuse les téléchargements directs vers ce fichier.",
            "Utilisez un lien direct autorisé ; OverLoad ne contourne aucune protection d'accès.",
        )
    if "vide" in text or "empty" in text:
        return info(
            "Fichier vide",
            "Le serveur n'a envoyé aucune donnée pour ce lien.",
            "Vérifiez que le lien pointe bien vers un fichier, puis réessayez plus tard.",
        )
    if "incomplet" in text or "incomplete" in text:
        return info(
            "Fichier incomplet",
            "Le serveur a annoncé une taille différente de celle réellement reçue.",
            "Relancez le téléchargement ; la reprise récupérera les données manquantes.",
        )
    if "redirection" in text:
        return info(
            "Redirection refusée",
            "Le site renvoie vers une adresse qui n'est pas un lien HTTP(S) direct.",
            "Utilisez l'adresse finale du fichier, ou téléchargez-le depuis votre navigateur.",
        )
    if "déjà ce nom" in text or "existe déjà" in text:
        return info(
            "Un fichier porte déjà ce nom",
            "OverLoad ne remplace jamais un fichier existant sans votre accord.",
            "Choisissez de télécharger une copie (« nom (2) ») ou renommez le fichier existant.",
        )
    if "adresse" in text and ("invalide" in text or "incomplète" in text or "mal formée" in text):
        return info(
            "Lien non pris en charge",
            "OverLoad accepte les adresses HTTP(S) qui pointent directement vers un fichier.",
            "Copiez le lien direct du fichier, pas l'adresse de la page qui le contient.",
        )
    return None


def explain_failure(message: str | None) -> FailureInfo:
    """Convertit un message d'erreur en explication utilisateur structurée."""
    technical = (message or "").strip()
    if not technical:
        return FailureInfo(
            "Téléchargement interrompu",
            "Le téléchargement s'est arrêté sans message détaillé.",
            "Relancez le téléchargement. Si le problème persiste, vérifiez le lien.",
            "—",
        )

    structured = _parse_structured(technical)
    if structured is not None:
        what, cause, action = structured
        refined = _match(cause) or _match(what)
        if refined is not None:
            return FailureInfo(
                refined.title,
                refined.detail,
                _sentence(action) if action else refined.action,
                technical,
            )
        return FailureInfo(
            what.rstrip("."),
            _sentence(cause) if cause else "La cause n'a pas pu être déterminée précisément.",
            _sentence(action)
            if action
            else "Relancez le téléchargement ; si l'erreur revient, vérifiez le lien.",
            technical,
        )

    refined = _match(technical)
    if refined is not None:
        return refined

    first_line = technical.splitlines()[0].strip()
    if len(first_line) > 160:
        first_line = first_line[:157].rstrip() + "…"
    return FailureInfo(
        "Téléchargement interrompu",
        _sentence(first_line),
        "Relancez le téléchargement. Si l'erreur revient, vérifiez le lien et votre connexion.",
        technical,
    )
