from flask import Blueprint, abort

from mine.auth_utils import login_required, roles_required
from mine.catalog_modules import SEGMENT_TO_STANDALONE_MODULE
from mine.content import run_standalone_repo_create, run_standalone_repo_edit

bp = Blueprint("repo_standalone", __name__)


def _module_for_segment(segment: str) -> str | None:
    return SEGMENT_TO_STANDALONE_MODULE.get((segment or "").strip())


@bp.route("/<string:segment>/new", methods=["GET", "POST"])
@login_required
@roles_required("admin", "moderator")
def repo_new(segment: str):
    mod = _module_for_segment(segment)
    if not mod:
        abort(404)
    return run_standalone_repo_create(mod)


@bp.route("/<string:segment>/<int:cid>/edit", methods=["GET", "POST"])
@login_required
@roles_required("admin", "moderator")
def repo_edit(segment: str, cid: int):
    mod = _module_for_segment(segment)
    if not mod:
        abort(404)
    return run_standalone_repo_edit(mod, cid)
