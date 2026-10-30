"""An international pool of author names for demo papers.

Co-authors often share a lab, so each paper draws most of its authors from one naming culture.
Cultures with gendered family names (Central Asian, Slavic) list full names instead of parts.
"""

import random

# (given names, family names): any given name pairs with any family name.
_CULTURES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("Ji-woo", "Seo-yeon", "Min-jun", "Ha-eun", "Do-hyun", "Ye-jin", "Hyun-woo", "Su-bin"),
        ("Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"),
    ),
    (
        ("Wei", "Xin", "Yuxuan", "Haoran", "Jing", "Mingyu", "Zihan", "Ruoxi", "Jiahui", "Tianyi"),
        ("Zhang", "Wang", "Li", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou"),
    ),
    (
        ("Haruto", "Yui", "Ren", "Sakura", "Takumi", "Aoi", "Kenji", "Mio", "Daiki", "Rina"),
        ("Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura"),
    ),
    (
        ("Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Kavya", "Arjun", "Meera", "Ishita"),
        ("Sharma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Menon", "Rao", "Banerjee"),
    ),
    (
        ("Omar", "Layla", "Yusuf", "Fatima", "Karim", "Nour", "Amir", "Leila", "Hassan", "Sara"),
        ("Haddad", "Rahman", "Farouk", "Hosseini", "Khalil", "Nasser", "Saleh", "Mansour"),
    ),
    (
        ("Lukas", "Sofia", "Matteo", "Emma", "Jonas", "Chiara", "Luca", "Clara", "Nils", "Elena"),
        ("Müller", "Rossi", "Dubois", "Novak", "Jansen", "Andersson", "Moreau", "Ricci"),
    ),
    (
        ("Chinedu", "Amara", "Kwame", "Zanele", "Tunde", "Wanjiru", "Kofi", "Nia", "Thabo"),
        ("Okafor", "Mensah", "Ndlovu", "Adeyemi", "Kamau", "Owusu", "Diallo", "Banda"),
    ),
    (
        ("Mateo", "Valentina", "Santiago", "Camila", "Diego", "Lucía", "Joaquín"),
        ("Hernández", "Gómez", "Rodríguez", "Fernández", "Morales", "Vargas"),
    ),
)

_FULL_NAMES: tuple[tuple[str, ...], ...] = (
    (
        "Dilnoza Karimova",
        "Javlon Rakhimov",
        "Malika Yusupova",
        "Bekzod Tursunov",
        "Nodira Abdullaeva",
        "Sardor Ismoilov",
        "Aziza Nazarova",
        "Timur Akhmedov",
        "Aigerim Seitkali",
        "Nurlan Bekov",
    ),
    (
        "Anna Kowalska",
        "Piotr Nowak",
        "Olga Ivanova",
        "Dmitri Sokolov",
        "Katarina Horvat",
        "Tomas Dvorak",
        "Irina Petrova",
        "Marek Zielinski",
    ),
)


def _name(rng: random.Random, culture: int) -> str:
    if culture < len(_CULTURES):
        given, family = _CULTURES[culture]
        return f"{rng.choice(given)} {rng.choice(family)}"
    return rng.choice(_FULL_NAMES[culture - len(_CULTURES)])


def author_names(rng: random.Random, count: int) -> list[str]:
    """``count`` distinct names; about two thirds come from the paper's main naming culture."""
    cultures = len(_CULTURES) + len(_FULL_NAMES)
    lab = rng.randrange(cultures)
    names: list[str] = []
    while len(names) < count:
        name = _name(rng, lab if rng.random() < 0.65 else rng.randrange(cultures))
        if name not in names:
            names.append(name)
    return names


def short_author_list(authors: list[str], limit: int = 3) -> str:
    """Reference-list form: "J. Park, W. Zhang and M. Rossi" or "J. Park, W. Zhang et al."."""
    initials = [_initials(name) for name in authors]
    if len(initials) == 1:
        return initials[0]
    if len(initials) <= limit:
        return f"{', '.join(initials[:-1])} and {initials[-1]}"
    return f"{', '.join(initials[: limit - 1])} et al."


def _initials(name: str) -> str:
    """ "Ha-eun Jung" -> "H.-E. Jung"."""
    given, _, family = name.rpartition(" ")
    first = "-".join(part[:1].upper() + "." for part in given.split("-")) if given else ""
    return f"{first} {family}".strip()
