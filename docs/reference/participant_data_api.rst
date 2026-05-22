Participant Data API
====================

Reference for the ``participant`` object and all template variables BOFS injects into every rendered template. For guidance on when and why to use each surface, see :doc:`/framework/participant_data`. For template variable injection mechanics, see :doc:`/framework/templates_jinja`.

.. contents:: On this page
   :local:
   :depth: 2


Template Variables
------------------

BOFS registers a context processor that adds the following variables to every template it renders.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Variable
     - Description
   * - ``participant``
     - The current :ref:`Participant object <participant-object>`. ``None`` when no participant is in session (admin previews, the consent page before submission, error pages). Guard with ``{% if participant %}`` in templates that may render in those contexts.
   * - ``session``
     - The Flask session dictionary. Contains the :ref:`session fields <session-fields>` described below. Populated progressively as the participant moves through the experiment.
   * - ``debug``
     - ``True`` when BOFS is running with the ``-d`` flag.
   * - ``config``
     - The project's TOML configuration, accessible as ``config['KEY']`` or ``config.KEY``. See :ref:`config-access` below.
   * - ``flat_page_list``
     - The current participant's filtered page sequence as a list of path strings, with ``show_if`` predicates and condition routing applied. Empty or condition-filtered pages are excluded.


.. _participant-object:

The Participant Object
----------------------

Attributes
~~~~~~~~~~

These are database columns on the ``Participant`` model, readable directly in templates and custom blueprint code.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Attribute
     - Type
     - Description
   * - ``participantID``
     - ``int``
     - Auto-assigned primary key. Unique per participant within the project database.
   * - ``condition``
     - ``int``
     - Assigned condition number, starting at 1. ``0`` means no condition has been assigned (single-condition projects, or before assignment runs).
   * - ``externalID``
     - ``str``
     - External worker or participant identifier (MTurk Worker ID, Prolific ID, or the value passed via the ``external_id`` query parameter). Empty string when not set. Also accessible as ``mTurkID``, an alias kept for backward compatibility with code written before the rename.
   * - ``timeStarted``
     - ``datetime``
     - UTC timestamp recorded after the participant submits the consent page (when their session is created). Naive datetime — no timezone info attached.
   * - ``timeEnded``
     - ``datetime`` or ``None``
     - UTC timestamp recorded when the participant reaches the final page. ``None`` until the participant finishes.
   * - ``finished``
     - ``bool``
     - ``True`` once the participant has completed the experiment.
   * - ``code``
     - ``str``
     - Completion code generated at the end of the experiment. Empty string until generated.


Methods
~~~~~~~

.. py:method:: participant.display_duration() -> str

   Returns a human-readable string representing elapsed time (``"HH:MM:SS"`` or shorter form) when the participant has finished, or a status string (``"In Progress"`` or ``"Abandoned"``) when they have not.

   When ``timeEnded`` is ``None``, the return value is ``"In Progress"`` if the participant is currently active, or ``"Abandoned"`` if they have been inactive beyond the ``ABANDONED_MINUTES`` threshold.


.. py:method:: participant.questionnaire(name, tag="") -> row

   Returns the participant's most recent response row for the questionnaire named ``name``, optionally filtered to the submission filed under ``tag``.

   When the participant has not yet submitted the questionnaire, returns a blank-default row whose field attributes hold each column's default value (empty string for text fields, ``0`` for numeric fields, ``False`` for boolean fields). Accessing any field on a blank-default row succeeds without raising — use :py:meth:`has_questionnaire` to distinguish a real submission from a defaulted one.

   When the same questionnaire has been submitted more than once under the same tag, the most recent submission (by ``timeEnded``) is returned.

   Field values and any ``participant_calculations`` columns are available as attributes on the returned row (e.g., ``row.age``, ``row.extraversion_score``). For the rules governing field IDs and calculated columns, see :doc:`/reference/questionnaire_properties`.

   **Parameters**

   - ``name`` (``str``) — The questionnaire filename without the ``.json`` extension.
   - ``tag`` (``str``, default ``""``) — The tag under which the questionnaire was submitted. Corresponds to the optional third segment of the URL path (``questionnaire/<name>/<tag>``). Pass the empty string (or omit) for untagged submissions.

   **Returns** a SQLAlchemy model instance with all questionnaire fields as attributes.


.. py:method:: participant.has_questionnaire(name, tag="") -> bool

   Returns ``True`` when the participant has at least one stored submission of ``name`` with the given ``tag``.

   ``questionnaire()`` always returns a row (falling back to a blank default), so this method is the only way to tell whether a real submission exists without inspecting field values.

   **Parameters**

   - ``name`` (``str``) — The questionnaire filename without the ``.json`` extension.
   - ``tag`` (``str``, default ``""``) — Tag to match. Pass the empty string (or omit) for untagged submissions.

   **Returns** ``bool``.


.. py:method:: participant.questionnaire_interactions(name, tag="") -> list

   Returns a list of interaction event rows for the questionnaire named ``name``, ordered by ``timestamp`` ascending. Requires ``LOG_QUESTIONNAIRE_INTERACTIONS = true`` in the project configuration; returns an empty list otherwise, or when the participant has not yet reached the questionnaire.

   Each row in the list has the following attributes:

   .. list-table::
      :header-rows: 1
      :widths: 25 15 60

      * - Attribute
        - Type
        - Description
      * - ``questionnaire``
        - ``str``
        - Questionnaire name.
      * - ``tag``
        - ``str``
        - Submission tag (``"0"`` for untagged submissions internally; treat empty string and ``"0"`` as equivalent when filtering).
      * - ``questionID``
        - ``str``
        - The ``id`` of the question field that generated the event.
      * - ``eventType``
        - ``str``
        - One of ``focus``, ``blur``, ``change``, ``paste``, or ``visibility``. Text inputs also log authenticity signals such as keystroke counts, backspace counts, paste character counts, focus duration, and time-to-first-keystroke as additional event records.
      * - ``timestamp``
        - ``datetime``
        - UTC timestamp of the event.
      * - ``value``
        - ``str`` or ``None``
        - The field value captured at event time. ``None`` for event types that do not carry a value.

   **Parameters**

   - ``name`` (``str``) — The questionnaire filename without the ``.json`` extension.
   - ``tag`` (``str``, default ``""``) — Tag to match.

   **Returns** ``list`` of ``QuestionnaireInteraction`` model instances.


