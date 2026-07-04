import os
import re
from html import escape
from typing import Iterable
from urllib.parse import quote

try:
    from services import gemini_service
except Exception:
    gemini_service = None


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "why",
    "with",
}


def _clean_hex_colour(value: str, fallback: str = "#247d76") -> str:
    value = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    return fallback


def _short_text(value: str, max_length: int = 32) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "."


def _initials(label: str, fallback: str = "AI") -> str:
    words = re.findall(r"[A-Za-z0-9]+", str(label or ""))
    if not words:
        return fallback
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(word[0] for word in words[:2]).upper()


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def _mindmap_image_svg(title: str, prompt: str, colour: str, icon: str) -> str:
    colour = _clean_hex_colour(colour)
    title = escape(_short_text(title, 34))
    prompt = escape(_short_text(prompt, 58))
    icon_text = escape(_initials(icon or title))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" rx="36" fill="#fff8f2"/>
  <rect x="18" y="18" width="604" height="324" rx="32" fill="{colour}" opacity="0.16"/>
  <circle cx="122" cy="92" r="54" fill="{colour}" opacity="0.95"/>
  <circle cx="530" cy="78" r="34" fill="#ffd166" opacity="0.88"/>
  <circle cx="500" cy="268" r="62" fill="#d9f3ec" opacity="0.96"/>
  <path d="M80 250 C170 155 270 310 392 184 S550 152 590 236" fill="none" stroke="{colour}" stroke-width="16" stroke-linecap="round" opacity="0.32"/>
  <rect x="210" y="78" width="220" height="142" rx="28" fill="#ffffff" opacity="0.94"/>
  <circle cx="320" cy="128" r="38" fill="{colour}" opacity="0.98"/>
  <text x="320" y="141" text-anchor="middle" font-family="Verdana,Arial,sans-serif" font-size="30" font-weight="700" fill="#ffffff">{icon_text}</text>
  <text x="320" y="184" text-anchor="middle" font-family="Verdana,Arial,sans-serif" font-size="24" font-weight="700" fill="#2d2636">{title}</text>
  <text x="320" y="270" text-anchor="middle" font-family="Verdana,Arial,sans-serif" font-size="17" font-weight="600" fill="#665f73">{prompt}</text>
