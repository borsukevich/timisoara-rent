from curl_cffi import requests
from bs4 import BeautifulSoup
import re
from typing import List
from scrapers.base import BaseScraper, Listing

class ImoRadarScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("imoradar", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[ImoRadar24] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            seen_ids = set()

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("/oferta/"):
                    continue

                m = re.search(r'-(\d+)$', href)
                if not m:
                    continue
                ad_id = m.group(1)
                if ad_id in seen_ids:
                    continue
                seen_ids.add(ad_id)

                url = f"https://www.imoradar24.ro{href}"

                container = a.find_parent("article") or a.find_parent("div", class_=lambda c: c and ("card" in c.lower() or "item" in c.lower())) or a.parent.parent
                container_text = container.get_text(" | ", strip=True) if container else a.get_text(strip=True)

                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    h_el = container.find(["h2", "h3", "h4"]) if container else None
                    title = h_el.get_text(strip=True) if h_el else "Apartament Timișoara"

                price = ""
                price_match = re.search(r'(\d+[\s.]?\d*)\s*(?:€|EUR)', container_text)
                if price_match:
                    price = f"{price_match.group(1).replace(' ', '')} €"

                rooms = "3 camere"
                rooms_match = re.search(r'(\d+)\s*camere', container_text, re.IGNORECASE)
                if rooms_match:
                    rooms = f"{rooms_match.group(1)} camere"

                exact_area = "от 55 м²"
                area_match = re.search(r'(\d+[\s.,]?\d*)\s*mp', container_text, re.IGNORECASE)
                if area_match:
                    exact_area = f"{area_match.group(1).strip()} м²"

                floor_match = re.search(r'(Etaj\s*\d+(?:\s*/\s*\d+)?|Parter|Demisol|Mansarda)', container_text, re.IGNORECASE)
                floor = self.format_floor(floor_match.group(1)) if floor_match else "Не указан"

                district = "Timișoara"
                slug_parts = href.split("-")
                if "timisoara" in slug_parts:
                    idx = slug_parts.index("timisoara")
                    if idx + 1 < len(slug_parts) and not slug_parts[idx+1].isdigit():
                        district = slug_parts[idx+1].capitalize()

                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"
                map_link = self.generate_map_link(address=full_address)

                photos = []
                if container:
                    for img in container.find_all("img"):
                        src = img.get("src") or img.get("data-src")
                        if src and "roamcdn.net" in src and src not in photos:
                            photos.append(src)

                is_promoted = "promovat" in container_text.lower()

                full_text = f"{title} {container_text}"
                has_boiler = self.check_boiler(full_text)
                is_owner = self.check_owner(full_text) or "proprietar" in container_text.lower()
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
                    uid=f"imoradar_{ad_id}",
                    source="imoradar",
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
                    description=container_text[:500],
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text="Azi" if "azi" in container_text.lower() else None,
                    is_today=True
                ))

        except Exception as e:
            print(f"[ImoRadar24] Exception while fetching: {e}")

        return listings
