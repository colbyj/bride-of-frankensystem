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
        # Check to see if the user has submitted this once already...
        previous = db.session.query(questionnaire.db_class).filter(
            questionnaire.db_class.participantID == self.participant_id,
            questionnaire.db_class.tag == tag
        ).all()

        if previous and len(previous) == 1:
            new_object = previous[0]
        else:
            new_object = questionnaire.db_class()

        try:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S.%f")
        except:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S")

        fields = questionnaire.fetch_fields()

        try:
            for click_event in str(request.form['gridItemClicks']).split(";"):
                if len(click_event) == 0:
                    continue  # There is no data (is it the last line?), so skip it.

                click_event = click_event.replace('\\', "")
                click_event_dict = json.loads(click_event)

                parsed_time = datetime.fromtimestamp(float(click_event_dict['time']))

                new_log = db.RadioGridLog()
                new_log.participantID = self.participant_id
                new_log.questionnaire = questionnaire.file_name
                new_log.tag = tag
                new_log.questionID = click_event_dict['id']
                new_log.timeClicked = parsed_time
                new_log.value = click_event_dict['value']

                db.session.add(new_log)

            db.session.commit()

        except:
            pass

        for field in fields:
            try:
                value = request.form.get(field.id, None)
                if value is not None:
                    setattr(new_object, field.id, value)
                else:
                    attr = getattr(questionnaire.db_class, field.id)
                    default = attr.expression.default.arg
                    setattr(new_object, field.id, default)
            except:
                print("Could not write field " + str(field.id))

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
        prior_values = self.fetch_prior_values(questionnaire, tag)
        return ParticipantQuestionnaireService.render_unloaded_questionnaire(
            questionnaire.json_data, template_name, tag, prior_values=prior_values)

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
        for sub_key in ('questions', 'q_text'):
            subs = q.get(sub_key)
            if not isinstance(subs, list):
                continue
            new_subs = []
            for sub in subs:
                if isinstance(sub, dict) and sub.get('id') in prior_values:
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

        # Render the HTML for each question
        for question_data in json_data['questions']:
            injected = ParticipantQuestionnaireService._inject_prior_values(question_data, prior_values)
            question_html = ParticipantQuestionnaireService.render_questionnaire_question(
                injected['questiontype'], injected)
            questions_html.append(question_html)

        return render_template(template_name,
                               **kwargs,
                               tag=tag,
                               q=json_data,
                               q_html=questions_html,
                               timeStarted=utcnow_naive())
