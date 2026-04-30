from datetime import datetime

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    Activity,
    Event,
    EventType,
    FileType,
    LapTrigger,
    SessionTrigger,
    Sport,
    SubSport,
    TimerTrigger,
)
from geopy.distance import geodesic


MANUFACTURER = 1
GARMIN_PRODUCT = 3415
GARMIN_SOFTWARE_VERSION = 3.58
GARMIN_SERIAL_NUMBER = 1234567890


def gpx_to_fit(gpx_data):
    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    if gpx_data.time:
        time_create = int(gpx_data.time.timestamp() * 1000)
    else:
        time_create = int(datetime.now().timestamp() * 1000)

    file_id = FileIdMessage()
    file_id.local_id = 0
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = MANUFACTURER
    file_id.product = GARMIN_PRODUCT
    file_id.time_created = time_create
    file_id.serial_number = GARMIN_SERIAL_NUMBER
    builder.add(file_id)

    device = DeviceInfoMessage()
    device.local_id = 1
    device.serial_number = GARMIN_SERIAL_NUMBER
    device.manufacturer = MANUFACTURER
    device.garmin_product = GARMIN_PRODUCT
    device.software_version = GARMIN_SOFTWARE_VERSION
    device.device_index = 0
    device.source_type = 5
    device.product = GARMIN_PRODUCT
    builder.add(device)

    distance = 0.0
    records = []
    prev_coord = None
    prev_time = None
    moving_time = 0
    total_distance = 0.0
    start_time = None
    end_time = None
    max_speed = 0.0
    min_altitude = float("inf")
    max_altitude = float("-inf")
    total_ascent = 0.0
    total_descent = 0.0
    prev_altitude = None

    for track in gpx_data.tracks:
        for segment in track.segments:
            for pt in segment.points:
                if pt.time is None:
                    continue

                current_coord = (pt.latitude, pt.longitude)
                current_time = pt.time
                current_altitude = pt.elevation if pt.elevation is not None else 0

                if start_time is None:
                    start_time = current_time
                    start_event = EventMessage()
                    start_event.local_id = 2
                    start_event.event = Event.TIMER
                    start_event.event_type = EventType.START
                    start_event.event_group = 0
                    start_event.timer_trigger = TimerTrigger.MANUAL
                    start_event.timestamp = int(current_time.timestamp() * 1000)
                    builder.add(start_event)

                if prev_coord and prev_time:
                    delta = geodesic(prev_coord, current_coord).meters
                    dt = (current_time - prev_time).total_seconds()
                    if 0 < dt < 60:
                        moving_time += dt
                        distance += delta
                        total_distance = distance
                        current_speed = max(0.0, min(delta / dt, 65.535))
                        max_speed = max(max_speed, current_speed)
                    else:
                        current_speed = 0.0
                else:
                    current_speed = 0.0

                if prev_altitude is not None:
                    altitude_diff = current_altitude - prev_altitude
                    if altitude_diff > 0:
                        total_ascent += altitude_diff
                    else:
                        total_descent += abs(altitude_diff)

                if current_altitude > 0:
                    min_altitude = min(min_altitude, current_altitude)
                    max_altitude = max(max_altitude, current_altitude)

                record = RecordMessage()
                record.local_id = 3
                record.position_lat = pt.latitude
                record.position_long = pt.longitude
                record.distance = distance
                record.altitude = current_altitude
                record.speed = current_speed
                record.enhanced_speed = current_speed
                record.timestamp = int(current_time.timestamp() * 1000)
                records.append(record)

                prev_coord = current_coord
                prev_time = current_time
                prev_altitude = current_altitude
                end_time = current_time

    builder.add_all(records)

    avg_speed = (total_distance / moving_time) if moving_time > 0 else 0.0
    avg_speed = max(0.0, min(avg_speed, 65.535))
    max_speed = max(0.0, min(max_speed, 65.535))

    if start_time and end_time and records:
        lap = LapMessage()
        lap.local_id = 4
        lap.timestamp = int(end_time.timestamp() * 1000)
        lap.message_index = 0
        lap.start_time = int(start_time.timestamp() * 1000)
        lap.total_elapsed_time = moving_time
        lap.total_timer_time = moving_time
        lap.start_position_lat = records[0].position_lat
        lap.start_position_long = records[0].position_long
        lap.end_position_lat = records[-1].position_lat
        lap.end_position_long = records[-1].position_long
        lap.total_distance = total_distance
        lap.sport = Sport.CYCLING
        lap.sub_sport = SubSport.GENERIC
        lap.avg_speed = avg_speed
        lap.enhanced_avg_speed = avg_speed
        lap.max_speed = max_speed
        lap.enhanced_max_speed = max_speed
        lap.total_ascent = total_ascent
        lap.total_descent = total_descent
        lap.min_altitude = min_altitude if min_altitude != float("inf") else 0
        lap.max_altitude = max_altitude if max_altitude != float("-inf") else 0
        lap.trigger = LapTrigger.MANUAL
        builder.add(lap)

        session = SessionMessage()
        session.local_id = 5
        session.timestamp = int(end_time.timestamp() * 1000)
        session.start_time = int(start_time.timestamp() * 1000)
        session.total_elapsed_time = moving_time
        session.total_timer_time = moving_time
        session.start_position_lat = records[0].position_lat
        session.start_position_long = records[0].position_long
        session.sport = Sport.CYCLING
        session.sub_sport = SubSport.GENERIC
        session.first_lap_index = 0
        session.num_laps = 1
        session.trigger = SessionTrigger.ACTIVITY_END
        session.event = Event.SESSION
        session.event_type = EventType.STOP
        session.total_distance = total_distance
        session.avg_speed = avg_speed
        session.enhanced_avg_speed = avg_speed
        session.max_speed = max_speed
        session.enhanced_max_speed = max_speed
        session.total_ascent = total_ascent
        session.total_descent = total_descent
        session.min_altitude = min_altitude if min_altitude != float("inf") else 0
        session.max_altitude = max_altitude if max_altitude != float("-inf") else 0
        builder.add(session)

        stop_event = EventMessage()
        stop_event.local_id = 2
        stop_event.event = Event.TIMER
        stop_event.event_type = EventType.STOP
        stop_event.event_group = 0
        stop_event.timer_trigger = TimerTrigger.MANUAL
        stop_event.timestamp = int(end_time.timestamp() * 1000)
        builder.add(stop_event)

        activity = ActivityMessage()
        activity.local_id = 6
        activity.timestamp = int(end_time.timestamp() * 1000)
        activity.total_timer_time = moving_time
        activity.num_sessions = 1
        activity.type = Activity.MANUAL
        activity.event = Event.ACTIVITY
        activity.event_type = EventType.STOP
        activity.event_group = 0
        builder.add(activity)

    return builder.build()
