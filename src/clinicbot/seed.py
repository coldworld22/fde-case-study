"""Load demo branches, doctors and two weeks of slots:  python -m clinicbot.seed"""

from datetime import UTC, datetime

from .config import get_settings
from .models import make_session_factory
from .scheduling import seed


def main() -> None:
    with make_session_factory(get_settings().database_url)() as session:
        created = seed(session, datetime.now(UTC))
    print(f"created {created} slots" if created else "already seeded")


if __name__ == "__main__":
    main()
