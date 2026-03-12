const api = {
	async testExtract(payload) {
		const response = await fetch("/api/test/extract", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(payload),
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

		return response.json();
	},
};

const nodes = {
	form: document.getElementById("extract-form"),
	providerHint: document.getElementById("provider-hint"),
	prompt: document.getElementById("prompt"),
	documentText: document.getElementById("document-text"),
	rawResponse: document.getElementById("raw-response"),
	runBtn: document.getElementById("run-btn"),
	fillSample: document.getElementById("fill-sample"),
	clearForm: document.getElementById("clear-form"),
	status: document.getElementById("result-status"),
	generatedPrompt: document.getElementById("generated-prompt"),
	resultRaw: document.getElementById("result-raw"),
	resultJson: document.getElementById("result-json"),
	resultErrors: document.getElementById("result-errors"),
	retryPrompt: document.getElementById("retry-prompt"),
	toast: document.getElementById("toast"),
};

let toastTimer = null;

const PROMPT_TEMPLATE = `请分析以下法院文书，并输出标准 JSON 结果。

必须遵循以下 JSON 结构：
{
	"case_id": "string###",
	"case_status": "结案|正在进行",
	"judgment_result": "leave|grant|dismiss",
	"hearing": "yes|no",
	"timeline": {
		"filing_date": "YYYY-MM-DD",
		"Applicant_file_completed": "YYYY-MM-DD",
		"reply_memo": "YYYY-MM-DD",
		"Sent_to_Court": "YYYY-MM-DD",
		"judgment_date": "YYYY-MM-DD"
	}
}

要求：
1. 只输出 JSON，不要额外解释。
2. 时间字段无法确认时请填 null。
3. case_status 只能是“结案”或“正在进行”。`;

const DOCUMENT_EXAMPLE = `{
	"case_id": "IMM-3-24",
	"case_number": "IMM-3-24",
	"title": "ZOHREH MASHAYEKHI v. MCI",
	"court": "Montréal",
	"filing_date": "2024-01-01",
	"docket_entries": [
		{
			"entry_date": "2024-06-14",
			"summary": "Sent to Court for leave disposition."
		},
		{
			"entry_date": "2024-10-01",
			"summary": "Final decision: dismissing the application for leave."
		},
		{
			"entry_date": "2024-10-11",
			"summary": "Decision endorsed on the record and sent to all parties."
		}
	]
}`;

const RAW_RESPONSE_EXAMPLE = `{
	"case_id": "IMM-3-24",
	"case_status": "结案",
	"judgment_result": "dismiss",
	"hearing": "no",
	"timeline": {
		"filing_date": "2024-01-01",
		"Applicant_file_completed": "2024-04-02",
		"reply_memo": "2024-05-01",
		"Sent_to_Court": "2024-06-14",
		"judgment_date": "2024-10-01"
	}
}`;

function showToast(message) {
	nodes.toast.textContent = message;
	nodes.toast.classList.add("show");
	clearTimeout(toastTimer);
	toastTimer = setTimeout(() => {
		nodes.toast.classList.remove("show");
	}, 2200);
}

function setStatus(kind, text) {
	nodes.status.classList.remove("status-idle", "status-ok", "status-fail", "status-error");
	nodes.status.classList.add(kind);
	nodes.status.textContent = text;
}

function setText(node, value) {
	node.textContent = value && value.length ? value : "(empty)";
}

function renderErrors(errors) {
	nodes.resultErrors.innerHTML = "";
	if (!errors || errors.length === 0) {
		const li = document.createElement("li");
		li.className = "muted";
		li.textContent = "none";
		nodes.resultErrors.appendChild(li);
		return;
	}

	for (const err of errors) {
		const li = document.createElement("li");
		li.textContent = err;
		nodes.resultErrors.appendChild(li);
	}
}

function readPayload() {
	const provider = nodes.providerHint.value;
	const payload = {
		prompt: nodes.prompt.value.trim(),
		document_text: nodes.documentText.value.trim(),
		raw_response: nodes.rawResponse.value.trim(),
	};
	if (provider) {
		payload.provider_hint = provider;
	}
	return payload;
}

function looksLikeTemplatePlaceholder(text) {
	if (!text) return false;
	const markers = [
		"string###",
		"结案|正在进行",
		"leave|grant|dismiss",
		"yes|no",
		"YYYY-MM-DD",
		"Applicant_file_completed",
		"reply_memo",
		"Sent_to_Court",
	];
	return markers.some((marker) => text.includes(marker));
}

function fillSample() {
	nodes.providerHint.value = "openchat";
	nodes.prompt.value = PROMPT_TEMPLATE;
	nodes.documentText.value = DOCUMENT_EXAMPLE;
	nodes.rawResponse.value = RAW_RESPONSE_EXAMPLE;
	showToast("Requirement sample filled");
}

function clearAll() {
	nodes.providerHint.value = "";
	nodes.prompt.value = "";
	nodes.documentText.value = "";
	nodes.rawResponse.value = "";
	setStatus("status-idle", "idle");
	setText(nodes.generatedPrompt, "");
	setText(nodes.resultRaw, "");
	setText(nodes.resultJson, "");
	setText(nodes.retryPrompt, "");
	renderErrors([]);
	showToast("Form cleared");
}

async function handleSubmit(event) {
	event.preventDefault();
	const payload = readPayload();

	if (!payload.prompt || !payload.document_text || !payload.raw_response) {
		showToast("prompt/document/raw response are required");
		return;
	}

	if (looksLikeTemplatePlaceholder(payload.raw_response)) {
		setStatus("status-fail", "invalid template");
		showToast("raw response 仍是模板占位符，请先填入真实值或点击 Fill Requirement Sample");
		return;
	}

	nodes.runBtn.disabled = true;
	setStatus("status-idle", "running...");

	try {
		const result = await api.testExtract(payload);
		setText(nodes.generatedPrompt, result.generated_prompt);
		setText(nodes.resultRaw, result.raw_response);
		setText(nodes.resultJson, result.extracted_json ? JSON.stringify(result.extracted_json, null, 2) : "");
		setText(nodes.retryPrompt, result.retry_prompt || "");
		renderErrors(result.validation_errors || []);

		if (result.valid) {
			setStatus("status-ok", "valid");
		} else {
			setStatus("status-fail", "invalid");
		}
		showToast("Extract test completed");
	} catch (err) {
		setStatus("status-error", "request error");
		showToast(err.message || "request failed");
	} finally {
		nodes.runBtn.disabled = false;
	}
}

function init() {
	nodes.form.addEventListener("submit", (event) => {
		handleSubmit(event).catch((err) => showToast(err.message));
	});

	nodes.fillSample.addEventListener("click", fillSample);
	nodes.clearForm.addEventListener("click", clearAll);

	clearAll();
}

init();
