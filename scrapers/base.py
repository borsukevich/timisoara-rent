from dataclasses import dataclass, field
from typing import List, Optional
import re
import html
import urllib.parse

@dataclass
class Listing:
    uid: str
    source: str
    title: str
    price: str
    url: str
    rooms: str = "3 camere"
    exact_area: str = "от 55 м²"
    floor: str = "Не указан"
    district: str = "Тимишоара"
    street: str = ""
    full_address: str = "Timișoara"
    complex_name: str = "Не указан"
    parking_info: str = "Не указано"
    pets_policy: str = "Не указано"
    ac_info: str = "Не указан"
    balcony_info: str = "Не указан"
    deposit_info: str = "1 месяц (обычно)"
    commission_info: str = "Уточнять"
    building_type: str = "Обычный дом"
    map_link: str = ""
    description: str = ""
    photos: List[str] = field(default_factory=list)
    phone: Optional[str] = None
    is_promoted: bool = False
    is_owner: bool = False
    has_boiler: bool = False
    date_text: Optional[str] = None
    is_today: bool = True

class BaseScraper:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    def extract_phone(self, text: str) -> Optional[str]:
        if not text:
            return None
        matches = re.findall(r'(?:(?:\+40|0)7[0-9]{2}[\s\.-]?[0-9]{3}[\s\.-]?[0-9]{3})', text)
        if matches:
            raw = matches[0].replace(" ", "").replace(".", "").replace("-", "")
            if raw.startswith("07"):
                return f"+40 {raw[1:4]} {raw[4:7]} {raw[7:]}"
            return raw
        return None

    def check_boiler(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        keywords = [
            "centrala proprie", "centrală proprie", "centrala pe gaz", "centrală pe gaz",
            "centrala termica", "centrală termică", "incalzire proprie", "încălzire proprie",
            "incalzire in pardoseala", "încălzire în pardoseală"
        ]
        return any(k in t for k in keywords)

    def check_owner(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        keywords = [
            "proprietar", "direct proprietar", "persoana fizica", "persoană fizică",
            "fara comision", "fără comision", "comision 0", "comision 0%"
        ]
        return any(k in t for k in keywords)

    def analyze_parking(self, text: str) -> str:
        if not text:
            return "Не указано"
        t = text.lower()
        
        parking_keywords = ["parcare", "garaj", "loc parcare", "loc de parcare", "parking"]
        if not any(k in t for k in parking_keywords):
            return "Не указано"

        ptype = []
        if any(k in t for k in ["subteran", "subterana", "subterană", "subterane", "demisol"]):
            ptype.append("подземный")
        elif any(k in t for k in ["suprateran", "la sol", "curte", "în curte", "exterior", "afara", "strada"]):
            ptype.append("на улице / во дворе")

        pcost = []
        if any(k in t for k in ["inclus", "inclusa", "inclusă", "in pret", "în preț", "gratuit", "asigurat"]):
            pcost.append("включен в стоимость")
        elif any(k in t for k in ["contra cost", "separat", "extra", "+ 50", "+50", "cost suplimentar", "+ 100"]):
            pcost.append("за отдельную плату")

        details = []
        if ptype:
            details.append(", ".join(ptype))
        if pcost:
            details.append(", ".join(pcost))

        if details:
            return f"✅ Да ({'; '.join(details)})"
        return "✅ Да (детали в описании)"

    def analyze_pets(self, text: str) -> str:
        if not text:
            return "Не указано"
        t = text.lower()
        if any(k in t for k in ["nu se accepta animale", "nu se acceptă animale", "fara animale", "fără animale", "fara pet"]):
            return "❌ Запрещены"
        if any(k in t for k in ["accepta animale", "acceptă animale", "pet friendly", "animale permise"]):
            return "✅ Разрешены"
        return "Не указано"

    def analyze_ac(self, text: str) -> str:
        if not text:
            return "Не указан"
        t = text.lower()
        if any(k in t for k in ["aer conditionat", "aer condiționat", "climatizare", "clima", " a/c "]):
            return "✅ Есть"
        return "Не указан"

    def analyze_balcony(self, text: str) -> str:
        if not text:
            return "Не указан"
        t = text.lower()
        if any(k in t for k in ["balcon", "terasa", "terasă", "logie"]):
            return "✅ Есть"
        return "Не указан"

    def analyze_deposit(self, text: str) -> str:
        if not text:
            return "1 месяц (обычно)"
        t = text.lower()
        if any(k in t for k in ["doua luni garantie", "două luni garanție", "2 luni garantie", "2 luni garanție"]):
            return "2 месяца аренды"
        if any(k in t for k in ["o luna garantie", "o lună garanție", "1 luna garantie", "1 lună garanție", "o luna de chirie"]):
            return "1 месяц аренды"
        m = re.search(r'(\d+)\s*(?:euro|€)\s*(?:garantie|depozit)', t)
        if m:
            return f"{m.group(1)} €"
        return "1 месяц (обычно)"

    def analyze_building_type(self, text: str) -> str:
        if not text:
            return "Обычный дом"
        t = text.lower()
        if any(k in t for k in ["cladire istorica", "clădire istorică", "istoric", "istorica", "istorică"]):
            return "🏛️ Историческое здание"
        if any(k in t for k in ["bloc nou", "ansamblu nou", "constructie noua", "construcție nouă", "an 202"]):
            return "🏢 Новостройка"
        return "Обычный фонд"

    def detect_complex(self, text: str) -> str:
        if not text:
            return "Не указан"
        
        known_complexes = [
            ("isho", "ISHO"),
            ("denya forest", "Denya Forest"),
            ("adora forest", "Adora Forest"),
            ("nord one", "Nord One"),
            ("city of mara", "City of Mara"),
            ("uptown", "Uptown Residence"),
            ("monarch", "Monarch"),
            ("afi park", "AFI Park"),
            ("ring residence", "Ring Residence"),
            ("iris armoniei", "Iris Armoniei"),
            ("vivalia", "Vivalia"),
            ("xcity", "XCity Park"),
            ("green park", "Green Park"),
            ("take ionescu", "Take Ionescu Residence"),
            ("athenaeum", "Athenaeum"),
            ("grand hill", "Grand Hill"),
            ("bega park", "Bega Park"),
            ("paltim", "Paltim"),
            ("campeador", "Campeador"),
            ("vox vertical", "Vox Vertical Village")
        ]
        t = text.lower()
        for key, name in known_complexes:
            if key in t:
                return name

        m = re.search(r'(?:complexul|ansamblul|rezidential|proiectul)\s+([A-Z][a-zA-Z0-9\s-]{2,20})', text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ["nou", "rezidential", "timisoara", "inchis"]:
                return candidate

        return "Не указан"

    def format_floor(self, raw_floor: str) -> str:
        if not raw_floor:
            return "Не указан"
        f = str(raw_floor).strip()
        floor_map = {
            "GROUND_FLOOR": "1 этаж (Parter)",
            "PARTER": "1 этаж (Parter)",
            "FIRST": "1 этаж",
            "SECOND": "2 этаж",
            "THIRD": "3 этаж",
            "FOURTH": "4 этаж",
            "FIFTH": "5 этаж",
            "SIXTH": "6 этаж",
            "SEVENTH": "7 этаж",
            "EIGHTH": "8 этаж",
            "NINTH": "9 этаж",
            "TENTH": "10 этаж"
        }
        if f.upper() in floor_map:
            return floor_map[f.upper()]
        
        if f.isdigit():
            return f"{f} этаж"
        
        m = re.search(r'etaj\s*(\d+)(?:\s*/\s*(\d+))?', f, re.IGNORECASE)
        if m:
            cur = m.group(1)
            tot = m.group(2)
            return f"{cur} из {tot} этаж" if tot else f"{cur} этаж"

        return f

    def generate_map_link(self, lat: float = None, lon: float = None, address: str = "") -> str:
        if lat and lon and lat != 0 and lon != 0:
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        if address:
            query = f"{address}, Timisoara, Romania"
            return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(query)}"
        return "https://www.google.com/maps/search/?api=1&query=Timisoara"

    def clean_html(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        clean = re.sub(r'<[^>]+>', ' ', raw_html)
        clean = html.unescape(clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def fetch_listings(self) -> List[Listing]:
        raise NotImplementedError
