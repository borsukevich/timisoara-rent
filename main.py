import argparse
import sys
import database
from service import RentalScannerService
from telegram_notifier import TelegramNotifier
from scrapers.base import Listing

def main():
    parser = argparse.ArgumentParser(description="Timisoara Rental Scanner CLI")
    parser.add_argument("--run", action="store_true", help="Run continuous background scanner daemon")
    parser.add_argument("--scan-once", action="store_true", help="Run a single scan cycle and exit")
    parser.add_argument("--test-scrape", action="store_true", help="Test scraping all 5 platforms and display top results")
    parser.add_argument("--add-chat", type=int, help="Manually register a Telegram chat_id")
    parser.add_argument("--test-tg", type=int, help="Send a test listing card to specified chat_id")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")

    args = parser.parse_args()
    database.init_db()

    if args.add_chat:
        database.add_subscriber(args.add_chat, username="manual", first_name="User")
        print(f"✅ Chat ID {args.add_chat} added to subscribers!")
        return

    if args.test_tg:
        notifier = TelegramNotifier()
        sample = Listing(
            uid="test_123",
            source="olx",
            title="Apartament 3 camere modern Take Ionescu",
            price="650 €",
            url="https://www.olx.ro",
            rooms="3 camere",
            area="72 mp",
            location="Take Ionescu, Timișoara",
            description="Apartament complet mobilat si utilat, centrala proprie pe gaz, loc de parcare inclus, finisaje de lux, disponibil imediat.",
            photos=[
                "https://frankfurt.apollo.olxcdn.com:443/v1/files/08goaasehhsk-RO/image;s=1000x750",
                "https://frankfurt.apollo.olxcdn.com:443/v1/files/z7d8y2n3nz4g1-RO/image;s=1000x750"
            ],
            phone="+40 722 123 456",
            is_promoted=False,
            is_owner=True,
            has_boiler=True
        )
        print(f"Sending test listing to chat_id {args.test_tg}...")
        ok = notifier.send_listing(args.test_tg, sample)
        print(f"Result: {'SUCCESS' if ok else 'FAILED'}")
        return

    if args.stats:
        stats = database.get_stats()
        print("=== Database Statistics ===")
        print(f"Total seen listings in DB: {stats['total_seen']}")
        print(f"Active subscribers: {stats['total_subscribers']}")
        for src, cnt in stats['by_source'].items():
            print(f"  • {src.upper()}: {cnt}")
        subscribers = database.get_subscribers()
        print(f"Subscriber IDs: {subscribers}")
        return

    if args.test_scrape:
        print("🔍 Testing all 5 scrapers on live data...")
        service = RentalScannerService()
        for scraper in service.scrapers:
            print(f"\n[{scraper.name.upper()}] Fetching...")
            listings = scraper.fetch_listings()
            print(f"  Total parsed: {len(listings)}")
            promoted_cnt = sum(1 for l in listings if l.is_promoted)
            organic_cnt = len(listings) - promoted_cnt
            print(f"  Promoted: {promoted_cnt} | Organic (New): {organic_cnt}")
            if listings:
                sample = listings[0]
                print(f"  Sample ad:")
                print(f"    UID: {sample.uid}")
                print(f"    Title: {sample.title}")
                print(f"    Price: {sample.price}")
                print(f"    Rooms/Area: {sample.rooms} / {sample.area}")
                print(f"    Location: {sample.location}")
                print(f"    Boiler: {sample.has_boiler} | Owner: {sample.is_owner}")
                print(f"    Photos: {len(sample.photos)}")
                print(f"    URL: {sample.url}")
        return

    if args.scan_once:
        print("Running single scan cycle...")
        service = RentalScannerService()
        service.run_scan_cycle()
        return

    # Default: Run continuous daemon
    service = RentalScannerService()
    service.start_loop()

if __name__ == "__main__":
    main()

