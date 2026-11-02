"""
Flask REST API server for Pageneitor v3.9.
Serves frontend static files and handles:
- Link cataloging, metadata extraction, search, and filtering
- Multi-account credentials vault per link
- Sublinks and associated tabs submodal
- Database export / import / backup with zero data loss guarantee
- Ollama local AI and gamification engine
"""

import os
import sys
import json
import time
import webbrowser
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, g
from flask_cors import CORS

from backend.database import (
    init_db, get_all_links, get_link_by_id, add_link, update_link,
    delete_link, get_profiles, add_profile, update_profile, delete_profile,
    get_categories, add_category, update_category, delete_category,
    get_stats, get_gamification, add_gamification_event, get_analytics,
    add_credential_to_link, update_credential_in_link, delete_credential_from_link,
    add_sublink_to_link, batch_add_sublinks, toggle_sublink_read, delete_sublink_from_link,
    export_database_json, import_database_json, restore_database_from_file,
    get_auto_backups, create_auto_backup, create_manual_backup, create_db_snapshot,
    get_db_info, DB_PATH, BACKUPS_DIR,
    create_chat_session, get_chat_sessions, get_chat_session,
    delete_chat_session, rename_chat_session,
    get_domain_settings, set_domain_settings, get_domain_groups,
    get_domain_suggestion, set_domain_suggestion_status,
    mark_domain_suggestions_read, count_pending_domain_suggestions,
    get_domain_action_log, apply_domain_merge,
    log_analytics_event, get_analytics_events,
)
from backend.analytics_service import (
    compute_snapshot, generate_insights, get_wordcloud, get_domain_detail,
    initialize_analytics,
)
from backend.link_assistant import preview_links, commit_links
from backend.domain_service import (
    analyze_domains, request_domain_scan, start_domain_watcher,
    get_suggestions_enriched, apply_suggestion, dismiss_suggestion,
    get_domain_dashboard, undo_last_action, enrich_suggestion,
    wake_domain_watcher,
)
from backend.scraper import extract_metadata, normalize_url
from backend.seed_data import seed_sample_links
from backend.ollama_service import ollama_service
from backend.chat_assistant import process_chat_message

def get_frontend_dir():
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        frontend_path = os.path.join(base_dir, "frontend")
        if os.path.exists(frontend_path):
            return frontend_path
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

FRONTEND_DIR = get_frontend_dir()

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)

# Lightweight API telemetry. Static assets and very frequent health reads are
# excluded; every functional API call is measured.
_ANALYTICS_EXCLUDED = {
    "/api/status",
    "/api/telemetry/event",
    "/api/domains/dashboard",
    "/api/analytics/overview",
    "/api/wordcloud",
    "/api/ollama/status",
}

@app.before_request
def _analytics_start_timer():
    g._analytics_started = time.time()

@app.after_request
def _analytics_log_request(response):
    try:
        path = request.path or ""
        if path.startswith("/api/") and path not in _ANALYTICS_EXCLUDED:
            duration = (time.time() - getattr(g, "_analytics_started", time.time())) * 1000
            log_analytics_event(
                "api_request",
                action=request.method,
                metadata={
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(duration, 1),
                },
            )
    except Exception as e:
        print(f"[Analytics] Request log warning: {e}")
    return response

# Snapshot BEFORE migrations: upgrading can add/alter columns and we always
# want a copy of the last known-good database.
if os.path.exists(DB_PATH):
    create_auto_backup("pre_startup")

# Initialize database, auto-migrations and seeds
init_db()
seed_sample_links()

# Snapshot on every startup: even a catastrophic failure leaves a recent copy.
create_auto_backup("startup")

initialize_analytics()

# Background domain watcher (can be disabled for automated tests).
if os.environ.get("PAGENEITOR_DISABLE_WATCHER") != "1":
    start_domain_watcher()

# Graceful shutdown snapshot (best effort).
import atexit
atexit.register(create_auto_backup, "shutdown")

