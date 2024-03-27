Defining Questions in JSON Syntax
=================================

The following attributes are common to every type of question (except
radiogrid).

-  ``id``: string - Your field's unique id. **This must be completely
   unique within each questionnaire.**
-  ``questiontype``: string - Defines the type of question/input field
   this is
-  ``instructions``: string - Appears directly above the field to
   indicate what the user should enter inside the field.

Currently, the following types of input are supported:

-  ``radiogrid`` - Display a collection of items in a grid. One row per
   item, with responses in a likert scale where the headers are shown
   above.
-  ``radiolist`` - Select one option out of a list
-  ``checklist`` - Select multiple options out of a list
-  ``slider`` - Drag the slider to a numeric value, with optional labels
   on the left and right.
-  ``field`` - Simple single-line text entry
-  ``num_field`` - Input a single number
-  ``multi_field`` - Multi-line text entry
-  ``drop_down`` - Select one option from a drop-down list
-  ``textview`` - Display plain text (HTML syntax is supported)

radiogrid
---------

``questiontype == 'radiogrid'``

-  contains one or more horizontal rows of radio buttons.
-  This input supports n-columns, and allows the researcher to provide a
   column header for each column.
-  A selection by the user is always required

**Properties**

-  ``instructions``: any text that is needed directly above the
   radiogrid (optional, string)
-  ``shuffle``: should the question order be shuffled? (optional,
   boolean: ``true`` or ``false``, default ``false``)
-  ``labels``: list of strings that represent column headers (required,
   list of strings)
-  ``q_text``: list of dictionaries that describe each individual
   question (required)

   -  ``id``: unique id of the row of radio buttons (string)
   -  ``text``: question text (string)

**Example**

.. code:: json

       {
           "questiontype": "radiogrid",
           "instructions": "Indicate how you feel about each food item.",
           "shuffle": true,
           "labels": [
               "I hate it!",
               "",
               "Neutral",
               "",
               "I love it!"
           ],
           "q_text": [
               {
                   "id": "q_1",
                   "text": "Ham"
               },
               {
                   "id": "q_2",
                   "text": "Bacon"
               },
               {
                   "id": "q_3",
                   "text": "Celery"
               }
           ]
       }

radiolist
---------

``questiontype == 'radiolist'``

**Properties**

-  ``id``: unique id for checklist (required, string)
-  ``instructions``: text needed to describe what slider input
   represents (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``shuffle``: whether or not the possible response labels should be
   shuffled (optional, boolean: ``true`` or ``false``, default is
   ``false``)
-  ``horizontal``: should be options be listed vertically (default) or
   horizontally? (optional, boolean: ``true`` or ``false``, default is
   ``true``)
-  ``labels``: A list. One entry per each radio button. (required, list
   of strings)

**Example**

.. code:: json

       {
           "questiontype":"radiolist",
           "instructions":"Do you eat meat?",
           "id":"radiolist_1",
           "horizontal": false,
           "required": true,
           "labels":[
               "Always",
               "Sometimes",
               "Never"
           ]
       }

checklist
---------

``questiontype == 'checklist'``

**Properties**

-  ``id``: unique id for checklist (required, string)
-  ``instructions``: text needed to describe what slider input
   represents (optional, string)
-  ``shuffle``: should the order of the responses be shuffled?
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``horizontal``: should be options be listed vertically? (optional,
   boolean: ``true`` or ``false``, default is ``true``)
-  ``questions``: one for each checkbox. Each needs text and a unique
   ID. (required)

**Example**

.. code:: json

       {
           "questiontype":"checklist",
           "instructions":"choose any options...",
           "id":"checklist_1",
           "shuffle":true,
           "horizontal": false,
           "questions":[
               {
                   "id":"cl_1",
                   "text":"Option 1"
               },
               {
                   "id":"cl_2",
                   "text":"Option 2"
               },
               {
                   "id":"cl_3",
                   "text":"Option 3"
               }
           ]
       }

slider
------

``questiontype == 'slider'``

**Properties**

-  ``id``: unique id for slider (string)
-  ``instructions``: text needed to describe what slider input
   represents (optional, string)
-  ``left``: text for left label (optional, string)
-  ``right``: text for right label (optional, string)
-  ``tick_count``: number of ticks represented by the slider (required,
   integer)
-  ``width``: width of drop down (optional, integer, default ``400``)

**Example**

.. code:: json

       {
           "questiontype": "slider",
           "instructions": "I am a slider",
           "id": "slider_1",
           "left": "left",
           "right": "right",
           "tick_count": 5
       }

field
-----

``questiontype == 'field'``

-  Standard single-line text entry field.

**Properties**

-  ``id``: unique id for text field (required, string)
-  ``instructions``: text needed to describe what field input should be
   (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``placeholder``: example text to show in field by default (optional,
   string)
-  ``width``: width of the field (optional, integer, default ``400``)

**Example**

.. code:: json

       {
           "questiontype": "field",
           "instructions": "enter text",
           "placeholder": "I am a placeholder",
           "id": "input_1"
       }

num_field
---------

``questiontype == 'num_field'``

-  Numeric text entry field.

**Properties**

-  ``id``: unique id for number field (required, string)
-  ``instructions``: text needed to describe what field input should be
   (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``min``: minimum range for input (optional, integer)
-  ``max``: maximum range for input (optional, integer)
-  ``width``: width of the field (optional, integer, default ``400``)

**Example**

.. code:: json

       {
           "questiontype": "num_field",
           "datatype": "integer",
           "instructions": "enter a number",
           "id": "input_1"
       }

multi_field
-----------

``questiontype == 'multi_field'``

-  Multi-line text field.

**Properites**

-  ``id``: unique id for number field (required, string)
-  ``instructions``: text needed to describe what field input should be
   (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``placeholder``: example text to show in field by default (optional,
   string)
-  ``height``: height of multifield (optional, integer, default ``80``)
-  ``width``: width of the field (optional, integer, default ``400``)

**Example**

.. code:: json

       {
           "questiontype": "multi_field",
           "id": "big",
           "placeholder": "I am holding the place",
           "instructions": "big text field",
           "height": 100
       }

drop_down
---------

``questiontype == 'drop_down'``

**Properties**

-  ``id``: unique id for drop down menu (required, string)
-  ``instructions``: text to describe what the selection is for
   (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``items``: list of strings to describe possible selections in drop
   down menu (list of strings)
-  ``width``: width of the drop down (optional, integer, default
   ``400``)

**Example**

.. code:: json

       {
           "questiontype": "drop_down",
           "instructions": "Which of the listed fruits is your favorite?",
           "items": [
               "apples", "oranges", "watermelon"
           ]
       }

textview
--------

``questiontype == 'textview'``

**Properties**

-  ``instructions``: title for block of text (optional, string)
-  ``text``: block of text to be displayed (optional, string)

**Example**

.. code:: json

       {
           "questiontype": "textview",
           "instructions": "Some header",
           "text": "These are some instructions which will appear wherever you place this question."
       }
