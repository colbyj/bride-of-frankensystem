"""Central collector for setup / configuration diagnostics surfaced at
startup.

A single :class:`DiagnosticCollector` is attached to the app as
``app.setup_diagnostics``. Every place that previously emitted a startup
warning via ``print()`` or ``app.logger.warning()`` now calls
:meth:`DiagnosticCollector.add`, which records a structured
:class:`Diagnostic` *and* writes to the app logger so console behaviour
stays informative.

Display surfaces (landing-page interstitial, fatal-error page,
researcher-facing diagnostics) all read from this one collector so the
researcher sees the same view of "what's wrong with my setup" regardless
of where they look.

Two-layer grouping:

* ``section`` — the high-level researcher-facing bucket used as the top
  heading on rendered diagnostic pages. One of ``Config``,
  ``Questionnaires``, ``Tables``, ``Database``, ``Blueprints``.
* ``category`` — the lower-level source tag, used for filtering and
  for sub-headings on the diagnostics page (e.g. PAGE_LIST, bindings,
  condition lookup all live inside the Config section).

Backwards compatibility: ``app.validation_errors`` is preserved as a
property that returns the error/warning subset of the collector. The
admin context processor, the existing fatal-error redirect, and any
researcher code that reads from it continue to work unchanged.
"""

from __future__ import annotations

from typing import Iterable, Optional


VALID_SEVERITIES = frozenset({"error", "warning", "info"})

# Top-level researcher-facing buckets. These are the section headings on
# the fatal-error page and the landing-page interstitial.
SECTION_CONFIG = "Config"
SECTION_QUESTIONNAIRES = "Questionnaires"
SECTION_TABLES = "Tables"
SECTION_DATABASE = "Database"
SECTION_BLUEPRINTS = "Blueprints"

VALID_SECTIONS = (
    SECTION_CONFIG,
    SECTION_QUESTIONNAIRES,
    SECTION_TABLES,
    SECTION_DATABASE,
    SECTION_BLUEPRINTS,
)

# Lower-level categories. The mapping below is how each category rolls up
# into a section; it's also the source for the sub-headings inside a
# section ("PAGE_LIST", "Database bindings", ...).
CATEGORY_TO_SECTION = {
    "config":           SECTION_CONFIG,
    "page_list":        SECTION_CONFIG,
    "bind":             SECTION_CONFIG,
    "condition_lookup": SECTION_CONFIG,
    "security":         SECTION_CONFIG,
    "questionnaire":    SECTION_QUESTIONNAIRES,
    "asset":            SECTION_QUESTIONNAIRES,
    "table":            SECTION_TABLES,
    "schema":           SECTION_DATABASE,
    "route":            SECTION_BLUEPRINTS,
}

VALID_CATEGORIES = frozenset(CATEGORY_TO_SECTION)

# Human-readable sub-heading per category. Used inside a section when
# the diagnostic isn't tied to a specific file (questionnaire/table
# diagnostics use their filename as the sub-heading instead).
CATEGORY_SUBHEADING = {
    "config":           "Config keys",
    "page_list":        "PAGE_LIST",
    "bind":             "Database bindings",
    "condition_lookup": "Condition lookup",
    "security":         "Security",
    "schema":           "Schema mismatches",
    "route":            "Routes",
    "asset":            "Missing assets",
    # ``questionnaire`` / ``table`` deliberately have no entry — those
    # diagnostics group by filename instead, set on the ``questionnaire``
    # attribute.
}


class Diagnostic:
    """A single setup-time finding.

    Attributes:

    * ``severity`` — ``error`` / ``warning`` / ``info``
    * ``section`` — top-level group for display
    * ``category`` — lower-level source tag
    * ``message`` — human-readable description
    * ``suggestion`` — what the researcher should do (optional)
    * ``questionnaire`` — filename when applicable; used as the
      sub-heading inside ``Questionnaires`` / ``Tables`` sections
    * ``source`` — free-form reference to the config key, route, bind,
      etc. that triggered the diagnostic (optional, displayed inline)
    """

    __slots__ = ("severity", "section", "category", "message", "suggestion",
                 "questionnaire", "source")

    def __init__(
        self,
        severity: str,
        category: str,
        message: str,
        suggestion: Optional[str] = None,
        *,
        questionnaire: Optional[str] = None,
        source: Optional[str] = None,
        section: Optional[str] = None,
    ):
        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"invalid severity {severity!r}; expected one of "
                f"{sorted(VALID_SEVERITIES)}"
            )
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"invalid category {category!r}; expected one of "
                f"{sorted(VALID_CATEGORIES)}"
            )
        resolved_section = section or CATEGORY_TO_SECTION[category]
        if resolved_section not in VALID_SECTIONS:
            raise ValueError(
                f"invalid section {resolved_section!r}; expected one of "
                f"{VALID_SECTIONS}"
            )
        self.severity = severity
        self.section = resolved_section
        self.category = category
        self.message = message
        self.suggestion = suggestion
        self.questionnaire = questionnaire
        self.source = source

    @property
    def subheading(self) -> str:
        """Human-readable second-level grouping label for the UI.

        Questionnaire / table diagnostics use the filename so all items
        about ``consent.json`` stack under one heading. Everything else
        uses a fixed per-category label (PAGE_LIST, Database bindings,
        Security, ...).
        """
        if self.questionnaire:
            return self.questionnaire
        return CATEGORY_SUBHEADING.get(self.category, self.category.title())

    def __str__(self) -> str:
        prefix = {"error": "ERROR", "warning": "WARNING", "info": "NOTE"}[self.severity]
        scope = self.questionnaire or self.subheading
        s = f"  {prefix} [{self.section}/{self.category}] {scope}: {self.message}"
        if self.suggestion:
            s += f"\n    -> {self.suggestion}"
        return s

    def __repr__(self) -> str:
        return (
            f"Diagnostic({self.severity!r}, {self.category!r}, "
            f"{self.message!r})"
        )