# Auto-start Ollama if local binary exists in root
if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "ollama.exe")):
    try:
        ok, msg = ollama_service.start_ollama()
        print(f"[Ollama] Local root binary detected: {msg}")
    except Exception as e:
        print(f"[Ollama] Auto-start warning: {e}")

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(FRONTEND_DIR, path)

# --- General Endpoints ---

@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "app": "Pageneitor", "version": "3.9.0", "db_path": DB_PATH})

@app.route("/api/db/info", methods=["GET"])
def db_info():
    return jsonify(get_db_info())

@app.route("/api/stats", methods=["GET"])
def stats():
    return jsonify(get_stats())

@app.route("/api/gamification", methods=["GET"])
def gamification():
    return jsonify(get_gamification())

@app.route("/api/analytics", methods=["GET"])
def analytics():
    return jsonify(get_analytics())

# --- Local Analytics, KPIs & Word Cloud ---

def _scrub_telemetry(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(x in lowered for x in ("password", "passwd", "secret", "token", "credential")):
                continue
            result[key] = _scrub_telemetry(item)
        return result
    if isinstance(value, list):
        return [_scrub_telemetry(v) for v in value[:50]]
    return value

@app.route("/api/telemetry/event", methods=["POST"])
def telemetry_event():
    data = request.json or {}
    log_analytics_event(
        event_type=(data.get("event_type") or "ui_event")[:80],
        action=(data.get("action") or "")[:80],
        entity_type=(data.get("entity_type") or "")[:80],
        entity_id=(data.get("entity_id") or "")[:120],
        metadata=_scrub_telemetry(data.get("metadata") or {}),
        session_id=data.get("session_id") or "",
    )
    return jsonify({"success": True})

@app.route("/api/analytics/overview", methods=["GET"])
def analytics_overview():
    force = request.args.get("force", "false").lower() == "true"
    return jsonify(compute_snapshot(force=force))

@app.route("/api/analytics/insights", methods=["POST"])
def analytics_insights():
    data = request.json or {}
    return jsonify(generate_insights(force=bool(data.get("force"))))

@app.route("/api/analytics/events", methods=["GET"])
def analytics_events():
    limit = request.args.get("limit", 250, type=int)
    event_type = request.args.get("event_type")
    return jsonify(get_analytics_events(limit=limit, event_type=event_type))

@app.route("/api/wordcloud", methods=["GET"])
def visual_wordcloud():
    force = request.args.get("force", "false").lower() == "true"
    return jsonify(get_wordcloud(force=force))

@app.route("/api/domains/detail", methods=["GET"])
def domains_detail():
    root = request.args.get("root_domain", type=str)
    if not root:
        return jsonify({"error": "Dominio requerido"}), 400
    detail = get_domain_detail(root)
    if not detail:
        return jsonify({"error": "Dominio no encontrado"}), 404
    return jsonify(detail)

# --- Link insertion assistant ---

@app.route("/api/links/assistant/preview", methods=["POST"])
def links_assistant_preview():
    data = request.json or {}
    text = data.get("text") or ""
    urls = data.get("urls")
    if isinstance(urls, list) and urls:
        text = "\n".join(str(u) for u in urls)
    if not text.strip():
        return jsonify({"success": False, "error": "Pega una o varias URLs."}), 400
    result = preview_links(text, use_llm=data.get("use_llm", True))
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/links/assistant/commit", methods=["POST"])
def links_assistant_commit():
    data = request.json or {}
    items = data.get("items") or []
    result = commit_links(
        items,
        accept_new_categories=data.get("accept_new_categories", True),
        accept_new_profiles=data.get("accept_new_profiles", True),
        skip_duplicates=data.get("skip_duplicates", True),
    )
    if result.get("created_count") or result.get("skipped_count") or result.get("error_count"):
        request_domain_scan(2.0)
    return jsonify(result)

# --- Persistent Floating Assistant ---

@app.route("/api/chat/sessions", methods=["GET", "POST"])
def chat_sessions():
    if request.method == "POST":
        data = request.json or {}
        created = create_chat_session(data.get("title"))
        return jsonify(created), 201
    return jsonify(get_chat_sessions())

@app.route("/api/chat/sessions/<int:session_id>", methods=["GET", "PUT", "DELETE"])
def chat_session_detail(session_id):
    if request.method == "GET":
        session = get_chat_session(session_id)
        if not session:
            return jsonify({"error": "Conversación no encontrada"}), 404
        return jsonify(session)

    if request.method == "PUT":
        data = request.json or {}
        ok = rename_chat_session(session_id, data.get("title"))
        return jsonify({"success": ok})

    ok = delete_chat_session(session_id)
    return jsonify({"success": ok})

@app.route("/api/chat", methods=["POST"])
def chat_message():
    data = request.json or {}
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    if not message:
        return jsonify({"error": "El mensaje está vacío"}), 400

    try:
        result = process_chat_message(message, session_id=session_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[Chat] Error: {e}")
        return jsonify({"error": "No se pudo procesar el mensaje del asistente"}), 500

# --- Domain grouping, LLM suggestions & undo ---

@app.route("/api/domains/dashboard", methods=["GET"])
def domains_dashboard():
    return jsonify(get_domain_dashboard())

@app.route("/api/domains/groups", methods=["GET"])
def domains_groups():
    return jsonify(get_domain_groups())

@app.route("/api/domains/suggestions", methods=["GET"])
def domains_suggestions():
    status = request.args.get("status", "pending")
    unread = request.args.get("unread", "false").lower() == "true"
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_suggestions_enriched(status=status, unread_only=unread, limit=limit))

@app.route("/api/domains/suggestions/<int:suggestion_id>", methods=["GET"])
def domains_suggestion_detail(suggestion_id):
    suggestion = enrich_suggestion(get_domain_suggestion(suggestion_id))
    if not suggestion:
        return jsonify({"error": "Sugerencia no encontrada"}), 404
    return jsonify(suggestion)

@app.route("/api/domains/suggestions/<int:suggestion_id>/apply", methods=["POST"])
def domains_suggestion_apply(suggestion_id):
    result = apply_suggestion(suggestion_id)
    if not result.get("success"):
        return jsonify(result), 400
    request_domain_scan(3.0)
    return jsonify(result)

@app.route("/api/domains/suggestions/<int:suggestion_id>/dismiss", methods=["POST"])
def domains_suggestion_dismiss(suggestion_id):
    return jsonify(dismiss_suggestion(suggestion_id))

@app.route("/api/domains/suggestions/read", methods=["POST"])
def domains_suggestions_read():
    data = request.json or {}
    mark_domain_suggestions_read(data.get("ids"))
    return jsonify({"success": True, "counts": count_pending_domain_suggestions()})

@app.route("/api/domains/settings", methods=["GET", "POST"])
def domains_settings():
    if request.method == "POST":
        data = request.json or {}
        settings = set_domain_settings(data)
        wake_domain_watcher()
        return jsonify({"success": True, "settings": settings})
    return jsonify(get_domain_settings())

@app.route("/api/domains/scan", methods=["POST"])
def domains_scan():
    data = request.json or {}
    if data.get("wait"):
        return jsonify(analyze_domains(force=True, use_llm=data.get("use_llm", True)))
    request_domain_scan(0.0)
    return jsonify({"success": True, "started": True})

@app.route("/api/domains/merge", methods=["POST"])
def domains_merge():
    data = request.json or {}
    root = data.get("root_domain")
    main_id = data.get("main_link_id")
    link_ids = data.get("link_ids") or []
    if not root or not main_id or len(link_ids) < 2:
        return jsonify({"error": "Datos de fusión incompletos"}), 400
    result = apply_domain_merge(root, main_id, link_ids, reason=data.get("reason", "manual"))
    if not result.get("success"):
        return jsonify(result), 400
    request_domain_scan(3.0)
    return jsonify(result)

@app.route("/api/domains/undo", methods=["POST"])
def domains_undo():
    result = undo_last_action()
    if not result.get("success"):
        return jsonify(result), 400
    request_domain_scan(3.0)
    return jsonify(result)

@app.route("/api/domains/actions", methods=["GET"])
def domains_actions():
    return jsonify(get_domain_action_log(30))

@app.route("/api/domains/open-all", methods=["POST"])
def domains_open_all():
    data = request.json or {}
    root = data.get("root_domain")
    if not root:
        return jsonify({"error": "Dominio requerido"}), 400
    group = next((g for g in get_domain_groups() if g["root_domain"] == root), None)
    if not group:
        return jsonify({"error": "Grupo no encontrado"}), 404

    opened = 0
    for link in group["links"]:
        try:
            webbrowser.open(link["url"])
            update_link(
                link["id"],
                visit_count=(link.get("visit_count") or 0) + 1,
                is_read=1,
            )
            opened += 1
        except Exception:
            pass

    event = add_gamification_event("open_link", xp_gain=min(200, opened * 25))
    return jsonify({"success": True, "opened_count": opened, "_gamification": event})

# --- Profiles CRUD ---

@app.route("/api/profiles", methods=["GET", "POST"])
def profiles():
    if request.method == "POST":
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Nombre de perfil es requerido"}), 400
        color = data.get("color", "#3b82f6")
        icon = data.get("icon", "fa-user")
        description = data.get("description", "")
        res = add_profile(name, color, icon, description)
        return jsonify(res), 201
    return jsonify(get_profiles())

@app.route("/api/profiles/<int:pid>", methods=["PUT", "DELETE"])
def profile_detail(pid):
    if request.method == "PUT":
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Nombre requerido"}), 400
        res = update_profile(pid, name, data.get("color"), data.get("icon"), data.get("description"))
        return jsonify(res)
    elif request.method == "DELETE":
        success = delete_profile(pid)
        return jsonify({"success": success})

# --- Categories CRUD ---

@app.route("/api/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Nombre de categoría es requerido"}), 400
        color = data.get("color", "#8b5cf6")
        icon = data.get("icon", "fa-folder")
        res = add_category(name, color, icon)
        return jsonify(res), 201
    return jsonify(get_categories())

