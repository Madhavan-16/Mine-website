from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any

from email_validator import EmailNotValidError, validate_email
from flask import current_app

from mine import token_store


@dataclass
class GraphError(Exception):
    message: str
    status_code: int | None = None
    needs_reconnect: bool = False

    def __str__(self) -> str:
        return self.message


FOLDER_MAP = {
    "inbox": "inbox",
    "sent": "sentitems",
    "drafts": "drafts",
    "trash": "deleteditems",
}


def graph_ready(app) -> bool:
    return (
        bool(app.config.get("MS_GRAPH_ENABLED"))
        and bool((app.config.get("MS_CLIENT_ID") or "").strip())
        and bool(app.config.get("MS_CLIENT_SECRET"))
        and bool((app.config.get("MS_TOKEN_ENCRYPTION_KEY") or "").strip())
    )


def _msal_module():
    try:
        return importlib.import_module("msal")
    except ModuleNotFoundError as exc:
        raise GraphError(
            "Microsoft Graph dependency is missing (msal). Install requirements in the Python environment running MiNe."
        ) from exc


def _requests_module():
    try:
        return importlib.import_module("requests")
    except ModuleNotFoundError as exc:
        raise GraphError(
            "HTTP dependency is missing (requests). Install requirements in the Python environment running MiNe."
        ) from exc


def _authority(app) -> str:
    tenant = (app.config.get("MS_TENANT") or "common").strip()
    return f"https://login.microsoftonline.com/{tenant}"


def _scopes(app) -> list[str]:
    scopes = app.config.get("MS_GRAPH_SCOPES") or ()
    return [str(s).strip() for s in scopes if str(s).strip()]


def _token_endpoint(app) -> str:
    return f"{_authority(app)}/oauth2/v2.0/token"


def _msal_client(app):
    msal_mod = _msal_module()
    return msal_mod.ConfidentialClientApplication(
        client_id=app.config["MS_CLIENT_ID"],
        client_credential=app.config["MS_CLIENT_SECRET"],
        authority=_authority(app),
    )


