import os
import logging
from typing import Literal, Optional, Callable, Type, TypeVar
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gemini_service")

# Load environment variables (useful for local command-line tests)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Select the model. Default to gemini-2.5-flash as it is fast, cost-effective,
# supports structured JSON outputs, and handles multimodal audio inputs natively.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Global client cache for lazy-instantiation
_client = None


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _falsy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"0", "false", "no", "off"}


def _api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def _vertex_project() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("VERTEXAI_PROJECT")
        or ""
    ).strip()


def _vertex_location() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("VERTEXAI_LOCATION")
        or "us-central1"
    ).strip()


def use_vertex_ai() -> bool:
    """
    Prefer Gemini Enterprise / Vertex AI when explicitly enabled or when a
    Google Cloud project is configured. Set GOOGLE_GENAI_USE_VERTEXAI=0 to
    force the legacy Gemini Developer API (AI Studio key) instead.
    """
    if _falsy_env("GOOGLE_GENAI_USE_VERTEXAI") or _falsy_env("GOOGLE_GENAI_USE_ENTERPRISE"):
        return False
    if _truthy_env("GOOGLE_GENAI_USE_VERTEXAI") or _truthy_env("GOOGLE_GENAI_USE_ENTERPRISE"):
        return True
    return bool(_vertex_project())


def use_vertex_express_mode() -> bool:
    return _truthy_env("GOOGLE_GENAI_USE_VERTEXAI_EXPRESS")


def is_configured() -> bool:
    """Return True when Vertex AI or Gemini Developer API credentials are present."""
    if use_vertex_ai():
        if use_vertex_express_mode():
            return bool(_api_key())
        if _vertex_project():
            return True
        return bool(_api_key())
    return bool(_api_key())


def get_gemini_client() -> genai.Client:
    """
    Lazily instantiates the Google Gen AI client.

    Default path: Gemini Enterprise / Vertex AI with Application Default
    Credentials (gcloud auth application-default login or a service account).

    Alternatives:
      - Vertex express mode: GOOGLE_GENAI_USE_VERTEXAI_EXPRESS=1 + GEMINI_API_KEY
      - Legacy Developer API: GOOGLE_GENAI_USE_VERTEXAI=0 + GEMINI_API_KEY
    """
    global _client
    if _client is None:
        http_options = types.HttpOptions(api_version="v1")

        if use_vertex_ai():
            project = _vertex_project()
            location = _vertex_location()
            api_key = _api_key()

            if use_vertex_express_mode() and api_key:
                logger.info("Initializing Gemini Enterprise client (Vertex express mode).")
                _client = genai.Client(
                    vertexai=True,
                    api_key=api_key,
                    http_options=http_options,
                )
            elif project:
                logger.info(
                    "Initializing Gemini Enterprise client for project=%s location=%s",
                    project,
                    location,
                )
                _client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                    http_options=http_options,
                )
            elif api_key:
                logger.info("Initializing Gemini Enterprise client with Vertex API key.")
                _client = genai.Client(
                    vertexai=True,
                    api_key=api_key,
                    http_options=http_options,
                )
            else:
                logger.warning(
                    "Vertex AI is enabled but GOOGLE_CLOUD_PROJECT and GEMINI_API_KEY are missing. "
                    "Set GOOGLE_CLOUD_PROJECT and authenticate with ADC, or configure express mode."
                )
                _client = genai.Client(http_options=http_options)
        else:
            api_key = _api_key()
            if not api_key:
                logger.warning(
                    "GEMINI_API_KEY not found. Set GOOGLE_GENAI_USE_VERTEXAI=1 with "
                    "GOOGLE_CLOUD_PROJECT for Gemini Enterprise, or provide GEMINI_API_KEY."
                )
            _client = genai.Client(api_key=api_key or None)
    return _client

# =====================================================================
# 0. Pydantic Schemas
# =====================================================================

class Concept(BaseModel):
    title: str = Field(description="Short concept title")
    notes: str = Field(description="Clear, accurate notes (roughly 80-150 words) covering the core idea, key facts, and why/how.")

class StudyNotes(BaseModel):
    concepts: list[Concept] = Field(description="List of 3-6 logical sub-concepts")

