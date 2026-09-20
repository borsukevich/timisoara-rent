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

    def test_extract_price_from_text(self):
        self.assertEqual(self.scraper.extract_price_from_text("Chirie 650 €/lună"), "650 €")
        self.assertEqual(self.scraper.extract_price_from_text("Preț 550 euro"), "550 €")
        self.assertEqual(self.scraper.extract_price_from_text("Pret: € 700 fix"), "700 €")
        self.assertEqual(self.scraper.extract_price_from_text("Chirie 3000 lei pe luna"), "600 €")
        self.assertEqual(self.scraper.extract_price_from_text("Fără preț specificat"), None)

    def test_parse_price_eur(self):
        self.assertEqual(self.scraper.parse_price_eur("650 €"), 650.0)
        self.assertEqual(self.scraper.parse_price_eur("600 € (было 700 €)"), 600.0)
        self.assertEqual(self.scraper.parse_price_eur("<s>700 €</s> 600 €"), 600.0)
        self.assertEqual(self.scraper.parse_price_eur("2500 lei"), 500.0)
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

if __name__ == "__main__":
    unittest.main()

