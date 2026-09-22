---
name: multimodal-agent-builder
description: Guide and reusable code assets for building custom multi-agent, multimodal systems with asset generation (images, videos, bespoke animated HTML pages), multimodal inputs (text + multiple images), universal human-in-the-loop interaction (ask_question & AskQuestionHook), and intermediate asset passing tailored to any automated process.
---

# Multimodal Agent Builder Skill

A comprehensive skill and toolkit that guides AI agents in architecting and implementing custom **multi-agent, multimodal systems with asset generation** for any automated business or creative workflow.

Unlike fixed-topology pipelines, systems designed with this skill derive their **entire agent team structure from the specific process being automated**.

The agents are built using Google [Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/skills/google-antigravity-sdk/SKILL.md) (`google-antigravity` Python package).
They will also need `google-genai`, `pydantic`, `google-cloud-storage`.

---

## 1. Core Principles

1. **The Idea**:

   - We automate a process with a team of sub-agents, each of its own unique role.
     Process is known, the specific goal is new every time.
   - The user gives an inspiration, a task, an idea, a product - to work towards a goal.
   - We are expected to ask a human sometimes. Give them good options to choose from.
     Grow those options from the brand and identity when known,
     but also with the context and that initial inspiration in mind, not hard-coded.

1. **Process-First Team Topology**:
   - The team structure (which subagents exist, their specialized roles, system prompts, dependencies, and handoffs) is defined entirely by the business or creative process.
   - Example 1 (*Architectural Virtual Staging*): `spatial_concept_architect` -> `staging_render_artist` -> `cinematic_video_director` -> `showcase_packager`.
   - Example 2 (*Luxury Product Reveal*): `industrial_lore_writer` -> `material_rendering_specialist` -> `product_cinematographer` -> `client_pitch_packager`.
   - Example 3 (*E-Commerce Flash Drop*): `merchandise_strategist` -> `hero_visual_stylist` -> `motion_ad_creator` -> `storefront_packager`.

2. **Multimodal Inputs (Text + Single or Multiple Images)**:
   - Systems can accept a prompt along with zero, one, or multiple input images (e.g. site photos, sketches, CAD references, moodboards, existing product images).
   - Images are normalized, inspected for dimensions/MIME types, and attached to SDK agent turns via `google.antigravity.types.Image`.

3. **Real Asset Generation Primitives (Agent Platform)**:
   - **Image Generation**: High-contrast, photorealistic image synthesis via `gemini-3.1-flash-lite-image` on Agent Platform with `location="global"`.
   - **Video Generation**: 10-second 9:16 or 16:9 cinematic video generation from image and text via `gemini-omni-1.1-flash-preview` on Agent Platform using `client.interactions.create`.
   - **Bespoke Presentation Packaging**: 100% from-scratch generative HTML/CSS/SVG pages presenting the campaign to stakeholders (Impression First -> Details After -> Scroll-driven Animated Background -> Mobile 9:16 responsive).
   - **Google Cloud Storage (GCS)**: Authenticated mTLS delivery (`https://storage.mtls.cloud.google.com/<bucket>/<path>`).

4. **Universal Human-in-the-Loop Interaction (`ask_question` & `AskQuestionHook`)**:
   - Human interaction is **NOT limited to approval gates**. The agent frequently needs to ask clarifying questions clarify requirements, solicit user preferences between options, or ask for human review.
   - The agent itself decides *when* to ask and *what* options to present using the SDK's native `BuiltinTools.ASK_QUESTION`.
     Agents are not supposed to hardcode options UNLESS IT'S DICTATED BY THE PROCESS. Options must be generated depending on the context.
     There should always be an option to provide a custom answer, and the agent is supposed to handle that.

     Example: The process describes a step when the user must choose one of 3 colors: red, gree or blue.
     Result in the agent: The agent must ask a question with 4 options: red, green, blue.
     Example 2: the process describes a step when the user must tell what architecture style to use.
     Result in the agent: Depending on the target business and the process, the agent _may_ suggest some options,
     but there should be an additional option when the user just enters their own answer.

   - The core toolkit provides `core/console_runner.py` with `ConsoleAskQuestionHook(hooks.OnInteractionHook)`:
     - **Interactive Mode**: Dynamically renders any question and options in the console, parses numeric or text selections, or accepts freeform user input.
     - **Autonomous Mode (`--autonomous`)**: Automatically answers with default choices without blocking, enabling headless testing and CI/CD.
   - Core tools remain universal and flexible; the automated process or agent prompt defines the dialogue, not hardcoded gate frameworks.