</svg>"""


def ensure_revision_images(resource: dict) -> dict:
    if not isinstance(resource, dict) or not resource.get("nodes"):
        return resource

    resource = dict(resource)
    central_colour = "#ef5d83"
    first_node = resource.get("nodes", [{}])[0] if resource.get("nodes") else {}
    if isinstance(first_node, dict):
        central_colour = _clean_hex_colour(first_node.get("color"), central_colour)

    if not resource.get("central_image_data_uri"):
        resource["central_image_data_uri"] = _svg_data_uri(
            _mindmap_image_svg(
                resource.get("central_idea") or resource.get("title") or "Mind map",
                resource.get("central_image_prompt") or "Inclusive study visual",
                central_colour,
                resource.get("central_idea") or "AI",
            )
        )

    enriched_nodes = []
    for node in resource.get("nodes", []):
        if not isinstance(node, dict):
            continue
        enriched = dict(node)
        if not enriched.get("image_data_uri"):
            enriched["image_data_uri"] = _svg_data_uri(
                _mindmap_image_svg(
                    enriched.get("label") or "Mind map node",
                    enriched.get("image_prompt") or enriched.get("summary") or "Study visual",
                    enriched.get("color") or "#247d76",
                    enriched.get("icon") or enriched.get("label") or "AI",
                )
            )
        enriched_nodes.append(enriched)
    resource["nodes"] = enriched_nodes
    return resource


def _gemini_enabled() -> bool:
    if not gemini_service:
        return False
    return gemini_service.is_configured()


def _safe_concepts(payload: dict) -> list[dict]:
    concepts = payload.get("concepts") if isinstance(payload, dict) else None
    if not concepts:
        return []
    cleaned = []
    for item in concepts:
        title = str(item.get("title", "Untitled concept")).strip()
        notes = str(item.get("notes") or item.get("source_notes") or "").strip()
        if title and notes:
            cleaned.append({"title": title, "notes": notes})
    return cleaned


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower())
        if token not in STOPWORDS
    }


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if paragraphs:
        return paragraphs
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _fallback_generated_concepts(topic: str) -> dict:
    topic = topic.strip() or "the topic"
    concepts = [
        {
            "title": f"{topic}: Big picture",
            "notes": (
                f"Start by naming what {topic} is, what problem it helps explain, "
                "and where a learner would notice it in real examples. A strong "
                "explanation connects the definition to a purpose instead of "
                "leaving it as a memorized phrase."
            ),
        },
        {
            "title": f"{topic}: Key mechanism",
            "notes": (
                f"Focus on the main process behind {topic}. Explain the steps in "
                "order, what changes at each step, and why one step leads to the "
                "next. This is where a student should practice saying how and why."
            ),
        },
        {
            "title": f"{topic}: Evidence and examples",
            "notes": (
                f"Use one concrete example of {topic} and point out the evidence "
                "that shows the idea is working. Examples help reveal whether the "
                "concept is understood or only repeated."
            ),
        },
        {
            "title": f"{topic}: Common mix-ups",
            "notes": (
                f"Look for ideas that are easy to confuse with {topic}. A useful "
                "teaching explanation names the difference clearly and checks the "
                "cause, effect, and vocabulary."
            ),
        },
    ]
    return {"concepts": concepts}


def _fallback_extract_concepts(raw_text: str) -> dict:
    parts = _split_paragraphs(raw_text)
    if not parts:
        return _fallback_generated_concepts("Imported notes")

    target_count = min(max(len(parts), 1), 6)
    if len(parts) > 6:
        chunk_size = max(1, len(parts) // 6)
        chunks = [
            " ".join(parts[index : index + chunk_size])
            for index in range(0, len(parts), chunk_size)
        ][:6]
    else:
        chunks = parts[:target_count]

    concepts = []
    for index, chunk in enumerate(chunks, start=1):
        first_line = chunk.splitlines()[0].strip()
        title = first_line[:60].rstrip(".:;") or f"Imported notes {index}"
        if len(title.split()) > 8:
            title = f"Imported notes {index}"
        concepts.append({"title": title, "notes": chunk})
    return {"concepts": concepts}


def _call_or_fallback(function_name: str, fallback, *args, **kwargs) -> dict:
    if _gemini_enabled():
        try:
            result = getattr(gemini_service, function_name)(*args, **kwargs)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return fallback(*args, **kwargs)


def generate_notes(topic: str) -> dict:
    return _call_or_fallback("generate_notes", _fallback_generated_concepts, topic)


def extract_concepts_from_notes(raw_text: str) -> dict:
    return _call_or_fallback("extract_concepts_from_notes", _fallback_extract_concepts, raw_text)


def get_clean_concepts(payload: dict, fallback_topic: str = "Study topic") -> list[dict]:
    concepts = _safe_concepts(payload)
    if concepts:
        return concepts
    return _safe_concepts(_fallback_generated_concepts(fallback_topic))


def _history_text(conversation_history: Iterable[dict]) -> str:
    fragments = []
    for turn in conversation_history:
        fragments.append(turn.get("student_text", ""))
        fragments.append(turn.get("peckish_response", ""))
    return " ".join(fragments)


def _fallback_reaction(
    topic: str,
    source_notes: str,
    conversation_history: list[dict],
    student_explanation: str,
) -> dict:
    source_terms = _tokens(source_notes)
    student_terms = _tokens(student_explanation)
    overlap = len(source_terms & student_terms)
    coverage = overlap / max(len(source_terms), 1)
    word_count = len(student_explanation.split())
    has_depth_words = any(
        marker in student_explanation.lower()
        for marker in ("because", "so that", "therefore", "which means", "this causes")
    )
    prior_text = _history_text(conversation_history)
    repeated = bool(prior_text and student_explanation.strip().lower() in prior_text.lower())

    depth_score = min(100, int((coverage * 85) + min(word_count, 80) * 0.55))
    if has_depth_words:
        depth_score = min(100, depth_score + 12)
    if repeated:
        depth_score = max(0, depth_score - 12)

    if word_count < 18:
        return {
            "reaction_type": "CURIOUS",
            "peckish_response": (
                "I think I caught the outline, but I am still pecking for the why. "
                "Can you explain what causes that part to happen?"
            ),
            "feedback_summary": "Your explanation has a starting outline but not enough cause-and-effect yet.",
            "subtle_hint": "Name the step or force that makes the main change happen.",
            "follow_up_question": f"What causes the main part of {topic} to happen?",
            "correct_points": [],
            "missing_points": ["Cause or mechanism", "Why the idea matters"],
            "depth_score": max(depth_score, 35),
            "misconception_detected": "The explanation is too brief to show the cause or mechanism.",
        }

    if coverage < 0.08:
        return {
            "reaction_type": "CONFUSED",
            "peckish_response": (
                f"Wait, I may have lost the trail on {topic}. Which part connects "
                "back to the notes we looked at?"
            ),
            "feedback_summary": "Your explanation does not clearly connect back to the source notes yet.",
            "subtle_hint": "Use one exact key term from the notes before adding your own wording.",
            "follow_up_question": f"Which key idea from the notes should Peckish hold onto for {topic}?",
            "correct_points": [],
            "missing_points": ["Connection to the source notes"],
            "depth_score": max(10, min(depth_score, 42)),
            "misconception_detected": "The explanation does not connect clearly to the source notes.",
        }

    if depth_score >= 70 and has_depth_words:
        return {
            "reaction_type": "SATISFIED",
            "peckish_response": (
                "Oh, that clicks now. You connected the idea to the reason it works, "
                "so I can carry it forward."
            ),
            "feedback_summary": "Your explanation connects the main idea to why it works.",
            "subtle_hint": "",
            "follow_up_question": "",
            "correct_points": ["Main idea", "Why/how connection"],
            "missing_points": [],
            "depth_score": depth_score,
            "misconception_detected": None,
        }

    return {
        "reaction_type": "CURIOUS",
        "peckish_response": (
            "I am close to getting it. Could you add one more layer about why that "
            "happens or what changes next?"
        ),
        "feedback_summary": "Your explanation is partly right but still needs one deeper connection.",
        "subtle_hint": "Add the next link in the chain: cause, change, then result.",
        "follow_up_question": f"What changes next in {topic}, and why does that change happen?",
        "correct_points": ["Some source vocabulary"],
        "missing_points": ["The why/how connection"],
        "depth_score": max(depth_score, 45),
        "misconception_detected": "The explanation is still missing a clear why/how connection.",
    }


def get_peckish_reaction(
    topic: str,
    source_notes: str,
    conversation_history: list[dict],
    student_text: str,
) -> dict:
    if _gemini_enabled():
        try:
            return gemini_service.get_peckish_reaction(
                topic,
                source_notes,
                conversation_history,
                student_text,
            )
        except Exception:
            pass
    return _fallback_reaction(topic, source_notes, conversation_history, student_text)


def _fallback_fossil(topic: str, misconception: str, correct_info: str) -> dict:
    fossil_topic = re.sub(r"[^a-zA-Z0-9 ]", "", topic).strip() or "Concept"
    short_topic = " ".join(fossil_topic.split()[:2])
    return {
        "fossil_name": f"{short_topic} Trace",
        "what_they_said": misconception,
        "the_truth": correct_info[:240] if correct_info else "Review the source notes and rebuild the explanation from the key cause.",
        "flavor_text": "A preserved learning footprint from a path that almost reached the nest.",
    }


def generate_fossil(topic: str, misconception: str, correct_info: str) -> dict:
    return _call_or_fallback(
        "generate_fossil",
        _fallback_fossil,
        topic,
        misconception,
        correct_info,
    )


def _fallback_reteach_prompt(topic: str, misconception_topic: str) -> dict:
    return {
        "peckish_prompt": (
            f"I was thinking about {topic} again, and the part about "
            f"{misconception_topic} got fuzzy. Can you teach it to me once more?"
        )
    }


def generate_reteach_prompt(topic: str, misconception_topic: str) -> dict:
    return _call_or_fallback(
        "generate_reteach_prompt",
        _fallback_reteach_prompt,
        topic,
        misconception_topic,
    )


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    if not _gemini_enabled() or not audio_bytes:
        return ""
    try:
        return gemini_service.transcribe_and_understand_explanation(audio_bytes, mime_type)
    except Exception:
        return ""


def _concept_payload(concepts) -> list[dict]:
    return [
        {
            "title": concept.title,
            "notes": concept.source_notes,
        }
        for concept in concepts
    ]


def _fallback_flashcards(topic: str, concepts: list[dict], sen_profile: str) -> dict:
    cards = []
    for concept in concepts:
        notes = concept["notes"]
        first_sentence = re.split(r"(?<=[.!?])\s+", notes.strip())[0] if notes.strip() else ""
        cards.append(
            {
                "front": concept["title"],
                "back": first_sentence or notes[:180],
                "cue": "Teach the idea in one sentence, then add why it matters.",
                "image_prompt": f"simple friendly study icon for {concept['title']}",
            }
        )
    return {
        "title": f"{topic} flashcards",
        "intro": "One idea per card, designed for quick recall before teaching Peckish.",
        "cards": cards[:8],
        "study_steps": [
            "Read the front.",
            "Answer from memory.",
            "Flip, compare, then teach Peckish the missing detail.",
        ],
        "sen_profile": sen_profile,
    }


def _fallback_mindmap(topic: str, concepts: list[dict], sen_profile: str) -> dict:
    palette = ["#ef5d83", "#247d76", "#8173c9", "#ff8a5b", "#2d9cdb", "#7a5634"]
    icons = ["sun", "leaf", "spark", "compass", "key", "link"]
    nodes = []
    for index, concept in enumerate(concepts[:6]):
        summary_parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", concept["notes"].strip())
            if part.strip()
        ][:3]
        summary = "; ".join(part.rstrip(".!?") for part in summary_parts)
        nodes.append(
            {
                "label": concept["title"],
                "summary": summary[:280],
                "icon": icons[index % len(icons)],
                "color": palette[index % len(palette)],
                "image_prompt": f"colourful friendly illustration representing {concept['title']}",
            }
        )
    return {
        "title": f"{topic} mind map",
        "central_idea": topic,
        "central_image_prompt": f"warm inclusive educational illustration for {topic}",
        "nodes": nodes,
        "sen_profile": sen_profile,
    }


def _fallback_flowchart(topic: str, concepts: list[dict], sen_profile: str) -> dict:
    steps = []
    for index, concept in enumerate(concepts[:8], start=1):
        summary = re.split(r"(?<=[.!?])\s+", concept["notes"].strip())[0]
        steps.append(
            {
                "title": concept["title"],
                "description": summary[:220],
                "checkpoint": f"Can I explain step {index} without looking?",
                "icon": str(index),
            }
        )
    return {
        "title": f"{topic} flow chart",
        "intro": "A predictable route through the topic, from first idea to final check.",
        "steps": steps,
        "sen_profile": sen_profile,
    }


def _fallback_revision_resource(topic: str, concepts: list[dict], resource_type: str, sen_profile: str) -> dict:
    if resource_type == "mindmap":
        return _fallback_mindmap(topic, concepts, sen_profile)
    if resource_type == "flowchart":
        return _fallback_flowchart(topic, concepts, sen_profile)
    return _fallback_flashcards(topic, concepts, sen_profile)


def _resource_has_content(resource: dict, resource_type: str) -> bool:
    if resource_type == "mindmap":
        return bool(resource.get("nodes"))
    if resource_type == "flowchart":
        return bool(resource.get("steps"))
    return bool(resource.get("cards"))


def generate_revision_resource(session, resource_type: str, sen_profile: str, sen_plan: dict) -> dict:
    concepts = _concept_payload(session.concepts.all())
    if _gemini_enabled():
        try:
            result = gemini_service.generate_revision_resource(
                topic=session.topic_title,
                concepts=concepts,
                resource_type=resource_type,
                sen_profile=sen_profile,
                sen_strategy=sen_plan,
            )
            if isinstance(result, dict) and _resource_has_content(result, resource_type):
                return result
        except Exception:
            pass
    result = _fallback_revision_resource(session.topic_title, concepts, resource_type, sen_profile)
    return result
