import os
import shutil
from dotenv import load_dotenv
import csv
import yaml
import asyncio
from date_utils import parse_date
from download_api import download_vessel_track_data
from download_api import fetch_vessel_track
from path_utils import get_output_dir_path, final_result_dir_path


def combine_result_files(mmsi: str, temp_dir: str, results_dir: str) -> None:
    """
    Combines all result files into a single file.
    """

    output_dir = get_output_dir_path(
        mmsi=mmsi,
        temp_dir=temp_dir,
    )

    if not os.path.exists(output_dir):
        print(f"Output directory does not exist: {output_dir}")

        return

    print(f"Combine all chunk files in {output_dir}:")
    final_result_dir = final_result_dir_path(
        mmsi=mmsi,
        results_dir=results_dir,
    )

    if os.path.exists(final_result_dir):
        shutil.rmtree(final_result_dir)

    os.makedirs(final_result_dir, exist_ok=True)

    combined_file_path = f"{final_result_dir}/vessel_track_{mmsi}_combined.csv"

    csv_files = [f for f in os.listdir(output_dir) if f.endswith(".csv")]
    csv_files.sort()  # Sort to maintain chronological order

    header_saved = False
    with open(combined_file_path, "w", newline="", encoding="utf-8") as outfile:
        writer = None
        for filename in csv_files:
            file_path = os.path.join(output_dir, filename)
            print(f"Processing chunk: {filename}")

            with open(file_path, "r", newline="", encoding="utf-8") as infile:
                reader = csv.reader(infile)
                try:
                    header = next(reader)
                    if not header_saved:
                        writer = csv.writer(outfile)
                        writer.writerow(header)
                        header_saved = True

                    for row in reader:
                        writer.writerow(row)
                except StopIteration:
                    print(f"Warning: {filename} is empty.")
                    continue

    print(f"Successfully combined all files into: {combined_file_path}")


async def main():
    load_dotenv()

    # Load configuration from YAML
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found.")
        return

    # Configuration
    API_KEY = os.getenv("MARINE_TRAFFIC_API_KEY")
    MMSI = config.get("mmsi")
    FROM_DATE = config.get("from_date")
    TO_DATE = config.get("to_date")
    TEMP_DIR = config.get("temp_dir")
    RESULTS_DIR = config.get("results_dir")

    if not all([API_KEY, MMSI, FROM_DATE, TO_DATE]):
        print(
            "Error: Missing required configuration (API_KEY, MMSI, FROM_DATE, or TO_DATE)."
        )
        return

    start_date = parse_date(FROM_DATE)
    end_date = parse_date(TO_DATE)

    res = await download_vessel_track_data(
        api_key=API_KEY,
        mmsi=MMSI,
        start_date=start_date,
        end_date=end_date,
        temp_dir=TEMP_DIR,
    )

    if not res:
        return

    combine_result_files(
        mmsi=MMSI,
        temp_dir=TEMP_DIR,
        results_dir=RESULTS_DIR,
    )


if __name__ == "__main__":
    asyncio.run(main())
