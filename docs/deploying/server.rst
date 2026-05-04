Deploying to a Server
=====================

This page covers production deployment: choosing a web server, configuring a reverse proxy with HTTPS, selecting a database, and securing the admin panel. For local development setup, see :doc:`/getting_started/install_and_run`. For crowdsourcing-platform integration (MTurk, Prolific), see :doc:`/deploying/recruiting`.

.. warning::
   Production servers hold participant data. Use a strong admin password, terminate TLS, and back up the database regularly.

Why Not the Development Server?
--------------------------------

The built-in development server (``BOFS run config.toml -d``) is single-threaded, has no TLS, has no process manager to restart it after a crash, and exposes debugging information that shouldn't reach participants. Production needs:

- HTTPS, with traffic routed through a reverse proxy
- A process manager (systemd) that restarts BOFS automatically on failure
- A database sized to the study (SQLite for small studies, PostgreSQL for larger ones)
- A strong admin password and a unique ``SECRET_KEY``

System Requirements
-------------------

**Small studies (fewer than 25 concurrent participants)** can run on a single shared VM:

- Ubuntu 20.04 or newer (or another recent Linux distribution)
- Python 3.9 or newer
- 1 GB RAM, 1 vCPU, 10 GB or more storage
- SQLite (bundled) or a small PostgreSQL instance

**Large studies (50+ concurrent participants)** benefit from a dedicated database. Two layouts work:

- *Single server*: 4 GB+ RAM, 2+ cores, 50 GB+ SSD, PostgreSQL on the same machine.
- *Two servers*: 2 GB / 2 cores for the BOFS application server; 2 GB+ / 2 cores / 50 GB+ SSD for a dedicated PostgreSQL server.

**Extremely large studies** can scale horizontally: multiple BOFS instances behind a load balancer, a shared PostgreSQL with connection pooling, and a CDN for static files. Most research studies do not reach this point — a single-server setup handles hundreds of concurrent users.

Setting Up the Server
---------------------

This is not a complete server administration tutorial; it covers the BOFS-specific steps. Adapt commands to your distribution and hosting environment.

Install BOFS in a Virtual Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    python3 -m venv bofs_production
    source bofs_production/bin/activate
    pip install --upgrade pip
    pip install bride-of-frankensystem

Copy Your Experiment to the Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``scp``, ``rsync``, or ``git clone`` from a private repository:

