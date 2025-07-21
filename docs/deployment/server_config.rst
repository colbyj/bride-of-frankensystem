Production Server Configuration
===============================

This guide covers how to deploy BOFS experiments on production servers for participant data collection. Moving from development to production requires careful attention to security, performance, and reliability.

.. note::
    This page covers server deployment and hosting. For platform integration with MTurk and Prolific, see :doc:`mturk_prolific`.

.. warning::
    Production deployment involves security considerations that are critical for protecting participant data.

Production vs Development
-------------------------

**Key Differences**

Production environments require additional considerations beyond development:

- **Security**: Strong secret keys, HTTPS, secure database connections
- **Performance**: Optimized for multiple concurrent users
- **Reliability**: Process management, monitoring, and automatic restart
- **Data Protection**: Secure data storage, backup procedures, audit logging
- **Scalability**: Database and server resources sized for expected load

**Development Setup Limitations**

The built-in development server (``BOFS config.toml -d``) is **not suitable for production** because:

- Single-threaded processing
- No SSL/HTTPS support
- Limited security features
- No process management
- Performance limitations

System Requirements
-------------------

**Small Studies**

Studies where typically fewer than 25 concurrent users will be online can use a single shared VM (e.g., DigitalOcean droplet, Linode, AWS t2.micro).

- **Operating System**: Linux is recommended (e.g., Ubuntu 20.04+)
- **Python**: 3.9 or newer
- **RAM**: 1GB or more
- **CPU**: 1 vCPU core
- **Storage**: 10GB+ (depending on expected data volume)
- **Database**: Use a SQLite database (included with BOFS) or optionally a small PostgreSQL instance


**Large Studies**

For studies with very large sample sizes, many concurrent users (e.g., 50+) will have higher system requirements. A dedicated database is also recommended.

- **Single Server Option** (recommended for most large studies):

  - RAM: 4GB+ 
  - CPU: 2+ cores
  - Storage: 50GB+ (SSD recommended for better database performance)
  - Database: PostgreSQL on same server

- **Two-Server Option** (for very large studies or institutional requirements):

  - **BOFS Application Server**: 2GB RAM, 2+ cores, 20GB storage
  - **PostgreSQL Database Server**: 2GB+ RAM, 2+ cores, 50GB+ SSD storage


**Extremely Large Studies**

For extremely large studies, consider adding the following.

- Multiple BOFS instances behind a load balancer
- Shared PostgreSQL database with connection pooling
- CDN for static file delivery

.. note::
    Most research studies will never need this level of scaling. The single-server setup can handle hundreds of concurrent users.


Setting Up a Server
-------------------

.. note::
    This section provides key deployment steps but is not a complete server administration tutorial.

Overview
~~~~~~~~

The basic deployment process involves:

1. **Environment Setup**: Create Python virtual environment and install BOFS
2. **File Transfer**: Copy your experiment files to the server
3. **Web Server**: Configure production web server (Eventlet + Nginx)
4. **Database**: Set up production database (PostgreSQL for large studies)
5. **Security**: Configure SSL certificates and secure access
6. **Process Management**: Set up automatic service restart
7. **Testing**: Verify everything works before launching


Create Production Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set up an environment for BOFS:

.. code-block:: bash

    # Create virtual environment
    python3 -m venv bofs_production
    source bofs_production/bin/activate

    # Install BOFS
    pip install --upgrade pip
    pip install bride-of-frankensystem

Install Your Experiment
~~~~~~~~~~~~~~~~~~~~~~~~

Copy your experiment files to the production server:

