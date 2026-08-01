"""Validarea produselor + cifre „golden” pentru preseturi (comparate apoi în aplicație)."""

from __future__ import annotations

import duckdb
import pandas as pd

from .config import DATA_OUT, STAGING

CAMPIE = "('câmpie','vale','grind','baltă/lac')"
DEAL = "('deal','podiș','depresiune')"


def step_validate() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW core AS SELECT * FROM read_parquet('{DATA_OUT / 'core.parquet'}')")
    con.execute(f"CREATE VIEW env AS SELECT * FROM read_parquet('{DATA_OUT / 'env.parquet'}')")
    con.execute(f"CREATE VIEW climate AS SELECT * FROM read_parquet('{DATA_OUT / 'climate.parquet'}')")
    con.execute(f"CREATE VIEW cells AS SELECT * FROM read_parquet('{STAGING / 'cells.parquet'}')")
    q = lambda sql: con.execute(sql).fetchone()[0]

    lines = ["# Raport de validare\n"]

    total = q("SELECT sum(pop_total) FROM core")
    lines += [
        "## Consistență internă\n",
        f"- Populația totală 2021 (suma pe grilă): **{total:,}**",
        f"- Celule: {q('SELECT count(*) FROM core'):,}",
        f"- Celule cu pop_total ≠ TOT_P_2021 (Eurostat): "
        f"{q('SELECT count(*) FROM cells WHERE pop_total != pop_2021_eurostat'):,}",
        f"- Celule cu F+M ≠ total: "
        f"{q('SELECT count(*) FROM core WHERE pop_f + pop_m != pop_total'):,}",
        f"- Celule cu suma grupelor de vârstă ≠ total: "
        f"{q('SELECT count(*) FROM core WHERE pop_0_14 + pop_15_64 + pop_65p != pop_total'):,}",
        "",
        "## Acoperirea join-urilor\n",
        f"- UAT (siruta): {q('SELECT avg(CASE WHEN siruta IS NULL THEN 0 ELSE 1 END) FROM env'):.2%}",
        f"- Relief: {q('SELECT avg(CASE WHEN landform_name IS NULL THEN 0 ELSE 1 END) FROM env'):.2%}",
        f"- Altitudine: {q('SELECT avg(CASE WHEN alt_mean IS NULL THEN 0 ELSE 1 END) FROM env'):.2%}",
        f"- Climă (tmean): {q('SELECT avg(CASE WHEN tmean IS NULL THEN 0 ELSE 1 END) FROM climate'):.2%}",
        "",
        "## Intervale\n",
        f"- Altitudine medie: [{q('SELECT min(alt_mean) FROM env'):.0f}, "
        f"{q('SELECT max(alt_mean) FROM env'):.0f}] m",
        f"- Panta medie: [{q('SELECT min(slope_mean) FROM env'):.1f}, "
        f"{q('SELECT max(slope_mean) FROM env'):.1f}] °",
        f"- Temperatura medie: [{q('SELECT min(tmean) FROM climate'):.1f}, "
        f"{q('SELECT max(tmean) FROM climate'):.1f}] °C",
        f"- Precipitații cumulate: [{q('SELECT min(precip_total) FROM climate'):.0f}, "
        f"{q('SELECT max(precip_total) FROM climate'):.0f}] mm",
        f"- Zile cu date temperatură: [{q('SELECT min(n_days_temp) FROM climate')}, "
        f"{q('SELECT max(n_days_temp) FROM climate')}]",
        f"- Încălzirea medie resimțită (91–20 vs 61–90, pond. populație): "
        f"{q('SELECT sum(warming_deg*pop_total)/sum(pop_total) FROM core JOIN climate USING(cell_id)'):.2f} °C",
        "",
        "## Cifre golden pentru preseturi (de reprodus identic în aplicație)\n",
    ]

    ce = "FROM core JOIN env USING (cell_id)"
    cc = "FROM core JOIN env USING (cell_id) JOIN climate USING (cell_id)"
    golden = [
        ("La mare (< 5 km de țărm)", f"SELECT sum(pop_total) {ce} WHERE dist_coast_km < 5"),
        ("În zona de frontieră (< 30 km)", f"SELECT sum(pop_total) {ce} WHERE dist_border_km < 30"),
        ("La munte (tip relief)", f"SELECT sum(pop_total) {ce} WHERE landform_type = 'munte'"),
        ("La deal (deal/podiș/depresiune)", f"SELECT sum(pop_total) {ce} WHERE landform_type IN {DEAL}"),
        ("La câmpie (câmpie/vale/grind/baltă)", f"SELECT sum(pop_total) {ce} WHERE landform_type IN {CAMPIE}"),
        ("Peste 1000 m altitudine", f"SELECT sum(pop_total) {ce} WHERE alt_mean > 1000"),
        ("Urban (după UAT)", f"SELECT sum(pop_total) {ce} WHERE mediu = 'urban'"),
        ("Rural (după UAT)", f"SELECT sum(pop_total) {ce} WHERE mediu = 'rural'"),
        ("La oraș (intravilan urban)", f"SELECT sum(pop_total) {ce} WHERE intravilan = 'oraș'"),
        ("La sat (intravilan rural)", f"SELECT sum(pop_total) {ce} WHERE intravilan = 'sat'"),
        ("Extravilan (fără intravilan)", f"SELECT sum(pop_total) {ce} WHERE intravilan IS NULL"),
        ("Branșați/branșabili la gaze naturale", f"SELECT sum(pop_total) {ce} WHERE acces_gaz = 'conectat'"),
        ("Neconectați la gaze naturale", f"SELECT sum(pop_total) {ce} WHERE acces_gaz = 'neconectat'"),
        ("Se intersectează cu o arie protejată (prag 0 km, fără buffer)",
         f"SELECT sum(pop_total) {ce} WHERE dist_protected_km <= 0"),
        ("La cel mult 1 km de o arie protejată (prag implicit)",
         f"SELECT sum(pop_total) {ce} WHERE dist_protected_km <= 1"),
        ("La mai puțin de 1 km de un corp de apă",
         f"SELECT sum(pop_total) {ce} WHERE dist_water_km < 1"),
        ("La mai puțin de 500 m de un curs de apă",
         f"SELECT sum(pop_total) {ce} WHERE dist_curs_km < 0.5"),
        ("La peste 10 km de un spital", f"SELECT sum(pop_total) {ce} WHERE dist_hospital_km >= 10"),
        ("La peste 20 km de un spital", f"SELECT sum(pop_total) {ce} WHERE dist_hospital_km >= 20"),
        ("La peste 25 km de un spital", f"SELECT sum(pop_total) {ce} WHERE dist_hospital_km >= 25"),
        ("La peste 50 km de un aeroport", f"SELECT sum(pop_total) {ce} WHERE dist_airport_km >= 50"),
        ("La peste 100 km de un aeroport", f"SELECT sum(pop_total) {ce} WHERE dist_airport_km >= 100"),
        ("Distanța medie (ponderată) la aeroport",
         f"SELECT round(sum(dist_airport_km*pop_total)/sum(pop_total),1) {ce}"),
        ("Încălzire ≥ 1,1 °C (91–20 vs 61–90)",
         f"SELECT sum(pop_total) {cc} WHERE warming_deg >= 1.1"),
        ("Femei, 200–500 m, precip < 400 mm, tmean 11,5–12,5 °C",
         f"SELECT sum(pop_f) {cc} WHERE alt_mean BETWEEN 200 AND 500 "
         "AND precip_total < 400 AND tmean BETWEEN 11.5 AND 12.5"),
    ]
    for label, sql in golden:
        val = q(sql)
        val = 0 if val is None else int(val)
        pct = val / total
        lines.append(f"- {label}: **{val:,}** ({pct:.1%})")

    report = "\n".join(lines) + "\n"
    (DATA_OUT / "validation_report.md").write_text(report, encoding="utf-8")
    print(report)
