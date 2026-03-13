const $ = (id) => document.getElementById(id);

const runningText = $("running-text");
const pidText = $("pid-text");
const managedText = $("managed-text");
const uptimeText = $("uptime-text");
const startedAtText = $("started-at-text");
const commandText = $("command-text");
const messageText = $("message-text");
const toast = $("toast");
const refreshBtn = $("refresh-btn");
const startBtn = $("start-btn");
const stopBtn = $("stop-btn");

function setBusy(busy) {
	refreshBtn.disabled = busy;
	startBtn.disabled = busy;
	stopBtn.disabled = busy;
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
	startedAtText.textContent = status.started_at ?? "-";
	commandText.textContent = status.command ?? "-";
	messageText.textContent = status.message ?? "-";

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
		const response = await fetch("/api/worker/status");
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

async function startWorker() {
	setBusy(true);
	try {
		const response = await fetch("/api/worker/start", { method: "POST" });
		if (!response.ok) {
			throw new Error(`启动失败: HTTP ${response.status}`);
		}
		const body = await response.json();
		renderStatus(body.status);
		showToast(body.status?.message || "worker 已启动");
	} catch (error) {
		showToast(String(error), true);
	} finally {
		setBusy(false);
	}
}

async function stopWorker() {
	setBusy(true);
	try {
		const response = await fetch("/api/worker/stop?force=true", { method: "POST" });
		if (!response.ok) {
			throw new Error(`停止失败: HTTP ${response.status}`);
		}
		const body = await response.json();
		renderStatus(body.status);
		showToast(body.status?.message || "worker 已停止");
	} catch (error) {
		showToast(String(error), true);
	} finally {
		setBusy(false);
	}
}

refreshBtn.addEventListener("click", fetchStatus);
startBtn.addEventListener("click", startWorker);
stopBtn.addEventListener("click", stopWorker);

fetchStatus();