@app.route("/api/categories/<int:cid>", methods=["PUT", "DELETE"])
def category_detail(cid):
    if request.method == "PUT":
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Nombre requerido"}), 400
        res = update_category(cid, name, data.get("color"), data.get("icon"))
        return jsonify(res)
    elif request.method == "DELETE":
        success = delete_category(cid)
        return jsonify({"success": success})

# --- Ollama AI Local Endpoints ---

@app.route("/api/ollama/status", methods=["GET"])
def ollama_status():
    return jsonify(ollama_service.get_status())

@app.route("/api/ollama/start", methods=["POST"])
def ollama_start():
    ok, msg = ollama_service.start_ollama()
    return jsonify({"success": ok, "message": msg, "status": ollama_service.get_status()})

@app.route("/api/ollama/config", methods=["POST"])
def ollama_config():
    data = request.json or {}
    status = ollama_service.set_config(data.get("host"), data.get("model"))
    return jsonify(status)

@app.route("/api/ollama/cyclic-tip", methods=["POST"])
def ollama_tip():
    data = request.json or {}
    tip = ollama_service.generate_cyclic_tip(data)
    return jsonify(tip)

# --- Links CRUD ---

@app.route("/api/scrape", methods=["POST"])
def scrape_url():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL no proporcionada"}), 400
    meta = extract_metadata(url)
    return jsonify(meta)

