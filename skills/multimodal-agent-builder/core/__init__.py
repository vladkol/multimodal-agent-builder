"""Multimodal Agent Builder Core Toolkit."""

from .asset_tools import (
    DEFAULT_GENERIC_MODEL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_LOCATION,
    DEFAULT_VIDEO_MODEL,
    generate_image_tool,
    generate_video_tool,
    get_agent_platform_client,
    upload_to_gcs_tool,
)
from .console_runner import (
    AskQuestionHook,
    ConsoleAskQuestionHook,
    GateDecision,
    prompt_approval_gate,
    prompt_ask_question,
)
from .html_packager import ProcessPresentationPackager
from .multimodal_input import (
    InputImageRecord,
    MultimodalInputBundle,
    load_multimodal_inputs,
)
from .pipeline_engine import (
    PipelineEngine,
    PipelineState,
    Stage,
    StageRoutingDecision,
    execute_structured_turn,
    resolve_rollback_stage,
)

__all__ = [
    "AskQuestionHook",
    "ConsoleAskQuestionHook",
    "GateDecision",
    "InputImageRecord",
    "MultimodalInputBundle",
    "PipelineEngine",
    "PipelineState",
    "ProcessPresentationPackager",
    "Stage",
    "StageRoutingDecision",
    "execute_structured_turn",
    "resolve_rollback_stage",
    "DEFAULT_GENERIC_MODEL",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_LOCATION",
    "DEFAULT_VIDEO_MODEL",
    "generate_image_tool",
    "generate_video_tool",
    "get_agent_platform_client",
    "load_multimodal_inputs",
    "prompt_approval_gate",
    "prompt_ask_question",
    "upload_to_gcs_tool",
]

