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

loadAll();
