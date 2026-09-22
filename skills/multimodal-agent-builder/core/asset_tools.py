"""Asset Generation Tools for Multimodal Multi-Agent Systems.

Equips Antigravity SDK agents with production-ready tools for:
- Image generation on Agent Platform (gemini-3.1-flash-lite-image)
- 9:16 or 16:9 Video generation on Agent Platform (gemini-omni-1.1-flash-preview)
- Cloud storage upload with authenticated mTLS browser URLs
"""

from __future__ import annotations

import base64
from functools import lru_cache
import logging
import os
import time
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Sequence, Union

from google import genai
from google.cloud import storage

logger = logging.getLogger(__name__)

DEFAULT_GENERIC_MODEL = "gemini-3.8-flash"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"
DEFAULT_VIDEO_MODEL = "gemini-omni-1.1-flash-preview"
DEFAULT_LOCATION = "global"

@lru_cache(maxsize=1)
def _get_current_project():
    try:
        from google.auth import default
        _, auth_project = default()
    except Exception:
        raise RuntimeError("Cannot obtain gcloud application default credentials. Run `gcloud auth application-default login` and try again.")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
    if not project:
        try:
            project = subprocess.check_output(["gcloud", "config", "get-value", "project", "-q"]).decode("utf-8").strip()
        except subprocess.CalledProcessError:
            project = auth_project
    if not project:
        raise ValueError("Set GOOGLE_CLOUD_PROJECT or configure gcloud config project.")
    return project


def get_agent_platform_client(
    project: Optional[str] = None,
    location: str = DEFAULT_LOCATION,
    timeout: Optional[int] = None,
) -> genai.Client:
    """Instantiates a Google GenAI Client configured for Agent Platform via ADC."""
    proj = project or _get_current_project()
    kwargs: Dict[str, Any] = {
        "vertexai": True,
        "project": proj,
        "location": location,
    }
    if timeout:
        kwargs["http_options"] = {"timeout": timeout}
    return genai.Client(**kwargs)


