from curl_cffi import requests
import json
import re
from typing import List
from scrapers.base import BaseScraper, Listing

class OLXScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("olx", url)

    def fetch_listings(self) -> List[Listing]:
        listings = []
        try:
            r = requests.get(self.url, impersonate="chrome124", timeout=15)
            if r.status_code != 200:
                print(f"[OLX] Error: HTTP {r.status_code}")
                return []

            m = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', r.text)
            if not m:
                print("[OLX] Could not find __PRERENDERED_STATE__")
                return []

            inner_str = json.loads(m.group(1))
            data = json.loads(inner_str)
            ads = data.get("listing", {}).get("listing", {}).get("ads", [])

            for ad in ads:
                ad_id = str(ad.get("id"))
                title = (ad.get("title") or "").strip()
                url = ad.get("url", "")

                promo = ad.get("promotion", {})
                is_promoted = bool(ad.get("isPromoted") or promo.get("top_ad") or promo.get("highlighted"))

                # Check if it is a bumped old ad (created > 2 days ago)
                created_str = ad.get("createdTime")
                if created_str:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_str.strip())
                        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                        age_days = (now - dt).total_seconds() / 86400
                        if age_days > 2.0:
                            is_promoted = True  # Treat bumped old ads as promoted so they are skipped
                    except Exception:
                        pass

                # Description
                raw_desc = ad.get("description", "")
                desc = self.clean_html(raw_desc)

                # Price
                price_obj = ad.get("price", {})
                price = price_obj.get("displayValue", "")
                if not price and "regularPrice" in price_obj:
                    val = price_obj["regularPrice"].get("value")
                    curr = price_obj["regularPrice"].get("currencyCode", "EUR")
                    price = f"{val} {curr}"

                # Photos (high-res)
                raw_photos = ad.get("photos", [])
                photos = []
                for p in raw_photos:
                    if isinstance(p, str):
                        photos.append(p.replace("540x720", "1000x750"))
                    elif isinstance(p, dict) and "link" in p:
                        photos.append(p["link"].replace("{width}x{height}", "1000x750"))

                # Parameters
                rooms = "3 camere"
                exact_area = ""
                raw_floor = ""
                params = ad.get("params", [])
                for p in params:
                    k = p.get("key")
                    v = p.get("value", {}).get("label") if isinstance(p.get("value"), dict) else str(p.get("value", ""))
                    if k == "number_of_rooms":
                        rooms = v
                    elif k == "m":
                        exact_area = v if "m" in v else f"{v} м²"
                    elif k in ["floor", "floor_select"]:
                        raw_floor = v

                floor = self.format_floor(raw_floor)

                # Location & Coordinates
                loc = ad.get("location", {})
                district = loc.get("districtName") or "Timișoara"
                city = loc.get("cityName") or "Timișoara"
                full_address = f"{district}, {city}" if district != city else city

                map_data = ad.get("map", {})
                lat = map_data.get("lat")
                lon = map_data.get("lon")
                map_link = self.generate_map_link(lat, lon, full_address)

                # Analysis
                full_text = f"{title} {desc}"
                has_boiler = self.check_boiler(full_text)
                is_owner = self.check_owner(full_text) or not ad.get("isBusiness", True)
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
                    uid=f"olx_{ad_id}",
                    source="olx",
                    title=title,
                    price=price,
                    url=url,
                    rooms=rooms,
                    exact_area=exact_area or "от 55 м²",
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
                    description=desc,
                    photos=photos,
                    phone=phone,
                    is_promoted=is_promoted,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    date_text=ad.get("lastRefreshTime") or ad.get("createdTime"),
                    is_today=True
                ))

        except Exception as e:
            print(f"[OLX] Exception while fetching: {e}")

        return listings
