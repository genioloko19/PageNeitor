"""
Domain grouping + LLM suggestion engine.

Rules decide the canonical domain and candidate groups. Ollama only proposes
safe actions on those groups (merge or refresh thumbnails); every action is
validated and stored as a persistent suggestion. Nothing is applied without an
explicit user confirmation.
"""

import threading
import time

from backend.database import (
    get_all_links,
    get_link_by_id,
    get_domain_settings,
    get_domain_groups,
    get_domain_suggestions,
    get_domain_suggestion,
    create_domain_suggestion,
    set_domain_suggestion_status,
    count_pending_domain_suggestions,
    get_domain_action_log,
    apply_domain_merge,
    refresh_domain_thumbnails,
    undo_last_domain_action,
)
from backend.ollama_service import ollama_service


ALLOWED_ACTIONS = {"merge_group", "refresh_thumbnail"}

_scan_lock = threading.Lock()
_schedule_lock = threading.Lock()
_scan_scheduled = False
_rescan_requested = False
_settings_wake = threading.Event()
_last_scan = {"at": None, "created": 0, "llm_used": False, "groups": 0}


def _link_preview(link):
    if not link:
        return None
    return {
        "id": link.get("id"),
        "title": link.get("title") or link.get("url"),
        "url": link.get("url"),
        "domain": link.get("domain"),
        "root_domain": link.get("root_domain"),
        "thumbnail_url": link.get("thumbnail_url") or "",
        "favicon_url": link.get("favicon_url") or "",
        "category_name": link.get("category_name") or "",
        "profile_name": link.get("profile_name") or "",
        "tags": link.get("tags") or [],
        "is_favorite": link.get("is_favorite") or 0,
        "is_read": link.get("is_read") or 0,
        "visit_count": link.get("visit_count") or 0,
        "credentials_count": len(link.get("credentials") or []),
        "sublinks_count": len(link.get("sublinks") or []),
    }


def _main_link_score(link):
    score = 0
    score += (link.get("is_favorite") or 0) * 100
    score += (link.get("visit_count") or 0) * 5
    score += len(link.get("credentials") or []) * 12
    score += len(link.get("sublinks") or []) * 8
    if link.get("thumbnail_url"):
        score += 5
    if (link.get("description") or "").strip():
        score += 3
    if (link.get("notes") or "").strip():
        score += 2
    score += len(link.get("tags") or []) * 2
    score += (link.get("id") or 0) / 100000.0
    return score


def _choose_main_link(links):
    if not links:
        return None
    return sorted(links, key=_main_link_score, reverse=True)[0]


def _candidate_groups():
    groups = get_domain_groups()
    candidates = []
    for group in groups:
        links = group.get("links") or []
        if not links:
            continue
        missing_thumbs = [link for link in links if not link.get("thumbnail_url")]
        if len(links) >= 2 or missing_thumbs:
            candidates.append({
                "root_domain": group["root_domain"],
                "links": links,
                "missing_thumbnails": missing_thumbs,
            })
    return candidates


def _build_llm_context(candidates):
    lines = []
    for group in candidates:
        links = group["links"]
        lines.append(
            f"GRUPO {group['root_domain']} ({len(links)} enlaces)"
        )
        for link in links:
            tags = ",".join(link.get("tags") or [])[:70]
            lines.append(
                f"- id={link['id']} | {link.get('title', '')[:90]} | "
                f"{link.get('url', '')[:110]} | visits={link.get('visit_count') or 0} | "
                f"fav={(link.get('is_favorite') or 0)} | "
                f"thumb={'si' if link.get('thumbnail_url') else 'no'} | "
                f"creds={len(link.get('credentials') or [])} | "
                f"subs={len(link.get('sublinks') or [])} | tags={tags}"
            )
        lines.append("")
    return "\n".join(lines)


