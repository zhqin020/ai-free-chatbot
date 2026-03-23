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

	getDispatchMode() {
		return this.request("/api/providers/app-params");
	},

	updateDispatchMode(payload) {
		return this.request("/api/providers/app-params", {
			method: "PUT",
			body: JSON.stringify(payload),
		});
	},
};

const state = {
	providers: [],
	editingName: null,
	toastTimer: null,
};

const nodes = {
	form: document.getElementById("provider-form"),
	dispatchForm: document.getElementById("dispatch-form"),
	dispatchMode: document.getElementById("dispatch-mode"),
	dispatchMaxRounds: document.getElementById("dispatch-max-rounds"),
	formTitle: document.getElementById("form-title"),
	editingName: document.getElementById("editing-name"),
	name: document.getElementById("provider-name"),
	url: document.getElementById("provider-url"),
	icon: document.getElementById("provider-icon"),
	iconPicker: document.getElementById("provider-icon-picker"),
	needLogin: document.getElementById("provider-need-login"),
	enable: document.getElementById("provider-enable"),
	lock: document.getElementById("provider-lock"),
	submit: document.getElementById("submit-btn"),
	reset: document.getElementById("reset-btn"),
	refresh: document.getElementById("refresh-btn"),
	stats: document.getElementById("stats"),
	rows: document.getElementById("provider-rows"),
	toast: document.getElementById("toast"),
};

function setIconValue(icon) {
	nodes.icon.value = icon;
	const chips = nodes.iconPicker?.querySelectorAll("button[data-icon]") || [];
	for (const chip of chips) {
		chip.classList.toggle("active", chip.dataset.icon === icon);
	}
}

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
	setIconValue("🤖");
	nodes.name.disabled = false;
	if (nodes.needLogin) nodes.needLogin.checked = false;
	if (nodes.enable) nodes.enable.checked = true;
	if (nodes.lock) nodes.lock.checked = false;
	nodes.formTitle.textContent = "Create Provider";
	nodes.submit.textContent = "Create";
}

function fillForEdit(row) {
	state.editingName = row.name;
	nodes.editingName.value = row.name;
	nodes.name.value = row.name;
	nodes.url.value = row.url;
	setIconValue(row.icon);
	nodes.name.disabled = true;
	if (nodes.needLogin) nodes.needLogin.checked = (row.need_login ?? false);
	if (nodes.enable) nodes.enable.checked = (row.enable ?? true);
	if (nodes.lock) nodes.lock.checked = (row.lock ?? false);
	nodes.formTitle.textContent = `Edit Provider: ${row.name}`;
	nodes.submit.textContent = "Update";
}

function renderRows() {
	nodes.rows.innerHTML = "";
	const rows = [...state.providers].sort((a, b) => a.name.localeCompare(b.name));
	for (const row of rows) {
		const tr = document.createElement("tr");
		const deleteAction = (row.builtin || row.lock)
			? ""
			: `<button type="button" class="btn btn-danger" data-action="delete" data-name="${row.name}">Delete</button>`;
			
		const flags = [];
		if (row.need_login) flags.push("Login");
		if (row.enable) flags.push("E");
		if (row.lock) flags.push("L");
		const flagsText = flags.length ? flags.join(",") : "-";

		tr.innerHTML = `
      <td><strong>${row.name}</strong>${row.builtin ? " <span class=\"muted\">(builtin)</span>" : ""}</td>
      <td class="icon-cell">${row.icon}</td>
      <td><span class="muted">[${flagsText}]</span></td>
      <td>${row.url}</td>
      <td>${row.session_provider || "-"}</td>
      <td>${new Date(row.updated_at).toLocaleString()}</td>
      <td>
        <div class="actions">
          <button type="button" class="btn btn-secondary" data-action="edit" data-name="${row.name}">Edit</button>
          <button type="button" class="btn btn-secondary" data-action="open" data-name="${row.name}">Open Browser</button>
          <button type="button" class="btn btn-secondary" data-action="view" data-name="${row.name}">View Session</button>
          <button type="button" class="btn btn-secondary" data-action="clear" data-name="${row.name}">Clear Session</button>
					${deleteAction}
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
		need_login: nodes.needLogin ? nodes.needLogin.checked : false,
		enable: nodes.enable ? nodes.enable.checked : true,
		lock: nodes.lock ? nodes.lock.checked : false,
	};
}

async function loadDispatchMode() {
	const row = await api.getDispatchMode();
	if (row?.mode) {
		nodes.dispatchMode.value = row.mode;
	}
	if (row?.max_chat_rounds !== undefined) {
		nodes.dispatchMaxRounds.value = row.max_chat_rounds;
	}
}

async function handleDispatchSubmit(event) {
	event.preventDefault();
	const mode = nodes.dispatchMode.value;
	const max_chat_rounds = parseInt(nodes.dispatchMaxRounds.value, 10) || 0;
	await api.updateDispatchMode({ mode, max_chat_rounds });
	showToast(`参数已更新: 分配=${mode === "round_robin" ? "循环" : "按优先级"}, 轮数=${max_chat_rounds}`);
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
		await api.updateProvider(state.editingName, { 
			url: payload.url, 
			icon: payload.icon,
			need_login: payload.need_login,
			enable: payload.enable,
			lock: payload.lock 
		});
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
		if (result?.opened_in_server) {
			showToast(result.open_message || `已在服务器浏览器打开: ${name}`);
		} else {
			showToast(result?.open_message || `服务器浏览器打开失败: ${name}`);
		}
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
		if (row.builtin) {
			showToast(`Builtin provider cannot be deleted: ${name}`);
			return;
		}

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

	nodes.dispatchForm.addEventListener("submit", (event) => {
		handleDispatchSubmit(event).catch((err) => showToast(err.message));
	});

	nodes.reset.addEventListener("click", () => {
		resetForm();
		showToast("Form reset");
	});

	nodes.refresh.addEventListener("click", () => {
		reload().then(() => showToast("Refreshed")).catch((err) => showToast(err.message));
	});

	nodes.iconPicker.addEventListener("click", (event) => {
		const button = event.target.closest("button[data-icon]");
		if (!button) return;
		setIconValue(button.dataset.icon || "🤖");
	});

	nodes.rows.addEventListener("click", (event) => {
		handleAction(event).catch((err) => showToast(err.message));
	});

	resetForm();
	await loadDispatchMode();
	await reload();
}

init().catch((err) => showToast(err.message));
