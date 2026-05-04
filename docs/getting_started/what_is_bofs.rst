What is BOFS?
=============

Bride of Frankensystem (BOFS) is an open-source framework for online behavioral experiments and surveys. It sits between general-purpose survey tools (which can't host arbitrary tasks) and writing a custom web application (which has no consent flow, condition assignment, or admin panel out of the box). BOFS provides the surrounding infrastructure — participant routing, condition assignment, questionnaires, data storage, and an admin panel — and lets you bring whatever task you want.

How BOFS development works
--------------------------

A BOFS project moves through three stages:

1. **Develop locally.** Build and run the experiment on your own machine. The project is a folder of configuration and content files you can edit freely.
2. **Test and debug.** Preview the experiment exactly as a participant will see it. The admin panel and debug tools surface errors before you go live.
3. **Deploy to a server.** Copy the project to a web server when you are ready to recruit participants. See :doc:`/deploying/server`.

Do I need programming experience?
---------------------------------

It depends on what you are building.

**Surveys, simple tasks, and A/B comparisons.** No programming required. You configure the experiment by editing three kinds of plain-text files: a settings file (TOML format, key-value pairs with ``#`` comments), one or more questionnaire files (JSON format, list of question definitions), and any custom HTML pages (consent form, instructions). Each format is documented with examples; you adapt more than you write from scratch.

**Interactive in-browser tasks.** Some JavaScript helps. Tasks like clicking on a canvas, drawing, or watching a video and answering questions about it are usually written in JavaScript. BOFS hosts the task page and stores the data, but the task code itself is JavaScript you write or borrow from a library like p5.js, jsPsych, or lab.js.

**Server-side logic.** Python helps. Generating stimuli on the fly, talking to an external service, or doing custom data processing means writing a Python *blueprint* — a folder with route definitions that BOFS picks up automatically. BOFS handles sessions, routing, and data storage; the code you write is the experiment-specific logic.

How BOFS compares
-----------------

**vs. survey platforms (Qualtrics, SurveyMonkey).** Survey platforms are easier for pure questionnaires but cannot host arbitrary tasks. They charge per response or per seat, and the data lives on their servers. BOFS hosts custom tasks alongside questionnaires, runs on hardware you control, and the data stays where you put it.

**vs. JavaScript experiment libraries (jsPsych, lab.js).** These libraries handle in-browser trial logic — timing, key capture, randomization — but do not provide consent forms, condition assignment, sessions, data storage, or an admin panel. BOFS provides those. A jsPsych or lab.js task can run inside a BOFS project; the two layers compose. See the example projects for how this looks.

**vs. building from scratch with Flask, Django, or Express.** A custom application gives you maximum control and maximum work. BOFS gives you participant tracking, condition assignment, consent flows, sessions, and a working admin panel without writing them. When the built-in patterns are not enough, BOFS exposes the same Flask underneath, so a Python developer can write custom routes alongside the built-in ones.

Where to go next
----------------

Read :doc:`install_and_run` next. It walks through installing BOFS, generating a project with the ``BOFS init`` wizard, and running the result.