class PeckishReaction(BaseModel):
    reaction_type: Literal["SATISFIED", "CURIOUS", "CONFUSED"] = Field(
        description="SATISFIED if accurate/complete, CURIOUS if accurate but shallow, CONFUSED if wrong/contradictory"
    )
    peckish_response: str = Field(
        description="What Peckish says out loud to the student. Short, 2-4 sentences, natural spoken style. Mention what landed, give a subtle hint if needed, and ask the next question."
    )
    feedback_summary: str = Field(
        default="",
        description="One short sentence naming what the student's answer currently shows."
    )
    subtle_hint: str = Field(
        default="",
        description="A gentle hint about the most important missing or unclear idea, without giving the full answer away."
    )
    follow_up_question: str = Field(
        default="",
        description="A specific meaningful question Peckish should ask next. Empty only when fully satisfied."
    )
    correct_points: list[str] = Field(
        default_factory=list,
        description="Up to three specific ideas from the student answer that were accurate or promising."
    )
    missing_points: list[str] = Field(
        default_factory=list,
        description="Up to three specific gaps, shallow areas, or misconceptions still present."
    )
    depth_score: int = Field(
        description="A calibrated score from 0 to 100 indicating explanation depth and accuracy. Wrong answers should be low, not 50."
    )
    misconception_detected: Optional[str] = Field(
        default=None,
        description="Short description of the specific misconception/gap, or None if none detected."
    )

class FossilCard(BaseModel):
    fossil_name: str = Field(
        description="A short, playful 2-4 word name for this misconception (like a species name, e.g., 'Ignis Fatuus Phlogiston')"
    )
    what_they_said: str = Field(
        description="One sentence, neutral, non-judgmental restatement of the student's gap/misconception."
    )
    the_truth: str = Field(
        description="One clear sentence explaining the correct concept."
    )
    flavor_text: str = Field(
        description="One whimsical museum-placard-style sentence."
    )

class ReteachPrompt(BaseModel):
    peckish_prompt: str = Field(
        description="Playful and curious prompt by Peckish asking the student to re-explain the misconception topic."
    )

class RevisionFlashcard(BaseModel):
    front: str = Field(description="Short prompt for the front of the flashcard")
    back: str = Field(description="Concise answer for the back of the flashcard")
    cue: str = Field(description="Memory cue or teaching prompt")
    image_prompt: str = Field(description="Short prompt for a friendly supporting illustration")

class RevisionMindmapNode(BaseModel):
    label: str = Field(description="Node label, 2-6 words")
    summary: str = Field(description="Two or three complete study-note points separated by semicolons. Each point should be 8-16 words and include useful detail.")
    icon: str = Field(description="One supported icon name: arrow, book, brain, chip, compass, gear, info, key, leaf, link, map, spark, or sun")
    color: str = Field(description="Hex colour for this node")
    image_prompt: str = Field(description="Short visual prompt for an image representing the node")

class RevisionFlowStep(BaseModel):
    title: str = Field(description="Step title")
    description: str = Field(description="Short description of this step")
    checkpoint: str = Field(description="Self-check question for this step")
    icon: str = Field(description="Short icon label or step number")

class RevisionResource(BaseModel):
    title: str = Field(description="Title for the revision resource")
    intro: str = Field(default="", description="Short SEN-aware introduction")
    central_idea: str = Field(default="", description="Central mindmap idea when relevant")
    central_image_prompt: str = Field(default="", description="Visual prompt for central mindmap image")
    cards: list[RevisionFlashcard] = Field(default_factory=list, description="Flashcards when resource_type is flashcards")
    nodes: list[RevisionMindmapNode] = Field(default_factory=list, description="Mindmap nodes when resource_type is mindmap")
    steps: list[RevisionFlowStep] = Field(default_factory=list, description="Flowchart steps when resource_type is flowchart")
    study_steps: list[str] = Field(default_factory=list, description="How to use this organiser")
    sen_profile: str = Field(description="SEN profile this resource was adapted for")

# Type variable for Pydantic schemas
T = TypeVar("T", bound=BaseModel)

# =====================================================================
# Error Handling Helper
# =====================================================================

def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "resource_exhausted" in message or "quota" in message


