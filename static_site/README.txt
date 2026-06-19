MiNe — static preview (no Python)
==================================

Open in a browser WITHOUT running Flask:

  Double-click:  index.html

Or use VS Code "Live Server" on index.html.

Contents
--------
- index.html — landing (no deployment table)
- journey.html — Freeport–Hexaware journey
- program/fmi-know-your-customer.html — Freeport KYC (Section 2)
- img/, media/, fonts/, vendor/ — mirrored from ../static/ (self-contained assets)

Other specification chapters are not published here; they were used only as build reference.

Full portal (login, database, search, uploads, admin) requires Python: python run.py
See parent folder README.md.

Asset sync
----------
After updating images or videos in static/, refresh this folder:

  python scripts/sync_static_site_assets.py

Or run the full deploy prep (bundle + sync + verify):

  python scripts/prepare_deploy.py

If styles look wrong on file://, use Live Server so CSS loads over http://.