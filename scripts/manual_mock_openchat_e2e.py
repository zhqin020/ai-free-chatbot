from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
                last_error = f"unexpected status={response.status}"
        except URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # pragma: no cover - safety branch
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"mock_openchat health check timeout: {last_error}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _wait_user_step(prompt: str) -> None:
    print("\n" + "=" * 72)
    print(prompt)
    print("完成后请在终端按回车继续...")
    input()


def _wait_user_step_until_ok(prompt: str, check_fn: object) -> None:
    while True:
        _wait_user_step(prompt)
        try:
            check_fn()
            return
        except Exception as exc:
            print(f"\n[WARN] 当前步骤校验未通过：{exc}")
            choice = input("请输入 r 重试，或 q 退出验收：").strip().lower()
            if choice == "q":
                raise RuntimeError(f"manual step aborted by user: {prompt}") from exc
            print("\n继续重试该步骤...")


def _is_visible(locator: object) -> bool:
    try:
        return bool(locator.is_visible())
    except Exception:
        return False


def _chat_ready(state_badge: object, input_box: object, send_btn: object) -> bool:
    try:
        return (
            input_box.is_enabled()
            and send_btn.is_enabled()
            and state_badge.inner_text().strip() == "已进入对话"
        )
    except Exception:
        return False


