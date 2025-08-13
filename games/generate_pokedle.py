#!/usr/bin/env python3
"""
Generate a JSON file of Pokémon data by scraping Bulbapedia.

Usage:
  python games/generate_pokedle.py --list-url <list_url> --out pokedex.json

This script scrapes the provided Bulbapedia list page for Pokémon links,
visits each Pokémon page, extracts fields from the infobox (height, weight,
catch rate, egg groups, abilities, national dex number, etc.) and emits a
JSON array of objects.

Notes:
- Bulbapedia blocks aggressive scraping. Use --limit and --delay to be polite.
- The parser uses heuristics and may not extract every field perfectly; you
  can extend the label mappings as needed.
"""
from __future__ import annotations

import argparse
import re
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag


USER_AGENT = "pokedle-scraper/1.0 (+https://example.com)"


def fetch(url: str, session: Optional[requests.Session] = None) -> str:
    s = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    resp = s.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def find_pokemon_links(list_html: str, base: str = "https://bulbapedia.bulbagarden.net") -> List[Dict[str, str]]:
    """Return list of {'name': name, 'url': full_url} preserving order.

    Uses heuristics: collects anchors under tables in page content that look
    like Pokémon article links (no namespace, short name).
    """
    soup = BeautifulSoup(list_html, "html.parser")
    content = soup.find(id="mw-content-text") or soup

    results: List[Dict[str, str]] = []
    seen = set()

    # Scan table rows that look like Pokédex entries: rows with a numeric index in a cell
    tables = content.find_all("table")
    for table in tables:
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            # check first few cells for a Pokédex number
            has_number = False
            for c in tds[:2]:
                txt = c.get_text(" ", strip=True)
                if re.search(r"#?\s*\d{1,4}", txt):
                    has_number = True
                    break
            if not has_number:
                continue

            # find the first candidate link in the row that looks like a Pokemon article
            a = None
            for cand in tr.find_all("a", href=True):
                href = cand["href"]
                if not href.startswith("/wiki/"):
                    continue
                if ":" in href:
                    continue
                name = cand.get_text(strip=True)
                if not name:
                    continue
                # require reasonable length
                if len(name) > 40:
                    continue
                a = cand
                break

            if not a:
                continue

            name = a.get_text(strip=True)
            # prefer the canonical Pokemon page name: remove parenthetical like (Pokémon)
            name_clean = re.sub(r"\s*\(.*\)", "", name).strip()
            key = name_clean.lower()
            if key in seen:
                continue
            seen.add(key)
            full = base + a["href"]
            results.append({"name": name_clean, "url": full})

    return results


def get_infobox_table(soup: BeautifulSoup) -> Optional[Tag]:
    # common Bulbapedia infobox tables use class 'roundy' or 'infobox'
    table = soup.find("table", class_=lambda c: c and ("roundy" in c or "infobox" in c))
    if table:
        return table
    # fallback: find the first table with many rows that contains 'Height' or 'Weight'
    tables = soup.find_all("table")
    for t in tables:
        text = t.get_text().lower()
        if "height" in text and "weight" in text:
            return t
    return None