class DiagnosticCollector:
    """Holds the set of diagnostics produced during app construction.

    Iteration order matches insertion order so the researcher sees
    diagnostics in the order BOFS encountered them, which usually mirrors
    the startup sequence (config -> page list -> questionnaires -> tables
    -> schema).
    """

    def __init__(self, app=None):
        self._items: list[Diagnostic] = []
        self._app = app

    def bind(self, app) -> None:
        """Attach the app after construction so :meth:`add` can route
        messages through the Flask logger."""
        self._app = app

    # -- write -----------------------------------------------------------

    def add(
        self,
        severity: str,
        category: str,
        message: str,
        suggestion: Optional[str] = None,
        *,
        questionnaire: Optional[str] = None,
        source: Optional[str] = None,
        section: Optional[str] = None,
        log: bool = True,
    ) -> Diagnostic:
        diag = Diagnostic(
            severity, category, message, suggestion,
            questionnaire=questionnaire, source=source, section=section,
        )
        self._items.append(diag)
        if log and self._app is not None:
            self._log(diag)
        return diag

    def extend(self, diagnostics: Iterable[Diagnostic], *, log: bool = True) -> None:
        for d in diagnostics:
            self._items.append(d)
            if log and self._app is not None:
                self._log(d)

    # Accept legacy ValidationResult objects produced by validation.py
    # without losing data. ValidationResult lacks ``category`` / ``section``;
    # the call site supplies them explicitly via ``category=`` so a single
    # batch of legacy results can be re-tagged at the boundary.
    def append(self, item, *, category: Optional[str] = None,
               section: Optional[str] = None,
               log: bool = True) -> None:
        if not isinstance(item, Diagnostic):
            resolved_category = (
                category or getattr(item, "category", None) or "questionnaire"
            )
            item = Diagnostic(
                getattr(item, "severity", "error"),
                resolved_category,
                getattr(item, "message", str(item)),
                getattr(item, "suggestion", None),
                questionnaire=getattr(item, "questionnaire", None),
                source=getattr(item, "source", None),
                section=section,
            )
        else:
            if category is not None and item.category != category:
                item.category = category
                if section is None:
                    item.section = CATEGORY_TO_SECTION[category]
            if section is not None and item.section != section:
                item.section = section
        self._items.append(item)
        if log and self._app is not None:
            self._log(item)

    def _log(self, diag: Diagnostic) -> None:
        level = {"error": "error", "warning": "warning", "info": "info"}[diag.severity]
        line = f"[{diag.section}/{diag.category}] {diag.subheading}: {diag.message}"
        if diag.suggestion:
            line += f" -> {diag.suggestion}"
        getattr(self._app.logger, level)(line)

    # -- read ------------------------------------------------------------

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __bool__(self):
        return bool(self._items)

    @property
    def items(self) -> list[Diagnostic]:
        return list(self._items)

    def by_severity(self, *severities: str) -> list[Diagnostic]:
        return [d for d in self._items if d.severity in severities]

    def by_category(self, category: str) -> list[Diagnostic]:
        return [d for d in self._items if d.category == category]

    def by_section(self, section: str) -> list[Diagnostic]:
        return [d for d in self._items if d.section == section]

    def has_fatal(self) -> bool:
        return any(d.severity == "error" for d in self._items)

    def actionable(self) -> list[Diagnostic]:
        """Error + warning entries — the things the researcher needs to
        see in the UI. Info notices stay log-only for now."""
        return [d for d in self._items if d.severity in ("error", "warning")]

    def grouped(self, severities=("error", "warning")) -> list[dict]:
        """Return a structure shaped for the diagnostics template:

            [
                {
                    "section": "Config",
                    "subgroups": [
                        {"label": "PAGE_LIST", "diagnostics": [...]},
                        {"label": "Database bindings", "diagnostics": [...]},
                        ...
                    ],
                },
                ...
            ]

        Order: sections in the canonical :data:`VALID_SECTIONS` order,
        subgroups in first-seen order, diagnostics in insertion order
        within each subgroup.

        ``diagnostics`` is used as the inner key (not the more natural
        ``items``) because Jinja's ``obj.attr`` lookup resolves dict
        methods before keys, so ``sub.items`` in the template would
        return the bound ``dict.items`` method rather than the list.
        """
        result: list[dict] = []
        section_buckets: dict[str, list[tuple[str, Diagnostic]]] = {
            s: [] for s in VALID_SECTIONS
        }
        for d in self._items:
            if d.severity not in severities:
                continue
            section_buckets[d.section].append((d.subheading, d))

        for section in VALID_SECTIONS:
            entries = section_buckets[section]
            if not entries:
                continue
            subgroups: list[dict] = []
            seen: dict[str, dict] = {}
            for label, diag in entries:
                bucket = seen.get(label)
                if bucket is None:
                    bucket = {"label": label, "diagnostics": []}
                    seen[label] = bucket
                    subgroups.append(bucket)
                bucket["diagnostics"].append(diag)
            result.append({"section": section, "subgroups": subgroups})
        return result
