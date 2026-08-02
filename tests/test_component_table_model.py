from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from kmfdm.config import (
    LibrarySelection,
    PolicyRule,
    WorkspaceConfig,
    load_bundled_policy_profiles,
    load_policy_profile,
    load_workspace_config,
    save_workspace_config,
)
from kmfdm.gui.main_window import (
    ComponentFilterProxyModel,
    ComponentTableModel,
    ConfigurationDialog,
    MainWindow,
    MockItem,
    MultiSelectFilterButton,
    RuleEditorDialog,
    attach_policy_findings_to_mock_items,
    audit_policy_settings_from_profiles,
    configured_symbol_items,
    configured_table_items_from_workspace,
    mock_audit_items,
    mock_footprint_items,
    mock_symbol_items,
    _audit_policy_settings_to_dict,
    _audit_policy_settings_overrides_from_config,
)
from kmfdm.models import CellState, Issue, IssueSeverity
from kmfdm.services.policy_audit import audit_items_against_policies


def test_no_op_edit_does_not_mark_cell_changed() -> None:
    model = ComponentTableModel(mock_symbol_items())
    value_index = model.index(1, model.columns.index("Value"))
    cell = model.items[1].cells["Value"]

    assert not cell.is_changed

    assert model.setData(value_index, "USB-C-16P", Qt.EditRole)

    assert not cell.is_changed


def test_apply_checkbox_can_be_unchecked_and_checked_again() -> None:
    model = ComponentTableModel(mock_symbol_items())
    apply_index = model.index(0, model.columns.index("Apply"))

    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Checked

    assert model.setData(apply_index, Qt.CheckState.Unchecked, Qt.CheckStateRole)
    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Unchecked

    assert model.setData(apply_index, Qt.CheckState.Checked, Qt.CheckStateRole)
    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Checked


def test_policy_finding_attaches_to_matching_mock_cell() -> None:
    symbol_items = mock_symbol_items()
    footprint_items = mock_footprint_items()
    symbol_items[0].cells["MPN"].working_value = "BAD PART NUMBER"
    findings = audit_items_against_policies(
        mock_audit_items(symbol_items, footprint_items),
        load_bundled_policy_profiles(),
    )

    attach_policy_findings_to_mock_items(symbol_items, footprint_items, findings)

    tps_mpn = symbol_items[0].cells["MPN"]
    assert any(issue.rule_name == "Manufacturer part number uses expected characters" for issue in tps_mpn.issues)
    assert any(issue.policy_name == "Manufacturer Part Policy" for issue in tps_mpn.issues)
    assert "Manufacturer part number uses expected characters" in tps_mpn.tooltip_text()
    assert "Policy: Manufacturer Part Policy" in tps_mpn.tooltip_text()


def test_missing_field_policy_finding_does_not_create_mock_cell() -> None:
    symbol_items = mock_symbol_items()
    footprint_items = mock_footprint_items()
    findings = audit_items_against_policies(
        mock_audit_items(symbol_items, footprint_items),
        load_bundled_policy_profiles(),
    )

    attach_policy_findings_to_mock_items(symbol_items, footprint_items, findings)

    assert "Supplier" not in symbol_items[0].cells


def test_hidden_field_policy_finding_attaches_to_visible_cell() -> None:
    symbol_items = mock_symbol_items()
    footprint_items = mock_footprint_items()
    symbol_items[0].metadata_fields = {
        "Value": "TPS54560",
        "Footprint": "ICs:DOES_NOT_EXIST",
    }
    findings = audit_items_against_policies(
        mock_audit_items(symbol_items, footprint_items),
        load_bundled_policy_profiles(),
    )

    attach_policy_findings_to_mock_items(symbol_items, footprint_items, findings)

    assert any(issue.rule_name == "Symbol footprint reference exists" for issue in symbol_items[0].cells["Value"].issues)


def test_component_filter_proxy_limits_rows_by_source_library() -> None:
    model = ComponentTableModel(mock_symbol_items())
    proxy = ComponentFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_enabled_libraries({"Analog"})

    assert proxy.rowCount() == 1
    library_index = proxy.index(0, model.columns.index("Library"))
    assert proxy.data(library_index, Qt.DisplayRole) == "Analog"

    proxy.set_enabled_libraries(set())

    assert proxy.rowCount() == 0


