# Microsoft Graph Mailbox Setup (Admin)

This guide configures MiNe to send and browse Outlook mail through Microsoft Graph API using OAuth 2.0 Authorization Code flow.

## 1) Register an app in Microsoft Entra ID

1. Open Microsoft Entra admin center.
2. Go to **App registrations** -> **New registration**.
3. Set **Supported account types**:
   - `Accounts in any organizational directory and personal Microsoft accounts`.
4. Add redirect URI (Web):
   - `https://<your-host>/admin/mailbox/oauth/callback`
   - For local dev: `http://127.0.0.1:5000/admin/mailbox/oauth/callback`
5. Create app and copy:
   - Application (client) ID
   - Directory (tenant) ID (optional if using `common`)
6. Create a **client secret** and copy its value.

## 2) Microsoft Graph API permissions

Add delegated Graph permissions:

- `User.Read`
- `Mail.ReadWrite`
- `Mail.Send`
- `offline_access`
- `openid`
- `profile`

Grant admin consent if your tenant policy requires it.

## 3) Configure MiNe environment

Add these variables to `.env`:

```env
MS_GRAPH_ENABLED=1
MS_CLIENT_ID=<application-client-id>
MS_CLIENT_SECRET=<client-secret-value>
MS_TENANT=common
MS_REDIRECT_PATH=/admin/mailbox/oauth/callback
MS_TOKEN_ENCRYPTION_KEY=<fernet-key>
```

Generate `MS_TOKEN_ENCRYPTION_KEY`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 4) Install dependencies and restart

```powershell
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

## 5) Connect mailbox in MiNe

1. Sign in as admin.
2. Open **Settings -> Outlook Mailbox**.
3. Click **Connect Microsoft account** and complete OAuth consent.
4. Use Inbox/Sent/Drafts/Trash and Compose pages.

## 6) Troubleshooting

- **OAuth state check failed**
  - Retry connect; ensure callback URL and host are consistent.
- **Token refresh failed / reconnect required**
  - Consent may be revoked or refresh token expired; reconnect mailbox.
- **403 permission error**
  - Verify Graph delegated permissions and tenant admin consent.
- **Send accepted but delivery missing**
  - Check recipient mailbox spam/quarantine/transport rules.

## Security notes

- Outlook passwords are never stored by MiNe.
- Access and refresh tokens are encrypted at rest.
- Keep `.env` private and rotate `MS_CLIENT_SECRET` / `MS_TOKEN_ENCRYPTION_KEY` per policy.
