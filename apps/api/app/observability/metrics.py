"""Tiny in-process metrics registry with Prometheus text exposition. No external dependency or service.

Per process only (not aggregated across workers). Labels are bounded: routes are path *templates*, never raw paths.
"""

import threading
from collections import defaultdict

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _labels(names: tuple[str, ...], values: tuple[str, ...]) -> str:
    return "{" + ",".join(f'{n}="{_esc(v)}"' for n, v in zip(names, values, strict=True)) + "}" if names else ""


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
            self._hist: dict[tuple[str, str], list[float]] = {}
            self._in_flight = 0
            self._auth: dict[str, int] = defaultdict(int)

    def inc_in_flight(self) -> None:
        with self._lock:
            self._in_flight += 1

    def dec_in_flight(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, str(status))] += 1
            h = self._hist.setdefault((method, route), [0.0] * (len(BUCKETS) + 2))  # buckets..., +Inf count, sum
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    h[i] += 1
            h[len(BUCKETS)] += 1
            h[len(BUCKETS) + 1] += seconds

    def auth_event(self, event: str) -> None:
        with self._lock:
            self._auth[event] += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP http_requests_total Requests by method, route template and status.",
                "# TYPE http_requests_total counter",
            ]
            for (method, route, status), n in sorted(self._requests.items()):
                lines.append(
                    f"http_requests_total{_labels(('method', 'route', 'status'), (method, route, status))} {n}"
                )
            lines += [
                "# HELP http_request_duration_seconds Request latency.",
                "# TYPE http_request_duration_seconds histogram",
            ]
            for (method, route), h in sorted(self._hist.items()):
                base = ("method", "route")
                for i, bound in enumerate(BUCKETS):
                    lab = _labels((*base, "le"), (method, route, str(bound)))
                    lines.append(f"http_request_duration_seconds_bucket{lab} {int(h[i])}")
                inf = _labels((*base, "le"), (method, route, "+Inf"))
                lines.append(f"http_request_duration_seconds_bucket{inf} {int(h[len(BUCKETS)])}")
                lines.append(
                    f"http_request_duration_seconds_sum{_labels(base, (method, route))} {h[len(BUCKETS) + 1]:.6f}"
                )
                lines.append(
                    f"http_request_duration_seconds_count{_labels(base, (method, route))} {int(h[len(BUCKETS)])}"
                )
            lines += [
                "# HELP http_requests_in_flight Requests currently being handled.",
                "# TYPE http_requests_in_flight gauge",
                f"http_requests_in_flight {self._in_flight}",
            ]
            lines += ["# HELP auth_events_total Authentication events.", "# TYPE auth_events_total counter"]
            for event, n in sorted(self._auth.items()):
                lines.append(f"auth_events_total{_labels(('event',), (event,))} {n}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
