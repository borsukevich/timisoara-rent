from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from typing import List, Optional
from scrapers.base import BaseScraper, Listing
from scrapers.publi24 import EXCLUDED_SOUTH_PATTERNS, PREFERRED_NORTH_CENTRAL_ZONES

class RentolaScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("rentola", url)

    def is_north_zone(self, text: str) -> bool:
        t = text.lower()
        for pat in PREFERRED_NORTH_CENTRAL_ZONES:
            if re.search(r'\b' + pat, t, re.IGNORECASE):
                return True
        return False

    def is_south_zone(self, text: str, context: str = "") -> Optional[str]:
        """Returns the matched excluded southern zone, or None if in North/Center."""
        t = text.lower()
        for pat in EXCLUDED_SOUTH_PATTERNS:
            m = re.search(r'\b' + pat, t, re.IGNORECASE)
            if m:
                if context and any(re.search(r'\b' + sp, context, re.IGNORECASE) for sp in EXCLUDED_SOUTH_PATTERNS):
                    return m.group(0)
                if context and self.is_north_zone(context):
                    return None
                return m.group(0)
        return None

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[Rentola] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            tiles = soup.select('[data-testid="propertyTile"]')
            if not tiles:
                tiles = soup.select('.grid > div.xl\\:hidden, .grid > div')

            seen_urls = set()

            for tile in tiles:
                link = tile.select_one('a[href*="/en/listings/"]')
                if not link:
                    continue
                href = link.get('href', '')
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)

                full_url = f"https://rentola.ro{href}" if href.startswith('/') else href

                slug_match = re.search(r'/listings/([^/?#]+)', href)
                slug = slug_match.group(1) if slug_match else ""
                m_id = re.search(r'-([pP][a-zA-Z0-9]+)$', slug)
                ad_id = m_id.group(1) if m_id else slug

                # Title from slug
                raw_words = re.sub(r'-[pP][a-zA-Z0-9]+$', '', slug).split('-')
                title = " ".join(raw_words).capitalize() if raw_words else "Apartament Timișoara"

                # Address / location
                addr_p = tile.select_one('p.text-grey-400')
                addr = addr_p.get_text(strip=True) if addr_p else "Timișoara"

                # Location checks
                if not self.is_timisoara_location(addr) or not self.is_timisoara_location(title):
                    continue

                if self.is_south_zone(addr, context=addr) or self.is_south_zone(title, context=title):
                    continue

                # Price
                price_p = tile.select_one('p.text-base.font-bold.text-blue-300, p[class*="font-bold"]')
                price_raw = price_p.get_text(strip=True) if price_p else ""
                price = re.sub(r'\s*/\s*month', '', price_raw, flags=re.IGNORECASE).strip()

                if not price or self.parse_price_eur(price) is None:
                    price = self.extract_price_from_text(tile.get_text()) or ""

                price_eur = self.parse_price_eur(price)
                if price_eur is not None and (price_eur < 400 or price_eur > 800):
                    continue

                # Area
                title_p = tile.select_one('p.text-base.font-medium.text-blue-300')
                area_text = title_p.get_text(strip=True) if title_p else ""
                m_area = re.search(r'(\d+[\s.,]?\d*)\s*m[²2]?', area_text)
                exact_area = f"{m_area.group(1)} м²" if m_area else "от 55 м²"

                # District
                district = "Timișoara"
                cand_dist = addr.split(',')[0].strip()
                if cand_dist.lower() not in ["timisoara", "timișoara", "romania"] and len(cand_dist) >= 3:
                    if not any(cand_dist.lower().startswith(p) for p in ["strada", "str.", "aleea"]):
                        district = cand_dist

                # Photos preview
                photos = []
                for img in tile.select('img'):
                    src = img.get('src')
                    if src and "rentola.com" in src:
                        m_orig = re.search(r'https%3A%2F%2F[^\s&]+', src)
                        if m_orig:
                            orig = urllib.parse.unquote(m_orig.group(0))
                            if orig not in photos:
                                photos.append(orig)
                        elif src not in photos:
                            photos.append(src)

                full_address = addr if "timișoara" in addr.lower() or "timisoara" in addr.lower() else f"{addr}, Timișoara"
                map_link = self.generate_map_link(address=full_address)

                listings.append(Listing(
                    uid=f"rentola_{ad_id}",
                    source="rentola",
                    title=title,
                    price=price,
                    url=full_url,
                    rooms="3 camere",
                    exact_area=exact_area,
                    floor="Не указан",
                    district=district,
                    full_address=full_address,
                    map_link=map_link,
                    photos=photos,
                    is_promoted=False,
                    is_today=True
                ))

        except Exception as e:
            print(f"[Rentola] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Optional[Listing]:
        try:
            r = requests.get(listing.url, impersonate="chrome124", timeout=12)
            if r.status_code != 200:
                return listing

            soup = BeautifulSoup(r.text, "html.parser")

            # 1. More detailed title from H2 if present
            for heading in soup.select('h2'):
                txt = heading.get_text(strip=True)
                if len(txt) > 10 and not any(k in txt.lower() for k in ['search', 'similar', 'popular', 'tenants', 'about', 'landlords', 'property']):
                    listing.title = txt
                    break

            # 2. Description from whitespace-pre-line container
            desc_el = soup.select_one('div.whitespace-pre-line')
            if desc_el:
                listing.description = self.clean_html(desc_el.get_text())

            # 3. Facts table extraction
            facts = {}
            for p in soup.select('p'):
                sibling = p.find_next_sibling('p')
                if sibling and p.parent == sibling.parent and len(list(p.parent.children)) == 2:
                    k = p.get_text(strip=True).lower()
                    v = sibling.get_text(strip=True)
                    if len(k) < 30 and len(v) < 50:
                        facts[k] = v

            if "size" in facts:
                m_sz = re.search(r'(\d+[\s.,]?\d*)', facts["size"])
                if m_sz:
                    clean_sz = m_sz.group(1).replace(' ', '')
                    listing.exact_area = f"{clean_sz} м²"

            if "price" in facts:
                fact_price = facts["price"].replace("€", "").strip()
                if fact_price.isdigit():
                    listing.price = f"{fact_price} €"

            if listing.district == "Timișoara":
                for pat in PREFERRED_NORTH_CENTRAL_ZONES:
                    m_z = re.search(r'\b(' + pat + r')', f"{listing.title} {listing.full_address}", re.IGNORECASE)
                    if m_z:
                        listing.district = m_z.group(1).capitalize()
                        break

            if "parking" in facts and "yes" in facts["parking"].lower():
                listing.parking_info = "✅ Да (парковочное место)"

            if "terrace" in facts and "yes" in facts["terrace"].lower():
                listing.balcony_info = "✅ Есть (терраса)"
            elif "balcony" in facts and "yes" in facts["balcony"].lower():
                listing.balcony_info = "✅ Есть (балкон)"

            if "year built" in facts and facts["year built"].isdigit():
                yr = int(facts["year built"])
                listing.build_year = yr
                listing.building_type = f"🏢 Новостройка | Дом {yr} года" if yr >= 2018 else f"Дом {yr} года"

            if "available from" in facts:
                listing.availability = facts["available from"]

            if "smoking allowed" in facts:
                sm = facts["smoking allowed"].lower()
                if "no" in sm:
                    listing.smoking_policy = "🚭 В квартире запрещено"
                elif "yes" in sm:
                    listing.smoking_policy = "🚬 Разрешено"

            if "pets allowed" in facts:
                pet = facts["pets allowed"].lower()
                if "yes" in pet:
                    listing.pets_policy = "✅ Разрешены"
                elif "no" in pet:
                    listing.pets_policy = "❌ Запрещены"

            # 4. Strict geographic & South zone verification on full content
            full_content = f"{listing.title} {listing.district} {listing.description}"
            if not self.is_timisoara_location(full_content):
                listing.exclusion_reason = "Описание указывает на другой город/пригород"
                return None

            south_m = self.is_south_zone(full_content, context=listing.title)
            if south_m:
                listing.exclusion_reason = f"Южный район: '{south_m}'"
                return None

            # 5. Extract floor, boiler, complex, owner/agency from full text
            m_fl = re.search(r'etaj(?:ul)?[:\s]+(\d+)(?:\s*/\s*(\d+))?', full_content, re.IGNORECASE)
            if m_fl:
                cur = m_fl.group(1)
                tot = m_fl.group(2)
                listing.floor = f"{cur} из {tot} этаж" if tot else f"{cur} этаж"

            listing.has_boiler = self.check_boiler(full_content)
            complex_name = self.detect_complex(full_content)
            if complex_name != "Не указан":
                listing.complex_name = complex_name

            has_agency = any(k in full_content.lower() for k in [
                "agentie", "agenție", "real estate", "comision", "broker", "consultant imobiliar"
            ])
            is_owner = not has_agency and self.check_owner(full_content)
            listing.is_owner = is_owner
            listing.commission_info = "0% (Без комиссии)" if is_owner else "Стандартная (обычно 50%)"

            # 6. High-res gallery photos
            full_photos = []
            for img in soup.select('img'):
                src = img.get('src')
                if src and "rentola.com" in src:
                    m_orig = re.search(r'https%3A%2F%2F[^\s&]+', src)
                    if m_orig:
                        orig = urllib.parse.unquote(m_orig.group(0))
                        if orig not in full_photos:
                            full_photos.append(orig)
                    elif src not in full_photos:
                        full_photos.append(src)

            if full_photos:
                listing.photos = full_photos[:20]

            found_phone = self.extract_phone(full_content)
            if found_phone:
                listing.phone = found_phone

        except Exception as e:
            print(f"[Rentola] Error enriching details for {listing.url}: {e}")

        return listing
