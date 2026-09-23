"""Architectural Virtual Staging & Spatial Showcase Multi-Agent Pipeline.

An example multi-agent, multimodal system built with the `multimodal-agent-builder`
skill toolkit and the Google Antigravity SDK (`google-antigravity`).

Process Topology:
1. `spatial_concept_architect`: Analyzes the user's architectural brief and optional
   room/site reference images (`MultimodalInputBundle`), produces a structured
   `SpatialConceptSpec` with context-derived staging directions, and collaborates
   with the user via `prompt_ask_question` / `BuiltinTools.ASK_QUESTION` (including
   custom write-in support) to lock in the spatial direction.
2. `staging_render_artist`: Synthesizes a factual image generation specification
   (`StagingRenderSpec`) strictly from the brief and confirmed direction, renders
   the staged architectural visual via `generate_image_tool`, and optionally uploads
   to Google Cloud Storage (`upload_to_gcs_tool`).
3. `cinematic_video_director`: Designs a temporal walkthrough motion specification
   (`CinematicMotionSpec`) grounded in the staged render and materializes a 10-second
   video asset via `generate_video_tool` using the rendered image as reference.
4. `showcase_packager`: Synthesizes presentation copy (`ShowcasePresentationSpec`)
   and packages all generated media into a bespoke, mobile-responsive, scroll-animated
   HTML5 presentation via `ProcessPresentationPackager`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pydantic
from google.antigravity import Agent, types

# Ensure `core` package from `skills/multimodal-agent-builder` is importable
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from core import (
    DEFAULT_LOCATION,
    PipelineEngine,
    PipelineState,
    ProcessPresentationPackager,
    Stage,
    add_logging_cli_args,
    configure_logging_from_args,
    execute_structured_turn,
    generate_image_tool,
    generate_video_tool,
    load_multimodal_inputs,
    prompt_ask_question,
    upload_to_gcs_tool,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Native Pydantic Schemas (`response_schema`)
# ============================================================================


class SpatialDirectionOption(pydantic.BaseModel):
    """A context-derived spatial staging option presented for human selection."""

    option_title: str = pydantic.Field(
        description="Concise title for this spatial staging direction derived from the brief."
    )
    rationale: str = pydantic.Field(
        description="How this direction fulfills the architectural context and user brief."
    )
    key_elements: List[str] = pydantic.Field(
        description="Concrete spatial, furniture, and material elements defined by this option."
    )


class SpatialConceptSpec(pydantic.BaseModel):
    """Structured output produced by `spatial_concept_architect`."""

    project_title: str = pydantic.Field(
        description="Name of the architectural staging concept."
    )
    architectural_summary: str = pydantic.Field(
        description="Analysis of the input space, geometry, and user requirements."
    )
    spatial_zones: List[str] = pydantic.Field(
        description="Functional zones and circulation layout derived from the brief."
    )
    material_and_furnishing_notes: List[str] = pydantic.Field(
        description="Specific materials, fixtures, and furnishings grounded in the brief."
    )
    proposed_directions: List[SpatialDirectionOption] = pydantic.Field(
        min_length=3,
        max_length=4,
        description="3 to 4 distinct, context-derived staging directions for the human reviewer to choose from.",
    )


class StagingRenderSpec(pydantic.BaseModel):
    """Structured output produced by `staging_render_artist`."""

    image_generation_prompt: str = pydantic.Field(
        description=(
            "Complete image synthesis prompt constructed strictly from the user's brief, "
            "input space geometry, and human-selected direction without unrequested buzzwords."
        )
    )
    focal_composition_notes: str = pydantic.Field(
        description="Camera framing and spatial alignment notes."
    )


class CinematicMotionSpec(pydantic.BaseModel):
    """Structured output produced by `cinematic_video_director`."""

    video_generation_prompt: str = pydantic.Field(
        description=(
            "Single continuous, unedited one-shot camera movement description (e.g. a slow, steady "
            "linear forward dolly push-in) starting from the exact staged render frame. Must NOT "
            "contain timestamped segments, cuts, cross-dissolves, or multi-room transitions."
        )
    )
    aspect_ratio: str = pydantic.Field(
        default="16:9",
        description="Target aspect ratio matching the staged render ('16:9' or '9:16').",
    )
    camera_movement_summary: str = pydantic.Field(
        description="Summary of the single continuous camera trajectory within the locked room geometry."
    )


class ShowcasePresentationSpec(pydantic.BaseModel):
    """Structured output produced by `showcase_packager`."""

    title: str = pydantic.Field(
        description="Presentation title for the above-the-fold hero section."
    )
    hook: str = pydantic.Field(
        description="Arresting single-sentence hook line summarizing the staged transformation."
    )
    narrative: str = pydantic.Field(
        description="Architectural design philosophy and spatial narrative."
    )
    headline: str = pydantic.Field(
        description="Below-the-fold section headline introducing the staging details."
    )
    body_text: str = pydantic.Field(
        description="Detailed walkthrough copy covering spatial layout, materials, and design choices."
    )
    cta_text: str = pydantic.Field(
        description="Actionable call-to-action label for client review or scheduling."
    )


# ============================================================================
# 2. Specialized Subagent Configurations (`types.SubagentConfig`)
# ============================================================================


SPATIAL_CONCEPT_ARCHITECT_INSTRUCTIONS = """You are the Spatial Concept Architect (`spatial_concept_architect`).
Your role is to analyze the user's architectural brief and any attached site or room photographs, decompose the spatial geometry and functional needs, and formulate a structured `SpatialConceptSpec`.

