from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from mine.auth_utils import load_current_user, login_required, roles_required
from mine.catalog_modules import KNOWLEDGE_SERIES_MODULES as KNOWLEDGE_MODULES
from mine.config import Config
from mine.db import get_db
from mine.hero_showcase import _hero_showcase_slides
from mine.project_catalog import count_portfolio_projects
from mine.team_roster import group_roster_for_display, load_team_roster, roster_member_count, roster_xlsx_path

bp = Blueprint("main", __name__)

_DOMAIN_INFOGRAPHICS_DIR = Config.BASE_DIR / "static" / "img" / "domain"


def _hero_motifs():
    """Bento tiles for the landing hero — each opens an in-page insight modal with its own image."""
    return [
        {
            "slug": "pit",
            "label": "Open-pit operations",
            "desc": "Bench to stockpile",
            "accent": "cyan",
            "featured": True,
            "modal_title": "Open-pit mining operations",
            "modal_image": "img/hero-motifs/hero-motifs-open-pit.png",
            "modal_image_alt": "Electric shovel and terraced benches in an open-pit copper mine",
            "modal_lead": (
                "Open-pit mining strips ore from nested benches — drill and blast, load with electric "
                "shovels or loaders, then haul to crushers or stockpiles before the concentrator ever sees a tonne."
            ),
            "modal_points": [
                "Drilling & blasting: pattern design, vibration control, and muckpile profile for clean digging.",
                "Loading: shovel/truck matching, bucket fill, and grade control from blast to bucket.",
                "Haul roads & dumps: road maintenance, traffic rules, and stockpile blending for stable feed.",
            ],
        },
        {
            "slug": "copper",
            "label": "Copper value chain",
            "desc": "Pit to port",
            "accent": "copper",
            "featured": True,
            "modal_title": "Copper from ore to market",
            "modal_image": "img/hero-motifs/hero-motifs-copper.png",
            "modal_image_alt": "Copper cathode sheets and copper ore at a processing facility",
            "modal_lead": (
                "Copper metal begins as sulphide or oxide ore in the pit, becomes concentrate or cathode "
                "through milling and smelting, then ships to fabricators powering grids, construction, and clean energy."
            ),
            "modal_points": [
                "Mine: recoverable copper in sulphide (chalcopyrite) or oxide (chrysocolla) mineralisation.",
                "Concentrate & cathode: flotation concentrates (~25–35% Cu) or SX/EW cathode sheets.",
                "Markets: rod, wire, and components for electrification and industrial demand worldwide.",
            ],
        },
        {
            "slug": "haul",
            "label": "Haulage & fleet",
            "desc": "Ultra-class trucks",
            "accent": "teal",
            "modal_title": "Haulage & fleet operations",
            "modal_image": "img/hero-motifs/hero-motifs-haul-truck.png",
            "modal_image_alt": "Ultra-class mining haul truck loaded in an open pit",
            "modal_lead": (
                "Haul trucks move 200–400 tonnes per cycle between shovels and dump points — cycle time, "
                "payload, and queue time at load and dump are the levers that define pit productivity."
            ),
            "modal_points": [
                "Load: spot time, bucket pass count, and payload verification before the truck pulls away.",
                "Haul: speed limits, grade, and dispatch routing to minimise queue and fuel burn.",
                "Dump: crusher feed, waste dump, or stockpile — each destination has its own spotting rules.",
            ],
        },
        {
            "slug": "process",
            "label": "Processing",
            "desc": "Mill & flotation",
            "accent": "blue",
            "modal_title": "Mineral processing plant",
            "modal_image": "img/hero-motifs/hero-motifs-processing.png",
            "modal_image_alt": "Ball mills, flotation cells, and processing equipment in a concentrator",
            "modal_lead": (
                "The concentrator liberates copper minerals from waste rock — crush, grind, float, thicken, "
                "and filter until a saleable concentrate leaves the gate or feeds the smelter."
            ),
            "modal_points": [
                "Comminution: gyratory crushers and ball/SAG mills reduce ore to fine particles for liberation.",
                "Flotation: reagents and air bubbles separate copper sulphides into a rich concentrate.",
                "Dewatering & dispatch: thickeners and filters produce transportable concentrate for rail or port.",
            ],
        },
        {
            "slug": "safety",
            "label": "Safety culture",
            "desc": "People-first sites",
            "accent": "mint",
            "modal_title": "Safety on a working mine",
            "modal_image": "img/hero-motifs/hero-motifs-safety.png",
            "modal_image_alt": "Mining crew in hard hats and high-visibility gear at a site safety briefing",
            "modal_lead": (
                "Every shift starts with safety — critical controls for vehicles, energy isolation, working "
                "at height, and fatigue management keep teams safe around heavy equipment and high-risk tasks."
            ),
            "modal_points": [
                "Pre-start: toolbox talks, journey management, and verification of permits before work begins.",
                "Vehicle interaction: segregated roads, speed limits, and spotter rules where people and trucks meet.",
                "Learning: incidents and near-misses captured so the whole site improves, not just one crew.",
            ],
        },
    ]


