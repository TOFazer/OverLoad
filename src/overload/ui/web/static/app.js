(() => {
  "use strict";

  const state = {
    filter: "all",
    historyQuery: "",
    historyStatus: "all",
    speedHistory: new Array(36).fill(0),
    demoPresets: null,
    pendingDuplicatePayload: null,
    settingsSyncedOnce: false,
  };

  const $ = (id) => document.getElementById(id);

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showToast(message, kind = "info") {
    const stack = $("toast-stack");
    const el = document.createElement("div");
    el.className = `toast ${kind === "error" ? "toast-error" : kind === "ok" ? "toast-ok" : ""}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  async function api(path, options = {}) {
    const init = {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
    };
    if (options.body !== undefined) {
      init.body = JSON.stringify(options.body);
    }
    const res = await fetch(path, init);
    const data = await res.json().catch(() => ({}));
    if (res.status === 409 && data.conflict) {
      const err = new Error(data.error || "Doublon détecté");
      err.conflict = true;
      err.duplicate = data.duplicate;
      throw err;
    }
    if (!res.ok) {
      const detail = [data.error, data.cause].filter(Boolean).join(" — ");
      throw new Error(detail || `Erreur HTTP ${res.status}`);
    }
    return data;
  }

  function renderSparkline(samples) {
    const w = 120;
    const h = 32;
    const maxVal = Math.max(...samples, 1024);
    const pts = samples.map((v, idx) => {
      const x = (idx / (samples.length - 1)) * w;
      const y = h - 3 - (Math.min(v, maxVal) / maxVal) * (h - 6);
      return [x, y];
    });
    const lineD = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const areaD = `${lineD} L${w},${h} L0,${h} Z`;
    $("sparkline-line").setAttribute("d", lineD);
    $("sparkline-area").setAttribute("d", areaD);
  }

  function stateLabel(task) {
    if (task.retrying) {
      return { text: `Reprise auto ${task.retry_count}/${task.max_retries}`, cls: "badge-retrying" };
    }
    switch (task.state) {
      case "running":
        return { text: "En cours", cls: "badge-running" };
      case "paused":
        return { text: "En pause", cls: "badge-paused" };
      case "queued":
        return { text: "En attente", cls: "badge-queued" };
      case "finalizing":
        return { text: "Vérification…", cls: "badge-running" };
      case "completed":
        return { text: "Terminé", cls: "badge-completed" };
      case "failed":
        return { text: "Échec", cls: "badge-failed" };
      case "cancelled":
        return { text: "Annulé", cls: "badge-queued" };
      default:
        return { text: task.state, cls: "badge-queued" };
    }
  }

  function buildTaskHtml(task) {
    const badge = stateLabel(task);
    const pct = task.progress_percent ?? 0;
    const pctText = task.progress_percent !== null ? `${task.progress_percent.toFixed(1)} %` : "Taille en cours…";
    const fillCls =
      task.state === "completed"
        ? "is-completed"
        : task.state === "paused"
          ? "is-paused"
          : task.state === "failed"
            ? "is-failed"
            : "";

    let actions = "";
    if (task.state === "running" || task.state === "queued") {
      actions += `<button type="button" class="btn btn-secondary btn-compact" data-action="pause" data-id="${task.id}">⏸ Pause</button>`;
      actions += `<button type="button" class="btn btn-ghost btn-compact" data-action="cancel" data-id="${task.id}">✕ Annuler</button>`;
    } else if (task.state === "paused") {
      actions += `<button type="button" class="btn btn-primary btn-compact" data-action="resume" data-id="${task.id}">▶ Reprendre</button>`;
      actions += `<button type="button" class="btn btn-ghost btn-compact" data-action="cancel" data-id="${task.id}">✕ Annuler</button>`;
    } else if (task.state === "failed" || task.state === "cancelled") {
      actions += `<button type="button" class="btn btn-primary btn-compact" data-action="retry" data-id="${task.id}">↻ Relancer</button>`;
      actions += `<button type="button" class="btn btn-ghost btn-compact" data-action="remove" data-id="${task.id}">Retirer</button>`;
    } else if (task.state === "completed") {
      actions += `<button type="button" class="btn btn-secondary btn-compact" data-action="open-task-folder" data-id="${task.id}">📁 Ouvrir le dossier</button>`;
      actions += `<button type="button" class="btn btn-ghost btn-compact" data-action="remove" data-id="${task.id}">Retirer</button>`;
    }

    const resumedPill = task.resumed_from_part
      ? `<span class="badge badge-paused">Reprise HTTP Range</span>`
      : "";

    let alertBox = "";
    if (task.state === "failed" && task.error_message) {
      alertBox = `<div class="issue-banner is-error">⚠ ${escapeHtml(task.error_message)}</div>`;
    } else if (task.active_warning) {
      alertBox = `<div class="issue-banner">⚡ ${escapeHtml(task.active_warning)}</div>`;
    } else if (task.issues && task.issues.length > 0 && task.state === "completed") {
      alertBox = `<div class="issue-banner">✓ Terminé avec succès après ${task.retry_count} reprise(s) automatique(s).</div>`;
    }

    const etaDisplay =
      task.state === "completed"
        ? "Terminé"
        : task.state === "paused"
          ? "Suspendu"
          : task.eta_human;

    return `
      <div class="task-top">
        <div class="task-title-wrap">
          <div class="task-title-line">
            <span class="task-filename">${escapeHtml(task.filename)}</span>
            <span class="badge ${badge.cls}">${escapeHtml(badge.text)}</span>
            ${resumedPill}
          </div>
          <div class="task-url" title="${escapeHtml(task.url)}">${escapeHtml(task.url)}</div>
          ${task.provider === "youtube" ? `<div class="task-provider">▶ YouTube · qualité ${escapeHtml(task.quality === "best" ? "meilleure disponible" : task.quality)}${task.media_title ? ` · ${escapeHtml(task.media_title)}` : ""}</div>` : ""}
        </div>
        <div class="task-actions">${actions}</div>
      </div>
      <div class="progress-track">
        <div class="progress-fill ${fillCls}" style="width: ${Math.max(pct, task.state === "running" ? 2 : 0)}%"></div>
      </div>
      <div class="task-metrics tabular">
        <div>
          <span class="metric-strong">${escapeHtml(task.downloaded_human)}</span>
          <span> / ${escapeHtml(task.total_human)} (${pctText})</span>
        </div>
        <div class="task-metrics-right">
          <span>Vitesse : <strong class="metric-strong">${escapeHtml(task.speed_human)}</strong></span>
          <span>Temps restant : <strong class="metric-strong">${escapeHtml(etaDisplay)}</strong></span>
        </div>
      </div>
      ${alertBox}
    `;
  }

  function reconcileTasks(tasks) {
    const filtered = tasks.filter((t) => {
      if (state.filter === "all") return true;
      if (state.filter === "failed") return t.state === "failed" || t.retrying || t.stalled;
      return t.state === state.filter;
    });

    $("tasks-empty").classList.toggle("hidden", filtered.length > 0);
    const container = $("tasks-list");
    const wantedIds = new Set(filtered.map((t) => t.id));

    for (const child of Array.from(container.children)) {
      if (!wantedIds.has(child.dataset.taskId)) {
        child.remove();
      }
    }

    filtered.forEach((task, idx) => {
      let card = container.querySelector(`[data-task-id="${task.id}"]`);
      const html = buildTaskHtml(task);
      if (!card) {
        card = document.createElement("div");
        card.className = "task-card";
        card.dataset.taskId = task.id;
        card.innerHTML = html;
        container.insertBefore(card, container.children[idx] || null);
      } else if (card.dataset.sig !== html) {
        card.innerHTML = html;
      }
      card.dataset.sig = html;
    });
  }

  function renderHistory(items) {
    const q = state.historyQuery.trim().toLowerCase();
    const filtered = items.filter((entry) => {
      if (state.historyStatus !== "all" && entry.status !== state.historyStatus) return false;
      if (!q) return true;
      return (
        entry.filename.toLowerCase().includes(q) || entry.url.toLowerCase().includes(q)
      );
    });

    $("history-count-badge").textContent = String(filtered.length);
    $("history-empty").classList.toggle("hidden", filtered.length > 0);

    const container = $("history-list");
    const html = filtered
      .map((entry) => {
        const statusBadge =
          entry.status === "completed"
            ? `<span class="badge badge-completed">Terminé</span>`
            : entry.status === "failed"
              ? `<span class="badge badge-failed">Échec</span>`
              : `<span class="badge badge-queued">Annulé</span>`;
        const presence =
          entry.status === "completed"
            ? entry.file_exists
              ? `<span>✓ Fichier présent (${escapeHtml(entry.size_human)})</span>`
              : `<span>⚠ Fichier déplacé ou supprimé</span>`
            : entry.error_message
              ? `<span>${escapeHtml(entry.error_message.split("\n")[0])}</span>`
              : "";
        const retriesInfo =
          entry.retries_used > 0 ? `<span>↻ ${entry.retries_used} reprise(s) auto</span>` : "";

        return `
          <div class="history-row">
            <div class="history-info">
              <div class="task-title-line">
                <strong class="task-filename">${escapeHtml(entry.filename)}</strong>
                ${statusBadge}
              </div>
              <div class="history-meta tabular">
                ${presence}
                <span> Débit moyen : ${escapeHtml(entry.average_speed_human)}</span>
                <span>Durée : ${escapeHtml(entry.duration_human)}</span>
                ${retriesInfo}
              </div>
            </div>
            <div class="task-actions">
              <button type="button" class="btn btn-secondary btn-compact" data-action="open-history-folder" data-id="${entry.id}">
                📁 Rouvrir le dossier
              </button>
              <button type="button" class="btn btn-ghost btn-compact" data-action="redownload" data-url="${escapeHtml(entry.url)}">
                ↻ Retélécharger
              </button>
              <button type="button" class="btn btn-ghost btn-compact" data-action="delete-history" data-id="${entry.id}" title="Retirer de l'historique">
                ✕
              </button>
            </div>
          </div>
        `;
      })
      .join("");

    if (container.dataset.sig !== html) {
      container.innerHTML = html;
      container.dataset.sig = html;
    }
  }

  function syncSettingsUI(settings) {
    $("concurrency-display").textContent = String(settings.max_concurrent);
    if (!state.settingsSyncedOnce) {
      state.settingsSyncedOnce = true;
      $("duplicate-policy").value = settings.duplicate_policy;
      $("auto-retry-toggle").checked = Boolean(settings.auto_retry);
      $("max-retries-select").value = String(settings.max_retries);
      const limit = settings.speed_limit_bps || 0;
      const presetOpt = Array.from($("speed-preset").options).find(
        (o) => Number(o.value) === limit
      );
      if (presetOpt) {
        $("speed-preset").value = presetOpt.value;
      } else if (limit > 0) {
        $("speed-preset").value = "custom";
        $("custom-speed-kbps").value = String(Math.round(limit / 1024));
        $("custom-speed-wrap").classList.remove("hidden");
      }
    }
  }

  async function refreshState() {
    try {
      const data = await api("/api/state");
      syncSettingsUI(data.settings);

      $("global-speed").textContent = data.total_speed_human;
      state.speedHistory.push(data.total_speed_bps || 0);
      if (state.speedHistory.length > 36) state.speedHistory.shift();
      renderSparkline(state.speedHistory);

      const c = data.counts;
      $("slot-usage").textContent = `${c.running} / ${data.settings.max_concurrent} actifs`;
      $("queue-summary").textContent = `${c.queued} en attente · ${c.paused} en pause`;

      $("cnt-all").textContent = String(data.tasks.length);
      $("cnt-running").textContent = String(c.running);
      $("cnt-queued").textContent = String(c.queued);
      $("cnt-paused").textContent = String(c.paused);
      $("cnt-failed").textContent = String(c.failed + data.retrying_count + data.stalled_count);

      const netCard = $("network-card");
      netCard.className = `metric-card network-${data.network_health}`;
      $("network-status-text").textContent = data.network_message;

      if (data.demo && data.demo.enabled) {
        state.demoPresets = data.demo;
        $("demo-bar").classList.remove("hidden");
      }

      reconcileTasks(data.tasks);
      renderHistory(data.history || []);
    } catch {
      // Ignoré silencieusement lors d'un rechargement transitoire
    }
  }

  async function openFolderModal(payload = {}) {
    try {
      const listing = await api("/api/open-folder", { method: "POST", body: payload });
      $("folder-path-code").textContent = listing.folder;
      $("folder-native-note").textContent = listing.opened_native
        ? "Le dossier a également été ouvert dans l'Explorateur du système."
        : "Contenu en direct du dossier de destination sur le disque :";
      const rows = listing.entries;
      $("folder-files-list").innerHTML =
        rows.length === 0
          ? `<div class="empty-state empty-compact"><p class="empty-desc">Ce dossier est actuellement vide.</p></div>`
          : rows
              .map(
                (f) => `
              <div class="folder-file-row ${f.highlighted ? "highlighted" : ""}">
                <div>
                  <strong>${escapeHtml(f.name)}</strong>
                  ${f.is_part ? `<span class="badge badge-running">Fichier partiel (.part)</span>` : ""}
                  <div class="metric-sub tabular">${escapeHtml(f.size_human)}</div>
                </div>
                <div>
                  ${
                    f.download_url
                      ? `<a class="btn btn-secondary btn-compact" href="${f.download_url}" download>Enregistrer</a>`
                      : ""
                  }
                </div>
              </div>
            `
              )
              .join("");
      $("folder-modal").classList.remove("hidden");
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function openDuplicateModal(duplicate, retryPayload) {
    state.pendingDuplicatePayload = retryPayload;
    $("dup-modal-reason").textContent = duplicate.reason;
    $("dup-modal-path").textContent = duplicate.existing_path;
    $("dup-open-folder-btn").onclick = () => {
      $("duplicate-modal").classList.add("hidden");
      openFolderModal({ path: duplicate.existing_path });
    };
    $("duplicate-modal").classList.remove("hidden");
  }

  function formatMediaDuration(seconds) {
    if (!seconds || seconds <= 0) return "";
    const total = Math.round(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const sec = total % 60;
    return h > 0
      ? `${h} h ${String(m).padStart(2, "0")} min`
      : `${m} min ${String(sec).padStart(2, "0")} s`;
  }

  function hideMediaInfo() {
    $("media-info").classList.add("hidden");
    $("media-thumb").removeAttribute("src");
    $("media-title").textContent = "";
    $("media-subtitle").textContent = "";
  }

  function populateQualities(qualities) {
    const select = $("single-quality-select");
    if (!Array.isArray(qualities) || qualities.length === 0) return;
    const current = select.value;
    const known = new Set([...select.options].map((opt) => opt.value));
    for (const item of qualities) {
      if (!item || known.has(item.value)) continue;
      const opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label || item.value;
      select.appendChild(opt);
      known.add(item.value);
    }
    if (known.has(current)) select.value = current;
  }

  function renderMediaInfo(info) {
    if (!info || info.provider !== "youtube") {
      hideMediaInfo();
      return;
    }
    $("media-info").classList.remove("hidden");
    const thumb = $("media-thumb");
    if (info.thumbnail_url) {
      thumb.src = info.thumbnail_url;
      thumb.alt = `Miniature de ${info.title}`;
    } else {
      thumb.removeAttribute("src");
    }
    $("media-title").textContent = info.title || "Vidéo YouTube";
    const parts = ["YouTube"];
    if (info.uploader) parts.push(info.uploader);
    const duration = formatMediaDuration(info.duration_seconds);
    if (duration) parts.push(duration);
    if (info.heights && info.heights.length > 0) {
      parts.push(`jusqu'à ${info.heights[0]}p`);
    }
    $("media-subtitle").textContent = parts.join(" · ");
    populateQualities(info.qualities);
  }

  async function loadMediaInfo(url) {
    try {
      const info = await api(`/api/media/info?url=${encodeURIComponent(url)}`);
      renderMediaInfo(info);
      return info;
    } catch (err) {
      hideMediaInfo();
      const banner = $("precheck-banner");
      banner.className = "precheck-banner precheck-warn";
      banner.textContent = `✕ ${err.message}`;
      return null;
    }
  }

  async function submitSingleDownload(payload) {
    try {
      const res = await api("/api/downloads", { method: "POST", body: payload });
      if (res.skipped) {
        showToast("Téléchargement ignoré : le fichier est déjà présent.");
      } else {
        showToast(`Ajouté : ${res.task.filename}`, "ok");
        $("single-url-input").value = "";
        $("single-filename-input").value = "";
        $("precheck-banner").classList.add("hidden");
        hideMediaInfo();
      }
      await refreshState();
    } catch (err) {
      if (err.conflict && err.duplicate) {
        openDuplicateModal(err.duplicate, payload);
      } else {
        showToast(err.message, "error");
      }
    }
  }

  // Initialisation des événements d'interface
  function bindEvents() {
    $("btn-theme").addEventListener("click", () => {
      const root = document.documentElement;
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    });

    $("btn-open-dest").addEventListener("click", () => openFolderModal({}));
    $("folder-close-btn").addEventListener("click", () => $("folder-modal").classList.add("hidden"));
    $("btn-copy-folder-path").addEventListener("click", async () => {
      const txt = $("folder-path-code").textContent;
      if (navigator.clipboard) await navigator.clipboard.writeText(txt);
      showToast("Chemin du dossier copié dans le presse-papiers.", "ok");
    });

    $("dup-close-btn").addEventListener("click", () => $("duplicate-modal").classList.add("hidden"));
    $("dup-skip-btn").addEventListener("click", () => {
      $("duplicate-modal").classList.add("hidden");
      state.pendingDuplicatePayload = null;
      showToast("Lien ignoré (fichier existant conservé).");
    });
    $("dup-rename-btn").addEventListener("click", async () => {
      const pending = state.pendingDuplicatePayload;
      $("duplicate-modal").classList.add("hidden");
      if (pending) {
        await submitSingleDownload({ ...pending, duplicate_policy: "rename" });
      }
    });

    // Contrôles intelligents en direct
    $("btn-conc-dec").addEventListener("click", async () => {
      const cur = Math.max(1, Number($("concurrency-display").textContent) - 1);
      await api("/api/settings", { method: "POST", body: { max_concurrent: cur } });
      await refreshState();
    });

    $("btn-conc-inc").addEventListener("click", async () => {
      const cur = Math.min(16, Number($("concurrency-display").textContent) + 1);
      await api("/api/settings", { method: "POST", body: { max_concurrent: cur } });
      await refreshState();
    });

    $("speed-preset").addEventListener("change", async (e) => {
      const val = e.target.value;
      if (val === "custom") {
        $("custom-speed-wrap").classList.remove("hidden");
        return;
      }
      $("custom-speed-wrap").classList.add("hidden");
      await api("/api/settings", { method: "POST", body: { speed_limit_bps: Number(val) } });
      showToast(Number(val) === 0 ? "Limite de vitesse désactivée." : "Limite de vitesse mise à jour.", "ok");
      await refreshState();
    });

    $("btn-apply-speed").addEventListener("click", async () => {
      const kbps = Math.max(16, Number($("custom-speed-kbps").value) || 500);
      await api("/api/settings", { method: "POST", body: { speed_limit_bps: kbps * 1024 } });
      showToast(`Limite fixée à ${kbps} Ko/s.`, "ok");
      await refreshState();
    });

    $("duplicate-policy").addEventListener("change", async (e) => {
      await api("/api/settings", { method: "POST", body: { duplicate_policy: e.target.value } });
    });

    const syncRetry = async () => {
      await api("/api/settings", {
        method: "POST",
        body: {
          auto_retry: $("auto-retry-toggle").checked,
          max_retries: Number($("max-retries-select").value),
        },
      });
    };
    $("auto-retry-toggle").addEventListener("change", syncRetry);
    $("max-retries-select").addEventListener("change", syncRetry);

    // Onglets Lien unique / Lot
    $("tab-single").addEventListener("click", () => {
      $("tab-single").classList.add("active");
      $("tab-batch").classList.remove("active");
      $("single-form").classList.remove("hidden");
      $("batch-form").classList.add("hidden");
    });

    $("tab-batch").addEventListener("click", () => {
      $("tab-batch").classList.add("active");
      $("tab-single").classList.remove("active");
      $("batch-form").classList.remove("hidden");
      $("single-form").classList.add("hidden");
    });

    // Pré-détection en direct à la saisie d'une URL
    let precheckTimer = null;
    $("single-url-input").addEventListener("input", () => {
      clearTimeout(precheckTimer);
      const raw = $("single-url-input").value.trim();
      const banner = $("precheck-banner");
      if (!raw) {
        banner.classList.add("hidden");
        return;
      }
      precheckTimer = setTimeout(async () => {
        try {
          const check = await api("/api/downloads/inspect", { method: "POST", body: { text: raw } });
          if (check.duplicates.length > 0) {
            banner.className = "precheck-banner precheck-warn";
            banner.textContent = `⚠ Détection : ${check.duplicates[0].reason}`;
          } else if (check.rejected.length > 0) {
            banner.className = "precheck-banner precheck-warn";
            banner.textContent = `✕ ${check.rejected[0].error.split("\n")[0]}`;
          } else if (check.valid[0] && check.valid[0].provider === "youtube") {
            banner.className = "precheck-banner";
            banner.textContent = "✓ Vidéo YouTube détectée : récupération du titre et des qualités…";
            await loadMediaInfo(raw);
          } else {
            hideMediaInfo();
            banner.className = "precheck-banner";
            banner.textContent = `✓ Prêt à télécharger sous « ${check.valid[0].filename} »`;
          }
        } catch {
          banner.classList.add("hidden");
        }
      }, 280);
    });

    $("single-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await submitSingleDownload({
        url: $("single-url-input").value.trim(),
        filename: $("single-filename-input").value.trim() || null,
        start_paused: $("start-paused-check").checked,
        quality: $("single-quality-select").value || "best",
      });
    });

    $("batch-file-input").addEventListener("change", async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const content = await file.text();
      const box = $("batch-urls-input");
      box.value = box.value.trim() ? `${box.value.trim()}\n${content}` : content;
      showToast(`Fichier « ${file.name} » importé.`, "ok");
    });

    $("btn-inspect-batch").addEventListener("click", async () => {
      const text = $("batch-urls-input").value;
      const report = $("batch-report");
      try {
        const res = await api("/api/downloads/inspect", { method: "POST", body: { text } });
        report.classList.remove("hidden");
        report.textContent = `Analyse du lot : ${res.valid.length} lien(s) prêt(s) · ${res.duplicates.length} déjà présent(s) · ${res.rejected.length} invalide(s).`;
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    $("batch-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/downloads/batch", {
          method: "POST",
          body: {
            text: $("batch-urls-input").value,
            duplicate_policy:
              $("duplicate-policy").value === "ask" ? "skip" : $("duplicate-policy").value,
            start_paused: $("start-paused-check").checked,
            quality: $("single-quality-select").value || "best",
          },
        });
        const s = res.summary;
        showToast(
          `Lot ajouté : ${s.added_count} lancé(s), ${s.skipped_count + s.conflict_count} doublon(s) ignoré(s), ${s.rejected_count} rejeté(s).`,
          "ok"
        );
        if (s.added_count > 0) $("batch-urls-input").value = "";
        $("batch-report").classList.add("hidden");
        await refreshState();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    // Banc d'essai en 1 clic
    $("demo-btn-batch").addEventListener("click", async () => {
      if (!state.demoPresets) return;
      await api("/api/downloads/batch", {
        method: "POST",
        body: {
          text: state.demoPresets.batch_urls.join("\n"),
          duplicate_policy: "rename",
        },
      });
      showToast("Lot de 4 médias lancé — testez Pause, Limite de vitesse ou Simultanéité !", "ok");
      await refreshState();
    });

    $("demo-btn-flaky").addEventListener("click", async () => {
      const fresh = await api("/api/state");
      if (!fresh.demo || !fresh.demo.enabled) return;
      await submitSingleDownload({
        url: fresh.demo.flaky_url,
        duplicate_policy: "rename",
      });
    });

    $("demo-btn-dup").addEventListener("click", async () => {
      if (!state.demoPresets) return;
      await submitSingleDownload({
        url: state.demoPresets.single_url,
        duplicate_policy: "ask",
      });
    });

    // Actions globales et filtres
    $("task-filters").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      state.filter = btn.dataset.filter;
      for (const el of $("task-filters").querySelectorAll(".pill")) {
        el.classList.toggle("active", el === btn);
      }
      refreshState();
    });

    $("btn-pause-all").addEventListener("click", async () => {
      await api("/api/downloads/pause-all", { method: "POST" });
      await refreshState();
    });

    $("btn-resume-all").addEventListener("click", async () => {
      await api("/api/downloads/resume-all", { method: "POST" });
      await refreshState();
    });

    $("btn-clear-finished").addEventListener("click", async () => {
      await api("/api/downloads/clear-finished", { method: "POST" });
      await refreshState();
    });

    $("tasks-list").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const { action, id } = btn.dataset;
      if (action === "open-task-folder") {
        await openFolderModal({ task_id: id });
        return;
      }
      try {
        await api(`/api/downloads/${id}/${action}`, { method: "POST" });
        await refreshState();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    $("history-list").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const { action, id, url } = btn.dataset;
      if (action === "open-history-folder") {
        await openFolderModal({ history_id: id });
      } else if (action === "redownload") {
        await submitSingleDownload({ url, duplicate_policy: "rename" });
      } else if (action === "delete-history") {
        await api(`/api/history/${id}`, { method: "DELETE" });
        await refreshState();
      }
    });

    $("history-search").addEventListener("input", (e) => {
      state.historyQuery = e.target.value;
      refreshState();
    });

    $("history-status-filter").addEventListener("change", (e) => {
      state.historyStatus = e.target.value;
      refreshState();
    });

    $("btn-clear-history").addEventListener("click", async () => {
      await api("/api/history", { method: "DELETE" });
      showToast("Historique effacé (les fichiers téléchargés sont conservés).", "ok");
      await refreshState();
    });
  }

  bindEvents();
  refreshState();
  setInterval(refreshState, 300);
})();
