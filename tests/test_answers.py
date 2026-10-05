"""The forms of a "why" answer: how numbers are printed, which parts of a sum are said, how a cell and a row are
named, and how a place is given (design, Layer 7).

[The fourth check of build step 2 changed causes.py in sixteen ways on purpose, and eight went unnoticed: small parts
of a sum left out, a difference of temperature without its sign, 273 taken off for 273.15, a driver's own unit
passed over, cell 0 and row 0 printed as "none", and north for south or east for west in three places. Each has a
test here; tools/why_scan.py holds the same things against every answer of a built world.]"""
import numpy as np
import pytest

import toy_processes as T
from test_engine_cases import GEO_FIELDS, engine, number, slot
from worldengine.causes import NO_VALUE, WORTH_SAYING, _fmt, as_text, explain
from worldengine.store import MemoryView


@pytest.mark.parametrize("value, unit, said", [
    (300.0, "C_from_K", "26.9 °C"), (273.15, "C_from_K", "0.0 °C"), (250.65, "C_from_K", "-22.5 °C"),      # kelvin, said in degrees Celsius
    (4.56, "K_difference", "+4.6 °C"), (-3.21, "K_difference", "-3.2 °C"), (0.0, "K_difference", "+0.0 °C"),   # a change keeps its sign
    (7.627148522e12, "km2_from_m2", "7,627,149 km²"), (4.6e5, "km2_from_m2", "0 km²"),
    (6.609e12, "km3_from_m3", "6,609 km³"), (2.78e10, "km3_from_m3", "27.8 km³"), (4.75e8, "km3_from_m3", "0.475 km³"),
    (0.5, "percent_from_share", "50 %"), (0.001, "percent_from_share", "under 1 %"), (0.999, "percent_from_share", "over 99 %"),
    (0.0, "percent_from_share", "0 %"), (1.0, "percent_from_share", "100 %"),
    (1234.56, "mm", "1235 mm"), (12.345, "mm", "12.3 mm"), (0.123, "mm", "0.12 mm"), (0.0123, "mm", "0.0123 mm"), (0.0, "mm", "0.00 mm"),
    (3, "", "3"), (np.int32(7), "cells", "7 cells"), (True, "", "true"), (np.bool_(False), "", "false"),
    (float("nan"), "mm", NO_VALUE), (None, "mm", NO_VALUE),
])
def test_a_number_is_printed_in_the_unit_its_pattern_names(value, unit, said):
    assert _fmt(value, unit) == said


POINTER = {"says": "The value is {value} over {span}:", "form": "sum", "drivers": {
    "large": {"says": "the large part gives {v}", "follows": ["ones"], "at": "to_cell"},
    "small": {"says": "the small part gives {v}, from {at}", "at": "to_cell"},
    "tiny": {"says": "the tiny part gives {v}"},
    "to_cell": {"cell": True},
    "to_row": {"row_of": "toy_items", "says": "row {row} holds {value}"},
    "span": {"aside": True, "unit": "km2_from_m2"}}}
POINTER_TABLES = {"tables": {"toy_items": {"columns": {"item": "int32", "value": "float64"}}}}


def pointer_view(target):
    T.Pointer.target = int(target)
    try:
        e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "Pointer": slot("Pointer", ["pointed"]),
                    "Marker": slot("Marker", ["ones", "month_no", "heading"])},
                   {**GEO_FIELDS, "pointed": number()}, tables=POINTER_TABLES)
        w = e.build()
    finally:
        T.Pointer.target = 0
    view = MemoryView(w, e)
    view.attrs["explanations"] = {"Pointer": {"pointed": POINTER}, "Marker": {"ones": {"says": "It is one here, at {lat}, {lon}."}}}
    return view, w.mesh


def in_quarter(mesh, north, east, among=None):
    """A cell well inside one quarter of the planet: north or south, east or west."""
    ok = (mesh.lat * (1 if north else -1) > 10) & (mesh.lon * (1 if east else -1) > 10) & (np.abs(mesh.lon) < 170)
    return int(np.flatnonzero(ok if among is None else ok & among)[0])


