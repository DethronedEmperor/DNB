import html
import json
import os
import re
import xml.etree.ElementTree as ET
import requests

# 1. YOUR DISCORD WEBHOOK URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1560666893554163814/Bp7mOgf8T_uDwrcaBVfRIuVGsVkB9rpePVmRn3zsJu8X0ge01z5ex-4kCQNoFUYPOWvp"

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
    # 1. Check <enclosure url="..."> tags (Standard RSS thumbnail tag)
    enclosure = item_xml.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        url = enclosure.get("url")
        if re.search(r"\.(?:jpg|jpeg|png|webp)", url, re.IGNORECASE):
            return url

    # 2. Check <media:content url="..."> or <media:thumbnail url="..."> tags
    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    media_node = item_xml.find("media:content", namespaces) or item_xml.find(
        "media:thumbnail", namespaces
    )
    if media_node is not None and media_node.get("url"):
        return media_node.get("url")

    # 3. Fallback: Scan full XML string, skipping known site banners/logos
    xml_str = ET.tostring(item_xml, encoding="utf-8").decode("utf-8")
    img_matches = re.findall(
        r'https?://[^\s"<>]+\.(?:jpg|jpeg|png|webp)', xml_str, re.IGNORECASE
    )

    for img in img_matches:
        # Ignore site logos, avatar icons, or standard fallback assets
        if any(
            ignore in img.lower()
            for ignore in ["logo", "avatar", "icon", "banner", "placeholder"]
        ):
            continue
        return img

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