def generate_image_tool(
    prompt: str,
    output_path: str,
    reference_image_path: Optional[Union[str, Sequence[str]]] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """Generates an image using Agent Platform (gemini-3.1-flash-lite-image).

    Args:
        prompt: Detailed generation prompt.
        output_path: Local filesystem destination path (.png).
        reference_image_path: Optional path or sequence of paths to input reference images for guided generation.
        project: Optional GCP Project ID.
        location: Cloud location/region (strictly 'global').

    Returns:
        The local file path of the generated image.
    """
    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    loc = location or DEFAULT_LOCATION

    ref_paths: list[str] = []
    if reference_image_path:
        if isinstance(reference_image_path, (str, Path)):
            ref_paths = [str(reference_image_path)]
        else:
            ref_paths = [str(p) for p in reference_image_path if p]

    contents: Any = prompt
    inline_parts: list[Dict[str, Any]] = []
    for rp in ref_paths:
        if Path(rp).exists():
            ref_p = Path(rp).resolve()
            raw = ref_p.read_bytes()
            mime = "image/png"
            if ref_p.suffix.lower() in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ref_p.suffix.lower() == ".webp":
                mime = "image/webp"
            inline_parts.append({"inline_data": {"mime_type": mime, "data": raw}})

    if inline_parts:
        contents = [*inline_parts, prompt]

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            client = get_agent_platform_client(project=project, location=loc)
            resp = client.models.generate_content(
                model=DEFAULT_IMAGE_MODEL,
                contents=contents,
            )
            if hasattr(resp, "candidates") and resp.candidates:
                for part in resp.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        dest.write_bytes(part.inline_data.data)
                        logger.info(
                            f"Generated image saved to {dest} ({dest.stat().st_size} bytes)"
                        )
                        return str(dest)
        except Exception as e:
            last_err = e
            logger.warning(
                f"Image generation attempt {attempt}/3 encountered error: {e}"
            )
            if attempt < 3:
                time.sleep(2.0 * attempt)

    if last_err is not None:
        raise RuntimeError(
            f"Agent Platform image generation ({DEFAULT_IMAGE_MODEL}) failed after 3 attempts: {last_err}"
        ) from last_err

    raise RuntimeError(f"Agent Platform image model ({DEFAULT_IMAGE_MODEL}) returned no image data.")


def _detect_image_aspect_ratio(raw_bytes: bytes, fallback: str = "16:9") -> str:
    """Detects whether an image is landscape ('16:9') or portrait ('9:16') from PNG/JPEG headers."""
    try:
        # PNG header: bytes 16..24 contain big-endian width (4B) and height (4B)
        if len(raw_bytes) >= 24 and raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(raw_bytes[16:20], "big")
            height = int.from_bytes(raw_bytes[20:24], "big")
            if width > 0 and height > 0:
                return "16:9" if width >= height else "9:16"
        # JPEG SOF markers
        if len(raw_bytes) > 4 and raw_bytes[:2] == b"\xff\xd8":
            idx = 2
            while idx + 9 < len(raw_bytes):
                if raw_bytes[idx] != 0xFF:
                    idx += 1
                    continue
                marker = raw_bytes[idx + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3) and idx + 9 < len(raw_bytes):
                    height = int.from_bytes(raw_bytes[idx + 5 : idx + 7], "big")
                    width = int.from_bytes(raw_bytes[idx + 7 : idx + 9], "big")
                    if width > 0 and height > 0:
                        return "16:9" if width >= height else "9:16"
                    break
                seg_len = int.from_bytes(raw_bytes[idx + 2 : idx + 4], "big")
                if seg_len < 2:
                    break
                idx += 2 + seg_len
    except Exception:
        pass
    return fallback


def generate_video_tool(
    prompt: str,
    output_path: str,
    image_path: Optional[str] = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    single_shot_consistency: bool = True,
    match_reference_aspect_ratio: bool = True,
    project: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """Generates a 10-second cinematic video using gemini-omni-1.1-flash-preview on Agent Platform.

    Args:
        prompt: Continuous single-shot camera motion description.
        output_path: Local filesystem destination path (.mp4).
        image_path: Optional path to an image guiding video generation as the opening frame.
        aspect_ratio: '16:9' (horizontal), '9:16' (vertical), or 'auto'.
        resolution: Output resolution (e.g. '1080p').
        single_shot_consistency: If True, enforces an unbroken one-shot take anchored to the reference image without cuts or cross-dissolves.
        match_reference_aspect_ratio: If True and image_path is provided, matches the video aspect ratio to the reference image orientation to prevent cropping/hallucination.
        project: Optional GCP Project ID.
        location: Cloud location/region (strictly 'global').

    Returns:
        The local file path of the generated MP4 video.
    """
    import re as _re

    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    loc = location or DEFAULT_LOCATION
    client = get_agent_platform_client(project=project, location=loc, timeout=360)

    resolved_aspect = aspect_ratio
    cleaned_prompt = prompt.strip()
    if single_shot_consistency:
        # Remove timestamped multi-beat markers (e.g. "[0:00 - 0:03s]") that trigger multi-clip stitching
        cleaned_prompt = _re.sub(
            r"\[\s*\d+:\d+(?:\.\d+)?\s*s?\s*-\s*\d+:\d+(?:\.\d+)?\s*s?\s*\]\s*",
            "",
            cleaned_prompt,
        )
        cleaned_prompt = " ".join(cleaned_prompt.split())

    input_payload: Any
    if image_path and Path(image_path).exists():
        img_p = Path(image_path).resolve()
        raw_bytes = img_p.read_bytes()
        if match_reference_aspect_ratio or resolved_aspect == "auto":
            detected_ar = _detect_image_aspect_ratio(raw_bytes, fallback="16:9")
            if resolved_aspect != detected_ar:
                logger.info(
                    f"Aligning video aspect_ratio to '{detected_ar}' to match reference image {img_p.name}"
                )
            resolved_aspect = detected_ar

        b64_image = base64.b64encode(raw_bytes).decode("utf-8")
        mime = "image/png"
        if img_p.suffix.lower() in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif img_p.suffix.lower() == ".webp":
            mime = "image/webp"

        if single_shot_consistency:
            anchored_prompt = (
                "SINGLE UNEDITED ONE-SHOT TAKE (NO CUTS, NO DISSOLVES, NO FADES, NO SCENE TRANSITIONS): "
                "Start directly from the exact provided image as Frame 0 and preserve 100% of the room geometry, "
                "architecture, windows, fireplace, and exact furniture arrangement without morphing or replacing any object. "
                f"Camera movement: {cleaned_prompt}"
            )
        else:
            anchored_prompt = cleaned_prompt

        input_payload = [
            {"type": "image", "data": b64_image, "mime_type": mime},
            {"type": "text", "text": anchored_prompt},
        ]
    else:
        if resolved_aspect == "auto":
            resolved_aspect = "16:9"
        input_payload = cleaned_prompt

    response_format = {
        "type": "video",
        "aspect_ratio": resolved_aspect,
        "resolution": resolution,
    }

    try:
        interaction = client.interactions.create(
            model=DEFAULT_VIDEO_MODEL,
            input=input_payload,
            response_format=response_format,
            background=True,
            timeout=360.0,
        )

        # Poll interaction until completion
        if hasattr(interaction, "id") and interaction.id:
            interaction_id = interaction.id
            for _ in range(60):
                if getattr(interaction, "status", None) == "completed":
                    break
                if getattr(interaction, "status", None) in ("failed", "cancelled"):
                    raise RuntimeError(f"Video generation {interaction.status}: {getattr(interaction, 'errors', None)}")
                time.sleep(5)
                interaction = client.interactions.get(id=interaction_id, timeout=60.0)

        # Handle direct output_video field
        if hasattr(interaction, "output_video") and interaction.output_video:
            out_vid = interaction.output_video
            if hasattr(out_vid, "data") and out_vid.data:
                video_bytes = base64.b64decode(out_vid.data) if isinstance(out_vid.data, str) else out_vid.data
                dest.write_bytes(video_bytes)
                logger.info(f"Generated video saved to {dest} ({dest.stat().st_size} bytes)")
                return str(dest)

            if hasattr(out_vid, "uri") and out_vid.uri:
                file_id = out_vid.uri.split("/")[-1]
                for _ in range(60):
                    time.sleep(5)
                    f_info = client.files.get(name=f"files/{file_id}")
                    if getattr(f_info, "state", None) and f_info.state.name == "ACTIVE":
                        break
                    if getattr(f_info, "state", None) and f_info.state.name == "FAILED":
                        raise RuntimeError("Agent Platform video generation failed during file processing.")
                client.files.download(file=out_vid.uri, destination=str(dest))
                return str(dest)

        # Handle steps array
        if hasattr(interaction, "steps") and interaction.steps:
            for step in interaction.steps:
                content_items = getattr(step, "content", []) or []
                if isinstance(content_items, list):
                    for item in content_items:
                        vdata = getattr(item, "data", None)
                        if getattr(item, "type", "") == "video" or vdata:
                            video_bytes = base64.b64decode(vdata) if isinstance(vdata, str) else vdata
                            dest.write_bytes(video_bytes)
                            return str(dest)

    except Exception as e:
        raise RuntimeError(f"Agent Platform video generation ({DEFAULT_VIDEO_MODEL}) failed: {e}") from e

    raise RuntimeError(f"{DEFAULT_VIDEO_MODEL} returned no video data for prompt: {prompt}")


def upload_to_gcs_tool(
    local_path: str,
    bucket_name: str,
    destination_path: str,
    content_type: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    """Uploads a local file to Google Cloud Storage and returns its authenticated mTLS browser URL.

    Args:
        local_path: Path to the local file to upload.
        bucket_name: Target GCS bucket name.
        destination_path: Path within the bucket (e.g. 'assets/image.png').
        content_type: Optional MIME type string.
        project: Optional GCP Project ID.

    Returns:
        Authenticated mTLS URL: https://storage.mtls.cloud.google.com/<bucket>/<destination_path>
    """
    p = Path(local_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"File to upload not found at: {local_path}")

    proj = project or _get_current_project()
    client = storage.Client(project=proj)
    bucket = client.bucket(bucket_name)

    # Auto-detect content type if omitted
    ctype = content_type
    if not ctype:
        ext = p.suffix.lower()
        if ext == ".html":
            ctype = "text/html; charset=utf-8"
        elif ext == ".json":
            ctype = "application/json"
        elif ext == ".png":
            ctype = "image/png"
        elif ext in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif ext == ".mp4":
            ctype = "video/mp4"

    blob = bucket.blob(destination_path)
    blob.upload_from_filename(str(p), content_type=ctype)
    logger.info(f"Uploaded {p.name} -> gs://{bucket_name}/{destination_path}")

    return f"https://storage.mtls.cloud.google.com/{bucket_name}/{destination_path}"
