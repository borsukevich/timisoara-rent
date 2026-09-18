from curl_cffi import requests
from bs4 import BeautifulSoup
import json
from typing import List, Optional
from scrapers.base import BaseScraper, Listing

class StoriaScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("storia", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[Storia] Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            next_data = soup.find("script", id="__NEXT_DATA__")
            if not next_data:
                print("[Storia] Could not find __NEXT_DATA__")
                return []

            data = json.loads(next_data.string)
            page_props = data.get("props", {}).get("pageProps", {})
            items = (page_props.get("data") or {}).get("searchAds", {}).get("items", [])

            seen_slugs = set()
            for item in items:
                if not isinstance(item, dict):
                    continue

                ad_id = str(item.get("id"))
                title = (item.get("title") or "").strip()
                slug = item.get("slug") or ""
                if slug:
                    if slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                url = f"https://www.storia.ro/ro/oferta/{slug}" if slug else item.get("href", "")

                is_promoted = False
                created_str = item.get("createdAtFirst") or item.get("dateCreated")

                # Price
                tp = item.get("totalPrice") or {}
                price_val = tp.get("value")
                price_curr = tp.get("currency", "EUR")
                price = f"{price_val} {price_curr}" if price_val else ""

                # Price filter: strictly 400 - 800 EUR
                price_eur = self.parse_price_eur(price)
                if price_eur is not None and (price_eur < 400 or price_eur > 800):
                    continue

                # Rooms & Area
                rooms_raw = str(item.get("roomsNumber") or "")
                rooms_map = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "MORE": "5+"}
                rooms_clean = rooms_map.get(rooms_raw, rooms_raw)
                rooms = f"{rooms_clean} camere" if rooms_clean else "3+ camere"

                area_val = item.get("areaInSquareMeters") or ""
                exact_area = f"{area_val} м²" if area_val else "от 55 м²"

                # Floor
                raw_floor = item.get("floorNumber") or ""
                floor = self.format_floor(str(raw_floor))

                # Location & Address
                loc_obj = item.get("location") or {}
                rev_geo = loc_obj.get("reverseGeocoding") or {}
                locations_list = rev_geo.get("locations") or []
                district = "Timișoara"
                for l in locations_list:
                    if isinstance(l, dict) and l.get("locationLevel") == "district":
                        district = l.get("name")
                        break

                addr_obj = loc_obj.get("address") or {}
                street_obj = addr_obj.get("street") or {}
                street = street_obj.get("name") if isinstance(street_obj, dict) else ""

                loc_parts = []
                if street:
                    loc_parts.append(street)
                if district and district != "Timișoara":
                    loc_parts.append(district)
                loc_parts.append("Timișoara")
                full_address = ", ".join(loc_parts)

                map_link = self.generate_map_link(address=full_address)

                # Photos
                photos = []
                for img in (item.get("images") or []):
                    if isinstance(img, dict):
                        img_url = img.get("large") or img.get("medium")
                        if img_url and img_url not in photos:
                            photos.append(img_url)

                # Description snippet
                desc = self.clean_html(item.get("shortDescription") or "")

                # Analysis
                full_text = f"{title} {desc}"
                has_boiler = self.check_boiler(full_text)
                
                is_private = bool(item.get("isPrivateOwner", False)) or item.get("advertiserType") == "private"
                has_agency = bool(item.get("agency") or item.get("advertiserType") == "agency" or any(k in full_text.lower() for k in [
                    "agentie imobiliara", "agenție imobiliară", "agent imobiliar", "consultant imobiliar", "comision agentie", "comision standard"
                ]))

                if has_agency:
                    is_owner = False
                elif is_private:
                    is_owner = True
                else:
                    is_owner = self.check_owner(full_text)

                has_zero_comm = self.check_zero_commission(full_text)
                if has_zero_comm:
                    commission_info = "0% (Без комиссии)"
                elif is_owner:
                    commission_info = "0% (Без комиссии)"
                elif has_agency:
                    commission_info = "Стандартная (обычно 50%)"
                else:
                    commission_info = "Уточнять (обычно 50%)"

                listings.append(Listing(
                    uid=f"storia_{slug}" if slug else f"storia_{ad_id}",
                    source="storia",
                    title=title,
                    price=price,
                    url=url,
                    rooms=rooms,
                    exact_area=exact_area,
                    floor=floor,
                    district=district,
                    street=street or "",
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
                    description=desc,
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=created_str,
                    is_today=True
                ))

        except Exception as e:
            print(f"[Storia] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Optional[Listing]:
        """Fetches the full offer page on Storia to extract complete description, all photos, phone, and specs."""
        try:
            r = requests.get(listing.url, impersonate="chrome124", timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data:
                    data = json.loads(next_data.string)
                    ad = data.get("props", {}).get("pageProps", {}).get("ad") or {}

                    # 1. Full description
                    raw_desc = ad.get("description", "")
                    if raw_desc:
                        full_desc = self.clean_html(raw_desc)
                        if full_desc:
                            listing.description = full_desc

                    # 2. Photos: get all high-resolution photos
                    images = ad.get("images", [])
                    if images:
                        full_photos = []
                        for img in images:
                            if isinstance(img, dict):
                                img_url = img.get("large") or img.get("medium")
                                if img_url and img_url not in full_photos:
                                    full_photos.append(img_url)
                        if full_photos:
                            listing.photos = full_photos

                    # 3. Owner Phone
                    owner = ad.get("owner", {}) or {}
                    phones = owner.get("phones", [])
                    if phones:
                        listing.phone = self.extract_phone(phones[0])

                    # 4. Characteristics
                    chars = {c.get("key"): c.get("value") for c in ad.get("characteristics", []) if isinstance(c, dict)}

                    # Deposit
                    if "deposit" in chars and chars["deposit"]:
                        dep_val = chars["deposit"]
                        listing.deposit_info = f"{dep_val} €" if str(dep_val).isdigit() else str(dep_val)

                    # Heating / Boiler
                    heating = str(chars.get("heating", "")).lower()
                    if any(k in heating for k in ["gas", "individual", "centrala", "gaz"]):
                        listing.has_boiler = True

                    # Floor
                    floor_no = chars.get("floor_no", "")
                    building_floors = chars.get("building_floors_num", "")
                    if floor_no:
                        cur_floor = str(floor_no).replace("floor_", "")
                        if cur_floor == "ground":
                            cur_floor = "1 (Parter)"
                        if building_floors:
                            listing.floor = f"{cur_floor} из {building_floors} этаж"
                        else:
                            listing.floor = f"{cur_floor} этаж"

                    # Building year
                    build_year = chars.get("build_year")
                    if not build_year:
                        build_year = self.extract_build_year(f"{listing.title} {listing.description}")
                    if build_year:
                        try:
                            year_int = int(build_year)
                            listing.build_year = year_int
                            listing.building_type = f"Дом {year_int} года"
                        except Exception:
                            pass

                    # 5. Full text analysis for amenities
                    full_text = f"{listing.title} {listing.description}"
                    if not listing.has_boiler:
                        listing.has_boiler = self.check_boiler(full_text)
                    has_agency = bool(ad.get("agency") or ad.get("advertiserType") == "agency" or any(k in full_text.lower() for k in [
                        "agentie imobiliara", "agenție imobiliară", "agent imobiliar", "consultant imobiliar", "comision agentie", "comision standard"
                    ]))
                    is_private = bool(ad.get("isPrivateOwner", False)) or ad.get("advertiserType") == "private"

                    if has_agency:
                        listing.is_owner = False
                    elif is_private:
                        listing.is_owner = True
                    elif not listing.is_owner:
                        listing.is_owner = self.check_owner(full_text)

                    has_zero_comm = self.check_zero_commission(full_text)
                    if has_zero_comm:
                        listing.commission_info = "0% (Без комиссии)"
                    elif listing.is_owner:
                        listing.commission_info = "0% (Без комиссии)"
                    elif has_agency:
                        listing.commission_info = "Стандартная (обычно 50%)"
                    else:
                        listing.commission_info = "Уточнять (обычно 50%)"

                    complex_cand = self.detect_complex(full_text)
                    if complex_cand != "Не указан":
                        listing.complex_name = complex_cand

                    parking_cand = self.analyze_parking(full_text)
                    if parking_cand != "Не указано":
                        listing.parking_info = parking_cand

                    # Exact street address extraction
                    street = self.extract_street_address(full_text)
                    if street and not listing.street:
                        listing.street = street
                        if listing.district and listing.district != "Timișoara":
                            listing.full_address = f"{street}, {listing.district}, Timișoara"
                        else:
                            listing.full_address = f"{street}, Timișoara"
                        listing.map_link = self.generate_map_link(address=listing.full_address)

                    # Pets, Availability, Smoking
                    listing.pets_policy = self.analyze_pets(full_text)
                    listing.availability = self.analyze_availability(full_text)
                    listing.smoking_policy = self.analyze_smoking(full_text)

                    listing.ac_info = self.analyze_ac(full_text)
                    listing.balcony_info = self.analyze_balcony(full_text)
                    if listing.deposit_info in ["1 месяц (обычно)", "Не указан"]:
                        listing.deposit_info = self.analyze_deposit(full_text)
                    listing.commission_info = "0% (Без комиссии)" if listing.is_owner else "Уточнять (обычно 50%)"
        except Exception as e:
            print(f"[Storia] Error enriching {listing.url}: {e}")
        return listing