def _generate_structured_data(
    prompt: str,
    schema: Type[T],
    default_factory: Callable[[], dict],
    system_instruction: Optional[str] = None
) -> dict:
    """
    Requests structured JSON from Gemini.
    If the response is missing, malformed, or fails validation:
      - It logs the error.
      - Retries once with a stricter instruction.
      - If that also fails, returns the safe default dictionary.
    """
    # Configuration setup
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.2,  # Keep temperature low for deterministic JSON structures
    )
    
    # --- Attempt 1 ---
    try:
        client = get_gemini_client()
        logger.info(f"API Request (Attempt 1) | Model: {GEMINI_MODEL} | Prompt: {prompt[:100]}...")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config
        )
        raw_text = response.text
        logger.info(f"Raw Response (Attempt 1): {raw_text}")
        
        # Validate structure
        validated_data = schema.model_validate_json(raw_text)
        return validated_data.model_dump()
        
    except Exception as e:
        if _is_quota_error(e):
            logger.error(f"Attempt 1 failed with quota/rate-limit error: {e}. Skipping retry.")
            return default_factory()

        logger.error(f"Attempt 1 failed. Error: {e}. Retrying once...")

        # --- Attempt 2 (Retry) ---
        try:
            client = get_gemini_client()
            retry_prompt = (
                f"{prompt}\n\n"
                "CRITICAL: Your previous response failed JSON schema validation or was malformed. "
                "You MUST output valid JSON that strictly conforms to the requested schema. "
                "Do not include any explanation or extra text outside of the raw JSON."
            )
            retry_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1,  # Lower temperature to decrease randomness
            )
            logger.info("API Request (Attempt 2 - Retry)...")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=retry_prompt,
                config=retry_config
            )
            raw_text = response.text
            logger.info(f"Raw Response (Attempt 2 - Retry): {raw_text}")
            
            validated_data = schema.model_validate_json(raw_text)
            return validated_data.model_dump()
            
        except Exception as retry_e:
            logger.critical(f"Both attempts failed. Returning safe fallback dictionary. Retry error: {retry_e}")
            return default_factory()

# =====================================================================
# 1. generate_notes
# =====================================================================

def default_study_notes() -> dict:
    return {
        "concepts": [
            {
                "title": "Core Concepts Overview",
                "notes": "No notes could be generated at this time. Please check your network connection or API settings."
            }
        ]
    }

def generate_notes(topic: str) -> dict:
    """
    Generates study notes on a topic, pre-split into 3-6 logical concept sections.
    
    Args:
        topic: The subject matter to generate notes for.
        
    Returns:
        A dictionary matching the StudyNotes schema, containing a list of concepts.
    """
    prompt = f"""You are creating concise, well-structured study notes on a topic for a student. Break the topic into 3-6 logical sub-concepts, each digestible on its own. For each sub-concept, write clear, accurate notes (roughly 80-150 words) covering the core idea, key facts, and — where relevant — the underlying "why/how", not just definitions.

Topic: {topic}"""

    return _generate_structured_data(
        prompt=prompt,
        schema=StudyNotes,
        default_factory=default_study_notes
    )

# =====================================================================
# 2. extract_concepts_from_notes
# =====================================================================

def default_extracted_notes(raw_text: str) -> dict:
    return {
        "concepts": [
            {
                "title": "Imported Notes Segment",
                "notes": raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
            }
        ]
    }

def extract_concepts_from_notes(raw_text: str) -> dict:
    """
    Splits student's uploaded raw text into 3-6 logical concept sections.
    Preserves original substantive content without inventing new content.
    
    Args:
        raw_text: The string content extracted from an uploaded document.
        
    Returns:
        A dictionary matching the StudyNotes schema.
    """
    prompt = f"""You will receive a raw text of study notes uploaded by a student. Your task is to split this raw text into 3-6 logical concept sections, each with a short title, without altering the substantive content. This is organizing existing material, not generating new content. Keep the text close to the original, but formatted into logical chunks.

Raw notes text:
{raw_text}"""

    return _generate_structured_data(
        prompt=prompt,
        schema=StudyNotes,
        default_factory=lambda: default_extracted_notes(raw_text)
    )

