import html
import json
import os
import re
import xml.etree.ElementTree as ET
import requests

# Automatically pulls your secret safely from GitHub Actions environment
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 16 Feeds total: Gaming + Tech
FEEDS = {
    # --- GAMING FEEDS ---
    "IGN": "https://feeds.feedburner.com/ign/all",
    "GameSpot": "https://www.gamespot.com/feeds/mashup/",
    "PC Gamer": "https://www.pcgamer.com/rss/",
    "VGC": "https://www.videogameschronicle.com/feed/",
    "Insider Gaming": "https://insider-gaming.com/feed/",
    "Rock Paper Shotgun": "https://www.rockpapershotgun.com/feed",
    "Eurogamer": "https://www.eurogamer.net/feed/news",
    "Gematsu": "https://www.gematsu.com/feed",
    "Dexerto": "https://www.dexerto.com/feed/",
    
    # --- TECH FEEDS ---
    "Tom's Hardware": "https://www.tomshardware.com/feeds/all",
    "TechPowerUp": "https://www.techpowerup.com/rss/news",
    "Wccftech": "https://wccftech.com/feed/",
    "KitGuru": "https://www.kitguru.net/feed/",
    "TechRadar": "https://www.techradar.com/rss",
    "Overclock3D": "https://overclock3d.net/feed/",
    "Guru3D": "https://www.guru3d.com/rss.xml",
}

HISTORY_FILE = "posted_links.txt"


def normalize_url(url):
    """Strips tracking parameters (like utm_source, ref, etc.) so identical articles aren't reposted."""
    if not url:
        return ""
    base_url = url.split("?")[0]
    return base_url.strip().rstrip("/")


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def fetch_webpage_image(article_url):
    """Fallback: Scrapes the article page for OpenGraph or featured images if RSS lacks them."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(article_url, headers=headers, timeout=5)
        if res.status_code == 200:
            og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', res.text, re.IGNORECASE)
            if og_match:
                return og_match.group(1)
            
            og_match_alt = re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', res.text, re.IGNORECASE)
            if og_match_alt:
                return og_match_alt.group(1)
    except Exception:
        pass
    return None


def extract_image_url(item_xml, article_url="", feed_name=""):
    if feed_name == "Guru3D":
        return None

    enclosure = item_xml.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        url = enclosure.get("url")
        if re.search(r"\.(?:jpg|jpeg|png|webp|avif)", url, re.IGNORECASE):
            return url

    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    media_node = item_xml.find("media:content", namespaces) or item_xml.find(
        "media:thumbnail", namespaces
    )
    if media_node is not None and media_node.get("url"):
        return media_node.get("url")

    xml_str = ET.tostring(item_xml, encoding="utf-8").decode("utf-8")
    all_urls = re.findall(r'https?://[^\s"<>]+\.(?:jpg|jpeg|png|webp|avif)(?:\?[^\s"<>]*)?', xml_str, re.IGNORECASE)
    for img in all_urls:
        if any(ignore in img.lower() for ignore in ["logo", "avatar", "icon", "banner", "placeholder", "pixel", "emoji", "gravatar", "button"]):
            continue
        return img

    if article_url:
        web_img = fetch_webpage_image(article_url)
        if web_img:
            return web_img

    return None


def load_posted_links():
    """Loads history into an ordered list, keeping insertion order deterministic."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return [normalize_url(line) for line in f if line.strip()]
    return []


def save_posted_links(posted_list):
    """Trims history deterministically to the last 500 links preserving order."""
    links_to_save = posted_list[-500:]
    with open(HISTORY_FILE, "w") as f:
        for link in links_to_save:
            f.write(f"{link}\n")


def process_feed(feed_name, feed_url, posted_list, posted_set):
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL secret is missing!")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch {feed_name}: Status {response.status_code}")
            return

        feed_content = response.text.strip()
        root = ET.fromstring(feed_content)
        items = root.findall(".//item")

        # Correct iteration order: Newest first (no reversed())
        for item in items[:15]:
            link_node = item.find("link")
            title_node = item.find("title")
            desc_node = item.find("description")

            raw_link = link_node.text.strip() if link_node is not None else ""
            link = normalize_url(raw_link)
            title = title_node.text.strip() if title_node is not None else ""
            raw_desc = desc_node.text if desc_node is not None else ""

            if not link or link in posted_set:
                continue

            clean_desc = clean_html(raw_desc)
            if len(clean_desc) > 250:
                clean_desc = clean_desc[:250] + "..."

            image_url = extract_image_url(item, raw_link, feed_name)

            embed = {
                "title": title,
                "url": raw_link,
                "description": clean_desc,
                "color": 14431526,
                "footer": {"text": feed_name},
            }

            if image_url:
                embed["image"] = {"url": image_url}

            payload = {"embeds": [embed]}

            res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if res.status_code in [200, 204]:
                print(f"Successfully posted: [{feed_name}] {title}")
                posted_list.append(link)
                posted_set.add(link)
                break  # Only one post per feed per run
            else:
                print(f"Failed to post to Discord: {res.status_code} {res.text}")
                break

    except Exception as e:
        print(f"Error processing {feed_name}: {e}")


def main():
    posted_list = load_posted_links()
    posted_set = set(posted_list)

    for name, url in FEEDS.items():
        process_feed(name, url, posted_list, posted_set)
        
    save_posted_links(posted_list)


if __name__ == "__main__":
    main()