def place(mesh, cell):
    lat, lon = mesh.lat[cell], mesh.lon[cell]
    return f"{abs(lat):.1f}° {'N' if lat >= 0 else 'S'}, {abs(lon):.1f}° {'E' if lon >= 0 else 'W'}"


@pytest.mark.parametrize("north, east", [(False, False), (True, False), (False, True), (True, True)])
def test_an_answer_gives_every_place_on_its_own_side_of_the_planet(north, east):
    """Three places of an answer give a latitude and a longitude: its heading, the cell that a driver names ({at}), and
    the first words of a step about another cell. Each is asked in every quarter of the planet, so that north for
    south or east for west shows wherever it is written."""
    view, mesh = pointer_view(0)
    target = in_quarter(mesh, north, east)
    asked = in_quarter(mesh, not north, not east, among=np.arange(mesh.n) >= 10)
    view, mesh = pointer_view(target)
    assert place(mesh, target) != place(mesh, asked) and place(mesh, target)[-1] == ("E" if east else "W")
    answer = explain(view, asked, "pointed")
    text = as_text(answer)
    assert text.splitlines()[0] == f"Why is pointed like this at {place(mesh, asked)} (cell {asked})?"
    assert f"the small part gives 1.00 none, from cell {target}, at {place(mesh, target)}" in answer["chain"][0]["text"]
    there = answer["chain"][1]
    assert there["cell"] == target and there["field"] == "ones"
    lat, lon = mesh.lat[target], mesh.lon[target]
    assert there["text"] == (f"At {place(mesh, target)} (cell {target}), where the cause lies: It is one here, at "
                             f"{abs(lat):.1f}° {'north' if north else 'south'}, {abs(lon):.1f}° {'east' if east else 'west'}.")


def test_a_small_part_of_a_sum_is_said_and_a_part_too_small_to_matter_is_not():
    """A part is said unless it is under WORTH_SAYING of the largest: a hundredth is said, a thousandth is not. What is
    left out is too small to change a figure of the sentence; a part of a fifth left out would make the parts given
    add up to something else than the value."""
    assert WORTH_SAYING == 0.002
    view, mesh = pointer_view(30)
    first = explain(view, 20, "pointed")["chain"][0]
    assert first["text"] == (f"The value is 101.1 none over 3 km²: the large part gives 100.0 none; the small part gives 1.00 none, "
                             f"from cell 30, at {place(mesh, 30)}; row 0 holds 1.00.")
    assert "tiny" not in first["text"] and first["drivers"]["tiny"] == "0.10 none"       # (the step still holds it for the page)


def test_an_amount_is_printed_in_its_drivers_own_unit():
    """The field is in one unit and a driver of it in another (a lake's share of a cell, and the lake's area): the
    driver's unit is the one printed with the driver."""
    view, _ = pointer_view(30)
    first = explain(view, 20, "pointed")["chain"][0]
    assert first["drivers"]["span"] == "3 km²" and "over 3 km²:" in first["text"]
    assert first["drivers"]["large"] == "100.0 none"                                     # one without a unit of its own takes the field's


def test_cell_0_and_row_0_are_a_cell_and_a_row_and_only_a_negative_number_names_none():
    """A driver that names a cell or a row holds -1 for none. Cell 0 is the north pole and row 0 the first row: both
    were at risk of being read as "none"."""
    view, mesh = pointer_view(0)
    first = explain(view, 20, "pointed")["chain"][0]
    assert first["drivers"]["to_cell"] == "cell 0" and first["drivers"]["to_row"] == "row 0 of the table toy_items"
    assert "from cell 0, at 90.0° N, " in first["text"] and "row 0 holds 1.00" in first["text"]
    assert explain(view, 20, "pointed")["chain"][1]["cell"] == 0                         # and the walk goes on at cell 0
    none = explain(view, 3, "pointed")["chain"]                                          # one of the first ten cells, which name no cell
    assert none[0]["drivers"]["to_cell"] == "no other cell" and "from no other cell" in none[0]["text"]
    assert none[1]["cell"] == 3                                                          # the walk stays where it is