Decision & Generation Rules:
1. Derive all observations, spatial zones, and material notes strictly from the user's brief and provided reference images.
2. Generate 3 to 4 distinct `proposed_directions` tailored specifically to the space and user brief so the human reviewer can choose a direction or provide a custom write-in response.
3. Never invent unrelated environmental tropes or use stock marketing clichés. If critical information is ambiguous, you may also use `ask_question` to clarify with the user.
"""

STAGING_RENDER_ARTIST_INSTRUCTIONS = """You are the Staging Render Artist (`staging_render_artist`).
Your role is to translate the confirmed `SpatialConceptSpec` and the human reviewer's selected direction into a precise `StagingRenderSpec` for image synthesis.

Decision & Generation Rules:
1. Construct `image_generation_prompt` exclusively from:
   - The user's original brief and reference image observations.
   - The spatial zones and materials in `SpatialConceptSpec`.
   - The exact direction selected (or custom written) by the human reviewer.
2. Do NOT inject unrequested aesthetic buzzwords, camera clichés, or fabricated backgrounds that were not specified by the brief or selected direction.
"""

CINEMATIC_VIDEO_DIRECTOR_INSTRUCTIONS = """You are the Cinematic Video Director (`cinematic_video_director`).
Your role is to design a single continuous, unedited 10-second one-shot camera movement (`CinematicMotionSpec`) anchored directly to the staged architectural render.

Decision & Generation Rules:
1. ONE-SHOT CONTINUITY ONLY: Write `video_generation_prompt` as a single unified paragraph describing one slow, steady, continuous camera motion (such as a gentle linear dolly push-in or subtle lateral slider move) starting from the exact frame of the staged render.
2. STRICT BAN ON MULTI-BEAT TIMESTAMPS & CUTS: Never use timestamp markers (like `[0:00 - 0:03s]`, `[0:03 - 0:06s]`), never describe scene cuts, cross-dissolves, fades, or multi-axis whip pans that look away from the main composition.
3. STRICT SPATIAL PERMANENCE: Every piece of furniture, material texture, ceiling truss, window mullion, and fireplace element visible in the staged render must remain locked in its exact position throughout the entire 10-second shot.
"""

SHOWCASE_PACKAGER_INSTRUCTIONS = """You are the Architectural Showcase Packager (`showcase_packager`).
Your role is to synthesize the final client-facing presentation copy (`ShowcasePresentationSpec`) uniting the spatial concept, the staged visual render, and the 10-second walkthrough video.

