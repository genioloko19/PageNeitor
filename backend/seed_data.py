"""
Initial seed data generator for Pageneitor.
Populates rich initial links across various profiles and categories.
"""

from backend.database import get_connection, add_link

def seed_sample_links():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM links")
    count = cursor.fetchone()[0]
    conn.close()

    if count > 0:
        return

    sample_links = [
        {
            "url": "https://github.com/trending",
            "title": "GitHub Trending Repositories",
            "description": "Explora los repositorios, temas y desarrolladores en tendencia en GitHub hoy. Código abierto actualizado.",
            "thumbnail_url": "https://images.unsplash.com/photo-1618401471353-b98afee0b2eb?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://github.githubassets.com/favicons/favicon.svg",
            "domain": "github.com",
            "category_id": 1, # Desarrollo Web
            "profile_id": 4,  # Dev & Tech
            "tags": ["código", "open-source", "git", "repositorios"],
            "notes": "Revisar todos los viernes para ver qué herramientas nuevas han salido."
        },
        {
            "url": "https://figma.com",
            "title": "Figma: El estándar de diseño colaborativo de interfaces",
            "description": "Herramienta líder de diseño vectorial e interactivo para crear interfaces, prototipos y design systems en equipo.",
            "thumbnail_url": "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://static.figma.com/app/icon/1/favicon.ico",
            "domain": "figma.com",
            "category_id": 2, # Diseño & UI/UX
            "profile_id": 2,  # Trabajo
            "tags": ["diseño", "ui-ux", "prototipos", "vector"],
            "notes": "Espacio para los mockups del proyecto Pageneitor."
        },
        {
            "url": "https://huggingface.co/models",
            "title": "Hugging Face – The AI Community Building the Future",
            "description": "El hub central para modelos de machine learning, datasets y espacios demo interactivos.",
            "thumbnail_url": "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://huggingface.co/favicon.ico",
            "domain": "huggingface.co",
            "category_id": 3, # Inteligencia Artificial
            "profile_id": 3,  # Estudio / Investigación
            "tags": ["ia", "modelos", "transformers", "llm"],
            "notes": "Modelos ligeros open-source para procesamiento local."
        },
        {
            "url": "https://developer.mozilla.org/es/",
            "title": "MDN Web Docs - Recursos para desarrolladores web",
            "description": "Documentación abierta y oficial sobre tecnologías web: HTML, CSS, JavaScript y Web APIs.",
            "thumbnail_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://developer.mozilla.org/favicon-48x48.png",
            "domain": "developer.mozilla.org",
            "category_id": 4, # Documentación
            "profile_id": 4,  # Dev & Tech
            "tags": ["docs", "javascript", "css", "html5", "referencia"],
            "notes": "Guía fundamental de CSS Backdrop-filter y Web APIs."
        },
        {
            "url": "https://stripe.com/es",
            "title": "Stripe: Infraestructura financiera para internet",
            "description": "Millones de empresas de todos los tamaños usan el software de Stripe para aceptar pagos y gestionar negocios en línea.",
            "thumbnail_url": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://images.stripeassets.com/fzn2n1nzq965/30s1VqWW9WtAGiyCWnaPHq/008a52c0081dc6db454e3416670ffd56/favicon.ico",
            "domain": "stripe.com",
            "category_id": 5, # Finanzas & Negocios
            "profile_id": 2,  # Trabajo
            "tags": ["pagos", "finanzas", "facturación", "api"],
            "notes": "Plataforma de procesamiento para SaaS."
        },
        {
            "url": "https://notion.so",
            "title": "Notion – Tu espacio de trabajo conectado",
            "description": "El espacio de trabajo todo en uno para tus notas, tareas, wikis y bases de datos con IA integrada.",
            "thumbnail_url": "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?auto=format&fit=crop&w=800&q=80",
            "favicon_url": "https://www.notion.so/images/favicon.ico",
            "domain": "notion.so",
            "category_id": 7, # Herramientas
            "profile_id": 1,  # Personal
            "tags": ["productividad", "notas", "organización", "workspace"],
            "notes": "Tablero personal de pendientes y metas del año."
        }
    ]

    for item in sample_links:
        add_link(
            url=item["url"],
            title=item["title"],
            description=item["description"],
            thumbnail_url=item["thumbnail_url"],
            favicon_url=item["favicon_url"],
            domain=item["domain"],
            category_id=item["category_id"],
            profile_id=item["profile_id"],
            tags=item["tags"],
            notes=item["notes"]
        )
