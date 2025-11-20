# time_sync.py
#
# This module provides functions to synchronize the device's Real-Time Clock (RTC)
# with an NTP server and automatically calculate and set the Central European
# Time (CET/CEST) based on German Daylight Saving Time (DST) rules.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.

from machine import RTC
import ntptime
import time

def is_summer_time(year, month, day, hour):
    """
    Determines whether a given date in Germany falls under Daylight Saving Time.
    Returns: True = CEST, False = CET
    """

    # Last Sunday in March
    last_sunday_march = max(
        d for d in range(25, 32)
        if time.localtime(time.mktime((year, 3, d, 0, 0, 0, 0, 0)))[6] == 6
    )

    # Last Sunday in October
    last_sunday_october = max(
        d for d in range(25, 32)
        if time.localtime(time.mktime((year, 10, d, 0, 0, 0, 0, 0)))[6] == 6
    )

    # DST rule logic
    if 3 < month < 10:
        return True
    elif month == 3 and (day > last_sunday_march or (day == last_sunday_march and hour >= 2)):
        return True
    elif month == 10 and (day < last_sunday_october or (day == last_sunday_october and hour < 3)):
        return True
    else:
        return False

async def sync_time():
    """
    Synchronizes the RTC time using NTP and applies the German local time offset,
    including automatic daylight saving time adjustment.
    """
    rtc = RTC()

    try:
        print("⏱️ Synchronizing time via NTP...")
        ntptime.settime()  # Set UTC time
        year, month, day, weekday, hour, minute, second, ms = rtc.datetime()

        # Determine timezone offset based on DST
        if is_summer_time(year, month, day, hour):
            tz_offset = 2  # CEST
        else:
            tz_offset = 1  # CET

        # Adjust hour with wrap-around at midnight
        local_hour = (hour + tz_offset) % 24

        rtc.datetime((year, month, day, weekday, local_hour, minute, second, ms))
        print(f"✅ Local German time set (UTC+{tz_offset}): {rtc.datetime()}")

    except Exception as e:
        print(f"⚠️ Failed to set NTP time: {e}")