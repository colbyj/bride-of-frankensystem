Creating Custom Questions
=========================

It is possible to create your own custom question types to use within questionnaires. These are defined inside of your
templates directory (for your blueprint, or your project), within the questions folder, so ``/templates/questions/``.

Custom question types are defined in an HTML file that leverages Jinja 2 templating. To make use of it when creating a
questionnaire, you specify a new question with a ``questiontype`` that matches the filename for your question (less the
``.html`` extension).

So for a question type of "custom", you need a .html file, ``/templates/questions/custom.html``. You would use that
custom question within your questionnaire's JSON via:

.. code-block:: json

    {
      "questiontype": "custom",
      "instructions": "I am special",
      "id": "special"
    }

The keys shown here are the minimum required. The ``instructions`` will show above the questions like any other BOFS
question, and the ``id`` gets used to generate the column within the database table (note that the ``id`` isn't
technically required, but without it, nothing can be saved to the database).

In the question template, you can use any HTML, JavaScript, Jinja 2 control structures, etc. that you want. If an input
with a ``name`` matches the ``id`` specified in the JSON question definition is in your question template, then that
input field will get written to the database when the form is submitted.

An important aspect about how the question template works is that all of the JSON data that you define about the
question in your questionnaire's JSON file gets passed to the template file as the ``question`` Jinja 2 variable.
Consider the example question template:

.. code-block:: html
    :caption: custom.html

    <p>Your condition is: {{ session['condition'] }}</p>
    <p>You chose "{{ participant.questionnaire("example").radiolist_1 }}" for radiolist_1 on the example questionnaire.</p>
    <p><b>Do you still agree with this?</b></p>

    <div class="form-check">
        <input class="form-check-input" type="radio" name="{{ question.id }}" id="{{ question.id }}_no" value="No">
        <label class="form-check-label" for="{{ question.id }}_no">No</label>
    </div>

    <div class="form-check">
        <input class="form-check-input" type="radio" name="{{ question.id }}" id="{{ question.id }}_yes" value="Yes">
        <label class="form-check-label" for="{{ question.id }}_yes">Yes</label>
    </div>

This template does some things that standard questions cannot do. First, it uses Jinja 2 to access the BOFS ``session``
variable and print out the participant's assigned condition. Consider what you could use this for. For example, you
might use a Jinja 2 `if statement <https://jinja.palletsprojects.com/en/latest/templates/#if>`_ to show something
different based on assigned condition.

Another thing it does is access the participant's questionnaire data. When rendering this template, the current instance
of the `Participant class <https://github.com/colbyj/bride-of-frankensystem/blob/master/BOFS/default/models.py>`_ (i.e.,
the current participant's data) is passed to the template. This gives access to, for example, the ``questionnaire()``
method, where you can access the data submitted to a questionnaire. This means you can show participants what their past
responses were, or do something different based on a past response.

Finally, notice that there is a ``questionnaire`` variable that was used, and the name of the radio input was set based
on this.

Multiple IDs
------------
One final note about IDs -- it is possible to have multiple IDs instead of just the one. This would let you have many
inputs associated with the one question type.

This is done just like the checklist and radiogrid question types:

.. code-block:: json

    {
      "questiontype": "custom2",
      "instructions": "I am a custom question with multiple inputs",
      "questions": [
        {
          "id": "question_1",
        },
        {
          "id": "question_2",
        },
        {
          "id": "question_3",
        }
      ]
    }

And then within your template you can use a Jinja 2 `for loop <https://jinja.palletsprojects.com/en/latest/templates/#for>`_:

.. code-block:: html
    :caption: custom2.html

    <div>
    {% for sub_question in question.questions %}
    Enter something: <input type="text" name="{{ sub_question.id }}" id="{{ sub_question.id }}"> <br>
    {% endfor %}
    </div>