Decision & Generation Rules:
1. Adhere to the Impression-First hierarchy: an arresting title and hook for above-the-fold impact, followed by detailed architectural storytelling and material specifications below the fold.
2. Keep all copy strictly factual to the user's brief, selected direction, and produced assets.
"""


def build_subagent_configs() -> Dict[str, types.SubagentConfig]:
    """Creates the process-specific subagent definitions for the 4 pipeline stages."""
    return {
        "concept": types.SubagentConfig(
            name="spatial_concept_architect",
            description="Analyzes architectural briefs and site photos to produce spatial concepts and context-derived staging options.",
            system_instructions=SPATIAL_CONCEPT_ARCHITECT_INSTRUCTIONS,
            tools=[types.BuiltinTools.ASK_QUESTION],
            capabilities=types.SubagentCapabilities(
                agent_behavior=types.AgentBehavior.INTERACTIVE,
            ),
        ),
        "visual_production": types.SubagentConfig(
            name="staging_render_artist",
            description="Synthesizes factual staging prompts from confirmed spatial specs and generates staged architectural renders.",
            system_instructions=STAGING_RENDER_ARTIST_INSTRUCTIONS,
            tools=[generate_image_tool, upload_to_gcs_tool],
            capabilities=types.SubagentCapabilities(
                agent_behavior=types.AgentBehavior.AUTONOMOUS,
            ),
        ),
        "video_production": types.SubagentConfig(
            name="cinematic_video_director",
            description="Designs camera movement choreography and generates 10-second architectural walkthrough videos from staged renders.",
            system_instructions=CINEMATIC_VIDEO_DIRECTOR_INSTRUCTIONS,
            tools=[generate_video_tool, upload_to_gcs_tool],
            capabilities=types.SubagentCapabilities(
                agent_behavior=types.AgentBehavior.AUTONOMOUS,
            ),
        ),
        "presentation_packaging": types.SubagentConfig(
            name="showcase_packager",
            description="Packages the staged visual, walkthrough video, and architectural narrative into a responsive HTML5 showcase.",
            system_instructions=SHOWCASE_PACKAGER_INSTRUCTIONS,
            tools=[upload_to_gcs_tool],
            capabilities=types.SubagentCapabilities(
                agent_behavior=types.AgentBehavior.AUTONOMOUS,
            ),
        ),
    }


# ============================================================================
# 3. Stage Execution Functions (`StageRunFn`)
# ============================================================================


def make_stage_runners(
    output_dir: Path,
    bucket_name: Optional[str],
    gcs_prefix: str,
    aspect_ratio: str,
    autonomous: bool,
    project_id: Optional[str],
):
    """Creates closures for each stage's `run_fn` wired to runtime configuration."""

    async def run_concept_step(
        agent: Agent, state: PipelineState, extra: Optional[str]
    ) -> Dict[str, Any]:
        """Stage 1: Multimodal intake, structured spatial concept, and human direction selection."""
        prompt_text = (
            f"Analyze the following architectural virtual staging brief and any attached reference images.\n\n"
            f"USER BRIEF:\n{state.input_bundle.prompt}\n\n"
            f"Produce a complete SpatialConceptSpec including 3 to 4 distinct, context-derived "
            f"staging directions tailored to this specific brief."
        )
        if extra:
            prompt_text += (
                f"\n\nHUMAN GATE REVISION INSTRUCTIONS (MUST BE APPLIED IN THIS ITERATION):\n{extra}"
            )

        turn_payload = state.input_bundle.build_chat_turn_payload(prompt_text)

        concept_spec, _ = await execute_structured_turn(
            prompt=turn_payload,
            response_schema=SpatialConceptSpec,
            system_instructions=SPATIAL_CONCEPT_ARCHITECT_INSTRUCTIONS,
            tools=[types.BuiltinTools.ASK_QUESTION],
            project_id=project_id,
            autonomous=autonomous,
        )

        # Present the context-derived options to the human reviewer (always includes custom write-in)
        option_strings = [
            f"{opt.option_title}: {opt.rationale} (Elements: {', '.join(opt.key_elements)})"
            for opt in concept_spec.proposed_directions
        ]
        selected_direction = prompt_ask_question(
            question=(
                f"Select the spatial staging direction for '{concept_spec.project_title}' "
                f"(or choose [Custom] to specify your own direction):"
            ),
            options=option_strings,
            default_index=0,
            autonomous=autonomous,
            allow_custom=True,
        )

        print(f"\n[Stage 1 Summary] Project: {concept_spec.project_title}")
        print(f"[Stage 1 Summary] Selected Direction: {selected_direction}")

        state.data["concept_spec"] = concept_spec.model_dump()
        state.data["selected_direction"] = selected_direction

        return {
            "concept_spec": concept_spec.model_dump(),
            "selected_direction": selected_direction,
        }

    async def run_render_step(
        agent: Agent, state: PipelineState, extra: Optional[str]
    ) -> Dict[str, Any]:
        """Stage 2: Dynamic prompt synthesis and image generation on Agent Platform."""
        concept_data = state.data["concept_spec"]
        selected_direction = state.data["selected_direction"]

        render_instruction = (
            f"Synthesize the StagingRenderSpec for the following confirmed spatial staging project.\n\n"
            f"ORIGINAL USER BRIEF:\n{state.input_bundle.prompt}\n\n"
            f"SPATIAL CONCEPT SPEC:\n{json.dumps(concept_data, indent=2)}\n\n"
            f"HUMAN-CONFIRMED DIRECTION:\n{selected_direction}\n\n"
            f"Ensure `image_generation_prompt` reflects only the user's brief, reference geometry, "
            f"and confirmed direction."
        )
        if extra:
            render_instruction += (
                f"\n\nHUMAN GATE REVISION INSTRUCTIONS (MUST BE APPLIED IN THIS ITERATION):\n{extra}"
            )

        render_spec, _ = await execute_structured_turn(
            prompt=render_instruction,
            response_schema=StagingRenderSpec,
            system_instructions=STAGING_RENDER_ARTIST_INSTRUCTIONS,
            project_id=project_id,
            autonomous=autonomous,
        )

        image_out_path = str((output_dir / "staged_render.png").resolve())
        reference_imgs = (
            [img.path for img in state.input_bundle.images]
            if state.input_bundle.has_images
            else None
        )

        generated_img_path = generate_image_tool(
            prompt=render_spec.image_generation_prompt,
            output_path=image_out_path,
            reference_image_path=reference_imgs,
            project=project_id,
            location=DEFAULT_LOCATION,
        )
        state.set_artifact("staged_render", generated_img_path)
        print(f"\n[Stage 2 Artifact] Staged render saved to: {generated_img_path}")

        if bucket_name:
            img_mtls = upload_to_gcs_tool(
                local_path=generated_img_path,
                bucket_name=bucket_name,
                destination_path=f"{gcs_prefix}/staged_render.png",
                project=project_id,
            )
            state.cloud_urls["staged_render"] = img_mtls
            state.set_artifact("staged_render_mtls", img_mtls)

        state.data["render_spec"] = render_spec.model_dump()
        return {
            "render_spec": render_spec.model_dump(),
            "staged_render_path": generated_img_path,
        }

    async def run_video_step(
        agent: Agent, state: PipelineState, extra: Optional[str]
    ) -> Dict[str, Any]:
        """Stage 3: Temporal walkthrough choreography and 10-second video generation."""
        concept_data = state.data["concept_spec"]
        selected_direction = state.data["selected_direction"]
        render_spec_data = state.data["render_spec"]
        staged_render_path = state.get_artifact("staged_render")

        video_instruction = (
            f"Inspect the attached staged architectural render and create a single-shot CinematicMotionSpec "
            f"for a 10-second continuous one-shot architectural video.\n\n"
            f"ORIGINAL USER BRIEF:\n{state.input_bundle.prompt}\n\n"
            f"CONFIRMED DIRECTION:\n{selected_direction}\n\n"
            f"STAGED RENDER DETAILS:\n{json.dumps(render_spec_data, indent=2)}\n\n"
            f"Target aspect ratio: {aspect_ratio}. Write ONE single continuous slow camera dolly/slider motion "
            f"with zero timestamp markers, zero cuts, zero cross-dissolves, and 100% locked room & furniture geometry."
        )
        if extra:
            video_instruction += (
                f"\n\nHUMAN GATE REVISION INSTRUCTIONS (MUST BE APPLIED IN THIS ITERATION):\n{extra}"
            )

        video_turn_payload: List[Any] = [video_instruction]
        if staged_render_path and Path(staged_render_path).exists():
            video_turn_payload.append(
                types.Image.from_file(
                    staged_render_path,
                    description="Staged Architectural Render (Exact Frame 0 for One-Shot Video)",
                )
            )

        motion_spec, _ = await execute_structured_turn(
            prompt=video_turn_payload,
            response_schema=CinematicMotionSpec,
            system_instructions=CINEMATIC_VIDEO_DIRECTOR_INSTRUCTIONS,
            project_id=project_id,
            autonomous=autonomous,
        )

        video_out_path = str((output_dir / "walkthrough_video.mp4").resolve())
        generated_video_path = generate_video_tool(
            prompt=motion_spec.video_generation_prompt,
            output_path=video_out_path,
            image_path=staged_render_path,
            aspect_ratio=aspect_ratio,
            single_shot_consistency=True,
            match_reference_aspect_ratio=True,
            project=project_id,
            location=DEFAULT_LOCATION,
        )
        state.set_artifact("walkthrough_video", generated_video_path)
        print(f"\n[Stage 3 Artifact] Walkthrough video saved to: {generated_video_path}")

        if bucket_name:
            vid_mtls = upload_to_gcs_tool(
                local_path=generated_video_path,
                bucket_name=bucket_name,
                destination_path=f"{gcs_prefix}/walkthrough_video.mp4",
                project=project_id,
            )
            state.cloud_urls["walkthrough_video"] = vid_mtls
            state.set_artifact("walkthrough_video_mtls", vid_mtls)

        state.data["motion_spec"] = motion_spec.model_dump()
        return {
            "motion_spec": motion_spec.model_dump(),
            "walkthrough_video_path": generated_video_path,
        }

    async def run_package_step(
        agent: Agent, state: PipelineState, extra: Optional[str]
    ) -> Dict[str, Any]:
        """Stage 4: Bespoke HTML5 presentation synthesis and metadata export."""
        concept_data = state.data["concept_spec"]
        selected_direction = state.data["selected_direction"]
        render_spec_data = state.data["render_spec"]
        motion_spec_data = state.data["motion_spec"]

        package_instruction = (
            f"Prepare the ShowcasePresentationSpec for the completed architectural virtual staging showcase.\n\n"
            f"ORIGINAL USER BRIEF:\n{state.input_bundle.prompt}\n\n"
            f"CONFIRMED DIRECTION:\n{selected_direction}\n\n"
            f"SPATIAL CONCEPT:\n{json.dumps(concept_data, indent=2)}\n\n"
            f"RENDER SPEC:\n{json.dumps(render_spec_data, indent=2)}\n\n"
            f"VIDEO MOTION SPEC:\n{json.dumps(motion_spec_data, indent=2)}"
        )
        if extra:
            package_instruction += (
                f"\n\nHUMAN GATE REVISION INSTRUCTIONS (MUST BE APPLIED IN THIS ITERATION):\n{extra}"
            )

        presentation_spec, _ = await execute_structured_turn(
            prompt=package_instruction,
            response_schema=ShowcasePresentationSpec,
            system_instructions=SHOWCASE_PACKAGER_INSTRUCTIONS,
            project_id=project_id,
            autonomous=autonomous,
        )

        local_img = state.get_artifact("staged_render") or ""
        local_vid = state.get_artifact("walkthrough_video") or ""
        img_mtls = state.cloud_urls.get("staged_render", local_img)
        vid_mtls = state.cloud_urls.get("walkthrough_video", local_vid)

        # Save pipeline metadata JSON first so its path/URL can be linked
        metadata_path = (output_dir / "pipeline_metadata.json").resolve()
        metadata_payload = {
            "prompt": state.input_bundle.prompt,
            "input_images": [img.path for img in state.input_bundle.images],
            "selected_direction": selected_direction,
            "concept_spec": concept_data,
            "render_spec": render_spec_data,
            "motion_spec": motion_spec_data,
            "presentation_spec": presentation_spec.model_dump(),
            "revision_history": state.revision_history,
            "artifacts": state.artifacts,
            "cloud_urls": state.cloud_urls,
        }
        metadata_path.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")
        state.set_artifact("metadata_json", str(metadata_path))

        meta_mtls = str(metadata_path)
        if bucket_name:
            meta_mtls = upload_to_gcs_tool(
                local_path=str(metadata_path),
                bucket_name=bucket_name,
                destination_path=f"{gcs_prefix}/pipeline_metadata.json",
                project=project_id,
            )
            state.cloud_urls["metadata_json"] = meta_mtls
            state.set_artifact("metadata_json_mtls", meta_mtls)

        packager = ProcessPresentationPackager()
        html_content = packager.render_presentation_html(
            title=presentation_spec.title,
            hook=presentation_spec.hook,
            narrative=presentation_spec.narrative,
            headline=presentation_spec.headline,
            body_text=presentation_spec.body_text,
            cta_text=presentation_spec.cta_text,
            image_src=img_mtls,
            video_src=vid_mtls,
            image_mtls_url=img_mtls,
            video_mtls_url=vid_mtls,
            metadata_mtls_url=meta_mtls,
            extra_context=(
                f"Selected Staging Direction: {selected_direction}\n"
                f"Spatial Zones: {', '.join(concept_data.get('spatial_zones', []))}\n"
                f"Camera Walkthrough: {motion_spec_data.get('camera_movement_summary', '')}"
            ),
            local_image_path=local_img,
            local_video_path=local_vid,
        )

        html_path = (output_dir / "showcase.html").resolve()
        html_path.write_text(html_content, encoding="utf-8")
        state.set_artifact("showcase_html", str(html_path))
        print(f"\n[Stage 4 Artifact] HTML5 Showcase saved to: {html_path}")

        if bucket_name:
            html_mtls = upload_to_gcs_tool(
                local_path=str(html_path),
                bucket_name=bucket_name,
                destination_path=f"{gcs_prefix}/showcase.html",
                project=project_id,
            )
            state.cloud_urls["showcase_html"] = html_mtls
            state.set_artifact("showcase_html_mtls", html_mtls)

        state.data["presentation_spec"] = presentation_spec.model_dump()
        return {
            "presentation_spec": presentation_spec.model_dump(),
            "showcase_html_path": str(html_path),
        }

    return {
        "concept": run_concept_step,
        "visual_production": run_render_step,
        "video_production": run_video_step,
        "presentation_packaging": run_package_step,
    }