5. **Intermediate Asset & State Tracking**:
   - `PipelineState` tracks prompt briefs, input images, intermediate assets (concepts, renders, scripts, videos, HTML), and user feedback across all stages.

6. **Design & Brand Guideline Independence**:
   - The skill and its core components **MUST NOT** impose design and brand guidelines (colors, fonts, visual tropes, styles).
   - Brand guidelines and visual direction MUST come from domain skills (e.g. `brand-guidelines`) or be derived dynamically from the specific process being automated.
   - The actual final agent that gets built for a specific process may impose its own process-specific or brand-specific guidelines, but the `multimodal-agent-builder` skill itself remains strictly unopinionated.

7. **Native Pydantic Structured Output (`response_schema`)**:
   - When subagents or stages produce structured data (e.g. compliance specs, design parameters, catalogs, metadata), they **MUST** use native Antigravity SDK structured output with Pydantic.
   - Define typed `pydantic.BaseModel` schemas and pass them to `LocalAgentConfig(response_schema=MyModel)`.
   - Extract validated results directly via `await response.structured_output()` and validate with `MyModel.model_validate(data)`:
     ```python
     import pydantic
     from google.antigravity import Agent, LocalAgentConfig

     class TaskSummary(pydantic.BaseModel):
         summary: str
         action_items: list[str]

     config = LocalAgentConfig(response_schema=TaskSummary, ...)
     async with Agent(config) as agent:
         response = await agent.chat("Analyze and summarize...")
         data = await response.structured_output()
         result = TaskSummary.model_validate(data)
     ```
   - **STRICTLY PROHIBITED**:
     - No regex code fence extraction (`re.search(r'```(?:json)?\s*(\{.*?\})\s*```')`).
     - No substring brace slicing (`first_brace:last_brace`).
     - No `json.loads(..., strict=False)` hacks. The SDK runtime enforces the schema at the model finish tool level.

8. **Zero Hardcoded Fallbacks & Dynamic Context-Driven Options**:
   - **ABSOLUTELY NO HARDCODED FALLBACK FOR ANYTHING**:
     - Never hardcode synthetic default dictionaries (e.g. fake laser specs or dummy product defaults).
     - Hardcoded values are ONLY allowed if they come directly from the process standard itself (e.g. ANSI/OSHA signal words: `DANGER`, `WARNING`, `CAUTION`) or the user creating the agent.
     - If schema validation fails, fail cleanly or allow the agent's turn to retry; never mask errors with synthetic domain slop.
   - **Dynamic Option Generation On The Fly**:
     - Question options presented to humans must be generated dynamically by the agent on the fly based on context, inspiration, and brand, rather than static script arrays.
     - Every question presented to the user **MUST** include an explicit choice allowing the user to provide their own custom answer (write-in), and the agent must handle that choice.

9. **Zero Fabricated Attributes & Dynamic Tool Prompt Synthesis**:
   - **Strict Ban on Hardcoded Prompt Templates**:
     Subagent system instructions (`system_instructions`) must define ONLY the subagent's role, inputs, and decision criteria. They must **NEVER** contain quoted prompt templates or boilerplate strings specifying what to pass to tools (e.g. `Specify: "Die-cut safety warning decal sticker badge, isolated on a neutral industrial slate surface..."`).
   - **Strict Ban on AI Stock Buzzwords & Aesthetic Tropes**:
     Never inject visual cliché buzzwords into prompts (e.g. `"8k resolution"`, `"photorealistic"`, `"macro photography"`, `"studio lighting"`, `"cinematic rim reflection"`, `"isolated on neutral slate surface"`, or unrequested color pairings).
   - **Strict Factual Derivation**:
     Tool prompts (for image generation, video generation, copywriting, presentation) MUST be synthesized dynamically by the subagent exclusively from:
     1. What the user actually specified in their prompt/brief.
     2. What the process strictly mandates (e.g. verified standard regulatory colors and symbols determined by upstream compliance analysis).
     3. Domain skills explicitly loaded (e.g. `brand-guidelines`).
   - If an attribute was not specified by the user or mandated by the standard (e.g. mounting surface, background, lighting, substrate finish), the agent must **never make it up**. If a choice is required, the agent must ask the user via `ask_question` or keep the prompt strictly focused on the required subject without fabricated environment slop.

