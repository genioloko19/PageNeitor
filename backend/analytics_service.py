"""
Local analytics and LLM data-processing service for Pageneitor.

All measurements stay on the user's machine. Credentials are never included in
metrics or sent to Ollama; only aggregate values and link text for word clouds.
"""

import hashlib
import json
import math
import random
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime

from backend.database import (
    get_connection,
    get_all_links,
    get_categories,
    get_profiles,
    get_stats,
    get_gamification,
    get_domain_groups,
    get_domain_group,
    get_domain_settings,
    get_llm_cache,
    set_llm_cache,
    log_analytics_event,
    prune_analytics_events,
)
from backend.ollama_service import ollama_service


_snapshot_cache = {"at": 0, "data": None}
_insight_inflight = False
_wordcloud_inflight = False
_wordcloud_lock = threading.Lock()


STOPWORDS = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "como", "con",
    "contra", "cual", "cuando", "de", "del", "desde", "donde", "durante",
    "el", "ella", "ellas", "ellos", "en", "entre", "era", "es", "esa", "ese",
    "eso", "esta", "este", "esto", "estos", "fue", "ha", "hacia", "hasta",
    "hay", "la", "las", "le", "les", "lo", "los", "más", "mas", "me", "mi",
    "mis", "mucho", "muy", "no", "nos", "o", "para", "pero", "por", "que",
    "se", "sin", "sobre", "su", "sus", "te", "tiene", "tu", "tus", "un",
    "una", "unas", "uno", "unos", "y", "ya", "the", "and", "for", "with",
    "from", "this", "that", "your", "you", "are", "was", "were", "have",
    "has", "not", "its", "our", "their", "http", "https", "www", "com",
}


def _normalize(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^\w\s]", " ", text)


def _percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] * (c - k) + ordered[c] * (k - f)


def describe(values):
    values = [float(v) for v in (values or [])]
    if not values:
        return {
            "count": 0, "sum": 0, "mean": 0, "median": 0, "mode": 0,
            "stddev": 0, "min": 0, "max": 0, "p25": 0, "p75": 0, "p90": 0,
        }
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    counts = Counter(round(v, 2) for v in values)
    mode = counts.most_common(1)[0][0] if counts else 0
    return {
        "count": len(values),
        "sum": round(sum(values), 2),
        "mean": round(mean, 2),
        "median": round(_percentile(values, 50), 2),
        "mode": round(mode, 2),
        "stddev": round(math.sqrt(variance), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "p25": round(_percentile(values, 25), 2),
        "p75": round(_percentile(values, 75), 2),
        "p90": round(_percentile(values, 90), 2),
    }


def _table_counts(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _event_summary():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT event_type, COUNT(*) AS count
    FROM analytics_events GROUP BY event_type ORDER BY count DESC
    """)
    by_type = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT action, COUNT(*) AS count
    FROM analytics_events GROUP BY action ORDER BY count DESC LIMIT 30
    """)
    by_action = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
    FROM analytics_events
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date ORDER BY date ASC
    """)
    daily = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT CAST(strftime('%H', created_at) AS INTEGER) AS hour, COUNT(*) AS count
    FROM analytics_events
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY hour ORDER BY hour ASC
    """)
    hourly = {int(r["hour"]): r["count"] for r in cursor.fetchall()}

    cursor.execute("""
    SELECT metadata FROM analytics_events
    WHERE event_type = 'api_request'
    ORDER BY id DESC LIMIT 2000
    """)
    api_rows = cursor.fetchall()

    conn.close()

    latencies = []
    endpoints = Counter()
    statuses = Counter()
    for row in api_rows:
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception:
            meta = {}
        if "duration_ms" in meta:
            try:
                latencies.append(float(meta["duration_ms"]))
            except Exception:
                pass
        if meta.get("path"):
            endpoints[meta["path"]] += 1
        statuses[str(meta.get("status", "?"))] += 1

    return {
        "by_type": by_type,
        "by_action": by_action,
        "daily": daily,
        "hourly": [{"hour": h, "count": hourly.get(h, 0)} for h in range(24)],
        "api": {
            "count": len(api_rows),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p95_latency_ms": round(_percentile(latencies, 95), 1) if latencies else 0,
            "top_endpoints": [{"path": p, "count": c} for p, c in endpoints.most_common(10)],
            "statuses": [{"status": s, "count": c} for s, c in statuses.most_common()],
        },
    }


