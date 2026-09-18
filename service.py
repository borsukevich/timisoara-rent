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
    Publi24Scraper
)
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("TimisoaraRent")

class RentalScannerService:
    def __init__(self):
        database.init_db()
        self.notifier = TelegramNotifier()
        self.update_offset = 0
        self.is_exporting_initial = False

        # Initialize scrapers with configured URLs (Imobiliare.ro + Storia.ro + Publi24.ro + OLX.ro)
        self.scrapers = [
            ImobiliareScraper(config.SOURCES_CONFIG["imobiliare"]["url"]),
            StoriaScraper(config.SOURCES_CONFIG["storia"]["url"]),
            Publi24Scraper(config.SOURCES_CONFIG["publi24"]["url"]),
            OLXScraper(config.SOURCES_CONFIG["olx"]["url"]),
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
            "🚀 <b>Запускаю полное сканирование!</b>\n\n"
            "Сейчас соберу и отправлю вам <b>все актуальные объявления за день</b> со всех 4 площадок "
            "(OLX, Storia, Imobiliare, Publi24) с полным описанием без сокращений, точной квадратурой, этажом, ЖК, паркингом и метками на карте.\n\n"
            "⏳ <i>Это займет около 1–2 минут (отправляю порциями, чтобы не сработал спам-фильтр Telegram)...</i>"
        )
        self.notifier.send_text_message(chat_id, intro_msg, reply_markup=self.notifier.REPLY_KEYBOARD)
        threading.Thread(target=self.run_export, args=(chat_id,), daemon=True, name="ExportThread").start()

    def on_reset_command(self, chat_id: int):
        """When user sends /reset or taps '🔄 Перезапустить поиск': clear seen history and run fresh export."""
        if self.is_exporting_initial:
            self.notifier.send_text_message(chat_id, "⏳ Выгрузка уже выполняется, пожалуйста, подождите...")
            return

        logger.info(f"User {chat_id} triggered reset. Clearing seen listings...")
        database.reset_seen_listings()

        reset_msg = (
            "🔄 <b>База поиска успешно сброшена!</b>\n\n"
            "Запускаю повторный сбор всех актуальных объявлений за день со всех 4 площадок "
            "(без ограничений по годам, с кнопками «⭐ В избранное» и каждой характеристикой на новой строке).\n\n"
            "⏳ <i>Пожалуйста, подождите 1–2 минуты...</i>"
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
                    top_items = organic_items[:30]
                    logger.info(f"[{scraper.name}] Exporting {len(top_items)} organic listings for {chat_id}...")

                    for listing in reversed(top_items):
                        price_eur = scraper.parse_price_eur(listing.price)
                        if price_eur is not None and (price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 800)):
                            continue

                        if hasattr(scraper, "enrich_listing_details"):
                            enriched = scraper.enrich_listing_details(listing)
                            if not enriched:
                                continue
                            listing = enriched

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
                        # Safe interval between apartments
                        time.sleep(1.0)

                    # Mark remaining existing organic items from page 1 as seen
                    # so they will not be treated as "new" in subsequent scans
                    for listing in organic_items[30:]:
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
                f"✅ <b>Выгрузка за сегодня завершена!</b>\n"
                f"Отправлено актуальных вариантов: <b>{sent_count}</b>.\n\n"
                f"📡 <b>Мониторинг активен:</b> теперь каждые 3 минуты бот проверяет все площадки и будет "
                f"присылать только свежие варианты сразу после их публикации!"
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

                # Filter price strictly 400 - 800 EUR
                price_eur = scraper.parse_price_eur(listing.price)
                if price_eur is not None and (price_eur < config.CRITERIA.get("min_price_eur", 400) or price_eur > config.CRITERIA.get("max_price_eur", 800)):
                    logger.info(f"🚫 [{listing.source}] Excluded: Цена {price_eur} EUR вне диапазона 400-800 EUR | {listing.title}")
                    database.mark_listing_seen(uid=listing.uid, source=listing.source, title=listing.title, price=listing.price, url=listing.url, sent=0)
                    continue

                # Truly new organic listing found!
                logger.info(f"🔥 NEW LISTING FOUND: [{listing.source}] {listing.title} ({listing.price}) - {listing.url}")

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
        logger.info(f"   Target: 3+ rooms, <=800 EUR, >=55 sqm          ")
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
