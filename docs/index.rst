Bride of Frankensystem
======================

`Bride of Frankensystem <https://frankensystem.net>`_ (BOFS) is an open-source framework for online behavioral experiments and surveys. It sits between survey-only platforms (Qualtrics, SurveyMonkey) and building from scratch: editing TOML, JSON, and HTML gets you a running study, and Python is available when you need it.

.. toctree::
   :hidden:

   Getting Started <getting_started/what_is_bofs>
   Building Your Experiment <building/index>
   Understanding the Framework <framework/architecture>
   Deploying Your Experiment <deploying/server>
   Reference <reference/index>

Where to start
--------------

- Never used BOFS? — :doc:`getting_started/what_is_bofs` then :doc:`getting_started/installation`.
- Already installed? — :doc:`getting_started/initialize_project` walks through ``BOFS init`` and what it generates.
- Want a JavaScript task? — :doc:`getting_started/quickstart_custom_task`.

.. note::

   If you need additional help, please `join us on Discord <https://discord.gg/XzXtUKFCJA>`_.

Citation
--------

If you use BOFS for your research, please cite it:

.. code-block:: bibtex

    @software{bride-of-frankensystem,
      author       = {Colby Johanson},
      title        = {colbyj/bride-of-frankensystem},
      month        = may,
      year         = 2024,
      publisher    = {Zenodo},
      version      = {2.0},
      doi          = {10.5281/zenodo.11176739},
      url          = {https://doi.org/10.5281/zenodo.11176739}
    }
