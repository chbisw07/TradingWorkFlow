"""Explicit development-only provisioning: python -m twf.bootstrap."""

import argparse
from getpass import getpass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from twf.auth import create_user
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a development TWF user (never updates users)"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    settings = Settings()
    if settings.environment not in {"development", "test"}:
        parser.exit(2, "User bootstrap is disabled in production.\n")
    password = getpass("Password (12–128 characters): ")
    if password != getpass("Confirm password: "):
        parser.exit(2, "Passwords do not match.\n")
    engine = create_database_engine(settings)
    try:
        with session_scope(create_session_factory(engine)) as session:
            create_user(session, args.username, args.display_name, password)
            session.commit()
    except IntegrityError:
        parser.exit(2, "Username already exists; no credentials changed.\n")
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    except SQLAlchemyError:
        parser.exit(
            2, "Database operation failed. Check configuration and run migrations explicitly.\n"
        )
    finally:
        engine.dispose()
    print("Development user created.")


if __name__ == "__main__":
    main()
