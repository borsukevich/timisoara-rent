from curl_cffi import requests
from bs4 import BeautifulSoup
import re
from typing import List
from scrapers.base import BaseScraper, Listing

class ImobiliareScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("imobiliare", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[Imobiliare] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select('[data-id]')

            for card in cards:
                card_id = card.get("data-id")
                if not card_id:
                    continue

                link_el = card.find("a", href=lambda h: h and "/oferta/" in h) or card.find("a", href=True)
                if not link_el:
                    continue
                href = link_el.get("href", "")
                url = f"https://www.imobiliare.ro{href}" if href.startswith("/") else href

                title_el = card.find(["h2", "h3"]) or link_el
                title = title_el.get_text(strip=True) if title_el else "Apartament Timișoara"

                classes = " ".join(card.get("class", []))
                is_promoted = "promovat" in classes.lower() or bool(card.select('.promovat, [class*="promovat"]'))

                # Price
                price = ""
                price_match = re.search(r'(\d+[\s.]?\d*)\s*€', card.get_text())
                if price_match:
                    price = f"{price_match.group(1).replace(' ', '')} €"

                # Rooms and area
                rooms = "3 camere"
                exact_area = "от 55 м²"
                rooms_match = re.search(r'(\d+)\s*camere', card.get_text(), re.IGNORECASE)
                if rooms_match:
                    rooms = f"{rooms_match.group(1)} camere"
                
                area_match = re.search(r'(\d+[\s.,]?\d*)\s*mp', card.get_text(), re.IGNORECASE)
                if area_match:
                    exact_area = f"{area_match.group(1).strip()} м²"

                # Floor
                card_text = card.get_text(" | ", strip=True)
                floor_match = re.search(r'(Etaj\s*\d+(?:\s*/\s*\d+)?|Parter|Demisol|Mansarda)', card_text, re.IGNORECASE)
                floor = self.format_floor(floor_match.group(1)) if floor_match else "Не указан"

                # Location & Address
                district = "Timișoara"
                loc_match = re.search(r'([A-Za-zĂÎÂȘȚăîâșț\s-]+),\s*Timișoara', card_text)
                if loc_match:
                    district = loc_match.group(1).strip()
                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"

                map_link = self.generate_map_link(address=full_address)

                # Photos
                photos = []
                for img in card.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and "roamcdn.net" in src and src not in photos:
                        photos.append(src)

                # Analysis
                full_text = f"{title} {card_text}"
                has_boiler = self.check_boiler(full_text)
                is_owner = self.check_owner(full_text)
                phone = self.extract_phone(full_text)
                complex_name = self.detect_complex(full_text)
                parking_info = self.analyze_parking(full_text)
                pets_policy = self.analyze_pets(full_text)
                ac_info = self.analyze_ac(full_text)
                balcony_info = self.analyze_balcony(full_text)
                deposit_info = self.analyze_deposit(full_text)
                building_type = self.analyze_building_type(full_text)
                commission_info = "0% (Без комиссии)" if is_owner else "Уточнять (обычно 50%)"

                listings.append(Listing(
                    uid=f"imob_{card_id}",
                    source="imobiliare",
                    title=title,
                    price=price,
                    url=url,
                    rooms=rooms,
                    exact_area=exact_area,
                    floor=floor,
                    district=district,
                    street="",
                    full_address=full_address,
                    complex_name=complex_name,
                    parking_info=parking_info,
                    pets_policy=pets_policy,
                    ac_info=ac_info,
                    balcony_info=balcony_info,
                    deposit_info=deposit_info,
                    commission_info=commission_info,
                    building_type=building_type,
                    map_link=map_link,
                    description=card_text[:500],
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text="Azi" if "azi" in card_text.lower() else None,
                    is_today=True
                ))

        except Exception as e:
            print(f"[Imobiliare] Exception while fetching: {e}")

        return listings