def _serve_domain_infographic(filename: str):
    image = _DOMAIN_INFOGRAPHICS_DIR / filename
    if not image.is_file():
        abort(404)
    resp = send_file(image, mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


def _approved_list(module: str | None = None, limit: int = 50):
    db = get_db()
    q = """
        SELECT c.*, u.display_name AS author_name
        FROM content c
        JOIN users u ON u.id = c.author_id
        WHERE c.status = 'approved'
    """
    args: list = []
    if module:
        q += " AND c.module = ?"
        args.append(module)
    q += " ORDER BY c.updated_at DESC LIMIT ?"
    args.append(limit)
    return db.execute(q, args).fetchall()


def _count_approved_module(db, module: str) -> int:
    r = db.execute(
        "SELECT COUNT(*) AS c FROM content WHERE status = 'approved' AND module = ?",
        (module,),
    ).fetchone()
    return int(r["c"] or 0)


def _count_approved_knowledge_repo(db) -> int:
    keys = [m[0] for m in KNOWLEDGE_MODULES]
    ph = ",".join("?" * len(keys))
    r = db.execute(
        f"SELECT COUNT(*) AS c FROM content WHERE status = 'approved' AND module IN ({ph})",
        keys,
    ).fetchone()
    return int(r["c"] or 0)


def _landing_tile_stat(count: int, *, kind: str = "articles") -> str | None:
    """Human-readable stat line for Explore tiles; None hides the line when empty catalogue."""
    if kind == "eras":
        return f"{count} {'era' if count == 1 else 'eras'}"
    if kind == "topics":
        return f"{count} {'topic' if count == 1 else 'topics'}"
    if kind == "pending":
        return "Nothing pending" if count == 0 else f"{count} pending"
    if kind == "overview":
        return "Program overview"
    if kind == "articles":
        if count == 0:
            return None
        return f"{count} {'article' if count == 1 else 'articles'}"
    if count == 0:
        return None
    return f"{count} items"


def _landing_quick_tile(
    label: str,
    emoji: str,
    destination: str,
    count: int,
    user,
    *,
    public: bool = False,
    stat_kind: str = "articles",
    stat_line: str | None = None,
):
    """Build explore tile; guests are sent to login with ?next= for protected destinations."""
    requires_login = not public and not user
    href = destination
    if requires_login:
        href = url_for("auth.login", next=destination)
    if stat_line is None:
        stat_line = _landing_tile_stat(count, kind=stat_kind)
    return {
        "label": label,
        "emoji": emoji,
        "href": href,
        "count": count,
        "stat_text": stat_line,
        "requires_login": requires_login,
        "is_empty": stat_kind == "articles" and count == 0,
    }


def _knowledge_module_counts(db):
    keys = [m for m, _ in KNOWLEDGE_MODULES]
    placeholders = ",".join("?" * len(keys))
    rows = db.execute(
        f"""
        SELECT module, COUNT(*) AS c
        FROM content
        WHERE status = 'approved' AND module IN ({placeholders})
        GROUP BY module
        """,
        keys,
    ).fetchall()
    counts = {k: 0 for k in keys}
    for r in rows:
        counts[r["module"]] = r["c"]
    return counts


def _innovation_bucket_counts(rows):
    def blob(r):
        return f"{r['title'] or ''} {r['summary'] or ''} {r['body'] or ''}".lower()

    auto_kw = ("automation", "automated", "bot", "nlp", "routing", "script")
    proc_kw = ("process", "pipeline", "ci/cd", "cicd", "standard", "workflow")
    ai_kw = ("ai", " ml", "machine learning", "analytics", "model", "data science")

    def cnt(kws):
        n = 0
        for r in rows:
            b = blob(r)
            if any(k in b for k in kws):
                n += 1
        return n

    return [
        {"label": "Automation", "icon": "⚙", "count": cnt(auto_kw)},
        {"label": "Process improvement", "icon": "📋", "count": cnt(proc_kw)},
        {"label": "AI & analytics", "icon": "🤖", "count": cnt(ai_kw)},
    ]


# The Freeport story: eight narrative beats (dashboard + KYC §2.2 interactive timeline; landing stat count).
_FREEPORT_STORY = [
    {
        "y": "1912",
        "t": "The beginning",
        "b": "Sulfur, not copper: the Freeport Sulphur Company and the Frasch process on the Texas Gulf Coast.",
        "c": "var(--hex-blue)",
    },
    {
        "y": "1913–1950s",
        "t": "Diversification",
        "b": "A holding model spanning gas, light, oil, and foreign mining: manganese, nickel, potash, and more.",
        "c": "var(--color-warning)",
    },
    {
        "y": "1959–1972",
        "t": "Indonesia & Ertsberg",
        "b": "Dozy’s 1936 discovery; rights in 1960; 1972 production and a 109 km slurry pipeline in New Guinea.",
        "c": "var(--hex-teal)",
    },
    {
        "y": "1967–1981",
        "t": "McMoRan",
        "b": "McMoRan Oil and Gas, Freeport Minerals, and the 1981 merger creating Freeport-McMoRan Inc.",
        "c": "var(--color-success)",
    },
    {
        "y": "1988",
        "t": "Grasberg",
        "b": "One of the great copper-gold systems—redefining Freeport as a world-scale miner.",
        "c": "var(--hex-blue-dark)",
    },
    {
        "y": "2007",
        "t": "Phelps Dodge",
        "b": "A $25.9B combination adding Morenci and other assets among the world’s top copper companies.",
        "c": "var(--hex-teal-dark)",
    },
    {
        "y": "2012–2016",
        "t": "Recentering",
        "b": "Oil and gas build-out, then commodity stress—strategic return to the core copper business.",
        "c": "var(--color-warning)",
    },
    {
        "y": "2018–2026",
        "t": "Resilience and today",
        "b": "Indonesian partnership renewal and lease to 2041; copper for AI, electrification, and mine productivity.",
        "c": "var(--color-success)",
    },
]


SEARCH_XP_PLACEHOLDERS = [
    "Search programmes, case studies, and account briefings…",
    "Try “Hidden Mine”, “copper demand”, “onboarding playbook”…",
    "Find KYC entries, RFP snippets, and delivery artefacts…",
    "Explore innovation stories and Hall of Fame wins…",
]

SEARCH_XP_CATEGORIES = [
    {"value": "", "label": "All catalogue"},
    {"value": "kyc", "label": "KYC"},
    {"value": "kya", "label": "KYA"},
    {"value": "case_study", "label": "Case studies"},
    {"value": "projects", "label": "Projects"},
    {"value": "innovation", "label": "Innovation"},
    {"value": "training", "label": "Training"},
]

SEARCH_XP_FILTER_TAGS = [
    "Grasberg",
    "Hidden Mine",
    "Copper",
    "RFP snippets",
    "Hexaware Journey",
]


def _module_public_label(module: str) -> str:
    for mid, label in KNOWLEDGE_MODULES:
        if mid == module:
            return label
    aliases = {
        "projects": "Projects",
        "innovation": "Innovation",
        "training": "Training",
        "onboarding": "Onboarding",
        "hall_of_fame": "Hall of Fame",
    }
    return aliases.get(module, module.replace("_", " ").title())


def _repo_search_spotlight(db, limit: int = 6) -> list[dict]:
    rows = db.execute(
        """
        SELECT id, module, title
        FROM content
        WHERE status = 'approved' AND LENGTH(TRIM(COALESCE(title, ''))) > 0
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "module": r["module"],
            "module_label": _module_public_label(r["module"]),
        }
        for r in rows
    ]


def _knowledge_repo_feed_recent(db, limit: int = 40):
    keys = [m[0] for m in KNOWLEDGE_MODULES]
    ph = ",".join("?" * len(keys))
    return db.execute(
        f"""
        SELECT c.*, u.display_name AS author_name
        FROM content c
        JOIN users u ON u.id = c.author_id
        WHERE c.status = 'approved' AND c.module IN ({ph})
        ORDER BY c.updated_at DESC LIMIT ?
        """,
        [*keys, limit],
    ).fetchall()


def _active_team_count(db) -> int:
    """Prefer roster workbook count when the tracker file is present."""
    try:
        n = roster_member_count()
        if n > 0:
            return n
    except Exception:
        pass
    return int(
        db.execute("SELECT COUNT(*) AS c FROM users WHERE is_active = 1").fetchone()["c"] or 0
    )


def _landing_page_context(db, user):
    """Shared template context for marketing / platform overview (landing.html)."""
    featured = _approved_list(None, 6) if user else []
    knowledge_repo_n = _count_approved_knowledge_repo(db)
    projects_n = count_portfolio_projects(db)
    onboarding_n = _count_approved_module(db, "onboarding")
    innovation_n = _count_approved_module(db, "innovation")
    training_n = _count_approved_module(db, "training")
    fame_n = _count_approved_module(db, "hall_of_fame")
    team_n = _active_team_count(db)
    pending_n = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM content WHERE status = 'pending'"
        ).fetchone()["c"]
        or 0
    )

    journey_story_beats = len(_FREEPORT_STORY)

    portal_stats = {
        "knowledge_items": knowledge_repo_n,
        "projects": projects_n,
        "innovations": innovation_n,
        "team_members": int(team_n or 0),
    }

    if user and user["role"] == "admin":
        team_href = url_for("main.team_roster")
    elif user:
        team_href = url_for("main.team_roster")
    else:
        team_href = url_for("main.team_roster")

    kpi_links = {
        "knowledge": url_for("main.knowledge") if user else url_for("auth.login", next=url_for("main.knowledge")),
        "projects": url_for("projects.project_list") if user else url_for("auth.login", next=url_for("projects.project_list")),
        "innovations": url_for("main.innovation") if user else url_for("auth.login", next=url_for("main.innovation")),
        "team": team_href,
    }

    quick_access = [
        _landing_quick_tile(
            "Freeport–Hexaware Journey",
            "📜",
            url_for("main.journey"),
            journey_story_beats,
            user,
            public=True,
            stat_kind="eras",
        ),
        _landing_quick_tile(
            "Domain Knowledge",
            "⛏️",
            url_for("main.open_pit_copper_domain"),
            6,
            user,
            stat_kind="topics",
        ),
        _landing_quick_tile(
            "Programs & Projects",
            "📊",
            url_for("projects.project_list"),
            projects_n,
            user,
        ),
        _landing_quick_tile(
            "Knowledge repository",
            "📚",
            url_for("main.knowledge"),
            knowledge_repo_n,
            user,
        ),
        _landing_quick_tile(
            "Onboarding Kit",
            "💼",
            url_for("main.onboarding"),
            onboarding_n,
            user,
        ),
        _landing_quick_tile(
            "Innovation Center",
            "💡",
            url_for("main.innovation"),
            innovation_n,
            user,
        ),
        _landing_quick_tile(
            "Training Corner",
            "🎓",
            url_for("main.training"),
            training_n,
            user,
        ),
        _landing_quick_tile(
            "Hall of Fame",
            "🏆",
            url_for("main.hall_of_fame"),
            fame_n,
            user,
        ),
    ]

    if not user:
        quick_access.append(
            _landing_quick_tile(
                "Program map (KYC)",
                "🗺️",
                url_for("reference.fmi_kyc"),
                1,
                user,
                public=True,
                stat_kind="overview",
            )
        )

    if user and user["role"] in ("admin", "moderator"):
        quick_access.append(
            _landing_quick_tile(
                "Analytics & insight",
                "📈",
                url_for("admin.analytics"),
                pending_n,
                user,
                stat_kind="pending",
            )
        )
    elif user:
        quick_access.append(
            _landing_quick_tile(
                "Dashboard",
                "📈",
                url_for("main.dashboard"),
                knowledge_repo_n,
                user,
                stat_kind="articles",
            )
        )

    hero_showcase = _hero_showcase_slides()
    hero_motifs = _hero_motifs()

    value_cards = [
        {
            "slug": "delivery",
            "lens": "Operate & ship",
            "title": "Delivery teams",
            "tagline": "Reusable intelligence for sprint-ready delivery.",
            "peek": [
                "Reuse approved references in proposals",
                "See projects and innovations in sync",
                "Cut context switching across teams",
            ],
            "highlights": [
                "Trusted catalog entries you can cite in client artefacts",
                "Case studies aligned to programmes and approvals",
                "Cross-team snippets so everyone reads the same story",
            ],
        },
        {
            "slug": "leadership",
            "lens": "Steer & report",
            "title": "Leadership",
            "tagline": "The partnership narrative — outcomes and signals.",
            "peek": [
                "Journey timeline at a glance",
                "Breadth of the knowledge corpus",
                "Spotlight wins from the catalogue",
            ],
            "highlights": [
                "Freeport–Hexaware Journey for stewardship conversations",
                "Analytics and KPIs anchored to live catalogue totals",
                "Innovation and Hall of Fame for visible delivery impact",
            ],
        },
        {
            "slug": "joiners",
            "lens": "Start strong",
            "title": "New employees",
            "tagline": "Ramp faster — people, onboarding, training in flow.",
            "peek": [
                "Meet who’s who on the account",
                "One onboarding path to follow",
                "Training artefacts without hunting",
            ],
            "highlights": [
                "Unified onboarding kit instead of fragmented links",
                "Directory and personas so newcomers find the right owner",
                "Training corner tuned to how MiNe organizes learning",
            ],
        },
    ]

    return {
        "featured": featured,
        "hero_motifs": hero_motifs,
        "hero_showcase": hero_showcase,
        "portal_stats": portal_stats,
        "kpi_links": kpi_links,
        "quick_access": quick_access,
        "value_cards": value_cards,
    }


def _pct_for_bars(entries, value_key):
    vals = [int(e[value_key]) for e in entries]
    mx = max(vals) if vals else 1
    for e in entries:
        v = int(e[value_key])
        e["pct"] = round(100 * v / mx) if mx else 0


@bp.route("/")
def landing():
    user = load_current_user()
    if user:
        return redirect(url_for("main.dashboard"))
    db = get_db()
    ctx = _landing_page_context(db, None)
    return render_template("landing.html", **ctx)


@bp.route("/welcome")
@login_required
def welcome():
    db = get_db()
    user = load_current_user()
    ctx = _landing_page_context(db, user)
    return render_template("landing.html", **ctx)


@bp.route("/team")
def team_roster():
    """Public roster — Name and TSR from the Freeport active resource tracker workbook."""
    roster = load_team_roster()
    roster_groups = group_roster_for_display(roster)
    return render_template("team_roster.html", roster=roster, roster_groups=roster_groups)


@bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = load_current_user()
    counts = _knowledge_module_counts(db)
    approved_total = int(
        db.execute("SELECT COUNT(*) AS c FROM content WHERE status = 'approved'").fetchone()["c"] or 0
    )
    projects_n = count_portfolio_projects(db)
    innovation_n = _count_approved_module(db, "innovation")
    team_n = _active_team_count(db)

    portal_stats = {
        "knowledge_items": approved_total,
        "projects": projects_n,
        "innovations": innovation_n,
        "team_members": team_n,
    }

    chart_modules = [
        {"label": label, "value": counts.get(mod, 0)} for mod, label in KNOWLEDGE_MODULES
    ]
    _pct_for_bars(chart_modules, "value")

    innov_rows = db.execute(
        """
        SELECT title, summary, body
        FROM content
        WHERE status = 'approved' AND module = 'innovation'
        """
    ).fetchall()
    innov_buckets = _innovation_bucket_counts(innov_rows)
    inn_entries = [{"label": b["label"], "value": int(b["count"])} for b in innov_buckets]
    _pct_for_bars(inn_entries, "value")

    project_rows = db.execute(
        """
        SELECT c.*, u.display_name AS author_name,
               p.program_name, p.project_manager, p.delivery_status
        FROM content c
        JOIN users u ON u.id = c.author_id
        JOIN projects p ON p.content_id = c.id
        WHERE c.module = 'projects' AND c.status = 'approved'
        ORDER BY c.updated_at DESC
        LIMIT 8
        """
    ).fetchall()

    feed_rows = _knowledge_repo_feed_recent(db, 36)

    pending_n = None
    if user and user["role"] in ("admin", "moderator"):
        pending_n = int(
            db.execute("SELECT COUNT(*) AS c FROM content WHERE status = 'pending'").fetchone()["c"] or 0
        )

    return render_template(
        "dashboard.html",
        portal_stats=portal_stats,
        chart_modules=chart_modules,
        innovation_bars=inn_entries,
        project_rows=project_rows,
        knowledge_feed=feed_rows,
        timeline=_FREEPORT_STORY,
        module_labels=dict(KNOWLEDGE_MODULES),
        pending_moderation=pending_n,
    )


@bp.route("/journey")
def journey():
    return render_template("journey.html")


@bp.route("/resources/software-tools")
@login_required
def software_tools():
    return render_template("software_tools.html")


@bp.route("/knowledge")
@login_required
def knowledge():
    db = get_db()
    module = request.args.get("module", "").strip() or None
    qtext = (request.args.get("q") or "").strip()
    author = (request.args.get("author") or "").strip()
    counts = _knowledge_module_counts(db)

    if not module and not qtext and not author:
        recent = _approved_list(None, 8)
        return render_template(
            "knowledge.html",
            landing=True,
            module_counts=counts,
            modules_meta=KNOWLEDGE_MODULES,
            recent_rows=recent,
            search_xp_placeholders=SEARCH_XP_PLACEHOLDERS,
            search_xp_categories=SEARCH_XP_CATEGORIES,
            search_xp_filter_tags=SEARCH_XP_FILTER_TAGS,
        )

    sql = """
        SELECT c.*, u.display_name AS author_name
        FROM content c
        JOIN users u ON u.id = c.author_id
        WHERE c.status = 'approved'
    """
    args: list = []
    if module:
        sql += " AND c.module = ?"
        args.append(module)
    if qtext:
        sql += " AND (c.title LIKE ? OR COALESCE(c.summary, '') LIKE ?)"
        like = f"%{qtext}%"
        args.extend([like, like])
    if author:
        sql += " AND u.display_name = ?"
        args.append(author)
    sql += " ORDER BY c.updated_at DESC LIMIT 100"
    rows = db.execute(sql, args).fetchall()

    author_options = db.execute(
        """
        SELECT DISTINCT u.display_name AS n
        FROM users u
        JOIN content c ON c.author_id = u.id
        WHERE c.status = 'approved'
        ORDER BY n COLLATE NOCASE
        LIMIT 100
        """
    ).fetchall()

    mod_labels = dict(KNOWLEDGE_MODULES)
    module_label = mod_labels.get(module, "Knowledge repository") if module else "Knowledge repository"

    return render_template(
        "knowledge.html",
        landing=False,
        rows=rows,
        module=module,
        q=qtext,
        author=author,
        module_counts=counts,
        modules_meta=KNOWLEDGE_MODULES,
        author_options=author_options,
        module_label=module_label,
    )


@bp.route("/onboarding")
@login_required
def onboarding():
    rows = _approved_list("onboarding", 100)
    return render_template("onboarding.html", rows=rows)


@bp.route("/innovation")
@login_required
def innovation():
    rows = _approved_list("innovation", 100)
    stats = _innovation_bucket_counts(rows)
    return render_template("innovation.html", rows=rows, innovation_stats=stats)


@bp.route("/training")
@login_required
def training():
    rows = _approved_list("training", 100)
    return render_template("training.html", rows=rows)


@bp.route("/hall-of-fame")
@login_required
def hall_of_fame():
    year = (request.args.get("year") or "").strip()
    db = get_db()
    year_rows = db.execute(
        """
        SELECT DISTINCT strftime('%Y', c.updated_at) AS y
        FROM content c
        WHERE c.status = 'approved' AND c.module = 'hall_of_fame' AND c.updated_at IS NOT NULL
        ORDER BY y DESC
        """
    ).fetchall()
    years = [r["y"] for r in year_rows if r["y"]]
    rows = _approved_list("hall_of_fame", 200)
    if year and year.isdigit():
        rows = [r for r in rows if str(r["updated_at"] or "")[:4] == year]
    return render_template("hall_of_fame.html", rows=rows, years=years, year_filter=year)


@bp.route("/open-pit-copper-domain")
@login_required
def open_pit_copper_domain():
    return render_template("open_pit_copper_domain.html")


@bp.route("/open-pit-copper-domain/raw")
@login_required
def open_pit_copper_domain_raw():
    from flask import redirect, url_for

    return redirect(url_for("main.open_pit_copper_domain"))


@bp.route("/open-pit-copper-domain/lifecycle-image")
@login_required
def open_pit_copper_domain_lifecycle_image():
    return _serve_domain_infographic("mining-lifecycle-value.png")


@bp.route("/open-pit-copper-domain/value-chain-image")
@login_required
def open_pit_copper_domain_value_chain_image():
    return _serve_domain_infographic("end-to-end-mining-value-chain.png")


@bp.route("/open-pit-copper-domain/digital-enablement-image")
@login_required
def open_pit_copper_domain_digital_enablement_image():
    return _serve_domain_infographic("digital-mining-value-chain-mapping.png")


@bp.route("/open-pit-copper-domain/service-map-image")
@login_required
def open_pit_copper_domain_service_map_image():
    return _serve_domain_infographic("mapping-services-to-client.png")


@bp.route("/open-pit-copper-domain/measurement-hierarchy-image")
@login_required
def open_pit_copper_domain_measurement_hierarchy_image():
    return _serve_domain_infographic("measurement-hierarchy.png")


@bp.route("/open-pit-copper-domain/pa-process-image")
@login_required
def open_pit_copper_domain_pa_process_image():
    return _serve_domain_infographic("mining-and-refining-process.png")


@bp.route("/my/submissions")
@login_required
@roles_required("admin", "moderator")
def my_submissions():
    user = load_current_user()
    db = get_db()
    rows = db.execute(
        """
        SELECT c.*, u.display_name AS author_name
        FROM content c
        JOIN users u ON u.id = c.author_id
        WHERE c.author_id = ?
        ORDER BY c.updated_at DESC
        """,
        (user["id"],),
    ).fetchall()
    return render_template("my_submissions.html", rows=rows)
