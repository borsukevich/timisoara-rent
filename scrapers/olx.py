from curl_cffi import requests
import json
import re
from datetime import datetime
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

class OLXScraper(BaseScraper):
    def __init__(self, url: str):
        super().__init__("olx", url)

    def is_north_zone(self, text: str) -> bool:
        t = text.lower()
        for pat in PREFERRED_NORTH_CENTRAL_ZONES:
            if re.search(r'\b' + pat, t, re.IGNORECASE):
                return True
        return False

    def is_explicitly_excluded(self, text: str, context: str = "") -> Optional[str]:
        """Returns the matched unwanted southern zone if explicitly stated, else None."""
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
                print(f"[OLX] Error: HTTP {r.status_code}")
                return []

            m = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', r.text)
            if not m:
                print("[OLX] Could not find __PRERENDERED_STATE__")
                return []

            inner_str = json.loads(m.group(1))
            data = json.loads(inner_str)
            ads = data.get("listing", {}).get("listing", {}).get("ads", [])

            now = datetime.now()
            seen_uids = set()

            for ad in ads:
                ad_id = str(ad.get("id"))
                if not ad_id or ad_id in seen_uids:
                    continue
                seen_uids.add(ad_id)

                title = (ad.get("title") or "").strip()
                url = ad.get("url", "")
                raw_desc = ad.get("description", "")
                desc = self.clean_html(raw_desc)

                # Check promotion and creation date
                promo = ad.get("promotion", {})
                is_promoted = bool(ad.get("isPromoted") or promo.get("top_ad") or promo.get("highlighted"))
                created_str = ad.get("createdTime")
                
                is_today = False
                if created_str:
                    try:
                        dt = datetime.fromisoformat(created_str.strip())
                        is_today = (dt.date() == now.date())
                    except Exception:
                        pass

                # If promoted ad is NOT from today, it's an old promoted/pinned ad - skip it
                if is_promoted and not is_today:
                    continue

                # Location & District
                loc = ad.get("location", {})
                district = loc.get("districtName")
                if not district or district.lower() in ["timisoara", "timișoara"]:
                    loc_m = re.search(r'(?:zona|în)\s+([A-Za-zĂÎÂȘȚăîâșț\s-]+)', title, re.IGNORECASE)
                    if loc_m:
                        district = loc_m.group(1).strip()
                    else:
                        district = "Timișoara"

                full_address = f"{district}, Timișoara" if district != "Timișoara" else "Timișoara"

                # Geographic Filter: Only exclude if an unwanted zone is EXPLICITLY mentioned
                full_text = f"{title} {district} {desc}"
                excluded_match = self.is_explicitly_excluded(full_text, context=title)
                exclusion_reason = None
                if excluded_match:
                    exclusion_reason = f"Южный район: '{excluded_match}'"

                # Price
                price_obj = ad.get("price", {})
                price = price_obj.get("displayValue", "")
                if not price and "regularPrice" in price_obj:
                    val = price_obj["regularPrice"].get("value")
                    curr = price_obj["regularPrice"].get("currencyCode", "EUR")
                    price = f"{val} {curr}"

                # Price filter: strictly 400 - 800 EUR
                price_eur = self.parse_price_eur(price)
                if price_eur is not None and (price_eur < 400 or price_eur > 800):
                    exclusion_reason = exclusion_reason or f"Цена {price_eur} EUR вне диапазона 400-800 EUR"

                # Photos (high-res 1600x1200)
                raw_photos = ad.get("photos", [])
                photos = []
                for p in raw_photos:
                    if isinstance(p, str):
                        high = re.sub(r';s=\d+x\d+', ';s=1600x1200', p)
                        if high not in photos:
                            photos.append(high)
                    elif isinstance(p, dict) and "link" in p:
                        high = p["link"].replace("{width}x{height}", "1600x1200")
                        if high not in photos:
                            photos.append(high)

                # Parameters
                rooms = "3 camere"
                exact_area = ""
                raw_floor = ""
                building_type = "Обычный фонд"
                build_year = None
                
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
                    elif k == "compartimentare":
                        v_lower = str(v).lower()
                        if "decomandat" in v_lower and "semi" not in v_lower:
                            building_type = "Раздельная (decomandat)"
                        elif "semidecomandat" in v_lower:
                            building_type = "Полураздельная (semidecomandat)"
                        elif "circular" in v_lower:
                            building_type = "Смежная (circular)"
                    elif k in ["constructie", "an_constructie", "anul_constructiei", "build_year"]:
                        m_yr = re.search(r'\b(19\d\d|20\d\d)\b', v)
                        if m_yr:
                            build_year = int(m_yr.group(1))
                        elif any(old in v.lower() for old in ["inainte", "1977", "1990", "inainte de 2000"]):
                            build_year = 1990

                if not build_year:
                    build_year = self.extract_build_year(f"{title} {desc}")

                if build_year:
                    building_type = f"{building_type} | Дом {build_year} года" if building_type != "Обычный фонд" else f"Дом {build_year} года"

                floor = self.format_floor(raw_floor)

                # Map Coordinates
                map_data = ad.get("map", {})
                lat = map_data.get("lat")
                lon = map_data.get("lon")
                # Street address extraction
                street = self.extract_street_address(full_text)
                if street:
                    if district and district != "Timișoara":
                        full_address = f"{street}, {district}, Timișoara"
                    else:
                        full_address = f"{street}, Timișoara"
                map_link = self.generate_map_link(lat=lat, lon=lon, address=full_address)

                # Amenities & Owner status
                phone = self.extract_phone(full_text)
                has_boiler = self.check_boiler(full_text)
                complex_name = self.detect_complex(full_text)
                parking_info = self.analyze_parking(full_text)
                ac_info = self.analyze_ac(full_text)
                balcony_info = self.analyze_balcony(full_text)
                deposit_info = self.analyze_deposit(full_text)
                building_type = self.analyze_building_type(full_text)
                is_business = bool(ad.get("isBusiness", True))
                has_agency_in_text = any(k in full_text.lower() for k in [
                    "agentie imobiliara", "agenție imobiliară", "agent imobiliar", "consultant imobiliar",
                    "comision agentie", "comisionul agentiei", "comision standard"
                ])

                if is_business or has_agency_in_text:
                    is_owner = False
                else:
                    is_owner = not is_business

                has_zero_comm = self.check_zero_commission(full_text)
                if has_zero_comm:
                    commission_info = "0% (Без комиссии)"
                elif is_owner:
                    commission_info = "0% (Без комиссии)"
                elif is_business or has_agency_in_text:
                    commission_info = "Стандартная (обычно 50%)"
                else:
                    commission_info = "Уточнять (обычно 50%)"
                pets_policy = self.analyze_pets(full_text)
                availability = self.analyze_availability(full_text)
                smoking_policy = self.analyze_smoking(full_text)

                listings.append(Listing(
                    uid=f"olx_{ad_id}",
                    source="olx",
                    title=title,
                    price=price,
                    url=url,
                    rooms=rooms,
                    exact_area=exact_area or "от 50 м²",
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
                    is_promoted=False,
                    is_owner=is_owner,
                    has_boiler=has_boiler,
                    build_year=build_year,
                    availability=availability,
                    smoking_policy=smoking_policy,
                    exclusion_reason=exclusion_reason,
                    date_text=created_str,
                    is_today=is_today
                ))

        except Exception as e:
            print(f"[OLX] Exception while fetching: {e}")

        return listings

    def enrich_listing_details(self, listing: Listing) -> Optional[Listing]:
        """OLX already provides full specs, descriptions and HD galleries in native JSON."""
        return listing
