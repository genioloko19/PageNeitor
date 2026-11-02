"""
Pageneitor floating assistant.

Responsibilities:
- Understand short Spanish requests about the user's own link bank.
- Search links by title, URL, tags, notes, category and profile.
- Return structured results (links, categories, profiles, stats) for the UI.
- Generate a short natural answer with local Ollama, or a deterministic
  fallback when Ollama is not running.
- Persist every conversation in SQLite (chat_sessions / chat_messages).
"""

import re
import unicodedata

from backend.database import (
    get_all_links,
    get_categories,
    get_profiles,
    get_stats,
    create_chat_session,
    get_chat_session,
    add_chat_message,
)
from backend.ollama_service import ollama_service
from backend.domain_service import (
    get_suggestions_enriched,
    get_domain_dashboard,
    enrich_suggestion,
    _choose_main_link,
    _link_preview,
)
from backend.database import get_domain_suggestion, get_domain_groups
from backend.link_assistant import preview_links, extract_urls


STOPWORDS = {
    "a", "al", "algo", "alguna", "algunas", "alguno", "algunos", "ante", "antes",
    "ayuda", "ayudame", "busca", "buscame", "buscar", "busco", "como", "con",
    "cual", "cuales", "cuando", "de", "del", "dame", "deja", "desde", "donde",
    "el", "ella", "ellas", "ellos", "en", "encuentra", "encuentrame", "ensename",
    "esa", "ese", "eso", "esta", "estan", "este", "esto", "estos", "favor",
    "favorito", "favoritos", "hay", "la", "las", "le", "les", "lista", "listar",
    "lo", "los", "me", "mi", "mis", "muestra", "muestrame", "muestro", "necesito",
    "o", "para", "pero", "por", "puedes", "que", "quiero", "relacionado",
    "relacionados", "ser", "sin", "sobre", "son", "su", "sus", "te", "tengo",
    "tiene", "tienes", "todo", "todos", "tu", "tus", "un", "una", "unas", "uno",
    "unos", "ver", "y", "ya", "tema", "temas", "categoria", "categorias", "perfil",
    "perfiles", "enlace", "enlaces", "cuanto", "cuanta", "cuantos", "cuantas",
    "resumen", "total", "balance", "estadistica", "estadisticas",
    "abre", "abrir", "abreme", "abrirme", "lanza", "abriendo",
    "hola", "buenas", "buenos", "dias", "tardes", "noches", "hey", "saludos",
    "tal", "quien", "eres", "haces", "que", "funciona", "sirves", "hacer",
    "comandos", "opciones", "instrucciones",
}


def _normalize(text):
    text = (text or "").lower().strip()
    text = text.replace("&", " y ").replace("/", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _words(text):
    return [w for w in _normalize(text).split() if w]


def _phrase_in(text, phrase):
    phrase = _normalize(phrase)
    if not phrase:
        return False
    pattern = r"(?<!\w)" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text) is not None


def _is_greeting(text):
    greetings = {
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
        "hey", "saludos", "que tal", "quien eres", "que haces",
    }
    return any(_phrase_in(text, g) for g in greetings) or text in greetings


def _is_help(text):
    help_words = [
        "que puedes hacer", "ayuda", "como funciona", "comandos",
        "para que sirves", "opciones", "instrucciones",
    ]
    return any(_phrase_in(text, h) for h in help_words)


def _brief_link(link):
    return {
        "id": link.get("id"),
        "title": link.get("title") or link.get("url"),
        "url": link.get("url"),
        "domain": link.get("domain"),
        "thumbnail_url": link.get("thumbnail_url") or "",
        "favicon_url": link.get("favicon_url") or "",
        "category_name": link.get("category_name") or "Sin categoría",
        "category_color": link.get("category_color") or "#8b5cf6",
        "profile_name": link.get("profile_name") or "General",
        "profile_color": link.get("profile_color") or "#6366f1",
        "tags": link.get("tags") or [],
        "notes": link.get("notes") or "",
        "is_read": link.get("is_read", 0),
        "is_favorite": link.get("is_favorite", 0),
        "credentials_count": len(link.get("credentials") or []),
        "sublinks_count": len(link.get("sublinks") or []),
    }


