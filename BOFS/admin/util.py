from builtins import str
import json
import six
from os import listdir, path
from functools import wraps
from flask import request, session, current_app, render_template, g, redirect, url_for
from BOFS.globals import db
import decimal, datetime


def _datetime_convert(v):
    return v.strftime("%Y-%m-%d %H:%M:%S")


def remove_non_ascii(s):
    return "".join([x for x in s if ord(x)<128]).encode('ascii', 'xmlcharrefreplace')


def alchemy_encoder(obj):
    """
    JSON encoder function for SQLAlchemy special classes.
    https://codeandlife.com/2014/12/07/sqlalchemy-results-to-json-the-easy-way/
    """
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)


def sqlalchemy_to_json(inst, cls):
    """
    Jsonify the sqlalchemy query result.
    http://stackoverflow.com/questions/7102754/jsonify-a-sqlalchemy-result-set-in-flask
    """
    convert = dict()
    convert['DATETIME'] = _datetime_convert

    d = dict()
    for c in cls.columns:
        v = getattr(inst, c.name)
        if c.type in list(convert.keys()) and v is not None:
            try:
                d[c.name] = convert[c.type](v)
            except Exception:
                d[c.name] = "Error:  Failed to covert using ", str(convert[c.type])
        elif v is None:
            d[c.name] = str()
        else:
            if isinstance(v, str):
                d[c.name] = remove_non_ascii(v).replace("'", "&#39;").replace("{", "&#123;").replace("}", "&#125;")
            else:
                d[c.name] = str(v)
    return json.dumps(d)


def verify_admin(f):
    """
    A decorator to be used for admin routes, which checks if the user is logged in. If not, the login page is shown.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedIn' not in session or not session['loggedIn']:
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def escape_csv(input):
    if isinstance(input, six.string_types):
        return str.format(u"\"{}\"", input.strip().replace("\n", " ").replace("\r", " ").replace("\"", "'"))
    if input is None:
        return str()
    if type(input) is bool:
        return str(1) if input == True else str(0)
    else:
        return str(input)


def questionnaire_name_and_tag(questionnnaireNameAndTagString):
    """
    The questionnaire paths might or might not include a tag, e.g., "questionnaire/tag".
    This function splits that up.
    :param questionnnaireNameAndTag:
    :return:
    """
    if u"/" in questionnnaireNameAndTagString:
        split = questionnnaireNameAndTagString.split(u"/")
        qName = split[0]
        qTag = split[1]
    else:
        qName = questionnnaireNameAndTagString
        qTag = ""

    return qName, qTag