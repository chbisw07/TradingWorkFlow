"""Settings use cases own transactions; transport never manipulates rows."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from twf.infrastructure.preferences import PreferenceChange, PreferenceProfile, UserPreferences
from twf.settings_contracts import (
    DEFINITIONS,
    CapabilityPolicy,
    PreferenceValues,
    ProfileInput,
    ProfileView,
    ResolvedValues,
    SettingsView,
)


class SettingsFailure(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


class Preferences:
    def __init__(
        self,
        session: Session,
        user_id: UUID,
        policy: CapabilityPolicy,
        request_id: str | None = None,
    ):
        self.session, self.user_id, self.policy, self.request_id = (
            session,
            user_id,
            policy,
            request_id,
        )

    def authorize(self) -> None:
        if any(not self.policy.allows(self.user_id, item.capability) for item in DEFINITIONS):
            raise SettingsFailure(403)

    def read(self) -> SettingsView:
        self.authorize()
        row = self.session.get(UserPreferences, self.user_id)
        values = PreferenceValues.model_validate(row.values if row else {})
        return SettingsView(
            revision=row.revision if row else 0,
            overrides=values,
            effective=ResolvedValues.model_validate(values.stored()),
            sources={
                item.key: "USER" if item.key in values.stored() else "PLATFORM"
                for item in DEFINITIONS
            },
            active_profile_id=row.active_profile_id if row else None,
            applied_profile_revision=row.applied_profile_revision if row else None,
        )

    def audit(self, target: str, action: str, revision: int) -> None:
        self.session.add(
            PreferenceChange(
                user_id=self.user_id,
                target=target,
                action=action,
                revision=revision,
                request_id=self.request_id,
                created_at=datetime.now(UTC),
            )
        )

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise SettingsFailure(409) from error

    def write(
        self,
        revision: int,
        values: PreferenceValues,
        action: str = "APPLY",
    ) -> SettingsView:
        self.authorize()
        # End authentication/read snapshots before the conditional write (SQLite and PostgreSQL).
        self.session.rollback()
        fields = dict(
            values=values.stored(),
            revision=revision + 1,
            schema_version=1,
            active_profile_id=None,
            applied_profile_revision=None,
            updated_at=datetime.now(UTC),
        )
        if revision == 0:
            self.session.add(UserPreferences(user_id=self.user_id, **fields))
        else:
            result = self.session.execute(
                update(UserPreferences)
                .where(
                    UserPreferences.user_id == self.user_id, UserPreferences.revision == revision
                )
                .values(**fields)
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                self.session.rollback()
                raise SettingsFailure(409)
        self.audit("settings", action, revision + 1)
        self.commit()
        return self.read()

    def profile(self, profile_id: UUID) -> PreferenceProfile:
        row = self.session.scalar(
            select(PreferenceProfile).where(
                PreferenceProfile.id == profile_id, PreferenceProfile.user_id == self.user_id
            )
        )
        if row is None:
            raise SettingsFailure(404)
        return row

    @staticmethod
    def view(row: PreferenceProfile) -> ProfileView:
        return ProfileView(
            id=row.id,
            name=row.name,
            revision=row.revision,
            values=PreferenceValues.model_validate(row.values),
        )

    def profiles(self) -> list[ProfileView]:
        self.authorize()
        return [
            self.view(row)
            for row in self.session.scalars(
                select(PreferenceProfile)
                .where(PreferenceProfile.user_id == self.user_id)
                .order_by(PreferenceProfile.id)
            )
        ]

    def save_profile(
        self, payload: ProfileInput, profile_id: UUID | None = None, revision: int | None = None
    ) -> ProfileView:
        self.authorize()
        self.session.rollback()
        if profile_id is None:
            row = PreferenceProfile(
                user_id=self.user_id,
                name=payload.name,
                values=payload.values.stored(),
                revision=1,
                updated_at=datetime.now(UTC),
            )
            self.session.add(row)
            self.session.flush()
        else:
            self.profile(profile_id)
            self.session.rollback()
            result = self.session.execute(
                update(PreferenceProfile)
                .where(
                    PreferenceProfile.id == profile_id,
                    PreferenceProfile.user_id == self.user_id,
                    PreferenceProfile.revision == revision,
                )
                .values(
                    name=payload.name,
                    values=payload.values.stored(),
                    revision=(revision or 0) + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                self.session.rollback()
                raise SettingsFailure(409)
            row = self.profile(profile_id)
        self.audit(str(row.id), "PROFILE_SAVE", row.revision)
        self.commit()
        return self.view(row)

    def apply_profile(self, profile_id: UUID, revision: int, profile_revision: int) -> SettingsView:
        self.authorize()
        self.session.rollback()
        # Conditional no-op UPDATE locks the profile revision until the settings write commits.
        result = self.session.execute(
            update(PreferenceProfile)
            .where(
                PreferenceProfile.id == profile_id,
                PreferenceProfile.user_id == self.user_id,
                PreferenceProfile.revision == profile_revision,
            )
            .values(revision=profile_revision)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            exists = self.session.scalar(
                select(PreferenceProfile.id).where(
                    PreferenceProfile.id == profile_id, PreferenceProfile.user_id == self.user_id
                )
            )
            self.session.rollback()
            raise SettingsFailure(409 if exists else 404)
        row = self.profile(profile_id)
        fields = dict(
            values=PreferenceValues.model_validate(row.values).stored(),
            revision=revision + 1,
            schema_version=1,
            active_profile_id=row.id,
            applied_profile_revision=row.revision,
            updated_at=datetime.now(UTC),
        )
        if revision == 0:
            self.session.add(UserPreferences(user_id=self.user_id, **fields))
        else:
            result = self.session.execute(
                update(UserPreferences)
                .where(
                    UserPreferences.user_id == self.user_id, UserPreferences.revision == revision
                )
                .values(**fields)
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                self.session.rollback()
                raise SettingsFailure(409)
        self.audit("settings", "PROFILE_APPLY", revision + 1)
        self.commit()
        return self.read()
