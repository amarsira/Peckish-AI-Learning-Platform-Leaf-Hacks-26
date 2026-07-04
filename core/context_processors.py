from django.db.models import Sum

from .models import Session


XP_PER_LEVEL = 120


def _level_from_xp(xp: int) -> int:
    return max(1, xp // XP_PER_LEVEL + 1)


def player_progress(request) -> dict:
    if not request.user.is_authenticated:
        return {}

    total_xp = Session.objects.filter(user=request.user).aggregate(total=Sum("pet_xp")).get("total") or 0
    level = _level_from_xp(total_xp)
    current_level_xp = total_xp % XP_PER_LEVEL
    return {
        "player_progress": {
            "level": level,
            "total_xp": total_xp,
            "current_level_xp": current_level_xp,
            "xp_to_next": XP_PER_LEVEL - current_level_xp if current_level_xp else XP_PER_LEVEL,
            "percent": round((current_level_xp / XP_PER_LEVEL) * 100),
        },
        "level_up_payload": request.session.pop("level_up_payload", None),
    }