.. py:method:: participant.table(name) -> TableAccessor

   Returns a :ref:`TableAccessor <table-accessor>` for the JSONTable named ``name``. Raises ``KeyError`` when no table by that name is loaded.

   For details on defining tables and their ``exports`` block, see :doc:`/reference/custom_tables`.

   **Parameters**

   - ``name`` (``str``) — The JSONTable filename without the ``.json`` extension.

   **Returns** :ref:`TableAccessor <table-accessor>`.


.. py:method:: participant.evaluate(expression) -> value or None

   Evaluates a BOFS expression string against this participant's stored data and returns the result. Uses the same syntax as ``show_if`` predicates and ``participant_calculations`` in questionnaire JSON files.

   Returns ``None`` when the expression cannot be parsed, contains unsupported syntax, or references a questionnaire the participant has not yet submitted. A template ``{% if participant.evaluate(...) %}`` therefore falls through to the ``else`` branch rather than raising.

   For direct field access, ``participant.questionnaire('name').field`` is shorter and more idiomatic. Reach for ``evaluate()`` when you want to share an expression string with a ``show_if`` predicate in a configuration file, or when you need to build the expression dynamically.

   **Parameters**

   - ``expression`` (``str``) — A BOFS expression string. See :doc:`/reference/expressions` for full syntax.

   **Returns** the expression result (bool, int, float, str, or list), or ``None`` on failure.


.. _table-accessor:

TableAccessor
-------------

``TableAccessor`` is returned by :py:meth:`participant.table`. It exposes the participant's raw rows and any per-participant aggregates declared in the table's ``exports`` block.

Iteration and indexing
~~~~~~~~~~~~~~~~~~~~~~

The accessor proxies ``__iter__``, ``__len__``, ``__getitem__``, and ``__bool__`` to its ``rows`` list, so the following patterns all work without accessing ``.rows`` explicitly:

- ``{% for row in participant.table('foo') %}``
- ``participant.table('foo')|length``
- ``participant.table('foo')[0]``
- ``{% if participant.table('foo') %}`` — ``False`` when the participant has no rows.

.. py:attribute:: TableAccessor.rows

   The participant's raw rows in the table as a list of model instances. Returns ``[]`` when the participant has no rows.

Export field attributes
~~~~~~~~~~~~~~~~~~~~~~~

Every field declared in the table's ``exports`` block is accessible as an attribute on the accessor. Each aggregate is computed once per accessor instance and cached; reading the same attribute twice in a template runs the query only once.

Scalar exports (no ``group_by``) return a single value, or ``None`` when no rows match the export's ``filter`` and ``having`` clauses.

``group_by`` exports return a dict keyed by the group value. When ``group_by`` is a list of columns, the key is a tuple of values in declaration order. An empty dict means the participant had no rows that satisfied the filter.

Page-level ``show_if`` expressions can consume scalar aggregates from a ``TableAccessor``; ``group_by`` exports are not reachable from ``show_if`` (the reference resolves to undecided). Access ``group_by`` results from templates or custom blueprint code instead.

.. py:attribute:: TableAccessor.exports

   All export aggregates as a plain ``dict``. Scalar exports map to their value; ``group_by`` exports map to a dict keyed by group value or tuple. Reading ``.exports`` computes and caches every aggregate at once, then returns the dict. Useful when you want to iterate: ``{% for key, value in participant.table('foo').exports.items() %}``.


.. _session-fields:

Session Fields
--------------

The ``session`` variable is the Flask session dictionary. It is populated progressively as the participant moves through the experiment, so some keys may be absent early in the flow. Use ``session.get('key')`` or ``'key' in session`` to guard against missing keys in templates that may render before a value is set.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Key
     - Type
     - Description
   * - ``participantID``
     - ``int``
     - Set when the participant's database row is created (after consent is submitted). Absent before consent.
   * - ``condition``
     - ``int``
     - The participant's assigned condition number. Set at the same time as ``participantID``.
   * - ``currentUrl``
     - ``str``
     - The path of the current page in the experiment sequence, as tracked by the page-flow system. Absent before the first page navigation.
   * - ``mTurkID``
     - ``str``
     - External worker or participant identifier. Set from query parameters (``workerId``, ``PROLIFIC_PID``, or ``external_id``) or copied from the participant row. Absent when not provided.
   * - ``code``
     - ``str``
     - Completion code. Set when the participant reaches the end page. Absent until then.


.. _config-access:

Config Access
-------------

The ``config`` variable provides access to all TOML configuration settings. Read values using dictionary syntax or attribute access:

.. code-block:: html+jinja

   {{ config['TITLE'] }}
   {{ config.TITLE }}

All keys defined in the project's ``.toml`` file are available, including custom keys you define for your own project logic. Built-in keys are documented in :doc:`/reference/configuration`.

The ``config`` object is Flask's application config, a dict-like object. It does not raise on missing keys when accessed with ``.get()``, but bracket access raises ``KeyError`` for undefined keys.
