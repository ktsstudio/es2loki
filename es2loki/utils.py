import gzip
import io


def seconds_to_str(seconds: int) -> str:
    """
    Функция должна вернуть текстовое представление времени
    20 -> 20s
    60 -> 01m00s
    65 -> 01m05s
    3700 -> 01h01m40s
    93600 -> 01d02h00m00s
    """
    seconds = int(seconds)
    days = int(seconds / (60 * 60 * 24))
    seconds -= days * 24 * 60 * 60
    hours = int(seconds / (60 * 60))
    seconds -= hours * 60 * 60
    minutes = int(seconds / 60)
    seconds -= minutes * 60

    days_str = f"{days:02d}d" if days else ""
    hours_str = f"{hours:02d}h" if hours else ""
    min_str = f"{minutes:02d}m" if minutes else ""
    sec_str = f"{seconds:02d}s"

    return f"{days_str}{hours_str}{min_str}{sec_str}"


def size_str(size: int) -> str:
    kb = size / 1024
    mb = kb / 1024
    gb = mb / 1024

    if gb >= 1:
        return f"{gb:.2f}gb"

    if mb >= 1:
        return f"{mb:.2f}mb"

    if kb >= 1:
        return f"{kb:.2f}kb"

    return f"{size:.2f}b"


def gzip_encode(content: bytes) -> bytes:
    out = io.BytesIO()
    f = gzip.GzipFile(fileobj=out, mode="w", compresslevel=5)
    f.write(content)
    f.close()
    return out.getvalue()
