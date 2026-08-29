import os
import re
import uuid
from utils.logger import setup_logger
from utils.config import get_config, get_userData
from utils import norm
from core.msg_builder import build_message
from core.browser import get_browser
from core.results import RunStatus, RunSummary, TargetSendResult
from playwright.sync_api import Response, TimeoutError as PlaywrightTimeoutError
import time

config = get_config()
userData = get_userData()
logger = setup_logger(level=config.get("logLevel", "Info"))
userIDDict = {}

CONVERSATION_ITEM_SELECTOR = ".conversationConversationItemwrapper"
CONVERSATION_TITLE_SELECTOR = ".conversationConversationItemtitle"
CONVERSATION_LIST_SELECTOR = ".conversationConversationListwrapper"
CHAT_EDITOR_SELECTOR = ".messageEditorimChatEditorContainer"
CHAT_EDITOR_INPUT_SELECTOR = f"{CHAT_EDITOR_SELECTOR} [contenteditable='true']"
OUTGOING_MESSAGE_TEXT_SELECTOR = (
    ".MessageItemTextcontainer.MessageItemTextisFromMe .TextMessageTextpureText"
)
CONVERSATION_SELECTED_SCRIPT = """
(element) => element.classList.contains("conversationConversationItemcurConversation")
"""
CONVERSATION_SETTLE_MS = 1000
MESSAGE_DELIVERY_TIMEOUT_MS = 10000
MESSAGE_DELIVERY_VERIFICATION_ATTEMPTS = 3
POST_SEND_SETTLE_MS = 3000
TRUST_LOGIN_CANCEL_SELECTOR = ".trust-login-dialog-button-cancel"
TRUST_LOGIN_DIALOG_TIMEOUT_MS = 3000
TARGET_IDENTITY_WAIT_TIMEOUT_MS = 5000
TARGET_IDENTITY_POLL_MS = 100
CLOUD_RUN_EXECUTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")

MESSAGE_COUNT_SCRIPT = r"""
({ messageSelector, message }) => {
    const normalizeText = (value) => (value || "")
        .replace(/\r\n?/g, "\n")
        .replace(/[\u200B-\u200D\uFEFF]/g, "")
        .replace(/\u00A0/g, " ")
        .split("\n")
        .map((line) => line.trimEnd())
        .join("\n")
        .trim();
    const normalizedMessage = normalizeText(message);

    return Array.from(document.querySelectorAll(messageSelector)).filter(
        (element) => normalizeText(element.innerText) === normalizedMessage
    ).length;
}
"""

MESSAGE_DELIVERED_SCRIPT = r"""
({ editorSelector, messageSelector, message, countBefore }) => {
    const normalizeText = (value) => (value || "")
        .replace(/\r\n?/g, "\n")
        .replace(/[\u200B-\u200D\uFEFF]/g, "")
        .replace(/\u00A0/g, " ")
        .split("\n")
        .map((line) => line.trimEnd())
        .join("\n")
        .trim();
    const editor = document.querySelector(editorSelector);
    const editorText = editor ? normalizeText(editor.innerText || editor.textContent) : null;
    if (!editor || editorText !== "") {
        return false;
    }

    const normalizedMessage = normalizeText(message);
    const renderedCount = Array.from(document.querySelectorAll(messageSelector)).filter(
        (element) => normalizeText(element.innerText) === normalizedMessage
    ).length;

    return renderedCount > countBefore;
}
"""


class MessageDeliveryError(RuntimeError):
    pass


def create_run_id():
    """Use a validated Cloud Run execution name or generate a local correlation ID."""
    execution_name = os.getenv("CLOUD_RUN_EXECUTION", "")
    if CLOUD_RUN_EXECUTION_PATTERN.fullmatch(execution_name):
        return execution_name
    return uuid.uuid4().hex


