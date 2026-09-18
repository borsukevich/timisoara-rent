from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import html
from typing import List, Optional
from scrapers.base import BaseScraper, Listing

EXCLUDED_SOUTH_PATTERNS = [
    r'giroc\w*',
    r'martirilor\b',
    r'soarelui',
    r'[sș]agului\w*',
    r'd[aâ]mbovi[tț]\w*',
    r'braytim\w*',
    r'steaua\b',
    r'frateli\w*',
    r'freidorf\w*',
    r'iosefin\w*',
    r'elisabet\w*',
    r'b[aă]lcescu\w*',
    r'ciarda\s*ro[sș]ie',
    r'buzia[sș]\w*',
    r'jude[tț]ean\w*',
    r'olimpia\w*',
    r'stadion\w*',
    r'rebreanu\w*',
    r'br[aâ]ncoveanu\w*',
    r'odobescu\w*',
    r'urseni\w*',
    r'sinaia\w*',
    r'p(?:ia)?[tț]a\s*maria\b',
    r'plopi\b',
    r'studen[tț]esc\w*',
    r'campus\b'
]

PREFERRED_NORTH_CENTRAL_ZONES = [
    r'lipovei', r'aradului', r'torontal\w*', r'bucovin\w*', r'circumvala[tț]iun\w*',
    r'mehala', r'dacia', r'take\s*ionescu', r'tipograf\w*', r'ultracentral\w*',
    r'central\w*', r'cetate', r'unirii', r'antim', r'iulius', r'botanic\w*',
    r'miresei', r'sever\s*bocu', r'felix', r'ion\s*ionescu', r'simion\s*b[aă]rnu[tț]iu'
]

