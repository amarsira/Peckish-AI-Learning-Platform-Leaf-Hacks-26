SEN_PLANS = {
    "none": {
        "label": "Default",
        "method": "Teach-to-learn recall",
        "recommended_resource": "flashcards",
        "summary": "Use the standard Peckish loop: read, recall, teach, and revisit fossils.",
        "session_focus": [
            "Retrieval practice through teaching out loud or typing.",
            "Gentle follow-up questions when the explanation is shallow.",
            "Fossil cards for misconceptions to revisit later.",
        ],
    },
    "dyslexia": {
        "label": "Dyslexia",
        "method": "Structured, multisensory chunks",
        "recommended_resource": "flashcards",
        "summary": "Peckish breaks notes into short, explicit cards with keywords, plain wording, and voice-friendly recall.",
        "session_focus": [
            "Short flashcards with one idea per card.",
            "Key vocabulary is separated from explanation text.",
            "Reading mode and speech support stay easy to reach.",
        ],
    },
    "autism": {
        "label": "Autism",
        "method": "Predictable visual sequence",
        "recommended_resource": "flowchart",
        "summary": "Peckish shows the learning path as precise, ordered steps with less ambiguity and a clear finish point.",
        "session_focus": [
            "Clear sequence before open-ended teaching.",
            "Direct language and predictable transitions.",
            "Flowcharts make cause, rule, and outcome relationships explicit.",
        ],
    },
    "adhd": {
        "label": "ADHD",
        "method": "Short active sprints",
        "recommended_resource": "mindmap",
        "summary": "Peckish turns the topic into a visual map and short tasks so attention has clear targets.",
        "session_focus": [
            "Small chunks with visible progress.",
            "Colourful mindmaps for quick scanning and re-entry.",
            "Short prompts, choices, and movement-friendly pacing.",
        ],
    },
    "dyscalculia": {
        "label": "Dyscalculia",
        "method": "Concrete step-by-step structure",
        "recommended_resource": "flowchart",
        "summary": "Peckish turns abstract rules into concrete sequences and named checkpoints.",
        "session_focus": [
            "Flowcharts expose each step and decision point.",
            "Examples connect symbols or rules to meaning.",
            "The student teaches the why before memorising a procedure.",
        ],
    },
    "dyspraxia": {
        "label": "Dyspraxia / DCD",
        "method": "Low-friction verbal planning",
        "recommended_resource": "flashcards",
        "summary": "Peckish reduces writing load with voice-friendly cards and clear task steps.",
        "session_focus": [
            "Typed and spoken responses are both supported.",
            "Cards reduce copying and layout demands.",
            "Tasks are broken into manageable actions.",
        ],
    },
}


def get_sen_plan(sen_profile: str) -> dict:
    return SEN_PLANS.get(sen_profile, SEN_PLANS["none"])


def resource_label(resource_type: str) -> str:
    return {
        "flashcards": "Flashcards",
        "mindmap": "Mind map",
        "flowchart": "Flow chart",
    }.get(resource_type, "Revision organiser")
