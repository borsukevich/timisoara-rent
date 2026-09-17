import html
import time
from typing import List
from curl_cffi import requests
from scrapers.base import Listing
from config import TELEGRAM_BOT_TOKEN
from translator import translate_to_russian
import database

class TelegramNotifier:
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def format_caption(self, listing: Listing) -> str:
        source_name = listing.source.upper()
        
        # Translate title to Russian
        title_ru = translate_to_russian(listing.title or "Квартира в Тимишоаре", max_chars=120)
        title_escaped = html.escape(title_ru)
        
        price_escaped = html.escape(listing.price or "Уточняйте")
        rooms_escaped = html.escape(listing.rooms or "3+ камеры")
        area_escaped = html.escape(listing.exact_area or "от 55 м²")
        floor_escaped = html.escape(listing.floor or "Не указан")
        district_escaped = html.escape(listing.district or "Тимишоара")
        address_escaped = html.escape(listing.full_address or "Тимишоара")
        complex_escaped = html.escape(listing.complex_name or "Не указан")
        parking_escaped = html.escape(listing.parking_info or "Не указано")
        ac_escaped = html.escape(listing.ac_info or "Не указан")
        balcony_escaped = html.escape(listing.balcony_info or "Не указан")
        deposit_escaped = html.escape(listing.deposit_info or "1 месяц (обычно)")
        commission_escaped = html.escape(listing.commission_info or "Уточнять")
        building_escaped = html.escape(listing.building_type or "Обычный фонд")
        map_escaped = html.escape(listing.map_link or "https://maps.google.com/?q=Timisoara")
        url_escaped = html.escape(listing.url)

        badges = []
        if listing.is_owner:
            badges.append("👤 <b>ОТ СОБСТВЕННИКА (Proprietar / 0% comision)</b>")
        if listing.has_boiler:
            badges.append("🔥 <b>Свой котёл (Centrală proprie / gaz)</b>")

        badge_block = ("\n" + "\n".join(badges)) if badges else ""

        phone_block = ""
        if listing.phone:
            phone_block = f"\n📞 <b>Телефон:</b> <code>{html.escape(listing.phone)}</code>"

        caption = (
            f"🏠 <b>[{source_name}]</b> <a href=\"{url_escaped}\">{title_escaped}</a>\n"
            f"💰 <b>Цена:</b> {price_escaped} | <b>Залог:</b> {deposit_escaped}\n"
            f"📐 <b>Квадратура:</b> {area_escaped} | <b>Комнат:</b> {rooms_escaped}\n"
            f"🏢 <b>Этаж:</b> {floor_escaped} | {building_escaped}\n"
            f"📍 <b>Район:</b> {district_escaped}\n"
            f"📮 <b>Адрес:</b> {address_escaped}\n"
            f"🏗️ <b>ЖК:</b> {complex_escaped}\n"
            f"🚗 <b>Паркинг:</b> {parking_escaped}\n"
            f"❄️ <b>Кондиционер:</b> {ac_escaped} | 🌿 <b>Балкон:</b> {balcony_escaped}\n"
            f"💼 <b>Комиссия:</b> {commission_escaped}\n"
            f"🗺️ <b>Метка на карте:</b> <a href=\"{map_escaped}\">Открыть в Google Maps</a>"
            f"{badge_block}"
            f"{phone_block}\n\n"
            f"🔗 <a href=\"{url_escaped}\">Перейти к оригиналу объявления</a>"
        )
        if len(caption) > 1020:
            caption = caption[:1015] + "..."
        return caption

    def send_listing(self, chat_id: int, listing: Listing) -> bool:
        caption = self.format_caption(listing)
        photos = [p for p in listing.photos if p and p.startswith("http")]
        sent_ok = False

        # 1. Send Photos (up to 10 in album)
        if len(photos) >= 2:
            media_photos = photos[:10]
            media = []
            for i, p_url in enumerate(media_photos):
                item = {"type": "photo", "media": p_url}
                if i == 0:
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media.append(item)

            try:
                r = requests.post(
                    f"{self.base_url}/sendMediaGroup",
                    json={"chat_id": chat_id, "media": media},
                    timeout=15
                )
                if r.status_code == 200:
                    sent_ok = True
            except Exception as e:
                print(f"[Telegram] sendMediaGroup exception: {e}")

        # 2. Single photo
        if not sent_ok and len(photos) >= 1:
            try:
                r = requests.post(
                    f"{self.base_url}/sendPhoto",
                    json={
                        "chat_id": chat_id,
                        "photo": photos[0],
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    timeout=15
                )
                if r.status_code == 200:
                    sent_ok = True
            except Exception as e:
                print(f"[Telegram] sendPhoto exception: {e}")

        # 3. Fallback text only
        if not sent_ok:
            try:
                r = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": caption,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False
                    },
                    timeout=10
                )
                if r.status_code == 200:
                    sent_ok = True
            except Exception as e:
                print(f"[Telegram] sendMessage failed: {e}")

        # 4. SEND FULL UNABRIDGED DESCRIPTION (Без сокращений!)
        if sent_ok and listing.description and len(listing.description.strip()) > 10:
            try:
                full_desc_ru = translate_to_russian(listing.description, max_chars=3500)
                if full_desc_ru:
                    # Escape html for telegram
                    desc_text = f"📝 <b>Полное описание:</b>\n\n<i>{html.escape(full_desc_ru)}</i>"
                    if len(desc_text) > 4000:
                        desc_text = desc_text[:3990] + "..."
                    
                    time.sleep(0.3)
                    self.send_text_message(chat_id, desc_text)
            except Exception as e:
                print(f"[Telegram] Error sending full description message: {e}")

        return sent_ok

    def broadcast_listing(self, listing: Listing) -> int:
        """Sends listing to all active subscribers."""
        subscribers = database.get_subscribers()
        if not subscribers:
            return 0

        success_count = 0
        for chat_id in subscribers:
            if self.send_listing(chat_id, listing):
                success_count += 1
            time.sleep(0.5)
        return success_count

    def send_text_message(self, chat_id: int, text: str) -> bool:
        try:
            r = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] send_text_message error: {e}")
            return False

    def poll_updates_once(self, offset: int = 0, on_start_command=None) -> int:
        """Polls Telegram for commands and registers new subscribers."""
        try:
            r = requests.get(f"{self.base_url}/getUpdates", params={"offset": offset, "timeout": 2}, timeout=5)
            if r.status_code != 200:
                return offset

            data = r.json()
            if not data.get("ok"):
                return offset

            for upd in data.get("result", []):
                update_id = upd.get("update_id", 0)
                offset = max(offset, update_id + 1)

                msg = upd.get("message", {})
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                username = chat.get("username", "")
                first_name = chat.get("first_name", "")
                text = (msg.get("text") or "").strip()

                if chat_id:
                    database.add_subscriber(chat_id, username, first_name)
                    if text.startswith("/start"):
                        print(f"[Telegram] /start received from: {chat_id} (@{username})")
                        if on_start_command:
                            on_start_command(chat_id)

            return offset
        except Exception as e:
            print(f"[Telegram] Error polling updates: {e}")
            return offset
