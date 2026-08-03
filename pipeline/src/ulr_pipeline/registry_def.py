"""Definițiile variabilelor publicate — sursa de adevăr pentru UI.

`role`: filter = apare în constructorul de filtre; profile = apare în fișa celulei.
Măsurile (ce numărăm) sunt listate separat în MEASURES.
Statisticile (min/max/percentile) și categoriile se completează la export, din date.
"""

from .config import CLIMATE_YEAR

Y = CLIMATE_YEAR  # anul datelor climatice — apare doar în etichete, nu în ID-uri

GROUPS = {
    "demografie": "Demografie (RPL 2021)",
    "administrativ": "Administrativ",
    "relief": "Relief",
    "distante": "Distanțe și apartenențe",
    "servicii": "Acces la servicii",
    "clima": f"Climă (an curent, {Y})",
    "clima_multi": "Climă multianuală (1961–2025)",
}

MEASURES = [
    {"id": "pop_total", "label": "persoane (total)"},
    {"id": "pop_f", "label": "femei"},
    {"id": "pop_m", "label": "bărbați"},
    {"id": "pop_0_14", "label": "copii (0–14 ani)"},
    {"id": "pop_15_64", "label": "persoane 15–64 ani"},
    {"id": "pop_65p", "label": "vârstnici (65+)"},
    {"id": "pop_ocupata", "label": "persoane ocupate"},
]

