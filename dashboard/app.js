// SecondMind dashboard — vanilla JS, no build step, no dependency.

const searchBox = document.getElementById("search-box");
const searchSpinner = document.getElementById("search-spinner");
const resultsList = document.getElementById("results");
const resultsEmpty = document.getElementById("results-empty");
const resultsNoMatch = document.getElementById("results-no-match");

const noteView = document.getElementById("note-view");
const noteViewTitle = document.getElementById("note-view-title");
const noteViewMeta = document.getElementById("note-view-meta");
const noteViewBody = document.getElementById("note-view-body");
const noteViewClose = document.getElementById("note-view-close");

let activeNoteId = null;

function renderList(items, { emptyKind } = {}) {
  resultsList.innerHTML = "";
  resultsEmpty.hidden = true;
  resultsNoMatch.hidden = true;

  if (items.length === 0) {
    if (emptyKind === "no-match") {
      resultsNoMatch.hidden = false;
    } else {
      resultsEmpty.hidden = false;
    }
    return;
  }

  for (const item of items) {
    const li = document.createElement("li");
    li.dataset.id = item.id;
    if (item.id === activeNoteId) li.classList.add("active");

    const titleSpan = document.createElement("span");
    titleSpan.textContent = item.title || item.id;
    li.appendChild(titleSpan);

    if (item.snippet) {
      const snippetSpan = document.createElement("span");
      snippetSpan.className = "result-snippet";
      snippetSpan.textContent = item.snippet;
      li.appendChild(snippetSpan);
    }

    li.addEventListener("click", () => showNote(item.id));
    resultsList.appendChild(li);
  }
}

async function loadAll() {
  try {
    const response = await fetch("/api/list");
    const payload = await response.json();
    renderList(payload.items);
  } catch (err) {
    renderList([]);
    console.error("SecondMind: failed to load notes", err);
  }
}

let searchAbort = null;

async function search(query) {
  if (!query) {
    return loadAll();
  }

  if (searchAbort) searchAbort.abort();
  searchAbort = new AbortController();

  searchSpinner.hidden = false;
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
      signal: searchAbort.signal,
    });
    const payload = await response.json();
    renderList(payload.results, { emptyKind: "no-match" });
  } catch (err) {
    if (err.name !== "AbortError") {
      renderList([], { emptyKind: "no-match" });
      console.error("SecondMind: search failed", err);
    }
  } finally {
    searchSpinner.hidden = true;
  }
}

async function showNote(id) {
  activeNoteId = id;
  for (const li of resultsList.children) {
    li.classList.toggle("active", li.dataset.id === id);
  }

  const response = await fetch(`/api/note/${encodeURIComponent(id)}`);
  if (!response.ok) {
    noteViewTitle.textContent = "Note not found";
    noteViewMeta.textContent = "";
    noteViewBody.textContent = "It may have been deleted or superseded.";
    noteView.hidden = false;
    return;
  }
  const note = await response.json();
  noteViewTitle.textContent = note.title || note.id;
  noteViewMeta.textContent = `${note.type} · updated ${note.updated}${note.tags?.length ? " · " + note.tags.join(", ") : ""}`;
  noteViewBody.textContent = note.body;
  noteView.hidden = false;
}

noteViewClose.addEventListener("click", () => {
  noteView.hidden = true;
  activeNoteId = null;
  for (const li of resultsList.children) li.classList.remove("active");
});

let debounceTimer = null;
searchBox.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => search(searchBox.value.trim()), 200);
});

const newNoteType = document.getElementById("new-note-type");
const newNoteTitle = document.getElementById("new-note-title");
const newNoteBody = document.getElementById("new-note-body");
const newNoteSubmit = document.getElementById("new-note-submit");
const newNoteStatus = document.getElementById("new-note-status");

newNoteSubmit.addEventListener("click", async () => {
  if (!newNoteTitle.value.trim() || !newNoteBody.value.trim()) {
    newNoteStatus.textContent = "Title and body are both required.";
    newNoteStatus.className = "error";
    return;
  }

  newNoteSubmit.disabled = true;
  newNoteStatus.textContent = "Saving...";
  newNoteStatus.className = "";

  try {
    const response = await fetch("/api/put", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: newNoteType.value,
        title: newNoteTitle.value,
        body: newNoteBody.value,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      newNoteStatus.textContent = `Error: ${error.error}`;
      newNoteStatus.className = "error";
      return;
    }
    newNoteStatus.textContent = "Saved.";
    newNoteTitle.value = "";
    newNoteBody.value = "";
    loadAll();
  } catch (err) {
    newNoteStatus.textContent = "Could not reach the server — is it still running?";
    newNoteStatus.className = "error";
  } finally {
    newNoteSubmit.disabled = false;
  }
});

const settingsToggle = document.getElementById("settings-toggle");
const settingsPanel = document.getElementById("settings-panel");
const settingsVault = document.getElementById("settings-vault");
const settingsIndex = document.getElementById("settings-index");
const settingsCount = document.getElementById("settings-count");

settingsToggle.addEventListener("click", async () => {
  const opening = settingsPanel.hidden;
  settingsPanel.hidden = !opening;
  if (!opening) return;

  try {
    const response = await fetch("/api/settings");
    const payload = await response.json();
    settingsVault.textContent = payload.vault_dir;
    settingsIndex.textContent = payload.index_db;
    settingsCount.textContent = payload.note_count;
  } catch (err) {
    settingsVault.textContent = "(could not load — is the server still running?)";
    settingsIndex.textContent = "—";
    settingsCount.textContent = "—";
  }
});

loadAll();
