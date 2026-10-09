(function () {
  const body = document.body;
  const readonly = body.dataset.readonly === "true";
  const maxUpload = Number(body.dataset.maxUpload || 0);
  const TAGS = ["red", "orange", "yellow", "green", "blue", "purple", "gray"];
  const enc = encodeURIComponent;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $all = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const currentPath = () => body.dataset.currentPath || "";
  const isNarrow = () => window.matchMedia("(max-width: 760px)").matches;

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  async function api(url, payload) {
    const options = payload === undefined ? {} : {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    };
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      throw new Error((data && data.detail) || data || `Request failed with ${response.status}`);
    }
    return data;
  }

  function toast(message, isError) {
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", Boolean(isError));
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_error) {
      // navigator.clipboard needs https or localhost; LAN http falls back to execCommand.
      const area = el("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      if (!ok) return toast("Clipboard access was blocked", true);
    }
    toast("Copied");
  }

  /* ---------------- modal ---------------- */

  let activeModal = null;

  function openModal(options) {
    const root = $("#modalRoot");
    if (!root) return Promise.resolve({ confirmed: false, value: "" });
    const input = $("#modalInput");
    const confirm = $("#modalConfirm");
    closeMenu();
    return new Promise((resolve) => {
      activeModal = { resolve, previousFocus: document.activeElement };
      $("#modalTitle").textContent = options.title || "Confirm";
      $("#modalMessage").textContent = options.message || "";
      $("#modalMessage").hidden = !options.message;
      confirm.textContent = options.confirmText || "OK";
      confirm.classList.toggle("danger", Boolean(options.danger));
      confirm.classList.toggle("primary", !options.danger);
      const hasInput = Boolean(options.inputLabel);
      $("#modalInputWrap").hidden = !hasInput;
      $("#modalInputLabel").textContent = options.inputLabel || "";
      input.value = options.inputValue || "";
      input.required = hasInput;
      root.hidden = false;
      body.classList.add("modal-open");
      if (!hasInput) return confirm.focus();
      input.focus();
      // Select the name without its extension, like Finder.
      const dot = input.value.lastIndexOf(".");
      input.setSelectionRange(0, options.selectStem && dot > 0 ? dot : input.value.length);
    });
  }

  function closeModal(confirmed) {
    if (!activeModal) return;
    const { resolve, previousFocus } = activeModal;
    activeModal = null;
    $("#modalRoot").hidden = true;
    body.classList.remove("modal-open");
    if (previousFocus && previousFocus.focus) previousFocus.focus({ preventScroll: true });
    resolve({ confirmed, value: $("#modalInput").value.trim() });
  }

  function initModal() {
    const form = $("#modalForm");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = $("#modalInput");
      if (input.required && !input.value.trim()) return input.focus();
      closeModal(true);
    });
    $all("[data-modal-cancel]").forEach((node) => node.addEventListener("click", () => closeModal(false)));
  }

  /* ---------------- items + selection ---------------- */

  const items = () => $all("#files .item");
  const selected = () => $all("#files .item.selected");
  let anchor = null;
  let cursor = null;

  function updateCount() {
    const count = $("#count");
    if (!count) return;
    const total = items().length;
    const picked = selected().length;
    count.textContent = picked ? `${picked} of ${total} selected` : `${total} item${total === 1 ? "" : "s"}`;
  }

  function select(list, keepAnchor) {
    items().forEach((item) => item.classList.toggle("selected", list.includes(item)));
    const last = list[list.length - 1] || null;
    if (!keepAnchor) anchor = last;
    cursor = last;
    if (last) {
      last.scrollIntoView({ block: "nearest" });
      last.focus({ preventScroll: true });
    }
    updateCount();
    if (qlOpen() && last) quickLook(last);
  }

  function selectRange(target) {
    const all = items();
    const from = Math.max(0, all.indexOf(anchor));
    const to = all.indexOf(target);
    const range = all.slice(Math.min(from, to), Math.max(from, to) + 1);
    if (to < from) range.reverse();
    select(range, true);
  }

  function selectPath(path) {
    const item = items().find((node) => node.dataset.path === path);
    if (item) select([item]);
  }

  const tagsOf = (item) => (item.dataset.tags || "").split(" ").filter(Boolean);
  const parentOf = (path) => path.split("/").slice(0, -1).join("/");
  const nameOf = (item) => item.dataset.name;

  function setTags(item, tags) {
    item.dataset.tags = tags.join(" ");
    const holder = $(".tags", item);
    holder.textContent = "";
    tags.forEach((tag) => holder.appendChild(el("i", { class: `dot tag-${tag}` })));
  }

  /* ---------------- navigation (swaps #view in place) ---------------- */

  let viewRequest = 0;

  async function loadView(url, how) {
    const id = ++viewRequest;
    let response;
    try {
      response = await fetch(url, { headers: { accept: "text/html" } });
    } catch (_error) {
      return toast("Network error", true);
    }
    const html = await response.text();
    if (id !== viewRequest) return;
    const doc = new DOMParser().parseFromString(html, "text/html");
    const next = doc.getElementById("view");
    if (!response.ok || !next || !$("#view")) {
      window.location.href = url; // error page or login: let the browser show it
      return;
    }
    $("#view").replaceWith(next);
    body.dataset.currentPath = doc.body.dataset.currentPath || "";
    document.title = doc.title;
    $("#viewTitle").textContent = next.dataset.title;
    const finalUrl = response.url || url;
    if (how === "push") history.pushState(null, "", finalUrl);
    if (how === "replace") history.replaceState(null, "", finalUrl);
    if (how !== "keep-search") {
      const search = $("#search");
      if (search) search.value = doc.getElementById("search")?.value || "";
    }
    const activeHrefs = $all(".sidebar .side-link.active", doc).map((link) => link.getAttribute("href"));
    $all(".sidebar .side-link").forEach((link) => link.classList.toggle("active", activeHrefs.includes(link.getAttribute("href"))));
    markTree();
    anchor = cursor = null;
    afterRender();
    if (isNarrow()) body.classList.remove("side-open");
  }

  const navigate = (url) => loadView(url, "push");
  const reloadView = () => loadView(window.location.href, "replace");
  const folderUrl = (path) => `/browse?path=${enc(path)}`;

  function openItem(item) {
    const href = item.dataset.href;
    if (!href) return toast("This item can't be opened", true);
    if (item.dataset.type === "folder") navigate(href);
    else window.location.href = href;
  }

  /* ---------------- rendering helpers ---------------- */

  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  const timeFormat = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });

  function formatDates() {
    const today = new Date().toDateString();
    $all("#files .c-date[data-ts]").forEach((cell) => {
      if (!cell.dataset.ts) return;
      const date = new Date(Number(cell.dataset.ts) * 1000);
      cell.textContent = date.toDateString() === today ? `Today at ${timeFormat.format(date)}` : dateFormat.format(date);
    });
  }

  let sort = { key: "name", dir: 1 };
  try { sort = JSON.parse(localStorage.getItem("sb_sort")) || sort; } catch (_error) { /* default */ }

  function applySort() {
    const files = $("#files");
    if (!files) return;
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    const value = (item) => (sort.key === "name" || sort.key === "kind" ? item.dataset[sort.key] : Number(item.dataset[sort.key]));
    const list = items().sort((a, b) => {
      const folders = (a.dataset.type === "folder" ? 0 : 1) - (b.dataset.type === "folder" ? 0 : 1);
      if (folders) return folders;
      const x = value(a);
      const y = value(b);
      const primary = typeof x === "string" ? collator.compare(x, y) : x - y;
      return primary * sort.dir || collator.compare(a.dataset.name, b.dataset.name);
    });
    list.forEach((item) => files.appendChild(item));
    $all("#files [data-sort]").forEach((button) => {
      button.classList.toggle("sorted", button.dataset.sort === sort.key);
      button.classList.toggle("desc", button.dataset.sort === sort.key && sort.dir < 0);
    });
  }

  function setView(mode) {
    const files = $("#files");
    if (files) {
      files.classList.toggle("grid", mode === "grid");
      files.classList.toggle("list", mode !== "grid");
    }
    $all("[data-view]").forEach((button) => button.classList.toggle("on", button.dataset.view === mode));
    // Cookie, so the server renders the right view on the next load without a flash.
    document.cookie = `sb_view=${mode}; path=/; max-age=31536000; samesite=lax`;
  }

  function afterRender() {
    const files = $("#files");
    if (files) files.tabIndex = 0;
    formatDates();
    applySort();
    updateCount();
  }

  /* ---------------- actions ---------------- */

  async function run(task) {
    try {
      return await task();
    } catch (error) {
      toast(error.message, true);
      return null;
    }
  }

  async function newFolder() {
    const result = await openModal({ title: "New Folder", inputLabel: "Name", inputValue: "untitled folder", confirmText: "Create" });
    if (!result.confirmed || !result.value) return;
    const data = await run(() => api("/api/mkdir", { path: currentPath(), name: result.value }));
    if (data) {
      await reloadView();
      selectPath(data.item.relative_path);
    }
  }

  async function renameItem(item) {
    const result = await openModal({
      title: "Rename",
      inputLabel: "Name",
      inputValue: nameOf(item),
      confirmText: "Rename",
      selectStem: item.dataset.type !== "folder",
    });
    if (!result.confirmed || !result.value || result.value === nameOf(item)) return;
    const data = await run(() => api("/api/rename", { path: item.dataset.path, new_name: result.value }));
    if (data) {
      await reloadView();
      selectPath(data.item.relative_path);
    }
  }

  async function moveItems(list, dest) {
    let moved = 0;
    for (const item of list) {
      const path = item.dataset.path;
      if (parentOf(path) === dest || path === dest) continue;
      if (await run(() => api("/api/move", { path, dest }))) moved += 1;
    }
    if (moved) {
      toast(`Moved ${moved} item${moved === 1 ? "" : "s"} to /${dest}`);
      await reloadView();
    }
  }

  async function moveDialog(list) {
    const result = await openModal({
      title: list.length === 1 ? `Move “${nameOf(list[0])}”` : `Move ${list.length} items`,
      message: "Destination folder, relative to the root. Leave empty for the root.",
      inputLabel: "Folder",
      inputValue: currentPath(),
      confirmText: "Move",
    });
    if (result.confirmed) moveItems(list, result.value.replace(/^\/+|\/+$/g, ""));
  }

  async function deleteItems(list) {
    const result = await openModal({
      title: list.length === 1 ? `Delete “${nameOf(list[0])}”?` : `Delete ${list.length} items?`,
      message: "This can't be undone.",
      confirmText: "Delete",
      danger: true,
    });
    if (!result.confirmed) return;
    for (const item of list) {
      await run(() => api("/api/delete", { path: item.dataset.path, confirm: true }));
    }
    reloadView();
  }

  async function toggleTag(list, tag) {
    const all = list.every((item) => tagsOf(item).includes(tag));
    for (const item of list) {
      const next = tagsOf(item).filter((t) => t !== tag);
      if (!all) next.push(tag);
      const data = await run(() => api("/api/tags", { path: item.dataset.path, tags: next }));
      if (data) setTags(item, data.tags);
    }
    if ($("#view")?.dataset.mode === "tag") reloadView();
  }

  function download(item) {
    const link = el("a", { href: `/download?path=${enc(item.dataset.path)}`, download: "" });
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  /* ---------------- uploads ---------------- */

  function upload(fileList, dest) {
    const files = Array.from(fileList || []);
    if (!files.length || readonly) return;
    const tooBig = files.find((file) => maxUpload && file.size > maxUpload);
    if (tooBig) return toast(`${tooBig.name} is larger than the upload limit`, true);

    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const progress = $("#progress");
    const bar = $("#progressBar");
    const label = $("#progressText");
    const what = files.length === 1 ? files[0].name : `${files.length} files`;
    progress.hidden = false;
    bar.style.width = "0%";
    label.textContent = `Uploading ${what}…`;

    const xhr = new XMLHttpRequest(); // fetch() has no upload progress
    xhr.open("POST", `/api/upload?path=${enc(dest)}`);
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const pct = Math.round((event.loaded / event.total) * 100);
      bar.style.width = `${pct}%`;
      label.textContent = `Uploading ${what}… ${pct}%`;
    };
    xhr.onload = async () => {
      progress.hidden = true;
      let detail = "";
      try { detail = JSON.parse(xhr.responseText).detail; } catch (_error) { /* not json */ }
      if (xhr.status >= 300) return toast(detail || `Upload failed (${xhr.status})`, true);
      toast(`Uploaded ${what}`);
      await reloadView();
      const uploaded = JSON.parse(xhr.responseText).uploaded || [];
      const paths = uploaded.map((item) => item.relative_path);
      const nodes = items().filter((item) => paths.includes(item.dataset.path));
      if (nodes.length) select(nodes);
    };
    xhr.onerror = () => {
      progress.hidden = true;
      toast("Upload failed: network error", true);
    };
    xhr.send(form);
  }

  /* ---------------- context menu ---------------- */

  function closeMenu() {
    const menu = $("#ctxMenu");
    if (menu) menu.hidden = true;
  }

  function showMenu(x, y, entries) {
    const menu = $("#ctxMenu");
    menu.textContent = "";
    let lastWasSep = true;
    entries.forEach((entry) => {
      if (entry === "sep") {
        if (!lastWasSep) menu.appendChild(el("hr"));
        lastWasSep = true;
        return;
      }
      lastWasSep = false;
      if (entry.label) {
        menu.appendChild(el("div", { class: "menu-label" }, entry.label));
      } else if (entry.tags) {
        const row = el("div", { class: "tag-row", role: "group", "aria-label": "Tags" });
        TAGS.forEach((tag) => {
          const on = entry.tags.every((item) => tagsOf(item).includes(tag));
          const button = el("button", { type: "button", class: `tag-${tag}${on ? " on" : ""}`, title: tag, "aria-label": `Tag ${tag}`, "aria-pressed": String(on) });
          button.addEventListener("click", () => { closeMenu(); toggleTag(entry.tags, tag); });
          row.appendChild(button);
        });
        menu.appendChild(row);
      } else {
        const [text, action, cls] = entry;
        const button = el("button", { type: "button", role: "menuitem", class: cls || "" }, text);
        button.addEventListener("click", () => { closeMenu(); action(); });
        menu.appendChild(button);
      }
    });
    if (menu.lastChild && menu.lastChild.tagName === "HR") menu.lastChild.remove();
    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, y + rect.height > window.innerHeight - 8 ? y - rect.height : y)}px`;
    const first = $("button", menu);
    if (first) first.focus({ preventScroll: true });
  }

  function itemMenu(list) {
    const one = list.length === 1 ? list[0] : null;
    const isFile = one && one.dataset.type === "file";
    const inResults = $("#view")?.dataset.mode !== "folder";
    const entries = [{ label: one ? nameOf(one) : `${list.length} items` }];
    if (one && one.dataset.href) entries.push(["Open", () => openItem(one)]);
    if (isFile) entries.push(["Quick Look", () => quickLook(one)], ["Download", () => download(one)]);
    if (one && inResults) entries.push(["Show in Enclosing Folder", () => navigate(folderUrl(parentOf(one.dataset.path)))]);
    entries.push("sep");
    if (!readonly && one) entries.push(["Rename…", () => renameItem(one)]);
    if (!readonly) entries.push(["Move to…", () => moveDialog(list)]);
    entries.push([one ? "Copy Path" : "Copy Paths", () => copyText(list.map((item) => item.dataset.path).join("\n"))]);
    if (isFile) entries.push(["Get Info", () => openItem(one)]);
    if (!readonly) {
      entries.push("sep", { tags: list }, "sep");
      entries.push([one ? "Delete…" : `Delete ${list.length} Items…`, () => deleteItems(list), "danger"]);
    }
    return entries;
  }

  function backgroundMenu() {
    const entries = [];
    const inFolder = $("#view")?.dataset.mode === "folder";
    if (!readonly && inFolder) {
      entries.push(["New Folder", newFolder], ["Upload Files…", () => $("#fileInput").click()], "sep");
    }
    entries.push(["View as Icons", () => setView("grid")], ["View as List", () => setView("list")], "sep");
    entries.push(["Copy Folder Path", () => copyText(currentPath() || "/")]);
    return entries;
  }

  /* ---------------- quick look ---------------- */

  const qlOpen = () => !$("#quickLook")?.hidden;
  let qlRequest = 0;

  function closeQuickLook() {
    const root = $("#quickLook");
    if (!root || root.hidden) return;
    root.hidden = true;
    $("#qlBody").textContent = ""; // stops audio/video
    body.classList.remove("modal-open");
  }

  async function quickLook(item) {
    const root = $("#quickLook");
    const view = $("#qlBody");
    const id = ++qlRequest;
    const d = item.dataset;
    const raw = `/raw?path=${enc(d.path)}`;
    $("#qlTitle").textContent = d.name;
    $("#qlOpen").href = d.href || "#";
    $("#qlDownload").href = `/download?path=${enc(d.path)}`;
    $("#qlDownload").hidden = d.type !== "file";
    view.textContent = "";
    root.hidden = false;
    body.classList.add("modal-open");

    if (d.preview === "image") view.appendChild(el("img", { src: raw, alt: d.name }));
    else if (d.preview === "video") view.appendChild(el("video", { src: raw, controls: "", autoplay: "" }));
    else if (d.preview === "audio") view.appendChild(el("audio", { src: raw, controls: "", autoplay: "" }));
    else if (d.preview === "pdf") view.appendChild(el("iframe", { src: raw, title: d.name }));
    else if (d.preview === "text") {
      const pre = el("pre", {}, "Loading…");
      view.appendChild(pre);
      try {
        const limit = 256 * 1024;
        const response = await fetch(raw, { headers: { range: `bytes=0-${limit - 1}` } });
        const text = await response.text();
        if (id !== qlRequest) return;
        const total = Number((response.headers.get("content-range") || "").split("/")[1]);
        pre.textContent = total > limit ? `${text}\n\n… (preview truncated, open the file to see all of it)` : text;
      } catch (_error) {
        if (id === qlRequest) pre.textContent = "Could not load preview.";
      }
    } else {
      const box = el("div", { class: "ql-none" });
      const icon = $(".icon", item).cloneNode(true);
      box.append(icon, el("strong", {}, d.name), el("span", {}, `${d.kind}${d.size >= 0 ? " · " + $(".c-size", item).textContent : ""}`));
      view.appendChild(box);
    }
  }

  /* ---------------- sidebar tree ---------------- */

  async function loadTree(container) {
    if (container.dataset.loaded === "true") return;
    container.dataset.loaded = "true";
    const path = container.dataset.treeChildren;
    try {
      const data = await api(`/api/tree?path=${enc(path)}`);
      container.textContent = "";
      if (!data.items.length && path) container.appendChild(el("div", { class: "tree-empty" }, "No folders"));
      data.items.forEach((item) => {
        const node = el("div", { class: "tree-node" });
        const row = el("div", { class: "tree-row", "data-drop-path": item.relative_path });
        const toggle = el("button", { type: "button", class: "tree-toggle", "data-tree-toggle": "", "aria-expanded": "false", "aria-label": `Expand ${item.name}` });
        toggle.innerHTML = '<svg><use href="#i-chev"/></svg>';
        row.append(toggle, el("a", { href: folderUrl(item.relative_path) }, item.name));
        node.append(row, el("div", { class: "tree-children", "data-tree-children": item.relative_path, hidden: "" }));
        container.appendChild(node);
      });
      markTree();
    } catch (error) {
      container.dataset.loaded = "";
      toast(error.message, true);
    }
  }

  function markTree() {
    const path = $("#view")?.dataset.mode === "folder" ? currentPath() : null;
    $all(".tree-row").forEach((row) => row.classList.toggle("active", row.dataset.dropPath === path));
  }

  /* ---------------- search ---------------- */

  let searchTimer = 0;

  function runSearch(scope) {
    const query = $("#search").value.trim();
    const url = query
      ? `/browse?path=${enc(currentPath())}&q=${enc(query)}&scope=${scope || $(".chip.on")?.dataset.scope || "root"}`
      : folderUrl(currentPath());
    loadView(url, "keep-search").then(() => history.replaceState(null, "", url));
  }

  /* ---------------- drag and drop ---------------- */

  const INTERNAL = "application/x-servebox-paths";
  let dragged = [];
  let overlayTimer = 0;

  function dropTargetFrom(node) {
    const target = node.closest("[data-drop-path], #files .item[data-type='folder']");
    if (!target) return null;
    const path = target.matches(".item") ? target.dataset.path : target.dataset.dropPath;
    return { target, path };
  }

  function clearDropTargets() {
    $all(".drop-target").forEach((node) => node.classList.remove("drop-target"));
  }

  function initDragDrop() {
    document.addEventListener("dragstart", (event) => {
      const item = event.target.closest && event.target.closest("#files .item");
      if (!item || readonly) return;
      if (!item.classList.contains("selected")) select([item]);
      dragged = selected();
      dragged.forEach((node) => node.classList.add("dragging"));
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData(INTERNAL, JSON.stringify(dragged.map((node) => node.dataset.path)));
      event.dataTransfer.setData("text/plain", dragged.map((node) => node.dataset.path).join("\n"));
    });

    document.addEventListener("dragend", () => {
      dragged.forEach((node) => node.classList.remove("dragging"));
      dragged = [];
      clearDropTargets();
    });

    document.addEventListener("dragover", (event) => {
      if (readonly) return;
      const types = Array.from(event.dataTransfer.types);
      const internal = types.includes(INTERNAL);
      const external = types.includes("Files");
      if (!internal && !external) return;
      const drop = dropTargetFrom(event.target);
      clearDropTargets();
      if (internal) {
        const paths = dragged.map((node) => node.dataset.path);
        if (!drop || paths.includes(drop.path)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        drop.target.classList.add("drop-target");
        return;
      }
      event.preventDefault();
      if (!$("#dropOverlay")) return;
      event.dataTransfer.dropEffect = "copy";
      if (drop) drop.target.classList.add("drop-target");
      $("#dropTarget").textContent = `/${drop ? drop.path : currentPath()}`;
      $("#dropOverlay").hidden = false;
      clearTimeout(overlayTimer);
      overlayTimer = setTimeout(() => { $("#dropOverlay").hidden = true; clearDropTargets(); }, 150);
    });

    document.addEventListener("drop", (event) => {
      if (readonly) return;
      const types = Array.from(event.dataTransfer.types);
      if (!types.includes(INTERNAL) && !types.includes("Files")) return;
      event.preventDefault();
      const drop = dropTargetFrom(event.target);
      clearDropTargets();
      if ($("#dropOverlay")) $("#dropOverlay").hidden = true;
      if (types.includes(INTERNAL)) {
        if (drop) moveItems(dragged.slice(), drop.path);
      } else if ($("#view")) {
        upload(event.dataTransfer.files, drop ? drop.path : currentPath());
      }
    });
  }

  /* ---------------- events ---------------- */

  let lastPointer = "mouse";

  function initEvents() {
    document.addEventListener("pointerdown", (event) => { lastPointer = event.pointerType; }, true);

    document.addEventListener("click", (event) => {
      if (!event.target.closest("#ctxMenu")) closeMenu();

      const copy = event.target.closest("[data-copy]");
      if (copy) return copyText(copy.dataset.copy);

      const more = event.target.closest("[data-more]");
      if (more) {
        event.preventDefault();
        const item = more.closest(".item");
        if (!item.classList.contains("selected")) select([item]);
        const rect = more.getBoundingClientRect();
        return showMenu(rect.left, rect.bottom + 4, itemMenu(selected()));
      }

      const item = event.target.closest("#files .item");
      if (item) {
        event.preventDefault();
        // Keyboard "click" on the name link, or a tap on touch screens, opens; mouse clicks select (Finder-style).
        if (event.detail === 0 || lastPointer === "touch") return openItem(item);
        if (event.metaKey || event.ctrlKey) {
          const next = selected().filter((node) => node !== item);
          if (!item.classList.contains("selected")) next.push(item);
          return select(next);
        }
        if (event.shiftKey && anchor) return selectRange(item);
        return select([item]);
      }
      if (event.target.closest("#files")) return select([]);

      const toggle = event.target.closest("[data-tree-toggle]");
      if (toggle) {
        const children = toggle.closest(".tree-node").querySelector(".tree-children");
        const open = children.hidden;
        children.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));
        if (open) loadTree(children);
        return;
      }

      const link = event.target.closest("a[href^='/browse']");
      if (link && $("#view") && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
        event.preventDefault();
        return navigate(link.getAttribute("href"));
      }

      const view = event.target.closest("[data-view]");
      if (view) return setView(view.dataset.view);

      const sortButton = event.target.closest("[data-sort]");
      if (sortButton) {
        const key = sortButton.dataset.sort;
        sort = sort.key === key ? { key, dir: -sort.dir } : { key, dir: key === "name" || key === "kind" ? 1 : -1 };
        try { localStorage.setItem("sb_sort", JSON.stringify(sort)); } catch (_error) { /* private mode */ }
        return applySort();
      }

      const scope = event.target.closest("[data-scope]");
      if (scope) return runSearch(scope.dataset.scope);

      const cmd = event.target.closest("[data-cmd]");
      if (cmd && cmd.dataset.cmd === "mkdir") return newFolder();
      if (cmd && cmd.dataset.cmd === "upload") return $("#fileInput").click();

      const nav = event.target.closest("[data-nav]");
      if (nav) return nav.dataset.nav === "back" ? history.back() : history.forward();

      if (event.target.closest("[data-sidebar-toggle]")) {
        return body.classList.toggle(isNarrow() ? "side-open" : "side-hidden");
      }
      if (event.target.closest("[data-sidebar-close]")) return body.classList.remove("side-open");
      if (event.target.closest("[data-ql-close]")) return closeQuickLook();
    });

    document.addEventListener("dblclick", (event) => {
      const item = event.target.closest("#files .item");
      if (item && !event.target.closest("[data-more]")) openItem(item);
    });

    document.addEventListener("contextmenu", (event) => {
      if (!event.target.closest("#files") || event.target.closest("input")) return;
      event.preventDefault();
      const item = event.target.closest(".item");
      if (item && !item.classList.contains("selected")) select([item]);
      if (!item) select([]);
      showMenu(event.clientX, event.clientY, item ? itemMenu(selected()) : backgroundMenu());
    });

    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", closeMenu);
    window.addEventListener("popstate", () => loadView(window.location.href));
    document.addEventListener("scroll", closeMenu, true);

    const search = $("#search");
    if (search) {
      search.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => runSearch(), 300);
      });
    }
    const fileInput = $("#fileInput");
    if (fileInput) {
      fileInput.addEventListener("change", () => {
        upload(fileInput.files, currentPath());
        fileInput.value = "";
      });
    }
  }

  function onKey(event) {
    const key0 = event.key;
    if (activeModal) {
      if (event.key === "Escape") closeModal(false);
      return;
    }
    const menu = $("#ctxMenu");
    if (menu && !menu.hidden) {
      const buttons = $all("button", menu);
      const index = buttons.indexOf(document.activeElement);
      if (event.key === "Escape") closeMenu();
      else if (event.key === "ArrowDown") buttons[(index + 1) % buttons.length].focus();
      else if (event.key === "ArrowUp") buttons[(index - 1 + buttons.length) % buttons.length].focus();
      else return;
      event.preventDefault();
      return;
    }
    if ((key0 === " " || key0 === "Enter") && event.target.matches("button, a")) return;
    if (event.target.matches("input, textarea, select")) {
      if (event.key === "Escape" && event.target.id === "search" && event.target.value) {
        event.target.value = "";
        runSearch();
      }
      return;
    }
    if (!$("#files")) return;

    const mod = event.metaKey || event.ctrlKey;
    const list = items();
    const picked = selected();
    const one = picked.length === 1 ? picked[0] : null;
    const key = event.key;

    if (mod && key.toLowerCase() === "f") {
      event.preventDefault();
      return $("#search").focus();
    }
    if (key === "Escape") return qlOpen() ? closeQuickLook() : select([]);
    if (key === " " && cursor) {
      event.preventDefault();
      return qlOpen() ? closeQuickLook() : quickLook(cursor);
    }
    if (mod && key.toLowerCase() === "a") {
      event.preventDefault();
      return select(list);
    }
    if (mod && key === "ArrowUp") {
      event.preventDefault();
      if (currentPath()) navigate(folderUrl(parentOf(currentPath())));
      return;
    }
    if ((key === "Enter" || (mod && key === "ArrowDown") || (mod && key.toLowerCase() === "o")) && one) {
      event.preventDefault();
      return openItem(one);
    }
    if (key === "F2" && one && !readonly) return renameItem(one);
    if ((key === "Delete" || (mod && key === "Backspace")) && picked.length && !readonly) {
      event.preventDefault();
      return deleteItems(picked);
    }

    const grid = $("#files").classList.contains("grid");
    const cols = grid ? getComputedStyle($("#files")).gridTemplateColumns.split(" ").length : 1;
    const moves = { ArrowDown: cols, ArrowUp: -cols, ArrowRight: grid ? 1 : 0, ArrowLeft: grid ? -1 : 0 };
    if (!(key in moves) || !list.length) return;
    event.preventDefault();
    const from = list.indexOf(cursor);
    const target = list[from < 0 ? 0 : Math.max(0, Math.min(list.length - 1, from + moves[key]))];
    if (event.shiftKey && anchor) selectRange(target);
    else select([target]);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initModal();
    initEvents();
    initDragDrop();
    afterRender();
    const root = $(".tree[data-tree-children='']");
    if (root) loadTree(root);
  });
})();
