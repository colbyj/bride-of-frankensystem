Advanced Custom Pages
=====================

For pages that need server-side logic — interactive tasks, form processing, dynamic content, or anything that talks to a custom database table or external API — BOFS uses `Flask Blueprints <https://flask.palletsprojects.com/en/latest/tutorial/views/>`_. A blueprint is a folder containing Python code, HTML templates, and static files (images, JavaScript), and BOFS auto-discovers any blueprint folder inside your project directory.

.. note::
    This section assumes basic Python programming knowledge. For static instruction or content pages that don't need any code, see :doc:`../getting_started/simple_custom_pages` instead.

Blueprint Layout
----------------

Each blueprint lives in its own folder at the project root. For a blueprint named ``my_blueprint``:

.. code-block:: text

    /my_blueprint/__init__.py
    /my_blueprint/views.py
    /my_blueprint/templates/
    /my_blueprint/static/

* ``__init__.py`` marks the folder as a Python package. It can be empty.
* ``views.py`` holds your route definitions.
* ``templates/`` holds Jinja2 HTML templates rendered by your routes.
* ``static/`` holds static assets — images, JavaScript, CSS — served alongside the blueprint.

The Views File
--------------

Your ``views.py`` starts out something like this:

.. code-block:: python
    :caption: views.py

    from flask import Blueprint, render_template
    from BOFS.util import *
    from BOFS.globals import db

    # The name of this variable must match the folder's name.
    my_blueprint = Blueprint('my_blueprint', __name__,
                             static_url_path='/my_blueprint',
                             template_folder='templates',
                             static_folder='static')


The ``Blueprint()`` arguments rarely need adjusting beyond the name. The Flask documentation explains the constructor in full if you're curious.

Creating Routes
---------------

Routes define the pages users can visit. The Flask documentation covers routing in depth; this section sticks to BOFS-specific concerns.

Writing Code
~~~~~~~~~~~~

A typical route, taken from the `advanced example <https://github.com/colbyj/bride-of-frankensystem-examples/blob/master/advanced_example/my_blueprint/views.py>`_:

.. code-block:: python
    :caption: views.py

    # preceding code in views.py omitted for brevity.

    @my_blueprint.route("/task", methods=['POST', 'GET'])
    @verify_correct_page
    @verify_session_valid
    def task():
        incorrect = None

        if request.method == 'POST':
            log = db.answers()  # This database table was defined in /advanced_example/tables/answers.json
            log.participantID = session['participantID']
            log.answer = request.form['answer']

            db.session.add(log)
            db.session.commit()

            if log.answer.lower() == "linux":
                return redirect("/redirect_next_page")
            incorrect = True

        return render_template("task.html", example="This is example text.", incorrect=incorrect)

Three decorators are stacked on this route:

* ``@my_blueprint.route("/task", methods=['POST', 'GET'])`` registers the function at ``/task`` and accepts both GET (loading the page) and POST (form submission) requests.
* ``@verify_correct_page`` prevents participants from visiting this page out of order — they have to reach it by following ``PAGE_LIST``.
* ``@verify_session_valid`` redirects participants to the first page of ``PAGE_LIST`` if their session is missing the expected values.

The function has two return paths. On a GET (or a wrong POST answer), it renders ``task.html`` with the ``example`` and ``incorrect`` variables. On a correct POST it writes the answer to the ``answers`` table and redirects to ``/redirect_next_page``, which sends the participant to the next entry in ``PAGE_LIST``.

.. tip:: Run the advanced example project locally and visit its ``/task`` page to see this in action.

The example also writes to a custom database table (``db.answers()``); custom tables are described in :doc:`database_tables`.

Accessing Questionnaire Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is possible to access the responses a participant has given to your questionnaires from within your custom code.
At the top of your ``views.py`` file, ensure that you are importing ``db`` from ``BOFS.globals``:

.. code-block:: python

    from BOFS.globals import db

Then inside of your custom route's function, you can access the data for the participant who is viewing your route.

.. code-block:: python

    participant = db.Participant.query.get(session['participantID'])

This gives you an instance of the the Participant class (defined in `/BOFS/default/models.py <https://github.com/colbyj/bride-of-frankensystem/blob/master/BOFS/default/models.py>`_),
with which you can access the attributes associated with that participant. There is a ``questionnaire()`` method that is relevant.
It takes in as arguments the name of the questionnaire (the filename without the ``.json`` extension) and the tag (which is often just a blank string ``""``).

Calling this method will return an instance of the related questionnaire, whose attributes are defined by the ``id`` used within the questionnaire.

Therefore, for a questionnaire named "demographics" and a question id of "age", you can get the age of the participant via:

.. code-block:: python

    participant = db.Participant.query.get(session['participantID'])
    age = participant.questionnaire('demographics').age


For more details, please see :doc:`accessing_participant_data`.


Redirecting Participants
~~~~~~~~~~~~~~~~~~~~~~~~

If you want to redirect participants, then it is crucial that you set the related session variable, ``currentUrl``.

For example, to redirect a participant to ``questionnaire/example``, you can use the following code within your route:

.. code-block:: python

    new_url = 'questionnaire/example'
    session['currentUrl'] = new_url
    return redirect('/' + new_url)

Keep in mind that the new URL should be defined somewhere inside of your ``PAGE_LIST`` configuration variable, otherwise
the system may redirect the participant somewhere else.


Templates (HTML) and Static Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The presentation of the page is defined in the ``task.html`` template.

.. code-block:: html
    :caption: task.html

    {% extends "template.html" %}
    {% block head %}
    {% endblock %}

    {% block content %}
        {% if incorrect %}
            <h1>You were wrong! Try again.</h1>
        {% else %}
            <div>
                <h3>Some Information</h3>
                <ul>
                    <li>Your participant ID is {{ session['participantID'] }}.</li>
                    <li>You were assigned to condition {{ session['condition'] }}.</li>
                    <li>This is the value of <tt>example</tt>: {{ example }}</li>
                </ul>
            </div>
        {% endif %}

        <hr>

        <form id="form" action="#" method="post">
            <p><img src="{{ url_for('my_blueprint.static', filename='tux.png') }}"></p>

            <p>
                <label for="answer">This is the mascot for which operating system?</label>
                <input type="text" id="answer" name="answer" required>
            </p>

            <input type="submit" name="submit" value="Submit Answer">
        </form>
    {% endblock %}

This template extends ``template.html``, which means that it will have the look and feel of other pages in BOFS. The
``template.html`` has two blocks, "head" and "content". By defining them in your own template (as in ``task.html``),
you can add your own content to the head of the page (useful for CSS, etc.) as well the body of the page.

This template demonstrates how to use **variables** and **static** content.  In particular, ``incorrect`` and ``example`` were
variables passed to the template from ``render_template()`` and are now being used, as well as ``session``, which is
always available to be used within the template. Static content is being demonstrated via displaying an image located at
``/my_blueprint/static/tux.png``.

In addition to ``session``, you will always have access to the following variables within your templates:

* ``session['participantID']`` - Accessible on routes that are decorated with ``@verify_session_valid``.
* ``session['condition']`` - Accessible on routes that ``@verify_session_valid``.
* ``debug`` - A boolean indicating whether the project is being run in debug mode.
* ``config[...]`` - Flask/BOFS configuration settings.

For more details on ``url_for()``, see the `Flask documentation on url_for() <https://flask.palletsprojects.com/en/latest/api/#flask.url_for>`_.

For more details on how Jinja2 templates work, see the `Flask documentation on templates <https://flask.palletsprojects.com/en/latest/tutorial/templates/>`_.