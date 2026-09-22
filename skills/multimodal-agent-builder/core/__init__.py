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
    prompt_ask_question,
)
from .html_packager import ProcessPresentationPackager
from .multimodal_input import (
    InputImageRecord,
    MultimodalInputBundle,
    load_multimodal_inputs,
)
from .pipeline_engine import PipelineEngine, PipelineState, Stage, execute_structured_turn

__all__ = [
    "AskQuestionHook",
    "ConsoleAskQuestionHook",
    "InputImageRecord",
    "MultimodalInputBundle",
    "PipelineEngine",
    "PipelineState",
    "ProcessPresentationPackager",
    "Stage",
    "execute_structured_turn",
    "DEFAULT_GENERIC_MODEL",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_LOCATION",
    "DEFAULT_VIDEO_MODEL",
    "generate_image_tool",
    "generate_video_tool",
    "get_agent_platform_client",
    "load_multimodal_inputs",
    "prompt_ask_question",
    "upload_to_gcs_tool",
]
