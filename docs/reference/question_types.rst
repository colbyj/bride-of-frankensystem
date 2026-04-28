Built-in Question Types
=======================

The following attributes are common to every type of question.

-  ``id``: string - Your field's unique id.

   - **This must be completely unique within each questionnaire.**
   - This can be omitted for question types which contain ``id``
     fields for each item in the question (e.g., radiogrid and checklist)

-  ``questiontype``: string - Defines the type of question/input field
   this is
-  ``instructions``: string - Appears directly above the field to
   indicate what the user should enter inside the field.
-  ``title``: string - Add text above the question, outside the question's
   box.

Note: Many of the attributes that accept strings support HTML, such as
``instructions`` and ``title``. However, JSON does not support line breaks, so
any HTML needs to appear on one line.

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
-  ``video`` - Embed an HTML5 video, optionally requiring the participant to
   watch it before continuing

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
-  ``required``: whether or not responses to this radio grid are required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``shuffle``: should the question order be shuffled? (optional,
   boolean: ``true`` or ``false``, default ``false``)
-  ``labels``: list of strings that represent column headers (required,
   list of strings)
-  ``questions``: list of dictionaries that describe each individual
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
           "questions": [
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

-  ``id``: Unique id for checklist (required, string)
-  ``instructions``: Text needed to describe what slider input
   represents (optional, string)
-  ``required``: whether or not this input is required to submit form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``required_selection``: If specified, force the user to select the specified value before the form can be submitted (optional, string).
-  ``shuffle``: Whether or not the possible response labels should be
   shuffled (optional, boolean: ``true`` or ``false``, default is
   ``false``)
-  ``horizontal``: Should the options be listed vertically (default) or
   horizontally? (optional, boolean: ``true`` or ``false``, default is
   ``true``)
-  ``labels``: A list. One entry per each radio button. (required, list
   of strings)
-  ``other_enabled``: Show an "other" option as one of the options in the list.
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``other_text_prompt``: Specify the text to indicate what the "other" option means (optional, string).
-  ``other_input_width``: How wide the input field for the "other" option should be (optional, integer).
-  ``other_input_hides``: Should the input field for the "other" hide if not selected (optional, boolean, default ``false``)?

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

-  ``instructions``: text needed to describe what slider input
   represents (optional, string)
-  ``shuffle``: should the order of the responses be shuffled?
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``horizontal``: should be options be listed vertically? (optional,
   boolean: ``true`` or ``false``, default is ``true``)
-  ``questions``: one for each checkbox, a list of dictionaries, each with the following keys.

   - ``id``: Must be unique within the questionnaire (required, integer).
   - ``text``: The label for the option (required, string).
   - ``text_entry``: Are users allowed to enter custom text to be associated with this checkbox (optional, boolean, default ``false``)?
   - ``text_entry_hides``: Does the text input area hide if the option is not selected (optional, boolean, default ``false``)?
   - ``text_entry_width``: How wide the input field for the text entry should be (optional, integer).

**Example**

.. code:: json

       {
           "questiontype":"checklist",
           "instructions":"choose any options...",
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

**Properties**

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

video
-----

``questiontype == 'video'``

Embeds an HTML5 ``<video>`` element from any URL. Can optionally require the
participant to watch the video to completion before the *Continue* button is
enabled, and (when ``id`` is set) records viewing telemetry to the database.

**How "force watch" works**

When ``force_watch`` is ``true``, the *Continue* button is disabled and an
explanatory notice appears beside it. A watched-time accumulator counts only
forward playback while the tab is visible — forward seeks, backward seeks,
playback rate changes, and background-tab playback do not count. The button
unlocks once the accumulator reaches ``completion_threshold`` of the video's
duration. If multiple videos on the same page set ``force_watch``, the
button is gated until *all* of them are satisfied.

When ``minimal_controls`` is ``false`` (the default), the native video
controls are shown and a "snap-back" guard prevents the participant from
scrubbing past the supposed playhead position. When ``minimal_controls`` is
``true``, the native controls are hidden entirely and only a custom
*Play/Pause* button is rendered, so seeking is impossible by construction.

**Properties**

-  ``src``: URL of the video file (required, string)
-  ``id``: when set, three columns are written to the questionnaire table
   (optional, string):

   -  ``{id}_started`` — epoch seconds when the participant first pressed
      play, or ``0`` if they never started it
   -  ``{id}_ended`` — epoch seconds at the last observed activity
      (play / timeupdate / pause / ended)
   -  ``{id}_watched`` — accumulated forward play time, in seconds

-  ``width``, ``height``: pixel dimensions for the video element
   (optional, integer)
-  ``autoplay``: start playing as soon as the page loads (optional, boolean,
   default ``false``)
-  ``force_watch``: disable the *Continue* button until the participant has
   watched ``completion_threshold`` of the video (optional, boolean,
   default ``false``)
-  ``completion_threshold``: fraction of the video's duration that counts
   as "watched" (optional, float between 0 and 1, default ``0.98``)
-  ``minimal_controls``: hide the native player controls and show only a
   custom Play/Pause button (optional, boolean, default ``false``)

**Example**

.. code:: json

       {
           "questiontype": "video",
           "id": "tutorial_video",
           "instructions": "Please watch the entire tutorial before continuing.",
           "src": "https://example.com/static/tutorial.webm",
           "width": 940,
           "height": 530,
           "force_watch": true,
           "completion_threshold": 0.95,
           "minimal_controls": true
       }