def send_message_verified(
    page,
    chat_input,
    message,
    timeout=MESSAGE_DELIVERY_TIMEOUT_MS,
    verification_attempts=MESSAGE_DELIVERY_VERIFICATION_ATTEMPTS,
    run_id=None,
):
    """Press Enter once and require a newly rendered message before succeeding."""
    message_lines = message.split("\\n")
    rendered_message = "\n".join(message_lines)
    count_before = page.evaluate(
        MESSAGE_COUNT_SCRIPT,
        {
            "messageSelector": OUTGOING_MESSAGE_TEXT_SELECTOR,
            "message": rendered_message,
        },
    )

    for index, line in enumerate(message_lines):
        chat_input.type(line)
        if index < len(message_lines) - 1:
            chat_input.press("Shift+Enter")

    chat_input.press("Enter")

    verification_arguments = {
        "editorSelector": CHAT_EDITOR_INPUT_SELECTOR,
        "messageSelector": OUTGOING_MESSAGE_TEXT_SELECTOR,
        "message": rendered_message,
        "countBefore": count_before,
    }
    attempts = max(1, verification_attempts)
    for attempt in range(attempts):
        try:
            page.wait_for_function(
                MESSAGE_DELIVERED_SCRIPT,
                arg=verification_arguments,
                timeout=timeout,
            )
            break
        except PlaywrightTimeoutError as error:
            if attempt == attempts - 1:
                raise MessageDeliveryError(
                    "Douyin did not render a new outgoing message after one send attempt"
                ) from error
            logger.warning(
                "Delivery confirmation is delayed; observing again without resending",
                extra={
                    "event": "message_delivery_confirmation_delayed",
                    "run_id": run_id,
                    "attempt": attempt + 1,
                    "attempts": attempts,
                },
            )

    page.wait_for_timeout(POST_SEND_SETTLE_MS)


def activate_conversation(page, element, timeout):
    """Select a conversation and wait for its message history to settle."""
    element.click()
    page.wait_for_function(
        CONVERSATION_SELECTED_SCRIPT,
        arg=element.element_handle(),
        timeout=timeout,
    )
    page.wait_for_timeout(CONVERSATION_SETTLE_MS)


def ensure_all_targets_sent(targets, sent_targets):
    missing_count = len(set(targets) - set(sent_targets))
    if missing_count:
        raise MessageDeliveryError(
            f"Message delivery was not verified for {missing_count} configured target(s)"
        )


def handle_response(response: Response):
    """
    只监听你要的那个接口响应
    """
    global userIDDict
    # 精准匹配目标接口 URL
    if "aweme/v1/web/im/user/info" in response.url:
        # print(f"URL: {response.url}")
        # print(f"状态码: {response.status}")
        try:
            # 获取接口返回的 JSON 数据
            json_data = response.json()
            # print("\n📦 响应 JSON 数据：")
            # print(json.dumps(json_data, indent=4, ensure_ascii=False))
            for item in json_data.get("data", []):
                short_id = item.get("short_id")  # short_id
                unique_id = item.get("unique_id")  # unique_id
                sec_uid = item.get("sec_uid", "")  # sec_uid 可能不存在，提供默认值为空字符串
                nickname = norm(item.get("nickname"))  # 昵称
                remark_name = norm(item.get("remark_name", nickname))  #  备注名，如果没有则使用昵称
                userIDDict[remark_name] = [short_id, unique_id, sec_uid, nickname, remark_name]
        except Exception as error:
            logger.warning(
                "Douyin user information response could not be parsed",
                extra={
                    "event": "target_identity_response_parse_failed",
                    "error_type": type(error).__name__,
                },
            )


