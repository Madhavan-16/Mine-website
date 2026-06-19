"""
Public account context pages (no login): Freeport — Know your customer.
Other specification sections are implementation reference only and are not exposed as routes.
"""

from flask import Blueprint, redirect, render_template, url_for

bp = Blueprint("reference", __name__, url_prefix="/program")


@bp.route("/")
def index():
    return redirect(url_for("reference.fmi_kyc"))


@bp.route("/fmi-know-your-customer")
def fmi_kyc():
    from mine.main import _FREEPORT_STORY

    return render_template(
        "program/fmi_know_your_customer.html",
        freeport_story=_FREEPORT_STORY,
    )


@bp.route("/background-context")
def background():
    """Legacy URL; Section 3 page removed — send users to KYC."""
    return redirect(url_for("reference.fmi_kyc"), code=301)