def test_component_filter_proxy_limits_rows_by_status_filters() -> None:
    items = [
        MockItem("Analog", "Changed", {"Value": CellState("old", "new")}),
        MockItem(
            "Analog",
            "Warning",
            {"Value": CellState(issues=[Issue(IssueSeverity.WARNING, "Warn", "")])},
        ),
        MockItem(
            "Analog",
            "Error",
            {"Value": CellState(issues=[Issue(IssueSeverity.ERROR, "Err", "")])},
        ),
        MockItem("Analog", "Clean", {"Value": CellState("clean", "clean")}),
    ]
    model = ComponentTableModel(items)
    proxy = ComponentFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_enabled_libraries({"Analog"})

    assert proxy.rowCount() == 4

    proxy.set_status_filters(unsaved=True, warnings=False, errors=False)

    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, model.columns.index("Name")), Qt.DisplayRole) == "Changed"

    proxy.set_status_filters(unsaved=False, warnings=True, errors=True)

    assert proxy.rowCount() == 2


def test_multi_select_filter_button_select_all_and_none(qtbot) -> None:
    button = MultiSelectFilterButton("Columns", ["Value", "MPN"])
    qtbot.addWidget(button)
    selections = []
    button.selectionChanged.connect(selections.append)

    button.select_none()

    assert button.selected_options() == set()
    assert selections[-1] == set()
    assert button.text() == "Columns: None"

    button.select_all()

    assert button.selected_options() == {"Value", "MPN"}
    assert selections[-1] == {"Value", "MPN"}
    assert button.text() == "Columns: All"


def test_multi_select_filter_button_can_refresh_options(qtbot) -> None:
    button = MultiSelectFilterButton("Source library", ["Analog", "Connectors"])
    qtbot.addWidget(button)

    button.set_options(["CONN.pretty", "GRAPHICS.pretty"])

    assert button.selected_options() == {"CONN.pretty", "GRAPHICS.pretty"}
    assert button.text() == "Source library: All"


def test_configured_symbol_items_use_enabled_workspace_libraries() -> None:
    items = configured_symbol_items(
        [
            LibrarySelection(
                "C:/Users/phoen/Documents/KiCAD/CUSTOM_LIBRARIES_TEST/CONN.pretty/CONN.kicad_sym"
            ),
            LibrarySelection("C:/Users/phoen/Documents/KiCAD/CUSTOM_LIBRARIES_TEST/OLD.kicad_sym", enabled=False),
        ]
    )

    assert [item.library for item in items] == ["CONN.pretty/CONN.kicad_sym"]
    assert items[0].name == "Configured symbol library"
    assert not items[0].auditable
    assert not mock_audit_items(symbol_items=items, footprint_items=[])


