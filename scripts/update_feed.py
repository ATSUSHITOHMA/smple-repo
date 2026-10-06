#!/usr/bin/env python3
"""新着フィードを取り直して index.html に埋め込む。

sources.json の各フィード（RSS 2.0 / Atom / RDF）から見出し・リンク・日付を取り、
index.html の <script id="feed-snapshot"> の中身を差し替える。
取得に失敗した媒体は、前回の内容をそのまま残す。標準ライブラリだけで動く。
"""
import datetime
import email.utils
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / 'index.html'
MAX_ITEMS = 5
# 省庁などの総合フィードは、美容医療に関係する見出しだけを残す（ページ側の絞り込みと同じ語）
RELEVANT = re.compile('美容|皮膚|レーザ|脱毛|医療広告|ボツリヌス|ヒアルロン|HIFU|ハイフ|未承認|個人輸入|化粧品|医薬部外品|痩身|エステ|再生医療|自由診療|注入|フィラー|ざ瘡|にきび|アートメイク|糸リフト|新医療機器', re.I)
UA = 'Mozilla/5.0 (compatible; biyou-matome-feed/1.0; +https://github.com/)'
MARK = re.compile(r'(<script type="application/json" id="feed-snapshot">)(.*?)(</script>)', re.S)


def local(tag):
    return tag.rsplit('}', 1)[-1].lower()


def text(node):
    return re.sub(r'\s+', ' ', ''.join(node.itertext())).strip() if node is not None else ''


def to_date(raw):
    raw = (raw or '').strip()
    if not raw:
        return ''
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', raw)
    if m:
        return m.group(0)
    try:
        return email.utils.parsedate_to_datetime(raw).date().isoformat()
    except Exception:
        return ''


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for node in root.iter():
        if local(node.tag) not in ('item', 'entry'):
            continue
        title = link = date = ''
        for ch in node:
            name = local(ch.tag)
            if name == 'title' and not title:
                title = text(ch)
            elif name == 'link':
                href = ch.attrib.get('href')
                rel = ch.attrib.get('rel', 'alternate')
                if href and rel == 'alternate' and not link:
                    link = href.strip()
                elif not href and not link:
                    link = text(ch)
            elif name in ('pubdate', 'published', 'updated', 'date') and not date:
                date = to_date(text(ch))
        if title and re.match(r'https?://', link):
            out.append({'t': title[:300], 'u': link, 'd': date})
    out.sort(key=lambda i: i['d'] or '0', reverse=True)
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'})
    with urllib.request.urlopen(req, timeout=25) as res:
        return res.read()


def main():
    html = PAGE.read_text(encoding='utf-8')
    m = MARK.search(html)
    if not m:
        sys.exit('feed-snapshot の場所が index.html に見つかりません')
    try:
        old = {d['id']: d for d in json.loads(m.group(2).replace('<\\/', '</')) or []}
    except Exception:
        old = {}
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()
    docs, ok, failed = [], 0, []
    for s in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8')):
        try:
            items = parse(fetch(s['feed']))
            if not items:
                raise ValueError('見出しが0件')
            if s.get('general'):
                items = [i for i in items if RELEVANT.search(i['t'])]
            items = items[:MAX_ITEMS]
            docs.append({'id': s['id'], 'name': s['name'], 'cat': s['cat'], 'lang': s['lang'], 'site': s['site'], 'fetched': today, 'items': items})
            ok += 1
        except Exception as e:  # 1媒体の失敗で全体を止めない
            failed.append('%s: %s' % (s['id'], str(e)[:80]))
            if s['id'] in old:
                docs.append(old[s['id']])
    print('取得できた媒体 %d、失敗 %d' % (ok, len(failed)))
    for f in failed:
        print('  -', f)
    if ok == 0:
        sys.exit('1媒体も取得できなかったため、index.html は書き換えません')
    payload = json.dumps(docs, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    PAGE.write_text(html[:m.start(2)] + payload + html[m.end(2):], encoding='utf-8')


if __name__ == '__main__':
    main()