.. code-block:: bash

    mkdir -p ~/experiments/my_study
    scp -r /local/path/to/experiment/* user@server:~/experiments/my_study/

Verify the Installation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    source bofs_production/bin/activate
    BOFS --help
    cd ~/experiments/my_study
    BOFS run production.toml --check-config

Web Server Configuration
-------------------------

Run BOFS with Waitress
~~~~~~~~~~~~~~~~~~~~~~~

BOFS ships with a Waitress-based production server that handles concurrent requests. Start it in production mode by running BOFS **without** the ``-d`` flag:

.. code-block:: bash

    BOFS run production.toml

This binds to ``0.0.0.0`` on the port specified in your config, so the project is reachable at ``http://your-ip-address:<PORT>``. The connection is unencrypted at this point — anything participants submit travels in plaintext. For studies recruiting real participants, put a reverse proxy in front of BOFS so traffic is encrypted under HTTPS.

Run BOFS Under systemd
~~~~~~~~~~~~~~~~~~~~~~~

A systemd unit ensures BOFS starts on boot and restarts on failure. Create ``/etc/systemd/system/bofs-experiment.service``:

.. code-block:: ini

    [Unit]
    Description=BOFS Experiment Server
    After=network.target

    [Service]
    Type=simple
    User=YOUR_USERNAME
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

A reverse proxy sits in front of BOFS, terminates TLS so traffic is encrypted as HTTPS, and forwards requests to BOFS over the local connection.

.. tabs::

   .. tab:: Caddy

      Caddy provisions and renews TLS certificates automatically via Let's Encrypt — no separate certbot step.

      Install Caddy (`installation instructions <https://caddyserver.com/docs/install>`__) and put this in ``/etc/caddy/Caddyfile``:

      .. code-block:: text

          yourdomain.com, www.yourdomain.com {
              reverse_proxy 127.0.0.1:5000

              handle_path /static/* {
                  root * /path/to/your/experiment/static
                  file_server
                  header Cache-Control "public, immutable, max-age=31536000"
              }

              header {
                  X-Frame-Options "SAMEORIGIN"
                  X-Content-Type-Options "nosniff"
              }
          }

      Reload Caddy to pick up the change:

      .. code-block:: bash

          sudo systemctl reload caddy

      Caddy obtains a TLS certificate the first time someone hits the domain.

   .. tab:: Nginx

      Two pieces are involved: installing Nginx and obtaining a TLS certificate for your domain.

      **Install Nginx.** Follow the `official Nginx installation instructions <https://nginx.org/en/docs/install.html>`__. On Debian/Ubuntu:

      .. code-block:: bash

          sudo apt update
          sudo apt install nginx

      **Obtain a TLS certificate.** The Nginx config below references certificate and key files. The simplest route is `Let's Encrypt's Certbot <https://certbot.eff.org/>`__:

      .. code-block:: bash

          sudo apt install certbot python3-certbot-nginx
          sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

      Certbot can modify your Nginx config in place or just produce cert files (typically under ``/etc/letsencrypt/live/yourdomain.com/``). For commercial certificates, follow your CA's installation guide.

      **Configure the site.** Create ``/etc/nginx/sites-available/bofs-experiment``:

      .. code-block:: nginx

          server {
              listen 80;
              server_name yourdomain.com www.yourdomain.com;
              return 301 https://$server_name$request_uri;
          }

          server {
              listen 443 ssl http2;
              server_name yourdomain.com www.yourdomain.com;

              ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
              ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
              ssl_protocols TLSv1.2 TLSv1.3;
              ssl_ciphers HIGH:!aNULL:!MD5;

              add_header X-Frame-Options "SAMEORIGIN" always;
              add_header X-Content-Type-Options "nosniff" always;

              location / {
                  proxy_pass http://127.0.0.1:5000;
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
          sudo nginx -t
          sudo systemctl restart nginx

.. note::
   Brotli-compressed Unity builds require HTTPS to decompress correctly in the browser. Serving them over plain HTTP will cause the game to fail to load.

Database Configuration
-----------------------

Set ``SQLALCHEMY_DATABASE_URI`` in your TOML config. BOFS supports anything SQLAlchemy supports; the common options are:

.. code-block:: toml

    # SQLite — file-based, no separate service needed
    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

    # PostgreSQL
    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@localhost/study_db"

    # MySQL
    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://username:password@localhost/study_db"

For PostgreSQL, install the Python adapter into the BOFS virtual environment:

.. code-block:: bash

    pip install psycopg2-binary

PostgreSQL installation and database creation are outside the scope of this guide — see your hosting provider's documentation or the `official PostgreSQL documentation <https://www.postgresql.org/docs/>`__. For connection pooling, see the `Flask-SQLAlchemy configuration guide <https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/config/>`__.

See :doc:`/reference/configuration` for all database-related settings.

Securing the Admin Panel
-------------------------

The admin panel exposes participant data and includes destructive controls.

Set a long, random ``ADMIN_PASSWORD`` in your TOML config:

.. code-block:: toml

    ADMIN_PASSWORD = "a-long-random-password-here"

To restrict ``/admin`` to a specific IP at the reverse-proxy layer:

.. tabs::

   .. tab:: Caddy

      .. code-block:: text

          yourdomain.com {
              @admin_block {
                  path /admin*
                  not remote_ip 203.0.113.5/32
              }
              respond @admin_block 403

              reverse_proxy 127.0.0.1:5000
          }

   .. tab:: Nginx

      .. code-block:: nginx

          location /admin {
              allow 203.0.113.5/32;
              deny all;

              proxy_pass http://127.0.0.1:5000;
              proxy_set_header Host $http_host;
              proxy_set_header X-Real-IP $remote_addr;
              proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
              proxy_set_header X-Forwarded-Proto $scheme;
          }

Brute-Force Protection and Session Security
--------------------------------------------

BOFS includes IP-based protection on the admin login, IP binding for sessions, and probe-URL / hostile-user-agent traps. All of these are on by default. See :doc:`/reference/configuration` for the full list of security settings.

Admin Login Protection
~~~~~~~~~~~~~~~~~~~~~~~

Failed admin logins are tracked per IP. After ``BRUTE_FORCE_MAX_ATTEMPTS`` failures (default: 5) within ``BRUTE_FORCE_WINDOW_MINUTES`` (default: 15 minutes), the IP is banned. Bans use a progressive schedule defined by ``BRUTE_FORCE_BAN_SCHEDULE`` (default: 1 min → 2 min → 5 min → 15 min → 1 hr → 6 hr → 1 day → 7 days), so the first ban is brief and repeat offenders escalate to multi-day bans.

Session IP Binding
~~~~~~~~~~~~~~~~~~~

Admin and participant sessions each bind to the IP that created them. See :doc:`/framework/sessions` for session lifecycle details.

- **Admin session**: when an admin logs in, the session records the request IP. Subsequent admin requests from a different IP are rejected and the session is cleared. Admins should not roam networks while logged in.
- **Participant session**: a participant's session is invalidated if a request comes from a different IP than the one that created the session. Disable with ``SESSION_BIND_TO_IP_PARTICIPANT = false`` for studies where participants may switch networks (cellular to Wi-Fi) mid-session.

Probe URL Traps and Hostile User Agents
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Any request to a path in ``BRUTE_FORCE_PROBE_URLS`` (e.g., ``/.env``, ``/wp-admin``, ``/.git``) immediately bans the source IP. If a custom blueprint serves a path that appears in the default list, edit the list in your TOML config.

Any request whose ``User-Agent`` contains a pattern from ``BRUTE_FORCE_HOSTILE_UA_PATTERNS`` (``sqlmap``, ``nikto``, ``nmap``, etc.) is also immediately banned. This is easily evaded — attackers can pass a different agent string — so it is defense in depth, not a primary control.

Auto-Trust for Known Admin IPs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Once an admin has logged in successfully from a given IP, that IP is added to a persistent allowlist (the ``admin_trusted_ip`` table) and exempted from future bans. To disable this, set ``BRUTE_FORCE_AUTO_TRUST_ADMIN = false``.

BEHIND_REVERSE_PROXY Setting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If BOFS runs behind Caddy or Nginx, set ``BEHIND_REVERSE_PROXY = true`` in your TOML so BOFS reads the real client IP from ``X-Forwarded-For`` rather than seeing ``127.0.0.1`` for every request. Without this, every IP-based check treats the proxy itself as the client. The Caddyfile and Nginx configs above already pass the correct headers.

.. code-block:: toml

    BEHIND_REVERSE_PROXY = true

Recovery from Self-Lockout
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The auto-trust list covers the common case. If a fresh admin (no prior successful login on record from their IP) exhausts the attempt budget, three recovery paths are available:

1. Add their IP to ``TRUSTED_IPS`` in ``config.toml`` and restart BOFS.
2. Set ``BRUTE_FORCE_PROTECTION = false`` in ``config.toml`` and restart; log in successfully (which adds the IP to ``admin_trusted_ip``); re-enable ``BRUTE_FORCE_PROTECTION`` and restart.
3. Edit the database directly: ``DELETE FROM banned_ip WHERE ipAddress = '...';``

Limits of IP-Based Protection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is application-layer protection calibrated for casual brute-force attackers. It does not stop a determined attacker rotating IPs through Tor or residential-proxy networks, and it can lock out legitimate users behind CGNAT (mobile carriers, university networks) when one bad actor on the same network trips a ban.

For DDoS protection and broader rate limiting, use proxy-layer controls. Caddy's `caddy-ratelimit <https://github.com/mholt/caddy-ratelimit>`__ plugin can rate-limit by path:

.. code-block:: text

    # Caddyfile snippet — requires the caddy-ratelimit plugin
    rate_limit {
        zone participant_create {
            match {
                path /consent /consent_nc /create_participant /create_participant_nc
            }
            key {client_ip}
            events 10
            window 1m
        }
    }

Troubleshooting
----------------

**Service won't start.** Check the journal first: ``sudo journalctl -u bofs-experiment --lines=50``. Common causes are TOML syntax errors, database connection failures, file-permission problems, and a port already in use.

**SSL certificate expired.** With Let's Encrypt and Certbot: ``sudo certbot renew && sudo systemctl reload nginx``. With Caddy, renewal is automatic.

**PostgreSQL connection refused.** Confirm the service is running (``sudo systemctl status postgresql``) and check ``/var/log/postgresql/postgresql-*-main.log``.

**PostgreSQL "too many connections".** Tune the pool in your TOML:

.. code-block:: toml

    [SQLALCHEMY_ENGINE_OPTIONS]
    pool_size = 5
    max_overflow = 10

**High CPU or memory.** Check for runaway processes or query patterns first. If the workload genuinely justifies it, scale up the VM or add swap. For slow responses, add indexes on frequently queried columns and enable compression at the proxy layer.

After Deployment
-----------------

Run a small pilot study before opening the project to real participants. Walk through the experiment yourself, verify rows appear in the database, and confirm the logs are clean. For recruiting participants via crowdsourcing platforms, see :doc:`/deploying/recruiting`.

.. warning::
   Production servers handling research data may need to comply with IRB requirements, GDPR, HIPAA, or other regulations. Consult your institution's IT and compliance teams before collecting data.
