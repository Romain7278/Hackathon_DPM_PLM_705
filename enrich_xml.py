"""Génère le XML enrichi à partir de l'export PLM d'origine (qui n'est jamais modifié).

Conservé de l'export d'origine : structure, ID, noms, révisions courantes, masses, matériaux, positions.
Simulé pour les scénarios : maturités, dates, propriétaires, descriptions manquantes et toute la
section ext:Enrichment (coûts, fournisseurs, états historiques, interfaces, fabrication, options d'allègement).
Les notes fournisseurs, constats et motifs historiques sont calculés dans l'application.
Les fournisseurs sont fictifs ; les prix sont des hypothèses calées sur des cours publics.

Usage : python enrich_xml.py
"""
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_XML = HERE / "Hackathon dataset" / "XPDMXML_ECAR_PLM.xml"
OUTPUT_XML = HERE / "data" / "XPDMXML_ECAR_PLM_ENRICHED.xml"

XPDM_URI = "http://www.3ds.com/xsd/XPDMXML"
XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"
EXT_URI = "urn:esilv-hackathon:plm-enrichment:v1"
XPDM = f"{{{XPDM_URI}}}"
EXT = f"{{{EXT_URI}}}"

PROGRAM = {
    "referenceDate": "2026-10-14",
    "annualVolume": 48000,
    "productionWeeks": 48,
    "workingDaysPerWeek": 5,
    "sopDate": "2027-09-06",
    "releaseGateDate": "2027-03-01",
    "sellingPriceEur": 1590,
    "assemblyTestCostEur": 125,
    "finishedGoodsDays": 3,
    "lineStopPenaltyEurDay": 120000,
    "airFreightEurKg": 6.5,
    "inventoryCarryingPct": 8,
    "massTargetKg": 95.0,
    "lightweightValueEurKg": 8.0,
}

# Al et Cu : calés sur les cours publics d'octobre 2026 (prime Europe et conversion incluses).
# Autres matières : hypothèses de travail, faute de cotation publique.
MATERIALS = [
    dict(id="MAT-ALSI9", plmName="Aluminium alloy EN AC-AlSi9Cu3(Fe) (HPDC)", family="Aluminium", densityKgDm3=2.71, priceEurKg=2.95, index="LME Aluminium + prime Europe", indexShare=0.90, co2KgPerKg=4.5, inBom="true"),
    dict(id="MAT-ALSI10", plmName="Aluminium alloy EN AC-AlSi10Mg (cast)", family="Aluminium", densityKgDm3=2.68, priceEurKg=3.45, index="LME Aluminium + prime Europe", indexShare=0.90, co2KgPerKg=11.0, inBom="true"),
    dict(id="MAT-6082", plmName="Aluminium alloy EN AW-6082-T6", family="Aluminium", densityKgDm3=2.70, priceEurKg=3.50, index="LME Aluminium + prime billette", indexShare=0.85, co2KgPerKg=9.5, inBom="true"),
    dict(id="MAT-M235", plmName="Electrical steel M235-35A (laminated)", family="Acier électrique", densityKgDm3=7.60, priceEurKg=2.30, index="Acier électrique NO (contrat)", indexShare=0.85, co2KgPerKg=2.8, inBom="true"),
    dict(id="MAT-CU", plmName="Copper Cu-ETP (enamelled wire)", family="Cuivre", densityKgDm3=8.90, priceEurKg=15.00, index="LME Cuivre", indexShare=0.84, co2KgPerKg=4.2, inBom="true"),
    dict(id="MAT-20MNCR5", plmName="Case-hardening steel 20MnCr5", family="Acier", densityKgDm3=7.85, priceEurKg=1.30, index="Acier spécial (barres)", indexShare=0.80, co2KgPerKg=2.3, inBom="true"),
    dict(id="MAT-16MNCR5", plmName="Case-hardening steel 16MnCr5", family="Acier", densityKgDm3=7.85, priceEurKg=1.25, index="Acier spécial (barres)", indexShare=0.80, co2KgPerKg=2.3, inBom="true"),
    dict(id="MAT-42CRMO4", plmName="Alloy steel 42CrMo4 (quenched and tempered)", family="Acier", densityKgDm3=7.85, priceEurKg=1.50, index="Acier spécial (barres)", indexShare=0.80, co2KgPerKg=2.5, inBom="true"),
    dict(id="MAT-100CR6", plmName="Bearing steel 100Cr6 (AISI 52100)", family="Acier", densityKgDm3=7.81, priceEurKg=1.70, index="Acier à roulement", indexShare=0.75, co2KgPerKg=2.6, inBom="true"),
    dict(id="MAT-109", plmName="Steel class 10.9 (zinc-flake coated)", family="Acier", densityKgDm3=7.85, priceEurKg=1.40, index="Fil machine", indexShare=0.75, co2KgPerKg=2.4, inBom="true"),
    dict(id="MAT-S355", plmName="Structural steel S355J2", family="Acier", densityKgDm3=7.85, priceEurKg=0.85, index="Bobine laminée à chaud Europe", indexShare=0.85, co2KgPerKg=2.0, inBom="true"),
    dict(id="MAT-GJS600", plmName="Ductile cast iron EN-GJS-600-3", family="Fonte", densityKgDm3=7.10, priceEurKg=0.95, index="Ferrailles et fonte brute", indexShare=0.80, co2KgPerKg=1.6, inBom="true"),
    dict(id="MAT-PA66", plmName="Polyamide PA66-GF30", family="Polymère", densityKgDm3=1.36, priceEurKg=3.90, index="Compound PA66", indexShare=0.60, co2KgPerKg=6.5, inBom="true"),
    dict(id="MAT-FKM", plmName="FKM fluoroelastomer (steel-reinforced)", family="Polymère", densityKgDm3=1.85, priceEurKg=38.00, index="Compound FKM", indexShare=0.50, co2KgPerKg=20.0, inBom="true"),
    dict(id="MAT-AM60", plmName="Magnesium AM60B (HPDC)", family="Magnésium", densityKgDm3=1.79, priceEurKg=4.10, index="Magnésium (Chine)", indexShare=0.90, co2KgPerKg=28.0, inBom="false"),
    dict(id="MAT-AE44", plmName="Magnesium AE44 (HPDC)", family="Magnésium", densityKgDm3=1.82, priceEurKg=5.60, index="Magnésium (Chine)", indexShare=0.75, co2KgPerKg=28.0, inBom="false"),
    dict(id="MAT-AL1370", plmName="Aluminium wire EN AW-1370 (enamelled)", family="Aluminium", densityKgDm3=2.70, priceEurKg=5.80, index="LME Aluminium", indexShare=0.60, co2KgPerKg=9.5, inBom="false"),
    dict(id="MAT-NO20", plmName="Electrical steel NO20 (0.20 mm)", family="Acier électrique", densityKgDm3=7.65, priceEurKg=3.40, index="Acier électrique NO (contrat)", indexShare=0.80, co2KgPerKg=3.2, inBom="false"),
    dict(id="MAT-ADI", plmName="Austempered ductile iron ADI", family="Fonte", densityKgDm3=7.10, priceEurKg=1.35, index="Ferrailles et fonte brute", indexShare=0.60, co2KgPerKg=2.2, inBom="false"),
    dict(id="MAT-6056", plmName="Aluminium alloy EN AW-6056 (fasteners)", family="Aluminium", densityKgDm3=2.72, priceEurKg=4.20, index="LME Aluminium", indexShare=0.70, co2KgPerKg=9.5, inBom="false"),
]

