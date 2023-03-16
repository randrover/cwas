"""
Default category domain information for CWAS project.
"""
from copy import deepcopy

# This domain dictionary is incomplete.
# 'conservation' domains are added by BigWig file keys.
# 'gene_list' domains are added by gene matrix.
# 'region' domains are added by BED file keys.
_default_domains = {
    "variant_type": ["All", "SNV", "Indel"],
    "conservation": ["All"],
    "gene_list": ["Any"],
    "gencode": [  # GENCODE annotation categories
        "Any",
        "CodingRegion",
        "FrameshiftRegion",
        "InFrameRegion",
        "SilentRegion",
        "LoFRegion",
        "DamagingMissenseRegion",
        "MissenseRegion",
        "NoncodingRegion",
        "SpliceSiteNoncanonRegion",
        "IntronRegion",
        "PromoterRegion",
        "IntergenicRegion",
        "UTRsRegion",
        "lincRnaRegion",
        "OtherTranscriptRegion",
    ],
    "region": ["Any"],  # Custom annotation categories
}

_domain_types = list(_default_domains.keys())

# A category (domain combination) that includes a redundant domain pair will be
# excluded from CWAS analysis.
_redundant_domain_pairs = {
    ("variant_type", "gencode"): {
        ("All", "FrameshiftRegion"),
        ("All", "InFrameRegion"),
        ("All", "DamagingMissenseRegion"),
        ("All", "MissenseRegion"),
        ("All", "SilentRegion"),
        ("Indel", "DamagingMissenseRegion"),
        ("Indel", "MissenseRegion"),
        ("Indel", "SilentRegion"),
        ("SNV", "FrameshiftRegion"),
        ("SNV", "InFrameRegion"),
    },
    ("gene_list", "gencode"): {
        ("Any", "CodingRegion"),
        ("Any", "FrameshiftRegion"),
        ("Any", "InFrameRegion"),
        ("Any", "LoFRegion"),
        ("Any", "DamagingMissenseRegion"),
        ("Any", "MissenseRegion"),
        ("Any", "SilentRegion"),
        ("Any", "lincRnaRegion"),
        ("lincRNA", "Any")
    },
}


def get_default_domains() -> dict:
    return deepcopy(_default_domains)


def get_domain_types() -> list:
    return deepcopy(_domain_types)


def get_redundant_domain_pairs() -> dict:
    return deepcopy(_redundant_domain_pairs)
