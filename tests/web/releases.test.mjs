import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  LATEST_DOWNLOAD_URL, LATEST_RELEASE_URL, RELEASE_API_URL, RELEASES_URL, updateReleaseInfo,
} from "../../site/releases.mjs";

const html = readFileSync(new URL("../../site/index.html", import.meta.url), "utf8");
const downloadTags = [...html.matchAll(/<a\b([^>]*\bdata-download="[^"]+"[^>]*)>/g)]
  .map((match) => match[1]);

// DOM minimal construit depuis les vrais attributs HTML : aucune dépendance npm
// ni accès réseau nécessaires pour tester tous les états de la page.
function createDocument() {
  const links = downloadTags.map((tag) => {
    const attribute = (name) => tag.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1];
    const label = { textContent: attribute("data-label-ready") };
    return {
      href: attribute("href"),
      dataset: {
        download: attribute("data-download"),
        labelReady: attribute("data-label-ready"),
        labelWaiting: attribute("data-label-waiting"),
      },
      label,
      querySelector: (selector) => {
        assert.equal(selector, "[data-label]");
        return label;
      },
    };
  });
  const elements = Object.fromEntries([
    "release-card", "release-version", "release-status", "release-date", "release-notes",
  ].map((id) => [id, { dataset: {}, textContent: "", hidden: true }]));
  return {
    links,
    elements,
    querySelectorAll: (selector) => {
      assert.equal(selector, "[data-download]");
      return links;
    },
    getElementById: (id) => elements[id],
  };
}

function latestRelease(overrides = {}) {
  return {
    tag_name: "v1.2.3",
    draft: false,
    prerelease: false,
    published_at: "2026-10-21T23:30:00Z",
    assets: ["OverLoad-Setup.exe", "OverLoad-Portable-win64.zip", "SHA256SUMS.txt"]
      .map((name) => ({ name, state: "uploaded", size: 1234,
        browser_download_url: "https://untrusted.example/not-used.exe" })),
    ...overrides,
  };
}

function apiResponse(release = latestRelease(), status = 200) {
  return async () => ({ ok: status === 200, status, json: async () => release });
}

function assertPermanentLinks(document) {
  for (const link of document.links) {
    assert.equal(link.href, `${LATEST_DOWNLOAD_URL}${link.dataset.download}`);
    assert.equal(link.label.textContent, link.dataset.labelReady);
  }
}

test("les liens HTML sans JavaScript ciblent latest et gardent des noms stables", () => {
  const document = createDocument();
  assert.deepEqual(document.links.map((link) => link.dataset.download), [
    "OverLoad-Setup.exe", "OverLoad-Portable-win64.zip", "SHA256SUMS.txt",
  ]);
  assertPermanentLinks(document);
  assert.match(html, /href="\.\/styles.css"/);
  assert.match(html, /src="\.\/releases.mjs"/);
  assert.match(html, /<noscript>/);
});

test("la dernière stable affiche sa version et une date UTC, sans figer les URL", async () => {
  const document = createDocument();
  let calls = 0;
  await updateReleaseInfo(document, async (url, options) => {
    calls += 1;
    assert.equal(url, RELEASE_API_URL);
    assert.equal(options.cache, "no-store");
    assert.ok(options.signal instanceof AbortSignal);
    return (await apiResponse()());
  });
  assert.equal(calls, 1);
  assert.equal(document.elements["release-card"].dataset.state, "ready");
  assert.equal(document.elements["release-version"].textContent, "v1.2.3");
  assert.equal(document.elements["release-date"].dateTime, "2026-10-21T23:30:00.000Z");
  assert.match(document.elements["release-date"].textContent, /21 octobre 2026/);
  assert.equal(document.elements["release-date"].hidden, false);
  assertPermanentLinks(document);
});

test("une nouvelle release change la version affichée, jamais les liens du site", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, apiResponse());
  const firstUrls = document.links.map((link) => link.href);
  await updateReleaseInfo(document, apiResponse(latestRelease({ tag_name: "v1.2.4" })));
  assert.equal(document.elements["release-version"].textContent, "v1.2.4");
  assert.deepEqual(document.links.map((link) => link.href), firstUrls);
});