# Fournisseurs fictifs : toute ressemblance avec une société existante serait fortuite.
SUPPLIERS = [
    dict(id="SUP-01", name="Voltaron Stanztechnik GmbH", country="DE", countryName="Allemagne", city="Siegen", lat=50.87, lon=8.02, region="UE", speciality="Emboutissage de tôles", certification="IATF 16949, ISO 14001", qualityPpm=38, otdPct=96.5, financialRating="A", geoRisk=1),
    dict(id="SUP-02", name="Slovlam s.r.o.", country="SK", countryName="Slovaquie", city="Košice", lat=48.72, lon=21.26, region="UE", speciality="Emboutissage de tôles", certification="IATF 16949", qualityPpm=110, otdPct=92.0, financialRating="B", geoRisk=1),
    dict(id="SUP-03", name="Yangtze Lamcore Co., Ltd.", country="CN", countryName="Chine", city="Changzhou", lat=31.81, lon=119.97, region="Asie", speciality="Emboutissage de tôles", certification="IATF 16949", qualityPpm=85, otdPct=94.0, financialRating="B", geoRisk=3),
    dict(id="SUP-04", name="Cuprotherm Wickeltechnik GmbH", country="DE", countryName="Allemagne", city="Nuremberg", lat=49.45, lon=11.08, region="UE", speciality="Bobinage en épingles", certification="IATF 16949, ISO 14001", qualityPpm=45, otdPct=97.0, financialRating="A", geoRisk=1),
    dict(id="SUP-05", name="Balkan Enamel Wire d.o.o.", country="RS", countryName="Serbie", city="Zaječar", lat=43.90, lon=22.27, region="Europe hors UE", speciality="Fil émaillé et épingles", certification="IATF 16949", qualityPpm=120, otdPct=91.0, financialRating="B", geoRisk=2),
    dict(id="SUP-06", name="Iberwire Esmaltados S.A.", country="ES", countryName="Espagne", city="Bilbao", lat=43.26, lon=-2.93, region="UE", speciality="Fil émaillé et épingles", certification="IATF 16949, ISO 14001", qualityPpm=70, otdPct=95.0, financialRating="A", geoRisk=1),
    dict(id="SUP-07", name="Garda Pressofusioni S.p.A.", country="IT", countryName="Italie", city="Brescia", lat=45.54, lon=10.22, region="UE", speciality="Fonderie aluminium HPDC et basse pression", certification="IATF 16949, ISO 14001", qualityPpm=65, otdPct=94.5, financialRating="C", geoRisk=1),
    dict(id="SUP-08", name="Bohemia Lightcast a.s.", country="CZ", countryName="Tchéquie", city="Plzeň", lat=49.74, lon=13.38, region="UE", speciality="Fonderie aluminium HPDC", certification="IATF 16949", qualityPpm=80, otdPct=93.0, financialRating="A", geoRisk=1),
    dict(id="SUP-09", name="Atlas Fonderie Automobile SARL", country="MA", countryName="Maroc", city="Tanger", lat=35.76, lon=-5.83, region="Afrique", speciality="Fonderie aluminium HPDC", certification="IATF 16949", qualityPpm=140, otdPct=90.0, financialRating="B", geoRisk=2),
    dict(id="SUP-10", name="Nordprofil Aluminium AS", country="NO", countryName="Norvège", city="Raufoss", lat=60.73, lon=10.61, region="Europe hors UE", speciality="Extrusion et soudage FSW", certification="IATF 16949, ISO 14001", qualityPpm=30, otdPct=98.0, financialRating="A", geoRisk=1),
    dict(id="SUP-11", name="Schwaben Getriebetechnik GmbH", country="DE", countryName="Allemagne", city="Friedrichshafen", lat=47.65, lon=9.48, region="UE", speciality="Engrenages rectifiés", certification="IATF 16949, ISO 14001", qualityPpm=25, otdPct=98.0, financialRating="A", geoRisk=1),
    dict(id="SUP-12", name="Moravia Gear Works a.s.", country="CZ", countryName="Tchéquie", city="Brno", lat=49.20, lon=16.61, region="UE", speciality="Engrenages rectifiés", certification="IATF 16949", qualityPpm=60, otdPct=95.0, financialRating="A", geoRisk=1),
    dict(id="SUP-13", name="Deccan Drive Gears Pvt. Ltd.", country="IN", countryName="Inde", city="Pune", lat=18.52, lon=73.86, region="Asie", speciality="Engrenages rectifiés", certification="IATF 16949", qualityPpm=95, otdPct=90.0, financialRating="B", geoRisk=2),
    dict(id="SUP-14", name="Forges du Dauphiné SAS", country="FR", countryName="France", city="Grenoble", lat=45.19, lon=5.72, region="UE", speciality="Arbres forgés et usinés", certification="IATF 16949, ISO 14001", qualityPpm=40, otdPct=96.0, financialRating="A", geoRisk=1),
    dict(id="SUP-15", name="Nordlager AB", country="SE", countryName="Suède", city="Göteborg", lat=57.71, lon=11.97, region="UE", speciality="Roulements", certification="IATF 16949, ISO 14001", qualityPpm=8, otdPct=98.5, financialRating="A", geoRisk=1),
    dict(id="SUP-16", name="Franken Wälzlager GmbH", country="DE", countryName="Allemagne", city="Schweinfurt", lat=50.05, lon=10.23, region="UE", speciality="Roulements", certification="IATF 16949, ISO 14001", qualityPpm=10, otdPct=98.0, financialRating="A", geoRisk=1),
    dict(id="SUP-17", name="Naniwa Precision Bearing K.K.", country="JP", countryName="Japon", city="Osaka", lat=34.69, lon=135.50, region="Asie", speciality="Roulements hybrides céramique", certification="IATF 16949, ISO 14001", qualityPpm=6, otdPct=97.0, financialRating="A", geoRisk=1),
    dict(id="SUP-18", name="Ductil'Est Fonderie SAS", country="FR", countryName="France", city="Pont-à-Mousson", lat=48.91, lon=6.05, region="UE", speciality="Fonderie de fonte GS", certification="IATF 16949", qualityPpm=90, otdPct=94.0, financialRating="B", geoRisk=1),
    dict(id="SUP-19", name="Anatolia Döküm A.Ş.", country="TR", countryName="Turquie", city="Bursa", lat=40.19, lon=29.06, region="Europe hors UE", speciality="Fonderie de fonte GS", certification="IATF 16949", qualityPpm=130, otdPct=91.0, financialRating="B", geoRisk=2),
    dict(id="SUP-20", name="Hanse Fasteners GmbH", country="DE", countryName="Allemagne", city="Hagen", lat=51.36, lon=7.47, region="UE", speciality="Visserie haute résistance", certification="IATF 16949, ISO 14001", qualityPpm=15, otdPct=98.0, financialRating="A", geoRisk=1),
    dict(id="SUP-21", name="Lombarda Viteria S.r.l.", country="IT", countryName="Italie", city="Lecco", lat=45.86, lon=9.40, region="UE", speciality="Visserie et décolletage", certification="IATF 16949", qualityPpm=25, otdPct=96.0, financialRating="B", geoRisk=1),
    dict(id="SUP-22", name="Formosa Bolt Industrial Co.", country="TW", countryName="Taïwan", city="Kaohsiung", lat=22.63, lon=120.30, region="Asie", speciality="Visserie haute résistance", certification="IATF 16949", qualityPpm=20, otdPct=95.0, financialRating="A", geoRisk=2),
    dict(id="SUP-23", name="Elastotec Dichtungen GmbH", country="DE", countryName="Allemagne", city="Weinheim", lat=49.55, lon=8.67, region="UE", speciality="Joints FKM haute vitesse", certification="IATF 16949, ISO 14001", qualityPpm=12, otdPct=98.0, financialRating="A", geoRisk=1),
    dict(id="SUP-24", name="Plastivallée Injection SAS", country="FR", countryName="France", city="Oyonnax", lat=46.26, lon=5.66, region="UE", speciality="Injection plastique technique", certification="IATF 16949", qualityPpm=55, otdPct=95.0, financialRating="A", geoRisk=1),
    dict(id="SUP-25", name="Décolletage de l'Arve SAS", country="FR", countryName="France", city="Cluses", lat=46.06, lon=6.58, region="UE", speciality="Décolletage de précision", certification="IATF 16949", qualityPpm=20, otdPct=97.0, financialRating="A", geoRisk=1),
]


def link(supplier, role, share, price, lead, transit, capacity, qualification, ppap=None, requal=0, ramp=2,
         switching=0, contract_end=None, clause="FIXED"):
    """Lien pièce-fournisseur. price en EUR/pièce rendu, lead et transit en jours, capacity en pièces/semaine."""
    row = dict(supplier=supplier, role=role, sharePct=share, leadTimeDays=lead, transitDays=transit,
               capacityPerWeek=capacity, qualification=qualification, requalWeeks=requal, rampUpWeeks=ramp,
               switchingCostEur=switching, priceClause=clause)
    if price is not None:
        row["unitPriceEur"] = price
    if ppap:
        row["ppapDate"] = ppap
    if contract_end:
        row["contractEnd"] = contract_end
    return row


