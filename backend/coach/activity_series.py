"""Decode Garmin's positional chart samples into bounded, unit-labelled private series.

Garmin wire values use descriptor units; factor is not a universal scale multiplier.
No coordinates, epoch timestamps or unknown developer fields are retained.
"""

import math

LIMIT = 5000
CHANNELS = {
    "heart_rate": ("Fréquence cardiaque", "bpm", ("directHeartRate",), {"bpm"}, 1),
    "speed": ("Vitesse", "km/h", ("directSpeed",), {"mps", "kph", "kmh"}, None),
    "power": ("Puissance", "W", ("directPower",), {"watt", "watts"}, 1),
    "run_cadence": (
        "Cadence de course",
        "pas/min",
        ("directDoubleCadence", "directRunCadence"),
        {"stepsPerMinute"},
        1,
    ),
    "bike_cadence": ("Cadence de pédalage", "tr/min", ("directBikeCadence",), {"rpm"}, 1),
    "elevation": (
        "Altitude",
        "m",
        ("directCorrectedElevation", "directElevation", "directUncorrectedElevation"),
        {"meter", "meters"},
        1,
    ),
    "temperature": ("Température", "°C", ("directAirTemperature",), {"celcius", "celsius"}, 1),
    "ground_contact": (
        "Temps de contact au sol",
        "ms",
        ("directGroundContactTime",),
        {"ms", "millisecond", "milliseconds"},
        1,
    ),
    "stride_length": (
        "Longueur de foulée",
        "m",
        ("directStrideLength",),
        {"meter", "meters", "centimeter"},
        None,
    ),
}


def number(value):
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        else None
    )


def decode(raw):
    if not isinstance(raw, dict):
        raise ValueError("Format des courbes Garmin indisponible.")
    rows, descriptors = raw.get("activityDetailMetrics", []), raw.get("metricDescriptors", [])
    if not isinstance(rows, list) or not isinstance(descriptors, list) or len(rows) > LIMIT:
        raise ValueError("Format ou volume des courbes Garmin non pris en charge.")
    fields = {}
    for d in descriptors:
        if not isinstance(d, dict) or not isinstance(d.get("key"), str):
            continue
        index = d.get("metricsIndex")
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < 200:
            # Conflicting duplicate names are not silently assigned to another channel.
            if d["key"] in fields:
                fields[d["key"]] = None
            else:
                fields[d["key"]] = d

    def column(key, units):
        d = fields.get(key)
        if not d or not isinstance(d.get("unit"), dict) or d["unit"].get("key") not in units:
            return None, None
        values = []
        for row in rows:
            metrics = row.get("metrics") if isinstance(row, dict) else None
            values.append(
                number(metrics[d["metricsIndex"]])
                if isinstance(metrics, list) and d["metricsIndex"] < len(metrics)
                else None
            )
        return values, d["unit"]["key"]

    timestamps, _ = column("directTimestamp", {"gmt", "unixMilliseconds"})
    if timestamps and any(v is not None for v in timestamps):
        first = next(v for v in timestamps if v is not None)
        elapsed = [(v - first) / 1000 if v is not None and v >= first else None for v in timestamps]
        origin = "first_timestamp"
    else:
        elapsed, _ = column("sumElapsedDuration", {"second", "seconds"})
        origin = "garmin_elapsed"
    distance, _ = column("sumDistance", {"meter", "meters"})
    axes = {"time": elapsed or [None] * len(rows), "distance": distance or [None] * len(rows)}
    for values in axes.values():
        previous = -1
        for i, v in enumerate(values):
            if v is not None:
                if v < previous or v < 0:
                    values[i] = None
                else:
                    previous = v
    channels, unsupported = [], []
    for key, (label, unit, sources, allowed, multiplier) in CHANNELS.items():
        for source in sources:
            values, source_unit = column(source, allowed)
            if values is None or not any(v is not None for v in values):
                continue
            scale = multiplier or (
                3.6 if source_unit == "mps" else 0.01 if source_unit == "centimeter" else 1
            )
            values = [
                v * scale
                if v is not None
                and (v >= 0 or key in {"elevation", "temperature"})
                and (key != "heart_rate" or v > 0)
                else None
                for v in values
            ]
            if any(v is not None for v in values):
                channels.append(
                    {"key": key, "label": label, "unit": unit, "source": source, "values": values}
                )
            break
        else:
            if any(fields.get(source) for source in sources):
                unsupported.append(key)
    return {
        "version": 1,
        "count": len(rows),
        "axes": axes,
        "time_origin": origin,
        "channels": channels,
        "unsupported": unsupported,
        "status": "available" if channels else "no_samples",
    }