def test_main_window_refreshes_table_filters_from_workspace_config(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.workspace_config = WorkspaceConfig(
        layout_profile_id="flat-contained-symbols",
        symbol_libraries=[
            LibrarySelection(str(tmp_path / "CONN.pretty" / "CONN.kicad_sym")),
            LibrarySelection(str(tmp_path / "GRAPHICS.pretty" / "GRAPHICS.kicad_sym")),
        ],
        footprint_libraries=[
            LibrarySelection(str(tmp_path / "CONN.pretty")),
            LibrarySelection(str(tmp_path / "GRAPHICS.pretty")),
        ],
    )

    window._refresh_configured_library_tables()

    assert window.symbol_tab_state.library_filter.selected_options() == {
        "CONN",
        "GRAPHICS",
    }
    assert window.footprint_tab_state.library_filter.selected_options() == {
        "CONN",
        "GRAPHICS",
    }
    assert window.symbol_tab_state.model.rowCount() == 2
    assert window.footprint_tab_state.model.rowCount() == 2


def test_main_window_constructs_before_deferred_library_load(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    symbol_path = tmp_path / "ICs.pretty" / "ICs.kicad_sym"
    symbol_path.parent.mkdir()
    symbol_path.write_text(
        """
        (kicad_symbol_lib
          (symbol "TPS54560" (property "Value" "TPS54560"))
        )
        """,
        encoding="utf-8",
    )
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(
        WorkspaceConfig(
            layout_profile_id="flat-contained-symbols",
            symbol_libraries=[LibrarySelection(str(symbol_path))],
        ),
        config_path,
    )

    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)

    assert window.symbol_tab_state.model.rowCount() == 0
    assert window.symbol_tab_state.inspector.label.text() == "Library data has not loaded yet."


def test_main_window_library_filter_aliases_are_unique(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.workspace_config = WorkspaceConfig(
        layout_profile_id="flat-contained-symbols",
        symbol_libraries=[
            LibrarySelection(str(tmp_path / "GRAPHICS.pretty" / "GRAPHICS.kicad_sym")),
            LibrarySelection(str(tmp_path / "other" / "GRAPHICS.kicad_sym")),
        ],
    )

    window._refresh_configured_library_tables()

    assert window.symbol_tab_state.library_filter.selected_options() == {
        "GRAPHICS (1)",
        "GRAPHICS (2)",
    }


def test_audit_items_include_full_metadata_fields_from_scanned_rows() -> None:
    symbol_items, footprint_items = mock_symbol_items(), mock_footprint_items()
    symbol_items[0].metadata_fields = {
        "Value": "TPS54560",
        "Footprint": "ICs:TPS54560",
    }
    footprint_items[0].metadata_fields = {
        "Value": "TPS54560_FOOTPRINT",
        "3D Model": "${CHRIS_KICAD_LIB}/ICs.pretty/TPS54560.step",
    }

    audit_items = mock_audit_items(symbol_items=symbol_items, footprint_items=footprint_items)

    assert audit_items[0].fields["Footprint"] == "ICs:TPS54560"
    assert audit_items[2].fields["3D Model"] == "${CHRIS_KICAD_LIB}/ICs.pretty/TPS54560.step"
    assert audit_items[0].fields["Value"] == "TPS54560"


def test_audit_items_include_canonical_table_fields_when_raw_metadata_uses_aliases() -> None:
    symbol_items = [
        MockItem(
            "CONNECTORs.pretty/CONNECTORs.kicad_sym",
            "CONN_HDMI",
            {
                "Manufacturer": CellState("Stewart Connector", "Stewart Connector"),
                "MPN": CellState("SS-53000-003", "SS-53000-003"),
            },
            metadata_fields={
                "MANUFACTURER": "Stewart Connector",
                "MPN": "SS-53000-003",
            },
        )
    ]

    audit_item = mock_audit_items(symbol_items=symbol_items, footprint_items=[])[0]

    assert audit_item.fields["MANUFACTURER"] == "Stewart Connector"
    assert audit_item.fields["Manufacturer"] == "Stewart Connector"


def test_manufacturer_required_policy_accepts_displayed_alias_value() -> None:
    symbol_items = [
        MockItem(
            "CONNECTORs.pretty/CONNECTORs.kicad_sym",
            "CONN_HDMI",
            {
                "Manufacturer": CellState("Stewart Connector", "Stewart Connector"),
                "MPN": CellState("SS-53000-003", "SS-53000-003"),
            },
            metadata_fields={
                "MANUFACTURER": "Stewart Connector",
                "MPN": "SS-53000-003",
            },
        )
    ]
    policy = next(
        profile
        for profile in load_bundled_policy_profiles()
        if profile.profile_id == "manufacturer-part-policy"
    )

    findings = audit_items_against_policies(
        mock_audit_items(symbol_items=symbol_items, footprint_items=[]),
        [policy],
    )

    assert not any(finding.rule_id == "manufacturer-required" for finding in findings)


def test_library_validation_policy_defaults_graphics_to_unchecked() -> None:
    symbol_items = [
        MockItem("GRAPHICS.pretty/GRAPHICS.kicad_sym", "SYM_Arrow", {}, library_alias="GRAPHICS"),
        MockItem("CONNECTORs.pretty/CONNECTORs.kicad_sym", "CONN_HDMI", {}, library_alias="CONNECTORs"),
    ]
    footprint_items = [
        MockItem("GRAPHICS.pretty", "Logo", {}, library_alias="GRAPHICS"),
        MockItem("CONNECTORs.pretty", "CONN_HDMI", {}, library_alias="CONNECTORs"),
    ]

    settings = audit_policy_settings_from_profiles(
        load_bundled_policy_profiles(),
        symbol_items,
        footprint_items,
    )["library-validation-policy"]

    assert settings.enabled
    assert settings.apply_to_new_libraries
    assert settings.target == "both"
    assert settings.severity == "warning"
    assert "CONNECTORs.pretty/CONNECTORs.kicad_sym" in settings.enabled_libraries
    assert "CONNECTORs.pretty" in settings.enabled_libraries
    assert "GRAPHICS.pretty/GRAPHICS.kicad_sym" not in settings.enabled_libraries
    assert "GRAPHICS.pretty" not in settings.enabled_libraries


def test_audit_target_and_severity_radio_groups_are_independent(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)

    window.audit_target_symbols.setChecked(True)
    window.audit_severity_error.setChecked(True)

    assert window.audit_target_symbols.isChecked()
    assert window.audit_severity_error.isChecked()


def test_audit_library_table_filters_by_target_and_shows_violation_placeholders(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _install_graphics_and_connector_items(window)
    _select_policy(window, "library-validation-policy")

    rows = _audit_library_rows(window)

    assert rows["GRAPHICS.pretty/GRAPHICS.kicad_sym"]["violations"] == "-"
    assert rows["GRAPHICS.pretty"]["violations"] == "-"
    assert rows["CONNECTORs.pretty/CONNECTORs.kicad_sym"]["violations"] != "-"
    assert rows["CONNECTORs.pretty"]["violations"] != "-"
    assert all(not row["icon_is_null"] for row in rows.values())

    window.audit_target_footprints.setChecked(True)

    rows = _audit_library_rows(window)
    assert set(rows) == {"GRAPHICS.pretty", "CONNECTORs.pretty"}


def test_audit_library_applicability_is_policy_specific(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _install_graphics_and_connector_items(window)

    _select_policy(window, "library-validation-policy")
    _audit_library_item(window, "GRAPHICS.pretty").setCheckState(Qt.CheckState.Checked)
    _audit_library_item(window, "GRAPHICS.pretty/GRAPHICS.kicad_sym").setCheckState(Qt.CheckState.Checked)
    assert "Default applicability" in window.audit_policy_details.label.text()

    _select_policy(window, "datasheet-link-policy")
    _audit_library_item(window, "GRAPHICS.pretty").setCheckState(Qt.CheckState.Unchecked)
    _audit_library_item(window, "GRAPHICS.pretty/GRAPHICS.kicad_sym").setCheckState(Qt.CheckState.Unchecked)
    assert "Related field coverage" in window.audit_policy_details.label.text()

    _select_policy(window, "library-validation-policy")
    assert _audit_library_item(window, "GRAPHICS.pretty").checkState() == Qt.CheckState.Checked
    assert _audit_library_item(window, "GRAPHICS.pretty/GRAPHICS.kicad_sym").checkState() == Qt.CheckState.Checked


def test_rule_editor_regex_preview_reports_pass_fail_and_invalid(qtbot) -> None:
    dialog = RuleEditorDialog(["MPN"])
    qtbot.addWidget(dialog)

    dialog.regex_enabled_checkbox.setChecked(True)
    dialog.regex_input.setText(r"^[A-Z0-9_.-]+$")
    dialog.test_input.setText("TPS54560")

    assert dialog.regex_result.text().startswith("Pass")

    dialog.test_input.setText("bad part")

    assert dialog.regex_result.text().startswith("Fail")

    dialog.regex_input.setText("[")

    assert dialog.regex_result.text().startswith("Invalid regex")


def test_rule_editor_builds_required_field_rule(qtbot) -> None:
    dialog = RuleEditorDialog(["MPN"])
    qtbot.addWidget(dialog)
    dialog.name_input.setText("MPN is present")
    dialog.field_combo.setCurrentText("MPN")
    dialog.required_checkbox.setChecked(True)

    rule = dialog.to_rule(existing_rule_ids=[])

    assert rule.rule_id == "mpn-is-present"
    assert rule.name == "MPN is present"
    assert rule.rule_type == "required_field"
    assert rule.parameters == {"field": "MPN"}


def test_rule_editor_builds_regex_rule_with_blank_handling(qtbot) -> None:
    dialog = RuleEditorDialog(["MPN"])
    qtbot.addWidget(dialog)
    dialog.name_input.setText("MPN shape")
    dialog.field_combo.setCurrentText("MPN")
    dialog.regex_enabled_checkbox.setChecked(True)
    dialog.regex_input.setText(r"^[A-Z0-9_.-]+$")

    rule = dialog.to_rule(existing_rule_ids=[])

    assert rule.rule_type == "regex_check"
    assert rule.parameters["field"] == "MPN"
    assert rule.parameters["pattern"] == r"^[A-Z0-9_.-]+$"
    assert rule.parameters["mode"] == "contains_match"
    assert rule.parameters["ignore_blank"] is True

    dialog.required_checkbox.setChecked(True)

    assert dialog.to_rule(existing_rule_ids=[]).parameters["ignore_blank"] is False


def test_main_window_policy_replacement_persists_workspace_override(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _select_policy(window, "minimal-library-policy")
    profile = window._current_audit_policy()
    assert profile is not None
    rule = PolicyRule(
        rule_id="local-test-rule",
        name="Local Test Rule",
        rule_type="required_field",
        target="both",
        severity="warning",
        save_behavior="advisory",
        parameters={"field": "MPN"},
    )

    window._replace_current_policy(replace(profile, rules=[*profile.rules, rule]))

    policy_path = tmp_path / ".kmfdm-policies" / "minimal-library-policy.json"
    assert not policy_path.exists()
    assert window.audit_policy_list.currentItem().text().endswith(" *")

    window.tabs.setCurrentIndex(2)
    window._save_selected()

    saved_profile = load_policy_profile(policy_path)
    saved_config = load_workspace_config(config_path)
    assert any(saved_rule.rule_id == "local-test-rule" for saved_rule in saved_profile.rules)
    assert saved_config.policy_files == [LibrarySelection(str(policy_path))]
    assert window.audit_policy_list.currentItem().text().endswith(
        f"({len(profile.rules) + 1} rules)"
    )
    reloaded_window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(reloaded_window)
    _select_policy(reloaded_window, "minimal-library-policy")
    assert any(
        saved_rule.rule_id == "local-test-rule"
        for saved_rule in reloaded_window._current_audit_policy().rules
    )


def test_main_window_rule_delete_persists_workspace_override(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _select_policy(window, "minimal-library-policy")
    profile = window._current_audit_policy()
    assert profile is not None
    original_rule_count = len(profile.rules)
    monkeypatch.setattr(
        "kmfdm.gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window._delete_current_rule()

    policy_path = tmp_path / ".kmfdm-policies" / "minimal-library-policy.json"
    assert not policy_path.exists()
    assert len(window._current_audit_policy().rules) == original_rule_count - 1

    window.tabs.setCurrentIndex(2)
    window._save_selected()

    saved_profile = load_policy_profile(policy_path)
    assert len(saved_profile.rules) == original_rule_count - 1
    assert len(window._current_audit_policy().rules) == original_rule_count - 1


def test_main_window_audit_settings_save_and_reload(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _install_graphics_and_connector_items(window)
    _select_policy(window, "datasheet-link-policy")

    window.audit_enabled_checkbox.setChecked(False)
    window.audit_severity_error.setChecked(True)
    _audit_library_item(window, "GRAPHICS.pretty").setCheckState(Qt.CheckState.Unchecked)
    assert window.audit_policy_list.currentItem().text().endswith(" *")

    window.tabs.setCurrentIndex(2)
    window._save_selected()

    reloaded_window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(reloaded_window)
    _install_graphics_and_connector_items(reloaded_window)
    _select_policy(reloaded_window, "datasheet-link-policy")
    settings = reloaded_window._current_audit_policy_settings()
    assert settings is not None
    assert not settings.enabled
    assert settings.severity == "error"
    assert "GRAPHICS.pretty" not in settings.enabled_libraries


def test_main_window_revert_selected_discards_unsaved_audit_settings(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    _install_graphics_and_connector_items(window)
    _select_policy(window, "library-validation-policy")

    _audit_library_item(window, "GRAPHICS.pretty").setCheckState(Qt.CheckState.Checked)
    assert "GRAPHICS.pretty" in window._current_audit_policy_settings().enabled_libraries

    window.tabs.setCurrentIndex(2)
    window._revert_selected()

    settings = window._current_audit_policy_settings()
    assert settings is not None
    assert "GRAPHICS.pretty" not in settings.enabled_libraries
    assert window.audit_policy_list.currentItem().text().endswith("(4 rules)")


def test_audit_action_buttons_follow_selected_policy_dirty_state(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.tabs.setCurrentIndex(2)
    _select_policy(window, "datasheet-link-policy")

    assert not window.save_selected_button.isEnabled()
    assert not window.revert_selected_button.isEnabled()
    assert not window.revert_all_button.isEnabled()

    window.audit_severity_error.setChecked(True)

    assert window.save_selected_button.isEnabled()
    assert window.revert_selected_button.isEnabled()
    assert window.revert_all_button.isEnabled()

    window._save_selected()

    assert not window.save_selected_button.isEnabled()
    assert not window.revert_selected_button.isEnabled()
    assert not window.revert_all_button.isEnabled()


def test_bottom_action_buttons_are_tab_dirty_state_specific(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.symbol_items = [
        MockItem(
            "Analog.pretty/Analog.kicad_sym",
            "TPS54560",
            {"Value": CellState("TPS54560", "TPS54560")},
            library_alias="Analog",
        )
    ]
    window._refresh_library_tab(window.symbol_tab_state, window.symbol_items)
    window.tabs.setCurrentIndex(0)

    assert not window.save_selected_button.isEnabled()
    assert not window.revert_selected_button.isEnabled()
    assert not window.revert_all_button.isEnabled()

    value_index = window.symbol_tab_state.model.index(0, window.symbol_tab_state.model.columns.index("Value"))
    assert window.symbol_tab_state.model.setData(value_index, "TPS54560A", Qt.EditRole)

    assert window.save_selected_button.isEnabled()
    assert window.revert_selected_button.isEnabled()
    assert window.revert_all_button.isEnabled()

    window.tabs.setCurrentIndex(2)

    assert not window.save_selected_button.isEnabled()
    assert not window.revert_selected_button.isEnabled()
    assert not window.revert_all_button.isEnabled()

    window.tabs.setCurrentIndex(0)

    assert window.save_selected_button.isEnabled()
    assert window.revert_selected_button.isEnabled()
    assert window.revert_all_button.isEnabled()


def test_library_tab_status_filter_buttons_show_counts_and_filter_rows(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(WorkspaceConfig(layout_profile_id="flat-contained-symbols"), config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.symbol_items = [
        MockItem("Analog", "Changed", {"Value": CellState("old", "new")}),
        MockItem(
            "Analog",
            "Warning",
            {"Value": CellState(issues=[Issue(IssueSeverity.WARNING, "Warn", "")])},
        ),
        MockItem(
            "Analog",
            "Error",
            {"Value": CellState(issues=[Issue(IssueSeverity.ERROR, "Err", "")])},
        ),
        MockItem("Analog", "Clean", {"Value": CellState("clean", "clean")}),
    ]

    window._refresh_library_tab(window.symbol_tab_state, window.symbol_items)

    assert window.symbol_tab_state.unsaved_filter.text() == "Unsaved: 1"
    assert window.symbol_tab_state.warning_filter.text() == "Warnings: 1"
    assert window.symbol_tab_state.error_filter.text() == "Errors: 1"

    window.symbol_tab_state.warning_filter.setChecked(True)

    assert window.symbol_tab_state.proxy_model.rowCount() == 1

    window.symbol_tab_state.error_filter.setChecked(True)

    assert window.symbol_tab_state.proxy_model.rowCount() == 2


def test_save_selected_writes_symbol_metadata_and_clears_dirty_state(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    symbol_path = tmp_path / "ICs.pretty" / "ICs.kicad_sym"
    symbol_path.parent.mkdir()
    symbol_path.write_text(
        """
        (kicad_symbol_lib
          (symbol "TPS54560"
            (property "Value" "TPS54560")
          )
        )
        """,
        encoding="utf-8",
    )
    config = WorkspaceConfig(
        layout_profile_id="flat-contained-symbols",
        symbol_libraries=[LibrarySelection(str(symbol_path))],
    )
    config_path = tmp_path / ".kmfdm-workspace.json"
    save_workspace_config(config, config_path)
    window = MainWindow(workspace_config_path=config_path)
    qtbot.addWidget(window)
    window.symbol_items, window.footprint_items = configured_table_items_from_workspace(config)
    window._refresh_library_tab(window.symbol_tab_state, window.symbol_items)
    window.tabs.setCurrentIndex(0)

    value_index = window.symbol_tab_state.model.index(0, window.symbol_tab_state.model.columns.index("Value"))
    assert window.symbol_tab_state.model.setData(value_index, "TPS54560A", Qt.EditRole)

    window._save_selected()

    assert '(property "Value" "TPS54560A")' in symbol_path.read_text(encoding="utf-8")
    assert window.symbol_items[0].cells["Value"].original_value == "TPS54560A"
    assert not window.symbol_items[0].cells["Value"].is_changed
    assert not window.save_selected_button.isEnabled()


def test_configuration_dialog_chooses_symbol_library_when_footprint_has_multiple_candidates(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    exact_symbol_library = footprint_library / "Connectors.kicad_sym"
    alternate_symbol_library = footprint_library / "Alternate.kicad_sym"
    footprint_library.mkdir()
    exact_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    alternate_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    dialog = ConfigurationDialog(WorkspaceConfig(layout_profile_id="flat-contained-symbols"))
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "kmfdm.gui.main_window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(alternate_symbol_library), ""),
    )

    symbol_library = dialog._symbol_library_for_footprint(str(footprint_library))

    assert symbol_library == alternate_symbol_library


def test_configuration_dialog_creates_symbol_library_when_footprint_has_no_candidates(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    footprint_library.mkdir()
    dialog = ConfigurationDialog(WorkspaceConfig(layout_profile_id="flat-contained-symbols"))
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "kmfdm.gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    symbol_library = dialog._symbol_library_for_footprint(str(footprint_library))

    assert symbol_library == footprint_library / "Connectors.kicad_sym"
    assert symbol_library.is_file()


def test_configuration_dialog_does_not_create_symbol_library_when_user_declines(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    footprint_library.mkdir()
    dialog = ConfigurationDialog(WorkspaceConfig(layout_profile_id="flat-contained-symbols"))
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "kmfdm.gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    symbol_library = dialog._symbol_library_for_footprint(str(footprint_library))

    assert symbol_library is None
    assert not (footprint_library / "Connectors.kicad_sym").exists()


def _select_policy(window: MainWindow, profile_id: str) -> None:
    for row in range(window.audit_policy_list.count()):
        item = window.audit_policy_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole).profile_id == profile_id:
            window.audit_policy_list.setCurrentRow(row)
            return
    raise AssertionError(f"Policy not found: {profile_id}")


def _install_graphics_and_connector_items(window: MainWindow) -> None:
    window.symbol_items = [
        MockItem(
            "GRAPHICS.pretty/GRAPHICS.kicad_sym",
            "SYM_Arrow",
            {"Value": CellState("", "")},
            library_alias="GRAPHICS",
            metadata_fields={"Value": "SYM_Arrow", "Datasheet": "", "Footprint": ""},
        ),
        MockItem(
            "CONNECTORs.pretty/CONNECTORs.kicad_sym",
            "CONN_HDMI",
            {"Value": CellState("", "")},
            library_alias="CONNECTORs",
            metadata_fields={"Value": "CONN_HDMI", "Datasheet": "", "Footprint": ""},
        ),
    ]
    window.footprint_items = [
        MockItem(
            "GRAPHICS.pretty",
            "Logo",
            {"Value": CellState("", "")},
            library_alias="GRAPHICS",
            metadata_fields={"Value": "Logo", "3D Model": ""},
        ),
        MockItem(
            "CONNECTORs.pretty",
            "CONN_HDMI",
            {"Value": CellState("", "")},
            library_alias="CONNECTORs",
            metadata_fields={"Value": "CONN_HDMI", "3D Model": ""},
        ),
    ]
    window.audit_policy_settings = audit_policy_settings_from_profiles(
        window.policy_profiles,
        window.symbol_items,
        window.footprint_items,
        _audit_policy_settings_overrides_from_config(window.workspace_config),
    )
    window._saved_audit_policy_settings = {
        profile_id: _audit_policy_settings_to_dict(settings)
        for profile_id, settings in window.audit_policy_settings.items()
    }
    window._refresh_policy_findings()


def _audit_library_item(window: MainWindow, library: str):
    for row in range(window.audit_library_table.rowCount()):
        item = window.audit_library_table.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == library:
            return item
    raise AssertionError(f"Audit library row not found: {library}")


def _audit_library_rows(window: MainWindow) -> dict[str, dict[str, object]]:
    rows = {}
    for row in range(window.audit_library_table.rowCount()):
        library_item = window.audit_library_table.item(row, 0)
        violations_item = window.audit_library_table.item(row, 1)
        rows[library_item.data(Qt.ItemDataRole.UserRole)] = {
            "violations": violations_item.text(),
            "icon_is_null": library_item.icon().isNull(),
        }
    return rows
