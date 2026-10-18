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

# Words/phrases that should never be posted (crypto spam, telegram invites, etc.)
BLOCK_KEYWORDS = [
    "t.me/",
    "telegram",
    "apt_loot",
    "apt_cult",
    "airdrop",
    "crypto bot",
    "join our channel",
    "any queries dm",
]


def normalize_url(url):
    """Strips tracking parameters so identical articles aren't reposted."""
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
    """Fallback: Scrapes the article page for OpenGraph images if RSS lacks them."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(article_url, headers=headers, timeout=5)
        if res.status_code == 200:
            og_match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']',
                res.text,
                re.IGNORECASE,
            )
            if og_match:
                return og_match.group(1)

            og_match_alt = re.search(
                r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']',
                res.text,
                re.IGNORECASE,
            )
            if og_match_alt:
                return og_match_alt.group(1)
    except Exception:
        pass
    return None


def extract_image_url(item_xml, article_url="", feed_name=""):
    if feed_name == "Guru3D":
        return None

    # 1. Standard <enclosure>
    enclosure = item_xml.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        url = enclosure.get("url")
        if re.search(r"\.(?:jpg|jpeg|png|webp|avif)", url, re.IGNORECASE):
            return url

    # 2. media:content / media:thumbnail
    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    media_node = item_xml.find("media:content", namespaces) or item_xml.find(
        "media:thumbnail", namespaces
    )
    if media_node is not None and media_node.get("url"):
        return media_node.get("url")

    # 3. Broad scan inside the item XML
    xml_str = ET.tostring(item_xml, encoding="utf-8").decode("utf-8")
    all_urls = re.findall(
        r'https?://[^\s"<>]+\.(?:jpg|jpeg|png|webp|avif)(?:\?[^\s"<>]*)?',
        xml_str,
        re.IGNORECASE,
    )
    for img in all_urls:
        if any(
            ignore in img.lower()
            for ignore in ["logo", "avatar", "icon", "banner", "placeholder", "pixel", "emoji", "gravatar", "button"]
        ):
            continue
        return img

    # 4. Webpage fallback
    if article_url:
        web_img = fetch_webpage_image(article_url)
        if web_img:
            return web_img

    return None


def load_posted_links():
    """Returns a list (keeps order) of previously posted normalized links."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return [normalize_url(line) for line in f if line.strip()]
    return []


def save_posted_links(posted_list):
    """Keeps only the most recent 500 links (order is preserved)."""
    with open(HISTORY_FILE, "w") as f:
        for link in posted_list[-2500:]:
            f.write(f"{link}\n")


def is_spam(title, description, link):
    """Returns True if the item looks like crypto/Telegram spam."""
    text = f"{title} {description} {link}".lower()
    return any(keyword in text for keyword in BLOCK_KEYWORDS)


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

        feed_content = response.content.lstrip()
        if feed_content.startswith(b"\xef\xbb\xbf"):
            feed_content = feed_content[3:]

        root = ET.fromstring(feed_content)
        items = root.findall(".//item")

        # Newest first → oldest. Post the first unposted non-spam item, then stop.
        for item in items[:50]:
            link_node = item.find("link")
            title_node = item.find("title")
            desc_node = item.find("description")

            raw_link = link_node.text.strip() if link_node is not None and link_node.text else ""
            link = normalize_url(raw_link)
            title = title_node.text.strip() if title_node is not None and title_node.text else ""
            raw_desc = desc_node.text if desc_node is not None else ""

            if not link or link in posted_set:
                continue

            clean_desc = clean_html(raw_desc)

            # Block crypto / Telegram spam
            if is_spam(title, clean_desc, raw_link):
                print(f"Blocked spam from {feed_name}: {title}")
                # Still mark it as seen so we don't keep checking it every run
                posted_list.append(link)
                posted_set.add(link)
                continue

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
                break  # only one post per feed
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
