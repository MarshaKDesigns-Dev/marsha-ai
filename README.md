# Sponsorship Coordinator MVP v6

Adds the Message Quality Review Worker.

V6 workflow:
1. Prospect research identifies a decision-maker.
2. Director approves and saves opportunity.
3. Outreach Execution Worker prepares test delivery.
4. Message Quality Review Worker improves the subject and message before sending.
5. Director reviews improved draft.
6. Send Test Email sends only to the configured test inbox while TEST_MODE=true.
7. App records Sent and schedules follow-up.

Setup:
- Copy `.env` and `instance/sponsorship.db` from v5.
- Run the database migration below because v6 adds new columns:
  - reviewed_message
  - message_review_notes
  - message_reviewed_at

Never share `.env` or API keys.