---

## 2. Reusable Code Asset Library

The skill provides modular, ready-to-use Python building blocks under `core/`:

| Module | Purpose |
| :--- | :--- |
| [`core/multimodal_input.py`](./core/multimodal_input.py) | Ingestion and normalization of text prompts and one or multiple input images into `Image` attachments. |
| [`core/asset_tools.py`](./core/asset_tools.py) | Standalone Agent Platform tool functions for image generation, video generation, and GCS mTLS uploads. |
| [`core/console_runner.py`](./core/console_runner.py) | Universal console runner with `ConsoleAskQuestionHook` supporting native SDK `BuiltinTools.ASK_QUESTION` in interactive and autonomous modes. |
| [`core/html_packager.py`](./core/html_packager.py) | Generative HTML presentation engine enforcing Impression First -> Details After -> Scroll Background -> Mobile 9:16. |
| [`core/pipeline_engine.py`](./core/pipeline_engine.py) | Process-agnostic multi-agent pipeline engine managing `Stage` definitions, execution, and state passing. |

---

## 3. How to Build an Agent Team for a Process

When given a process to automate, follow this 5-step engineering pattern:

### Step 1: Decompose the Process into Stages & Map Media Modalities
Identify the inputs, transformations, intermediate assets, and checkpoints:
1. **Starting Inputs**: Ingest text brief, plus zero, one, or more reference images (`MultimodalInputBundle`).
2. **Process-to-Media Modality Mapping (Static vs. Kinetic / Temporal)**:
   - **Static Form, Plating, or Product Design**: Map to **Image Generation** via `generate_image_tool`.
   - **Temporal Action, Kinetic Motion, Table Landing, or Dynamic Reveal**:
     When the process describes a dynamic experience, movement, tableside reveal, or *how something lands in front of a guest or client*, do NOT leave it solely as text or written instructions. **Materialize it as an animated video asset** via `generate_video_tool` (10-second 9:16 or 16:9 motion loop), attaching the rendered image as multimodal reference (`image_path`).
   - **Stakeholder Presentation & Packaging**: Map to `ProcessPresentationPackager`, embedding both the generated image (`image_src`) and the motion video (`video_src`).
3. **Human-in-the-Loop Checkpoints**: Where does the process dictate collaboration, iteration, or sign-off? Equip `BuiltinTools.ASK_QUESTION` or `prompt_ask_question` with dynamic context-derived options and custom write-in handling.

### Step 2: Define Pydantic Schemas & Specialized Subagents
For any stage producing structured data, define a typed `pydantic.BaseModel`:
```python
import pydantic

class ConceptSpec(pydantic.BaseModel):
    title: str
    narrative_hook: str
    core_attributes: list[str]
```

Create `types.SubagentConfig` instances with:
- `name`: Clean lowercase identifier.
- `description`: Actionable summary of role and responsibilities.
- `system_instructions`: Focused persona. **Do not hardcode styles or hex codes in prompts**; instruct subagents to consult relevant domain skills.
- `tools`: Equip only the tools the specific subagent requires (including `types.BuiltinTools.ASK_QUESTION` when interactive dialogue is needed).
- `capabilities`: Typically `types.SubagentCapabilities(agent_behavior=types.AgentBehavior.AUTONOMOUS)` (or `types.AgentBehavior.INTERACTIVE` if the subagent directly initiates user questions).

