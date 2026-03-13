const $ = (id) => document.getElementById(id);

const hostInput = $("host-input");
const portInput = $("port-input");
const reloadInput = $("reload-input");

const runningText = $("running-text");
const pidText = $("pid-text");
const managedText = $("managed-text");
const uptimeText = $("uptime-text");
const urlText = $("url-text");
const startedAtText = $("started-at-text");
const commandText = $("command-text");
const messageText = $("message-text");

const refreshBtn = $("refresh-btn");
const startBtn = $("start-btn");
const stopBtn = $("stop-btn");
const openPageBtn = $("open-page-btn");
const toast = $("toast");

function parsePort() {
	const value = Number.parseInt(portInput.value, 10);
	if (!Number.isInteger(value) || value < 1 || value > 65535) {
		throw new Error("端口必须是 1-65535 的整数");
	}
	return value;
}

function getHost() {
	const host = (hostInput.value || "").trim();
	if (!host) {
		throw new Error("Host 不能为空");
	}
	return host;
}

function setBusy(busy) {
	refreshBtn.disabled = busy;
	startBtn.disabled = busy;
	stopBtn.disabled = busy;
	openPageBtn.disabled = busy;
	hostInput.disabled = busy;
	portInput.disabled = busy;
	reloadInput.disabled = busy;
}

function showToast(message, isError = false) {
	toast.textContent = message;
	toast.style.color = isError ? "#9e1e1e" : "#33445f";
}

function renderStatus(status) {
	if (!status) {
		showToast("状态为空", true);
		return;
	}

	runningText.textContent = status.running ? "running" : "stopped";
	runningText.classList.toggle("running", Boolean(status.running));
	runningText.classList.toggle("stopped", !status.running);
	pidText.textContent = status.pid ?? "-";
	managedText.textContent = status.managed_by_api ? "yes" : "no";
	uptimeText.textContent = status.uptime_seconds ?? "-";
	urlText.textContent = status.url ?? "-";
	startedAtText.textContent = status.started_at ?? "-";
	commandText.textContent = status.command ?? "-";
	messageText.textContent = status.message ?? "-";

	if (status.host) {
		hostInput.value = status.host;
	}
	if (status.port) {
		portInput.value = String(status.port);
	}

	if (status.running) {
		startBtn.disabled = true;
		stopBtn.disabled = false;
	} else {
		startBtn.disabled = false;
		stopBtn.disabled = true;
	}
}

async function fetchStatus() {
	setBusy(true);
	try {
		const host = getHost();
		const port = parsePort();
		const response = await fetch(`/api/mock-openai/status?host=${encodeURIComponent(host)}&port=${port}`);
		if (!response.ok) {
			throw new Error(`状态查询失败: HTTP ${response.status}`);
		}
		const body = await response.json();
		renderStatus(body);
		showToast("状态已刷新");
	} catch (error) {
		showToast(String(error), true);
	} finally {
		setBusy(false);
	}
}

async function startMockOpenAI() {
	setBusy(true);
	try {
		const host = getHost();
		const port = parsePort();
		const response = await fetch("/api/mock-openai/start", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ host, port, reload: Boolean(reloadInput.checked) }),
		});
		if (!response.ok) {
			throw new Error(`启动失败: HTTP ${response.status}`);
		}
		const body = await response.json();
		renderStatus(body.status);
		showToast(body.status?.message || "mock_openai 已启动");
	} catch (error) {
		showToast(String(error), true);
	} finally {
		setBusy(false);
	}
}

async function stopMockOpenAI() {
	setBusy(true);
	try {
		const host = getHost();
		const port = parsePort();
		const response = await fetch(
			`/api/mock-openai/stop?host=${encodeURIComponent(host)}&port=${port}&force=true`,
			{ method: "POST" },
		);
		if (!response.ok) {
			throw new Error(`停止失败: HTTP ${response.status}`);
		}
		const body = await response.json();
		renderStatus(body.status);
		showToast(body.status?.message || "mock_openai 已停止");
	} catch (error) {
		showToast(String(error), true);
	} finally {
		setBusy(false);
	}
}

function openMockOpenAIPage() {
	setBusy(true);
	const run = async () => {
		try {
			const host = getHost();
			const port = parsePort();
			const response = await fetch(
				`/api/mock-openai/open-browser?host=${encodeURIComponent(host)}&port=${port}`,
				{ method: "POST" },
			);
			if (!response.ok) {
				throw new Error(`打开失败: HTTP ${response.status}`);
			}
			const body = await response.json();
			if (body?.opened_in_server) {
				showToast(body.open_message || "已在服务器浏览器打开页面");
			} else {
				showToast(body?.open_message || "服务器浏览器打开失败", true);
			}
		} catch (error) {
			showToast(String(error), true);
		} finally {
			setBusy(false);
		}
	};

	run();
}

refreshBtn.addEventListener("click", fetchStatus);
startBtn.addEventListener("click", startMockOpenAI);
stopBtn.addEventListener("click", stopMockOpenAI);
openPageBtn.addEventListener("click", openMockOpenAIPage);

fetchStatus();
