import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta
import hashlib
import os
import re

BASE_URL = "https://ipu-japan.ac.jp"
LIST_URL = "https://ipu-japan.ac.jp/athletic/club/rugby/news/"
OUTPUT_FILE = "ipu_rugby.xml"

JST = timezone(timedelta(hours=9))

headers = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# ページ取得
# --------------------------------------------------

def get_page(url):
    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        r.raise_for_status()
        return r

    except requests.RequestException as e:
        print("取得失敗:", url)
        print("理由:", e)
        return None


# --------------------------------------------------
# 既存RSSを読み込む
# --------------------------------------------------

old_items = {}

if os.path.exists(OUTPUT_FILE):
    try:
        old_tree = ElementTree()
        old_tree.parse(OUTPUT_FILE)
        old_root = old_tree.getroot()

        for item in old_root.findall("./channel/item"):
            link = item.findtext("link", "").strip()
            title = item.findtext("title", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            if link:
                old_items[link] = {
                    "title": title,
                    "pubDate": pub_date
                }

    except Exception as e:
        print("既存XML読み込みエラー:", e)

print("既存RSS件数:", len(old_items))


# --------------------------------------------------
# ニュース一覧ページを取得
# --------------------------------------------------

r = get_page(LIST_URL)

if r is None:
    print()
    print("ニュース一覧を取得できなかったため、今回は更新しません。")
    print("既存RSSをそのまま維持します。")
    raise SystemExit(0)

print("一覧 HTTP:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")

current_items = []
seen_urls = set()


# --------------------------------------------------
# 個別記事を抽出
# --------------------------------------------------

for a in soup.find_all("a", href=True):

    link = urljoin(BASE_URL, a["href"])

    # /athletic/club/rugby/news/数字/ のみ対象
    if not re.fullmatch(
        r"https://ipu-japan\.ac\.jp/athletic/club/rugby/news/\d+/",
        link
    ):
        continue

    if link in seen_urls:
        continue

    text = " ".join(a.stripped_strings).strip()

    # 末尾の掲載日を取得
    date_match = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*$",
        text
    )

    if not date_match:
        print("掲載日取得失敗:", link)
        continue

    year = int(date_match.group(1))
    month = int(date_match.group(2))
    day = int(date_match.group(3))

    published = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )

    # --------------------------------------------------
    # タイトル取得
    #
    # カード内には
    # タイトル → 本文抜粋 → 掲載日
    # が入っている。
    #
    # HTML内の見出しタグを優先してタイトルを取得する。
    # --------------------------------------------------

    title = ""

    heading = a.find(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    )

    if heading:
        title = " ".join(
            heading.stripped_strings
        ).strip()

    # 見出しタグが取れない場合の予備
    if not title:

        # 日付部分を削除
        without_date = re.sub(
            r"\s*20\d{2}年\d{1,2}月\d{1,2}日\s*$",
            "",
            text
        ).strip()

        # 最初の改行・構造を利用できない場合は
        # strong等も確認
        strong = a.find(["strong", "b"])

        if strong:
            title = " ".join(
                strong.stripped_strings
            ).strip()

        else:
            title = without_date

    if not title:
        print("タイトル取得失敗:", link)
        continue

    seen_urls.add(link)

    current_items.append({
        "title": title,
        "link": link,
        "pubDate": format_datetime(published)
    })


print("一覧から取得:", len(current_items), "件")


# --------------------------------------------------
# 安全確認
# --------------------------------------------------

if len(current_items) == 0:
    print()
    print("記事を1件も取得できませんでした。")
    print("サイト構造変更の可能性があるため、今回は更新しません。")
    print("既存RSSをそのまま維持します。")
    raise SystemExit(0)


# --------------------------------------------------
# 現在の記事＋過去RSSを統合
#
# 一覧から古い記事が消えてもRSSには残す
# --------------------------------------------------

all_items = {}

for link, data in old_items.items():

    all_items[link] = {
        "title": data["title"],
        "link": link,
        "pubDate": data["pubDate"]
    }


# 現在取得した情報を優先
for data in current_items:

    all_items[data["link"]] = data


# --------------------------------------------------
# pubDateをdatetimeへ変換
# --------------------------------------------------

def parse_pubdate(value):
    try:
        return datetime.strptime(
            value,
            "%a, %d %b %Y %H:%M:%S %z"
        )

    except Exception:
        return datetime(
            1970,
            1,
            1,
            tzinfo=timezone.utc
        )


# --------------------------------------------------
# 新しい記事順に並べる
# 同日なら記事番号が大きいものを上にする
# --------------------------------------------------

rss_items = list(all_items.values())

rss_items.sort(
    key=lambda x: (
        parse_pubdate(x["pubDate"]),
        int(
            re.search(
                r"/news/(\d+)/",
                x["link"]
            ).group(1)
        )
    ),
    reverse=True
)


# --------------------------------------------------
# 取得結果表示
# --------------------------------------------------

for i, data in enumerate(rss_items, 1):

    date = parse_pubdate(
        data["pubDate"]
    ).astimezone(JST)

    status = (
        "OLD"
        if data["link"] in old_items
        else "NEW"
    )

    print(
        f"[{i}] {status} "
        f"{date.strftime('%Y/%m/%d')} "
        f"{data['title']}"
    )


# --------------------------------------------------
# RSS作成
# --------------------------------------------------

rss = Element(
    "rss",
    version="2.0"
)

channel = SubElement(
    rss,
    "channel"
)

SubElement(
    channel,
    "title"
).text = "IPU・環太平洋大学 ラグビー部 お知らせ"

SubElement(
    channel,
    "link"
).text = LIST_URL

SubElement(
    channel,
    "description"
).text = "IPU・環太平洋大学ラグビー部のお知らせ"

SubElement(
    channel,
    "language"
).text = "ja"


# --------------------------------------------------
# RSS item作成
# --------------------------------------------------

for data in rss_items:

    item = SubElement(
        channel,
        "item"
    )

    SubElement(
        item,
        "title"
    ).text = data["title"]

    SubElement(
        item,
        "link"
    ).text = data["link"]

    guid = SubElement(
        item,
        "guid",
        isPermaLink="false"
    )

    guid.text = hashlib.sha256(
        data["link"].encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "pubDate"
    ).text = data["pubDate"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ElementTree(rss)

tree.write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True
)

print()
print("RSS総件数:", len(rss_items))
print("保存:", OUTPUT_FILE)
print("RSS更新完了")