def clean_text(node) -> str:
    if node is None:
        return ""
    text = "".join(node.strings)
    # remove bracketed footnotes like [1]
    text = re.sub(r"\[.*?\]", "", text)
    text = text.replace('\u2009', ' ')  # thin space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_infobox(table: Tag) -> Dict[str, object]:
    data: Dict[str, object] = {}
    meta_raw: Dict[str, str] = {}
    rows = table.find_all(["tr", "div"])  # some infoboxes use divs
    for r in rows:
        # th (label) and td (value) commonly used
        label_node = r.find(["th", "b"])
        value_node = r.find(["td", "div", "span"])
        if not label_node or not value_node:
            # sometimes label is a preceding small tag
            continue
        label = clean_text(label_node).lower()
        value = clean_text(value_node)
        # also keep the node for link-based extraction
        val_node = value_node
        if not label:
            continue

        # normalize label
        label_norm = label
        # mapping heuristics
        if "national" in label_norm and ("dex" in label_norm or "pokédex" in label_norm):
            # find first number in value
            m = re.search(r"#?\s*(\d{1,4})", value)
            if m:
                data["national_dex"] = int(m.group(1))
            else:
                # sometimes label contains the number e.g. #001
                m2 = re.search(r"#(\d{1,4})", label)
                if m2:
                    data["national_dex"] = int(m2.group(1))
            continue
        if "ndex" in label_norm or label_norm.strip().startswith("#"):
            m = re.search(r"#?\s*(\d{1,4})", value)
            if m:
                data["national_dex"] = int(m.group(1))
            continue

        if "height" in label_norm:
            # try to extract meters first
            m = re.search(r"(\d+(?:\.\d+)?)\s*m", value)
            if m:
                try:
                    data["height_m"] = float(m.group(1))
                except Exception:
                    data["height"] = value
            else:
                data["height"] = value
            continue
        if "weight" in label_norm:
            m = re.search(r"(\d+(?:\.\d+)?)\s*kg", value)
            if m:
                try:
                    data["weight_kg"] = float(m.group(1))
                except Exception:
                    data["weight"] = value
            else:
                data["weight"] = value
            continue
        if "catch rate" in label_norm or "catch" in label_norm:
            m = re.search(r"(\d{1,3})", value)
            if m:
                data["catch_rate"] = int(m.group(1))
            else:
                data.setdefault("catch_rate", value)
            continue
        if "egg group" in label_norm:
            # prefer link texts, but filter out stray label tokens
            links = [a.get_text(strip=True) for a in val_node.find_all("a")]
            if links:
                groups = [g.lower() for g in links if g and g.lower() not in ("egg group", "egg groups")]
            else:
                groups = re.split(r"[,/]| and ", value)
                groups = [g.strip().lower() for g in groups if g.strip() and g.strip().lower() not in ("egg group", "egg groups")]
            data["egg_groups"] = groups
            continue
        if "ability" in label_norm:
            # prefer link texts for abilities (includes hidden abilities)
            links = [a.get_text(strip=True) for a in val_node.find_all("a")]
            if links:
                parts = [p for p in links if p and p.lower() not in ("hidden ability", "ability")]
            else:
                parts = re.split(r"\s*[,/]\s*|\s+\/\s+", value)
                parts = [p.strip() for p in parts if p.strip() and p.lower() != "hidden ability"]
            # normalize duplicates and empty strings
            def clean_ability_name(s: str) -> str:
                s2 = s.strip()
                # remove common noise tokens
                s2 = re.sub(r"(?i)hidden ability", "", s2)
                s2 = re.sub(r"(?i)\bability\b", "", s2)
                s2 = s2.replace("Cacophony", "")
                s2 = s2.replace("Gigantamax", "")
                s2 = s2.replace("Mega", "")
                s2 = re.sub(r"\s+", " ", s2).strip()
                return s2

            parts = [clean_ability_name(p) for p in dict.fromkeys(parts) if p]
            parts = [p for p in parts if p and len(p) > 1]
            data.setdefault("abilities", parts)
            continue

        if "breed" in label_norm or "breeding" in label_norm:
            # extract hatch time in cycles if present
            m = re.search(r"Hatch time\s*(\d+)\s*cycles", value, flags=re.I)
            if m:
                try:
                    data["hatch_time_cycles"] = int(m.group(1))
                except Exception:
                    pass
            # egg groups likely parsed elsewhere; store raw under meta_raw_breeding if necessary
            meta_raw["breeding"] = value
            continue

        if "mega stone" in label_norm or "mega" in label_norm and "stone" in label_norm:
            # collect mega stones from links or split by comma
            links = [a.get_text(strip=True) for a in val_node.find_all("a")]
            if links:
                stones = [s for s in links if s and s.lower() not in ("mega stone", "]")]
            else:
                stones = [s.strip() for s in re.split(r"[,/]| and ", value) if s.strip()]
            # cleanup
            stones = [re.sub(r"\]", "", s) for s in stones]
            data["mega_stones"] = stones
            continue

        if "shape" in label_norm:
            data["shape"] = value.strip()
            continue

        if "pokedex color" in label_norm or "pokédex color" in label_norm or "pok_dex_color" in label_norm:
            data["pokedex_color"] = value.strip()
            continue

        if "external link" in label_norm or "external_links" in label_norm:
            # skip external links entirely
            continue

        # explicit types parsing: many infoboxes have a 'Type' label
        if "type" in label_norm:
            links = [a.get_text(strip=True) for a in val_node.find_all("a")]
            if links:
                types = [t for t in links if t and t.lower() != "type"]
            else:
                # fallback: remove leading 'Type' and split
                tval = re.sub(r"^Type\s*", "", value, flags=re.I)
                types = [s.strip() for s in re.split(r"[,/]", tval) if s.strip()]
            data["types"] = types
            continue
        if "gender" in label_norm:
            # look for percentages
            m_male = re.search(r"(\d+(?:\.\d+)?)%\s*male", value)
            m_female = re.search(r"(\d+(?:\.\d+)?)%\s*female", value)
            if m_male or m_female:
                male = float(m_male.group(1)) if m_male else None
                female = float(m_female.group(1)) if m_female else None
                data["gender_ratio"] = {"male_percent": male, "female_percent": female}
            else:
                data["gender_ratio"] = value
            continue
        if "base friendship" in label_norm or "friendship" in label_norm:
            m = re.search(r"(\d{1,3})", value)
            if m:
                data["base_friendship"] = int(m.group(1))
            else:
                data["base_friendship"] = value
            continue
        if "base exp" in label_norm or "base experience" in label_norm:
            m = re.search(r"(\d{1,4})", value)
            if m:
                data["base_experience"] = int(m.group(1))
            else:
                data["base_experience"] = value
            continue
        if "growth rate" in label_norm:
            data["growth_rate"] = value
            continue
        if "ev yield" in label_norm or "evs" in label_norm:
            # try to extract total
            m = re.search(r"Total:\s*(\d+)", value)
            if m:
                data["ev_yield_total"] = int(m.group(1))
            else:
                data["ev_yield"] = value
            continue

        # fallback: keep other labels prefixed with 'meta_'
        key = re.sub(r"[^a-z0-9_]+", "_", label.strip())
        key = key.strip("_")
        if key:
            meta_raw[key] = value

    if meta_raw:
        data["meta_raw"] = meta_raw
    return data


