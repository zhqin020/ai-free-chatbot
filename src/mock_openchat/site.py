from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def _extract_case_id(user_message: str) -> str:
    match = re.search(r"([A-Za-z]{2,}-\d{2,}|\d{4}[-_/]\d+)", user_message)
    if match:
        return f"{match.group(1)}###"
    return "MOCK-2026-001###"


def _date_str(value: date) -> str:
    return value.isoformat()


def build_mock_json_payload(user_message: str) -> dict[str, object]:
    today = datetime.now(UTC).date()
    filing = today - timedelta(days=120)
    applicant_file_completed = filing + timedelta(days=12)
    reply_memo = applicant_file_completed + timedelta(days=22)
    sent_to_court = reply_memo + timedelta(days=15)
    judgment = sent_to_court + timedelta(days=30)

    return {
        "case_id": _extract_case_id(user_message),
        "case_status": "结案",
        "judgment_result": "grant",
        "hearing": "yes",
        "timeline": {
            "filing_date": _date_str(filing),
            "Applicant_file_completed": _date_str(applicant_file_completed),
            "reply_memo": _date_str(reply_memo),
            "Sent_to_Court": _date_str(sent_to_court),
            "judgment_date": _date_str(judgment),
        },
    }


def _render_page() -> str:
    return """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Mock OpenChat</title>
  <style>
    :root {
      --bg1: #f6efe3;
      --bg2: #dce7f5;
      --card: #fffdf8;
      --ink: #17212b;
      --accent: #006b5f;
      --accent-2: #c06014;
      --line: #c8d1da;
      --danger: #9d2b0f;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: \"Noto Sans SC\", \"Microsoft YaHei\", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 20% 12%, rgba(192, 96, 20, 0.18), transparent 35%),
        radial-gradient(circle at 80% 88%, rgba(0, 107, 95, 0.2), transparent 40%),
        linear-gradient(140deg, var(--bg1), var(--bg2));
      display: grid;
      place-items: center;
      padding: 20px;
    }

    .shell {
      width: min(960px, 100%);
      border: 1px solid var(--line);
      border-radius: 20px;
      background: var(--card);
      overflow: hidden;
      box-shadow: 0 18px 60px rgba(23, 33, 43, 0.2);
    }

    .topbar {
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      gap: 12px;
      justify-content: space-between;
      align-items: center;
      background: #fff;
    }

    .badge {
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
    }

    .badge.ok { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 30%, white); }
    .badge.warn { color: var(--accent-2); border-color: color-mix(in srgb, var(--accent-2) 30%, white); }
    .badge.err { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 30%, white); }

    .chat {
      display: grid;
      grid-template-rows: 1fr auto;
      min-height: 62vh;
    }

    .messages {
      padding: 16px;
      overflow-y: auto;
      display: grid;
      gap: 10px;
      background: linear-gradient(180deg, #fff, #f5f8fb);
    }

    .msg {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 12px;
      max-width: 92%;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      font-size: 14px;
    }

    .msg.user { justify-self: end; background: #f4faf9; border-color: #a9d8d2; }
    .msg.assistant { justify-self: start; background: #fffefb; }

    .composer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      border-top: 1px solid var(--line);
      padding: 12px;
      background: #fff;
    }

    textarea[data-testid='chat-input'] {
      width: 100%;
      min-height: 78px;
      resize: vertical;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 10px;
      font-size: 14px;
      font-family: inherit;
    }

    button {
      border: 1px solid transparent;
      border-radius: 11px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
      transition: transform .12s ease, filter .12s ease;
    }

    button:hover { transform: translateY(-1px); filter: brightness(1.04); }
    button:disabled { cursor: not-allowed; transform: none; filter: grayscale(0.5); opacity: 0.75; }

    .btn-main { background: var(--accent); color: #fff; }
    .btn-sub { background: #fff; border-color: var(--line); color: var(--ink); }

    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 33, 0.52);
      display: none;
      place-items: center;
      z-index: 30;
      padding: 18px;
    }

    .overlay.show { display: grid; }

    .modal {
      width: min(520px, 100%);
      background: #fff;
      border-radius: 16px;
      border: 1px solid var(--line);
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.28);
      padding: 16px;
      display: grid;
      gap: 12px;
    }

    .modal h2 { margin: 0; font-size: 20px; }
    .modal p { margin: 0; line-height: 1.5; font-size: 14px; }
    .modal .row { display: flex; gap: 8px; justify-content: flex-end; }

    .login-form {
      display: grid;
      gap: 8px;
    }

    .login-form input {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      font-size: 14px;
    }

    .tip {
      margin: 0;
      font-size: 12px;
      color: #4b5f73;
    }
  </style>
</head>
<body>
  <div class=\"shell\">
    <header class=\"topbar\">
      <strong>Mock OpenChat Sandbox</strong>
      <span id=\"stateBadge\" class=\"badge warn\">待处理 Cookie</span>
    </header>

    <main class=\"chat\">
      <section id=\"messages\" class=\"messages\" aria-live=\"polite\"></section>
      <section class=\"composer\">
        <textarea data-testid=\"chat-input\" placeholder=\"Message OpenChat\" disabled></textarea>
        <button data-testid=\"send-button\" class=\"btn-main\" disabled>Send</button>
      </section>
    </main>
  </div>

  <div id=\"cookieOverlay\" class=\"overlay show\" role=\"dialog\" aria-modal=\"true\">
    <div class=\"modal\">
      <h2>Cookie 设置</h2>
      <p>请先同意 Cookie 设置，否则无法进入登录流程。</p>
      <div class=\"row\">
        <button id=\"cookieAcceptBtn\" class=\"btn-main\" data-testid=\"cookie-accept\">同意并继续</button>
      </div>
    </div>
  </div>

  <div id=\"verifyOverlay\" class=\"overlay\" role=\"dialog\" aria-modal=\"true\">
    <div class=\"modal\">
      <h2>Cloudflare 验证</h2>
      <p>请完成验证后继续。</p>
      <p class=\"tip\">为兼容自动化检测，这里会显示关键文案：Verify you are human</p>
      <div class=\"row\">
        <button id=\"verifyBtn\" class=\"btn-main\" data-testid=\"verify-human\">Verify you are human</button>
      </div>
    </div>
  </div>

  <div id=\"loginOverlay\" class=\"overlay\" role=\"dialog\" aria-modal=\"true\">
    <div class=\"modal\">
      <h2>登录 Mock OpenChat</h2>
      <p>可随意输入用户名密码，提交后进入对话窗口。</p>
      <form id=\"loginForm\" class=\"login-form\">
        <input id=\"username\" type=\"text\" placeholder=\"用户名\" required />
        <input id=\"password\" type=\"password\" placeholder=\"密码\" required />
        <div class=\"row\">
          <button id=\"signinBtn\" type=\"submit\" class=\"btn-main\">Sign in</button>
        </div>
      </form>
    </div>
  </div>

  <script>
    const STORAGE_KEY = 'mock_openchat_auth_state_v1';
    const COOKIE_KEY_PREFIX = 'mock_openchat_';

    const state = {
      cookieAccepted: false,
      humanVerified: false,
      loggedIn: false,
    };

    function getCookieValue(name) {
      const found = document.cookie
        .split('; ')
        .find((part) => part.startsWith(name + '='));
      return found ? found.slice(name.length + 1) : '';
    }

    function boolFromCookie(name) {
      return getCookieValue(name) === '1';
    }

    function persistCookie(name, enabled) {
      const maxAge = 60 * 60 * 24 * 30;
      const value = enabled ? '1' : '0';
      document.cookie = `${name}=${value}; Max-Age=${maxAge}; Path=/; SameSite=Lax`;
    }

    function loadState() {
      state.cookieAccepted = boolFromCookie(COOKIE_KEY_PREFIX + 'cookie_accepted');
      state.humanVerified = boolFromCookie(COOKIE_KEY_PREFIX + 'human_verified');
      state.loggedIn = boolFromCookie(COOKIE_KEY_PREFIX + 'logged_in');

      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const saved = JSON.parse(raw);
        state.cookieAccepted = state.cookieAccepted || !!saved.cookieAccepted;
        state.humanVerified = state.humanVerified || !!saved.humanVerified;
        state.loggedIn = state.loggedIn || !!saved.loggedIn;
      } catch (_err) {
        // ignore invalid persisted state and continue with defaults
      }
    }

    function persistState() {
      persistCookie(COOKIE_KEY_PREFIX + 'cookie_accepted', state.cookieAccepted);
      persistCookie(COOKIE_KEY_PREFIX + 'human_verified', state.humanVerified);
      persistCookie(COOKIE_KEY_PREFIX + 'logged_in', state.loggedIn);

      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch (_err) {
        // ignore storage failures in restrictive environments
      }
    }

    const cookieOverlay = document.getElementById('cookieOverlay');
    const verifyOverlay = document.getElementById('verifyOverlay');
    const loginOverlay = document.getElementById('loginOverlay');
    const cookieAcceptBtn = document.getElementById('cookieAcceptBtn');
    const verifyBtn = document.getElementById('verifyBtn');
    const loginForm = document.getElementById('loginForm');
    const input = document.querySelector("textarea[data-testid='chat-input']");
    const sendBtn = document.querySelector("button[data-testid='send-button']");
    const messages = document.getElementById('messages');
    const stateBadge = document.getElementById('stateBadge');

    function setBadge(text, cls) {
      stateBadge.textContent = text;
      stateBadge.className = 'badge ' + cls;
    }

    function addMessage(role, text) {
      const item = document.createElement('div');
      item.className = 'msg ' + role;
      if (role === 'assistant') {
        item.setAttribute('data-testid', 'assistant-message');
      }
      item.textContent = text;
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
    }

    function updateUiState() {
      if (!state.cookieAccepted) {
        setBadge('待处理 Cookie', 'warn');
      } else if (!state.humanVerified) {
        setBadge('待做人机验证', 'warn');
      } else if (!state.loggedIn) {
        setBadge('待登录', 'warn');
      } else {
        setBadge('已进入对话', 'ok');
      }

      input.disabled = !state.loggedIn;
      sendBtn.disabled = !state.loggedIn;
      cookieOverlay.classList.toggle('show', !state.cookieAccepted);
      verifyOverlay.classList.toggle('show', state.cookieAccepted && !state.humanVerified);
      loginOverlay.classList.toggle('show', state.cookieAccepted && state.humanVerified && !state.loggedIn);
      persistState();
    }

    function buildMockJson(userText) {
      const now = new Date();
      const day = 24 * 60 * 60 * 1000;
      const asDate = (offset) => new Date(now.getTime() + offset * day).toISOString().slice(0, 10);
      const caseIdMatch = userText.match(/([A-Za-z]{2,}-\\d{2,}|\\d{4}[-_/]\\d+)/);
      const caseId = (caseIdMatch ? caseIdMatch[1] : 'MOCK-2026-001') + '###';

      const payload = {
        case_id: caseId,
        case_status: '结案',
        judgment_result: 'grant',
        hearing: 'yes',
        timeline: {
          filing_date: asDate(-120),
          Applicant_file_completed: asDate(-108),
          reply_memo: asDate(-86),
          Sent_to_Court: asDate(-71),
          judgment_date: asDate(-41),
        },
      };
      return JSON.stringify(payload, null, 2);
    }

    cookieAcceptBtn.addEventListener('click', () => {
      state.cookieAccepted = true;
      updateUiState();
    });

    verifyBtn.addEventListener('click', () => {
      state.humanVerified = true;
      updateUiState();
    });

    loginForm.addEventListener('submit', (ev) => {
      ev.preventDefault();
      state.loggedIn = true;
      updateUiState();
      if (!document.querySelector("[data-testid='assistant-message']")) {
        addMessage('assistant', '欢迎进入 Mock OpenChat。现在可以发送消息，我将返回符合模板的 JSON。');
      }
      input.focus();
    });

    sendBtn.addEventListener('click', () => {
      const text = input.value.trim();
      if (!text) return;
      addMessage('user', text);
      input.value = '';
      setTimeout(() => {
        addMessage('assistant', buildMockJson(text));
      }, 250);
    });

    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        sendBtn.click();
      }
    });

    loadState();
    updateUiState();
    if (state.loggedIn && !document.querySelector("[data-testid='assistant-message']")) {
      addMessage('assistant', '已恢复登录状态。现在可以继续发送消息。');
    }
  </script>
</body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(title="mock-openchat-site")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _render_page()

    @app.get("/api/mock-json")
    def mock_json(message: str = "") -> dict[str, object]:
        # Keep an API endpoint for future automation and debugging, even though UI currently builds JSON locally.
        return build_mock_json_payload(message)

    return app


app = create_app()
