import random
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


# Config
QUERY_DATE = datetime.now().strftime("%Y-%m-%d")
TRAIN_CODE = "G1"

TRAIN_SEARCH_URL = "https://search.12306.cn/search/v1/train/search"
TRAIN_STOPS_URL = "https://kyfw.12306.cn/otn/czxx/queryByTrainNo"
REQUEST_DELAY_SECONDS = (0.1, 3.0)
DEBUG_RESPONSE_FILE = Path(__file__).resolve().parent / "last_12306_response.txt"
STATION_NAME_FILE = Path(__file__).resolve().parent / "data" / "station_name"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://kyfw.12306.cn/otn/czxx/init",
    "Accept": "application/json, text/plain, */*",
}


def load_station_code_map(path=STATION_NAME_FILE):
    station_code_map = {}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed to read station name file: {path}") from exc

    for item in text.split("@"):
        if not item:
            continue

        fields = item.split("|")
        if len(fields) < 3:
            continue

        name = fields[1].strip()
        code = fields[2].strip()
        if name and code:
            station_code_map[name] = code

    if not station_code_map:
        raise RuntimeError(f"No station data loaded from: {path}")

    return station_code_map


STATION_CODE_MAP = load_station_code_map()


def get_station_code(name):
    if name not in STATION_CODE_MAP:
        raise ValueError(f"No station code for: {name}. Please check {STATION_NAME_FILE}.")
    return STATION_CODE_MAP[name]


def sleep_before_query():
    delay = random.uniform(*REQUEST_DELAY_SECONDS)
    print(f"Waiting {delay:.2f}s before query...")
    time.sleep(delay)


def parse_json_response(response):
    text = response.text.strip()
    if not text:
        print(f"Empty response from {response.url}")
        return None

    try:
        return response.json()
    except ValueError as exc:
        DEBUG_RESPONSE_FILE.write_text(response.text, encoding="utf-8", errors="replace")
        print(f"Response is not JSON: {exc}")
        print(f"HTTP {response.status_code}, content length: {len(response.text)}")
        print(f"Full response saved to: {DEBUG_RESPONSE_FILE}")
        return None


def fetch_json(session, url, params):
    if requests is None:
        print("Missing dependency: requests. Please run: pip install requests")
        return None

    try:
        sleep_before_query()
        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Request failed for {url}: {exc}")
        return None

    return parse_json_response(response)


def search_train(session, train_code, date):
    params = {
        "keyword": train_code,
        "date": date.replace("-", ""),
    }
    data = fetch_json(session, TRAIN_SEARCH_URL, params)
    if not data:
        return None

    trains = data.get("data", [])
    exact_matches = [
        train for train in trains
        if train.get("station_train_code", "").upper() == train_code.upper()
    ]

    if not exact_matches:
        print(f"No exact train match found for: {train_code}")
        return None

    return exact_matches[0]


def query_train_stops(session, train_info, date):
    try:
        from_station_code = get_station_code(train_info["from_station"])
        to_station_code = get_station_code(train_info["to_station"])
    except ValueError as exc:
        print(exc)
        return []

    params = {
        "train_no": train_info["train_no"],
        "from_station_telecode": from_station_code,
        "to_station_telecode": to_station_code,
        "depart_date": date,
    }
    data = fetch_json(session, TRAIN_STOPS_URL, params)
    if not data:
        return []

    payload = data.get("data", {})
    records = payload.get("data", [])
    if not isinstance(records, list):
        return []

    return records


def print_train_info(train_info):
    print(
        f"{train_info['station_train_code']} "
        f"{train_info['from_station']} -> {train_info['to_station']} "
        f"internal train_no: {train_info['train_no']}"
    )


def print_train_stops(stops):
    print(f"Found {len(stops)} stops:")
    for stop in stops:
        print(
            f"{stop.get('station_no', '--'):>2} "
            f"{stop.get('station_name', ''):<10} "
            f"arrive {stop.get('arrive_time', '--:--'):>5} "
            f"depart {stop.get('start_time', '--:--'):>5} "
            f"stop {stop.get('stopover_time', '--')}"
        )


def main():
    if requests is None:
        print("Missing dependency: requests. Please run: pip install requests")
        return

    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Querying train {TRAIN_CODE}, date: {QUERY_DATE}\n")
    train_info = search_train(session, TRAIN_CODE, QUERY_DATE)
    if not train_info:
        return

    print_train_info(train_info)
    stops = query_train_stops(session, train_info, QUERY_DATE)
    if not stops:
        print("No stop data found.")
        return

    print_train_stops(stops)


if __name__ == "__main__":
    main()