def scrape_pokemon(poke: Dict[str, str], session: Optional[requests.Session] = None) -> Dict[str, object]:
    name = poke["name"]
    url = poke["url"]
    print(f"Fetching {name} - {url}")
    html = fetch(url, session=session)
    soup = BeautifulSoup(html, "html.parser")
    table = get_infobox_table(soup)
    info = {"name": name, "url": url}
    if table is None:
        print(f"Warning: no infobox found for {name}")
        return info
    parsed = parse_infobox(table)
    info.update(parsed)
    # parse base stats from the page
    base_stats = parse_base_stats(soup)
    if base_stats:
        info["base_stats"] = base_stats
    return info


def parse_base_stats(soup: BeautifulSoup) -> Optional[Dict[str, int]]:
    """Attempt to find base stats table and return a dict with keys:
    hp, attack, defense, sp_attack, sp_defense, speed, total (when available).
    Uses regex heuristics against table text.
    """
    stat_names = {
        "hp": [r"HP"],
        "attack": [r"Attack", r"Atk"],
        "defense": [r"Defense", r"Def"],
        "sp_attack": [r"Sp\. ?Atk", r"Sp\. ?Att|SpAttack|Special Attack"],
        "sp_defense": [r"Sp\. ?Def", r"Sp\. ?Def|SpDefense|Special Defense"],
        "speed": [r"Speed"],
        "total": [r"Total"],
    }

    # First, try to locate the "Base stats" section header and its following table
    header = None
    # try id anchor first
    header = soup.find(id=re.compile(r"base[_ ]?stats", flags=re.I))
    if header:
        # header might be inside an element; find the parent header tag
        if header.name not in ("h1", "h2", "h3", "h4", "h5", "h6"):
            header = header.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"]) or header

    if not header:
        # find header element with text "Base stats"
        for htag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if "base stat" in htag.get_text(strip=True).lower() or "base stats" in htag.get_text(strip=True).lower():
                header = htag
                break

    tables_to_check = []
    if header:
        # look for next table sibling(s)
        sib = header.find_next_sibling()
        steps = 0
        while sib and steps < 10:
            if sib.name == "table":
                tables_to_check.append(sib)
            # sometimes tables are wrapped in divs
            if sib.find_all("table"):
                tables_to_check.extend(sib.find_all("table"))
            sib = sib.find_next_sibling()
            steps += 1

    # fallback: search all tables if none found near header
    if not tables_to_check:
        tables_to_check = soup.find_all("table")

    # helper to parse numeric from string
    def extract_int(s: str) -> Optional[int]:
        if not s:
            return None
        m = re.search(r"(\d{1,3})", s)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None

    for table in tables_to_check:
        # Try horizontal layout: header row with HP/Attack/... and a following numeric row
        headers = [clean_text(th).strip() for th in table.find_all("th")]
        header_tokens = [h.lower() for h in headers]
        if any(tok in " ".join(header_tokens) for tok in ("hp", "attack", "defense", "speed")):
            # find the first row that contains mostly digits
            for tr in table.find_all("tr"):
                tds = [clean_text(td).strip() for td in tr.find_all(["td", "th"])]
                if not tds:
                    continue
                num_vals = [extract_int(x) for x in tds]
                num_count = sum(1 for v in num_vals if v is not None)
                if num_count >= 4:
                    # align numeric cells to header positions if possible
                    stats: Dict[str, int] = {}
                    mapping = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed", "total"]
                    # If headers length matches numeric cells, map by index
                    if len(headers) == len([v for v in num_vals if v is not None]):
                        vals = [v for v in num_vals if v is not None]
                        for i, v in enumerate(vals):
                            if i < len(mapping) and v is not None:
                                stats[mapping[i]] = v
                    else:
                        # fallback: take first 6-7 numeric values
                        vals = [v for v in num_vals if v is not None]
                        for i, v in enumerate(vals[:7]):
                            if i < len(mapping):
                                stats[mapping[i]] = v
                    if stats:
                        return stats

        # Try vertical layout: rows where first cell is stat name and second cell is number
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 2:
                key_label = clean_text(tds[0]).strip().lower()
                if any(k in key_label for k in ("hp", "attack", "defense", "speed", "special", "total")):
                    # try to extract all stat rows in this table
                    stats: Dict[str, int] = {}
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all(["td", "th"])
                        if len(cols) < 2:
                            continue
                        k = clean_text(cols[0]).strip().lower()
                        v = extract_int(clean_text(cols[1]))
                        if v is None:
                            continue
                        if "hp" in k:
                            stats["hp"] = v
                        elif "attack" in k and "sp" not in k:
                            stats["attack"] = v
                        elif "defense" in k and "sp" not in k:
                            stats["defense"] = v
                        elif "sp" in k and ("attack" in k or "spatk" in k or "sp atk" in k):
                            stats["sp_attack"] = v
                        elif "sp" in k and ("defense" in k or "spdef" in k or "sp def" in k):
                            stats["sp_defense"] = v
                        elif "speed" in k:
                            stats["speed"] = v
                        elif "total" in k:
                            stats["total"] = v
                    if stats:
                        return stats

        # fallback: search table text for labels like 'HP 45'
        txt = table.get_text(" ", strip=True)
        if all(k in txt for k in ("HP", "Attack", "Defense", "Speed")):
            stats: Dict[str, int] = {}
            for key, patterns in stat_names.items():
                found = None
                for pat in patterns:
                    m = re.search(rf"{pat}[^0-9\n\r\-]?(?:[:]?\s*)(\d{{1,3}})", txt, flags=re.I)
                    if m:
                        try:
                            found = int(m.group(1))
                            break
                        except Exception:
                            continue
                if found is not None:
                    stats[key] = found
            if stats:
                return stats

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Bulbapedia to generate pokedle JSON")
    parser.add_argument("--list-url", default="https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_by_National_Pok%C3%A9dex_number")
    parser.add_argument("--out", default="pokedex.json")
    parser.add_argument("--limit", type=int, default=0, help="max number of Pokémon to process (0 = all)")
    # delay is hard-coded per user request
    DELAY = 0.5
    args = parser.parse_args()

    session = requests.Session()
    try:
        list_html = fetch(args.list_url, session=session)
    except Exception as e:
        print(f"Failed to fetch list page: {e}")
        sys.exit(1)

    links = find_pokemon_links(list_html)
    if args.limit and args.limit > 0:
        links = links[: args.limit]

    print(f"Found {len(links)} candidate links; scraping up to {len(links)} Pokémon")

    # Stream a valid JSON object to file. Keys will be zero-padded national dex
    # numbers when available (e.g. "0001"), otherwise the Pokémon name.
    # Parallelize scraping with a thread pool
    max_workers = 1
    def worker(poke_item: Dict[str, str]) -> Dict[str, object]:
        sess = requests.Session()
        try:
            d = scrape_pokemon(poke_item, session=sess)
        finally:
            sess.close()
        # polite per-thread delay
        time.sleep(DELAY)
        return d

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("{")
        first = True
        seen_keys = set()
        count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(worker, p): p for p in links}

            for fut in as_completed(futures):
                poke = futures[fut]
                try:
                    data = fut.result()
                except Exception as e:
                    print(f"Error scraping {poke['name']}: {e}")
                    continue

                data.setdefault("name", poke.get("name"))
                data.setdefault("url", poke.get("url"))

                nat = data.get("national_dex")
                if isinstance(nat, int):
                    key = f"{nat:04d}"
                else:
                    key = str(data.get("name") or poke["name"]).strip()

                orig_key = key
                i = 1
                while key in seen_keys:
                    i += 1
                    key = f"{orig_key}_{i}"
                seen_keys.add(key)

                value_json = json.dumps(data, ensure_ascii=False)

                if not first:
                    fh.write(",")
                fh.write("\n")
                fh.write(json.dumps(key, ensure_ascii=False))
                fh.write(": ")
                fh.write(value_json)
                fh.flush()

                first = False
                count += 1
                print(f"Wrote {data.get('name', poke['name'])} ({count}/{len(links)})")

        fh.write("\n}\n")
    print(f"Wrote {count} entries to {args.out}")


if __name__ == "__main__":
    main()