def _sanitize_llm_suggestions(raw_suggestions, candidates, min_confidence):
    by_domain = {group["root_domain"]: group for group in candidates}
    clean = []

    for item in raw_suggestions or []:
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").strip()
        root = (item.get("root_domain") or "").strip().lower()
        if action not in ALLOWED_ACTIONS or root not in by_domain:
            continue

        try:
            confidence = float(item.get("confidence", 0))
        except Exception:
            confidence = 0.0
        if confidence < min_confidence:
            continue

        group = by_domain[root]
        group_links = {int(l["id"]): l for l in group["links"]}
        raw_ids = item.get("link_ids") or []
        link_ids = []
        for value in raw_ids:
            try:
                lid = int(value)
            except Exception:
                continue
            if lid in group_links and lid not in link_ids:
                link_ids.append(lid)

        if action == "refresh_thumbnail":
            link_ids = [
                lid for lid in link_ids
                if not group_links[lid].get("thumbnail_url")
            ][:5]
            if not link_ids:
                continue
            clean.append({
                "action": action,
                "root_domain": root,
                "link_ids": link_ids,
                "confidence": confidence,
                "reason": (item.get("reason") or "Enlaces sin miniatura detectados.")[:180],
            })
            continue

        # merge_group
        if len(link_ids) < 2:
            continue
        try:
            main_id = int(item.get("main_link_id"))
        except Exception:
            main_id = None
        if main_id not in link_ids:
            main_id = _choose_main_link([group_links[lid] for lid in link_ids])["id"]
        clean.append({
            "action": action,
            "root_domain": root,
            "main_link_id": main_id,
            "link_ids": link_ids,
            "confidence": confidence,
            "reason": (item.get("reason") or "Enlaces del mismo dominio relacionados.")[:180],
        })

    return clean


def _deterministic_suggestions(candidates, already_covered, min_confidence):
    suggestions = []
    for group in candidates:
        root = group["root_domain"]
        links = group["links"]

        covered = already_covered.get(root, set())

        if group["missing_thumbnails"] and "refresh_thumbnail" not in covered:
            missing_ids = [l["id"] for l in group["missing_thumbnails"]][:5]
            suggestions.append({
                "action": "refresh_thumbnail",
                "root_domain": root,
                "link_ids": missing_ids,
                "confidence": 0.7,
                "reason": f"{len(missing_ids)} enlace(s) de {root} sin miniatura.",
            })

        if len(links) >= 2 and "merge_group" not in covered:
            main = _choose_main_link(links)
            suggestions.append({
                "action": "merge_group",
                "root_domain": root,
                "main_link_id": main["id"],
                "link_ids": [l["id"] for l in links],
                "confidence": 0.65,
                "reason": f"{len(links)} enlaces comparten el dominio {root}.",
            })

    return [s for s in suggestions if s["confidence"] >= min_confidence]


def analyze_domains(force=False, use_llm=True):
    """
    Scans domain groups and stores suggestions. Safe to call from a thread.
    Returns a summary.
    """
    global _rescan_requested

    settings = get_domain_settings()
    if not settings["domain_scan_enabled"] and not force:
        return {"success": True, "skipped": True, "reason": "scan_disabled", "created": 0}

    if not _scan_lock.acquire(blocking=False):
        _rescan_requested = True
        return {"success": True, "skipped": True, "reason": "already_running", "created": 0}

    try:
        candidates = _candidate_groups()
        if not candidates:
            _last_scan.update({"at": time.time(), "created": 0, "llm_used": False, "groups": 0})
            return {"success": True, "created": 0, "groups": 0, "llm_used": False}

        min_confidence = settings["domain_min_confidence"]
        raw = None
        llm_used = False
        if use_llm:
            raw = ollama_service.domain_suggestions(_build_llm_context(candidates))
            llm_used = raw is not None

        clean = _sanitize_llm_suggestions(raw, candidates, min_confidence) if raw else []

        covered = {}
        for suggestion in clean:
            covered.setdefault(suggestion["root_domain"], set()).add(suggestion["action"])

        deterministic = _deterministic_suggestions(candidates, covered, min_confidence)
        final_suggestions = clean + deterministic

        created = 0
        for suggestion in final_suggestions[:10]:
            payload = {
                "root_domain": suggestion["root_domain"],
                "link_ids": suggestion.get("link_ids", []),
            }
            if suggestion.get("main_link_id"):
                payload["main_link_id"] = suggestion["main_link_id"]

            # Enrich with preview info so the UI/chat can show thumbnails
            previews = []
            for lid in suggestion.get("link_ids", []):
                link = get_link_by_id(lid)
                if link:
                    previews.append(_link_preview(link))
            payload["links"] = previews

            result = create_domain_suggestion(
                root_domain=suggestion["root_domain"],
                action=suggestion["action"],
                payload=payload,
                reason=suggestion.get("reason", ""),
                confidence=suggestion.get("confidence", 0),
            )
            if result:
                created += 1

        _last_scan.update({
            "at": time.time(),
            "created": created,
            "llm_used": llm_used,
            "groups": len(candidates),
        })
        return {
            "success": True,
            "created": created,
            "groups": len(candidates),
            "llm_used": llm_used,
        }
    except Exception as e:
        print(f"[Domains] Scan error: {e}")
        return {"success": False, "error": str(e), "created": 0}
    finally:
        _scan_lock.release()
        if _rescan_requested:
            _rescan_requested = False
            request_domain_scan(1.0)


