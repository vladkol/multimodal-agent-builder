"""Generic From-Scratch Campaign & Process Presentation Packager.

Generates a fully bespoke, animated, and mobile-responsive presentation page
for any automated multi-agent workflow using Agent Platform (gemini-3.8-flash).

Enforces the Customer Presentation Hierarchy:
1. Impression First: Arresting hero punch and visual focus above the fold.
2. Details Go After: In-depth narrative, specifications, video showcase, and CTA.
3. Scroll-Driven Animated CSS/SVG Background: Uniquely ideated per process.
4. Mobile-First (9:16 Viewport) and Desktop Responsiveness.
"""

from __future__ import annotations

import base64
import html
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .asset_tools import DEFAULT_GENERIC_MODEL, get_agent_platform_client

logger = logging.getLogger(__name__)


class ProcessPresentationPackager:
    """Generates custom, animated presentation experiences tailored to any process."""

    def render_presentation_html(
        self,
        title: str,
        hook: str,
        narrative: str,
        headline: str,
        body_text: str,
        cta_text: str,
        image_src: str,
        video_src: Optional[str] = None,
        image_mtls_url: Optional[str] = None,
        video_mtls_url: Optional[str] = None,
        metadata_mtls_url: Optional[str] = None,
        extra_context: Optional[str] = None,
        local_image_path: Optional[str] = None,
        local_video_path: Optional[str] = None,
        theme_colors: Optional[Dict[str, str]] = None,
        font_family: Optional[str] = None,
    ) -> str:
        """Synthesizes a bespoke presentation page designed from scratch."""
        # Prepare base64 fallbacks for local/offline rendering
        resolved_img_src = image_src
        if local_image_path and Path(local_image_path).exists():
            try:
                raw_img = Path(local_image_path).read_bytes()
                b64_img = base64.b64encode(raw_img).decode("utf-8")
                resolved_img_src = f"data:image/png;base64,{b64_img}"
            except Exception as e:
                logger.debug(f"Image base64 fallback error: {e}")

        resolved_vid_src = video_src or ""
        if local_video_path and Path(local_video_path).exists():
            try:
                raw_vid = Path(local_video_path).read_bytes()
                b64_vid = base64.b64encode(raw_vid).decode("utf-8")
                resolved_vid_src = f"data:video/mp4;base64,{b64_vid}"
            except Exception as e:
                logger.debug(f"Video base64 fallback error: {e}")

        # Attempt 1: Agentic synthesis from scratch via Agent Platform
        try:
            generated_html = self._generate_bespoke_page_with_llm(
                title=title,
                hook=hook,
                narrative=narrative,
                headline=headline,
                body_text=body_text,
                cta_text=cta_text,
                image_src=resolved_img_src,
                video_src=resolved_vid_src,
                image_mtls_url=image_mtls_url or image_src,
                video_mtls_url=video_mtls_url or (video_src or ""),
                metadata_mtls_url=metadata_mtls_url or "",
                extra_context=extra_context or "",
            )
            if generated_html and "<!DOCTYPE html>" in generated_html and "</html>" in generated_html:
                return generated_html
        except Exception as e:
            logger.warning(f"Agent Platform bespoke presentation synthesis fallback: {e}")

        # Attempt 2: Resilient structural fallback
        return self._build_structural_fallback_html(
            title=title,
            hook=hook,
            headline=headline,
            body_text=body_text,
            cta_text=cta_text,
            image_src=resolved_img_src,
            video_src=resolved_vid_src,
            image_mtls_url=image_mtls_url or image_src,
            video_mtls_url=video_mtls_url or "",
            metadata_mtls_url=metadata_mtls_url or "",
            theme_colors=theme_colors,
            font_family=font_family,
        )

    def _generate_bespoke_page_with_llm(
        self,
        title: str,
        hook: str,
        narrative: str,
        headline: str,
        body_text: str,
        cta_text: str,
        image_src: str,
        video_src: str,
        image_mtls_url: str,
        video_mtls_url: str,
        metadata_mtls_url: str,
        extra_context: str,
    ) -> Optional[str]:
        """Prompts gemini-3.8-flash on Agent Platform to synthesize the HTML page."""
        client = get_agent_platform_client()

        prompt = f"""You are an elite Digital Creative Technologist and Process Presentation Architect.
Your task is to design and write the complete, self-contained HTML5 presentation code from scratch for this showcase:

CORE CONCEPT / TITLE: "{title}"
PROVOCATIVE HOOK: "{hook}"
NARRATIVE & PHILOSOPHY: "{narrative}"
HEADLINE: "{headline}"
BODY & STORYTELLING:
{body_text}
CALL TO ACTION: "{cta_text}"
ADDITIONAL PROCESS CONTEXT:
{extra_context}

PRESENTATION ARCHITECTURE:
1. IMPRESSION FIRST (Above the Fold):
   - Deliver an unmistakable, arresting visceral punch about the project/promo.
   - High-contrast typographic hierarchy, provocative hook line, and the hero Visual Asset frame.
   - Immediate emotional resonance before lengthy text.

2. DETAILS GO AFTER (Below the Fold):
   - As the user scrolls down, unpack the full depth:
     - The narrative body and craftsmanship/methodology.
     - The 10-second one-shot video showcase (embedded video player preserving its native aspect ratio in an architectural frame).
     - Clear, magnetic Call to Action ({cta_text}).

3. SCROLL-DRIVEN ANIMATED CSS / SVG BACKGROUND:
   - Ideate and write a custom animated CSS or SVG background that responds dynamically to scrolling up and down.
   - Conceive an animation suited to "{title}" (e.g. morphing vector flux, shifting bezier waves, kinetic geometric depth, or dynamic gradient illumination).
   - You can include modern animation libraries:
     <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
     <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>

4. MOBILE-FIRST & 9:16 SCREEN RESPONSIVENESS:
   - The page MUST look stunning on mobile screens (including 9:16 vertical smartphone viewports) as well as desktop displays.
   - Use: `<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">`.
   - Fluid typography via clamp(), clean stacking on mobile (@media (max-width: 768px)), zero horizontal scrollbar (overflow-x: hidden), and touch-friendly buttons.

5. MEDIA INTEGRATION:
   - Visual Asset: `<img src="__KEY_VISUAL_SRC__" alt="{html.escape(title)}" class="hero-media-asset" />`
   - Video Short: `<video controls playsinline class="video-media-asset" src="__PRODUCT_VIDEO_SRC__"></video>` (ensure CSS uses `width: 100%; height: auto;` so both 16:9 and 9:16 videos display uncropped)
   - Authenticated Cloud URLs:
     - Visual: {image_mtls_url}
     - Video: {video_mtls_url}
     - Metadata: {metadata_mtls_url}

6. OUTPUT FORMAT:
   - Respond ONLY with the complete standalone HTML document starting with `<!DOCTYPE html>` and ending with `</html>`.
   - Inlined CSS and JavaScript inside `<style>` and `<script>` tags.
   - Now raw markdown or LaTeX, this will be an HTML page.
   - Zero markdown commentary outside of optional ```html ... ``` fences.
"""

        response = client.models.generate_content(
            model=DEFAULT_GENERIC_MODEL,
            contents=prompt,
        )

        text = response.text if hasattr(response, "text") else ""
        if not text:
            return None

        generated_html = ""
        fence_match = re.search(r"```(?:html)?\s*(<!DOCTYPE html>.*?</html>)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            generated_html = fence_match.group(1).strip()
        else:
            doc_match = re.search(r"(<!DOCTYPE html>.*?</html>)", text, re.DOTALL | re.IGNORECASE)
            if doc_match:
                generated_html = doc_match.group(1).strip()

        if generated_html:
            # Substitute media placeholders post-generation
            generated_html = generated_html.replace("__KEY_VISUAL_SRC__", image_src)
            generated_html = generated_html.replace("__PRODUCT_VIDEO_SRC__", video_src)
            if image_src != image_mtls_url:
                generated_html = generated_html.replace(f'src="{image_mtls_url}"', f'src="{image_src}"')
            if video_src and video_src != video_mtls_url:
                generated_html = generated_html.replace(f'src="{video_mtls_url}"', f'src="{video_src}"')
            return generated_html

        return None

    def _build_structural_fallback_html(
        self,
        title: str,
        hook: str,
        headline: str,
        body_text: str,
        cta_text: str,
        image_src: str,
        video_src: str,
        image_mtls_url: str,
        video_mtls_url: str,
        metadata_mtls_url: str,
        theme_colors: Optional[Dict[str, str]] = None,
        font_family: Optional[str] = None,
    ) -> str:
        """Resilient structural fallback adhering to Impression First and mobile responsiveness without imposing brand styles."""
        title_esc = html.escape(title)
        hook_esc = html.escape(hook)
        headline_esc = html.escape(headline)
        body_esc = html.escape(body_text).replace("\n", "<br>")
        cta_esc = html.escape(cta_text)

        colors = theme_colors or {
            "bg_dark": "#0f172a",
            "bg_surface": "#1e293b",
            "accent": "#3b82f6",
            "border": "rgba(255, 255, 255, 0.1)",
            "text": "#f8fafc",
            "muted": "#94a3b8",
        }
        font = font_family or "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

        video_tag = ""
        if video_src:
            video_tag = f"""
            <div class="video-showcase">
              <div class="video-frame-916">
                <video controls playsinline src="{video_src}"></video>
              </div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{title_esc} — Process Showcase</title>
  <style>
    :root {{
      --bg-dark: {colors.get("bg_dark", "#0f172a")};
      --bg-surface: {colors.get("bg_surface", "#1e293b")};
      --accent: {colors.get("accent", "#3b82f6")};
      --border: {colors.get("border", "rgba(255, 255, 255, 0.1)")};
      --text: {colors.get("text", "#f8fafc")};
      --muted: {colors.get("muted", "#94a3b8")};
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg-dark);
      color: var(--text);
      font-family: {font};
      overflow-x: hidden;
      line-height: 1.6;
      min-height: 100vh;
    }}
    #bg-svg {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
      opacity: 0.25;
    }}
    .wrapper {{
      position: relative;
      z-index: 1;
      max-width: 1200px;
      margin: 0 auto;
      padding: clamp(1.5rem, 4vw, 3rem) clamp(1rem, 3vw, 2rem);
    }}
    .impression-hero {{
      min-height: 80vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      padding: 3rem 0;
    }}
    .hero-punch {{
      font-size: clamp(2.5rem, 6vw, 5rem);
      font-weight: 900;
      line-height: 1.05;
      margin-bottom: 1.2rem;
      background: linear-gradient(135deg, #FFFFFF 40%, var(--accent) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .hero-hook {{
      font-size: clamp(1.1rem, 2.5vw, 1.5rem);
      color: var(--muted);
      max-width: 800px;
      margin-bottom: 2.5rem;
    }}
    .hero-media-box {{
      width: 100%;
      max-width: 960px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      box-shadow: 0 25px 50px rgba(0,0,0,0.6);
      background: var(--bg-surface);
    }}
    .hero-media-box img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .details-grid {{
      padding: 4rem 0;
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 3rem;
      align-items: start;
    }}
    @media (max-width: 768px) {{
      .details-grid {{ grid-template-columns: 1fr; gap: 2rem; }}
    }}
    .details-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: clamp(1.5rem, 3vw, 2.5rem);
    }}
    .headline {{
      font-size: clamp(1.5rem, 3vw, 2.2rem);
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 1rem;
    }}
    .body-copy {{
      color: #E2E8F0;
      font-size: 1.05rem;
      margin-bottom: 2rem;
    }}
    .cta-btn {{
      display: inline-block;
      background: var(--accent);
      color: var(--bg-dark);
      font-weight: 700;
      padding: 0.9rem 2rem;
      border-radius: 6px;
      text-decoration: none;
    }}
    .video-frame-916 {{
      width: 100%;
      border-radius: 16px;
      overflow: hidden;
      border: 2px solid var(--border);
      background: #000;
      margin: 0 auto;
    }}
    .video-frame-916 video {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .mtls-footer {{
      margin-top: 3rem;
      padding-top: 2rem;
      border-top: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      justify-content: center;
    }}
    .mtls-link {{
      color: var(--muted);
      font-family: 'Space Grotesk', monospace;
      font-size: 0.85rem;
      text-decoration: none;
      border: 1px solid var(--border);
      padding: 0.4rem 0.8rem;
      border-radius: 4px;
    }}
    .mtls-link:hover {{ color: var(--accent); border-color: var(--accent); }}
  </style>
</head>
<body>
  <svg id="bg-svg" viewBox="0 0 1000 1000" preserveAspectRatio="none">
    <path id="svg-wave" d="M0,300 Q500,100 1000,300" fill="none" stroke="{html.escape(colors.get('accent', '#3b82f6'))}" stroke-width="2" />
  </svg>

  <div class="wrapper">
    <section class="impression-hero">
      <h1 class="hero-punch">{title_esc}</h1>
      <p class="hero-hook">{hook_esc}</p>
      <div class="hero-media-box">
        <img src="{image_src}" alt="{title_esc}" />
      </div>
    </section>

    <section class="details-grid">
      <div class="details-card">
        <h2 class="headline">{headline_esc}</h2>
        <div class="body-copy">{body_esc}</div>
        <a href="#action" class="cta-btn">{cta_esc}</a>
      </div>
      {video_tag}
    </section>

    <div class="mtls-footer">
      <a href="{image_mtls_url}" target="_blank" class="mtls-link">Visual Asset (mTLS)</a>
      <a href="{video_mtls_url}" target="_blank" class="mtls-link">Video Short (mTLS)</a>
      <a href="{metadata_mtls_url}" target="_blank" class="mtls-link">Metadata JSON (mTLS)</a>
    </div>
  </div>

  <script>
    window.addEventListener('scroll', () => {{
      const y = window.scrollY || window.pageYOffset;
      const wave = document.getElementById('svg-wave');
      if (wave) wave.setAttribute('d', `M0,${{300 + y * 0.15}} Q500,${{100 - y * 0.1}} 1000,${{300 + y * 0.08}}`);
    }});
  </script>
</body>
</html>
"""
