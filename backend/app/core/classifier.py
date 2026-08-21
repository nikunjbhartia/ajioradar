import re
from typing import List, Dict, Any, Optional
from collections import Counter

# Exhaustive authoritative Brand -> Department dictionary from Ajio catalog
BRAND_DEPT = {
    # Women Fashion & Ethnic
    'zelzis': 'WOMEN', 'vredevogel': 'WOMEN', 'miss chase': 'WOMEN', 'fig': 'WOMEN', 'avaasa': 'WOMEN',
    'avaasa mix n\' match': 'WOMEN', 'avaasa set': 'WOMEN', 'rio': 'WOMEN', 'fusion': 'WOMEN', 
    'soch': 'WOMEN', 'janasya': 'WOMEN', 'gosriki': 'WOMEN', 'zivame': 'WOMEN', 'clovia': 'WOMEN', 
    'saree mall': 'WOMEN', 'anni designer': 'WOMEN', 'myshka': 'WOMEN', 'kotty': 'WOMEN', 
    'ishin': 'WOMEN', 'libas': 'WOMEN', 'biba': 'WOMEN', 'aurelia': 'WOMEN', 'w': 'WOMEN', 
    'lulu & sky': 'WOMEN', 'scorpius': 'WOMEN', 'vastani enterprise': 'WOMEN', 
    'madhuram textiles': 'WOMEN', 'revangi': 'WOMEN', 'panash': 'WOMEN', 'svaraa': 'WOMEN', 
    'kayrah': 'WOMEN', 'ichaa': 'WOMEN', 'readiprint': 'WOMEN', 'nyrika': 'WOMEN', 'j & jp': 'WOMEN', 
    'katapol': 'WOMEN', '4you dresses': 'WOMEN', 'muhuratam': 'WOMEN', 'fabbhue': 'WOMEN', 
    'acai': 'WOMEN', 'sthula\'s': 'WOMEN', 'draax fashions': 'WOMEN', 'tanuka': 'WOMEN', 
    'amour secret': 'WOMEN', 'ebadat': 'WOMEN', 'oxolloxo': 'WOMEN', 'alyne': 'WOMEN', 
    'siore': 'WOMEN', 'fabindia': 'WOMEN', 'one femme': 'WOMEN', 'folli follie': 'WOMEN', 
    'popmantra': 'WOMEN', 'hivora': 'WOMEN', 'serona nostalgia': 'WOMEN', 'clafoutis': 'WOMEN', 
    'leia': 'WOMEN', 'beach curve': 'WOMEN', 'indie picks': 'WOMEN', 'fabnex': 'WOMEN',
    'molcha by babita singh': 'WOMEN', 'zimcon': 'WOMEN', 'crosmo': 'WOMEN', 'ashrifab': 'WOMEN',
    'thoillling': 'WOMEN', 'poshax': 'WOMEN', 'french accent': 'WOMEN', 'alpha tribe': 'WOMEN',
    'hevignon': 'WOMEN', 'jazz and sizzle': 'WOMEN', 'bhrm': 'WOMEN', 'swi stylish': 'WOMEN',
    'zevora': 'WOMEN', 'nobarr': 'WOMEN', 'rrc': 'WOMEN', 'arrabi': 'WOMEN', 'xe looks': 'WOMEN',
    'winsome deal': 'WOMEN', 'grishu collection': 'WOMEN', 'dipi': 'WOMEN', 'eblooming': 'WOMEN',
    'shooting star': 'WOMEN', 'shopcash': 'WOMEN', 'la martina': 'WOMEN',

    # Bags, Luggage & Accessories
    'caprese': 'ACCESSORIES & LUGGAGE', 'lavie': 'ACCESSORIES & LUGGAGE', 'lino perros': 'ACCESSORIES & LUGGAGE',
    'toteteca': 'ACCESSORIES & LUGGAGE', 'astrid': 'ACCESSORIES & LUGGAGE', 'bagsy malone': 'ACCESSORIES & LUGGAGE',
    'safari': 'ACCESSORIES & LUGGAGE', 'skybags': 'ACCESSORIES & LUGGAGE', 'aristocrat': 'ACCESSORIES & LUGGAGE',
    'nasher miles': 'ACCESSORIES & LUGGAGE', 'sassora': 'ACCESSORIES & LUGGAGE', 'luggero': 'ACCESSORIES & LUGGAGE',
    'priority': 'ACCESSORIES & LUGGAGE', 'haute sauce': 'ACCESSORIES & LUGGAGE', 'wiki': 'ACCESSORIES & LUGGAGE',

    # Kids & Infants
    'hellcat': 'KIDS & INFANTS', 'pspeaches': 'KIDS & INFANTS', 'aarika girls ethnic': 'KIDS & INFANTS',
    'tior': 'KIDS & INFANTS', 'point cove': 'KIDS & INFANTS', 'mini klub': 'KIDS & INFANTS',
    'miniklub': 'KIDS & INFANTS', 'bumzee': 'KIDS & INFANTS', 'nauti nati': 'KIDS & INFANTS',
    '612 league': 'KIDS & INFANTS', 'inf frendz': 'KIDS & INFANTS', 'kg frendz': 'KIDS & INFANTS',
    'rio girls': 'KIDS & INFANTS', 'yb dnmx': 'KIDS & INFANTS', 'peppermint': 'KIDS & INFANTS',
    'kuchipoo': 'KIDS & INFANTS', 'nap chief': 'KIDS & INFANTS', 'jbn creation': 'KIDS & INFANTS',
    'sg yuvraj': 'KIDS & INFANTS', 'cherry crumble by nitt hyman': 'KIDS & INFANTS', 'lilpicks': 'KIDS & INFANTS',
    'hunny bunny': 'KIDS & INFANTS', 'd\'chica': 'KIDS & INFANTS', 'trampoline': 'KIDS & INFANTS',
    'sweetie pie': 'KIDS & INFANTS', 'under fourteen only': 'KIDS & INFANTS', 'learning through fun': 'KIDS & INFANTS',
    'boyz n galz': 'KIDS & INFANTS', 'minimyn': 'KIDS & INFANTS', 'wingsfield': 'KIDS & INFANTS',
    'charliekeen': 'KIDS & INFANTS', 'neska moda': 'KIDS & INFANTS', 'caredone': 'KIDS & INFANTS',
    'hamster london': 'KIDS & INFANTS', 'we3': 'KIDS & INFANTS',

    # Men
    'netplay': 'MEN', 'john players': 'MEN', 'john players select': 'MEN', 'dnmx men': 'MEN', 
    'buda jeans co': 'MEN', 'peter england': 'MEN', 'van heusen': 'MEN', 'louis philippe': 'MEN', 
    'flying machine': 'MEN', 'mufti': 'MEN', 'indian terrain': 'MEN', 'blackberrys': 'MEN', 
    'snitch': 'MEN', 'the souled store': 'MEN', 'sojanya': 'MEN', 'vastramay': 'MEN', 
    'instafab': 'MEN', 'chkokko': 'MEN', 'eyebogler': 'MEN', 'ivoc': 'MEN', 'griffel': 'MEN', 
    'mischief monkey': 'MEN', 'wildhorn': 'MEN', 'donmora': 'MEN', 'ketch': 'MEN', 
    'samavart designs': 'MEN', 'bene kleed': 'MEN', 'jompers': 'MEN', 'royal ful': 'MEN',
    'hoodler': 'MEN', 'klotthe': 'MEN', 'theallchemy': 'MEN', 'leriya fashion': 'MEN',
    'okane': 'MEN', 'usoxo': 'MEN', 'ninja clothes': 'MEN', 'neonomad': 'MEN', 'oh rare': 'MEN',
    'nmii': 'MEN', 'ffu': 'MEN', 'fourfolds': 'MEN', 'chevignon': 'MEN', 'rigo': 'MEN',
    'bstories': 'MEN', 'axxtitude': 'MEN', 'sports 52 wear': 'MEN', 'network': 'MEN',

    # Footwear
    'bata': 'FOOTWEAR', 'red tape': 'FOOTWEAR', 'clarks': 'FOOTWEAR', 'puma': 'FOOTWEAR',
    'kazarmax': 'FOOTWEAR', 'longwalk': 'FOOTWEAR', 'feet well shoes': 'FOOTWEAR', 'style shoes': 'FOOTWEAR',
    'havaianas': 'FOOTWEAR', 'aadi': 'FOOTWEAR', 'converse': 'FOOTWEAR', 'truffle collection': 'FOOTWEAR',
    'marc loire': 'FOOTWEAR', 'shoetopia': 'FOOTWEAR', 'decathlon': 'FOOTWEAR',

    # Gadgets & Tech
    'noise': 'GADGETS & TECH', 'boat': 'GADGETS & TECH', 'skullcandy': 'GADGETS & TECH',
    'ptron': 'GADGETS & TECH', 'zebronics': 'GADGETS & TECH', 'portronics': 'GADGETS & TECH',
    'hammer': 'GADGETS & TECH', 'cellecor': 'GADGETS & TECH', '3pin': 'GADGETS & TECH',

    # Beauty & Grooming
    'wet n wild': 'BEAUTY & GROOMING', 'profusion cosmetics': 'BEAUTY & GROOMING',
    'beautiliss professional': 'BEAUTY & GROOMING', 'bronson professional': 'BEAUTY & GROOMING',
    'pro': 'BEAUTY & GROOMING',

    # Fashion Jewellery
    'giva': 'FASHION JEWELLERY', 'yellow chimes': 'FASHION JEWELLERY', 'karatcart': 'FASHION JEWELLERY',
    'zeneme': 'FASHION JEWELLERY', 'youbella': 'FASHION JEWELLERY', 'jewels galaxy': 'FASHION JEWELLERY',
    'ornate jewels': 'FASHION JEWELLERY', 'viraasi': 'FASHION JEWELLERY', 'nvr': 'FASHION JEWELLERY',
    'touch925': 'FASHION JEWELLERY', 'menjewell': 'FASHION JEWELLERY', 'mahi': 'FASHION JEWELLERY',
    'oomph': 'FASHION JEWELLERY', 'fabula': 'FASHION JEWELLERY', 'valley of jewellery (voj)': 'FASHION JEWELLERY',

    # Home & Kitchen
    'divine casa': 'HOME & KITCHEN', 'cortina eyelet curtain': 'HOME & KITCHEN', 'rosarahome': 'HOME & KITCHEN',
    'ecraftindia': 'HOME & KITCHEN', 'jaipur fabric': 'HOME & KITCHEN', 'bianca': 'HOME & KITCHEN',
    'baskety': 'HOME & KITCHEN', 'sunny\'s': 'HOME & KITCHEN'
}