@app.route("/api/links", methods=["GET", "POST"])
def links():
    if request.method == "POST":
        data = request.json or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "La URL es obligatoria"}), 400

        auto_meta = extract_metadata(url)
        title = data.get("title") or auto_meta["title"]
        description = data.get("description") if "description" in data else auto_meta["description"]
        thumbnail_url = data.get("thumbnail_url") if "thumbnail_url" in data else auto_meta["thumbnail_url"]
        favicon_url = data.get("favicon_url") if "favicon_url" in data else auto_meta["favicon_url"]
        domain = auto_meta["domain"]
        category_id = data.get("category_id") or auto_meta["category_id"]
        profile_id = data.get("profile_id")
        tags = data.get("tags") or auto_meta["suggested_tags"]
        credentials = data.get("credentials") or []
        sublinks = data.get("sublinks") or []
        notes = data.get("notes", "")

        new_link = add_link(
            url=auto_meta["url"],
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            favicon_url=favicon_url,
            domain=domain,
            category_id=category_id,
            profile_id=profile_id,
            tags=tags,
            credentials=credentials,
            sublinks=sublinks,
            notes=notes
        )
        request_domain_scan(2.0)
        return jsonify(new_link), 201

    # GET request with filtering
    profile_id = request.args.get("profile_id", type=int)
    category_id = request.args.get("category_id", type=int)
    query = request.args.get("q", type=str)
    favorite_only = request.args.get("favorite", "false").lower() == "true"
    unread_only = request.args.get("unread", "false").lower() == "true"
    archived = request.args.get("archived", "false").lower() == "true"
    root_domain = request.args.get("root_domain", type=str)

    all_links = get_all_links(
        profile_id=profile_id,
        category_id=category_id,
        query=query,
        favorite_only=favorite_only,
        unread_only=unread_only,
        archived=archived,
        root_domain=root_domain
    )
    return jsonify(all_links)

