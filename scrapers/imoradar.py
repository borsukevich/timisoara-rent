from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import json
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
            cards = soup.select("article[data-id]")
            seen_ids = set()

            for card in cards:
                card_id = card.get("data-id") or card.get("data-listing-id")
                if not card_id or card_id in seen_ids:
                    continue
                seen_ids.add(card_id)

                link_el = card.find("a", href=True)
                if not link_el:
                    continue
                href = link_el.get("href", "")
                url = f"https://www.imoradar24.ro{href}" if href.startswith("/") else href

                # Title: prefer aria-label, data-name, or h2/h3
                aria_label = link_el.get("aria-label", "").strip()
                data_name = card.get("data-name", "").strip()
                h_el = card.find(["h2", "h3", "h4"])
                title_text = h_el.get_text(strip=True) if h_el else ""
                title = aria_label or data_name or title_text or "Apartament Timișoara"

                # Classes & Promoted
                classes = " ".join(card.get("class", []))
                is_promoted = "promovat" in classes.lower() or bool(card.select('.promovat, [class*="promovat"]'))

                # Price: prefer data-item-price
                data_price = card.get("data-item-price")
                if data_price and data_price.isdigit():
                    price = f"{data_price} €"
                else:
                    price_match = re.search(r'(\d+[\s.]?\d*)\s*(?:€|EUR)', card.get_text())
                    price = f"{price_match.group(1).replace(' ', '')} €" if price_match else ""

                # Rooms
                rooms = "3 camere"
                cat3 = card.get("data-category3", "")
                if "bedroom" in cat3:
                    m_bed = re.search(r'(\d+)', cat3)
                    if m_bed:
                        rooms = f"{m_bed.group(1)} camere"
                else:
                    rooms_match = re.search(r'(\d+)\s*camere', card.get_text(), re.IGNORECASE)
                    if rooms_match:
                        rooms = f"{rooms_match.group(1)} camere"

                # Surface & Area
                data_surface = card.get("data-surface")
                if data_surface:
                    try:
                        exact_area = f"{int(float(data_surface))} м²"
                    except Exception:
                        exact_area = f"{data_surface} м²"
                else:
                    area_match = re.search(r'(\d+[\s.,]?\d*)\s*mp', card.get_text(), re.IGNORECASE)
                    exact_area = f"{area_match.group(1).strip()} м²" if area_match else "от 55 м²"

                # Floor
                floor_attr = card.select_one('[data-cy="card-floor_number"]')
                if floor_attr:
                    floor_txt = floor_attr.get_text(strip=True)
                else:
                    floor_match = re.search(r'(Etaj\s*\d+(?:\s*/\s*\d+)?|Parter|Demisol|Mansarda)', card.get_text(), re.IGNORECASE)
                    floor_txt = floor_match.group(1) if floor_match else "Не указан"
                floor = self.format_floor(floor_txt)

                # District
                district = card.get("data-area") or "Timișoara"
                if not district or district == "Timisoara":
                    loc_match = re.search(r'([A-Za-zĂÎÂȘȚăîâșț\s-]+),\s*Timișoara', card.get_text())
                    if loc_match:
                        district = loc_match.group(1).strip()
                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"
                map_link = self.generate_map_link(address=full_address)

                # Photos directly in card
                photos = []
                for img in card.find_all("img"):
                    src = img.get("src") or img.get("data-src") or ""
                    if any(cdn in src for cdn in ["roamcdn.net", "apollo.olxcdn.com", "publi24"]) and src not in photos:
                        photos.append(src)

                # Description snippet
                desc_div = card.select_one('.text-body-sm')
                card_desc = desc_div.get_text(strip=True) if desc_div else ""

                affiliation = card.get("data-affiliation", "").upper()
                is_owner = (affiliation == "PROPRIETAR") or "comision 0%" in card.get_text().lower() or self.check_owner(card.get_text())

                card_text = card.get_text(" | ", strip=True)
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
                commission_info = "0% (Без комиссии)" if is_owner else "Уточнять (обычно 50%)"

                p_el = card.select_one('.posted-at, [class*="posted-at"]')
                posted_at = p_el.get_text(strip=True) if p_el else ""

                listings.append(Listing(
                    uid=f"imoradar_{card_id.replace('LT_', '')}",
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
                    description=card_desc if card_desc else title,
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=posted_at or "Azi",
                    is_today=True
                ))

        except Exception as e:
            print(f"[ImoRadar24] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Listing:
        """Fetches the full offer page on ImoRadar24 (or follows external redirect) to extract complete description, all photos, phone, etc."""
        try:
            r = requests.get(listing.url, impersonate="chrome124", timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")

                # 1. Full description from schema.org
                full_desc = ""
                for s in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(s.string)
                        for it in data.get("@graph", []):
                            if it.get("@type") in ["Product", "Apartment", "RealEstateListing"] and "description" in it:
                                full_desc = it["description"].strip()
                                break
                    except Exception:
                        pass
                if not full_desc:
                    desc_el = soup.select_one('.description, [data-cy="description"]')
                    if desc_el:
                        full_desc = desc_el.get_text(" ", strip=True)

                if full_desc:
                    listing.description = full_desc

                # 2. Photos: extract ONLY genuine high-resolution gallery images (1200w / 900w)
                high_res_photos = []
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src") or ""
                    if not src:
                        continue
                    if any(bad in src for bad in ["thumb-140w", "listing-thumb", "thumb-400w", "logo", "icon"]):
                        continue
                    if any(good in src for good in ["gallery-full-1200w", "gallery-main-900w", "apollo.olxcdn.com", "publi24"]):
                        fname = src.split("/")[-1]
                        if not any(fname in p for p in high_res_photos):
                            high_res_photos.append(src)

                if high_res_photos:
                    listing.photos = high_res_photos
                elif "publicată fără poze" in r.text or "Proprietate publicată fără poze" in r.text:
                    listing.photos = []

                # 3. Characteristics text
                chars_text = ""
                chars_section = soup.find(id=lambda x: x and "caracteristici" in x)
                if chars_section:
                    chars_text = chars_section.get_text(" ", strip=True)

                # 4. Floor update if page has exact Etaj X/Y
                m_fl = re.search(r'etaj(?:ul)?[:\s]+(\d+)(?:\s*/\s*(\d+))?', f"{listing.description} {chars_text}", re.IGNORECASE)
                if m_fl:
                    cur = m_fl.group(1)
                    tot = m_fl.group(2)
                    listing.floor = f"{cur} из {tot} этаж" if tot else f"{cur} этаж"

                # 5. Extract phone numbers strictly from text description or specs
                desc_and_chars = f"{listing.description} {chars_text}"
                phones = re.findall(r'\b(?:(?:\+40|0040|0)7[0-9]{8}|(?:\+40|0)7[0-9]{2}[\s\.-][0-9]{3}[\s\.-][0-9]{3})\b', desc_and_chars)
                if phones:
                    listing.phone = self.extract_phone(phones[0])

                # 6. Analyze features strictly from listing content
                content_text = f"{listing.title} {listing.description} {chars_text}"
                listing.has_boiler = self.check_boiler(content_text) or listing.has_boiler
                listing.is_owner = self.check_owner(content_text) or listing.is_owner

                complex_cand = self.detect_complex(content_text)
                if complex_cand != "Не указан":
                    listing.complex_name = complex_cand

                parking_cand = self.analyze_parking(content_text)
                if parking_cand != "Не указано":
                    listing.parking_info = parking_cand

                listing.ac_info = self.analyze_ac(content_text)
                listing.balcony_info = self.analyze_balcony(content_text)
                if listing.deposit_info in ["1 месяц (обычно)", "Не указан"]:
                    listing.deposit_info = self.analyze_deposit(content_text)
                listing.building_type = self.analyze_building_type(content_text)
                listing.commission_info = "0% (Без комиссии)" if listing.is_owner else "Уточнять (обычно 50%)"
        except Exception as e:
            print(f"[ImoRadar24] Error enriching {listing.url}: {e}")
        return listing
