from app import (
    app,
    db,
    Organization,
    SponsorshipInitiative
)

with app.app_context():
    db.create_all()

    organization = Organization.query.first()

    if not organization:
        organization = Organization(
            name="Ms. Full-Figured North Carolina Pageant",
            organization_type="Pageant",
            city="Durham",
            state="NC",
            mission=(
                "Empower, Inspire, and Serve through confidence, leadership, "
                "community service, personal growth, and sisterhood."
            ),
            sender_name="Marsha Shearin",
            sender_title="Assistant Director",
            sender_email=""
        )
        db.session.add(organization)
        db.session.flush()
        print("Created default organization profile.")
    else:
        print("Organization profile already exists.")

    initiative = SponsorshipInitiative.query.filter_by(
        organization_id=organization.id
    ).first()

    if not initiative:
        initiative = SponsorshipInitiative(
            organization_id=organization.id,
            name="2026 Ms. Full-Figured North Carolina Pageant",
            fundraising_target="$25,000 cash + $10,000 in-kind",
            audience=(
                "Delegates, pageant attendees, families, supporters, local "
                "community members, social media followers, and women connected "
                "to confidence, service, and empowerment."
            ),
            needs=(
                "Venue costs, printing, program book, delegate experiences, "
                "awards, photography, beauty services, fashion support, "
                "hospitality, community service support, and event production."
            ),
            goals="Build a qualified sponsorship pipeline and secure cash and in-kind support.",
            status="Active"
        )
        db.session.add(initiative)
        print("Created default sponsorship initiative.")
    else:
        print("Sponsorship initiative already exists.")

    db.session.commit()
    print("Organization setup migration complete.")
