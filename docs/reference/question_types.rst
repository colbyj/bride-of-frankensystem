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
-  ``picture_select`` - Select one option from a set of images
-  ``image_click`` - Click on an image to record one or more (x, y)
   positions in the image's natural pixel space
-  ``textview`` - Display plain text (HTML syntax is supported)
-  ``video`` - Embed an HTML5 video, optionally requiring the participant to
   watch it before continuing
-  ``audio`` - Embed an HTML5 audio clip, optionally requiring the participant
   to listen to it before continuing
-  ``group`` - Render a header followed by several sub-questions of any other
   type, optionally laid out side-by-side

radiogrid
---------

``questiontype == 'radiogrid'``

-  contains one or more horizontal rows of radio buttons.
-  This input supports n-columns, and allows the researcher to provide a
   column header for each column.

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

-  ``na_column``: add an extra column at the right of the grid for an
   "N/A" option. Selecting it satisfies ``required`` but stores the
   row's value as ``NULL``. (optional, boolean, default ``false``)
-  ``na_label``: header text for the N/A column. (optional, string,
   default ``"N/A"``)
-  ``store_labels``: store the chosen column's label string (e.g.
   ``"Strongly agree"``) instead of its 1-based index. Calculated fields
   that reference rows in this grid are rejected at questionnaire load
   time, since label values are not numeric. (optional, boolean,
   default ``false``)

.. note::

   Radiogrid row columns are nullable so the ``na_column`` option can
   record ``NULL``. Tables created before this option existed have
   non-null columns; to use ``na_column`` on a previously deployed
   questionnaire, drop or alter the existing table so it can be
   recreated with the new schema.

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

picture_select
--------------

``questiontype == 'picture_select'``

Select one option out of a set of images. Each image becomes a clickable
thumbnail; the participant's selection is stored as the chosen image's
``value``. Only one image can be selected at a time (radio behaviour).

**Properties**

-  ``id``: unique id for this question (required, string)
-  ``instructions``: text shown above the image grid (optional, string)
-  ``required``: whether a selection is required to submit the form
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``shuffle``: whether to shuffle the image order on each render
   (optional, boolean: ``true`` or ``false``, default is ``false``)
-  ``horizontal``: when ``true`` (the default), images wrap in a centered
   row; when ``false``, they stack in a single centered column (optional,
   boolean: ``true`` or ``false``, default is ``true``)
-  ``width``: explicit width (in pixels) applied to every image
   (optional, integer). Ignored when ``auto_resize`` is ``true``.
-  ``auto_resize``: normalize the rendered image dimensions on the client
   so they all match the smallest image in the group. With
   ``horizontal: false`` all widths are matched to the smallest natural
   width; otherwise all heights are matched to the smallest natural
   height (optional, boolean: ``true`` or ``false``, default is
   ``false``).
-  ``images``: list of image entries (required). Each entry is an object:

   -  ``src``: URL of the image (required, string), e.g.
      ``/static/option_a.png``
   -  ``value``: value stored in the database when this image is
      selected (required, string / integer / float). When every entry's
      ``value`` is an integer (or float), the database column is created
      with that numeric type automatically.
   -  ``label``: short caption shown beneath the image, also used as
      ``alt`` text fallback (optional, string)
   -  ``alt``: explicit ``alt`` text for the ``<img>`` tag. Use this when
      the screen-reader description should differ from the visible
      caption, or set it to ``""`` for a purely decorative image
      (optional, string)

**Example**

.. code:: json

       {
           "questiontype": "picture_select",
           "id": "favorite_picture",
           "instructions": "Pick whichever you'd rather look at.",
           "auto_resize": true,
           "required": true,
           "images": [
               {"src": "/static/option_a.jpg", "value": 1, "label": "Option A"},
               {"src": "/static/option_b.jpg", "value": 2, "label": "Option B"}
           ]
       }


image_click
-----------

``questiontype == 'image_click'``

Displays an image and stores the natural-image pixel coordinates of one or
more clicks. Each click leaves a crosshair marker at the cursor position.

Coordinates are reported in the source image's *natural* pixel space
(origin top-left, x to the right, y downward), independent of how the
browser sized the image. A click on a 1000×800 image always lands within
``(0, 0)–(1000, 800)`` even when the image was scaled to fit the viewport.

**Properties**

-  ``id``: unique id for this question (required, string)
-  ``src``: URL of the image to display (required, string), e.g.
   ``/static/map.png``
-  ``instructions``: text shown above the image (optional, string)
-  ``required``: when ``true``, the *Continue* button is disabled until the
   participant has placed at least one click (optional, boolean, default
   ``false``)
-  ``max_clicks``: maximum number of clicks accepted (optional, integer,
   default ``1``).

   -  ``1`` (default): each click moves the single marker to the new
      position.
   -  any integer ``> 1``: up to that many markers can be placed; once
      full, a new click drops the oldest marker.
   -  ``0``: unlimited clicks.

-  ``width``: maximum displayed width of the image, in pixels (optional,
   positive integer). The image is scaled down to fit while preserving
   aspect ratio. Coordinates remain in natural pixels regardless.
-  ``marker_color``: CSS colour of the crosshair (optional, string, default
   ``"#ff0000"``)
-  ``marker_size``: pixel size of the crosshair (optional, integer, default
   ``14``)

**Storage**

The database schema depends on ``max_clicks``:

