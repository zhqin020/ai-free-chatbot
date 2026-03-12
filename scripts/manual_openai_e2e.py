from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


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
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"health check timeout: {last_error}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _pick_visible_selector(page: object, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible():
                return selector
        except Exception:
            continue
    return None


def _extract_json_from_text(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise RuntimeError("assistant response does not contain JSON object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise RuntimeError("assistant JSON root is not object")
    return payload


def _try_extract_json_from_text(text: str) -> dict[str, object] | None:
    try:
        return _extract_json_from_text(text)
    except Exception:
        return None


def _wait_user(prompt: str) -> None:
    print("\n" + "=" * 72)
    print(prompt)
    print("完成后按回车继续...")
    input()


def _latest_message_text(page: object, selectors: list[str]) -> tuple[str | None, int, str]:
    chosen_selector: str | None = None
    chosen_count = 0
    chosen_text = ""

    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
            if count <= 0:
                continue
            text = locator.nth(count - 1).inner_text()

            if chosen_selector is None:
                chosen_selector = selector
                chosen_count = count
                chosen_text = text
                continue

            # Prefer selectors with more items; if equal, prefer longer text.
            if count > chosen_count or (count == chosen_count and len(text) > len(chosen_text)):
                chosen_selector = selector
                chosen_count = count
                chosen_text = text
        except Exception:
            continue

    return chosen_selector, chosen_count, chosen_text


def _read_body_text(page: object) -> str:
    try:
        return page.locator("body").inner_text(timeout=1200)
    except Exception:
        return ""


def _wait_for_response_text_change(
    page: object,
    selectors: list[str],
    previous_count: int,
    previous_text: str,
    previous_body_text: str,
    timeout_seconds: float,
) -> tuple[str, str]:
    deadline = time.time() + timeout_seconds
    last_snapshot = ""
    while time.time() < deadline:
        selector, count, text = _latest_message_text(page, selectors)
        if selector is None:
            time.sleep(0.5)
            continue

        candidate_text = ""
        candidate_selector = ""
        if count > previous_count:
            candidate_text = text
            candidate_selector = selector
        elif text and text != previous_text:
            candidate_text = text
            candidate_selector = selector

        if candidate_text:
            if candidate_text != last_snapshot:
                print(
                    f"[INFO] 回复流式更新: selector={candidate_selector}, text_len={len(candidate_text)}"
                )
                last_snapshot = candidate_text

            if _try_extract_json_from_text(candidate_text) is not None:
                return candidate_selector, candidate_text

        # Fallback for sites where assistant nodes are virtualized or use unknown selectors.
        body_text = _read_body_text(page)
        if (
            body_text
            and body_text != previous_body_text
            and len(body_text) > len(previous_body_text) + 20
            and "{" in body_text
            and "}" in body_text
        ):
            if body_text != last_snapshot:
                print(f"[INFO] 回复流式更新: selector=body, text_len={len(body_text)}")
                last_snapshot = body_text
            if _try_extract_json_from_text(body_text) is not None:
                return "body", body_text

        time.sleep(0.5)

    raise RuntimeError(
        "timeout waiting for assistant response update "
        "(neither message count nor message text changed)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual E2E for mock_openai/openai chat flow")
    parser.add_argument(
        "--target",
        choices=["mock_site", "real_site", "mock_openai", "openai"],
        default="mock_site",
        help="run against local mock site first, then optional real site",
    )
    parser.add_argument("--chat-url", default="https://chatgpt.com/", help="real site chat url")
    parser.add_argument("--mock-host", default="127.0.0.1", help="mock site host")
    parser.add_argument("--mock-port", type=int, default=8010, help="mock site port")
    parser.add_argument("--timeout-seconds", type=float, default=90.0, help="wait timeout for response")
    parser.add_argument(
        "--max-manual-retries",
        type=int,
        default=6,
        help="max manual retries when OpenAI verification/login keeps reappearing",
    )
    parser.add_argument("--user-data-dir", default="tmp/manual_openai_profile", help="persistent browser profile dir")
    parser.add_argument("--force-fresh", action="store_true", help="clear profile directory before run")
    parser.add_argument("--headless", action="store_true", help="run browser headless")
    return parser.parse_args()


def _normalize_hearing(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    yes_values = {
        "yes", "y", "true", "1", "是", "有", "开庭", "需要庭审", "需庭审", "庭审",
    }
    no_values = {
        "no", "n", "false", "0", "否", "无", "不开庭", "无需庭审", "不需要庭审",
    }

    if text in yes_values:
        return "true"
    if text in no_values:
        return "false"
    return None


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


def _validate_payload(payload: dict[str, object]) -> None:
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
    _require(isinstance(timeline, dict), "timeline must be object")
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


def _wait_openai_chat_ready(page: object, max_manual_retries: int) -> str:
    input_selectors = [
        "textarea[data-testid='chat-input']",
        "textarea#prompt-textarea",
        "textarea[placeholder*='message' i]",
        "div[contenteditable='true']",
    ]
    verify_selectors = [
        "text=Verify you are human",
        "iframe[title*='challenge' i]",
        "iframe[src*='challenges.cloudflare.com']",
    ]
    login_hint_selectors = [
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "a:has-text('Sign in')",
    ]

    for attempt in range(1, max_manual_retries + 1):
        input_selector = _pick_visible_selector(page, input_selectors)
        if input_selector is not None:
            try:
                if page.locator(input_selector).first.is_enabled():
                    if attempt == 1:
                        print("[INFO] OpenAI 页面已就绪，直接进入发送阶段。")
                    else:
                        print(f"[INFO] OpenAI 页面已就绪（第 {attempt} 次检测通过）。")
                    return input_selector
            except Exception:
                pass

        verify_selector = _pick_visible_selector(page, verify_selectors)
        login_selector = _pick_visible_selector(page, login_hint_selectors)

        reason = "聊天输入框暂不可用"
        if verify_selector:
            reason = "检测到 Cloudflare/人机验证反复出现"
        elif login_selector:
            reason = "检测到登录状态未完成"

        try:
            page.bring_to_front()
        except Exception:
            pass

        _wait_user(
            f"第 {attempt}/{max_manual_retries} 次处理：{reason}。\n"
            "请在浏览器中继续完成验证/登录，稳定进入可发送消息页面后再回车。"
        )

    raise RuntimeError(
        "OpenAI 页面仍未就绪：Cloudflare/登录步骤可能反复触发。"
        "建议保持同一网络和浏览器 profile，必要时稍后重试。"
    )


def main() -> None:
    args = parse_args()

    # Backward-compatible aliases.
    normalized_target = args.target
    if normalized_target == "openai":
        normalized_target = "real_site"
    elif normalized_target == "mock_openai":
        normalized_target = "mock_site"

    mock_server: subprocess.Popen[bytes] | None = None
    target_url: str

    if normalized_target == "mock_site":
        target_url = f"http://{args.mock_host}:{args.mock_port}/"
        mock_server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.mock_openchat.site:app",
                "--host",
                args.mock_host,
                "--port",
                str(args.mock_port),
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_health(f"http://{args.mock_host}:{args.mock_port}")
    else:
        target_url = args.chat_url

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"Playwright unavailable: {exc}. Please run: playwright install chromium"
        )

    profile_dir = Path(args.user_data_dir)
    if args.force_fresh and profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    prompt = (
        "请只输出一个 JSON 对象，不要解释，不要代码块标记。"
        "结构必须包含 case_id/case_status/judgment_result/hearing/timeline，"
        "其中 case_status 只能是 Closed 或 On-Going，hearing 只能是 true 或 false。"
        "其中 timeline 包含 filing_date/Applicant_file_completed/reply_memo/Sent_to_Court/judgment_date。"
        "case_id 请沿用原文中的案件编号，用于后续程序匹配。"
        "请给出合法日期。case IMM-1234-24，2024-01-01立案，2024-01-15提交法官，"
        "2024-02-20回复备忘，2024-03-10送交法院，2024-05-01判决，Closed，grant，true。"
    )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=args.headless,
            slow_mo=80 if not args.headless else 0,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded")
            page.bring_to_front()

            print(f"[INFO] target={normalized_target} url={target_url}")
            print(f"[INFO] profile={profile_dir}")

            if normalized_target == "mock_site":
                cookie_btn = _pick_visible_selector(page, ["[data-testid='cookie-accept']", "button:has-text('同意并继续')"])
                if cookie_btn:
                    page.locator(cookie_btn).first.click()

                verify_btn = _pick_visible_selector(page, ["[data-testid='verify-human']", "text=Verify you are human"])
                if verify_btn:
                    page.locator(verify_btn).first.click()

                try:
                    if page.locator("#loginOverlay").is_visible():
                        page.fill("#username", "tester")
                        page.fill("#password", "secret")
                        page.click("#signinBtn")
                except Exception:
                    pass
            else:
                input_selector = _wait_openai_chat_ready(page, args.max_manual_retries)

            if normalized_target == "mock_site":
                input_selector = _pick_visible_selector(
                    page,
                    [
                        "textarea[data-testid='chat-input']",
                        "textarea#prompt-textarea",
                        "textarea[placeholder*='message' i]",
                        "div[contenteditable='true']",
                    ],
                )
                _require(input_selector is not None, "cannot find chat input selector")
                print("[INFO] mock_openai 页面已就绪，进入发送阶段。")

            assistant_selectors = [
                "[data-testid='assistant-message']",
                "article[data-role='assistant']",
                "div.message.assistant",
                "article",
                ".markdown",
                "div[class*='assistant']",
                "div.ds-markdown",
                "div[class*='markdown']",
                "div[class*='response']",
            ]
            _, previous_count, previous_text = _latest_message_text(page, assistant_selectors)
            previous_body_text = _read_body_text(page)
            print(
                f"[INFO] 发送前回复基线: count={previous_count}, "
                f"text_len={len(previous_text)}, body_len={len(previous_body_text)}"
            )

            input_locator = page.locator(input_selector).first
            input_locator.fill(prompt)

            send_selector = _pick_visible_selector(
                page,
                [
                    "button[data-testid='send-button']",
                    "button[aria-label*='send' i]",
                    "button:has-text('Send')",
                ],
            )
            if send_selector:
                page.locator(send_selector).first.click()
            else:
                input_locator.press("Enter")

            print("[INFO] 已发送消息，等待 assistant 返回...")
            response_selector, response_text = _wait_for_response_text_change(
                page,
                assistant_selectors,
                previous_count=previous_count,
                previous_text=previous_text,
                previous_body_text=previous_body_text,
                timeout_seconds=args.timeout_seconds,
            )
            print(f"[INFO] 捕获到回复，selector={response_selector}, text_len={len(response_text)}")

            payload = _extract_json_from_text(response_text)
            _validate_payload(payload)

            print("\n[INFO] 已采集并解析返回 JSON：")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("\n[PASS] E2E 发送与返回校验通过。")
        finally:
            try:
                context.close()
            except Exception:
                pass

    if mock_server is not None:
        mock_server.terminate()
        try:
            mock_server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock_server.kill()


if __name__ == "__main__":
    main()
