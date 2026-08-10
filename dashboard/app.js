// SecondMind dashboard — vanilla JS, no build step, no dependency.

const searchBox = document.getElementById("search-box");
const resultsList = document.getElementById("results");
const noteView = document.getElementById("note-view");

async function renderList(items) {
  resultsList.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item.title || item.id;
    li.addEventListener("click", () => showNote(item.id));
    resultsList.appendChild(li);
  }
}

async function loadAll() {
  const response = await fetch("/api/list");
  const payload = await response.json();
  renderList(payload.items);
}

async function search(query) {
  if (!query) {
    return loadAll();
  }
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  const payload = await response.json();
  renderList(payload.results);
}

async function showNote(id) {
  const response = await fetch(`/api/note/${encodeURIComponent(id)}`);
  if (!response.ok) {
    noteView.textContent = "Note not found.";
    noteView.style.display = "block";
    return;
  }
  const note = await response.json();
  noteView.textContent = `${note.title}\n\n${note.body}`;
  noteView.style.display = "block";
}

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
  newNoteStatus.textContent = "Saving...";
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
    return;
  }
  newNoteStatus.textContent = "Saved.";
  newNoteTitle.value = "";
  newNoteBody.value = "";
  loadAll();
});

loadAll();