def _extract_json_from_text(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("response JSON root is not an object")
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("no JSON object found in assistant response")
        payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise RuntimeError("response JSON root is not an object")
        return payload


def _normalize_case_status(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    normalized = text.lower().replace("_", "-").replace(" ", "")
    if normalized in {"closed", "结案"}:
        return "Closed"
    if normalized in {"on-going", "ongoing", "正在进行"}:
        return "On-Going"
    return text


def _normalize_hearing(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in {"yes", "y", "true", "1", "是", "有", "开庭", "需要庭审", "需庭审", "庭审"}:
        return "true"
    if text in {"no", "n", "false", "0", "否", "无", "不开庭", "无需庭审", "不需要庭审"}:
        return "false"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual E2E acceptance for mock_openchat: requires real browser + human input"
    )
    parser.add_argument("--host", default="127.0.0.1", help="mock site host")
    parser.add_argument("--port", type=int, default=8010, help="mock site port, set 0 for auto")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="wait timeout for post-action checks")
    parser.add_argument(
        "--user-data-dir",
        default="tmp/manual_mock_profile",
        help="Playwright user data dir for persistent login/session state",
    )
    parser.add_argument(
        "--force-fresh",
        action="store_true",
        help="clear user-data-dir before launch to force a fresh login flow",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    port = args.port or _find_free_port()
    base_url = f"http://{args.host}:{port}"

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.mock_openchat.site:app",
            "--host",
            args.host,
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    context = None
    try:
        _wait_health(base_url)

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - runtime dependency path
            raise RuntimeError(
                f"Playwright is not available: {exc}. Please install and run: playwright install chromium"
            )

        with sync_playwright() as p:
            profile_dir = Path(args.user_data_dir)
            if args.force_fresh and profile_dir.exists():
                shutil.rmtree(profile_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                slow_mo=80,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(f"{base_url}/", wait_until="domcontentloaded")
            page.bring_to_front()
            print(f"[INFO] mock_openchat 已打开：{base_url}")
            print(f"[INFO] 使用持久化 profile：{profile_dir}")
            if args.force_fresh:
                print("[INFO] 已启用 --force-fresh，本次会话从全新状态开始。")

            cookie_overlay = page.locator("#cookieOverlay")
            verify_overlay = page.locator("#verifyOverlay")
            login_overlay = page.locator("#loginOverlay")
            state_badge = page.locator("#stateBadge")
            input_box = page.locator("textarea[data-testid='chat-input']")
            send_btn = page.locator("button[data-testid='send-button']")

            print(f"[INFO] 当前状态徽标：{state_badge.inner_text().strip()}")

            # Adaptive flow: some dialogs may be absent, or session may already be in chat-ready state.
            if not _chat_ready(state_badge, input_box, send_btn):
                if _is_visible(cookie_overlay):
                    _wait_user_step_until_ok(
                        "步骤 1/4：请在浏览器中手工点击『同意并继续』(Cookie).",
                        lambda: _require(not _is_visible(cookie_overlay), "Cookie overlay is still visible"),
                    )
                else:
                    print("[INFO] 未检测到 Cookie 弹窗，已跳过步骤 1。")

                if not _chat_ready(state_badge, input_box, send_btn):
                    page.bring_to_front()
                    if _is_visible(verify_overlay):
                        _wait_user_step_until_ok(
                            "步骤 2/4：请在浏览器中手工点击『Verify you are human』.",
                            lambda: _require(not _is_visible(verify_overlay), "Verify overlay is still visible"),
                        )
                    else:
                        print("[INFO] 未检测到 Verify 弹窗，已跳过步骤 2。")

                if not _chat_ready(state_badge, input_box, send_btn):
                    page.bring_to_front()
                    if _is_visible(login_overlay):
                        _wait_user_step_until_ok(
                            "步骤 3/4：请手工输入用户名和密码，并点击『Sign in』登录.",
                            lambda: _require(_chat_ready(state_badge, input_box, send_btn), "Chat is not ready after login"),
                        )
                    else:
                        # Fallback: no visible dialogs but still not ready, let user manually repair state.
                        _wait_user_step_until_ok(
                            "步骤 3/4：未检测到登录弹窗，但聊天尚未就绪。请在页面手工完成必要操作后继续。",
                            lambda: _require(_chat_ready(state_badge, input_box, send_btn), "Chat is still not ready"),
                        )
            else:
                print("[INFO] 检测到已进入对话状态，已跳过 cookie/verify/login 人工步骤。")

            _require(input_box.is_enabled(), "Chat input should be enabled after login")
            _require(send_btn.is_enabled(), "Send button should be enabled after login")
            _require(state_badge.inner_text() == "已进入对话", "State badge should be 已进入对话")

            messages = page.locator("[data-testid='assistant-message']")
            prev_count = messages.count()
            _require(prev_count >= 1, "Welcome assistant message is missing")

            page.bring_to_front()
            _wait_user_step_until_ok(
                "步骤 4/4：请在对话框手工输入一条消息并发送（例如: case AB-42 please extract）。",
                lambda: page.wait_for_function(
                    "(p) => document.querySelectorAll(p.selector).length > p.count",
                    arg={"selector": "[data-testid='assistant-message']", "count": prev_count},
                    timeout=int(args.timeout_seconds * 1000),
                ),
            )

            response_text = messages.nth(prev_count).inner_text()
            payload = _extract_json_from_text(response_text)

            case_id = str(payload.get("case_id", "")).strip()
            _require(bool(case_id), "case_id must be a non-empty string")
            case_status = _normalize_case_status(payload.get("case_status"))
            _require(case_status in {"Closed", "On-Going"}, "invalid case_status")
            payload["case_status"] = case_status
            _require(payload.get("judgment_result") in {"leave", "grant", "dismiss"}, "invalid judgment_result")
            hearing = _normalize_hearing(payload.get("hearing"))
            _require(hearing in {"true", "false"}, "invalid hearing")
            payload["hearing"] = hearing

            timeline = payload.get("timeline") or {}
            for key in (
                "filing_date",
                "Applicant_file_completed",
                "reply_memo",
                "Sent_to_Court",
                "judgment_date",
            ):
                _require(key in timeline, f"timeline missing key: {key}")
                _require(
                    bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(timeline[key]))),
                    f"timeline[{key}] must match YYYY-MM-DD",
                )

            print("\n[INFO] 已采集并解析 chat 返回 JSON：")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

            print("\n[PASS] 手工 E2E 验收通过：真实浏览器 + 人工输入 + JSON 校验全部完成。")

    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