# =====================================================================
# 3. get_peckish_reaction
# =====================================================================

def _terms(text: str) -> set[str]:
    import re

    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
        "is", "it", "of", "on", "or", "that", "the", "this", "to", "what", "when",
        "where", "why", "with",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower())
        if token not in stopwords
    }


def default_peckish_reaction(
    topic: str = "this topic",
    source_notes: str = "",
    student_explanation: str = "",
) -> dict:
    source_terms = _terms(source_notes)
    student_terms = _terms(student_explanation)
    overlap = len(source_terms & student_terms)
    coverage = overlap / max(len(source_terms), 1)
    word_count = len(student_explanation.split())
    has_depth_words = any(
        marker in student_explanation.lower()
        for marker in ("because", "so that", "therefore", "which means", "this causes", "this means")
    )
    depth_score = min(100, int((coverage * 82) + min(word_count, 90) * 0.48))
    if has_depth_words:
        depth_score = min(100, depth_score + 12)

    if word_count < 18:
        depth_score = max(20, min(depth_score, 42))
        return {
            "reaction_type": "CURIOUS",
            "peckish_response": (
                "I can hear the outline, but I am still missing the bit that makes it work. "
                "Try adding what causes the main change and why it matters."
            ),
            "feedback_summary": "Your answer gives a starting outline but not enough cause-and-effect yet.",
            "subtle_hint": "Name the mechanism or reason behind the key step.",
            "follow_up_question": f"What is the main cause or mechanism behind {topic}?",
            "correct_points": [],
            "missing_points": ["Cause or mechanism", "Why the idea matters"],
            "depth_score": depth_score,
            "misconception_detected": "The explanation is too brief to show the cause or mechanism.",
        }

    if coverage < 0.08:
        depth_score = max(5, min(depth_score, 34))
        return {
            "reaction_type": "CONFUSED",
            "peckish_response": (
                "Wait, I am not sure I can connect that back to the notes yet. "
                "Can you anchor it to one key word or process from the source?"
            ),
            "feedback_summary": "Your answer does not clearly connect to the source notes yet.",
            "subtle_hint": "Use one exact key term from the notes, then explain how it fits.",
            "follow_up_question": f"Which key part of the notes is most important for {topic}?",
            "correct_points": [],
            "missing_points": ["Connection to the source notes"],
            "depth_score": depth_score,
            "misconception_detected": "The explanation does not connect clearly to the source notes.",
        }

    if depth_score >= 70 and has_depth_words:
        return {
            "reaction_type": "SATISFIED",
            "peckish_response": (
                "That clicks now. You connected the idea to why it works, so I can carry it forward."
            ),
            "feedback_summary": "Your answer explains the main idea with useful cause-and-effect.",
            "subtle_hint": "",
            "follow_up_question": "",
            "correct_points": ["Main idea", "Cause-and-effect"],
            "missing_points": [],
            "depth_score": depth_score,
            "misconception_detected": None,
        }

    return {
        "reaction_type": "CURIOUS",
        "peckish_response": (
            "I am close to getting it, and the main idea is starting to stick. "
            "The missing piece is the next why: what changes, or what causes the result?"
        ),
        "feedback_summary": "Your answer is partly right but still needs one deeper connection.",
        "subtle_hint": "Add the next step in the chain: cause, change, then result.",
        "follow_up_question": f"What changes next in {topic}, and why does that change happen?",
        "correct_points": ["Some source vocabulary"],
        "missing_points": ["The why/how connection"],
        "depth_score": max(depth_score, 45),
        "misconception_detected": "The explanation is still missing a clear why/how connection."
    }