@app.route("/api/links/<int:link_id>", methods=["GET", "PUT", "DELETE"])
def link_detail(link_id):
    if request.method == "GET":
        link = get_link_by_id(link_id)
        if not link:
            return jsonify({"error": "Enlace no encontrado"}), 404
        return jsonify(link)

    elif request.method == "PUT":
        data = request.json or {}
        updated = update_link(link_id, **data)
        if not updated:
            return jsonify({"error": "Error al actualizar enlace"}), 400
        request_domain_scan(3.0)
        return jsonify(updated)

    elif request.method == "DELETE":
        result = delete_link(link_id)
        request_domain_scan(2.0)
        return jsonify(result)

@app.route("/api/links/<int:link_id>/open", methods=["POST"])
def open_link_in_browser(link_id):
    link = get_link_by_id(link_id)
    if not link:
        return jsonify({"error": "Enlace no encontrado"}), 404
    
    update_link(link_id, visit_count=(link.get("visit_count", 0) + 1), is_read=1)
    webbrowser.open(link["url"])
    event = add_gamification_event("open_link", xp_gain=35)
    return jsonify({"success": True, "url": link["url"], "_gamification": event})

# --- Multi-Account Credentials Vault Endpoints ---

@app.route("/api/links/<int:link_id>/credentials", methods=["GET", "POST"])
def link_credentials(link_id):
    link = get_link_by_id(link_id)
    if not link:
        return jsonify({"error": "Enlace no encontrado"}), 404

    if request.method == "POST":
        data = request.json or {}
        label = data.get("label", "Cuenta")
        username = data.get("username", "")
        password = data.get("password", "")
        notes = data.get("notes", "")

        res = add_credential_to_link(link_id, label, username, password, notes)
        return jsonify(res), 201

    return jsonify(link.get("credentials", []))