# ============================================================================
# 4. Pipeline Wiring & CLI Entrypoint
# ============================================================================


def build_pipeline(
    output_dir: Path,
    bucket_name: Optional[str] = None,
    gcs_prefix: str = "architectural-staging",
    aspect_ratio: str = "16:9",
    autonomous: bool = False,
    project_id: Optional[str] = None,
) -> PipelineEngine:
    """Instantiates the 4-stage `PipelineEngine` for Architectural Virtual Staging."""
    output_dir.mkdir(parents=True, exist_ok=True)
    subagents = build_subagent_configs()
    runners = make_stage_runners(
        output_dir=output_dir,
        bucket_name=bucket_name,
        gcs_prefix=gcs_prefix.strip("/"),
        aspect_ratio=aspect_ratio,
        autonomous=autonomous,
        project_id=project_id,
    )

    stages = [
        Stage(
            name="concept",
            description="Spatial analysis, concept specification, and interactive direction selection.",
            subagent_config=subagents["concept"],
            response_schema=SpatialConceptSpec,
            run_fn=runners["concept"],
            requires_approval=True,
            approval_question=(
                "Do you approve this Spatial Concept & Selected Staging Direction to proceed "
                "to Stage 2 (3D Staged Render)? (Only Option [1] Approve advances the workflow; "
                "Deny or Custom feedback will re-run Stage 1 with your revisions.)"
            ),
        ),
        Stage(
            name="visual_production",
            description="Dynamic staging prompt synthesis and high-resolution image generation.",
            subagent_config=subagents["visual_production"],
            response_schema=StagingRenderSpec,
            run_fn=runners["visual_production"],
            requires_approval=True,
            approval_question=(
                "Inspect the generated `staged_render.png`. Do you approve this Staged Render "
                "to proceed to Stage 3 (10-Second Walkthrough Video)? (Only Option [1] Approve "
                "advances the gate; any other response triggers the AI router to roll back to "
                "either `concept` or `visual_production` based on your feedback.)"
            ),
        ),
        Stage(
            name="video_production",
            description="Temporal walkthrough choreography and 10-second video generation.",
            subagent_config=subagents["video_production"],
            response_schema=CinematicMotionSpec,
            run_fn=runners["video_production"],
            requires_approval=True,
            approval_question=(
                "Inspect the generated `walkthrough_video.mp4`. Do you approve this Walkthrough Video "
                "to proceed to Stage 4 (HTML5 Showcase Packaging)? (Only Option [1] Approve "
                "advances the gate; any other response triggers the AI router to roll back to "
                "`concept`, `visual_production`, or `video_production` based on your feedback.)"
            ),
        ),
        Stage(
            name="presentation_packaging",
            description="Bespoke mobile-responsive HTML5 showcase packaging with scroll animation.",
            subagent_config=subagents["presentation_packaging"],
            response_schema=ShowcasePresentationSpec,
            run_fn=runners["presentation_packaging"],
        ),
    ]

    return PipelineEngine(
        stages=stages,
        project_id=project_id,
        checkpoint_path=output_dir / "pipeline_checkpoint.json",
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses CLI arguments for the Architectural Virtual Staging agent."""
    parser = argparse.ArgumentParser(
        description="Architectural Virtual Staging & Spatial Showcase Multi-Agent Pipeline"
    )
    parser.add_argument(
        "--brief",
        type=str,
        required=True,
        help="Architectural staging brief describing the space, purpose, and desired transformation.",
    )
    parser.add_argument(
        "--image",
        action="append",
        dest="images",
        default=[],
        help="Optional path to an input room photo, floorplan, or material reference (repeatable).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/architectural_staging"),
        help="Directory where generated images, videos, metadata, and HTML showcase are saved.",
    )
    parser.add_argument(
        "--aspect-ratio",
        type=str,
        choices=["16:9", "9:16", "auto"],
        default="16:9",
        help="Target aspect ratio for the 10-second architectural walkthrough video (defaults to 16:9 to match staged render).",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=None,
        help="Optional Google Cloud Storage bucket name for uploading assets and generating mTLS URLs.",
    )
    parser.add_argument(
        "--gcs-prefix",
        type=str,
        default="architectural-staging",
        help="Object path prefix inside the GCS bucket when --bucket is specified.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Optional Google Cloud project ID override (defaults to ADC / GOOGLE_CLOUD_PROJECT).",
    )
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Run in headless autonomous mode, automatically selecting default options and approving gates without blocking.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from an existing pipeline_checkpoint.json in --output-dir if present (default: start fresh).",
    )
    add_logging_cli_args(parser)
    return parser.parse_args(argv)


async def async_main(argv: Optional[List[str]] = None) -> PipelineState:
    """Asynchronous entrypoint loading multimodal inputs and executing the pipeline."""
    args = parse_args(argv)
    configure_logging_from_args(args)

    input_bundle = load_multimodal_inputs(
        prompt=args.brief,
        image_paths=args.images,
    )

    engine = build_pipeline(
        output_dir=args.output_dir,
        bucket_name=args.bucket,
        gcs_prefix=args.gcs_prefix,
        aspect_ratio=args.aspect_ratio,
        autonomous=args.autonomous,
        project_id=args.project,
    )

    return await engine.execute(
        inputs=input_bundle,
        autonomous=args.autonomous,
        resume=args.resume,
    )


def main() -> None:
    """Synchronous CLI wrapper."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
