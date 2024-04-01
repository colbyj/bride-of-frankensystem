Project Configuration
=====================

This page includes a description of each of the options within a project's configuration file (its ``.toml`` file).

.. table:: Configuration variables
    :widths: 32,17,45

    ============================ ===================== ==================
    Variable                     Data Type             Description
    ============================ ===================== ==================
    SQLALCHEMY_DATABASE_URI      string                This is the URI of the SQLite database.
    SECRET_KEY                   string                You *must* set this to a unique string. At least mash your keyboard's keys a bit.
    APPLICATION_ROOT             string                Rarely adjusted, used to set the project to be accessible at a different URL rather than /.
    TITLE                        string                What users see at the top of the page.
    ADMIN_PASSWORD               string                Used to log in to the admin pages at ``/admin``.
    USE_BREADCRUMBS              boolean               Show breadcrumbs-style progress bar.
    PORT                         integer               Configure what port the project will be accessible at.
    RETRIEVE_SESSIONS            boolean               If ID entered at ``/external_id`` was already used, then attempt to load a participant's progress from the database and redirect them to where they last were.
    ALLOW_RETAKES                boolean               With the external_id page in use, setting this to true will prevent the same ID from being used twice.
    LOG_GRID_CLICKS              boolean               Used for more fine-grained logging of participant's progress through questionnaires. Log the time the each radio button in a radio grid is clicked.
    CONDITIONS                   list of dictionaries  See :doc:`conditions`.
    ABANDONED_MINUTES            integer               The minutes that a participant needs to have been away from the study before they are considered to have abandoned it.
    COUNTS_INCLUDE_ABANDONED     boolean               If true, then when assigning participants to a condition, the abandoned participants will be considered as a member of the condition group.
    EXTERNAL_ID_LABEL            string                For example, "Mechanical Turk Worker ID".
    EXTERNAL_ID_PROMPT           string                For example, "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."
    STATIC_COMPLETION_CODE       string                Set this if you want all participants to be given the same completion code at the end of the survey.
    GENERATE_COMPLETION_CODE     boolean               Generate a random completion code for the user.
    COMPLETION_CODE_MESSAGE      string                For example, "Please copy and paste this code into the MTurk form:".
    OUTGOING_URL                 string                On the ``/end`` route, participants can be optionally redirected to an external page instead of being given a code. Specify the URL here.
    PAGE_LIST                    list of dictionaries  See :doc:`routing/main`.
    ============================ ===================== ==================