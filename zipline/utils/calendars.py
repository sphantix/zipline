# flake8: noqa
# reexport trading_calendars for backwards compat
from exchange_calendars import (
    clear_calendars,
    deregister_calendar,
    get_calendar,
    register_calendar,
    register_calendar_alias,
    register_calendar_type,
)
