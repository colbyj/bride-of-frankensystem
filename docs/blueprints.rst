Adding Custom Routes (Blueprints)
=================================

Custom web pages and functionality can be added to your Bride of Frankensystem projects by making use of Flask
Blueprints. The Flask documentation describes `blueprints <https://flask.palletsprojects.com/en/latest/tutorial/views/>`_
as a way to organize groups of related views and other code ("view" refers to the web page seen by end users). You may
find it helpful to look through Flask's documentation to see code for some example pages.

The code you write for BOFS Blueprints is like any other Flask blueprint, with the exception that your files must
be structured in a specific way. BOFS blueprints must be in their own directory inside of your project's root directory.

For example, consider a blueprint called "my_blueprint":

.. code-block:: text

    /my_blueprint/__init__.py
    /my_blueprint/views.py
    /my_blueprint/templates
    /my_blueprint/static

* ``__init__.py`` is a mandatory file to indicate that this is a Python package. It will typically be empty.
* ``views.py`` is a mandatory file that contains your code for your custom Flask views (web pages).

The Views File
--------------

Views are made up of three different components.

* **HTML templates**, which are defined in HTML and the Jinja2 templating system and are placed within ``/my_blueprint/templates``.
* **Static files**, such as images and Javascript and are placed within ``/my_blueprint/static``.
* **Python code** that controls what BOFS should do and display, within ``/my_blueprint/views.py``.

Your ``views.py`` will initially look something like this (feel free to use this as a starting point in your own blueprint):

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


The arguments passed to the ``Blueprint()`` constructor generally do not need to be adjusted (aside from the name, "my_blueprint").
If you want to learn more about how this works then refer to the Flask documentation.


Creating Routes
---------------

Routes define the actual pages that users can visit. This documentation will not go into much detail as to how routes
work, so if you have further questions, do visit the Flask documentation and see if your questions are answered there.

Python Code
~~~~~~~~~~~

In BOFS, your routes will look something like this (this route is directly from the `advanced example <https://github.com/colbyj/bride-of-frankensystem-examples/blob/master/advanced_example/my_blueprint/views.py>`_):

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

This ``task()`` function has three decorators on it. The first one (``@my_blueprint.route()``) registers the function as
a route associated with the ``/task`` URL, and indicates that the URL will accept POST requests (e.g., form submissions)
and GET requests (in which the user asks to see what is at that URL). Note that within the function, ``request.method``
is checked and if it is a POST request, then something is added to the database.

The second decorator (``@verify_correct_page``) ensures that the user does not access this page except for when accessed
by following the order defined within ``PAGE_LIST``.

The third decorator (``@verify_session_valid``) checks that the user has the correct session values set and if not,
redirects them to the first page listed in ``PAGE_LIST``.

This function has two return values. At the bottom, the return value of the function in this example renders a template
that will show the user the task. Two variables are sent to the template that configure aspects of how the template
should render to the participant (``example`` and ``incorrect``). If a POST request was made, then an alternative return
value is to do a redirection to ``/redirect_next_page``, which takes the user to the next page in ``PAGE_LIST`` after
the ``/task`` page.

.. tip:: To better understand this example, you may want to run the provided advanced example project and see what ``/task`` looks like for yourself.


Database Tables
~~~~~~~~~~~~~~~

This example makes use of a database table. For more information on how to use database tables in your custom routes,
see :doc:`tables`.

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