def _normalize_ms_error(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "Microsoft Graph request failed."
    outer = payload.get("error")
    if isinstance(outer, dict):
        code = outer.get("code")
        msg = outer.get("message")
        if code and msg:
            return f"{code}: {msg}"
        if msg:
            return str(msg)
    if isinstance(outer, str):
        desc = payload.get("error_description") or payload.get("message")
        if desc:
            return f"{outer}: {desc}"
        return outer
    return str(payload)


def build_authorization_url(app, redirect_uri: str, state: str) -> str:
    if not graph_ready(app):
        raise GraphError("Microsoft Graph integration is not configured on the server.")
    return _msal_client(app).get_authorization_request_url(
        scopes=_scopes(app),
        redirect_uri=redirect_uri,
        state=state,
        prompt="select_account",
    )


def exchange_code_for_token(app, code: str, redirect_uri: str) -> dict[str, Any]:
    if not code:
        raise GraphError("Missing OAuth authorization code.")
    result = _msal_client(app).acquire_token_by_authorization_code(
        code=code,
        scopes=_scopes(app),
        redirect_uri=redirect_uri,
    )
    if "access_token" not in result:
        raise GraphError(_normalize_ms_error(result), needs_reconnect=True)
    return result


def _refresh_token(app, refresh_token: str) -> dict[str, Any]:
    requests_mod = _requests_module()
    form = {
        "client_id": app.config["MS_CLIENT_ID"],
        "client_secret": app.config["MS_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(_scopes(app)),
    }
    try:
        res = requests_mod.post(_token_endpoint(app), data=form, timeout=20)
    except requests_mod.RequestException as exc:
        raise GraphError(f"Could not reach Microsoft token endpoint: {exc}") from exc
    payload = {}
    try:
        payload = res.json()
    except Exception:
        payload = {}
    if res.status_code >= 400 or "access_token" not in payload:
        err = _normalize_ms_error(payload) or f"HTTP {res.status_code}"
        needs_reconnect = any(k in err.lower() for k in ("invalid_grant", "interaction_required", "consent"))
        raise GraphError(f"Token refresh failed: {err}", status_code=res.status_code, needs_reconnect=needs_reconnect)
    return payload


def persist_oauth_result(db, app, user_id: int, oauth_result: dict[str, Any]) -> None:
    id_claims = oauth_result.get("id_token_claims") or {}
    account_email = str(
        id_claims.get("preferred_username")
        or id_claims.get("email")
        or id_claims.get("upn")
        or ""
    ).strip()
    account_name = str(id_claims.get("name") or "").strip()
    scope = oauth_result.get("scope") or " ".join(_scopes(app))
    tenant_hint = str(id_claims.get("tid") or (app.config.get("MS_TENANT") or "common")).strip()
    token_store.store_user_token(
        db=db,
        app=app,
        user_id=user_id,
        access_token=oauth_result["access_token"],
        refresh_token=oauth_result.get("refresh_token") or "",
        expires_in_seconds=int(oauth_result.get("expires_in") or 3600),
        scope=scope,
        tenant_hint=tenant_hint,
        account_email=account_email,
        account_display_name=account_name,
    )


def get_valid_access_token(db, app, user_id: int) -> tuple[str, dict[str, Any]]:
    row = token_store.load_user_token(db, app, user_id)
    if not row:
        raise GraphError("Your mailbox is not connected yet.", needs_reconnect=True)

    if not token_store.token_is_expired(row):
        return row["access_token"], row

    if not row.get("refresh_token"):
        raise GraphError("Your mailbox session expired. Please reconnect Outlook.", needs_reconnect=True)

    refreshed = _refresh_token(app, row["refresh_token"])
    token_store.store_user_token(
        db=db,
        app=app,
        user_id=user_id,
        access_token=refreshed["access_token"],
        refresh_token=refreshed.get("refresh_token") or row["refresh_token"],
        expires_in_seconds=int(refreshed.get("expires_in") or 3600),
        scope=refreshed.get("scope") or row.get("scope") or "",
        tenant_hint=row.get("tenant_hint") or (app.config.get("MS_TENANT") or "common"),
        account_email=row.get("account_email") or "",
        account_display_name=row.get("account_display_name") or "",
    )
    fresh_row = token_store.load_user_token(db, app, user_id)
    if not fresh_row:
        raise GraphError("Could not refresh mailbox session.", needs_reconnect=True)
    return fresh_row["access_token"], fresh_row


def disconnect_user(db, user_id: int) -> None:
    token_store.remove_user_token(db, user_id)


def _graph_json_request(
    access_token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    ok_statuses: set[int] | None = None,
) -> dict[str, Any] | None:
    app = current_app
    requests_mod = _requests_module()
    url = f"{app.config['MS_GRAPH_BASE_URL'].rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    try:
        res = requests_mod.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=25,
        )
    except requests_mod.RequestException as exc:
        raise GraphError(f"Could not reach Microsoft Graph: {exc}") from exc

    if ok_statuses is None:
        ok_statuses = {200}
    payload = None
    if res.content:
        try:
            payload = res.json()
        except Exception:
            payload = None

    if res.status_code not in ok_statuses:
        txt = _normalize_ms_error(payload)
        reconnect = res.status_code in (401, 403) and any(
            k in txt.lower() for k in ("invalid", "expired", "consent", "interaction_required")
        )
        raise GraphError(
            f"Graph API call failed ({res.status_code}): {txt}",
            status_code=res.status_code,
            needs_reconnect=reconnect,
        )
    return payload


def get_folder_messages(access_token: str, folder_key: str, top: int = 30) -> list[dict[str, Any]]:
    folder = FOLDER_MAP.get(folder_key.lower())
    if not folder:
        raise GraphError("Unknown folder requested.")
    payload = _graph_json_request(
        access_token,
        "GET",
        f"/me/mailFolders/{folder}/messages",
        params={
            "$top": max(1, min(50, int(top))),
            "$orderby": "receivedDateTime DESC",
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,hasAttachments,isRead,bodyPreview",
        },
    )
    return list((payload or {}).get("value") or [])


def get_message(access_token: str, message_id: str) -> dict[str, Any]:
    payload = _graph_json_request(
        access_token,
        "GET",
        f"/me/messages/{message_id}",
        params={
            "$select": "id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,sentDateTime,hasAttachments,isRead,body,bodyPreview,internetMessageId,parentFolderId",
        },
    )
    return payload or {}


def _normalize_recipients_csv(value: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    parts = [p.strip() for p in (value or "").replace(";", ",").split(",") if p.strip()]
    seen: set[str] = set()
    for raw in parts:
        try:
            v = validate_email(raw, check_deliverability=False)
        except EmailNotValidError as exc:
            raise GraphError(f"Invalid email address {raw!r}: {exc}")
        addr = v.normalized
        k = addr.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({"emailAddress": {"address": addr}})
    return out


def _attachments_payload(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": item["name"],
                "contentType": item.get("content_type") or "application/octet-stream",
                "contentBytes": item["content_b64"],
            }
        )
    return out


def send_mail(
    access_token: str,
    *,
    to_raw: str,
    cc_raw: str,
    bcc_raw: str,
    subject: str,
    body_text: str,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    to = _normalize_recipients_csv(to_raw)
    if not to:
        raise GraphError("At least one valid recipient is required in To.")
    cc = _normalize_recipients_csv(cc_raw)
    bcc = _normalize_recipients_csv(bcc_raw)
    msg: dict[str, Any] = {
        "subject": (subject or "").strip(),
        "body": {
            "contentType": "Text",
            "content": body_text or "",
        },
        "toRecipients": to,
        "ccRecipients": cc,
        "bccRecipients": bcc,
    }
    if attachments:
        msg["attachments"] = _attachments_payload(attachments)

    _graph_json_request(
        access_token,
        "POST",
        "/me/sendMail",
        json_body={
            "message": msg,
            "saveToSentItems": True,
        },
        ok_statuses={202},
    )