V = [
    # --- demografie (core) ---
    dict(id="pop_total", table="core", group="demografie", label="Populația totală (2021)",
         unit="persoane", dtype="int", role=["filter", "profile"]),
    dict(id="pop_f", table="core", group="demografie", label="Populația feminină", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_m", table="core", group="demografie", label="Populația masculină", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_0_14", table="core", group="demografie", label="Persoane sub 15 ani", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_15_64", table="core", group="demografie", label="Persoane 15–64 ani", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_65p", table="core", group="demografie", label="Persoane 65+ ani", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_ocupata", table="core", group="demografie", label="Populația ocupată", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_cet_ro", table="core", group="demografie", label="Cetățeni români", unit="persoane",
         dtype="int", role=["profile"]),
    dict(id="pop_mutati_in_tara", table="core", group="demografie",
         label="Și-au schimbat reședința în țară", unit="persoane", dtype="int", role=["profile"]),
    dict(id="pop_mutati_strainatate", table="core", group="demografie",
         label="Și-au schimbat reședința în străinătate", unit="persoane", dtype="int", role=["profile"]),
    dict(id="pop_2011", table="core", group="demografie", label="Populația 2011 (Eurostat)",
         unit="persoane", dtype="float", decimals=0, role=["profile"],
         note="Grila Eurostat/GEOSTAT 2011 — metodologie diferită de RPL 2021."),
    dict(id="pop_2006", table="core", group="demografie", label="Populația 2006 (Eurostat)",
         unit="persoane", dtype="float", decimals=0, role=["profile"],
         note="Grila GEOSTAT 2006 — estimare, metodologie diferită."),

    # --- administrativ (env) ---
    dict(id="mediu", table="env", group="administrativ", label="Mediul (urban/rural)",
         dtype="cat", role=["filter", "profile"],
         note="După statutul administrativ al UAT (comună = rural). Definiția pe grad de "
              "urbanizare (DEGURBA) va fi adăugată ulterior."),
    dict(id="intravilan", table="env", group="administrativ", label="Intravilan (oraș/sat)",
         dtype="cat", role=["filter", "profile"],
         note="Apartenența celulei la intravilanul (perimetrul construit) al unei localități, "
              "după tipul dominant de construit pe celulă: „oraș” (localitate urbană) sau „sat”. "
              "Celulele fără construit (extravilan) nu apar în niciuna. Sursă: ANCPI/CNGCFT 2020."),
    dict(id="uat_status", table="env", group="administrativ", label="Statutul UAT",
         dtype="cat", role=["filter", "profile"]),
    dict(id="uat_name", table="env", group="administrativ", label="UAT",
         dtype="cat", role=["profile"]),
    dict(id="county_mn", table="env", group="administrativ", label="Județul",
         dtype="cat", role=["filter", "profile"]),
    dict(id="region_name", table="env", group="administrativ", label="Regiunea",
         dtype="cat", role=["filter", "profile"]),

    # --- relief (env) ---
    dict(id="alt_mean", table="env", group="relief", label="Altitudinea medie", unit="m",
         dtype="float", decimals=0, role=["filter", "profile"], filterRange=[0, 2544],
         note="FABDEM agregat la 1 km."),
    dict(id="alt_min", table="env", group="relief", label="Altitudinea minimă", unit="m",
         dtype="float", decimals=0, role=["profile"]),
    dict(id="alt_max", table="env", group="relief", label="Altitudinea maximă", unit="m",
         dtype="float", decimals=0, role=["profile"]),
    dict(id="alt_std", table="env", group="relief", label="Rugozitatea (σ altitudine)", unit="m",
         dtype="float", decimals=1, role=["profile"]),
    dict(id="slope_mean", table="env", group="relief", label="Panta medie", unit="°",
         dtype="float", decimals=1, role=["filter", "profile"],
         note="Calculată din DEM 100 m — valorile sunt netezite față de teren."),
    dict(id="landform_type", table="env", group="relief", label="Tipul formei de relief",
         dtype="cat", role=["filter", "profile"]),
    dict(id="landform_lvl0", table="env", group="relief", label="Marea unitate de relief",
         dtype="cat", role=["filter", "profile"]),
    dict(id="landform_lvl1", table="env", group="relief", label="Subunitatea de relief",
         dtype="cat", role=["profile"]),
    dict(id="landform_name", table="env", group="relief", label="Forma de relief locală",
         dtype="cat", role=["profile"]),

    # --- distanțe (env) ---
    dict(id="dist_coast_km", table="env", group="distante", label="Distanța până la mare", unit="km",
         dtype="float", decimals=0, role=["filter", "profile"], filterRange=[0, 685],
         note="Distanță euclidiană până la linia țărmului, precizie ±1 km."),
    dict(id="dist_water_km", table="env", group="distante",
         label="Distanța până la un corp de apă", unit="km",
         dtype="float", decimals=1, role=["filter", "profile"], filterRange=[0, 28],
         note="Distanță în linie dreaptă până la cel mai apropiat corp de apă — lac, lac de "
              "acumulare, iaz, baltă, bazin sau lagună. 0 km = pe apă. Sursă: OpenStreetMap."),
    dict(id="categorie_apa", table="env", group="distante",
         label="Tipul celui mai apropiat corp de apă", dtype="cat", role=["filter", "profile"],
         catPinLast=["Alt tip"],
         note="Categoria celui mai apropiat corp de apă (lac, lac de acumulare, iaz, bazin, "
              "lagună sau alt tip). Sursă: OpenStreetMap."),
    dict(id="dist_curs_km", table="env", group="distante",
         label="Distanța până la un curs de apă", unit="km",
         dtype="float", decimals=1, role=["filter", "profile"], filterRange=[0, 30],
         note="Distanță în linie dreaptă până la cel mai apropiat curs de apă — râu sau pârâu. "
              "0 km = pe cursul de apă. Sursă: OpenStreetMap."),
    dict(id="categorie_curs", table="env", group="distante",
         label="Tipul celui mai apropiat curs de apă", dtype="cat", role=["filter", "profile"],
         note="Categoria celui mai apropiat curs de apă (râu sau pârâu). Sursă: OpenStreetMap."),
    dict(id="dist_inundatii_km", table="env", group="distante",
         label="Distanța până la o zonă cu risc de inundații", unit="km",
         dtype="float", decimals=1, role=["filter", "profile"], filterRange=[0, 20],
         note="Distanță în linie dreaptă până la cea mai apropiată zonă cu hazard de inundații "
              "(orice scenariu). 0 km = locul se află într-o zonă inundabilă."),
    dict(id="scenariu_inundatii", table="env", group="distante",
         label="Scenariul de inundații cel mai apropiat", dtype="cat", role=["filter", "profile"],
         note="Cel mai frecvent scenariu de hazard care atinge locul: 10% probabilitate anuală "
              "(revenire ~10 ani), 1% (~100 ani) sau 0,1% (~1.000 ani). Fără bifă = toate "
              "scenariile combinate."),
    dict(id="dist_border_km", table="env", group="distante", label="Distanța până la frontieră",
         unit="km", dtype="float", decimals=0, role=["filter", "profile"], filterRange=[0, 218],
         note="Distanță euclidiană până la frontiera terestră/fluvială, precizie ±1 km."),
    dict(id="border_neighbor", table="env", group="distante", label="Cea mai apropiată frontieră",
         dtype="cat", role=["filter", "profile"]),
    dict(id="dist_crossing_km", table="env", group="distante",
         label="Distanța până la un punct de trecere a frontierei", unit="km",
         dtype="float", decimals=0, role=["filter", "profile"], filterRange=[0, 235],
         note="Distanță în linie dreaptă până la cel mai apropiat punct de trecere auto a "
              "frontierei (unde se poate ieși efectiv din țară). Ruta reală pe șosea se "
              "calculează la cerere, din fișa celulei. Sursă: Poliția de Frontieră."),
    dict(id="nearest_crossing", table="env", group="distante",
         label="Cel mai apropiat punct de trecere", dtype="cat", role=["profile"]),
    dict(id="dist_protected_km", table="env", group="distante",
         label="Distanța până la o arie protejată", unit="km",
         dtype="float", decimals=1, role=["filter", "profile"],
         note="Distanță de la cel mai apropiat punct al celulei până la cea mai apropiată arie "
              "protejată — parc național, parc natural, rezervație naturală/științifică, monument "
              "al naturii sau sit Natura 2000. 0 km = celula se intersectează cu o arie protejată. "
              "Sursă: ANANP."),

    # --- acces la servicii (env) ---
    dict(id="acces_gaz", table="env", group="servicii", label="Acces la gaze naturale",
         dtype="cat", role=["filter", "profile"],
         note="Localitatea (dominantă pe celulă) este branșată sau se poate branșa la "
              "rețeaua de gaze naturale. Sursă: ANCPI/CNGCFT."),
    dict(id="dist_hospital_km", table="env", group="servicii",
         label="Distanța până la cel mai apropiat spital", unit="km",
         dtype="float", decimals=1, role=["filter", "profile"], filterRange=[0, 73],
         note="Distanță în linie dreaptă până la cel mai apropiat spital activ din registrul "
              "ANMCS (~718 unități). Distanța și timpul pe șosea se calculează la cerere, "
              "din fișa celulei, prin serviciul de rutare."),
    dict(id="nearest_hospital", table="env", group="servicii",
         label="Cel mai apropiat spital", dtype="cat", role=["profile"]),
    dict(id="dist_airport_km", table="env", group="servicii",
         label="Distanța până la cel mai apropiat aeroport", unit="km",
         dtype="float", decimals=0, role=["filter", "profile"], filterRange=[0, 126],
         note="Distanță în linie dreaptă până la cel mai apropiat aeroport (18 aeroporturi, "
              "OurAirports). Ruta reală pe șosea se calculează la cerere, din fișa celulei."),
    dict(id="nearest_airport", table="env", group="servicii",
         label="Cel mai apropiat aeroport", dtype="cat", role=["profile"]),

    # --- climă (climate); ID-urile nu poartă anul, doar etichetele (an curent, actualizat zilnic) ---
    dict(id="tmean", table="climate", group="clima", label=f"Temperatura medie ({Y})",
         unit="°C", dtype="float", decimals=1, role=["filter", "profile"],
         note=f"Media (tmin+tmax)/2 pe zilele disponibile din {Y} (nu normală climatologică). "
              "Se actualizează zilnic din opendata MeteoRomania."),
    dict(id="tmin_mean", table="climate", group="clima", label="Media minimelor zilnice",
         unit="°C", dtype="float", decimals=1, role=["profile"]),
    dict(id="tmax_mean", table="climate", group="clima", label="Media maximelor zilnice",
         unit="°C", dtype="float", decimals=1, role=["profile"]),
    dict(id="precip_total", table="climate", group="clima",
         label=f"Precipitații cumulate ({Y})", unit="mm", dtype="float", decimals=0,
         role=["filter", "profile"], note=f"Cumulat de la 1 ianuarie {Y} până la ultima zi disponibilă."),
    dict(id="precip_max_daily", table="climate", group="clima",
         label="Precipitația zilnică maximă", unit="mm", dtype="float", decimals=1,
         role=["filter", "profile"]),
    dict(id="hot_days", table="climate", group="clima", label="Zile caniculare (max ≥ 30 °C)",
         unit="zile", dtype="int", role=["filter", "profile"]),
    dict(id="tropical_nights", table="climate", group="clima",
         label="Nopți tropicale (min ≥ 20 °C)", unit="zile", dtype="int", role=["filter", "profile"]),
    dict(id="frost_days", table="climate", group="clima", label="Zile cu îngheț (min < 0 °C)",
         unit="zile", dtype="int", role=["filter", "profile"]),
    dict(id="summer_days", table="climate", group="clima", label="Zile de vară (max ≥ 25 °C)",
         unit="zile", dtype="int", role=["profile"]),
    dict(id="wet_days", table="climate", group="clima", label="Zile cu precipitații ≥ 1 mm",
         unit="zile", dtype="int", role=["profile"]),

    # --- climă multianuală 1961–2025 (climate, din cubul Zarr) ---
    dict(id="tmean_norm_9120", table="climate", group="clima_multi",
         label="Temperatura medie anuală (normala 1991–2020)", unit="°C",
         dtype="float", decimals=1, role=["filter", "profile"],
         note="Media multianuală 1991–2020 a temperaturii medii zilnice (tmin+tmax)/2. "
              "Sursă: grilele zilnice MeteoRomania 1961–prezent, omogenizate în cubul Zarr."),
    dict(id="tmean_norm_6190", table="climate", group="clima_multi",
         label="Temperatura medie anuală (normala 1961–1990)", unit="°C",
         dtype="float", decimals=1, role=["profile"]),
    dict(id="warming_deg", table="climate", group="clima_multi",
         label="Încălzirea: 1991–2020 față de 1961–1990", unit="°C",
         dtype="float", decimals=2, role=["filter", "profile"],
         note="Diferența dintre normalele climatologice 1991–2020 și 1961–1990 — cât s-a "
              "încălzit efectiv clima locului în ultimele decenii."),
    dict(id="tmean_trend_dec", table="climate", group="clima_multi",
         label="Tendința temperaturii (1961–2025)", unit="°C/deceniu",
         dtype="float", decimals=2, role=["filter", "profile"],
         note="Panta regresiei liniare a temperaturii medii anuale, 1961–2025."),
    dict(id="tmean_anom_2025", table="climate", group="clima_multi",
         label="Anomalia anului 2025 (față de 1991–2020)", unit="°C",
         dtype="float", decimals=1, role=["filter", "profile"]),
    dict(id="prec_norm_9120", table="climate", group="clima_multi",
         label="Precipitații anuale (normala 1991–2020)", unit="mm",
         dtype="float", decimals=0, role=["filter", "profile"]),
    dict(id="prec_norm_6190", table="climate", group="clima_multi",
         label="Precipitații anuale (normala 1961–1990)", unit="mm",
         dtype="float", decimals=0, role=["profile"]),
    dict(id="prec_change_pct", table="climate", group="clima_multi",
         label="Schimbarea precipitațiilor: 1991–2020 vs 1961–1990", unit="%",
         dtype="float", decimals=1, role=["filter", "profile"]),
]
