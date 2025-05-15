import os
import requests
import json

def main():
    # 1. Get the latest patch version
    versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    versions = requests.get(versions_url).json()
    latest_version = versions[0]
    print(f"Using Data Dragon version: {latest_version}")

    # 2. Fetch profile icon data
    profile_icon_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/profileicon.json"
    profile_data = requests.get(profile_icon_url).json()["data"]

    # 3. Ensure output directory exists
    output_dir = "profile_icons"
    os.makedirs(output_dir, exist_ok=True)

    # 4. Download each profile icon
    total_icons = len(profile_data)
    print(f"Found {total_icons} profile icons to download")

    for icon_id, icon_info in profile_data.items():
        icon_filename = icon_info["image"]["full"]  # e.g. "profileicon1.png"
        download_url = (
            f"https://ddragon.leagueoflegends.com/cdn/"
            f"{latest_version}/img/profileicon/{icon_filename}"
        )
        filepath = os.path.join(output_dir, f"profileicon{icon_id}.png")

        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"Skipping profile icon {icon_id}, already downloaded.")
            continue

        # Fetch and save
        resp = requests.get(download_url, stream=True)
        if resp.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            print(f"Saved profile icon {icon_id} → {filepath}")
        else:
            print(f"Failed to download profile icon {icon_id}: HTTP {resp.status_code}")

    print("\nDownload complete!")
    print(f"Profile icons saved to: {os.path.abspath(output_dir)}")

if __name__ == "__main__":
    main()