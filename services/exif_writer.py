from datetime import datetime
from fractions import Fraction
from io import BytesIO

import piexif
from PIL import Image


def _to_rational(value, max_denominator=1000000):
    fraction = Fraction(float(value)).limit_denominator(max_denominator)
    return fraction.numerator, fraction.denominator


def _parse_dms(value):
    if isinstance(value, (int, float)):
        decimal = float(value)
        ref = 1 if decimal >= 0 else -1
        decimal = abs(decimal)
        degrees = int(decimal)
        minutes_float = (decimal - degrees) * 60
        minutes = int(minutes_float)
        seconds = (minutes_float - minutes) * 60
        return ref, degrees, minutes, seconds

    text = str(value).strip()
    separators = [";", ",", " "]
    parts = [text]
    for separator in separators:
        if separator in text:
            parts = [part for part in text.split(separator) if part.strip()]
            break

    if len(parts) == 3:
        degrees = float(parts[0])
        ref = 1 if degrees >= 0 else -1
        return ref, int(abs(degrees)), int(float(parts[1])), float(parts[2])

    decimal = float(text)
    return _parse_dms(decimal)


def _gps_coord(value):
    _, degrees, minutes, seconds = _parse_dms(value)
    return (
        _to_rational(degrees),
        _to_rational(minutes),
        _to_rational(seconds),
    )


def _gps_ref(value, positive_ref, negative_ref):
    ref, _, _, _ = _parse_dms(value)
    return positive_ref if ref >= 0 else negative_ref


def _normalize_exif_time(value):
    if not value:
        return datetime.now().strftime("%Y:%m:%d %H:%M:%S")

    text = str(value).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return text


def _ascii(value):
    return str(value).encode("ascii", errors="ignore")


def write_image_exif(
    file_storage,
    latitude,
    longitude,
    altitude=None,
    taken_at=None,
    make="Lechange",
    model="9A024A3PCG3F942",
):
    image = Image.open(file_storage.stream)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    exif_time = _normalize_exif_time(taken_at)
    zeroth_ifd = {
        piexif.ImageIFD.Make: _ascii(make),
        piexif.ImageIFD.Model: _ascii(model),
        piexif.ImageIFD.Software: b"flask_web exif tool",
        piexif.ImageIFD.DateTime: _ascii(exif_time),
    }
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: _ascii(exif_time),
        piexif.ExifIFD.DateTimeDigitized: _ascii(exif_time),
    }
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: _ascii(_gps_ref(latitude, "N", "S")),
        piexif.GPSIFD.GPSLatitude: _gps_coord(latitude),
        piexif.GPSIFD.GPSLongitudeRef: _ascii(_gps_ref(longitude, "E", "W")),
        piexif.GPSIFD.GPSLongitude: _gps_coord(longitude),
        piexif.GPSIFD.GPSMapDatum: b"WGS-84",
    }

    if altitude not in (None, ""):
        altitude_value = float(altitude)
        gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude_value >= 0 else 1
        gps_ifd[piexif.GPSIFD.GPSAltitude] = _to_rational(abs(altitude_value))

    exif_bytes = piexif.dump({
        "0th": zeroth_ifd,
        "Exif": exif_ifd,
        "GPS": gps_ifd,
        "1st": {},
        "thumbnail": None,
    })

    output = BytesIO()
    image.save(output, format="JPEG", quality=95, exif=exif_bytes)
    output.seek(0)
    return output


def write_bytes_exif(
    image_bytes,
    latitude,
    longitude,
    altitude=None,
    taken_at=None,
    make="Lechange",
    model="9A024A3PCG3F942",
):
    class _FileStorageLike:
        def __init__(self, data):
            self.stream = BytesIO(data)

    return write_image_exif(
        _FileStorageLike(image_bytes),
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        taken_at=taken_at,
        make=make,
        model=model,
    )
