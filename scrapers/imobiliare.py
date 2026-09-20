from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import json
from typing import List, Optional
from scrapers.base import BaseScraper, Listing

class ImobiliareScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("imobiliare", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            html_text = ""
            try:
                r = requests.get(self.url, impersonate="chrome124", timeout=12)
                if r.status_code == 200:
                    html_text = r.text
            except Exception:
                pass

            if not html_text:
                import urllib.request
                req = urllib.request.Request(
                    self.url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html_text = resp.read().decode("utf-8", errors="replace")

            if not html_text:
                print(f"[Imobiliare] Failed to retrieve page content")
                return []

            soup = BeautifulSoup(html_text, "html.parser")
            cards = soup.select("[data-id]")

            for card in cards:
                card_id = card.get("data-id")
                if not card_id:
                    continue

                link_el = card.find("a", href=lambda h: h and "/oferta/" in h) or card.find("a", href=True)
                if not link_el:
                    continue
                href = link_el.get("href", "")
                url = f"https://www.imobiliare.ro{href}" if href.startswith("/") else href

                # Title: prefer aria-label which has full descriptive text (e.g. "Apartament 3 camere de inchiriat, Centrala Proprie...")
                aria_label = link_el.get("aria-label", "").strip()
                data_name = card.get("data-name", "").strip()
                title_el = card.find(["h2", "h3"])
                title_text = title_el.get_text(strip=True) if title_el else ""
                title = aria_label or data_name or title_text or "Apartament Timișoara"

                city = card.get("data-city", "")
                if city and not self.is_timisoara_location(city):
                    continue
                if not self.is_timisoara_location(title):
                    continue

                classes = " ".join(card.get("class", []))
                is_promoted = "promovat" in classes.lower() or bool(card.select('.promovat, [class*="promovat"]'))

                # Date check from .posted-at
                p_el = card.select_one('.posted-at, [class*="posted-at"]')
                posted_at = p_el.get_text(strip=True) if p_el else ""
                is_fresh = bool(posted_at and any(k in posted_at.lower() for k in ["azi", "ore", "acum"]))

                # Price: prefer data-item-price
                data_price = card.get("data-item-price")
                if data_price and data_price.isdigit():
                    price = f"{data_price} €"
                else:
                    price_match = re.search(r'(\d+[\s.]?\d*)\s*€', card.get_text())
                    price = f"{price_match.group(1).replace(' ', '')} €" if price_match else ""

                if not price:
                    price = self.extract_price_from_text(f"{title} {card.get_text()}") or ""

                # Price filter: strictly 400 - 800 EUR
                price_eur = self.parse_price_eur(price)
                if price_eur is not None and (price_eur < 400 or price_eur > 800):
                    continue

                # Rooms and area
                rooms = "3 camere"
                cat3 = card.get("data-category3", "")
                if "bedroom" in cat3:
                    m_bed = re.search(r'(\d+)', cat3)
                    if m_bed:
                        rooms = f"{m_bed.group(1)} camere"

                data_surface = card.get("data-surface")
                if data_surface and data_surface.isdigit():
                    exact_area = f"{data_surface} м²"
                else:
                    area_match = re.search(r'(\d+[\s.,]?\d*)\s*mp', card.get_text(), re.IGNORECASE)
                    exact_area = f"{area_match.group(1).strip()} м²" if area_match else "от 55 м²"

                # Floor: check card-floor_number or regex
                floor_attr = card.select_one('[data-cy="card-floor_number"]')
                if floor_attr:
                    floor_txt = floor_attr.get_text(strip=True)
                else:
                    floor_match = re.search(r'(Etaj\s*\d+(?:\s*/\s*\d+)?|Parter|Demisol|Mansarda)', card.get_text(), re.IGNORECASE)
                    floor_txt = floor_match.group(1) if floor_match else "Не указан"
                floor = self.format_floor(floor_txt)

                # Location & District
                district = card.get("data-area") or "Timișoara"
                if not district or district == "Timisoara":
                    loc_match = re.search(r'([A-Za-zĂÎÂȘȚăîâșț\s-]+),\s*Timișoara', card.get_text())
                    if loc_match:
                        district = loc_match.group(1).strip()
                if not self.is_timisoara_location(district):
                    continue
                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"
                map_link = self.generate_map_link(address=full_address)

                # Photos from gallery inside card
                photos = []
                for img in card.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and "roamcdn.net" in src and src not in photos:
                        photos.append(src)

                # Description snippet in card
                desc_div = card.select_one('.text-body-sm')
                card_desc = desc_div.get_text(strip=True) if desc_div else ""

                card_text = card.get_text(" | ", strip=True)
                affiliation = card.get("data-affiliation", "").upper()
                has_agency = bool(
                    affiliation == "AGENTIE"
                    or card.find("a", href=lambda h: h and "/agentie/" in h)
                    or any(k in card_text.lower() for k in ["agentie", "agenție", "consultant imobiliar", "broker", "real estate"])
                )

                if has_agency:
                    is_owner = False
                elif affiliation == "PROPRIETAR":
                    is_owner = True
                else:
                    is_owner = self.check_owner(card_text)

                has_zero_comm = self.check_zero_commission(card_text)
                if has_zero_comm:
                    commission_info = "0% (Без комиссии)"
                elif is_owner:
                    commission_info = "0% (Без комиссии)"
                elif has_agency:
                    commission_info = "Стандартная (обычно 50%)"
                else:
                    commission_info = "Уточнять (обычно 50%)"

                full_text = f"{title} {card_desc} {card_text}"
                has_boiler = self.check_boiler(full_text)
                phone = self.extract_phone(full_text)
                complex_name = self.detect_complex(full_text)
                parking_info = self.analyze_parking(full_text)
                pets_policy = self.analyze_pets(full_text)
                ac_info = self.analyze_ac(full_text)
                balcony_info = self.analyze_balcony(full_text)
                deposit_info = self.analyze_deposit(full_text)
                building_type = self.analyze_building_type(full_text)

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
                    description=card_desc if card_desc else title,
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=posted_at,
                    is_today=is_fresh
                ))

        except Exception as e:
            print(f"[Imobiliare] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Optional[Listing]:
        """Fetches the full offer page on Imobiliare to extract complete description, boiler, phone, etc."""
        try:
            html_text = ""
            try:
                r = requests.get(listing.url, impersonate="chrome124", timeout=10)
                if r.status_code == 200:
                    html_text = r.text
            except Exception:
                pass

            if not html_text:
                import urllib.request
                req = urllib.request.Request(
                    listing.url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    html_text = resp.read().decode("utf-8", errors="replace")

            if html_text:
                soup = BeautifulSoup(html_text, "html.parser")

                # 1. Full description from schema.org / Product
                full_desc = ""
                for s in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(s.string)
                        for it in data.get("@graph", []):
                            if it.get("@type") == "Product" and "description" in it:
                                full_desc = it["description"].strip()
                                break
                    except Exception:
                        pass
                if full_desc:
                    listing.description = full_desc

                # Check breadcrumbs / location
                bc_text = " ".join([b.get_text(strip=True) for b in soup.select('.breadcrumb, .breadcrumbs, [itemprop="breadcrumb"], .localizare, [class*="locat"]')])
                if bc_text and not self.is_timisoara_location(bc_text):
                    listing.exclusion_reason = f"Другой город: {bc_text}"
                    return None

                # 2. Extract characteristics block text
                chars_text = ""
                chars_section = soup.find(id=lambda x: x and "caracteristici" in x)
                if chars_section:
                    chars_text = chars_section.get_text(" ", strip=True)

                content_text = f"{listing.title} {listing.district} {listing.description} {chars_text}"
                if not self.is_timisoara_location(content_text):
                    listing.exclusion_reason = "Описание указывает на другой город/пригород"
                    return None

                # Fallback price extraction
                if not listing.price or self.parse_price_eur(listing.price) is None:
                    p_el = soup.find(class_=lambda c: c and "pret" in str(c).lower()) or soup.find(itemprop="price")
                    if p_el:
                        cand_p = p_el.get_text(strip=True)
                        if cand_p and self.parse_price_eur(cand_p):
                            listing.price = cand_p
                    if not listing.price or self.parse_price_eur(listing.price) is None:
                        cand_p = self.extract_price_from_text(content_text)
                        if cand_p:
                            listing.price = cand_p

                # 3. Floor update if page has exact Etaj X/Y or Etaj X
                m_fl = re.search(r'etaj(?:ul)?[:\s]+(\d+)(?:\s*/\s*(\d+))?', f"{listing.description} {chars_text}", re.IGNORECASE)
                if m_fl:
                    cur = m_fl.group(1)
                    tot = m_fl.group(2)
                    listing.floor = f"{cur} из {tot} этаж" if tot else f"{cur} этаж"

                # 4. Extract phone numbers strictly from text description or specs (avoid SVG/HTML code)
                desc_and_chars = f"{listing.description} {chars_text}"
                phones = re.findall(r'\b(?:(?:\+40|0040|0)7[0-9]{8}|(?:\+40|0)7[0-9]{2}[\s\.-][0-9]{3}[\s\.-][0-9]{3})\b', desc_and_chars)
                if phones:
                    listing.phone = self.extract_phone(phones[0])

                # 5. Analyze features strictly from listing content (title + description + specs)
                content_text = f"{listing.title} {listing.description} {chars_text}"

                # Building year (informative)
                build_year = self.extract_build_year(content_text)
                if build_year:
                    listing.build_year = build_year
                    listing.building_type = f"{listing.building_type} | Дом {build_year} года" if listing.building_type != "Обычный дом" else f"Дом {build_year} года"

                # Check for agency presence on the detailed page
                has_agency_on_page = bool(
                    soup.find("a", href=lambda h: h and "/agentie/" in h)
                    or soup.find(class_=lambda c: c and any(k in str(c).lower() for k in ["agent-contact", "consultant-imobiliar", "agency"]))
                    or any(k in content_text.lower() for k in ["consultant imobiliar", "agent imobiliar", "agentie imobiliara", "agenție imobiliară", "comision standard"])
                )

                if has_agency_on_page:
                    listing.is_owner = False
                elif not listing.is_owner:
                    listing.is_owner = self.check_owner(content_text)

                # Commission check
                is_explicit_zero = self.check_zero_commission(content_text)
                is_standard = "comision standard" in content_text.lower() or bool(
                    soup.find(string=lambda s: s and "comision" in str(s).lower() and "standard" in str(s).lower())
                )

                if is_explicit_zero:
                    listing.commission_info = "0% (Без комиссии)"
                elif listing.is_owner:
                    listing.commission_info = "0% (Без комиссии)"
                elif is_standard or has_agency_on_page:
                    listing.commission_info = "Стандартная (обычно 50%)"
                else:
                    listing.commission_info = "Уточнять (обычно 50%)"

                complex_cand = self.detect_complex(content_text)
                if complex_cand != "Не указан":
                    listing.complex_name = complex_cand

                parking_cand = self.analyze_parking(content_text)
                if parking_cand != "Не указано":
                    listing.parking_info = parking_cand

                # Exact street address extraction
                street = self.extract_street_address(content_text)
                if street:
                    listing.street = street
                    if listing.district and listing.district != "Timișoara":
                        listing.full_address = f"{street}, {listing.district}, Timișoara"
                    else:
                        listing.full_address = f"{street}, Timișoara"
                    listing.map_link = self.generate_map_link(address=listing.full_address)

                # Pets, Availability, Smoking
                listing.pets_policy = self.analyze_pets(content_text)
                listing.availability = self.analyze_availability(content_text)
                listing.smoking_policy = self.analyze_smoking(content_text)

                listing.ac_info = self.analyze_ac(content_text)
                listing.balcony_info = self.analyze_balcony(content_text)
                listing.deposit_info = self.analyze_deposit(content_text)
                if not build_year:
                    listing.building_type = self.analyze_building_type(content_text)
        except Exception as e:
            print(f"[Imobiliare] Error enriching {listing.url}: {e}")
        return listing