def _chat_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chat_sessions")
    sessions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chat_messages")
    messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE role = 'user'")
    user_messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant'")
    assistant_messages = cursor.fetchone()[0]
    conn.close()
    return {
        "sessions": sessions,
        "messages": messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "avg_messages_per_session": round(messages / sessions, 2) if sessions else 0,
    }


def _domain_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) AS count FROM domain_suggestions GROUP BY status")
    suggestions = {r["status"]: r["count"] for r in cursor.fetchall()}
    cursor.execute("SELECT COUNT(*) FROM domain_action_log WHERE action = 'merge_domain'")
    merges = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM domain_action_log WHERE action = 'merge_domain' AND undone = 1")
    undo_merges = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM domain_action_log WHERE action = 'refresh_thumbnail'")
    thumb_refreshes = cursor.fetchone()[0]
    conn.close()
    applied = suggestions.get("applied", 0)
    dismissed = suggestions.get("dismissed", 0)
    pending = suggestions.get("pending", 0)
    total_decided = applied + dismissed
    return {
        "suggestions": suggestions,
        "pending": pending,
        "applied": applied,
        "dismissed": dismissed,
        "acceptance_rate": round((applied / total_decided) * 100, 1) if total_decided else 0,
        "merges": merges,
        "undo_merges": undo_merges,
        "thumbnail_refreshes": thumb_refreshes,
    }


