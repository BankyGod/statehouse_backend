"""Seed institutions + concrete programs across United Amir."""

from app.models.education import (
    EDUCATION_CATALOG,
    EducationTrack,
    InstitutionKind,
    InstitutionOwnership,
)

# slug, name, kind, ownership, state_slug, prestige, description, enterprise_slug|None
INSTITUTIONS: list[dict] = [
    {
        "slug": "nuua",
        "name": "National University of United Amir",
        "kind": InstitutionKind.PUBLIC_UNIVERSITY,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "amira-central",
        "prestige": 5,
        "description": "Flagship public university in Amirabad.",
        "enterprise_slug": "uanus",
        "programs": [
            ("BSc Computer Science", EducationTrack.BACHELORS, 0),
            ("BA Economics", EducationTrack.BACHELORS, 0),
            ("LLB Law", EducationTrack.LAW, 3),
            ("MBA", EducationTrack.MASTERS, 3),
            ("Certificate in Public Admin", EducationTrack.SHORT_COURSE, 0),
        ],
    },
    {
        "slug": "capital-poly",
        "name": "Capital Polytechnic",
        "kind": InstitutionKind.POLYTECHNIC,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "amira-central",
        "prestige": 3,
        "description": "Applied diplomas and short courses for civil service pathways.",
        "enterprise_slug": "uanus",
        "programs": [
            ("Diploma in Accounting", EducationTrack.DIPLOMA, 0),
            ("Diploma in IT Support", EducationTrack.DIPLOMA, 0),
            ("Certificate in Office Skills", EducationTrack.SHORT_COURSE, 0),
        ],
    },
    {
        "slug": "college-row",
        "name": "College Row University",
        "kind": InstitutionKind.PUBLIC_UNIVERSITY,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "scholars-haven",
        "prestige": 5,
        "description": "Research-heavy campus in Scholar's Haven.",
        "enterprise_slug": "uanus",
        "programs": [
            ("BSc Biology", EducationTrack.BACHELORS, 0),
            ("BA History", EducationTrack.BACHELORS, 0),
            ("MSc Data Science", EducationTrack.MASTERS, 3),
            ("PhD Prep Seminar", EducationTrack.SHORT_COURSE, 3),
        ],
    },
    {
        "slug": "haven-private",
        "name": "Haven Private College",
        "kind": InstitutionKind.PRIVATE_UNIVERSITY,
        "ownership": InstitutionOwnership.PRIVATE,
        "state_slug": "scholars-haven",
        "prestige": 4,
        "description": "Selective private college — higher fees, faster tracks.",
        "enterprise_slug": None,
        "programs": [
            ("BBA Business Administration", EducationTrack.BACHELORS, 0, 1.25),
            ("Executive MBA", EducationTrack.MASTERS, 3, 1.35),
            ("Certificate in Entrepreneurship", EducationTrack.SHORT_COURSE, 0, 1.2),
        ],
    },
    {
        "slug": "defence-academy",
        "name": "Northwatch Defence Academy",
        "kind": InstitutionKind.MILITARY_ACADEMY,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "northwatch",
        "prestige": 4,
        "description": "Basic training and defence studies for United Amir forces.",
        "enterprise_slug": None,
        "programs": [
            ("Military Basic Training", EducationTrack.MILITARY_BASIC, 0),
            ("Diploma in Logistics", EducationTrack.DIPLOMA, 0),
        ],
    },
    {
        "slug": "health-sciences",
        "name": "Crystal Springs Health Sciences Institute",
        "kind": InstitutionKind.MEDICAL_SCHOOL,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "crystal-springs",
        "prestige": 5,
        "description": "National medical school and clinical training.",
        "enterprise_slug": "uanus",
        "programs": [
            ("Doctor of Medicine", EducationTrack.MEDICAL, 3),
            ("Diploma in Nursing", EducationTrack.DIPLOMA, 0),
            ("Certificate in First Aid", EducationTrack.SHORT_COURSE, 0),
        ],
    },
    {
        "slug": "silkmarket-trade",
        "name": "Silkmarket Trade Institute",
        "kind": InstitutionKind.POLYTECHNIC,
        "ownership": InstitutionOwnership.PRIVATE,
        "state_slug": "silkmarket",
        "prestige": 3,
        "description": "Trade, textiles, and small-business diplomas.",
        "enterprise_slug": None,
        "programs": [
            ("Diploma in Merchandising", EducationTrack.DIPLOMA, 0),
            ("Certificate in Market Trading", EducationTrack.SHORT_COURSE, 0),
            ("BSc Supply Chain", EducationTrack.BACHELORS, 0),
        ],
    },
    {
        "slug": "meridian-maritime",
        "name": "Meridian Maritime College",
        "kind": InstitutionKind.POLYTECHNIC,
        "ownership": InstitutionOwnership.PRIVATE,
        "state_slug": "port-meridian",
        "prestige": 3,
        "description": "Shipping, logistics, and port operations training.",
        "enterprise_slug": None,
        "programs": [
            ("Diploma in Maritime Ops", EducationTrack.DIPLOMA, 0),
            ("Certificate in Customs Brokerage", EducationTrack.SHORT_COURSE, 0),
        ],
    },
    {
        "slug": "golden-coast-hospitality",
        "name": "Lagune Hospitality School",
        "kind": InstitutionKind.PRIVATE_UNIVERSITY,
        "ownership": InstitutionOwnership.PRIVATE,
        "state_slug": "golden-coast",
        "prestige": 3,
        "description": "Tourism and hospitality programs on the coast.",
        "enterprise_slug": None,
        "programs": [
            ("Diploma in Hospitality", EducationTrack.DIPLOMA, 0),
            ("Certificate in Culinary Basics", EducationTrack.SHORT_COURSE, 0),
        ],
    },
    {
        "slug": "ironridge-tech",
        "name": "Ironridge Technical Institute",
        "kind": InstitutionKind.POLYTECHNIC,
        "ownership": InstitutionOwnership.GOVERNMENT,
        "state_slug": "ironridge",
        "prestige": 3,
        "description": "Heavy industry and engineering diplomas.",
        "enterprise_slug": "uanus",
        "programs": [
            ("Diploma in Mechanical Engineering", EducationTrack.DIPLOMA, 0),
            ("Certificate in Workplace Safety", EducationTrack.SHORT_COURSE, 0),
            ("BEng Industrial Systems", EducationTrack.BACHELORS, 2),
        ],
    },
]


def program_metrics(track: EducationTrack, cost_mult: float = 1.0) -> dict:
    meta = EDUCATION_CATALOG[track]
    return {
        "real_days": meta["real_days"] * (0.9 if cost_mult > 1.1 else 1.0),
        "age_years": meta["age_years"],
        "cost": round(meta["cost"] * cost_mult, 2),
        "level": meta["level"],
    }
