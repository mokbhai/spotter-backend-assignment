def test_django_settings_load(settings):
    assert "rest_framework" in settings.INSTALLED_APPS
    assert "fuel" in settings.INSTALLED_APPS
    assert "routing" in settings.INSTALLED_APPS
