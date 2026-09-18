import html
import time
from typing import List
from curl_cffi import requests
from scrapers.base import Listing
from config import TELEGRAM_BOT_TOKEN
from translator import translate_to_russian
import database

class TelegramNotifier:
    REPLY_KEYBOARD = {
        "keyboard": [
            [{"text": "⭐ Избранные квартиры"}, {"text": "📊 Статистика"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

    def __init__(self, token: str = TELEGRAM_BOT_TOKEN):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.setup_bot_commands()

    def setup_bot_commands(self):
        try:
            commands = [
                {"command": "favorites", "description": "⭐ Избранные квартиры"},
                {"command": "stats", "description": "📊 Статистика базы"},
                {"command": "start", "description": "🚀 Перезапуск / Статус"}
            ]
            requests.post(f"{self.base_url}/setMyCommands", json={"commands": commands}, timeout=5)
        except Exception:
            pass

    def get_fav_markup(self, chat_id: int, uid: str, url: str) -> dict:
        is_fav = database.is_favorite(chat_id, uid)
        fav_text = "✅ В избранном" if is_fav else "⭐ В избранное"
        buttons = [
            {"text": fav_text, "callback_data": f"fav:{uid}"}
        ]
        if url and url.startswith("http"):
            buttons.append({"text": "🔗 На сайт", "url": url})
        return {
            "inline_keyboard": [buttons]
        }

    def format_caption(self, listing: Listing) -> str:
        source_name = listing.source.upper()
        
        # Translate title to Russian
        title_ru = translate_to_russian(listing.title or "Квартира в Тимишоаре", max_chars=120)
        title_escaped = html.escape(title_ru)
        
        price_escaped = html.escape(listing.price or "Уточняйте").replace("&lt;s&gt;", "<s>").replace("&lt;/s&gt;", "</s>")
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

        pets_escaped = html.escape(listing.pets_policy or "Не указано")
        smoking_escaped = html.escape(listing.smoking_policy or "")
        avail_escaped = html.escape(listing.availability or "")

        extra_lines = []
        pet_smoke = []
        if pets_escaped != "Не указано":
            pet_smoke.append(f"🐾 <b>Животные:</b> {pets_escaped}")
        if smoking_escaped:
            pet_smoke.append(f"🚭 <b>Курение:</b> {smoking_escaped}")
        if pet_smoke:
            extra_lines.append(" | ".join(pet_smoke))

        if avail_escaped:
            extra_lines.append(f"📅 <b>Заселение:</b> {avail_escaped}")

        extra_block = ("\n" + "\n".join(extra_lines)) if extra_lines else ""

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
            f"❄️ <b>Кондиционер:</b> {ac_escaped} | 🌿 <b>Балкон:</b> {balcony_escaped}"
            f"{extra_block}\n"
            f"💼 <b>Комиссия:</b> {commission_escaped}\n"
            f"🗺️ <b>Метка на карте:</b> <a href=\"{map_escaped}\">Google Maps</a>"
            f"{badge_block}"
            f"{phone_block}\n\n"
            f"🔗 <a href=\"{url_escaped}\">Оригинал на {source_name}</a>"
        )
        if len(caption) > 1020:
            # Drop bottom link to stay strictly within 1024 chars without breaking HTML tags
            caption = (
                f"🏠 <b>[{source_name}]</b> <a href=\"{url_escaped}\">{title_escaped}</a>\n"
                f"💰 <b>Цена:</b> {price_escaped} | <b>Залог:</b> {deposit_escaped}\n"
                f"📐 <b>Квадратура:</b> {area_escaped} | <b>Комнат:</b> {rooms_escaped}\n"
                f"🏢 <b>Этаж:</b> {floor_escaped} | {building_escaped}\n"
                f"📍 <b>Район:</b> {district_escaped}\n"
                f"📮 <b>Адрес:</b> {address_escaped}\n"
                f"🏗️ <b>ЖК:</b> {complex_escaped}\n"
                f"🚗 <b>Паркинг:</b> {parking_escaped}\n"
                f"❄️ <b>Кондиционер:</b> {ac_escaped} | 🌿 <b>Балкон:</b> {balcony_escaped}"
                f"{extra_block}\n"
                f"💼 <b>Комиссия:</b> {commission_escaped}\n"
                f"🗺️ <b>Метка на карте:</b> <a href=\"{map_escaped}\">Google Maps</a>"
                f"{badge_block}"
                f"{phone_block}"
            )
        return caption

    def send_listing(self, chat_id: int, listing: Listing) -> bool:
        caption = self.format_caption(listing)
        photos = [p for p in listing.photos if p and p.startswith("http")]
        sent_ok = False
        fav_markup = self.get_fav_markup(chat_id, listing.uid, listing.url)
        has_description = bool(listing.description and len(listing.description.strip()) > 20)

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
                else:
                    print(f"[Telegram] sendMediaGroup error {r.status_code}: {r.text}")
                    if r.status_code == 429:
                        retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                        time.sleep(retry_after + 1)
            except Exception as e:
                print(f"[Telegram] sendMediaGroup exception: {e}")

        # 2. Single photo
        if not sent_ok and len(photos) >= 1:
            try:
                photo_payload = {
                    "chat_id": chat_id,
                    "photo": photos[0],
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                if not has_description:
                    photo_payload["reply_markup"] = fav_markup

                r = requests.post(
                    f"{self.base_url}/sendPhoto",
                    json=photo_payload,
                    timeout=15
                )
                if r.status_code == 200:
                    sent_ok = True
                else:
                    print(f"[Telegram] sendPhoto error {r.status_code}: {r.text}")
                    if r.status_code == 429:
                        retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                        time.sleep(retry_after + 1)
            except Exception as e:
                print(f"[Telegram] sendPhoto exception: {e}")

        # 3. Fallback text only
        if not sent_ok:
            try:
                msg_payload = {
                    "chat_id": chat_id,
                    "text": caption,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                if not has_description:
                    msg_payload["reply_markup"] = fav_markup

                r = requests.post(
                    f"{self.base_url}/sendMessage",
                    json=msg_payload,
                    timeout=10
                )
                if r.status_code == 200:
                    sent_ok = True
                else:
                    print(f"[Telegram] sendMessage error {r.status_code}: {r.text}")
            except Exception as e:
                print(f"[Telegram] sendMessage failed: {e}")

        # 4. SEND FULL UNABRIDGED DESCRIPTION (Без сокращений!) с кнопкой «В избранное»
        desc_sent = False
        if sent_ok and has_description:
            try:
                full_desc_ru = translate_to_russian(listing.description, max_chars=3500)
                if full_desc_ru and len(full_desc_ru.strip()) > 20:
                    if len(full_desc_ru) > 3800:
                        full_desc_ru = full_desc_ru[:3800] + "..."
                    desc_text = f"📝 <b>Полное описание:</b>\n\n<i>{html.escape(full_desc_ru)}</i>"
                    time.sleep(0.4)
                    self.send_text_message(chat_id, desc_text, reply_markup=fav_markup)
                    desc_sent = True
            except Exception as e:
                print(f"[Telegram] Error sending full description message: {e}")

        # Если был отправлен альбом и нет блока описания, отправляем панель действий
        if sent_ok and len(photos) >= 2 and not desc_sent:
            try:
                time.sleep(0.3)
                self.send_text_message(chat_id, "⭐ <b>Действия с объявлением:</b>", reply_markup=fav_markup)
            except Exception as e:
                print(f"[Telegram] Error sending favorite button bar: {e}")

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

    def send_text_message(self, chat_id: int, text: str, reply_markup: dict = None) -> bool:
        try:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            r = requests.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=10
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] send_text_message error: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
        try:
            payload = {"callback_query_id": callback_query_id}
            if text:
                payload["text"] = text
                payload["show_alert"] = show_alert
            r = requests.post(f"{self.base_url}/answerCallbackQuery", json=payload, timeout=5)
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] answerCallbackQuery error: {e}")
            return False

    def edit_message_reply_markup(self, chat_id: int, message_id: int, reply_markup: dict) -> bool:
        try:
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": reply_markup
            }
            r = requests.post(f"{self.base_url}/editMessageReplyMarkup", json=payload, timeout=5)
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] editMessageReplyMarkup error: {e}")
            return False

    def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup: dict = None) -> bool:
        try:
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            r = requests.post(f"{self.base_url}/editMessageText", json=payload, timeout=5)
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] editMessageText error: {e}")
            return False

    def send_favorites_list(self, chat_id: int):
        favs = database.get_favorites(chat_id)
        if not favs:
            msg = (
                "⭐ <b>У вас пока нет сохранённых квартир.</b>\n\n"
                "Чтобы добавить квартиру в этот список, нажмите кнопку <b>«⭐ В избранное»</b> "
                "под любым объявлением, которое присылает бот!"
            )
            self.send_text_message(chat_id, msg, reply_markup=self.REPLY_KEYBOARD)
            return

        header = (
            f"⭐ <b>Ваши избранные квартиры ({len(favs)}):</b>\n"
            f"Нажмите на объявление для перехода на сайт или удалите его из списка."
        )
        self.send_text_message(chat_id, header, reply_markup=self.REPLY_KEYBOARD)

        for i, item in enumerate(favs, 1):
            source_upper = (item.get("source") or "портал").upper()
            title_esc = html.escape(item.get("title") or "Квартира")
            price_esc = html.escape(item.get("price") or "")
            url = item.get("url") or ""

            if url and url.startswith("http"):
                title_link = f"<a href=\"{html.escape(url)}\">{title_esc}</a>"
                btn_row = [
                    {"text": "🔗 На сайт", "url": url},
                    {"text": "🗑 Удалить", "callback_data": f"unfav:{item['listing_uid']}"}
                ]
            else:
                title_link = title_esc
                btn_row = [
                    {"text": "🗑 Удалить", "callback_data": f"unfav:{item['listing_uid']}"}
                ]

            card_text = (
                f"<b>{i}. [{source_upper}]</b> {title_link}\n"
                f"💰 <b>Цена:</b> {price_esc}"
            )
            keyboard = {"inline_keyboard": [btn_row]}
            self.send_text_message(chat_id, card_text, reply_markup=keyboard)
            time.sleep(0.3)

    def send_stats(self, chat_id: int):
        stats = database.get_stats()
        fav_count = len(database.get_favorites(chat_id))
        by_src = stats.get("by_source", {})
        src_lines = "\n".join([f"  • {k.capitalize()}: <b>{v}</b>" for k, v in by_src.items()])
        msg = (
            f"📊 <b>Статистика мониторинга:</b>\n\n"
            f"🏠 Всего квартир в базе: <b>{stats.get('total_seen', 0)}</b>\n"
            f"👥 Активных подписчиков: <b>{stats.get('total_subscribers', 0)}</b>\n"
            f"⭐ В вашем избранном: <b>{fav_count}</b>\n\n"
            f"<b>По источникам:</b>\n{src_lines}\n\n"
            f"📡 <i>Сканирование выполняется каждые 3 минуты.</i>"
        )
        self.send_text_message(chat_id, msg, reply_markup=self.REPLY_KEYBOARD)

    def poll_updates_once(self, offset: int = 0, on_start_command=None) -> int:
        """Polls Telegram for commands, callback buttons and registers new subscribers."""
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

                # 1. Handle Inline Callback Queries (Кнопки «В избранное» и «Удалить»)
                cq = upd.get("callback_query")
                if cq:
                    cq_id = cq.get("id")
                    user = cq.get("from", {})
                    user_chat_id = user.get("id")
                    cq_data = cq.get("data", "")
                    msg = cq.get("message", {})
                    msg_id = msg.get("message_id")

                    if cq_data.startswith("fav:"):
                        uid = cq_data.split(":", 1)[1]
                        is_now_fav = database.toggle_favorite(user_chat_id, uid)
                        if is_now_fav:
                            self.answer_callback_query(
                                cq_id,
                                text="⭐ Добавлено в избранное!\nНажмите кнопку «⭐ Избранные квартиры» внизу, чтобы посмотреть список."
                            )
                        else:
                            self.answer_callback_query(
                                cq_id,
                                text="❌ Удалено из избранного."
                            )
                        listing_data = database.get_listing_by_uid(uid) or {}
                        item_url = listing_data.get("url", "")
                        new_markup = self.get_fav_markup(user_chat_id, uid, item_url)
                        self.edit_message_reply_markup(user_chat_id, msg_id, new_markup)

                    elif cq_data.startswith("unfav:"):
                        uid = cq_data.split(":", 1)[1]
                        database.remove_favorite(user_chat_id, uid)
                        self.answer_callback_query(cq_id, text="❌ Удалено из избранного.")
                        self.edit_message_text(user_chat_id, msg_id, "🗑 <i>Квартира удалена из избранного.</i>")

                    continue

                # 2. Handle Text Messages and Commands
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
                        else:
                            self.send_text_message(
                                chat_id,
                                "✅ <b>Мониторинг активен!</b> Бот проверяет площадки каждые 3 минуты.",
                                reply_markup=self.REPLY_KEYBOARD
                            )
                    elif text.startswith("/favorites") or text.startswith("/fav") or "избранн" in text.lower():
                        self.send_favorites_list(chat_id)
                    elif text.startswith("/stats") or "статистик" in text.lower():
                        self.send_stats(chat_id)

            return offset
        except Exception as e:
            print(f"[Telegram] Error polling updates: {e}")
            return offset
