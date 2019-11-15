from flask.globals import _app_ctx_stack, _request_ctx_stack, LocalProxy


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
    top = _app_ctx_stack.top
    if top is None:
        raise RuntimeError(_app_ctx_err_msg)
    return top.app.db


def _find_referrer():
    top = _request_ctx_stack.top
    if top is None:
        raise RuntimeError(_request_ctx_err_msg)

    # Remove trailing "/" from URL, if it's there
    url_root = top.request.url_root
    if url_root.endswith("/"):
        url_root = url_root[:-1]

    # Remove the beginning portion of the URL from the referrer URL
    _referrer = top.request.referrer.replace(url_root, "")

    # Don't have leading slash on URL
    if _referrer.startswith("/"):
        _referrer = _referrer[1:]

    return _referrer


def _find_app_questionnaires():
    top = _app_ctx_stack.top
    if top is None:
        raise RuntimeError(_app_ctx_err_msg)
    return top.app.questionnaires


def _find_app_page_list():
    top = _app_ctx_stack.top
    if top is None:
        raise RuntimeError(_app_ctx_err_msg)
    return top.app.page_list


def _find_app_socketio():
    top = _app_ctx_stack.top
    if top is None:
        raise RuntimeError(_app_ctx_err_msg)
    return top.app.socketio


db = LocalProxy(_find_app_db)
referrer = LocalProxy(_find_referrer)
questionnaires = LocalProxy(_find_app_questionnaires)
page_list = LocalProxy(_find_app_page_list)
socketio = LocalProxy(_find_app_socketio)