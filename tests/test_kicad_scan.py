from kmfdm.config import LibrarySelection, WorkspaceConfig
from kmfdm.gui.main_window import configured_table_items_from_workspace
from kmfdm.parsers.sexpr import parse_sexpressions, sexpr_head
from kmfdm.services.kicad_scan import scan_footprint_library, scan_symbol_library


def test_parse_sexpressions_builds_tree_with_quoted_values() -> None:
    forms = parse_sexpressions('(property "Value" "USB C Connector")')

    assert len(forms) == 1
    assert isinstance(forms[0], list)
    assert sexpr_head(forms[0]) == "property"
    assert forms[0][1:] == ["Value", "USB C Connector"]


def test_scan_symbol_library_extracts_direct_symbol_properties(tmp_path) -> None:
    symbol_path = tmp_path / "CONNECTORs.pretty" / "CONNECTORs.kicad_sym"
    symbol_path.parent.mkdir()
    symbol_path.write_text(
        """
        (kicad_symbol_lib
          (version 20230121)
          (symbol "CONN_HDMI"
            (property "Value" "SS-53000-003")
            (property "MANUFACTURER" "BELFUSE")
            (property "Datasheet" "https://example.test/conn.pdf")
            (symbol "CONN_HDMI_0_0"
              (property "Value" "nested unit should not become an item")
            )
          )
        )
        """,
        encoding="utf-8",
    )

    items = scan_symbol_library(symbol_path)

    assert len(items) == 1
    assert items[0].library == "CONNECTORs.pretty/CONNECTORs.kicad_sym"
    assert items[0].name == "CONN_HDMI"
    assert items[0].fields["Value"] == "SS-53000-003"
    assert items[0].fields["MANUFACTURER"] == "BELFUSE"
    assert items[0].fields["Datasheet"] == "https://example.test/conn.pdf"


def test_scan_footprint_library_extracts_footprint_value_and_properties(tmp_path) -> None:
    footprint_dir = tmp_path / "CONNECTORs.pretty"
    footprint_dir.mkdir()
    footprint_path = footprint_dir / "CONN_HDMI.kicad_mod"
    footprint_path.write_text(
        """
        (footprint "CONN_HDMI"
          (fp_text reference REF** (at 0 0 0) (layer F.SilkS))
          (fp_text value "CONN_HDMI_VALUE" (at 0 0 0) (layer F.Fab))
          (property "MPN" "SS-53000-003")
          (property "ImportedBy" "kicad-import-assistant")
          (model "${CHRIS_KICAD_LIB}/CONNECTORs.pretty/CONN_HDMI.step")
        )
        """,
        encoding="utf-8",
    )

    items = scan_footprint_library(footprint_dir)

    assert len(items) == 1
    assert items[0].library == "CONNECTORs.pretty"
    assert items[0].name == "CONN_HDMI"
    assert items[0].fields["Value"] == "CONN_HDMI_VALUE"
    assert items[0].fields["MPN"] == "SS-53000-003"
    assert items[0].fields["3D Model"] == "${CHRIS_KICAD_LIB}/CONNECTORs.pretty/CONN_HDMI.step"


def test_configured_table_items_use_scanned_kicad_data(tmp_path) -> None:
    symbol_path = tmp_path / "ICs.pretty" / "ICs.kicad_sym"
    symbol_path.parent.mkdir()
    symbol_path.write_text(
        """
        (kicad_symbol_lib
          (symbol "TPS54560"
            (property "Value" "TPS54560")
            (property "MANUFACTURER" "Texas Instruments")
          )
        )
        """,
        encoding="utf-8",
    )
    footprint_path = symbol_path.parent / "TPS54560.kicad_mod"
    footprint_path.write_text(
        """
        (footprint "TPS54560"
          (fp_text value "TPS54560_FOOTPRINT" (at 0 0 0) (layer F.Fab))
          (model "${CHRIS_KICAD_LIB}/ICs.pretty/TPS54560.step")
        )
        """,
        encoding="utf-8",
    )

    symbol_items, footprint_items = configured_table_items_from_workspace(
        WorkspaceConfig(
            symbol_libraries=[LibrarySelection(str(symbol_path))],
            footprint_libraries=[LibrarySelection(str(symbol_path.parent))],
        )
    )

    assert symbol_items[0].name == "TPS54560"
    assert symbol_items[0].library == "ICs.pretty/ICs.kicad_sym"
    assert symbol_items[0].display_library == "ICs"
    assert symbol_items[0].cells["Value"].working_value == "TPS54560"
    assert symbol_items[0].cells["Manufacturer"].working_value == "Texas Instruments"
    assert footprint_items[0].name == "TPS54560"
    assert footprint_items[0].library == "ICs.pretty"
    assert footprint_items[0].display_library == "ICs"
    assert footprint_items[0].cells["Value"].working_value == "TPS54560_FOOTPRINT"
    assert footprint_items[0].metadata_fields["3D Model"] == "${CHRIS_KICAD_LIB}/ICs.pretty/TPS54560.step"
