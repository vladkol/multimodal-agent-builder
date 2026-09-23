"""Universal Antigravity SDK Console Interaction Runner.

Provides universal integration with google.antigravity SDK's BuiltinTools.ASK_QUESTION
and AskQuestionHook (hooks.OnInteractionHook) for user interaction, preference choices,
clarifications, and reviews, with full support for headless autonomous evaluation.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Union

from google.antigravity import hooks, types
from google.antigravity.utils.interactive import async_input

logger = logging.getLogger(__name__)


class ConsoleAskQuestionHook(hooks.OnInteractionHook):
    """Universal SDK-native interaction hook for BuiltinTools.ASK_QUESTION.

    Fulfills ask_question tool calls executed by the agent or subagents for ANY
    interaction the agent initiates (clarifications, preferences, approvals, feedback):
    - Interactive Mode: Renders the agent's question and options in the console,
      handles user selection by number, ID, or text, or captures freeform input.
    - Autonomous Mode: Automatically selects the default option without blocking,
      logging the decision for CI/CD and unattended testing.
    """


    def __init__(self, autonomous: bool = False, default_index: int = 0):
        self.autonomous = autonomous
        self.default_index = default_index

    async def run(
        self,
        context: hooks.HookContext,
        data: types.AskQuestionInteractionSpec,
    ) -> types.QuestionHookResult:
        """Executes the interaction hook whenever the model calls ask_question.

        Args:
            context: The hook context provided by the SDK.
            data: The interaction specification containing questions and options.

        Returns:
            QuestionHookResult populated with user or autonomous responses.
        """
        questions = data.questions
        responses: List[types.QuestionResponse] = []

        divider = "-" * 64
        print(f"\n{divider}")
        print("💬 AGENT QUESTION (BuiltinTools.ASK_QUESTION)")
        print(divider)

        for q in questions:
            options = list(q.options) if hasattr(q, "options") else []
            print(f"\n? {q.question}")
            for idx, opt in enumerate(options, 1):
                marker = " (default)" if idx - 1 == self.default_index else ""
                print(f"  [{idx}] {opt.text}{marker}")

            # Autonomous / Headless mode: resolve without blocking
            if self.autonomous:
                if options:
                    selected_idx = (
                        self.default_index
                        if 0 <= self.default_index < len(options)
                        else 0
                    )
                    selected = options[selected_idx]
                    print(f"  [AUTONOMOUS RESPONSE]: {selected.text} (ID: '{selected.id}')\n")
                    responses.append(
                        types.QuestionResponse(selected_option_ids=[selected.id])
                    )
                else:
                    print("  [AUTONOMOUS RESPONSE]: Skipped (no options provided)\n")
                    responses.append(types.QuestionResponse(skipped=True))
                continue

            # Interactive mode
            try:
                prompt_str = (
                    f"\nResponse [1-{len(options)}] (default: {self.default_index + 1}) > "
                    if options
                    else "\nResponse > "
                )
                ans = await async_input(prompt_str)
                ans = ans.strip()

                # Enter pressed with no input -> use default option if available
                if not ans:
                    if options and 0 <= self.default_index < len(options):
                        default_opt = options[self.default_index]
                        print(f"✔ Selected: {default_opt.text}\n")
                        responses.append(
                            types.QuestionResponse(selected_option_ids=[default_opt.id])
                        )
                    else:
                        responses.append(types.QuestionResponse(skipped=True))
                    continue

                # 1. Match by numeric option index (1-based)
                matched_id: Optional[str] = None
                if options and ans.isdigit():
                    num = int(ans)
                    if 1 <= num <= len(options):
                        matched_id = options[num - 1].id

                # 2. Match by exact ID or option text substring
                if not matched_id and options:
                    for opt in options:
                        if ans.lower() == opt.id.lower() or ans.lower() == opt.text.lower():
                            matched_id = opt.id
                            break
                    if not matched_id:
                        for opt in options:
                            if ans.lower() in opt.text.lower():
                                matched_id = opt.id
                                break

                if matched_id:
                    matched_opt = next((o for o in options if o.id == matched_id), None)
                    text_disp = matched_opt.text if matched_opt else matched_id
                    if matched_opt and ("custom" in matched_opt.id.lower() or "[custom]" in matched_opt.text.lower() or "enter your own" in matched_opt.text.lower()):
                        custom_input = (await async_input("Enter your custom answer > ")).strip()
                        if custom_input:
                            print(f"✔ Custom response entered: {custom_input}\n")
                            responses.append(types.QuestionResponse(freeform_response=custom_input))
                            continue
                    print(f"✔ Selected: {text_disp}\n")
                    responses.append(
                        types.QuestionResponse(selected_option_ids=[matched_id])
                    )
                else:
                    # User provided a custom / freeform response
                    print(f"✔ Response entered: {ans}\n")
                    responses.append(types.QuestionResponse(freeform_response=ans))

            except (KeyboardInterrupt, EOFError):
                if options and 0 <= self.default_index < len(options):
                    default_opt = options[self.default_index]
                    print(f"\n[Default selected]: {default_opt.text}\n")
                    responses.append(
                        types.QuestionResponse(selected_option_ids=[default_opt.id])
                    )
                else:
                    return types.QuestionHookResult(responses=responses, cancelled=True)

        print(divider + "\n")
        return types.QuestionHookResult(responses=responses)


# Alias for backward compatibility / convenience
AskQuestionHook = ConsoleAskQuestionHook


def prompt_ask_question(
    question: str,
    options: Union[List[str], List[types.AskQuestionOption]],
    default_index: int = 0,
    autonomous: bool = False,
    allow_custom: bool = True,
) -> str:
    """Universal helper for asking questions directly in console intake scripts.

    Formats the query using standard AskQuestion schemas, respects autonomy,
    and supports custom write-in answers from the user.

    Args:
        question: The question prompt.
        options: List of string options or AskQuestionOption objects.
        default_index: Default option index.
        autonomous: If True, selects default option without blocking.
        allow_custom: If True, automatically adds a [Custom] write-in option if not present.

    Returns:
        The selected option text or custom user answer.
    """
    opts: List[types.AskQuestionOption] = []
    for idx, opt in enumerate(options):
        if isinstance(opt, types.AskQuestionOption):
            opts.append(opt)
        else:
            opts.append(types.AskQuestionOption(id=str(idx + 1), text=str(opt)))

    if allow_custom and not any("custom" in o.text.lower() or "other" in o.text.lower() for o in opts):
        opts.append(types.AskQuestionOption(id="custom", text="[Custom] Provide your own custom answer"))

    if autonomous:
        chosen = opts[default_index] if 0 <= default_index < len(opts) else opts[0]
        print(f"\n? {question}\n  [AUTONOMOUS SELECTION]: {chosen.text}")
        return chosen.text

    print(f"\n? {question}")
    for idx, opt in enumerate(opts, 1):
        marker = " (default)" if idx - 1 == default_index else ""
        print(f"  [{idx}] {opt.text}{marker}")

    while True:
        try:
            choice = input(f"Enter choice [1-{len(opts)}] (default: {default_index + 1}) > ").strip()
            if not choice:
                return opts[default_index].text
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(opts):
                    selected = opts[num - 1]
                    if selected.id == "custom" or "[custom]" in selected.text.lower():
                        custom_ans = input("Enter your custom answer > ").strip()
                        return custom_ans or selected.text
                    return selected.text
            for opt in opts:
                if choice.lower() == opt.text.lower() or choice.lower() in opt.text.lower():
                    if opt.id == "custom" or "[custom]" in opt.text.lower():
                        custom_ans = input("Enter your custom answer > ").strip()
                        return custom_ans or opt.text
                    return opt.text
            # If user typed freeform answer directly, return it
            return choice
        except (KeyboardInterrupt, EOFError):
            print("\n[Default applied]")
            return opts[default_index].text


STRICT_APPROVAL_TOKENS = {"yes", "y", "approve", "approved", "accept", "accepted"}
STRICT_REJECTION_TOKENS = {"no", "n", "deny", "denied", "reject", "rejected", "revise"}


class GateDecision:
    """Deterministic result of an approval or yes/no gate interaction."""

    def __init__(
        self,
        approved: bool,
        raw_response: str,
        selected_option_id: Optional[str] = None,
        selected_option_text: Optional[str] = None,
    ):
        # Enforce strict boolean type
        self.approved: bool = bool(approved)
        self.raw_response: str = raw_response
        self.selected_option_id: Optional[str] = selected_option_id
        self.selected_option_text: Optional[str] = selected_option_text

    def __repr__(self) -> str:
        return (
            f"GateDecision(approved={self.approved}, "
            f"selected_option_id={self.selected_option_id!r}, "
            f"raw_response={self.raw_response!r})"
        )


def prompt_approval_gate(
    question: str,
    approve_label: str = "Approve & Proceed to next stage",
    deny_label: str = "Deny / Revise (stay or return to an earlier stage)",
    custom_label: str = "[Custom] Provide feedback or specify which earlier stage to revisit",
    autonomous: bool = False,
) -> GateDecision:
    """Deterministically evaluates a human-in-the-loop approval / yes-no gate.

    Rule:
    - `approved` is True ONLY if the user explicitly selects the approval option (`[1]` / ID `'approve'`)
      or types an exact affirmative token (`yes`, `y`, `approve`, `approved`).
    - Any other choice (`[2]` Deny, `[3]` Custom) or any freeform text input (even if it contains
      partial words) deterministically sets `approved = False` and captures the user's feedback
      so the pipeline agent can route execution back to the appropriate previous stage.
    """
    opts = [
        types.AskQuestionOption(id="approve", text=approve_label),
        types.AskQuestionOption(id="deny", text=deny_label),
        types.AskQuestionOption(id="custom", text=custom_label),
    ]

    divider = "=" * 64
    print(f"\n{divider}")
    print(f"🔒 DETERMINISTIC APPROVAL GATE")
    print(divider)
    print(f"? {question}")
    for idx, opt in enumerate(opts, 1):
        marker = " (default)" if idx == 1 else ""
        print(f"  [{idx}] {opt.text}{marker}")

    if autonomous:
        print(f"  [AUTONOMOUS GATE APPROVAL]: {opts[0].text}\n{divider}\n")
        return GateDecision(
            approved=True,
            raw_response=opts[0].text,
            selected_option_id="approve",
            selected_option_text=opts[0].text,
        )

    try:
        raw_input = input(f"\nGate Decision [1-{len(opts)}] (1=Approve, 2=Deny, or type feedback) > ").strip()
    except (KeyboardInterrupt, EOFError):
        raw_input = ""

    # Pressing Enter with empty input selects the default option [1] Approve
    if not raw_input or raw_input == "1" or raw_input.lower() in STRICT_APPROVAL_TOKENS:
        print(f"✔ Gate Approved: {opts[0].text}\n{divider}\n")
        return GateDecision(
            approved=True,
            raw_response=raw_input or opts[0].text,
            selected_option_id="approve",
            selected_option_text=opts[0].text,
        )

    # Explicit Deny option [2] or strict rejection token
    if raw_input == "2" or raw_input.lower() in STRICT_REJECTION_TOKENS:
        try:
            feedback = input(
                "Gate Denied. Describe what should be revised (or which earlier stage to return to) > "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            feedback = "User denied approval at gate and requested revision."
        feedback_text = feedback or "User denied approval at gate and requested revision."
        print(f"✖ Gate Denied — Revision requested: {feedback_text}\n{divider}\n")
        return GateDecision(
            approved=False,
            raw_response=feedback_text,
            selected_option_id="deny",
            selected_option_text=opts[1].text,
        )

    # Explicit Custom option [3]
    if raw_input == "3" or raw_input.lower() in {"custom", "[custom]"}:
        try:
            feedback = input(
                "Enter your revision instructions or specify which stage to revisit > "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            feedback = "User requested custom revision at gate."
        feedback_text = feedback or "User requested custom revision at gate."
        print(f"↺ Gate Blocked (Custom Input) — Routing feedback: {feedback_text}\n{divider}\n")
        return GateDecision(
            approved=False,
            raw_response=feedback_text,
            selected_option_id="custom",
            selected_option_text=opts[2].text,
        )

    # Any other freeform response -> deterministically NOT approved!
    print(
        f"↺ Gate Blocked (Non-approval response: {raw_input!r}) — "
        f"Agent will determine which previous stage to return to.\n{divider}\n"
    )
    return GateDecision(
        approved=False,
        raw_response=raw_input,
        selected_option_id=None,
        selected_option_text=None,
    )

