import unittest
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import xarray as xr

from ulr_pipeline.forecast_live import (
    aggregate_air_daily,
    aggregate_weather_daily,
    air_candidate_dates,
    aqi_rank,
    complete_local_days,
    interpolated_grid_map,
    local_date_labels,
    nearest_grid_map,
    rolling_mean,
    _require_coverage,
    _spatial_cube,
)


class ForecastHelpersTest(unittest.TestCase):
    def test_local_dates_use_bucharest_timezone(self):
        times = np.array(["2026-01-01T21:00", "2026-01-01T22:00"], dtype="datetime64[m]")
        self.assertEqual(local_date_labels(times).tolist(), ["2026-01-01", "2026-01-02"])

    def test_weather_daily_extrema_and_kelvin_conversion(self):
        times = np.array(
            ["2026-01-01T18:00", "2026-01-01T21:00", "2026-01-02T00:00"],
            dtype="datetime64[h]",
        )
        minimum = np.array([[273.15], [271.15], [269.15]])
        maximum = np.array([[278.15], [279.15], [280.15]])
        days, tmin, tmax = aggregate_weather_daily(minimum, maximum, times)
        self.assertEqual(days.tolist(), ["2026-01-01", "2026-01-02"])
        np.testing.assert_allclose(tmin[:, 0], [-2.0, -4.0])
        np.testing.assert_allclose(tmax[:, 0], [6.0, 7.0])

    def test_aqi_boundaries_and_daily_worst_pollutant(self):
        self.assertEqual(aqi_rank([10, 10.01, 75, 75.01, np.nan], "pm25").tolist(), [0, 1, 4, 5, -1])
        times = np.array(["2026-07-01T00:00", "2026-07-01T01:00"], dtype="datetime64[h]")
        days, maxima, worst = aggregate_air_daily(
            {
                "pm25": (np.array([[9.0], [26.0]]), times),
                "no2": (np.array([[20.0], [50.0]]), times),
            }
        )
        self.assertEqual(days.tolist(), ["2026-07-01"])
        self.assertEqual(maxima["pm25"][0, 0], 26.0)
        self.assertEqual(worst[0, 0], 1)

        pm_24h = rolling_mean(np.full((24, 1), 26.0), 24)
        self.assertTrue(np.isnan(pm_24h[:23]).all())
        self.assertEqual(aqi_rank(pm_24h, "pm25")[-1, 0], 3)

    def test_only_full_local_days_are_retained(self):
        times = pd.date_range("2026-07-19T00:00Z", periods=72, freq="h").to_numpy()
        self.assertEqual(complete_local_days(times, 1).tolist(), ["2026-07-20", "2026-07-21"])

    def test_nearest_mapping_uses_native_grid_ids(self):
        mapping = nearest_grid_map(
            [2, 1], [29.9, 20.1], [45.0, 45.0], [7, 8], [20.0, 30.0], [45.0, 45.0]
        )
        self.assertEqual(mapping.to_dict("list"), {"cell_id": [1, 2], "grid_id": [7, 8]})

    def test_interpolated_mapping_blends_the_four_neighbours(self):
        # grila nativa 2x2 (noduri la lon 20/21, lat 45/46), grid_id in ordine
        # rand-major: (45,20)=0 (45,21)=1 (46,20)=2 (46,21)=3. Celula e mai
        # aproape de randul lat=45 ca sa nu existe ambiguitate de "cel mai
        # apropiat" din curbura sferei (distanta unghiulara pe longitudine se
        # comprima usor cu latitudinea, deci un punct exact la mijloc pe lat nu
        # e un test stabil).
        mapping = interpolated_grid_map(
            [1], [20.25], [45.3],
            [0, 1, 2, 3], [20.0, 21.0, 20.0, 21.0], [45.0, 45.0, 46.0, 46.0],
        )
        row = mapping.iloc[0]
        self.assertEqual(row["grid_id"], 0)  # cel mai apropiat nod
        weights = {
            row["grid_id_a"]: row["weight_a"], row["grid_id_b"]: row["weight_b"],
            row["grid_id_c"]: row["weight_c"], row["grid_id_d"]: row["weight_d"],
        }
        self.assertAlmostEqual(weights[0], 0.7 * 0.75, places=5)
        self.assertAlmostEqual(weights[1], 0.7 * 0.25, places=5)
        self.assertAlmostEqual(weights[2], 0.3 * 0.75, places=5)
        self.assertAlmostEqual(weights[3], 0.3 * 0.25, places=5)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=5)

    def test_interpolated_mapping_falls_back_to_nearest_when_grid_has_holes(self):
        # o gaura in grila nativa (lipseste nodul (46,21)) -> nu mai e dreptunghi
        # complet, deci se revine la comportamentul vechi: doar cel mai apropiat.
        mapping = interpolated_grid_map(
            [1], [20.1], [45.1],
            [0, 1, 2], [20.0, 21.0, 20.0], [45.0, 45.0, 46.0],
        )
        row = mapping.iloc[0]
        self.assertEqual(row["grid_id"], 0)
        self.assertEqual(row["grid_id_a"], 0)
        self.assertAlmostEqual(row["weight_a"], 1.0, places=5)
        self.assertAlmostEqual(row["weight_b"] + row["weight_c"] + row["weight_d"], 0.0, places=5)

    def test_air_candidates_never_start_in_the_future(self):
        self.assertEqual(
            air_candidate_dates(date(2026, 7, 20), date(2026, 7, 22)),
            [date(2026, 7, 20), date(2026, 7, 19), date(2026, 7, 18)],
        )

    def test_coverage_ignores_datetime_storage_resolution(self):
        actual = np.array(["2026-07-19T15:00", "2026-07-19T18:00"], dtype="datetime64[s]")
        expected = pd.date_range("2026-07-19T15:00Z", periods=2, freq="3h")
        _require_coverage(actual, expected, "test")

    def test_cams_hour_axis_uses_run_as_fallback(self):
        ds = xr.Dataset(
            {"no2_conc": (("time", "level", "latitude", "longitude"), np.ones((2, 1, 2, 2)))},
            coords={
                "time": ("time", [0.0, 1.0], {"units": "hours"}),
                "level": [0.0],
                "latitude": [44.0, 43.0],
                "longitude": [20.0, 21.0],
            },
        )
        cube = _spatial_cube(
            ds["no2_conc"], ds, datetime(2026, 7, 18, tzinfo=timezone.utc)
        )
        np.testing.assert_array_equal(
            cube.times,
            np.array([
                np.datetime64("2026-07-18T00:00:00", "ns"),
                np.datetime64("2026-07-18T01:00:00", "ns"),
            ]),
        )


if __name__ == "__main__":
    unittest.main()
