from io import BytesIO
from functools import wraps
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
import requests as http_requests

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from . import ai
from .models import Concept, Fossil, RevisionResource, Session, TeachingTurn, UserProfile
from .sen import SEN_PLANS, get_sen_plan, resource_label


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
logger = logging.getLogger(__name__)
XP_PER_LEVEL = 120
FULL_UNDERSTANDING_DEPTH = getattr(settings, "UNDERSTANDING_DEPTH_THRESHOLD", 72)


def _extract_upload_text(uploaded_file) -> tuple[str, str | None]:
    if not uploaded_file:
        return "", None

    filename = uploaded_file.name.lower()
    data = uploaded_file.read()
    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip(), None
        except Exception:
            return "", "I could not read that PDF. Paste the notes text instead for this demo."

    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding).strip(), None
        except UnicodeDecodeError:
            continue
    return "", "I could not read that file. Try a text file, PDF, or pasted notes."


def _display_name(user) -> str:
    return user.get_full_name() or user.first_name or user.email or user.username


def _google_redirect_uri(request) -> str:
    return settings.GOOGLE_REDIRECT_URI or request.build_absolute_uri(reverse("core:google_callback"))


def _google_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def _get_learning_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def profile_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        profile = _get_learning_profile(request.user)
        if not profile.setup_complete:
            return redirect("core:profile_setup")
        request.learning_profile = profile
        request.sen_plan = get_sen_plan(profile.sen_profile)
        return view_func(request, *args, **kwargs)

    return wrapped


def _create_session(user, topic_title: str, source_type: str, raw_notes: str, concepts: list[dict]) -> Session:
    session = Session.objects.create(
        user=user,
        topic_title=topic_title,
        source_type=source_type,
        raw_notes=raw_notes,
    )
    for index, concept in enumerate(concepts, start=1):
        Concept.objects.create(
            session=session,
            title=concept["title"][:255],
            source_notes=concept["notes"],
            order=index,
        )
    return session


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value) -> str:
    return str(value or "").strip()


def _clean_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:3]
    if value:
        return [str(value).strip()]
    return []


