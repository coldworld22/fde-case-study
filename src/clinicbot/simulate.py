"""Chat with the bot in a terminal, no WhatsApp account needed.

    python -m clinicbot.simulate            interactive, fresh in-memory database
    python -m clinicbot.simulate --demo     replays the scripted demo conversation used in the README
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .config import RIYADH
from .conversation import BookingFlow
from .models import make_session_factory
from .scheduling import seed
from .triage import RuleTriage

DEMO_PHONE = "+966551234567"
DEMO_NOW = datetime(2026, 11, 22, 9, 0, tzinfo=RIYADH)  # a Sunday morning
DEMO_SCRIPT = [
    "السلام عليكم",
    "1",
    "ابني عنده حرارة وكحة من يومين",
    "1",
    "محمد أحمد العسيري",
    "1012345672",
    "نعم",
    "EN",
    "1",
    "I have chest pain and I'm short of breath",
    "2",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="replay the scripted demo conversation")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    now = DEMO_NOW if args.demo else datetime.now(RIYADH)
    session = make_session_factory("sqlite://")()
    seed(session, now)
    flow = BookingFlow(session, RuleTriage())

    def exchange(text: str) -> None:
        print(f"\n👤 {text}")
        for reply in flow.handle(DEMO_PHONE, text, now):
            print("🤖 " + reply.replace("\n", "\n   "))

    if args.demo:
        for line in DEMO_SCRIPT:
            exchange(line)
        return
    print("Type a message (Ctrl+C to quit). Try: 'hi', then '1'.")
    try:
        while True:
            exchange(input("> "))
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