VALID_CANONICAL_DEPTS = {
    "MEN", "WOMEN", "KIDS & INFANTS", "FOOTWEAR", "GADGETS & TECH", 
    "BEAUTY & GROOMING", "HOME & KITCHEN", "FASHION JEWELLERY", 
    "ACCESSORIES & LUGGAGE", "INDIE & HANDLOOM", "LUXE & DESIGNER", "Multi-Category"
}


def classify_product(name: str, brand: str = "", cat: str = "", existing_dept: str = "") -> str:
    """
    Classifies an individual product into one of the 11 platform taxonomy departments.
    Uses regex word boundaries to prevent substring collisions (e.g. 'women' or 'ornament' matching 'men').
    """
    t = f"{name or ''} {cat or ''}".lower()
    b_low = (brand or '').strip().lower()

    # 1. Tech & Gadgets
    if any(k in t for k in ['smartwatch', 'smart watch', 'wearable', 'headphone', 'earphone', 'earbud', 'neckband', 'tws', 'speaker', 'bluetooth speaker', 'power bank', 'charger', 'gadget']):
        return 'GADGETS & TECH'

    # 2. Beauty & Grooming
    if any(k in t for k in ['lipstick', 'lip gloss', 'eyeliner', 'mascara', 'foundation', 'concealer', 'serum', 'shampoo', 'conditioner', 'face wash', 'moisturizer', 'sunscreen', 'perfume', 'fragrance', 'deodorant', 'edp', 'edt', 'skincare', 'haircare', 'grooming', 'makeup', 'nail polish', 'kajal', 'cleanser']):
        return 'BEAUTY & GROOMING'

    # 3. Home & Kitchen
    if any(k in t for k in ['bedsheet', 'bed sheet', 'bed cover', 'cushion', 'curtain', 'towel', 'pillow', 'comforter', 'duvet', 'quilt', 'cookware', 'pan', 'crockery', 'cutlery', 'utensil', 'decor', 'clock', 'wall art', 'mat', 'rug', 'carpet', 'dinner set', 'blanket', 'linen']):
        return 'HOME & KITCHEN'

    # 4. Fashion Jewellery
    if any(k in t for k in ['jewel', 'earring', 'necklace', 'pendant', 'ring', 'bangle', 'bracelet', 'anklet', 'mangalsutra', 'choker', 'jhumka', 'kundan']):
        return 'FASHION JEWELLERY'

    # 5. Accessories & Luggage
    if any(k in t for k in ['backpack', 'luggage', 'trolley', 'suitcase', 'duffle', 'wallet', 'belt', 'sunglass', 'eyewear', 'handbag', 'tote bag', 'sling bag', 'clutch']):
        return 'ACCESSORIES & LUGGAGE'

    # 6. Footwear
    if any(k in t for k in ['shoe', 'sneaker', 'sandal', 'boot', 'heel', 'flat', 'jutti', 'mojari', 'slipper', 'flip flop', 'slider', 'clog', 'derby', 'oxford', 'loafer']):
        return 'FOOTWEAR'

    # 7. Kids & Infants
    if any(k in t for k in ['boy', 'boys', 'girl', 'girls', 'infant', 'kid', 'kids', 'baby', 'babies', 'toddler', 'frock', 'romper', 'dungaree', 'toy', 'crib', 'newborn']):
        return 'KIDS & INFANTS'

    # 8. Women
    if 'women' in t or 'womens' in t or 'ladies' in t or any(k in t for k in ['saree', 'sari', 'kurti', 'kurta set', 'lehenga', 'anarkali', 'salwar', 'dupatta', 'dress', 'skirt', 'gown', 'top', 'blouse', 'lingerie', 'bra', 'panty', 'nighty', 'nightwear', 'camisole', 'palazzo', 'churidar', 'kaftan']):
        return 'WOMEN'

    # 9. Men (strict regex boundaries: \b(men|mens|man|gents|male)\b)
    if re.search(r'\b(men|mens|man|gents|male)\b', t) or any(k in t for k in ['formal shirt', 'casual shirt', 'polo tshirt', 'polo t-shirt', 'boxer', 'brief', 'blazer', 'sherwani', 'kurta pajama', 'nehru jacket']):
        return 'MEN'

    # 10. Check Brand table
    if b_low in BRAND_DEPT:
        return BRAND_DEPT[b_low]

    # 11. Normalize existing department
    if existing_dept:
        ed = existing_dept.upper().strip()
        if ed == 'BEAUTY': return 'BEAUTY & GROOMING'
        if ed in ['KIDS', 'BOYS', 'GIRLS', 'INFANTS']: return 'KIDS & INFANTS'
        if ed == 'ACCESSORIES': return 'ACCESSORIES & LUGGAGE'
        if ed == 'JEWELLERY': return 'FASHION JEWELLERY'
        if ed in ['WESTERN WEAR', 'ETHNICWEAR', 'WOMEN\'S COLLECTION']: return 'WOMEN'
        if ed in VALID_CANONICAL_DEPTS: return ed

    return 'Multi-Category'


