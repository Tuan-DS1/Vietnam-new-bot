import feedparser, requests, json, os, time
from fuzzywuzzy import fuzz
from datetime import datetime, timedelta
print(f"Current UTC time: {datetime.utcnow().isoformat()}")
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = '7463208687'  # Sẽ lấy tự động sau bước dưới
SENT_FILE = 'sent_articles.json'

# RSS feeds
RSS_URLS = [
    'https://vnexpress.net/rss/tin-moi-nhat.rss',
    'https://tuoitre.vn/rss/tin-moi-nhat.rss',
    'https://thanhnien.vn/rss/home.rss',
    'https://zingnews.vn/rss/tin-moi-nhat.rss',
    'https://vietnamnet.vn/rss/tin-moi-nhat.rss'
]

def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sent(data):
    with open(SENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def similar_title(new_title, old_titles, threshold=70):
    for old in old_titles:
        if fuzz.ratio(new_title.lower(), old.lower()) >= threshold:
            return True
    return False

def format_article(entry, is_update=False):
    title = entry.get('title', 'Không có tiêu đề')
    desc = entry.get('description', '')
    # Tách câu từ description
    sentences = [s.strip() for s in desc.replace('\n', ' ').split('. ') if s.strip()]
    if len(sentences) >= 3:
        event, context, future = sentences[0], sentences[1], sentences[2]
    elif len(sentences) == 2:
        event, context, future = sentences[0], sentences[1], 'Đang cập nhật'
    elif len(sentences) == 1:
        event, context, future = sentences[0], 'Đang cập nhật', 'Đang cập nhật'
    else:
        event, context, future = title, 'Đang cập nhật', 'Đang cập nhật'

    if is_update:
        header = f"🔄 CẬP NHẬT: {title}"
    else:
        header = f"📌 {title}"
    
    return f"{header}\n• Sự kiện: {event}\n• Bối cảnh: {context}\n• Dự báo/Diễn biến: {future}"

def get_chat_id():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    r = requests.get(url).json()
    if r['ok'] and r['result']:
        return r['result'][-1]['message']['chat']['id']
    return None

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    requests.post(url, data=payload)

# === MAIN ===
if __name__ == '__main__':
    # Tự động lấy chat_id nếu chưa có (chạy thủ công lần đầu)
    if CHAT_ID == 'YOUR_CHAT_ID':
        cid = get_chat_id()
        if cid:
            print(f"CHAT_ID của bạn là: {cid}. Hãy cập nhật vào biến CHAT_ID trong bot.py và chạy lại.")
        else:
            print("Hãy nhắn /start cho bot trước!")
        exit(0)

    sent = load_sent()
    sent_urls = [item['url'] for item in sent]
    sent_titles = [item['title'] for item in sent]

    new_items = []
    # Thời gian 12 giờ gần nhất để lấy tin mới
    time_limit = datetime.utcnow() - timedelta(hours=12)

    for rss_url in RSS_URLS:
        try:
            feed = feedparser.parse(rss_url)
        except:
            continue
        for entry in feed.entries:
            # Chỉ lấy bài trong 12h qua (nếu có published)
            published = entry.get('published_parsed')
            if published:
                pub_time = datetime.fromtimestamp(time.mktime(published))
                if pub_time < time_limit:
                    continue
            url = entry.get('link')
            title = entry.get('title', '')
            if url in sent_urls:
                continue
            # Kiểm tra cập nhật
            is_update = similar_title(title, sent_titles, threshold=65)  # 65% tương đồng
            new_items.append({
                'title': title,
                'url': url,
                'entry': entry,
                'is_update': is_update
            })

    if new_items:
        for item in new_items:
            msg = format_article(item['entry'], item['is_update'])
            send_telegram_message(msg)
            time.sleep(1)  # tránh rate limit

        # Lưu lại đã gửi
        for item in new_items:
            sent.append({'title': item['title'], 'url': item['url']})
        save_sent(sent)
    else:
        send_telegram_message("📭 Hiện chưa có tin tức mới trong 12 giờ qua.")
