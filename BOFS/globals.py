from flask.globals import app_ctx, request, LocalProxy


# This code is based on flask's globals.py file

_request_ctx_err_msg = '''\
Working outside of request context.
This typically means that you attempted to use functionality that needed
an active HTTP request.  Consult the documentation on testing for
information about how to avoid this problem.\
'''

_app_ctx_err_msg = '''\
Working outside of application context.
This typically means that you attempted to use functionality that needed
to interface with the current application object in a way.  To solve
this set up an application context with app.app_context().  See the
documentation for more information.\
'''


def _find_app_db():
    if app_ctx is None:
        raise RuntimeError(_app_ctx_err_msg)
    return app_ctx.app.db


def _find_referrer():
    if request is None:
        raise RuntimeError(_request_ctx_err_msg)

    # Remove trailing "/" from URL, if it's there
    url_root = request.url_root
    if url_root.endswith("/"):
        url_root = url_root[:-1]


    _referrer = request.referrer
    if _referrer is None:
        return None

    _referrer = _referrer.replace(url_root, "")  # Remove the beginning portion of the URL from the referrer URL

    # Don't have leading slash on URL
    if _referrer.startswith("/"):
        _referrer = _referrer[1:]

    return _referrer


def _find_app_questionnaires():
    if app_ctx is None:
        raise RuntimeError(_app_ctx_err_msg)
    return app_ctx.app.questionnaires


def _find_app_tables():
    if app_ctx is None:
        raise RuntimeError(_app_ctx_err_msg)
    return app_ctx.app.tables


def _find_app_page_list():
    if app_ctx is None:
        raise RuntimeError(_app_ctx_err_msg)
    return app_ctx.app.page_list


db = LocalProxy(_find_app_db)
referrer = LocalProxy(_find_referrer)
questionnaires = LocalProxy(_find_app_questionnaires)
tables = LocalProxy(_find_app_tables)
page_list = LocalProxy(_find_app_page_list)