.. code-block:: bash

    # Create experiment directory
    mkdir -p ~/experiments/my_study
    cd ~/experiments/my_study

    # Copy your files (questionnaires, templates, config)
    # Either via scp, git, or file transfer
    scp -r /local/path/to/experiment/* user@server:~/experiments/my_study/

Test Production Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Verify BOFS works in the production environment:

.. code-block:: bash

    # Activate environment
    source bofs_production/bin/activate

    # Test BOFS installation
    BOFS --help

    # Test your experiment configuration
    cd ~/experiments/my_study
    BOFS production.toml --check-config

Web Server Configuration
------------------------

BOFS Built-in Server (Eventlet)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BOFS includes an Eventlet-based production server that's suitable for most research applications:

**Starting the Production Server**

.. code-block:: bash

    # Production mode (no debug) automatically binds to 0.0.0.0 (all available IP addresses) at the port specified in the config file.
    BOFS production.toml

Your BOFS project should now be visible at ``http://your-ip-address:5000``.

Process Management with systemd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a systemd service for automatic startup and restart:

.. code-block:: bash

    # Create service file
    sudo nano /etc/systemd/system/bofs-experiment.service

Add this content:

.. code-block:: ini

    [Unit]
    Description=BOFS Experiment Server
    After=network.target

    [Service]
    Type=simple
    User=$USER  # Replace with your username
    WorkingDirectory=/path/to/your/experiment  # Replace with your experiment directory
    Environment=PATH=/path/to/bofs_production/bin  # Replace with your virtual environment path
    ExecStart=/path/to/bofs_production/bin/python -m BOFS production.toml
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

Enable and start the service:

.. code-block:: bash

    # Enable and start the service
    sudo systemctl enable bofs-experiment
    sudo systemctl start bofs-experiment

    # Check status
    sudo systemctl status bofs-experiment

    # View logs
    sudo journalctl -u bofs-experiment -f

Reverse Proxy with Nginx
~~~~~~~~~~~~~~~~~~~~~~~~~

Set up Nginx as a reverse proxy for SSL termination and static file serving:

.. code-block:: bash

    # Install Nginx
    sudo apt install nginx

    # Create site configuration
    sudo nano /etc/nginx/sites-available/bofs-experiment

Add this configuration:

.. code-block:: nginx

    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;
        
        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com www.yourdomain.com;

        # SSL Configuration
        ssl_certificate /path/to/ssl/certificate.crt;
        ssl_certificate_key /path/to/ssl/private.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header X-Content-Type-Options "nosniff" always;

        # Proxy to BOFS
        location / {
            proxy_pass http://127.0.0.1:5000;  # URL that BOFS is listening on
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Static file serving (optional optimization)
        location /static {
            alias /path/to/your/experiment/static;  # Replace with your experiment path
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

Enable the site:

.. code-block:: bash

    # Enable site and restart Nginx
    sudo ln -s /etc/nginx/sites-available/bofs-experiment /etc/nginx/sites-enabled/
    sudo nginx -t  # Test configuration
    sudo systemctl restart nginx

.. note::
    The above Nginx configuration requires valid SSL certificates. For free SSL certificates, see `Let's Encrypt's Certbot tutorial <https://certbot.eff.org/>`_. For commercial certificates, consult your certificate authority's installation guide.

Database Configuration
----------------------

SQLite vs Production Databases
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**SQLite (Development/Small Studies)**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

**PostgreSQL (Recommended for Production)**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@localhost/study_db"

**MySQL (Alternative)**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://username:password@localhost/study_db"

For connection pooling and advanced database configuration, see the `Flask-SQLAlchemy documentation <https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/config/>`_.

PostgreSQL Setup
~~~~~~~~~~~~~~~~

For PostgreSQL installation and database setup, consult your hosting provider's documentation or the `official PostgreSQL documentation <https://www.postgresql.org/docs/>`_.

To use PostgreSQL with BOFS, install the Python adapter:

.. code-block:: bash

    # In your BOFS virtual environment
    pip install psycopg2-binary


Admin Panel Security Recommendations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Strong Admin Password**

.. code-block:: toml

    # Use a long, random password
    ADMIN_PASSWORD = "ThisIsAVeryLongAndSecurePasswordForTheAdminPanel2024!"

**IP Restriction (Optional)**

Configure Nginx to restrict admin access to only your IP address:

.. code-block:: nginx

    # In your Nginx configuration
    location /admin {
        allow xxx.xxx.xxx.xxx/32;  # Your IP address
        deny all;
        
        proxy_pass http://127.0.0.1:5000;
        # ... other proxy settings
    }

Production Configuration
------------------------

Complete Production Configuration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a complete production TOML configuration that brings together all the elements:

.. code-block:: toml

    # Basic Settings
    TITLE = "Research Study - Production"
    SECRET_KEY = "generate-a-long-random-secret-key-here"
    
    # Server Configuration
    PORT = 5000
    
    # Database (choose one)
    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"  # For small studies
    # SQLALCHEMY_DATABASE_URI = "postgresql://username:password@localhost/study_db"  # For large studies
    
    # Admin Security
    ADMIN_PASSWORD = "very-secure-admin-password-here"
    USE_ADMIN = true
    
    # External Platform Integration (if using MTurk/Prolific)
    EXTERNAL_ID_LABEL = "Participant ID"
    GENERATE_COMPLETION_CODE = true
    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false
    
    # Study Configuration
    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Main Task", path="questionnaire/main_task"},
        {name="End", path="end"}
    ]



Troubleshooting Common Issues
-----------------------------

Service Won't Start
~~~~~~~~~~~~~~~~~~~

**Check logs for errors:**

.. code-block:: bash

    sudo journalctl -u bofs-experiment --lines=50

**Common causes:**

- Configuration file syntax errors
- Database connection failures
- Permission issues
- Port already in use

SSL Certificate Issues
~~~~~~~~~~~~~~~~~~~~~~

**Certificate expired:**

.. code-block:: bash

    # Renew Let's Encrypt certificate (if used)
    sudo certbot renew

    # Restart nginx
    sudo systemctl reload nginx


Database Connection Problems
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Connection refused (PostgreSQL):**

.. code-block:: bash

    # Check PostgreSQL status
    sudo systemctl status postgresql
    
    # Check PostgreSQL logs
    sudo tail -f /var/log/postgresql/postgresql-*-main.log

**Too many connections:**

.. code-block:: toml

    # Reduce connection pool size
    SQLALCHEMY_ENGINE_OPTIONS = {pool_size=5, max_overflow=10}

Performance Issues
~~~~~~~~~~~~~~~~~~

**High CPU usage:**

- Check for runaway processes
- Monitor database queries
- Consider scaling up server resources

**High memory usage:**

- Monitor database connection pools
- Check for memory leaks in logs
- Consider adding swap space

**Slow response times:**

- Add database indexes
- Optimize database queries
- Enable compression
- Use CDN for static files

Next Steps
----------

After successful deployment, always run a small pilot study to verify all systems. Ensure that all data is being logged correctly by inspecting the database, and that there are no errors by inspecting the logs.

.. warning::
    Remember that production servers handling research data may need to comply with institutional IRB requirements, GDPR, HIPAA, or other data protection regulations. Consult with your institution's IT and compliance teams as needed.

