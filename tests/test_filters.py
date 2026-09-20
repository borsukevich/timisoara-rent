import unittest
from scrapers.base import BaseScraper, Listing

class DummyScraper(BaseScraper):
    def __init__(self):
        super().__init__("dummy", "http://example.com")

    def fetch_listings(self):
        return []

class TestFilters(unittest.TestCase):
    def setUp(self):
        self.scraper = DummyScraper()

    def test_timisoara_location_filtering(self):
        # True: Timisoara locations
        self.assertTrue(self.scraper.is_timisoara_location("Apartament 3 camere, Timișoara, Aradului"))
        self.assertTrue(self.scraper.is_timisoara_location("Calea Aradului, Timișoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Calea Sagului, Timișoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Circumvalatiunii, Timisoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Complex Studentesc, Timisoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Iosefin, Timisoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Torontalului, Timisoara"))
        self.assertTrue(self.scraper.is_timisoara_location("Lipovei, Timisoara"))

        # False: Other cities or external suburbs
        self.assertFalse(self.scraper.is_timisoara_location("Strada Distribuției, Sibiu, Turnișor"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament 3 camere Arad, Centru"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament Cluj-Napoca, Marasti"))
        self.assertFalse(self.scraper.is_timisoara_location("Giroc, Calea Timisoarei"))
        self.assertFalse(self.scraper.is_timisoara_location("Dumbravita, str. Simfoniei"))
        self.assertFalse(self.scraper.is_timisoara_location("Mosnita Noua, Timis"))
        self.assertFalse(self.scraper.is_timisoara_location("Lugoj, Timis"))
        self.assertFalse(self.scraper.is_timisoara_location("Comuna Sag, Timis"))
        self.assertFalse(self.scraper.is_timisoara_location("Bucuresti, Sector 1"))
        self.assertFalse(self.scraper.is_timisoara_location("Apart 3 cam langa metrou"))
        self.assertFalse(self.scraper.is_timisoara_location("Lux! Apartament cu 3 camere in Selimbar pe Doamna Stanca"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament cu 3 camere in Sibiu pe Strada Distribuției"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament cu 3 camere, bloc nou, Coresi"))
        self.assertFalse(self.scraper.is_timisoara_location("Aparatorii Patriei Ap 3 Camere Mobilat de Inchiriat"))
        self.assertFalse(self.scraper.is_timisoara_location("Titan, Galeriile Titan, Metrou"))
        self.assertFalse(self.scraper.is_timisoara_location("3 camere între metrou Unirii și Tineretului, Parcul Carol, Bd Marasesti, nr 42"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament 3 camere Ultracentral Pitesti"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament 3 camere Ploiesti"))
        self.assertFalse(self.scraper.is_timisoara_location("Apartament 3 camere Bacau"))

    def test_extract_price_from_text(self):
        self.assertEqual(self.scraper.extract_price_from_text("Chirie 650 €/lună"), "650 €")
        self.assertEqual(self.scraper.extract_price_from_text("Preț 550 euro"), "550 €")
        self.assertEqual(self.scraper.extract_price_from_text("Pret: € 700 fix"), "700 €")
        self.assertEqual(self.scraper.extract_price_from_text("Chirie 3000 lei pe luna"), "600 €")
        self.assertEqual(self.scraper.extract_price_from_text("<span class='product-price'>450EUR</span>"), "450 €")
        self.assertEqual(self.scraper.extract_price_from_text("<span class='price'>3.500 lei</span>"), "700 €")
        self.assertEqual(self.scraper.extract_price_from_text("<div class='price-box'> 550.00 € / luna </div>"), "550 €")
        self.assertEqual(self.scraper.extract_price_from_text("<p>2 500 RON chirie</p>"), "500 €")
        self.assertEqual(self.scraper.extract_price_from_text("Chirie 450 euro / luna. Garantie 900 euro."), "450 €")
        self.assertEqual(self.scraper.extract_price_from_text("Fără preț specificat"), None)

    def test_parse_price_eur(self):
        self.assertEqual(self.scraper.parse_price_eur("650 €"), 650.0)
        self.assertEqual(self.scraper.parse_price_eur("600 € (было 700 €)"), 600.0)
        self.assertEqual(self.scraper.parse_price_eur("<s>700 €</s> 600 €"), 600.0)
        self.assertEqual(self.scraper.parse_price_eur("2500 lei"), 500.0)
        self.assertEqual(self.scraper.parse_price_eur("490 EUR"), 490.0)
        self.assertIsNone(self.scraper.parse_price_eur(""))
        self.assertIsNone(self.scraper.parse_price_eur("Уточняйте"))
        self.assertIsNone(self.scraper.parse_price_eur("Pret la cerere"))

    def test_price_range_criteria(self):
        # Criteria strictly 400 - 800 EUR
        valid_prices = ["400 €", "550 €", "800 €", "2500 lei"]
        for p in valid_prices:
            val = self.scraper.parse_price_eur(p)
            self.assertIsNotNone(val)
            self.assertTrue(400 <= val <= 800)

        invalid_prices = ["350 €", "850 €", "Уточняйте", "", "1500 lei"]
        for p in invalid_prices:
            val = self.scraper.parse_price_eur(p)
            is_valid = (val is not None and 400 <= val <= 800)
            self.assertFalse(is_valid)

    def test_publi24_and_olx_zone_disambiguation(self):
        from scrapers.publi24 import Publi24Scraper
        from scrapers.olx import OLXScraper

        p24 = Publi24Scraper("http://example.com")
        olx = OLXScraper("http://example.com")

        # Boiler (Centrala Proprie) must NOT override Girocului exclusion
        giroc_title = "Apartament cu 3 camere 89 mp decomandat | Centrala Proprie | Zona Girocului"
        self.assertIsNotNone(p24.is_south_zone(giroc_title, context=giroc_title))
        self.assertIsNotNone(olx.is_explicitly_excluded(giroc_title, context=giroc_title))

        # North titles must be kept
        north_title = "Zona Calea Lipovei - De închiriat apartament cu 3 camere cu centrală proprie"
        self.assertIsNone(p24.is_south_zone(north_title, context=north_title))
        self.assertIsNone(olx.is_explicitly_excluded(north_title, context=north_title))

        ring_title = "Proprietar - Apartament de închiriat Complex The Ring"
        self.assertIsNone(p24.is_south_zone(ring_title, context=ring_title))
        self.assertIsNone(olx.is_explicitly_excluded(ring_title, context=ring_title))

    def test_publi24_user_markup_snippets(self):
        from bs4 import BeautifulSoup

        # User card markup snippet
        card_html = """
        <div class="article-info">
            <span class="article-lbl">
                <span class="article-price">490 EUR</span>
            </span>
        </div>
        """
        card_soup = BeautifulSoup(card_html, "html.parser")
        price_el = card_soup.select_one(".article-price") or card_soup.select_one(".product-price")
        self.assertIsNotNone(price_el)
        self.assertEqual(price_el.get_text(strip=True), "490 EUR")
        self.assertEqual(self.scraper.parse_price_eur(price_el.get_text(strip=True)), 490.0)

        # User detail page markup snippet
        detail_html = """
        <div class="large-4 medium-5 columns medium-text-right">
            <span class="product-price">
                <span>490</span>
                <span>EUR <span class="detail-price-type"></span></span>
                <span class="pricePerSquare"></span>
            </span>
        </div>
        """
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        p_el = detail_soup.select_one(".product-price")
        self.assertIsNotNone(p_el)
        p_copy = BeautifulSoup(str(p_el), "html.parser")
        for extra in p_copy.select('.pricePerSquare, .detail-price-type'):
            extra.decompose()
        cand_p = p_copy.get_text(" ", strip=True)
        self.assertEqual(cand_p, "490 EUR")
        self.assertEqual(self.scraper.parse_price_eur(cand_p), 490.0)

if __name__ == "__main__":
    unittest.main()

