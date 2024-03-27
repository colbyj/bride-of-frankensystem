Questionnaires
==============

Bride of Frankensystem includes a simple questionnaire system for displaying static questionnaires. These questionnaires
are defined in the JSON language so that they can be easily re-used across multiple projects and shared.

For an example of the JSON markup for a complete questionnaire, see :ref:`example`.

Creating Questionnaires
-----------------------

Questionnaires are defined as JSON files and placed within your project under the ``/questionnaires`` directory.

Syntax of a Questionnaire
~~~~~~~~~~~~~~~~~~~~~~~~~

Questionnaires are created by defining the structure of the questionnaire within a `.json` file. This stucture is made up of key-value pairs.
For an introduction to the syntax and structure of JSON and see `this tutorial <https://www.digitalocean.com/community/tutorials/an-introduction-to-json>`_.

The overall structure of the ``.json`` files that define questionnaires looks like this:

.. code-block:: JSON
    :linenos:

    {
        "title": "",
        "reference": "",
        "doi": "",
        "instructions": "",
        "code":"",
        "questions": [ ],
        "participant_calculations": {}
    }

============================= ========== ====================
Key                           Data Type  Description of value
============================= ========== ====================
``title``                     string     Optional field used to label the questionnaire for reference only. This is never shown to participants and only shows up on the preview in the Administration section.
``reference``                 string     Optional field to store the citation information for the questionnaire. This is never shown to participants and only shows up on the preview in the Administration section.
``doi``                       string     Optional field to store the doi string relating to the citation. This is never shown to participants and only shows up as a link on the preview in the Administration section.
``instructions``              string     Instructions to appear at the top of the form, before any questions are asked. Supports HTML. Optional.
``code``                      string     For advanced users. JavaScript code to be executed at run time. Optional.
``questions``                 list       A list of questions. Each question is defined as a dictionary of key-value pairs. Question types are shown below.
``participant_calculations``  dictionary A dictionary of named calculated fields. The keys are the name of the calculated field and the value is the calculation. The calculation is Python-compatible code that gets executed for the calculation. Question IDs can be used as variables, and the code is not sand-boxed in any way, so some caution is required.
============================= ========== ====================

.. NOTE::
    You can safely add new keys here as desired and they will be ignored by BOFS. This can be used to add relevant
    metadata for the questionnaire, including the citation, questionnaire name, or instructions to the researcher.


Adding Questions
~~~~~~~~~~~~~~~~

On line 7 of the example of the JSON structure for questionnaires, you can see that there is a blank list (`[]`). It is
within this list that new questions can be added to the questionnaire. For examples of how to define questions of
different types, see the example below. For a detailed reference, see :doc:`question_types`.



.. _example:

Example Questionnaire
~~~~~~~~~~~~~~~~~~~~~
An example questionnaire demonstrating every question type.

.. literalinclude:: example.json
    :caption: example.json
    :language: JSON


Participant Calculations
~~~~~~~~~~~~~~~~~~~~~~~~

You can perform calculations with the data captured by this questionnaire. These calculations are done on a
per-participant basis. So you can, for example, calculate a participant's score on a set of questions, or work out the
value associated with a particular scale.

The calculations must be placed within the ```participant_calculations`` dictionary.
The key is the variable name (this will become the column header in the export) and the value is Python code that
represents the calculation. The Python code can reference any of the question ``id``s within the questionnaire.

**Example**

.. code-block:: JSON

    {
        /* title, questions, etc. hidden for brevity. */
        "participant_calculations":
        {
            "MyCalculatedVariable": "mean([id01, id02, id03, id04, id05])"
        }
    }

The following functions are supported: ``mean``, ``variance``, ``std``, and ``median``.

Below is a complete questionnaire featuring calculations:

.. literalinclude:: grid.json
    :caption: grid.json
    :language: JSON


Previewing Questionnaires
-------------------------

Every questionnaire inside of the ``/questionnaires`` directory can be previewed from within BOFS via the admin panel.
This is accessed at ``http://<host>:<port>/admin``. ``host`` is the IP address of the system on which BOFS is running
and if running locally will be ``127.0.0.1``. ``port`` is defined within your project's configuration file and is shown
when the project is run via the ``BOFS`` command.

The preview will inform you of any and all syntax errors, and offer to add columns to the database if this questionnaire
is one listed in the page sequence and it detects that there are new columns to add. For this reason, it is recommended
that you use this preview feature when developing new questionnaires.


Adding Questionnaires to Your Study
-----------------------------------

Questionnaires must be added to the ``PAGE_LIST`` variable within your project's configuration file to be displayed to
the end user. After adding the questionnaires ``.json`` file to `/questionnaires`, you then add a entry to
``PAGE_LIST``.

For example, the ``my_questionnaire.json`` file will have the ``PAGE_LIST`` entry:

    ``{'name': 'Questionnaire', 'path': 'questionnaire/my_questionnaire'}``

Doing this signals BOFS that a database table should be created for the questionnaire. Once the study is run, this
table with get created.

If changes are made to the questionnaire, the table will `not` get updated to match. This is a problem any time a
question ID changes or whenever a new question gets added. The easiest way to resolve this is to delete the database
file and restart the project. This does mean you lose your data, so this option is only viable during development.

For a live database with participant data, you have three options:

1. ``DROP`` the table.
    - You lose data, but this time it's just the one table.

2. Add the missing columns.
    - This can get ugly as it has the potential to leave in old columns when renaming.
    - This can be done automatically within the system when previewing questionnaires.
    - This doesn't fix issues with mismatched data types if the type was changed

3. Alter the table directly.
    - This is tidiest solution if you need to modify a database with existing data. With SQLite, you would have to rename the table, create a new table with the correct structure and name, then copy over the data with an ``INSERT INTO ... SELECT ...`` statement. Other DBMS allow you to alter the table more directly.

If you drop the table or delete the database, you will need to restart the app in order for the table to be generated.
