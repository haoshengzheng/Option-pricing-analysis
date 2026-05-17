from datetime import datetime, date, timedelta, time
from typing import Optional, List
import pandas_market_calendars as mcal

_nyse = mcal.get_calendar('NYSE')


_DAY_SESSIONS: list[tuple[time, time]] = [
    (time(9, 30), time(16, 0))
]

SECONDS_PER_FULL_TRADE_DAY = 23400
trading_days_per_year = 252


def is_us_trading_day(d: date) -> bool:
    schedule = _nyse.schedule(start_date=d, end_date=d)
    return not schedule.empty


def _in_day_sessions(t: time) -> bool:
    return any(s <= t <= e for s, e in _DAY_SESSIONS)


def prev_trading_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_us_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    cur = d + timedelta(days=1)
    while not is_us_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def next_trading_day_open(dt: datetime) -> datetime:
    next_dt = next_trading_day(dt.date())
    return datetime.combine(next_dt, _DAY_SESSIONS[0][0])


def get_all_sessions_of_trading_day(d: date) -> list[tuple[datetime, datetime]]:
    if not is_us_trading_day(d):
        return []

    sessions = []
    for s_time, e_time in _DAY_SESSIONS:
        sessions.append((datetime.combine(d, s_time), datetime.combine(d, e_time)))
    return sessions


def count_trading_seconds_precise(start_dt: datetime, end_dt: datetime) -> float:
    total_seconds = 0
    curr_d = start_dt.date()
    scan_end_d = end_dt.date()

    while curr_d <= scan_end_d:
        if is_us_trading_day(curr_d):
            for s_dt, e_dt in get_all_sessions_of_trading_day(curr_d):
                overlap_start = max(s_dt, start_dt)
                overlap_end = min(e_dt, end_dt)
                if overlap_start < overlap_end:
                    total_seconds += (overlap_end - overlap_start).total_seconds()
        curr_d += timedelta(days=1)
    return total_seconds


def get_trading_day(dt: datetime) -> Optional[date]:
    d, t = dt.date(), dt.time()
    if is_us_trading_day(d):
        if _in_day_sessions(t):
            return d
    return None


def resolve_trading_day(dt: datetime) -> Optional[date]:
    d, t = dt.date(), dt.time()

    td = get_trading_day(dt)
    if td is not None:
        return td


    if t < _DAY_SESSIONS[0][0]:
        return d if is_us_trading_day(d) else next_trading_day(d)


    if t > _DAY_SESSIONS[-1][1]:
        return next_trading_day(d)

    return None


def count_trading_days(start_dt: datetime, end_dt: datetime) -> int:
    start_td = resolve_trading_day(start_dt)
    # 简单的结束日期处理
    if is_us_trading_day(end_dt.date()):
        end_td = end_dt.date()
    else:
        cur = end_dt.date()
        while not is_us_trading_day(cur):
            cur -= timedelta(days=1)
        end_td = cur

    if start_td > end_td:
        return 0
    schedule = _nyse.schedule(start_date=start_td, end_date=end_td)
    return len(schedule)


def parse_dt(s: str) -> datetime:
    for fmt in ('%Y.%m.%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
                '%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间字符串: {s!r}")


def generate_trading_day_obs(start_dt: str, end_dt: str, obs_time: time = time(16, 0)) -> List[str]:
    start = parse_dt(start_dt)
    end = parse_dt(end_dt)
    result = []

    schedule = _nyse.schedule(start_date=start.date(), end_date=end.date())

    for day in schedule.index:
        obs_dt = datetime.combine(day.date(), obs_time)
        if start <= obs_dt <= end:
            result.append(obs_dt.strftime('%Y-%m-%d %H:%M:%S'))
    return result