def get_peckish_reaction(
    topic: str,
    source_notes: str,
    conversation_history: list[dict],
    student_explanation: str
) -> dict:
    """
    Acts as Peckish the flamingo, analyzing a student explanation against source notes.
    Decides reaction (SATISFIED, CURIOUS, CONFUSED) and provides a short character reaction.
    
    Args:
        topic: The specific concept topic being taught.
        source_notes: The ground truth study notes.
        conversation_history: List of prior turns: [{'student_text': str, 'peckish_response': str}, ...]
        student_explanation: What the student just said/typed.
        
    Returns:
        A dictionary matching the PeckishReaction schema.
    """
    system_instruction = (
        "You are Peckish, a curious young flamingo being taught a topic by a student. "
        "You are NOT an expert - you're an eager learner hearing this for the first time. "
        "Genuinely try to understand, and push back gently when something is unclear, incomplete, "
        "or doesn't quite make sense - the way a smart, curious peer would.\n\n"
        "Your task:\n"
        "1. Privately assess the explanation against SOURCE_NOTES for accuracy, completeness, and whether it explains WHY/HOW, not just WHAT.\n"
        "2. Decide one of three reactions:\n"
        "   a. SATISFIED - accurate and reasonably complete for this point\n"
        "   b. CURIOUS - accurate so far, but shallow or missing a why/how - ask a natural follow-up question that pushes one level deeper\n"
        "   c. CONFUSED - inaccurate, contradictory, or not anchored in SOURCE_NOTES - react with genuine confusion and ask for clarification\n"
        "3. Calibrate depth_score carefully. Use 0-34 for mostly wrong/off-topic, 35-59 for partial or shallow, 60-79 for mostly right but missing important detail, and 80-100 for strong understanding.\n"
        "4. Return specific feedback_summary, subtle_hint, follow_up_question, correct_points, and missing_points. Hints should point to the missing area without handing over the full answer.\n"
        "5. Never lecture, never say 'that's wrong,' and never reveal the whole correct answer outright. Stay in character as a peer learner, not a teacher.\n"
        "6. peckish_response should include: what Peckish understood, a subtle hint if needed, and one meaningful next question unless satisfied.\n"
        "7. Keep responses short - 2-4 sentences, natural spoken-language style, since this may be read aloud via text-to-speech."
    )
    
    # Format conversation history
    history_str = ""
    for i, turn in enumerate(conversation_history):
        student_txt = turn.get("student_text", "").strip() or turn.get("student_explanation", "").strip()
        peckish_txt = turn.get("peckish_response", "").strip()
        history_str += f"Turn {i+1}:\nStudent: {student_txt}\nPeckish: {peckish_txt}\n"
        
    if not history_str:
        history_str = "No prior turns in this conversation."
        
    prompt = f"""TOPIC: {topic}
SOURCE_NOTES: {source_notes}
CONVERSATION_HISTORY:
{history_str}
STUDENT_EXPLANATION: {student_explanation}"""

    return _generate_structured_data(
        prompt=prompt,
        schema=PeckishReaction,
        default_factory=lambda: default_peckish_reaction(topic, source_notes, student_explanation),
        system_instruction=system_instruction
    )

# =====================================================================
# 4. generate_fossil
# =====================================================================

def default_fossil_card(topic: str, misconception: str) -> dict:
    return {
        "fossil_name": f"The {topic} Misstep",
        "what_they_said": misconception,
        "the_truth": "Double check the reference materials to align with the core explanation.",
        "flavor_text": "An interesting path taken, preserved for future reflection."
    }

def generate_fossil(topic: str, misconception: str, correct_info: str) -> dict:
    """
    Turns a misconception into a non-judgmental, museum-placard-style fossil card.
    
    Args:
        topic: The topic of study.
        misconception: Description of the student's wrong idea.
        correct_info: The accurate ground truth information.
        
    Returns:
        A dictionary matching the FossilCard schema.
    """
    system_instruction = (
        "You are generating a 'fossil card' for a study app. A student had a gap or "
        "misconception while explaining a topic to a study companion. Turn this into a "
        "short, charming, non-embarrassing artifact card — like a museum placard for "
        "their own mistake, treated with warmth and curiosity, never mockery."
    )
    prompt = f"""TOPIC: {topic}
MISCONCEPTION: {misconception}
CORRECT_INFO: {correct_info}"""

    return _generate_structured_data(
        prompt=prompt,
        schema=FossilCard,
        default_factory=lambda: default_fossil_card(topic, misconception),
        system_instruction=system_instruction
    )

# =====================================================================
# 5. generate_reteach_prompt
# =====================================================================

def default_reteach_prompt(misconception_topic: str) -> dict:
    return {
        "peckish_prompt": f"Oh! I was thinking about {misconception_topic} earlier and got a bit confused again. Can you explain that to me one more time?"
    }

