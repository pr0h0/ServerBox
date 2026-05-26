(function () {
  const state = window.SERVEBOX || {};
  const currentPath = state.currentPath || "";

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function $all(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function buildUrl(path, params) {
    const url = new URL(path, window.location.origin);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    });
    return url.toString();
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function apiFetch(url, options) {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof body === "object" && body.detail ? body.detail : body;
      throw new Error(detail || `Request failed with ${response.status}`);
    }
    return body;
  }

  function showToast(message, isError) {
    const toast = $("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", Boolean(isError));
    toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      toast.hidden = true;
    }, 3500);
  }

  function setStatus(message) {
    const status = $("#statusLine");
    if (status) status.textContent = message || "";
  }

  let activeModal = null;

  function modalElements() {
    return {
      root: $("#modalRoot"),
      form: $("#modalForm"),
      title: $("#modalTitle"),
      message: $("#modalMessage"),
      inputWrap: $("#modalInputWrap"),
      inputLabel: $("#modalInputLabel"),
      input: $("#modalInput"),
      confirm: $("#modalConfirm"),
    };
  }

  function openModal(options) {
    const elements = modalElements();
    if (!elements.root || !elements.form) {
      return Promise.resolve({ confirmed: false, value: "" });
    }

    return new Promise((resolve) => {
      activeModal = {
        resolve,
        previousFocus: document.activeElement,
      };

      elements.title.textContent = options.title || "Confirm";
      elements.message.textContent = options.message || "";
      elements.message.hidden = !options.message;
      elements.confirm.textContent = options.confirmText || "Confirm";
      elements.confirm.classList.toggle("danger", Boolean(options.danger));

      const hasInput = Boolean(options.inputLabel);
      elements.inputWrap.hidden = !hasInput;
      elements.inputLabel.textContent = options.inputLabel || "";
      elements.input.value = options.inputValue || "";
      elements.input.required = Boolean(hasInput && options.required);
      elements.input.placeholder = options.placeholder || "";

      elements.root.hidden = false;
      document.body.classList.add("modal-open");

      window.setTimeout(() => {
        if (hasInput) {
          elements.input.focus();
          elements.input.select();
        } else {
          elements.confirm.focus();
        }
      }, 0);
    });
  }

  function closeModal(confirmed) {
    if (!activeModal) return;
    const elements = modalElements();
    const value = elements.input ? elements.input.value : "";
    const { resolve, previousFocus } = activeModal;
    activeModal = null;

    if (elements.root) elements.root.hidden = true;
    document.body.classList.remove("modal-open");
    if (previousFocus && typeof previousFocus.focus === "function") {
      previousFocus.focus();
    }
    resolve({ confirmed, value });
  }

  function initModal() {
    const elements = modalElements();
    if (!elements.form) return;

    elements.form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (elements.input && elements.input.required && !elements.input.value.trim()) {
        elements.input.focus();
        return;
      }
      closeModal(true);
    });

    $all("[data-modal-cancel]").forEach((element) => {
      element.addEventListener("click", () => closeModal(false));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && activeModal) {
        closeModal(false);
      }
    });
  }

  function initDirectoryFilter() {
    const filter = $("#dirFilter");
    const rows = $all("#fileTableBody tr[data-name]");
    if (!filter || rows.length === 0) return;
    filter.addEventListener("input", () => {
      const needle = filter.value.trim().toLowerCase();
      rows.forEach((row) => {
        row.hidden = needle && !row.dataset.name.includes(needle);
      });
    });
  }

  async function uploadFiles(files) {
    if (!files || files.length === 0) return;
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    setStatus(`Uploading ${files.length} file${files.length === 1 ? "" : "s"}...`);
    try {
      await apiFetch(buildUrl("/api/upload", { path: currentPath }), {
        method: "POST",
        body: formData,
      });
      setStatus("Upload complete. Refreshing...");
      window.location.reload();
    } catch (error) {
      setStatus("");
      showToast(error.message, true);
    }
  }

  function initUploads() {
    if (state.readonly) return;
    const input = $("#fileInput");
    const button = $("#uploadButton");
    const dropZone = $("#dropZone");
    if (button && input) {
      button.addEventListener("click", () => input.click());
      input.addEventListener("change", () => uploadFiles(input.files));
    }
    if (dropZone) {
      ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropZone.classList.add("dragging");
        });
      });
      ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropZone.classList.remove("dragging");
        });
      });
      dropZone.addEventListener("drop", (event) => {
        uploadFiles(event.dataTransfer.files);
      });
    }
  }

  function initMutations() {
    const mkdirButton = $("#mkdirButton");
    if (mkdirButton) {
      mkdirButton.addEventListener("click", async () => {
        const result = await openModal({
          title: "New folder",
          message: `Create a folder in /${currentPath}`,
          inputLabel: "Folder name",
          confirmText: "Create",
          required: true,
        });
        const name = result.value.trim();
        if (!result.confirmed) return;
        if (!name) return;
        try {
          await apiFetch("/api/mkdir", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ path: currentPath, name }),
          });
          window.location.reload();
        } catch (error) {
          showToast(error.message, true);
        }
      });
    }

    document.addEventListener("click", async (event) => {
      const target = event.target.closest("[data-action]");
      if (!target) return;
      const action = target.dataset.action;
      const path = target.dataset.path;
      if (action === "rename") {
        const result = await openModal({
          title: "Rename item",
          message: path,
          inputLabel: "New name",
          inputValue: target.dataset.name || "",
          confirmText: "Rename",
          required: true,
        });
        const nextName = result.value.trim();
        if (!result.confirmed) return;
        if (!nextName) return;
        try {
          await apiFetch("/api/rename", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ path, new_name: nextName }),
          });
          window.location.reload();
        } catch (error) {
          showToast(error.message, true);
        }
      }
      if (action === "delete") {
        const itemName = target.dataset.name || path.split("/").pop() || path;
        const result = await openModal({
          title: "Delete item",
          message: `Delete "${itemName}"? This cannot be undone.`,
          confirmText: "Delete",
          danger: true,
        });
        if (!result.confirmed) return;
        try {
          await apiFetch("/api/delete", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ path, confirm: true }),
          });
          window.location.reload();
        } catch (error) {
          showToast(error.message, true);
        }
      }
    });
  }

  function initCopyButtons() {
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-copy]");
      if (!button) return;
      try {
        await navigator.clipboard.writeText(button.dataset.copy || "");
        showToast("Relative path copied");
      } catch (_error) {
        showToast("Clipboard access was blocked", true);
      }
    });
  }

  async function loadTree(path, container, toggle) {
    if (!container || container.dataset.loaded === "true") return;
    container.textContent = "Loading...";
    try {
      const payload = await apiFetch(buildUrl("/api/tree", { path }));
      container.textContent = "";
      if (payload.items.length === 0) {
        container.innerHTML = '<div class="tree-link">No folders</div>';
      } else {
        payload.items.forEach((item) => {
          const wrapper = document.createElement("div");
          wrapper.innerHTML = `
            <div class="tree-node">
              <button class="tree-toggle" data-tree-toggle data-path="${escapeHtml(item.relative_path)}" aria-label="Expand ${escapeHtml(item.name)}">+</button>
              <a class="tree-link" href="${buildUrl("/browse", { path: item.relative_path })}">${escapeHtml(item.name)}</a>
            </div>
            <div class="tree-children" data-tree-children="${escapeHtml(item.relative_path)}" hidden></div>
          `;
          container.appendChild(wrapper);
        });
      }
      container.dataset.loaded = "true";
      if (toggle) toggle.textContent = "-";
    } catch (error) {
      container.textContent = "";
      showToast(error.message, true);
    }
  }

  function initTree() {
    const rootChildren = $("#treeChildren");
    if (!rootChildren) return;
    loadTree("", rootChildren, $('[data-tree-toggle][data-path=""]'));
    document.addEventListener("click", (event) => {
      const toggle = event.target.closest("[data-tree-toggle]");
      if (!toggle) return;
      const path = toggle.dataset.path || "";
      const childSelector = path
        ? `[data-tree-children="${CSS.escape(path)}"]`
        : "#treeChildren";
      const children = $(childSelector);
      if (!children) return;
      const shouldShow = children.hidden;
      children.hidden = !shouldShow;
      if (shouldShow) {
        loadTree(path, children, toggle);
      } else {
        toggle.textContent = "+";
      }
    });
  }

  function renderSearchResults(items, query) {
    const panel = $("#searchResults");
    if (!panel) return;
    if (!query) {
      panel.hidden = true;
      panel.innerHTML = "";
      return;
    }
    if (items.length === 0) {
      panel.innerHTML = '<div class="empty-state">No matches found.</div>';
      panel.hidden = false;
      return;
    }
    panel.innerHTML = items
      .map((item) => {
        const openHref = item.type === "folder"
          ? buildUrl("/browse", { path: item.relative_path })
          : buildUrl("/view", { path: item.relative_path });
        const download = item.type === "file"
          ? `<a class="button compact" href="${buildUrl("/download", { path: item.relative_path })}">Download</a>`
          : "";
        return `
          <div class="search-result">
            <div>
              <strong>${escapeHtml(item.name)}</strong>
              <small>${escapeHtml(item.relative_path)} ${item.size_display ? " - " + escapeHtml(item.size_display) : ""}</small>
            </div>
            <div class="row-actions">
              <a class="button compact" href="${openHref}">Open</a>
              ${download}
              <a class="button compact" href="${buildUrl("/browse", { path: item.parent_path })}">Folder</a>
            </div>
          </div>
        `;
      })
      .join("");
    panel.hidden = false;
  }

  function initGlobalSearch() {
    const input = $("#globalSearch");
    const scope = $("#searchScope");
    const panel = $("#searchResults");
    if (!input || !panel) return;
    let timer = 0;
    input.addEventListener("input", () => {
      window.clearTimeout(timer);
      const query = input.value.trim();
      if (!query) {
        renderSearchResults([], "");
        return;
      }
      timer = window.setTimeout(async () => {
        try {
          const payload = await apiFetch(
            buildUrl("/api/search", {
              q: query,
              scope: scope ? scope.value : "root",
              path: currentPath,
            })
          );
          renderSearchResults(payload.results, query);
        } catch (error) {
          showToast(error.message, true);
        }
      }, 260);
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".global-search")) {
        panel.hidden = true;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initModal();
    initDirectoryFilter();
    initUploads();
    initMutations();
    initCopyButtons();
    initTree();
    initGlobalSearch();
  });
})();
