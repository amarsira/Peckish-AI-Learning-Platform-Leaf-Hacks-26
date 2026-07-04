import base64
import logging
import os
import re
from urllib.parse import urlparse

import requests


GOOGLE_ENDPOINT = "https://customsearch.googleapis.com/customsearch/v1"
COMMONS_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "PeckishHackathon/1.0 (educational demo)"
MAX_EMBEDDED_IMAGE_BYTES = 850_000
logger = logging.getLogger(__name__)
_PROVIDER_BLOCKED: set[str] = set()
_LOGGED_PROVIDER_ERRORS: set[tuple[str, object]] = set()
_SEARCH_CACHE: dict[tuple[str, str], dict | None] = {}


def _enabled() -> bool:
    return os.environ.get("PECKISH_WEB_IMAGES", "1") == "1"


def _clean_query(prompt: str, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9 ,:+/_-]", " ", prompt or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = fallback
    text = re.sub(
        r"\b(colou?rful|friendly|warm|inclusive|illustration|representing|simple|study|visual|image|prompt)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return f"{text or fallback} educational diagram"


def _query_candidates(prompt: str, fallback: str) -> list[str]:
    fallback_query = _clean_query(fallback, fallback)
    prompt_query = _clean_query(prompt, fallback)
    short_prompt = " ".join(re.findall(r"[A-Za-z0-9]+", prompt or "")[:7])
    short_query = _clean_query(short_prompt, fallback) if short_prompt else fallback_query
    candidates = [fallback_query, short_query, prompt_query]
    return list(dict.fromkeys(query for query in candidates if query))


def _simple_query(value: str, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9 ]", " ", value or fallback or "")
    text = re.sub(
        r"\b(big|picture|key|mechanism|evidence|examples|common|mix-ups|colourful|friendly|cartoon|warm|inclusive|illustration|representing|study|visual|prompt)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    words = []
    for word in re.findall(r"[A-Za-z0-9]+", text):
        lowered = word.lower()
        if len(lowered) < 3 and not lowered.isdigit():
            continue
        if lowered in {existing.lower() for existing in words}:
            continue
        words.append(word)
    return " ".join(words[:6]) or fallback or value


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "web"


def _provider_error(provider_name: str, exc: Exception) -> None:
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        status = getattr(response, "status_code", "unknown")
        message = ""
        try:
            message = response.json().get("error", {}).get("message", "")
        except Exception:
            message = ""
        if status in {403, 429}:
            _PROVIDER_BLOCKED.add(provider_name)
        log_key = (provider_name, status)
        if log_key not in _LOGGED_PROVIDER_ERRORS:
            logger.warning("Image provider %s failed with HTTP %s. %s", provider_name, status, message)
            _LOGGED_PROVIDER_ERRORS.add(log_key)
        return
    log_key = (provider_name, exc.__class__.__name__)
    if log_key not in _LOGGED_PROVIDER_ERRORS:
        logger.warning("Image provider %s failed with %s.", provider_name, exc.__class__.__name__)
        _LOGGED_PROVIDER_ERRORS.add(log_key)


def _image_data_uri(url: str) -> str | None:
    if not url:
        return None
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        stream=True,
        timeout=8,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        return None

    chunks = []
    total = 0
    for chunk in response.iter_content(65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_EMBEDDED_IMAGE_BYTES:
            return None
        chunks.append(chunk)
    if not chunks:
        return None
    encoded = base64.b64encode(b"".join(chunks)).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _with_embedded_image(result: dict) -> dict:
    if result.get("web_image_data_uri") or not result.get("image_url"):
        return result
    try:
        embedded = _image_data_uri(result["image_url"])
    except Exception as exc:
        _provider_error("image download", exc)
        return result
    if embedded:
        result = dict(result)
        result["web_image_data_uri"] = embedded
    return result


def _looks_like_search_page(url: str) -> bool:
    host = _host(url)
    return host in {"google.com", "images.google.com"} or host.endswith(".google.com")


def _google_image(query: str) -> dict | None:
    api_key = os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY")
    engine_id = os.environ.get("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")
    if not api_key or not engine_id:
        return None

    response = requests.get(
        GOOGLE_ENDPOINT,
        params={
            "key": api_key,
            "cx": engine_id,
            "q": query,
            "searchType": "image",
            "num": 5,
            "safe": "active",
            "imgSize": "medium",
        },
        timeout=6,
    )
    response.raise_for_status()
    for item in response.json().get("items", []):
        image_url = item.get("link")
        if not image_url:
            continue
        image_meta = item.get("image", {})
        source_url = image_meta.get("contextLink") or image_url
        return {
            "image_url": image_url,
            "image_source_url": source_url,
            "image_credit": item.get("title") or _host(source_url),
            "image_source": "Google image search",
            "image_query": query,
        }
    return None


def _commons_image(query: str) -> dict | None:
    response = requests.get(
        COMMONS_ENDPOINT,
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 900,
            "format": "json",
            "origin": "*",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=6,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info_items = page.get("imageinfo") or []
        if not info_items:
            continue
        info = info_items[0]
        mime = info.get("mime", "")
        if not mime.startswith("image/"):
            continue
        metadata = info.get("extmetadata", {})
        license_short = metadata.get("LicenseShortName", {}).get("value", "Wikimedia Commons")
        artist = re.sub("<[^>]+>", "", metadata.get("Artist", {}).get("value", "")).strip()
        credit_parts = [part for part in (page.get("title", "").replace("File:", ""), artist, license_short) if part]
        return {
            "image_url": info.get("thumburl") or info.get("url"),
            "image_source_url": info.get("descriptionurl") or info.get("url"),
            "image_credit": " | ".join(credit_parts[:3]),
            "image_source": "Wikimedia Commons",
            "image_query": query,
        }
    return None


def find_educational_image(prompt: str, fallback: str) -> dict | None:
    if not _enabled():
        return None
    google_queries = _query_candidates(prompt, fallback)[:2]
    commons_query = _simple_query(fallback, prompt)
    provider_queries = [
        (_google_image, google_queries),
        (_commons_image, [commons_query]),
    ]
    for provider, queries in provider_queries:
        provider_name = provider.__name__
        if provider_name in _PROVIDER_BLOCKED:
            continue
        for query in queries:
            cache_key = (provider_name, query)
            if cache_key in _SEARCH_CACHE:
                cached = _SEARCH_CACHE[cache_key]
                if cached:
                    return dict(cached)
                continue
            try:
                result = provider(query)
                if result and result.get("image_url"):
                    result = _with_embedded_image(result)
                    _SEARCH_CACHE[cache_key] = result
                    return dict(result)
                _SEARCH_CACHE[cache_key] = None
            except Exception as exc:
                _provider_error(provider_name, exc)
                _SEARCH_CACHE[cache_key] = None
                if provider_name in _PROVIDER_BLOCKED:
                    break
    return None


def enrich_mindmap_images(resource: dict, topic: str) -> dict:
    if not _enabled() or not isinstance(resource, dict) or not resource.get("nodes"):
        return resource

    enriched = dict(resource)
    if (
        enriched.get("central_image_url")
        and not enriched.get("central_web_image_data_uri")
        and not _looks_like_search_page(enriched.get("central_image_url", ""))
    ):
        embedded = _with_embedded_image({"image_url": enriched["central_image_url"]})
        if embedded.get("web_image_data_uri"):
            enriched["central_web_image_data_uri"] = embedded["web_image_data_uri"]

    if not enriched.get("central_image_url") or _looks_like_search_page(enriched.get("central_image_url", "")):
        central = find_educational_image(
            enriched.get("central_image_prompt") or enriched.get("central_idea") or topic,
            enriched.get("central_idea") or topic,
        )
        if central:
            for key, value in central.items():
                enriched[f"central_{key}"] = value

    nodes = []
    for node in enriched.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_copy = dict(node)
        if (
            node_copy.get("image_url")
            and not node_copy.get("web_image_data_uri")
            and not _looks_like_search_page(node_copy.get("image_url", ""))
        ):
            embedded = _with_embedded_image({"image_url": node_copy["image_url"]})
            if embedded.get("web_image_data_uri"):
                node_copy["web_image_data_uri"] = embedded["web_image_data_uri"]

        if not node_copy.get("image_url") or _looks_like_search_page(node_copy.get("image_url", "")):
            image = find_educational_image(
                node_copy.get("image_prompt") or node_copy.get("label") or topic,
                f"{topic} {node_copy.get('label', '')}",
            )
            if image:
                node_copy.update(image)
        nodes.append(node_copy)
    enriched["nodes"] = nodes
    return enriched
