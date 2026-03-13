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
		return this.request("/api/sessions?enabled_only=true");
	},

	discoverSessions() {
		return this.request("/api/sessions/discover", { method: "POST" });
	},

	markLoginOk(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/mark-login-ok`, { method: "POST" });
	},

	openSession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/open`, { method: "POST" });
	},

	rebuildSession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/rebuild`, { method: "POST" });
	},

	getSessionStats(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/stats`);
	},

	probeHttpSession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/http-session`);
	},

	verifySession(id) {
		return this.request(`/api/sessions/${encodeURIComponent(id)}/verify`, { method: "POST" });
	},

	listErrors() {
		return this.request("/api/logs?level=ERROR&page=1&page_size=20");
	},
};

const state = {
	sessions: [],
	filteredSessions: [],
	openedWindows: new Map(),
	filters: {
		keyword: "",
		provider: "all",
		status: "all",
		enabled: "all",
	},
	toastTimer: null,
};

const nodes = {
	refreshBtn: document.getElementById("refresh-btn"),
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

function stateBadgeClass(sessionState) {
	if (sessionState === "READY") return "badge badge-ready";
	if (sessionState === "WAIT_LOGIN") return "badge badge-wait";
	return "badge badge-other";
}

function renderRows() {
	const sessions = [...state.filteredSessions].sort((a, b) => a.id.localeCompare(b.id));
	nodes.rows.innerHTML = "";

	for (const session of sessions) {
		const tr = document.createElement("tr");
		tr.innerHTML = `
      <td><strong>${session.id}</strong></td>
		<td>${session.session_name || "-"}</td>
		<td>${session.http_session_id || "-"}</td>
      <td>${session.provider}</td>
      <td><span class="${stateBadgeClass(session.state)}">${session.state}</span></td>
      <td>${session.login_state}</td>
		<td>${session.start_time ? new Date(session.start_time).toLocaleString() : "-"}</td>
      <td>${session.priority}</td>
      <td>${session.enabled ? "yes" : "no"}</td>
      <td>${new Date(session.updated_at).toLocaleString()}</td>
      <td>
        <div class="row-actions">
		  <button type="button" class="btn btn-mini btn-secondary" data-action="stats" data-id="${session.id}">统计</button>
		  <button type="button" class="btn btn-mini btn-secondary" data-action="probe" data-id="${session.id}">验证会话</button>
		  <button type="button" class="btn btn-mini btn-secondary" data-action="login-ok" data-id="${session.id}">标记就绪</button>
		  <button type="button" class="btn btn-mini btn-secondary" data-action="open" data-id="${session.id}">打开页面</button>
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
		nodes.errorSummary.innerHTML = '<p class="muted">暂无错误。</p>';
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

async function reloadSessions() {
	state.sessions = await api.listSessions();
	applyFilters();
}

async function discoverAndReloadSessions() {
	await api.discoverSessions();
	await reloadSessions();
}

async function handleRowAction(event) {
	const button = event.target.closest("button[data-action]");
	if (!button) return;

	const action = button.dataset.action;
	const id = button.dataset.id;
	const row = state.sessions.find((s) => s.id === id);
	if (!row) {
		showToast(`会话不存在: ${id}`);
		return;
	}

	if (action === "login-ok") {
		await api.markLoginOk(id);
		showToast(`已标记就绪: ${id}`);
	}

	if (action === "probe") {
		const result = await api.verifySession(id);
		if (result?.deleted) {
			showToast(`会话已删除: ${id}`);
			await reloadSessions();
			return;
		}
		if (result?.tracked && result?.composed_session_id) {
			showToast(`会话有效（浏览器实时 cookie 一致）: ${result.composed_session_id}`);
		} else {
			showToast(result?.reason || "无法从浏览器读取实时 cookie，请人工确认登录状态");
		}
	}

	if (action === "open") {
		const result = await api.openSession(id);
		if (result?.requires_rebuild_confirmation) {
			const confirmed = window.confirm(
				`${result.warning || "HTTP session changed."}\n\n是否删除并重建当前会话记录？`
			);
			if (confirmed) {
				await api.rebuildSession(id);
				showToast(`会话已重建: ${id}`);
				await discoverAndReloadSessions();
				return;
			}
		}
		if (result?.warning) {
			showToast(`会话打开提示: ${result.warning}`);
		} else {
			showToast(`已在服务器浏览器打开会话页面: ${id}`);
		}
	}

	if (action === "stats") {
		const result = await api.getSessionStats(id);
		showToast(result?.message || "统计功能待实现");
	}

	await reloadSessions();
}

async function init() {
	nodes.refreshBtn.addEventListener("click", () => {
		Promise.all([discoverAndReloadSessions(), reloadErrors()])
			.then(() => showToast("发现并刷新完成"))
			.catch((err) => showToast(err.message));
	});

	nodes.rows.addEventListener("click", (event) => {
		handleRowAction(event).catch((err) => showToast(err.message));
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
		showToast("筛选已清空");
	});

	nodes.refreshErrors.addEventListener("click", () => {
		reloadErrors().then(() => showToast("错误摘要已刷新")).catch((err) => showToast(err.message));
	});

	clearFilters();
	const queryProvider = new URLSearchParams(window.location.search).get("provider");
	if (queryProvider && [...nodes.filterProvider.options].some((opt) => opt.value === queryProvider)) {
		state.filters.provider = queryProvider;
		nodes.filterProvider.value = queryProvider;
	}
	await Promise.all([discoverAndReloadSessions(), reloadErrors()]);
}

init().catch((err) => showToast(err.message));
