// Les noms des fichiers restent constants entre les releases. GitHub résout
// « latest » au clic : aucun tag ni lien de téléchargement fourni par l'API
// n'est injecté dans la page, et aucun déploiement du site n'est nécessaire.
export const REPOSITORY_URL = "https://github.com/TOFazer/OverLoad";
export const RELEASES_URL = `${REPOSITORY_URL}/releases`;
export const LATEST_RELEASE_URL = `${RELEASES_URL}/latest`;
export const LATEST_DOWNLOAD_URL = `${LATEST_RELEASE_URL}/download/`;
export const RELEASE_API_URL = "https://api.github.com/repos/TOFazer/OverLoad/releases/latest";

function setDownloads(document, availableAssets = null, fallback = LATEST_RELEASE_URL) {
  for (const link of document.querySelectorAll("[data-download]")) {
    const available = availableAssets === null || availableAssets.has(link.dataset.download);
    link.href = available ? `${LATEST_DOWNLOAD_URL}${link.dataset.download}` : fallback;
    link.querySelector("[data-label]").textContent = available
      ? link.dataset.labelReady
      : link.dataset.labelWaiting;
  }
}

function setStatus(document, state, version, message) {
  document.getElementById("release-card").dataset.state = state;
  document.getElementById("release-version").textContent = version;
  document.getElementById("release-status").textContent = message;
}

export async function updateReleaseInfo(document = globalThis.document, fetcher = globalThis.fetch) {
  // L'API sert uniquement à enrichir l'affichage. Si elle est indisponible
  // (réseau, quota GitHub...), les liens permanents restent utilisables.
  setDownloads(document);
  const notes = document.getElementById("release-notes");
  notes.href = LATEST_RELEASE_URL;
  const date = document.getElementById("release-date");
  date.hidden = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetcher(RELEASE_API_URL, {
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (response.status === 404) {
      setStatus(document, "empty", "Première version à venir",
        "Aucune version stable n’est encore publiée. Retrouvez les prochaines versions sur GitHub.");
      setDownloads(document, new Set(), RELEASES_URL);
      notes.href = RELEASES_URL;
      return;
    }
    if (!response.ok) throw new Error(`GitHub HTTP ${response.status}`);
    const release = await response.json();
    if (!release || release.draft || release.prerelease ||
        typeof release.tag_name !== "string" || !release.tag_name ||
        !Array.isArray(release.assets)) {
      throw new Error("Réponse de release invalide");
    }
    const assets = new Set(release.assets
      .filter((asset) => asset && asset.state === "uploaded" && asset.size > 0)
      .map((asset) => asset.name));
    setDownloads(document, assets);
    if (assets.has("OverLoad-Setup.exe")) {
      setStatus(document, "ready", release.tag_name,
        "La dernière version stable est prête à télécharger.");
    } else {
      setStatus(document, "preparing", release.tag_name,
        "L’installateur de cette version n’est pas encore disponible. Consultez la release ou actualisez après la compilation.");
    }
    const publishedAt = new Date(release.published_at);
    if (typeof release.published_at === "string" && Number.isFinite(publishedAt.getTime())) {
      date.dateTime = publishedAt.toISOString();
      date.textContent = `Publiée le ${new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "long", timeZone: "UTC",
      }).format(publishedAt)}`;
      date.hidden = false;
    }
  } catch {
    setStatus(document, "unknown", "Dernière version stable",
      "Les informations de version sont momentanément indisponibles. Les liens permanents GitHub restent accessibles.");
    setDownloads(document);
  } finally {
    clearTimeout(timeout);
  }
}

if (typeof document !== "undefined") {
  void updateReleaseInfo();
}
