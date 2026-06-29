from typing import Union
from flask import current_app, g, has_request_context, request, session
from BOFS import util
from BOFS.expressions import (
    ExpressionError,
    build_participant_env,
    default_functions,
    evaluate,
    parse_page_predicate,
    referenced_fields,
)
from urllib.parse import urlsplit


# Sentinel for ``flat_page_list(participant_id=...)``. It distinguishes
# "the caller didn't pass anything, fall back to the Flask session"
# (the default for participant-facing routes) from "the caller explicitly
# passed None, do not filter by show_if at all" (admin views).
_RESOLVE_FROM_SESSION = object()


# Request-scoped flat_page_list cache, keyed by (condition, participant_id,
# hide_unresolved) — the inputs that fully determine the result.
_CACHE_ATTR = "_bofs_flat_page_list_cache"


def _flat_page_list_cache():
    """Per-request cache dict on ``flask.g``, created on first use. ``None``
    outside a request context so those callers always recompute."""
    if not has_request_context():
        return None
    cache = g.get(_CACHE_ATTR)
    if cache is None:
        cache = {}
        setattr(g, _CACHE_ATTR, cache)
    return cache


def invalidate_flat_page_list_cache():
    """Drop the cache. Wired to ``after_commit`` because a committed write
    can change ``show_if`` visibility (e.g. ``route_end`` stamps ``finished``
    then resolves the filtered page list). No-op outside a request."""
    if not has_request_context():
        return
    g.pop(_CACHE_ATTR, None)


class Visibility:
    """Tri-state result of evaluating a page entry's or routing arm's
    ``show_if``. ``UNRESOLVED`` means the predicate referenced data that
    has not been collected yet (typically a prior questionnaire that
    hasn't been submitted), and the caller should decide whether to treat
    that as visible (the conservative default for routing, so participants
    aren't locked out) or hidden (the right choice for the breadcrumb,
    where we don't want to display pages we can't yet promise the
    participant will visit).
    """
    VISIBLE = "visible"
    HIDDEN = "hidden"
    UNRESOLVED = "unresolved"