def rev(name, date, eco, mass=None, material=None):
    row = dict(name=name, date=date, eco=eco)
    if mass is not None:
        row["massKg"] = mass
    if material:
        row["material"] = material
    return row


def option(id_, label, kind, mass_factor, cost_delta, weeks, one_off, feasibility, space, risk, material=None):
    """Option d'allègement. cost_delta en EUR par pièce, weeks = délai avant série (validation incluse)."""
    row = dict(id=id_, label=label, kind=kind, massFactor=mass_factor, costDeltaEur=cost_delta, requalWeeks=weeks,
               oneOffEur=one_off, feasibility=feasibility, spaceImpact=space, risk=risk)
    if material:
        row["newMaterial"] = material
    return row


# Pièces 3D (feuilles de la nomenclature), indexées par leur ID XML d'origine.
PARTS = {
    "ID_3": dict(
        description="Roulement arrière de l'arbre rapide, hybride céramique isolé (courants d'arbre).",
        criticality="A", safetyStockDays=15, usageKg=0.8, conversionEur=30.64,
        maturityDate="2026-07-07", plannedRelease="2026-12-15",
        sourcing=[link("SUP-17", "PRIMARY", 100, 32.0, 63, 42, 2000, "APPROVED", "2026-05-20", contract_end="2027-12-31")],
        revisions=[rev("A", "2025-02-18", "ECO-0114", 0.55)],
    ),
    "ID_5": dict(
        description="High Speed Shaft",
        criticality="A", safetyStockDays=8, usageKg=8.4, conversionEur=46.0,
        maturityDate="2026-06-23", plannedRelease="2026-12-10",
        sourcing=[
            link("SUP-14", "PRIMARY", 100, 58.6, 20, 2, 1200, "APPROVED", "2026-06-10", contract_end="2027-06-30"),
            link("SUP-11", "CANDIDATE", 0, 63.5, 18, 2, 800, "NOT_STARTED", requal=26, ramp=4, switching=240000),
        ],
        revisions=[
            rev("A", "2025-02-11", "ECO-0112", 7.3),
            rev("B", "2025-11-18", "ECO-0487", 6.8),
        ],
        options=[option("HSH-HOLLOW", "Arbre creux (forgeage orbital)", "DESIGN", 0.68, 9.0, 20, 210000, "HIGH", "Aucun : diamètres extérieurs inchangés.", "Faible : solution courante sur moteurs de traction. Réduit aussi l'inertie.")],
    ),
    "ID_7": dict(
        description="Chemise de refroidissement extrudée à canaux hélicoïdaux, soudée FSW.",
        criticality="A", safetyStockDays=10, usageKg=4.1, conversionEur=35.05,
        maturityDate="2026-07-22", plannedRelease="2027-02-12",
        sourcing=[link("SUP-10", "PRIMARY", 100, 49.4, 28, 6, 1150, "CONDITIONAL", "2027-02-05", ramp=3, contract_end="2027-09-30", clause="INDEX_Q")],
        revisions=[
            rev("A", "2025-03-04", "ECO-0130", 3.2),
            rev("B", "2026-07-22", "ECO-0861", 3.4),
        ],
        options=[option("COOL-THIN", "Parois minces et canal intégré", "DESIGN", 0.85, 2.0, 20, 90000, "MEDIUM", "Aucun : diamètre extérieur inchangé.", "Moyen : à revalider en pression à cause des micro-fuites déjà constatées.")],
    ),
    "ID_10": dict(
        physical="false", criticality="C",
        maturityDate="2025-01-20",
        revisions=[rev("A", "2025-01-20", "ECO-0096", 0.12)],
        options=[option("DATA-TOOTH", "Retirer de la nomenclature (géométrie d'étude)", "DATA", 0.0, 0.0, 0, 0, "HIGH", "Aucun.", "Aucun : correction de données, pas de pièce physique supprimée.")],
    ),
    "ID_12": dict(
        physical="false", criticality="C",
        maturityDate="2025-09-30",
        revisions=[
            rev("A", "2025-01-20", "ECO-0098", 0.18),
            rev("B", "2025-09-30", "ECO-0402", 0.16),
        ],
        options=[option("DATA-COIL", "Retirer de la nomenclature (géométrie d'étude)", "DATA", 0.0, 0.0, 0, 0, "HIGH", "Aucun.", "Aucun : correction de données, à confirmer avec l'OEM.")],
    ),
    "ID_14": dict(
        criticality="A", safetyStockDays=5, usageKg=31.0, conversionEur=46.7,
        maturityDate="2026-06-12", plannedRelease="2027-01-20",
        sourcing=[
            link("SUP-01", "PRIMARY", 100, 118.0, 15, 2, 1300, "APPROVED", "2026-04-15", contract_end="2027-12-31", clause="INDEX_Q"),
            link("SUP-02", "CANDIDATE", 0, 111.0, 18, 3, 700, "IN_PROGRESS", "2027-01-29", requal=12, ramp=3, switching=420000, clause="INDEX_Q"),
            link("SUP-03", "CANDIDATE", 0, 96.0, 60, 42, 1500, "NOT_STARTED", requal=38, ramp=6, switching=650000, clause="INDEX_Q"),
        ],
        revisions=[
            rev("A", "2025-01-20", "ECO-0097", 22.4, "Electrical steel M270-35A (laminated)"),
            rev("B", "2025-08-12", "ECO-0366", 22.4),
            rev("C", "2026-03-03", "ECO-0655", 21.5),
        ],
        options=[
            option("CORE-YOKE", "Culasse amincie et encoches optimisées", "DESIGN", 0.96, 0.0, 26, 180000, "MEDIUM", "Aucun : diamètre extérieur inchangé.", "Moyen : saturation magnétique à revérifier par simulation."),
            option("CORE-NO20", "Tôle mince NO20 et paquet raccourci de 5 %", "MATERIAL", 0.95, 21.0, 30, 240000, "MEDIUM", "Gain : longueur active réduite de 7 mm.", "Moyen : gain de rendement de 0,5 point, mais tôle plus chère et moins disponible.", "Electrical steel NO20 (0.20 mm)"),
        ],
    ),
    "ID_16": dict(
        description="Bobinage en épingles (hairpin), 8 conducteurs par encoche.",
        criticality="A", safetyStockDays=6, usageKg=7.7, conversionEur=44.0,
        maturityDate="2026-09-08", plannedRelease="2027-03-19",
        sourcing=[
            link("SUP-04", "PRIMARY", 70, 159.5, 12, 2, 900, "CONDITIONAL", "2027-02-26", contract_end="2027-12-31", clause="INDEX_M"),
            link("SUP-05", "SECONDARY", 30, 151.0, 20, 5, 450, "CONDITIONAL", "2027-03-05", ramp=3, contract_end="2027-06-30", clause="INDEX_M"),
            link("SUP-06", "CANDIDATE", 0, 156.0, 16, 4, 500, "IN_PROGRESS", "2027-02-12", requal=14, ramp=4, switching=190000, clause="INDEX_M"),
        ],
        revisions=[
            rev("A", "2025-01-20", "ECO-0099", 7.9),
            rev("B", "2026-09-08", "ECO-0912", 7.2),
        ],
        options=[option("COIL-AL", "Épingles en aluminium", "MATERIAL", 0.50, -84.0, 78, 1600000, "LOW", "Conflit : section à multiplier par 1,64, soit stator plus long de 40 mm ou plus large de 12 mm.", "Élevé : rendement en baisse d'environ 1,2 point, refonte électromagnétique complète.", "Aluminium wire EN AW-1370 (enamelled)")],
    ),
    "ID_20": dict(
        description="Boîtier de différentiel en fonte GS, couronne boulonnée.",
        criticality="B", safetyStockDays=8, usageKg=4.6, conversionEur=23.03,
        maturityDate="2026-02-17",
        sourcing=[
            link("SUP-18", "PRIMARY", 75, 27.4, 25, 2, 900, "APPROVED", "2026-01-22", contract_end="2027-12-31", clause="INDEX_Q"),
            link("SUP-19", "SECONDARY", 25, 24.8, 35, 12, 500, "APPROVED", "2026-02-05", ramp=3, contract_end="2027-06-30", clause="INDEX_Q"),
        ],
        revisions=[
            rev("A", "2025-02-25", "ECO-0121", 3.8),
            rev("B", "2025-10-07", "ECO-0431", 3.6),
        ],
        options=[option("DIFF-ADI", "Fonte ADI et parois réduites", "MATERIAL", 0.88, 2.5, 20, 70000, "MEDIUM", "Aucun.", "Moyen : traitement thermique supplémentaire, usinage plus difficile.", "Austempered ductile iron ADI")],
    ),
    "ID_22": dict(
        criticality="C", safetyStockDays=10, usageKg=0.45, conversionEur=3.44,
        maturityDate="2025-12-09",
        sourcing=[
            link("SUP-25", "PRIMARY", 80, 4.0, 15, 2, 1400, "APPROVED", "2025-11-14", contract_end="2027-12-31"),
            link("SUP-21", "SECONDARY", 20, 3.8, 18, 2, 500, "APPROVED", "2025-11-28", contract_end="2027-12-31"),
        ],
        revisions=[rev("A", "2025-03-04", "ECO-0124", 0.35)],
    ),
    "ID_24": dict(
        description="Satellite conique du différentiel.",
        criticality="B", safetyStockDays=8, usageKg=0.75, conversionEur=7.42,
        maturityDate="2025-12-09",
        sourcing=[
            link("SUP-11", "PRIMARY", 70, 8.4, 30, 2, 1800, "APPROVED", "2025-11-20", contract_end="2027-06-30"),
            link("SUP-12", "SECONDARY", 30, 8.0, 32, 3, 1200, "APPROVED", "2025-12-02", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-03-04", "ECO-0125", 0.55)],
    ),
    "ID_26": dict(
        description="Planétaire du différentiel, côté gauche et côté droit.",
        criticality="B", safetyStockDays=8, usageKg=1.2, conversionEur=10.94,
        maturityDate="2025-12-09",
        sourcing=[
            link("SUP-11", "PRIMARY", 70, 12.5, 30, 2, 1800, "APPROVED", "2025-11-20", contract_end="2027-06-30"),
            link("SUP-12", "SECONDARY", 30, 11.9, 32, 3, 1200, "APPROVED", "2025-12-02", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-03-04", "ECO-0126", 0.9)],
    ),
    "ID_30": dict(
        description="Roulement de l'arbre rapide, côté extérieur du réducteur.",
        criticality="B", safetyStockDays=15, usageKg=0.85, conversionEur=16.05,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-15", "PRIMARY", 60, 17.5, 25, 4, 1500, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
            link("SUP-16", "SECONDARY", 40, 18.0, 21, 2, 1200, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0115", 0.6)],
    ),
    "ID_32": dict(
        description="Roulement de l'arbre rapide, côté moteur.",
        criticality="B", safetyStockDays=15, usageKg=0.7, conversionEur=13.81,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-15", "PRIMARY", 60, 15.0, 25, 4, 1500, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
            link("SUP-16", "SECONDARY", 40, 15.4, 21, 2, 1200, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0116", 0.5)],
    ),
    "ID_34": dict(
        description="Roulement de sortie, côté couvercle (dans le logement de roulement).",
        criticality="B", safetyStockDays=15, usageKg=1.9, conversionEur=17.77,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-16", "PRIMARY", 70, 21.0, 21, 2, 1300, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
            link("SUP-15", "SECONDARY", 30, 21.6, 25, 4, 900, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
            link("SUP-17", "CANDIDATE", 0, 19.5, 63, 42, 1500, "IN_PROGRESS", "2027-01-15", requal=10, ramp=4, switching=45000),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0117", 1.4)],
    ),
    "ID_36": dict(
        description="Roulement de sortie, côté moteur.",
        criticality="B", safetyStockDays=15, usageKg=1.65, conversionEur=16.2,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-16", "PRIMARY", 70, 19.0, 21, 2, 1300, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
            link("SUP-15", "SECONDARY", 30, 19.5, 25, 4, 900, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0118", 1.2)],
    ),
    "ID_38": dict(
        description="Roulement de l'arbre intermédiaire, côté couvercle.",
        criticality="B", safetyStockDays=15, usageKg=1.25, conversionEur=13.88,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-15", "PRIMARY", 60, 16.0, 25, 4, 1500, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
            link("SUP-16", "SECONDARY", 40, 16.4, 21, 2, 1200, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0119", 0.9)],
    ),
    "ID_40": dict(
        description="Roulement de l'arbre intermédiaire, côté moteur.",
        criticality="B", safetyStockDays=15, usageKg=1.1, conversionEur=12.63,
        maturityDate="2025-11-05",
        sourcing=[
            link("SUP-15", "PRIMARY", 60, 14.5, 25, 4, 1500, "APPROVED", "2025-10-14", contract_end="2027-06-30"),
            link("SUP-16", "SECONDARY", 40, 14.9, 21, 2, 1200, "APPROVED", "2025-10-21", contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-18", "ECO-0120", 0.8)],
    ),
    "ID_42": dict(
        description="Pignon d'entrée, 1er étage, sur l'arbre rapide.",
        criticality="A", safetyStockDays=8, usageKg=1.9, conversionEur=22.53,
        maturityDate="2026-01-27",
        sourcing=[
            link("SUP-11", "PRIMARY", 70, 25.0, 30, 2, 1300, "APPROVED", "2025-12-16", contract_end="2027-06-30"),
            link("SUP-12", "SECONDARY", 30, 23.0, 30, 3, 800, "APPROVED", "2026-01-13", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-02-03", "ECO-0104", 1.3)],
    ),
    "ID_44": dict(
        description="Roue du 1er étage, sur l'arbre intermédiaire.",
        criticality="A", safetyStockDays=8, usageKg=5.4, conversionEur=38.98,
        maturityDate="2026-05-26", plannedRelease="2026-12-18",
        sourcing=[
            link("SUP-11", "PRIMARY", 70, 46.0, 30, 2, 900, "APPROVED", "2026-05-12", contract_end="2027-06-30"),
            link("SUP-12", "SECONDARY", 30, 43.5, 32, 3, 500, "APPROVED", "2026-05-19", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[
            rev("A", "2025-02-03", "ECO-0105", 4.2),
            rev("B", "2025-09-09", "ECO-0395", 4.0),
            rev("C", "2026-04-14", "ECO-0702", 3.9),
        ],
        options=[option("GEARC-WEB", "Voile allégé par perçages", "DESIGN", 0.90, 1.6, 24, 60000, "MEDIUM", "Aucun.", "Moyen : essai NVH et tenue du voile à refaire.")],
    ),
    "ID_46": dict(
        description="Pignon du 2e étage, sur l'arbre intermédiaire.",
        criticality="A", safetyStockDays=8, usageKg=2.3, conversionEur=25.01,
        maturityDate="2025-12-16",
        sourcing=[
            link("SUP-11", "PRIMARY", 70, 28.0, 30, 2, 900, "APPROVED", "2025-11-25", contract_end="2027-06-30"),
            link("SUP-12", "SECONDARY", 30, 26.5, 32, 3, 500, "APPROVED", "2025-12-09", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[
            rev("A", "2025-02-03", "ECO-0106", 1.7),
            rev("B", "2025-09-09", "ECO-0396", 1.6),
        ],
    ),
    "ID_48": dict(
        description="Couronne du 2e étage, boulonnée sur le boîtier de différentiel.",
        criticality="A", safetyStockDays=8, usageKg=10.4, conversionEur=57.98,
        maturityDate="2026-09-22", plannedRelease="2027-02-26",
        sourcing=[
            link("SUP-11", "PRIMARY", 100, 71.5, 30, 2, 1100, "CONDITIONAL", "2027-02-19", contract_end="2027-06-30"),
            link("SUP-12", "CANDIDATE", 0, 67.0, 32, 3, 700, "IN_PROGRESS", "2027-02-26", requal=16, ramp=4, switching=210000),
            link("SUP-13", "CANDIDATE", 0, 60.0, 65, 35, 1200, "NOT_STARTED", requal=30, ramp=6, switching=280000),
        ],
        revisions=[
            rev("A", "2025-02-03", "ECO-0107", 7.9),
            rev("B", "2025-09-09", "ECO-0397", 7.7),
            rev("C", "2026-02-17", "ECO-0634", 7.5),
            rev("D", "2026-09-22", "ECO-0931", 7.4),
        ],
        options=[option("GEARD-WEB", "Voile aminci et perçages supplémentaires", "DESIGN", 0.88, 3.2, 24, 110000, "MEDIUM", "Aucun.", "Moyen : révision D encore en essai NVH, à enchaîner avec la campagne en cours.")],
    ),
    "ID_50": dict(
        description="Arbre intermédiaire.",
        criticality="A", safetyStockDays=8, usageKg=4.6, conversionEur=38.02,
        maturityDate="2026-06-02", plannedRelease="2026-12-18",
        sourcing=[
            link("SUP-11", "PRIMARY", 100, 44.0, 30, 2, 1300, "APPROVED", "2026-05-12", contract_end="2027-06-30"),
            link("SUP-14", "CANDIDATE", 0, 46.5, 22, 2, 800, "NOT_STARTED", requal=20, ramp=4, switching=150000),
        ],
        revisions=[
            rev("A", "2025-02-10", "ECO-0110", 3.6),
            rev("B", "2025-10-21", "ECO-0450", 3.4),
        ],
        options=[option("ISH-HOLLOW", "Arbre creux", "DESIGN", 0.75, 6.5, 22, 140000, "MEDIUM", "Aucun.", "Moyen : emmanchement des pignons à revalider.")],
    ),
    "ID_53": dict(
        description="Joint à lèvre FKM haute vitesse de l'arbre rapide.",
        criticality="A", safetyStockDays=20, usageKg=0.03, conversionEur=7.36,
        maturityDate="2026-03-24",
        sourcing=[link("SUP-23", "PRIMARY", 100, 8.5, 30, 2, 1500, "APPROVED", "2026-03-10", contract_end="2027-12-31")],
        revisions=[rev("A", "2025-04-01", "ECO-0156", 0.06)],
    ),
    "ID_55": dict(
        description="Demi-carter gauche du réducteur, porte les roulements côté couvercle.",
        criticality="A", safetyStockDays=6, usageKg=9.8, conversionEur=38.0,
        maturityDate="2026-06-30", modified="2026-08-19", plannedRelease="2027-01-29",
        sourcing=[
            link("SUP-07", "PRIMARY", 100, 66.9, 21, 3, 1200, "APPROVED", "2026-06-16", contract_end="2028-03-31", clause="INDEX_Q"),
            link("SUP-08", "CANDIDATE", 0, 70.5, 24, 3, 800, "IN_PROGRESS", "2027-03-26", requal=20, ramp=6, switching=620000, clause="INDEX_Q"),
        ],
        revisions=[
            rev("A", "2025-03-18", "ECO-0142", 9.1),
            rev("B", "2026-01-13", "ECO-0588", 8.4),
        ],
        options=[
            option("LEFT-TOPO", "Optimisation topologique, voile 2,5 mm", "DESIGN", 0.90, 0.5, 16, 95000, "HIGH", "Aucun.", "Faible : retouche de moule, contrôle de la tenue vibratoire."),
            option("LEFT-MG", "Magnésium AM60B en HPDC", "MATERIAL", 0.72, 7.5, 40, 780000, "MEDIUM", "Local : parois 15 % plus épaisses, inserts acier aux portées.", "Élevé : corrosion, fluage aux portées, offre très concentrée en Chine, CO2 matière en forte hausse.", "Magnesium AM60B (HPDC)"),
        ],
    ),
    "ID_57": dict(
        description="Demi-carter droit du réducteur, porte les roulements côté moteur.",
        criticality="A", safetyStockDays=6, usageKg=6.9, conversionEur=29.0,
        maturityDate="2026-08-25", plannedRelease="2027-02-05",
        sourcing=[
            link("SUP-07", "PRIMARY", 100, 49.4, 21, 3, 1200, "CONDITIONAL", "2027-01-22", contract_end="2028-03-31", clause="INDEX_Q"),
            link("SUP-08", "CANDIDATE", 0, 52.0, 24, 3, 800, "IN_PROGRESS", "2027-03-26", requal=20, ramp=6, switching=480000, clause="INDEX_Q"),
        ],
        revisions=[
            rev("A", "2025-03-18", "ECO-0143", 6.4),
            rev("B", "2025-12-02", "ECO-0541", 6.1),
            rev("C", "2026-08-25", "ECO-0889", 5.9),
        ],
        options=[
            option("RIGHT-TOPO", "Optimisation topologique, voile 2,5 mm", "DESIGN", 0.90, 0.4, 16, 80000, "HIGH", "Aucun.", "Faible : retouche de moule, contrôle de la tenue vibratoire."),
            option("RIGHT-MG", "Magnésium AM60B en HPDC", "MATERIAL", 0.72, 5.5, 40, 620000, "MEDIUM", "Local : parois 15 % plus épaisses, inserts acier aux portées.", "Élevé : corrosion, fluage aux portées, offre très concentrée en Chine, CO2 matière en forte hausse.", "Magnesium AM60B (HPDC)"),
        ],
    ),
    "ID_59": dict(
        description="Logement du roulement de sortie, côté couvercle.",
        criticality="B", safetyStockDays=8, usageKg=2.5, conversionEur=12.03,
        maturityDate="2026-03-03",
        sourcing=[
            link("SUP-07", "PRIMARY", 70, 19.4, 21, 3, 1000, "APPROVED", "2026-02-17", contract_end="2028-03-31", clause="INDEX_Q"),
            link("SUP-09", "SECONDARY", 30, 17.6, 28, 6, 500, "APPROVED", "2026-02-24", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[
            rev("A", "2025-04-08", "ECO-0158", 2.2),
            rev("B", "2025-12-16", "ECO-0560", 2.1),
        ],
    ),
    "ID_61": dict(
        description="Carter du moteur, coulé en basse pression, reçoit le stator fretté.",
        criticality="A", safetyStockDays=6, usageKg=8.4, conversionEur=46.02,
        maturityDate="2026-09-01", plannedRelease="2027-01-15",
        sourcing=[link("SUP-07", "PRIMARY", 100, 75.0, 21, 3, 1150, "APPROVED", "2026-08-28", contract_end="2028-03-31", clause="INDEX_Q")],
        revisions=[
            rev("A", "2025-03-25", "ECO-0150", 7.6, "Aluminium alloy EN AC-AlSi9Cu3(Fe) (HPDC)"),
            rev("B", "2025-09-23", "ECO-0411", 7.3),
            rev("C", "2026-05-12", "ECO-0748", 7.0),
        ],
        options=[
            option("MOTOR-THIN", "Parois réduites et noyau optimisé", "DESIGN", 0.90, 1.5, 18, 120000, "HIGH", "Aucun.", "Faible à moyen : contrôle de l'étanchéité et de la tenue du frettage."),
            option("MOTOR-MG", "Magnésium AE44", "MATERIAL", 0.74, 11.0, 52, 950000, "LOW", "Conflit : dilatation différente, le frettage du stator se desserre à chaud.", "Élevé : fluage, corrosion par le liquide de refroidissement, offre concentrée en Chine.", "Magnesium AE44 (HPDC)"),
        ],
    ),
    "ID_63": dict(
        criticality="B", safetyStockDays=8, usageKg=1.5, conversionEur=5.53,
        maturityDate="2026-06-30", plannedRelease="2027-03-05",
        sourcing=[],
        revisions=[
            rev("A", "2025-04-15", "ECO-0163", 1.2),
            rev("B", "2026-06-30", "ECO-0812", 1.1),
        ],
        options=[option("PLATE-AL", "Flasque en EN AW-6082 avec bague acier", "MATERIAL", 0.50, 5.0, 14, 40000, "MEDIUM", "Local : flasque 3 mm plus épais.", "Moyen : dilatation à la portée de roulement, bague acier nécessaire.", "Aluminium alloy EN AW-6082-T6")],
    ),
    "ID_65": dict(
        description="Support de transmission fixé au carter.",
        criticality="B", safetyStockDays=8, usageKg=3.7, conversionEur=12.68,
        maturityDate="2026-04-07", plannedRelease="2027-02-12",
        sourcing=[
            link("SUP-09", "PRIMARY", 100, 23.6, 28, 6, 1100, "IN_PROGRESS", "2027-02-12", requal=17, contract_end="2027-06-30"),
            link("SUP-07", "CANDIDATE", 0, 25.9, 21, 3, 900, "NOT_STARTED", requal=22, ramp=4, switching=280000, clause="INDEX_Q"),
        ],
        revisions=[
            rev("A", "2025-04-22", "ECO-0170", 3.5),
            rev("B", "2026-02-03", "ECO-0611", 3.2),
        ],
        options=[
            option("SUPPORT-TOPO", "Seconde passe d'optimisation topologique", "DESIGN", 0.88, 0.2, 12, 55000, "HIGH", "Aucun.", "Faible : contrôle de la tenue vibratoire."),
            option("SUPPORT-MG", "Magnésium AM60B en HPDC", "MATERIAL", 0.72, 2.8, 32, 260000, "MEDIUM", "Local : nervures épaissies.", "Élevé : corrosion, offre concentrée en Chine, CO2 matière en forte hausse.", "Magnesium AM60B (HPDC)"),
        ],
    ),
    "ID_67": dict(
        description="Raccord coudé du circuit de refroidissement.",
        criticality="C", safetyStockDays=10, usageKg=0.13, conversionEur=2.09,
        maturityDate="2026-01-20",
        sourcing=[link("SUP-24", "PRIMARY", 100, 2.6, 18, 2, 2600, "APPROVED", "2026-01-06", contract_end="2027-12-31")],
        revisions=[rev("A", "2025-04-29", "ECO-0176", 0.12)],
    ),
    "ID_69": dict(
        description="Vis M10 x 115, classe 10.9, fixation du support de transmission.",
        criticality="C", safetyStockDays=15, usageKg=0.1, conversionEur=0.31,
        maturityDate="2025-10-14",
        sourcing=[
            link("SUP-20", "PRIMARY", 60, 0.45, 14, 2, 6000, "APPROVED", "2025-09-30", contract_end="2027-12-31"),
            link("SUP-21", "SECONDARY", 30, 0.43, 16, 2, 3000, "APPROVED", "2025-09-30", contract_end="2026-06-30"),
            link("SUP-22", "SECONDARY", 10, 0.38, 70, 40, 5000, "APPROVED", "2025-10-07", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-05-06", "ECO-0181", 0.089)],
    ),
    "ID_71": dict(
        description="Vis M8 x 50, classe 10.9, fixation du couvercle.",
        criticality="C", safetyStockDays=15, usageKg=0.032, conversionEur=0.13,
        maturityDate="2026-08-04", plannedRelease="2026-12-11",
        sourcing=[
            link("SUP-20", "PRIMARY", 60, 0.17, 14, 2, 20000, "APPROVED", "2025-09-30", contract_end="2027-12-31"),
            link("SUP-21", "SECONDARY", 40, 0.16, 16, 2, 9000, "APPROVED", "2025-09-30", contract_end="2026-06-30"),
        ],
        revisions=[rev("A", "2025-05-06", "ECO-0182", 0.028)],
    ),
    "ID_73": dict(
        description="Vis de fixation du carter moteur.",
        criticality="C", safetyStockDays=15, usageKg=0.036, conversionEur=0.14,
        maturityDate="2025-10-14",
        sourcing=[link("SUP-20", "PRIMARY", 100, 0.19, 14, 2, 5000, "APPROVED", "2025-09-30", contract_end="2027-12-31")],
        revisions=[rev("A", "2025-05-06", "ECO-0183", 0.03)],
    ),
    "ID_74": dict(
        description="Vis de fixation du flasque moteur.",
        criticality="C", safetyStockDays=15, usageKg=0.056, conversionEur=0.17,
        maturityDate="2025-10-14",
        sourcing=[
            link("SUP-20", "PRIMARY", 80, 0.25, 14, 2, 4000, "APPROVED", "2025-09-30", contract_end="2027-12-31"),
            link("SUP-22", "SECONDARY", 20, 0.21, 70, 40, 2500, "APPROVED", "2025-10-07", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-05-06", "ECO-0184", 0.05)],
    ),
    "ID_76": dict(
        criticality="C", safetyStockDays=15, usageKg=0.032, conversionEur=0.12,
        maturityDate="2026-09-29", plannedRelease="2026-12-04",
        sourcing=[link("SUP-20", "PRIMARY", 100, None, 14, 2, 4000, "APPROVED", "2025-09-30", contract_end="2027-12-31")],
        revisions=[rev("A", "2025-05-06", "ECO-0185", 0.028)],
    ),
    "ID_78": dict(
        criticality="C", safetyStockDays=15, usageKg=0.125, conversionEur=0.38,
        description="Vis M10 x 155, classe 10.9, assemblage des deux demi-carters.",
        maturityDate="2025-10-14",
        sourcing=[
            link("SUP-20", "PRIMARY", 60, 0.55, 14, 2, 21000, "APPROVED", "2025-09-30", contract_end="2027-12-31"),
            link("SUP-21", "SECONDARY", 30, 0.52, 16, 2, 9000, "APPROVED", "2025-09-30", contract_end="2026-06-30"),
            link("SUP-22", "SECONDARY", 10, 0.46, 70, 40, 7000, "APPROVED", "2025-10-07", ramp=3, contract_end="2027-06-30"),
        ],
        revisions=[rev("A", "2025-05-06", "ECO-0186", 0.113)],
        options=[option("BOLT-AL", "Vis en aluminium EN AW-6056", "MATERIAL", 0.40, 1.2, 14, 45000, "MEDIUM", "Aucun : mêmes dimensions.", "Moyen : précharge et fluage à revalider, couple de serrage à reprendre.", "Aluminium alloy EN AW-6056 (fasteners)")],
    ),
}

# Complexité de fabrication : (procédé, note du procédé sur 5, note de précision sur 5, nombre d'opérations).
_BEARING = ("Roulement de précision catalogue", 3, 4, 8)
_GEAR = ("Taillage, cémentation et rectification de denture", 4, 5, 12)
_SCREW = ("Vis catalogue : frappe à froid, roulage, revêtement lamellaire", 1, 2, 4)
COMPLEXITY = {
    "ID_3": ("Roulement hybride céramique à isolation électrique", 5, 5, 11),
    "ID_5": ("Forgeage, tournage, cannelures, trempe et rectification", 4, 5, 11),
    "ID_7": ("Extrusion à canaux hélicoïdaux, soudage FSW, contrôle d'étanchéité", 4, 3, 8),
    "ID_14": ("Découpe progressive, empilage et assemblage du paquet de tôles", 4, 4, 7),
    "ID_16": ("Épingles : formage, insertion, torsadage, soudage laser, imprégnation", 5, 4, 12),
    "ID_20": ("Fonderie de fonte GS, usinage multi-faces", 3, 4, 7),
    "ID_22": ("Décolletage, cémentation et rectification", 2, 3, 5),
    "ID_24": ("Forgeage de précision, cémentation, finition de denture conique", 3, 4, 7),
    "ID_26": ("Forgeage de précision, cannelures, cémentation et rectification", 3, 4, 8),
    "ID_30": _BEARING, "ID_32": _BEARING, "ID_34": _BEARING, "ID_36": _BEARING, "ID_38": _BEARING, "ID_40": _BEARING,
    "ID_42": _GEAR, "ID_44": _GEAR, "ID_46": _GEAR,
    "ID_48": ("Forgeage, taillage, cémentation, rectification avec micro-géométrie NVH", 4, 5, 13),
    "ID_50": ("Forgeage, tournage, taillage, cémentation et rectification", 4, 5, 11),
    "ID_53": ("Moulage FKM sur armature acier, lèvre haute vitesse", 3, 3, 4),
    "ID_55": ("Fonderie sous pression, usinage des portées, contrôle d'étanchéité", 4, 4, 9),
    "ID_57": ("Fonderie sous pression, usinage des portées, contrôle d'étanchéité", 4, 4, 9),
    "ID_59": ("Fonderie sous pression, usinage de la portée", 3, 4, 6),
    "ID_61": ("Coulée basse pression à noyaux sable, usinage, logement du stator fretté", 5, 4, 10),
    "ID_63": ("Découpe-emboutissage, usinage de la portée", 2, 4, 5),
    "ID_65": ("Fonderie sous pression, usinage des fixations", 3, 3, 6),
    "ID_67": ("Injection plastique", 2, 2, 3),
    "ID_69": _SCREW, "ID_71": _SCREW, "ID_73": _SCREW, "ID_74": _SCREW, "ID_76": _SCREW, "ID_78": _SCREW,
}

# Assemblages : historique de révision. La maturité est dans MATURITY.
ASSEMBLIES = {
    "ID_0": dict(description="E-drive avant 410 kW : moteur, réducteur à deux étages et différentiel, carters.", maturityDate="2026-10-06", revisions=[
        rev("A", "2025-05-06", "ECO-0180", 106.9),
        rev("B", "2025-12-09", "ECO-0545", 104.2),
        rev("C", "2026-04-28", "ECO-0720", 101.8),
        rev("D", "2026-10-06", "ECO-0948", 100.1),
    ]),
    "ID_1": dict(description="Moteur électrique avant : stator, arbre rapide, refroidissement.", maturityDate="2026-04-14", revisions=[
        rev("A", "2025-02-18", "ECO-0113", 42.9),
        rev("B", "2025-11-25", "ECO-0490", 42.4),
        rev("C", "2026-03-17", "ECO-0660", 39.73),
    ]),
    "ID_8": dict(description="Stator : paquet de tôles et bobinage.", maturityDate="2026-05-19", revisions=[
        rev("A", "2025-01-28", "ECO-0100", 30.6),
        rev("B", "2025-08-19", "ECO-0370", 30.5),
        rev("C", "2026-03-10", "ECO-0657", 28.98),
    ]),
    "ID_17": dict(description="Réducteur à deux étages avec différentiel (entraxes 100 et 154 mm).", maturityDate="2026-09-29", revisions=[
        rev("A", "2025-02-25", "ECO-0122", 31.2),
        rev("B", "2025-09-16", "ECO-0398", 30.6),
        rev("C", "2026-02-24", "ECO-0640", 30.05),
        rev("D", "2026-09-29", "ECO-0935", 29.85),
    ]),
    "ID_18": dict(description="Différentiel : boîtier, axe, satellites et planétaires.", maturityDate="2026-02-24", revisions=[
        rev("A", "2025-03-04", "ECO-0127", 7.05),
        rev("B", "2025-10-14", "ECO-0435", 6.85),
    ]),
    "ID_51": dict(description="Carters, joints, raccords et visserie de l'e-drive.", maturityDate="2026-09-01", revisions=[
        rev("A", "2025-04-29", "ECO-0177", 33.0),
        rev("B", "2026-02-10", "ECO-0615", 31.1),
        rev("C", "2026-09-01", "ECO-0892", 30.52),
    ]),
}

# Maturités simulées : 3DEXPERIENCE VPLM_SMB_Definition (PRIVATE, IN_WORK, FROZEN, RELEASED, OBSOLETE).
# Incohérences volontaires : STATOR et EMOTOR au-dessus de leurs enfants, EI droit RELEASED sur 3D IN_WORK,
# vis M8 obsolète encore utilisée, support RELEASED sans PPAP approuvé.
PART_MATURITY = {
    "ID_3": "FROZEN", "ID_5": "FROZEN", "ID_7": "IN_WORK", "ID_10": "PRIVATE", "ID_12": "PRIVATE", "ID_14": "FROZEN",
    "ID_16": "IN_WORK", "ID_20": "RELEASED", "ID_22": "RELEASED", "ID_24": "RELEASED", "ID_26": "RELEASED",
    "ID_30": "RELEASED", "ID_32": "RELEASED", "ID_34": "RELEASED", "ID_36": "RELEASED", "ID_38": "RELEASED",
    "ID_40": "RELEASED", "ID_42": "RELEASED", "ID_44": "FROZEN", "ID_46": "RELEASED", "ID_48": "IN_WORK",
    "ID_50": "FROZEN", "ID_53": "RELEASED", "ID_55": "FROZEN", "ID_57": "IN_WORK", "ID_59": "RELEASED",
    "ID_61": "FROZEN", "ID_63": "IN_WORK", "ID_65": "RELEASED", "ID_67": "RELEASED", "ID_69": "RELEASED",
    "ID_71": "OBSOLETE", "ID_73": "RELEASED", "ID_74": "RELEASED", "ID_76": "IN_WORK", "ID_78": "RELEASED",
}
WRAPPER_MATURITY_OVERRIDE = {"ID_56": "RELEASED"}
ASSEMBLY_MATURITY = {"ID_0": "IN_WORK", "ID_1": "FROZEN", "ID_8": "RELEASED", "ID_17": "IN_WORK", "ID_18": "RELEASED", "ID_51": "IN_WORK"}

OWNERS = {"ID_1": "ing_emoteur", "ID_17": "ing_reducteur", "ID_51": "ing_carter"}
FASTENERS = {"ID_69", "ID_71", "ID_73", "ID_74", "ID_76", "ID_78"}

INTERFACE_TYPES = [
    dict(id="mesh", label="Engrènement", test="Essai NVH et endurance au banc", weeks=10, costEur=85000),
    dict(id="bearing_seat", label="Portée de roulement", test="Contrôle d'ajustement et endurance", weeks=6, costEur=30000),
    dict(id="press_fit", label="Emmanchement", test="Essai d'emmanchement et de couple", weeks=5, costEur=25000),
    dict(id="shrink_fit", label="Frettage", test="Cycle thermique et tenue du frettage", weeks=6, costEur=35000),
    dict(id="winding", label="Bobinage en encoches", test="Essais électriques et thermiques", weeks=8, costEur=60000),
    dict(id="thermal", label="Échange thermique", test="Essai thermique moteur", weeks=5, costEur=30000),
    dict(id="bolted", label="Assemblage boulonné", test="Tenue de l'assemblage et couple de serrage", weeks=3, costEur=10000),
    dict(id="sealing", label="Étanchéité", test="Essai d'étanchéité", weeks=4, costEur=15000),
    dict(id="coolant", label="Circuit de refroidissement", test="Essai de pression et de débit", weeks=4, costEur=18000),
    dict(id="pin", label="Axe et satellite", test="Endurance du différentiel", weeks=6, costEur=30000),
    dict(id="study", label="Géométrie d'étude", test="Aucun essai", weeks=0, costEur=0),
]


# (pièce, pièce, type, description, justification)
INTERFACES = [
    ("ID_42", "ID_44", "mesh", "1er étage, entraxe 100,0 mm, même plan de denture"),
    ("ID_46", "ID_48", "mesh", "2e étage, entraxe 154,0 mm, même plan de denture"),
    ("ID_24", "ID_26", "mesh", "Engrènement conique du différentiel"),
    ("ID_5", "ID_3", "bearing_seat", "Roulement coaxial à l'arbre rapide, côté arrière du moteur"),
    ("ID_5", "ID_30", "bearing_seat", "Roulement coaxial à l'arbre rapide, côté couvercle"),
    ("ID_5", "ID_32", "bearing_seat", "Roulement coaxial à l'arbre rapide, côté moteur"),
    ("ID_50", "ID_38", "bearing_seat", "Roulement coaxial à l'arbre intermédiaire, côté couvercle"),
    ("ID_50", "ID_40", "bearing_seat", "Roulement coaxial à l'arbre intermédiaire, côté moteur"),
    ("ID_20", "ID_34", "bearing_seat", "Roulement de sortie coaxial au différentiel, côté couvercle"),
    ("ID_20", "ID_36", "bearing_seat", "Roulement de sortie coaxial au différentiel, côté moteur"),
    ("ID_5", "ID_42", "press_fit", "Pignon coaxial à l'arbre rapide"),
    ("ID_50", "ID_44", "press_fit", "Roue coaxiale à l'arbre intermédiaire"),
    ("ID_50", "ID_46", "press_fit", "Pignon coaxial à l'arbre intermédiaire"),
    ("ID_48", "ID_20", "bolted", "Couronne coaxiale au boîtier de différentiel"),
    ("ID_20", "ID_22", "pin", "Axe de satellites dans le boîtier"),
    ("ID_22", "ID_24", "pin", "Satellites de part et d'autre de l'axe"),
    ("ID_14", "ID_16", "winding", "Épingles insérées dans les encoches du paquet"),
    ("ID_14", "ID_61", "shrink_fit", "Paquet de tôles fretté dans le carter moteur"),
    ("ID_7", "ID_14", "thermal", "Chemise autour du paquet de tôles, même axe que le moteur"),
    ("ID_7", "ID_61", "sealing", "Chemise étanche dans le carter moteur"),
    ("ID_7", "ID_67", "coolant", "Raccords d'entrée et de sortie de la chemise"),
    ("ID_67", "ID_61", "coolant", "Raccords sur le dessus du carter moteur"),
    ("ID_10", "ID_14", "study", "Secteur de maillage dupliquant le paquet complet"),
    ("ID_12", "ID_16", "study", "Bobine unitaire dupliquant le bobinage complet"),
    ("ID_30", "ID_55", "bearing_seat", "Plan de roulements côté couvercle (Y = -175 mm environ)"),
    ("ID_38", "ID_55", "bearing_seat", "Plan de roulements côté couvercle (Y = -175 mm environ)"),
    ("ID_34", "ID_59", "bearing_seat", "Roulement de sortie dans son logement"),
    ("ID_59", "ID_55", "bolted", "Logement rapporté sur le demi-carter gauche"),
    ("ID_32", "ID_57", "bearing_seat", "Plan de roulements côté moteur (Y = 0 mm environ)"),
    ("ID_40", "ID_57", "bearing_seat", "Plan de roulements côté moteur (Y = 0 mm environ)"),
    ("ID_36", "ID_57", "bearing_seat", "Plan de roulements côté moteur (Y = 0 mm environ)"),
    ("ID_3", "ID_63", "bearing_seat", "Roulement arrière dans le flasque (Y = 315 mm environ)"),
    ("ID_63", "ID_61", "bolted", "Flasque vissé à l'arrière du carter moteur"),
    ("ID_55", "ID_57", "bolted", "Demi-carters assemblés par 14 vis M10 x 155"),
    ("ID_78", "ID_55", "bolted", "Couronne de 14 vis autour du carter (Y = -170 mm)"),
    ("ID_78", "ID_57", "bolted", "Couronne de 14 vis autour du carter (Y = -170 mm)"),
    ("ID_69", "ID_65", "bolted", "4 vis M10 x 115 sur le support de transmission"),
    ("ID_65", "ID_57", "bolted", "Support fixé au demi-carter droit"),
    ("ID_71", "ID_55", "bolted", "Couronne de 13 vis M8 du couvercle (Y = -229 mm)"),
    ("ID_73", "ID_61", "bolted", "3 vis de fixation du carter moteur"),
    ("ID_74", "ID_63", "bolted", "2 vis du flasque (Y = 325 mm)"),
    ("ID_76", "ID_63", "bolted", "Vis du flasque (Y = 325 mm)"),
    ("ID_61", "ID_57", "bolted", "Carter moteur assemblé au demi-carter droit"),
    ("ID_53", "ID_5", "sealing", "Lèvre du joint sur l'arbre rapide"),
    ("ID_53", "ID_57", "sealing", "Joint logé dans le demi-carter droit"),
]




def ext(parent, tag, **attrs):
    return ET.SubElement(parent, EXT + tag, {k: str(v) for k, v in attrs.items()})


def set_text(element, tag, value):
    child = element.find(XPDM + tag)
    if child is not None:
        child.text = value


def iso(date):
    return f"{date}T09:00:00.0Z"


def wrapper_targets(structure):
    """Associe chaque enveloppe EI à sa pièce 3D et chaque produit à son sous-ensemble de premier niveau."""
    children = {}
    for instance in structure.findall(XPDM + "ProductInst"):
        children.setdefault(instance.findtext(XPDM + "Owned"), []).append(instance.findtext(XPDM + "Instancing"))
    wrappers = {}
    for parent, kids in children.items():
        if parent not in ASSEMBLIES and kids[0] in PARTS:
            wrappers[parent] = kids[0]
    top_level = {}

    def walk(product, top):
        top_level[product] = top
        for kid in children.get(product, []):
            walk(kid, top if top else OWNERS.get(kid) and kid)

    walk("ID_0", None)
    return wrappers, top_level


def owner_of(product_id, top_level):
    target = product_id
    if target in FASTENERS:
        return "ing_standards"
    top = top_level.get(target)
    return OWNERS.get(top, "chef_programme")


def update_products(structure):
    wrappers, top_level = wrapper_targets(structure)
    for element in structure.findall(XPDM + "Product"):
        product_id = element.get("id")
        part_id = wrappers.get(product_id, product_id)
        spec = ASSEMBLIES.get(part_id) or PARTS[part_id]
        if product_id in ASSEMBLIES:
            maturity = ASSEMBLY_MATURITY[product_id]
        else:
            maturity = WRAPPER_MATURITY_OVERRIDE.get(product_id, PART_MATURITY[part_id])
        set_text(element, "Maturity", maturity)
        set_text(element, "TimeCreated", iso(spec["revisions"][0]["date"]))
        set_text(element, "TimeModified", iso(spec.get("modified", spec["revisions"][-1]["date"])))
        set_text(element, "Owner", owner_of(part_id, top_level))
        description = element.find(XPDM + "Description")
        is_wrapper = product_id in wrappers
        if not is_wrapper and not (description.text or "").strip() and spec.get("description"):
            description.text = spec["description"]

    for element in structure.findall(XPDM + "Rep3DAggr"):
        part_id = element.findtext(XPDM + "Owned")
        spec = PARTS[part_id]
        set_text(element, "Maturity", PART_MATURITY[part_id])
        set_text(element, "TimeCreated", iso(spec["revisions"][0]["date"]))
        set_text(element, "TimeModified", iso(spec["revisions"][-1]["date"]))
        set_text(element, "Owner", owner_of(part_id, top_level))
    return wrappers


def build_enrichment(root, structure, wrappers):
    enrichment = ET.SubElement(root, EXT + "Enrichment", {
        "status": "SIMULATED",
        "generatedFrom": SOURCE_XML.name,
        "referenceDate": PROGRAM["referenceDate"],
        "note": "Données simulées pour les scénarios du hackathon : fournisseurs et événements fictifs, prix hypothétiques.",
    })
    program = ext(enrichment, "Program")
    for name, value in PROGRAM.items():
        ext(program, "Param", name=name, value=value)

    materials = ext(enrichment, "Materials")
    for material in MATERIALS:
        ext(materials, "Material", **material)

    suppliers = ext(enrichment, "Suppliers")
    for supplier in SUPPLIERS:
        ext(suppliers, "Supplier", **supplier)

    parts = ext(enrichment, "PartData")
    for product_id, spec in {**ASSEMBLIES, **PARTS}.items():
        attrs = {k: v for k, v in spec.items() if k not in ("revisions", "sourcing", "options", "description", "modified", "blocking", "sourcingNote")}
        if product_id in COMPLEXITY:
            process, process_rating, precision_rating, operations = COMPLEXITY[product_id]
            attrs.update(process=process, processRating=process_rating, precisionRating=precision_rating, operations=operations)
        part = ext(parts, "Part", ref=product_id, **attrs)
        for row in spec.get("sourcing", []):
            ext(part, "Sourcing", **row)
        for row in spec["revisions"]:
            ext(part, "Revision", **row)
        for row in spec.get("options", []):
            ext(part, "MassOption", **row)
    for wrapper_id, part_id in wrappers.items():
        date = PARTS[part_id]["maturityDate"]
        ext(parts, "Part", ref=wrapper_id, maturityDate=date)

    interface_types = ext(enrichment, "InterfaceTypes")
    for row in INTERFACE_TYPES:
        ext(interface_types, "InterfaceType", **row)

    interfaces = ext(enrichment, "Interfaces")
    for first, second, kind, note in INTERFACES:
        ext(interfaces, "Interface", first=first, second=second, type=kind, note=note)

    ET.indent(enrichment, space="  ", level=1)
    enrichment.tail = "\n"


def build_tree():
    """Construit un nouvel export sans écrire dans le fichier d'origine."""
    ET.register_namespace("", XPDM_URI)
    ET.register_namespace("xsi", XSI_URI)
    ET.register_namespace("ext", EXT_URI)
    tree = ET.parse(SOURCE_XML)
    root = tree.getroot()
    structure = root.find(XPDM + "ProductStructure")

    header = root.find(XPDM + "InfoHeader")
    header[-1].tail = "\n    "
    for name, value in (("EnrichmentStatus", "SIMULATED"), ("EnrichedFrom", SOURCE_XML.name)):
        info = ET.SubElement(header, XPDM + "Info", {"name": name, "value": value})
        info.tail = "\n    "
    header[-1].tail = "\n  "

    wrappers = update_products(structure)
    build_enrichment(root, structure, wrappers)
    return tree


def main():
    tree = build_tree()

    OUTPUT_XML.parent.mkdir(exist_ok=True)
    tree.write(OUTPUT_XML, encoding="UTF-8", xml_declaration=True, short_empty_elements=False)
    print(f"Écrit : {OUTPUT_XML}")


if __name__ == "__main__":
    main()
