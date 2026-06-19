# Send real email through Microsoft 365 (Outlook)

MiNe uses normal **SMTP client submission**, the same idea as Outlook desktop “send through this account”.

## 1. Turn off dev file logging

In `.env`:

- Set **`MAIL_DUMMY=0`** (or delete the `MAIL_DUMMY` line).

## 2. Set these variables (Microsoft 365)

Typical values:

| Variable | Example |
|----------|---------|
| `MAIL_ENABLED` | `1` |
| `MAIL_SERVER` | `smtp.office365.com` |
| `MAIL_PORT` | `587` |
| `MAIL_USE_TLS` | `1` |
| `MAIL_USE_SSL` | `0` |
| `MAIL_USERNAME` | Your full mailbox address, e.g. `you@company.com` |
| `MAIL_PASSWORD` | That account’s password, or an **app password** if MFA is on |
| `MAIL_DEFAULT_SENDER` | Same mailbox, e.g. `MiNe <you@company.com>` |

**Important:** For most tenants, Microsoft only lets you send **as** a mailbox you are allowed to use. Use the **same** licensed Microsoft 365 address for `MAIL_USERNAME` and the address inside `MAIL_DEFAULT_SENDER`.

## 3. Allow SMTP on the mailbox (admin / tenant)

If login fails or the server rejects mail:

1. In **Microsoft 365 admin center**, ensure **authenticated SMTP (SMTP AUTH)** is allowed for that mailbox (or for the organization policy your admin uses). Names vary: “SMTP AUTH”, “Authenticated SMTP”, “Manage email apps” for the user.
2. Some organizations block SMTP; your **Exchange / cloud admin** must allow client submission for your account or provide a **relay** host and credentials they support.

## 4. Multi-factor authentication (MFA)

If the account has MFA, a normal password often **does not** work for SMTP. Create an **app password** (where your org still supports it) or use a **dedicated service account** with SMTP allowed and no MFA, per your security policy.

## 5. Restart MiNe

Restart the Flask / Waitress process after editing `.env` so settings reload.

## 6. If it still does not arrive in Outlook

- Check **Junk email**.
- A green “Message sent” in MiNe means the **SMTP server accepted** the message; Microsoft 365 may still apply **anti-spoofing** or transport rules. Your admin can trace the message in **Exchange message trace**.

## Optional: capture mail locally while testing SMTP

Run [Mailpit](https://mailpit.axllent.org/) (see `docker-compose.mailpit.yml` in the repo), point `MAIL_SERVER` at `127.0.0.1` and `MAIL_PORT` at `1025`, set `MAIL_USE_TLS=0`, and leave username/password empty if your relay allows that.