class PageList(object):
    page_list = []
    procedure = []

    def __init__(self, page_list):
        self.page_list = page_list
        self._compile_show_if(self.page_list)
        #self.procedure = self.parse_list_into_procedure()

    @staticmethod
    def _compile_show_if(page_list):
        """Parse any ``show_if`` predicate strings on page entries and any
        nested ``conditional_routing.page_list`` entries. The parsed AST is
        attached as ``_show_if_ast`` so evaluation at navigation time skips
        the parser. Failures are raised so they surface at app startup.

        ``show_if`` may also appear on an arm of a ``conditional_routing``
        block (alongside or instead of ``condition``), in which case the
        AST is attached to the arm dict itself.
        """
        for entry in page_list:
            if not isinstance(entry, dict):
                continue
            if "conditional_routing" in entry:
                for cr in entry["conditional_routing"]:
                    PageList._compile_arm_show_if(cr)
                    PageList._compile_show_if(cr.get("page_list", []))
                continue
            PageList._compile_one_show_if(entry)
            PageList._validate_outgoing_url(entry)

    @staticmethod
    def _compile_one_show_if(entry):
        """Parse a single entry's ``show_if`` (page entry or routing arm)."""
        expr = entry.get("show_if")
        if expr is None:
            return
        if not isinstance(expr, str) or not expr.strip():
            raise Exception(
                f"PAGE_LIST entry {entry.get('name', entry.get('path'))!r} "
                f"has a non-string show_if: {expr!r}"
            )
        try:
            ast_node, refs = parse_page_predicate(expr)
        except ExpressionError as e:
            raise Exception(
                f"Unable to parse show_if on page "
                f"{entry.get('name', entry.get('path'))!r}: "
                f"`{expr}`. {e}"
            )
        entry["_show_if_ast"] = ast_node
        entry["_show_if_refs"] = refs

    @staticmethod
    def _validate_outgoing_url(entry):
        """Reject ``outgoing_url`` on entries that are not end terminations.

        ``outgoing_url`` is only meaningful for entries whose ``path`` is
        ``end`` or starts with ``end/``. Allowing it on questionnaire or
        custom-page entries would create the "will this render or
        redirect?" ambiguity the design explicitly avoids. The string
        itself is stored as-is and rendered through Jinja at request time
        by :func:`route_end`; no parsing happens here.
        """
        if "outgoing_url" not in entry:
            return
        url = entry["outgoing_url"]
        if not isinstance(url, str) or not url.strip():
            raise Exception(
                f"PAGE_LIST entry {entry.get('name', entry.get('path'))!r} "
                f"has a non-string or empty outgoing_url: {url!r}"
            )
        path = entry.get("path")
        if not isinstance(path, str) or (path != "end" and not path.startswith("end/")):
            raise Exception(
                f"PAGE_LIST entry {entry.get('name', entry.get('path'))!r} "
                f"has outgoing_url but its path is {path!r}; outgoing_url "
                f"is only valid on entries whose path is 'end' or starts "
                f"with 'end/'."
            )

    @staticmethod
    def _compile_arm_show_if(arm):
        """Parse the optional ``show_if`` on a ``conditional_routing`` arm.

        An arm without a ``name``/``path`` is identified by its ``condition``
        in error messages so a researcher can find the offending arm.
        """
        expr = arm.get("show_if")
        if expr is None:
            return
        if not isinstance(expr, str) or not expr.strip():
            raise Exception(
                f"conditional_routing arm "
                f"(condition={arm.get('condition')!r}) has a non-string "
                f"show_if: {expr!r}"
            )
        try:
            ast_node, refs = parse_page_predicate(expr)
        except ExpressionError as e:
            raise Exception(
                f"Unable to parse show_if on conditional_routing arm "
                f"(condition={arm.get('condition')!r}): `{expr}`. {e}"
            )
        arm["_show_if_ast"] = ast_node
        arm["_show_if_refs"] = refs

    @staticmethod
    def _page_visibility(entry, participant_id):
        """Evaluate an entry's ``_show_if_ast`` against the given participant
        and return a :class:`Visibility`.

        Entries without a ``_show_if_ast`` are unconditionally ``VISIBLE``.
        When the predicate exists but BOFS lacks the context to evaluate
        it — no participant identity, no Flask app context, or the
        predicate references a questionnaire that hasn't been submitted
        yet — the result is ``UNRESOLVED``. The boolean wrapper
        :meth:`_page_visible` collapses ``UNRESOLVED`` back to "visible"
        so runtime navigation isn't restricted, while callers that opt
        into stricter filtering (e.g. the breadcrumb via
        ``flat_page_list(hide_unresolved=True)``) can drop the entry.
        """
        ast = entry.get("_show_if_ast")
        refs = entry.get("_show_if_refs", {})
        if ast is None:
            return Visibility.VISIBLE
        if participant_id is None:
            return Visibility.UNRESOLVED
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            return Visibility.UNRESOLVED
        env = build_participant_env(
            participant_id,
            referenced_fields(ast),
            refs,
            getattr(app, "questionnaires", {}),
            app.db,
            tables=getattr(app, "tables", {}),
        )
        try:
            value = evaluate(ast, env, functions=default_functions())
        except ExpressionError:
            return Visibility.UNRESOLVED
        return Visibility.VISIBLE if bool(value) else Visibility.HIDDEN

    @staticmethod
    def _page_visible(entry, participant_id):
        """Boolean wrapper around :meth:`_page_visibility`. Treats
        ``UNRESOLVED`` as visible so participants aren't locked out of a
        path whose gating data is still upstream — this preserves the
        runtime navigation behavior callers have always relied on.
        """
        return PageList._page_visibility(entry, participant_id) != Visibility.HIDDEN

    @staticmethod
    def _arm_status(arm, condition, participant_id):
        """Tri-state classifier for a ``conditional_routing`` arm,
        combining the ``condition`` check with the ``show_if`` check.

        Returns ``HIDDEN`` if the arm's ``condition`` is set and doesn't
        match (with ``condition == 0`` preserved as a "match anything"
        escape hatch for admin views). Otherwise delegates to
        :meth:`_page_visibility` on the arm itself.
        """
        arm_condition = arm.get("condition")
        if arm_condition is not None and condition != 0 and arm_condition != condition:
            return Visibility.HIDDEN
        return PageList._page_visibility(arm, participant_id)

    @staticmethod
    def _arm_matches(arm, condition, participant_id):
        """Boolean: ``True`` if the arm should be selected. An arm matches
        when its ``condition`` is unset or matches (with ``condition == 0``
        as the admin-view "match anything" escape hatch) AND its
        ``show_if`` is unset or evaluates to true. Calls :meth:`_page_visible`
        rather than :meth:`_page_visibility` so ``UNRESOLVED`` is treated
        as a match — the cautious default that keeps participants from
        being locked out of a path whose gating data is still upstream.
        """
        arm_condition = arm.get("condition")
        if arm_condition is not None and condition != 0 and arm_condition != condition:
            return False
        return PageList._page_visible(arm, participant_id)

    def unconditional_pages(self):
        pages = []
        for entry in self.page_list:
            if 'conditional_routing' in entry:
                continue
            pages.append(entry)

        return pages

    def conditional_pages(self, condition):
        """Return the inner pages of the first ``conditional_routing`` arm
        whose ``condition`` matches (or is unset) for each routing block.

        ``conditional_pages`` is used for enumeration (e.g. building the
        questionnaire list), not runtime navigation, so an arm's ``show_if``
        is treated as potentially-true here — the runtime filter happens
        in :meth:`flat_page_list` where participant context is available.
        """
        pages = []

        for entry in self.page_list:
            if 'conditional_routing' in entry:
                for arm in entry['conditional_routing']:
                    arm_condition = arm.get('condition')
                    if arm_condition is not None and arm_condition != condition:
                        continue
                    for conditional_entry in arm['page_list']:
                        pages.append(conditional_entry)
                    break  # once a match has been found, then we're done

        return pages

    @staticmethod
    def _resolve_participant_id(participant_id):
        """Resolve the participant_id arg into an effective ID for show_if
        evaluation. Three cases:

        * a concrete integer  → use it.
        * ``None``             → caller explicitly opts out of filtering;
                                 return ``None`` (do not filter).
        * the ``_RESOLVE_FROM_SESSION`` sentinel → caller didn't pass
                                 anything; fall back to the Flask session.

        The sentinel pattern is what lets admin views ask for the
        unfiltered page list without the lookup latching onto whatever
        the admin's session happens to contain.
        """
        if participant_id is _RESOLVE_FROM_SESSION:
            try:
                return session.get("participantID")
            except RuntimeError:
                return None
        return participant_id

    @staticmethod
    def extract_questionnaire_from_path(path, include_tag=False):
        questionnaire = path.replace("questionnaire/", "", 1)

        if not include_tag:
            questionnaire_name = questionnaire.split("/")[0]
            return questionnaire_name

        return questionnaire

    @staticmethod
    def _parse_questionnaire_path(path):
        """Extract (name, tag) from a questionnaire path like
        'questionnaire/example' or 'questionnaire/example/before'."""
        full = path.replace("questionnaire/", "", 1)
        parts = full.split("/", 1)
        name = parts[0]
        tag = parts[1] if len(parts) > 1 else ""
        return name, tag

    def auto_tag_duplicate_questionnaires(self, condition_count=0):
        """Detect questionnaire entries that collide on (name, tag) within any
        single-condition traversal and auto-assign integer tags to untagged
        duplicates.

        For each condition's flat page list, walks the entries tracking
        (name, tag) pairs. When an untagged duplicate (tag == "") is found,
        assigns the lowest unused integer tag >= 2 and rewrites the entry's
        path to questionnaire/<name>/<tag>.

        Sibling arms of one conditional_routing block are never both visited
        by the same participant, so the same questionnaire in different arms
        is NOT a duplicate. Only collisions within a single traversal are
        tagged.

        Explicitly tagged duplicates (same name AND same explicit tag) are
        left untouched — they surface as a fatal error via the existing
        questionnaire_list_is_safe check.

        Returns a list of (name, tag_string) tuples for the warning diagnostic.
        """
        conditions = list(range(1, condition_count + 1)) if condition_count > 0 else [0]
        assigned = []

        for condition in conditions:
            flat = self.flat_page_list(condition=condition, participant_id=None)
            seen = {}

            for entry in flat:
                path = entry.get('path', '')
                if not path.startswith('questionnaire/'):
                    continue

                name, tag = PageList._parse_questionnaire_path(path)

                if entry.get('_bofs_auto_tagged'):
                    seen[(name, tag)] = entry
                    continue

                key = (name, tag)
                if key not in seen:
                    seen[key] = entry
                elif tag == "":
                    used = set()
                    for e in flat:
                        e_path = e.get('path', '')
                        if e_path.startswith('questionnaire/'):
                            e_name, e_tag = PageList._parse_questionnaire_path(e_path)
                            if e_name == name:
                                used.add(e_tag)

                    n = 2
                    while str(n) in used:
                        n += 1
                    new_tag = str(n)

                    entry['path'] = f"questionnaire/{name}/{new_tag}"
                    entry['_bofs_auto_tagged'] = True
                    assigned.append((name, new_tag))
                    seen[(name, new_tag)] = entry

        return assigned

    def flat_page_list(self, condition=None,
                       participant_id=_RESOLVE_FROM_SESSION,
                       hide_unresolved=False) -> list[str]:
        """
        This is the typical access point for the page_list variable.
        By default, it tries to get the current condition from the session variable.

        :param condition: Set this to override the default functionality.
        :param participant_id: Controls how ``show_if`` predicates are
            evaluated.

            * Omit it (the default) and BOFS reads ``participantID`` from
              the Flask session — the right thing for participant-facing
              routes and template breadcrumbs.
            * Pass an integer to filter against that specific participant.
            * Pass ``None`` to skip ``show_if`` filtering entirely; every
              page that any participant could possibly visit is returned.
              Use this from admin views, where filtering by the admin's
              session participant ID would hide pages other participants
              actually visited.
        :param hide_unresolved: If ``False`` (the default and the right
            thing for runtime navigation), pages and routing arms whose
            ``show_if`` cannot yet be evaluated are treated as visible —
            otherwise participants could be locked out of a path whose
            gating data is still upstream. If ``True``, those entries are
            skipped instead, and a ``conditional_routing`` block whose
            relevant arms are still unresolved contributes nothing. This
            mode is intended for the breadcrumb, where displaying pages
            we don't yet know the participant will visit is misleading.
        """
        if condition is None:
            condition = util.fetch_current_condition()

        participant_id = self._resolve_participant_id(participant_id)

        # Serve repeated identical builds within a request from cache;
        # a DB commit invalidates it (invalidate_flat_page_list_cache).
        # Hand back a copy so a caller mutating the list can't poison it.
        cache = _flat_page_list_cache()
        cache_key = (condition, participant_id, hide_unresolved)
        if cache is not None and cache_key in cache:
            return list(cache[cache_key])

        flat_page_list = list()

        for entry in self.page_list:
            if 'conditional_routing' in entry:
                arms = entry['conditional_routing']
                if hide_unresolved:
                    arm_statuses = [
                        self._arm_status(arm, condition, participant_id)
                        for arm in arms
                    ]
                    # If any not-condition-eliminated arm is still
                    # unresolved, we don't yet know which arm the
                    # participant will follow — leave the whole block
                    # out of the breadcrumb rather than guess.
                    if any(s == Visibility.UNRESOLVED for s in arm_statuses):
                        continue
                    for arm, status in zip(arms, arm_statuses):
                        if status != Visibility.VISIBLE:
                            continue
                        for conditional_entry in arm['page_list']:
                            if self._page_visibility(conditional_entry, participant_id) == Visibility.VISIBLE:
                                flat_page_list.append(conditional_entry)
                        break  # once a match has been found, then we're done
                else:
                    for arm in arms:
                        if not self._arm_matches(arm, condition, participant_id):
                            continue
                        for conditional_entry in arm['page_list']:
                            if self._page_visible(conditional_entry, participant_id):
                                flat_page_list.append(conditional_entry)
                        break  # once a match has been found, then we're done
            else:
                if hide_unresolved:
                    if self._page_visibility(entry, participant_id) == Visibility.VISIBLE:
                        flat_page_list.append(entry)
                else:
                    if self._page_visible(entry, participant_id):
                        flat_page_list.append(entry)

        if cache is not None:
            cache[cache_key] = list(flat_page_list)

        return flat_page_list

    def has_branching(self) -> bool:
        """True if PAGE_LIST contains any ``conditional_routing`` block,
        or any top-level page has a ``show_if`` predicate. Used at startup
        to decide whether to warn the researcher that the breadcrumb may
        grow as participants answer gating questions.
        """
        for entry in self.page_list:
            if not isinstance(entry, dict):
                continue
            if "_show_if_ast" in entry or "conditional_routing" in entry:
                return True
        return False

    def get_questionnaire_list(self, include_tags=False) -> list[str]:
        """
        Returns a list of the questionnaires specified in the config's PAGE_LIST variable.
        :param bool include_tags: if true, then the paths will be in the format <questionnaire>/<tag>.
        :returns: list -- one entry per questionnaire, the filename of the questionnaire (without the .json).
        """
        condition_count = util.fetch_condition_count()
        questionnaires: list[str] = list()

        for page in self.unconditional_pages():
            if not page['path'].startswith("questionnaire/"):
                continue  # Not a questionnaire

            questionnaire_name = self.extract_questionnaire_from_path(page['path'], include_tags)
            questionnaires.append(questionnaire_name)

        for condition in range(1, condition_count+1):
            for page in self.conditional_pages(condition):
                if not page['path'].startswith("questionnaire/"):
                    continue  # Not a questionnaire

                questionnaire_name = page['path'].replace("questionnaire/", "", 1)

                if not include_tags:
                    questionnaire_name = questionnaire_name.split("/")[0]

                # The same questionnaire may appear in multiple conditions, so don't add it again.
                if questionnaire_name not in questionnaires:
                    questionnaires.append(questionnaire_name)

        return questionnaires

    def parse_list_into_procedure(self) -> list[Union[str, dict]]:
        procedure = []
        for entry in self.page_list:
            if 'conditional_routing' not in entry:
                #questionnaire_name = self.extract_questionnaire_from_path(entry['path'], False)
                procedure.append(entry)
            else:
                # Need to work out the page list lengths for each condition, so I don't end up accessing an invalid index.
                page_list_lengths = {}
                max_length = 0
                for cr_option in entry['conditional_routing']:
                    list_length = len(cr_option['page_list'])
                    page_list_lengths[cr_option['condition']] = list_length

                    if list_length > max_length:
                        max_length = list_length

                for i in range(max_length):
                    new_sub_list = {}
                    for cr_option in entry['conditional_routing']:
                        cr_condition = cr_option['condition']
                        new_sub_list[cr_condition] = None

                        if page_list_lengths[cr_condition] > i:  # Then it's safe to access the page entry
                            #questionnaire_name = self.extract_questionnaire_from_path(cr_option['page_list'][i]['path'], False)
                            new_sub_list[cr_condition] = cr_option['page_list'][i]

                    procedure.append(new_sub_list)

        return procedure

    def to_mermaid(self):
        def mermaid_entry_to_syntax(entry) -> str:
            return f"{entry['name']}(\"<b>{entry['header']}</b><br>{entry['text']}\")"

        def parse_until_cr(page_list, mermaid_entries, name_prefix=""):
            index_reached = 0

            if mermaid_entries is None:
                mermaid_entries = []

            for entry in page_list:
                if "conditional_routing" in entry:
                    break  # End early

                idx = len(mermaid_entries)
                path = entry['path'].replace("questionnaire/", "")

                if len(mermaid_entries) > 0 and 'header' in mermaid_entries[-1] and mermaid_entries[-1]['header'] == entry['name']:
                    mermaid_entries[-1]['text'] += f"<br>{path}"
                else:
                    mermaid_entries.append({'name': f"{name_prefix}{idx}", 'header': entry['name'], 'text': path})
                index_reached += 1

            return page_list[index_reached:]  # Return the remaining pages

        mermaid_entries = []
        page_list_copy = self.page_list[:]

        while len(page_list_copy) > 0:
            if "conditional_routing" in page_list_copy[0]:

                conditional_entries = {}
                for cr in page_list_copy[0]['conditional_routing']:
                    name_prefix = f"{len(mermaid_entries)}_cr_{cr['condition']}_"
                    conditional_entries[cr["condition"]] = []

                    parse_until_cr(cr['page_list'], conditional_entries[cr["condition"]], name_prefix)

                page_list_copy = page_list_copy[1:]

                    #sub_idx = 0
                    #conditional_entries[cr["condition"]] = []
                    #
                    #for cr_entry in cr['page_list']:
                    #    name = f"{idx}_{sub_idx}_{cr['condition']}"
                    #    conditional_entries[cr["condition"]].append({
                    #        'name': name,
                    #        'text': entry_to_mermaid_syntax(name, cr_entry)
                    #    })
                    #    sub_idx += 1

                mermaid_entries.append(conditional_entries)
            #idx += 1

            page_list_copy = parse_until_cr(page_list_copy, mermaid_entries)

        # for entry in self.page_list:
        #     if "conditional_routing" not in entry:
        #         entry_text = entry_to_mermaid_syntax(idx, entry)
        #         mermaid_entries.append({'name': idx, 'text': entry_text})
        #
        #     else:
        #         conditional_entries = {}
        #         for cr in entry['conditional_routing']:
        #             sub_idx = 0
        #             conditional_entries[cr["condition"]] = []
        #
        #             for cr_entry in cr['page_list']:
        #                 name = f"{idx}_{sub_idx}_{cr['condition']}"
        #                 conditional_entries[cr["condition"]].append({
        #                     'name': name,
        #                     'text': entry_to_mermaid_syntax(name, cr_entry)
        #                 })
        #                 sub_idx += 1
        #         mermaid_entries.append(conditional_entries)
        #     idx += 1

        output_str = "flowchart TB\n"

        first = True
        last_entry = None
        cr_idx = 0

        for entry in mermaid_entries:
            if 'text' in entry:
                if not first:
                    output_str += "-->"
                output_str += mermaid_entry_to_syntax(entry)
                first = False
                last_entry = entry
            else:
                #output_str += f"\nsubgraph conditional_routing_{cr_idx}"
                #cr_idx += 1
                last_ids = {}

                for condition in entry:
                    output_str += "\n"
                    if last_entry is not None:
                        output_str += f"{last_entry['name']}"

                    for subidx, subentry in enumerate(entry[condition]):
                        output_str += "-->"
                        output_str += mermaid_entry_to_syntax(subentry)
                        last_ids[condition] = subentry['name']

                #output_str += "\nend\n"
                output_str += "\n"
                output_str += " & ".join(last_ids.values())

        #output_str += "-->".join([entry['text'] for entry in mermaid_entries])

        return output_str

    @staticmethod
    def annotate_occurrences(flat_pages):
        """Return ``[(entry, occurrence), ...]`` where *occurrence* is the
        running 0-based count of ``entry['path']`` seen so far.

        Pure function — no special cases for ``end``, ``consent``, or any
        other path. Every entry receives an occurrence number.
        """
        seen = {}
        result = []
        for entry in flat_pages:
            path = entry.get('path', '')
            occ = seen.get(path, 0)
            seen[path] = occ + 1
            result.append((entry, occ))
        return result

    def get_index(self, path):
        """
        This function determines which index a path is within the ``flat_page_list()`` list.
        :param str path: the path to determine the index of.
        :returns: int -- the index of the path

        .. note::
            * Uses startswith() to determine a match.
            * Paths will have their leading forward-slash removed, if it exists.
        """
        if path.startswith("/"):
            path = path[1:]
        for i, page in enumerate(self.flat_page_list()):
            if page['path'] == path:
                return i
        return None

    def next_path(self, current_path=None):
        """
        Gives the next path from ``flat_page_list()``, based on incrementing the index of the current path.
        :param str current_path: The user's current path
        :returns: str -- the next path in ``flat_page_list()`` which the user should be sent to.
        """
        if current_path is None:
            current_path = request.path
        if current_path == '/redirect_next_page':
            parsed = urlsplit(request.referrer)
            current_path = parsed.path
        if current_path.startswith("/"):
            current_path = current_path[1:]
        current_index = self.get_index(current_path)
        flat_page_list = self.flat_page_list()

        # get_index returns None for a path that isn't in the page list.
        # Without this guard the subtraction below blows up with TypeError;
        # fall back to the first page so the participant lands somewhere
        # valid instead of seeing a 500.
        if current_index is None:
            return flat_page_list[0]['path'] if flat_page_list else current_path

        if current_index == len(flat_page_list) - 1:
            return current_path

        return flat_page_list[current_index + 1]['path']

    def previous_path(self, current_path=None):
        """
        Gives the previous path from ``flat_page_list()``, based on incrementing the index of the current path.
        :param str current_path: The user's current path
        :returns: str -- the next path in ``flat_page_list()`` which the user should be sent to.
        """
        if current_path is None:
            current_path = request.path
        if current_path.startswith("/"):
            current_path = current_path[1:]

        current_index = self.get_index(current_path)
        flat_page_list = self.flat_page_list()

        # Same None-guard as next_path — a path outside the configured list
        # would otherwise hit ``flat_page_list[None - 1]`` and TypeError.
        if current_index is None:
            return flat_page_list[0]['path'] if flat_page_list else current_path

        if current_index == 0:
            return current_path

        return flat_page_list[current_index - 1]['path']
