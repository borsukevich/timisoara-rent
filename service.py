import sys
import time
import threading
import logging
from typing import List

import config
import database
from scrapers import (
    Listing,
    OLXScraper,
    StoriaScraper,
    ImobiliareScraper,
    Publi24Scraper,
    RentolaScraper,
)
import collections
from telegram_notifier import TelegramNotifier

LOG_BUFFER = collections.deque(maxlen=400)

class DequeHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.append(msg)
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("TimisoaraRent")

deque_handler = DequeHandler()
deque_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logging.getLogger().addHandler(deque_handler)

class RentalScannerService:
    def __init__(self):
        database.init_db()
        self.notifier = TelegramNotifier()
        self.update_offset = 0
        self.is_exporting_initial = False

        # Initialize scrapers with configured URLs (Imobiliare.ro + Storia.ro + Publi24.ro + OLX.ro + Rentola.ro)
        self.scrapers = [
            ImobiliareScraper(config.SOURCES_CONFIG["imobiliare"]["url"]),
            StoriaScraper(config.SOURCES_CONFIG["storia"]["url"]),
            Publi24Scraper(config.SOURCES_CONFIG["publi24"]["url"]),
            OLXScraper(config.SOURCES_CONFIG["olx"]["url"]),
            RentolaScraper(config.SOURCES_CONFIG["rentola"]["url"]),
        ]

        # Seed initial state if DB is completely empty (cold-start protection against cloud spam)
        if database.is_db_empty():
            logger.info("Empty database detected. Performing initial cold-start seeding (recording existing listings without sending)...")
            count = 0
            for scraper in self.scrapers:
                try:
                    items = scraper.fetch_listings()
                    for it in items:
                        database.mark_listing_seen(
                            uid=it.uid,
                            source=it.source,
                            title=it.title,
                            price=it.price,
                            url=it.url,
                            sent=0
                        )
                        count += 1
                except Exception as e:
                    logger.error(f"Error seeding {scraper.name}: {e}")
            logger.info(f"Cold-start seeding finished: {count} listings recorded.")

    def on_start_command(self, chat_id: int):
        """When user clicks /start: run initial export once, then switch to pure monitoring."""
        if database.has_user_received_initial(chat_id):
            status_msg = (
                "✅ <b>Мониторинг уже активен!</b>\n\n"
                "Выгрузка актуальных вариантов за день уже была выполнена.\n"
                "Сейчас система в режиме реального времени проверяет площадки <b>каждые 3 минуты</b> "
                "и будет присылать <b>только новые варианты</b> сразу после их публикации.\n\n"
                "💡 <i>Если вы хотите заново получить все варианты за день, нажмите кнопку «🔄 Перезапустить поиск» или отправьте /reset.</i>"
            )
            self.notifier.send_text_message(chat_id, status_msg, reply_markup=self.notifier.REPLY_KEYBOARD)
            return

        if self.is_exporting_initial:
            self.notifier.send_text_message(chat_id, "⏳ Выгрузка уже выполняется, пожалуйста, подождите немного...")
            return

        intro_msg = (
            "🚀 <b>Запускаю сканирование!</b>\n\n"
            "Сейчас соберу и отправлю вам по <b>3 последних актуальных объявления</b> с каждой из 5 площадок "
            "(OLX, Storia, Imobiliare, Publi24, Rentola) с полным описанием без сокращений, точной квадратурой, этажом, ЖК, паркингом и метками на карте.\n\n"
            "⏳ <i>Это займет около 30–45 секунд...</i>"
        )
        self.notifier.send_text_message(chat_id, intro_msg, reply_markup=self.notifier.REPLY_KEYBOARD)
        threading.Thread(target=self.run_export, args=(chat_id,), daemon=True, name="ExportThread").start()

    def on_reset_command(self, chat_id: int):
        """When user sends /reset or taps '🔄 Перезапустить поиск': clear seen history and run fresh export of 3 posts per source."""
        if self.is_exporting_initial:
            self.notifier.send_text_message(chat_id, "⏳ Выгрузка уже выполняется, пожалуйста, подождите...")
            return

        logger.info(f"User {chat_id} triggered reset. Clearing seen listings...")
        database.reset_seen_listings()

        reset_msg = (
            "🔄 <b>База поиска полностью очищена!</b>\n\n"
            "Запускаю контрольную выгрузку: по <b>3 последних объявления</b> с каждой из 5 площадок "
            "(OLX, Storia, Imobiliare, Publi24, Rentola), чтобы вы могли убедиться в корректной работе каждого источника.\n\n"
            "⏳ <i>Пожалуйста, подождите около 30–45 секунд...</i>"
        )
        self.notifier.send_text_message(chat_id, reset_msg, reply_markup=self.notifier.REPLY_KEYBOARD)
        threading.Thread(target=self.run_export, args=(chat_id,), daemon=True, name="ExportThread").start()

    def run_export(self, chat_id: int):
        self.is_exporting_initial = True
        logger.info(f"Starting export for user {chat_id}...")

        sent_count = 0
        try:
            for scraper in self.scrapers:
                try:
                    listings = scraper.fetch_listings()
                    organic_items = [l for l in listings if not l.is_promoted]
                    logger.info(f"[{scraper.name}] Processing {len(organic_items)} organic listings for {chat_id} (target: up to 3 posts)...")

                    qualified_to_send = []
                    remaining_to_seed = []

                    for listing in organic_items:
                        if len(qualified_to_send) < 3:
                            price_eur = scraper.parse_price_eur(listing.price)
                            if price_eur is not None and (price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 850)):
                                remaining_to_seed.append(listing)
                                continue

                            if hasattr(scraper, "enrich_listing_details"):
                                enriched = scraper.enrich_listing_details(listing)
                                if not enriched:
                                    remaining_to_seed.append(listing)
                                    continue
                                listing = enriched

                            # Strict Timișoara check (applied only to publi24)
                            if scraper.name == "publi24":
                                full_loc = f"{listing.title} {listing.district} {listing.full_address}"
                                if not scraper.is_timisoara_location(full_loc):
                                    logger.info(f"🚫 [{listing.source}] Excluded: Не в Тимишоаре | {listing.title}")
                                    remaining_to_seed.append(listing)
                                    continue

                            # Strict price check: MUST have valid price in 400 - 850 EUR range
                            price_eur = scraper.parse_price_eur(listing.price)
                            if price_eur is None or price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 850):
                                logger.info(f"🚫 [{listing.source}] Excluded: Нет цены 400-850 EUR ('{listing.price}') | {listing.title}")
                                remaining_to_seed.append(listing)
                                continue

                            qualified_to_send.append(listing)
                        else:
                            remaining_to_seed.append(listing)

                    logger.info(f"[{scraper.name}] Sending {len(qualified_to_send)} qualified posts to {chat_id}...")

                    # Send qualified listings in reverse order: from older to newest (от старых к новым, самое свежее - последним)
                    for listing in reversed(qualified_to_send):
                        ok = self.notifier.send_listing(chat_id, listing)
                        if ok:
                            sent_count += 1
                            database.mark_listing_seen(
                                uid=listing.uid,
                                source=listing.source,
                                title=listing.title,
                                price=listing.price,
                                url=listing.url,
                                sent=1
                            )
                        time.sleep(1.0)

                    # Mark remaining organic items as seen (sent=0) so subsequent scan cycles don't spam
                    for listing in remaining_to_seed:
                        database.mark_listing_seen(
                            uid=listing.uid,
                            source=listing.source,
                            title=listing.title,
                            price=listing.price,
                            url=listing.url,
                            sent=0
                        )

                    # Mark promoted listings as seen (sent=0)
                    for listing in listings:
                        if listing.is_promoted:
                            database.mark_listing_seen(
                                uid=listing.uid,
                                source=listing.source,
                                title=listing.title,
                                price=listing.price,
                                url=listing.url,
                                sent=0
                            )
                except Exception as e:
                    logger.error(f"Error during export for {scraper.name}: {e}", exc_info=True)

            # Mark user as having received the initial batch
            database.mark_user_initial_received(chat_id)

            finish_msg = (
                f"✅ <b>Контрольная выгрузка завершена!</b>\n"
                f"Отправлено актуальных вариантов: <b>{sent_count}</b> (по 3 последних с каждого из 5 порталов).\n\n"
                f"📡 <b>Мониторинг активен:</b> теперь каждые 3 минуты бот проверяет все площадки и будет "
                f"присылать только новые варианты сразу после их публикации!"
            )
            self.notifier.send_text_message(chat_id, finish_msg, reply_markup=self.notifier.REPLY_KEYBOARD)
            logger.info(f"Export completed. Sent {sent_count} listings to {chat_id}.")
        except Exception as e:
            logger.error(f"Critical error in run_export: {e}", exc_info=True)
        finally:
            self.is_exporting_initial = False

    def check_telegram_subscribers(self):
        """Polls for commands and subscribers."""
        self.update_offset = self.notifier.poll_updates_once(
            self.update_offset,
            on_start_command=self.on_start_command,
            on_reset_command=self.on_reset_command
        )

    def scan_source(self, scraper) -> List[Listing]:
        try:
            items = scraper.fetch_listings()
            return items
        except Exception as e:
            logger.error(f"[{scraper.name}] Error during scan: {e}")
            return []

    def run_scan_cycle(self):
        self.check_telegram_subscribers()

        total_new = 0
        for scraper in self.scrapers:
            listings = self.scan_source(scraper)

            # Process in reverse order: older listings first, newest sent last
            for listing in reversed(listings):
                if listing.is_promoted:
                    continue

                if database.is_listing_seen(listing.uid, listing.url):
                    continue

                # Check explicit exclusion reason if already determined
                if listing.exclusion_reason:
                    logger.info(f"🚫 [{listing.source}] Excluded: {listing.exclusion_reason} | {listing.title}")
                    database.mark_listing_seen(uid=listing.uid, source=listing.source, title=listing.title, price=listing.price, url=listing.url, sent=0)
                    continue

                # Filter card price strictly 400 - 850 EUR if present
                price_eur = scraper.parse_price_eur(listing.price)
                if price_eur is not None and (price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 850)):
                    logger.info(f"🚫 [{listing.source}] Excluded: Цена {price_eur} EUR вне диапазона 400-850 EUR | {listing.title}")
                    database.mark_listing_seen(uid=listing.uid, source=listing.source, title=listing.title, price=listing.price, url=listing.url, sent=0)
                    continue

                if hasattr(scraper, "enrich_listing_details"):
                    enriched = scraper.enrich_listing_details(listing)
                    if not enriched:
                        reason = getattr(listing, "exclusion_reason", None) or "Не соответствует критериям района / параметров"
                        logger.info(f"🚫 [{listing.source}] Excluded: {reason} | {listing.title}")
                        database.mark_listing_seen(
                            uid=listing.uid,
                            source=listing.source,
                            title=listing.title,
                            price=listing.price,
                            url=listing.url,
                            sent=0
                        )
                        continue
                    listing = enriched

                # Strict Timișoara check (applied only to publi24)
                if scraper.name == "publi24":
                    full_loc = f"{listing.title} {listing.district} {listing.full_address}"
                    if not scraper.is_timisoara_location(full_loc):
                        logger.info(f"🚫 [{listing.source}] Excluded: Не в Тимишоаре | {listing.title}")
                        database.mark_listing_seen(
                            uid=listing.uid,
                            source=listing.source,
                            title=listing.title,
                            price=listing.price,
                            url=listing.url,
                            sent=0
                        )
                        continue

                # Strict price check: MUST have valid price in 400 - 850 EUR range
                price_eur = scraper.parse_price_eur(listing.price)
                if price_eur is None or price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 850):
                    logger.info(f"🚫 [{listing.source}] Excluded: Нет подтвержденной цены 400-850 EUR ('{listing.price}') | {listing.title}")
                    database.mark_listing_seen(
                        uid=listing.uid,
                        source=listing.source,
                        title=listing.title,
                        price=listing.price,
                        url=listing.url,
                        sent=0
                    )
                    continue

                # Fully qualified and verified organic listing!
                logger.info(f"🔥 NEW LISTING FOUND: [{listing.source}] {listing.title} ({listing.price}) - {listing.url}")

                # Broadcast to Telegram subscribers
                sent_count = self.notifier.broadcast_listing(listing)

                database.mark_listing_seen(
                    uid=listing.uid,
                    source=listing.source,
                    title=listing.title,
                    price=listing.price,
                    url=listing.url,
                    sent=1 if sent_count > 0 else 0
                )
                total_new += 1
                time.sleep(1.5)

        stats = database.get_stats()
        logger.info(
            f"Cycle finished. New: {total_new}. "
            f"Total in DB: {stats['total_seen']}. Active subscribers: {stats['total_subscribers']}."
        )

    def start_loop(self):
        logger.info("==================================================")
        logger.info("   TIMIȘOARA RENT SCANNER BOT STARTED 🚀        ")
        logger.info(f"   Target: 3+ rooms, <=850 EUR, >=55 sqm          ")
        logger.info(f"   Interval: every {config.SCAN_INTERVAL_SECONDS}s")
        logger.info("==================================================")

        while True:
            try:
                self.run_scan_cycle()
            except Exception as e:
                logger.error(f"Unexpected error in scan cycle: {e}", exc_info=True)

            next_scan_time = time.time() + config.SCAN_INTERVAL_SECONDS
            while time.time() < next_scan_time:
                self.check_telegram_subscribers()
                time.sleep(1)

if __name__ == "__main__":
    service = RentalScannerService()
    service.start_loop()
