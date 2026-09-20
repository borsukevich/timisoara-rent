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
    build_year: Optional[int] = None
    availability: str = ""
    smoking_policy: str = ""
    exclusion_reason: Optional[str] = None
    date_text: Optional[str] = None
    is_today: bool = True

class BaseScraper:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    def extract_phone(self, text: str) -> Optional[str]:
        if not text:
            return None
        norm_text = re.sub(r'\b[Oo](7\d{2})', r'0\1', text)
        matches = re.findall(r'(?:(?:\+40|0)7[0-9]{2}[\s\.-]?[0-9]{3}[\s\.-]?[0-9]{3})', norm_text)
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

    def check_zero_commission(self, text: str) -> bool:
        """Strictly checks if 0% commission is explicitly stated."""
        if not text:
            return False
        t = text.lower()
        if any(neg in t for neg in [
            "comision standard", "comision 50%", "comisionul agentiei", "comision agentie",
            "comision de 50%", "plata comision"
        ]):
            return False

        patterns = [
            r'\bcomision\s*0\s*%',
            r'\bcomision\s*0\b',
            r'\b0\s*%\s*comision\b',
            r'\bcomision\s*zero\b',
            r'\bzero\s*comision\b',
            r'\bf[aă]r[aă]\s+comision\b',
            r'\bcomision\s+cump[aă]r[aă]tor\s+0\b',
            r'\bcomision\s+chiria[sș]\s+0\b',
        ]
        return any(re.search(p, t) for p in patterns)

    def check_owner(self, text: str) -> bool:
        """Strictly checks if the author explicitly identifies as the direct private owner."""
        if not text:
            return False
        t = text.lower()

        # If it explicitly mentions being an agency or broker, it's NOT direct owner
        agency_indicators = [
            "agentie imobiliara", "agenție imobiliară", "agent imobiliar", "consultant imobiliar",
            "birou imobiliar", "comision agentie", "comisionul agentiei", "comision standard",
            "comision 50%", "la cererea proprietarului", "acordul proprietarului",
            "in numele proprietarului", "în numele proprietarului", "reprezentam proprietarul",
            "reprezentăm proprietarul", "amenajat de proprietar", "locuit de proprietar",
            "proprietari civilizati", "proprietarul doreste", "proprietarul își rezervă"
        ]
        if any(a in t for a in agency_indicators):
            return False

        owner_patterns = [
            r'\bdirect\s+(?:de\s+la\s+)?proprietar\b',
            r'\bproprietar\s*,\s*(?:dau|ofer|inchiriez|închiriez|propun)\b',
            r'\bpersoan[aă]\s+fizic[aă]\s*,\s*(?:dau|ofer|inchiriez|închiriez)\b',
            r'\banun[tț]\s+postat\s+de\s+proprietar\b',
            r'\b[iî]nchiriez\s+ca\s+proprietar\b',
            r'\bsunt\s+proprietar\b',
            r'\bproprietar\s+unic\b',
        ]
        return any(re.search(p, t) for p in owner_patterns)

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
        if any(k in t for k in ["nu se accepta animale", "nu se acceptă animale", "fara animale", "fără animale", "fara pet", "nu sunt acceptate animale"]):
            return "❌ Запрещены"
        if any(k in t for k in ["animale mici", "animale de talie mica", "animale de talie mică"]):
            return "✅ Разрешены (небольшие)"
        if any(k in t for k in ["accepta animale", "acceptă animale", "acceptate animale", "sunt acceptate animale", "pet friendly", "animale permise", "animale de companie acceptate", "permis cu animale"]):
            return "✅ Разрешены"
        return "Не указано"

    def analyze_availability(self, text: str) -> str:
        if not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["disponibil imediat", "disponibil de acum", "ocupabil imediat", "disponibilitate imediata", "liber imediat"]):
            return "Сразу (свободна)"
        m = re.search(r'disponibil(?:[aă])?\s+(?:de\s+la|din)?\s*([0-9]{1,2}\s+[a-zăîâșț]+(?:\s+[0-9]{4})?|[0-9]{1,2}[./-][0-9]{1,2}(?:[./-][0-9]{2,4})?)', t)
        if m:
            return f"С {m.group(1).strip()}"
        return ""

    def analyze_smoking(self, text: str) -> str:
        if not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["fumatul este permis doar afara", "fumatul permis doar afara", "doar afara", "doar afară", "pe balcon", "numai pe balcon"]):
            return "🚬 Только на улице/балконе"
        if any(k in t for k in ["fumatul interzis", "nu se fumeaza", "nu se fumează", "fara fumat", "fără fumat"]):
            return "🚭 В квартире запрещено"
        return ""

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

    def extract_build_year(self, text: str) -> Optional[int]:
        if not text:
            return None
        m = re.search(r'(?:anul\s+construc[tț]iei|an\s+construc[tț]ie|an\s+de\s+construc[tț]ie|const[ru]+it\s+(?:în|in)(?:\s+anul)?|bloc\s+(?:nou\s+)?din)\s*[:\s-]+(\d{4})', text, re.IGNORECASE)
        if m:
            try:
                year = int(m.group(1))
                if 1900 <= year <= 2030:
                    return year
            except Exception:
                pass
        return None

    def extract_street_address(self, text: str) -> Optional[str]:
        if not text:
            return None
        # 1. Explicit address prefix: 'Adresa exacta este: ...' or 'Adresa: ...'
        m = re.search(r'adresa\s*(?:exact[aă])?\s*(?:este)?\s*[:\s-]+([A-Za-zĂÎÂȘȚăîâșț0-9\s.,/-]+?)(?:\n|$)', text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            cand = re.split(r'\s{2,}|\n', cand)[0].strip(' ,.-|–—')
            cand = re.sub(r',?\s*Timi[sș]oara\b.*', '', cand, flags=re.IGNORECASE).strip(' ,.-|–—')
            ctx = text[max(0, m.start() - 100):min(len(text), m.end() + 100)].lower()
            if len(cand) >= 4 and any(w in cand.lower() for w in ['str', 'calea', 'bd', 'bulevard', 'piata', 'aleea', 'splai']):
                if not any(b in ctx for b in ["oradea", "publi24"]) and "dacia nr 34" not in cand.lower():
                    return cand

        # 2. Match street patterns with optional number
        prefix_pat = r'(?:strada\s+|str\.\s*|str\b\s+|calea\s+|bulevardul\s+|bd\.\s*|bd\b\s+|aleea\s+|splaiul\s+|splai\b\s+|pia[tț]a\s+)'
        m_num = re.search(rf'\b({prefix_pat}[A-ZĂÎÂȘȚ][A-Za-zĂÎÂȘȚăîâșț\s.-]+?\s+(?:(?:nr\.?|num[aă]rul)\s*)?\d+[A-Za-z]?)\b', text, re.IGNORECASE)
        if m_num:
            cand = m_num.group(1).strip(' ,.-|–—')
            ctx = text[max(0, m_num.start() - 100):min(len(text), m_num.end() + 100)].lower()
            if 4 <= len(cand) <= 60 and not any(b in ctx for b in ["oradea", "publi24"]) and "dacia nr 34" not in cand.lower():
                return cand

        m_no_num = re.search(rf'\b({prefix_pat}[A-ZĂÎÂȘȚ][A-Za-zĂÎÂȘȚăîâșț\s.-]+?)(?=[,.;\n]|\s+(?:la|în|in|cu|de|pe|care|este|se|apartament|bloc)\b|$)', text, re.IGNORECASE)
        if m_no_num:
            cand = m_no_num.group(1).strip(' ,.-|–—')
            ctx = text[max(0, m_no_num.start() - 100):min(len(text), m_no_num.end() + 100)].lower()
            if 4 <= len(cand) <= 60 and not any(b in ctx for b in ["oradea", "publi24"]) and "dacia nr 34" not in cand.lower():
                return cand

        return None

    def parse_price_eur(self, price_str: str) -> Optional[float]:
        if not price_str:
            return None
        cleaned = re.sub(r'<s>.*?</s>', '', price_str, flags=re.DOTALL)
        cleaned = re.sub(r'\(было.*?\)', '', cleaned, flags=re.DOTALL)
        is_lei = bool(re.search(r'\b(?:lei|ron)\b', cleaned, re.IGNORECASE))
        cleaned = cleaned.replace(' ', '')
        m = re.search(r'(\d+(?:[.,]\d+)?)', cleaned)
        if not m:
            return None
        num_str = m.group(1).replace(',', '.')
        if re.search(r'\.\d{3}$', num_str):
            num_str = num_str.replace('.', '')
        try:
            val = float(num_str)
            if is_lei:
                val = val / 5.0
            return val
        except Exception:
            return None

    def is_timisoara_location(self, text: str) -> bool:
        """Returns False if location or text indicates another city/suburb outside Timișoara.
        Applied ONLY for publi24 as other portals already have strict platform-level geo bounds."""
        if self.name != "publi24" and self.name != "dummy":
            return True
        if not text:
            return True
        t = text.lower()
        # Other cities or external suburbs outside Timișoara
        excluded_locations = [
            r'\bsibiu\b', r'\bcluj\b', r'(?<!calea\s)(?<!strada\s)(?<!zona\s)(?<!b-dul\s)\barad\b', r'\bbucure[sș]ti\b', r'\boradea\b', r'\bbra[sș]ov\b',
            r'\bia[sș]i\b', r'\bcraiova\b', r'\bconstan[tț]a\b', r'(?<!calea\s)\blugoj\b', r'\bbuzia[sș]\b',
            r'\bs[aâ]nnicolau\b', r'\bjimbolia\b', r'\bf[aă]get\b', r'\bdeta\b', r'\bgiroc\b',
            r'\bchi[sș]oda\b', r'\bdumbr[aă]vi[tț]a\b', r'\bmo[sș]ni[tț]a\b', r'\bghiroda\b',
            r'\bs[aă]c[aă]laz\b', r'\bs[aâ]nandrei\b', r'\b[sș]ag\b', r'\bremetea\b', r'\bpeciu\b',
            r'\bs[aâ]nmihaiu\b', r'\bgiarmata\b', r'\borti[sș]oara\b', r'\breca[sș]\b', r'\bg[aă]taia\b',
            r'\bcovaci\b', r'\butvin\b', r'\bcarani\b', r'\bberegs[aă]u\b',
            r'\bmetrou\b', r'\b[sș]elimb[aă]r\b', r'\bselimbar\b', r'\bcoresi\b',
            r'\bsector(?:ul)?\s*[1-6]\b', r'\bmilitari\b', r'\bpantelimon\b',
            r'\bberceni\b', r'\bdrumul taberei\b', r'\bpipera\b', r'\bfloreasca\b',
            r'\btineretului\b', r'\bparcul carol\b', r'\btitan\b', r'\bap[aă]r[aă]torii patriei\b',
            r'\bpite[sș]ti\b', r'\bploie[sș]ti\b', r'\bbac[aă]u\b', r'\bsuceava\b', r'\bgala[tț]i\b',
            r'\bbr[aă]ila\b', r'\bbaia mare\b', r'\bt[aâ]rgu\s*mure[sș]\b', r'\btargu\s*mures\b',
            r'\balba\s*iulia\b', r'\bdeva\b', r'\bhunedoara\b', r'\bre[sș]i[tț]a\b'
        ]
        for pat in excluded_locations:
            if re.search(pat, t):
                return False
        return True

    def extract_price_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        t = html.unescape(text)

        # Look for currency symbols and numeric values:
        # e.g., 450 €, 450EUR, 450 euro, € 450, €450, 450.00 €, 3.500 lei, 2 500 lei, etc.
        patterns = [
            r'€\s*([0-9]{1,2}[. ][0-9]{3}|[0-9]{3,4}(?:[.,][0-9]{2})?)',
            r'([0-9]{1,2}[. ][0-9]{3}|[0-9]{3,4}(?:[.,][0-9]{2})?)\s*(€|eur\b|euro\b|lei\b|ron\b)',
            r'(?:chirie|pre[tț]|pret|price)[:\s]+([0-9]{1,2}[. ][0-9]{3}|[0-9]{3,4})\b'
        ]

        candidates = []
        for pat in patterns:
            for m in re.finditer(pat, t, re.IGNORECASE):
                val_str = m.group(1)
                curr_str = (m.group(2) if m.lastindex and m.lastindex >= 2 else "€").lower()
                clean_num = re.sub(r'[.,][0-9]{2}$', '', val_str).replace(" ", "").replace(".", "")
                if clean_num.isdigit():
                    num = int(clean_num)
                    if "lei" in curr_str or "ron" in curr_str:
                        eur_val = int(round(num / 5.0))
                    else:
                        eur_val = num
                    if 250 <= eur_val <= 3000:
                        candidates.append((eur_val, f"{eur_val} €"))

        if candidates:
            # If any candidate is in the target 400-850 EUR range, prioritize it!
            for eur_val, formatted in candidates:
                if 400 <= eur_val <= 850:
                    return formatted
            return candidates[0][1]

        return None

    def fetch_listings(self) -> List[Listing]:
        raise NotImplementedError
