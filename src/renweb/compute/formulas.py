"""Renewable-energy statistics from one country-year of normalised balances.

Inputs are terajoules. Electricity-output rows have already been converted
from the gigawatt-hour figures that the bulk file stores in its TJ column.
Shares are fractions, not percentages. Missing inputs are treated as zero
except shares, which are omitted when the denominator is zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from renweb.refdata.codes import (
    CONV_HYDRO,
    CONV_NUCLEAR_GEO_CSP,
    CONV_OTHER_THERMAL,
    canon,
    fallback_multipliers,
    fossil_products,
)
from renweb.refdata.countries import is_oecd

METHOD_VERSION = "2"
ENERGY = "TJ"
SHARE = "1"

SECTORS = (
    ("residential", "RESIDENT"),
    ("commercial", "COMMPUB"),
    ("industry", "TOTIND"),
    ("transport", "TOTTRANS"),
    ("agriculture", "AGRICULT"),
    ("fishing", "FISHING"),
)
SUBSECTORS = (
    ("mining", "MINING"),
    ("paper", "PAPERPRO"),
    ("chemical", "CHEMICAL"),
    ("food", "FOODPRO"),
    ("iron_steel", "IRONSTL"),
    ("nonferrous", "NONFERR"),
    ("nonmetallic", "NONMET"),
)
ELEC_TECHS = (
    ("hydropower", "HYDRO"),
    ("geothermal", "GEOTHERM"),
    ("solar_pv", "SOLARPV"),
    ("csp", "SOLARTH"),
    ("ocean", "OCEAN"),
    ("wind", "WIND"),
)
BIO_PRODUCTS = (
    "PRIMSBIO",
    "CHARCOAL",
    "BIOGAS",
    "BIOGASES",
    "BIOGASOL",
    "BIODIESEL",
    "OTHLIQBIO",
    "BIOJETKERO",
    "MUNWASTE",
    "MUNWASTER",
)
OWN_USE = {
    "fossil": ("COALMINES", "OILGAS", "GASWORKS", "PATFUEL", "BKBPB", "OILREF"),
    "nuclear": ("NUCIND",),
    "biomass": ("CHARCOAL",),
    "hydro": ("PUMPSTOR",),
    "other": ("BLASTFUR", "COKEOVENS"),
    "plants": ("ELECPLT", "CHPPLT", "HEATPLT"),
}
BASE_FLOWS = ("IMPORTS", "EXPORTS", "STATDIFF", "TOTTRANSF")
MULTIPLIER_FLOOR = 0.5
MULTIPLIER_CEILING = 1.5


@dataclass
class Frame:
    """Flow × product values in TJ, keyed by canonical codes."""

    rows: dict[tuple[str, str], float]

    @classmethod
    def from_pairs(cls, pairs: dict[tuple[str, str], float]) -> Frame:
        folded: dict[tuple[str, str], float] = {}
        for (flow, product), value in pairs.items():
            key = (canon(flow), canon(product))
            folded[key] = folded.get(key, 0.0) + float(value)
        return cls(folded)

    def get(self, flow: str, product: str) -> float:
        return self.rows.get((canon(flow), canon(product)), 0.0)

    def get_sum(self, flow: str, products: tuple[str, ...] | list[str]) -> float:
        seen: set[str] = set()
        total = 0.0
        for product in products:
            key = canon(product)
            if key in seen:
                continue
            seen.add(key)
            total += self.get(flow, product)
        return total

    def flow_abs(self, flows: tuple[str, ...], product: str = "ELECTR") -> float:
        seen: set[str] = set()
        total = 0.0
        for flow in flows:
            key = canon(flow)
            if key in seen:
                continue
            seen.add(key)
            total += abs(self.get(flow, product))
        return total


def _add(
    out: dict[str, tuple[float, str]], name: str, value: float | None, unit: str
) -> None:
    if value is None:
        return
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return
    out[name] = (number, unit)


def _share(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _first(frame: Frame, flows: tuple[str, ...], product: str) -> float:
    for flow in flows:
        value = frame.get(flow, product)
        if value:
            return value
    return 0.0


def adjustment_multipliers(frame: Frame) -> tuple[dict[str, float], bool]:
    """Technology multipliers from own-use and losses, else the vendored constants.

    Quantities are taken as absolute values. The bulk file stores some of
    these flows as negative consumption. A multiplier outside 0.5–1.5 means
    the own-use identity did not close, and the vendored constants are used.
    """
    fallback = fallback_multipliers()
    base = frame.flow_abs(BASE_FLOWS)
    if base == 0:
        return fallback, True
    losses_share = frame.flow_abs(("LOSSES",)) / base
    category = {name: frame.flow_abs(flows) / base for name, flows in OWN_USE.items()}

    def multiplier(offset: float, *categories: str) -> float:
        extra = sum(category[name] for name in categories)
        factor = -(offset + extra + losses_share)
        return 1.0 - factor

    computed = {
        "hydropower": multiplier(CONV_HYDRO, "hydro"),
        "geothermal": multiplier(CONV_NUCLEAR_GEO_CSP, "other"),
        "solar_pv": multiplier(0.0, "other"),
        "csp": multiplier(CONV_NUCLEAR_GEO_CSP, "other"),
        "ocean": multiplier(0.0, "other"),
        "wind": multiplier(0.0, "other"),
        "biopower": multiplier(CONV_OTHER_THERMAL, "biomass", "other"),
        "nuclear": multiplier(CONV_NUCLEAR_GEO_CSP, "nuclear", "other"),
    }
    if any(
        value < MULTIPLIER_FLOOR or value > MULTIPLIER_CEILING
        for value in computed.values()
    ):
        return fallback, True
    return computed, False


def _allocated(frame: Frame) -> dict[str, float]:
    raw = {name: frame.get(flow, "TOTAL") for name, flow in SECTORS}
    base = sum(raw.values())
    non_energy = frame.get("NONENUSE", "TOTAL")
    if base == 0:
        return raw
    return {name: value - (value / base) * non_energy for name, value in raw.items()}


def _bioenergy(frame: Frame, flow: str) -> float:
    return (
        frame.get(flow, "MRENEW")
        - frame.get(flow, "GEOTHERM")
        - frame.get(flow, "SOLARTH")
    )


def compute_one(
    frame: Frame,
    country: str,
    year: int,
) -> dict[str, tuple[float, str]]:
    out: dict[str, tuple[float, str]] = {}
    oecd = is_oecd(country)
    traditional = (
        0.0
        if oecd
        else (frame.get("RESIDENT", "PRIMSBIO") + frame.get("RESIDENT", "CHARCOAL"))
    )
    industry_bio = _bioenergy(frame, "TOTIND")
    agri_bio = _bioenergy(frame, "AGRICULT")
    fishing_bio = _bioenergy(frame, "FISHING")
    commercial_bio = _bioenergy(frame, "COMMPUB")
    residential_bio = _bioenergy(frame, "RESIDENT")

    _add(out, "heatbio_industry_bioenergy_tj", industry_bio, ENERGY)
    _add(out, "heatbio_agriculture_bioenergy_tj", agri_bio, ENERGY)
    _add(out, "heatbio_fishing_bioenergy_tj", fishing_bio, ENERGY)
    _add(out, "heatbio_commercial_bioenergy_tj", commercial_bio, ENERGY)
    _add(out, "heatbio_residential_bioenergy_tj", residential_bio, ENERGY)
    _add(out, "heatbio_traditional_biomass_tj", traditional, ENERGY)
    _add(
        out,
        "heatbio_industry_agriculture_bioenergy_tj",
        industry_bio + agri_bio,
        ENERGY,
    )

    elec_total = frame.get("ELOUTPUT", "TOTAL")
    elec_renew_out = frame.get("ELOUTPUT", "MRENEW")
    elec_nuclear_out = frame.get("ELOUTPUT", "NUCLEAR")
    heat_total = frame.get("HEATOUT", "TOTAL")
    heat_renew_out = frame.get("HEATOUT", "MRENEW")
    heat_nuclear_out = frame.get("HEATOUT", "NUCLEAR")
    gen_renew_share = _share(elec_renew_out, elec_total)
    gen_nuclear_share = _share(elec_nuclear_out, elec_total)
    heat_renew_share = _share(heat_renew_out, heat_total)
    heat_nuclear_share = _share(heat_nuclear_out, heat_total)
    biopower = frame.get_sum("ELOUTPUT", BIO_PRODUCTS)
    tfc = frame.get("TFC", "TOTAL")
    non_energy = frame.get("NONENUSE", "TOTAL")
    tfc_elec = frame.get("TFC", "ELECTR")
    tfc_heat = frame.get("TFC", "HEAT")
    tfc_renew = frame.get("TFC", "MRENEW")
    tes = _first(frame, ("TES", "SUPPLY"), "TOTAL")
    fossil_imports = frame.get_sum("IMPORTS", fossil_products())
    if fossil_imports == 0:
        fossil_imports = frame.get("IMPORTS", "MFOSSIL")

    _add(out, "raw_tfc_total_tj", tfc, ENERGY)
    _add(out, "raw_non_energy_use_tj", non_energy, ENERGY)
    _add(out, "raw_tfc_renewable_tj", tfc_renew, ENERGY)
    _add(out, "raw_tfc_electricity_tj", tfc_elec, ENERGY)
    _add(out, "raw_tfc_heat_tj", tfc_heat, ENERGY)
    _add(out, "raw_electricity_output_total_tj", elec_total, ENERGY)
    _add(out, "raw_electricity_output_renewable_tj", elec_renew_out, ENERGY)
    _add(out, "raw_electricity_output_nuclear_tj", elec_nuclear_out, ENERGY)
    _add(out, "raw_electricity_output_biopower_tj", biopower, ENERGY)
    for name, product in ELEC_TECHS:
        _add(
            out,
            f"raw_electricity_output_{name}_tj",
            (
                frame.get("ELOUTPUT", product)
                if name != "ocean"
                else frame.get_sum("ELOUTPUT", ("OCEAN", "TIDE"))
            ),
            ENERGY,
        )
    _add(out, "raw_electricity_renewable_share", gen_renew_share, SHARE)
    _add(out, "raw_electricity_nuclear_share", gen_nuclear_share, SHARE)
    _add(out, "raw_heat_output_total_tj", heat_total, ENERGY)
    _add(out, "raw_heat_output_renewable_tj", heat_renew_out, ENERGY)
    _add(out, "raw_heat_output_nuclear_tj", heat_nuclear_out, ENERGY)
    _add(out, "raw_heat_renewable_share", heat_renew_share, SHARE)
    _add(out, "raw_heat_nuclear_share", heat_nuclear_share, SHARE)
    if gen_renew_share is not None:
        _add(
            out, "raw_tfc_electricity_renewable_tj", tfc_elec * gen_renew_share, ENERGY
        )
    if gen_nuclear_share is not None:
        _add(
            out, "raw_tfc_electricity_nuclear_tj", tfc_elec * gen_nuclear_share, ENERGY
        )
    if heat_renew_share is not None:
        _add(out, "raw_tfc_heat_renewable_tj", tfc_heat * heat_renew_share, ENERGY)
    if heat_nuclear_share is not None:
        _add(out, "raw_tfc_heat_nuclear_tj", tfc_heat * heat_nuclear_share, ENERGY)
    biofuels = frame.get_sum("TOTTRANS", BIO_PRODUCTS)
    _add(out, "raw_biofuels_transport_tj", biofuels, ENERGY)
    _add(out, "raw_traditional_biomass_tj", traditional, ENERGY)
    _add(out, "raw_tes_tj", tes, ENERGY)
    _add(out, "raw_fossil_imports_tj", fossil_imports, ENERGY)
    for name, flow in SECTORS:
        _add(out, f"raw_tfc_{name}_tj", frame.get(flow, "TOTAL"), ENERGY)

    multipliers, used_fallback = adjustment_multipliers(frame)
    for name, value in multipliers.items():
        _add(out, f"adjustment_multiplier_{name}", value, SHARE)
    _add(out, "adjustment_used_fallback", 1.0 if used_fallback else 0.0, SHARE)

    tech_tj = {}
    for name, product in ELEC_TECHS:
        output = (
            frame.get_sum("ELOUTPUT", ("OCEAN", "TIDE"))
            if name == "ocean"
            else frame.get("ELOUTPUT", product)
        )
        tech_tj[name] = output * multipliers[name]
        _add(out, f"adjusted_tfec_electricity_{name}_tj", tech_tj[name], ENERGY)
    biopower_tj = biopower * multipliers["biopower"]
    _add(out, "adjusted_tfec_electricity_biopower_tj", biopower_tj, ENERGY)
    elec_renew = sum(tech_tj.values()) + biopower_tj
    elec_nuclear = elec_nuclear_out * multipliers["nuclear"]
    _add(out, "adjusted_tfec_electricity_renewable_tj", elec_renew, ENERGY)
    _add(out, "adjusted_tfec_electricity_nuclear_tj", elec_nuclear, ENERGY)

    heat_renew = tfc_heat * (heat_renew_share or 0.0)
    heat_nuclear = tfc_heat * (heat_nuclear_share or 0.0)
    tfec = tfc - non_energy
    renewable = elec_renew + tfc_renew + heat_renew
    nuclear = elec_nuclear + heat_nuclear
    fossil = tfec - nuclear - renewable
    modern = renewable - traditional
    _add(out, "adjusted_tfec_tj", tfec, ENERGY)
    _add(out, "adjusted_tfec_renewable_tj", renewable, ENERGY)
    _add(out, "adjusted_tfec_nuclear_tj", nuclear, ENERGY)
    _add(out, "adjusted_tfec_fossil_tj", fossil, ENERGY)
    _add(out, "adjusted_tfec_traditional_biomass_tj", traditional, ENERGY)
    _add(out, "adjusted_tfec_modern_renewables_tj", modern, ENERGY)
    _add(out, "adjusted_tfec_renewable_share", _share(renewable, tfec), SHARE)
    _add(out, "adjusted_tfec_nuclear_share", _share(nuclear, tfec), SHARE)
    _add(out, "adjusted_tfec_fossil_share", _share(fossil, tfec), SHARE)
    _add(
        out, "adjusted_tfec_traditional_biomass_share", _share(traditional, tfec), SHARE
    )
    _add(out, "adjusted_tfec_modern_renewables_share", _share(modern, tfec), SHARE)

    allocated = _allocated(frame)
    for name, value in allocated.items():
        _add(out, f"adjusted_tfec_{name}_tj", value, ENERGY)
    buildings_tfec = allocated["residential"] + allocated["commercial"]
    _add(out, "adjusted_tfec_buildings_tj", buildings_tfec, ENERGY)

    final_renew_share = _share(elec_renew, tfc_elec)
    if final_renew_share is None:
        final_renew_share = gen_renew_share
    _add(out, "renewable_electricity_share", final_renew_share, SHARE)

    _add(
        out,
        "sectoral_tfec_share_transport",
        _share(allocated["transport"], tfec),
        SHARE,
    )
    _add(
        out, "sectoral_tfec_share_industry", _share(allocated["industry"], tfec), SHARE
    )
    _add(out, "sectoral_tfec_share_buildings", _share(buildings_tfec, tfec), SHARE)
    agri_tfec = allocated["agriculture"] + allocated["fishing"]
    _add(out, "sectoral_tfec_share_agriculture", _share(agri_tfec, tfec), SHARE)

    gen_fossil = elec_total - elec_nuclear_out - elec_renew_out
    _add(out, "power_electricity_output_tj", elec_total, ENERGY)
    _add(out, "power_electricity_output_fossil_tj", gen_fossil, ENERGY)
    _add(out, "power_electricity_output_nuclear_tj", elec_nuclear_out, ENERGY)
    _add(out, "power_electricity_output_renewable_tj", elec_renew_out, ENERGY)
    _add(out, "power_share_fossil", _share(gen_fossil, elec_total), SHARE)
    _add(out, "power_share_nuclear", gen_nuclear_share, SHARE)
    _add(out, "power_share_renewable", gen_renew_share, SHARE)
    _add(out, "power_tfec_electricity_renewable_tj", elec_renew, ENERGY)
    for name, product in ELEC_TECHS:
        output = (
            frame.get_sum("ELOUTPUT", ("OCEAN", "TIDE"))
            if name == "ocean"
            else frame.get("ELOUTPUT", product)
        )
        _add(out, f"power_share_{name}", _share(output, elec_total), SHARE)
    _add(out, "power_share_biopower", _share(biopower, elec_total), SHARE)

    s_re = gen_renew_share or 0.0
    s_nuc = gen_nuclear_share or 0.0
    h_re = heat_renew_share or 0.0
    h_nuc = heat_nuclear_share or 0.0

    solar_heat = sum(frame.get(flow, "SOLARTH") for _, flow in SECTORS)
    geo_heat = sum(frame.get(flow, "GEOTHERM") for _, flow in SECTORS)
    _add(out, "heat_tfc_tj", tfc_heat, ENERGY)
    _add(out, "heat_tfc_renewable_tj", heat_renew, ENERGY)
    _add(out, "heat_solar_tj", solar_heat, ENERGY)
    _add(out, "heat_geothermal_tj", geo_heat, ENERGY)
    _add(
        out,
        "heat_modern_bioenergy_tj",
        max(industry_bio, 0.0)
        + max(agri_bio, 0.0)
        + max(fishing_bio, 0.0)
        + max(commercial_bio, 0.0)
        + max(residential_bio - traditional, 0.0),
        ENERGY,
    )
    _add(out, "heat_traditional_biomass_tj", traditional, ENERGY)
    _add(out, "heat_renewable_share", heat_renew_share, SHARE)

    def sector_bundle(
        flow: str, tfec_value: float
    ) -> tuple[float, float, float, float]:
        elec = frame.get(flow, "ELECTR")
        bio = _bioenergy(frame, flow)
        district = frame.get(flow, "HEAT") * h_re
        renew = frame.get(flow, "MRENEW") + district + elec * s_re
        nuclear_part = elec * s_nuc + frame.get(flow, "HEAT") * h_nuc
        fossil_part = tfec_value - renew - nuclear_part
        return renew, fossil_part, elec * s_re, bio

    transport_elec = frame.get("TOTTRANS", "ELECTR")
    transport_elec_re = transport_elec * s_re
    transport_renew = biofuels + transport_elec_re
    transport_nuclear = transport_elec * s_nuc
    transport_fossil = allocated["transport"] - transport_renew - transport_nuclear
    _add(out, "transport_tfec_tj", allocated["transport"], ENERGY)
    _add(out, "transport_biofuels_tj", biofuels, ENERGY)
    _add(out, "transport_electricity_tj", transport_elec, ENERGY)
    _add(out, "transport_electricity_renewable_tj", transport_elec_re, ENERGY)
    _add(out, "transport_renewable_tj", transport_renew, ENERGY)
    _add(out, "transport_fossil_tj", transport_fossil, ENERGY)
    _add(
        out,
        "transport_renewable_share",
        _share(transport_renew, allocated["transport"]),
        SHARE,
    )
    _add(
        out,
        "transport_fossil_share",
        _share(transport_fossil, allocated["transport"]),
        SHARE,
    )
    _add(
        out,
        "transport_biofuels_share",
        _share(biofuels, allocated["transport"]),
        SHARE,
    )

    b_elec = frame.get("RESIDENT", "ELECTR") + frame.get("COMMPUB", "ELECTR")
    b_solar = frame.get("RESIDENT", "SOLARTH") + frame.get("COMMPUB", "SOLARTH")
    b_geo = frame.get("RESIDENT", "GEOTHERM") + frame.get("COMMPUB", "GEOTHERM")
    b_district = (frame.get("RESIDENT", "HEAT") + frame.get("COMMPUB", "HEAT")) * h_re
    b_modern_bio = max(residential_bio - traditional, 0.0) + max(commercial_bio, 0.0)
    b_elec_re = b_elec * s_re
    b_renew = b_modern_bio + b_elec_re + b_solar + b_geo + b_district
    b_nuclear = (
        b_elec * s_nuc
        + (frame.get("RESIDENT", "HEAT") + frame.get("COMMPUB", "HEAT")) * h_nuc
    )
    b_fossil = buildings_tfec - b_renew - traditional - b_nuclear
    _add(out, "buildings_tfec_tj", buildings_tfec, ENERGY)
    _add(out, "buildings_electricity_tj", b_elec, ENERGY)
    _add(out, "buildings_electricity_renewable_tj", b_elec_re, ENERGY)
    _add(out, "buildings_traditional_biomass_tj", traditional, ENERGY)
    _add(out, "buildings_modern_bioenergy_tj", b_modern_bio, ENERGY)
    _add(out, "buildings_solar_tj", b_solar, ENERGY)
    _add(out, "buildings_geothermal_tj", b_geo, ENERGY)
    _add(out, "buildings_district_heat_renewable_tj", b_district, ENERGY)
    _add(out, "buildings_renewable_tj", b_renew, ENERGY)
    _add(out, "buildings_fossil_tj", b_fossil, ENERGY)
    _add(out, "buildings_renewable_share", _share(b_renew, buildings_tfec), SHARE)
    _add(
        out,
        "buildings_traditional_biomass_share",
        _share(traditional, buildings_tfec),
        SHARE,
    )

    ind_renew, ind_fossil, ind_elec_re, ind_bio = sector_bundle(
        "TOTIND", allocated["industry"]
    )
    _add(out, "industry_tfec_tj", allocated["industry"], ENERGY)
    _add(out, "industry_renewable_tj", ind_renew, ENERGY)
    _add(out, "industry_fossil_tj", ind_fossil, ENERGY)
    _add(
        out,
        "industry_renewable_share",
        _share(ind_renew, allocated["industry"]),
        SHARE,
    )
    _add(out, "industry_electricity_renewable_tj", ind_elec_re, ENERGY)
    _add(out, "industry_bioenergy_tj", ind_bio, ENERGY)
    _add(out, "industry_solar_tj", frame.get("TOTIND", "SOLARTH"), ENERGY)
    _add(out, "industry_geothermal_tj", frame.get("TOTIND", "GEOTHERM"), ENERGY)
    for name, flow in SUBSECTORS:
        sub_total = frame.get(flow, "TOTAL")
        sub_renew = (
            frame.get(flow, "MRENEW")
            + frame.get(flow, "HEAT") * h_re
            + frame.get(flow, "ELECTR") * s_re
        )
        _add(out, f"industry_{name}_tfec_tj", sub_total, ENERGY)
        _add(
            out,
            f"industry_{name}_renewable_share",
            _share(sub_renew, sub_total),
            SHARE,
        )

    agri_renew_a, agri_fossil_a, agri_elec_a, agri_bio_a = sector_bundle(
        "AGRICULT", allocated["agriculture"]
    )
    fish_renew, fish_fossil, fish_elec, fish_bio_v = sector_bundle(
        "FISHING", allocated["fishing"]
    )
    _add(out, "agriculture_tfec_tj", agri_tfec, ENERGY)
    _add(out, "agriculture_renewable_tj", agri_renew_a + fish_renew, ENERGY)
    _add(out, "agriculture_fossil_tj", agri_fossil_a + fish_fossil, ENERGY)
    _add(
        out,
        "agriculture_renewable_share",
        _share(agri_renew_a + fish_renew, agri_tfec),
        SHARE,
    )
    _add(out, "agriculture_electricity_renewable_tj", agri_elec_a + fish_elec, ENERGY)
    _add(out, "agriculture_bioenergy_tj", agri_bio_a + fish_bio_v, ENERGY)

    _add(out, "economy_tfec_tj", tfec, ENERGY)
    _add(out, "economy_tfec_fossil_tj", fossil, ENERGY)
    _add(out, "economy_tfec_nuclear_tj", nuclear, ENERGY)
    _add(out, "economy_tfec_renewable_tj", renewable, ENERGY)
    _add(out, "economy_tfec_traditional_biomass_tj", traditional, ENERGY)
    _add(out, "economy_tfec_modern_renewables_tj", modern, ENERGY)
    _add(out, "economy_share_fossil", _share(fossil, tfec), SHARE)
    _add(out, "economy_share_nuclear", _share(nuclear, tfec), SHARE)
    _add(out, "economy_share_renewable", _share(renewable, tfec), SHARE)
    _add(out, "economy_share_traditional_biomass", _share(traditional, tfec), SHARE)
    _add(out, "economy_share_modern_renewables", _share(modern, tfec), SHARE)
    _add(out, "economy_tes_tj", tes, ENERGY)
    _add(out, "economy_fossil_import_ratio", _share(fossil_imports, tes), SHARE)

    enduse = {
        "buildings": (buildings_tfec, b_renew),
        "industry": (allocated["industry"], ind_renew),
        "agriculture": (agri_tfec, agri_renew_a + fish_renew),
        "transport": (allocated["transport"], transport_renew),
    }
    for name, (total, renew) in enduse.items():
        _add(out, f"enduse_tfec_{name}_tj", total, ENERGY)
        _add(out, f"enduse_share_{name}", _share(total, tfec), SHARE)
        _add(out, f"enduse_renewable_{name}_tj", renew, ENERGY)
        _add(out, f"enduse_renewable_share_{name}", _share(renew, total), SHARE)
    _add(
        out,
        "enduse_unallocated_tj",
        tfec - sum(total for total, _ in enduse.values()),
        ENERGY,
    )
    return out