class Publi24Scraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("publi24", url)

    def is_north_zone(self, text: str) -> bool:
        t = text.lower()
        for pat in PREFERRED_NORTH_CENTRAL_ZONES:
            if re.search(r'\b' + pat, t, re.IGNORECASE):
                return True
        return False

    def is_south_zone(self, text: str, context: str = "") -> Optional[str]:
        """Returns the matched excluded southern zone, or None if in North/Center."""
        if context and self.is_north_zone(context):
            return None
        t = text.lower()
        for pat in EXCLUDED_SOUTH_PATTERNS:
            m = re.search(r'\b' + pat, t, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[Publi24] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            
            # Find the subtitle delimiter that separates promoted ads from organic listings
            sub = soup.find("p", class_="article-list-subtitle")
            if sub:
                items = sub.find_all_next("div", class_="article-item")
            else:
                items = soup.select(".article-item")

            for item in items:
                # 1. Skip promoted / advertising blocks
                if item.select(".art-promoted, .art-img-promoted, [class*='promoted'], [class*='promovat']"):
                    continue
                if "promovat" in item.get_text().lower():
                    continue

                # 2. Extract basic link and UID
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

                item_text = item.get_text(" ", strip=True)

                # 3. Check for excluded South zones directly in card
                south_match = self.is_south_zone(f"{title} {item_text}", context=title)
                if south_match:
                    # Skip South zones (outside user map polygon)
                    continue

                # 4. Extract price (show both new and old price if discounted)
                new_price_el = item.select_one('.new-price')
                old_price_el = item.select_one('.old-price')

                if new_price_el and old_price_el:
                    new_val = new_price_el.get_text(strip=True)
                    old_val = old_price_el.get_text(strip=True)
                    price = f"{new_val} (было <s>{old_val}</s> 📉)"
                elif new_price_el:
                    price = new_price_el.get_text(strip=True)
                elif old_price_el:
                    price = old_price_el.get_text(strip=True)
                else:
                    price_el = item.select_one('.article-price') or item.select_one('.price')
                    price = price_el.get_text(strip=True) if price_el else ""

                # Price filter: strictly 400 - 800 EUR
                price_eur = self.parse_price_eur(price)
                if price_eur is not None and (price_eur < 400 or price_eur > 800):
                    continue

                # 5. Extract date (e.g. azi 12:49)
                date_el = item.select_one('.article-date')
                date_text = date_el.get_text(strip=True) if date_el else ""

                # 6. Extract area
                area_m = re.search(r'(\d+[\s.,]?\d*)\s*m(?:p|2|<sup>2</sup>)?', item_text, re.IGNORECASE)
                exact_area = f"{area_m.group(1).strip()} м²" if area_m else "от 50 м²"

                # 7. Extract district name if detectable from title/card
                district = "Timișoara"
                loc_m = re.search(r'(?:zona|în)\s+([A-Za-zĂÎÂȘȚăîâșț\s-]+)', title, re.IGNORECASE)
                if loc_m:
                    district = loc_m.group(1).strip()

                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"
                map_link = self.generate_map_link(address=full_address)

                # 8. Photos preview from card
                photos = []
                for img in item.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and "s3.publi24.ro" in src:
                        high_src = src.replace("/top/", "/extralarge/").replace("/large/", "/extralarge/")
                        if high_src not in photos:
                            photos.append(high_src)

                full_text = f"{title} {item_text}"
                has_boiler = self.check_boiler(full_text)
                is_owner = self.check_owner(full_text)
                phone = self.extract_phone(full_text)
                complex_name = self.detect_complex(full_text)
                parking_info = self.analyze_parking(full_text)
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
                    floor="Не указан",
                    district=district,
                    street="",
                    full_address=full_address,
                    complex_name=complex_name,
                    parking_info=parking_info,
                    pets_policy="Уточнять",
                    ac_info=ac_info,
                    balcony_info=balcony_info,
                    deposit_info=deposit_info,
                    commission_info=commission_info,
                    building_type=building_type,
                    map_link=map_link,
                    description=item_text[:400],
                    photos=photos,
                    phone=phone,
                    is_promoted=False,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=date_text,
                    is_today=True
                ))

        except Exception as e:
            print(f"[Publi24] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Optional[Listing]:
        """Fetches full listing detail page to get high-res gallery, specs, and contacts."""
        try:
            r = requests.get(listing.url, impersonate="chrome124", timeout=12)
            if r.status_code != 200:
                return listing

            soup = BeautifulSoup(r.text, "html.parser")

            # 1. Check detail page district tag (e.g. ?area=dacia)
            area_links = soup.select('a[href*="area="]')
            for al in area_links:
                area_name = al.get_text(strip=True)
                if self.is_south_zone(area_name):
                    listing.exclusion_reason = f"Южный район: '{area_name}'"
                    return None
                if area_name and listing.district == "Timișoara":
                    listing.district = area_name
                    listing.full_address = f"{area_name}, Timișoara"
                    listing.map_link = self.generate_map_link(address=listing.full_address)

            # 2. Extract description
            desc_el = soup.select_one('.article-description, #description, [itemprop="description"]')
            if desc_el:
                listing.description = self.clean_html(desc_el.get_text())

            # Check full text for any South mentions
            south_m = self.is_south_zone(f"{listing.title} {listing.description}", context=listing.title)
            if south_m:
                listing.exclusion_reason = f"Южный район в описании: '{south_m}'"
                return None

            # 3. High-res photo extraction via native imageList.push script (2000x1500)
            images_from_script = re.findall(r"imageList\.push\(\{\s*src:\s*'(https://[^']+)'", r.text)
            if images_from_script:
                full_photos = []
                for img_url in images_from_script:
                    high_url = img_url.replace("/top/", "/extralarge/").replace("/large/", "/extralarge/")
                    if high_url not in full_photos:
                        full_photos.append(high_url)
                if full_photos:
                    listing.photos = full_photos
            else:
                # Fallback to img tags
                fallback_photos = []
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy")
                    if src and "s3.publi24.ro" in src and not any(k in src for k in ["avatars", "logo"]):
                        high_src = src.replace("/top/", "/extralarge/").replace("/large/", "/extralarge/")
                        if high_src not in fallback_photos:
                            fallback_photos.append(high_src)
                if fallback_photos:
                    listing.photos = fallback_photos

            # 4. Extract specs from attribute table
            specs = {}
            for attr in soup.select('.attribute-item'):
                lbl = attr.select_one('.attribute-label')
                val = attr.select_one('.attribute-value')
                if lbl and val:
                    specs[lbl.get_text(strip=True).lower()] = val.get_text(strip=True)

            if "suprafata utila" in specs:
                area_m = re.search(r'(\d+[\s.,]?\d*)', specs["suprafata utila"])
                if area_m:
                    listing.exact_area = f"{area_m.group(1).strip()} м²"

            if "etaj" in specs:
                listing.floor = self.format_floor(specs["etaj"])

            if "compartimentare" in specs:
                comp = specs["compartimentare"].lower()
                if "decomandat" in comp and "semi" not in comp:
                    listing.building_type = "Раздельная (decomandat)"
                elif "semidecomandat" in comp:
                    listing.building_type = "Полураздельная (semidecomandat)"
                elif "circular" in comp:
                    listing.building_type = "Смежная (circular)"

            if "anul constructiei" in specs:
                year_raw = specs["anul constructiei"]
                m_yr = re.search(r'\b(19\d\d|20\d\d)\b', year_raw)
                if m_yr:
                    year_int = int(m_yr.group(1))
                    listing.build_year = year_int
                    if year_int < 2010:
                        listing.exclusion_reason = f"Год постройки {year_int} (< 2010)"
                        return None
                    listing.building_type = f"{listing.building_type} | Дом {year_int} года" if listing.building_type != "Обычный фонд" else f"Дом {year_int} года"

            # 5. Extract amenities & contacts from full page text
            page_text = f"{listing.title} {listing.description} {r.text}"
            if not listing.build_year:
                parsed_year = self.extract_build_year(page_text)
                if parsed_year:
                    listing.build_year = parsed_year
                    if parsed_year < 2010:
                        listing.exclusion_reason = f"Год постройки {parsed_year} (< 2010)"
                        return None
                    listing.building_type = f"{listing.building_type} | Дом {parsed_year} года" if listing.building_type != "Обычный фонд" else f"Дом {parsed_year} года"
            if not listing.has_boiler:
                listing.has_boiler = self.check_boiler(page_text)
            listing.is_owner = self.check_owner(page_text) or listing.is_owner
            listing.commission_info = "0% (Без комиссии)" if listing.is_owner else "Уточнять (обычно 50%)"

            complex_cand = self.detect_complex(page_text)
            if complex_cand != "Не указан":
                listing.complex_name = complex_cand

            parking_cand = self.analyze_parking(page_text)
            if parking_cand != "Не указано":
                listing.parking_info = parking_cand

            # Exact street address extraction
            street = self.extract_street_address(page_text)
            if street:
                listing.street = street
                if listing.district and listing.district != "Timișoara":
                    listing.full_address = f"{street}, {listing.district}, Timișoara"
                else:
                    listing.full_address = f"{street}, Timișoara"
                listing.map_link = self.generate_map_link(address=listing.full_address)

            # Pets, Availability, Smoking
            listing.pets_policy = self.analyze_pets(page_text)
            listing.availability = self.analyze_availability(page_text)
            listing.smoking_policy = self.analyze_smoking(page_text)

            listing.ac_info = self.analyze_ac(page_text)
            listing.balcony_info = self.analyze_balcony(page_text)
            if listing.deposit_info in ["1 месяц (обычно)", "Не указан"]:
                listing.deposit_info = self.analyze_deposit(page_text)

            found_phone = self.extract_phone(page_text)
            if found_phone:
                listing.phone = found_phone

        except Exception as e:
            print(f"[Publi24] Error enriching details for {listing.url}: {e}")

        return listing
