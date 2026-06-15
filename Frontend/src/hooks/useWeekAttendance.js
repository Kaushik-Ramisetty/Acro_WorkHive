import { useEffect, useState } from 'react';
import { attendance } from '../services/attendance';
import { fmtIso } from '../utils/weekHelpers';

/**
 * Fetches attendance hours for every day in the active week from the backend.
 *
 * Returns:
 *   attendanceMap  — { [dateStr: YYYY-MM-DD]: AttendanceDayRecord }
 *   isLoading      — true while the request is in flight
 *   error          — Error object if the request failed, null otherwise
 *   refetch        — call to re-fetch manually (e.g. after check-out)
 *
 * AttendanceDayRecord: { date, check_in, check_out, effective_hours, attendance_status }
 *   attendance_status: 'FINALIZED' | 'PENDING_CHECKOUT' | 'NO_ATTENDANCE'
 */
export function useWeekAttendance(activeWeekStart) {
  const [attendanceMap, setAttendanceMap] = useState({});
  const [isLoading, setIsLoading]         = useState(false);
  const [error, setError]                 = useState(null);
  const [tick, setTick]                   = useState(0);

  const refetch = () => setTick((t) => t + 1);

  useEffect(() => {
    if (!activeWeekStart) return;

    const weekStartStr = activeWeekStart instanceof Date
      ? fmtIso(activeWeekStart)
      : String(activeWeekStart);

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    attendance.weeklyHours(weekStartStr)
      .then((records) => {
        if (cancelled) return;
        const map = {};
        records.forEach((r) => { map[r.date] = r; });
        setAttendanceMap(map);
      })
      .catch((err) => {
        if (cancelled) return;
        console.warn('useWeekAttendance: could not fetch attendance hours', err);
        setError(err);
        setAttendanceMap({});
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [activeWeekStart, tick]);

  return { attendanceMap, isLoading, error, refetch };
}