def generate_reteach_prompt(topic: str, misconception_topic: str) -> dict:
    """
    Generates a prompt for a returning session where Peckish asks the student to re-explain a past fossil.
    
    Args:
        topic: The general topic (e.g. 'Photosynthesis').
        misconception_topic: The specific misconception description or short label.
        
    Returns:
        A dictionary matching the ReteachPrompt schema.
    """
    system_instruction = (
        "You are Peckish, a curious flamingo. You previously learned about the topic but "
        "have forgotten some of it since (you're a flamingo, it happens). Ask the student, "
        "in character, to re-explain the misconception topic — reference that you remember "
        "getting a bit confused about it before. 1-2 sentences, playful and curious, "
        "natural spoken style."
    )
    prompt = f"""TOPIC: {topic}
MISCONCEPTION_TOPIC: {misconception_topic}"""

    return _generate_structured_data(
        prompt=prompt,
        schema=ReteachPrompt,
        default_factory=lambda: default_reteach_prompt(misconception_topic),
        system_instruction=system_instruction
    )

# =====================================================================
# 6. generate_revision_resource
# =====================================================================

def default_revision_resource(topic: str, resource_type: str, sen_profile: str) -> dict:
    return {
        "title": f"{topic} {resource_type}",
        "intro": "A simple revision organiser generated from the session notes.",
        "central_idea": topic,
        "central_image_prompt": f"friendly inclusive study illustration for {topic}",
        "cards": [],
        "nodes": [],
        "steps": [],
        "study_steps": ["Review the organiser.", "Teach one section to Peckish.", "Mark any confusing part as a fossil."],
        "sen_profile": sen_profile,
    }

def generate_revision_resource(
    topic: str,
    concepts: list[dict],
    resource_type: Literal["flashcards", "mindmap", "flowchart"],
    sen_profile: str,
    sen_strategy: dict
) -> dict:
    """
    Converts session notes into an SEN-aware revision organiser.
    For mindmaps, Gemini returns image prompts and visual styling for each node.
    """
    system_instruction = (
        "You are designing accessible SEN-aware revision resources for an EdTech app. "
        "Respect neurodiversity: do not diagnose, stereotype, or imply one method works for everyone. "
        "Use the SEN strategy as an adaptation preference. Keep language clear, warm, and age-neutral. "
        "For mindmaps, prioritise concise diagram node labels, full study-note summaries, supported icon words, and varied node colours. The app renders these as connected idea boxes, not picture cards. Supported icons are: arrow, book, brain, chip, compass, gear, info, key, leaf, link, map, spark, sun."
    )
    prompt = f"""TOPIC: {topic}
RESOURCE_TYPE: {resource_type}
SEN_PROFILE: {sen_profile}
SEN_STRATEGY: {sen_strategy}
CONCEPTS: {concepts}

Create exactly the requested resource type:
- flashcards: produce 4-8 cards and 3 study_steps.
- mindmap: produce a central_idea and 4-7 colourful nodes with icon, color, summary, and a brief image_prompt for backwards compatibility. Icon must be one of the supported icon names. Each node summary must be note form but still educational: 2-3 complete study-note points, 8-16 words each, separated by semicolons.
- flowchart: produce 4-8 steps with title, description, checkpoint, and icon.

Make it practical for a student who will then teach Peckish from memory."""

    return _generate_structured_data(
        prompt=prompt,
        schema=RevisionResource,
        default_factory=lambda: default_revision_resource(topic, resource_type, sen_profile),
        system_instruction=system_instruction
    )

# =====================================================================
# 7. transcribe_and_understand_explanation
# =====================================================================