def retry_operation(name, operation, retries=3, delay=2, *args, **kwargs):
    """
    通用的重试逻辑
    :param name: 操作名称（用于日志记录）
    :param operation: 要执行的异步操作
    :param retries: 最大重试次数
    :param delay: 每次重试之间的延迟（秒）
    :param args: 传递给操作的参数
    :param kwargs: 传递给操作的关键字参数
    """
    for attempt in range(retries):
        try:
            return operation(*args, **kwargs)
        except Exception as error:
            if attempt < retries - 1:
                logger.warning(
                    "Browser operation failed and will be retried",
                    extra={
                        "event": "browser_operation_retry",
                        "attempt": attempt + 1,
                        "attempts": retries,
                        "error_type": type(error).__name__,
                    },
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Browser operation exhausted its retries",
                    extra={
                        "event": "browser_operation_failed",
                        "attempt": attempt + 1,
                        "attempts": retries,
                        "error_type": type(error).__name__,
                    },
                )
                raise


def open_chat_page(page):
    """Open Douyin chat without waiting for the SPA's long-lived load event."""
    retry_operation(
        "打开抖音网页聊天页面",
        page.goto,
        retries=config["taskRetryTimes"],
        delay=5,
        url="https://www.douyin.com/chat",
        wait_until="domcontentloaded",
    )
    page.wait_for_selector(
        CONVERSATION_LIST_SELECTOR,
        timeout=config["browserTimeout"],
    )


def dismiss_trust_login_dialog(page, timeout=TRUST_LOGIN_DIALOG_TIMEOUT_MS):
    """Cancel Douyin's temporary save-login-information prompt when it appears."""
    try:
        page.locator(TRUST_LOGIN_CANCEL_SELECTOR).click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


def target_identity_data_ready(targets):
    """Return whether Douyin's user-info responses identify a configured target."""
    normalized_targets = {norm(str(target)) for target in targets if target}
    for identity_values in userIDDict.values():
        normalized_values = {
            norm(str(value)) for value in identity_values if value
        }
        if normalized_targets.intersection(normalized_values):
            return True
    return False


def wait_for_target_identity_data(
    page,
    targets,
    timeout=TARGET_IDENTITY_WAIT_TIMEOUT_MS,
    poll_interval=TARGET_IDENTITY_POLL_MS,
):
    """Wait only as long as needed for the target's user-info response."""
    elapsed = 0
    while elapsed < timeout:
        if target_identity_data_ready(targets):
            return True
        wait_ms = min(poll_interval, timeout - elapsed)
        page.wait_for_timeout(wait_ms)
        elapsed += wait_ms
    return target_identity_data_ready(targets)


def prepare_chat_page(page, account_label, targets):
    """Open chat and wait for the data needed to identify target conversations."""
    open_chat_page(page)
    dismiss_trust_login_dialog(page)

    identity_ready = wait_for_target_identity_data(
        page,
        targets,
        timeout=max(config["friendListTimeout"], TARGET_IDENTITY_WAIT_TIMEOUT_MS),
    )
    if identity_ready:
        logger.debug(f"{account_label} 已加载目标好友身份信息")
    else:
        logger.warning(
            f"{account_label} 等待目标好友身份信息超时，将继续按聊天标题查找"
        )


def checkTargetName(targetName, targets):
    """检查targetName是否为目标
    """
    
    targetSymbol = None
    
    targetName = norm(targetName)
    
    if targetName in userIDDict:
        matched = next((v for v in userIDDict[targetName] if v and v in targets), None)
        if matched is not None:
            targetSymbol = matched
    else:
        if targetName in targets:
            targetSymbol = targetName
    return targetSymbol