-  When ``max_clicks`` is ``1`` (the default), two ``FLOAT`` columns are
   created — ``{id}_x`` and ``{id}_y`` — holding the natural-pixel x and y
   of the click.
-  Otherwise, one ``TEXT`` column ``{id}`` is created, holding a JSON
   array of ``{"x": ..., "y": ...}`` objects in click order, e.g.
   ``[{"x": 123.45, "y": 67.89}, {"x": 200.0, "y": 150.5}]``.

If the participant submits without clicking and ``required`` is ``false``,
the corresponding columns receive their default zero / empty value.

**Example (single-click)**

.. code:: json

       {
           "questiontype": "image_click",
           "id": "target_location",
           "instructions": "Click on the location you think is correct.",
           "src": "/static/map.png",
           "required": true
       }

**Example (multi-click)**

.. code:: json

       {
           "questiontype": "image_click",
           "id": "all_errors",
           "instructions": "Click on every part of the diagram that looks wrong.",
           "src": "/static/diagram.png",
           "max_clicks": 0,
           "marker_color": "#0066ff"
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

audio
-----

``questiontype == 'audio'``

Embeds an HTML5 ``<audio>`` element from any URL with native player controls.
Can optionally require the participant to listen to the clip in full before
the *Continue* button is enabled, and (when ``id`` is set) records listening
telemetry to the database.

When ``force_listen`` is on, a snap-back guard prevents the participant from
scrubbing past the supposed playhead position, the playback rate is pinned
to 1.0, and the clip pauses automatically when the tab loses focus. The
*Continue* button is gated by the same shared notice used by ``video`` —
if a page contains both pending audio and video, the notice reads "Please
play all media before continuing."

Audio always shows native controls; there is no ``minimal_controls`` option,
because the scrubber doubles as the participant's only progress indicator.

**Properties**

-  ``src``: URL of the audio file (required, string)
-  ``id``: when set, three columns are written to the questionnaire table
   (optional, string):

   -  ``{id}_started`` — epoch seconds when the participant first pressed
      play, or ``0`` if they never started it
   -  ``{id}_ended`` — epoch seconds at the last observed activity
      (play / timeupdate / pause / ended)
   -  ``{id}_listened`` — accumulated forward play time, in seconds

-  ``autoplay``: start playing as soon as the page loads (optional, boolean,
   default ``false``)
-  ``force_listen``: disable the *Continue* button until the participant has
   listened to ``completion_threshold`` of the clip (optional, boolean,
   default ``false``)
-  ``completion_threshold``: fraction of the clip's duration that counts
   as "listened" (optional, float between 0 and 1, default ``0.98``)

**Example**

.. code:: json

       {
           "questiontype": "audio",
           "id": "instructions_clip",
           "instructions": "Please listen to the instructions in full before continuing.",
           "src": "https://example.com/static/instructions.ogg",
           "force_listen": true,
           "completion_threshold": 0.95
       }

group
-----

``questiontype == 'group'``

Renders a header followed by a list of sub-questions of any other type.These
questions are all visually grouped within the same card. The group itself
does not create a database column — only its sub-questions do — so the group
's ``id`` is purely structural. Groups cannot contain other groups.

Sub-question ``id``\ s share the same namespace as top-level question ids,
so each one must be unique within the questionnaire as a whole, not just
within the group.

The ``show_sub_labels`` property controls how the group reads:

- When ``false`` (the default), the per-sub-question ``instructions`` labels
  are hidden and the group reads as a single compound question — for
  example, one "About you" header above height and weight inputs.
- When ``true``, each sub-question keeps its own ``instructions`` label and
  the group reads as a visually-grouped cluster of separately-labelled
  fields.

A group has two layered headings:

- ``instructions``: the bold heading rendered at the top, like the
  ``instructions`` field on every other question type.
- ``text``: an optional non-bold sub-heading rendered inside the group's
  fieldset, between the bold heading and the sub-questions.

**Properties**

-  ``id``: optional structural id for the group's HTML wrapper; not stored
   as a database column (optional, string). Sub-questions carry their own
   IDs, which is what populates the database.
-  ``instructions``: bold heading shown above the group (optional, string).
   Same as the common ``instructions`` attribute on other question types.
-  ``text``: optional non-bold sub-heading shown inside the group, between
   the bold ``instructions`` and the sub-questions (optional, string)
-  ``questions``: list of sub-question objects of any non-``group`` type
   (required, list)
-  ``show_sub_labels``: whether each sub-question keeps its own
   ``instructions`` label (optional, boolean: ``true`` or ``false``,
   default ``false``)
-  ``horizontal``: lay the sub-questions out side-by-side instead of
   stacked vertically (optional, boolean: ``true`` or ``false``, default
   ``false``)
-  ``show_if``: expression that conditionally shows or hides the entire
   group (optional, string)

**Example**

.. code:: json

       {
           "questiontype": "group",
           "id": "demographics",
           "instructions": "About you",
           "text": "These details help us interpret your responses.",
           "show_sub_labels": true,
           "questions": [
               {
                   "questiontype": "field",
                   "id": "first_name",
                   "instructions": "First name"
               },
               {
                   "questiontype": "num_field",
                   "id": "age",
                   "instructions": "Age (years)"
               },
               {
                   "questiontype": "slider",
                   "id": "experience",
                   "instructions": "Experience level",
                   "tick_count": 5
               }
           ]
       }
