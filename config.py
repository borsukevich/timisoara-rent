import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "timisoara_rent_bot")

# Polling interval in seconds (between scans)
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "180"))  # 3 minutes

# Default filter settings
CRITERIA = {
    "min_rooms": 3,
    "min_price_eur": 400,
    "max_price_eur": 800,
    "min_area_sqm": 50,
    "city": "Timișoara",
}

# Target URLs verified by user (min 400 EUR, max 800 EUR)
SOURCES_CONFIG = {
    "olx": {
        "url": "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-inchiriat/3-camere/timisoara/?currency=EUR&search%5Border%5D=created_at:desc&search%5Bfilter_float_price:from%5D=400&search%5Bfilter_float_price:to%5D=800&search%5Bfilter_float_m:from%5D=50",
        "name": "OLX.ro",
        "max_items": 20
    },
    "storia": {
        "url": "https://www.storia.ro/ro/rezultate/inchiriere/apartament/toata-romania?limit=36&priceMin=400&priceMax=800&areaMin=55&roomsNumber=%5BTHREE%2CFOUR%2CFIVE%5D&by=LATEST&direction=DESC&geometry=manvGoaw%60Cca%40dgByGxmChn%40xuAxcAhaAhcAt%7DAfm%40%60Jhc%40%7BFtVkPdLw%5DyB%7BoBw%5CgcB%7CHic%40gAky%40%7DYuVsPgg%40jCihC%7BMgk%40eQ%7DMic%40uGou%40vN_e%40te%40_%60%40rgA&mapBounds=21.278969545958066%2C45.79718845161485%2C21.177700454041933%2C45.74502994994667",
        "name": "Storia.ro",
        "max_items": 20
    },
    "imobiliare": {
        "url": "https://www.imobiliare.ro/inchirieri-apartamente/judetul-timis/timisoara?area=55&map-area=min_VZJLDgMxCEMvVI2Cw1e9_72qiZ1Fl08YbEg8nhr_wB7sHV9_EU3OIa8gT4vzsHse7i5yOzntcLgY1CeKbJucdriCXIt-SbtimjSmKydHXTXdw-mecguM3EfMflZ9wF3Abm-aoTX9kNWWmpusud0v2kyo2ch25WdRa1M0EyrooWoW01mtATk31YvDsvxvWI6mla4GhcG94mW9CseN7Lp4Fop7RLhP7Fq89AV4VIBhhmGB8R8&map-latitude=45.762493&map-longitude=21.230993&map-zoom=13&price=400-800&rooms=3%2C4&sort=latest",
        "name": "Imobiliare.ro",
        "max_items": 20
    },
    "publi24": {
        "url": "https://www.publi24.ro/anunturi/imobiliare/de-inchiriat/apartamente/apartamente-3-camere/timis/timisoara/?livingspace=50-&minprice=400&maxprice=800&sort=date_desc",
        "name": "Publi24.ro",
        "max_items": 20
    }
}

DB_PATH = os.getenv("DB_PATH", "rentals.db")

