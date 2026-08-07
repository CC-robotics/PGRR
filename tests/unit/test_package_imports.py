def test_package_versions() -> None:
    import ramp_core
    import ramp_ml

    assert ramp_core.__version__ == "0.1.0"
    assert ramp_ml.__version__ == "0.1.0"
