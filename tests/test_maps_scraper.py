from atlasleads.maps_scraper import _parse_coordinates


def test_parse_coordinates_extracts_lat_lon_from_maps_url():
    url = "https://www.google.com/maps/place/Padaria/@-23.5505,-46.6333,15z/data=..."
    lat, lon = _parse_coordinates(url)
    assert lat == -23.5505
    assert lon == -46.6333
