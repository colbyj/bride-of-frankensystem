Production Server Configuration
===============================

Deploying a BOFS project to a production server means switching off the development server, putting the application behind a real web server with HTTPS, and choosing a database that suits the study size. This guide covers the deployment pieces; for crowdsourcing-platform integration (MTurk, Prolific) see :doc:`mturk_prolific`.

.. warning::
    Production servers hold participant data. The choices in this guide affect the security and integrity of that data — pick a strong admin password, terminate TLS, and back up the database regularly.

Why Not the Development Server?
-------------------------------

The built-in development server (``BOFS run config.toml -d``) is single-threaded, doesn't terminate TLS, has no process manager to restart it on failure, and exposes debugging information that shouldn't be visible to participants. Production needs:

- HTTPS, with traffic routed through a reverse proxy (Nginx in this guide)
- A process manager (systemd here) that restarts BOFS automatically if it crashes
- A database sized to the study (SQLite for small studies, PostgreSQL for larger ones)
- A strong admin password and a unique ``SECRET_KEY``

System Requirements
-------------------

These docs focus on a small-study setup — a single VM running BOFS with a reverse proxy in front of it. The sizing notes below sketch what larger studies look like, but the configuration details for those (load balancers, multi-instance deployments, dedicated database servers, connection pooling) are outside the scope of the BOFS documentation; consult your hosting provider's docs and a sysadmin if your study is in that territory.

Sizing depends on the number of concurrent participants you expect.

**Small studies (< 25 concurrent users)** can run on a single shared VM (DigitalOcean droplet, Linode, AWS t2.micro):

- Ubuntu 20.04+ (or another recent Linux distribution)
- Python 3.9 or newer
- 1GB RAM, 1 vCPU, 10GB+ storage (more if you expect a lot of data)
- SQLite (bundled) or a small PostgreSQL instance

**Large studies (50+ concurrent users)** want a dedicated database. Two layouts work:

- *Single server*: 4GB+ RAM, 2+ cores, 50GB+ SSD, PostgreSQL on the same machine.
- *Two servers*: 2GB / 2 cores for the BOFS application server, 2GB+ / 2 cores / 50GB+ SSD for a dedicated PostgreSQL server.

**Extremely large studies** can scale horizontally: multiple BOFS instances behind a load balancer, a shared PostgreSQL with connection pooling, and a CDN for static files. Most research studies never reach this point — a single-server setup handles hundreds of concurrent users.

Setting Up the Server
---------------------

This isn't a complete server administration tutorial; it covers the BOFS-specific pieces. Adapt the commands to your distribution and hosting setup.

Install BOFS in a Virtual Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    python3 -m venv bofs_production
    source bofs_production/bin/activate
    pip install --upgrade pip
    pip install bride-of-frankensystem

Copy Your Experiment to the Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``scp``, ``rsync``, or a ``git clone`` from a private repo:

