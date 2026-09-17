from curl_cffi import requests
from bs4 import BeautifulSoup
import json
from typing import List
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

            for item in items:
                if not isinstance(item, dict):
                    continue

                ad_id = str(item.get("id"))
                title = (item.get("title") or "").strip()
                slug = item.get("slug") or ""
                url = f"https://www.storia.ro/ro/oferta/{slug}" if slug else item.get("href", "")

                is_promoted = bool(item.get("isPromoted", False))

                # Price
                tp = item.get("totalPrice") or {}
                price_val = tp.get("value")
                price_curr = tp.get("currency", "EUR")
                price = f"{price_val} {price_curr}" if price_val else ""

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
                        if img_url:
                            photos.append(img_url)

                # Description
                desc = self.clean_html(item.get("shortDescription") or "")

                # Analysis
                full_text = f"{title} {desc}"
                has_boiler = self.check_boiler(full_text)
                is_owner = bool(item.get("isPrivateOwner", False)) or self.check_owner(full_text)
                phone = self.extract_phone(full_text)

                dev_title = item.get("developmentTitle") or ""
                complex_name = dev_title.strip() if dev_title.strip() else self.detect_complex(full_text)
                
                parking_info = self.analyze_parking(full_text)
                pets_policy = self.analyze_pets(full_text)
                ac_info = self.analyze_ac(full_text)
                balcony_info = self.analyze_balcony(full_text)
                deposit_info = self.analyze_deposit(full_text)
                building_type = self.analyze_building_type(full_text)
                commission_info = "0% (Без комиссии)" if is_owner else "Уточнять (обычно 50%)"

                listings.append(Listing(
                    uid=f"storia_{ad_id}",
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
                    date_text=item.get("createdAtFirst") or item.get("dateCreated"),
                    is_today=True
                ))

        except Exception as e:
            print(f"[Storia] Exception while fetching: {e}")

        return listings
