# Follow-Up Worker Build

Replace these files in your project:

- `app.py`
- `templates/opportunity.html`
- `templates/pipeline.html`

Then run:

```powershell
py migrate_follow_up.py
py app.py
```

Test with an opportunity whose `stage` is `Sent` and whose `follow_up_date` is today or earlier.

This build adds:
- calculated Follow-Up Due status
- channel-aware follow-up drafting
- follow-up quality review
- reviewed follow-up locking
- channel-aware completion
- automatic next follow-up scheduling for seven days later
