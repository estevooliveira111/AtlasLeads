from atlasleads.models import Business, BusinessCollection


def test_business_hash_stable_for_identical_data():
    a = Business(name="Padaria Sol", website="https://padariasol.com")
    b = Business(name="Padaria Sol", website="https://padariasol.com")
    assert hash(a) == hash(b)
    assert a == b


def test_business_hash_differs_by_contact_fields():
    a = Business(name="Padaria Sol", website="https://padariasol.com")
    b = Business(name="Padaria Sol", website="https://outrapadaria.com")
    assert a != b


def test_collection_deduplicates_on_add():
    collection = BusinessCollection()
    collection.add(Business(name="Padaria Sol", phone_number="1122223333"))
    collection.add(Business(name="Padaria Sol", phone_number="1122223333"))
    assert len(collection) == 1


def test_collection_keeps_distinct_businesses():
    collection = BusinessCollection()
    collection.add(Business(name="Padaria Sol", phone_number="1122223333"))
    collection.add(Business(name="Mercado Bom Preco", phone_number="1144445555"))
    assert len(collection) == 2


def test_to_dataframe_includes_business_fields():
    collection = BusinessCollection()
    collection.add(Business(name="Padaria Sol", address="Rua A, 100"))
    df = collection.to_dataframe()
    assert list(df["name"]) == ["Padaria Sol"]
    assert list(df["address"]) == ["Rua A, 100"]
