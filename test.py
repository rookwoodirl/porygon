import os
import requests

def main():
    # 1. Get the latest patch version
    versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    versions = requests.get(versions_url).json()
    latest_version = versions[0]
    print(f"Using Data Dragon version: {latest_version}")

    # 2. Fetch champion data for that version
    champ_data_url = (
        f"https://ddragon.leagueoflegends.com/cdn/"
        f"{latest_version}/data/en_US/champion.json"
    )
    champ_data = requests.get(champ_data_url).json()["data"]

    # 3. Ensure output directory exists
    output_dir = "icons"
    os.makedirs(output_dir, exist_ok=True)

    # 4. Download each champion’s icon
    for champ_key, champ_info in champ_data.items():
        icon_filename = champ_info["image"]["full"]  # e.g. "Ahri.png"
        download_url = (
            f"https://ddragon.leagueoflegends.com/cdn/"
            f"{latest_version}/img/champion/{icon_filename}"
        )
        filepath = os.path.join(output_dir, champ_key + ".png")

        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"Skipping {champ_key}, already downloaded.")
            continue

        # Fetch and save
        resp = requests.get(download_url, stream=True)
        if resp.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            print(f"Saved {champ_key} → {filepath}")
        else:
            print(f"Failed to download {champ_key}: HTTP {resp.status_code}")

if __name__ == "__main__":
    main()