def compute_snapshot(force=False):
    if not force and _snapshot_cache["data"] and time.time() - _snapshot_cache["at"] < 10:
        return _snapshot_cache["data"]

    links = get_all_links()
    categories = get_categories()
    profiles = get_profiles()
    stats = get_stats()
    groups = get_domain_groups()
    gami = get_gamification()
    events = _event_summary()
    chat = _chat_stats()
    domains = _domain_stats()

    total = len(links)
    with_thumb = sum(1 for l in links if l.get("thumbnail_url"))
    missing_thumb = total - with_thumb
    with_category = sum(1 for l in links if l.get("category_id"))
    with_profile = sum(1 for l in links if l.get("profile_id"))
    with_tags = sum(1 for l in links if l.get("tags"))
    with_notes = sum(1 for l in links if (l.get("notes") or "").strip())
    total_credentials = sum(len(l.get("credentials") or []) for l in links)
    total_sublinks = sum(len(l.get("sublinks") or []) for l in links)

    links_per_domain = [g["count"] for g in groups]
    links_per_category = [c.get("link_count", 0) for c in categories]
    links_per_profile = [p.get("link_count", 0) for p in profiles]
    visits = [l.get("visit_count") or 0 for l in links]
    tags_per_link = [len(l.get("tags") or []) for l in links]
    credentials_per_link = [len(l.get("credentials") or []) for l in links]
    sublinks_per_link = [len(l.get("sublinks") or []) for l in links]

    tag_counter = Counter()
    for link in links:
        for tag in link.get("tags") or []:
            tag_counter[tag.lower()] += 1

    url_counter = Counter()
    for link in links:
        url = (link.get("url") or "").strip().rstrip("/").lower()
        if url:
            url_counter[url] += 1
    duplicates = [{"url": u, "count": c} for u, c in url_counter.items() if c > 1]

    timeseries_links = _table_counts("""
    SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
    FROM links
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date ORDER BY date ASC
    """)

    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kpis": {
            "total_links": total,
            "active_links": stats.get("total_active", 0),
            "archived_links": stats.get("total_archived", 0),
            "favorites": stats.get("total_favorites", 0),
            "unread": stats.get("total_unread", 0),
            "domains": len(groups),
            "categories": len(categories),
            "profiles": len(profiles),
            "credentials": total_credentials,
            "sublinks": total_sublinks,
            "thumbnail_coverage": round((with_thumb / total) * 100, 1) if total else 0,
            "level": gami.get("level", 1),
            "xp": gami.get("xp", 0),
            "trophies": gami.get("unlocked_count", 0),
            "chat_sessions": chat["sessions"],
            "pending_suggestions": domains["pending"],
        },
        "basic": {
            "total_links": total,
            "with_thumbnail": with_thumb,
            "missing_thumbnail": missing_thumb,
            "with_category": with_category,
            "without_category": total - with_category,
            "with_profile": with_profile,
            "without_profile": total - with_profile,
            "with_tags": with_tags,
            "with_notes": with_notes,
            "total_credentials": total_credentials,
            "total_sublinks": total_sublinks,
            "total_visits": sum(visits),
        },
        "distributions": {
            "links_per_domain": links_per_domain,
            "links_per_category": links_per_category,
            "links_per_profile": links_per_profile,
            "visits": visits,
            "tags_per_link": tags_per_link,
            "credentials_per_link": credentials_per_link,
            "sublinks_per_link": sublinks_per_link,
        },
        "descriptive": {
            "links_per_domain": describe(links_per_domain),
            "links_per_category": describe(links_per_category),
            "links_per_profile": describe(links_per_profile),
            "visits": describe(visits),
            "tags_per_link": describe(tags_per_link),
            "credentials_per_link": describe(credentials_per_link),
            "sublinks_per_link": describe(sublinks_per_link),
        },
        "timeseries": {
            "links_added": timeseries_links,
            "events_daily": events["daily"],
        },
        "activity": {
            "hourly": events["hourly"],
            "by_type": events["by_type"],
            "by_action": events["by_action"],
        },
        "top": {
            "domains": [{"name": g["root_domain"], "count": g["count"]} for g in groups[:12]],
            "categories": sorted(
                [{"name": c["name"], "count": c.get("link_count", 0), "color": c.get("color")} for c in categories],
                key=lambda x: -x["count"]
            ),
            "profiles": sorted(
                [{"name": p["name"], "count": p.get("link_count", 0), "color": p.get("color")} for p in profiles],
                key=lambda x: -x["count"]
            ),
            "tags": [{"name": t, "count": c} for t, c in tag_counter.most_common(20)],
        },
        "scatter": [
            {
                "title": l.get("title") or l.get("url"),
                "domain": l.get("root_domain") or l.get("domain"),
                "visits": l.get("visit_count") or 0,
                "tags": len(l.get("tags") or []),
                "credentials": len(l.get("credentials") or []),
                "sublinks": len(l.get("sublinks") or []),
                "thumbnail": 1 if l.get("thumbnail_url") else 0,
            }
            for l in links[:300]
        ],
        "quality": {
            "missing_thumbnails": missing_thumb,
            "missing_category": total - with_category,
            "missing_profile": total - with_profile,
            "missing_tags": total - with_tags,
            "missing_notes": total - with_notes,
            "duplicates": duplicates,
            "duplicate_count": sum(d["count"] - 1 for d in duplicates),
            "thumbnail_coverage": round((with_thumb / total) * 100, 1) if total else 0,
        },
        "chat": chat,
        "domains": domains,
        "events": events,
        "api": events["api"],
        "gamification": {
            "level": gami.get("level", 1),
            "level_title": gami.get("level_title", ""),
            "xp": gami.get("xp", 0),
            "next_level_xp": gami.get("next_level_xp", 0),
            "progress_pct": gami.get("progress_pct", 0),
            "trophies": gami.get("unlocked_count", 0),
            "total_trophies": gami.get("total_trophies", 0),
            "tabs_closed": gami.get("tabs_closed", 0),
            "deleted_count": gami.get("deleted_count", 0),
        },
    }

    _snapshot_cache["at"] = time.time()
    _snapshot_cache["data"] = snapshot
    return snapshot


