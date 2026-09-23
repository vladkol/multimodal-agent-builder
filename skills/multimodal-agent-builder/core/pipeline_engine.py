"""Process-Agnostic Multimodal Multi-Agent Pipeline Engine.

Executes custom agent teams architected specifically for any automated business
or creative process. Supports multimodal inputs (text + multiple images),
intermediate asset passing, universal user interaction via BuiltinTools.ASK_QUESTION,
and cloud storage delivery.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, TypeVar, Union

import pydantic
from google.antigravity import Agent, LocalAgentConfig, policy, types

from .asset_tools import (
    DEFAULT_GENERIC_MODEL,
    DEFAULT_LOCATION,
    _get_current_project,
    generate_image_tool,
    generate_video_tool,
    upload_to_gcs_tool,
)
from .console_runner import ConsoleAskQuestionHook, GateDecision, prompt_approval_gate
from .multimodal_input import MultimodalInputBundle

logger = logging.getLogger(__name__)


def _default_retry_config() -> types.RetryConfig:
    """Builds a resilient SDK RetryConfig for transient API and schema errors."""
    return types.RetryConfig(
        api_retry=types.ModelAPIRetryConfig(
            max_retries=5,
            initial_sleep_duration_ms=1500,
            exponential_multiplier=2.0,
            jitter_range=0.2,
        ),
        model_output_retry=types.ModelOutputRetryConfig(
            max_retries=4,
        ),
    )


@dataclass
class PipelineState:
    """Consolidated state tracking pipeline execution, assets, and decisions."""

    input_bundle: MultimodalInputBundle
    data: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    stage_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    revision_history: List[Dict[str, Any]] = field(default_factory=list)
    cloud_urls: Dict[str, str] = field(default_factory=dict)

    def set_artifact(self, label: str, path_or_url: str) -> None:
        """Records an intermediate or final asset path or URL."""
        self.artifacts[label] = path_or_url

    def get_artifact(self, label: str) -> Optional[str]:
        """Retrieves an artifact by label."""
        return self.artifacts.get(label)

    def save_checkpoint(self, checkpoint_path: Path) -> None:
        """Persists current pipeline state to a JSON checkpoint file."""
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "prompt": self.input_bundle.prompt,
            "images": [img.path for img in self.input_bundle.images],
            "data": self.data,
            "artifacts": self.artifacts,
            "stage_outputs": self.stage_outputs,
            "revision_history": self.revision_history,
            "cloud_urls": self.cloud_urls,
        }
        checkpoint_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def restore_from_checkpoint(self, checkpoint_path: Path) -> bool:
        """Restores state from a checkpoint file if inputs match."""
        if not checkpoint_path.exists():
            return False
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            current_images = [img.path for img in self.input_bundle.images]
            if (
                payload.get("prompt") != self.input_bundle.prompt
                or payload.get("images") != current_images
            ):
                return False
            self.data = payload.get("data", {})
            self.artifacts = payload.get("artifacts", {})
            self.stage_outputs = payload.get("stage_outputs", {})
            self.revision_history = payload.get("revision_history", [])
            self.cloud_urls = payload.get("cloud_urls", {})
            return True
        except Exception as e:
            logger.warning(f"Could not load checkpoint {checkpoint_path}: {e}")
            return False


T = TypeVar("T", bound=pydantic.BaseModel)

StageRunFn = Callable[[Agent, PipelineState, Optional[str]], Awaitable[Dict[str, Any]]]


@dataclass
class Stage:
    """Specification of an individual process stage executed by a specialized subagent."""

    name: str
    subagent_config: types.SubagentConfig
    run_fn: StageRunFn
    description: str = ""
    response_schema: Optional[Type[pydantic.BaseModel]] = None
    requires_approval: bool = False
    approval_question: Optional[str] = None
    approve_label: str = "Approve & Proceed to next stage"
    deny_label: str = "Deny / Revise (return to current or earlier stage)"


class StageRoutingDecision(pydantic.BaseModel):
    """Structured routing decision emitted by the agent when a human gate is not approved."""

    target_stage: str = pydantic.Field(
        description=(
            "The exact name of the stage to return to (must be one of the candidate previous/current stages)."
        )
    )
    revision_instructions: str = pydantic.Field(
        description=(
            "Concrete, actionable revision instructions to pass to `target_stage` incorporating the human's response."
        )
    )
    reasoning: str = pydantic.Field(
        description="Explanation of why `target_stage` was selected based on the human's non-approval response."
    )


async def execute_structured_turn(
    prompt: types.Content,
    response_schema: Type[T],
    system_instructions: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    skills_paths: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    autonomous: bool = False,
    max_session_retries: int = 3,
) -> tuple[T, types.ChatResponse]:
    """Executes an agent turn strictly adhering to a native Pydantic response_schema.

    Uses Antigravity SDK's native structured output capability with both SDK-level
    `RetryConfig` and session-level retry for transient HTTP/2 stream drops.
    """
    resolved_project = project_id or _get_current_project()
    cfg = LocalAgentConfig(
        vertex=True,
        project=resolved_project,
        location=DEFAULT_LOCATION,
        model=DEFAULT_GENERIC_MODEL,
        system_instructions=system_instructions,
        skills_paths=skills_paths or [],
        tools=tools or [],
        response_schema=response_schema,
        retry_config=_default_retry_config(),
        hooks=[ConsoleAskQuestionHook(autonomous=autonomous)],
        policies=[policy.allow_all()],
        capabilities=types.CapabilitiesConfig(
            agent_behavior=types.AgentBehavior.INTERACTIVE,
            enabled_tools=[
                *types.BuiltinTools.default(),
                types.BuiltinTools.ASK_QUESTION,
            ],
        ),
    )

    last_err: Optional[Exception] = None
    for attempt in range(1, max_session_retries + 1):
        try:
            async with Agent(cfg) as agent:
                response = await agent.chat(prompt)
                raw_output = await response.structured_output()
                if raw_output is None:
                    raise ValueError(
                        f"Agent did not emit structured output for {response_schema.__name__}. "
                        f"Ensure the model called the finish tool matching the schema."
                    )
                validated = response_schema.model_validate(raw_output)
                return validated, response
        except Exception as e:
            last_err = e
            if attempt < max_session_retries:
                backoff = 2.5 * attempt
                logger.warning(
                    f"Structured turn ({response_schema.__name__}) attempt {attempt}/{max_session_retries} "
                    f"interrupted ({e}); retrying in {backoff:.1f}s..."
                )
                await asyncio.sleep(backoff)
            else:
                raise

    assert last_err is not None
    raise last_err


async def resolve_rollback_stage(
    current_stage_name: str,
    candidate_stages: List[Stage],
    user_response: str,
    state: PipelineState,
    project_id: Optional[str] = None,
) -> StageRoutingDecision:
    """Determines which previous (or current) stage the workflow should return to when a gate is not approved."""
    stage_catalog = "\n".join(
        f"  - '{s.name}' (Subagent: {s.subagent_config.name}): {s.description or s.subagent_config.description}"
        for s in candidate_stages
    )
    valid_names = [s.name for s in candidate_stages]

    router_instructions = (
        "You are the Pipeline Gate Router. A human reviewer did NOT approve the current stage gate. "
        "Your job is to inspect the human's response/feedback and decide which stage in `valid_stages` "
        "(either the current stage or an earlier stage) the workflow must rewind to so the feedback can be addressed.\n"
        "Rules:\n"
        f"1. `target_stage` MUST be one of: {valid_names}.\n"
        "2. If the user's feedback asks to change high-level concepts, layout directions, or initial parameters, "
        "route back to the earliest concept/planning stage.\n"
        "3. If the user's feedback only asks to adjust or regenerate the current stage's artifact (e.g. re-render image "
        "or adjust camera motion), route to the stage responsible for that artifact.\n"
        "4. Formulate clear, self-contained `revision_instructions` that the target stage subagent will execute."
    )

    prompt_text = (
        f"CURRENT BLOCKED GATE STAGE: '{current_stage_name}'\n"
        f"CANDIDATE STAGES TO RETURN TO (in chronological order):\n{stage_catalog}\n\n"
        f"HUMAN NON-APPROVAL RESPONSE / FEEDBACK:\n{user_response}\n\n"
        f"CURRENT PIPELINE ARTIFACTS:\n{json.dumps(state.artifacts, indent=2)}\n\n"
        f"Select `target_stage` from {valid_names} and provide `revision_instructions`."
    )

    decision, _ = await execute_structured_turn(
        prompt=prompt_text,
        response_schema=StageRoutingDecision,
        system_instructions=router_instructions,
        project_id=project_id,
        autonomous=True,
    )

    # Deterministic clamp: never allow target_stage outside candidate_stages
    if decision.target_stage not in valid_names:
        logger.warning(
            f"Router suggested stage '{decision.target_stage}' outside valid rollback set {valid_names}; "
            f"clamping to '{current_stage_name}'."
        )
        decision.target_stage = current_stage_name

    return decision


class PipelineEngine:
    """Coordinates the execution of process-specific multi-agent teams."""

    def __init__(
        self,
        stages: List[Stage],
        project_id: Optional[str] = None,
        skills_paths: Optional[List[str]] = None,
        tools: Optional[List[Any]] = None,
        checkpoint_path: Optional[Union[str, Path]] = None,
    ):
        self.stages = stages
        self.project_id = project_id or _get_current_project()
        self.skills_paths = skills_paths or []
        self.default_tools = tools or [
            generate_image_tool,
            generate_video_tool,
            upload_to_gcs_tool,
        ]
        self.checkpoint_path = Path(checkpoint_path).resolve() if checkpoint_path else None

    def _build_agent_config(self, autonomous: bool = False) -> LocalAgentConfig:
        """Constructs LocalAgentConfig with universal ConsoleAskQuestionHook, subagents, and tools."""
        subagents = [s.subagent_config for s in self.stages]
        subagent_names = [s.subagent_config.name for s in self.stages]

        return LocalAgentConfig(
            vertex=True,
            project=self.project_id,
            location=DEFAULT_LOCATION,
            model=DEFAULT_GENERIC_MODEL,
            skills_paths=self.skills_paths,
            subagents=subagents,
            tools=self.default_tools,
            retry_config=_default_retry_config(),
            hooks=[ConsoleAskQuestionHook(autonomous=autonomous)],
            policies=[policy.allow_all()],
            capabilities=types.CapabilitiesConfig(
                enable_subagents=True,
                allowed_subagents=subagent_names,
                agent_behavior=types.AgentBehavior.INTERACTIVE,
                enabled_tools=[
                    *types.BuiltinTools.default(),
                    types.BuiltinTools.ASK_QUESTION,
                ],
            ),
        )

    async def execute(
        self,
        inputs: MultimodalInputBundle,
        autonomous: bool = False,
        resume: bool = True,
    ) -> PipelineState:
        """Executes the multi-stage pipeline with deterministic approval gates and iterative rollback routing.

        Args:
            inputs: MultimodalInputBundle with prompt and optional reference images.
            autonomous: If True, auto-answers any agent questions using default options.
            resume: If True and checkpoint_path is configured, skips already-completed stages.

        Returns:
            Completed PipelineState with all stage outputs and artifacts.
        """
        state = PipelineState(input_bundle=inputs)
        if resume and self.checkpoint_path and state.restore_from_checkpoint(self.checkpoint_path):
            logger.info(
                f"Restored pipeline checkpoint from {self.checkpoint_path} "
                f"(completed stages: {list(state.stage_outputs.keys())})"
            )

        config = self._build_agent_config(autonomous=autonomous)

        divider = "-" * 64
        print(f"\n{divider}")
        print(f"▶ INITIALIZING MULTIMODAL PROCESS PIPELINE ({len(self.stages)} Stages)")
        print(f"  Prompt: {inputs.prompt[:75]}...")
        print(f"  Input Images: {len(inputs.images)}")
        print(f"  Subagents: {[s.subagent_config.name for s in self.stages]}")
        print(f"  Interaction Hook: ConsoleAskQuestionHook (autonomous={autonomous})")
        print(f"{divider}\n")

        pending_revision: Dict[str, str] = {}
        stage_idx = 0

        async with Agent(config) as agent:
            while stage_idx < len(self.stages):
                stage = self.stages[stage_idx]
                revision_note = pending_revision.pop(stage.name, None)

                if resume and stage.name in state.stage_outputs and revision_note is None:
                    print(
                        f"[{stage_idx + 1}/{len(self.stages)}] Skipping Stage: '{stage.name}' "
                        f"({stage.subagent_config.name}) — restored from checkpoint.\n"
                    )
                    stage_idx += 1
                    continue

                if revision_note:
                    print(
                        f"[{stage_idx + 1}/{len(self.stages)}] Re-Running Stage: '{stage.name}' "
                        f"({stage.subagent_config.name}) with Revision Instructions:\n"
                        f"  ↳ {revision_note}"
                    )
                else:
                    print(
                        f"[{stage_idx + 1}/{len(self.stages)}] Running Stage: '{stage.name}' "
                        f"({stage.subagent_config.name})..."
                    )

                stage_output = await stage.run_fn(agent, state, revision_note)

                # Deterministic Gate Enforcement:
                # If the stage declares `requires_approval=True` or returned a `GateDecision` in `stage_output`,
                # the workflow CANNOT move past `stage_idx` unless `gate_decision.approved is True`.
                gate_decision: Optional[GateDecision] = None
                if isinstance(stage_output.get("gate_decision"), GateDecision):
                    gate_decision = stage_output.pop("gate_decision")
                elif stage.requires_approval:
                    question_str = (
                        stage.approval_question
                        or f"Approve outputs of Stage '{stage.name}' ({stage.subagent_config.name}) to proceed?"
                    )
                    gate_decision = prompt_approval_gate(
                        question=question_str,
                        approve_label=stage.approve_label,
                        deny_label=stage.deny_label,
                        autonomous=autonomous,
                    )

                if gate_decision is not None and gate_decision.approved is not True:
                    # Gate NOT approved -> Deterministically block forward progression and route to a previous/current stage
                    candidate_stages = self.stages[: stage_idx + 1]
                    routing = await resolve_rollback_stage(
                        current_stage_name=stage.name,
                        candidate_stages=candidate_stages,
                        user_response=gate_decision.raw_response,
                        state=state,
                        project_id=self.project_id,
                    )
                    target_idx = next(
                        (i for i, s in enumerate(self.stages) if s.name == routing.target_stage),
                        stage_idx,
                    )
                    # Deterministic safety guarantee: never jump forward
                    target_idx = min(target_idx, stage_idx)
                    target_stage_name = self.stages[target_idx].name

                    print(
                        f"🔄 GATE ROUTER DECISION:\n"
                        f"  • Blocked at Stage: '{stage.name}'\n"
                        f"  • Rewinding Workflow to Stage [{target_idx + 1}/{len(self.stages)}]: '{target_stage_name}'\n"
                        f"  • Reasoning: {routing.reasoning}\n"
                        f"  • Revision Instructions: {routing.revision_instructions}\n"
                    )

                    # Invalidate stage_outputs from target_idx onwards so they are re-executed cleanly
                    for invalidated in self.stages[target_idx : stage_idx + 1]:
                        state.stage_outputs.pop(invalidated.name, None)

                    state.revision_history.append(
                        {
                            "from_stage": stage.name,
                            "to_stage": target_stage_name,
                            "user_response": gate_decision.raw_response,
                            "revision_instructions": routing.revision_instructions,
                            "reasoning": routing.reasoning,
                        }
                    )
                    pending_revision[target_stage_name] = routing.revision_instructions
                    if self.checkpoint_path:
                        state.save_checkpoint(self.checkpoint_path)

                    stage_idx = target_idx
                    continue

                # Gate passed (or no approval gate on this stage) -> record completion and advance
                state.stage_outputs[stage.name] = stage_output
                if self.checkpoint_path:
                    state.save_checkpoint(self.checkpoint_path)

                print(f"✔ Stage '{stage.name}' completed.\n")
                stage_idx += 1

        print(f"\n{divider}")
        print("🎉 PIPELINE EXECUTION COMPLETED")
        print(f"Artifacts Produced: {len(state.artifacts)}")
        for k, v in state.artifacts.items():
            print(f"  • {k}: {v}")
        print(f"{divider}\n")

        return state