def classify_campaign(
    title: str = "", 
    desc: str = "", 
    brands_str: str = "", 
    slug: str = "", 
    sample_deals: Optional[List[Dict[str, Any]]] = None, 
    seed_dept: str = ""
) -> str:
    """
    Aggregates product deals, brand affiliations, and metadata to classify a promotion campaign.
    Prevents single-gender default biases by relying on statistical majority voting.
    """
    # 1. If sample deals are available, vote from resolved items
    if sample_deals and len(sample_deals) > 0:
        dept_votes = [d.get('department') for d in sample_deals if d.get('department') and d.get('department') != 'Multi-Category']
        if dept_votes:
            counter = Counter(dept_votes)
            top_dept, top_count = counter.most_common(1)[0]
            # If >= 50% items align on one department
            if (top_count / len(sample_deals)) >= 0.5:
                return top_dept
            elif len(counter) >= 2:
                return "Multi-Category"

    # 2. Score from brand list & metadata keywords
    t = f"{title} {desc} {slug}".lower()
    brands = [b.strip().lower() for b in brands_str.split(',') if b.strip()]
    scores = Counter()

    for b in brands:
        if b in BRAND_DEPT:
            scores[BRAND_DEPT[b]] += 4
        elif 'women' in b or 'saree' in b:
            scores['WOMEN'] += 3
        elif re.search(r'\b(men|man)\b', b):
            scores['MEN'] += 3

    if any(k in t for k in ['smartwatch', 'headphone', 'earphone', 'speaker', 'tws', 'gadget']):
        scores['GADGETS & TECH'] += 5
    if any(k in t for k in ['lipstick', 'perfume', 'makeup', 'serum', 'grooming', 'beauty']):
        scores['BEAUTY & GROOMING'] += 5
    if any(k in t for k in ['bedsheet', 'curtain', 'cushion', 'towel', 'kitchen', 'cookware', 'home']):
        scores['HOME & KITCHEN'] += 5
    if any(k in t for k in ['jewel', 'earring', 'necklace', 'bangle', 'ring']):
        scores['FASHION JEWELLERY'] += 5
    if any(k in t for k in ['handbag', 'backpack', 'luggage', 'trolley', 'wallet']):
        scores['ACCESSORIES & LUGGAGE'] += 5
    if any(k in t for k in ['shoe', 'sneaker', 'sandal', 'heel', 'flat', 'footwear', 'juttis']):
        scores['FOOTWEAR'] += 4
    if any(k in t for k in ['boy', 'girl', 'infant', 'kid', 'baby', 'frock', 'romper', 'children']):
        scores['KIDS & INFANTS'] += 5
    if 'women' in t or any(k in t for k in ['saree', 'sari', 'kurti', 'lehenga', 'lingerie', 'bra', 'panty', 'dress', 'skirt', 'ladies', 'anarkali']):
        scores['WOMEN'] += 5
    if re.search(r'\b(men|mens|man|gents|male)\b', t) or any(k in t for k in ['shirt', 'tshirt', 'boxer', 'brief', 'trousers']):
        scores['MEN'] += 5

    if scores:
        top_dept, top_score = scores.most_common(1)[0]
        total_score = sum(scores.values())
        if len(scores) >= 2 and (top_score / total_score) < 0.55:
            return 'Multi-Category'
        return top_dept

    # Fallback to seed department if clean, else Multi-Category
    if seed_dept:
        sd = seed_dept.upper().strip()
        if sd == 'BEAUTY': return 'BEAUTY & GROOMING'
        if sd in ['KIDS', 'BOYS', 'GIRLS', 'INFANTS']: return 'KIDS & INFANTS'
        if sd in VALID_CANONICAL_DEPTS and sd != 'MEN':
            return sd

    return 'Multi-Category'