def request_domain_scan(delay=2.0):
    """Debounced background scan after saving/importing links."""
    global _scan_scheduled
    with _schedule_lock:
        if _scan_scheduled:
            return False
        _scan_scheduled = True

    def worker():
        global _scan_scheduled
        try:
            if delay:
                time.sleep(delay)
            analyze_domains()
        finally:
            with _schedule_lock:
                _scan_scheduled = False

    threading.Thread(target=worker, daemon=True).start()
    return True


def start_domain_watcher():
    """Periodic scan thread. Reads the interval from settings each cycle."""
    def loop():
        # Initial scan shortly after startup.
        request_domain_scan(5.0)
        while True:
            try:
                settings = get_domain_settings()
                interval = settings["domain_scan_interval"]
                if settings["domain_scan_enabled"] and interval > 0:
                    timeout = max(1, interval) * 60
                else:
                    timeout = 60

                woke = _settings_wake.wait(timeout)
                if woke:
                    _settings_wake.clear()
                    continue
                if settings["domain_scan_enabled"] and interval > 0:
                    analyze_domains()
            except Exception as e:
                print(f"[Domains] Watcher error: {e}")
                time.sleep(60)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def wake_domain_watcher():
    """Applies a new interval/enabled setting without restarting the app."""
    _settings_wake.set()
    request_domain_scan(1.0)


def enrich_suggestion(suggestion):
    if not suggestion:
        return None
    item = dict(suggestion)
    payload = item.get("payload") or {}
    if not payload.get("links"):
        payload["links"] = [
            _link_preview(get_link_by_id(lid))
            for lid in payload.get("link_ids", [])
            if get_link_by_id(lid)
        ]
    if payload.get("main_link_id"):
        main = get_link_by_id(payload["main_link_id"])
        payload["main_link"] = _link_preview(main)
    item["payload"] = payload
    return item


def get_suggestions_enriched(status=None, unread_only=False, limit=50):
    return [
        enrich_suggestion(s)
        for s in get_domain_suggestions(status=status, unread_only=unread_only, limit=limit)
    ]


def apply_suggestion(suggestion_id):
    suggestion = get_domain_suggestion(suggestion_id)
    if not suggestion:
        return {"success": False, "error": "La sugerencia no existe."}
    if suggestion.get("status") != "pending":
        return {"success": False, "error": "La sugerencia ya fue procesada."}

    action = suggestion.get("action")
    payload = suggestion.get("payload") or {}
    root = suggestion.get("root_domain")
    link_ids = payload.get("link_ids") or []

    if action == "merge_group":
        result = apply_domain_merge(
            root,
            payload.get("main_link_id"),
            link_ids,
            reason=suggestion.get("reason", ""),
            suggestion_id=suggestion_id,
        )
    elif action == "refresh_thumbnail":
        result = refresh_domain_thumbnails(link_ids, suggestion_id=suggestion_id)
    else:
        return {"success": False, "error": "Acción de sugerencia no reconocida."}

    if result.get("success"):
        set_domain_suggestion_status(suggestion_id, "applied")
    return result


def dismiss_suggestion(suggestion_id):
    ok = set_domain_suggestion_status(suggestion_id, "dismissed")
    return {"success": ok}


def get_domain_dashboard():
    groups = get_domain_groups()
    summary = [
        {
            "root_domain": g["root_domain"],
            "count": g["count"],
            "thumbnails": g["thumbnails"],
            "links": [_link_preview(link) for link in g["links"][:4]],
        }
        for g in groups
    ]
    return {
        "groups": summary,
        "suggestions": get_suggestions_enriched(status="pending"),
        "counts": count_pending_domain_suggestions(),
        "actions": get_domain_action_log(10),
        "settings": get_domain_settings(),
        "last_scan": _last_scan,
    }


def undo_last_action():
    return undo_last_domain_action()
