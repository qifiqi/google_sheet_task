from flask import Blueprint, render_template, request


auth_pages_bp = Blueprint("auth_pages", __name__)


@auth_pages_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html", next_url=request.args.get("next", ""))
