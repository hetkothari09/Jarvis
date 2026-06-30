"""Entry point: run the JARVIS daemon."""
from jarvis.core.daemon import Daemon


def main() -> int:
    return Daemon().run()


if __name__ == "__main__":
    raise SystemExit(main())
