import os
import json
import pprint
import traceback
from datetime import datetime
from flask import current_app, request, session, render_template

from ..globals import db
from ..util import utcnow_naive


class ParticipantQuestionnaireService:
    """Per-participant runtime operations for a JSONQuestionnaire: submission
    persistence, prior-value lookup, and the render pipeline."""

    def __init__(self, participant_id: int):
        self.participant_id = participant_id

    def handle_submission(self, questionnaire, tag: str = "") -> None:
        # Check to see if the user has submitted this once already. If
        # multiple prior rows exist (legacy data, or a fix-and-resubmit
        # workflow), use the most recent rather than inserting yet another.
        previous = db.session.query(questionnaire.db_class).filter(
            questionnaire.db_class.participantID == self.participant_id,
            questionnaire.db_class.tag == tag
        ).order_by(questionnaire.db_class.timeEnded.desc()).all()

        if previous:
            new_object = previous[0]
            if len(previous) > 1:
                current_app.logger.warning(
                    "Multiple prior rows for participant=%s questionnaire=%s tag=%r — using most recent",
                    self.participant_id, questionnaire.file_name, tag,
                )
        else:
            new_object = questionnaire.db_class()

        # ``timeStarted`` is normally posted in microsecond format by the
        # client; a few legacy paths post the second-only format. Fall back
        # gracefully through both, then to "now" if the field is missing or
        # unparseable — better to record a slightly wrong timeStarted than
        # to 500 a participant mid-experiment.
        ts_str = request.form.get('timeStarted')
        timeStarted = None
        if ts_str:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    timeStarted = datetime.strptime(ts_str, fmt)
                    break
                except ValueError:
                    continue
        if timeStarted is None:
            current_app.logger.warning(
                "Missing/unparseable timeStarted=%r for participant=%s questionnaire=%s",
                ts_str, self.participant_id, questionnaire.file_name,
            )
            timeStarted = utcnow_naive()

        fields = questionnaire.fetch_fields()

        if current_app.config.get('LOG_QUESTIONNAIRE_INTERACTIONS', False):
            raw = request.form.get('questionnaireInteractions', '')
            for event_str in raw.split(';'):
                if not event_str:
                    continue
                try:
                    event = json.loads(event_str)
                    interaction = db.QuestionnaireInteraction()
                    interaction.participantID = self.participant_id
                    interaction.questionnaire = questionnaire.file_name
                    interaction.tag = tag
                    interaction.questionID = event.get('questionID', '')
                    interaction.eventType = event.get('eventType', '')
                    interaction.timestamp = datetime.fromtimestamp(float(event['timestamp']))
                    interaction.value = event.get('value', '') or ''
                    db.session.add(interaction)
                except Exception:
                    current_app.logger.exception(
                        "Failed to parse questionnaire interaction event: %r", event_str
                    )
            db.session.commit()

        for field in fields:
            try:
                value = request.form.get(field.id, None)
                attr = getattr(questionnaire.db_class, field.id)
                # An empty string from a nullable column means the
                # participant explicitly chose a "no value" option (e.g. a
                # radiogrid N/A column) — store NULL rather than "" so
                # consumers can distinguish missing-by-design from a real
                # empty answer.
                if value == "" and attr.expression.nullable:
                    value = None
                    setattr(new_object, field.id, value)
                elif value is not None:
                    setattr(new_object, field.id, value)
                else:
                    column_default = attr.expression.default
                    default = column_default.arg if column_default is not None else None
                    setattr(new_object, field.id, default)
            except (AttributeError, TypeError, ValueError, KeyError):
                # Don't roll back the whole submission for one bad field —
                # the rest of the row is still useful — but make the failure
                # visible so the researcher can spot a schema/JSON mismatch.
                current_app.logger.exception(
                    "Failed to write field id=%r for participant=%s questionnaire=%s",
                    field.id, self.participant_id, questionnaire.file_name,
                )

        setattr(new_object, 'participantID', self.participant_id)
        setattr(new_object, 'timeStarted', timeStarted)
        setattr(new_object, 'timeEnded', utcnow_naive())
        setattr(new_object, 'tag', tag)

        db.session.add(new_object)
        db.session.commit()

        if 'ENABLE_LOGGING' in current_app.config and current_app.config['ENABLE_LOGGING'] == True:
            if not os.path.exists("logs"):
                os.makedirs("logs")

            with open("logs/" + questionnaire.file_name + ".txt", "a+") as f:
                f.write("Time = " + str(timeStarted) + "; pID = " + str(self.participant_id) + ";\n" + pprint.pformat(request.form) + "\n\n")

    def fetch_prior_values(self, questionnaire, tag: str = "") -> dict:
        """Return {field_id: stored_value} for this participant's prior submission of this
        questionnaire+tag, or an empty dict if there is no prior submission. Used to repopulate
        the form when a participant returns to a questionnaire they've already submitted."""
        previous = db.session.query(questionnaire.db_class).filter(
            questionnaire.db_class.participantID == self.participant_id,
            questionnaire.db_class.tag == tag
        ).first()

        if previous is None:
            return {}

        fields = questionnaire.fetch_fields()
        return {f.id: getattr(previous, f.id) for f in fields}

    def render_questionnaire(self, questionnaire, template_name: str = 'questionnaire.html', tag: str = "") -> str:
        from ..expressions import substitute_in_questionnaire
        prior_values = self.fetch_prior_values(questionnaire, tag)
        participant = (
            db.session.get(db.Participant, self.participant_id)
            if self.participant_id is not None else None
        )
        json_data = (
            substitute_in_questionnaire(questionnaire.json_data, participant)
            if participant is not None else questionnaire.json_data
        )
        return ParticipantQuestionnaireService.render_unloaded_questionnaire(
            json_data, template_name, tag, prior_values=prior_values)

    @staticmethod
    def _inject_prior_values(question_data: dict, prior_values: dict) -> dict:
        """Return a shallow-copied question dict with `value` and `has_value` keys populated
        from prior_values, for the question and any sub-questions in `questions`/`q_text`.
        Templates check `has_value` to decide whether to prefill — that flag handles values
        that are legitimately falsy (0, empty string) without leaking that detail into the
        template. Returns the input unchanged when prior_values is empty."""
        if not prior_values:
            return question_data

        q = dict(question_data)
        if 'id' in q and q['id'] in prior_values:
            q['value'] = prior_values[q['id']]
            q['has_value'] = True

        parent_type = (q.get('questiontype') or '').lower()

        # Expanded types (e.g. video) store one row across multiple suffixed
        # columns. Surface those priors as `prior_<suffix>` so the template
        # can repopulate hidden fields when a participant returns mid-flow.
        from BOFS.validation import EXPANDED_TYPES
        if parent_type in EXPANDED_TYPES and 'id' in q:
            for suffix, _dtype in EXPANDED_TYPES[parent_type]:
                full_id = q['id'] + suffix
                if full_id in prior_values:
                    q['prior' + suffix] = prior_values[full_id]

        # image_click in single-click mode stores _x/_y like an expanded type.
        # (Multi-click mode stores a JSON string under the bare id, which the
        # generic `id in prior_values` branch above already populates as `value`.)
        if parent_type == 'image_click' and 'id' in q:
            max_clicks = q.get('max_clicks', 1)
            if isinstance(max_clicks, int) and max_clicks == 1:
                for suffix in ('_x', '_y'):
                    full_id = q['id'] + suffix
                    if full_id in prior_values:
                        q['prior' + suffix] = prior_values[full_id]
        for sub_key in ('questions', 'q_text'):
            subs = q.get(sub_key)
            if not isinstance(subs, list):
                continue
            new_subs = []
            for sub in subs:
                if parent_type == 'group' and isinstance(sub, dict):
                    # Group sub-questions are heterogeneous and may be
                    # expanded-types (audio/video/image_click) themselves —
                    # recurse so each sub goes through its own type-specific
                    # prior-value handling.
                    new_subs.append(
                        ParticipantQuestionnaireService._inject_prior_values(
                            sub, prior_values
                        )
                    )
                elif isinstance(sub, dict) and sub.get('id') in prior_values:
                    s = dict(sub)
                    s['value'] = prior_values[sub['id']]
                    s['has_value'] = True
                    # Plain checklist sub-questions are boolean: stored 1 means checked.
                    if parent_type == 'checklist' and not sub.get('text_entry'):
                        s['checked'] = s['value'] == 1
                    new_subs.append(s)
                else:
                    new_subs.append(sub)
            q[sub_key] = new_subs

        return q

    @staticmethod
    def render_questionnaire_question(question_type: str, question_data: dict) -> str:
        if 'participantID' not in session:
            raise Exception('Error: No participantID in session. Did you forget /consent or /create_participant, etc.?')

        participant = db.session.get(db.Participant, session['participantID'])

        try:
            return render_template(f'questions/{question_type}.html',
                                   question=question_data,
                                   participant=participant)
        except Exception as ex:
            if current_app.run_with_debugging:
                debugging_info = str(ex) + "<p><pre>" + str(traceback.format_exc()) + "</pre>"
            else:
                debugging_info = str(ex)

            return f"Exception in <b>{question_type}.html</b>: {debugging_info}"

    @staticmethod
    def render_unloaded_questionnaire(json_data: dict, template_name='questionnaire.html', tag="", prior_values: dict = None, **kwargs):
        questions_html = []
        prior_values = prior_values or {}

        # Render the HTML for each question. For groups, pre-render each
        # sub-question through the same render_questionnaire_question path
        # used for top-level questions — this is what gets each sub the
        # per-question try/except wrapper and the explicit ``participant``
        # kwarg. The pre-rendered strings are stashed on the group's dict
        # under ``_sub_html`` (parallel to ``questions``) and the group
        # template splices them in by loop index, mirroring how the outer
        # macro consumes ``q_html``.
        for question_data in json_data['questions']:
            injected = ParticipantQuestionnaireService._inject_prior_values(question_data, prior_values)

            if injected.get('questiontype') == 'group':
                sub_html = []
                for sub in injected.get('questions', []) or []:
                    sub_type = sub.get('questiontype') if isinstance(sub, dict) else None
                    if sub_type == 'group' or not isinstance(sub_type, str):
                        # Validation rejects nested groups; if one slips
                        # through, surface it inline rather than crashing
                        # the whole group render.
                        sub_html.append(
                            '<div class="bofs-error">Invalid sub-question '
                            'inside group.</div>'
                        )
                    else:
                        sub_html.append(
                            ParticipantQuestionnaireService.render_questionnaire_question(
                                sub_type, sub
                            )
                        )
                injected = dict(injected)
                injected['_sub_html'] = sub_html

            question_html = ParticipantQuestionnaireService.render_questionnaire_question(
                injected['questiontype'], injected)
            questions_html.append(question_html)

        return render_template(template_name,
                               **kwargs,
                               tag=tag,
                               q=json_data,
                               q_html=questions_html,
                               timeStarted=utcnow_naive())