def _brief_category(category):
    return {
        "id": category.get("id"),
        "name": category.get("name"),
        "slug": category.get("slug"),
        "color": category.get("color") or "#8b5cf6",
        "icon": category.get("icon") or "fa-folder",
        "link_count": category.get("link_count", 0),
    }


def _brief_profile(profile):
    return {
        "id": profile.get("id"),
        "name": profile.get("name"),
        "slug": profile.get("slug"),
        "color": profile.get("color") or "#6366f1",
        "icon": profile.get("icon") or "fa-user",
        "link_count": profile.get("link_count", 0),
    }


def _match_named(text, items):
    """Finds the best category/profile mentioned in the message."""
    tokens = [w for w in text.split() if len(w) >= 2 and w not in STOPWORDS]
    best = None
    best_score = 0

    for item in items:
        name = _normalize(item.get("name", ""))
        slug = _normalize(item.get("slug", ""))
        if not name and not slug:
            continue

        score = 0
        if name and _phrase_in(text, name):
            score = 100 + len(name)
        elif slug and len(slug) >= 3 and _phrase_in(text, slug):
            score = 90 + len(slug)
        else:
            name_words = name.split()
            for token in tokens:
                if len(token) < 2:
                    continue
                if token in name_words:
                    score = max(score, 40 + len(token))
                elif len(token) >= 4 and any(w.startswith(token) for w in name_words):
                    score = max(score, 30 + len(token))

        if score > best_score:
            best_score = score
            best = item

    return best


def _clean_query(text):
    intent_prefixes = (
        "categor", "tema", "perfil", "cuant", "favorit", "destacad", "pendient",
    )
    tokens = [
        w for w in text.split()
        if w not in STOPWORDS and len(w) >= 2 and not w.startswith(intent_prefixes)
    ]
    return " ".join(tokens).strip()


def _score_link(link, tokens, phrase=""):
    title = _normalize(link.get("title", ""))
    desc = _normalize(link.get("description", ""))
    tags = _normalize(" ".join(link.get("tags") or []))
    notes = _normalize(link.get("notes", ""))
    category = _normalize(link.get("category_name", ""))
    profile = _normalize(link.get("profile_name", ""))
    url = _normalize(link.get("url", ""))
    domain = _normalize(link.get("domain", ""))

    score = 0
    if phrase:
        if phrase in title:
            score += 18
        if phrase in tags:
            score += 14
        if phrase in category:
            score += 10
        if phrase in desc:
            score += 6
        if phrase in notes:
            score += 5
        if phrase in url or phrase in domain:
            score += 6

    for token in tokens:
        if token in title:
            score += 8
        if token in tags:
            score += 6
        if token in category:
            score += 4
        if token in profile:
            score += 3
        if token in desc:
            score += 3
        if token in notes:
            score += 2
        if token in url or token in domain:
            score += 3

    return score


def _search_links(links, tokens, phrase=""):
    if not tokens and not phrase:
        return []
    scored = []
    for link in links:
        score = _score_link(link, tokens, phrase)
        if score > 0:
            scored.append((score, link.get("id", 0), link))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [item[2] for item in scored]


def _suggestions_for_links(categories, limit=4):
    chips = []
    for category in categories[:limit]:
        chips.append(f"enlaces de {category['name']}")
    chips.extend(["Ver perfiles", "Resumen de mi banco"])
    return chips


def _build_context(result, stats):
    lines = [f"Tipo de resultado: {result['type']}"]

    if result.get("links"):
        lines.append(f"Enlaces encontrados: {len(result['links'])}")
        for link in result["links"][:8]:
            lines.append(
                f"- {link['title']} | {link['domain']} | tema: {link['category_name']} "
                f"| perfil: {link['profile_name']} | {link['url']}"
            )
    if result.get("categories"):
        lines.append(f"Temas disponibles: {len(result['categories'])}")
        for category in result["categories"][:10]:
            lines.append(f"- {category['name']} ({category['link_count']} enlaces)")
    if result.get("profiles"):
        lines.append(f"Perfiles disponibles: {len(result['profiles'])}")
        for profile in result["profiles"][:10]:
            lines.append(f"- {profile['name']} ({profile['link_count']} enlaces)")
    if result.get("stats"):
        s = result["stats"]
        lines.append(
            f"Totales: {s.get('total_active', 0)} enlaces, "
            f"{s.get('total_favorites', 0)} favoritos, "
            f"{s.get('total_unread', 0)} pendientes, "
            f"{s.get('total_categories', 0)} temas, "
            f"{s.get('total_profiles', 0)} perfiles."
        )

    lines.append("Respuesta base recomendada: " + result["answer"])
    return "\n".join(lines)