test("sans première release, on propose la liste GitHub plutôt qu'un téléchargement 404", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, apiResponse(null, 404));
  assert.equal(document.elements["release-card"].dataset.state, "empty");
  assert.equal(document.elements["release-date"].hidden, true);
  assert.equal(document.elements["release-notes"].href, RELEASES_URL);
  for (const link of document.links) {
    assert.equal(link.href, RELEASES_URL);
    assert.equal(link.label.textContent, link.dataset.labelWaiting);
  }
});

test("une release sans fichiers est présentée comme en préparation", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, apiResponse(latestRelease({ assets: [] })));
  assert.equal(document.elements["release-card"].dataset.state, "preparing");
  assert.match(document.elements["release-status"].textContent, /pas encore disponible/);
  assert.ok(document.links.every((link) => link.href === LATEST_RELEASE_URL));
});

test("chaque téléchargement n'est proposé que si son propre fichier existe", async () => {
  const document = createDocument();
  const release = latestRelease();
  release.assets = release.assets.filter((asset) => asset.name === "OverLoad-Setup.exe");
  await updateReleaseInfo(document, apiResponse(release));
  assert.equal(document.elements["release-card"].dataset.state, "ready");
  assert.equal(document.links[0].href, `${LATEST_DOWNLOAD_URL}OverLoad-Setup.exe`);
  assert.equal(document.links[1].href, LATEST_RELEASE_URL);
  assert.equal(document.links[2].href, LATEST_RELEASE_URL);
});

test("un fichier vide ou encore en upload n'est pas proposé", async () => {
  const document = createDocument();
  const release = latestRelease();
  release.assets[0].state = "starter";
  release.assets[1].size = 0;
  await updateReleaseInfo(document, apiResponse(release));
  assert.equal(document.elements["release-card"].dataset.state, "preparing");
  assert.equal(document.links[0].href, LATEST_RELEASE_URL);
  assert.equal(document.links[1].href, LATEST_RELEASE_URL);
  assert.equal(document.links[2].href, `${LATEST_DOWNLOAD_URL}SHA256SUMS.txt`);
});

for (const status of [403, 429, 500]) {
  test(`si l'API répond ${status}, les liens directs restent utilisables`, async () => {
    const document = createDocument();
    await updateReleaseInfo(document, apiResponse(null, status));
    assert.equal(document.elements["release-card"].dataset.state, "unknown");
    assertPermanentLinks(document);
  });
}

test("une panne réseau ou un timeout ne bloque pas les liens GitHub", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, async () => { throw new DOMException("timeout", "AbortError"); });
  assert.equal(document.elements["release-card"].dataset.state, "unknown");
  assertPermanentLinks(document);
});

for (const [name, invalid] of [
  ["réponse vide", null], ["tag absent", {}],
  ["liste des fichiers absente", latestRelease({ assets: null })],
  ["brouillon", latestRelease({ draft: true })],
  ["préversion", latestRelease({ prerelease: true })],
]) {
  test(`une réponse invalide ou non stable n'est pas affichée : ${name}`, async () => {
    const document = createDocument();
    await updateReleaseInfo(document, apiResponse(invalid));
    assert.equal(document.elements["release-card"].dataset.state, "unknown");
    assertPermanentLinks(document);
  });
}

test("un JSON illisible laisse les liens permanents accessibles", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, async () => ({
    ok: true, status: 200, json: async () => { throw new SyntaxError("JSON invalide"); },
  }));
  assertPermanentLinks(document);
  assert.equal(document.elements["release-card"].dataset.state, "unknown");
});

test("une date invalide est masquée sans empêcher de télécharger", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, apiResponse(latestRelease({ published_at: "invalide" })));
  assert.equal(document.elements["release-card"].dataset.state, "ready");
  assert.equal(document.elements["release-date"].hidden, true);
  assertPermanentLinks(document);
});

test("les liens sont rétablis quand les fichiers deviennent disponibles", async () => {
  const document = createDocument();
  await updateReleaseInfo(document, apiResponse(latestRelease({ assets: [] })));
  await updateReleaseInfo(document, apiResponse());
  assert.equal(document.elements["release-card"].dataset.state, "ready");
  assertPermanentLinks(document);
});

test("les métadonnées distantes sont du texte, pas du HTML ni des URL exécutables", async () => {
  const document = createDocument();
  const tag = '<img src=x onerror="alert(1)">';
  await updateReleaseInfo(document, apiResponse(latestRelease({ tag_name: tag })));
  assert.equal(document.elements["release-version"].textContent, tag);
  assertPermanentLinks(document);
});