@app.route("/api/links/<int:link_id>/credentials/<cred_id>", methods=["PUT", "DELETE"])
def link_credential_detail(link_id, cred_id):
    if request.method == "PUT":
        data = request.json or {}
        res = update_credential_in_link(
            link_id, cred_id,
            label=data.get("label", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            notes=data.get("notes", "")
        )
        return jsonify(res)
    elif request.method == "DELETE":
        res = delete_credential_from_link(link_id, cred_id)
        return jsonify(res)

# --- Sublinks / Associated Tabs Endpoints ---

@app.route("/api/links/<int:link_id>/sublinks", methods=["GET", "POST"])
def link_sublinks(link_id):
    link = get_link_by_id(link_id)
    if not link:
        return jsonify({"error": "Enlace no encontrado"}), 404

    if request.method == "POST":
        data = request.json or {}
        title = data.get("title", "")
        url = data.get("url", "")
        if not url:
            return jsonify({"error": "URL requerida"}), 400

        res = add_sublink_to_link(link_id, title, url)
        return jsonify(res), 201

    return jsonify(link.get("sublinks", []))

@app.route("/api/links/<int:link_id>/sublinks/batch", methods=["POST"])
def link_sublinks_batch(link_id):
    data = request.json or {}
    text = data.get("text", "")
    res = batch_add_sublinks(link_id, text)
    if not res:
        return jsonify({"error": "Enlace no encontrado"}), 404
    return jsonify(res), 201

@app.route("/api/links/<int:link_id>/sublinks/<sub_id>/toggle-read", methods=["PUT"])
def link_sublink_toggle(link_id, sub_id):
    res = toggle_sublink_read(link_id, sub_id)
    if not res:
        return jsonify({"error": "No encontrado"}), 404
    return jsonify(res)

@app.route("/api/links/<int:link_id>/sublinks/<sub_id>/open", methods=["POST"])
def link_sublink_open(link_id, sub_id):
    link = get_link_by_id(link_id)
    if not link:
        return jsonify({"error": "Enlace no encontrado"}), 404
    
    sublinks = link.get("sublinks", [])
    target_sub = next((s for s in sublinks if s.get("id") == sub_id), None)
    if not target_sub:
        return jsonify({"error": "Sub-enlace no encontrado"}), 404

    webbrowser.open(target_sub["url"])
    toggle_sublink_read(link_id, sub_id)
    event = add_gamification_event("open_link", xp_gain=25)
    return jsonify({"success": True, "url": target_sub["url"], "_gamification": event})

@app.route("/api/links/<int:link_id>/sublinks/open-all", methods=["POST"])
def link_sublink_open_all(link_id):
    link = get_link_by_id(link_id)
    if not link:
        return jsonify({"error": "Enlace no encontrado"}), 404
    
    sublinks = link.get("sublinks", [])
    for s in sublinks:
        try:
            webbrowser.open(s["url"])
            s["is_read"] = 1
        except Exception:
            pass

    update_link(link_id, sublinks=sublinks)
    event = add_gamification_event("open_link", xp_gain=len(sublinks) * 15 + 30)
    return jsonify({"success": True, "opened_count": len(sublinks), "_gamification": event})

@app.route("/api/links/<int:link_id>/sublinks/<sub_id>", methods=["DELETE"])
def link_sublink_delete(link_id, sub_id):
    res = delete_sublink_from_link(link_id, sub_id)
    if not res:
        return jsonify({"error": "No encontrado"}), 404
    return jsonify(res)

@app.route("/api/batch-import", methods=["POST"])
def batch_import():
    data = request.json or {}
    raw_text = data.get("text", "")
    profile_id = data.get("profile_id")
    category_id = data.get("category_id")

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    imported = []

    for line in lines:
        if line.startswith("http://") or line.startswith("https://") or "." in line:
            try:
                meta = extract_metadata(line)
                new_l = add_link(
                    url=meta["url"],
                    title=meta["title"],
                    description=meta["description"],
                    thumbnail_url=meta["thumbnail_url"],
                    favicon_url=meta["favicon_url"],
                    domain=meta["domain"],
                    category_id=category_id or meta["category_id"],
                    profile_id=profile_id,
                    tags=meta["suggested_tags"]
                )
                imported.append(new_l)
            except Exception as e:
                print(f"[Import] Error importing {line}: {e}")

    request_domain_scan(2.0)
    batch_event = add_gamification_event("batch_import", xp_gain=len(imported) * 20 + 50)
    return jsonify({"imported_count": len(imported), "items": imported, "_gamification": batch_event})

# --- Backup, Export & Restore Endpoints (Zero Data Loss) ---

def _attach_cleanup(response, path):
    """Deletes an exported temp file only after the file was fully sent."""
    def cleanup():
        try:
            os.remove(path)
        except Exception:
            pass
    try:
        response.call_on_close(cleanup)
    except Exception:
        pass
    return response

@app.route("/api/backup/export-db", methods=["GET"])
def export_db_file():
    """
    Downloads a CONSISTENT snapshot of the database.
    Raw copying pageneitor.db can lose recent WAL transactions, so we use
    SQLite's online backup API.
    """
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Base de datos no encontrada"}), 404

    try:
        snapshot = create_db_snapshot()
    except Exception as e:
        return jsonify({"error": f"No se pudo crear el respaldo: {e}"}), 500

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pageneitor_backup_{timestamp}.db"
    response = send_file(snapshot, as_attachment=True, download_name=filename,
                         mimetype="application/x-sqlite3")
    return _attach_cleanup(response, snapshot)

@app.route("/api/backup/export-json", methods=["GET"])
def export_json_file():
    """Generates and downloads portable JSON backup."""
    backup_data = export_database_json()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pageneitor_backup_{timestamp}.json"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
    try:
        json.dump(backup_data, tmp, ensure_ascii=False, indent=2)
    finally:
        tmp.close()

    response = send_file(tmp.name, as_attachment=True, download_name=filename,
                         mimetype="application/json")
    return _attach_cleanup(response, tmp.name)

@app.route("/api/backup/import-json", methods=["POST"])
def import_json_data():
    """Imports JSON backup data. Mode can be 'merge' or 'replace'."""
    data = request.json or {}
    mode = data.get("mode", "merge")
    # Accept both shapes: {backup_data: {...}} and the raw backup object.
    payload = data.get("backup_data") or data.get("payload") or data

    if not isinstance(payload, dict) or ("links" not in payload and "profiles" not in payload):
        return jsonify({"error": "Estructura de respaldo no válida"}), 400
    if mode not in ("merge", "replace"):
        return jsonify({"error": "Modo de importación no válido"}), 400

    try:
        res = import_database_json(payload, mode=mode)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    request_domain_scan(2.0)
    return jsonify(res)

@app.route("/api/backup/import-db", methods=["POST"])
def import_db_file():
    """Restores database from uploaded .db file."""
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    file = request.files['file']
    filename = (file.filename or "").lower()
    if not filename.endswith(('.db', '.sqlite', '.sqlite3')):
        return jsonify({"error": "El archivo debe ser una base de datos SQLite (.db)"}), 400

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    file.save(tmp.name)

    try:
        success, msg = restore_database_from_file(tmp.name)
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass

    if success:
        request_domain_scan(2.0)
    return jsonify({"success": success, "message": msg})

@app.route("/api/backup/create", methods=["POST"])
def create_backup_now():
    """Creates a manual, non-pruned backup snapshot."""
    try:
        path = create_manual_backup()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    if not path:
        return jsonify({"success": False, "error": "No se pudo crear la copia."}), 500
    return jsonify({
        "success": True,
        "filename": os.path.basename(path),
        "message": "Copia de seguridad creada correctamente."
    })

@app.route("/api/backup/on-close", methods=["POST"])
def backup_on_close():
    """Prunable safety snapshot when the desktop window closes."""
    path = create_auto_backup("close")
    return jsonify({"success": bool(path)})

@app.route("/api/backup/list-auto", methods=["GET"])
def list_auto_backups():
    return jsonify(get_auto_backups())

@app.route("/api/backup/restore-auto", methods=["POST"])
def restore_auto_backup():
    data = request.json or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "Nombre de archivo requerido"}), 400

    # Prevent path traversal: only a plain .db filename inside BACKUPS_DIR.
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.endswith(".db"):
        return jsonify({"error": "Nombre de archivo no válido"}), 400

    file_path = os.path.join(BACKUPS_DIR, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "La copia de seguridad no existe"}), 404

    success, msg = restore_database_from_file(file_path)
    if success:
        request_domain_scan(2.0)
    return jsonify({"success": success, "message": msg})

def run_server(port=5241, debug=False):
    app.run(host="127.0.0.1", port=port, debug=debug)

if __name__ == "__main__":
    run_server(debug=True)
