import feedparser
import requests
import json
import os
import time
from fuzzywuzzy import fuzz
from datetime import datetime, timedelta, timezone

# ========== CẤU HÌNH ==========
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = 'YOUR_CHAT_ID'   # Sẽ tự động lấy ở lần chạy đầu, sau đó cập nhật lại
SENT_FILE = 'sent_articles.json'

# Danh sách RSS các báo Việt Nam
RSS_URLS = [
    'https://vnexpress.net/rss/tin-moi-nhat.rss',
    'https://tuoitre.vn/rss/tin-moi-nhat.rss',
    'https://thanhnien.vn/rss/home.rss',
    'https://zingnews.vn/rss/tin-moi-nhat.rss',
    'https://vietnamnet.vn/rss/tin-moi-nhat.rss'
]

# ========== CÁC HÀM XỬ LÝ ==========
def load_sent():
    """Tải danh sách bài đã gửi từ file JSON."""
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sent(data):
    """Lưu danh sách bài đã gửi vào file JSON."""
    with open(SENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def similar_title(new_title, old_titles, threshold=65):
    """Kiểm tra tiêu đề mới có trùng (tương tự) với tiêu đề cũ không."""
    for old in old_titles:
        if fuzz.ratio(new_title.lower(), old.lower()) >= threshold:
            return True
    return False

def format_article(entry, is_update=False):
    """Định dạng một bài báo thành tin nhắn Telegram theo phong cách '3 gạch đầu dòng'."""
    title = entry.get('title', 'Không có tiêu đề')
    desc = entry.get('description', '')

    # Tách các câu từ mô tả
    sentences = [s.strip() for s in desc.replace('\n', ' ').split('. ') if s.strip()]

    if len(sentences) >= 3:
        event, context, future = sentences[0], sentences[1], sentences[2]
    elif len(sentences) == 2:
        event, context, future = sentences[0], sentences[1], 'Đang cập nhật'
    elif len(sentences) == 1:
        event, context, future = sentences[0], 'Đang cập nhật', 'Đang cập nhật'
    else:
        event, context, future = title, 'Đang cập nhật', 'Đang cập nhật'

    header = f"🔄 CẬP NHẬT: {title}" if is_update else f"📌 {title}"
    return f"{header}\n• Sự kiện: {event}\n• Bối cảnh: {context}\n• Dự báo/Diễn biến: {future}"

def should_send_now():
    """Chỉ gửi tin nếu đang trong khung 8h-8h10 hoặc 14h-14h10 giờ Việt Nam."""
    utc_now = datetime.now(timezone.utc)
    vn_now = utc_now.astimezone(timezone(timedelta(hours=7)))
    current_hour = vn_now.hour
    current_minute = vn_now.minute

    # Cho phép sai số tối đa 10 phút để cron kịp chạy
    if current_hour == 8 and 0 <= current_minute <= 10:
        return True
    if current_hour == 14 and 0 <= current_minute <= 10:
        return True
    return False

def get_chat_id():
    """Lấy chat ID từ bot Telegram (dùng cho lần đầu)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url).json()
        if r['ok'] and r['result']:
            return r['result'][-1]['message']['chat']['id']
    except:
        pass
    return None

def send_telegram_message(text):
    """Gửi tin nhắn qua Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Lỗi gửi tin nhắn: {e}")

# ========== CHƯƠNG TRÌNH CHÍNH ==========
if __name__ == '__main__':
    print(f"Current UTC time: {datetime.now(timezone.utc).isoformat()}")

    # Nếu chưa có CHAT_ID, thử lấy tự động và yêu cầu cập nhật
    if CHAT_ID == 'YOUR_CHAT_ID':
        cid = get_chat_id()
        if cid:
            print(f"CHAT_ID của bạn là: {cid}. Hãy cập nhật vào biến CHAT_ID trong bot.py và chạy lại.")
        else:
            print("Hãy nhắn /start cho bot Telegram của bạn trước!")
        exit(0)

    # Kiểm tra khung giờ, nếu không đúng thì dừng
    if not should_send_now():
        print("Chưa đến giờ gửi tin (8h hoặc 14h VN), thoát.")
        exit(0)

    # Tải lịch sử bài đã gửi
    sent = load_sent()
    sent_urls = [item['url'] for item in sent]
    sent_titles = [item['title'] for item in sent]

    new_items = []
    # Lấy bài trong vòng 18 giờ qua
    time_limit = datetime.now(timezone.utc) - timedelta(hours=18)

    for rss_url in RSS_URLS:
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"Lỗi parse RSS {rss_url}: {e}")
            continue

        for entry in feed.entries:
            # Kiểm tra thời gian xuất bản nếu có
            published = entry.get('published_parsed')
            if published:
                pub_time = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_time < time_limit:
                    continue

            url = entry.get('link')
            title = entry.get('title', '')

            # Bỏ qua nếu URL đã gửi
            if url in sent_urls:
                continue

            # Phát hiện tin cập nhật dựa trên độ tương đồng tiêu đề
            is_update = similar_title(title, sent_titles)

            new_items.append({
                'title': title,
                'url': url,
                'entry': entry,
                'is_update': is_update
            })

    # Gửi tin hoặc thông báo không có tin mới
    if new_items:
        for item in new_items:
            msg = format_article(item['entry'], item['is_update'])
            send_telegram_message(msg)
            time.sleep(1)   # Tránh bị giới hạn tốc độ Telegram

        # Cập nhật và lưu danh sách đã gửi
        for item in new_items:
            sent.append({'title': item['title'], 'url': item['url']})
        save_sent(sent)
        print(f"Đã gửi {len(new_items)} tin tức mới.")
    else:
        send_telegram_message("📭 Hiện chưa có tin tức mới trong 18 giờ qua.")
        print("Không có tin mới để gửi.")
