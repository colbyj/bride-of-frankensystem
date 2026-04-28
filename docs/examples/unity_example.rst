Unity Example
=============

A worked example of integrating a Unity WebGL build with a BOFS project. Two parallel copies live in the examples repo, one built against Unity 2021.1 and one against Unity 2023.2 — pick whichever matches your local Unity install:

* `unity_example_2021.1 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2021.1>`_
* `unity_example_2023.2 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2023.2>`__

Each example contains both the ready-to-run BOFS project (``bofs_project/``) and the Unity source project (``unity_project/``) that produced the build, so you can run the example as-is or rebuild after editing the scene or scripts.

What It Demonstrates
--------------------

* **Custom Flask blueprint** with auto-discovered templates and static files (``views.py``).
* **Custom database table** (``GameLog``) for input posted from the running Unity build.
* **Three embedding layouts** for the WebGL build:

  * Inside the standard BOFS chrome (extends ``unity_webgl.html``).
  * At viewport size, no chrome (extends ``unity_webgl_fullscreen.html``).
  * On a fully custom HTML page that calls ``createUnityInstance()`` directly.

* **Pushing the participant ID into the running build** via ``gameInstance.SendMessage(...)``, picked up by a public method on the ``Canvas`` GameObject.
* **Reading the assigned condition from inside Unity** via a ``UnityWebRequest.Get("/fetch_condition")`` call to a session-validated Flask route.
* **Posting data from Unity back to BOFS** with a ``WWWForm`` POST that writes a row to the ``game_log`` table.
* **Advancing the BOFS page flow from inside Unity** through a small ``BOF.jslib`` plugin that navigates the host page to ``/redirect_next_page``.

Running It
----------

From inside one of the ``unity_example_*/bofs_project/`` directories after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS run unity_example.toml -d

Default port is 5007. Open http://localhost:5007 to step through the experiment, or http://localhost:5007/admin (password ``example``) to inspect participant progress and download the ``game_log`` table as CSV.

Each example's own ``README.md`` covers how the integration works in detail and how to rebuild the Unity project against your own scene or scripts.
