from importlib import resources


def test_kmfdm_icon_resource_exists() -> None:
    icon_path = resources.files("kmfdm").joinpath("resources", "kmfdm.ico")

    assert icon_path.is_file()
