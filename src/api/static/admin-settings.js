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
				// noop
			}
			throw new Error(detail);
		}

		const text = await response.text();
		return text ? JSON.parse(text) : null;
	},

	listProviders() {
		return this.request("/api/providers");
	},

	createProvider(payload) {
		return this.request("/api/providers", { method: "POST", body: JSON.stringify(payload) });
	},

	updateProvider(name, payload) {
		return this.request(`/api/providers/${encodeURIComponent(name)}`, {
			method: "PUT",
			body: JSON.stringify(payload),
		});
	},

	deleteProvider(name) {
		return this.request(`/api/providers/${encodeURIComponent(name)}`, { method: "DELETE" });
	},

	openBrowser(name) {
		return this.request(`/api/providers/${encodeURIComponent(name)}/open-browser`, { method: "POST" });
	},

	clearSessions(name) {
		return this.request(`/api/providers/${encodeURIComponent(name)}/clear-sessions`, { method: "POST" });
	},

	getSessionTarget(name) {
		return this.request(`/api/providers/${encodeURIComponent(name)}/session-target`);
	},
};

const state = {
	providers: [],
	editingName: null,
	toastTimer: null,
};

const nodes = {
	form: document.getElementById("provider-form"),
	formTitle: document.getElementById("form-title"),
	editingName: document.getElementById("editing-name"),
	name: document.getElementById("provider-name"),
	url: document.getElementById("provider-url"),
	icon: document.getElementById("provider-icon"),
	submit: document.getElementById("submit-btn"),
	reset: document.getElementById("reset-btn"),
	refresh: document.getElementById("refresh-btn"),
	stats: document.getElementById("stats"),
	rows: document.getElementById("provider-rows"),
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
	state.editingName = null;
	nodes.editingName.value = "";
	nodes.name.value = "";
	nodes.url.value = "";
	nodes.icon.value = "";
	nodes.name.disabled = false;
	nodes.formTitle.textContent = "Create Provider";
	nodes.submit.textContent = "Create";
}

function fillForEdit(row) {
	state.editingName = row.name;
	nodes.editingName.value = row.name;
	nodes.name.value = row.name;
	nodes.url.value = row.url;
	nodes.icon.value = row.icon;
	nodes.name.disabled = true;
	nodes.formTitle.textContent = `Edit Provider: ${row.name}`;
	nodes.submit.textContent = "Update";
}

function renderRows() {
	nodes.rows.innerHTML = "";
	const rows = [...state.providers].sort((a, b) => a.name.localeCompare(b.name));
	for (const row of rows) {
		const tr = document.createElement("tr");
		tr.innerHTML = `
      <td><strong>${row.name}</strong>${row.builtin ? " <span class=\"muted\">(builtin)</span>" : ""}</td>
      <td class="icon-cell">${row.icon}</td>
      <td>${row.url}</td>
      <td>${row.session_provider || "-"}</td>
      <td>${new Date(row.updated_at).toLocaleString()}</td>
      <td>
        <div class="actions">
          <button type="button" class="btn btn-secondary" data-action="edit" data-name="${row.name}">Edit</button>
          <button type="button" class="btn btn-secondary" data-action="open" data-name="${row.name}">Open Browser</button>
          <button type="button" class="btn btn-secondary" data-action="view" data-name="${row.name}">View Session</button>
          <button type="button" class="btn btn-secondary" data-action="clear" data-name="${row.name}">Clear Session</button>
          <button type="button" class="btn btn-danger" data-action="delete" data-name="${row.name}">Delete</button>
        </div>
      </td>
    `;
		nodes.rows.appendChild(tr);
	}
	nodes.stats.textContent = `Total: ${rows.length}`;
}

async function reload() {
	state.providers = await api.listProviders();
	renderRows();
}

function readPayload() {
	return {
		name: nodes.name.value.trim(),
		url: nodes.url.value.trim(),
		icon: nodes.icon.value.trim(),
	};
}

async function handleSubmit(event) {
	event.preventDefault();
	const payload = readPayload();
	if (!payload.name) {
		showToast("Provider name is required.");
		return;
	}
	if (!payload.url) {
		showToast("Provider url is required.");
		return;
	}
	if (!payload.icon) {
		showToast("Provider icon is required.");
		return;
	}

	if (state.editingName) {
		await api.updateProvider(state.editingName, { url: payload.url, icon: payload.icon });
		showToast(`Provider updated: ${state.editingName}`);
	} else {
		await api.createProvider(payload);
		showToast(`Provider created: ${payload.name}`);
	}

	await reload();
	resetForm();
}

async function handleAction(event) {
	const button = event.target.closest("button[data-action]");
	if (!button) return;

	const action = button.dataset.action;
	const name = button.dataset.name;
	const row = state.providers.find((item) => item.name === name);
	if (!row) {
		showToast(`Provider not found: ${name}`);
		return;
	}

	if (action === "edit") {
		fillForEdit(row);
		return;
	}

	if (action === "open") {
		const result = await api.openBrowser(name);
		if (result?.url) {
			window.open(result.url, "_blank", "noopener,noreferrer");
		}
		showToast(`Opened: ${name}`);
		return;
	}

	if (action === "view") {
		const result = await api.getSessionTarget(name);
		window.location.href = result?.sessions_url || "/admin/sessions";
		return;
	}

	if (action === "clear") {
		const ok = window.confirm(`Clear sessions for provider ${name}?`);
		if (!ok) return;
		const result = await api.clearSessions(name);
		showToast(`Sessions cleared: ${result.cleared_count}`);
		return;
	}

	if (action === "delete") {
		const ok = window.confirm(`Delete provider ${name}?`);
		if (!ok) return;
		await api.deleteProvider(name);
		showToast(`Deleted: ${name}`);
		if (state.editingName === name) {
			resetForm();
		}
		await reload();
	}
}

async function init() {
	nodes.form.addEventListener("submit", (event) => {
		handleSubmit(event).catch((err) => showToast(err.message));
	});

	nodes.reset.addEventListener("click", () => {
		resetForm();
		showToast("Form reset");
	});

	nodes.refresh.addEventListener("click", () => {
		reload().then(() => showToast("Refreshed")).catch((err) => showToast(err.message));
	});

	nodes.rows.addEventListener("click", (event) => {
		handleAction(event).catch((err) => showToast(err.message));
	});

	resetForm();
	await reload();
}

init().catch((err) => showToast(err.message));