### Step 3: Wire Stages into the Pipeline Engine
```python
from core.pipeline_engine import PipelineEngine, Stage
from core.multimodal_input import load_multimodal_inputs

engine = PipelineEngine(
    stages=[
        Stage(
            name="concept",
            subagent_config=concept_subagent_config,
            response_schema=ConceptSpec,
            run_fn=run_concept_step,
        ),
        Stage(
            name="visual_production",
            subagent_config=render_subagent_config,
            run_fn=run_render_step,
        ),
        Stage(
            name="video_production",
            subagent_config=video_subagent_config,
            run_fn=run_video_step,
        ),
        Stage(
            name="presentation_packaging",
            subagent_config=presenter_subagent_config,
            run_fn=run_package_step,
        ),
    ]
)
```

Each stage's `run_fn` has the signature `async def run_fn(agent: Agent, state: PipelineState, extra: Optional[str]) -> Dict[str, Any]`:
- **Structured Extraction**: Call `spec, _ = await execute_structured_turn(prompt, response_schema=MyModel, ...)` to enforce Pydantic output natively.
- **Human Dialogue / Review**: Ask clarifying questions or review direction via `BuiltinTools.ASK_QUESTION` or `prompt_ask_question(question, dynamic_options, default_index=0, autonomous=...)` with dynamic context-driven options and custom write-in.
- **Asset Generation**: Call `generate_image_tool(...)` or `generate_video_tool(...)`, register outputs in `state.set_artifact("visual", local_path)`, and upload to GCS via `upload_to_gcs_tool(...)`.


### Step 4: Ingest Multimodal Inputs
```python
input_bundle = load_multimodal_inputs(
    prompt="Minimalist Brutalist Lakehouse with warm cedar accents",
    image_paths=["path/to/site_photo.jpg", "path/to/blueprint.png"],
)
```

### Step 5: Execute and Deliver
```python
results = await engine.execute(
    inputs=input_bundle,
    autonomous=args.autonomous,
)
```

---

## 4. Client Presentation Philosophy (Bespoke HTML)

All HTML presentation outputs generated by the packager must adhere to the 4 tenets:
1. **Impression First**: Deliver a monumental, arresting visual punch about the innovation or promo above the fold.
2. **Details Go After**: Secondary scroll sections reveal substantive storytelling, social copy, video showcases, and specs.
3. **Scroll-Driven Animated CSS/SVG Background**: The agent ideates a unique dynamic vector/SVG background that reacts to scrolling up and down.
4. **Mobile (9:16) & Desktop Responsive**: Fluid sizing via `clamp()`, `viewport-fit=cover`, single-column stacking under `@media (max-width: 768px)`, and zero horizontal overflow.

If the agent is able to upload the presentation to Google Cloud Storage, it should present mTLS URLs to the user.

---

## 5. Execution Environment & CLI Commands

When invoking scripts built with this toolkit:

1. **Virtual Environment Scope (`uv`)**:
   Always use `uv` and virtual environments.
   Check if you are operating in a workspace with a virtual environment.
   Keep it simple: run `uv` to check current venv under current folder, see if there is a `.venv` sub-folder.
   If there is venv, use it. Otherwise create one with `uv venv`.
   Don't spend too much time looking for an existing venv.
   If you create a new venv, use `uv`, and leverage `pyproject.toml`.

   Always execute using the active `uv` project. From the workspace root:
   ```bash
   uv run python <script_path>.py --brief "<Process Brief>" [OPTIONS]
   ```

   Do not hardcode Google Cloud project Ids, user names or any PII that was not explicitly provided by the user.

2. **Multimodal Reference Images (`--image`)**:
   - For image-guided workflows, supply relevant domain photos (e.g. site photos, sketches, product references).
   - Omit `--image` for pure text-guided generation. Never supply mismatched images from unrelated campaigns.

3. **Human-in-the-Loop Interaction & Autonomy**:
   - **Interactive Mode** (default): Uses `ConsoleAskQuestionHook` to render questions and options in the console whenever the agent invokes `ask_question`. Reviewers can pick numbers, option text, or provide freeform direction.
   - **Autonomous Mode (`--autonomous`)**: Automatically answers agent questions using the default options without blocking, enabling unattended CI/CD runs and automated regression testing.

