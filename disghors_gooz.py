import html
import json
import os
import re
import xml.etree.ElementTree as ET
import requests

# 1. YOUR DISCORD WEBHOOK URL (Replace this with your real Discord Webhook URL)
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"

# 2. RSS FEEDS TO MONITOR
FEEDS = {
    "VGC": "https://www.videogameschronicle.com/feed/",
    "PC Gamer": "https://www.pcgamer.com/rss/",
    "GameSpot": "https://www.gamespot.com/feeds/mashup/",
    "IGN": "https://feeds.feedburner.com/ign/all",
}

HISTORY_FILE = "posted_links.txt"


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def extract_image_url(item_xml):
    xml_str = ET.tostring(item_xml, encoding="utf-8").decode("utf-8")
    img_match = re.search(
        r'https?://[^\s"<>]+\.(?:jpg|jpeg|png|webp)', xml_str, re.IGNORECASE
    )
    if img_match:
        return img_match.group(0)
    return None


def load_posted_links():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_posted_links(posted_links):
    with open(HISTORY_FILE, "w") as f:
        for link in posted_links:
            f.write(f"{link}\n")


def process_feed(feed_name, feed_url, posted_links):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch {feed_name}: Status {response.status_code}")
            return

        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        for item in reversed(items[:3]):
            link_node = item.find("link")
            title_node = item.find("title")
            desc_node = item.find("description")

            link = link_node.text.strip() if link_node is not None else ""
            title = title_node.text.strip() if title_node is not None else ""
            raw_desc = desc_node.text if desc_node is not None else ""

            if not link or link in posted_links:
                continue

            clean_desc = clean_html(raw_desc)
            if len(clean_desc) > 250:
                clean_desc = clean_desc[:250] + "..."

            image_url = extract_image_url(item)

            embed = {
                "title": title,
                "url": link,
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
                posted_links.add(link)
            else:
                print(f"Failed to post to Discord: {res.status_code} {res.text}")

    except Exception as e:
        print(f"Error processing {feed_name}: {e}")


def main():
    posted_links = load_posted_links()
    for name, url in FEEDS.items():
        process_feed(name, url, posted_links)
    save_posted_links(posted_links)


if __name__ == "__main__":
    main()
