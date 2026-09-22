"""Multimodal Input Ingestion and Normalization Module.

Handles loading, validating, and formatting multimodal input bundles containing
a primary text prompt and zero, one, or multiple reference images for Antigravity SDK
agents and Agent Platform models.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

from google.antigravity import types

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@dataclass
class InputImageRecord:
    """Metadata and raw payload for an input reference image."""

    path: str
    filename: str
    mime_type: str
    size_bytes: int
    base64_data: str
    sdk_image: types.Image

    def to_data_uri(self) -> str:
        """Returns the base64 data URI."""
        return f"data:{self.mime_type};base64,{self.base64_data}"


@dataclass
class MultimodalInputBundle:
    """Consolidated input payload passed into an automated multi-agent pipeline."""

    prompt: str
    images: List[InputImageRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_images(self) -> bool:
        """Checks if bundle contains any reference images."""
        return len(self.images) > 0

    @property
    def sdk_attachments(self) -> List[types.Image]:
        """Returns list of google.antigravity.types.Image attachments for agent.chat()."""
        return [img.sdk_image for img in self.images]

    def build_chat_turn_payload(self, text_instruction: str) -> List[Union[str, types.Image]]:
        """Constructs a composite turn payload [text, image1, image2, ...] for agent.chat()."""
        payload: List[Union[str, types.Image]] = [text_instruction]
        payload.extend(self.sdk_attachments)
        return payload


def load_multimodal_inputs(
    prompt: str,
    image_paths: Optional[Union[str, Sequence[str]]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> MultimodalInputBundle:
    """Loads and validates a text prompt and one or multiple input image paths.

    Args:
        prompt: Primary task, brief, or creative prompt string.
        image_paths: Path or list of paths to input reference images.
        metadata: Optional dictionary of supplementary context.

    Returns:
        A validated MultimodalInputBundle containing typed Image attachments.
    """
    cleaned_paths: List[str] = []
    if image_paths:
        if isinstance(image_paths, (str, Path)):
            cleaned_paths = [str(image_paths)]
        else:
            cleaned_paths = [str(p) for p in image_paths]

    image_records: List[InputImageRecord] = []
    for raw_path in cleaned_paths:
        p = Path(raw_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Multimodal input image not found at path: {p}")

        ext = p.suffix.lower()
        if ext not in SUPPORTED_MIME_TYPES:
            raise ValueError(
                f"Unsupported image format '{ext}' for file {p}. "
                f"Supported extensions: {list(SUPPORTED_MIME_TYPES.keys())}"
            )

        mime = SUPPORTED_MIME_TYPES[ext]
        raw_bytes = p.read_bytes()
        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        sdk_img = types.Image.from_file(str(p), description=f"Reference Image: {p.name}")

        image_records.append(
            InputImageRecord(
                path=str(p),
                filename=p.name,
                mime_type=mime,
                size_bytes=len(raw_bytes),
                base64_data=b64,
                sdk_image=sdk_img,
            )
        )

    logger.info(
        f"Loaded MultimodalInputBundle with {len(image_records)} image(s) and prompt: '{prompt[:60]}...'"
    )

    return MultimodalInputBundle(
        prompt=prompt,
        images=image_records,
        metadata=metadata or {},
    )