def _level_from_xp(xp: int) -> int:
    return max(1, xp // XP_PER_LEVEL + 1)


def _user_total_xp(user) -> int:
    if not user.is_authenticated:
        return 0
    return Session.objects.filter(user=user).aggregate(total=Sum("pet_xp")).get("total") or 0


def _xp_for_turn(reaction_type: str, depth_score: int) -> int:
    if reaction_type == TeachingTurn.SATISFIED:
        return 28 + min(22, max(depth_score - 60, 0) // 2)
    if reaction_type == TeachingTurn.CURIOUS:
        return 8 + min(14, max(depth_score, 0) // 8)
    return 0


def _award_turn_xp(request, session: Session, turn: TeachingTurn) -> None:
    xp_awarded = _xp_for_turn(turn.reaction_type, turn.depth_score)
    if xp_awarded <= 0:
        return

    before_global_level = _level_from_xp(_user_total_xp(request.user))
    turn.xp_awarded = xp_awarded
    turn.save(update_fields=["xp_awarded"])

    session.pet_xp += xp_awarded
    session.pet_level = _level_from_xp(session.pet_xp)
    session.save(update_fields=["pet_xp", "pet_level"])

    after_global_xp = _user_total_xp(request.user)
    after_global_level = _level_from_xp(after_global_xp)
    if after_global_level > before_global_level:
        request.session["level_up_payload"] = {
            "level": after_global_level,
            "total_xp": after_global_xp,
        }


def _reaction_type(payload: dict) -> str:
    reaction_type = str(payload.get("reaction_type") or TeachingTurn.CURIOUS).upper()
    valid_types = {choice[0] for choice in TeachingTurn.REACTION_CHOICES}
    return reaction_type if reaction_type in valid_types else TeachingTurn.CURIOUS


def _turn_from_reaction(concept: Concept, student_text: str, reaction: dict) -> TeachingTurn:
    return TeachingTurn.objects.create(
        concept=concept,
        turn_number=concept.turns.count() + 1,
        student_text=student_text,
        reaction_type=_reaction_type(reaction),
        peckish_response=_clean_text(reaction.get("peckish_response")) or "Can you say that another way?",
        feedback_summary=_clean_text(reaction.get("feedback_summary")),
        subtle_hint=_clean_text(reaction.get("subtle_hint")),
        follow_up_question=_clean_text(reaction.get("follow_up_question")),
        missing_points=_clean_list(reaction.get("missing_points")),
        correct_points=_clean_list(reaction.get("correct_points")),
        depth_score=max(0, min(100, _safe_int(reaction.get("depth_score"), 0))),
    )


def _turn_shows_full_understanding(turn: TeachingTurn | None) -> bool:
    if not turn:
        return False
    return (
        turn.reaction_type == TeachingTurn.SATISFIED
        and turn.depth_score >= FULL_UNDERSTANDING_DEPTH
    )


def _attempt_snapshots(concept: Concept) -> list[dict]:
    attempts = []
    for turn in concept.turns.order_by("turn_number"):
        attempts.append(
            {
                "turn_number": turn.turn_number,
                "student_text": turn.student_text,
                "peckish_response": turn.peckish_response,
                "feedback_summary": turn.feedback_summary,
                "subtle_hint": turn.subtle_hint,
                "follow_up_question": turn.follow_up_question,
                "reaction_type": turn.reaction_type,
                "depth_score": turn.depth_score,
                "xp_awarded": turn.xp_awarded,
                "created_at": turn.created_at.isoformat() if turn.created_at else "",
            }
        )
    return attempts


def _fossil_gap_from_reaction(reaction: dict, concept: Concept) -> str:
    misconception = _clean_text(reaction.get("misconception_detected"))
    if misconception:
        return misconception
    missing_points = _clean_list(reaction.get("missing_points"))
    if missing_points:
        return "Missing after three attempts: " + "; ".join(missing_points)
    return (
        f"After three attempts, Peckish still needed a clearer explanation of "
        f"the why/how behind {concept.title}."
    )


def _store_fossil_if_needed(concept: Concept, turn: TeachingTurn, reaction: dict) -> None:
    if turn.turn_number < settings.MAX_FOLLOWUPS_PER_CONCEPT:
        return
    if _turn_shows_full_understanding(turn):
        return

    misconception = _fossil_gap_from_reaction(reaction, concept)
    attempts = _attempt_snapshots(concept)
    fossil_payload = ai.generate_fossil(
        concept.title,
        misconception,
        concept.source_notes,
    )
    existing_fossil = concept.fossils.filter(re_taught_successfully=False).first()
    if existing_fossil:
        existing_fossil.what_they_said = fossil_payload.get("what_they_said", misconception)
        existing_fossil.the_truth = fossil_payload.get("the_truth", concept.source_notes[:240])
        existing_fossil.flavor_text = fossil_payload.get(
            "flavor_text",
            "A preserved learning footprint from today's explanation.",
        )
        existing_fossil.source_notes_snapshot = concept.source_notes
        existing_fossil.student_attempts = attempts
        existing_fossil.save(
            update_fields=[
                "what_they_said",
                "the_truth",
                "flavor_text",
                "source_notes_snapshot",
                "student_attempts",
            ]
        )
        return

    Fossil.objects.create(
        concept=concept,
        fossil_name=fossil_payload.get("fossil_name", "Learning Trace")[:100],
        what_they_said=fossil_payload.get("what_they_said", misconception),
        the_truth=fossil_payload.get("the_truth", concept.source_notes[:240]),
        flavor_text=fossil_payload.get(
            "flavor_text",
            "A preserved learning footprint from today's explanation.",
        ),
        source_notes_snapshot=concept.source_notes,
        student_attempts=attempts,
    )


def _concept_is_complete(concept: Concept) -> bool:
    latest_turn = concept.turns.order_by("-turn_number").first()
    if not latest_turn:
        return False
    return (
        _turn_shows_full_understanding(latest_turn)
        or concept.turns.count() >= settings.MAX_FOLLOWUPS_PER_CONCEPT
    )


def _next_concept(session: Session, concept: Concept | None = None) -> Concept | None:
    concepts = list(session.concepts.all())
    if concept is None:
        return concepts[0] if concepts else None

    for candidate in concepts:
        if candidate.order > concept.order:
            return candidate
    return None


def _session_progress(session: Session) -> dict:
    concepts = list(session.concepts.prefetch_related("turns"))
    completed = sum(1 for concept in concepts if _concept_is_complete(concept))
    total = len(concepts)
    percent = int((completed / total) * 100) if total else 0
    return {"completed": completed, "total": total, "percent": percent}


def login_page(request):
    if request.user.is_authenticated:
        if not _get_learning_profile(request.user).setup_complete:
            return redirect("core:profile_setup")
        return redirect("core:home")
    return render(
        request,
        "core/login.html",
        {
            "google_configured": _google_configured(),
            "google_redirect_uri": _google_redirect_uri(request),
        },
    )


def google_login(request):
    if not _google_configured():
        messages.error(request, "Google login is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
        return redirect("core:login")

    # OAuth state must survive the Google round trip. Starting with a clean
    # session prevents old dev cookies signed with a previous SECRET_KEY from
    # breaking the callback.
    request.session.flush()
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    next_url = request.GET.get("next") or request.POST.get("next") or settings.LOGIN_REDIRECT_URL
    request.session["login_next_url"] = next_url if next_url.startswith("/") else settings.LOGIN_REDIRECT_URL

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


def google_callback(request):
    expected_state = request.session.pop("google_oauth_state", "")
    returned_state = request.GET.get("state", "")
    if not expected_state or returned_state != expected_state:
        logger.warning(
            "Google OAuth state mismatch. expected_present=%s returned_present=%s",
            bool(expected_state),
            bool(returned_state),
        )
        messages.error(request, "Google sign-in expired. Please try again.")
        return redirect("core:login")

    if request.GET.get("error"):
        messages.error(request, "Google sign-in was cancelled.")
        return redirect("core:login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Google did not return a sign-in code.")
        return redirect("core:login")

    try:
        token_response = http_requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _google_redirect_uri(request),
                "grant_type": "authorization_code",
            },
            timeout=12,
        )
        if not token_response.ok:
            logger.warning(
                "Google token exchange failed: status=%s body=%s",
                token_response.status_code,
                token_response.text[:500],
            )
            messages.error(
                request,
                "Google rejected the OAuth callback. Check GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI.",
            )
            return redirect("core:login")
        token_payload = token_response.json()
        google_user = id_token.verify_oauth2_token(
            token_payload["id_token"],
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=30,
        )
    except Exception as exc:
        logger.exception("Google sign-in failed during callback: %s", exc)
        messages.error(request, f"Google sign-in failed: {exc}")
        return redirect("core:login")

    if not google_user.get("email_verified"):
        messages.error(request, "Please use a Google account with a verified email address.")
        return redirect("core:login")

    email = google_user.get("email", "").lower()
    if not email:
        messages.error(request, "Google did not return an email address.")
        return redirect("core:login")

    User = get_user_model()
    username = f"google_{google_user.get('sub', secrets.token_hex(8))}"[:150]
    user = User.objects.filter(email=email).first()
    created = user is None
    if created:
        user = User.objects.create(
            email=email,
            username=username,
            first_name=google_user.get("given_name", "")[:150],
            last_name=google_user.get("family_name", "")[:150],
        )
    updates = []
    if created:
        user.set_unusable_password()
        updates.append("password")
    if user.username != username and user.username.startswith("google_"):
        user.username = username
        updates.append("username")
    if google_user.get("given_name") and user.first_name != google_user.get("given_name"):
        user.first_name = google_user.get("given_name", "")[:150]
        updates.append("first_name")
    if google_user.get("family_name") and user.last_name != google_user.get("family_name"):
        user.last_name = google_user.get("family_name", "")[:150]
        updates.append("last_name")
    if updates:
        user.save(update_fields=updates)

    login(request, user)
    profile = _get_learning_profile(user)
    if not profile.setup_complete:
        return redirect("core:profile_setup")
    return redirect(request.session.pop("login_next_url", settings.LOGIN_REDIRECT_URL))


@require_http_methods(["POST"])
def logout_user(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


@login_required
def profile_setup(request):
    profile = _get_learning_profile(request.user)
    if request.method == "POST":
        selected_sen = request.POST.get("sen_profile", UserProfile.SEN_NONE)
        valid_choices = {choice[0] for choice in UserProfile.SEN_CHOICES}
        if selected_sen not in valid_choices:
            messages.error(request, "Choose the option that fits you best.")
            return redirect("core:profile_setup")
        profile.sen_profile = selected_sen
        profile.setup_complete = True
        profile.save(update_fields=["sen_profile", "setup_complete", "updated_at"])
        messages.success(request, "Your learning profile is ready.")
        return redirect("core:home")

    return render(
        request,
        "core/profile_setup.html",
        {
            "profile": profile,
            "sen_options": [
                {
                    "value": value,
                    "label": label,
                    "plan": get_sen_plan(value),
                }
                for value, label in UserProfile.SEN_CHOICES
            ],
        },
    )


@login_required
@profile_required
def profile(request):
    profile_obj = request.learning_profile
    sessions = (
        Session.objects.filter(user=request.user)
        .prefetch_related("concepts__turns", "concepts__fossils")
        .order_by("-created_at")
    )
    fossils = Fossil.objects.filter(
        concept__session__user=request.user,
        re_taught_successfully=False,
    ).select_related("concept", "concept__session")
    total_concepts = sum(session.concepts.count() for session in sessions)
    completed_concepts = sum(
        1
        for session in sessions
        for concept in session.concepts.all()
        if _concept_is_complete(concept)
    )
    return render(
        request,
        "core/profile.html",
        {
            "display_name": _display_name(request.user),
            "learning_profile": profile_obj,
            "sen_plan": request.sen_plan,
            "sessions": sessions,
            "open_fossils": fossils,
            "total_concepts": total_concepts,
            "completed_concepts": completed_concepts,
        },
    )


@login_required
@profile_required
def home(request):
    profile_obj = request.learning_profile
    sen_plan = request.sen_plan
    unresolved_fossils = Fossil.objects.filter(
        concept__session__user=request.user,
        re_taught_successfully=False,
    ).select_related("concept", "concept__session")[:2]
    recent_sessions = (
        Session.objects.filter(user=request.user)
        .prefetch_related("concepts__turns")
        .order_by("-created_at")[:3]
    )

    if request.method == "POST":
        source_type = request.POST.get("source_type", Session.SOURCE_GENERATED)
        topic_title = request.POST.get("topic_title", "").strip()

        if source_type == Session.SOURCE_GENERATED:
            if not topic_title:
                messages.error(request, "Add a topic so Peckish knows what to study.")
                return redirect("core:home")
            payload = ai.generate_notes(topic_title)
            concepts = ai.get_clean_concepts(payload, topic_title)
            raw_notes = "\n\n".join(
                f"{concept['title']}\n{concept['notes']}" for concept in concepts
            )
        else:
            typed_notes = request.POST.get("raw_notes", "").strip()
            uploaded_text, upload_error = _extract_upload_text(request.FILES.get("notes_file"))
            if upload_error:
                messages.error(request, upload_error)
                return redirect("core:home")
            raw_notes = "\n\n".join(part for part in (typed_notes, uploaded_text) if part)
            if not raw_notes:
                messages.error(request, "Paste notes or upload a readable file first.")
                return redirect("core:home")
            topic_title = topic_title or "Imported notes"
            payload = ai.extract_concepts_from_notes(raw_notes)
            concepts = ai.get_clean_concepts(payload, topic_title)

        session = _create_session(request.user, topic_title, source_type, raw_notes, concepts)
        request.session["last_session_id"] = session.id
        return redirect("core:read", session_id=session.id)

    return render(
        request,
        "core/home.html",
        {
            "unresolved_fossils": unresolved_fossils,
            "recent_sessions": recent_sessions,
            "learning_profile": profile_obj,
            "sen_plan": sen_plan,
            "recommended_resource": sen_plan["recommended_resource"],
            "recommended_resource_label": resource_label(sen_plan["recommended_resource"]),
        },
    )


@login_required
@profile_required
def read_session(request, session_id: int):
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    concepts = session.concepts.prefetch_related("turns", "fossils")
    first_concept = _next_concept(session)
    sen_plan = request.sen_plan
    return render(
        request,
        "core/read.html",
        {
            "session": session,
            "concepts": concepts,
            "first_concept": first_concept,
            "progress": _session_progress(session),
            "learning_profile": request.learning_profile,
            "sen_plan": sen_plan,
            "recommended_resource": sen_plan["recommended_resource"],
            "recommended_resource_label": resource_label(sen_plan["recommended_resource"]),
        },
    )


@login_required
@profile_required
@require_http_methods(["GET", "POST"])
def teach_concept(request, session_id: int, concept_id: int):
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    concept = get_object_or_404(Concept, pk=concept_id, session=session)

    if request.method == "POST":
        student_text = request.POST.get("student_text", "").strip()
        if not student_text:
            messages.error(request, "Give Peckish at least a sentence to chew on.")
            return redirect("core:teach", session_id=session.id, concept_id=concept.id)

        history = [
            {
                "student_text": turn.student_text,
                "peckish_response": turn.peckish_response,
            }
            for turn in concept.turns.order_by("turn_number")
        ]
        reaction = ai.get_peckish_reaction(
            concept.title,
            concept.source_notes,
            history,
            student_text,
        )
        turn = _turn_from_reaction(concept, student_text, reaction)
        _award_turn_xp(request, session, turn)
        _store_fossil_if_needed(concept, turn, reaction)

        return redirect(f"{reverse('core:teach', args=[session.id, concept.id])}?turn={turn.id}")

    latest_turn = concept.turns.order_by("-turn_number").first()
    turns_count = concept.turns.count()
    concept_complete = _concept_is_complete(concept)
    next_concept = _next_concept(session, concept)
    review_fossil = concept.fossils.filter(re_taught_successfully=False).first()
    return render(
        request,
        "core/teach.html",
        {
            "session": session,
            "concept": concept,
            "latest_turn": latest_turn,
            "turns_count": turns_count,
            "concept_complete": concept_complete,
            "next_concept": next_concept,
            "review_fossil": review_fossil,
            "progress": _session_progress(session),
            "max_followups": settings.MAX_FOLLOWUPS_PER_CONCEPT,
        },
    )


@login_required
@profile_required
def session_summary(request, session_id: int):
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    concepts = list(session.concepts.prefetch_related("turns", "fossils"))
    latest_turns = [
        concept.turns.order_by("-turn_number").first()
        for concept in concepts
        if concept.turns.exists()
    ]
    average_depth = (
        round(sum(turn.depth_score for turn in latest_turns) / len(latest_turns))
        if latest_turns
        else 0
    )
    first_try_satisfied = sum(
        1
        for concept in concepts
        if concept.turns.order_by("turn_number").first()
        and concept.turns.order_by("turn_number").first().reaction_type == TeachingTurn.SATISFIED
    )
    completed_count = sum(1 for concept in concepts if _concept_is_complete(concept))
    expected_level = _level_from_xp(session.pet_xp)
    if session.pet_level != expected_level:
        session.pet_level = expected_level
        session.save(update_fields=["pet_level"])

    fossils = Fossil.objects.filter(concept__session=session).select_related("concept")
    return render(
        request,
        "core/summary.html",
        {
            "session": session,
            "concepts": concepts,
            "fossils": fossils,
            "average_depth": average_depth,
            "completed_count": completed_count,
            "first_try_satisfied": first_try_satisfied,
            "progress": _session_progress(session),
        },
    )


@login_required
@profile_required
@require_http_methods(["GET", "POST"])
def reteach_fossil(request, fossil_id: int):
    fossil = get_object_or_404(
        Fossil.objects.select_related("concept", "concept__session"),
        pk=fossil_id,
        concept__session__user=request.user,
    )
    result = None
    success = False
    review_turn = None
    prompt = ai.generate_reteach_prompt(fossil.concept.title, fossil.fossil_name).get(
        "peckish_prompt",
        "Can you teach that idea to me one more time?",
    )

    if request.method == "POST":
        student_text = request.POST.get("student_text", "").strip()
        if not student_text:
            messages.error(request, "Give Peckish a quick re-teach before moving on.")
            return redirect("core:reteach", fossil_id=fossil.id)

        result = ai.get_peckish_reaction(
            fossil.concept.title,
            fossil.concept.source_notes,
            [],
            student_text,
        )
        turn = _turn_from_reaction(fossil.concept, student_text, result)
        _award_turn_xp(request, fossil.concept.session, turn)
        review_turn = turn
        success = _turn_shows_full_understanding(turn)
        if success and not fossil.re_taught_successfully:
            fossil.re_taught_successfully = True
            fossil.save(update_fields=["re_taught_successfully"])

    next_fossil = Fossil.objects.filter(
        concept__session__user=request.user,
        re_taught_successfully=False,
    ).exclude(pk=fossil.pk).select_related("concept").first()

    return render(
        request,
        "core/reteach.html",
        {
            "fossil": fossil,
            "prompt": prompt,
            "result": result,
            "review_turn": review_turn,
            "success": success,
            "next_fossil": next_fossil,
            "attempts": fossil.student_attempts or _attempt_snapshots(fossil.concept),
            "source_notes": fossil.source_notes_snapshot or fossil.concept.source_notes,
        },
    )


@login_required
@profile_required
@require_http_methods(["POST"])
def transcribe_audio(request):
    audio_file = request.FILES.get("audio")
    if not audio_file:
        return JsonResponse(
            {"ok": False, "error": "No audio reached Peckish. Try the mic again or type instead."},
            status=400,
        )

    if audio_file.size > 12 * 1024 * 1024:
        return JsonResponse(
            {"ok": False, "error": "That recording is too long for the demo. Try a shorter explanation."},
            status=413,
        )

    mime_type = request.POST.get("mime_type") or audio_file.content_type or "audio/webm"
    transcript = ai.transcribe_audio(audio_file.read(), mime_type).strip()
    if not transcript:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Recording worked, but transcription is not configured. "
                    "Configure Gemini Enterprise in .env or type your answer."
                ),
            },
            status=422,
        )

    return JsonResponse({"ok": True, "transcript": transcript})


@login_required
@profile_required
def revision_resource(request, session_id: int, resource_type: str):
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    valid_types = {choice[0] for choice in RevisionResource.RESOURCE_CHOICES}
    if resource_type not in valid_types:
        messages.error(request, "Choose flashcards, a mind map, or a flow chart.")
        return redirect("core:read", session_id=session.id)

    profile_obj = request.learning_profile
    resource_obj, created = RevisionResource.objects.get_or_create(
        session=session,
        resource_type=resource_type,
        sen_profile=profile_obj.sen_profile,
        defaults={"content": {}},
    )
    if created or not resource_obj.content or request.GET.get("refresh") == "1":
        resource_obj.content = ai.generate_revision_resource(
            session=session,
            resource_type=resource_type,
            sen_profile=profile_obj.sen_profile,
            sen_plan=request.sen_plan,
        )
        resource_obj.save(update_fields=["content", "updated_at"])

    return render(
        request,
        "core/revision_resource.html",
        {
            "session": session,
            "resource": resource_obj,
            "content": resource_obj.content,
            "resource_label": resource_label(resource_type),
            "learning_profile": profile_obj,
            "sen_plan": request.sen_plan,
            "recommended_resource": request.sen_plan["recommended_resource"],
        },
    )
