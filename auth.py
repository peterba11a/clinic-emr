from functools import wraps
from flask import session, redirect, url_for, request, abort, g
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_db


def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        g.roles = []
        return
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)).fetchone()
    if user is None:
        conn.close()
        g.user = None
        g.roles = []
        return
    roles = conn.execute(
        "SELECT r.name FROM roles r "
        "JOIN user_roles ur ON ur.role_id = r.id "
        "WHERE ur.user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    g.user = user
    g.roles = [r["name"] for r in roles]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    """Allow access if the current user holds ANY of the given roles.
    Admin is always allowed, since Admin manages everything."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.path))
            if "Admin" in g.roles:
                return view(*args, **kwargs)
            if not any(r in g.roles for r in allowed_roles):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def authenticate(username, password):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND active=1", (username,)
    ).fetchone()
    conn.close()
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def hash_password(password):
    return generate_password_hash(password)