def _fallback_insights(snapshot):
    k = snapshot["kpis"]
    q = snapshot["quality"]
    d = snapshot["domains"]
    insights = [
        f"Tienes {k['total_links']} enlaces en {k['domains']} dominios y {k['categories']} temas.",
        f"La cobertura de miniaturas es del {k['thumbnail_coverage']}% "
        f"({q['missing_thumbnails']} enlaces sin imagen).",
        f"{q['missing_category']} enlaces no tienen categoría y {q['missing_profile']} no tienen perfil.",
        f"La tasa de aceptación de sugerencias de dominio es del {d['acceptance_rate']}%.",
        f"El asistente ha registrado {snapshot['chat']['messages']} mensajes en "
        f"{snapshot['chat']['sessions']} conversaciones.",
    ]
    return insights


def generate_insights(force=False):
    snapshot = compute_snapshot(force=force)
    key = "analytics_insights_v1"
    digest = hashlib.sha1(json.dumps({
        "kpis": snapshot["kpis"],
        "quality": snapshot["quality"],
        "domains": snapshot["domains"],
        "chat": snapshot["chat"],
        "top": snapshot["top"],
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    cached = get_llm_cache(key)
    if cached and not force and (cached.get("payload") or {}).get("hash") == digest:
        payload = cached["payload"]
        if payload.get("insights"):
            return {
                "insights": payload["insights"],
                "source": payload.get("source", "cache"),
                "generated_at": cached.get("updated_at"),
            }

    context_lines = [
        f"Enlaces activos: {snapshot['kpis']['total_links']}",
        f"Dominios: {snapshot['kpis']['domains']}",
        f"Temas: {snapshot['kpis']['categories']}",
        f"Perfiles: {snapshot['kpis']['profiles']}",
        f"Favoritos: {snapshot['kpis']['favorites']}",
        f"Pendientes: {snapshot['kpis']['unread']}",
        f"Credenciales: {snapshot['kpis']['credentials']}",
        f"Subenlaces: {snapshot['kpis']['sublinks']}",
        f"Cobertura de miniaturas: {snapshot['kpis']['thumbnail_coverage']}%",
        f"Sin categoría: {snapshot['quality']['missing_category']}",
        f"Sin perfil: {snapshot['quality']['missing_profile']}",
        f"Sin etiquetas: {snapshot['quality']['missing_tags']}",
        f"Duplicados estimados: {snapshot['quality']['duplicate_count']}",
        f"Aceptación de sugerencias: {snapshot['domains']['acceptance_rate']}%",
        f"Fusiones realizadas: {snapshot['domains']['merges']}",
        f"Mensajes de chat: {snapshot['chat']['messages']}",
        f"Nivel: {snapshot['gamification']['level']} ({snapshot['gamification']['level_title']})",
        f"Latencia media API: {snapshot['api']['avg_latency_ms']} ms",
        "Top dominios: " + ", ".join(
            f"{x['name']} ({x['count']})" for x in snapshot["top"]["domains"][:6]
        ),
        "Top temas: " + ", ".join(
            f"{x['name']} ({x['count']})" for x in snapshot["top"]["categories"][:6]
        ),
    ]

    source = "Pageneitor Analytics"
    insights = None
    llm = ollama_service.analytics_insights("\n".join(context_lines))
    if llm:
        insights = llm
        source = f"Ollama ({ollama_service.selected_model})"
    if not insights:
        insights = _fallback_insights(snapshot)

    set_llm_cache(key, "analytics_insights", {
        "hash": digest,
        "insights": insights,
        "source": source,
    })
    return {"insights": insights, "source": source, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def _content_for_wordcloud(links, categories, profiles):
    parts = []
    for link in links:
        parts.append(link.get("title") or "")
        parts.append(link.get("description") or "")
        parts.append(" ".join(link.get("tags") or []))
        parts.append(link.get("notes") or "")
    parts.extend(c.get("name", "") for c in categories)
    parts.extend(p.get("name", "") for p in profiles)
    text = "\n".join(parts)
    return text[:12000]


def _fallback_wordcloud(links, categories, profiles, sets=3):
    text = _content_for_wordcloud(links, categories, profiles)
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9+#.-]{2,}", text)
    counter = Counter()
    for word in words:
        norm = _normalize(word).strip()
        if not norm or norm in STOPWORDS or len(norm) < 3:
            continue
        counter[norm] += 1
    top = counter.most_common(40)
    if not top:
        return []
    max_count = max(c for _, c in top) or 1
    base = [
        {"text": word, "weight": max(8, min(100, int((count / max_count) * 100)))}
        for word, count in top
    ]
    result = []
    for idx in range(sets):
        group = base[idx * 8:] + base[:idx * 8] if idx else base[:]
        rnd = random.Random(idx + 7)
        rnd.shuffle(group)
        result.append(group[:24])
    return result


def _refresh_wordcloud_cache(content_hash, content_text):
    global _wordcloud_inflight
    try:
        sets = ollama_service.wordcloud_keywords(content_text)
        source = "Ollama"
        if not sets:
            return
        payload = {
            "hash": content_hash,
            "sets": sets,
            "source": source,
        }
        set_llm_cache("wordcloud_v1", "wordcloud", payload)
    finally:
        with _wordcloud_lock:
            _wordcloud_inflight = False


def get_wordcloud(force=False):
    links = get_all_links()
    categories = get_categories()
    profiles = get_profiles()
    text = _content_for_wordcloud(links, categories, profiles)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    cache = get_llm_cache("wordcloud_v1")
    settings = get_domain_settings()
    rotation = settings.get("wordcloud_rotation", 60)

    if cache and not force:
        payload = cache.get("payload") or {}
        if payload.get("hash") == digest and payload.get("sets"):
            return {
                "sets": payload["sets"],
                "source": payload.get("source", "cache"),
                "rotation": rotation,
                "generated_at": cache.get("updated_at"),
            }

    fallback = _fallback_wordcloud(links, categories, profiles)
    global _wordcloud_inflight
    with _wordcloud_lock:
        should_start = not _wordcloud_inflight
        if should_start:
            _wordcloud_inflight = True
    if should_start and text:
        threading.Thread(
            target=_refresh_wordcloud_cache,
            args=(digest, text),
            daemon=True
        ).start()

    return {
        "sets": fallback,
        "source": "fallback dinámico",
        "rotation": rotation,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_domain_detail(root_domain):
    group = get_domain_group(root_domain)
    if not group:
        return None
    links = group.get("links") or []
    categories = Counter()
    profiles = Counter()
    tags = Counter()
    for link in links:
        categories[link.get("category_name") or "Sin categoría"] += 1
        profiles[link.get("profile_name") or "General"] += 1
        for tag in link.get("tags") or []:
            tags[tag] += 1

    visits = [l.get("visit_count") or 0 for l in links]
    return {
        "root_domain": group["root_domain"],
        "count": group["count"],
        "links": links,
        "thumbnails": group.get("thumbnails") or [],
        "stats": {
            "total_visits": sum(visits),
            "avg_visits": round(sum(visits) / len(visits), 1) if visits else 0,
            "thumbnail_coverage": round(
                (sum(1 for l in links if l.get("thumbnail_url")) / len(links)) * 100, 1
            ) if links else 0,
            "favorites": sum(1 for l in links if l.get("is_favorite")),
            "unread": sum(1 for l in links if not l.get("is_read")),
            "credentials": sum(len(l.get("credentials") or []) for l in links),
            "sublinks": sum(len(l.get("sublinks") or []) for l in links),
        },
        "categories": [{"name": n, "count": c} for n, c in categories.most_common()],
        "profiles": [{"name": n, "count": c} for n, c in profiles.most_common()],
        "tags": [{"name": n, "count": c} for n, c in tags.most_common(15)],
    }


def initialize_analytics():
    settings = get_domain_settings()
    prune_analytics_events(days=settings.get("analytics_retention_days", 90))
    return True