def scroll_and_select_user(page, account_label, targets):
    """尝试滚动并查找用户名"""
    # 定义目标元素和滚动容器的选择器
    target_selector = CONVERSATION_ITEM_SELECTOR
    scrollable_friends_selector = CONVERSATION_LIST_SELECTOR

    # [修复] 使用模糊匹配 no-more-tip- 前缀，不再依赖精确哈希后缀
    # 同时增加文本匹配作为兜底
    # no_more_selector = 'xpath=//div[contains(@class, "no-more-tip-")]'
    # loading_selector = 'xpath=//div[contains(@class, "semi-spin")]'

    logger.debug(f"{account_label} 开始查找 {len(targets)} 个目标好友")

    found_targets = set()
    # [修改] 复制一份目标列表用于追踪进度
    remaining_targets = set(targets)

    # [修复] 新增：连续空滚动计数器（滚动后没有发现新好友的次数）
    empty_scroll_count = 0
    MAX_EMPTY_SCROLLS = 10  # 连续10次滚动没有新好友，认为到底了

    while True:
        # 查找所有目标元素
        target_elements = page.locator(target_selector).all()

        # [修复] 记录本轮循环前已发现的好友数，用于判断是否有新发现
        prev_found_count = len(found_targets)

        for element in target_elements:
            try:
                # 查找子元素 span，模糊匹配 class
                span = element.locator(CONVERSATION_TITLE_SELECTOR)
                targetName = span.inner_text()

                if targetName in found_targets:
                    continue  # 已处理过，跳过
                found_targets.add(targetName)

                logger.debug(f"{account_label} 找到一个好友候选项")
                
                targetSymbol = checkTargetName(targetName, targets)

                if targetSymbol:
                    activate_conversation(page, element, config["browserTimeout"])
                    
                    yield targetSymbol

                    # [修改] 标记已找到，如果全找到了直接退出
                    if targetSymbol in remaining_targets:
                        remaining_targets.remove(targetSymbol)
                    if len(remaining_targets) == 0:
                        logger.debug(f"{account_label} 所有目标好友均已找到，停止搜索")
                        return
                    break
            except Exception as error:
                logger.warning(
                    "A conversation candidate could not be inspected",
                    extra={
                        "event": "conversation_candidate_scan_failed",
                        "account": account_label,
                        "error_type": type(error).__name__,
                    },
                )
        else:
            # [修复] 检查本轮是否有新好友被发现
            new_found = len(found_targets) > prev_found_count
            if new_found:
                empty_scroll_count = 0  # 有新发现，重置计数器
            else:
                empty_scroll_count += 1  # 无新发现，递增计数器

            # [修复] 状态检测逻辑（多重兜底）

            # # 1. 检查是否到底（"没有更多了" —— 使用模糊类名匹配）
            # if page.locator(no_more_selector).count() > 0:
            #     logger.info(f"账号 {username} 检测到'没有更多了'标志，已到达底部")
            #     if len(remaining_targets) > 0:
            #         logger.warning(
            #             f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}"
            #         )
            #     break

            # 2. [修复] 检查连续空滚动次数，防止死循环
            if empty_scroll_count >= MAX_EMPTY_SCROLLS:
                logger.warning(
                    f"{account_label} 连续 {MAX_EMPTY_SCROLLS} 次滚动未发现新好友，判定已到达底部"
                )
                if len(remaining_targets) > 0:
                    logger.warning(
                        f"{account_label} 搜索结束，仍有 {len(remaining_targets)} 个好友未找到"
                    )
                break


            # 3. 检查是否正在加载
            # if page.locator(loading_selector).count() > 0:
            #     logger.debug(f"账号 {username} 列表正在加载中 (Loading)...")
            #     time.sleep(1.5)  # 给加载留点时间
            #     # 不 break，继续去滚动以触发后续内容

            # 4. 滚动容器
            scrollable_element = page.locator(
                scrollable_friends_selector
            ).element_handle()

            if scrollable_element:
                # [修复] 记录滚动前的 scrollTop，用于检测是否真的滚动了
                scroll_top_before = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )

                page.evaluate(
                    "(element) => element.scrollTop += 800", scrollable_element
                )

                # [修复] 检测滚动后的 scrollTop
                time.sleep(0.3)
                scroll_top_after = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )

                if scroll_top_before == scroll_top_after:
                    # scrollTop 没有变化，说明已经到底了
                    empty_scroll_count += 2  # 加速判定到底
                    logger.debug(
                        f"{account_label} scrollTop 未变化 ({scroll_top_before})，可能已到底 (空滚动计数: {empty_scroll_count}/{MAX_EMPTY_SCROLLS})"
                    )
                else:
                    logger.debug(
                        f"{account_label} 滚动好友列表以加载更多好友 (scrollTop: {scroll_top_before} -> {scroll_top_after})"
                    )

                time.sleep(1.5)
            else:
                logger.error(f"{account_label} 未找到滚动容器，退出")
                break


