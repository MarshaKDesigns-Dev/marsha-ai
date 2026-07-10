# Context-Driven AI Workers

This update makes the existing AI workers use the saved organization and active
sponsorship initiative throughout:

- Contact Research Worker
- Outreach Drafting Worker
- Message Quality Review Worker
- Follow-Up Worker
- Follow-Up Quality Review

It also restores explicit contact-form drafting logic and removes pageant-specific
fallback context from the worker layer.

## Install

1. Stop Flask.
2. Replace the project `app.py` with this `app.py`.
3. Do not run a migration; this update adds no database columns.
4. Start the app with:

```powershell
py app.py
```

5. Test by re-running contact research for one unsaved prospect.
