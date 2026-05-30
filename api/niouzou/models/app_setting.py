from datetime import datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class AppSetting(Base):
    """Runtime-overridable settings persisted in DB (E8-S2).

    A row in this table overrides the matching env-var-backed value in
    ``Settings``. Reads go through ``SettingsService.get(key)``.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