def _result(kind, answer, links=None, categories=None, profiles=None, stats=None,
            suggestions=None, llm_allowed=False, domain_groups=None,
            domain_suggestions=None, domain_action=None, link_preview=None):
    return {
        "type": kind,
        "answer": answer,
        "links": links or [],
        "categories": categories or [],
        "profiles": profiles or [],
        "stats": stats or {},
        "suggestions": suggestions or [],
        "llm_allowed": llm_allowed,
        "domain_groups": domain_groups or [],
        "domain_suggestions": domain_suggestions or [],
        "domain_action": domain_action,
        "link_preview": link_preview,
    }


def _count_text(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def _respond_to_message(message, categories, profiles, links, stats):
    text = _normalize(message)
    query = _clean_query(text)
    tokens = [w for w in text.split() if w not in STOPWORDS and len(w) >= 2]

    if _is_greeting(text) and not query:
        return _result(
            "greeting",
            "Hola. Soy tu asistente de Pageneitor: puedo buscar enlaces, mostrar temas, "
            "perfiles, dominios y sugerencias de Ollama. ¿Qué necesitas?",
            suggestions=["Ver categorías", "Ver perfiles", "Ver dominios", "Ver sugerencias"],
        )

    if _is_help(text) and not query:
        return _result(
            "help",
            "Puedo buscar enlaces, mostrar temas, perfiles y dominios, revisar sugerencias "
            "de Ollama y ayudarte a fusionar grupos. Ejemplo: «fusiona github.com» o «ver sugerencias».",
            suggestions=["Ver categorías", "Ver dominios", "Ver sugerencias", "Enlaces sin leer"],
        )

    words = text.split()

    # ---- Link insertion assistant ----
    urls_in_message = extract_urls(message)
    wants_insert = any(
        w.startswith(("inserta", "insertar", "guarda", "guardar", "agrega",
                      "agregar", "anade", "anadir", "añade", "añadir"))
        for w in words
    )
    if urls_in_message:
        preview = preview_links(message, use_llm=True)
        if preview.get("success"):
            count = len(preview.get("items") or [])
            new_taxonomy = bool(preview.get("new_categories") or preview.get("new_profiles"))
            return _result(
                "link_insert_preview",
                f"Detecté {_count_text(count, 'enlace', 'enlaces')}. Revisa la propuesta"
                + (" y decide si crear los temas/perfiles nuevos." if new_taxonomy else " y confirma para guardarlos."),
                link_preview=preview,
                suggestions=["Abrir asistente de enlaces", "Ver dominios"],
            )
        return _result(
            "link_insert_preview",
            preview.get("error") or "No pude preparar los enlaces.",
            suggestions=["Abrir asistente de enlaces", "Ayuda"],
        )

    if wants_insert:
        return _result(
            "link_insert_preview",
            "Pega una o varias URLs y las clasificaré antes de guardarlas. No guardaré nada sin tu confirmación.",
            suggestions=["Busca enlaces", "Ver dominios"],
        )

    # ---- Domain grouping / LLM suggestions intents ----
    wants_apply = any(w.startswith(("aplica", "aplicar", "ejecuta")) for w in words)
    wants_suggestions = (
        any(w.startswith(("sugerenc", "notificacion")) for w in words)
        and not wants_apply
    ) or _phrase_in(text, "cambios pendientes")
    wants_domains = any(w.startswith("dominio") for w in words) or _phrase_in(text, "por dominio")
    wants_undo = any(w.startswith(("deshaz", "deshacer", "revertir")) for w in words)
    wants_merge = any(w.startswith(("fusiona", "fusionar", "agrupa", "agrupar", "unifica", "unificar")) for w in words)

    if wants_suggestions:
        suggestions = get_suggestions_enriched(status="pending", limit=10)
        if not suggestions:
            return _result(
                "domain_suggestions",
                "No tienes sugerencias pendientes. Cuando detecte enlaces del mismo dominio, te avisaré.",
                suggestions=["Ver dominios", "Resumen de mi banco"],
            )
        return _result(
            "domain_suggestions",
            f"Tienes {_count_text(len(suggestions), 'sugerencia pendiente', 'sugerencias pendientes')}.",
            domain_suggestions=suggestions,
            suggestions=["Ver dominios", "Resumen de mi banco"],
        )

    if wants_domains:
        dashboard = get_domain_dashboard()
        groups = dashboard.get("groups") or []
        pending = dashboard.get("counts", {}).get("pending", 0)
        return _result(
            "domain_groups",
            f"Tienes {_count_text(len(groups), 'dominio agrupado', 'dominios agrupados')} "
            f"y {pending} sugerencia(s) pendiente(s).",
            domain_groups=groups,
            suggestions=["Ver sugerencias", "Resumen de mi banco"],
        )

    if wants_undo:
        actions = get_domain_dashboard().get("actions") or []
        last = next((a for a in actions if not a.get("undone")), None)
        if not last:
            return _result(
                "domain_undo",
                "No hay cambios recientes de dominios para deshacer.",
                suggestions=["Ver dominios"],
            )
        return _result(
            "domain_undo",
            "Puedo deshacer la última acción de dominios. Confirma para continuar.",
            domain_action={
                "action": "undo",
                "description": last.get("description") or "Deshacer última acción",
                "log_id": last.get("id"),
            },
            suggestions=["Ver dominios", "Ver sugerencias"],
        )

    if wants_apply:
        match = re.search(r"(?:sugerencia|n[uú]mero|numero)\s*#?(\d+)", text)
        if match:
            suggestion = get_domain_suggestion(int(match.group(1)))
            if suggestion and suggestion.get("status") == "pending":
                return _result(
                    "domain_suggestion_preview",
                    "Revisa la sugerencia y confirma para aplicarla.",
                    domain_action={
                        "action": "apply_suggestion",
                        "suggestion": enrich_suggestion(suggestion),
                    },
                    suggestions=["Ver sugerencias"],
                )
        return _result(
            "domain_suggestion_preview",
            "Dime el número de sugerencia que quieres aplicar. Puedes verlas con «ver sugerencias».",
            suggestions=["Ver sugerencias"],
        )

    if wants_merge:
        groups = get_domain_groups()
        matched = None
        for group in groups:
            root = group["root_domain"]
            if _phrase_in(text, root) or _phrase_in(text, root.split(".")[0]):
                matched = group
                break

        if matched:
            root = matched["root_domain"]
            pending = next(
                (s for s in get_suggestions_enriched(status="pending", limit=50)
                 if s.get("root_domain") == root and s.get("action") == "merge_group"),
                None
            )
            if pending:
                return _result(
                    "domain_suggestion_preview",
                    "Ya tengo una sugerencia preparada para este dominio. Revísala y confirma.",
                    domain_action={
                        "action": "apply_suggestion",
                        "suggestion": pending,
                    },
                    suggestions=["Ver dominios", "Ver sugerencias"],
                )

            main = _choose_main_link(matched["links"])
            link_ids = [l["id"] for l in matched["links"]]
            return _result(
                "domain_merge_preview",
                f"Puedo fusionar {_count_text(len(link_ids), 'enlace', 'enlaces')} de "
                f"«{root}» en «{main.get('title', root)}». Confirma para continuar.",
                domain_action={
                    "action": "merge_preview",
                    "root_domain": root,
                    "main_link_id": main["id"],
                    "main_link": _link_preview(main),
                    "link_ids": link_ids,
                    "links": [_link_preview(l) for l in matched["links"]],
                    "reason": f"Fusión manual del grupo {root}",
                },
                suggestions=["Ver dominios", "Ver sugerencias"],
            )

        return _result(
            "domain_merge_preview",
            "No encontré ese dominio en tu banco. Prueba con «ver dominios».",
            suggestions=["Ver dominios", "Ver sugerencias"],
        )

    wants_unread = (
        any(_phrase_in(text, x) for x in ["sin leer", "por leer"])
        or any(w.startswith("pendient") for w in words)
    )
    wants_fav = any(w.startswith("favorit") or w.startswith("destacad") for w in words)

    # A specific category or profile mentioned by name.
    matched_category = _match_named(text, categories)
    matched_profile = _match_named(text, profiles)

    if matched_category:
        matched = [l for l in links if l.get("category_id") == matched_category["id"]]
        if wants_unread:
            matched = [l for l in matched if not l.get("is_read")]
        if wants_fav:
            matched = [l for l in matched if l.get("is_favorite")]
        if tokens:
            ranked = _search_links(matched, tokens, query)
            if ranked:
                matched = ranked
        matched.sort(key=lambda l: (-(l.get("is_favorite") or 0), -(l.get("id") or 0)))
        briefs = [_brief_link(l) for l in matched[:15]]
        answer = (
            f"Encontré {_count_text(len(briefs), 'enlace', 'enlaces')} en «{matched_category['name']}»."
            if briefs else f"No hay enlaces en «{matched_category['name']}» con ese filtro."
        )
        return _result(
            "links", answer, links=briefs, categories=[_brief_category(matched_category)],
            suggestions=_suggestions_for_links(categories),
        )

    if matched_profile:
        matched = [l for l in links if l.get("profile_id") == matched_profile["id"]]
        if wants_unread:
            matched = [l for l in matched if not l.get("is_read")]
        if wants_fav:
            matched = [l for l in matched if l.get("is_favorite")]
        if tokens:
            ranked = _search_links(matched, tokens, query)
            if ranked:
                matched = ranked
        matched.sort(key=lambda l: (-(l.get("is_favorite") or 0), -(l.get("id") or 0)))
        briefs = [_brief_link(l) for l in matched[:15]]
        answer = (
            f"Encontré {_count_text(len(briefs), 'enlace', 'enlaces')} en el perfil «{matched_profile['name']}»."
            if briefs else f"No hay enlaces en el perfil «{matched_profile['name']}»."
        )
        return _result(
            "links", answer, links=briefs, profiles=[_brief_profile(matched_profile)],
            suggestions=_suggestions_for_links(categories),
        )

    list_categories = any(w.startswith("categor") or w.startswith("tema") for w in words)
    list_profiles = any(w.startswith("perfil") for w in words)
    wants_stats = any(
        w.startswith("cuant") or w in ("resumen", "total", "balance")
        or w.startswith("estadistic")
        for w in words
    )

    if list_categories and not query:
        briefs = [_brief_category(c) for c in categories]
        return _result(
            "categories",
            f"Tienes {_count_text(len(briefs), 'tema', 'temas')}. Pulsa uno para ver sus enlaces.",
            categories=briefs,
            suggestions=["Ver perfiles", "Resumen de mi banco"],
        )

    if list_profiles and not query:
        briefs = [_brief_profile(p) for p in profiles]
        return _result(
            "profiles",
            f"Tienes {_count_text(len(briefs), 'perfil', 'perfiles')}. Pulsa uno para ver sus enlaces.",
            profiles=briefs,
            suggestions=["Ver categorías", "Resumen de mi banco"],
        )

    if wants_stats and (not query or query in ("banco", "datos", "pageneitor")):
        return _result(
            "stats",
            f"Tienes {stats.get('total_active', 0)} enlaces en "
            f"{stats.get('total_categories', 0)} temas y {stats.get('total_profiles', 0)} perfiles. "
            f"{stats.get('total_favorites', 0)} favoritos y {stats.get('total_unread', 0)} pendientes.",
            stats=stats,
            suggestions=["Ver categorías", "Ver perfiles", "Enlaces sin leer"],
        )

    if wants_unread or wants_fav:
        matched = links
        if wants_unread:
            matched = [l for l in matched if not l.get("is_read")]
        if wants_fav:
            matched = [l for l in matched if l.get("is_favorite")]
        if query:
            ranked = _search_links(matched, tokens, query)
            if ranked:
                matched = ranked
        matched.sort(key=lambda l: (-(l.get("is_favorite") or 0), -(l.get("id") or 0)))
        briefs = [_brief_link(l) for l in matched[:15]]
        label_singular = "pendiente" if wants_unread else "favorito"
        label_plural = "pendientes" if wants_unread else "favoritos"
        answer = (
            f"Tienes {_count_text(len(briefs), label_singular, label_plural)}."
            if briefs else f"No tienes enlaces {label_plural}."
        )
        return _result("links", answer, links=briefs, suggestions=_suggestions_for_links(categories))

    if query:
        matched = _search_links(links, tokens, query)
        briefs = [_brief_link(l) for l in matched[:15]]

        if briefs:
            category_names = []
            seen = set()
            for link in briefs:
                name = link["category_name"]
                if name not in seen:
                    seen.add(name)
                    category_names.append(name)
            chips = [f"enlaces de {name}" for name in category_names[:3]]
            chips.extend(["Ver perfiles", "Ver categorías"])
            return _result(
                "links",
                f"Encontré {_count_text(len(briefs), 'enlace', 'enlaces')} para «{query}».",
                links=briefs,
                suggestions=chips,
                llm_allowed=True,
            )

        # No links: suggest matching categories/profiles or generic actions.
        suggestions = ["Ver categorías", "Ver perfiles", "Enlaces sin leer"]
        return _result(
            "links",
            f"No encontré enlaces para «{query}». Prueba con otro término o revisa tus temas.",
            suggestions=suggestions,
        )

    # No specific query: useful overview instead of a generic answer.
    recent = sorted(links, key=lambda l: l.get("id") or 0, reverse=True)[:6]
    return _result(
        "summary",
        f"Tienes {stats.get('total_active', 0)} enlaces guardados. "
        f"Puedo buscar por tema, perfil, etiqueta o título.",
        links=[_brief_link(l) for l in recent],
        stats=stats,
        suggestions=["Ver categorías", "Ver perfiles", "Enlaces favoritos", "Enlaces sin leer"],
    )


def process_chat_message(message, session_id=None):
    """
    Persists the user message, builds grounded results, asks Ollama for a short
    phrasing when available, persists the assistant reply and returns everything.
    """
    message = (message or "").strip()
    if not message:
        raise ValueError("El mensaje está vacío.")

    session = get_chat_session(session_id) if session_id else None
    if not session:
        created = create_chat_session(message[:70])
        session_id = created["id"]

    user_message = add_chat_message(session_id, "user", message)

    categories = get_categories()
    profiles = get_profiles()
    links = get_all_links()
    stats = get_stats()
    stats.pop("db_path", None)

    result = _respond_to_message(message, categories, profiles, links, stats)

    # Give the LLM the last turns plus a strict, grounded context.
    session = get_chat_session(session_id) or {}
    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in session.get("messages", [])
        if m.get("role") in ("user", "assistant")
    ][-8:]

    source = "Pageneitor Assistant"
    final_answer = result["answer"]

    # The LLM is used to phrase normal search results naturally. For exact
    # counts, filters, themes and profiles we keep the deterministic answer so
    # the assistant can never contradict the user's real data.
    if result.get("llm_allowed"):
        llm = ollama_service.chat_reply(history, _build_context(result, stats))
        if llm and llm.get("text"):
            final_answer = llm["text"]
            source = llm.get("source") or source

    payload = {
        "type": result["type"],
        "links": result["links"],
        "categories": result["categories"],
        "profiles": result["profiles"],
        "stats": result["stats"],
        "suggestions": result["suggestions"],
        "domain_groups": result.get("domain_groups") or [],
        "domain_suggestions": result.get("domain_suggestions") or [],
        "domain_action": result.get("domain_action"),
        "link_preview": result.get("link_preview"),
        "source": source,
    }
    assistant_message = add_chat_message(session_id, "assistant", final_answer, payload)
    session = get_chat_session(session_id)

    return {
        "session_id": session_id,
        "session": session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "answer": final_answer,
        "source": source,
        "results": payload,
    }
