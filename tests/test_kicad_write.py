from pathlib import Path

from kmfdm.services.kicad_scan import scan_footprint_library, scan_symbol_library
from kmfdm.services.kicad_write import KiCadMetadataChange, save_metadata_changes


def test_save_metadata_changes_updates_symbol_property_and_adds_new_property(tmp_path) -> None:
    symbol_path = tmp_path / "ICs.pretty" / "ICs.kicad_sym"
    symbol_path.parent.mkdir()
    symbol_path.write_text(
        """
        (kicad_symbol_lib
          ; keep this comment
          (version 20230121)
          (symbol "TPS54560"
            (property "Value" "TPS54560")
            (property "DATASHEET" "old.pdf")
          )
        )
        """,
        encoding="utf-8",
    )

    save_metadata_changes(
        [
            _change("symbol", symbol_path, "TPS54560", "Datasheet", "https://example.test/new.pdf"),
            _change("symbol", symbol_path, "TPS54560", "MPN", "TPS54560BDDAR"),
        ]
    )

    items = scan_symbol_library(symbol_path)
    saved_text = symbol_path.read_text(encoding="utf-8")
    assert "; keep this comment" in saved_text
    assert '(property "DATASHEET" "https://example.test/new.pdf")' in saved_text
    assert items[0].fields["DATASHEET"] == "https://example.test/new.pdf"
    assert items[0].fields["MPN"] == "TPS54560BDDAR"


def test_save_metadata_changes_updates_footprint_value_and_alias_property(tmp_path) -> None:
    footprint_dir = tmp_path / "ICs.pretty"
    footprint_dir.mkdir()
    footprint_path = footprint_dir / "TPS54560.kicad_mod"
    footprint_path.write_text(
        """
        (footprint "TPS54560"
          (fp_text reference "REF**" (at 0 0 0))
          (fp_text value "TPS54560_OLD" (at 0 0 0))
          (property "MANUFACTURER" "Old Manufacturer")
        )
        """,
        encoding="utf-8",
    )

    save_metadata_changes(
        [
            _change("footprint", footprint_path, "TPS54560", "Value", "TPS54560_NEW"),
            _change("footprint", footprint_path, "TPS54560", "Manufacturer", "Texas Instruments"),
        ]
    )

    items = scan_footprint_library(footprint_dir)
    assert items[0].fields["Value"] == "TPS54560_NEW"
    assert items[0].fields["MANUFACTURER"] == "Texas Instruments"


def _change(
    item_type: str,
    source_path: Path,
    item_name: str,
    field_name: str,
    value: str,
) -> KiCadMetadataChange:
    return KiCadMetadataChange(
        item_type=item_type,
        source_path=source_path,
        item_name=item_name,
        field_name=field_name,
        value=value,
    )