def transcribe_and_understand_explanation(audio_bytes: bytes, mime_type: str) -> str:
    """
    Directly sends audio bytes to Gemini as a multimodal part, returning the transcription.
    
    Args:
        audio_bytes: Raw binary file data of the recording.
        mime_type: The file's MIME type (e.g. 'audio/webm', 'audio/wav', 'audio/mp3').
        
    Returns:
        A string containing the transcribed text, or empty string on failure.
    """
    if not audio_bytes:
        logger.warning("Empty audio_bytes provided to transcription service.")
        return ""
    try:
        client = get_gemini_client()
        logger.info(f"API Audio Request | Model: {GEMINI_MODEL} | MIME: {mime_type} | Size: {len(audio_bytes)} bytes")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                "You are an accurate audio transcriber. Listen to the student's explanation in the audio. "
                "Transcribe what they said clearly. Correct minor stutters or speech repetitions if necessary to make it readable, "
                "but keep their wording. Do not add any introduction or conclusion. Output ONLY the transcribed explanation.",
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type
                )
            ]
        )
        transcription = response.text.strip()
        logger.info(f"Transcription response: {transcription}")
        return transcription
    except Exception as e:
        logger.error(f"Error during audio transcription: {e}")
        return ""

# =====================================================================
# Standalone Test Execution Block
# =====================================================================

if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("PECKISH GEMINI SERVICE STANDALONE TEST RUNNER")
    print("=" * 60)
    
    if not is_configured():
        print("WARNING: Gemini is not configured.")
        print("Set GOOGLE_CLOUD_PROJECT + ADC for Vertex AI, or GEMINI_API_KEY for express/Developer API.")
        print("Default mock fallbacks will be exercised if we continue.")
        print("-" * 60)
        
    topic = "Photosynthesis"
    
    # 1. Test generate_notes
    print("\n--- 1. Testing generate_notes ---")
    notes_res = generate_notes(topic)
    print(f"Result:\n{notes_res}")
    
    # 2. Test extract_concepts_from_notes
    print("\n--- 2. Testing extract_concepts_from_notes ---")
    raw_notes = "Plants gather sunlight using chlorophyll. Chlorophyll captures blue and red wavelengths of light but reflects green light. Water is drawn from roots and carbon dioxide is absorbed through stomata. These are combined using the sunlight's energy to yield glucose and release oxygen."
    extract_res = extract_concepts_from_notes(raw_notes)
    print(f"Result:\n{extract_res}")
    
    # 3. Test get_peckish_reaction (Shallow explanation)
    print("\n--- 3. Testing get_peckish_reaction (Shallow explanation) ---")
    source_notes = (
        "Concept 1: Light capture. Chlorophyll in leaves absorbs red and blue light, reflecting green. This light energy excites electrons.\n"
        "Concept 2: Water splitting. Light energy is used to split H2O, generating oxygen gas and releasing protons/electrons.\n"
        "Concept 3: Carbon fixation. Stomata take in CO2, which is converted to glucose using energy from ATP and NADPH."
    )
    explanation = "Plants take in sunlight through leaves and convert it to glucose."
    reaction_res = get_peckish_reaction(topic, source_notes, [], explanation)
    print(f"Result:\n{reaction_res}")

    # 4. Test get_peckish_reaction (Misconception explanation)
    print("\n--- 3.1. Testing get_peckish_reaction (Misconception explanation) ---")
    wrong_explanation = "Plants absorb water, and then they convert the water directly into oxygen using green light."
    reaction_wrong_res = get_peckish_reaction(topic, source_notes, [], wrong_explanation)
    print(f"Result:\n{reaction_wrong_res}")
    
    # 5. Test generate_fossil
    print("\n--- 4. Testing generate_fossil ---")
    fossil_res = generate_fossil(
        topic=topic,
        misconception="Plants convert water directly into oxygen using green light.",
        correct_info="Light energy splits water to release oxygen, but chlorophyll reflects green light (it absorbs red and blue light to power the reaction)."
    )
    print(f"Result:\n{fossil_res}")
    
    # 6. Test generate_reteach_prompt
    print("\n--- 5. Testing generate_reteach_prompt ---")
    reteach_res = generate_reteach_prompt(topic, "The Green Light Water Splitting Myth")
    print(f"Result:\n{reteach_res}")
    
    # 7. Test transcribe_and_understand_explanation
    print("\n--- 6. Testing transcribe_and_understand_explanation ---")
    # Using small empty bytes for demonstration/safeness check (should log warning & return empty or err)
    audio_res = transcribe_and_understand_explanation(b"", "audio/wav")
    print(f"Result (Expected Empty): '{audio_res}'")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)
