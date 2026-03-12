const api = {
	async request(path, options = {}) {
		const response = await fetch(path, {
			headers: { "Content-Type": "application/json" },
			...options,
		});
		if (!response.ok) {
			let detail = `${response.status} ${response.statusText}`;
			try {
				const body = await response.json();
				if (body && body.detail) {
					detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
				}
			} catch (_err) {
				// noop: keep generic detail
			}
			throw new Error(detail);
		}
		const text = await response.text();
		return text ? JSON.parse(text) : null;
	},

	listSessions() {
		return this.request("/api/sessions");
	},

	discoverSessions() {
		return this.request("/api/sessions/discover", { method: "POST" });
	},

	createSession(payload) {
		return this.request("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
	},

	updateSession(id, payload) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}`, {
			method: "PUT",
			body: JSON.stringify(payload),
		});
	},

	deleteSession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
	},

	markLoginOk(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/mark-login-ok`, { method: "POST" });
	},

	openSession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/open`, { method: "POST" });
	},

	listErrors() {
		return this.request("/api/logs?level=ERROR&page=1&page_size=20");
	},
};

const state = {
	sessions: [],
	filteredSessions: [],
	selectedIds: new Set(),
	filters: {
		keyword: "",
		provider: "all",
		status: "all",
		enabled: "all",
	},
	editingId: null,
	toastTimer: null,
};

const nodes = {
	form: document.getElementById("session-form"),
	formTitle: document.getElementById("form-title"),
	submitBtn: document.getElementById("submit-btn"),
	resetBtn: document.getElementById("reset-form"),
	refreshBtn: document.getElementById("refresh-btn"),
	editingId: document.getElementById("editing-id"),
	id: document.getElementById("session-id"),
	provider: document.getElementById("provider"),
	chatUrl: document.getElementById("chat-url"),
	priority: document.getElementById("priority"),
	enabled: document.getElementById("enabled"),
	rows: document.getElementById("session-rows"),
	countTotal: document.getElementById("count-total"),
	countFiltered: document.getElementById("count-filtered"),
	countEnabled: document.getElementById("count-enabled"),
	countWaitLogin: document.getElementById("count-wait-login"),
	filterKeyword: document.getElementById("filter-keyword"),
	filterProvider: document.getElementById("filter-provider"),
	filterState: document.getElementById("filter-state"),
	filterEnabled: document.getElementById("filter-enabled"),
	clearFilters: document.getElementById("clear-filters"),
	selectedCount: document.getElementById("selected-count"),
	selectFiltered: document.getElementById("select-filtered"),
	clearSelection: document.getElementById("clear-selection"),
	batchEnable: document.getElementById("batch-enable"),
	batchDisable: document.getElementById("batch-disable"),
	errorSummary: document.getElementById("error-summary"),
	errorRows: document.getElementById("error-rows"),
	refreshErrors: document.getElementById("refresh-errors"),
	toast: document.getElementById("toast"),
};

function showToast(message) {
	nodes.toast.textContent = message;
	nodes.toast.classList.add("show");
	clearTimeout(state.toastTimer);
	state.toastTimer = setTimeout(() => {
		nodes.toast.classList.remove("show");
	}, 2200);
}

function resetForm() {
	state.editingId = null;
	nodes.editingId.value = "";
	nodes.id.value = "";
	nodes.provider.value = "openchat";
	nodes.chatUrl.value = "";
	nodes.priority.value = "100";
	nodes.enabled.checked = true;
	nodes.id.disabled = false;
	nodes.formTitle.textContent = "Create Session";
	nodes.submitBtn.textContent = "Create";
}

function fillFormForEdit(session) {
	state.editingId = session.id;
	nodes.editingId.value = session.id;
	nodes.id.value = session.id;
	nodes.provider.value = session.provider;
	nodes.chatUrl.value = session.chat_url;
	nodes.priority.value = String(session.priority);
	nodes.enabled.checked = !!session.enabled;
	nodes.id.disabled = true;
	nodes.formTitle.textContent = `Edit Session: ${session.id}`;
	nodes.submitBtn.textContent = "Update";
}

function stateBadgeClass(sessionState) {
	if (sessionState === "READY") return "badge badge-ready";
	if (sessionState === "WAIT_LOGIN") return "badge badge-wait";
	return "badge badge-other";
}

function renderRows() {
	const sessions = [...state.filteredSessions].sort((a, b) => a.id.localeCompare(b.id));
	nodes.rows.innerHTML = "";

	for (const session of sessions) {
		const isSelected = state.selectedIds.has(session.id);
		const tr = document.createElement("tr");
		tr.innerHTML = `
      <td>
        <input type="checkbox" data-select-id="${session.id}" ${isSelected ? "checked" : ""} />
      </td>
      <td><strong>${session.id}</strong></td>
      <td>${session.provider}</td>
      <td><span class="${stateBadgeClass(session.state)}">${session.state}</span></td>
      <td>${session.login_state}</td>
      <td>${session.priority}</td>
      <td>${session.enabled ? "yes" : "no"}</td>
      <td>${new Date(session.updated_at).toLocaleString()}</td>
      <td>
        <div class="row-actions">
		  <button type="button" class="btn btn-mini btn-secondary" data-action="login-ok" data-id="${session.id}">Mark Ready</button>
		  <button type="button" class="btn btn-mini btn-secondary" data-action="open" data-id="${session.id}">Open</button>
        </div>
      </td>
    `;
		nodes.rows.appendChild(tr);
	}

	const enabledCount = sessions.filter((s) => s.enabled).length;
	const waitLoginCount = sessions.filter((s) => s.state === "WAIT_LOGIN").length;
	nodes.countTotal.textContent = `Total: ${state.sessions.length}`;
	nodes.countFiltered.textContent = `Filtered: ${sessions.length}`;
	nodes.countEnabled.textContent = `Enabled: ${enabledCount}`;
	nodes.countWaitLogin.textContent = `Wait login: ${waitLoginCount}`;
	nodes.selectedCount.textContent = `Selected: ${state.selectedIds.size}`;
}

function applyFilters() {
	const keyword = state.filters.keyword.trim().toLowerCase();
	state.filteredSessions = state.sessions.filter((session) => {
		if (state.filters.provider !== "all" && session.provider !== state.filters.provider) {
			return false;
		}
		if (state.filters.status !== "all" && session.state !== state.filters.status) {
			return false;
		}
		if (state.filters.enabled === "yes" && !session.enabled) {
			return false;
		}
		if (state.filters.enabled === "no" && session.enabled) {
			return false;
		}
		if (!keyword) {
			return true;
		}
		const haystack = `${session.id} ${session.provider} ${session.state} ${session.login_state}`.toLowerCase();
		return haystack.includes(keyword);
	});

	const visibleIds = new Set(state.filteredSessions.map((row) => row.id));
	state.selectedIds = new Set([...state.selectedIds].filter((id) => visibleIds.has(id)));
	renderRows();
}

function clearFilters() {
	state.filters.keyword = "";
	state.filters.provider = "all";
	state.filters.status = "all";
	state.filters.enabled = "all";
	nodes.filterKeyword.value = "";
	nodes.filterProvider.value = "all";
	nodes.filterState.value = "all";
	nodes.filterEnabled.value = "all";
	applyFilters();
}

async function reloadErrors() {
	const response = await api.listErrors();
	const items = response?.items || [];
	nodes.errorRows.innerHTML = "";

	if (!items.length) {
		nodes.errorSummary.innerHTML = '<p class="muted">No recent errors.</p>';
		return;
	}

	const bySession = new Map();
	for (const item of items) {
		const key = item.session_id || "unknown";
		bySession.set(key, (bySession.get(key) || 0) + 1);
	}

	const chips = [...bySession.entries()]
		.sort((a, b) => b[1] - a[1])
		.slice(0, 5)
		.map(([sessionId, count]) => `<span class="chip">${sessionId}: ${count}</span>`)
		.join("");
	nodes.errorSummary.innerHTML = chips || '<p class="muted">No recent errors.</p>';

	for (const item of items.slice(0, 12)) {
		const tr = document.createElement("tr");
		tr.innerHTML = `
      <td>${new Date(item.created_at).toLocaleString()}</td>
      <td>${item.level}</td>
      <td>${item.provider || "-"}</td>
      <td>${item.session_id || "-"}</td>
      <td>${item.event}</td>
      <td>${item.message}</td>
    `;
		nodes.errorRows.appendChild(tr);
	}
}

function readFormPayload() {
	return {
		id: nodes.id.value.trim(),
		provider: nodes.provider.value,
		chat_url: nodes.chatUrl.value.trim(),
		enabled: !!nodes.enabled.checked,
		priority: Number(nodes.priority.value),
	};
}

async function reloadSessions() {
	state.sessions = await api.listSessions();
	applyFilters();
}

async function discoverAndReloadSessions() {
	await api.discoverSessions();
	await reloadSessions();
}

async function batchSetEnabled(enabled) {
	const targets = state.sessions.filter((row) => state.selectedIds.has(row.id));
	if (!targets.length) {
		showToast("Select at least one session first.");
		return;
	}

	for (const row of targets) {
		if (row.enabled === enabled) continue;
		await api.updateSession(row.id, {
			provider: row.provider,
			chat_url: row.chat_url,
			enabled,
			priority: row.priority,
		});
	}

	showToast(`Batch ${enabled ? "enabled" : "disabled"}: ${targets.length}`);
	await reloadSessions();
}

async function handleSubmit(event) {
	event.preventDefault();
	showToast("Manual create/update is disabled. Sessions are discovered from Provider settings.");
}

async function handleRowAction(event) {
	const button = event.target.closest("button[data-action]");
	if (!button) return;

	const action = button.dataset.action;
	const id = button.dataset.id;
	const row = state.sessions.find((s) => s.id === id);
	if (!row) {
		showToast(`Session not found: ${id}`);
		return;
	}

	if (action === "login-ok") {
		await api.markLoginOk(id);
		showToast(`Session marked ready: ${id}`);
	}

	if (action === "open") {
		const result = await api.openSession(id);
		if (result && result.chat_url) {
			window.open(result.chat_url, "_blank", "noopener,noreferrer");
		}
		showToast(`Open link for: ${id}`);
	}

	await reloadSessions();
}

async function init() {
	nodes.form.addEventListener("submit", (event) => {
		handleSubmit(event).catch((err) => showToast(err.message));
	});

	nodes.resetBtn.addEventListener("click", () => {
		resetForm();
		showToast("Manual form is disabled in discovery mode");
	});

	nodes.refreshBtn.addEventListener("click", () => {
		Promise.all([discoverAndReloadSessions(), reloadErrors()])
			.then(() => showToast("Discovered and refreshed"))
			.catch((err) => showToast(err.message));
	});

	nodes.rows.addEventListener("click", (event) => {
		handleRowAction(event).catch((err) => showToast(err.message));
	});

	nodes.rows.addEventListener("change", (event) => {
		const checkbox = event.target.closest("input[data-select-id]");
		if (!checkbox) return;
		const id = checkbox.dataset.selectId;
		if (!id) return;
		if (checkbox.checked) {
			state.selectedIds.add(id);
		} else {
			state.selectedIds.delete(id);
		}
		nodes.selectedCount.textContent = `Selected: ${state.selectedIds.size}`;
	});

	nodes.filterKeyword.addEventListener("input", (event) => {
		state.filters.keyword = event.target.value || "";
		applyFilters();
	});
	nodes.filterProvider.addEventListener("change", (event) => {
		state.filters.provider = event.target.value;
		applyFilters();
	});
	nodes.filterState.addEventListener("change", (event) => {
		state.filters.status = event.target.value;
		applyFilters();
	});
	nodes.filterEnabled.addEventListener("change", (event) => {
		state.filters.enabled = event.target.value;
		applyFilters();
	});
	nodes.clearFilters.addEventListener("click", () => {
		clearFilters();
		showToast("Filters cleared");
	});

	nodes.selectFiltered.addEventListener("click", () => {
		for (const row of state.filteredSessions) {
			state.selectedIds.add(row.id);
		}
		renderRows();
		showToast(`Selected ${state.filteredSessions.length} sessions`);
	});

	nodes.clearSelection.addEventListener("click", () => {
		state.selectedIds.clear();
		renderRows();
		showToast("Selection cleared");
	});

	nodes.batchEnable.addEventListener("click", () => {
		showToast("Batch enable is disabled in discovery mode.");
	});

	nodes.batchDisable.addEventListener("click", () => {
		showToast("Batch disable is disabled in discovery mode.");
	});

	nodes.refreshErrors.addEventListener("click", () => {
		reloadErrors().then(() => showToast("Errors refreshed")).catch((err) => showToast(err.message));
	});

	resetForm();
	clearFilters();
	const formPanel = document.querySelector('section[aria-label="Session form"]');
	if (formPanel) {
		formPanel.style.display = "none";
	}
	const batchBar = document.querySelector(".batch-bar");
	if (batchBar) {
		batchBar.style.display = "none";
	}
	const queryProvider = new URLSearchParams(window.location.search).get("provider");
	if (queryProvider && [...nodes.filterProvider.options].some((opt) => opt.value === queryProvider)) {
		state.filters.provider = queryProvider;
		nodes.filterProvider.value = queryProvider;
	}
	await Promise.all([discoverAndReloadSessions(), reloadErrors()]);
}

init().catch((err) => showToast(err.message));
