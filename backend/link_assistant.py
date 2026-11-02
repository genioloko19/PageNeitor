"""
Assistant for inserting one or many links.

- Extracts URLs from pasted text.
- Enriches metadata, detects the root domain and existing domain groups.
- Checks exact duplicates.
- Classifies links with local Ollama, with deterministic fallback.
- Proposes new categories/profiles only when nothing existing fits.
- Commits only after the user confirms the preview.
"""

import re
import hashlib
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from backend.database import (
    get_all_links,
    get_categories,
    get_profiles,
    add_category,
    add_profile,
    add_link,
    get_domain_groups,
    get_domain_settings,
    log_analytics_event,
)
from backend.domain_utils import get_root_domain
from backend.scraper import extract_metadata, normalize_url
from backend.ollama_service import ollama_service


URL_RE = re.compile(
    r"(https?://[^\s<>\"']+)"
    r"|((?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>\"']*)?)",
    re.IGNORECASE,
)


def _normalize_name(value):
    value = unicodedata.normalize("NFKD", (value or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _clean_url(value):
    value = (value or "").strip().strip(".,;:!?)]}\"'")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return normalize_url(value)


def extract_urls(text):
    found = []
    seen = set()
    for match in URL_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2) or ""
        url = _clean_url(raw)
        if not url:
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(url)
    return found[:12]


def _safe_color(value, fallback):
    value = (value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", value):
        return value
    return fallback


def _safe_icon(value, fallback):
    value = (value or "").strip()
    if re.match(r"^fa-[a-z0-9-]+$", value):
        return value
    return fallback


def _find_existing_by_name(items, name):
    wanted = _normalize_name(name)
    if not wanted:
        return None
    for item in items:
        if _normalize_name(item.get("name")) == wanted:
            return item
    return None


def _default_profile(profiles):
    for profile in profiles:
        if profile.get("is_default"):
            return profile
    return profiles[0] if profiles else None


def _metadata_for_url(url):
    try:
        meta = extract_metadata(url)
    except Exception:
        meta = {
            "url": url,
            "title": url,
            "description": "",
            "thumbnail_url": "",
            "favicon_url": "",
            "domain": get_root_domain(url),
            "category_id": None,
            "suggested_tags": [],
        }
    return meta


def preview_links(text, use_llm=True):
    urls = extract_urls(text)
    if not urls:
        return {
            "success": False,
            "error": "No se detectaron URLs válidas.",
            "items": [],
            "categories": get_categories(),
            "profiles": get_profiles(),
        }

    categories = get_categories()
    profiles = get_profiles()
    existing_links = get_all_links()
    groups = get_domain_groups()
    domain_counts = {g["root_domain"]: g["count"] for g in groups}
    settings = get_domain_settings()

    existing_by_url = {}
    for link in existing_links:
        key = (link.get("url") or "").strip().rstrip("/").lower()
        if key:
            existing_by_url[key] = link

    with ThreadPoolExecutor(max_workers=4) as pool:
        metas = list(pool.map(_metadata_for_url, urls))

    default_profile = _default_profile(profiles)
    items = []
    for meta in metas:
        url = meta.get("url") or ""
        normalized_url = url.rstrip("/").lower()
        root = get_root_domain(
            meta.get("domain") or url,
            settings["group_subdomains"]
        )
        duplicate = existing_by_url.get(normalized_url)
        deterministic_category = meta.get("category_id")
        items.append({
            "temp_id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12],
            "url": url,
            "title": meta.get("title") or url,
            "description": meta.get("description") or "",
            "thumbnail_url": meta.get("thumbnail_url") or "",
            "favicon_url": meta.get("favicon_url") or "",
            "domain": meta.get("domain") or root,
            "root_domain": root,
            "domain_exists": root in domain_counts,
            "domain_count": domain_counts.get(root, 0),
            "tags": meta.get("suggested_tags") or [],
            "category_id": deterministic_category,
            "profile_id": default_profile["id"] if default_profile else None,
            "category_name": next(
                (c["name"] for c in categories if c["id"] == deterministic_category),
                "Sin categoría"
            ),
            "profile_name": default_profile["name"] if default_profile else "General",
            "duplicate": bool(duplicate),
            "duplicate_id": duplicate.get("id") if duplicate else None,
            "new_category": None,
            "new_profile": None,
            "confidence": 0.55,
            "reason": "Clasificación automática inicial.",
            "source": "reglas",
        })

    llm_used = False
    if use_llm and items:
        context_lines = [
            "CATEGORÍAS EXISTENTES:",
        ]
        for c in categories:
            context_lines.append(f"- id={c['id']} | {c['name']}")
        context_lines.append("PERFILES EXISTENTES:")
        for p in profiles:
            context_lines.append(f"- id={p['id']} | {p['name']}")
        context_lines.append("ENLACES NUEVOS:")
        for idx, item in enumerate(items):
            context_lines.append(
                f"[{idx}] {item['title'][:100]} | {item['url'][:130]} | "
                f"dominio={item['root_domain']} | desc={item['description'][:180]} | "
                f"tema_regla={item['category_name']} | tags_regla={','.join(item['tags'][:5])}"
            )

        classified = ollama_service.classify_links("\n".join(context_lines))
        if classified:
            llm_used = True
            category_ids = {c["id"] for c in categories}
            profile_ids = {p["id"] for p in profiles}
            for result in classified:
                if not isinstance(result, dict):
                    continue
                try:
                    index = int(result.get("index"))
                except Exception:
                    continue
                if index < 0 or index >= len(items):
                    continue
                item = items[index]

                category_id = result.get("category_id")
                try:
                    category_id = int(category_id)
                except Exception:
                    category_id = None
                if category_id in category_ids:
                    item["category_id"] = category_id
                    item["category_name"] = next(
                        c["name"] for c in categories if c["id"] == category_id
                    )

                profile_id = result.get("profile_id")
                try:
                    profile_id = int(profile_id)
                except Exception:
                    profile_id = None
                if profile_id in profile_ids:
                    item["profile_id"] = profile_id
                    item["profile_name"] = next(
                        p["name"] for p in profiles if p["id"] == profile_id
                    )

                tags = result.get("tags")
                if isinstance(tags, list):
                    item["tags"] = [
                        str(t).strip().lstrip("#")[:32]
                        for t in tags if str(t).strip()
                    ][:6]

                try:
                    item["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.7))))
                except Exception:
                    item["confidence"] = 0.7
                item["reason"] = str(result.get("reason", ""))[:180]
                item["source"] = "Ollama"

                new_category = result.get("new_category")
                if isinstance(new_category, dict) and new_category.get("name"):
                    name = str(new_category["name"]).strip()[:60]
                    existing = _find_existing_by_name(categories, name)
                    if existing:
                        item["category_id"] = existing["id"]
                        item["category_name"] = existing["name"]
                    else:
                        item["new_category"] = {
                            "name": name,
                            "color": _safe_color(new_category.get("color"), "#8b5cf6"),
                            "icon": _safe_icon(new_category.get("icon"), "fa-folder"),
                            "reason": str(new_category.get("reason", ""))[:180],
                        }

                new_profile = result.get("new_profile")
                if isinstance(new_profile, dict) and new_profile.get("name"):
                    name = str(new_profile["name"]).strip()[:60]
                    existing = _find_existing_by_name(profiles, name)
                    if existing:
                        item["profile_id"] = existing["id"]
                        item["profile_name"] = existing["name"]
                    else:
                        item["new_profile"] = {
                            "name": name,
                            "color": _safe_color(new_profile.get("color"), "#6366f1"),
                            "icon": _safe_icon(new_profile.get("icon"), "fa-user"),
                            "reason": str(new_profile.get("reason", ""))[:180],
                        }

    new_categories = []
    new_profiles = []
    for item in items:
        if item["new_category"] and not any(
            x["name"] == item["new_category"]["name"] for x in new_categories
        ):
            new_categories.append(item["new_category"])
        if item["new_profile"] and not any(
            x["name"] == item["new_profile"]["name"] for x in new_profiles
        ):
            new_profiles.append(item["new_profile"])

    return {
        "success": True,
        "items": items,
        "categories": categories,
        "profiles": profiles,
        "new_categories": new_categories,
        "new_profiles": new_profiles,
        "llm_used": llm_used,
        "source": f"Ollama ({ollama_service.selected_model})" if llm_used else "Reglas locales",
    }


def commit_links(items, accept_new_categories=True, accept_new_profiles=True, skip_duplicates=True):
    if not isinstance(items, list) or not items:
        return {"success": False, "error": "No hay enlaces para guardar.", "created": []}

    categories = get_categories()
    profiles = get_profiles()
    existing = {((l.get("url") or "").strip().rstrip("/").lower()): l for l in get_all_links()}
    created = []
    skipped = []
    errors = []

    for raw in items[:30]:
        if not isinstance(raw, dict):
            continue
        url = _clean_url(raw.get("url"))
        if not url:
            errors.append({"url": raw.get("url"), "error": "URL no válida"})
            continue
        key = url.rstrip("/").lower()
        if skip_duplicates and key in existing:
            skipped.append({"url": url, "reason": "duplicado"})
            continue

        category_id = raw.get("category_id")
        try:
            category_id = int(category_id) if category_id else None
        except Exception:
            category_id = None

        category = next((c for c in categories if c["id"] == category_id), None)
        new_category = raw.get("new_category")
        if isinstance(new_category, dict) and accept_new_categories and new_category.get("name"):
            name = str(new_category["name"]).strip()[:60]
            category = _find_existing_by_name(categories, name)
            if not category:
                category = add_category(
                    name,
                    _safe_color(new_category.get("color"), "#8b5cf6"),
                    _safe_icon(new_category.get("icon"), "fa-folder"),
                )
                categories = get_categories()
        if not category:
            category = next((c for c in categories if c.get("slug") == "tools"), None)
        category_id = category["id"] if category else None

        profile_id = raw.get("profile_id")
        try:
            profile_id = int(profile_id) if profile_id else None
        except Exception:
            profile_id = None

        profile = next((p for p in profiles if p["id"] == profile_id), None)
        new_profile = raw.get("new_profile")
        if isinstance(new_profile, dict) and accept_new_profiles and new_profile.get("name"):
            name = str(new_profile["name"]).strip()[:60]
            profile = _find_existing_by_name(profiles, name)
            if not profile:
                profile = add_profile(
                    name,
                    _safe_color(new_profile.get("color"), "#6366f1"),
                    _safe_icon(new_profile.get("icon"), "fa-user"),
                    "Perfil propuesto por el asistente de enlaces",
                )
                profiles = get_profiles()
        if not profile:
            profile = _default_profile(profiles)
        profile_id = profile["id"] if profile else None

        tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
        tags = [str(t).strip().lstrip("#")[:32] for t in tags if str(t).strip()][:8]

        try:
            link = add_link(
                url=url,
                title=(raw.get("title") or url)[:300],
                description=(raw.get("description") or "")[:1000],
                thumbnail_url=raw.get("thumbnail_url") or "",
                favicon_url=raw.get("favicon_url") or "",
                domain=raw.get("domain") or get_root_domain(url, get_domain_settings()["group_subdomains"]),
                category_id=category_id,
                profile_id=profile_id,
                tags=tags,
                notes=(raw.get("notes") or "")[:1000],
            )
            if link:
                created.append(link)
                existing[key] = link
        except Exception as e:
            errors.append({"url": url, "error": str(e)})

    log_analytics_event(
        "link_insert",
        action="assistant_commit",
        entity_type="link",
        metadata={
            "created": len(created),
            "skipped": len(skipped),
            "errors": len(errors),
            "new_categories": sum(1 for x in items if x.get("new_category")),
            "new_profiles": sum(1 for x in items if x.get("new_profile")),
        },
    )

    return {
        "success": len(created) > 0,
        "created": created,
        "created_count": len(created),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "errors": errors,
        "error_count": len(errors),
    }