def send_targets_with_recovery(
    page,
    account_label,
    targets,
    max_search_attempts=None,
    run_id=None,
):
    """Send once per target, retrying only discovery of targets still missing."""
    configured_attempts = max_search_attempts or config["taskRetryTimes"]
    search_attempts = max(1, min(configured_attempts, 3))
    sent_targets = set()
    failed_targets = set()

    for search_attempt in range(1, search_attempts + 1):
        remaining_targets = set(targets) - sent_targets - failed_targets
        if not remaining_targets:
            break

        if search_attempt > 1:
            logger.warning(
                f"{account_label} 将重新加载聊天列表查找剩余目标，"
                f"第 {search_attempt}/{search_attempts} 次",
                extra={
                    "event": "target_discovery_retry",
                    "run_id": run_id,
                    "account": account_label,
                    "attempt": search_attempt,
                    "attempts": search_attempts,
                    "remaining_count": len(remaining_targets),
                },
            )
            prepare_chat_page(page, account_label, remaining_targets)

        for target_symbol in scroll_and_select_user(
            page,
            account_label,
            remaining_targets,
        ):
            if target_symbol in sent_targets:
                continue

            logger.debug(f"{account_label} 已选中目标好友发送消息")
            page.wait_for_selector(
                CHAT_EDITOR_INPUT_SELECTOR,
                timeout=config["browserTimeout"],
            )
            chat_input = page.locator(CHAT_EDITOR_INPUT_SELECTOR)

            try:
                message = build_message()
                send_message_verified(page, chat_input, message, run_id=run_id)
            except Exception as error:
                failed_targets.add(target_symbol)
                logger.error(
                    "Message send could not be verified and will not be retried",
                    extra={
                        "event": "message_send_failed",
                        "run_id": run_id,
                        "account": account_label,
                        "verified_count": len(sent_targets),
                        "target_count": len(targets),
                        "error_type": type(error).__name__,
                    },
                )
                continue

            sent_targets.add(target_symbol)
            logger.info(
                "Message send was verified",
                extra={
                    "event": "message_send_verified",
                    "run_id": run_id,
                    "account": account_label,
                    "verified_count": len(sent_targets),
                    "target_count": len(targets),
                },
            )

    return TargetSendResult(
        target_count=len(targets),
        verified_count=len(sent_targets),
    )


def do_user_task(browser, account_label, cookies, targets, run_id=None):
    userIDDict.clear()
    context = browser.new_context()  # 每个任务使用独立的上下文
    context.set_default_navigation_timeout(
        config["browserTimeout"]
    )  # 设置导航超时时间为 120 秒
    context.set_default_timeout(
        config["browserTimeout"]
    )  # 设置所有操作的默认超时时间为 120 秒

    try:
        page = context.new_page()
        page.on("response", handle_response)
        context.add_cookies(cookies)

        prepare_chat_page(page, account_label, targets)
        logger.debug(f"{account_label} 开始发送消息")
        return send_targets_with_recovery(
            page,
            account_label,
            targets,
            run_id=run_id,
        )
    finally:
        try:
            context.close()
        except Exception as error:
            logger.warning(
                "Browser context cleanup failed",
                extra={
                    "event": "browser_context_cleanup_failed",
                    "run_id": run_id,
                    "account": account_label,
                    "error_type": type(error).__name__,
                },
            )


