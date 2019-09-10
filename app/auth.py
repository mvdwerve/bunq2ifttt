"""
Handles various authentications for the app:
- user authentication for the web interface by password
- OAuth flow / API key submission for bunq
- IFTTT service key submission
"""
# pylint: disable=broad-except

import base64
import hashlib
import re
import secrets
import traceback

import requests
from flask import request, render_template, make_response, redirect

import bunq
import storage
import util


def user_login():
    """ Handles password login """
    try:
        hashfunc = hashlib.sha256()
        hashfunc.update(request.form["password"].encode("utf-8"))

        stored_hash = storage.retrieve("config", "password_hash")
        if stored_hash is not None:
            salt = storage.retrieve("config", "password_salt")["value"]
            hashfunc.update(salt.encode('ascii'))
            calc_hash = base64.b64encode(hashfunc.digest()).decode('ascii')
            if calc_hash != stored_hash["value"]:
                return render_template("message.html", msgtype="danger", msg=\
                    'Invalid password! - To try again, '\
                    '<a href="/">click here</a>')
        else:
            # first time login, so store the password
            salt = secrets.token_urlsafe(32)
            hashfunc.update(salt.encode('ascii'))
            calc_hash = base64.b64encode(hashfunc.digest()).decode('ascii')
            storage.store("config", "password_salt",
                          {"value": salt})
            storage.store("config", "password_hash",
                          {"value": calc_hash})

        session = secrets.token_urlsafe(32)
        util.save_session_cookie(session)

        resp = make_response(redirect('/'))
        resp.set_cookie("session", session)
        return resp

    except Exception:
        traceback.print_exc()
        return render_template("message.html", msgtype="danger", msg=\
            'An unknown exception occurred. See the logs. <br><br>'\
            '<a href="/">Click here to return home</a>')


def set_ifttt_service_key():
    """ Store the IFTTT service key """
    try:
        key = request.form["iftttkey"]
        if len(key) != 64:
            print("Invalid key: ", key)
            return render_template("message.html", msgtype="danger", msg=\
                'Invalid key! <br><br>'\
                '<a href="/">Click here to try again</a>')
        util.save_ifttt_service_key(key)
        return render_template("message.html", msgtype="success", msg=\
            'IFTTT service key successfully set <br><br>'\
            '<a href="/">Click here to return home</a>')

    except Exception:
        traceback.print_exc()
        return render_template("message.html", msgtype="danger", msg=\
            'An unknown exception occurred. See the logs. <br><br>'\
            '<a href="/">Click here to return home</a>')

def set_bunq_oauth_response():
    """ Handles the bunq OAuth redirect """
    try:
        code = request.args["code"]
        if len(code) != 64:
            print("Invalid code: ", code)
            return render_template("message.html", msgtype="danger", msg=\
                'Invalid code! <br><br>'\
                '<a href="/">Click here to try again</a>')
        url = "https://api.oauth.bunq.com/v1/token?grant_type="\
              "authorization_code&code={}&redirect_uri={}"\
              "&client_id={}&client_secret={}"\
              .format(code,
                      request.url_root + "auth",
                      storage.retrieve("config", "bunq_client_id")["value"],
                      storage.retrieve("config", "bunq_client_secret")["value"]
                     )
        req = requests.post(url)
        key = req.json()["access_token"]
        allips = storage.retrieve("config", "bunq_allips")["value"]
        bunq.install(key, allips=allips, urlroot=request.url_root)
        util.save_bunq_security_mode("OAuth")
        util.save_app_mode("master")
        util.update_bunq_accounts()
        return render_template("message.html", msgtype="success", msg=\
            'OAuth successfully setup <br><br>'\
            '<a href="/">Click here to return home</a>')

    except Exception:
        traceback.print_exc()
        return render_template("message.html", msgtype="danger", msg=\
            'An unknown exception occurred. See the logs. <br><br>'\
            '<a href="/">Click here to return home</a>')

def set_bunq_oauth_api_key():
    """ Handles bunq OAuth id/secret submission or API key submission """
    try:
        key = request.form["bunqkey"]
        allips = False
        if "allips" in request.form and request.form["allips"] == 'on':
            allips = True
        print("allips:", allips)
        tokens = re.split("[:, \r\n\t]+", key.strip())
        if len(tokens) == 6 and len(tokens[2]) == 64 and len(tokens[5]) == 64:
            # OAuth client id/secret submitted
            storage.store("config", "bunq_client_id", {"value": tokens[2]})
            storage.store("config", "bunq_client_secret", {"value": tokens[5]})
            storage.store("config", "bunq_allips", {"value": allips})
            redirect_url = request.url_root + "auth"
            url = "https://oauth.bunq.com/auth?response_type=code"\
                  "&client_id=" + tokens[2] + \
                  "&redirect_uri=" + redirect_url
            return render_template("message.html", msgtype="primary", msg=\
                "Make sure the following URL is included as a redirect url:"\
                "<br><br><b>" + redirect_url + "</b><br><br>"\
                'Then click <a href="' + url + '">this link</a>')
        if len(tokens) == 1 and len(tokens[0]) == 64:
            # API key submitted
            try:
                bunq.install(key, allips=allips)
                util.save_bunq_security_mode("API key")
                util.update_bunq_accounts()
                return render_template("message.html", msgtype="success", msg=\
                    'API key successfully installed <br><br>'\
                    '<a href="/">Click here to return home</a>')
            except Exception:
                traceback.print_exc()
                return render_template("message.html", msgtype="danger", msg=\
                    'An exception occurred while installing the API key. '\
                    'See the logs. <br><br>'\
                    '<a href="/">Click here to try again</a>')
        print("Invalid key: ", key)
        return render_template("message.html", msgtype="danger", msg=\
            'No valid API key or OAuth client id/secret found!<br><br>'\
            '<a href="/">Click here to return home</a>')
    except Exception:
        traceback.print_exc()
        return render_template("message.html", msgtype="danger", msg=\
            'An unknown exception occurred. See the logs. <br><br>'\
            '<a href="/">Click here to return home</a>')

def bunq_oauth_reauthorize():
    redirect_url = request.url_root + "auth"
    url = "https://oauth.bunq.com/auth?response_type=code"\
          "&client_id=" + storage.get_value("config", "bunq_client_id") + \
          "&redirect_uri=" + redirect_url
    return render_template("message.html", msgtype="primary", msg=\
        "Make sure the following URL is included as a redirect url:"\
        "<br><br><b>" + redirect_url + "</b><br><br>"\
        'Then click <a href="' + url + '">this link</a>')
