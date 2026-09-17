from curl_cffi import requests
from bs4 import BeautifulSoup
import re
from typing import List
from scrapers.base import BaseScraper, Listing

class Publi24Scraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("publi24", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[Publi24] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select('.article-item')

            for item in items:
                link_el = item.find("a", href=lambda h: h and "/anunt/" in h)
                if not link_el:
                    continue

                url = link_el.get("href", "")
                if not url.startswith("http"):
                    url = f"https://www.publi24.ro{url}"

                m = re.search(r'/([a-zA-Z0-9]+)\.html', url)
                if not m:
                    continue
                ad_id = m.group(1)

                title_el = item.select_one('.article-title, h2, h3, a[title]')
                title = title_el.get_text(strip=True) if title_el else "Apartament Timișoara"

                item_text = item.get_text(" | ", strip=True)
                price_el = item.select_one('.price, .article-price')
                price = price_el.get_text(strip=True) if price_el else ""

                is_promoted = "promovat" in item_text.lower() or bool(item.select('.promovat, [class*="promovat"], .badge'))

                date_el = item.select_one('.article-date, .date, [class*="date"]')
                date_text = date_el.get_text(strip=True) if date_el else ""

                # Strictly today or just now (ignore yesterday or older)
                if date_text and not any(k in date_text.lower() for k in ["azi", "acum"]):
                    is_promoted = True

                district = "Timișoara"
                loc_m = re.search(r'(?:zona|în)\s+([A-Za-zĂÎÂȘȚăîâșț\s-]+)', title, re.IGNORECASE)
                if loc_m:
                    district = loc_m.group(1).strip()

                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"
                map_link = self.generate_map_link(address=full_address)

                area_m = re.search(r'(\d+[\s.,]?\d*)\s*mp', item_text, re.IGNORECASE)
                exact_area = f"{area_m.group(1).strip()} м²" if area_m else "от 55 м²"

                floor_m = re.search(r'(etaj\s*\d+(?:\s*/\s*\d+)?|parter|demisol)', item_text, re.IGNORECASE)
                floor = self.format_floor(floor_m.group(1)) if floor_m else "Не указан"

                photos = []
                for img in item.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and "publi24.ro" in src:
                        photos.append(src)

                full_text = f"{title} {item_text}"
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
                    uid=f"publi_{ad_id}",
                    source="publi24",
                    title=title,
                    price=price,
                    url=url,
                    rooms="3 camere",
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
                    description=item_text[:400],
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=date_text,
                    is_today=True
                ))

        except Exception as e:
            print(f"[Publi24] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Listing:
        """Fetches full ad page to get all photos, full specs, and phone."""
        try:
            r = requests.get(listing.url, impersonate="chrome124", timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                full_photos = []
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy")
                    if src and "publi24.ro" in src and any(sz in src for sz in ["large", "detail", "top"]):
                        if src not in full_photos:
                            full_photos.append(src)
                if full_photos:
                    listing.photos = full_photos

                desc_el = soup.select_one('.article-description, #description, [itemprop="description"]')
                if desc_el:
                    listing.description = self.clean_html(desc_el.get_text())

                page_text = f"{listing.title} {listing.description} {r.text}"
                listing.has_boiler = self.check_boiler(page_text)
                listing.is_owner = self.check_owner(page_text)
                
                area_m = re.search(r'(\d+[\s.,]?\d*)\s*mp', page_text, re.IGNORECASE)
                if area_m:
                    listing.exact_area = f"{area_m.group(1).strip()} м²"

                floor_m = re.search(r'(etaj\s*\d+(?:\s*/\s*\d+)?|parter|demisol)', page_text, re.IGNORECASE)
                if floor_m:
                    listing.floor = self.format_floor(floor_m.group(1))

                complex_cand = self.detect_complex(page_text)
                if complex_cand != "Не указан":
                    listing.complex_name = complex_cand

                parking_cand = self.analyze_parking(page_text)
                if parking_cand != "Не указано":
                    listing.parking_info = parking_cand

                listing.pets_policy = self.analyze_pets(page_text)
                listing.ac_info = self.analyze_ac(page_text)
                listing.balcony_info = self.analyze_balcony(page_text)
                listing.deposit_info = self.analyze_deposit(page_text)
                listing.building_type = self.analyze_building_type(page_text)

                found_phone = self.extract_phone(page_text)
                if found_phone:
                    listing.phone = found_phone
        except Exception as e:
            print(f"[Publi24] Error enriching details for {listing.url}: {e}")

        return listing