.. code-block:: bash

    mkdir -p ~/experiments/my_study
    scp -r /local/path/to/experiment/* user@server:~/experiments/my_study/

Verify the Installation
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    source bofs_production/bin/activate
    BOFS --help
    cd ~/experiments/my_study
    BOFS run production.toml --check-config

Web Server Configuration
------------------------

Run BOFS with Eventlet
~~~~~~~~~~~~~~~~~~~~~~

BOFS ships with an Eventlet-based production server that handles concurrent requests. To start it in production mode, **run BOFS without the** ``-d`` **flag**:

.. code-block:: bash

    BOFS run production.toml

This binds to ``0.0.0.0`` on the port specified in your config, so the project is reachable at ``http://your-ip-address:<PORT>``. This is enough to collect data — the production server is fully functional on its own — but the connection is unencrypted, so anything participants submit (including consent, responses, and any IDs) travels in plaintext. For studies that recruit real participants you'll want to put a reverse proxy in front of BOFS so traffic is encrypted under HTTPS. The next two sections cover that.

Run BOFS Under systemd
~~~~~~~~~~~~~~~~~~~~~~

A systemd unit ensures BOFS starts on boot and restarts on failure. Create ``/etc/systemd/system/bofs-experiment.service``:

.. code-block:: ini

    [Unit]
    Description=BOFS Experiment Server
    After=network.target

    [Service]
    Type=simple
    User=$USER  # Replace with your username
    WorkingDirectory=/path/to/your/experiment
    Environment=PATH=/path/to/bofs_production/bin
    ExecStart=/path/to/bofs_production/bin/python -m BOFS run production.toml
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

Enable, start, and inspect the service:

.. code-block:: bash

    sudo systemctl enable bofs-experiment
    sudo systemctl start bofs-experiment
    sudo systemctl status bofs-experiment
    sudo journalctl -u bofs-experiment -f

Reverse Proxy
~~~~~~~~~~~~~

A reverse proxy sits in front of BOFS, terminates TLS (so traffic is encrypted as HTTPS), and forwards requests on to BOFS over the local connection. Two common choices:

.. tabs::

   .. tab:: Nginx

      Nginx is the long-established option — wider tooling support and more configuration knobs at the cost of more setup work. Two pieces are involved: installing Nginx itself and obtaining a TLS certificate for your domain.

      **Install Nginx.** Follow the `official Nginx installation instructions <https://nginx.org/en/docs/install.html>`_ for your distribution. On Debian/Ubuntu it's typically:

      .. code-block:: bash

          sudo apt update
          sudo apt install nginx

      **Obtain a TLS certificate.** The Nginx configuration below references ``certificate.crt`` and ``private.key`` files — you'll need to fill those in with paths to a real certificate and key for your domain. The simplest route is `Let's Encrypt's Certbot <https://certbot.eff.org/>`_, which provisions free certificates and configures auto-renewal:

      .. code-block:: bash

          sudo apt install certbot python3-certbot-nginx
          sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

      Certbot can either modify your Nginx config in place to point at the issued certificate, or just produce the cert files for you to reference manually (typically under ``/etc/letsencrypt/live/yourdomain.com/fullchain.pem`` and ``/etc/letsencrypt/live/yourdomain.com/privkey.pem``). For commercial certificates, follow your CA's installation guide.

      **Configure the site.** Create ``/etc/nginx/sites-available/bofs-experiment`` with:

      .. code-block:: nginx

          server {
              listen 80;
              server_name yourdomain.com www.yourdomain.com;
              return 301 https://$server_name$request_uri;
          }

          server {
              listen 443 ssl http2;
              server_name yourdomain.com www.yourdomain.com;

              ssl_certificate /path/to/ssl/certificate.crt;
              ssl_certificate_key /path/to/ssl/private.key;
              ssl_protocols TLSv1.2 TLSv1.3;
              ssl_ciphers HIGH:!aNULL:!MD5;

              add_header X-Frame-Options "SAMEORIGIN" always;
              add_header X-XSS-Protection "1; mode=block" always;
              add_header X-Content-Type-Options "nosniff" always;

              location / {
                  proxy_pass http://127.0.0.1:5000;  # The port BOFS is listening on
                  proxy_set_header Host $http_host;
                  proxy_set_header X-Real-IP $remote_addr;
                  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                  proxy_set_header X-Forwarded-Proto $scheme;
              }

              location /static {
                  alias /path/to/your/experiment/static;
                  expires 1y;
                  add_header Cache-Control "public, immutable";
              }
          }

      Enable the site:

      .. code-block:: bash

          sudo ln -s /etc/nginx/sites-available/bofs-experiment /etc/nginx/sites-enabled/
          sudo nginx -t  # Test the configuration
          sudo systemctl restart nginx

   .. tab:: Caddy

      Caddy provisions and renews TLS certificates automatically via Let's Encrypt — no separate certbot step. The trade-off is fewer configuration knobs than Nginx, which is rarely a problem for a BOFS deployment.

      Install Caddy (`installation instructions <https://caddyserver.com/docs/install>`_) and put this in ``/etc/caddy/Caddyfile``:

      .. code-block:: text

          yourdomain.com, www.yourdomain.com {
              # Forward everything to BOFS
              reverse_proxy 127.0.0.1:5000

              # Serve static files directly with a long cache lifetime
              handle_path /static/* {
                  root * /path/to/your/experiment/static
                  file_server
                  header Cache-Control "public, immutable, max-age=31536000"
              }

              # Sensible default security headers
              header {
                  X-Frame-Options "SAMEORIGIN"
                  X-Content-Type-Options "nosniff"
              }
          }

      Reload Caddy to pick up the change:

      .. code-block:: bash

          sudo systemctl reload caddy

      Caddy will obtain a TLS certificate the first time someone hits the domain.

Database Configuration
----------------------

Set ``SQLALCHEMY_DATABASE_URI`` in your TOML config. BOFS supports anything SQLAlchemy supports; the common options are:

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@localhost/study_db"
    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://username:password@localhost/study_db"

For PostgreSQL, install the Python adapter into the BOFS virtual environment:

.. code-block:: bash

    pip install psycopg2-binary

PostgreSQL installation and database creation is outside the scope of this guide — see your hosting provider's documentation or the `official PostgreSQL documentation <https://www.postgresql.org/docs/>`_. For connection pooling and other advanced options, see the `Flask-SQLAlchemy configuration guide <https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/config/>`_.

Securing the Admin Panel
------------------------

The admin panel exposes participant data and includes destructive controls. Two pieces matter most.

Set a long, random ``ADMIN_PASSWORD`` in your TOML config:

.. code-block:: toml

    ADMIN_PASSWORD = "ThisIsAVeryLongAndSecurePasswordForTheAdminPanel2024!"

Optionally, restrict ``/admin`` to a specific IP at the Nginx layer:

.. code-block:: nginx

    location /admin {
        allow xxx.xxx.xxx.xxx/32;  # Your IP address
        deny all;

        proxy_pass http://127.0.0.1:5000;
        # ... other proxy settings
    }

Troubleshooting
---------------

**Service won't start.** Check the logs first: ``sudo journalctl -u bofs-experiment --lines=50``. Usual causes are TOML syntax errors, database connection failures, file-permission problems, and a port already in use.

**SSL certificate expired.** With Let's Encrypt: ``sudo certbot renew && sudo systemctl reload nginx``.

**PostgreSQL connection refused.** Confirm the service is running (``sudo systemctl status postgresql``) and inspect ``/var/log/postgresql/postgresql-*-main.log``.

**PostgreSQL "too many connections".** Tune the pool in your TOML:

.. code-block:: toml

    SQLALCHEMY_ENGINE_OPTIONS = {pool_size=5, max_overflow=10}

**High CPU or memory.** Look for runaway processes or query patterns first. If the workload genuinely justifies it, scale up the VM or add swap. For slow responses, add indexes on frequently queried columns and enable compression at the Nginx layer.

After Deployment
----------------

Run a small pilot study before opening the project to real participants. Walk through the experiment yourself, verify rows appear in the database as expected, and confirm the logs are clean.

.. warning::
    Production servers handling research data may need to comply with IRB requirements, GDPR, HIPAA, or other regulations. Consult your institution's IT and compliance teams as needed.