def runTasks():
    run_id = create_run_id()
    started_at = time.monotonic()
    target_count = sum(len(user["targets"]) for user in userData)
    verified_count = 0
    completed_account_count = 0
    runtime_error_type = None
    playwright = None
    browser = None
    try:
        playwright, browser = get_browser()
        # 检查是否启用多任务和任务数量
        # 创建信号量以限制并发任务数量
        logger.info(
            "Scheduled messaging run started",
            extra={
                "event": "run_started",
                "run_id": run_id,
                "account_count": len(userData),
            },
        )
        logger.debug(f"已加载 {len(userData)} 个账号任务")

        for account_index, user in enumerate(userData, start=1):
            cookies = user["cookies"]
            targets = user["targets"]
            account_label = f"account-{account_index}"
            logger.info(
                "Account task started",
                extra={
                    "event": "account_task_started",
                    "run_id": run_id,
                    "account": account_label,
                    "target_count": len(targets),
                },
            )
            try:
                account_result = do_user_task(
                    browser,
                    account_label,
                    cookies,
                    targets,
                    run_id=run_id,
                )
            except Exception as error:
                logger.error(
                    "Account task failed before producing a delivery result",
                    extra={
                        "event": "account_task_failed",
                        "run_id": run_id,
                        "account": account_label,
                        "target_count": len(targets),
                        "outcome": "failure",
                        "error_type": type(error).__name__,
                    },
                )
                continue

            verified_count += account_result.verified_count
            if account_result.failed_count == 0:
                completed_account_count += 1
            if account_result.failed_count == 0:
                account_outcome = "success"
            elif account_result.verified_count:
                account_outcome = "partial_success"
            else:
                account_outcome = "failure"
            logger.info(
                "Account task completed",
                extra={
                    "event": "account_task_completed",
                    "run_id": run_id,
                    "account": account_label,
                    "target_count": account_result.target_count,
                    "verified_count": account_result.verified_count,
                    "failed_count": account_result.failed_count,
                    "outcome": account_outcome,
                },
            )
    except Exception as error:
        runtime_error_type = type(error).__name__
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as error:
                logger.warning(
                    "Browser cleanup failed",
                    extra={
                        "event": "browser_cleanup_failed",
                        "run_id": run_id,
                        "error_type": type(error).__name__,
                    },
                )
        if playwright is not None:
            try:
                playwright.stop()
            except Exception as error:
                logger.warning(
                    "Playwright cleanup failed",
                    extra={
                        "event": "playwright_cleanup_failed",
                        "run_id": run_id,
                        "error_type": type(error).__name__,
                    },
                )

    summary = RunSummary.from_counts(
        run_id=run_id,
        target_count=target_count,
        verified_count=verified_count,
        account_count=len(userData),
        completed_account_count=completed_account_count,
        duration_ms=round((time.monotonic() - started_at) * 1000),
    )
    log_method = (
        logger.info
        if summary.status is RunStatus.SUCCESS
        else logger.warning
        if summary.status is RunStatus.PARTIAL_SUCCESS
        else logger.error
    )
    event = (
        "run_completed"
        if summary.status is RunStatus.SUCCESS
        else "run_partial_success"
        if summary.status is RunStatus.PARTIAL_SUCCESS
        else "run_failed"
    )
    final_fields = {
        "event": event,
        "run_id": run_id,
        "account_count": summary.account_count,
        "completed_account_count": summary.completed_account_count,
        "target_count": summary.target_count,
        "verified_count": summary.verified_count,
        "failed_count": summary.failed_count,
        "duration_ms": summary.duration_ms,
        "outcome": summary.status.value.lower(),
    }
    if runtime_error_type is not None:
        final_fields["error_type"] = runtime_error_type

    log_method(
        "Scheduled messaging run produced a final result",
        extra=final_fields,
    )
    return summary
