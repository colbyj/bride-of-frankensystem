Assigning and Making Use of Conditions
======================================

Conditions are set up in your project's configuration ``.toml`` file, with the ``CONDITIONS`` variable.

Leave the value an empty list (``[]``) if you do not need multiple conditions.
The format for multiple conditions is ``[{label='condition 1', enabled=true}, {label='condition 2', enabled=true}]``.
The first entry in the list is condition 1, the second is condition 2, etc. A participant without an explicitly assigned condition will have a condition of ``0``.

Assigning Conditions
--------------------
By default, a condition will be assigned to the participant if they visit the ``/consent``, ``/create_participant``, or ``/assign_condition`` route.
They will be assigned to whichever condition has the fewest number of participants, with the lowest number condition being chosen in the case of a tie.
Participants who have abandoned the study without completing it will not be considered within the count of participants in the condition group.

Using Conditions
----------------
These condition group numbers can be used within your project configurations ``PAGE_LIST`` variable. See :doc:`routing/main` for more details.

When developing custom pages, you can access the participant's assigned condition via the ``condition`` session variable: ``session['condition']``.