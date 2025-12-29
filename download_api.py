import os
import shutil
import httpx
import asyncio
from datetime import date
from datetime import timedelta
from date_utils import validate_dates
from path_utils import get_output_dir_path, final_result_dir_path


async def fetch_vessel_track(
    api_key: str,
    mmsi: str,
    from_date: date,
    to_date: date,
    protocol: str = "csv",
    version: int = 3,
    *,
    output_dir: str,
) -> None:
    """
    Fetches vessel track data from MarineTraffic API and saves it to a file.

    Args:
        api_key: The MarineTraffic API key
        mmsi: Maritime Mobile Service Identity number
        from_date: Start date (YYYY-MM-DD or date object)
        to_date: End date (YYYY-MM-DD or date object)
        protocol: Output format (default: csv)
        version: API version (default: 3)
    """
    base_url = f"https://services.marinetraffic.com/api/exportvesseltrack/{api_key}"

    params = {
        "v": version,
        "fromdate": str(from_date),
        "todate": str(to_date),
        "MMSI": mmsi,
        "protocol": protocol,
    }

    print(f"Fetching data for MMSI: {mmsi}...")
    print(f"Fetching chunk: {from_date} to {to_date}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()

            # Generate filename based on parameters
            filename = f"vessel_track_{mmsi}_{from_date}_{to_date}.{protocol}"

            with open(f"{output_dir}/{filename}", "wb") as f:
                f.write(response.content)

            print(f"Successfully downloaded: {filename}")

            return True

    except httpx.HTTPStatusError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.text}")

        return False
    except Exception as e:
        print(f"An error occurred: {e}")

        return False


async def download_vessel_track_data(
    api_key: str, mmsi: str, start_date: date, end_date: date, temp_dir: str
) -> None:
    """
    Validates dates and downloads vessel track data, splitting into chunks if necessary.
    """

    res = validate_dates(start_date, end_date)
    if not (isinstance(res, tuple) and res[0] == "正確"):
        print(f"Error: {res}")
        return

    days = res[1]

    print(f"Correct, total days: {days}")

    output_dir = get_output_dir_path(
        mmsi=mmsi,
        temp_dir=temp_dir,
    )

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    if days <= 180:
        res = await fetch_vessel_track(
            api_key=api_key,
            mmsi=mmsi,
            from_date=start_date,
            to_date=end_date,
            output_dir=output_dir,
        )

        if not res:
            print("Failed to download vessel track data")
            return False

        return True

    else:
        print(f"Interval is {days} days (> 180), splitting requests...")

        current_start = start_date
        while current_start < end_date:
            current_end = current_start + timedelta(days=180)
            if current_end > end_date:
                current_end = end_date

            res = await fetch_vessel_track(
                api_key=api_key,
                mmsi=mmsi,
                from_date=current_start,
                to_date=current_end,
                output_dir=output_dir,
            )

            if not res:
                print("Failed to download vessel track data")
                return False

            current_start = current_end + timedelta(days=1)

            # If we haven't reached the end, sleep
            if current_start < end_date:
                print("Sleeping for 60 seconds between chunks...")
                await asyncio.sleep(60)

        return True
